# Modelo dimensional: SECOP

> Diseño del modelo, con el razonamiento que llevó a cada decisión.
> Se apoya en `00_inventario_fuentes.md` (evidencia empírica H1-H9 y H34) y en
> `02_ecosistema_secop.md` (los datasets hermanos, H17-H33) y
> `03_decisiones_capa_raw.md` (las decisiones D1-D8, D10, D11 e I1-I5).
> **Cómo leerlo:** sección 0 es un glosario de los términos de modelado; los del
> dominio están en el glosario del inventario. Este documento dice **qué** se
> decidió y da una frase de por qué; el razonamiento completo de las decisiones
> de la capa raw vive en `03_decisiones_capa_raw.md`, y desde acá se lo
> referencia con ->.
>
> **H10 a H16 no existen**: nunca se asignaron, y este documento los citaba como
> si existieran. Los hallazgos de la fuente principal son H1-H9 y H34.
>
> Última revisión: 28 de agosto de 2026.

---

## 0. Glosario

Términos de modelado que este documento usa constantemente. **Los del dominio y
del pipeline (grano, watermark, backfill, SCD tipo 2, las capas de dbt,
freshness, columna material, UNSPSC, ESE, SMLMV) están en el glosario de
`00_inventario_fuentes.md`.** Acá van solo los que no están allá.

**Modelo dimensional**: forma de organizar datos para analizarlos, no para
operarlos. En vez de decenas de tablas normalizadas, unas pocas tablas grandes
de *hechos* rodeadas de tablas chicas de *dimensiones*. Se lee rápido y se
entiende sin ser ingeniero.

**Tabla de hechos**: la tabla del medio, con lo que se mide: valores, conteos,
días. Una fila por cada cosa que ocurrió.

**Dimensión**: las tablas de alrededor, con el contexto por el que se filtra y
se agrupa: qué entidad, qué proveedor, qué categoría, qué fecha. Responden los
"por" y los "según" de una pregunta de negocio.

**Kimball**: Ralph Kimball, el autor cuyo método de cuatro pasos se sigue en la
sección 1. Es el enfoque estándar para diseñar modelos dimensionales.

**Snapshot acumulativo**: una foto que se **pisa**: la fila se actualiza en su
lugar y solo refleja el presente. Así es `fct_contratos`.

**Snapshot periódico**: fotos que se **acumulan**: cada observación se guarda
además de las anteriores, así se puede mirar hacia atrás. Así es
`fct_contratos_snapshot`.

 **"Periódico" no quiere decir "regular".** Kimball llama así al patrón por
oposición al acumulativo, no porque el período sea fijo. Acá el período lo marca
la fuente, que se regenera de forma irregular (H34), así que las observaciones
llegan a intervalos desiguales. El patrón es el mismo; lo que no se puede es leer
la palabra como una promesa de cadencia.

**Surrogate key** (`sk_`): una llave inventada por el pipeline, normalmente un
número, que reemplaza a la llave de la fuente para unir tablas. Se usa porque
las llaves reales cambian de formato, se reciclan o son largas. Todas las
columnas que empiezan con `sk_` son esto.

**Aditiva / semiaditiva / no aditiva**: si una medida se puede sumar o no.
Aditiva se suma por cualquier eje; semiaditiva se suma entre entidades pero no a
través del tiempo; no aditiva no se suma nunca (porcentajes, promedios). Está
desarrollado en la sección 7.

**CTE** (*common table expression*): el `with nombre as (...)` de SQL. Un
resultado intermedio con nombre, para partir una consulta larga en pasos
legibles en vez de anidar subconsultas.

**Fan-out**: cuando un `join` multiplica filas sin querer. Si un contrato tiene
tres versiones y se une con una tabla de una fila por contrato, el valor de ese
contrato se cuenta tres veces. Es el error de la sección 9.

**`MERGE`**: instrucción SQL que inserta la fila si no existe y la actualiza si
ya está. Es lo que permite correr la carga dos veces sin duplicar.

**Idempotencia**, que correr algo dos veces dé el mismo resultado que correrlo
una. Sin esto, un reintento de Airflow duplica datos.

**Materialización incremental**: en dbt, recalcular solo las filas nuevas o
cambiadas en vez de reconstruir la tabla entera cada vez.

**`--full-refresh`**: la opción de dbt que ignora lo incremental y reconstruye
la tabla desde cero. Es lo que permite corregir el pasado cuando se arregla un
error de transformación.

**Ventana de reproceso**: cuántos días hacia atrás recalcula una carga
incremental en cada corrida. Cubre las llegadas tardías sin rehacer todo.

**CDP**: Certificado de Disponibilidad Presupuestal. Documento colombiano que
reserva plata del presupuesto antes de firmar un contrato. `saldo_cdp` es lo que
queda de esa reserva.

**PyME**: pequeña y mediana empresa. La fuente lo trae como marca en
`es_pyme`.

---

## 1. Método

Se siguieron los cuatro pasos de Kimball (ver sección 0), más dos que el método no
incluye:

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
| Modificación contractual | se adiciona, prorroga, cede, suspende | días adicionados, delta de valor | **Sí, pero sin medidas.** Ver nota abajo |
| Ejecución financiera | se factura, se paga | facturado, pagado, pendiente, amortizado | **No.** Solo el acumulado a hoy, sin fecha |

Tres procesos reales. Uno observable como evento **con sus medidas**.

**Por qué "sí, pero sin medidas".** La modificación contractual **sí** queda
registrada como evento, en un dataset aparte que no es evidente mirando la
fuente principal: `SECOP II - Adiciones` (`cb9c-h8sn`), con una fila por
modificación, su tipo y una justificación en texto libre.

Pero no sirve para medir. No tiene **ninguna columna de valor** (el monto está
enterrado en la prosa (H17)) y su única fecha **trunca mes y día al primer
dígito significativo** (H33): el día solo sobrevive en el 16,8% de las filas.

Lo que descarta el dataset es la **ausencia de la medida**, no el estado de la
fecha. Aunque `fecharegistro` estuviera intacta, seguiría sin haber una columna
de valor, y las preguntas 6 y 7 necesitan pesos. La fecha truncada agrava.

O sea: el Estado publica el evento sin la medida; esta plataforma reconstruye la
medida sin el evento. Por eso el proceso 2 sigue necesitando la comparación
entre observaciones.

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

**Construida el 29/08/2026.** 2.849.209 contratos, 27 columnas, 10,9 s. Sale de
filtrar `es_version_vigente` sobre el snapshot, así que las dos tablas son
consistentes por construcción y no por coincidencia. Eso obligó a que el snapshot
llevara `fecha_de_firma`, que no tenía.

**El `MERGE` de arriba no se implementó, y conviene decir por qué.** Ese `MERGE`
protege contra duplicar cuando se **insertan deltas**, y acá no se insertan
deltas: se filtra una tabla que ya se reconstruyó entera. La idempotencia sale de
la construcción y no de la estrategia de carga, que es más fuerte. Cuando el
pipeline pase a incremental (D5), esta tabla pasa con él y ahí sí la estrategia es
`merge`, que existe en los dos adaptadores (D9).

