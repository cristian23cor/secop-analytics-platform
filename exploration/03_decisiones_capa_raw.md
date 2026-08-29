# Decisiones de diseño de la capa raw

> El razonamiento completo detrás de cada decisión, con las alternativas que se
> descartaron y por qué. `01_modelo_dimensional.md` dice **qué** se decidió;
> acá está el **por qué**.
>
> **Cómo leerlo:** las decisiones tienen identificadores estables. **D1 a D8**
> son de arquitectura —dónde vive cada cosa— y se tomaron antes de escribir
> código. **I1 a I5** son de implementación y salieron al escribir el cargador;
> I5 salió más tarde todavía, releyendo el código ya escrito. **D10 y D11**
> salieron de descubrir que la fuente no se regenera a diario, con el cargador ya
> escrito y corrido dos veces. **D9 no está acá**: es infraestructura del
> proyecto entero, no de la capa raw, y dónde se documenta sigue abierto.
> Cada una lleva su alternativa descartada; eso es deliberado, porque una
> decisión sin alternativa no es una decisión.
>
> **No re-decidir sin leer.** Si algo parece arbitrario, la razón está escrita.
> Si encontrás una contradicción entre dos decisiones, eso sí es un problema y
> hay que resolverlo.
>
> Documentos hermanos: `00_inventario_fuentes.md` (la fuente, H1–H9) y
> `02_ecosistema_secop.md` (los datasets hermanos, H17–H33).

---

## El problema que D1 resuelve

Antes del mapa conviene entender el conflicto que originó todo. Había dos cosas
escritas que **no se sostienen juntas**:

1. Raw guarda lo crudo, y la normalización vive en `staging`, que es dbt, que
 corre **después** de raw.
2. La detección de cambios ocurre **al cargar** raw.

Si la comparación ocurre antes de la normalización, compara valores crudos. Y
comparar crudo produce versiones falsas por tres razones distintas:

| Razón | De dónde sale | Qué produce |
|---|---|---|
| La API omite las claves nulas | H13 | Ausencia leída como cambio de esquema |
| Centinelas y capitalización | H5, H13 | `terminado` → `Terminado` = versión falsa |
| Los números vienen como texto | H6 | `"1000"` ≠ `"1000.0"`, mismo valor |

El caso de los centinelas no es hipotético: `estado_contrato` es una columna
material y su normalización de capitalización está asignada a `staging`. Si la
fuente arregla la capitalización de `terminado`, son **774.500 versiones falsas
en una noche**.

Y fijate en la asimetría: este error solo **infla**. Nunca hay un cambio real
que se vea como no-cambio. Así que el pipeline no se rompe, ningún test falla, y
el número está mal.

**D1 es qué se mueve para resolverlo.**

Sobre los tipos hay un matiz que se arrastra a D6: H6 prohíbe la **inferencia
silenciosa** de tipos, no la conversión declarada.

---

## Mapa de decisiones

alternativas descartadas anotadas abajo.

| # | Decisión | Resolución |
|---|---|---|
| D1 | Frontera crudo / comparable | **A** — raw fiel, normalización y comparación en dbt |
| D2 | Formato y particionado | **JSONL + gzip**, `flujo/fecha_extraccion`, trozos numerados con manifiesto (revisada, ver abajo) |
| D3 | Retención de raw | **(c)** — deduplicación por bytes antes de persistir; retención completa |
| D4 | Motor de la comparación | **SQL**, por arrastre de D1 |
| D5 | Contra qué se compara | **La observación anterior en raw**, no la tabla destino |
| D6 | Mecánica de la clasificación | **Columna por columna** con `IS DISTINCT FROM`; produce `motivo_del_cambio` |
| D7 | Alerta de imposibles | **Cargar, registrar y alertar**; severidad `warn` al inicio |
| D8 | Semántica temporal | **`observado_desde` / `observado_hasta`**, intervalos semiabiertos, nulo abierto |
| D10 | Procedencia de la observación | **En el `_manifiesto.json`** de la partición: corte anterior, al iniciar y al terminar. **Implementada el 28/08** |
| D11 | Qué dispara el flujo 3 | **El corte de la fuente, no el calendario.** El cargador consulta y se planta si ese corte ya se ingirió completo. **Implementada el 28/08** |

**El hilo que las une.** Seis de las ocho se resolvieron con el mismo criterio:
*entre un error que sobra y uno que falta, elegir el que sobra.* Aparece en la
deduplicación por bytes (D3), en el orden escribir-antes-que-índice (D2), en la
decisión de no bloquear la carga (D7) y en el rechazo del hash (D6). Es el
mismo criterio del `$select` explícito .

**Lo que queda por construir** (ya sin decisiones pendientes):

1. ~~El cargador con deduplicación por bytes, trozos y manifiesto.~~ Escrito.
2. ~~El índice de hashes en DuckDB, con su reconstrucción desde raw.~~ Escrito.
2b. ~~La consulta del corte, los campos de procedencia y el guardarraíl.~~
 Escrito y corrido contra la fuente el 28/08. Queda anotar hacia atrás el
 manifiesto de la partición del 25 con
 `corte_al_iniciar = 2026-08-25T09:05:54.277Z`, que es legítimo porque la fuente
 quedó congelada en ese valor y esa corrida arrancó de día.
3. El generador `columnas.py` → dbt, con el test de deriva en CI.
4. `stg_contratos`: relleno H13, centinelas, tipos, `urlproceso`, `noticeUID`.
5. El modelo SCD2 propio, incremental, con `motivo_del_cambio` y
 `motivo_de_cierre`.
6. La tabla de alertas de imposibles.


---

## Arquitectura: D1 a D8, más D10 y D11

###  D1 DECIDIDA — Opción A (raw fiel, comparación en SQL después de staging)


Raw guarda lo que devolvió la API sin tocar un carácter. El relleno (H13), los
centinelas, los tipos y `urlproceso` se resuelven en `staging` (dbt). La
comparación corre en SQL, sobre valores ya normalizados.

**Razón principal, y es una sola:** la fuente se sobrescribe entera cada vez que
se regenera, así que lo que se guarde mal no se puede volver a pedir. Y la probabilidad de que
la primera versión de la normalización tenga un error es alta — H33 es la
prueba: una columna tipada como fecha, que parsea sin quejarse, y está
sistemáticamente corrupta. Va a aparecer otro defecto así. Con raw fiel se
corrige el código y se reprocesa; con raw canónico queda un agujero permanente
en la historia.

**Por qué no B:** apuesta a que la limpieza está bien escrita hoy, y esta
fuente ya demostró que no perdona esa apuesta. (Los argumentos de velocidad y
acoplamiento son secundarios.)

**Por qué no C:** el `canonico` de C hace exactamente lo que hace `staging` —
rellenar, normalizar centinelas, castear, aplanar. Escrito como modelo de dbt,
C es A con un nombre de más. Escrito en Python, materializa millones de filas
para hacer lo que dbt haría igual una capa más abajo, y **encima sigue pagando
el costo de traducir la clasificación a SQL**. Tiene los dos costos y ninguna
ventaja exclusiva.

**Cómo se paga el costo de A.** El único problema real es que la clasificación
material/cosmética/imposible vive en `columnas.py` y la comparación estará en
SQL. No se traduce: **se genera**. Un script lee `columnas.py` y escribe un
archivo dentro del proyecto de dbt, más un test de CI que falla si el generado
no coincide con el módulo. ~40 líneas.

Eso convierte la debilidad en la mejor parte, y da una frase de README:

> `columnas.py` no es documentación que hay que mantener sincronizada con dbt.
> Es la fuente desde la cual dbt se genera, con un test en CI que falla si
> alguien las separa.

**Lo que se resigna, dicho sin adornos:** B es más rápido de construir. Se
cambia velocidad de construcción por capacidad de corregir el pasado. En este
proyecto la moneda es correcta, porque el pasado que se guarda **es el
producto**.

 **CONDICIÓN ABIERTA — revisar al decidir D3.** Todo el argumento se apoya en
"podés reprocesar desde raw". Si el volumen obliga a una retención corta (por
ejemplo 30 días), esa promesa vale 30 días y la ventaja de A se achica mucho.
**Si D3 termina en retención corta, hay que volver sobre D1.** Queda anotado en
vez de resuelto en silencio.

###  D2 DECIDIDA — formato, particionado y punto de control

**Formato: JSONL comprimido con `zstd`.** Casi forzado por D1=A, no es
preferencia:

- `urlproceso` es objeto anidado. Meterlo en Parquet exige struct, string JSON,
 o aplanar — y aplanar ya es normalizar.
- La API omite claves nulas: las filas no comparten esquema. Parquet exige
 esquema fijo; materializar las 67 columnas **es** el relleno de H13.
- La ventaja principal de Parquet, el tipado, no aplica: todo viene texto (H6).

`zstd` sobre `gzip` por ratio y velocidad, soportado por DuckDB. Decisión de
bajo riesgo, reversible recomprimiendo.

Variante nombrada y no elegida: Parquet con una columna `payload` que contenga
el JSON crudo más columnas de metadatos. Da particionado columnar sin tocar el
contenido; más maquinaria de la que hace falta hoy.

**Particionado: por flujo, después por fecha de extracción.**

```
raw/flujo=refresco_de_vivos/fecha_extraccion=2026-08-21/particion=2020-01/parte-0001.jsonl.gz
```

Flujo primero porque los tres tienen volúmenes y cadencias distintas y podrían
necesitar políticas distintas; con la fecha primero no se pueden aplicar sin
recorrer todos los directorios.

Fecha **de extracción**, no de negocio: raw responde "qué entregó la fuente ese
día".

**Punto de control: opción 3 — trozos numerados con manifiesto.**

Un archivo cerrado cada N páginas, más un registro de progreso con el último
cursor de keyset confirmado. Al reiniciar se descarta el trozo incompleto y se
retoma desde el cursor del último trozo cerrado.

*Argumento decisivo: la compresión.* Los límites de los trozos son los puntos
donde el stream de compresión se cierra, así que nunca queda un archivo a medio
comprimir. Eso es exactamente lo que descarta la opción 2 (apéndice con
cursor): un archivo comprimido cortado a la mitad tiene la cola corrupta y el
archivo entero se vuelve sospechoso — habría que dejar raw sin comprimir y
multiplicar el volumen por diez.

*(Este párrafo se escribió cuando el compresor elegido era `zstd`. El argumento
no depende del compresor y vale igual con `gzip`; ver D2 revisada.)*

Opción 1 (todo o nada, con directorio temporal y renombrado atómico) era
perfectamente defendible: más simple y ningún lector ve datos a medias. Se
descarta solo porque tirar 40 minutos de descarga por morir en la página 550 de
560 es evitable barato.

**Detalle:** en noches tranquilas la deduplicación de D3 puede producir trozos
vacíos —cincuenta páginas sin un solo cambio dan cero filas—. No se escriben.

#### Dos invariantes que valen para cualquier implementación

**1. Escribir primero, actualizar el índice de hashes después.** Si el índice se
actualiza antes de escribir y el proceso muere en el medio, el índice dice "ya
vi este contrato" y la fila **no está en ningún lado**: se perdió para siempre,
porque la fuente ya se sobrescribió. Al revés, como mucho se reescribe la fila
en el reintento — un duplicado en raw, que dbt resuelve tomando la última
observación por contrato.

Misma asimetría que decidió D3: entre un error que sobra y uno que falta, se
elige el que sobra.

**2. Una marca de completitud por partición.** Un archivo `_COMPLETO` que solo
aparece al final. dbt lee únicamente particiones que la tengan. Sin eso, un
`dbt run` disparado mientras la ingesta corre lee media noche y produce números
que nadie va a poder explicar.

###  D2 REVISADA — el compresor pasa de `zstd` a `gzip`

D2 eligió `zstd` "por mejor ratio y velocidad". Dos cosas aparecieron después:

1. **`zstd` no está en la biblioteca estándar de Python 3.12** — llegó en 3.14.
 Usarlo significa agregar `zstandard` a `pyproject.toml`.
2. **El problema de volumen que lo justificaba no existe.**

