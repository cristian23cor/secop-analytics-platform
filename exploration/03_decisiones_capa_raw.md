# Decisiones de diseño de la capa raw

El razonamiento detrás de cada decisión, con las alternativas que se descartaron
y por qué. `01_modelo_dimensional.md` dice **qué** se decidió; acá está el porqué.

Los identificadores son estables. **D1 a D8** son de arquitectura y se tomaron
antes de escribir código. **I1 a I5** son de implementación y salieron al
escribir el cargador. **D10 y D11** salieron de descubrir que la fuente no se
regenera a diario, con el cargador ya escrito y corrido dos veces. **D9** es
infraestructura del proyecto entero y no de la capa raw; el identificador queda
reservado y no se reutiliza.

Cada decisión lleva su alternativa descartada. Eso es deliberado: una decisión sin
alternativa no es una decisión. Y si algo parece arbitrario, la razón está
escrita: no re-decidir sin leer.

Documentos hermanos: `00_inventario_fuentes.md` (la fuente, H1-H9 y H34) y
`02_ecosistema_secop.md` (los datasets hermanos, H17-H33).

---

## El problema que D1 resuelve

Antes del mapa conviene entender el conflicto que originó todo. Había dos cosas
escritas que no se sostienen juntas: que raw guarda lo crudo y la normalización
vive en `staging` (que corre *después* de raw), y que la detección de cambios
ocurre *al cargar* raw.

Si la comparación ocurre antes de la normalización, compara valores crudos. Y
comparar crudo produce versiones falsas por tres razones distintas:

| Razón | De dónde sale | Qué produce |
|---|---|---|
| La API omite las claves nulas | H6 | Ausencia leída como cambio de esquema |
| Centinelas y capitalización | H5, H6 | `terminado` a `Terminado` = versión falsa |
| Los números vienen como texto | H6 | `"1000"` distinto de `"1000.0"`, mismo valor |

El caso de los centinelas no es hipotético: `estado_contrato` es material y su
normalización de capitalización está asignada a staging. Si la fuente arregla la
capitalización de `terminado`, son **774.500 versiones falsas en una noche**.

Y fijate en la asimetría: este error solo **infla**. Nunca hay un cambio real que
se vea como no-cambio. Así que el pipeline no se rompe, ningún test falla, y el
número está mal.

---

## Mapa de decisiones

| # | Decisión | Resolución |
|---|---|---|
| D1 | Frontera crudo / comparable | A: raw fiel, normalización y comparación en dbt |
| D2 | Formato y particionado | JSONL + gzip, `flujo/fecha_extraccion/particion`, trozos con manifiesto |
| D3 | Retención de raw | (c): deduplicación por bytes antes de persistir; retención completa |
| D4 | Motor de la comparación | SQL, por arrastre de D1 |
| D5 | Contra qué se compara | La observación anterior en raw, no la tabla destino |
| D6 | Mecánica de la clasificación | Columna por columna con `IS DISTINCT FROM` |
| D7 | Alerta de imposibles | Cargar, registrar y alertar; severidad `warn` al inicio |
| D8 | Semántica temporal | `observado_desde` / `observado_hasta`, semiabiertos, nulo abierto |
| D10 | Procedencia de la observación | En el `_manifiesto.json` de la partición |
| D11 | Qué dispara el flujo 3 | El corte de la fuente, no el calendario |

**El hilo que las une.** Seis de las diez se resolvieron con el mismo criterio:
*entre un error que sobra y uno que falta, elegir el que sobra.* Aparece en la
deduplicación por bytes (D3), en el orden escribir-antes-que-índice (D2), en la
decisión de no bloquear la carga (D7) y en el rechazo del hash (D6). Es el mismo
criterio del `$select` explícito.

---

## D1: raw fiel, comparación en SQL después de staging

Raw guarda lo que devolvió la API sin tocar un carácter. El relleno, los
centinelas, los tipos y `urlproceso` se resuelven en staging. La comparación corre
en SQL, sobre valores ya normalizados.

**La razón es una sola:** la fuente se sobrescribe entera cada vez que se
regenera, así que lo que se guarde mal no se puede volver a pedir. Y la
probabilidad de que la primera versión de la normalización tenga un error es alta;
H33 es la prueba, una columna tipada como fecha que parsea sin quejarse y está
sistemáticamente corrupta. Va a aparecer otro defecto así. Con raw fiel se corrige
el código y se reprocesa; con raw canónico queda un agujero permanente en la
historia.

**Por qué no B** (raw canónico, comparación en Python): apuesta a que la limpieza
está bien escrita hoy, y esta fuente ya demostró que no perdona esa apuesta.

**Por qué no C** (dos subcapas): el `canonico` de C hace exactamente lo que hace
staging. Escrito como modelo de dbt, C es A con un nombre de más; escrito en
Python, materializa millones de filas para hacer lo que dbt haría igual una capa
más abajo, y encima sigue pagando el costo de traducir la clasificación a SQL.
Tiene los dos costos y ninguna ventaja exclusiva.

**Cómo se paga el costo de A.** El único problema real es que la clasificación
vive en `columnas.py` y la comparación está en SQL. No se traduce: **se genera**.
Un script lee `columnas.py` y escribe un archivo dentro del proyecto de dbt, más
un test de CI que falla si el generado no coincide con el módulo.

> `columnas.py` no es documentación que hay que mantener sincronizada con dbt. Es
> la fuente desde la cual dbt se genera, con un test en CI que falla si alguien
> las separa.

Lo que se resigna, sin adornos: B es más rápido de construir. Se cambia velocidad
de construcción por capacidad de corregir el pasado, y en este proyecto la moneda
es correcta, porque el pasado que se guarda **es el producto**.

**Y el generador destapó una duplicación adentro del módulo que existe para
evitarlas.** Al agregar el macro `fuentes_de_financiacion()`, las seis fuentes
estaban escritas a mano en tres lugares: dos veces dentro de `columnas.py`, en
MATERIALES y en MONETARIAS, y otra en `medir_rn1.py`. El modelo de dbt iba a ser
el cuarto. Son un concepto y no una coincidencia de clasificación, porque RN1
exige que sumen `valor_del_contrato` y RN6 que eso valga en toda versión
histórica, así que quedaron como una constante propia de la que las otras dos
listas se arman. El refactor se comprobó byte a byte: el archivo generado no
cambió, o sea que los conjuntos son los mismos.

D1 quedó con una condición abierta —si D3 terminaba en retención corta, la promesa
de "podés reprocesar desde raw" valdría 30 días y la ventaja de A se achicaría—
pero D3 terminó en retención completa y la condición se disolvió.

---

## D2: formato, particionado y punto de control

**Formato: JSONL comprimido.** Casi forzado por D1=A, no es preferencia.
`urlproceso` es un objeto anidado, y meterlo en Parquet exige struct, string JSON
o aplanar, y aplanar ya es normalizar. La API omite claves nulas, así que las
filas no comparten esquema, y Parquet exige esquema fijo: materializar las 67
columnas *es* el relleno que D1 prohíbe. Y la ventaja principal de Parquet, el
tipado, no aplica porque todo viene como texto (H6).

Variante nombrada y no elegida: Parquet con una columna `payload` que contenga el
JSON crudo más metadatos. Da particionado columnar sin tocar el contenido; más
maquinaria de la que hace falta hoy.

**Particionado: por flujo, después por fecha de extracción, después por
partición.** Flujo primero porque los tres tienen volúmenes y cadencias distintas
y podrían necesitar políticas distintas. Fecha *de extracción*, no de negocio: raw
responde "qué entregó la fuente ese día".

**Punto de control: trozos numerados con manifiesto.** Un archivo cerrado cada N
páginas, más un registro del último cursor de keyset confirmado. Al reiniciar se
descarta el trozo incompleto y se retoma desde el cursor del último trozo cerrado.

El argumento decisivo es la compresión: los límites de los trozos son los puntos
donde el stream se cierra, así que nunca queda un archivo a medio comprimir. Eso
es exactamente lo que descarta el apéndice con cursor, porque un archivo
comprimido cortado a la mitad tiene la cola corrupta y el archivo entero se vuelve
sospechoso: habría que dejar raw sin comprimir y multiplicar el volumen por diez.

La opción "todo o nada" con directorio temporal y renombrado atómico era
perfectamente defendible, y se descarta solo porque tirar 40 minutos de descarga
por morir en la página 550 de 560 es evitable barato.

### Dos invariantes que valen para cualquier implementación

**1. Escribir primero, actualizar el índice de hashes después.** Si el índice se
actualiza antes y el proceso muere en el medio, el índice dice "ya vi este
contrato" y la fila no está en ningún lado: se perdió para siempre, porque la
fuente ya se sobrescribió. Al revés, como mucho se reescribe la fila en el
reintento. Misma asimetría que decidió D3.

**2. Una marca de completitud por partición.** Un archivo `_COMPLETO` que solo
aparece al final, y dbt lee únicamente particiones que lo tengan. Sin eso, un
`dbt run` disparado mientras la ingesta corre lee media noche y produce números
que nadie va a poder explicar.

### D2 revisada: el compresor pasa de zstd a gzip

D2 eligió `zstd` por mejor ratio y velocidad. Después aparecieron dos cosas:
`zstd` no está en la biblioteca estándar de Python 3.12 (llegó en 3.14), y el
problema de volumen que lo justificaba no existe.

Una fila pesa 2.845 bytes sin comprimir, y los nombres de columna se repiten
idénticos en cada línea, así que comprimen extraordinariamente bien. zstd comprime
20% mejor y es 8 veces más rápido, pero a esta escala eso son 200 MB al año y
fracciones de segundo dentro de un proceso de 20 minutos: **el argumento técnico
casi no existe.**

Se elige gzip, nivel 6, con un criterio explícito: *una dependencia se justifica
cuando resuelve un problema que se tiene*, y el problema de volumen resultó no
existir. Beneficio concreto: quien clone el repo abre un archivo de raw con
`gzip.open` de la stdlib, sin instalar nada.

**La tabla de compresores que sostenía esto no reproduce, y hay que decirlo.** Se
midió 1,81 MB para 30.000 filas, o sea 63 bytes por fila. El barrido completo del
23/08 midió **324 bytes por fila** sobre 2.824.446 filas, y las mediciones
intermedias (269, 342 y 320) coinciden con la grande, no con esa. Cuatro
mediciones entre 269 y 342; una sola en 63. La hipótesis es que esas 30.000 filas
vinieron de una consulta con mucha más redundancia —una sola entidad, o un solo
día— y no está confirmada. La decisión no cambia, porque el argumento decisivo fue
la biblioteca estándar y no el ratio, pero los números absolutos de esa tabla
están mal.