**El filtro de 2020 de H3 tampoco está acá, y es deliberado.** H3 dice "el
análisis de **los marts**", y los filtros de negocio de este proyecto van lo más
tarde posible, donde son reversibles. `fct_contratos` es el inventario completo de
lo que el pipeline conoce; 71.512 de sus contratos son anteriores a 2020. La
contracara hay que anotarla: un mart que se olvide del recorte no falla, mezcla
2016 con 2025 y devuelve una comparación interanual inválida.

### `fct_contratos_snapshot`

> **Una fila = el estado de un contrato tal como fue OBSERVADO en una fecha de
> extracción.**

La palabra "observado" es deliberada y es más débil que "el estado en una
fecha". La plataforma no sabe cuándo cambió el contrato: sabe cuándo el cambio
se volvió visible, con una resolución igual a la frecuencia del barrido (D8).
Prometer más sería inventar.

 **Y la frecuencia del barrido está acotada por arriba por la de la fuente**,
que es irregular (H34). `observado_desde` marca cuándo lo vimos nosotros; de qué
corte de la fuente venía ese estado se registra aparte, en el manifiesto de la
partición (D10 en `03_decisiones_capa_raw.md`). Son dos fechas distintas y hasta
el 28 de agosto solo existía la primera.

- Llave: `id_contrato` + `observado_desde`
- Tipo: snapshot periódico, almacenado como SCD tipo 2 (ver sección 4).

**Esa llave tiene un supuesto que nadie había escrito: que un contrato aparece
a lo sumo una vez por `fecha_extraccion`.** Si aparece dos veces (el flujo 1 lo
trae por la mañana, el contrato cambia, y el flujo 3 lo trae esa misma noche) las
dos escrituras son correctas y aun así `id_contrato + observado_desde` deja de ser
única.

El efecto sobre el SCD2 es peor que un duplicado. La primera versión queda con
`observado_desde == observado_hasta`, y bajo los intervalos semiabiertos de D8
**no corresponde a ningún instante**: está en la tabla, la cuenta cualquier
`count(*)`, y ninguna consulta puntual puede seleccionarla. Dos respuestas sobre
el mismo contrato discrepan y nada falla.

Y hay un segundo efecto, que toca D5: con un empate, `order by observado_en` no
tiene orden definido, así que **cuál de las dos observaciones queda como versión 1
no está garantizado** entre corridas ni entre motores. La propiedad de que el
hecho sea *función de raw* (se borra, se corre `dbt build --full-refresh` y sale
idéntico) deja de estar garantizada.

**Medido el 29/08/2026: cero empates sobre 2.902.163 observaciones.** Pero el
mecanismo está vivo: el 22 de agosto ya hubo tres particiones bajo la misma
`fecha_extraccion`, una por flujo, y el índice de hashes es global por contrato
(D3), así que lo único que hace falta es que el contrato cambie entre las dos
corridas, que es justo cuando queremos guardarlo. **Raw hace lo correcto; el que
no sabe representarlo es el modelo**, porque su resolución temporal es el día.

Lo vigila `fct_una_observacion_por_contrato_y_fecha` en severidad `error`. Qué se
hace cuando salte queda en la pregunta abierta 10.

Columnas de control, con la decisión que las originó:

| Columna | Decisión | Para qué |
|---|---|---|
| `observado_desde` / `observado_hasta` | D8 | Intervalo **semiabierto**: `>= desde AND < hasta`. Nulo en `hasta` = versión abierta |
| `motivo_de_cierre` | D8 | `version_nueva` / `abierta` / `fuera_de_observacion`. **Implementada el 29/08/2026** |
| `sk_proveedor` | sección 9, hallazgo 1 | El proveedor cambia con la cesión; entidad y categoría no |

**`motivo_del_cambio` salió de esta tabla y pasó a ser un modelo propio**,
`int_cambios_por_columna`, con grano de una fila por contrato, versión y columna
que cambió. Estaba escrito como una columna del hecho y **no cabe en una**: medido
el 29/08/2026, de los 32.431 contratos con dos versiones solo **12.838 (el
39,6%) cambiaron exactamente una columna material**; el resto cambió entre 2 y
**12 a la vez**. Un motivo escalar describiría mal seis de cada diez versiones.

Y hay una razón de modelado además de la medición: 28 banderas en el hecho no son
ni llaves ni fechas ni medidas, y ensancharlo es justo lo que R3 mostró que cuesta
caro. La tabla larga son 88.395 filas contra 2,88 millones del hecho.

El modelo lleva además los dos deltas ya calculados (`delta_valor` en pesos o días
adicionados, `delta_dias` en días de corrimiento de fecha) en columnas separadas,
porque pesos y días no se suman entre sí. Con eso las preguntas 6 y 7 salen sin
recalcular, que era lo que la fila de esta tabla prometía.

`motivo_de_cierre` existe porque un contrato que pasa a estado terminal deja de
ser barrido, y su última versión queda con `observado_hasta` nulo para siempre.
Sin esa columna, el nulo significaría tres cosas distintas: un fallo silencioso
esperando.

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
Cancelado) ya no cambian, y por eso quedan fuera del universo. Es razonable pero
no está probado: ver la pregunta abierta 3.

---

## 4. Frecuencia de observación y de almacenamiento

Son dos decisiones distintas y se confunden con facilidad:

- **Cada cuánto se mira** determina la resolución de detección.
- **Cada cuánto se guarda** determina el costo de almacenamiento.

### Decisión: mirar en cada regeneración, guardar solo cuando algo cambió

**Esta decisión decía "mirar diario", y la palabra "diario" no describe lo que
pasa.** La fuente se regenera de forma irregular: en nueve días observados hubo
tres regeneraciones y cuatro días sin ninguna, con saltos de dos y de cinco días
entre cortes conocidos (H34, en `00_inventario_fuentes.md`). Lo que sí se decide
acá sigue en pie: **mirar tan seguido como la fuente se mueva, y guardar solo
cuando algo cambió.** Lo que cambia es la resolución que el modelo puede
prometer.

Comparación de las alternativas de almacenamiento:

| | Denso (foto completa por período) | Solo cambios (SCD2) |
|---|---|---|
| Filas por año | Mensual: ~34M / Diario: ~1.000M | Del orden de 1 a 3M |
| Resolución | La del período | **La de la fuente**: como mucho la de sus regeneraciones |
| Consulta "estado al 1 de marzo" | `WHERE fecha_snapshot = '2026-03-01'` | `WHERE observado_desde <= '2026-03-01' AND (observado_hasta > '2026-03-01' OR observado_hasta IS NULL)` |

El denso diario queda descartado por volumen: mil millones de filas al año,
mayormente copias idénticas de la fila anterior. El denso mensual es más cómodo
de consultar pero no distingue dos modificaciones ocurridas dentro del mismo mes.

Guardar solo los cambios da la máxima resolución que la fuente permite, a costo
menor que el mensual denso. No es trabajo adicional: la capa raw tiene que
decidir igual qué conserva de cada extracción.

 **La resolución la fija la fuente y el modelo no puede superarla.** Entre dos
