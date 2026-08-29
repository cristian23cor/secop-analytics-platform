# Inventario de fuentes — SECOP

> Registro de evaluación de las fuentes candidatas del ecosistema SECOP.
> Cada hallazgo va acompañado de la consulta que lo demuestra, para que sea
> reproducible por cualquiera.
> **Alcance:** este documento cubre la fuente principal (`jbjy-vk9h`), con los
> hallazgos H1 a H9 y **H34**. Los datasets hermanos del ecosistema y sus
> hallazgos H17–H33 están en `02_ecosistema_secop.md`; acá se listan en la
> sección 2 con su veredicto. Las **decisiones de diseño** que salieron de estos
> hallazgos tampoco viven acá: se las referencia con →.
>
> **H10 a H16 no existen.** Nunca se asignaron: sus contenidos viven dentro de H6
> y las referencias cruzadas de otros documentos quedaron colgando. Por eso el
> hallazgo nuevo es H34 y no H10 — los identificadores son estables y no se
> reciclan.
>
> Última verificación contra la API: 28 de agosto de 2026.

---

## Glosario

Términos que este documento usa constantemente.

**Grano** — qué representa una fila. "Una fila = un contrato" es distinto de
"una fila = una versión de un contrato", y confundirlos infla todos los totales.
Es la primera pregunta de cualquier modelo de datos.

**Watermark** (marca de agua) — una columna que dice *cuándo cambió cada fila*.
Sirve para pedirle a la fuente solo lo nuevo, en vez de descargar todo cada vez.
Sin watermark no hay carga incremental posible.

**Carga incremental** — traer solo lo que cambió desde la última corrida, en
lugar de rehacer todo. Es lo que hace que un pipeline recurrente sea barato.

**Backfill** — reprocesar el pasado. Se usa cuando se agrega una fuente nueva o
se corrige un error: en vez de esperar a mañana, se recorre el histórico por
pedazos.

**SCD tipo 2** (*slowly changing dimension*) — técnica para guardar **versiones**
en vez de sobrescribir. Cada versión lleva desde cuándo y hasta cuándo fue
válida, así se puede preguntar "¿cómo estaba esto en marzo?".

**Capas de dbt** — el pipeline transforma en tres pasos, cada uno un conjunto de
consultas SQL:
  - `staging` — limpieza mecánica: renombrar, normalizar, convertir tipos.
  - `intermediate` — lógica de negocio: derivar columnas, cruzar tablas.
  - `marts` — las tablas finales que consume el tablero.

**Freshness** (frescura) — test que verifica que la fuente no esté vieja. Si el
dato más reciente tiene más de X horas, algo se rompió.

**Columna material** — una columna cuyo cambio significa que el contrato cambió
de verdad, y por eso genera una versión nueva. Se opone a *cosmética*, donde
cambió el registro y no el contrato (una tilde corregida por ej). El detalle está en
`03_decisiones_capa_raw.md`.

**Vista derivada** — un dataset del portal que no es una fuente propia, sino un
recorte o una copia de otro. Usarla en vez del maestro trae datos incompletos
sin avisar.

**ESE** — Empresa Social del Estado. 

**PGN, SGP, SGR** — las tres grandes bolsas del presupuesto público colombiano:
Presupuesto General de la Nación, Sistema General de Participaciones (lo que la
nación transfiere a municipios y departamentos) y Sistema General de Regalías
(lo que produce la explotación de recursos naturales).

**Dígito de verificación** — el último número del NIT colombiano, separado por un
guion. Sirve para detectar errores de tipeo. La fuente a veces lo incluye y a
veces no, así que el mismo NIT aparece escrito de dos formas.

**UNSPSC** — clasificador internacional de bienes y servicios, con una jerarquía
de cuatro niveles. Es lo que permite preguntar "¿quién compra lo que yo vendo?".

**Regeneración** — la operación con la que la fuente se rehace entera y
sobrescribe su propio estado anterior. No es una actualización de filas: es un
reemplazo total (H2). Ocurre de madrugada, pero **no todos los días** (H34).

**Corte** — el estado de la fuente que produjo una regeneración. Se identifica
por el valor de `:updated_at`, que es idéntico en todas las filas y por eso
funciona como llave del corte, aunque no sirva como watermark de fila (H2). "El
corte del 25" es lo que un analista llamaría la foto de ese día.

 **"Partición" significa dos cosas distintas** y conviene no mezclarlas:
  - **Ventana de backfill** — un pedazo del histórico, normalmente un mes. Se
    usa para reprocesar el pasado sin bajar todo de una vez.
  - **Partición de paralelismo** — un pedazo del universo vivo que se reparte
    entre varios procesos **de la misma corrida**, para que terminen antes.

  Confundirlas tiene consecuencias: darle una ventana de backfill al flujo 3
  hace que parezca que se está reprocesando el pasado, y no es así. Por eso el
  código lo rechaza (ver *El flujo 3 no se puede reejecutar hacia atrás* en
  `03_decisiones_capa_raw.md`).

---

**Endpoint base usado en todas las consultas:**

```
https://www.datos.gov.co/resource/jbjy-vk9h.json
```

**Documentación oficial consultada:**

Diccionario de Datos y Ficha Técnica – Registros Administrativos, ANCP-CCE,
Subdirección de Información y Desarrollo Tecnológico, versión 1.0, agosto 2025.
`https://www.colombiacompra.gov.co/wp-content/uploads/2026/03/GES215ABCDEFH_Ficha-tecnica-de-RA.pdf`

---

## 1. SECOP II — Contratos Electrónicos (ELEGIDA)

### Ficha

| Campo | Valor |
|---|---|
| Identificador | `jbjy-vk9h` |
| Tipo | Dataset maestro (no vista derivada) |
| Publica | Agencia Nacional de Contratación Pública – Colombia Compra Eficiente |
| Filas | 5.958.553 |
| Columnas | **85 en el esquema real**, enumeradas contra el endpoint de metadatos el 20/08/2026. El diccionario declara 87 (ver pregunta abierta 4) |
| Frecuencia declarada | Diaria. ⚠ **Declarada, no verificada — y contradicha** (H34) |
| Rezago real de publicación | ~1 día (máximo observado: 2026-08-17) |
| Hora de regeneración | Madrugada colombiana, en una ventana de ~35 min entre 04:06 y 04:41 sobre tres observaciones. **No es un horario publicado** (H34) |
| Rango temporal | 2015-06-11 a 2026-08-17 |
| Licencia | Datos abiertos (Ley 1712 de 2014) |

### Qué representa una fila

Un contrato estatal registrado en SECOP II, con su estado **actual**. No es un
registro histórico: la fila se sobrescribe cuando el contrato cambia.

### Sanidad de negocio (Fase 5)

El diccionario oficial reportaba ~4.775.550 contratos al 31 de agosto de 2025.
Hoy, 18 de agosto de 2026, hay 5.958.553. La diferencia de ~1,18 millones en un
año es consistente con la curva de ~1M contratos anuales de H3. Los números
cierran contra una fuente independiente.

### Decisión de versión de API: SODA2

Socrata ofrece SODA2 y SODA3; la plataforma usa SODA3 por defecto desde octubre
de 2025. Se eligió **SODA2** para la v1 por tres razones:

1. Depurable a mano — SODA2 usa GET, así que una consulta se prueba pegando una
   URL en el navegador. SODA3 exige POST con payload JSON.
2. Diez años de documentación y ejemplos frente a menos de un año de SODA3.
3. El riesgo es asimétrico: si SODA2 falla se migra; si SODA3 se comporta raro en
   la paginación, no hay precedentes de la comunidad con datasets de este tamaño.

**Mitigación:** toda la lógica que conoce `$limit` / `$offset` vive aislada en una
sola función del extractor. Migrar a SODA3 es cambiar esa función.

---

## Hallazgos de la exploración

### H1 — El grano es un contrato por fila

**Por qué se validó:** es la primera pregunta de cualquier modelo dimensional. Si
el grano fuera "una versión de contrato", todos los totales estarían inflados y
los tests de unicidad fallarían de una forma que invita a taparlos con un
`distinct`.

**Consulta 1 — buscar duplicados:**

```
?$select=id_contrato,count(*) as n&$group=id_contrato&$having=count(*) > 1&$limit=5
```

Resultado: `[]`

**Consulta 2 — confirmación independiente:**

```
?$select=count(*) as total,count(distinct id_contrato) as unicos
```