### D2 corregida: la ruta necesita un nivel `particion=`

Es un defecto de diseño, no de implementación. La ruta original,
`raw/flujo=.../fecha_extraccion=...`, colisiona en dos casos reales y sin fallar
ruidosamente.

**El flujo 3 en paralelo:** se lanzan varias particiones del universo vivo a la
vez, las cuatro corren la misma noche con el mismo flujo, así que las cuatro
escriben en el mismo directorio, se pisan `parte-0001.jsonl.gz` y se machacan el
manifiesto.

**El backfill:** las ~80 particiones mensuales de los flujos 1 y 2 se extraen
todas hoy, así que todas caen en la misma `fecha_extraccion`. Peor que pisarse: la
segunda **lee el manifiesto de la primera**, cree estar reanudando y saltea
trozos. Produce un directorio que parece válido y está incompleto.

Ninguna de las dos falla: producen archivos.

La causa es que la ruta decía *cuándo* se extrajo, no *qué pedazo*, y la unidad de
trabajo real no es "el flujo tal día" sino "este rango, extraído tal día". Como el
manifiesto y `_COMPLETO` son por directorio, la ruta tiene que identificar
unívocamente una unidad de trabajo:

> un directorio = una unidad de trabajo = un escritor = un manifiesto

`particion` es el día en corrida diaria de los flujos 1 y 2, el mes en backfill, y
el rango de `fecha_de_firma` que le tocó a cada proceso del flujo 3. Beneficio
colateral: el nombre del directorio dice qué se pidió, cosa que antes solo se
podía reconstruir leyendo los datos.