regeneraciones separadas por cinco días, dos modificaciones del mismo contrato
son indistinguibles: llegan juntas en el mismo corte. Es exactamente el defecto
que se le critica al denso mensual, solo que impuesto desde afuera y no elegido.
El modelo aguanta (D8 ya había decidido no prometer resolución diaria) pero
**el README tiene que decir que la serie tiene la resolución de la fuente, con
huecos, y no una resolución diaria**.

**Hay dos filtros, no uno** (D3 y D6). Conviene no confundirlos:

| Filtro | Dónde | Qué decide | Finura |
|---|---|---|---|
| Bytes idénticos | Python, antes de escribir raw | Si la fila se guarda en disco | Grueso |
| Clasificación material | dbt, sobre `staging` | Si la fila **merece una versión** | Fino |

El primero descarta el ~99% que no cambió en nada y baja el volumen de raw de
~250 GB/año a **~1 GB/año**, medido comprimiendo filas reales (los nombres de
columna se repiten en cada línea, así que el JSONL comprime unas 47 veces).

El segundo filtro sigue siendo imprescindible: una fila puede cambiar en bytes
sin cambiar materialmente: una tilde corregida en `nombre_entidad` es
cosmética. Esa distinción solo la sabe `columnas.py`.

 **La trampa del `BETWEEN`.** Escribir esa consulta como
`WHERE '2026-03-01' BETWEEN observado_desde AND observado_hasta` es el reflejo
natural, y está **mal**: `BETWEEN` incluye los dos extremos, y los intervalos de
D8 son **semiabiertos**. El día de frontera aparecería en dos versiones y
cualquier suma lo contaría dos veces.

Es el mismo criterio de `_rango()` en `flujos.py`: cerrado a la izquierda,
abierto a la derecha, en los dos extremos del pipeline.

**Costo aceptado:** las consultas sobre rangos de validez son más
difíciles de escribir que una igualdad. Si un mart necesita la comodidad del
formato denso, se genera desde esta tabla con dbt.

---

## 5. Clasificación de columnas para detección de cambios

Comparar las 85 columnas genera una versión nueva cada vez que la fuente corrige
un espacio. Comparar solo los valores monetarios pierde las cesiones. Hace falta
un criterio.

| Categoría | Definición | Comportamiento |
|---|---|---|
| **Material** | Cambió el contrato en el mundo real, y alguna pregunta de negocio lo necesita | Genera versión nueva |
| **Cosmética** | Cambió el registro, no el contrato (tildes, "No definido" que se llena) | No genera versión. Ver la corrección de abajo |
| **Imposible** | No debería cambiar nunca | No se compara. Si cambia, dispara alerta |

#### Cuánto vale la distinción, medido el 28/08/2026

D6 tenía un argumento y ahora tiene un número. Entre el barrido del 23 y la
corrida del 25, la fuente publicó **52.954 contratos cambiados** (lo que raw
detecta comparando bytes sobre las 67 columnas). De esos, el SCD2 generó versión
para **32.431**.

**Los otros 20.523 cambiaron algo que no es el contrato: el 38,8%.**

Cuatro de cada diez veces que SECOP publica un contrato como cambiado, al
contrato no le pasó nada. Sin la clasificación de D6, la serie temporal tendría
un 60% más de filas y ninguna información adicional.

**Y casi todo ese ruido es un solo evento, no ruido difuso.**
`entidad_centralizada` explica 20.675 de los 20.523 (el exceso son contratos que
además cambiaron algo material), y son seis entidades reclasificadas de golpe.
Ver `00_inventario_fuentes.md`.

Eso matiza el 38,8%: es una medición de **un** intervalo, dominada por un evento
administrativo puntual. Con más regeneraciones ingeridas el número va a moverse,
y la cifra estable todavía no se conoce.

**"Se pisa el valor actual" era una descripción equivocada, y se corrige el
28/08/2026 al implementar el snapshot.** Esa frase describe un SCD2 de
dimensiones, donde hay una sola fila por entidad y pisarla tiene sentido.
`fct_contratos_snapshot` es un **snapshot acumulativo**: no existe "la fila
actual" que pisar, hay una fila por cada versión conservada.

Lo que ocurre de verdad: **el valor cosmético queda congelado en el de la
observación que abrió la versión.** Si una entidad se renombra y el contrato no
cambia nada material, la tabla de hechos sigue mostrando el nombre viejo.

Es deliberado. Una fila del snapshot dice *"así se veía este contrato cuando lo
observamos"*, y con las 67 columnas viniendo de la misma observación eso es
literalmente cierto: se vieron juntas, el mismo día, en la misma respuesta. Tomar
las cosméticas de una observación posterior haría que la fila mezclara dos
momentos sin que nada lo advirtiera, y rompería la trazabilidad con `hash`, que
es el hash de los bytes de **una** observación.

**Para el valor al día está la dimensión**, unida por su llave IMPOSIBLE. El
nombre viejo en la tabla de hechos no molesta porque nadie debería leerlo de ahí.

Lo que sí se pierde es **cuándo** cambió una cosmética. Ninguna pregunta de
negocio lo necesita, pero es una pérdida y no un efecto neutro.

La prueba para separar material de imposible: *si esta columna cambia mañana,
¿quiero una alarma o quiero un registro?* Imposible es solo para las que
justifican una alarma.

**La lista exacta vive en `src/secop_analytics/columnas.py`**, que es la fuente
de verdad única: 28 materiales, 7 imposibles, 32 cosméticas y 18 personales, y
un test verifica que las cuatro sean una partición exacta de las 85. Este
documento explica el criterio; el módulo guarda la lista. Duplicarla acá crearía
la desincronización que ese módulo se escribió para evitar.

### Cómo se compara

**Columna por columna, con `IS DISTINCT FROM`.** No con un hash de las 28
materiales juntas.

`IS DISTINCT FROM` en vez de `!=` porque en SQL `NULL != NULL` no da verdadero,
da `NULL`, y tres materiales arrancan nulas y se llenan, que es el cambio más
informativo del snapshot.

Columna por columna en vez de hash porque produce **`motivo_del_cambio`**: saber
*qué* cambió, no solo *que* algo cambió. Eso responde las preguntas 6 y 7
directamente, y deriva la clasificación del delta observado en lugar de confiar
en la etiqueta que escribió cada entidad, que H26 mostró que no es de fiar.

Las monetarias se comparan sobre el valor numérico, no sobre el texto:
`"1000"` contra `"1000.00"` daría un cambio falso.

*Razonamiento completo y alternativas descartadas en `03_decisiones_capa_raw.md`, D6.*

### Materiales