Resultado: `total = 5958553`, `unicos = 5958553`

**Conclusión:** `id_contrato` es llave primaria. Una fila = un contrato.

**El diccionario oficial se contradice sobre este punto.** Declara `ID Contrato`
como llave única del registro, pero en la sección "Unidad de Medida" afirma que
cada unidad corresponde a *un proceso de contratación* publicado por una entidad
estatal. Un proceso y un contrato no son lo mismo: un proceso puede derivar en
varios contratos. **La evidencia empírica prevalece** — la unicidad de
`id_contrato` está verificada por dos métodos independientes.

**Implicación no obvia:** los contratos se modifican en la realidad (adiciones,
prórrogas, cesiones) pero no aparecen filas nuevas. Por lo tanto la fuente
**actualiza la fila en su lugar**. Esto lleva directo a H2.

---

### H2 — La fuente tiene tres mecanismos de cambio y solo dos son detectables (CRÍTICO)

> Este hallazgo se construyó en tres etapas. Se documenta el recorrido completo
> porque las hipótesis descartadas son parte del razonamiento.

#### Etapa 1 — El campo de sistema de Socrata no sirve

**Consulta A — ¿existen campos de sistema?**

```
?$select=:*,*&$limit=1
```

Resultado: existe `:updated_at`.

**Consulta B — ¿el campo distingue algo?**

```
?$select=min(:updated_at) as mas_viejo,max(:updated_at) as mas_nuevo
```

```json
{"mas_viejo":"2026-08-18T09:22:15.735Z","mas_nuevo":"2026-08-18T09:22:15.735Z"}
```

Mínimo y máximo idénticos **al milisegundo**, sobre 5,96 millones de filas.

**Conclusión parcial:** Colombia Compra Eficiente no actualiza filas
individuales en Socrata; regenera el dataset completo en una sola operación.
Coherente con la metodología declarada en el diccionario, que describe un proceso
ETL nocturno que genera las vistas publicadas. `:updated_at` es inútil **como
watermark de fila**.

**Confirmado cuatro veces**, siempre con `min = max` al milisegundo sobre 5,96
millones de filas:

| Fecha de la consulta | Valor observado |
|---|---|
| 18/08/2026 | `2026-08-18T09:22:15.735Z` |
| 21/08/2026 | `2026-08-20T09:41:20.358Z` |
| 26/08/2026 | `2026-08-25T09:05:54.277Z` |
| 28/08/2026 | `2026-08-25T09:05:54.277Z` |

**H2 es el hallazgo más sólido del documento y no está en discusión.** Pero fijate
en la segunda y la cuarta fila: el valor observado **no es del día de la
consulta**. Esa lectura tardó ocho días en hacerse y es lo que hoy es H34.

⚠ **Lo que sí hay que corregir de este hallazgo: `:updated_at` no es inútil, es
inútil para una cosa.** La conclusión original decía "inútil como watermark", a
secas. Es cierto fila por fila, que era la pregunta que se le estaba haciendo.
Pero la misma propiedad que lo inutiliza para eso —que min y max coincidan al
milisegundo— lo convierte en la **llave natural del corte**: una petición de
segundos dice qué estado está vivo, y dos observaciones con el mismo valor vieron
el mismo estado. Sobre eso se apoyan D10 y D11 en `03_decisiones_capa_raw.md`.
No vale para los hermanos, que escriben en continuo y no tienen corte (H23).

#### Etapa 2 — Sí existe un watermark de negocio (aportado por el diccionario)

El diccionario documenta una columna que **no apareció en la fila de muestra**:
`ultima_actualizacion`, descrita como "Fecha de última actualización del
contrato electrónico". Ver H6 para por qué la muestra no la mostró, y H8 para lo
que resultó ser en realidad.

**Consulta C:**

```
?$select=min(ultima_actualizacion) as min_ua,max(ultima_actualizacion) as max_ua,count(ultima_actualizacion) as con_valor
```

```json
{"min_ua":"2016-01-29T00:00:00.000","max_ua":"2026-08-17T00:00:00.000","con_valor":"3448849"}
```

Rango de diez años → **el campo sí distingue**. Pero está nulo en 2.509.704 filas
(42%). Ver H8.

#### Etapa 3 — Hay un tercer mecanismo que ninguna columna registra

Los pagos avanzan sin que ninguna fecha lo registre. Está desarrollado en H9,
que es donde se cuantifica.

#### Conclusión consolidada

| Mecanismo de cambio | Columna que lo detecta | Volumen |
|---|---|---|
| Contrato nuevo | `fecha_de_firma` | ~2.900/día |
| Evento contractual (modificación, cesión, cierre, liquidación) | `ultima_actualizacion` | ~2.065/día |
| Avance de ejecución financiera (pagos, facturación) | **ninguna** | 735.809 contratos afectados |

**Estrategia de extracción resultante — tres flujos:**

1. **Nuevos** — ventana diaria sobre `fecha_de_firma`.
2. **Eventos** — ventana diaria sobre `ultima_actualizacion`.
3. **Deriva financiera** — refresco del universo vivo. No hay atajo: hay que
   reextraer y comparar.

   Barre los **cuatro estados vivos** —`En ejecución`, `Modificado`,
   `Suspendido`, `Prorrogado`— que suman **2.825.685** contratos, y lo hace
   **una vez por cada regeneración de la fuente** (H34). Correrlo dos veces
   contra el mismo corte no aporta nada, y por eso el cargador se planta
   → *ver D11 en* `03_decisiones_capa_raw.md`.

    Es tentador acotarlo a `En ejecución` y correrlo semanal: son 1,7M de filas
   en vez de 2,8M. No alcanza. Un contrato `Modificado` o `Suspendido` sigue
   recibiendo pagos, y una semana de resolución pierde el orden de los eventos
   dentro de ese lapso. **Ojo con el argumento simétrico:** que la fuente pase
   días sin regenerar (H34) no justifica bajar el flujo a semanal. La resolución
   la fija la fuente, y renunciar a más resolución de la que ella impone es
   perder observaciones que sí existían.

   Los parámetros de fecha de `refresco_de_vivos()` son una **partición de
   paralelismo** —un reparto entre procesos de la misma corrida— y **no** una
   ventana de backfill. Ver el glosario.

    **Este flujo no admite backfill.** Pregunta por el estado actual, y el
   estado de una fecha pasada ya se destruyó. Reejecutarlo hacia atrás
   escribiría el hoy con fecha de ayer. → *Ver* El flujo 3 no se puede reejecutar hacia atrás *(R1) en*
   `03_decisiones_capa_raw.md`.

Los flujos 1 y 2 suman ~5.000 filas por día de negocio: una sola petición. El DAG
es liviano; todo el peso está en el flujo 3.

**Consecuencia de fondo:** el historial no existe en el origen. Cada
regeneración sobrescribe el estado anterior de la fuente, y nadie puede consultar
cuánto valía un contrato antes de una adición.

El argumento completo —por qué esto justifica la plataforma entera— está en H9,
que es donde se cuantifica.

---

### H3 — La curva de volumen mide adopción, no gasto

**Por qué se validó:** dimensiona el backfill y determina si los años son
comparables entre sí.

**Consulta:**

```
?$select=date_trunc_y(fecha_de_firma) as anio,count(*) as n&$group=anio&$order=anio
```

| Año | Contratos |
|---|---|
| 2015 | 10 |
| 2016 | 1.342 |
| 2017 | 22.259 |
| 2018 | 142.973 |
| 2019 | 142.592 |
| 2020 | 357.251 |
| 2021 | 561.581 |
| 2022 | 710.534 |
| 2023 | 843.059 |
| 2024 | 950.670 |
| 2025 | 1.050.857 |
| 2026 (parcial) | 751.450 |
| **Sin fecha** | **423.975** |

**Conclusión 1:** el salto de 10 contratos en 2015 a más de un millón en 2025 es
la curva de adopción de SECOP II, que se volvió obligatorio por etapas. **No es
crecimiento del gasto público.** Cualquier comparación interanual que cruce 2020
es inválida.

**Decisión:** el análisis de los marts se restringe a **2020 en adelante**. Se
pierden 309.176 filas (5,2%) y se gana validez. Los años previos permanecen en la
capa raw.

**Conclusión 2:** el volumen reciente es de ~2.900 contratos firmados por día.
El backfill son ~80 **ventanas de backfill** mensuales de 2020 a 2026, ninguna
superior a ~100.000 filas. (Ventana de backfill, no partición de paralelismo:
ver el glosario.)

