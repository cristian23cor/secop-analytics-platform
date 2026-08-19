# Inventario de fuentes — SECOP

> Registro de evaluación de las fuentes candidatas del ecosistema SECOP.
> Cada hallazgo va acompañado de la consulta que lo demuestra, para que sea
> reproducible por cualquiera.
> Última actualización: 18 de agosto de 2026

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
| Columnas | 87 según el diccionario oficial; 85 visibles en una fila de muestra (ver H6) |
| Frecuencia declarada | Diaria |
| Rezago real de publicación | ~1 día (máximo observado: 2026-08-17) |
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

Ver H9.

#### Conclusión consolidada

| Mecanismo de cambio | Columna que lo detecta | Volumen |
|---|---|---|
| Contrato nuevo | `fecha_de_firma` | ~2.900/día |
| Evento contractual (modificación, cesión, cierre, liquidación) | `ultima_actualizacion` | ~2.065/día |
| Avance de ejecución financiera (pagos, facturación) | **ninguna** | 735.809 contratos afectados |

**Estrategia de extracción resultante — tres flujos:**

1. **Nuevos** — ventana diaria sobre `fecha_de_firma`.
2. **Eventos** — ventana diaria sobre `ultima_actualizacion`.
3. **Deriva financiera** — refresco periódico (semanal) del conjunto
   "En ejecución". No hay atajo: hay que reextraer y comparar. 1,7M de filas son
   ~350 peticiones de 5.000, unos veinte minutos. Los pagos estatales no son
   intradía, así que la periodicidad semanal es defendible.

Los flujos 1 y 2 suman ~5.000 filas diarias: una sola petición. El DAG diario es
liviano.

**Consecuencia de fondo — la razón de ser del proyecto:**

El historial no existe en el origen. Cada noche la fuente sobrescribe su propio
estado anterior, y además hay una dimensión completa del cambio —cuánto se ha
pagado de cada contrato a lo largo del tiempo— que no está registrada en ninguna
parte, ni en los datos ni en el diccionario.

Esta plataforma construirá esa serie tomando snapshots. **El SCD tipo 2 deja de
ser un requisito de tutorial y pasa a ser lo único que justifica que la
plataforma exista.**

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
El backfill son ~80 particiones mensuales de 2020 a 2026, ninguna superior a
~100.000 filas.

**Conclusión 3 — lección de método:** `min()` y `max()` habían reportado el rango
2015–2026 sin mencionar las 423.975 filas nulas. **Las funciones de agregación
ignoran los nulos en silencio.** El `GROUP BY` completo se hace siempre, aunque
parezca redundante frente a un `min/max` ya ejecutado.

---

### H4 — Los nulos de fecha de firma son todos pre-firma

**Por qué se validó:** particionar el backfill por año de firma dejaría 423.975
filas huérfanas sin que ningún error lo advirtiera.

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
técnico de partición como efecto colateral. Cuando una decisión de modelado
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

Esta hipótesis quedó reforzada por H8: los contratos `Modificado` casi siempre
tienen `ultima_actualizacion` poblada, lo que sugiere que el estado cambia
cuando ocurre el evento y se lleva la fecha consigo.

**Decisión:** derivar en la capa `intermediate` columnas propias
(`esta_vigente`, `fue_modificado`) con la lógica documentada. No usar
`estado_contrato` crudo como máquina de estados.

**Inconsistencia de formato:** `terminado`, `cedido` y `enviado Proveedor` no
respetan la capitalización de los demás, lo que sugiere orígenes o épocas
distintas dentro del sistema fuente. Se normaliza en `staging`.

**Anomalía menor:** `Borrador` suma 245.385 en total pero solo 244.947 tienen
fecha de firma nula. Quedan **438 contratos en Borrador con fecha de firma**, lo
cual es contradictorio. No afecta el modelo (se excluyen igual), pero se
documenta.

---

### H6 — Observaciones sobre el esquema

Obtenidas de inspeccionar una fila completa (`?$limit=1`) y de contrastarla con
el diccionario oficial.

#### Lección de método: una fila no revela el esquema

La fila de muestra trajo 85 claves; el diccionario documenta 87 columnas.
**Socrata omite del JSON las claves cuyo valor es nulo**, así que una fila
individual subestima el esquema.

Columnas documentadas que no aparecieron en la muestra:

`fecha_de_inicio_de_ejecucion`, `fecha_de_fin_de_ejecucion`, `estado_bpin`,
`c_digo_bpin`, `anno_bpin`, **`ultima_actualizacion`**,
`fecha_inicio_liquidacion`, `fecha_fin_liquidacion`,
`fecha_de_notificaci_n_de_prorrogaci_n`.

La omitida más importante era `ultima_actualizacion`: ninguna cantidad de
exploración sobre esa fila la habría revelado, y es la columna sobre la que se
apoya la mitad de la estrategia de extracción (H2, H8).

#### Tipos

**Todos los valores llegan como texto** por la API, incluso los que el
diccionario declara como Número (`nit_entidad`, `valor_del_contrato`).
Ejemplos: `"valor_del_contrato":"8959088"`, `"es_pyme":"No"`.

Se descargará todo como string a propósito: si pandas infiere tipos, convierte a
`NaN` los valores mal formados y esconde la suciedad.

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