Se agregó validación: `particion` no puede traer `/`, `\`, `=`, espacios ni estar
vacía. Un `particion="2020/01"` crearía un nivel extra de directorio en silencio.

---

## D3: deduplicación por bytes antes de persistir

**El problema.** El flujo 3 barre los ~2,8M de contratos vivos por corrida. A ~2,5
KB de JSON por fila son ~7 GB por corrida crudos, ~250 GB/año. Inviable en un
portátil. Y el 99% de lo que se guardaría es idéntico a lo de ayer.

**La decisión.** El cargador compara la fila contra el último hash guardado de ese
contrato y solo escribe si los bytes cambiaron.

**Por qué no es circular con D1=A.** La objeción obvia es que detectar cambios
exige normalizar. No aplica: acá no se compara para decidir si generar una
versión, sino para decidir **qué escribir en disco**. Una comparación cruda de
bytes solo se equivoca en una dirección: si `"1000"` pasó a `"1000.00"`, la lee
como cambio y guarda de más. Nunca se equivoca al revés. Tampoco pierde fidelidad:
si la fila de hoy es byte por byte igual a la última guardada, guardarla otra vez
no agrega información.

**Volumen resultante, medido sobre dos corridas completas:**

| | Barrido inicial (23/08) | Corrida incremental (25/08) |
|---|---|---|
| Filas recibidas | 2.835.895 | 2.840.337 |
| Filas escritas | 2.824.446 | 58.971 |
| Comprimido por fila | 324 bytes | 320 bytes |
| En disco | 916 MB | 18 MB |

**Lo que cambió en el intervalo, separado por población:**

| | Filas |
|---|---|
| Contratos conocidos que cambiaron | 52.954 |
| Contratos nuevos en el universo vivo | 6.017 |
| Descartadas por bytes idénticos | 2.781.366 |
| Tasa de cambio sobre las conocidas | **1,87%** |

`escritas` mezcla dos poblaciones y no se puede citar como tasa de cambio: de las
58.971 filas, 6.017 son contratos nuevos que se escriben por serlo, no por haber
cambiado. Sin la separación, la tasa se citaría un 11% más alta de lo que es.

Y no se divide por el número de días. El índice guarda un hash por contrato, así
que uno que cambió dos veces dentro del intervalo se escribió una sola vez: el
delta de un intervalo largo es *menor* que la suma de los deltas cortos que
contiene.

**Dos cifras por unidad de tiempo quedaron retiradas.** Esta sección decía "al
menos 26.477 contratos cambian por día" y "al año, a ese ritmo, al menos 3,4 GB".
Las dos salían de dividir por 2, y ese 2 era el ancho *supuesto* del intervalo, no
uno medido. Con un ancho real de entre 2 y 5 días, el piso por día cae a un rango
de ~10.600 a ~26.477, y ninguno de los dos extremos es una medición.

Lo que sí se sostiene, y es lo que hay que citar: en ese intervalo cambiaron
52.954 contratos conocidos de 2.834.320, o sea 1,87%. Es una razón sobre el
intervalo mismo y no depende de su ancho. Cualquier reexpresión por día o por año
necesita un intervalo con los dos extremos fechados, que es justo lo que D10
existe para garantizar de ahora en adelante.

### La reducción de almacenamiento, partida y medida

Frente a guardar la foto entera sin comprimir en cada regeneración (8,08 GB por
corte):

| Efecto | Factor | Qué es |
|---|---|---|
| Compresión | 8,9 veces | gzip haciendo su trabajo |
| Deduplicación | 48,2 veces | el diseño |
| Total | **428 veces** | 8,08 GB contra 18 MB |

428 veces es cota inferior, y conviene decir en qué dirección se equivoca: el
intervalo medido abarca entre 2 y 5 días, así que cambiaron más contratos de los
que cambian entre dos cortes consecutivos, y con un intervalo más corto la
deduplicación descarta más y el factor sube.

Este bloque reemplaza tres estimaciones anteriores, las tres equivocadas: la
original decía 12 MB por noche y 5 GB al año; la corrección de D2 decía 2 MB y 1
GB; y el factor circuló como "~250 veces" y como "~800 veces" sin que ninguno
saliera de una medición sobre el universo completo.

**Costos, sin adornos.** "Qué había el 21 de agosto" deja de ser un `WHERE fecha =
...` y pasa a ser un join contra el registro de observaciones. Comparar bytes
exige que el JSON venga siempre con las claves en el mismo orden, así que se
ordenan antes de hashear (ordenar claves no es transformar valores, así que no
rompe D1). Y hace falta el último hash por contrato: 2,8M hashes, **171 MB** en
DuckDB, medido; la estimación de 90 MB no contaba el índice de la llave primaria.

**Propiedad de diseño importante:** el índice de hashes es derivado, no
autoritativo. Si se pierde o se corrompe, se reconstruye releyendo raw y tomando
el último hash por contrato. Los archivos siguen siendo la fuente de verdad; el
índice es caché.

**Opciones descartadas:** guardar todo (inviable); ventana móvil de N días (mata
la premisa con la que se eligió D1=A); bajar el flujo 3 a semanal (queda como plan
B: divide por siete pero le baja resolución a la serie que *es* el producto).

---

## D4: la comparación corre en SQL

No fue una decisión propia: D1=A la determina. La comparación material / cosmética
/ imposible vive en dbt, sobre staging.

Los dos filtros son de finura distinta y hacen falta los dos: el de bytes decide
si la fila se guarda en disco, el de clasificación decide si la fila **merece una
versión**. Una fila puede cambiar en bytes sin cambiar materialmente, y esa
distinción solo la sabe `columnas.py`.

Beneficio colateral: dbt pasa de procesar 2,8M de filas por corrida a decenas de
miles.

---

## D5: se compara contra la observación anterior en raw

Para cada contrato, las observaciones se ordenan por fecha de extracción y cada
una se compara con la que la precede. **No** se compara contra la versión vigente
en `fct_contratos_snapshot`.

**El argumento es de coherencia con D1, no técnico.** Comparando contra raw, el
hecho es una **función de raw**: se borra entero, se corre `dbt build`, y sale
exactamente la misma tabla. La historia la determinan los archivos, no el orden en
que se corrieron las cosas. Comparando contra la tabla destino sería estado
acumulado: borrarla significaría no poder reconstruirla, porque cada comparación
necesita el resultado de la anterior.

Y eso choca de frente con D1. Se eligió raw fiel con un solo argumento: va a
aparecer un defecto de normalización y se va a querer corregir el pasado. Ese día,
comparando contra raw se arregla staging, se corre `dbt build --full-refresh` y
toda la historia se recalcula. Comparando contra la tabla destino, las versiones
ya escritas siguen calculadas con la lógica vieja. **Sería pagar el costo de A sin
cobrar el beneficio.**

`dbt snapshot` no sirve por dos razones: compara contra la tabla destino y
acumula, y aunque se quisiera eso, compara con `check_cols` y no tiene forma de
expresar una clasificación de tres vías. No hay manera de decirle "estas 32
columnas no generan versión".

---

## D6: comparación columna por columna, con `IS DISTINCT FROM`

Se comparan las 28 materiales una por una y se guarda **qué** cambió, no solo que
algo cambió. Se descarta el hash de las materiales.

**La columna `motivo_del_cambio` no es adorno.** Responde directamente si una
versión se generó por adición de valor, prórroga, pago o cesión; cuántas versiones
de un contrato son avance de pagos; y qué entidades generan más eventos de
prórroga, que es la pregunta 6.

Y conecta con H26: en el dataset oficial, `ADICION EN EL VALOR` existe pero no es
exhaustivo, porque hay adiciones dentro de `MODIFICACION GENERAL`. **El Estado
clasifica mal sus propias modificaciones.** La comparación por columna produce esa
clasificación derivada del delta observado, no de una etiqueta escrita a mano por
cada entidad: si `valor_del_contrato` subió, fue una adición, sin ambigüedad.

> La clasificación oficial de modificaciones es incompleta; la plataforma la
> reconstruye desde el delta observado.

**Cuántas columnas cambian a la vez, medido el 29/08/2026.** De los 32.431
contratos con dos versiones, solo 12.838 (el 39,6%) cambiaron exactamente una
material, y el resto cambió entre 2 y 12 a la vez. Eso no toca la decisión de D6,
pero sí dónde vive el resultado: quedó como modelo propio,
`int_cambios_por_columna`, con grano de una fila por contrato, versión y columna.
Y confirma el argumento contra el hash por un camino que no se había previsto: con
un hash de las 28 se sabría que seis de cada diez versiones cambiaron "algo" y
nunca cuántas cosas ni cuáles.

**Dos trampas técnicas, ambas golpean al hash.** `NULL != NULL` no da verdadero,
da `NULL`, y tres materiales arrancan nulas y se llenan: el cambio que
`columnas.py` describe como el más informativo que existe en un snapshot
acumulativo. Un `!=` ingenuo lo pierde. Y concatenar con `NULL` da `NULL`, así que
un contrato con una sola columna nula produciría hash nulo, y todos los hashes
nulos se ven iguales entre sí; se arregla con `COALESCE` a un centinela, pero el
centinela tiene que ser un valor imposible en los datos, y esta fuente usa
`"No definido"` como texto real en el 22% de una columna (H28).

El hash es más rápido pero tiene más formas de fallar en silencio, que es justo la
categoría de error contra la que se viene diseñando. Y con D3 el volumen por
corrida es de decenas de miles de filas, no millones: el argumento de rendimiento
no aplica a este volumen.

---

## D7: cargar igual, registrar y alertar

Cuando una columna imposible cambia, la fila entra normalmente, la discrepancia se
guarda con ambos valores y la fecha en que divergieron, y un test de dbt la
reporta.

**Las siete imposibles no son iguales.** `id_contrato` es la llave por la que se
unen las observaciones: si "cambia", no se detecta comparando, sería simplemente
otro contrato. Su modo de fallo no es la mutación sino la duplicación, y eso lo
captura un test de unicidad. Las otras seis sí pueden cambiar.

**Por qué no bloquear.** Una entidad puede corregir un error de tipeo en
`fecha_de_firma`: corrección legítima, no catástrofe. Bloquear detendría la
ingesta de 2,8M de contratos por eso, y una alerta que **para el pipeline** enseña
a desactivarla.

**Por qué no cuarentena.** Rompe la coherencia con D5. Si la fila no entra a raw,
la historia deja de ser función de raw; si entra a raw pero se excluye del modelo,
hay dos verdades sobre qué contratos existen y algún conteo no va a cuadrar sin
que nadie sepa por qué.

**Severidad: todo arranca en `warn`.** No se sabe cuántas veces se dispara: puede
ser cero al año o cinco mil, y no hay forma de saberlo hasta correrlo. Si arranca
en `error` y se dispara mil veces, la reacción natural es bajarlo o borrarlo, y
ahí se perdió la alerta. Medir y subir a `error` solo las columnas que
efectivamente no se mueven.

Ese ejercicio tiene valor propio: contar cuántos contratos cambian de
`nit_entidad` es en sí mismo un hallazgo.

---

## D8: `observado_desde` / `observado_hasta`, intervalos semiabiertos

**Las fechas son de observación, no de vigencia.** En un SCD2 de manual,
`valido_desde` es "desde cuándo esto fue verdad en el mundo real", y acá no se
puede saber. Si el 21 de agosto se observa que `valor_pagado` subió de 10M a 15M,
el pago ocurrió en algún momento entre la observación anterior y esta, y ninguna
columna dice cuándo. Es H8.

Se descarta usar fechas de negocio cuando existan, porque para los pagos no
existen y quedaría una columna que a veces significa una cosa y a veces otra: peor
que una columna consistentemente aproximada.

> La plataforma no sabe cuándo cambió el contrato; sabe cuándo el cambio se volvió
> visible, con una resolución igual a la frecuencia del barrido.

**El borde derecho.** La versión anterior se cierra con la fecha de la observación
nueva, no con el día anterior: intervalos semiabiertos, `>= desde AND < hasta`.
Encajan sin huecos ni solapes, y es el mismo criterio que ya usa `_rango` en
`flujos.py`. La versión abierta lleva `observado_hasta` nulo; se descarta el
centinela `9999-12-31`, que haría que un contrato cerrado hace tres años parezca
vigente hasta el año 9999 en cualquier gráfico que no filtre.

**Las cosméticas pisan solo la versión abierta.** Si pisaran todas, un
`--full-refresh` reconstruido desde raw daría un resultado distinto, porque el
reproceso sí ve la historia de nombres, y eso rompe lo ganado en D5. Efecto que se
acepta a conciencia: las versiones viejas muestran nombres de entidad
desactualizados. La solución no es pisar la historia, es que el mart una contra
`dim_entidad` por la llave y tome el nombre actual.

**Un hueco que hay que nombrar: `motivo_de_cierre`.** Un contrato en estado
terminal deja de ser barrido, así que su última versión queda abierta para
siempre, aunque hace tres años que nadie lo mira. Es honesto, pero un lector puede
interpretar el nulo como "sigue activo". La columna distingue `version_nueva`,
`abierta` y `fuera_de_observacion`. Un nulo que significa tres cosas distintas es
un fallo silencioso esperando.

---

## D9: lo que el porte a Snowflake enseñó

La disciplina decía: un único modelo toca los archivos, y por eso el porte iba a
ser reescribir ese modelo y nada más. Se cumplió a medias, y la mitad que falló
vale más que la que funcionó.

**Lo que funcionó.** El modelo frontera se ramificó por motor y el resto del
proyecto no se enteró: solo cambia el CTE de origen, `read_json()` sobre el disco
en DuckDB y un `select` sobre un stage interno en Snowflake. La proyección de las
67 columnas quedó compartida entre las dos ramas, así que las columnas y su orden
coinciden por construcción.

**Lo que no.** `stg_contratos` también hablaba dialecto y nadie lo había notado:
aplana `urlproceso` con `json_extract_string` y saca el `noticeUID` con
`regexp_extract`, dos funciones de DuckDB.

> "Un único modelo toca los archivos" no implica "un único modelo habla dialecto".

Son dos propiedades distintas y solo la primera estaba vigilada. La segunda se
descubrió corriendo un grep por funciones sospechosas sobre los once modelos, que
es una comprobación de treinta segundos que nadie había hecho en tres días de
escribir SQL.

Se resolvió con tres macros en `limpieza.sql`, cada uno con su rama por motor:
`campo_json()`, `extraer_grupo()` y `campo_de_datos()`. Se comprobó que el refactor
fuera **puro para DuckDB**: se reconstruyó `stg_contratos` y la salida es idéntica
al byte. Un cambio que se justifica por otro motor y de paso mueve los números del
motor que ya andaba es un cambio que hay que revertir.

Un cuarto macro salió del mismo trabajo: `campo_de_datos()` necesita saber qué
columnas son anidadas, y escribir ese nombre a mano habría creado el segundo lugar
que lo sabe. Se agregó `columnas_anidadas()` al generador, aplicando la regla
antes de que la lista se desincronizara en vez de después.

---

## D10: la procedencia se registra en el manifiesto de la partición

**El problema.** Raw no registra de qué estado de la fuente vino cada observación.
La partición se llama por `fecha_extraccion`, que es cuándo bajamos los datos, no
qué vimos. Mientras se creyó que la fuente se regeneraba a diario las dos cosas
parecían la misma; no lo son, y el costo ya se pagó: el ancho del intervalo de la
corrida del 25 es irrecuperable porque nadie anotó de qué corte leyó el barrido
del 23.

**Qué identifica a una regeneración.** El valor de `min(:updated_at) =
max(:updated_at)`, al milisegundo. No es una etiqueta nuestra: es el sello que la
propia fuente le puso a ese estado, y por H2 es único por regeneración. Esto
invierte a medias la conclusión de H2, que declara ese campo inútil: es inútil
como watermark *de fila*, y la misma propiedad que lo inutiliza para eso lo
convierte en la llave natural del corte. Dos límites: vale solo para `jbjy-vk9h`,
porque los hermanos escriben en continuo y no tienen corte (H23); y no es
reconstruible desde las filas, porque ninguna lo contiene.

**Qué se registra: tres valores, no uno.**

| Campo | Qué es |
|---|---|
| `corte_anterior` | el corte de la última ingesta completa; contra esto compara D11 |
| `corte_al_iniciar` | el corte vivo al arrancar la corrida |
| `corte_al_terminar` | el corte vivo al terminar |

Los dos primeros convierten cada partición en un intervalo con sus dos extremos
fechados, que es lo que la corrida del 25 no tiene. El tercero cubre un caso hoy
invisible: una corrida dura ~50 minutos y nada impide que la fuente regenere en el
medio, dejando una partición **a caballo** de dos cortes. Qué se hace en ese caso
queda sin decidir; por ahora se registra y se advierte.

**Dónde vive: el manifiesto, no las filas.**

| | Alternativa | Por qué no |
|---|---|---|
| A | Bitácora aparte, fuera de raw | Crea un segundo lugar autoritativo que, a diferencia del índice de hashes, no es reconstruible desde raw |
| B | En el `_manifiesto.json` de cada partición | **Elegida** |
| C | En los metadatos de cada fila | ~30 B sobre 320, y el raw ya escrito no los tiene: quedan dos formas de raw para siempre |
| D | B y C juntos | Redundancia, y con ella la posibilidad de que un día no coincidan |

Tres argumentos decidieron. **No toca las líneas de datos**, así que el hash, el
índice y las cifras medidas siguen valiendo tal cual. **El estado del guardarraíl
deja de ser un lugar aparte**: "¿cuál fue el último corte que ingerí?" se contesta
leyendo los manifiestos y tomando el máximo, así que D11 no necesita ninguna
bitácora. Y **no cierra la puerta a C**: si algún día la procedencia tiene que
vivir en la fila, las particiones nuevas la llevan y las viejas conservan su
manifiesto.

El punto débil de B es que la atribución es por partición, así que solo es verdad
si una partición contiene un corte y uno solo. Con el guardarraíl de D11 delante y
`corte_al_iniciar`/`corte_al_terminar` detrás, esa condición deja de ser un
supuesto y pasa a ser un invariante comprobado en las dos puntas.

**Migración de lo ya escrito.** Las particiones existentes no tienen estos campos.
"Sin corte anotado" es desconocido, y se advierte sin bloquear: un guardarraíl que
se planta ante datos viejos es el error que falta. Se recupera un valor hacia
atrás y uno solo, el de la partición del 25, porque la fuente quedó congelada en
ese valor desde entonces y esa corrida arrancó de día. De qué corte leyó el
barrido del 23 no se recupera.

**Tres cosas que salieron al implementarla.**

1. **Reanudar puede mezclar dos cortes, y no estaba previsto.** `_retomar()` seguía
   desde el cursor sin mirar contra qué corte se había empezado. Una corrida que
   arranca a las 04:00 y cruza la ventana de regeneración dejaría trozos de un
   estado y seguiría con otro en el mismo directorio, y el manifiesto se
   reescribiría con el corte nuevo: el viejo se perdería sin rastro. Ahora se
   descarta el progreso y se empieza de cero, avisando. Cuesta hasta 50 minutos y
   no pierde nada, que es el error que sobra.
2. **La procedencia se escribe en los tres flujos y se lee en uno.** La consulta ya
   se hizo, así que anotarla es gratis.
3. **Las dos consultas fallan distinto, a propósito.** Al arrancar, un fallo de red
   aborta, porque reintentar cuesta volver a escribir el comando. Al terminar, se
   completa igual con la marca en nulo: perder el `_COMPLETO` de un barrido de
   cincuenta minutos por un 429 en una consulta de metadatos es el error que falta.

---

## D11: el disparador del flujo 3 es el corte de la fuente, no el calendario

**El problema.** Con cadencia irregular, correr por calendario cuesta ~50 minutos
para escribir una partición vacía, y correr tarde es lo único que pierde datos de
verdad. Las alternativas eran sondear a mano y decidir a mano (cero código, y el
error queda en comparar mentalmente dos valores de 24 caracteres); que el cargador
consulte y se plante solo; o que consulte, registre y corra igual, que documenta
el duplicado en vez de evitarlo. Se eligió la segunda.

**El guardarraíl va en la dirección permisiva, y eso es deliberado.** Los dos
errores posibles no valen lo mismo:

| Error | Costo |
|---|---|
| Deja pasar una corrida contra un corte ya visto | ~50 minutos y una partición vacía. Recuperable |
| Bloquea una corrida legítima | Si la fuente regenera antes de que alguien lo note, **esa observación no existe más** |

Es el criterio de siempre, y el escarmiento concreto es R2: el guardarraíl de
`fecha_extraccion` con dos definiciones de "hoy" habría rechazado cargas legítimas
cinco horas al día. De ahí dos exigencias. La condición de aborto es "existe una
partición **completa** para este corte", no "vi este corte": una muerte dura deja
una partición incompleta contra el mismo corte, y reanudarla es exactamente lo que
I5 permite. Y hay una bandera de forzado, nombrada en el propio mensaje de aborto,
porque un guardarraíl que no se puede saltar a mano, en un pipeline que corre a
mano, es un pipeline que un día no corre.

`CorteYaIngerido` devuelve **código 4**, distinto del 1 y del 2, porque un
orquestador tiene que separar "no había nada nuevo" de "algo se rompió". Y corta
antes de bajar una sola página: es la diferencia entre cincuenta minutos y
ninguno.

**D11 solo agrega valor entre días distintos.** Salió al escribir los tests, que
fallaron los primeros cuatro por reusar la `fecha_extraccion`: dentro del mismo
día el directorio es el mismo y el `_solo_lectura` de `escritura.py` ya bloqueaba.
Lo que no estaba cubierto es correr hoy y mañana contra el mismo estado de la
fuente.

### Qué implica para Airflow

Tres cosas, y las tres son consecuencia de que el calendario no manda. **El DAG es
un sensor sobre el corte más un cortocircuito, no un `schedule` a una hora**, y
como la lógica vive en el cargador, el DAG la hereda; si viviera solo en el DAG,
correr a mano la perdería. **`catchup` tiene que ser `False`**, y no es una
preferencia: Airflow rellena por defecto las corridas que cree que faltaron, y
contra el flujo 3 eso es exactamente lo que R1 prohíbe. Y **`logical_date` no
sirve como identidad de la corrida**, porque acá la identidad es el corte de la
fuente, que no tiene relación con el calendario.

El DAG tiene **una sola tarea**. La tentación era partirlo en "preguntar por el
corte" y "cargar si cambió", pero eso duplica la pregunta y abre una ventana entre
las dos en la que la fuente puede regenerar. El DAG llama al cargador y lee su
código de salida: el 4 se traduce a *saltar* y no a *fallar*, porque con cadencia
irregular esa es la respuesta correcta la mayoría de los días, y una alerta que
suena todos los días deja de mirarse en dos semanas.

Corre cada tres horas. No es un horario: es cada cuánto se hace una pregunta que
cuesta dos segundos.

**El límite de tiempo se puso contra el peor caso y no contra el promedio.** Hay
tres barridos medidos entre 4,20 y 5,22 segundos por página, y una página suelta
que tardó 28 sin explicación. Sobre 570 páginas eso es la diferencia entre
cincuenta minutos y cuatro horas, y el límite está en cuatro.

Cinco tests lo cuidan, y cuatro de ellos no comprueban que funcione sino que las
decisiones sigan tomadas: `catchup`, una sola corrida a la vez, el código 4
mapeado y el límite de tiempo. El quinto simplemente lo importa, que es el fallo
más común de un DAG y el más invisible.

---

## Implementación: I1 a I5

| # | Decisión |
|---|---|
| I1 | JSON canónico, y esos mismos bytes se escriben |
| I2 | BLAKE2b truncado a 128 bits |
| I3 | Manifiesto como JSON dentro de cada partición |
| I4 | Tres módulos; el índice completo en memoria |
| I5 | El trozo se cierra por líneas o por páginas; el cursor solo si el buffer está vacío |

I1 e I2 juntas definen el contrato del índice de hashes. Si cambian después de la
primera corrida, todos los hashes guardados quedan inservibles. No es catastrófico
—el índice es derivado y se reconstruye desde raw— pero conviene fijarlas antes de
la primera corrida.

### I1: JSON canónico, y esos mismos bytes se escriben

La propiedad que se busca es que el hash sea el hash de los bytes que quedan en
disco. Se serializa **una sola vez**; esa cadena se hashea y esa misma cadena se
escribe, así que "los bytes cambiaron" y "el archivo habría sido distinto" son la
misma afirmación. Serializar dos veces crearía dos rutas que pueden divergir en
silencio.

```python
linea = json.dumps(fila, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")
```

`sort_keys=True` ordena alfabéticamente, también dentro de `urlproceso`. Ordenar
claves no es normalizar: el orden no es información, así que no rompe D1. Los
separadores sin espacios ahorran volumen que no dice nada sobre 2,8M de filas. Y
`ensure_ascii=False` deja el archivo más chico y legible, con los caracteres rotos
de H22 visibles en vez de escapados. Cualquiera de las dos opciones sirve mientras
sea consistente; cambiarla después invalida todos los hashes.

**Opciones descartadas:** concatenar campos con separador (más rápido, pero esta
fuente tiene saltos de línea embebidos, comillas rotas y punto y coma en los
textos: elegir mal el separador da colisiones silenciosas); y msgpack u otro
binario, que rompe D1 porque raw dejaría de ser inspeccionable a ojo.

**Tres reglas que no se tocan.**

1. **Los metadatos se agregan DESPUÉS de hashear.** `fecha_extraccion` y `flujo`
   cambian en cada corrida por definición; si entran al hash, nada se deduplica
   jamás. Van como envoltorio: `{"fecha_extraccion": ..., "flujo": ..., "hash":
   ..., "datos": {...}}`.
2. **Las claves ausentes se dejan ausentes.** D1 prohíbe rellenar en raw. Si una
   vez la API omite `ultima_actualizacion` y a la siguiente la manda como `null`
   sin que nada haya cambiado, el hash cambia y se guarda una fila de más: el error
   que sobra. Esto va como comentario en el código, porque el instinto de
   cualquiera que lo lea después va a ser "arreglarlo" rellenando antes de hashear,
   y eso sí rompería D1.
3. **Si `json.dumps` falla, falla ruidosamente**, con el `id_contrato` en el
   mensaje. No se salta la fila.

### I2: BLAKE2b truncado a 128 bits

`hashlib.blake2b(linea, digest_size=16)`, de la biblioteca estándar. Se guarda en
hexadecimal, no en bytes crudos: legible al depurar, y la diferencia es 90 MB
contra 45 para 2,8M de contratos.

**Por qué 128 bits.** Una colisión significa que dos filas distintas dan el mismo
hash, el cargador concluye "no cambió nada", no guarda la fila nueva, y esa
observación se pierde para siempre. Es el error caro, y **el único punto de todo
el diseño donde el error puede ir en la dirección equivocada**: la deduplicación
por bytes solo puede sobrar, salvo por esto.

Con ~20M de observaciones guardadas en un año, 64 bits dan ~1 en 100.000, que es
bajo pero no despreciable a diez años; 128 dan ~1 en 10^24; 256 no aporta nada a
cambio del doble de índice. Un matiz reduce aún más el riesgo real: la colisión
tendría que ocurrir entre dos versiones **del mismo contrato**, porque el índice es
por `id_contrato`, así que el espacio efectivo son decenas de versiones y no 20
millones.

**Corrige una suposición previa.** Se había dicho que BLAKE2b se elegía en parte
por ser más rápido que MD5. Medido, la diferencia es del 5%: irrelevante.

| Operación | Velocidad | 2.825.685 filas |
|---|---|---|
| `blake2b(digest_size=16)` | 1.036.096/s | 2,7 s |
| `md5` | 1.052.565/s | 2,7 s |
| `json.dumps` canónico | 184.449/s | **15,3 s** |

**El hash no es el costo: serializar lo es**, y es cinco veces más caro. Pero como
I1 decidió que se serializa una sola vez y esa misma cadena se escribe, esos 15 s
se pagarían igual: la deduplicación sale prácticamente gratis. Y los dos números
se pierden dentro de los ~20 minutos que tarda la API. **El cuello de botella es
la red, no el CPU**, y queda escrito para que nadie optimice el lugar equivocado.

Entonces la razón para elegir BLAKE2b sobre MD5 es una sola: no arrastrar la
conversación sobre criptografía rota en un repo de portafolio. La respuesta
correcta sería "sí, MD5 está roto, y acá no hay adversario", pero es una defensa
que no hace falta tener que dar.

El algoritmo se escribe en el manifiesto como `algoritmo_hash: "blake2b-128"`. Si
algún día hay que cambiarlo, hay que poder distinguir hashes viejos de nuevos sin
adivinar.

### I3: manifiesto como archivo JSON dentro de cada partición

Guarda el último cursor de keyset confirmado, cuántos trozos se cerraron, el
algoritmo de hash y marcas de tiempo.

**`_COMPLETO` y el manifiesto no duplican información.** Son la misma pregunta con
dos respuestas posibles, y dos verdades sobre si una partición terminó van a
discrepar algún día. Se separan por responsabilidad: el manifiesto lleva el
progreso, para reanudar, y `_COMPLETO` es la única señal de terminado, para que
dbt sepa qué leer. Un archivo vacío es más barato de comprobar desde dbt que
parsear un JSON.

**Dos argumentos decidieron.** Primero, la coherencia con el invariante de orden
de D2: con el manifiesto en DuckDB, cada punto de control tendría que escribir en
dos sistemas distintos, y eso no se puede hacer atómicamente; con el manifiesto en
la partición, el trozo y el manifiesto viven en el mismo directorio y el orden es
local. Segundo, **DuckDB no admite dos escritores simultáneos**, y el flujo 3 se
paraleliza lanzando varias particiones a la vez: con manifiestos por partición,
cada proceso escribe en su propio directorio y no hay contención.

Beneficio colateral: la partición queda autocontenida. Se copia, se inspecciona o
se borra entera sin abrir nada.

El índice de hashes sí va en DuckDB, porque son cosas distintas: el índice es
global por `id_contrato` y el manifiesto es local a una partición.

### I4: tres módulos, y el índice completo en memoria

| Módulo | Responsabilidad | Toca I/O |
|---|---|---|
| `hashing.py` | Canonicalizar, hashear, envolver | No: funciones puras |
| `indice.py` | Leer el índice, acumular, escribir la tanda | DuckDB |
| `escritura.py` | Trozos, compresión, manifiesto, `_COMPLETO` | Disco |

`indice` y `escritura` van separados, y no es estética: son los dos lados del
invariante *escribir el archivo antes de tocar el índice*. En un mismo archivo,
nada impide que alguien invierta el orden en un refactor; separados, el orden es
visible en el orquestador y se puede testear.

**El problema del escritor único de DuckDB**, que dejó abierto I3. Tres salidas se
evaluaron: serializar el flujo 3 (pierde el paralelismo, 20 minutos se vuelven
80); un índice por partición fusionado al final (no funciona, porque el índice es
global por contrato y uno parcial no puede responder cuál fue el último hash); y
separar lectura de escritura, que es la elegida. Cada proceso lee al arrancar
—DuckDB admite muchos lectores—, acumula en memoria, y escribe su tanda al cerrar.

Funciona por una razón concreta de este caso: un contrato pertenece a una sola
partición del flujo 3, porque las particiones son rangos disjuntos de
`fecha_de_firma`. Dos procesos nunca compiten por el mismo `id_contrato`.

El costo es que si el proceso muere antes de escribir su tanda, esos hashes se
pierden y la próxima corrida ve esas filas como nuevas. Duplicados en raw, que dbt
resuelve tomando la última observación por contrato: otra vez el error que sobra.

**La medición salió al revés de lo esperado y cambió la recomendación.** Se iba a
proponer consulta por lotes por prudencia de memoria:

| Estrategia | Memoria | Tiempo (566 páginas) |
|---|---|---|
| Índice completo en un dict | 185 MB | **2,1 s** (4,2 s en otra corrida) |
| Consulta por lotes de 5.000 | Constante | **95,4 s** |

La opción "prudente" es 23 veces más lenta y protege 185 MB que no hacía falta
proteger. Proponerla por instinto habría metido minuto y medio de latencia por
corrida a cambio de nada.

**El caso extremo real fue 55,7 s de volcado, no los 13,9 estimados.** Eso rompe
el presupuesto de reintentos de `_abrir()`, que suma 15,5 s de espera: con
particiones en paralelo, la que llegue mientras otra vuelca no alcanza a esperar y
muere. Hoy no muerde porque las particiones se corren en serie, y hay que rehacer
el cálculo antes de paralelizar. Pero el caso extremo es más raro de lo que
parecía: la corrida incremental volcó 58.971 hashes en 4,0 s, así que los 55,7 s
ocurren en la primera corrida y en un re-barrido completo, no en una corrida
típica.

Y hay que vigilar si el dataset crece: cuatro particiones en paralelo son cuatro
copias del índice, o sea 740 MB.

**Dos cosas que la medición dejó ver.** La inserción inicial tarda 20,6 s y ocurre
en la primera corrida con el índice vacío, así que el mensaje de progreso tiene
que anunciarlo o va a parecer colgado. Y la carga tiene dos muestras que difieren
al doble (2,1 s y 4,2 s con un 0,8% más de filas): una lectura de disco no es
determinista, así que lo que hay que retirar es la idea de que 2,1 s sea *el*
número. La conclusión no se mueve.

### I5: cuándo se cierra el trozo y cuándo avanza el cursor

**Encontrado leyendo el código, no corriéndolo.** Es un defecto de la interacción
entre dos piezas que por separado están bien.

**El defecto.** El punto de control y el cierre del trozo iban a ritmos distintos:
el cursor se guardaba en el manifiesto en cada página, y el trozo se escribía a
disco cada 5.000 líneas. En el flujo 3, de cada página de 5.000 filas cambian unas
50, así que llenar un trozo lleva ~100 páginas, y durante esas cien páginas el
manifiesto ya anunciaba el avance mientras las líneas seguían en memoria.

Una muerte dura —SIGKILL, corte de luz, OOM; no una excepción, que el `with` sí
alcanza a cubrir— dejaba el manifiesto diciendo "ya pasé por acá" con las filas
evaporadas. La reanudación arrancaba después de ellas y **no las volvía a pedir
nunca**, con la fuente ya sobrescrita. Invierte la asimetría sobre la que está
construido todo el diseño: de los tres lugares donde vivía una fila (buffer,
índice y cursor) el único que sobrevivía al fallo era el que no debía.

**La decisión.** Dos cotas para cerrar el trozo, la que ocurra primero: líneas
acumuladas (5.000) y páginas desde el último cierre (20). Y una regla para el
cursor: **solo pasa al manifiesto si el buffer está vacío.** La regla vive en
`_guardar_manifiesto()`, que es el único punto donde el cursor llega al disco, así
que el manifiesto no puede anunciar un avance mayor que lo escrito, por
construcción y en un solo lugar.

La condición es "el buffer está vacío", no "se acaba de cerrar un trozo". Parece
lo mismo y no lo es: en la segunda corrida de una misma ventana el descarte es del
100%, no se escribe ni una línea y nunca se cierra un trozo, así que con la regla
del trozo el cursor no avanzaría jamás y cualquier interrupción reiniciaría desde
cero.

**Por qué no cerrar el trozo en cada página.** Era la opción más simple y elimina
el riesgo por construcción. Se midió su costo:

| líneas por trozo | archivos | penalización de tamaño |
|---|---|---|
| 5.000 | 1 | - |
| 500 | 10 | +1,8% |
| 100 | 50 | +9,3% |
| 50 (una página del flujo 3) | 100 | +18,1% |

El espacio no es el problema. Lo que cuesta son **~200.000 archivos al año** entre
las cuatro particiones, de forma permanente, a cambio de un riesgo ocasional.

**La cota de páginas se revisó el 31/08/2026 y se deja como está.** Estaba anotado
que se revisaría cuando existieran los reintentos, porque ahí la interrupción
volvería a ser rara. La premisa resultó falsa a medias: los reintentos cubren las
interrupciones de red, y la cota protege contra la muerte dura, contra la que los
reintentos no hacen nada. O sea que las interrupciones que la cota protege son
exactamente las que no se volvieron raras.

**El número de páginas era una estimación, y ya está medido.** 20 suponía ~50
líneas escritas por página. Medido: **103,6 líneas por página**, el doble. Llenar
un trozo toma 48 páginas, así que la cota que manda sigue siendo la de páginas,
pero por un margen menor que el previsto.

Esa corrida cerró 31 trozos y no los 29 que dan 569 páginas divididas por 20, y el
porqué importa más que el número: **la escritura no está repartida a lo largo del
recorrido, está apilada al final.** La página 1 escribió 0 filas de 5.000; la 568
escribió 2.413, o sea el 48%. Un factor de 600 veces entre el arranque y la cola.

No se sabe por qué se apila. La explicación tentadora ("los contratos nuevos
cambian más") no se sostiene: el keyset ordena `id_contrato` como texto, así que
la cola del recorrido son los ids de seis dígitos que empiezan por 9, ni los más
nuevos ni los más viejos. Es una observación, no un hallazgo. Consecuencia
práctica para el día que se paralelice: las particiones no van a tener carga de
escritura pareja.

**Lo que esto dejó ver sobre los tests.** El test
`test_el_punto_de_control_guarda_el_cursor` pasaba, y **afirmaba el defecto**:
escribía una línea, llamaba al punto de control y exigía que el manifiesto ya
tuviera el cursor, con la línea todavía en el buffer. O sea que el defecto estaba
*cubierto* por un test, no descubierto por falta de cobertura. Conviene releer los
demás con esa sospecha puesta, y no solo con la de "¿falta cobertura?".

---

## Las tres corridas contra la fuente real

### El primer barrido completo: 23 de agosto de 2026

| | Estimado | Medido |
|---|---|---|
| Contratos vivos | 2.825.685 | 2.835.895 |
| Páginas de 5.000 | ~566 | 568 |
| Tiempo del barrido | ~20 min | **39 min 46 s** |
| Volcado del índice | 13,9 s | 55,7 s |
| Comprimido por fila | 63 B | 324 B |
| La partición en disco | ~140 MB | 916 MB |

**D3 funciona entre días distintos, no solo dentro de una corrida.** De las 11.449
filas que ya estaban en el índice del día anterior, se descartaron las 11.449:
bytes idénticos con otra `fecha_extraccion`, o sea que los metadatos están
efectivamente fuera del hash y la canonicalización es estable en el tiempo.

### La segunda corrida: 25 de agosto de 2026

La primera vez que el flujo 3 corrió sobre un índice ya poblado, y la que convierte
la deduplicación de una propiedad demostrada en una propiedad medida.

**Los dos extremos del intervalo, con lo que se sabe de cada uno.** El derecho está
fechado al milisegundo, recuperado hacia atrás porque la fuente quedó congelada en
ese valor. El izquierdo es **desconocido**: nadie consultó el `:updated_at` el 23, y
ese corte ya no existe.

Esta corrida estaba anotada como "intervalo de dos regeneraciones, 23 a 25". Esa
anotación se retira: daba por sentado que la fuente había regenerado el domingo 23,
y no hay ninguna observación que lo respalde. El ancho está entre 2 y 5 días y es
irrecuperable. Todo lo que se exprese *por unidad de tiempo* a partir de esta
corrida hereda esa indeterminación; lo que se exprese *como razón sobre el
intervalo* no.

**Existe un flujo de salida del universo vivo, y es de miles.** Se puede acotar
pero no fijar: entre 1.575 y 8.872 contratos dejaron de estar vivos en el
intervalo. Es el primer dato empírico sobre la pregunta abierta de si los estados
terminales cambian, y no la cierra.

**Retirado: el calce de los contratos nuevos con H3.** Esta sección decía que
6.017 en dos días son ~3.000 por día, contra los ~2.900 que H3 obtuvo, y que eran
"dos caminos independientes al mismo número". Se cae por dos razones distintas. El
divisor no se conoce: sobre un intervalo de 2 a 5 días da entre ~1.200 y ~3.000, y
el calce solo aparece si se elige el divisor 2, que era el supuesto. Y no son la
misma población: "nuevo en el universo vivo" es *no estaba en el índice*, y un
contrato puede entrar por cambio de estado sin haberse firmado ese día, mientras
que H3 cuenta firmas. Es un caso de libro: **un calce demasiado bueno es
sospechoso.**

**Lo que empeoró.** El ritmo de la API: 5,22 s por página contra 4,20, y 5,00 en
la corrida del 28. Con tres muestras el rango es 4,20-5,22.

**Lo que sigue sin medirse: el delta de veinticuatro horas.** Conviene separar dos
cosas que hasta ahora se usaban como sinónimos:

| | Qué mide | Para qué sirve |
|---|---|---|
| Delta de una regeneración | cuánto cambia entre dos cortes consecutivos, sean del día que sean | el umbral del canario; es lo que el pipeline ve |
| Delta de veinticuatro horas | cuánta actividad de negocio se acumula en un día | la proyección anual |

El primero se obtiene siempre que se corra en cada corte, y D10 garantiza que
venga con sus dos extremos fechados. El segundo exige que exista un par de cortes
separados por exactamente un día, cosa que no depende de nosotros. Mientras no
exista ese par, las cifras por día y por año se enuncian como rangos o no se
enuncian.

### La tercera corrida: 28 de agosto, contra una fuente congelada

La fuente llevaba tres días sin regenerar, así que se corrió el flujo 3 contra el
mismo corte que ya estaba en el índice, idéntico al milisegundo. No es un delta:
es una prueba de determinismo con intervalo cero, y es la primera corrida del
proyecto donde **todo se anotó antes de verlo**.

| | Predicho | Real |
|---|---|---|
| recibidas / páginas | 2.840.337 / 569 | idéntico |
| escritas | 0 | 0 |
| descarte sobre conocidas | 100,00% | idéntico |
| trozos cerrados | 0 | 0 |
| el canario | callado | callado |

**La canonicalización es determinista a tres días de distancia, sobre 2,84
millones de filas.** Es la confirmación más fuerte que tiene D3: lo anterior eran
11.449 filas y una incremental; esto es el universo entero, con la fuente byte a
byte igual, y no se escribió ni una línea de más. Cualquier dependencia del reloj,
del orden de las claves o del entorno se habría visto acá.

**El camino "cero cambios" de I5 corrió a escala real por primera vez.** El
manifiesto quedó con cero trozos y cero líneas, y el cursor avanzó las 569
páginas: exactamente la regla del buffer vacío. Con la otra regla el cursor no
habría avanzado nunca y la corrida habría quedado sin punto de reanudación.

---

## El canario del descarte

**El canario callado fue el defecto, no el alivio.** Con descarte del 100% no
llegaba al umbral, así que no cantó. Con cadencia irregular, el 100,00% dejó de
ser el caso perfecto y pasó a ser también la señal de haber corrido contra un
corte ya visto.

Tenía dos cosas mal y solo una estaba anotada.

**El denominador.** Decidía sobre descartadas / recibidas, que se diluye cuando
casi todas las filas son nuevas:

| corrida | sobre recibidas | sobre las conocidas | el canario viejo |
|---|---|---|---|
| barrido completo 23/08 | 0,4% | 100,00% | **cantaba** |
| incremental 25/08 | 97,9% | 98,13% | callaba |
| intervalo nulo 28/08 | 100,0% | 100,00% | callaba |

Las tres son sanas y en la primera cantaba: el barrido descartó el 0,4% de lo
recibido porque casi todo era nuevo. **La misma corrida se leía como catástrofe o
como éxito según el denominador.**

El arreglo no necesitó ningún contador nuevo, porque toda fila descartada es
necesariamente conocida. La tasa vive en `tasa_sobre_conocidas`, que devuelve
`None` y no cero cuando no hay ninguna conocida: cero significaría "todo lo
conocido cambió", `None` es "no hay nada contra qué comparar", y confundirlas es
el mismo error por otro lado.

**El umbral, que no estaba en la ficha.** Con 0,5 el canario solo atrapa la rotura
total: con la mitad de los hashes invalidados el descarte cae al 50% y se queda
callado. Y una rotura parcial es realista, porque la API omite las claves nulas,
así que una columna nueva poblada en parte del universo invalida solo esos hashes.

Se subió a 0,90, que deja ocho puntos de margen contra el ancla más baja (98,13%),
y medido atrapa toda rotura de más del 10% de los hashes. Una rotura del 5% da
95,20% y no la ve: ese es el límite del umbral elegido y está escrito en un test
para que no se descubra el día que haga falta.

**Y después el umbral se partió en dos, porque no puede servir para dos
regímenes.** Con un intervalo largo cambian más contratos de verdad y la tasa baja
sin que nada esté roto. La carga del 08/09/2026, con catorce días de intervalo,
descartó el 83,02% sobre las conocidas: una corrida perfectamente sana que hizo
cantar al canario. Ahora el umbral depende del ancho del intervalo, que D10 ya
registra: 0,90 para intervalos de hasta siete días, respaldado por tres anclas
entre 0 y 5 días, y 0,50 para intervalos largos, respaldado por una sola. Ese
segundo número es débil a propósito y está anotado como tal.

---

## La paridad entre motores, y lo que destapó

La cuenta de Snowflake es de prueba y vence el 12/09/2026. Lo que sobrevive al
vencimiento no es la cuenta sino la **medición fechada**, si se captura antes. De
ahí `scripts/verificar_paridad_de_motores.py` y su informe: **38 comprobaciones,
las 38 coinciden.**

Contar filas no alcanza, porque dos tablas del mismo tamaño pueden tener
contenidos distintos. Las comprobaciones apuntan a donde los motores hablan
dialectos distintos: las huellas blake2b de la ingesta, los castings, las ventanas
del SCD2, los `datediff` de la capa intermedia, la jerarquía UNSPSC derivada con
`substr`, y los cuatro contadores de signo del mart.

### Lo que destapó, que vale más que el informe

**El cambio a incremental había roto Snowflake, y nadie lo sabía.** El modelo
frontera referenciaba el stage sin calificar, `@secop_raw`, y Snowflake lo resuelve
contra el esquema de la *sesión*. Funcionaba mientras el modelo se materializaba
como `table` y dejó de funcionar al pasar a incremental, porque dbt cambia ese
contexto. El mismo defecto tenía el formato de archivo, un nivel más abajo; los dos
se arreglaron calificando con `target.schema`, que sale del mismo
`SNOWFLAKE_SCHEMA` que lee el script de subida, así que los dos lados coinciden por
construcción.

Fue invisible por dos razones y las dos importan. CI no toca Snowflake, a propósito
y con razón. Y nadie reconstruyó allá después del cambio: el código se modificó por
la mañana y el motor conservaba las tablas de días antes, correctas porque se
habían construido con el código viejo.

> Un porte no está verificado por haber corrido una vez. Cada cambio en un modelo
> compartido lo pone en duda otra vez, y si el otro motor no se reconstruye, sus
> tablas viejas siguen dando la respuesta correcta a una pregunta que ya nadie hizo.

**Y el informe mentía, por la misma razón.** La primera versión de este script dijo
"38 de 38 coinciden" con la construcción de Snowflake rota: comparaba una tabla
local recién hecha contra una de Snowflake de dos días antes, y no decía de cuándo
era ninguna de las dos. El informe ahora fecha los dos lados y lo pone arriba de
todo, normalizados a hora colombiana porque vienen de relojes distintos.

> Una comparación entre dos sistemas tiene que decir de cuándo es cada lado. Sin
> eso no compara el código de hoy: compara dos fotos, y una puede ser vieja.

**Quién vigila al que compara.** Se probó el verificador rompiéndolo. Detectó que
un lado midiera sobre un subconjunto, y **no detectó** que la función que compara
dijera "igual" siempre: no puede, es la pieza con la que verifica. Se prueba desde
afuera, con 14 tests.

Escribirlos destapó otro defecto: **si una comprobación fallaba en los dos motores,
contaba como acuerdo.** Dos errores no son una coincidencia, son dos comprobaciones
que no se hicieron, y sumarlas inflaba justo el número que el informe existe para
sostener.

**Una cifra documentada que estaba mal.** Los documentos decían "402 familias y 57
segmentos UNSPSC". Son 401 y 56: el conteo viejo incluía el nulo de `UNSPECIFIED`
como si fuera una familia, y no lo es. Lo destapó esta comparación, porque
`count(distinct)` excluye el nulo.

**El jinja se comió los saltos de línea por cuarta vez.** Al calificar el stage se
agregó un comentario `{#- ... -#}` entre la última columna y el `from`, y el SQL
compilado dijo `as datosfrom @RAW.secop_raw`. Ya estaba documentado que iba a
volver a pasar, y volvió. CI no puede atraparlo compilando, porque el modelo
frontera tiene una rama que exige credenciales de Snowflake. Pero el defecto es
estático y se ve en el archivo: `tests/test_jinja_no_se_come_el_sql.py` marca un
comentario que cierre con `-#}` cuando arriba queda un identificador y abajo
empieza una cláusula. Las dos mitades hacen falta: con solo la de abajo, la regla
marcaba tres modelos sanos, y **una regla que marca de más se termina desactivando
entera**.

---

## Airflow, instalado y probado en local

El DAG existía y estaba probado; faltaba un scheduler que lo leyera. Se instaló en
local y **no en Docker**, y la razón es una medición: el `docker-compose` oficial
de Airflow levanta siete contenedores y su propia documentación pide al menos 4 GB
de RAM asignados a Docker. La máquina tiene 3,8 GB en total.

Hay una segunda razón, más de fondo. El DAG ejecuta `uv run python
scripts/cargar_raw.py`. Meterlo en un contenedor exigiría empaquetar adentro el
proyecto, uv, el entorno virtual, el `.env` con el token, y montar `datos/raw`
para que escriba afuera: sería empaquetar el proyecto entero para ejecutar un
comando que ya funciona en la máquina donde vive.

Su estado vive en `.airflow/` dentro del proyecto, ignorado por git, para que
borrar ese directorio reinicie Airflow por completo sin tocar nada más. El DAG sí
va a git, en `dags/`, que es lo que permite que CI lo pruebe. SQLite y
LocalExecutor: para un DAG con una tarea cada tres horas sobra, porque postgres y
Celery existen para un paralelismo que acá no hay.

**Lo que la prueba de punta a punta demostró.** Se corrió `airflow dags test`, y
salió barato por una circunstancia útil: el corte vivo ya estaba ingerido, así que
el guardarraíl de D11 corta antes de bajar una sola página. Siete segundos, la
tarea en `skipped` y la corrida en `success`. Esa distinción es la que se diseñó:
con cadencia irregular ese va a ser el resultado la mayoría de los días, y marcarlo
como fallo haría sonar la alerta a diario hasta que nadie la mire.

**El límite que hay que decir, porque es el que decide todo: Airflow local no corre
con la máquina apagada.** Da la interfaz, el historial y la demostración de que el
pipeline está orquestado, pero no da operación desatendida. Por eso la vigilancia
de la fuente no vive acá sino en GitHub Actions: la pregunta de dos segundos corre
de noche y los fines de semana, y avisa. El barrido de cincuenta minutos se lanza a
mano cuando llega el aviso.

Hacer que el barrido también corra solo exigiría mudar la capa cruda y el índice a
un bucket, y con ellos el modelo frontera. Es un proyecto aparte y está anotado
como tal, no como pendiente.

---

## El registro de cadencia, y quién lo escribe

Cierra la pregunta abierta de dónde vive el registro de sondeo, y la cierra de una
forma que no estaba entre las opciones pensadas.

**Vive en `exploration/cadencia.csv`**, una línea por día, versionada. No en
`datos/`, que no va a git: esto es una medición y no datos crudos, pesa unos bytes
por día, y es **lo único del proyecto que no se recupera hacia atrás**. Un día que
nadie miró es un día perdido.

No crea un segundo lugar autoritativo, que era el reparo: los manifiestos guardan
los cortes *ingeridos* y este archivo los *vistos*. Son conjuntos distintos, y los
vistos-y-no-cargados son justamente los que miden la cadencia.

**La deducción, escrita.** El corte solo avanza. Si dos observaciones que rodean un
día muestran el mismo corte, ese día no regeneró: una regeneración lo habría movido
y no puede volver atrás. Si los cortes difieren, los días del medio son
genuinamente desconocidos. Aplicada de forma pareja, la regla convierte dos días de
"no se sabe" en "no regeneró" y deja cuatro genuinamente desconocidos. El tablero
deducía uno de los dos y el otro no, sin motivo.

**Lo escribe GitHub Actions con un cron, no el DAG.** Airflow corre en una máquina
que se apaga, y la fuente no espera a que la enciendan. Y hay una segunda razón: el
DAG corre el cargador, que sale por código 4 cuando el corte ya se ingirió, **sin
dejar rastro de haber preguntado**. Un sondeo que no carga no es lo mismo que una
carga que no hizo falta.

`scripts/sondear.py` devuelve código 5 cuando la fuente regeneró, distinto de 0 y
de los errores. Es el mismo criterio del 4 del cargador.

**Dos decisiones que salieron de imaginarlo corriendo.** Sondea cada tres horas
pero escribe una vez al día: si commiteara en cada sondeo serían ocho commits
diarios de ruido en un historial que alguien va a leer. Y un sondeo posterior
agrega información, nunca la quita: la consulta al testigo puede fallar sin abortar
el sondeo, y sin cuidado un fallo pasajero al mediodía borraba el testigo bueno de
la mañana.

**El defecto que esto tuvo, y su costo medido.** La primera versión decidía si la
fuente se había movido comparando contra el último corte de un día *anterior*. En
un día en que la fuente sí se movió, ese contraste seguía siendo verdadero en los
ocho sondeos, así que cada uno reescribía el archivo, commiteaba y abría otro
issue: **20 issues y hasta seis commits en un mismo día**, entre el 3 y el 8 de
septiembre de 2026.

> Cuando dos preguntas se parecen, comprobalas por separado. "Cambió desde ayer" y
> "cambió desde que miré" solo coinciden si mirás una vez por día.

---

## Materialización incremental: la mitad segura

Los once modelos se reconstruían enteros en cada corrida. Dos pasaron a
incrementales y el resto no, y esa división no es de rendimiento sino estructural.

`raw_observaciones` y `stg_contratos` son transformaciones fila a fila sobre
particiones que no cambian: una partición se escribe una vez, se marca con
`_COMPLETO` y no se toca más. Incremental ahí solo agrega filas, así que la
propiedad de D5 se conserva **por construcción**.

El SCD2 y las dos dimensiones con historia no. Ahí una observación nueva tiene que
cerrar la versión que estaba abierta, o sea modificar una fila que ya existe, y eso
necesita `merge` con una ventana de retroceso y la equivalencia hay que demostrarla
en serio.

**La clave de una partición es el triple, no la fecha.** El filtro natural,
`where fecha > (select max(fecha) from this)`, está mal, y el motivo está en la
capa cruda real: el 22/08 hay dos particiones con la misma `fecha_extraccion` y el
mismo nombre de partición, una de cada flujo. Un filtro por fecha las trata como
una y pierde la segunda sin fallar. La clave es `flujo/fecha/particion`,
concatenada porque `(a,b,c) in (select ...)` no se escribe igual en los dos motores
y D9 pide que el dialecto viva en un macro.

La estrategia es `append` y no `merge`: las particiones son disjuntas, así que no
hay nada que actualizar y un `merge` costaría un anti-join sobre 2,9 millones de
filas para protegerse de algo que no puede pasar.

**Lo que se midió, y lo que se esperaba de más.** La construcción completa de los
dos modelos y sus tests son 252 s; la segunda pasada incremental, sin nada nuevo,
88 s. La estimación previa era de unos 10 segundos y estaba mal por una razón que
se midió antes de escribir el código: **el filtro no evita abrir los archivos.** Un
`where` sobre la columna que sale del nombre del archivo poda el parseo, no la
apertura.

**El modo de fallo que queda, escrito.** Una partición reescrita con
`--forzar-corte-repetido` no se vuelve a leer, porque su clave ya está en la tabla:
hay que reconstruir con `--full-refresh`. No se intentó resolverlo automáticamente
porque cualquier detección sería una segunda respuesta a una pregunta que el
manifiesto ya contesta.

**Y se demuestra, no se supone.** `scripts/verificar_incremental.py` construye la
capa sintética en seis etapas, agregando una partición por vez, y compara contra
una construcción de cero con `--full-refresh`, fila por fila y en los dos sentidos.

Las seis etapas no son decorativas: se probó el verificador rompiendo el filtro a
propósito seis veces y **la primera versión solo detectaba tres**. Cargaba varias
particiones juntas, así que el filtro por fecha sola las dejaba pasar y la prueba
daba verde con el filtro roto. Arreglarlo obligó a sembrar dos casos nuevos en el
generador sintético: dos flujos escribiendo la misma fecha y la misma ventana, y un
mismo flujo con dos particiones el mismo día.

> Un dato de prueba en el que todo sale bien prueba que el código corre, no que
> decida bien. Y un verificador que solo se vio dar verde tampoco está probado.

**El caso nuevo destapó un defecto en el generador.** Al sembrar el barrido
partido, los dos rangos recibieron su desplazamiento con `hash(rango) % 50`. El
hash de las cadenas de Python cambia en cada proceso, así que el generador dejó de
ser reproducible pese a tener un parámetro `--semilla`, y de tanto en tanto los dos
rangos se solapaban y metían el mismo contrato dos veces bajo la misma
`fecha_extraccion`. Lo atrapó `fct_una_observacion_por_contrato_y_fecha`, el test
que vigila el supuesto no escrito del SCD2.

> Una semilla que no reproduce no es una semilla.

---

## Los reintentos ante 429 y 5xx

El TODO más viejo del módulo. Cada barrido son unas 570 peticiones y cincuenta
minutos contra una API que H32 mostró que se cae bajo carga, y hasta acá una sola
respuesta 429 abortaba la corrida entera.

**Qué se reintenta, y qué no.** Se reintentan 429, 500, 502, 503, 504, los timeouts
y los fallos de conexión: todos se arreglan solos. **No** se reintenta ningún otro
4xx, y eso es la mitad de la política: un 400 por un `$where` mal armado o un 403
por token inválido no se van a ir esperando, y reintentarlos cinco veces es tardar
medio minuto en dar el mismo mensaje y encima gastar cupo en peticiones que ya se
sabían perdidas.

**El presupuesto.** Cinco intentos con espera creciente de 2, 4, 8 y 16 segundos:
30 segundos de espera acumulada por petición. Es el punto medio entre dos filos.
Más corto no aguanta un pico de rate limit, que suele durar del orden de diez
segundos. Más largo sería lo correcto si el barrido corriera desatendido de
madrugada, pero con la consola delante dos minutos por página se sienten como un
cuelgue.

**`Retry-After` se respeta, con tope.** La espera creciente queda como piso —volver
antes de lo que el servidor pidió es gastar un intento en una petición que va a ser
rechazada otra vez— y el presupuesto restante como techo. El techo importa: una
cabecera de una hora dejaría la corrida en silencio y no habría forma de
distinguir eso de un cuelgue. El presupuesto es de espera **acumulada** y no por
intento, justamente para que respetar la cabecera no pueda estirar el total sin que
nadie lo note.

**Cuando se agotan, se relanza el error original**, no uno propio. Los dos lugares
que hoy manejan estos fallos capturan `Exception` y muestran el tipo; envolverlo en
un `RuntimeError` los dejaría diciendo "RuntimeError" donde antes decían "HTTPError
503", que es peor mensaje para quien lo lee a las tres de la mañana.

Se comprobó que los tests midan algo rompiendo la política a propósito, seis veces:
sin reintentar el 429, reintentando también los 4xx, sin tope para `Retry-After`,
ignorando la cabecera, con espera constante en vez de creciente, y envolviendo el
error. Las seis mutaciones fueron detectadas. Y ninguno de los tests duerme:
`time.sleep` se reemplaza por una función que anota cuánto le pidieron, lo que
además vuelve la espera observable y permite afirmar que crece en vez de suponerlo.

---

## La cadencia de la fuente no es diaria

Todo el proyecto se escribió sobre la frase "la fuente se regenera cada noche".
Nadie la comprobó nunca, y es falsa. El registro completo, el testigo que descarta
la caída de plataforma y el supuesto retirado están en H34, en
`00_inventario_fuentes.md`; acá va solo lo que D10 y D11 necesitan.

Tres regeneraciones observadas (18, 20 y 25 de agosto) y siete días comprobados sin
regenerar. Saltos de dos días, de cinco, y uno de siete que retiró el supuesto de
planificación. **Ningún par de cortes separados por exactamente un día**, en todo
el registro.

**Qué se cae:** la palabra "noche" en todas las frases del proyecto, el delta de
veinticuatro horas como objetivo alcanzable a voluntad, y la resolución temporal
que el producto final puede prometer, que es la de la fuente y no la diaria.

**Qué no se toca:** la premisa del proyecto, H2 y los tres flujos, los datos ya
escritos en raw, y **D8**. Esto último merece subrayarse: `observado_desde` /
`observado_hasta` ya había decidido no prometer resolución diaria, y ya estaba
escrito que la serie iba a tener huecos. La cadencia irregular no rompe ese diseño;
lo confirma por un camino que no se había previsto.

---

## Restricciones que no se negocian

Salieron de las decisiones pero valen por sí solas: son las cosas que, si alguien
las invierte en un refactor, rompen el diseño en silencio.

### R1: El flujo 3 no se puede reejecutar hacia atrás

Los flujos 1 y 2 preguntan por rangos de fechas de negocio, así que la fuente
devuelve lo mismo hoy que dentro de un mes y reprocesar una fecha pasada
reconstruye esa fecha. El flujo 3 no: pregunta "¿cómo están AHORA los contratos
vivos?", y correrlo hoy para la partición del 15 de agosto devuelve el estado de
hoy. Ese estado se destruyó, y es la premisa entera del proyecto.

> Reejecutar el flujo 3 **dentro de la misma ventana de estado de la fuente**
> produce el mismo resultado. Reejecutarlo sobre una fecha pasada no reconstruye
> esa fecha: produce una observación nueva con fecha vieja, que es **peor que no
> hacer nada** porque mete una mentira en raw.

"La misma ventana de estado" dejó de ser una noción vaga: es exactamente el mismo
valor de `min(:updated_at)`, y desde D10 queda anotado en el manifiesto. D11 es
esa restricción hecha guardarraíl.

Consecuencias: el reintento de Airflow para el flujo 3 tiene sentido dentro de la
misma corrida y no tres días después; un `backfill` del flujo 3 sobre fechas
pasadas no debe existir, y es un `raise` y no una opción; y "puedo reprocesar
cualquier rango histórico con un comando" aplica a los flujos 1 y 2, no al 3.

No es una limitación del diseño: es una propiedad de la fuente. Decirla
explícitamente es mejor que un backfill que parece funcionar y contamina.

### R2: `fecha_extraccion` es el día COLOMBIANO, no el del reloj del sistema

Encontrado al probar el orquestador, con el reloj puesto. `date.today()` devuelve
la fecha del sistema, y en un contenedor o en Airflow eso suele ser UTC. Colombia
es UTC-5, así que entre las 19:00 y la medianoche hora local, UTC ya está en el día
siguiente. Verificado en vivo: `ahora UTC: 2026-08-22 01:10 | Bogotá: 2026-08-21
20:10`.

Con `date.today()`, esa misma corrida habría escrito en
`fecha_extraccion=2026-08-22`, partiendo el día de negocio en dos particiones, y el
guardarraíl habría **rechazado una carga legítima** diciendo que era backfill.

**Por qué la fecha de Colombia y no UTC.** UTC es la convención estándar y no está
mal, pero acá produce el error justo cuando alguien corre el cargador a mano por la
tarde-noche —depurando, rehaciendo algo, probando—, que es cuando menos va a
sospechar de la fecha. Con el DAG corriendo poco después de la regeneración, las
dos convenciones coinciden y la diferencia no se ve nunca, hasta que se ve. Y el
día colombiano es además el que coincide con lo que un analista llamaría "el corte
del 21".

**La regla es una sola definición de "hoy"**, en una función, y no dos llamadas
sueltas en lugares distintos, que es lo que había. El orquestador la usa para
nombrar la partición y el guardarraíl para decidir si una corrida es backfill; si
se calcularan con criterios distintos, el guardarraíl rechazaría corridas legítimas
**cinco horas al día**.

Casi vuelve a pasar tres veces, y las tres las atrapó `ruff`, no una revisión.

### R3: El pipeline entero corre en ~3 GB de memoria

La máquina de desarrollo es WSL2 con 3,8 GB de RAM, y DuckDB se pone un techo de 3
GB sobre eso. **No es una anécdota del entorno: ya descartó tres enfoques.**

**El modelo frontera.** Abrir las 67 columnas con `json_extract_string` (una
llamada por columna) agota la memoria y muere, porque parsea el mismo documento 67
veces por fila. Declarar el `STRUCT` explícito desde `columnas.py` hace lo mismo
sin parsear:

| Enfoque | Tiempo | Tabla | Memoria |
|---|---|---|---|
| `datos` como JSON, sin abrir | 46,6 s | 2.090 MB | pasa |
| 67 llamadas a `json_extract_string` | - | - | **muere** |
| STRUCT explícito | 42,3 s | 224 MB | pasa |

**El SCD2 pasó de 734 s a 52.** `fct_contratos_snapshot` hacía `select *` y
arrastraba las 73 columnas de staging:

| Etapa | Costo |
|---|---|
| Construir la huella de 28 columnas | 3,6 s |
| Las dos ventanas (`lag` y `lead`) | 5,1 s |
| Escribir 11 columnas con ventana | 8,9 s |
| Escribir 73 columnas sin ventana | 109 s |
| El modelo completo | 734 s |

**Toda la lógica sospechada suma nueve segundos: el 98,8% del tiempo era escribir
columnas anchas después de ordenar.** Y la relación no es lineal —seis veces más
columnas costaban ochenta veces más tiempo—, que es la firma del volcado a disco.
El arreglo fue dejar en el hecho solo las 28 materiales más las llaves.

**El problema de rendimiento y el de modelado eran el mismo.** Una tabla de hechos
lleva llaves, fechas y medidas; los atributos descriptivos van en las dimensiones.
Eso ya estaba escrito en el modelo dimensional, y el `select *` lo violaba
duplicando 1,2 GB en disco sin agregar información. **R3 empujó hacia el diseño
correcto en vez de alejar de él.**

**Menos hilos, más rápido.** Con siete modelos, la construcción tardaba 432 s con
los 4 hilos por defecto:

| Hilos | Construcción completa | `dim_proveedor` | `fct_contratos_snapshot` |
|---|---|---|---|
| 4 | 432 s | 152 s | 207 s |
| 2 | 458 s | 160 s | 236 s |
| 1 | **326 s** | **6,4 s** | **100 s** |

`dim_proveedor` es 24 veces más rápido con un solo hilo, y 2 hilos salió peor que
4. La curva no es monótona en el número: lo que importa es que los dos modelos que
ordenan millones de filas no coincidan en el tiempo. Con cualquier valor mayor que
1, coinciden, se pelean por los 3 GB y los dos vuelcan a disco. `threads: 1` quedó
fijado con la tabla al lado, porque es justo el tipo de valor que alguien sube
"para mejorarlo". Y no se hereda al objetivo de Snowflake, donde esa restricción no
existe.

**No se negocia subiendo la memoria.** Un proyecto que necesita 16 GB para procesar
916 MB tiene un problema de diseño. Que quepa en 3 GB es una propiedad del trabajo,
no una limitación heredada: esta restricción ya produjo un modelo nueve veces más
chico que el que se iba a escribir sin ella.

---

## Alternativas descartadas, para no reabrirlas

**Las tres opciones de D1.** (A) Raw fiel, comparación en SQL después de staging:
raw auditable de verdad, y un bug de normalización se arregla con `dbt run`; el
costo es que la clasificación de `columnas.py` hay que expresarla en SQL, o
generarla. (B) Raw canónico, comparación en Python: `columnas.py` sigue siendo la
única fuente de verdad y se testea con pytest; el costo es que raw deja de ser
fiel, un bug de casteo obliga a re-descargar, y comparar 2,8M de filas por corrida
en Python es lento. (C) Dos subcapas: el relleno tiene lugar propio y testeable; el
costo son dos escrituras y el doble de disco.

El eje real no es el disco: es **dónde vive `columnas.py` en el linaje**. En A y C
es un documento que hay que traducir; en B es código ejecutable en el camino
crítico.

**La cuarta opción no apareció.** Los hermanos sí tienen watermark propio (H23),
pero eso no abre una opción de arquitectura nueva: abre una restricción sobre las
tres existentes. La capa raw tendría que alojar dos patrones de ingesta
incompatibles, y eso mueve peso en contra de B, no a favor de una D.

**Restricciones ya identificadas para D2 y D3.** El volumen es todo del flujo 3:
raw append-only con foto completa serían ~1.000M de filas al año, mientras que los
flujos 1 y 2 son ~5.000 filas por día. `urlproceso` es un objeto anidado y rompe la
conversión a Parquet, así que "raw fiel" y "raw en Parquet" no conviven gratis. Y
raw no se filtra por negocio: H3 ya dejó los años previos a 2020 adentro, coherente
con la decisión del extractor.