#### Medición sobre filas realistas (67 columnas, textos y entidades reales)

Una fila pesa **2.845 bytes** sin comprimir. Los nombres de columna se repiten
idénticos en cada línea, así que comprimen extraordinariamente bien:

| Compresor | 30.000 filas | Ratio | Tiempo | Proyección anual |
|---|---|---|---|---|
| gzip nivel 6 | 1,81 MB | 47× | 0,40 s | **~1,2 GB** | 
| gzip nivel 9 | 1,77 MB | 48× | 0,74 s | ~1,2 GB |
| zstd nivel 3 | 1,44 MB | 60× | 0,05 s | ~1,0 GB |
| zstd nivel 10 | 1,30 MB | 66× | 0,26 s | ~0,9 GB |

 **Corrige la estimación de D3.** Se había escrito "~5 GB/año". El total real
ronda **1 GB/año**, y la primera corrida completa (2.825.685 filas) son
**~140 MB**. Pesimista por un factor de cinco.

 **Esta tabla no reproduce, y hay que decirlo.** El barrido completo del
2026-08-23 midió **324 bytes por fila** comprimidos sobre 2.824.446 filas, no
los 63 que se deducen de 1,81 MB / 30.000. Son cinco veces más, y las mediciones
intermedias —269 y 342 bytes por fila, sobre muestras de 18.746 y 5.331 filas—
coinciden con la grande, no con esta.

La segunda corrida agregó la muestra que faltaba: **320 bytes por fila sobre
58.971 filas**, o sea una partición de noche típica y no un barrido completo.
Era la duda razonable —que el ratio del barrido saliera de su mezcla particular
de filas— y queda descartada. Cuatro mediciones entre 269 y 342; una sola en 63.

La hipótesis es que las 30.000 filas de esta tabla vinieron de una consulta con
mucha más redundancia que una muestra representativa: una sola entidad, o un
solo día. **No está confirmada** — habría que revisar qué consulta las trajo.

La decisión de D2 no cambia: el argumento decisivo fue la biblioteca estándar,
no el ratio. Pero la comparación entre compresores de esta tabla queda sin
respaldo, y los números absolutos de la columna "al año" están mal.

#### La decisión

zstd comprime 20% mejor y es 8× más rápido. Pero a esta escala eso son 200 MB al
año y fracciones de segundo dentro de un proceso de 20 minutos: **el argumento
técnico casi no existe**.

Se elige **gzip**, y el criterio es explícito: *una dependencia se justifica
cuando resuelve un problema que se tiene*, y el problema de volumen resultó no
existir. Beneficio concreto: quien clone el repo abre un archivo de raw con
`gzip.open` de la stdlib, sin instalar nada — que es el punto 7 de la definición
de terminado.

**Nivel 6**, el de por defecto. El 9 gana 2% a cambio del doble de tiempo.

**Lo que NO cambia de D2:** JSONL como formato (las razones eran `urlproceso`
anidado, claves ausentes y tipado inútil — ninguna depende del compresor),
`flujo/fecha_extraccion` como particionado, y trozos numerados con manifiesto.


###  D2 CORREGIDA (segunda vez) — la ruta necesita un nivel `particion=`

Es un defecto de diseño, no de implementación: la ruta que fijó D2 **colisiona en dos casos
reales, y sin fallar ruidosamente**.

#### Ruta vieja

```
raw/flujo=refresco_de_vivos/fecha_extraccion=2026-08-21/
```

**Colisión 1 — el flujo 3 en paralelo.** Se lanzan varias particiones del
universo vivo a la vez. Las cuatro corren la misma noche con el mismo flujo, así
que **las cuatro escriben en el mismo directorio**: se pisan
`parte-0001.jsonl.gz` y se machacan el manifiesto.

**Colisión 2 — el backfill.** Las ~80 particiones mensuales de los flujos 1 y 2
se extraen todas hoy, así que todas caen en la misma `fecha_extraccion`. Peor
que pisarse: la segunda **lee el manifiesto de la primera**, cree estar
reanudando y saltea trozos. Produce un directorio que parece válido y está
incompleto.

Ninguna de las dos falla: producen archivos.

#### La causa

La ruta decía **cuándo** se extrajo, no **qué pedazo**. Y la unidad de trabajo
real no es "el flujo tal día", es "este rango, extraído tal día". Como el
manifiesto y `_COMPLETO` son por directorio (I3), la ruta tiene que identificar
unívocamente una unidad de trabajo.

#### Ruta corregida

```
raw/flujo=refresco_de_vivos/fecha_extraccion=2026-08-21/particion=2020-01/
```

Regla que ahora se sostiene:

> **un directorio = una unidad de trabajo = un escritor = un manifiesto**

`particion` es el día en corrida diaria de los flujos 1 y 2 (redundante con
`fecha_extraccion`, pero inofensivo y consistente), el mes en backfill, y el
rango de `fecha_de_firma` que le tocó a cada proceso del flujo 3.

**Beneficio colateral:** el nombre del directorio dice **qué se pidió**. Con la
ruta vieja eso solo se podía reconstruir leyendo los datos.