`estado_contrato`, `valor_del_contrato`, `valor_pagado`, `valor_facturado`,
`valor_pendiente_de_pago`, `valor_pendiente_de_ejecucion`, `valor_amortizado`,
`valor_de_pago_adelantado`, `valor_pendiente_de`, `saldo_cdp`,
`saldo_vigencia`, **las seis** fuentes de financiación, `dias_adicionados`, `fecha_de_fin_del_contrato`,
`fecha_inicio_liquidacion`, `fecha_fin_liquidacion`,
`fecha_de_notificaci_n_de_prorrogaci_n`, `duraci_n_del_contrato`,
`liquidaci_n`, `ultima_actualizacion`, `proveedor_adjudicado`,
`documento_proveedor`, `codigo_proveedor`.

Cuatro casos que no son obvios:

- **`valor_pagado`** es la columna que justifica el proyecto. Si no genera
  versión, los 735.809 contratos con pagos siguen sin serie temporal, la tabla
  de snapshots queda casi vacía y ningún test falla. Es el error más caro
  posible en este diseño.
- **`duraci_n_del_contrato` no es un número**: trae la unidad pegada al valor
  (`"6 Mes(es)"`, `"180 Dia(s)"`) y ningún valor castea a entero. Cinco unidades
  conviven en la misma columna, así que el número solo no significa nada:
  `"1 Año(s)"` y `"365 Dia(s)"` son la misma duración con cifras que difieren 365
  veces. Queda como texto en `staging`. Para duración real están las dos fechas
  del contrato, que son fechas de verdad.
- **`liquidaci_n` es booleana**, no un hito que arranca nulo: `"No"` en
  2.611.371 filas y `"Si"` en 290.792, sin un solo nulo. Es material porque el
  paso de `"No"` a `"Si"` es un cambio de estado real, no porque se llene una
  fecha. Estaba clasificada con el motivo de los hitos y no le aplicaba.
- **Las seis fuentes de financiación** son materiales porque RN1 exige que su
  suma iguale `valor_del_contrato`. Si el valor sube por una adición y las
  fuentes no versionan, quedan versiones históricas donde RN1 no se cumple.
  (Son seis, no cinco, y las seis entran en la suma: medido el 28/08 contra raw: ver sección 10.)
- **`fecha_de_fin_del_contrato`** se corre con cada prórroga. Es el mismo evento
  que registra `dias_adicionados`, visto desde el otro lado.
- **El trío del proveedor** se clasificó como material porque cambia con la
  cesión. **Medido el 29/08/2026, el trío no se mueve junto**: el nombre cambió
  en 513 contratos, el documento en 61 y `codigo_proveedor` en **uno**. Ver la
  pregunta abierta 11.

Las **fechas de liquidación y prórroga** arrancan nulas y se llenan cuando el
hito ocurre. Pasar de nulo a fecha es el cambio más informativo que existe en un
snapshot acumulativo.

#### Qué cambia de verdad: medido el 29/08/2026

Sobre los 32.431 contratos que tienen dos versiones, cuántos cambiaron cada
material:

| Columna | Contratos |
|---|---|
| `valor_pendiente_de_pago` | 18.510 |
| `valor_pendiente_de_ejecucion` | 18.431 |
| `valor_facturado` | 18.123 |
| `valor_pagado` | 16.539 |
| `ultima_actualizacion` | 2.853 |
| `estado_contrato` | 2.528 |
| `fecha_de_fin_del_contrato` | 2.227 |
| `dias_adicionados` | 2.083 |
| `valor_del_contrato` | 1.925 |
| ... | cola larga hasta 1 |

**Las cuatro de arriba son la ejecución financiera de H9**, el mecanismo que el
inventario probó que ninguna columna de fecha registra. Y `valor_facturado` sola
explica 10.419 de los 12.838 casos en que cambió una sola columna. O sea: **el
evento más frecuente que el pipeline captura es exactamente el que la fuente no
registra.** H9 decía que ese mecanismo existe y era invisible; ahora está contado.

**Las 28 cambiaron al menos una vez.** Ninguna sobra en la clasificación, que era
una duda razonable con una lista armada en parte por deducción.

**La muestra es un intervalo de entre 2 y 5 días y una sola regeneración
ingerida.** Las proporciones entre columnas pueden moverse mucho con más cortes;
lo que no se mueve es que ninguna quedó en cero.

### Imposibles (disparan alerta)

`id_contrato`, `fecha_de_firma`, `fecha_de_inicio_del_contrato`,
`proceso_de_compra`, `nit_entidad`, `codigo_entidad`,
`codigo_de_categoria_principal`.

Si alguna cambia, o hay un error en la fuente o se reasignó un `id_contrato`.
En ambos casos conviene enterarse, no generar una versión en silencio.

#### Medido el 29/08/2026: cinco no cambian, una sí

Es la primera evidencia empírica de D7 en todo el proyecto. Comparando versiones
consecutivas de los 32.431 contratos que tienen más de una:

| Columna | Cambios |
|---|---|
| `codigo_de_categoria_principal` | 0 |
| `codigo_entidad` | 0 |
| `nit_entidad` | 0 |
| `proceso_de_compra` | 0 |
| `fecha_de_firma` | 0 |
| **`fecha_de_inicio_del_contrato`** | **685** |

**Y el desglose dice que no es una alerta, es una clasificación equivocada.**
De los 685: **648 van de nulo a fecha**, **cero** de fecha a nulo, y solo **37**
son mutaciones reales, con mediana de 1 día y rango de -31 a +42.

O sea que `fecha_de_inicio_del_contrato` **no es una columna inmutable que se
rompió: es un hito que se llena**, exactamente como
`fecha_inicio_liquidacion`, `fecha_fin_liquidacion` y
`fecha_de_notificaci_n_de_prorrogaci_n`, que están clasificadas como
**MATERIALES**, y de las que este mismo documento dice que *"pasar de nulo a
fecha es el cambio más informativo que existe en un snapshot acumulativo"*.

Es el error simétrico al de `liquidaci_n`: aquella estaba clasificada como hito y
resultó booleana; ésta está clasificada como inmutable y resulta ser un hito.
**Reclasificarla a material es una decisión pendiente**: ver la pregunta abierta
12.

El control de que la medición vale: el mismo conteo hecho sobre **todas** las
observaciones de `stg_contratos`, y no solo sobre las que generaron versión, da
**el mismo número**. Ninguna transición quedó invisible, porque cuando un
contrato arranca también cambia algo material.

**Qué hace la alerta.** La fila **entra normalmente**; la discrepancia se guarda
en una tabla de alertas con los dos valores, y un test de dbt la reporta. No se
bloquea la carga ni se pone la fila en cuarentena: bloquear detendría la ingesta
entera porque una entidad corrigió un error de tipeo, y una alerta que para el
pipeline enseña a desactivarla.

El valor que queda en la versión abierta es el **nuevo**, igual que una
cosmética. Las versiones históricas conservan lo observado entonces.

Todos los tests arrancan en severidad `warn` y suben a `error` recién cuando se
sepa cuántas veces se disparan de verdad.

*Razonamiento completo en `03_decisiones_capa_raw.md`, D7.*

 `id_contrato` es distinta de las otras seis: es la llave por la que se unen
las observaciones, así que su modo de fallo no es la mutación sino la
**duplicación**. Lo captura un test de unicidad, no la comparación de cambios.

