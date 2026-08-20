# Modelo dimensional — SECOP

> Diseño del modelo, con el razonamiento que llevó a cada decisión.
> Se apoya en `00_inventario_fuentes.md`, que contiene la evidencia empírica
> (hallazgos H1 a H7).
> Última actualización: 20 de agosto de 2026 (fin de sesión 3)

---

## 1. Método

Se siguieron los cuatro pasos de Kimball, más dos que el método no incluye:

1. Identificar los procesos de negocio
2. Declarar el grano de cada tabla de hechos
3. Identificar las dimensiones
4. Identificar las medidas
5. Confrontar el diseño contra lo que la fuente puede entregar
6. Escribir el SQL de una pregunta de negocio contra el modelo, antes de codificar

El paso 6 encontró tres problemas que el diagrama no mostraba. Están en la
sección 9.

**Nota de método:** los procesos de negocio se identificaron desde el dominio
(Ley 80, Ley 1150, funcionamiento de SECOP II), no leyendo el esquema. El orden
importa. Si se derivan los procesos de las columnas disponibles, se asume que la
fuente registró todo lo que ocurre, y en esta fuente no es cierto: el proceso de
pago existe y no tiene ninguna columna de fecha que lo acompañe. Ese hallazgo
solo es visible si se sabe de antemano que los pagos ocurren.

---

## 2. Procesos de negocio

| Proceso | Verbo | Mediciones | ¿Registrado como evento? |
|---|---|---|---|
| Ciclo de vida del contrato | se firma, inicia, termina, se liquida | valor, duración, fechas de hito | **Sí.** `fecha_de_firma` marca el nacimiento |
| Modificación contractual | se adiciona, prorroga, cede, suspende | días adicionados, delta de valor | **No.** El resultado sobrescribe la fila |
| Ejecución financiera | se factura, se paga | facturado, pagado, pendiente, amortizado | **No.** Solo el acumulado a hoy, sin fecha |

Tres procesos reales. Uno observable como evento.

Los procesos 2 y 3 no dejan rastro legible, pero sí son observables como
**diferencia entre dos observaciones consecutivas**. Si el 1 de septiembre
`valor_pagado` es 5M y el 1 de octubre es 8M, hubo pagos por 3M en septiembre,
aunque nadie lo haya registrado.

Ambos se miden sobre el mismo objeto (el contrato) en el mismo momento de corte,
así que comparten una sola tabla.

De ahí salen dos tablas de hechos y no una ni tres.

---

## 3. Tablas de hechos y grano

### `fct_contratos`

> **Una fila = un contrato estatal firmado, en su estado más reciente conocido.**

- Llave: `id_contrato`, verificada en H1 por dos métodos independientes.
- Tipo: snapshot acumulativo. La fila se actualiza en su lugar cuando el contrato
  avanza de etapa.

Consecuencias operativas:

- **Idempotencia:** se carga con `MERGE` sobre `id_contrato`. Con `INSERT` se
  duplica.
- **Backfill:** reprocesar un rango histórico recalcula el presente, no
  reconstruye el pasado, porque el pasado ya no existe en la fuente. El backfill
  de esta tabla es de cobertura, no de historia.

### `fct_contratos_snapshot`

> **Una fila = el estado de un contrato en una fecha de corte.**

- Llave: `id_contrato` + `valido_desde`
- Tipo: snapshot periódico, almacenado como SCD tipo 2 (ver sección 4).

Universo: solo los contratos que todavía pueden cambiar. Sumando de H5:

| Estado | Filas |
|---|---|
| En ejecución | 1.737.502 |
| Modificado | 1.081.413 |
| Suspendido | 6.650 |
| Prorrogado | 120 |
| **Total** | **2.825.685** |

Antes del filtro 2020+.

**Suposición sin verificar:** que los estados terminales (Cerrado, terminado,
Cancelado) ya no cambian. Es razonable pero no está probado. Un contrato Cerrado
podría recibir pagos rezagados. Verificar antes de excluirlos del refresco
diario.

---

## 4. Frecuencia de observación y de almacenamiento

Son dos decisiones distintas y se confunden con facilidad:

- **Cada cuánto se mira** determina la resolución de detección.
- **Cada cuánto se guarda** determina el costo de almacenamiento.

### Decisión: mirar diario, guardar solo cuando algo cambió

Comparación de las alternativas de almacenamiento:

| | Denso (foto completa por período) | Solo cambios (SCD2) |
|---|---|---|
| Filas por año | Mensual: ~34M · Diario: ~1.000M | Del orden de 1 a 3M |
| Resolución | La del período | Diaria |
| Consulta "estado al 1 de marzo" | `WHERE fecha_snapshot = '2026-03-01'` | `WHERE '2026-03-01' BETWEEN valido_desde AND valido_hasta` |

El denso diario queda descartado por volumen: mil millones de filas al año,
mayormente copias idénticas de la fila anterior. El denso mensual es más cómodo
de consultar pero no distingue dos modificaciones ocurridas dentro del mismo mes.

Guardar solo los cambios da resolución diaria a costo menor que el mensual denso.
No es trabajo adicional: la capa raw tiene que decidir igual qué conserva de cada
extracción nocturna.

**Costo aceptado:** las consultas con `BETWEEN` sobre rangos de validez son más
difíciles de escribir que una igualdad. Si un mart necesita la comodidad del
formato denso, se genera desde esta tabla con dbt.

---

## 5. Clasificación de columnas para detección de cambios

Comparar las 87 columnas genera una versión nueva cada vez que la fuente corrige
un espacio. Comparar solo los valores monetarios pierde las cesiones. Hace falta
un criterio.

| Categoría | Definición | Comportamiento |
|---|---|---|
| **Material** | Cambió el contrato en el mundo real, y alguna pregunta de negocio lo necesita | Genera versión nueva |
| **Cosmética** | Cambió el registro, no el contrato (tildes, "No definido" que se llena) | Se pisa el valor actual, sin versión |
| **Imposible** | No debería cambiar nunca | No se compara. Si cambia, dispara alerta |

La prueba para separar material de imposible: *si esta columna cambia mañana,
¿quiero una alarma o quiero un registro?* Imposible es solo para las que
justifican una alarma.

### Materiales

`estado_contrato`, `valor_del_contrato`, `valor_pagado`, `valor_facturado`,
`valor_pendiente_de_pago`, `valor_pendiente_de_ejecucion`, `valor_amortizado`,
`valor_de_pago_adelantado`, `saldo_cdp`, `saldo_vigencia`, las cinco fuentes de
financiación, `dias_adicionados`, `fecha_de_fin_del_contrato`,
`fecha_inicio_liquidacion`, `fecha_fin_liquidacion`,
`fecha_de_notificaci_n_de_prorrogaci_n`, `duraci_n_del_contrato`,
`liquidaci_n`, `ultima_actualizacion`, `proveedor_adjudicado`,
`documento_proveedor`, `codigo_proveedor`.

Cuatro casos que no son obvios:

- **`valor_pagado`** es la columna que justifica el proyecto. Si no genera
  versión, los 735.809 contratos con pagos siguen sin serie temporal, la tabla
  de snapshots queda casi vacía y ningún test falla. Es el error más caro
  posible en este diseño.
- **Las cinco fuentes de financiación** son materiales porque RN1 exige que su
  suma iguale `valor_del_contrato`. Si el valor sube por una adición y las
  fuentes no versionan, quedan versiones históricas donde RN1 no se cumple.
- **`fecha_de_fin_del_contrato`** se corre con cada prórroga. Es el mismo evento
  que registra `dias_adicionados`, visto desde el otro lado.
- **El trío del proveedor** cambia con la cesión. H5 documenta 28.557 contratos
  en estado `cedido`.

Las **fechas de liquidación y prórroga** arrancan nulas y se llenan cuando el
hito ocurre. Pasar de nulo a fecha es el cambio más informativo que existe en un
snapshot acumulativo.

### Imposibles (disparan alerta)

`id_contrato`, `fecha_de_firma`, `fecha_de_inicio_del_contrato`,
`proceso_de_compra`, `nit_entidad`, `codigo_entidad`,
`codigo_de_categoria_principal`.

Si alguna cambia, o hay un error en la fuente o se reasignó un `id_contrato`.
En ambos casos conviene enterarse, no generar una versión en silencio.

### Cosméticas

El resto. Con dos precauciones:

- `objeto_del_contrato` y `descripcion_del_proceso` pueden cambiar con una
  modificación de alcance, pero son texto libre largo con saltos de línea
  embebidos y truncamiento (H6). Si se comparan, normalizar primero.
- `direcci_n_de_ejecuci_n_del_contrato` se deja como cosmética: el ruido supera
  la ganancia.

### Fuera del pipeline

Todo el bloque de datos personales (representante legal, ordenador del gasto,
supervisor, ordenador de pago, datos bancarios) se excluye desde la extracción
por la decisión de H7. No se clasifica porque no entra. El filtro corre antes de
la comparación de cambios.

---

## 6. Dimensiones