**Validación agregada:** `particion` no puede traer `/`, `\`, `=`, espacios ni
estar vacía. Un `particion="2020/01"` crearía un nivel extra de directorio en
silencio y rompería la regla. Falla temprano.

**Lo que no cambia:** el índice de hashes sigue resuelto por I4 —leer al
arrancar, escribir al cerrar—. Cuatro directorios distintos, cuatro volcados
serializados al final.

**Tests que lo cubren:** `test_dos_particiones_de_la_misma_noche_no_se_pisan`,
`test_el_backfill_no_reanuda_la_particion_equivocada`,
`test_una_particion_que_rompe_la_ruta_falla_temprano`.

###  D3 DECIDIDA — Opción (c): deduplicación por bytes antes de persistir

 Las letras (a)-(d) de D3 son un eje distinto de las A/B/C de D1. No se
corresponden.

**El problema.** El flujo 3 barre los ~2,8M de contratos vivos por corrida —
verificado contra `flujos.py`: la partición de `refresco_de_vivos` es
paralelismo **dentro** de una noche, no reparto entre noches. A ~2,5 KB de JSON
por fila (los nombres de columna son larguísimos y se repiten), son ~7 GB/noche
crudos, ~700 MB comprimidos, **~250 GB/año**. Inviable en un portátil. Y el 99%
de lo que se guardaría es idéntico a lo de ayer.

**La decisión.** El cargador compara la fila contra el último hash guardado de
ese contrato y **solo escribe si los bytes cambiaron**.

**Por qué no es circular con D1=A.** La objeción obvia es que detectar cambios
exige normalizar. No aplica: acá no se compara para decidir si generar una
versión, sino para decidir **qué escribir en disco**. Una comparación cruda de
bytes solo se equivoca en una dirección — si `"1000"` pasó a `"1000.00"`, la
lee como cambio y guarda de más. **Nunca se equivoca al revés.** Un error que
solo puede sobrar es seguro; mismo criterio que el `$select` explícito.

Tampoco pierde fidelidad: si la fila de hoy es byte por byte igual a la última
guardada, guardarla otra vez no agrega información.

**Volumen resultante, medido sobre dos corridas completas:**

| | Barrido inicial (2026-08-23) | Corrida incremental (2026-08-25) |
|---|---|---|
| Filas recibidas | 2.835.895 | 2.840.337 |
| Filas escritas | 2.824.446 | **58.971** |
| Comprimido por fila | 324 bytes | **320 bytes** |
| En disco | 916 MB | **18 MB** |

La segunda corrida es la que faltaba: convierte la proyección de "si cambian
~30.000 por corte" en una medición. **Su muestra:** corrida completa sin
reanudar, con los flujos 1 y 2 sin correr antes, así que no contaminaron el
índice. El intervalo **no se conoce**: nadie registró de qué corte de la fuente
leyó el barrido del 23, y la fuente pasa días sin regenerar. Ver *La cadencia de
la fuente no es diaria*, abajo.

⚠ **El ancho del intervalo está entre 2 y 5 días y ya no se puede averiguar.**
La versión anterior de esta sección lo anotaba como "dos regeneraciones, 23 → 25,
cubriendo domingo y lunes". Eso daba por sentado que la fuente había regenerado
el domingo 23, cosa que nadie observó. El extremo izquierdo del intervalo se
destruyó con el corte que lo contenía.

**Lo que cambió en el intervalo, separado por población:**

| | Filas |
|---|---|
| Contratos conocidos que cambiaron | **52.954** |
| Contratos nuevos en el universo vivo | 6.017 |
| Descartadas por bytes idénticos | 2.781.366 |
| Tasa de cambio sobre las conocidas | **1,87%** |

 **`escritas` mezcla dos poblaciones y no se puede citar como tasa de
cambio.** De las 58.971 filas, 6.017 son contratos nuevos que se escriben por
serlo, no por haber cambiado. Sin la separación, la tasa de cambio se citaría
un 11% más alta de lo que es.

 **Y no se divide por el número de días.** El índice guarda un hash por
contrato, así que uno que cambió dos veces dentro del intervalo se escribió una
sola vez: el delta de un intervalo largo es **menor** que la suma de los deltas
cortos que contiene.

⚠ **RETIRADAS — dos cifras por unidad de tiempo que no se pueden sostener.**
Esta sección decía *"al menos 26.477 contratos cambian por día"* y *"al año, a
ese ritmo, ≥3,4 GB"*. Las dos salían de dividir por **2**, y ese 2 era el ancho
supuesto del intervalo, no uno medido. Con un ancho de entre 2 y 5 días, el piso
por día cae a un rango de ~10.600 a ~26.477 y el anual a ~1,3–3,4 GB, y ninguno
de los dos extremos es una medición.

**Lo que sí se sostiene, y es lo que hay que citar:** en ese intervalo cambiaron
**52.954 contratos conocidos de 2.834.320**, un **1,87%**. Es una razón sobre el
intervalo mismo y no depende de su ancho. Cualquier reexpresión por día o por año
necesita un intervalo con **los dos extremos fechados**, que es justo lo que D10
existe para garantizar de ahora en adelante.

#### La reducción de almacenamiento, partida y medida

Frente a guardar la foto entera sin comprimir cada vez que la fuente se
regenera —8,08 GB por corte—:

| Efecto | Factor | Qué es |
|---|---|---|
| Compresión | **8,9×** | gzip haciendo su trabajo |
| Deduplicación | **48,2×** | el diseño |
| **Total** | **428×** | 8,08 GB contra 18 MB |

 **428× es cota inferior, y hay que decir en qué dirección se equivoca.** El
intervalo medido abarca entre 2 y 5 días, así que cambiaron más contratos de los
que cambian entre dos cortes consecutivos; con un intervalo más corto la
deduplicación descarta más y el factor sube. La dirección del error no cambia
con el ancho desconocido — solo cambia cuánto. El "~800×" que circulaba no era
absurdo: era un número sin medición, y ahora hay un piso.

 **Este bloque reemplaza tres estimaciones anteriores, las tres equivocadas.**
La original decía 12 MB por noche y 5 GB al año; la corrección de D2 revisada
decía 2 MB y 1 GB; y el factor de reducción circuló como "~250×" y como "~800×"
sin que ninguno saliera de una medición sobre el universo completo.

**Consecuencia sobre D1:** la condición abierta **se disuelve**. Hay retención
completa sin retención corta, así que "puedo reprocesar el pasado" sigue en pie
entero. **D1 no hay que revisarla.**

**Costos, sin adornos:**

- *Ergonomía de lectura.* "Qué había el 21 de agosto" deja de ser un
 `WHERE fecha = ...` y pasa a ser un join contra el registro de observaciones.
- *Orden de claves.* Comparar bytes exige que el JSON venga siempre con las
 claves en el mismo orden. Se ordenan antes de hashear. Ordenar claves no es
 transformar valores, así que no rompe A.
- *Índice de estado.* Hace falta el último hash por contrato: 2,8M hashes,
 **171 MB** en DuckDB, medido: la estimación de 90 MB no contaba
 el índice de la llave primaria.

**Propiedad de diseño importante:** el índice de hashes es **derivado, no
autoritativo**. Si se pierde o se corrompe, se reconstruye releyendo los
archivos de raw y tomando el último hash por contrato. Los archivos siguen
siendo la fuente de verdad; el índice es caché.

**Opciones descartadas:** (a) guardar todo — inviable. (b) ventana móvil de N
días — mata la premisa con la que se eligió A. (d) bajar el flujo 3 a semanal —
queda en el bolsillo como plan B; divide por siete pero le baja resolución a la
serie que **es** el producto.

###  D4 CERRADA POR ARRASTRE — la comparación corre en SQL

No fue una decisión propia: D1=A la determina. La comparación material /
cosmética / imposible vive en dbt, sobre `staging`.

Los dos filtros son de finura distinta y hacen falta los dos:

| Filtro | Dónde | Qué decide |
|---|---|---|
| Bytes | Python, antes de escribir | Si la fila se guarda en disco |
| Clasificación | dbt, sobre staging | Si la fila **merece una versión** |

El segundo sigue siendo imprescindible: una fila puede cambiar en bytes sin
cambiar materialmente (una tilde corregida en `nombre_entidad` es cosmética).
Esa distinción solo la sabe `columnas.py`.

Beneficio colateral: dbt pasa de procesar 2,8M de filas por noche a decenas de
miles. `dbt build` corre en segundos y los tests corren sobre un volumen
manejable en un portátil.

###  D5 DECIDIDA — se compara contra la observación anterior en raw

Para cada contrato, las observaciones se
ordenan por fecha de extracción y cada una se compara con la que la precede
(`LAG` sobre la historia de raw). **No** se compara contra la versión vigente
en `fct_contratos_snapshot`.

**El argumento es de coherencia con D1, no técnico.**

Comparando contra raw, `fct_contratos_snapshot` es una **función de raw**: se
borra entera, se corre `dbt build`, y se obtiene exactamente la misma tabla. La
historia la determinan los archivos, no el orden en que se corrieron las cosas.

Comparando contra la tabla destino, sería **estado acumulado**: borrarla
significa no poder reconstruirla con un `dbt run`, porque cada comparación
necesita el resultado de la anterior.

Y eso choca de frente con D1. Se eligió raw fiel con un solo argumento: *va a
aparecer un defecto de normalización y se va a querer corregir el pasado*. Ese
día, comparando contra raw se arregla `staging`, se corre
`dbt build --full-refresh` y toda la historia se recalcula. Comparando contra
la tabla destino, las versiones ya escritas siguen calculadas con la lógica
vieja. **Sería pagar el costo de A sin cobrar el beneficio.**

**Materialización:** incremental con ventana de reproceso. La *lógica* compara
contra la observación anterior en raw (determinista, reconstruible); la
*materialización* no recalcula diez años en cada corrida. Patrón estándar de dbt.

#### `dbt snapshot` no sirve, por dos razones

1. Es la opción 2: compara contra la tabla destino y acumula.
2. Aunque se quisiera la 2, compara con `check_cols` —todas o una lista— y **no
 tiene forma de expresar una clasificación de tres vías**. No hay manera de
 decirle "estas 32 columnas pisan el valor actual sin generar versión".
 `columnas.py` no cabe en esa herramienta.

En cualquier caso hay que escribir un modelo propio. Es material de README:

> `dbt snapshot` no soporta columnas cosméticas, así que el SCD2 está
> implementado a mano, con la clasificación generada desde `columnas.py`.

**Pregunta que D5 deja abierta (va a D6/D8):** las cosméticas "pisan el valor
actual sin generar versión" — ¿pisan **qué**? Si hoy se corrige el nombre de una
entidad, ¿se actualiza solo la versión abierta, o las cuarenta versiones
históricas de ese contrato? Las dos son defendibles y dicen cosas distintas:
"así se llamaba entonces" contra "así se llama, y el nombre no es parte de la
historia".

###  D6 DECIDIDA — comparación columna por columna, con `IS DISTINCT FROM`

Se comparan las 28 materiales una por
una y se guarda **qué** cambió, no solo que algo cambió. Se descarta el hash de
las materiales y el híbrido.

**El argumento: la columna `motivo_del_cambio` no es adorno.** Responde
directamente:

- ¿Esta versión se generó por adición de valor, prórroga, pago o cesión?
- ¿Cuántas versiones de un contrato son avance de pagos y cuántas
 modificaciones reales?
- ¿Qué entidades generan más eventos de prórroga? — **pregunta 6**.

Y conecta con H26: en el dataset oficial, `ADICION EN EL VALOR` existe pero no
es exhaustivo — hay adiciones dentro de `MODIFICACION GENERAL`, el 75% de las
filas. **El Estado clasifica mal sus propias modificaciones.** La comparación
por columna produce esa clasificación derivada del **delta observado**, no de
una etiqueta escrita a mano por cada entidad: si `valor_del_contrato` subió,
fue una adición, sin ambigüedad.

Deja de ser detalle de implementación y pasa a ser hallazgo del proyecto:

> La clasificación oficial de modificaciones es incompleta; la plataforma la
> reconstruye desde el delta observado.

#### Dos trampas técnicas, ambas golpean al hash

**1. `NULL != NULL` no da verdadero, da `NULL`.** Y las materiales incluyen
`fecha_inicio_liquidacion`, `fecha_fin_liquidacion` y
`fecha_de_notificaci_n_de_prorrogaci_n`, que **arrancan nulas y se llenan** —
el cambio que `columnas.py` describe como el más informativo que existe en un
snapshot acumulativo. Un `!=` ingenuo lo pierde. Se usa **`IS DISTINCT FROM`**.

**2. Concatenar con `NULL` da `NULL`.** Un contrato con una sola columna nula
produciría hash nulo, y todos los hashes nulos se ven iguales entre sí. Se
arregla con `COALESCE` a un centinela — pero el centinela tiene que ser un
valor imposible en los datos, y esta fuente usa `"No definido"` como texto real
en el 22% de una columna (H28). Elegir mal el centinela crea colisiones
silenciosas.

El hash es más rápido pero tiene más formas de fallar en silencio — justo la
categoría de error contra la que se viene diseñando. Y con D3 el volumen
nocturno es de decenas de miles de filas, no millones: **el argumento de
rendimiento del hash no aplica a este volumen.**

**Nota de implementación:** las columnas monetarias se comparan sobre el valor
**numérico canónico**, no sobre el texto, o `"1000"` contra `"1000.00"` genera
un motivo falso. Lo resuelve `staging` por D1, pero hay que tenerlo presente al
escribir el modelo.

###  D7 DECIDIDA — cargar igual, registrar y alertar (severidad `warn` al inicio)

Cuando una columna imposible cambia: la
fila entra normalmente, la discrepancia se guarda en una tabla de alertas con
ambos valores y la fecha en que divergieron, y un test de dbt la reporta.

**Observación previa: las siete imposibles no son iguales.** `id_contrato` es
la llave por la que se unen las observaciones — si "cambia", no se detecta
comparando, sería simplemente otro contrato. Su modo de fallo no es la
mutación sino la **duplicación**: dos filas con el mismo id en una extracción.
Eso lo captura un test de unicidad, no la comparación de cambios. Está en
`IMPOSIBLES` por razones correctas pero se verifica con otro mecanismo; no hay
que buscar una alerta que estructuralmente no puede dispararse. Las otras seis
sí pueden cambiar.

**Por qué no bloquear.** Una entidad puede corregir un error de tipeo en
`fecha_de_firma`: corrección legítima, no catástrofe. Bloquear detendría la
ingesta de 2,8M de contratos por eso. Y aplica lo ya escrito en `columnas.py`
sobre `referencia_del_contrato` —*"una alerta ruidosa enseña a ignorarla"*—
con un agravante: una alerta que **para el pipeline** enseña a desactivarla.

**Por qué no cuarentena.** Rompe la coherencia con D5. Si la fila no entra a
raw, la historia deja de ser función de raw. Si entra a raw pero se excluye del
modelo, hay dos verdades sobre qué contratos existen y algún conteo no va a
cuadrar sin que nadie sepa por qué.

**Qué valor queda en la tabla.** Se toma el **valor nuevo**, igual que una
cosmética. Las versiones históricas conservan lo observado entonces, la versión
abierta refleja lo que dice la fuente hoy, y la tabla de alertas guarda ambos.
Nada se pierde y la tabla principal no se llena de casos especiales.

**Severidad: todo arranca en `warn`.** No se sabe cuántas veces se dispara —
puede ser cero al año o cinco mil, y no hay forma de saberlo hasta correrlo. Si
arranca en `error` y se dispara mil veces, la reacción natural es bajarlo o
borrarlo, y ahí se perdió la alerta. Medir un mes y **subir a `error` solo las
columnas que efectivamente no se mueven**.

Ese ejercicio tiene valor propio: contar cuántos contratos cambian de
`nit_entidad` es en sí mismo un hallazgo. Si la entidad contratante de un
contrato cambia, eso es una historia.

###  D8 DECIDIDA — `observado_desde` / `observado_hasta`, intervalos semiabiertos

Cierra el mapa: las ocho resueltas.

#### Las fechas son de observación, no de vigencia

En un SCD2 de manual, `valido_desde` es "desde cuándo esto fue verdad en el
mundo real". **Acá no se puede saber.** Si el 21 de agosto se observa que
`valor_pagado` subió de 10M a 15M, el pago ocurrió en algún momento entre la
observación anterior y esta. Ninguna columna dice cuándo. Es H8.

Se descarta usar fechas de negocio cuando existan (`ultima_actualizacion` para
modificaciones): para los pagos no existe, y quedaría una columna que a veces
significa una cosa y a veces otra. **Peor que una columna consistentemente
aproximada.**

**Los nombres cambian a `observado_desde` / `observado_hasta`.** Un nombre que
no promete lo que no puede cumplir vale más que la convención. Frase de README:

> La plataforma no sabe cuándo cambió el contrato; sabe cuándo el cambio se
> volvió visible, con una resolución igual a la frecuencia del barrido.

#### El borde derecho

La versión anterior se cierra con **la fecha de la observación nueva**, no con
el día anterior. Intervalos semiabiertos: `>= desde AND < hasta`. Encajan sin
huecos ni solapes, y es el **mismo criterio que ya usa `_rango` en
`flujos.py`** — usarlo en los dos extremos del pipeline es coherencia que se
nota.

La versión abierta lleva `observado_hasta` **nulo**. Se descarta el centinela
`9999-12-31`: haría que un contrato cerrado hace tres años parezca vigente
hasta el año 9999 en cualquier gráfico que no filtre.

#### Las cosméticas pisan SOLO la versión abierta

Resuelve la pregunta que dejó D5. Si se pisaran todas las versiones, un
`--full-refresh` reconstruiría la tabla desde raw y **daría un resultado
distinto**, porque el reproceso sí ve la historia de nombres. Eso rompe lo
ganado en D5: la tabla dejaría de ser función de raw.

Efecto que se acepta a conciencia: **las versiones viejas muestran nombres de
entidad desactualizados.** Correcto para auditar, molesto para un tablero. La
solución no es pisar la historia: el mart une contra `dim_entidad` por la llave
y toma el nombre actual. Ese es precisamente el trabajo de una dimensión.

#### Un hueco que hay que nombrar: `motivo_de_cierre`

Un contrato en estado terminal deja de ser barrido por el flujo 3, así que su
última versión queda abierta para siempre — `observado_hasta` nulo, aunque hace
tres años que nadie lo mira. Es honesto ("es lo último que observé") pero un
lector puede interpretar el nulo como "sigue activo".

Se agrega una columna **`motivo_de_cierre`** que distinga:

| Valor | Significado |
|---|---|
| `version_nueva` | Se cerró porque llegó una observación distinta |
| `abierta` | Sigue en el universo vivo y se sigue observando |
| `fuera_de_observacion` | Pasó a estado terminal; ya no se barre |

Un nulo que significa tres cosas distintas es un fallo silencioso esperando.


###  D10 IMPLEMENTADA — la procedencia se registra en el manifiesto de la partición

> **Salta de D8 a D10 a propósito.** D9 —dbt sobre DuckDB local, con el porte a
> Snowflake como trabajo posterior— es infraestructura del proyecto entero y no
> de la capa raw, así que dónde se documenta sigue abierto. El identificador
> queda reservado; no se reutiliza.

#### El problema

Raw no registra **de qué estado de la fuente vino cada observación**. La
partición se llama por `fecha_extraccion`, que es cuándo bajamos los datos, no
qué vimos. Mientras se creyó que la fuente se regeneraba a diario las dos cosas
parecían la misma; no lo son, y el costo ya se pagó: el ancho del intervalo de la
corrida del 25 es irrecuperable porque nadie anotó de qué corte leyó el barrido
del 23. Si la fuente salta un día, dos particiones con fechas distintas contienen
el **mismo** estado y nada en raw lo dice.

#### Qué identifica a una regeneración

**El valor de `min(:updated_at) = max(:updated_at)`**, al milisegundo. No es una
etiqueta nuestra: es el sello que la propia fuente le puso a ese estado, y por H2
—confirmado cuatro veces: 18, 21, 26 y 28 de agosto— es único por regeneración.

Esto **invierte a medias la conclusión de H2**, y conviene decirlo porque el
inventario declara ese campo inútil. Es inútil como watermark *de fila*, que era
la pregunta que se le hizo. La misma propiedad que lo inutiliza para eso —que
min y max coincidan— lo convierte en la **llave natural del corte**. Dos
límites: vale solo para `jbjy-vk9h`, porque los hermanos escriben en continuo y
no tienen corte (H23); y no es reconstruible desde las filas, porque ninguna lo
contiene.

#### Qué se registra: tres valores, no uno

| Campo | Qué es | De dónde sale |
|---|---|---|
| `corte_anterior` | el corte de la última ingesta completa | contra esto compara el guardarraíl de D11 |
| `corte_al_iniciar` | el corte vivo al arrancar la corrida | la consulta que D11 hace igual |
| `corte_al_terminar` | el corte vivo al terminar | una consulta de segundos al final de ~50 minutos |

Los dos primeros convierten cada partición en un **intervalo con sus dos extremos
fechados**, que es lo que la corrida del 25 no tiene. El tercero cubre un caso
que hoy es invisible: una corrida dura ~50 minutos y nada impide que la fuente
regenere en el medio, dejando una partición **a caballo** de dos cortes, con las
páginas de antes de un estado y las de después de otro. Si `corte_al_iniciar ≠
corte_al_terminar`, la partición está a caballo. **Qué se hace en ese caso queda
sin decidir**; por ahora se registra y se advierte, que es lo barato y no
compromete nada.

#### Dónde vive: el manifiesto (I3), no las filas

| | Alternativa | Por qué no |
|---|---|---|
| A | Bitácora aparte, fuera de raw | Crea un **segundo lugar autoritativo** que, a diferencia del índice de hashes, **no es reconstruible desde raw**: si se pierde, la procedencia se pierde con ella |
| **B** | **En el `_manifiesto.json` de cada partición** | **Elegida** |
| C | En los metadatos de cada fila, fuera del hash | ~30 B sobre 320, un 9% más de disco, y el raw ya escrito no los tiene: quedan **dos formas de raw para siempre** y `staging` tiene que tolerar las dos |
| D | B y C juntos | Redundancia, y con ella la posibilidad de que un día no coincidan |
| — | En el índice DuckDB | Descartada aparte: el índice está declarado **derivado y reconstruible**, y meterle estado autoritativo rompe la propiedad que hoy hace que perderlo no sea grave |

**Los tres argumentos que decidieron:**

1. **No toca las líneas de datos.** El hash, el índice, los 916 MB del barrido,
   los 18 MB de la incremental, el 98,13% y los 320 B por fila siguen valiendo
   tal cual. Los metadatos están fuera del hash por I1, y eso está verificado:
   11.449 filas se descartaron con otra `fecha_extraccion`.
2. **El estado del guardarraíl deja de ser un lugar aparte.** "¿Cuál fue el
   último corte que ingerí?" se contesta leyendo los manifiestos y tomando el
   máximo. Son archivos diminutos, unas decenas. Así que **D11 no necesita
   ninguna bitácora**: su estado es derivado de raw, igual que el índice.
3. **No cierra la puerta a C.** Si algún día la procedencia tiene que vivir en la
   fila, las particiones nuevas la llevan y las viejas conservan su manifiesto.
   Es aditivo, no una reescritura.

**El punto débil de B, y por qué deja de serlo.** La atribución es por partición,
así que solo es verdad si una partición contiene un corte y uno solo. Con el
guardarraíl de D11 delante —que rechaza correr contra un corte ya ingerido— y con
`corte_al_iniciar`/`corte_al_terminar` detrás, esa condición deja de ser un
supuesto y pasa a ser un **invariante comprobado en las dos puntas**.

#### Los dos costos que se aceptan

**dbt va a leer dos formas de archivo.** La disciplina de D9 pide que un único
modelo toque los archivos, para que el porte a Snowflake no sea una reescritura.
Con B hay un segundo modelo que lee los `_manifiesto.json` y se une por la ruta
de la partición. Es una excepción real, y se acepta porque son JSON minúsculos,
la unión es por una columna, y el día del porte los dos modelos caen bajo el
mismo problema —Snowflake no lee el disco local—, así que no es un caso nuevo
sino el mismo dos veces.

**Si se pierden los manifiestos y quedan solo los `.jsonl.gz`, la procedencia se
pierde.** Se acepta: el manifiesto vive dentro del directorio de la partición, y
perderlo significa haber perdido también `trozos_cerrados`, el cursor y
`_COMPLETO`. No es un escenario donde raw sobrevive a medias; es uno donde raw ya
está roto.

#### Migración de lo ya escrito

Las particiones existentes no tienen estos campos. **"Sin corte anotado" es
desconocido, y se advierte sin bloquear.** Un guardarraíl que se planta ante
datos viejos es el error que falta, y entre un error que sobra y uno que falta ya
está elegido cuál se prefiere.

**Se recupera un valor hacia atrás, y uno solo:** la partición del 25 se anota
con `corte_al_iniciar = 2026-08-25T09:05:54.277Z`. La fuente quedó congelada en
ese valor desde entonces —comprobado el 26 a las 20:30 y el 28 a las ~10:00— y
esa corrida arrancó de día, muy después de las 04:05 COT, así que no pudo haber
leído otro. **De qué corte leyó el barrido del 23 no se recupera**: ahí no hay
congelamiento que ayude.

#### Cómo quedó implementada — 28/08/2026

`paginacion.corte()` devuelve un `Corte` con los dos extremos y la propiedad
`confiable`. `ParticionRaw` recibe `corte_al_iniciar`, `corte_anterior` y
`corte_confiable`, y `completar()` recibe `corte_al_terminar`. Los cuatro van al
manifiesto **siempre, incluso en nulo**: un nulo escrito dice "no se sabe", una
clave ausente es indistinguible de un manifiesto viejo.

Corrió contra la fuente real el 28. Este es el primer manifiesto con procedencia:

```json
"corte_anterior": null,
"corte_al_iniciar": "2026-08-25T09:05:54.277Z",
"corte_al_terminar": "2026-08-25T09:05:54.277Z",
"corte_confiable": true
```

`corte_anterior` en nulo porque la ingesta previa —la del 25— es anterior a D10.
El intervalo de esa partición tiene ancho cero y el manifiesto lo dice.

**Tres cosas que salieron al implementarla:**

1. **Reanudar puede mezclar dos cortes, y no estaba previsto.** `_retomar()`
   sigue desde el cursor sin mirar contra qué corte se había empezado. Una
   corrida que arranca a las 04:00 y cruza la ventana de regeneración dejaría
   trozos de un estado y seguiría con otro en el mismo directorio, y el
   manifiesto se reescribiría con el corte nuevo: el viejo se perdería sin
   rastro. Ahora se descarta el progreso y se empieza de cero, avisando. Cuesta
   hasta 50 minutos y no pierde nada, que es el error que sobra.
2. **La procedencia se escribe en los tres flujos y se lee en uno.** La consulta
   ya se hizo, así que anotarla es gratis, y el día que haga falta saber de qué
   estado venía una partición del flujo 1 el dato va a estar.
3. **Las dos consultas fallan distinto, a propósito.** Al arrancar, un fallo de
   red aborta: reintentar cuesta volver a escribir el comando. Al terminar, se
   completa igual con la marca en nulo: perder el `_COMPLETO` de un barrido de
   cincuenta minutos por un 429 en una consulta de metadatos es el error que
   falta.

#### Lo que queda sin decidir

- Qué se hace con una partición a caballo de dos cortes. Hoy se registra, se
  advierte y **se deja legible**: negarle `_COMPLETO` sería tomar esa decisión
  de costado.
- Si algún día se migra a C.

###  D11 IMPLEMENTADA — el disparador del flujo 3 es el corte de la fuente, no el calendario

#### El problema

Con cadencia irregular, correr por calendario cuesta ~50 minutos para escribir
una partición vacía, y correr tarde es lo único que pierde datos de verdad. Las
alternativas eran: **(a)** sondear a mano y decidir a mano —cero código, y el
error queda en comparar mentalmente dos valores de 24 caracteres—; **(b)** el
cargador consulta y se planta solo; **(c)** el cargador consulta, registra y
corre igual, que documenta el duplicado en vez de evitarlo. **Se eligió (b).**

La consulta vive en `paginacion.py`, que es el único módulo que puede conocer una
URL. Es la misma grieta que tiene abierta la pregunta de `validar_cobertura()`:
hoy no hay forma de preguntarle nada a la fuente que no sean filas.

#### El guardarraíl va en la dirección permisiva, y eso es deliberado

Los dos errores posibles no valen lo mismo:

| Error | Costo |
|---|---|
| Deja pasar una corrida contra un corte ya visto | ~50 minutos y una partición vacía. Recuperable, y el descarte del 100% lo grita en pantalla |
| Bloquea una corrida legítima | Si la fuente regenera otra vez antes de que alguien lo note, **esa observación no existe más** |

Es el criterio de siempre —entre un error que sobra y uno que falta, el que
sobra— y el escarmiento concreto es R2: el guardarraíl de `fecha_extraccion` con
dos definiciones de "hoy" habría rechazado cargas legítimas cinco horas al día.
De ahí dos exigencias:

1. **La condición de aborto es "existe una partición COMPLETA para este corte"**,
   no "vi este corte". Una muerte dura deja una partición incompleta contra el
   mismo corte, y reanudarla es exactamente lo que I5 permite; con la condición
   ingenua, la reanudación quedaría bloqueada. `_COMPLETO` ya distingue los dos
   casos.
2. **Una bandera de forzado**, nombrada en el propio mensaje de aborto. Un
   guardarraíl que no se puede saltar a mano, en un pipeline que corre a mano, es
   un pipeline que un día no corre.

#### Qué implica para Airflow

Tres cosas, y las tres son consecuencia de que el calendario no manda:

- **El DAG es un sensor sobre el corte más un corte-circuito, no un `schedule` a
  una hora.** Como la lógica vive en el cargador, el DAG la hereda; si viviera
  solo en el DAG, correr a mano la perdería.
- **`catchup` tiene que ser `False`, y no es una preferencia.** Airflow rellena
  por defecto las corridas que cree que faltaron, y contra el flujo 3 eso es
  exactamente lo que R1 prohíbe: escribiría el hoy con fecha vieja. Con cadencia
  irregular, esa lista va a ser larga.
- **`logical_date` no sirve como identidad de la corrida.** Airflow nombra cada
  ejecución por un intervalo de calendario; acá la identidad es el corte de la
  fuente, que no tiene relación con el calendario.

#### Cómo quedó implementada — 28/08/2026

Vive en `cargar_vivos`, junto al guardarraíl de R1, y **corta antes de bajar una
sola página**: es la diferencia entre cincuenta minutos y ninguno, y hay una
aserción dedicada a eso. La bandera es `--forzar-corte-repetido`, larga a
propósito. `CorteYaIngerido` devuelve **código 4**, distinto del 1 y del 2,
porque un DAG tiene que separar "no había nada nuevo" de "algo se rompió".

⚠ **D11 solo agrega valor entre días distintos.** Salió al escribir los tests,
que fallaron los primeros cuatro por reusar la `fecha_extraccion`: dentro del
mismo día el directorio es el mismo y el `_solo_lectura` de `escritura.py` ya
bloqueaba. Lo que no estaba cubierto es correr hoy y mañana contra el mismo
estado de la fuente, que es exactamente el caso del 26 de agosto.

**Y necesita que los manifiestos tengan el corte.** El 28 avisó de dos
particiones sin anotar —el barrido del 23 y la incremental del 25— y dejó
correr, que es la regla de migración: desconocido no bloquea. Desde la corrida
del 28, que sí lo anota, el agujero está cerrado.

#### Lo que queda sin decidir

Si el guardarraíl aplica solo al flujo 3 o a los tres. El flujo 3 pregunta por el
estado vivo, así que contra el mismo corte no aporta nada. Los flujos 1 y 2
preguntan por ventanas de fecha de negocio y son reproducibles hacia atrás por
R1, así que ahí un corte repetido no es el mismo tipo de error. La lectura
provisional es que el guardarraíl es del flujo 3.


---

## Implementación: I1 a I5

Las ocho decisiones de diseño (D1–D8) no cubren estas. Se numeran I1–I5.

| # | Decisión | Estado |
|---|---|---|
| I1 | Cómo se representa la fila para hashear |  **JSON canónico, los mismos bytes que se escriben** |
| I2 | Qué algoritmo de hash |  **BLAKE2b truncado a 128 bits** |
| I3 | Dónde vive el manifiesto |  **JSON dentro de cada partición** |
| I4 | Cómo se estructura el módulo |  **Tres módulos; el índice completo en memoria** |
| I5 | Cuándo se cierra el trozo y cuándo avanza el cursor |  **Por líneas o por páginas; el cursor solo si el buffer está vacío** |

 **I1 e I2 juntas definen el contrato del índice de hashes.** Si cambian
después de la primera corrida, todos los hashes guardados quedan inservibles.
No es catastrófico —el índice es derivado y se reconstruye desde raw (D3)— pero
conviene fijarlas antes de la primera corrida y no descubrirlo en tres meses.

###  I1 DECIDIDA — JSON canónico, y esos mismos bytes se escriben

**La propiedad que se busca:** que el hash sea el hash de los bytes que quedan
en disco. Se serializa **una sola vez**; esa cadena se hashea y esa misma cadena
se escribe. Así "los bytes cambiaron" y "el archivo habría sido distinto" son la
misma afirmación. Serializar dos veces crearía dos rutas que pueden divergir en
silencio.

```python
linea = json.dumps(fila, sort_keys=True, ensure_ascii=False,
 separators=(",", ":")).encode("utf-8")