En la fila inspeccionada suman exactamente `valor_del_contrato`. Base de la regla
de negocio RN1.

---

### H7 — Datos personales sensibles

El dataset expone cédulas, nombres completos, género y **domicilio residencial**
del representante legal (ej. `"AMBAR RESERVA APTO 1006 TORRE A"`), del ordenador
del gasto y del supervisor.

Son datos legalmente abiertos, pero republicarlos en un tablero público es una
decisión distinta a consultarlos.

**Decisión:** estas columnas se excluyen del modelo desde el diseño. Se documenta
en el README como criterio explícito.

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
   flujo 3 de H2: refresco periódico completo del conjunto "En ejecución".
2. **Este es el hallazgo que más justifica la plataforma.** La serie temporal de
   ejecución financiera por contrato —cuánto se había pagado en cada momento— no
   existe en ninguna fuente pública. Solo puede construirse tomando snapshots a
   lo largo del tiempo, que es precisamente lo que hará el pipeline.

---

## Reglas de negocio para tests de dbt

Derivadas de los hallazgos, no inventadas para llenar el requisito.

| ID | Regla | Origen |
|---|---|---|
| RN1 | La suma de las fuentes de financiación iguala `valor_del_contrato` | H6 |
| RN2 | Ningún registro de la tabla de hechos tiene estado pre-firma | H4, H5 |
| RN3 | Ningún registro de la tabla de hechos tiene `fecha_de_firma` nula | H3, H4 |
| RN4 | La fuente no tiene más de 48 horas de rezago (`freshness`) | H8 |

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
4. **Probá la hipótesis obvia y aceptá cuando falla.** En H8 la explicación
   intuitiva de los nulos era la opuesta a la real. Verificarla fue lo que reveló
   la semántica verdadera del campo.
5. **El diccionario oficial puede estar equivocado.** Se contradice sobre el
   grano (H1) y define mal `nombre_representante_legal` (H6). La evidencia
   empírica prevalece, pero hay que dejar constancia de la discrepancia.

---

## Preguntas abiertas

**Resueltas:**

- ~~¿Qué es `valor_pendiente_de`?~~ → **Valor Pendiente de Amortización**, según
  el diccionario oficial. Coherente con la existencia de `valor_amortizado`.
- ~~¿Cómo se representan las modificaciones?~~ → Parcialmente: `dias_adicionados`
  registra el tiempo añadido y `ultima_actualizacion` la fecha del evento (H8),
  pero el valor previo del contrato no se conserva. De ahí el SCD tipo 2.

**Pendientes:**

1. **¿`Cerrado` y `terminado` son sinónimos o estados distintos?** Son 1,69M y
   774K filas. El diccionario no enumera los valores posibles del campo. Habrá
   que resolverlo empíricamente comparando `fecha_de_fin_del_contrato`,
   `fecha_fin_liquidacion` y `liquidaci_n` entre ambos grupos.
2. **¿Qué miden `orden` y `rama`?** El diccionario los define de forma circular
   ("Orden entidad del estado que publica el contrato"). Los valores observados
   no coinciden con la intuición: un hospital departamental figura como
   "Nacional".
3. **¿Qué contienen las columnas de liquidación y ejecución** que el diccionario
   documenta pero no aparecieron en la muestra (`fecha_de_inicio_de_ejecucion`,
   `fecha_fin_liquidacion`, `estado_bpin`)? Requiere perfilarlas
   explícitamente.

---

## 2. Otras fuentes del ecosistema — pendientes de evaluar

| Dataset | Etapa del ciclo | Decisión preliminar |
|---|---|---|
| SECOP II – Procesos de Contratación | Proceso previo al contrato | **Candidato v2** — son oportunidades abiertas, no contratos ya perdidos. Más valioso comercialmente. Fuera del alcance v1 por tener múltiples etapas y estados, y porque cruzarlo con contratos es un problema de llaves no trivial. |
| SECOP II – Facturas | Ejecución y pago | Por evaluar. **Sube de prioridad tras H9:** podría contener la granularidad de pagos que Contratos Electrónicos no registra. |
| TVEC – Tienda Virtual del Estado Colombiano | Compra por acuerdo marco | Nuevo candidato detectado en el diccionario oficial. ~150.673 órdenes de compra. Llave: `identificador_de_la_orden`. Volumen pequeño pero es un canal de compra distinto. |
| Plan Anual de Adquisiciones | Planeación | Por evaluar |
| SECOP I – Proponentes | Registro de proveedores | Por evaluar |

**Advertencia sobre el catálogo:** muchos datasets de `datos.gov.co` son vistas
derivadas, no fuentes distintas. Si la ficha dice "Vista en función de X" o
"creado por un miembro del público", hay que ignorarlo e ir al maestro. Ejemplos
de vistas encontradas: "…PYMES", "…ACTIVOS", "…del Departamento de Sucre",
"…INVIAS", "CONTRATOS ELECTRONISHBSE", "SECOP II – Contratos – 2017".

**SECOP I vs SECOP II** son dos generaciones, no alternativas. SECOP I era un
tablón de anuncios (datos pobres, ya no crece); SECOP II es transaccional. Se usa
SECOP II.