**Conclusión 3 — lección de método:** `min()` y `max()` habían reportado el rango
2015–2026 sin mencionar las 423.975 filas nulas. **Las funciones de agregación
ignoran los nulos en silencio.** El `GROUP BY` completo se hace siempre, aunque
parezca redundante frente a un `min/max` ya ejecutado.

---

### H4 — Los nulos de fecha de firma son todos pre-firma

**Por qué se validó:** partir el backfill por año de firma dejaría 423.975 filas
huérfanas —las que no tienen fecha de firma— sin que ningún error lo advirtiera.
Simplemente no entrarían en ninguna ventana.

**Consulta:**

```
?$select=estado_contrato,count(*) as n&$where=fecha_de_firma IS NULL&$group=estado_contrato
```

| Estado | Filas |
|---|---|
| Borrador | 244.947 |
| Cancelado | 110.585 |
| enviado Proveedor | 43.814 |
| En aprobación | 24.627 |
| Aprobado | 2 |

Suma: 423.975 — coincide exactamente con el grupo nulo de H3.

**Conclusión:** los cinco estados son anteriores a la firma. **No hay ni un solo
contrato "En ejecución", "Cerrado" o "terminado" sin fecha de firma.** El filtro
de negocio que excluye lo que no es un contrato ejecutable resuelve el problema
técnico de las ventanas como efecto colateral. Cuando una decisión de modelado
limpia dos problemas a la vez, normalmente está bien elegida.

---

### H5 — `estado_contrato` mezcla dos dimensiones

**Consulta:**

```
?$select=estado_contrato,count(*) as n&$group=estado_contrato&$order=n DESC
```

| Estado | Filas |
|---|---|
| En ejecución | 1.737.502 |
| Cerrado | 1.690.510 |
| Modificado | 1.081.413 |
| terminado | 774.500 |
| Borrador | 245.385 |
| Aprobado | 214.615 |
| Cancelado | 110.665 |
| enviado Proveedor | 43.924 |
| cedido | 28.557 |
| En aprobación | 24.712 |
| Suspendido | 6.650 |
| Prorrogado | 120 |

Suma: 5.958.553 

El diccionario define el campo como "Estado del contrato, frente a su ejecución,
firma o liquidación" y **no enumera los valores posibles**, así que la lista de
arriba es la única fuente de verdad disponible.

**Problema de modelado:** los valores pertenecen a dos ejes distintos.

- **Etapa del ciclo:** Borrador, En aprobación, enviado Proveedor, Aprobado,
  En ejecución, Cerrado, terminado
- **Qué le ocurrió al contrato:** Modificado, Prorrogado, cedido, Suspendido,
  Cancelado

Un contrato en ejecución que fue modificado tiene dos verdades, pero la columna
solo guarda una. `Modificado` (1,08M filas) probablemente esconde el estado real.
H8 refuerza la hipótesis: esos contratos casi siempre tienen fecha de evento, lo
que sugiere que el estado cambia cuando el evento ocurre y se lleva la fecha
consigo.

**Decisión:** derivar en la capa `intermediate` columnas propias
(`esta_vigente`, `fue_modificado`) con la lógica documentada. No usar
`estado_contrato` crudo como máquina de estados.

**Inconsistencia de formato:** `terminado`, `cedido` y `enviado Proveedor` no
respetan la capitalización de los demás, lo que sugiere orígenes o épocas
distintas dentro del sistema fuente. Se normaliza en `staging`.

→ *Esta inconsistencia tuvo consecuencias de diseño: fue uno de los argumentos
que decidieron dónde corre la comparación de cambios. Ver `03_decisiones_capa_raw.md`, D1.*

**Anomalía menor:** `Borrador` suma 245.385 en total pero solo 244.947 tienen
fecha de firma nula. Quedan **438 contratos en Borrador con fecha de firma**, lo
cual es contradictorio. No afecta el modelo (se excluyen igual), pero se
documenta.

---

### H6 — Observaciones sobre el esquema

Obtenidas de inspeccionar una fila completa (`?$limit=1`) y de contrastarla con
el diccionario oficial.

#### Lección de método: una fila no revela el esquema

La fila de muestra trajo 81 claves de las 85 reales. **Socrata omite del JSON las
claves cuyo valor es nulo**, así que una fila individual subestima el esquema.

Columnas documentadas en el diccionario que no aparecieron en la muestra:
`fecha_de_inicio_de_ejecucion`, `fecha_de_fin_de_ejecucion`, `estado_bpin`,
`c_digo_bpin`, `anno_bpin`, **`ultima_actualizacion`**,
`fecha_inicio_liquidacion`, `fecha_fin_liquidacion`,
`fecha_de_notificaci_n_de_prorrogaci_n`.

**Resuelto parcialmente** al enumerar el esquema completo contra el endpoint de
metadatos, en vez de inferirlo de una muestra:

| Columna | Veredicto |
|---|---|
| `ultima_actualizacion` | **Existe.** Estaba nula en esa fila. Material |
| `fecha_inicio_liquidacion` | **Existe.** Material |
| `fecha_fin_liquidacion` | **Existe.** Material |
| `fecha_de_notificaci_n_de_prorrogaci_n` | **Existe.** Material |
| `fecha_de_inicio_de_ejecucion` | **No existe en la API** |
| `fecha_de_fin_de_ejecucion` | **No existe en la API** |
| `estado_bpin` | **No existe en la API** |
| `c_digo_bpin` | **No existe en la API** |
| `anno_bpin` | **No existe en la API** |

 **Contradicción sin resolver, ver pregunta abierta 4.** Son **cinco** columnas
documentadas y ausentes, pero la diferencia declarada entre diccionario (87) y
esquema real (85) es de **dos**. Alguno de los dos números está mal.

La omitida más importante era `ultima_actualizacion`: ninguna cantidad de
exploración sobre esa fila la habría revelado, y es la columna sobre la que se
apoya la mitad de la estrategia de extracción (H2, H8).

#### Tipos

**Todos los valores llegan como texto** por la API, incluso los que el
diccionario declara como Número (`nit_entidad`, `valor_del_contrato`).
Ejemplos: `"valor_del_contrato":"8959088"`, `"es_pyme":"No"`.

Se descargará todo como string a propósito: si pandas infiere tipos, convierte a
`NaN` los valores mal formados y esconde la suciedad.

Cuidado con leer esto de más: lo que se prohíbe es que la herramienta **adivine**
el tipo en silencio, no convertir de forma explícita cuando hace falta.

→ *Ver `03_decisiones_capa_raw.md`, D6, para qué implica esto al comparar valores monetarios.*

#### Nombres de columna deformados por Socrata

- Acentos reemplazados por `_`: `localizaci_n`, `liquidaci_n`,
  `g_nero_representante_legal`, `duraci_n_del_contrato`,
  `direcci_n_de_ejecuci_n_del_contrato`
- Nombres truncados: `justificacion_modalidad_de`, `valor_pendiente_de`

El renombrado a nombres limpios se hace en `staging` y funciona como
documentación.

#### `urlproceso` es un objeto anidado

`{"url": "https://..."}`, no un escalar como las otras 84 columnas. Hay que
extraer `urlproceso.url` explícitamente o rompe la conversión a Parquet.

→ *Esta rareza terminó decidiendo el formato de archivo de la capa raw. Ver
`03_decisiones_capa_raw.md`, D2.*

La URL trae además un `noticeUID=CO1.NTC.xxx` que **no se puede reconstruir**
desde `proceso_de_compra` (que es `CO1.BDOS.xxx`). Es un tercer identificador y
probablemente la llave hacia el dataset de Procesos de Contratación.

#### Suciedad detectable en una sola fila

- `nit_entidad` sin dígito de verificación — requiere normalización
- `localizaci_n` con espacios dobles y redundante con `departamento` y `ciudad`
- `direcci_n_de_ejecuci_n_del_contrato` contiene saltos de línea embebidos
- `duraci_n_del_contrato` es texto libre: `"2 Mes(es)"`
- `orden` = "Nacional" para un hospital **departamental**; `rama` = "Corporación
  Autónoma" para una ESE. Estas categorías no son confiables tal como vienen.
- Los proveedores mezclan personas naturales (cédula) y empresas (NIT). Hay que
  decidir si se separan en la dimensión.