```

- `sort_keys=True` — ordena alfabéticamente, también dentro de `urlproceso`, el
 único objeto anidado. **Ordenar claves no es normalizar**: el orden no es
 información (`{"a":1,"b":2}` y `{"b":2,"a":1}` son el mismo objeto JSON), así
 que no rompe D1. Beneficio colateral: los archivos quedan deterministas y
 comparables con `diff`.
- `separators=(",", ":")` — sin esto, `json.dumps` mete un espacio tras cada
 coma y cada dos puntos. Sobre 2,8M de filas es volumen que no dice nada.
- `ensure_ascii=False` — archivo más chico y legible. Con H22 en mente
 (`\u0093`, `\u0092` son comillas de Windows-1252 mal decodificadas), esos
 caracteres quedan visibles en vez de escapados. Cualquiera de las dos sirve
 mientras sea **consistente**; cambiarla después invalida todos los hashes.

**Opciones descartadas:** concatenar campos con separador (más rápido, pero esta
fuente tiene saltos de línea embebidos, comillas rotas y punto y coma en los
textos — elegir mal el separador da colisiones silenciosas); msgpack u otro
binario (rompe D1: raw dejaría de ser inspeccionable a ojo, que es media razón
por la que se eligió JSONL en D2).

#### Reglas que no se tocan

**1. Los metadatos se agregan DESPUÉS de hashear.** `fecha_extraccion` y `flujo`
cambian todas las noches por definición; si entran al hash, nada se deduplica
jamás. Van como envoltorio alrededor de la carga útil:

```json
{"fecha_extraccion": "...", "flujo": "...", "hash": "...", "datos": {...}}
```

El archivo se autodocumenta y el hash sigue siendo solo de `datos`.

**2. Las claves ausentes se dejan ausentes.** D1 prohíbe rellenar en raw. Si una
noche la API omite `ultima_actualizacion` y a la siguiente la manda como `null`
sin que nada haya cambiado, el hash cambia y se guarda una fila de más. Es el
error que sobra, o sea el aceptable.

 **Esto va como comentario en el código.** El instinto de cualquiera que lo lea
después va a ser "arreglarlo" rellenando antes de hashear — y eso **sí** rompería
D1.

**3. Si `json.dumps` falla, falla ruidosamente** con el `id_contrato` en el
mensaje. No se salta la fila.

###  I2 DECIDIDA — BLAKE2b truncado a 128 bits

`hashlib.blake2b(linea, digest_size=16)`, de la biblioteca estándar. Se guarda
en **hexadecimal** (32 caracteres), no en bytes crudos: legible al depurar en
DuckDB, y la diferencia es 90 MB contra 45 MB para 2.825.685 contratos.

#### Por qué 128 bits, y no 64 ni 256

Una colisión significa que dos filas distintas dan el mismo hash, el cargador
concluye "no cambió nada", **no guarda la fila nueva**, y esa observación se
pierde para siempre porque la fuente ya se sobrescribió.

Es el **error caro**, y el único punto de todo el diseño donde el error puede ir
en la dirección equivocada: la deduplicación por bytes solo puede sobrar, salvo
por esto.

Probabilidad de al menos una colisión entre *n* elementos con *b* bits ≈
**n² / 2^(b+1)**. Con ~20M de observaciones guardadas en un año:

| Bits | Colisión en 20M | Lectura |
|---|---|---|
| 64 | ~1 en 100.000 | Bajo, pero no despreciable a diez años |
| 128 | ~1 en 10²⁴ | No va a pasar |
| 256 | Absurdamente menor | No va a pasar, con el doble de índice |

Matiz que reduce aún más el riesgo real: la colisión tendría que ocurrir entre
dos versiones **del mismo contrato**, porque el índice es por `id_contrato`. El
espacio efectivo son decenas de versiones, no 20 millones.

#### Medición real, sobre una fila de ejemplo

 **Corrige una suposición previa.** Se había dicho que BLAKE2b se elegía en
parte por ser más rápido que MD5. Medido, la diferencia es del 5%: irrelevante.

| Operación | Velocidad | 2.825.685 filas |
|---|---|---|
| `blake2b(digest_size=16)` | 1.036.096/s | **2,7 s** |
| `md5` | 1.052.565/s | 2,7 s |
| `json.dumps` canónico | 184.449/s | **15,3 s** |

**El hash no es el costo: serializar lo es**, y es cinco veces más caro. Pero
como I1 decidió que se serializa una sola vez y esa misma cadena se escribe,
esos 15 s no son overhead de la deduplicación — se pagarían igual para escribir
el archivo. **La deduplicación sale prácticamente gratis.**

Los dos números se pierden dentro de los ~20 minutos que tarda la API. **El
cuello de botella es la red, no el CPU.** Queda escrito para que nadie optimice
el lugar equivocado.

Entonces la razón para elegir BLAKE2b sobre MD5 es una sola y hay que decirla
sin adornos: **no arrastrar la conversación sobre criptografía rota** en un repo
de portafolio. La respuesta correcta sería "sí, MD5 está roto, y acá no hay
adversario", pero es una defensa que no hace falta tener que dar.

**Descartados:** xxhash y BLAKE3 — dependencias externas para ahorrar segundos
en un proceso limitado por la red.

#### El algoritmo se escribe en el manifiesto

Campo `algoritmo_hash: "blake2b-128"` junto al cursor. Si algún día hay que
cambiarlo, hay que poder distinguir hashes viejos de nuevos sin adivinar.

#### Verificado

- Un mismo objeto con las claves en distinto orden produce, con
 `sort_keys=True`, la **cadena idéntica**. La canonicalización de I1 funciona.
- Salida de ejemplo: `20c3a9e4fe5f274b53317978e305d840` (32 caracteres hex).

###  I3 DECIDIDA — manifiesto como archivo JSON dentro de cada partición

```
raw/flujo=refresco_de_vivos/fecha_extraccion=2026-08-21/particion=2020-01/
 _manifiesto.json ← progreso: cursor, trozos cerrados, algoritmo
 parte-0001.jsonl.gz
 parte-0002.jsonl.gz
 _COMPLETO ← única señal de "terminado"
