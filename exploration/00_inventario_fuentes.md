# Inventario de fuentes — SECOP

> Registro de evaluación de las fuentes candidatas del ecosistema SECOP.
> Cada hallazgo va acompañado de la consulta que lo demuestra, para que sea
> reproducible por cualquiera.
> **Alcance:** este documento cubre la fuente principal (`jbjy-vk9h`), con los
> hallazgos H1 a H9. Los datasets hermanos del ecosistema y sus hallazgos
> H17–H33 están en `02_ecosistema_secop.md`; acá se listan en la sección 2
> con su veredicto. Las **decisiones de diseño** que salieron de estos hallazgos
> tampoco viven acá: se las referencia con →.
>
> **Cómo leerlo:** empezá por el glosario si no venís del dominio. Después los
> hallazgos en orden: cada uno abre con *por qué se validó*, sigue con la
> consulta exacta y su resultado, y cierra con la conclusión.
>
> Última verificación contra la API: 21 de agosto de 2026.

---

## Glosario

Términos que este documento usa constantemente. Si ya los conocés, saltealos.

**Grano** — qué representa una fila. "Una fila = un contrato" es distinto de
"una fila = una versión de un contrato", y confundirlos infla todos los totales.
Es la primera pregunta de cualquier modelo de datos.

**Watermark** (marca de agua) — una columna que dice *cuándo cambió cada fila*.
Sirve para pedirle a la fuente solo lo nuevo, en vez de descargar todo cada vez.
Sin watermark no hay carga incremental posible.

**Carga incremental** — traer solo lo que cambió desde la última corrida, en
lugar de rehacer todo. Es lo que hace que un pipeline diario sea barato.

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
dato más reciente tiene más de X horas, algo se rompió río arriba.

**Columna material** — una columna cuyo cambio significa que el contrato cambió
de verdad, y por eso genera una versión nueva. Se opone a *cosmética*, donde
cambió el registro y no el contrato (una tilde corregida). El detalle está en
`03_decisiones_capa_raw.md`.

**Vista derivada** — un dataset del portal que no es una fuente propia, sino un
recorte o una copia de otro. Usarla en vez del maestro trae datos incompletos
sin avisar.

**ETL / ELT** — el proceso de mover datos de un lado a otro transformándolos.
*Extract, Transform, Load*; en ELT se transforma después de cargar.

**ESE** — Empresa Social del Estado. Son los hospitales públicos colombianos.

**PGN, SGP, SGR** — las tres grandes bolsas del presupuesto público colombiano:
Presupuesto General de la Nación, Sistema General de Participaciones (lo que la
nación transfiere a municipios y departamentos) y Sistema General de Regalías
(lo que produce la explotación de recursos naturales).

**Dígito de verificación** — el último número del NIT colombiano, separado por un
guion. Sirve para detectar errores de tipeo. La fuente a veces lo incluye y a
veces no, así que el mismo NIT aparece escrito de dos formas.

**UNSPSC** — clasificador internacional de bienes y servicios, con una jerarquía
de cuatro niveles. Es lo que permite preguntar "¿quién compra lo que yo vendo?".

⚠ **"Partición" significa dos cosas distintas** y conviene no mezclarlas:
  - **Ventana de backfill** — un pedazo del histórico, normalmente un mes. Se
    usa para reprocesar el pasado sin bajar todo de una vez.
  - **Partición de paralelismo** — un pedazo del universo vivo que se reparte
    entre varios procesos **de la misma noche**, para que terminen antes.

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

## 1. SECOP II — Contratos Electrónicos ✅ ELEGIDA

### Ficha

| Campo | Valor |
|---|---|
| Identificador | `jbjy-vk9h` |
| Tipo | Dataset maestro (no vista derivada) |
| Publica | Agencia Nacional de Contratación Pública – Colombia Compra Eficiente |
| Filas | 5.958.553 |
| Columnas | **85 en el esquema real**, enumeradas contra el endpoint de metadatos el 20/08/2026. El diccionario declara 87 (ver pregunta abierta 4) |
| Frecuencia declarada | Diaria |
| Rezago real de publicación | ~1 día (máximo observado: 2026-08-17) |
| Hora de regeneración | ~04:41 hora de Colombia (ver H8) |
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

La decisión se pagó sola: media docena de verificaciones posteriores se
resolvieron pegando URLs en el navegador, incluida la que demostró que
Suspensiones es una vista derivada (H25).

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