- **Discrepancia con el diccionario:** define `nombre_representante_legal` como
  el representante legal *de la entidad*, pero en la fila inspeccionada su valor
  coincide exactamente con `proveedor_adjudicado` (una persona natural). O la
  definición está mal, o el campo se usa mal en la práctica. Refuerza la decisión
  de H7.

**Los nulos también vienen como centinela de texto**, con dos capitalizaciones:
`"No definido"` y `"No Definido"`. No son nulos de verdad, así que la omisión de
claves no los cubre. Se normalizan en `staging`.

El centinela no se limita a columnas de detalle: también aparece en columnas
**categóricas**, donde es más dañino porque parece una categoría legítima. En el
dataset de Adiciones es el 22% de los tipos de modificación entre 2015 y 2022
(H28; ese porcentaje tiene denominador parcial y no vale para el dataset
entero).

#### Columna clave para el caso de uso comercial

`codigo_de_categoria_principal` = `"V1.80111701"` es un código **UNSPSC**, el
clasificador estándar internacional de bienes y servicios. Responde la pregunta
"¿qué entidades públicas compran lo que yo vendo?". Requiere quitar el prefijo
`V1.` y decidir el nivel de agregación de la jerarquía.

El diccionario de SECOP I documenta la jerarquía completa —Grupo → Familia →
Clase— y remite al clasificador oficial en
`colombiacompra.gov.co/clasificador-de-bienes-y-servicios`, que es la fuente para
traducir códigos a nombres legibles en la dimensión de categoría.

#### Seis entidades reclasificadas entre el 23 y el 25 de agosto de 2026

**Este es el primer cambio real que el pipeline capturó, y la prueba de que la
premisa del proyecto no es teórica.**

Comparando el barrido del 23 contra la corrida del 25, **20.675 contratos**
cambiaron `entidad_centralizada` de `"Centralizada"` a `"Descentralizada"`.
Ninguno en sentido contrario. Pertenecen a **seis entidades**:

| Entidad | `orden` | Contratos |
|---|---|---|
| Gobernación del Cauca | Territorial | 8.955 |
| SENA Regional Valle — Grupo de Apoyo Administrativo | Nacional | 5.553 |
| SENA Secretaría General | Nacional | 3.014 |
| Instituto Municipal de Cultura y Turismo de B… | Territorial | 1.274 |
| Instituto Departamental de Salud de Nariño | Territorial | 1.156 |
| Hospital de Castilla la Nueva — ESE | Territorial | 723 |

**Nadie que consulte SECOP hoy puede saber que esto pasó.** La fuente se
sobrescribió: hoy solo dice `"Descentralizada"` y no queda rastro del estado
anterior. Existe únicamente porque se guardaron las dos fotos y se compararon.

#### ⚠ Pero la lectura fácil no se sostiene

Sería cómodo enunciarlo como "se corrigieron seis clasificaciones erróneas".
Cuatro de las seis encajan: dos regionales del SENA, un instituto municipal, un
instituto departamental de salud y una ESE son entidades con personería jurídica
propia, o sea descentralizadas por definición.

**La Gobernación del Cauca no encaja, y son 8.955 contratos — el 43% del
total.** Una gobernación *es* el nivel central de la administración
departamental; reclasificarla como descentralizada parece incorrecto.

A menos que "centralizada/descentralizada" en SECOP no signifique lo que dice la
doctrina administrativa — que es exactamente el problema de la **pregunta abierta
2**: el diccionario define `orden` y `rama` de forma circular, y sus valores ya
contradicen la intuición (un hospital departamental figura como "Nacional"). Es
el mismo defecto en la columna de al lado.

**La afirmación que se sostiene:** la fuente reclasificó seis entidades en un
solo movimiento, sobre una taxonomía cuyo significado su propio diccionario no
define bien. No que haya corregido errores.

#### Y el evento pertenece a la dimensión, no al contrato

`entidad_centralizada` es **cosmética**, así que el snapshot no generó versión
para esos 20.675 contratos. La clasificación es correcta: no cambió nada del
contrato, cambió la ficha de su entidad.

Pero el evento es real e interesante, y eso convierte una decisión pendiente en
una con evidencia: **`dim_entidad` necesita historia propia**, y ya tiene su
primer caso documentado para probarla.

#### Valores imposibles en `valor_del_contrato` — medido el 28/08/2026

La columna que justifica el proyecto entero tiene basura, y de dos clases que
hay que mantener separadas porque se atrapan con herramientas distintas.

**La que el sistema de tipos rechaza.** Un contrato trae
`767747876936238525636` — 21 dígitos, unos 767 mil trillones de pesos. No entra
en `decimal(20,2)` y `try_cast` lo vuelve nulo. Es **1 sobre 2.902.163**.

⚠ **Agrandar el decimal para que entre sería lo peor que se puede hacer.** El
valor pasaría a contaminar toda suma, promedio y máximo del proyecto. Que se
rechace es el sistema funcionando.

**La que el sistema de tipos deja pasar, y es peor.** Hay **siete contratos
distintos** —no siete observaciones del mismo— cuyo valor supera el Presupuesto
General de la Nación de 2026, que el Congreso aprobó en **546,9 billones de
pesos**. Los siete **castean limpio** y tienen `castings_fallidos = 0`.

| Valor declarado | Veces el PGN | Estado | Entidad |
|---|---|---|---|
| 12.858 billones | **23,5** | En ejecución | Instituto municipal de deportes |
| 6.453 billones | 11,8 | En ejecución | Institución educativa |
| 3.247 billones | 5,9 | Modificado | Ministerio del Interior |
| 714 billones | 1,3 | Modificado | Ministerio del Interior |
| 601 billones | 1,1 | Modificado | Secretaría distrital |
| 579 billones | 1,1 | Modificado | DISAN-DMSOC |
| 577 billones | 1,1 | En ejecución | Hospital Central de la Policía |

Las entidades son lo que cierra la lectura. Un megaproyecto de infraestructura
mal digitado sería discutible; **un instituto municipal de deportes con 23,5
veces el presupuesto del Estado no lo es**.

⚠ **Pero el dinero no se movió, y eso hay que decirlo.** Seis de los siete
declaran `valor_pagado = 0`; el séptimo, 22,7 millones sobre 577 billones — el
0,000004%. Son errores de digitación publicados sin ningún filtro, no desfalcos.
La afirmación sostenible es que **la fuente oficial no valida sus propios
valores**, y esa versión no necesita adorno para ser fuerte.

`valor_pagado = 0` no sirve para detectarlos: la mayoría de los contratos sanos
también lo tiene en cero. Sirve para interpretarlos.

⚠ **Y la distribución sugiere dos fenómenos, no uno.** Los tres primeros están
órdenes de magnitud por encima; los últimos cuatro apenas cruzan el techo, entre
1,1 y 1,3 veces. El umbral del PGN parte ese segundo grupo por la mitad, lo que
confirma que es el nivel de lo imposible y apenas la punta: los 32 contratos por
encima del billón siguen esperando un segundo umbral.

Es H33 otra vez, en otra columna: un valor con forma válida y contenido
imposible. `castings_fallidos = 0` para esa fila. **Un casting que no falla no
dice que el dato sea cierto**, y esta clase de basura solo la atrapa una regla de
negocio con un techo defendible → *RN13 en* `01_modelo_dimensional.md`.

**La escala del problema:** 32 contratos superan el billón de pesos. No todos son
basura — el mínimo es 1,07 billones y una obra de infraestructura grande puede
valer eso. La misma lista contiene contratos reales y corrupción, y separarlos es
lo que RN13 tiene que resolver.

**Y una pérdida de precisión silenciosa:** 3 contratos traen más de dos
decimales, como `51041037891.7566`. `decimal(20,2)` los redondea sin avisar. Tres
sobre 2,9 millones; se anota y no se cambia el tipo, porque dos decimales es lo
correcto para pesos y son los datos los que están raros.

#### `liquidaci_n` es booleana, no un hito — medido el 28/08/2026

Este documento y `columnas.py` la ponían junto a `fecha_inicio_liquidacion` y
`fecha_fin_liquidacion`, bajo el rótulo de "hitos que arrancan nulos y se
llenan". **No arranca nula nunca.** Sobre las 2.902.163 observaciones de raw:

| Valor | Filas |
|---|---|
| `"No"` | 2.611.371 |
| `"Si"` | 290.792 |
| nulo o centinela | **0** |

