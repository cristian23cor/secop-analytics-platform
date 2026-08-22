# Decisiones de diseño de la capa raw

> El razonamiento completo detrás de cada decisión, con las alternativas que se
> descartaron y por qué. `01_modelo_dimensional.md` dice **qué** se decidió;
> acá está el **por qué**.
>
> **Cómo leerlo:** las decisiones tienen identificadores estables. **D1 a D8**
> son de arquitectura —dónde vive cada cosa— y se tomaron antes de escribir
> código. **I1 a I4** son de implementación y salieron al escribir el cargador.
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

**El hilo que las une.** Seis de las ocho se resolvieron con el mismo criterio:
*entre un error que sobra y uno que falta, elegir el que sobra.* Aparece en la
deduplicación por bytes (D3), en el orden escribir-antes-que-índice (D2), en la
decisión de no bloquear la carga (D7) y en el rechazo del hash (D6). Es el
mismo criterio del `$select` explícito .

**Lo que queda por construir** (ya sin decisiones pendientes):

1. El cargador con deduplicación por bytes, trozos y manifiesto.
2. El índice de hashes en DuckDB, con su reconstrucción desde raw.
3. El generador `columnas.py` → dbt, con el test de deriva en CI.
4. `stg_contratos`: relleno H13, centinelas, tipos, `urlproceso`, `noticeUID`.
5. El modelo SCD2 propio, incremental, con `motivo_del_cambio` y
 `motivo_de_cierre`.
6. La tabla de alertas de imposibles.


---

## Arquitectura: D1 a D8

###  D1 DECIDIDA — Opción A (raw fiel, comparación en SQL después de staging)


Raw guarda lo que devolvió la API sin tocar un carácter. El relleno (H13), los
centinelas, los tipos y `urlproceso` se resuelven en `staging` (dbt). La
comparación corre en SQL, sobre valores ya normalizados.

**Razón principal, y es una sola:** la fuente se sobrescribe cada noche, así
que lo que se guarde mal no se puede volver a pedir. Y la probabilidad de que
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
raw/flujo=3/fecha_extraccion=2026-08-21/parte-0001.jsonl.zst
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
donde el stream de `zstd` se cierra, así que nunca queda un archivo a medio
comprimir. Eso es exactamente lo que descarta la opción 2 (apéndice con
cursor): un `.zst` cortado a la mitad tiene la cola corrupta y el archivo
entero se vuelve sospechoso — habría que dejar raw sin comprimir y multiplicar
el volumen por diez.

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

**Volumen resultante:** ~12 MB comprimidos por noche, **~5 GB/año**. Cincuenta
veces menos, con el histórico completo intacto. La primera corrida sí escribe
los 2,8M (~700 MB, una sola vez).

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
 ~100 MB en DuckDB.

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
*materialización* no recalcula diez años cada noche. Patrón estándar de dbt.

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


---

## Implementación: I1 a I4

Las ocho decisiones de diseño (D1–D8) no cubren estas. Se numeran I1–I4.

| # | Decisión | Estado |
|---|---|---|
| I1 | Cómo se representa la fila para hashear |  **JSON canónico, los mismos bytes que se escriben** |
| I2 | Qué algoritmo de hash | abierta |
| I3 | Dónde vive el manifiesto | abierta |
| I4 | Cómo se estructura el módulo | abierta |

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
raw/flujo=3/fecha_extraccion=2026-08-21/
 _manifiesto.json ← progreso: cursor, trozos cerrados, algoritmo
 parte-0001.jsonl.zst
 parte-0002.jsonl.zst
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
| **Índice completo en un dict** | **185 MB** | **2,1 s** (una vez) |
| Consulta por lotes de 5.000 | Constante | **95,4 s** (169 ms × 566) |

La opción "prudente" es **47× más lenta** y protege 185 MB que no hacía falta
proteger. Proponerla por instinto habría metido minuto y medio de latencia por
noche a cambio de nada.

**Decisión:** cargar el índice completo al arrancar la partición, acumular los
hashes nuevos en un dict aparte, escribir la tanda al cerrar.

**Escritura final medida:** 0,2 s para los ~30.000 que cambian en una noche
típica. Los 13,9 s del caso extremo (cambia todo) solo ocurren la primera vez.

 **Vigilar si el dataset crece.** Cuatro particiones en paralelo son cuatro
copias del índice: **740 MB**. Manejable hoy; si el dataset se duplica, hay que
volver a mirar los lotes.

#### Dos cosas que la medición dejó ver

**La inserción inicial tarda 20,6 s** y ocurre en la primera corrida, con el
índice vacío. El mensaje de progreso tiene que anunciarlo o va a parecer
colgado — lección .

**El archivo del índice pesa 171 MB, no 90.** La estimación de I2 no contaba el
índice de la llave primaria. Irrelevante frente a los ~5 GB anuales de raw, pero
el número correcto es 171.


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
el DAG corriendo poco después de la regeneración de las 04:41 COT (H24), las dos
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

**Una cuarta opción puede aparecer** según el resultado de la FASE 3: si
Adiciones y Suspensiones son append-only, hay un watermark real disponible y
cambia el planteo.

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