```

**Qué guarda:** último cursor de keyset confirmado, cuántos trozos se cerraron,
`algoritmo_hash`, y marcas de tiempo de inicio y última escritura.

#### `_COMPLETO` y el manifiesto no duplican información

Son la misma pregunta con dos respuestas posibles, y dos verdades sobre si una
partición terminó **van a discrepar algún día**. Se separan por
responsabilidad: el **manifiesto lleva el progreso** (para reanudar), y
**`_COMPLETO` es la única señal de terminado** (para que dbt sepa qué leer).
Un archivo vacío es más barato de comprobar desde dbt que parsear un JSON.

#### Los dos argumentos que decidieron

**1. Coherencia con el invariante de orden de D2.** El invariante *escribir el
archivo antes de tocar el índice* existe porque, si el proceso muere en el
medio, se prefiere un duplicado en disco antes que una fila perdida. Con el
manifiesto en DuckDB, cada punto de control tendría que escribir en **dos
sistemas distintos**, y eso no se puede hacer atómicamente. Con el manifiesto en
la partición, el trozo y el manifiesto viven en el mismo directorio y el orden
es local: cerrar el trozo → actualizar el manifiesto → recién ahí tocar el
índice.

**2. DuckDB no admite dos escritores simultáneos.**  *Este punto apareció al
discutir I3 y no se había visto antes.* El flujo 3 se paraleliza lanzando varias
particiones a la vez — para eso existen los parámetros de fecha de
`refresco_de_vivos`. Con el manifiesto en DuckDB, cada partición paralela
pelearía por el mismo archivo de base de datos. Con manifiestos por partición,
cada proceso escribe en su propio directorio y **no hay contención**.

**Beneficio colateral:** la partición queda autocontenida. Se copia, se
inspecciona o se borra entera sin abrir nada, y si DuckDB se corrompe el
progreso sigue en disco.

#### El índice de hashes SÍ va en DuckDB — son cosas distintas

| | Alcance | Dónde |
|---|---|---|
| Índice de hashes | Global, por `id_contrato` | DuckDB, uno solo |
| Manifiesto | Local a una partición | JSON en el directorio |

 **PREGUNTA QUE ESTO DEJA ABIERTA.** Si varias particiones del flujo 3 corren
en paralelo y todas necesitan **escribir** en el índice de hashes, vuelve el
problema del escritor único de DuckDB. No se resuelve acá: depende de I4 (la
estructura del módulo), que podría cambiar la respuesta. Queda señalado en vez
de resuelto en silencio.

###  I4 DECIDIDA — tres módulos, y el índice completo en memoria

#### Estructura

| Módulo | Responsabilidad | Toca I/O |
|---|---|---|
| `hashing.py` | Canonicalizar, hashear, envolver | No — funciones puras |
| `indice.py` | Leer el índice, acumular, escribir la tanda | DuckDB |
| `escritura.py` | Trozos, compresión, manifiesto, `_COMPLETO` | Disco |

El orquestador vive en `scripts/`, no en `src/`.

**Por qué `indice` y `escritura` van separados, y no es estética:** son los dos
lados del invariante *escribir el archivo antes de tocar el índice* (D2). En un
mismo archivo, nada impide que alguien invierta el orden en un refactor.
Separados, el orden es visible en el orquestador y se puede testear.

#### El problema del escritor único de DuckDB

Lo dejó abierto I3: si varias particiones del flujo 3 corren en paralelo y todas
escriben en el índice, pelean por el mismo archivo. Tres salidas evaluadas:

1. **Serializar el flujo 3.** Pierde el paralelismo para el que
 `refresco_de_vivos` fue diseñado: 20 minutos se vuelven 80.
2. **Un índice por partición, fusionado al final.** No funciona: el índice es
 **global por contrato**, y uno parcial no puede responder "¿cuál fue el
 último hash de este contrato?". Rompe la deduplicación.
3. **Separar lectura de escritura.**  Cada proceso **lee** al arrancar (DuckDB
 admite muchos lectores), acumula en memoria, y **escribe su tanda al
 cerrar**. La escritura se serializa; la lectura no.

La 3 funciona por una razón concreta de este caso: un contrato pertenece a **una
sola partición** del flujo 3, porque las particiones son rangos disjuntos de
`fecha_de_firma`. Dos procesos nunca compiten por el mismo `id_contrato`, así
que una foto del índice tomada al arrancar alcanza.

**Costo:** si el proceso muere antes de escribir su tanda, esos hashes se
pierden y la próxima corrida ve esas filas como nuevas y las guarda de nuevo.
Duplicados en raw, que dbt resuelve tomando la última observación por contrato.
Otra vez el error que sobra.

#### Medición: cargar todo en memoria contra consultar por lotes

 **El resultado salió al revés de lo esperado y cambió la recomendación.**
Se iba a proponer consulta por lotes por prudencia de memoria.

| Estrategia | Memoria | Tiempo (flujo 3, 566 páginas) |
|---|---|---|
| **Índice completo en un dict** | **185 MB** | **2,1 s** · 4,2 s el 28 (una vez) |
| Consulta por lotes de 5.000 | Constante | **95,4 s** (169 ms × 566) |

La opción "prudente" es **47× más lenta** y protege 185 MB que no hacía falta
proteger. Proponerla por instinto habría metido minuto y medio de latencia por
noche a cambio de nada.

**Decisión:** cargar el índice completo al arrancar la partición, acumular los
hashes nuevos en un dict aparte, escribir la tanda al cerrar.

**Escritura final medida:** 0,2 s para los ~30.000 que cambian en una noche
típica. Los 13,9 s del caso extremo (cambia todo) solo ocurren la primera vez.

 **El caso extremo real fue 55,7 s, no 13,9.** Medido en el primer barrido
completo: 2.824.446 hashes volcados. Eso rompe el presupuesto de reintentos de
`_abrir()`, que suma 15,5 s de espera — no los ~30 que dice su docstring, porque
el último intento no duerme. Con particiones en paralelo, la que llegue mientras
otra vuelca **no alcanza a esperar y muere con `RuntimeError`**.

Hoy no muerde porque las particiones se corren en serie. Hay que rehacer el
cálculo antes de paralelizar.

 **Pero el caso extremo es más raro de lo que parecía.** La corrida
incremental del 2026-08-25 volcó 58.971 hashes en **4,0 s**, y los cargó en
4,2 s. O sea que los 55,7 s ocurren en la primera corrida y en un re-barrido
completo, no en una noche típica: en operación normal el volcado entra cómodo
en el presupuesto de 15,5 s.

Eso baja la prioridad del arreglo, **no lo cancela**. El día que exista el DAG,
la primera corrida sigue siendo una corrida, y es justo la que más tarda en
volcar.

 **Vigilar si el dataset crece.** Cuatro particiones en paralelo son cuatro
copias del índice: **740 MB**. Manejable hoy; si el dataset se duplica, hay que
volver a mirar los lotes.

#### Dos cosas que la medición dejó ver

**La inserción inicial tarda 20,6 s** y ocurre en la primera corrida, con el
índice vacío. El mensaje de progreso tiene que anunciarlo o va a parecer
colgado — lección .

**La carga tiene dos muestras y difieren al doble.** 2,1 s con 2.825.685
contratos el 23, y **4,2 s con 2.849.209** el 28 — un 0,8% más de filas y el
doble de tiempo. Una lectura de disco no es determinista y la máquina no estaba
en las mismas condiciones, así que no hay nada roto; lo que hay que retirar es
la idea de que 2,1 s sea *el* número. La conclusión de I4 no se mueve: contra
los 95,4 s de consultar por lotes, 4,2 sigue siendo 23× más rápido.

**El archivo del índice pesa 171 MB, no 90.** La estimación de I2 no contaba el
índice de la llave primaria. Sigue siendo chico frente al crecimiento anual de
raw —cuya cifra quedó retirada por depender de un intervalo de ancho supuesto,
ver D3— pero el número correcto es 171.


###  I5 DECIDIDA — el trozo se cierra por líneas o por páginas; el cursor solo avanza si el buffer está vacío

**Encontrado leyendo el código, no corriéndolo.** Es un defecto de la
interacción entre dos piezas que por separado están bien.

#### El defecto

El punto de control y el cierre del trozo iban a ritmos distintos: el cursor se
guardaba en el manifiesto **en cada página**, y el trozo se escribía a disco
**cada 5.000 líneas**. En el flujo 3, de cada página de 5.000 filas cambian
unas 50, así que llenar un trozo lleva ~100 páginas — y durante esas cien
páginas el manifiesto ya anunciaba el avance mientras las líneas seguían en
memoria.

Una muerte **dura** —`SIGKILL`, corte de luz, OOM; no una excepción, que el
`with` sí alcanza a cubrir— dejaba el manifiesto diciendo "ya pasé por acá" con
las filas evaporadas. La reanudación arrancaba después de ellas y **no las
volvía a pedir nunca.** La fuente ya se había sobrescrito.

Invierte la asimetría sobre la que está construido todo el diseño: de los tres
lugares donde vivía una fila —buffer, índice y cursor— el único que sobrevivía
al fallo era el que no debía.

#### La decisión

Dos cotas para cerrar el trozo, la que ocurra primero: **líneas acumuladas**
(5.000) y **páginas desde el último cierre** (20). Y una regla para el cursor:
**solo pasa al manifiesto si el buffer está vacío.**

La regla vive en `_guardar_manifiesto()`, que es el único punto donde el cursor
llega al disco. Así el manifiesto no puede anunciar un avance mayor que lo
escrito, por construcción y en un solo lugar.

 **La condición es "el buffer está vacío", no "se acaba de cerrar un trozo".**
Parece lo mismo y no lo es: en la segunda corrida de una misma ventana el
descarte es del 100%, no se escribe ni una línea y nunca se cierra un trozo. Con
la regla del trozo el cursor no avanzaría jamás y cualquier interrupción
reiniciaría desde cero.

#### Por qué no cerrar el trozo en cada página

Era la opción más simple y elimina el riesgo por construcción, sin tener que
razonar sobre cuándo muere el proceso. Se midió su costo sobre filas
sintéticas con la redundancia de las reales:

| líneas por trozo | archivos | penalización de tamaño |
|---|---|---|
| 5.000 | 1 | — |
| 500 | 10 | +1,8% |
| 100 | 50 | +9,3% |
| **50** (una página del flujo 3) | 100 | **+18,1%** |
| 25 | 200 | +34,5% |

El espacio no es el problema: 18% sobre 2 MB por noche son 360 KB. Lo que cuesta
son **~200.000 archivos al año** entre las cuatro particiones, de forma
permanente, a cambio de un riesgo ocasional.

#### Por qué no solo la cota de páginas sin número

La alternativa era que el cursor apuntara al último trozo cerrado y nada más:
igual de segura, más simple, sin parámetro nuevo. Deja el peor caso en ~100
páginas rebajadas.

Se eligió acotarlo **porque hoy la interrupción no es el caso raro**:
`paginacion.py` todavía no tiene reintentos ante 429 y 5xx, y H32 ya demostró
que esta fuente se cae bajo carga. Un solo error en la página 300 aborta el
barrido.

 **Esta decisión se revisa cuando existan los reintentos.** Ahí la
interrupción vuelve a ser rara y la versión sin cota es preferible por simple.

#### El número de páginas era una estimación. Ya está medido

20 suponía ~50 líneas escritas por página, que a su vez suponía el 1% de cambio.

**Medido en la corrida incremental del 2026-08-25: 103,6 líneas por página**
(58.971 líneas en 569 páginas). El doble de lo supuesto. Llenar un trozo de
5.000 líneas toma **48 páginas**, así que la cota que manda sigue siendo la de
páginas — pero por un margen bastante menor que el previsto.

Esa corrida cerró **31 trozos**, no los 29 que dan 569 páginas divididas por 20.
Los dos extra salen de la cota de líneas, y el porqué importa más que el número:

 **La escritura no está repartida a lo largo del recorrido: está apilada al
final.** La página 1 escribió 0 filas de 5.000; la 568 escribió **2.413**, o sea
el 48%. Un factor de 600× entre el arranque y la cola, contra un promedio de
104. En la cola, veinte páginas superan las 5.000 líneas y el trozo cierra por
líneas antes de llegar a la cota de páginas.

No se sabe por qué se apila. La explicación tentadora —"los contratos nuevos
cambian más"— **no se sostiene**: el keyset ordena `id_contrato` como texto, así
que `CO1.PCCNTR.1735835` va antes que `CO1.PCCNTR.285227`, y la cola del
recorrido son los ids de seis dígitos que empiezan por 9. Ni los más nuevos ni
los más viejos. Es una observación, no un hallazgo.

**Consecuencia práctica para el día que se paralelice:** las particiones por
rango de `fecha_de_firma` no van a tener carga de escritura pareja. El tiempo lo
domina la red, así que probablemente no importe — pero conviene no descubrirlo
con el DAG andando.

#### Lo que esto dejó ver sobre los tests

El test `test_el_punto_de_control_guarda_el_cursor` **pasaba, y afirmaba el
defecto**: escribía una línea, llamaba al punto de control y exigía que el
manifiesto ya tuviera el cursor, con la línea todavía en el buffer.

O sea que el defecto estaba **cubierto** por un test, no descubierto por falta
de cobertura. Es la advertencia de `conftest.py` en su forma más pura —los
tests se escriben desde la expectativa— aplicada esta vez no a los dobles de la
fuente sino a los del propio diseño. Conviene releer los demás con esa sospecha
puesta, y no solo con la de "¿falta cobertura?".

Lo reemplazan seis tests que fallan contra el código viejo y pasan contra el
nuevo, incluido el de la muerte dura.


---

## El primer barrido completo — 23 de agosto de 2026

Lo que se midió la primera vez que el flujo 3 corrió entero contra la fuente.
Reemplaza estimaciones, así que conviene tenerlo junto.

| | Estimado | **Medido** |
|---|---|---|
| Contratos vivos | 2.825.685 | **2.835.895** |
| Páginas de 5.000 | ~566 | **568** |
| Tiempo del barrido | ~20 min | **39 min 46 s** |
| Segundos por página | — | **~4,1** |
| Volcado del índice | 13,9 s | **55,7 s** |
| Comprimido por fila | 63 B | **324 B** |
| La partición en disco | ~140 MB | **916 MB** |

### Lo que esto confirma

**D3 funciona entre días distintos, no solo dentro de una corrida.** De las
11.449 filas que ya estaban en el índice del día anterior, se descartaron las
11.449. Bytes idénticos con otra `fecha_extraccion`, o sea que los metadatos
están efectivamente fuera del hash (I1) y la canonicalización es estable en el
tiempo. Es una comprobación que la fase 3 de `verificar_carga_raw.py` no puede
hacer, porque corre las dos veces el mismo día.

**El barrido dura cuarenta minutos.** Se dijo que "entra en la ventana nocturna,
arrancando después de las 04:41 COT (H24)". ⚠ **Esa frase no se sostiene: 04:41
no es un horario.** Son tres regeneraciones fechadas —04:22, 04:41 y 04:06 COT—
moviéndose en una ventana de 35 minutos, y 04:41 es la más tardía de las tres, no
un horario publicado. Nada se puede programar contra ese número. Lo que la
medición dice es cuánto dura el barrido, no cuándo cabe.

---

## La segunda corrida — 25 de agosto de 2026

La primera vez que el flujo 3 corrió sobre un índice ya poblado. Es la corrida
que convierte la deduplicación de una propiedad demostrada en una propiedad
medida.

**Su muestra, que es parte de la medición:** corrida completa sin reanudar, con
los flujos 1 y 2 sin correr antes para no contaminar el índice.

**Los dos extremos del intervalo, con lo que se sabe de cada uno:**

| Extremo | Corte de la fuente | Cómo se sabe |
|---|---|---|
| Derecho | `2026-08-25T09:05:54.277Z` | **Fechado al milisegundo.** Recuperado hacia atrás: la fuente quedó congelada en ese valor desde entonces, comprobado el 26 y el 28, y la corrida arrancó de día, muy después de las 04:05 COT |
| Izquierdo | **desconocido** | Nadie consultó el `:updated_at` el 23. Ese corte ya no existe |

⚠ **Esta corrida estaba anotada como "intervalo de dos regeneraciones, 23 → 25,
cubriendo domingo y lunes". Esa anotación se retira.** Daba por sentado que la
fuente había regenerado el domingo 23, y no hay ninguna observación que lo
respalde; sí hay dos observaciones de días sin regeneración (ver *La cadencia de
la fuente no es diaria*). Si tampoco regeneró el 22 ni el 23, el barrido leyó el
corte del jueves 20 y el intervalo fue de cinco días.

**El ancho está entre 2 y 5 días y es irrecuperable.** Todo lo que se exprese
*por unidad de tiempo* a partir de esta corrida hereda esa indeterminación; lo
que se exprese *como razón sobre el intervalo* no.

| | Barrido inicial (23) | Segunda corrida (25) |
|---|---|---|
| Índice al arrancar | 18.746 | 2.843.192 |
| Recibidas | 2.835.895 en 568 págs | 2.840.337 en 569 págs |
| Conocidas | 11.449 | 2.834.320 |
| Escritas | 2.824.446 | **58.971** |
| Descarte global | 0,4% | **97,9%** |
| Descarte sobre las conocidas | 100,00% | **98,13%** |
| Tiempo | 39 min 46 s | **49 min 31 s** |
| Segundos por página | 4,20 | **5,22** · 5,00 el 28 |
| Volcado del índice | 55,7 s | **4,0 s** |
| En disco | 916 MB | **18 MB** |

Las dos tasas de descarte están juntas a propósito: la corrida del 23 muestra
por qué la global no sirve como señal —0,4% y 100% describen la misma corrida— y
es el argumento del arreglo del canario.

### Lo que confirma

**El índice cierra sin resto.** Al arrancar tenía 2.843.192, que se descompone
exacto en las 2.824.446 escritas el 23 más las 18.746 anteriores de los flujos 1
y 2 y de la partición de prueba `2020-01`. De esas 18.746, solo 11.449 estaban
en el universo vivo el 23.

**Existe un flujo de salida del universo vivo, y es de miles.** Se puede acotar
pero no fijar: **entre 1.575 y 8.872 contratos** dejaron de estar vivos en el
intervalo, que abarca entre 2 y 5 días. El rango es ancho porque `conocidos_al_inicio` es global y no se sabe
cuántos de esos 7.297 no-vivos entraron al universo a la vez. Es el primer dato
empírico sobre la pregunta abierta de si los estados terminales cambian, y no la
cierra.

⚠ **RETIRADO — el calce de los contratos nuevos con H3.** Esta sección decía:
*"6.017 en dos días son ~3.000 por día, contra los ~2.900 que H3 obtuvo de un
`GROUP BY` sobre `fecha_de_firma`. Dos caminos independientes al mismo número."*
Se cae por dos razones independientes, y conviene ver las dos porque son errores
distintos:

1. **El divisor no se conoce.** 6.017 sobre un intervalo de entre 2 y 5 días da
   entre ~1.200 y ~3.000 por día. El calce con 2.900 solo aparece si se elige el
   divisor 2, que era el supuesto.
2. **No son la misma población.** "Nuevo en el universo vivo" es *no estaba en el
   índice*, y un contrato puede entrar por cambio de estado sin haberse firmado
   ese día. H3 cuenta firmas. Los dos caminos no miden lo mismo, así que su
   coincidencia no confirma nada.

Es un caso de libro de la tercera regla: **un calce demasiado bueno es
sospechoso.** Se puede cerrar barato con un `GROUP BY` sobre `fecha_de_firma`
aplicado a lo que se escribió el 25, que además responde la pregunta abierta
sobre la distribución de la escritura.

**El ratio de compresión se sostiene fuera del barrido.** 320 bytes por fila en
una partición incremental, contra 324 en el barrido completo. Era una duda
razonable: que el ratio saliera de la mezcla particular de filas del barrido.

### Lo que empeoró, y hay que anotarlo

**El ritmo de la API: 5,22 s por página contra 4,20**, y 5,00 en la corrida del
28. Con tres muestras el rango es 4,20–5,22 y el promedio ~4,8. Un 24% más
lento, sobre
569 páginas. Con dos muestras, el margen del `schedule` del DAG no se puede
calcular con 4,1.

### Lo que sigue sin medirse

**El delta de veinticuatro horas, que puede no ser observable.** Lo de arriba
abarca entre 2 y 5 días, y no se divide por el ancho: el índice guarda un hash
por contrato, así que lo que cambió varias veces se escribió una. Todo lo que
sale de esta corrida —la tasa de cambio por día, el volumen anual, el factor de
deduplicación— son **cotas inferiores**.

Hasta acá se decía que el número limpio salía de "dos corridas en días
consecutivos hábiles". ⚠ **Eso presupone que la fuente produce cortes en días
consecutivos, y no hay una sola observación de que lo haga.** Los tres cortes
conocidos están separados por dos y por cinco días. Conviene separar dos cosas
que hasta ahora se usaban como sinónimos:

| | Qué mide | Para qué sirve |
|---|---|---|
| **Delta de una regeneración** | cuánto cambia entre dos cortes consecutivos de la fuente, sean del día que sean | el umbral del canario; es lo que el pipeline ve realmente |
| **Delta de veinticuatro horas** | cuánta actividad de negocio se acumula en un día | la proyección anual y el factor de deduplicación por día |

El primero se obtiene siempre que se corra en cada corte, y D10 garantiza que
venga con sus dos extremos fechados. El segundo exige que exista un par de
cortes separados por exactamente un día, cosa que no depende de nosotros.
**Mientras no exista ese par, las cifras por día y por año se enuncian como
rangos o no se enuncian.**

**Por qué una página tardó 28 segundos.** El 2026-08-22 una partición de dos
páginas tardó 55,6 s, y la repetición de esa misma partición 6,4 s. Los dos
barridos completos promediaron 4,20, 5,22 y 5,00 s. Se dijo "arranque en frío de
Socrata" y sigue siendo una hipótesis sin respaldo. Importa para el margen del
`schedule`: si el rango real va de 3 a 28 segundos por página, el peor caso son
cuatro horas.

**La distribución de la escritura a lo largo del recorrido.** Va de 0% en la
primera página a 48% en la 568. Documentado en I5; sin explicación.


---

## La tercera corrida — 28 de agosto de 2026, contra una fuente congelada

La fuente llevaba tres días sin regenerar (H34), así que se corrió el flujo 3
contra el **mismo corte que ya estaba en el índice**: `2026-08-25T09:05:54.277Z`,
idéntico al milisegundo. No es un delta. Es una prueba de determinismo con
intervalo cero, y es la primera corrida del proyecto donde **todo se anotó antes
de verlo**.

**Su muestra:** intervalo de ancho **cero** —mismo corte en los dos extremos,
fechado al milisegundo—, corrida completa sin reanudar, con los flujos 1 y 2 sin
correr antes.

| | Predicho | Real |
|---|---|---|
| recibidas · páginas | 2.840.337 · 569 | **idéntico** |
| escritas | 0 | **0** |
| descarte global / sobre conocidas | 100,0% / 100,00% | **idéntico** |
| trozos cerrados | 0 | **0** |
| `corte_al_terminar` | igual al inicial | **igual** |
| el canario | callado | **callado** |

Tiempo: **47 min 27 s**, o sea 5,00 s por página.

### Qué demuestra

**La canonicalización es determinista a tres días de distancia, sobre 2,84
millones de filas.** Es la confirmación más fuerte que tiene D3. Lo anterior eran
11.449 filas en el barrido del 23 y el 98,13% de la incremental; esto es el
universo entero, con la fuente byte a byte igual, y no se escribió ni una línea
de más. Cualquier dependencia del reloj, del orden de las claves o del entorno
se habría visto acá.

**El índice cerró exacto: 2.849.209.** Era la predicción documentada —2.843.192
al arrancar el 25, más 6.017 contratos nuevos— y confirma que nada lo tocó entre
las dos corridas. Era uno de los pendientes de antes de correr.

**El camino "cero cambios" de I5 corrió a escala real por primera vez.** El
manifiesto quedó con `trozos_cerrados: 0`, `lineas_totales: 0` y el cursor en
`CO1.PCCNTR.999803`: el cursor avanzó las 569 páginas **sin cerrar un solo
trozo**. Es exactamente la regla del buffer vacío. Con la otra regla —"se cerró
un trozo"— el cursor no habría avanzado nunca y la corrida habría quedado sin
punto de reanudación.

**Y da la cota superior que al canario le faltaba.** Con el 98,13% de un
intervalo de entre 2 y 5 días y el 100,00% de un intervalo nulo, el paso 1.7
tiene los dos extremos del rango en que se mueve una corrida sana.

### El canario callado es el defecto, no el alivio

Con descarte del 100% no llega al umbral de 0,5, así que no cantó. Estaba
anotado antes de correr y salió así. **Un canario que no puede cantar en la
dirección que importa es el defecto 4.1 mostrándose entero**: con cadencia
irregular, el 100,00% dejó de ser el caso perfecto y pasó a ser también la señal
de haber corrido contra un corte ya visto.

---

## La cadencia de la fuente no es diaria — comprobado el 28 de agosto de 2026

> **Pendiente de numerar como hallazgo en `00_inventario_fuentes.md`.** Se
> documenta acá porque D10 y D11 cuelgan de él, pero el identificador estable le
> corresponde al inventario y los identificadores no se inventan de a dos.

Todo el proyecto se escribió sobre la frase "la fuente se regenera cada noche".
Nadie la comprobó nunca. **Es falsa.**

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
**Ningún par de cortes consecutivos separados por un día**, en todo el registro.
Ninguna regeneración observada en fin de semana.

**Dos aclaraciones sobre la evidencia**, porque la calidad de cada fila es
distinta:

- La del **21** estaba en el registro desde el principio, en el inventario y en
  la FASE 3 de H23, leída como confirmación de H2 —que lo es— y nunca como
  evidencia sobre la cadencia. No es un dato nuevo: es un dato que estaba mal
  leído.
- La del **27** es deducción, no observación: como el corte vivo el 28 es el del
  25, no pudo haber habido uno del 27.

**No es una caída de la plataforma.** El control es el dataset hermano de
Adiciones (`cb9c-h8sn`), que escribe en continuo: el 26 tenía escrituras de esa
misma mañana, y el 28 a las 09:51:29Z también. La plataforma transaccional está
viva; lo que no corre es el ETL que regenera la vista publicada.

**H2 sale reforzado, no tocado.** `min = max` al milisegundo sobre 5,96M de
filas se observó el 18, el 21, el 26 y el 28. El reemplazo total no está en
discusión; lo que cambia es cada cuánto ocurre.

### Qué se cae y qué no

**No se toca:** la premisa del proyecto —cada regeneración destruye el estado
anterior, y que ocurra dos veces por semana en vez de siete no la debilita—, H2 y
los tres flujos, los datos ya escritos en raw, y **D8**. Esto último merece
subrayarse: `observado_desde` / `observado_hasta` ya había decidido no prometer
resolución diaria, y ya estaba escrito que la serie iba a tener huecos. La
cadencia irregular no rompe ese diseño; lo confirma por un camino que no se había
previsto.

**Se cae:** la palabra "noche" en todas las frases del proyecto —lo correcto es
"cada vez que se regenera"—, el delta de veinticuatro horas como objetivo
alcanzable a voluntad, y la resolución temporal que el producto final puede
prometer, que es la de la fuente y no la diaria.

### El supuesto de planificación que se adopta

**Se supone que hay al menos una regeneración por semana.** Es un supuesto para
poder avanzar, **no un dato**: el salto máximo observado es de cinco días y el
salto en curso es de tres. Se verifica con el registro de sondeo. Si un intervalo
pasa de siete días, hay que volver acá.

### El registro de sondeo

Una línea por día: fecha, hora COT y el valor de `max(:updated_at)`. Es lo único
que puede convertir el supuesto de arriba en un dato, y de él salen tres cosas
que hoy no se pueden fijar:

- El umbral de `freshness` de dbt. Los 48 h planeados **fallarían hoy sobre una
  fuente sana**.
- El margen del DAG, que además no se puede calcular con 4,1 s por página: hay
  tres muestras: 4,20 · 5,22 · 5,00.
- Si hay patrón de días hábiles, que las tres regeneraciones conocidas —martes,
  jueves, martes— insinúan y no alcanzan para afirmar.

---

## Restricciones que no se negocian

Salieron de las decisiones pero valen por sí solas: son las cuatro cosas que, si
alguien las invierte en un refactor, rompen el diseño en silencio.

### R1 — El flujo 3 no se puede reejecutar hacia atrás

*Corrige el punto 2 de la definición de terminado.*

Descubierto al decidir D2. Los flujos 1 y 2 preguntan por rangos de fechas de
negocio (`fecha_de_firma`, `ultima_actualizacion`): la fuente devuelve lo mismo
hoy que dentro de un mes, así que reprocesar una fecha pasada reconstruye esa
fecha.

**El flujo 3 no.** Pregunta "¿cómo están AHORA los contratos vivos?". Correrlo
hoy para la partición del 15 de agosto devuelve el estado de hoy, no el del 15.
Ese estado se destruyó — es la premisa entera del proyecto.

Entonces su idempotencia significa algo más chico, y hay que enunciarlo así:

> Reejecutar el flujo 3 **dentro de la misma ventana de estado de la fuente**
> produce el mismo resultado. Reejecutarlo sobre una fecha pasada no
> reconstruye esa fecha: produce una observación nueva con fecha vieja, que es
> **peor que no hacer nada** porque mete una mentira en raw.

**"La misma ventana de estado" dejó de ser una noción vaga.** Es exactamente
*el mismo valor de `min(:updated_at)`*, y desde D10 queda anotado en el
manifiesto. D11 es esa restricción hecha guardarraíl: el cargador se planta
antes de gastar cincuenta minutos en reescribir un corte ya ingerido.

**Consecuencias:**

- El reintento de Airflow para el flujo 3 tiene sentido dentro de la misma
 noche y no lo tiene tres días después.
- **Un `backfill` del flujo 3 sobre fechas pasadas no debe existir.** Es un
 `raise`, no una opción.
- El punto 2 de la definición de terminado —"puedo reprocesar cualquier rango
 histórico con un comando"— **aplica a los flujos 1 y 2, no al 3**. Hay que
 corregir esa redacción.

No es una limitación del diseño: es una propiedad de la fuente. Decirla
explícitamente es mejor que un backfill que parece funcionar y contamina.

### R2 — `fecha_extraccion` es el día COLOMBIANO, no el del reloj del sistema

**Encontrado al probar el orquestador, con el reloj puesto.**

`date.today` devuelve la fecha del sistema, y en un contenedor o en Airflow eso
suele ser UTC. Colombia es **UTC−5**, así que entre las 19:00 y la medianoche
hora local, UTC ya está en el día siguiente.

**Verificado en vivo, con el reloj puesto:**

```
ahora UTC: 2026-08-22 01:10 | Bogotá: 2026-08-21 20:10
```

Con `date.today`, esa misma corrida habría escrito en
`fecha_extraccion=2026-08-22` —partiendo el día de negocio en dos particiones—
y el guardarraíl de C5 habría **rechazado una carga legítima** diciendo que era
backfill.

#### Por qué la fecha de Colombia y no UTC

UTC es la convención estándar y no está mal. Pero acá produce el error **justo
cuando alguien corre el cargador a mano por la tarde-noche** —depurando,
rehaciendo algo, probando—, que es cuando menos va a sospechar de la fecha. Con
el DAG corriendo poco después de la regeneración de la madrugada (H24), las dos
convenciones coinciden y la diferencia no se ve nunca... hasta que se ve.

Y el día colombiano es además el que coincide con lo que un analista llamaría
"el corte del 21".

`ZoneInfo("America/Bogota")` está en la biblioteca estándar desde 3.9: cero
dependencias nuevas.

#### La regla: una sola definición de "hoy"

```python
ZONA = ZoneInfo("America/Bogota")