Sigue siendo material, y por un motivo mejor que el que tenía escrito: pasar de
`"No"` a `"Si"` es un cambio de estado real del contrato. Lo que se corrige es la
razón. Un motivo equivocado es el que después justifica la siguiente decisión
equivocada — acá habría llevado a esperar un `NULL → fecha` que no va a ocurrir.

⚠ **Y no calza con `fecha_inicio_liquidacion`:** 290.792 contra 292.694, o sea
**1.902 de diferencia**. Si fueran lo mismo dicho de dos formas, coincidirían.
Un casi-calce pide explicación igual que un calce demasiado bueno. Pregunta
abierta 14.

#### Dos contratos terminan una liquidación que nunca empezó

Del mismo recorrido, cruzando las dos fechas de liquidación:

| | Filas | Lectura |
|---|---|---|
| Inicio sí, fin no | 35 | Liquidaciones en curso. Normal |
| **Fin sí, inicio no** | **2** | **Imposible** |

Dos sobre 2.902.163 es 0,00007%. La rareza es lo que los hace interesantes: es
corrupción puntual, del mismo tipo que H33 encontró en una columna de fechas, y
no una categoría con significado.

→ *Candidata a RN12 en* `01_modelo_dimensional.md`: una regla que hoy falla con
dos incumplimientos es un test que sirve — se puede investigar en vez de ahogarse
en ruido.

#### Desagregación de financiación

`presupuesto_general_de_la_nacion_pgn`, `sistema_general_de_participaciones`,
`sistema_general_de_regal_as`,
`recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_`,
`recursos_de_credito`, `recursos_propios`.

**Son seis, no cinco.** La sexta se descubrió al enumerar el esquema completo;
este documento decía cinco.

#### Medido el 28/08/2026 contra raw: la sexta entra, y por goleada

Se midió sobre las **2.824.446 filas del barrido del 23**, o sea el universo
vivo entero, con `scripts/medir_rn1.py`. No contra la API: raw ya tenía las seis
columnas en disco, y en SoQL un nulo en cualquier sumando anula la suma.

| | Filas | % |
|---|---|---|
| La sexta con valor **distinto de cero** | **1.281.254** | 45,4% |
| Cierran igual con cinco o con seis | 1.449.900 | 51,3% |
| **Cierran SOLO incluyendo la sexta** | **1.280.989** | **45,4%** |
| No cierran de ninguna forma | 93.557 | 3,3% |

**RN1 son seis columnas.** Con cinco, la regla fallaría en casi la mitad del
universo vivo. La pregunta abierta 1 queda cerrada.

⚠ **La expectativa era la contraria, y el error es instructivo.** Se esperaba que
la sexta no apareciera casi nunca, razonando desde que ninguna muestra de filas
la había mostrado. Pero *la API omite las claves nulas*, así que una muestra
subestima el esquema — cosa que este mismo documento advierte. "No apareció en
las muestras" y "está casi siempre vacía" son afirmaciones distintas, y de la
primera no se sigue la segunda.

⚠ **Y las seis están presentes en las 2.824.446 filas, sin una sola ausencia ni
un solo centinela.** Eso acota la advertencia de H6 sobre las claves omitidas:
vale para `ultima_actualizacion` y las fechas de hito, no para estas. Son
esquema estable, y `staging` no tiene que rellenarlas.

**La muestra, que es parte del resultado:** el universo vivo, no el histórico.
RN1 sobre contratos cerrados o liquidados puede comportarse distinto y esto no
lo mide.

#### Los 93.557 que no cierran — pregunta abierta 13

El 3,31% de los contratos vivos declaran fuentes que **no suman su propio
valor**, y las diez diferencias inspeccionadas son **todas negativas**: la suma
de las seis queda por debajo de `valor_del_contrato`. Los montos no son
menores — uno de 1.062 millones de pesos.

Diez de diez con el mismo signo no es casualidad. Tres explicaciones, sin
separar:

1. Hay una séptima fuente de financiación que el esquema nombra de otro modo.
2. `valor_del_contrato` incluye algo que las fuentes no —adiciones ya aprobadas,
   por ejemplo—, y entonces RN1 hay que formularla contra un valor base y no
   contra el actual.
3. Es un incumplimiento real de la fuente, y entonces es un hallazgo de calidad
   publicable.

La tercera sería material para el README. **Pero antes hay que descartar que el
error sea nuestro**, y la vía barata es cruzar esos contratos contra Adiciones:
si la diferencia coincide con el monto de las adiciones registradas, es la
segunda y RN1 se reformula.

Esto **no bloquea** a `stg_contratos`: la definición de RN1 está cerrada. Lo que
bloquea es fijar el umbral con el que la regla falla en dbt.

---

### H7 — Datos personales sensibles

El dataset expone cédulas, nombres completos, género y **domicilio residencial**
del representante legal (ej. `"AMBAR RESERVA APTO 1006 TORRE A"`), del ordenador
del gasto y del supervisor.

Son datos legalmente abiertos, pero republicarlos en un tablero público es una
decisión distinta a consultarlos.

**Decisión:** estas columnas se excluyen del modelo desde el diseño. Se documenta
en el README como criterio explícito.

Son **18 columnas** y el filtro corre en el `$select`, no después: la exclusión
más barata de auditar es la que hace que el dato no viaje. Es la única exclusión
que vive en la extracción; el corte de 2020 y los estados pre-firma son filtros
de negocio y viven en dbt, donde son reversibles. Acá la irreversibilidad es la
característica buscada.

---

### H8 — `ultima_actualizacion` no es lo que su nombre sugiere

**Por qué se validó:** el campo tenía 42% de nulos (H2, etapa 2). Un watermark
con ese nivel de ausencia no se puede usar sin entender qué significa el nulo.

**Hipótesis inicial (descartada):** que los nulos fueran los contratos en estado
terminal, dado que ~43% del dataset está en Cerrado / terminado / Cancelado.

**Consulta:**

```
?$select=estado_contrato,count(*) as n&$where=ultima_actualizacion IS NULL&$group=estado_contrato
```

| Estado | Nulos | Total del estado | % nulo |
|---|---|---|---|
| En ejecución | 1.728.553 | 1.737.502 | **99,5%** |
| Borrador | 245.385 | 245.385 | 100% |
| Aprobado | 213.109 | 214.615 | 99,3% |
| Cancelado | 110.625 | 110.665 | 99,9% |
| enviado Proveedor | 43.924 | 43.924 | 100% |
| Modificado | 41.953 | 1.081.413 | 3,9% |
| terminado | 33.864 | 774.500 | 4,4% |
| Cerrado | 66.607 | 1.690.510 | 3,9% |
| En aprobación | 24.712 | 24.712 | 100% |
| cedido | 846 | 28.557 | 3,0% |
| Suspendido | 126 | 6.650 | 1,9% |

Suma: 2.509.704 

**La hipótesis era exactamente al revés.** Los contratos que llegaron a un
desenlace (Cerrado, terminado, Modificado, cedido) casi todos tienen fecha. Los
que están simplemente en ejecución, casi ninguno.

**Conclusión:** `ultima_actualizacion` **no es un campo de auditoría técnica**.
Es la fecha del último **evento contractual**: modificación, cesión, suspensión,
cierre o liquidación. Si a un contrato no le ha pasado nada desde su firma, el
campo queda vacío.