Salieron de subrayar los "por", "según" y "para cada" en las preguntas de
negocio.

### `dim_entidad`

**Grano: `codigo_entidad`, no `nit_entidad`.**

Evidencia: el DANE aparece con un solo NIT (899999027) y tres `codigo_entidad`
distintos, correspondientes a sus territoriales Norte, Centro Oriente y
Noroccidente.

Para el usuario comercial la dependencia es el cliente: es la que ejecuta
presupuesto y firma. "El DANE" no compra nada. Y como `nit_entidad` queda como
atributo agrupador, sumar por persona jurídica es un `GROUP BY` de distancia.
Al revés no se podría.

Problemas conocidos a resolver en `staging`:

- `nit_entidad` viene con y sin dígito de verificación (`8002469532` frente a
  `800098911`). Normalizar antes de usarlo para agrupar.
- `nombre_entidad` trae caracteres pegados: `Gobernación Norte de Santander*`,
  `SUBRED ... E.S.E.**`, `... PUERTO CARREÑO1`. No sirve como llave.
- `orden`, `rama` y `sector` no son confiables (H6 documenta un hospital
  departamental marcado como "Nacional" y una ESE marcada como "Corporación
  Autónoma"). Entran como atributos con la advertencia documentada. No se
  construye lógica de negocio encima.

### `dim_proveedor`

**Una sola dimensión, con `tipo_persona` derivado.**

La pregunta abierta de H6 era si separar persona natural de persona jurídica.
Con `tipodocproveedor` no se puede: en una muestra de 35 filas apareció una
S.A.S. marcada como "Cédula de Ciudadanía" y una persona natural marcada como
"NIT". El campo falla en ambas direcciones.

`tipo_persona` se deriva con reglas propias (longitud y rango del documento,
patrones en el nombre como SAS, LTDA, S.A., cruce con `es_pyme`) y se documenta
como inferido.

Dos dimensiones separadas obligarían a dos llaves foráneas en el hecho, una
siempre nula.

**Pendiente:** decidir si la llave es `documento_proveedor` o `codigo_proveedor`.
Probablemente aplica el mismo patrón que en la entidad, pero no se verificó.

### `dim_categoria`

`codigo_de_categoria_principal` es un código UNSPSC. Hay que quitar el prefijo
`V1.` y desplegar los cuatro niveles de la jerarquía:

```
V1.80111701 → segmento 80 → familia 8011 → clase 801117 → producto 80111701
```

La jerarquía es lo que hace utilizable el mart. Un vendedor de servicios de TI
no busca el código exacto, busca su familia.

### `dim_tiempo`

Generada con SQL, no viene de la fuente. Con atributos de año, trimestre, mes y
día hábil. Sirve para la pregunta 4, el pico de diciembre.

### `dim_modalidad`

`modalidad_de_contratacion`, `tipo_de_contrato` y `justificacion_modalidad_de`.
Pocos valores, la necesita la pregunta 5.

---

## 7. Medidas y aditividad

Cada medida pasa tres filtros: ¿es numérica?, ¿es cierta a este grano?,
¿es aditiva?

### En `fct_contratos`: todas aditivas

`valor_del_contrato` y las cinco fuentes de financiación. Un contrato aparece
una sola vez, no hay eje temporal en el que pueda repetirse.

Se agrega `conteo_contratos = 1` en cada fila, para contar sin
`COUNT(DISTINCT)`.

### En `fct_contratos_snapshot`: todas semiaditivas

`valor_del_contrato`, `valor_pagado`, `valor_facturado`,
`valor_pendiente_de_pago`, `valor_pendiente_de_ejecucion`, `valor_amortizado`,
`saldo_cdp`, `saldo_vigencia`, `dias_adicionados`.

Semiaditiva significa que se suman entre entidades y categorías, pero **no a
través del tiempo**. Ejemplo con un contrato:

| Corte | Pendiente de pago |
|---|---|
| 31-ene | $10M |
| 28-feb | $7M |
| 31-mar | $4M |

Lo que se debe en el trimestre es $4M, el último valor. Un tablero que sume la
columna devuelve $21M, que no corresponde a nada. No falla nada: sale un número
con signo de pesos en una celda.

**Regla: entre entidades y categorías se suma; a través del tiempo se toma el
último valor.**

Que todas las medidas sean semiaditivas es la firma de una tabla de snapshots:
mide estados, no eventos.

### Medidas derivadas: de estado a flujo

```
pago_del_periodo   = valor_pagado(corte)        − valor_pagado(corte anterior)
delta_valor        = valor_del_contrato(corte)  − valor_del_contrato(corte ant.)
```

Estas **sí son plenamente aditivas**, porque son flujos.

Esto es lo que hace la plataforma: convierte estados semiaditivos que la fuente
publica y sobrescribe en flujos aditivos que no existen en ninguna fuente
pública. La serie de pagos de los 735.809 contratos sale de acá.

Se calculan en la capa `intermediate` y se materializan en el mart. No se dejan
al tablero.

### No aditivas: no se guardan

`porcentaje_de_ejecucion` y similares. Si se guarda el porcentaje por contrato y
el tablero lo promedia, un contrato de $5.000 pesa igual que uno de $50.000
millones.

Se guardan numerador y denominador; la división va al final:

```sql
SUM(valor_pagado) / NULLIF(SUM(valor_del_contrato), 0)
```

**Regla: razones, porcentajes y promedios se calculan después de agregar.**

### Nota sobre `duraci_n_del_contrato`

Todavía no es una medida. Llega como texto libre: `"2 Mes(es)"`,
`"135 Dia(s)"`, `"No definido"`. Se parsea a `duracion_dias` en `staging`, con
una columna `duracion_dias_valida` para los casos que fallen, en lugar de
descartar la fila.

---

## 8. Decisión sobre SCD tipo 2

**El versionado se aplica sobre el hecho, no sobre una dimensión.**

SCD tipo 2 consiste en guardar versiones con período de validez en lugar de
sobrescribir. La técnica es la misma en los dos casos; lo que cambia es dónde se
aplica.

En esta fuente las dimensiones casi no se mueven. Una entidad cambia de nombre
cada tanto, un proveedor pasa de PyME a no PyME. Lo que cambia todos los días,
en millones de filas, es el contrato: su valor, su estado, su plazo, su
proveedor tras una cesión.

`fct_contratos_snapshot` con `valido_desde` y `valido_hasta` **es** SCD tipo 2,
aplicado donde está el movimiento.

**Alternativa considerada y descartada:** `dim_proveedor` en SCD2. Cumpliría el
requisito formal del punto 5 de la definición de terminado, sin capturar lo que
realmente cambia.

Esto reemplaza el punto 5 de la definición de terminado, que pedía "una
dimensión en SCD tipo 2".

---

## 9. Validación del modelo (paso 6)

Se escribió el SQL de la pregunta 7 contra el modelo propuesto, antes de escribir
dbt.

### El error que apareció en el primer intento

Partir de la tabla de versiones y unir directo contra las dimensiones produce
*fan-out*: un contrato con tres adiciones aparece tres veces, y
`SUM(valor_del_contrato)` lo cuenta tres veces. Los deltas están bien porque son
flujos; lo que se rompe es mezclar una medida de flujo con una de estado en el
mismo `SELECT`.

**Regla:** al partir de una tabla versionada, primero se agrega al grano de
contrato, después se une con las dimensiones.

### Consulta corregida

```sql
with versiones as (
    select
        id_contrato,
        valido_desde,
        valor_del_contrato,
        lag(valor_del_contrato) over (
            partition by id_contrato order by valido_desde
        ) as valor_version_anterior
    from fct_contratos_snapshot
),

deltas as (
    select
        id_contrato,
        valor_del_contrato - valor_version_anterior as delta_valor
    from versiones
    where valor_version_anterior is not null
      and valor_del_contrato <> valor_version_anterior
),

por_contrato as (                      -- vuelve al grano de contrato
    select
        id_contrato,
        sum(delta_valor) as pesos_adicionados,
        count(*)         as n_adiciones
    from deltas
    group by 1
)

select
    e.nombre_entidad,
    c.familia_unspsc,
    count(*)                    as contratos_con_adicion,
    sum(p.n_adiciones)          as adiciones_totales,
    sum(p.pesos_adicionados)    as pesos_adicionados,
    sum(f.valor_del_contrato)   as valor_actual_total,

    sum(p.pesos_adicionados)
      / nullif(sum(f.valor_del_contrato - p.pesos_adicionados), 0) as sobrecosto

from por_contrato p
join fct_contratos f  on f.id_contrato  = p.id_contrato
join dim_entidad   e  on e.sk_entidad   = f.sk_entidad
join dim_categoria c  on c.sk_categoria = f.sk_categoria
group by 1, 2
having sum(p.pesos_adicionados) > 0
order by sobrecosto desc
```

El resultado se lee directo: en esta familia UNSPSC, esta entidad adiciona X%
sobre el valor inicial.

### Tres hallazgos que el diagrama no mostraba

**1. `sk_proveedor` va en el snapshot.** Entidad y categoría son columnas
imposibles, así que leerlas de `fct_contratos` es correcto. El proveedor cambia
con la cesión. Si se lee de `fct_contratos` se obtiene siempre el proveedor
actual y se pierde quién ejecutaba cuando ocurrió la adición.

> `fct_contratos_snapshot` lleva `sk_proveedor`. Entidad y categoría no se
> repiten por versión.

**2. La primera versión de cada contrato no sirve para calcular deltas.** El
filtro `where valor_version_anterior is not null` la descarta. La consecuencia no
es técnica: si el contrato se adicionó antes de que el pipeline arrancara, esa
adición ya viene incorporada en la primera foto y es invisible.

El universo medible es "contratos que cambiaron de valor mientras los
observábamos". Debe quedar escrito en la documentación del mart, o el número se
lee como si fuera un total nacional.

**3. Falta `fecha_primer_snapshot` en `fct_contratos`.** Sin ella no se puede
distinguir "no tuvo adiciones" de "tuvo adiciones que no vimos".

> Los análisis de delta se restringen a contratos donde
> `fecha_primer_snapshot <= fecha_de_firma + margen`. Son los observados desde el
> nacimiento, los únicos con historia completa. Sin esa restricción el mart
> mezcla dos poblaciones y subestima el sobrecosto.

### Veredicto

El modelo sobrevive. Dos de los hallazgos son ajustes de columnas y uno es una
nota metodológica. Ninguno obliga a rediseñar.

La misma consulta, cambiando `valor_del_contrato` por `dias_adicionados`,
responde la pregunta 6 en días. Cambiando por `valor_pagado`, produce la serie
mensual de ejecución financiera.

---

## 10. Reglas de negocio para tests de dbt

| ID | Regla | Origen |
|---|---|---|
| RN1 | La suma de las fuentes de financiación iguala `valor_del_contrato` | H6 |
| RN2 | Ningún registro de la tabla de hechos tiene estado pre-firma | H4, H5 |
| RN3 | Ningún registro de la tabla de hechos tiene `fecha_de_firma` nula | H3, H4 |
| RN4 | La fuente no tiene más de 48 horas de rezago | Sesión 2 |
| RN5 | `valor_pagado` no decrece entre versiones consecutivas | Sesión 3 |
| RN6 | RN1 se cumple en toda versión histórica, no solo en la fila actual | Sesión 3 |
| RN7 | `dias_adicionados` y `fecha_de_fin_del_contrato` cambian juntos | Sesión 3 |

RN5 es interesante en los dos resultados posibles: si decrece, o hubo reversión
de un pago o la fuente tiene un error. Ambos casos valen la pena.

---

## 11. Limitaciones conocidas

Van al README, no se esconden.

1. **`fct_contratos_snapshot` empieza vacía.** No se puede backfillear: la
   historia previa no existe en ninguna fuente pública. La tabla madura con el
   tiempo.
2. **Los deltas solo son válidos para contratos observados desde su firma.**
   Ver hallazgo 2 de la sección 9.
3. **El backfill de `fct_contratos` es de cobertura, no de historia.**
4. **`orden`, `rama` y `sector` no son confiables** y están documentados como
   tales.
5. **`tipo_persona` es inferido**, no viene de la fuente.
6. **Análisis restringido a 2020 en adelante** (decisión de H3). Antes de esa
   fecha la curva mide adopción de SECOP II, no gasto público.

---

## 12. Preguntas abiertas

Heredadas del inventario, más las nuevas:

1. ¿`Cerrado` (1,69M) y `terminado` (774K) son sinónimos?
2. ¿Qué miden `orden` y `rama`? El diccionario los define de forma circular.
3. ¿Los estados terminales realmente no cambian? Determina si se excluyen del
   refresco diario.
4. ¿La llave de `dim_proveedor` es `documento_proveedor` o `codigo_proveedor`?
5. ¿Qué contienen `fecha_de_inicio_de_ejecucion`, `fecha_fin_liquidacion` y
   `estado_bpin`, que el diccionario documenta pero no aparecieron en la
   muestra?

**Hipótesis descartada en la sesión 3:** se probó que `dias_adicionados > 0`
identificara a los contratos en estado `Modificado`. La consulta devolvió miles
de contratos `Modificado` con cero días adicionados. `Modificado` cubre
modificaciones de valor, cesiones y otros eventos que no dejan huella en ninguna
columna. Refuerza la pregunta 7: hay más historia destruida de la que sugería el
inventario.