### Cosméticas

Las 32 restantes, agrupadas por lo que alimentan. El detalle está en
`columnas.py`; acá va la forma:

| Grupo | Cuántas | Ejemplos |
|---|---|---|
| Atributos de `dim_entidad` | 5 | `nombre_entidad`, `orden`, `rama`, `sector` |
| Atributos de `dim_proveedor` | 3 | `tipodocproveedor`, `es_pyme`, `es_grupo` |
| Atributos de `dim_modalidad` | 3 | `modalidad_de_contratacion`, `tipo_de_contrato` |
| Texto libre | 5 | `objeto_del_contrato`, `descripcion_del_proceso` |
| Geografía | 4 | `departamento`, `ciudad`, `localizaci_n` |
| Marcas de política pública | 6 | `espostconflicto`, `obligaci_n_ambiental`, `reversion` |
| Casos que hubo que evaluar uno por uno | 6 | `origen_de_los_recursos`, `destino_gasto`, `urlproceso` |

 **No clasificar por descarte.** La tentación es escribir "material e imposible
son estas, el resto es cosmética" y seguir. Las seis del último grupo parecían
obviamente cosméticas y al mirarlas una por una resultaron serlo **por razones
distintas entre sí**, y dos quedaron con pendientes abiertos. Una categoría
definida como "todo lo demás" no está definida.

Con dos precauciones:

- `objeto_del_contrato` y `descripcion_del_proceso` pueden cambiar con una
  modificación de alcance, pero son texto libre largo con saltos de línea
  embebidos y truncamiento (H6). Si se comparan, normalizar primero.
- `direcci_n_de_ejecuci_n_del_contrato` se deja como cosmética: el ruido supera
  la ganancia.
- `urlproceso` llega como objeto anidado `{"url": "..."}` y trae un tercer
  identificador (`noticeUID=CO1.NTC.xxx`) que no aparece en ninguna otra
  columna. Se aplana en `staging` y el `noticeUID` sale a columna propia: es
  probablemente la llave hacia el dataset de Procesos de Contratación.
- Dos cumplen la primera condición de material y fallan la segunda (ninguna
  pregunta necesita saber *cuándo* cambiaron): `el_contrato_puede_ser_prorrogado`
  y `habilita_pago_adelantado`. Sirven mejor como tests de coherencia sobre la
  fila actual (RN9 y RN10).

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
V1.80111701 -> segmento 80 -> familia 8011 -> clase 801117 -> producto 80111701
```

La jerarquía es lo que hace utilizable el mart. Un vendedor de servicios de TI
no busca el código exacto, busca su familia.

**Construida el 29/08/2026, sin nombres.** 11.231 códigos, **401 familias** y
**56 segmentos**, sin historia: medido: `codigo_de_categoria_principal` cambió
cero veces.

> **Corregido el 01/09/2026: eran 401 y 56, no 402 y 57.** La cifra vieja contaba
> el nulo de `UNSPECIFIED` como una familia y como un segmento. No lo es: es el
> centinela que no tiene jerarquia, y el modelo lo deja nulo a proposito. Lo
> destapo la prueba de paridad entre motores, que usa `count(distinct ...)` y por
> eso excluye el nulo, contra una cifra documentada que lo incluia.
>
> Es la regla de siempre en otra forma: **un conteo depende de como se cuente, y
> eso hay que escribirlo al lado del numero.**

**La jerarquía se deriva del código; lo único que falta comprar son los
nombres.** El inventario lista el catálogo UNSPSC como dato externo pendiente, y
lo sigue siendo, pero eso cambia qué bloquea: sin el catálogo la pregunta 1 no se
puede **leer**, y sí se puede **agrupar**. El usuario objetivo conoce su propia
familia. Cuando llegue, entra como `seed` y la dimensión gana columnas de nombre
sin que nada más cambie.

**25.597 contratos (el 0,9%) no tienen categoría**, y la columna reporta cero
nulos: traen el centinela `UNSPECIFIED`, en inglés, que la limpieza de `staging`
no toca. Ver `00_inventario_fuentes.md`.

### `dim_tiempo`

Generada con SQL, no viene de la fuente. Con atributos de año, trimestre, mes y
día hábil. Sirve para la pregunta 4, la estacionalidad de apertura.

**"El pico de diciembre" es una expectativa heredada, no una medición**, y
hay un indicio en contra. El control de H33 sobre `fecha_de_firma` (una columna
sana) dio **17,4% de contratos firmados entre octubre y diciembre**, cuando lo
uniforme sería 25%. Parte se explica porque 2026 está a mitad de camino y no
aporta ningún cuarto trimestre, así que el número no es concluyente; pero
apunta al revés de lo que la frase asume. La pregunta 4 tiene que **medir** la
estacionalidad, no confirmarla: si el mart se construye buscando el pico de
diciembre, va a encontrarlo.

### `dim_modalidad`

`modalidad_de_contratacion`, `tipo_de_contrato` y `justificacion_modalidad_de`.
Pocos valores, la necesita la pregunta 5.

---

## 7. Medidas y aditividad

Cada medida pasa tres filtros: ¿es numérica?, ¿es cierta a este grano?,
¿es aditiva?

### En `fct_contratos`: todas aditivas

`valor_del_contrato` y las seis fuentes de financiación. Un contrato aparece
una sola vez, no hay eje temporal en el que pueda repetirse.

Se agrega `conteo_contratos = 1` en cada fila, para contar sin
`COUNT(DISTINCT)`.

### En `fct_contratos_snapshot`: todas semiaditivas

`valor_del_contrato`, `valor_pagado`, `valor_facturado`,
`valor_pendiente_de_pago`, `valor_pendiente_de_ejecucion`, `valor_amortizado`,
`valor_de_pago_adelantado`, `valor_pendiente_de`, `saldo_cdp`,
`saldo_vigencia`, `dias_adicionados`.

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
pago_del_periodo = valor_pagado(observación)       - valor_pagado(anterior)
delta_valor      = valor_del_contrato(observación) - valor_del_contrato(anterior)
```

"Observación", no "corte": el período que cubre cada delta es el que va entre
dos barridos, no un mes calendario (D8).

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

`fct_contratos_snapshot` con `observado_desde` y `observado_hasta` **es** SCD
tipo 2, aplicado donde está el movimiento.

**`dbt snapshot`, la funcionalidad nativa, no sirve acá**, por dos razones: compara
contra la tabla destino en vez de contra raw (lo que impediría corregir el pasado
con un `--full-refresh`), y no tiene forma de expresar una clasificación de tres
vías: no hay manera de decirle "estas 32 columnas pisan el valor actual sin
generar versión".

*Razonamiento completo en `03_decisiones_capa_raw.md`, D5.*

El SCD2 se implementa a mano: la lógica compara contra la observación anterior
**en raw**, y la materialización es incremental con ventana de reproceso. Es
material de README, no una carencia:

> `dbt snapshot` no soporta columnas cosméticas, así que el SCD2 está
> implementado a mano, con la clasificación generada desde `columnas.py`.