### H2 — La fuente tiene tres mecanismos de cambio y solo dos son detectables ⚠️ CRÍTICO

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
individuales en Socrata; regenera el dataset completo en una sola operación cada
noche. Coherente con la metodología declarada en el diccionario, que describe un
proceso ETL nocturno que genera las vistas publicadas. `:updated_at` es inútil
como watermark.

**Reconfirmado el 21/08/2026:** `min = max = 2026-08-20T09:41:20.358Z`. Tres días
después de la primera medición, mismo comportamiento.

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
   **cada noche**.

   ⚠ Es tentador acotarlo a `En ejecución` y correrlo semanal: son 1,7M de filas
   en vez de 2,8M. No alcanza. Un contrato `Modificado` o `Suspendido` sigue
   recibiendo pagos, y una semana de resolución pierde el orden de los eventos
   dentro de ese lapso.

   Los parámetros de fecha de `refresco_de_vivos()` son una **partición de
   paralelismo** —un reparto entre procesos de la misma noche— y **no** una
   ventana de backfill. Ver el glosario.

   ⚠ **Este flujo no admite backfill.** Pregunta por el estado actual, y el
   estado de una fecha pasada ya se destruyó. Reejecutarlo hacia atrás
   escribiría el hoy con fecha de ayer. → *Ver* El flujo 3 no se puede reejecutar hacia atrás *(R1) en*
   `03_decisiones_capa_raw.md`.

Los flujos 1 y 2 suman ~5.000 filas diarias: una sola petición. El DAG diario es
liviano; todo el peso está en el flujo 3.

**Consecuencia de fondo:** el historial no existe en el origen. Cada noche la
fuente sobrescribe su propio estado anterior, y nadie puede consultar cuánto
valía un contrato antes de una adición.

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

Suma: 5.958.553 ✅

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

⚠ **Contradicción sin resolver, ver pregunta abierta 4.** Son **cinco** columnas
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
dataset de Adiciones es el 22% de los tipos de modificación (H28).

#### Columna clave para el caso de uso comercial

`codigo_de_categoria_principal` = `"V1.80111701"` es un código **UNSPSC**, el
clasificador estándar internacional de bienes y servicios. Responde la pregunta
"¿qué entidades públicas compran lo que yo vendo?". Requiere quitar el prefijo
`V1.` y decidir el nivel de agregación de la jerarquía.

El diccionario de SECOP I documenta la jerarquía completa —Grupo → Familia →
Clase— y remite al clasificador oficial en
`colombiacompra.gov.co/clasificador-de-bienes-y-servicios`, que es la fuente para
traducir códigos a nombres legibles en la dimensión de categoría.

#### Desagregación de financiación

`presupuesto_general_de_la_nacion_pgn`, `sistema_general_de_participaciones`,
`sistema_general_de_regal_as`,
`recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_`,
`recursos_de_credito`, `recursos_propios`.

**Son seis, no cinco.** La sexta se descubrió al enumerar el esquema completo;
este documento decía cinco. En la fila inspeccionada las seis suman exactamente
`valor_del_contrato`: es la base de RN1, que **queda pendiente de revisión**
hasta decidir si la sexta entra en la suma.

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

Suma: 2.509.704 ✅

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
`fecha_de_firma`. La fuente tiene ~1 día de rezago. El test de `freshness` de dbt
debe alertar a las **48 horas**, no a las 24, o va a dar falsos positivos todos
los días.

**Hora de regeneración (H24).** El `:updated_at` del 21/08/2026 marcaba
`2026-08-20T09:41:20.358Z`, es decir **04:41 hora de Colombia**. Es el primer
dato duro sobre *cuándo* se rehace la fuente, y define el `schedule` del DAG:
programarlo a medianoche leería el corte del día anterior todas las noches.

Es una observación de una corrida, **no un horario publicado**. Confirmar en dos
o tres días distintos antes de escribirlo en Airflow.

---

### H9 — La ejecución financiera cambia sin dejar rastro ⚠️

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
   flujo 3 de H2: refresco nocturno del universo vivo.
2. **Este es el hallazgo que más justifica la plataforma.** La serie temporal de
   ejecución financiera por contrato —cuánto se había pagado en cada momento— no
   existe en ninguna fuente pública. Solo puede construirse tomando snapshots a
   lo largo del tiempo, que es precisamente lo que hará el pipeline.

   Dicho de otro modo: el SCD tipo 2 deja de ser un requisito de tutorial y pasa
   a ser lo único que justifica que la plataforma exista.