El nombre es engañoso y la definición del diccionario ("Fecha de última
actualización del contrato electrónico") no lo aclara. Solo se descubre cruzando
el diccionario con la distribución real de los datos.

**Uso correcto:** sirve como watermark para el flujo de eventos contractuales
(flujo 2 de H2), no como watermark general. El nulo no es un dato faltante: es
información — significa "sin eventos posteriores a la firma".

**Dimensionamiento del flujo:**

```
?$select=count(*) as n&$where=ultima_actualizacion > '2026-08-10T00:00:00'
```

Resultado: 14.459 en 7 días ≈ **2.065 eventos/día**.

**Nota sobre el rango:** el mínimo es 2016-01-29 aunque la fuente arranca en
2015-06-11. Consistente con la interpretación: los contratos de 2015 no
registraron eventos posteriores.

**Nota sobre freshness:** el máximo es 2026-08-17, igual que el de
`fecha_de_firma`. La fuente tiene ~1 día de rezago. Se dijo que el test de
`freshness` de dbt debía alertar a las **48 horas**, no a las 24, para no dar
falsos positivos todos los días.

⚠ **Las 48 horas no alcanzan.** El 28/08/2026 el corte vivo era el del 25: una
fuente que no tiene nada roto llevaba tres días sin regenerar. Un `freshness` de
48 h habría alertado sobre una fuente sana. El umbral no se puede fijar hasta
tener el registro de sondeo de H34, y hay que decidir además **contra qué se
mide**: contra `ultima_actualizacion` (el negocio) o contra `:updated_at` (la
regeneración). Son dos preguntas distintas y hoy el documento solo contempla la
primera.

**Hora de regeneración (H24, en `02_ecosistema_secop.md`).** Hay tres
regeneraciones fechadas: `09:22:15Z`, `09:41:20Z` y `09:05:54Z`, o sea **04:22,
04:41 y 04:06 hora de Colombia**. Se mueven en una ventana de ~35 minutos.

⚠ **04:41 no es un horario y no se puede programar contra él.** Este documento
decía que ese valor "define el `schedule` del DAG". Es la más tardía de tres
observaciones, no una hora publicada, y H34 muestra además que hay días sin
ninguna regeneración: ningún `schedule` acierta contra un evento que a veces no
ocurre. → *El disparador es el corte, no el calendario: ver D11 en*
`03_decisiones_capa_raw.md`.

---

### H9 — La ejecución financiera cambia sin dejar rastro 

**Por qué se validó:** los campos `valor_facturado`, `valor_pagado`,
`valor_pendiente_de_pago` y `valor_amortizado` son acumulados que se mueven
durante la vida del contrato. Si se mueven sin que ninguna fecha lo registre,
existe un mecanismo de cambio invisible para todos los watermarks.

**Consulta:**

```
?$select=count(*) as n&$where=estado_contrato='En ejecución' AND valor_pagado > 0 AND ultima_actualizacion IS NULL
```

Resultado: **735.809**

**Conclusión:** 735.809 contratos (42% de los que están en ejecución) tienen
pagos registrados y **ninguna columna de fecha lo refleja**. El dinero se movió;
el dataset no lo dice.

**Consecuencias:**

1. Ningún watermark puede capturar el avance de ejecución financiera. Requiere el
   flujo 3 de H2: refresco del universo vivo en cada regeneración (H34).
2. **Este es el hallazgo que más justifica la plataforma.** La serie temporal de
   ejecución financiera por contrato —cuánto se había pagado en cada momento— no
   existe en ninguna fuente pública. Solo puede construirse tomando snapshots a
   lo largo del tiempo, que es precisamente lo que hará el pipeline.

   Dicho de otro modo: el SCD tipo 2 deja de ser un requisito de tutorial y pasa
   a ser lo único que justifica que la plataforma exista.

**Se buscó esta serie en todo el ecosistema y no está**: no hay columna de valor
en el dataset de modificaciones (H17), su única fecha llega truncada a nivel de
día en el 83% de las filas (H33), y la publicación en OCDS que sí conservaba
enmiendas se apagó en abril de 2022 (H21). Tres verificaciones independientes
que endurecen la afirmación.

El argumento no se apoya en la fecha: aunque `fecharegistro` estuviera intacta,
seguiría faltando **el monto**, que es lo que la pregunta 7 necesita. La fecha
truncada agrava, no sostiene.

El único candidato del ecosistema que queda sin evaluar es
`SECOP II – Ejecución de Contratos` (pregunta abierta 8).

---

### H34 — La fuente no se regenera todos los días (CRÍTICO)

**Por qué se validó:** todo el proyecto se escribió sobre la frase "la fuente se
regenera cada noche". Nadie la comprobó. La ficha oficial declara frecuencia
diaria, y una frecuencia declarada es una promesa, no una medición.

**Consulta**, la misma de la etapa 1 de H2:

```
?$select=min(:updated_at) as mas_viejo,max(:updated_at) as mas_nuevo
```

**Resultado el 28/08/2026, ~10:00 COT:**

```json
{"mas_viejo":"2026-08-25T09:05:54.277Z","mas_nuevo":"2026-08-25T09:05:54.277Z"}
```

El corte vivo era del **martes 25**. La consulta se hizo un **viernes**.

#### El registro completo

| Día | Evidencia | Lectura |
|---|---|---|
| mar 18 | corte fechado `09:22:15.735Z` | regeneró |
| mié 19 | — | sin observación |
| jue 20 | corte fechado `09:41:20.358Z` | regeneró |
| **vie 21** | a las ~09:37 COT el corte vivo era el del 20 | **no regeneró** |
| sáb 22 – lun 24 | — | sin observación |
| mar 25 | corte fechado `09:05:54.277Z` | regeneró |
| **mié 26** | a las 20:30 COT el corte vivo era el del 25 | **no regeneró** |
| **jue 27** | deducido: si hubiera regenerado, el corte vivo del 28 sería suyo | **no regeneró** |
| **vie 28** | a las ~10:00 COT el corte vivo sigue siendo el del 25 | **no regeneró** |

Tres regeneraciones y cuatro días sin regenerar, tres de ellos consecutivos.
Saltos observados entre cortes: **dos días** (18→20) y **cinco días** (20→25).
**Ningún par de cortes separados por exactamente un día**, en todo el registro.
Ninguna regeneración observada en fin de semana; las tres conocidas caen martes,
jueves y martes.

**La calidad de cada fila es distinta y conviene no aplanarla:** las del 21, 26 y
28 son observaciones directas; la del 27 es una deducción —si hubiera habido un
corte del 27, sería el que está vivo hoy—; el resto son huecos donde nadie miró.

#### No es una caída de la plataforma

El control es el dataset hermano de Adiciones (`cb9c-h8sn`), que escribe en
continuo (H23) y por lo tanto sirve de testigo:

| Momento | `max(:updated_at)` del hermano |
|---|---|
| 26/08 ~20:30 COT | `2026-08-26T11:21:12.119Z` |
| 28/08 ~10:00 COT | `2026-08-28T09:51:29.013Z` |

La plataforma transaccional está viva y escribiendo. Lo que no corre es el ETL
que regenera la vista publicada. Son dos sistemas y solo uno está detenido.

#### El dato del 21 estaba en este documento desde el principio

La etapa 1 de H2 anotaba: *"Reconfirmado el 21/08/2026: min = max =
2026-08-20T09:41:20.358Z"*. Esa consulta se hizo cerca de las 09:37 COT del
viernes 21 —lo fecha la FASE 3 de H23, cuyos hermanos marcaban 14:28Z y 14:36Z—,
o sea cinco horas después del final de la ventana de regeneración. **La fuente
llevaba un día sin regenerar y el documento lo registró como confirmación de que
todo iba bien.**

No es un dato nuevo: es un dato que estaba mal leído. Y no invalida nada de H2,
que era lo que la consulta buscaba comprobar. → *ver la lección de método 9.*

#### Qué se cae

- **La palabra "noche"** en todas las frases del proyecto. Lo correcto es "cada
  vez que se regenera".
- **El `schedule` del DAG contra las 04:41.** Ningún horario acierta contra un
  evento que a veces no ocurre. → *D11.*
- **El `freshness` de 48 h**, que hoy alertaría sobre una fuente sana. → *ver la
  nota de H8.*
- **El delta de veinticuatro horas** como cosa que se puede medir a voluntad:
  exige un par de cortes separados por un día, y no existe ninguno.
- **El ancho del intervalo de la corrida incremental del 25/08**, que estaba
  anotado como dos días y está entre dos y cinco. Irrecuperable. → *ver
  `03_decisiones_capa_raw.md`.*

#### Qué NO se cae

**H2, que sale reforzado.** El reemplazo total se observó cuatro veces. Lo que
cambia es cada cuánto ocurre, no qué ocurre.

**La premisa del proyecto.** Cada regeneración destruye el estado anterior; que
ocurra tres veces por semana en vez de siete no la debilita en nada. Si acaso al
revés: menos cortes significa menos oportunidades de capturar la historia, y
perder una cuesta más.

**El diseño de la capa raw.** `observado_desde` / `observado_hasta` ya había
decidido no prometer resolución diaria, y ya estaba escrito que la serie iba a
tener huecos. La cadencia irregular confirma esa decisión por un camino que no
se había previsto.

#### El supuesto que se adopta para poder seguir

**Se supone que hay al menos una regeneración por semana.** Es un supuesto de
planificación y **no un dato**: el salto máximo observado es de cinco días y el
salto en curso, al cerrar esta nota, es de tres. Se verifica con un **registro de
sondeo**: una línea por día con la fecha, la hora COT y el valor de
`max(:updated_at)`. Si algún intervalo pasa de siete días, este hallazgo hay que
reescribirlo.

Del registro dependen tres cosas que hoy no se pueden fijar: el umbral de
`freshness`, el margen del DAG y si existe un patrón de días hábiles.

#### Preguntas que deja abiertas

1. ¿Regenera los fines de semana? Ninguna observación, y los tres cortes
   conocidos son de días hábiles.
2. ¿Hay un anuncio público de la ANCP-CCE sobre interrupciones del proceso ETL?
   Si lo hay, es una cita para el README.
3. ¿La ventana de 35 minutos aguanta con más observaciones, o es un artefacto de
   tener solo tres?

---

## Reglas de negocio para tests de dbt

Derivadas de los hallazgos, no inventadas para llenar el requisito.

> **La lista canónica vive en `01_modelo_dimensional.md` §10.** Acá se listan
> con su origen; si las dos se desincronizan, manda el modelo dimensional.

| ID | Regla | Origen |
|---|---|---|
| RN1 | La suma de las **seis** fuentes de financiación iguala `valor_del_contrato` | H6 |
| RN2 | Ningún registro de la tabla de hechos tiene estado pre-firma | H4, H5 |
| RN3 | Ningún registro de la tabla de hechos tiene `fecha_de_firma` nula | H3, H4 |
| RN4 | La fuente no tiene más de 48 horas de rezago (`freshness`) | H8 |
| RN5 | `valor_pagado` no decrece entre versiones consecutivas | H9 — es un acumulado |
| RN6 | RN1 se cumple en toda versión histórica, no solo en la fila actual | RN1 + diseño SCD2 |
| RN7 | `dias_adicionados` y `fecha_de_fin_del_contrato` cambian juntos | Dominio — son el mismo evento |
| RN8 | `valor_de_pago_adelantado = valor_amortizado + valor_pendiente_de` | Diccionario oficial |
| RN9 | Si `el_contrato_puede_ser_prorrogado = "No"`, entonces `dias_adicionados = 0` | Coherencia interna |
| RN10 | Si `habilita_pago_adelantado = "No"`, entonces `valor_de_pago_adelantado = 0` | Coherencia interna |
| RN11 | Las adiciones no superan el 50% del valor inicial, en SMLMV al momento de la firma | Ley 80 art. 40 |

RN5 es interesante en los dos resultados posibles: si decrece, o hubo reversión
de un pago o la fuente tiene un error. Ambos casos valen la pena.

⚠ **RN5 protege `valor_pagado`, que es acumulado. No generalizar a
`valor_del_contrato`**, que sí puede bajar: el dataset oficial de modificaciones
tiene un tipo `REDUCCION EN EL VALOR` (H27).

 **RN9 y RN10 tienen una trampa:** `habilita_pago_adelantado` **no es
booleana**. Se observó en `"No Definido"` — tres estados, y `"No Definido"` no
equivale a `"No"`.

---

## Lecciones de método

Aplicables a cualquier fuente futura, no solo a esta.

1. **Explorá antes de leer, pero leé antes de concluir.** Mirar los datos primero
   genera preguntas específicas que hacen que el diccionario se lea en cinco
   minutos en vez de una hora. Pero cerrar una conclusión de diseño sin haber
   consultado el diccionario lleva a errores: H2 estuvo mal escrita hasta que el
   documento reveló `ultima_actualizacion`.
2. **Las funciones de agregación ignoran los nulos en silencio.** `min/max`
   reportó un rango limpio ocultando 423.975 filas sin fecha. Hacé siempre el
   `GROUP BY` completo.
3. **Una fila no revela el esquema** cuando la API omite las claves nulas. Contar
   columnas desde una muestra individual subestima la estructura real.
   Corolario: **enumerar el esquema contra el endpoint de metadatos**, no
   inferirlo de los datos. Fue así como apareció la sexta fuente de
   financiación, que ninguna muestra había mostrado.
4. **Probá la hipótesis obvia y aceptá cuando falla.** En H8 la explicación
   intuitiva de los nulos era la opuesta a la real. Verificarla fue lo que reveló
   la semántica verdadera del campo.
5. **El diccionario oficial puede estar equivocado.** Se contradice sobre el
   grano (H1) y define mal `nombre_representante_legal` (H6). La evidencia
   empírica prevalece, pero hay que dejar constancia de la discrepancia.
6. **Buscá la misma realidad publicada dos veces.** Si el mismo
   hecho aparece en dos datasets, compararlos revela defectos que ninguno
   confiesa por separado. H33 —una fecha con el mes y el día truncados— solo fue
   visible cruzando Adiciones contra Suspensiones.

   Y si al compararlos los conteos coinciden **exactamente**, no es
   coincidencia: son las mismas filas. Catorce números iguales fueron la pista;
   la verificación fila a fila vino después.

   **Corolario que costó aprender: el cruce descubre el defecto, no lo mide.**
   Ocho filas cruzadas revelaron el truncamiento de H33; hicieron falta seis
   consultas agregadas para saber que afecta a 26,5 millones de filas, que el
   mes sobrevive en el 79% y que el daño es identificable fila por fila. Y una
   de esas seis salió mal la primera vez, por aplicarle al mes el umbral del
   día. Una muestra que revela un patrón invita a darlo por medido.
7. **Los tipos declarados no garantizan nada.** `fecharegistro`
   está declarada como fecha, parsea sin error, y está sistemáticamente mal. Un
   tipo válido no es un valor correcto.
8. **Las etiquetas de la fuente no son de fiar, ni las de afuera ni las de
   adentro.** Afuera: "Adiciones" es un log de modificaciones donde
   las adiciones son una minoría, y la ficha de Suspensiones no declara que sea
   una vista derivada, siéndolo. Adentro: el tipo `ADICION EN EL VALOR` existe
   como categoría pero no sirve como filtro, porque hay adiciones escondidas en
   el tipo genérico. Que una categoría exista no significa que sea exhaustiva.
9. **Una frecuencia declarada no es una medición, y una confirmación puede tapar
   un hallazgo.** La ficha declaraba frecuencia diaria y nadie la comprobó
   durante ocho días de exploración. Peor: la evidencia de lo contrario **ya
   estaba en este documento**, anotada como "reconfirmado" porque confirmaba lo
   que se le estaba preguntando (H2, el reemplazo total) mientras contradecía en
   silencio lo que no se le preguntaba (la cadencia). Ver H34.

   El corolario es incómodo y general: **una consulta hecha para confirmar A
   puede contener la refutación de B, y solo se ve si uno mira el dato entero.**
   La defensa concreta es barata: anotar siempre *cuándo* se hizo la consulta,
   no solo qué devolvió. Fue la hora de la corrida del 21 —recuperada desde los
   datasets hermanos— lo que permitió releer ese dato ocho días después.

---

## Preguntas abiertas

**Resueltas:**

- ~~¿Qué es `valor_pendiente_de`?~~ → **Valor Pendiente de Amortización**, según
  el diccionario oficial. Coherente con la existencia de `valor_amortizado`.
- ~~¿Cómo se representan las modificaciones?~~ → Sí existe un registro de
  eventos, en un dataset aparte que no es evidente desde la fuente principal: el
  dataset `SECOP II – Adiciones` (`cb9c-h8sn`), una fila por modificación, con
  tipo y justificación. Pero **no tiene ninguna columna de valor** —el monto está
  en prosa dentro del texto libre (H17)— y su única fecha, `fecharegistro`,
  **trunca mes y día al primer dígito significativo** (H33, confirmado sobre las
  26.571.106 filas del dataset). El año sobrevive siempre, el mes en el 79,0% de
  las filas y la fecha completa en el 13,6%, y se sabe fila por fila cuáles son.
  El evento existe; su monto no es utilizable y su fecha lo es solo en parte.
- ~~¿Qué contienen `fecha_de_inicio_de_ejecucion`, `fecha_fin_liquidacion` y
  `estado_bpin`?~~ → `fecha_fin_liquidacion` existe y está clasificada como
  material; `fecha_de_inicio_de_ejecucion` y `estado_bpin` **no existen en la
  API**. Ver la tabla de H6.

**Pendientes:**

1. **¿`Cerrado` y `terminado` son sinónimos o estados distintos?** Son 1,69M y
   774K filas. El diccionario no enumera los valores posibles del campo. Habrá
   que resolverlo empíricamente comparando `fecha_de_fin_del_contrato`,
   `fecha_fin_liquidacion` y `liquidaci_n` entre ambos grupos.
2. **¿Qué miden `orden` y `rama`?** El diccionario los define de forma circular
   ("Orden entidad del estado que publica el contrato"). Los valores observados
   no coinciden con la intuición: un hospital departamental figura como
   "Nacional".
3. **¿Los estados terminales realmente no cambian?** `ESTADOS_VIVOS` excluye
   Cerrado, terminado y Cancelado del flujo 3. Es razonable pero no está
   probado: un contrato Cerrado podría recibir pagos rezagados, y si el supuesto
   es falso el flujo 3 es ciego a esos pagos.
4. **¿Cuántas columnas documenta realmente el diccionario?**  *Contradicción
   sin resolver.* La ficha dice 87 documentadas contra 85 reales, o sea dos
   ausentes. Pero H6 identifica **cinco** columnas documentadas que no
   existen en la API: `fecha_de_inicio_de_ejecucion`, `fecha_de_fin_de_ejecucion`,
   `estado_bpin`, `c_digo_bpin`, `anno_bpin`. Y `columnas.py` afirma —con un test
   que lo verifica— que sus cuatro conjuntos cubren las 85 sin solaparse, así que
   esas cinco no están clasificadas en ninguna parte.

   Cinco ausentes contra una diferencia declarada de dos. O el conteo de 87 está
   mal, o el diccionario documenta más campos de los contados, o alguna de esas
   columnas existe bajo un nombre que Socrata deformó y no se reconoció. Se
   cierra recontando el PDF contra el endpoint de metadatos.
5. **¿`origen_de_los_recursos` es redundante con las seis fuentes de
   financiación?** En una fila coincidía; una fila genera hipótesis, no
   conclusión. Requiere un cruce sobre el dataset completo. Se puede contestar
   contra raw, con el mismo recorrido que cerró RN1 (ver la pregunta 13): las
   seis columnas están en las 2.824.446 filas.
6. **¿Por qué `saldo_cdp` no se consume con la ejecución?**
7. **¿La llave de `dim_proveedor` es `documento_proveedor` o `codigo_proveedor`?**
8. **¿Aporta algo `SECOP II – Ejecución de Contratos`?** Sin evaluar. Es el
   candidato obvio para la serie de pagos que H9 demostró que no existe.
9. **¿Por qué la ANCP-CCE dejó de publicar OCDS en abril de 2022?** Si hay un
   anuncio público, es una cita valiosa para el README.
10. **¿La fuente regenera los fines de semana?** (H34) Ninguna observación; las
    tres regeneraciones conocidas caen martes, jueves y martes. Lo contesta el
    registro de sondeo, no una consulta.
11. **¿Hay un anuncio público sobre interrupciones del ETL de la ANCP-CCE?**
    (H34) Tres días consecutivos sin regenerar, con la plataforma transaccional
    escribiendo normalmente, es lo bastante visible como para que alguien lo
    haya dicho. Si existe, es cita de README igual que la pregunta 9.
12. **¿Contra qué se mide el `freshness` de dbt?** Contra `ultima_actualizacion`
    mide el rezago del negocio; contra `:updated_at` mide si la fuente se
    regeneró. Son dos alertas distintas y hoy solo está contemplada la primera,
    con un umbral —48 h— que H34 dejó sin piso.
13. **¿Por qué 93.557 contratos vivos no cierran RN1, y siempre por defecto?**
    Medido el 28/08 contra raw: el 3,31% del universo vivo declara fuentes de
    financiación que suman **menos** que su propio `valor_del_contrato`, con
    diferencias de hasta 1.062 millones. Las tres explicaciones posibles y la
    vía para separarlas están en H6, desagregación de financiación. **No bloquea
    a `stg_contratos`**: bloquea el umbral con el que RN1 falla en dbt.
14. **¿Por qué `liquidaci_n = "Si"` y `fecha_inicio_liquidacion` no coinciden?**
    290.792 contra 292.694, 1.902 de diferencia. O miden cosas distintas, o hay
    incoherencia en la fuente. Se cierra con una consulta cruzada sobre raw.
15. **¿Cuántos de los 32 contratos por encima del billón son reales?** El
    mínimo es 1,07 billones, que una obra grande puede valer; el máximo supera
    23 veces el PGN. Separar los legítimos de la basura es lo que RN13 tiene que
    resolver, y el umbral de sospecha todavía no está fijado.

---

## 2. Otras fuentes del ecosistema

### Evaluadas

| Dataset | ID | Veredicto |
|---|---|---|
| SECOP II – Adiciones | `cb9c-h8sn` | **Evaluado, fuera de la v1.** Log de modificaciones, **26.571.106 filas — 4,5× la fuente principal** (H29, medido). Cinco columnas, **ninguna de valor**. `fecharegistro` trunca mes y día (H33). La llave `id_contrato` empata sin trabajo |
| SECOP II – Suspensiones | `u99c-7mfm` | **Es una vista derivada de Adiciones** (H25), con las mismas filas y las etiquetas corregidas. No es fuente independiente. ~734.759 filas |
| SECOP II – Ejecución de Contratos | — | **Sin evaluar.** Candidato prioritario: es el único lugar donde podría estar la serie de pagos de H9 |
| SECOP II – Rubros Presupuestales | — | Sin evaluar |
| OCDS (Open Contracting Data Standard) | `ocds-k50g02` | **Existió y se apagó.** 3.008.861 enmiendas, enero 2011 – abril 2022, marcado como no actualizado por el publicador. La API devuelve 404 |

**Por qué los hermanos no entran a la v1.** Su valor ya se capturó como hallazgos
—H17 a H33 son material de README— sin cargar una sola fila. Incorporarlos
quintuplicaría el tamaño del proyecto (H29) y exigiría un **segundo patrón de
ingesta**:
se actualizan en continuo y tienen watermark propio (H23), a diferencia de la
fuente principal que se regenera entera. La v1 se define por hacer una cosa
impecablemente.

### Pendientes de evaluar

| Dataset | Etapa del ciclo | Decisión preliminar |
|---|---|---|
| SECOP II – Procesos de Contratación | Proceso previo al contrato | **Candidato v2** — son oportunidades abiertas, no contratos ya perdidos. Más valioso comercialmente. Fuera del alcance v1 por tener múltiples etapas y estados. El problema de llaves quedó resuelto: el `noticeUID` de `urlproceso` es la llave (H6) |
| SECOP II – Facturas | Ejecución y pago | Por evaluar. **Sube de prioridad tras H9:** podría contener la granularidad de pagos que Contratos Electrónicos no registra |
| TVEC – Tienda Virtual del Estado Colombiano | Compra por acuerdo marco | Candidato detectado en el diccionario oficial. ~150.673 órdenes de compra. Llave: `identificador_de_la_orden`. Volumen pequeño pero es un canal de compra distinto |
| Plan Anual de Adquisiciones | Planeación | Por evaluar |
| SECOP I – Proponentes | Registro de proveedores | Por evaluar |

### Advertencia sobre el catálogo

Muchos datasets de `datos.gov.co` son vistas derivadas, no fuentes distintas. Si
la ficha dice "Vista en función de X" o "creado por un miembro del público", hay
que ignorarlo e ir al maestro. Ejemplos de vistas encontradas: "…PYMES",
"…ACTIVOS", "…del Departamento de Sucre", "…INVIAS", "CONTRATOS ELECTRONISHBSE",
"SECOP II – Contratos – 2017".

 **La señal no siempre está.** La ficha de `SECOP II – Suspensiones` **no
declara** que sea derivado, y lo es: las mismas filas de
Adiciones, con las etiquetas corregidas (H25). Se descubrió comparando conteos
anuales entre los dos datasets, no leyendo fichas. Cuando dos datasets cubren el
mismo hecho, hay que compararlos aunque ninguno se declare derivado.

### SECOP I vs SECOP II

Son dos generaciones, no alternativas. SECOP I era un tablón de anuncios (datos
pobres, ya no crece); SECOP II es transaccional. Se usa SECOP II.

Y son dos **plataformas**, no dos agencias: Colombia Compra Eficiente es la
agencia que las administra. La tercera plataforma es TVEC. Marco normativo en
tres capas: Ley 80 de 1993 (estatuto de contratación), Ley 1150 de 2007 (crea el
SECOP), Ley 1712 de 2014 (obliga a publicarlo como dato abierto).