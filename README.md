# SECOP: reconstruir lo que el Estado colombiano borra

[![CI](https://github.com/cristian23cor/secop-analytics-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/cristian23cor/secop-analytics-platform/actions/workflows/ci.yml)

Colombia publica todos sus contratos públicos como datos abiertos. El conjunto
tiene casi seis millones de filas, se puede descargar sin registrarse y está
razonablemente completo.

Tiene un problema: cada vez que se regenera, se sobrescribe entero.

No es que borren contratos. Lo que se pierde es el pasado de cada uno. Si un
contrato de mil millones se adiciona a mil quinientos, la fila cambia y la
anterior deja de existir. Nadie puede consultar cuánto valía antes, ni cuánto se
había pagado en marzo, ni cuántas veces le corrieron el plazo. Esa historia no
está archivada en ningún lado: se destruye en cada regeneración y no hay copia.

Este proyecto guarda una foto de cada corte y reconstruye la serie.

**El tablero está en <https://cristian23cor.github.io/secop-analytics-platform/>.** Se genera desde el
modelo con `scripts/generar_tablero.py`, así que se rehace después de cada ingesta
y no se edita a mano.

---

## Por qué importa

Hay siete preguntas que un vendedor le hace al mercado público antes de decidir
si le vende al Estado. Cinco se responden con los datos tal como vienen: quién
compra mi categoría, quién es el proveedor dominante, cuánto vale un contrato
típico, cuándo se abren las licitaciones, cuánto se adjudica a dedo.

Las otras dos no:

> **6.** ¿Qué entidades y categorías extienden sistemáticamente el plazo, y
> cuántos días?
>
> **7.** ¿Cuánto cuesta esa extensión en pesos?

Para responderlas hace falta comparar el contrato de hoy contra el de antes, y
"el de antes" no existe en ninguna fuente pública. Busqué la serie en todo el
ecosistema SECOP antes de construirla:

- El dataset oficial de modificaciones tiene una fila por adición y **ninguna
  columna de valor**. El monto está escrito en prosa, en letras y en números,
  mezclado con la prórroga de plazo en la misma frase.
- Su única fecha viene corrupta, y de una forma que ningún sistema detecta
  (abajo, en los hallazgos).
- La publicación en formato OCDS, que sí modelaba enmiendas, se apagó en abril
  de 2022.

O sea que el Estado publica el evento sin la medida. Esta plataforma reconstruye
la medida sin el evento, comparando fotos.

El tablero oficial de la agencia, que son unas veinte visualizaciones en Power
BI, cubre las cinco primeras preguntas y no toca las dos últimas.

---

## Qué hace

Tres flujos de ingesta escriben archivos comprimidos en disco, y dbt los
transforma en un modelo dimensional.

La fuente no tiene ninguna columna que diga cuándo cambió cada fila, así que no
hay carga incremental posible en el sentido habitual. Hay tres mecanismos de
cambio distintos y solo dos dejan rastro:

| Qué cambió | Cómo se detecta |
|---|---|
| Contrato nuevo | ventana sobre `fecha_de_firma` |
| Evento contractual: modificación, cesión, cierre | ventana sobre `ultima_actualizacion` |
| Avance de pagos y facturación | **ninguna columna lo registra** |

El tercero afecta a 735.809 contratos y es el que obliga a barrer los 2,8
millones de contratos vivos completos en cada corte, comparar y quedarse con lo
que cambió.

Ese barrido tarda unos cincuenta minutos y devuelve 8 GB de JSON. En disco quedan
18 MB, porque el cargador calcula un hash de cada fila antes de escribirla y
descarta la que ya vio idéntica. Sobre la última corrida medida, el 98,13% de las
filas conocidas se descartó.

Después dbt arma el modelo:

```
datos/raw/*.jsonl.gz
  raw_observaciones          2.902.163 observaciones, 67 columnas como texto
    stg_contratos            tipos, centinelas a nulo, urlproceso aplanado
      dim_entidad            5.168 filas, con historia
      dim_proveedor          930.071, con historia
      dim_modalidad          232
      dim_geografia          958
      fct_contratos_snapshot 2.881.640 versiones (SCD tipo 2)
        fct_contratos           2.849.209 contratos
          dim_categoria         11.231 codigos UNSPSC
        int_cambios_por_columna 88.395 cambios, con su delta
          mart_extension_de_plazo   las preguntas 6 y 7
```

La construcción completa son once modelos y tarda siete minutos y medio en un
portátil, con 46 tests de dbt y 215 de pytest. Los mismos modelos corren en
Snowflake en 79 segundos.

---

## Cómo correrlo

Hace falta Python 3.12 y [uv](https://docs.astral.sh/uv/). Nada más: los archivos
de la capa cruda se abren con `gzip.open` de la biblioteca estándar, sin instalar
un compresor de terceros.

```bash
uv sync

# Bajar el corte vivo de la fuente. Tarda ~50 minutos.
uv run python scripts/cargar_raw.py --flujo vivos

# Construir el modelo. ~7 minutos.
cd dbt && uv run dbt build --profiles-dir .
```

El cargador consulta el corte de la fuente antes de empezar y se planta si ya
ingirió ese mismo estado, así que correrlo dos veces el mismo día no cuesta nada
ni escribe una partición vacía. Devuelve código 4 en ese caso, distinto del 1 y
del 2, para que un orquestador pueda separar "no había nada nuevo" de "algo se
rompió".

Los otros dos flujos, que son ventanas de un día y tardan segundos:

```bash
uv run python scripts/cargar_raw.py --flujo nuevos  --desde 2026-08-20 --hasta 2026-08-21
uv run python scripts/cargar_raw.py --flujo eventos --desde 2026-08-20 --hasta 2026-08-21
```

---

## Lo que encontramos

Los hallazgos valen más que el volumen. Cualquiera procesa millones de filas;
encontrar defectos que la fuente no confiesa es lo que demuestra criterio. Todos
están documentados con la consulta que los reproduce, en `exploration/`.

### Un dataset oficial con las fechas truncadas al primer dígito

El registro de modificaciones contractuales tiene 26,5 millones de filas y una
columna de fecha declarada como fecha, que parsea sin error. En ninguna de esas
26,5 millones de filas el día es mayor que 9. Tampoco el mes.

La fecha está truncada al primer dígito significativo: el 21 de diciembre se
guardó como 1 de enero, el 15 de julio como 1 de julio. Se confirmó de dos
maneras independientes, y la segunda es la que prueba el mecanismo y no solo el
síntoma. Si truncás el día, el balde "1" absorbe once días reales (el 1 y del 10
al 19), el "2" otros once, el "3" apenas tres, y del "4" al "9" uno cada uno.
Contando filas por balde, el 1 vale 12,6 días, el 2 vale 14,0 y el 3 vale 3,0.
La hipótesis predice 11, 10,9 y 2,5. Ninguna lectura alternativa produce esa
distribución.

El daño no es parejo, y ahí está la parte útil: el año sobrevive siempre, el mes
en el 79% de las filas y la fecha entera en el 13,6%. Como los meses solo llegan
a 12, apenas tres colapsan; los días llegan a 31 y colapsan veintidós. Se sabe
fila por fila de cuáles fiarse.

### Dos datasets publican las mismas filas con las etiquetas invertidas

Comparando conteos anuales entre el registro de modificaciones y el de
suspensiones aparecieron catorce números idénticos cruzados. No era coincidencia:
son las mismas filas. Uno de los dos tiene las etiquetas dadas vuelta, y se puede
saber cuál leyendo la descripción en texto libre. Ocho de ocho filas verificadas
dicen "se suspende" y están clasificadas como reactivación.

Ninguna de las dos fichas declara que uno sea vista del otro.

### La fuente declara frecuencia diaria y no la cumple

Esta es la que más costó, porque la evidencia estaba escrita y nadie la había
leído.

La ficha oficial dice que el conjunto se actualiza a diario. En diez días
observados hubo tres regeneraciones y siete días sin ninguna. Los saltos entre
cortes conocidos son de dos y de cinco días, y el que está en curso lleva siete:
el 1 de septiembre de 2026 seguía publicado el corte del 25 de agosto. No hay un
solo par de cortes separados por exactamente un día.

Y no es una caída de la plataforma. Un conjunto oficial hermano, que escribe en
continuo, registró escrituras esa misma mañana. Lo que está detenido es el
proceso que rehace la vista publicada.

Se detecta con una petición de dos segundos, porque todas las filas comparten el
mismo sello de tiempo. Y para descartar que fuera una caída de la plataforma
sirve un dataset hermano, que escribe en continuo: mientras el principal llevaba
tres días congelado, el hermano registraba escrituras de esa misma mañana. Son
dos sistemas y solo uno estaba detenido.

La consecuencia de ingeniería es concreta: el pipeline no puede dispararse por
calendario. Ningún horario acierta contra un evento que a veces no ocurre. Se
dispara por el estado de la fuente.

### Seis entidades cambiaron de clasificación y ya no queda rastro

Entre el barrido del 23 de agosto y el del 25, 20.675 contratos cambiaron la
clasificación de su entidad. Son seis entidades, y el cambio va en las dos
direcciones: una unidad del SENA pasó a centralizada mientras otra del mismo SENA
pasó a descentralizada, el mismo día.

Quien consulte SECOP hoy no puede saber que eso pasó. La fuente se sobrescribió y
solo dice el valor nuevo. El evento existe únicamente porque se guardaron las dos
fotos y se compararon, y es la premisa del proyecto demostrada con un caso real
en vez de con un argumento.

### Siete contratos por encima del presupuesto del Estado

El Presupuesto General de la Nación de 2026 es de 546,9 billones de pesos. Siete
contratos declaran valores por encima de esa cifra. El mayor, 12.858 billones, la
supera veintitrés veces y pertenece a un instituto municipal de deportes.

Los siete castean limpio a `decimal(20,2)`: para el sistema de tipos son válidos.
En 2,9 millones de observaciones, el tipado atrapa **un** valor mal formado y toda
la demás basura pasa. Esta clase de error solo la detecta una regla de negocio con
un techo defendible, y el techo se elige contra una cifra pública, no a ojo.

El dinero no se movió: seis de los siete declaran cero pagado. Son errores de
digitación publicados sin ningún filtro. La afirmación que se sostiene es que la
fuente oficial no valida sus propios valores.

### El 74% de la contratación pública es directa

Sumando contratación directa, directa con ofertas y régimen especial, la
contratación sin licitación abierta supera el 90% de los contratos. Sale de una
dimensión de 232 filas.

### El 21% de los contratos no tiene ciudad, y el dato no está escondido

Al construir la dimensión geográfica parecía que la columna `localizaci_n`
(que tiene cero nulos) podía rellenar los 611.751 contratos sin ciudad. No puede:
de esos 611.751 permite recuperar 2.875, el 0,47%. Los demás traen "No Definido"
adentro de la cadena, así que la columna miente sus cero nulos.

Y tiene una trampa aparte. Un departamento colombiano se llama *San Andrés,
Providencia y Santa Catalina*, con comas en el nombre, así que 17.085 filas traen
cuatro campos donde el resto trae tres. Un parseo por comas habría inventado un
departamento llamado "Providencia y Santa Catalina" con 13.102 contratos, sin que
nada fallara.

La conclusión es que la fuente no publica ese dato. Un análisis por municipio deja
fuera la quinta parte de la contratación, y eso hay que decirlo en el tablero en
lugar de compensarlo.

### El 38,8% de lo que la fuente marca como cambio no es un cambio

Entre dos cortes, la fuente publicó 52.954 contratos como modificados. De esos,
solo 32.431 cambiaron algo del contrato. Los otros 20.523 cambiaron el registro y
no el contrato, y casi todos por un solo evento administrativo.

Es la razón por la que el modelo clasifica las 85 columnas en materiales,
cosméticas e imposibles antes de decidir si genera una versión. Sin esa
clasificación, la serie temporal tendría un 60% más de filas y ninguna
información adicional.

---

## Decisiones que vale la pena mirar

El razonamiento completo de cada una, con las alternativas que se descartaron,
está en `exploration/03_decisiones_capa_raw.md`. Acá van las que explican la forma
del proyecto.

**Entre un error que sobra y uno que falta, se elige el que sobra.** Resolvió seis
de las ocho decisiones de arquitectura. La deduplicación compara bytes crudos, así
que puede guardar una fila de más si la fuente cambia `"1000"` por `"1000.00"`;
nunca puede descartar un cambio real. El cargador escribe el archivo antes de
tocar el índice de hashes, así que una muerte a mitad deja un duplicado en disco y
no una fila perdida. Cuando se puede elegir la dirección del error, se elige la
que se puede corregir después.

**La capa cruda guarda lo que devolvió la API sin tocar un carácter.** La
tentación de normalizar al escribir es fuerte y es un error caro: si la limpieza
tiene un defecto (y esta fuente ya demostró que los tiene) con datos crudos se
corrige el código y se reprocesa. Con datos ya limpiados queda un agujero
permanente, porque la fuente que los originó se sobrescribió.

**La lista de columnas no se documenta, se genera.** La clasificación de las 85
columnas vive en un módulo de Python. Un script escribe desde ahí el macro que usa
dbt, y otro falla si los dos archivos difieren en un byte. No es documentación que
haya que mantener sincronizada con dbt: es la fuente desde la cual dbt se genera.

**Un solo modelo sabe de qué motor se trata.** Los archivos se leen en un único
modelo frontera, que se ramifica según el objetivo: DuckDB los lee del disco,
Snowflake de un stage interno. La proyección de las 67 columnas es la misma para
las dos ramas, así que las columnas y su orden coinciden por construcción y no
porque alguien las mantenga a la par.

Eso salió a medias la primera vez, y la corrección vale más que el acierto. "Un
único modelo toca los archivos" no implica "un único modelo habla dialecto": la
capa de limpieza aplanaba una columna anidada con funciones que solo existen en
DuckDB, y nadie lo había notado en tres días de escribir SQL. Lo destapó un grep
por funciones sospechosas sobre los once modelos, que es una comprobación de
treinta segundos. Las tres diferencias de dialecto viven ahora en macros y los
modelos volvieron a ser agnósticos.

**El SCD tipo 2 está escrito a mano.** La funcionalidad nativa de dbt no sirve
acá, por dos razones. Compara contra la tabla destino en vez de contra los
archivos, lo que impediría corregir el pasado; y no tiene forma de expresar una
clasificación de tres vías, o sea de decirle "estas 32 columnas cambian sin
generar versión".

**Las fechas se llaman `observado_desde` y `observado_hasta`.** La plataforma no
sabe cuándo cambió el contrato. Sabe cuándo el cambio se volvió visible. Un pago
detectado el 25 pudo ocurrir cualquier día desde la observación anterior, y con la
fuente saltando días ese hueco puede ser de una semana. Un nombre que promete
menos vale más que la convención.

**El disparador es el corte de la fuente, no el reloj.** El cargador pregunta qué
estado está vivo antes de bajar una sola página y se planta si ya lo ingirió. La
lógica vive en el cargador y no en el orquestador, para que correr a mano no la
pierda.

---

## Lo que no hace, y por qué

**No se puede backfillear la historia.** No existe en ninguna fuente pública. La
tabla de versiones arranca vacía y madura con el tiempo. Los dos primeros flujos
sí admiten reprocesar el pasado, pero devuelven una sola observación por contrato
(la de hoy, filtrada por una fecha vieja) y no una serie.

**La serie tiene la resolución de la fuente, no la diaria.** Entre dos
regeneraciones separadas por siete días, dos modificaciones del mismo contrato son
indistinguibles: llegan juntas en el mismo corte. El diseño lo aguanta; lo que no
se puede es inventar los días que faltan.

**Los deltas solo son válidos para contratos observados desde su firma.** Esta es
la limitación más importante y la más fácil de esconder. Un contrato firmado en
2021 al que le vimos una sola versión no es un contrato sin modificaciones: es uno
cuya historia empieza el día que encendimos el pipeline, con sus adiciones
anteriores ya incorporadas en la primera foto.

Hoy eso deja poquísimo. Con un margen de treinta días entre la firma y la primera
observación, la pregunta 7 se apoya en 39 contratos repartidos en 29 entidades.
Con esa base la palabra "sistemáticamente" no se sostiene. Sin la restricción hay
1.925 contratos, pero el número es cota inferior.

El mart no elige por vos: lleva las dos poblaciones separadas por grano, cada una
con su tamaño al lado, y la población medible crece sola con cada corte ingerido.

**El análisis se restringe a 2020 en adelante.** Antes de ese año la curva de
volumen mide la adopción de la plataforma, no el gasto público: se pasó de diez
contratos en 2015 a más de un millón en 2025. Cualquier comparación interanual que
cruce 2020 es inválida.

**`orden`, `rama` y `sector` no son confiables.** Un hospital departamental figura
como "Nacional" y una empresa social del Estado como "Corporación Autónoma". El
diccionario oficial define esos campos de forma circular. Entran como atributos
con la advertencia escrita, y no se construye lógica de negocio encima.

**Los datos personales quedan fuera desde la extracción.** El conjunto expone
cédulas, nombres completos, género y domicilio residencial del representante
legal, del ordenador del gasto y del supervisor. Son datos legalmente abiertos,
pero republicarlos en un tablero es una decisión distinta a consultarlos. Son 18
columnas y el filtro corre en la petición a la API, no después: la exclusión más
fácil de auditar es la que hace que el dato no viaje.

---

## Estado

Funciona de punta a punta, con estas partes hechas y estas no.

Hecho: los tres flujos de ingesta, la deduplicación por hash, el índice
reconstruible, el registro de procedencia de cada partición, el guardarraíl del
corte, las tres capas de dbt, cinco dimensiones, el SCD2, la capa de cambios con
sus deltas, el mart de las preguntas 6 y 7, y el porte a Snowflake.

El porte está verificado, no solo conectado. Los mismos once modelos corren en los
dos motores y devuelven exactamente lo mismo: cada conteo, cada suma y los dos
avisos de reglas de negocio con sus mismos números, hasta el último peso de los
121.078.133.897 adicionados. En Snowflake la construcción completa tarda 79
segundos contra 344 en el portátil, y esa diferencia dice más del techo de memoria
de la máquina local que del diseño.

El orquestador está escrito y probado: un DAG de Airflow que no se dispara por
reloj sino por el estado de la fuente, porque ningún horario acierta contra un
evento que a veces no ocurre. Cinco tests cuidan que sus decisiones sigan tomadas.

Falta levantarlo en algún lado. Ningún modelo es incremental todavía: la
construcción completa se rehace entera cada vez.

Las preguntas abiertas están numeradas en `exploration/`, con lo que haría falta
para cerrar cada una. Algunas necesitan datos externos que todavía no conseguí: el
catálogo UNSPSC para traducir códigos de categoría a nombres legibles, y el
calendario de festivos colombianos.

---

## El repositorio

```
exploration/                    Cuatro documentos con el razonamiento completo
  00_inventario_fuentes.md        La fuente principal, sus hallazgos, el glosario
  01_modelo_dimensional.md        El modelo, las reglas de negocio, las preguntas abiertas
  02_ecosistema_secop.md          Los datasets hermanos y por qué no entran
  cadencia.csv              Un dia por linea. El unico dato no recuperable
  03_decisiones_capa_raw.md       Cada decisión con su alternativa descartada

src/secop_analytics/
  columnas.py       Qué se descarga y cómo se compara. Fuente de verdad del esquema
  paginacion.py     Lo único que conoce la API. Paginación por keyset
  flujos.py         Los tres flujos de ingesta
  hashing.py        Canonicalización y hash
  indice.py         Índice de hashes en DuckDB. Derivado, no autoritativo
  escritura.py      Trozos comprimidos, manifiesto, marca de completitud

scripts/
  cargar_raw.py                    Orquestador. Punto de entrada
  generar_columnas_dbt.py          Genera el macro de dbt desde columnas.py
  verificar_columnas_dbt.py        Falla si los dos se separaron
  verificar_tests_del_snapshot.py  Siembra defectos y comprueba que los tests los vean
  verificar_extraccion.py          Contra la API real
  verificar_carga_raw.py           Contra la API real, cuatro fases
  medir_particiones.py             Distribución del universo vivo
  medir_rn1.py                     Las fuentes de financiación contra raw
  verificar_incremental.py         Lo incremental da lo mismo que reconstruir
  sondear.py                       Que corte esta publicado. Lo corre Actions
  subir_raw_a_snowflake.py         Sube la capa cruda a un stage, conservando la ruta
  generar_raw_sintetico.py         Datos chicos y sembrados, para que CI pueda correr dbt
  generar_tablero.py               Escribe docs/index.html desde el modelo

dbt/
  models/staging/        El modelo frontera y la limpieza
  models/intermediate/   Qué columna cambió en cada versión, con su delta
  models/marts/          Hechos, dimensiones y el mart
  macros/                El generado desde columnas.py, y los de unión y limpieza
  tests/                 Reglas de negocio e invariantes del modelo

dags/
  secop_ingesta.py       El DAG. Se dispara por el corte de la fuente, no por reloj

docs/
  index.html             El tablero. Lo publica GitHub Pages; lo escribe el generador

.github/workflows/
  ci.yml                 Seis comprobaciones, ninguna toca la red
  sondeo.yml             Cada tres horas: pregunta por el corte y avisa

tests/                   215 tests. Los 5 del DAG se saltan si Airflow no está
```

---

## Sobre la verificación

Dos costumbres que este proyecto adoptó por haberse equivocado, y que explican
varios de los archivos de arriba.

**Una medición sin su muestra anotada al lado no es una medición.** Cinco cifras
documentadas como medidas resultaron falsas, todas por lo mismo: tomadas sobre
muestras chicas y después citadas como hechos. Ahora cada número lleva escrito
sobre qué se midió, y las cifras retiradas quedan tachadas con el motivo en vez de
borrarse.

**Un test que solo se ve dar cero no demuestra que sepa dar otra cosa.** Un test
del punto de control pasaba y afirmaba el defecto que existía. Por eso los tests
del modelo dimensional se verifican contra tablas corrompidas a propósito:
`verificar_tests_del_snapshot.py` siembra veintidós defectos, comprueba que los
veintidós salgan con el motivo correcto, y que los casos sanos no salgan de
ninguno.

La misma costumbre se aplicó a los reintentos de la ingesta y al DAG: se rompió la
política a propósito seis veces cada uno, y las doce mutaciones fueron detectadas.

**Y todo eso corre solo, en cada push.** Son cinco comprobaciones y ninguna toca la
red, que no es casualidad: lo que necesita la API real se dejó fuera a propósito,
porque un test que falla porque el portal del Estado está caído enseña a ignorar
los tests.

| | |
|---|---|
| Los 198 tests de la capa de ingesta | con dobles de la API |
| `columnas.py` contra el macro de dbt | byte a byte, para que el esquema no se duplique |
| Que los tests del modelo detecten sus defectos | 22 sembrados, 22 detectados |
| Los once modelos y sus 46 tests | contra una capa cruda sintética generada al vuelo |
| Que el DAG importe y conserve sus decisiones | `catchup`, una corrida a la vez, el código 4 |

La capa cruda de CI se genera y no se commitea: son 898 MB los reales, y el
repositorio guarda código. `generar_raw_sintetico.py` escribe 620 observaciones con
los casos sembrados a propósito, incluidos cuarenta contratos cuyo único cambio es
cosmético, para que el filtro que decide qué merece una versión se ejercite de
verdad.

---

## Licencia y fuente

Los datos son públicos, publicados por la Agencia Nacional de Contratación
Pública: Colombia Compra Eficiente bajo la Ley 1712 de 2014, y se consultan
desde
`datos.gov.co`. El código es mío y el análisis también, incluidos los errores.