**Las cosméticas pisan solo la versión abierta**, no las históricas. Si pisaran
todas, un `--full-refresh` reconstruido desde raw daría un resultado distinto,
porque el reproceso sí ve la historia de nombres. Efecto que se acepta: las
versiones viejas muestran nombres de entidad desactualizados. La solución no es
pisar la historia: el mart une contra `dim_entidad` por la llave y toma el
nombre actual. Ese es el trabajo de una dimensión.

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
        observado_desde,
        valor_del_contrato,
        lag(valor_del_contrato) over (
            partition by id_contrato order by observado_desde
        ) as valor_version_anterior
    from fct_contratos_snapshot
),

deltas as (
    select
        id_contrato,
        valor_del_contrato - valor_version_anterior as delta_valor
    from versiones
    where valor_version_anterior is not null
      and valor_del_contrato is distinct from valor_version_anterior
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

**Nota:** con `motivo_del_cambio` el `where` del CTE `deltas` se acorta una
línea, pero el `lag()` sigue haciendo falta: el motivo dice *qué* columna
cambió, no *cuánto*. La consulta se deja como está: es el artefacto del ejercicio
que encontró los tres hallazgos de abajo, y reescribirla borraría ese registro.

 `delta_valor` **puede ser negativo**: existe el tipo `REDUCCION EN EL VALOR`
en el dataset oficial de modificaciones (H27). El `having` filtra los positivos
para la pregunta del sobrecosto, pero ninguna lógica de deltas debe asumir
monotonía en `valor_del_contrato`.

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

**Implementada el 29/08/2026, y el número que produjo es incómodo.**
`fct_contratos` lleva `fecha_primer_snapshot` y `dias_hasta_el_primer_snapshot`,
que mide el hueco entre la firma y la primera observación:

| Margen | Contratos con historia completa | % |
|---|---|---|
| 0 días | **0** | 0% |
| 7 días | **11.066** | **0,39%** |
| 30 días | 76.245 | 2,7% |

Mediana del hueco: **657 días**. Máximo: 3.876, o sea diez años y medio. **El
99,6% del hecho tiene la historia truncada por la izquierda.**

**Y el margen no puede ser cero, por construcción.** El mínimo observado es de
**un día** y no de cero: ningún contrato se ve el mismo día en que se firma,
porque la fuente publica con ~1 día de rezago (H8). Escribir la restricción con
margen cero deja el universo vacío por una propiedad de la fuente y no por falta
de datos.

El margen no se fija en el hecho a propósito: es decisión del mart, y hornearlo
acá lo volvería invisible. Lo que sí es del hecho es exponer el hueco medido.

Este número **crece solo** con cada regeneración ingerida, y es la forma concreta
de la limitación 1 de sección 11 ("`fct_contratos_snapshot` empieza vacía y madura con el
tiempo"). Lo que no se puede es esconderlo.

### El mart, construido el 29/08/2026

`mart_extension_de_plazo` responde las dos preguntas. La consulta de arriba se
acortó bastante: los deltas ya vienen calculados desde
`int_cambios_por_columna`, así que **no hay ningún `lag()`**: es lo que D6
compró al comparar columna por columna en vez de guardar un hash.

**Grano: entidad, familia UNSPSC y `historia_completa`.** El tercer eje es el
hallazgo 2 de esta sección convertido en columna, y hay que explicar por qué está
en el grano y no en un `where`.

Sobre contratos firmados desde 2020:

| | Contratos | Entidades |
|---|---|---|
| Extendieron el plazo, sin restricción | 2.227 | 421 |
| Extendieron el plazo, con historia completa | **193** | **88** |
| Adicionaron valor, sin restricción | 1.925 | 358 |
| Adicionaron valor, con historia completa | **39** | **29** |

**Con 39 contratos en 29 entidades (1,3 cada una) la palabra
"sistemáticamente" no se sostiene.** Y usar los 1.925 sin decir nada es
exactamente lo que el hallazgo 2 advierte: mezcla contratos cuya historia vimos
entera con otros de los que vimos una semana.

Ninguna de las dos poblaciones responde bien la pregunta hoy, y **esa es la
respuesta honesta**. Por eso están separadas por grano: cada celda declara a cuál
pertenece, ninguna consulta las mezcla por descuido, y las dos traen su tamaño al
lado. La población medible **crece sola** con cada regeneración ingerida, sin que
el modelo cambie.

**Y el primer resultado del mart destapó un defecto del propio mart: el plazo
también se acorta.** Una celda mostraba *"12 extensiones, -12 días"*, que no es
una extensión de nada. Medido: de los 2.227 cambios de
`fecha_de_fin_del_contrato`, **2.131 alargaron el plazo (+134.296 días) y 96 lo
acortaron (-2.351)**. Sumarlos en neto esconde dos poblaciones y le pone el
nombre de una a la mezcla.

Es **H27 en el otro eje**. Para el valor ya estaba anotado que puede bajar (el
dataset oficial de modificaciones tiene un tipo `REDUCCION EN EL VALOR`) y para
el plazo nadie lo había dicho. Medido, del lado del valor son **101 reducciones
de 1.925**, con -1.027 millones contra +121.078.

El mart separa los cuatro conteos (`extensiones` / `acortamientos`,
`adiciones` / `reducciones`) y guarda el neto aparte, que es el que responde
"cuánto se encareció". Al corregirlo, la entidad que encabezaba el ranking de la
pregunta 6 desapareció de él.

**Regla que sale de esto: en una tabla de deltas, nunca agregar en neto una
columna cuyo nombre afirme el signo.**

**El margen es de 30 días y no puede ser cero** (ver el hallazgo 3). Con 7 días
serían 748 contratos con algún cambio; con 30, 1.616.

**El filtro de 2020 de H3 vive acá**, que es donde H3 dijo. Hoy casi no muerde:
de los 2.227 contratos que extendieron el plazo, 1.940 se firmaron en 2026 y 240
en 2025; uno solo es de 2020 y ninguno anterior. Los contratos que se modifican
ahora son los recientes, pero la tabla madura y el histórico entra.

Lo que el mart todavía no puede decir: **nombres** de categoría, que esperan el
catálogo UNSPSC.

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
| RN1 | La suma de las **seis** fuentes de financiación iguala `valor_del_contrato` | H6 |
| RN2 | Ningún registro de la tabla de hechos tiene estado pre-firma | H4, H5 |
| RN3 | Ningún registro de la tabla de hechos tiene `fecha_de_firma` nula | H3, H4 |
| RN4 | **Umbral sin fijar.** Decía 48 horas de rezago (`freshness`); el 28/08 una fuente sana llevaba tres días sin regenerar, así que ese umbral habría alertado sobre ella. Falta decidir el número y **contra qué columna se mide**: `ultima_actualizacion` mide el rezago del negocio, `:updated_at` mide si la fuente se regeneró | H8, H34 |
| RN5 | `valor_pagado` no decrece entre versiones consecutivas | H9: es un acumulado |
| RN6 | RN1 se cumple en toda versión histórica, no solo en la fila actual | RN1 + diseño SCD2 |
| RN7 | `dias_adicionados` y `fecha_de_fin_del_contrato` cambian juntos | Dominio: son el mismo evento |
| RN8 | `valor_de_pago_adelantado = valor_amortizado + valor_pendiente_de` | Diccionario oficial |
| RN9 | Si `el_contrato_puede_ser_prorrogado = "No"`, entonces `dias_adicionados = 0` | Coherencia interna |
| RN10 | Si `habilita_pago_adelantado = "No"`, entonces `valor_de_pago_adelantado = 0` | Coherencia interna |
| RN11 | Las adiciones no superan el 50% del valor inicial, en SMLMV al momento de la firma | Ley 80 art. 40 |
| RN12 | Si `fecha_fin_liquidacion` no es nula, `fecha_inicio_liquidacion` tampoco | Coherencia interna, medida |
| RN13 | `valor_del_contrato` no supera el Presupuesto General de la Nación | PGN 2026: 546,9 billones |

**RN1 quedó cerrada el 28/08/2026: son las seis.** Se midió contra raw, sobre
las 2.824.446 filas del barrido del 23, con `scripts/medir_rn1.py`. La sexta
(`recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_`) trae valor
distinto de cero en **1.281.254 contratos**, y **1.280.989 filas solo cierran
incluyéndola**. Con cinco, RN1 fallaría en el 45% del universo vivo.

**Falta el umbral, no la definición.** El **3,31%** (93.557 filas) no cierra de
ninguna forma, y siempre por defecto: la suma queda por debajo de
`valor_del_contrato`. Puede ser una séptima fuente, puede ser que
`valor_del_contrato` incluya adiciones que las fuentes no, o puede ser un
incumplimiento real de la fuente. Hasta separarlas, **RN1 no puede escribirse
como test que falle la construcción**: sería rojo el primer día por un motivo que
no entendemos. Ver la pregunta abierta 13 del inventario.

**RN3 quedó escrita el 29/08/2026 y pasa con cero**, sobre los 2.849.209
contratos de `fct_contratos`. No es un test que espera romperse: confirma H4
sobre el universo entero en vez de sobre un `GROUP BY` de estados.

**RN2 NO se escribió, y no por olvido.** Exige una lista de cuáles son los
estados pre-firma; esa lista no existe como constante en ninguna parte y su
definición es ambigua. H4 documenta cinco estados con fecha de firma nula y uno de
ellos es `Aprobado`, con **2 filas de 214.615**, o sea que `Aprobado` es
pre-firma casi nunca. Inventar la lista dentro de un test escondería ahí una
definición del ciclo de vida del contrato, que es una decisión de modelado y no de
prueba. Por H4, RN3 la cubre en la práctica salvo por esas 2 filas.

**RN12 nace con sus incumplimientos ya contados: son 2**, sobre 2.902.163
observaciones. Un contrato no puede terminar una liquidación que nunca empezó.

Es la única de las doce que llega con la medición hecha antes del test, y eso la
hace útil de una forma que las otras todavía no: **falla, y falla por poco**. Un
test que falla con dos casos se puede investigar; uno que falla con noventa mil
(como RN1 hoy) se ignora. La contracara es que, escrita como test bloqueante,
hace roja la construcción desde el primer día, así que hay que decidir si entra
como error o como advertencia.

Para orientar: 35 contratos tienen inicio de liquidación sin fin, y eso **no**
incumple nada: son liquidaciones en curso. La regla es en un solo sentido.

**RN13 atrapa lo que el sistema de tipos deja pasar**, que es la clase de basura
más peligrosa. Los siete contratos que la incumplen **castean limpio** a
`decimal(20,2)` y tienen `castings_fallidos = 0`. Un casting que no falla dice
que la forma era válida, no que el valor sea cierto.

Para dimensionar la asimetría: en 2.902.163 observaciones, el sistema de tipos
atrapa **un** valor con forma inválida. Todo lo demás pasa limpio y solo lo
detectan reglas de negocio.

**El techo se elige contra una cifra pública y verificable, no a ojo.** El
Presupuesto General de la Nación de 2026, aprobado por el Congreso, es de
**546,9 billones de pesos**: el gasto de todo el Estado colombiano en un año. Un
contrato individual no puede superarlo. El de 12.858 billones lo supera
**veintitrés veces**.

**Esto es el nivel de lo IMPOSIBLE, no el de lo sospechoso.** Con este techo,
RN13 tiene **siete incumplimientos**, todos contratos distintos. El mayor
(12.858 billones, 23,5 veces el PGN) es de un instituto municipal de deportes, y
otro es de una institución educativa: no son megaproyectos mal digitados.

Y aun así la regla **no toca** a los 32 contratos por encima del billón de pesos.
El mínimo de esos 32 es 1,07 billones, que una obra de infraestructura grande
puede valer legítimamente.

Falta el segundo nivel, y el umbral no está fijado: por encima de qué fracción
del **presupuesto de inversión anual** (88,4 billones para 2026) un contrato pasa
de improbable a sospechoso. Ese número es una decisión y no se pone a ojo; ver la
pregunta abierta 15 del inventario.

**RN9 y RN10 tienen una trampa:** `habilita_pago_adelantado` **no es booleana**.
Se observó en `"No Definido"`: tres estados, y `"No Definido"` no equivale a
`"No"`.

**RN11 es la mejor de las once** y también la más cara de implementar. Sale del
dominio y no del esquema; solo se puede testear conservando el valor inicial, o
sea que **justifica la tabla de snapshots desde la normativa**; y su
incumplimiento es un hallazgo publicable. La trampa: el límite es en **salarios
mínimos al momento de la firma**, no en pesos corrientes, así que necesita una
tabla de SMLMV por año que hoy no existe en el modelo: una dimensión chica, o
una columna de `dim_tiempo`.

**RN5 es interesante en los dos resultados posibles:** si `valor_pagado`
decrece, o hubo reversión de un pago o la fuente tiene un error. Los dos casos
valen la pena.

 Pero protege `valor_pagado`, que es **acumulado**. No generalizar a
`valor_del_contrato`, que sí puede bajar: existe el tipo `REDUCCION EN EL VALOR`
en el dataset oficial de modificaciones (H27).

---

## 11. Limitaciones conocidas

Van al README, no se esconden.

1. **`fct_contratos_snapshot` empieza vacía.** No se puede backfillear: la
   historia previa no existe en ninguna fuente pública. La tabla madura con el
   tiempo.
2. **Los deltas solo son válidos para contratos observados desde su firma.**
   Ver hallazgo 2 de la sección 9.
3. **El backfill de `fct_contratos` es de cobertura, no de historia.** Y el
   **flujo 3 no admite backfill hacia atrás**: pregunta por el estado actual, y
   el de una fecha pasada ya se destruyó. *Ver* El flujo 3 no se puede
   reejecutar hacia atrás *(R1) en*
   `03_decisiones_capa_raw.md`.
4. **`orden`, `rama` y `sector` no son confiables** y están documentados como
   tales.
5. **`tipo_persona` es inferido**, no viene de la fuente.
6. **Análisis restringido a 2020 en adelante** (decisión de H3). Antes de esa
   fecha la curva mide adopción de SECOP II, no gasto público.
7. **La resolución temporal es la del barrido, no la del evento** (D8). Las
   columnas se llaman `observado_desde` / `observado_hasta` justamente por eso:
   la plataforma sabe cuándo vio el cambio, no cuándo ocurrió. Un pago detectado
   el 21 de agosto pudo ocurrir cualquier día desde la observación anterior.

    Y **el barrido no puede ver más seguido de lo que la fuente se regenera**,
   que es irregular: saltos observados de dos y de cinco días entre cortes (H34).
   La serie tiene la resolución de la fuente, con huecos, y **no una resolución
   diaria**. Es la limitación que más hay que cuidar al redactar el README,
   porque es la única que un lector podría entender como una promesa incumplida
   en vez de como una propiedad del origen.
8. **RN1 está definida pero sin umbral.** Son las seis fuentes (medido), y el
   3,31% del universo vivo no cierra por motivos que todavía no se separaron.
   Escribirla como test bloqueante haría fallar la construcción el primer día.
   Ver sección 10 y la pregunta abierta 13 del inventario.

---

## 12. Preguntas abiertas

Heredadas del inventario, más las nuevas:

1. ¿`Cerrado` (1,69M) y `terminado` (774K) son sinónimos?
2. ¿Qué miden `orden` y `rama`? El diccionario los define de forma circular.
3. ¿Los estados terminales realmente no cambian? Determina si se excluyen del
   refresco del universo vivo.
4. ¿La llave de `dim_proveedor` es `documento_proveedor` o `codigo_proveedor`?
5. ~~¿Qué contienen `fecha_de_inicio_de_ejecucion`, `fecha_fin_liquidacion` y
   `estado_bpin`?~~ Resuelta al enumerar el esquema contra el endpoint de
   metadatos: `fecha_fin_liquidacion` existe y está clasificada como material;
   `fecha_de_inicio_de_ejecucion` y `estado_bpin` **no existen en la API**.

    Pero **cuántas columnas documenta el diccionario sigue sin resolverse**: se
   habla de 87 contra 85 reales, o sea dos ausentes, y son cinco las que se
   identificaron. Ver la pregunta abierta 4 del inventario.
6. ¿`origen_de_los_recursos` es redundante con las seis fuentes de financiación?
   En una fila coincidía; una fila genera hipótesis, no conclusión.
7. ¿Por qué `saldo_cdp` no se consume con la ejecución?
8. ¿Aporta algo `SECOP II - Ejecución de Contratos`? Es el candidato obvio para
   la serie de pagos que hoy no existe en ninguna fuente.
9. **¿El mart puede prometer que un evento de Adiciones se refleja en el
   contrato?** Los hermanos van más frescos que la fuente principal (H24): una
   modificación aprobada hoy está en Adiciones al rato, pero su efecto sobre
   `valor_del_contrato` no aparece hasta la próxima regeneración, que puede
   tardar días. La ventana en que el evento existe y su consecuencia todavía no
   estaba anotada como "de hasta un día" y no lo es. Nota para el mart, no bug,
   pero hay que decidir cómo se muestra.

10. **¿Cuál observación sobrevive cuando hay dos del mismo día?** Un contrato
    puede escribirse dos veces bajo la misma `fecha_extraccion` si cambia entre
    la corrida de un flujo y la de otro. Las dos escrituras son legítimas, pero
    el modelo tiene resolución de día y no puede representar dos estados dentro
    de uno: una de las dos se pierde sí o sí. Falta decidir **cuál**, y de dónde
    sale el orden entre particiones del mismo día: el manifiesto de D10 lleva
    marcas de tiempo y es el candidato natural, pero el modelo que las lee
    todavía no existe. Hoy son cero casos (medido el 29/08/2026 sobre 2.902.163
    observaciones) y `fct_una_observacion_por_contrato_y_fecha` para la
    construcción si aparece uno. Ver sección 3.

11. **¿Los 498 cambios de `proveedor_adjudicado` son renombres o cesiones mal
    registradas?** La columna está clasificada como material con el motivo "el
    trío del proveedor cambia con la cesión", y medido el 29/08/2026 el trío no
    se mueve junto: el nombre cambió en 513 contratos, el documento en 61 y
    `codigo_proveedor` (la llave, o sea una cesión de verdad) en **uno**. 498
    cambiaron solo el nombre, con el mismo código y el mismo documento.

    Los ejemplos apuntan a renombre del mismo proveedor: `'LARJ'` ->
    `'LUIS ANTONIO RIVADENEIRA JOJOA'`, `'RCN Radio S.A.S'` ->
    `'RADIO CADENA NACIONAL SAS'`. Bajo la definición de D6 (cosmética es que
    cambió el registro y no el contrato) esos son cosméticos y hoy generan
    versión.

    **Pero no se reclasifica sin mirar los 498.** Un renombre y una cesión donde
    la fuente no actualizó el código se ven idénticos desde acá, y
    `codigo_proveedor` recién se confirmó como llave el 28/08 sobre una sola
    regeneración. Reclasificar desde el patrón sin medir el universo es la regla
    6 otra vez. Y el error tiene dirección: dejarla material deja versiones de
    más, que es el error que este proyecto elige; sacarla puede borrar una cesión
    real, que es el que falta.
12. **¿`fecha_de_inicio_del_contrato` debe pasar de IMPOSIBLE a MATERIAL?**
    Medido el 29/08/2026: cambió en 685 contratos, y **648 de esos cambios son de
    nulo a fecha**. Eso no es la mutación contra la que existe la categoría
    IMPOSIBLE: es un hito que se llena, igual que las tres fechas de liquidación
    y prórroga, que sí son materiales. Las 37 mutaciones reales tienen mediana de
    un día y se parecen a correcciones.

    A favor de moverla: hoy esos 648 arranques de ejecución **no generan versión
    por sí solos**, porque las imposibles no entran en la huella. Se ven solo
    cuando coinciden con otro cambio material, que hasta ahora fue siempre, pero
    eso no está garantizado.

    En contra: mover una columna de categoría invalida la comparación entre lo ya
    construido y lo que venga, y hay que reconstruir el snapshot. Y `Aprobado` ->
    `En ejecución` ya genera versión por `estado_contrato`, así que la pérdida
    real puede ser cero.

    Lo que cierra la pregunta es medir cuántos de los 648 **no** coincidieron con
    un cambio material. Hoy son cero, y eso es un dato, no una garantía.

**Hipótesis descartada: vale la pena no volver a intentarla.** Se probó si
`dias_adicionados > 0` identificaba a los contratos en estado `Modificado`. La
consulta devolvió miles de contratos `Modificado` con cero días adicionados.

`Modificado` cubre modificaciones de valor, cesiones y otros eventos que **no
dejan huella en ninguna columna**. Refuerza la pregunta 7: hay más historia
destruida de la que sugiere el inventario a primera vista.