def hoy -> date:
 return datetime.now(ZONA).date
```

**No dos llamadas sueltas a `date.today` en lugares distintos**, que es lo que
había. El orquestador la usa para nombrar la partición y el guardarraíl de C5
para decidir si una corrida es backfill; si se calcularan con criterios
distintos, el guardarraíl rechazaría corridas legítimas **cinco horas al día**.

**Pendiente:** revisar si `flujos.py` o `paginacion.py` usan `date.today` o
`datetime.now` en algún lado. Si lo hacen, tienen que pasar a `hoy`.

### Observación sobre `flujos.py`

El docstring de `Flujo` dice que la etiqueta *"viaja con cada fila hasta la capa
raw"*, pero **el código no la agrega**: los tres flujos hacen
`yield from paginar(...)` y devuelven las filas tal como llegaron de la API.

No es un bug — es coherente con que el extractor no transforme nada — pero
define el punto de partida del cargador: **etiquetar es trabajo del cargador**.
Cuando la fila llega, es exactamente lo que devolvió Socrata, sin metadatos.


---

### R3 — El pipeline entero corre en ~3 GB de memoria

> La máquina de desarrollo es WSL2 con **3,8 GB** de RAM y 8 núcleos, y DuckDB
> se pone un techo de 3 GB sobre eso. Cualquier diseño que no quepa ahí no es
> un diseño para este proyecto.

**No es una anécdota del entorno: ya descartó un enfoque.** Al escribir el modelo
frontera de dbt, abrir las 67 columnas con `json_extract_string` —una llamada por
columna— agota la memoria y muere, porque parsea el mismo documento 67 veces por
fila. Declarar el `STRUCT` explícito desde `columnas.py` hace lo mismo sin
parsear, y pasa.

Medido el 28/08/2026, con 2,2 millones de filas y el límite escalado:

| Enfoque | Tiempo | Tabla | Memoria |
|---|---|---|---|
| `datos` como JSON, sin abrir | 46,6 s | 2.090 MB | pasa |
| 67 × `json_extract_string` | — | — | **muere** |
| **STRUCT explícito** | **42,3 s** | **224 MB** | **pasa** |

Confirmado después contra los datos reales: **1,2 GB en 57 s**, contra 4,3 GB en
154 s del primer intento. Tres veces y media más chico y casi tres veces más
rápido.

**Dónde vuelve a aparecer.** El SCD2 une 2,9 millones de filas contra sí mismas;
es la operación más pesada que le queda al proyecto y hay que diseñarla sabiendo
esto. Las palancas conocidas, en el orden en que conviene usarlas: declarar los
esquemas en vez de dejarlos inferir, bajar los hilos —cada uno mantiene su propio
juego de vectores—, `preserve_insertion_order=false` cuando el orden no signifique
nada, y `temp_directory` para volcar a disco antes de morir.

#### Segunda vez que R3 decide, y la más cara: el SCD2 pasó de 734 s a 52

`fct_contratos_snapshot` hacía `select *` y arrastraba las 73 columnas de
staging. Tardaba **734 segundos**, cinco veces más que `stg_contratos`.

El desglose, medido el 28/08/2026 sobre 2,9 millones de filas:

| Etapa | Costo |
|---|---|
| Construir la huella de 28 columnas | 3,6 s |
| Las dos ventanas (`lag` y `lead`) | 5,1 s |
| Escribir **11** columnas con ventana | 8,9 s |
| Escribir **73** columnas sin ventana | 109 s |
| El modelo completo | **734 s** |

**Toda la lógica sospechada suma nueve segundos: el 98,8% del tiempo era
escribir columnas anchas después de ordenar.** Y la relación no es lineal —seis
veces más columnas costaban ochenta veces más tiempo—, que es la firma del
volcado a disco cuando el ancho deja de entrar en memoria.

El arreglo fue dejar en el hecho solo las 28 columnas materiales más las llaves.
Resultado: **52 s**, catorce veces más rápido, y el snapshot pasó a tardar menos
que `stg_contratos`.

⚠ **El problema de rendimiento y el de modelado eran el mismo.** Una tabla de
hechos lleva llaves, fechas y medidas; los atributos descriptivos van en las
dimensiones. Eso ya estaba escrito en el modelo dimensional, y el `select *` lo
violaba duplicando 1,2 GB en disco sin agregar información. **R3 empujó hacia el
diseño correcto en vez de alejar de él**, igual que había hecho con el modelo
frontera.

**Y no se negocia subiendo la memoria.** Un proyecto que necesita 16 GB para
procesar 916 MB tiene un problema de diseño, y se nota. Que quepa en 3 GB es una
propiedad del trabajo, no una limitación heredada: esta restricción ya produjo un
modelo nueve veces más chico que el que se iba a escribir sin ella.

---

## Alternativas descartadas, para no reabrirlas

### Opciones que estaban sobre la mesa para D1 (histórico de la decisión)

- **A — Raw fiel, comparación en SQL después de staging.** Raw auditable de
 verdad; un bug de normalización se arregla con `dbt run`. Costo: la
 clasificación de `columnas.py` hay que expresarla en SQL, o generarla.
- **B — Raw canónico, comparación en Python.** `columnas.py` sigue siendo la
 única fuente de verdad y se testea con pytest. Costo: raw deja de ser
 fiel; un bug de casteo obliga a re-descargar, y comparar 2,8M filas por
 noche en Python es lento.
- **C — Dos subcapas, `raw` fiel y `canonico` comparable.** El relleno H13
 tiene lugar propio y testeable. Costo: dos escrituras y el doble de disco.

El eje real no es el disco: es **dónde vive `columnas.py` en el linaje**. En
A y C es un documento que hay que traducir; en B es código ejecutable en el
camino crítico.

**La cuarta opción no apareció.** La FASE 3 corrió (H23): los hermanos sí
tienen watermark propio, pero eso **no abre una opción de arquitectura nueva**
—abre una restricción sobre las tres existentes—. La capa raw tendría que
alojar dos patrones de ingesta incompatibles, y eso mueve peso en contra de B,
no a favor de una D. Ver H23 en `02_ecosistema_secop.md`.

### Restricciones ya identificadas para D2 y D3

- **Volumen.** El flujo 3 barre ~2,8M contratos vivos por noche. Raw
 append-only con foto completa son ~1.000M filas/año — el mismo orden que
 §4 del modelo dimensional descartó para el snapshot denso diario. Los
 flujos 1 y 2 son ~5.000 filas/día, irrelevantes. **El problema es todo del
 flujo 3.**
- **`urlproceso` es un objeto anidado** y rompe la conversión a Parquet
 (H6). "Raw fiel" y "raw en Parquet" no conviven gratis: o struct, o JSON
 como string, o aplanar — y aplanar ya es normalizar. El raw fiel más
 barato probablemente sea **JSONL comprimido**, no Parquet.
- **Raw no se filtra por negocio.** H3 ya dejó los años previos a 2020 en
 raw. Coherente con la decisión del extractor.

---