**Se buscó esta serie en todo el ecosistema y no está**: no hay columna de valor
en el dataset de modificaciones (H17), su única fecha está corrupta (H33), y la
publicación en OCDS que sí conservaba enmiendas se apagó en abril de 2022 (H21).
Tres verificaciones independientes que endurecen la afirmación.

El único candidato del ecosistema que queda sin evaluar es
`SECOP II – Ejecución de Contratos` (pregunta abierta 8).

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

⚠ **RN9 y RN10 tienen una trampa:** `habilita_pago_adelantado` **no es
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
7. **Los tipos declarados no garantizan nada.** `fecharegistro`
   está declarada como fecha, parsea sin error, y está sistemáticamente mal. Un
   tipo válido no es un valor correcto.
8. **Las etiquetas de la fuente no son de fiar, ni las de afuera ni las de
   adentro.** Afuera: "Adiciones" es un log de modificaciones donde
   las adiciones son una minoría, y la ficha de Suspensiones no declara que sea
   una vista derivada, siéndolo. Adentro: el tipo `ADICION EN EL VALOR` existe
   como categoría pero no sirve como filtro, porque hay adiciones escondidas en
   el tipo genérico. Que una categoría exista no significa que sea exhaustiva.

---

## Preguntas abiertas

**Resueltas:**

- ~~¿Qué es `valor_pendiente_de`?~~ → **Valor Pendiente de Amortización**, según
  el diccionario oficial. Coherente con la existencia de `valor_amortizado`.
- ~~¿Cómo se representan las modificaciones?~~ → Sí existe un registro de
  eventos, en un dataset aparte que no es evidente desde la fuente principal: el
  dataset `SECOP II – Adiciones` (`cb9c-h8sn`), una fila por modificación, con
  tipo y justificación. Pero **no tiene ninguna columna de valor** —el monto está
  en prosa dentro del texto libre (H17)— y su única fecha, `fecharegistro`, está
  **corrupta**: mes y día truncados al primer dígito significativo, solo el año
  sobrevive (H33). El evento existe; ni su monto ni su fecha son utilizables.
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
4. **¿Cuántas columnas documenta realmente el diccionario?** ⚠ *Contradicción
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
   conclusión. Requiere un cruce sobre el dataset completo.
6. **¿Por qué `saldo_cdp` no se consume con la ejecución?**
7. **¿La llave de `dim_proveedor` es `documento_proveedor` o `codigo_proveedor`?**
8. **¿Aporta algo `SECOP II – Ejecución de Contratos`?** Sin evaluar. Es el
   candidato obvio para la serie de pagos que H9 demostró que no existe.
9. **¿Por qué la ANCP-CCE dejó de publicar OCDS en abril de 2022?** Si hay un
   anuncio público, es una cita valiosa para el README.

---

## 2. Otras fuentes del ecosistema

### Evaluadas

| Dataset | ID | Veredicto |
|---|---|---|
| SECOP II – Adiciones | `cb9c-h8sn` | **Evaluado, fuera de la v1.** Log de modificaciones, >6M filas (más grande que la fuente principal). Cinco columnas, **ninguna de valor**. `fecharegistro` corrupta (H33). La llave `id_contrato` empata sin trabajo |
| SECOP II – Suspensiones | `u99c-7mfm` | **Es una vista derivada de Adiciones** (H25), con las mismas filas y las etiquetas corregidas. No es fuente independiente. ~734.759 filas |
| SECOP II – Ejecución de Contratos | — | **Sin evaluar.** Candidato prioritario: es el único lugar donde podría estar la serie de pagos de H9 |
| SECOP II – Rubros Presupuestales | — | Sin evaluar |
| OCDS (Open Contracting Data Standard) | `ocds-k50g02` | **Existió y se apagó.** 3.008.861 enmiendas, enero 2011 – abril 2022, marcado como no actualizado por el publicador. La API devuelve 404 |

**Por qué los hermanos no entran a la v1.** Su valor ya se capturó como hallazgos
—H17 a H33 son material de README— sin cargar una sola fila. Incorporarlos
duplicaría el tamaño del proyecto y exigiría un **segundo patrón de ingesta**:
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

⚠ **La señal no siempre está.** La ficha de `SECOP II – Suspensiones` **no
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