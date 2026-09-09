# Inventario de fuentes: SECOP

Registro de la evaluación de las fuentes candidatas. Cada hallazgo va con la
consulta que lo demuestra, para que cualquiera pueda repetirlo.

Este documento cubre la fuente principal, `jbjy-vk9h`: hallazgos H1 a H9 y H34.
Los datasets hermanos y sus hallazgos H17-H33 están en `02_ecosistema_secop.md`;
acá aparecen en la sección 2 solo con su veredicto. Las decisiones de diseño que
salieron de estos hallazgos viven en `03_decisiones_capa_raw.md`.

H10 a H16 no existen: nunca se asignaron y sus contenidos quedaron dentro de H6.
Por eso el hallazgo nuevo es H34 y no H10. Los identificadores no se reciclan.

Última verificación contra la API: 28 de agosto de 2026.

## Tres palabras que este documento usa a cada rato

**Regeneración.** La fuente no actualiza filas: se rehace entera y sobrescribe su
estado anterior (H2). Ocurre de madrugada, y no todos los días (H34).

**Corte.** El estado que produjo una regeneración. Se identifica por
`:updated_at`, que es idéntico en todas las filas y por eso funciona como llave
del corte aunque no sirva como watermark de fila. "El corte del 25" es lo que un
analista llamaría la foto de ese día.

**Partición**, que significa dos cosas y conviene no mezclarlas. Una *ventana de
backfill* es un pedazo del histórico, normalmente un mes, para reprocesar el
pasado sin bajar todo de una vez. Una *partición de paralelismo* es un pedazo del
universo vivo que se reparte entre procesos de la misma corrida. Darle una
ventana de backfill al flujo 3 hace creer que se está reprocesando el pasado, y
no es así: por eso el código lo rechaza (R1).

El resto del vocabulario (grano, watermark, SCD2, aditividad) es estándar y está
explicado en `01_modelo_dimensional.md`.

---

## 1. SECOP II: Contratos Electrónicos (ELEGIDA)

Endpoint: `https://www.datos.gov.co/resource/jbjy-vk9h.json`

Documentación consultada: Diccionario de Datos y Ficha Técnica - Registros
Administrativos, ANCP-CCE, versión 1.0, agosto 2025.

| Campo | Valor |
|---|---|
| Identificador | `jbjy-vk9h` |
| Tipo | Dataset maestro, no vista derivada |
| Publica | Agencia Nacional de Contratación Pública - Colombia Compra Eficiente |
| Filas | 5.958.553 |
| Columnas | 85 en el esquema real, enumeradas contra el endpoint de metadatos el 20/08/2026. El diccionario declara 87 (pregunta abierta 4) |
| Frecuencia declarada | Diaria. Declarada, no verificada, y contradicha (H34) |
| Rezago de publicación | ~1 día |
| Hora de regeneración | Madrugada colombiana, ventana de ~35 min entre 04:06 y 04:41 sobre tres observaciones. No es un horario publicado (H34) |
| Rango temporal | 2015-06-11 a 2026-08-17 |
| Licencia | Datos abiertos, Ley 1712 de 2014 |

Una fila es un contrato estatal con su estado **actual**. No es un registro
histórico: la fila se sobrescribe cuando el contrato cambia.

**Sanidad de negocio.** El diccionario reportaba ~4.775.550 contratos al 31 de
agosto de 2025. Un año después hay 5.958.553. La diferencia de ~1,18 millones es
consistente con la curva de ~1M anuales de H3: los números cierran contra una
fuente independiente.

**Por qué SODA2 y no SODA3.** La plataforma usa SODA3 por defecto desde octubre
de 2025. Se eligió SODA2 porque usa GET, así que una consulta se prueba pegando
una URL en el navegador; porque tiene diez años de documentación frente a menos
de uno; y porque el riesgo es asimétrico: si SODA2 falla se migra, mientras que
si SODA3 se comporta raro paginando datasets de este tamaño no hay precedentes
de la comunidad. Toda la lógica que conoce `$limit` y `$offset` vive aislada en
un solo módulo, así que migrar es reescribir ese archivo.

---

## Hallazgos

### H1: El grano es un contrato por fila

Es la primera pregunta de cualquier modelo dimensional. Si el grano fuera "una
versión de contrato", todos los totales estarían inflados y los tests de
unicidad fallarían de una forma que invita a taparlos con un `distinct`.

```
?$select=id_contrato,count(*) as n&$group=id_contrato&$having=count(*) > 1&$limit=5
?$select=count(*) as total,count(distinct id_contrato) as unicos
```

La primera devuelve `[]`. La segunda, `total = unicos = 5958553`. Dos métodos
independientes: `id_contrato` es llave primaria.

El diccionario oficial se contradice sobre esto. Declara `ID Contrato` como
llave única, pero en "Unidad de Medida" dice que cada unidad es un *proceso de
contratación*, y un proceso puede derivar en varios contratos. Prevalece la
evidencia, y queda la constancia de la discrepancia.

Lo no obvio: los contratos se modifican en la realidad (adiciones, prórrogas,
cesiones) y no aparecen filas nuevas. Entonces la fuente actualiza la fila en su
lugar, que lleva directo a H2.

---

### H2: La fuente tiene tres mecanismos de cambio y solo dos son detectables (CRÍTICO)

**El campo de sistema no sirve como watermark.** Existe `:updated_at`, y:

```
?$select=min(:updated_at) as mas_viejo,max(:updated_at) as mas_nuevo
```

devuelve mínimo y máximo idénticos al milisegundo sobre 5,96 millones de filas.
Confirmado cuatro veces:

| Consulta | Valor observado |
|---|---|
| 18/08/2026 | `2026-08-18T09:22:15.735Z` |
| 21/08/2026 | `2026-08-20T09:41:20.358Z` |
| 26/08/2026 | `2026-08-25T09:05:54.277Z` |
| 28/08/2026 | `2026-08-25T09:05:54.277Z` |

Colombia Compra Eficiente no actualiza filas individuales: regenera el dataset
completo en una sola operación, coherente con el proceso ETL nocturno que
describe el diccionario.

Mirá la segunda y la cuarta fila: el valor observado no es del día de la
consulta. Esa lectura tardó ocho días en hacerse, y es H34.

Y hay un matiz que la primera versión de este hallazgo no tenía. `:updated_at` no
es inútil, es inútil *para una cosa*. No sirve fila por fila, que era la pregunta
que se le estaba haciendo. Pero la misma propiedad que lo inutiliza para eso
—que min y max coincidan— lo convierte en la llave natural del corte: una
petición de segundos dice qué estado está vivo, y dos observaciones con el mismo
valor vieron el mismo estado. Sobre eso se apoyan D10 y D11. No vale para los
datasets hermanos, que escriben en continuo y no tienen corte (H23).

**Sí existe un watermark de negocio**, y lo aportó el diccionario, no los datos:
`ultima_actualizacion`, que no había aparecido en la fila de muestra (ver H6).
Cubre 3.448.849 filas con un rango de diez años, y está nula en el 42%. Qué
significa ese nulo es H8.

**Y hay un tercer mecanismo que ninguna columna registra:** los pagos avanzan sin
que ninguna fecha lo diga. Es H9.

| Mecanismo de cambio | Columna que lo detecta | Volumen |
|---|---|---|
| Contrato nuevo | `fecha_de_firma` | ~2.900/día |
| Evento contractual (modificación, cesión, cierre, liquidación) | `ultima_actualizacion` | ~2.065/día |
| Avance de ejecución financiera | ninguna | 735.809 contratos |

De ahí salen los tres flujos de ingesta: una ventana diaria sobre
`fecha_de_firma`, otra sobre `ultima_actualizacion`, y un refresco del universo
vivo para el tercero, porque no hay atajo: hay que reextraer y comparar.

El flujo 3 barre los cuatro estados vivos (`En ejecución`, `Modificado`,
`Suspendido`, `Prorrogado`), que suman 2.825.685 contratos, una vez por cada
regeneración. Correrlo dos veces contra el mismo corte no aporta nada, y el
cargador se planta (D11).

Es tentador acotarlo a `En ejecución` y correrlo semanal: 1,7M de filas en vez de
2,8M. No alcanza, porque un contrato `Modificado` o `Suspendido` sigue recibiendo
pagos, y una semana de resolución pierde el orden de los eventos dentro de ese
lapso. Ojo con el argumento simétrico: que la fuente pase días sin regenerar
(H34) tampoco justifica bajar el flujo a semanal. La resolución la fija la
fuente, y renunciar a más resolución de la que ella impone es perder
observaciones que sí existían.

Este flujo no admite backfill. Pregunta por el estado actual, y el estado de una
fecha pasada ya se destruyó: reejecutarlo hacia atrás escribiría el hoy con fecha
de ayer (R1).

Los flujos 1 y 2 suman ~5.000 filas por día hábil: una sola petición. Todo el
peso está en el flujo 3.

La consecuencia de fondo: **el historial no existe en el origen**. Nadie puede
consultar cuánto valía un contrato antes de una adición.

---

### H3: La curva de volumen mide adopción, no gasto

```
?$select=date_trunc_y(fecha_de_firma) as anio,count(*) as n&$group=anio&$order=anio
```

| Año | Contratos | | Año | Contratos |
|---|---|---|---|---|
| 2015 | 10 | | 2021 | 561.581 |
| 2016 | 1.342 | | 2022 | 710.534 |
| 2017 | 22.259 | | 2023 | 843.059 |
| 2018 | 142.973 | | 2024 | 950.670 |
| 2019 | 142.592 | | 2025 | 1.050.857 |
| 2020 | 357.251 | | 2026 (parcial) | 751.450 |
| | | | Sin fecha | 423.975 |

El salto de 10 contratos en 2015 a más de un millón en 2025 es la curva de
adopción de SECOP II, que se volvió obligatorio por etapas. No es crecimiento del
gasto público, y cualquier comparación interanual que cruce 2020 es inválida.

Por eso el análisis de los marts se restringe a 2020 en adelante: se pierden
309.176 filas (5,2%) y se gana validez. Los años previos quedan en raw.

El backfill son ~80 ventanas mensuales de 2020 a 2026, ninguna superior a
~100.000 filas.

Y una lección: `min()` y `max()` habían reportado el rango 2015-2026 sin
mencionar las 423.975 filas nulas, porque las funciones de agregación ignoran los
nulos en silencio. El `GROUP BY` completo se hace siempre.

---

### H4: Los nulos de fecha de firma son todos pre-firma

Partir el backfill por año de firma dejaría 423.975 filas huérfanas sin que
ningún error lo advirtiera: simplemente no entrarían en ninguna ventana.

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

Suman 423.975, que coincide exactamente con el grupo nulo de H3. Los cinco
estados son anteriores a la firma: no hay un solo contrato "En ejecución",
"Cerrado" o "terminado" sin fecha de firma.

Así que el filtro de negocio que excluye lo que no es un contrato ejecutable
resuelve el problema técnico de las ventanas como efecto colateral. Cuando una
decisión de modelado limpia dos problemas a la vez, normalmente está bien
elegida.

---

### H5: `estado_contrato` mezcla dos dimensiones

| Estado | Filas | | Estado | Filas |
|---|---|---|---|---|
| En ejecución | 1.737.502 | | Cancelado | 110.665 |
| Cerrado | 1.690.510 | | enviado Proveedor | 43.924 |
| Modificado | 1.081.413 | | cedido | 28.557 |
| terminado | 774.500 | | En aprobación | 24.712 |
| Borrador | 245.385 | | Suspendido | 6.650 |
| Aprobado | 214.615 | | Prorrogado | 120 |

Suman 5.958.553. El diccionario define el campo como "Estado del contrato, frente
a su ejecución, firma o liquidación" y no enumera los valores posibles, así que
esta lista es la única fuente de verdad disponible.

Los valores pertenecen a dos ejes distintos. Uno es la etapa del ciclo (Borrador,
En aprobación, enviado Proveedor, Aprobado, En ejecución, Cerrado, terminado); el
otro es qué le ocurrió al contrato (Modificado, Prorrogado, cedido, Suspendido,
Cancelado). Un contrato en ejecución que fue modificado tiene dos verdades y la
columna solo guarda una: `Modificado`, con 1,08M de filas, probablemente esconde
el estado real. H8 lo refuerza, porque esos contratos casi siempre tienen fecha
de evento.

Por eso la capa intermedia deriva columnas propias (`esta_vigente`,
`fue_modificado`) en vez de usar `estado_contrato` crudo como máquina de estados.

`terminado`, `cedido` y `enviado Proveedor` no respetan la capitalización de los
demás, lo que sugiere orígenes o épocas distintas dentro del sistema fuente. Se
normaliza en staging, y fue uno de los argumentos que decidieron dónde corre la
comparación de cambios (D1).

Anomalía menor: `Borrador` suma 245.385 pero solo 244.947 tienen fecha de firma
nula. Quedan 438 contratos en Borrador con fecha de firma, lo cual es
contradictorio. No afecta al modelo porque se excluyen igual.

---

### H6: Observaciones sobre el esquema

**Una fila no revela el esquema.** La fila de muestra trajo 81 claves de las 85
reales, porque Socrata omite del JSON las claves cuyo valor es nulo. Enumerando
contra el endpoint de metadatos:

| Columna | Veredicto |
|---|---|
| `ultima_actualizacion` | Existe, estaba nula en esa fila. Material |
| `fecha_inicio_liquidacion` | Existe. Material |
| `fecha_fin_liquidacion` | Existe. Material |
| `fecha_de_notificaci_n_de_prorrogaci_n` | Existe. Material |
| `fecha_de_inicio_de_ejecucion` | No existe en la API |
| `fecha_de_fin_de_ejecucion` | No existe en la API |
| `estado_bpin`, `c_digo_bpin`, `anno_bpin` | No existen en la API |

Son cinco columnas documentadas y ausentes, contra una diferencia declarada de
dos entre el diccionario (87) y el esquema real (85). Alguno de los dos números
está mal: pregunta abierta 4.

La omitida más importante era `ultima_actualizacion`: ninguna cantidad de
exploración sobre esa fila la habría revelado, y sobre ella se apoya la mitad de
la estrategia de extracción.

**Tipos.** Todos los valores llegan como texto, incluso los que el diccionario
declara como número. Se descarga todo como string a propósito: si pandas infiere
tipos, convierte a `NaN` los valores mal formados y esconde la suciedad. Lo que
se prohíbe es que la herramienta adivine en silencio, no convertir de forma
explícita cuando hace falta (D6).

**Nombres deformados por Socrata.** Acentos reemplazados por `_`
(`localizaci_n`, `duraci_n_del_contrato`) y nombres truncados
(`justificacion_modalidad_de`, `valor_pendiente_de`). El renombrado a nombres
limpios se hace en staging y funciona como documentación.

**`urlproceso` es un objeto anidado**, `{"url": "https://..."}`, no un escalar
como las otras 84 columnas. Hay que extraer `urlproceso.url` explícitamente o
rompe la conversión a Parquet, y esa rareza terminó decidiendo el formato de
archivo de la capa raw (D2). La URL trae además un `noticeUID=CO1.NTC.xxx` que no
se puede reconstruir desde `proceso_de_compra`: es un tercer identificador, y
probablemente la llave hacia el dataset de Procesos.

**Suciedad detectable en una sola fila.** `nit_entidad` sin dígito de
verificación; `localizaci_n` con espacios dobles; saltos de línea embebidos en la
dirección de ejecución; `duraci_n_del_contrato` como texto libre (`"2 Mes(es)"`);
`orden` = "Nacional" para un hospital departamental y `rama` = "Corporación
Autónoma" para una ESE; proveedores que mezclan personas naturales y empresas. Y
una discrepancia con el diccionario: define `nombre_representante_legal` como el
representante de la entidad, pero en la fila inspeccionada coincide exactamente
con `proveedor_adjudicado`.

#### Los centinelas de texto

Los nulos vienen como centinela, con dos capitalizaciones: `"No definido"` y
`"No Definido"`. No son nulos de verdad, así que la omisión de claves no los
cubre, y se normalizan en staging.

Y hay un tercero en inglés que no estaba documentado: `UNSPECIFIED`. Medido el
29/08/2026 sobre las 67 columnas de `stg_contratos`, aparece en 26.156
observaciones y en una sola columna, `codigo_de_categoria_principal`, que es la
que responde la pregunta 1 del negocio. La limpieza no lo toca, porque
`columnas.py` declara solo los dos primeros. El efecto es el de siempre: la
columna reporta cero nulos y aun así el 0,9% de los contratos no tiene categoría.

Por ahora se marca en `dim_categoria` con `es_sin_especificar` y los cuatro
niveles de la jerarquía quedan nulos, para que un `group by familia` no invente
una familia llamada `ECIF`, que es lo que devuelve cortar `UNSPECIFIED` por donde
va el código. Meterlo en los centinelas aplicaría a las 67 columnas y obliga a
reconstruir todo el pipeline: queda pendiente.

Deja además una pregunta de método abierta: si hay un centinela en inglés que
ocho días de exploración no encontraron, puede haber otros. La búsqueda que lo
encontró (contar un valor literal sobre las 67 columnas de texto) es barata y no
se había hecho nunca de forma sistemática.

#### Seis entidades reclasificadas entre el 23 y el 25 de agosto de 2026

Es el primer cambio real que el pipeline capturó, y la prueba de que la premisa
del proyecto no es teórica. Comparando el barrido del 23 contra la corrida del
25, 20.675 contratos cambiaron `entidad_centralizada`, en seis entidades y en las
dos direcciones:

| Entidad | `orden` | Contratos | Cambio |
|---|---|---|---|
| Gobernación del Cauca | Territorial | 8.955 | a Descentralizada |
| SENA Regional Valle | Nacional | 5.553 | a Centralizada |
| SENA Secretaría General | Nacional | 3.014 | a Descentralizada |
| Instituto Municipal de Cultura y Turismo | Territorial | 1.274 | a Centralizada |
| Instituto Departamental de Salud de Nariño | Territorial | 1.156 | a Centralizada |
| Hospital de Castilla la Nueva ESE | Territorial | 723 | a Descentralizada |

La primera versión de esta nota decía que todas iban hacia "Descentralizada", y
era falso. El error salió de la consulta: pedía `min()` y `max()` de la columna y
los mostraba como "de → a", y alfabéticamente "Centralizada" precede a
"Descentralizada", así que toda fila salía como "Centralizada → Descentralizada"
sin importar hacia dónde hubiera ido. La consulta no podía dar otro resultado. Se
detectó al construir `dim_entidad`, que versiona en orden cronológico y por lo
tanto muestra la dirección real.

Nadie que consulte SECOP hoy puede saber que esto pasó: la fuente se sobrescribió
y hoy solo dice "Descentralizada". Existe únicamente porque se guardaron las dos
fotos y se compararon.

Y la bidireccionalidad descarta la lectura cómoda. Sería fácil enunciarlo como
"se corrigieron seis clasificaciones erróneas", pero el SENA se mueve en las dos
direcciones el mismo día; dos entidades descentralizadas por definición legal
(un instituto departamental de salud, uno municipal de cultura) fueron marcadas
como centralizadas; y una gobernación, que es el nivel central de la
administración departamental, fue marcada como descentralizada. Los movimientos
van en contra de la doctrina administrativa.

Lo que se sostiene es que la fuente reclasificó seis entidades en un solo
movimiento, en ambas direcciones, sobre una taxonomía cuyo significado su propio
diccionario no define. No que haya corregido errores, y no se puede construir
lógica de negocio sobre esa columna hasta saber qué mide. Engancha con la
pregunta abierta 2.

El evento pertenece a la dimensión y no al contrato: `entidad_centralizada` es
cosmética, así que el snapshot no generó versión para esos 20.675 contratos, y la
clasificación es correcta. `dim_entidad` se construyó con historia el 28/08/2026
y captura las seis reclasificaciones: 5.168 filas para 5.162 entidades, con las
seis cortando el 25 de agosto. El evento existe en el modelo aunque ya no exista
en la fuente.

#### Llaves de entidad

`codigo_entidad` es la llave: 5.162 valores, cada uno con exactamente un NIT y
exactamente un nombre, sin excepciones.

`nit_entidad` no sirve, porque 281 NITs tienen más de un código. Son entidades
jurídicas con varias unidades ejecutoras que contratan por separado, y agrupar
por NIT las colapsaría.

Y hay 5.140 nombres para 5.162 códigos: 22 nombres repetidos, que pueden ser
homonimia real (dos hospitales San José) o suciedad. En cualquier caso, agrupar
por nombre en un tablero da un resultado equivocado.

#### `localizaci_n` no completa a `departamento` y `ciudad`

Al construir `dim_geografia` pareció que sí: tiene cero nulos, contra 56.335 en
`departamento` y 611.751 en `ciudad` (el 21% de las observaciones). No lo es, por
tres razones independientes, medidas el 28/08/2026.

De los 611.751 contratos sin ciudad, la cadena permite recuperar 2.875: el 0,47%.
Los otros 608.876 traen `"No Definido"` **dentro** de la cadena, y de departamento
se recupera cero. Eso explica sus cero nulos: su ausencia de dato viene escrita
adentro del texto, y la limpieza de centinelas trata valores que *son* el
centinela, no que lo *contienen*.

El formato tampoco es fijo: 2.885.078 filas tienen tres campos separados por coma
y 17.085 tienen cuatro, porque un departamento se llama *San Andrés, Providencia
y Santa Catalina* y tiene comas en el nombre. Un parseo ingenuo habría inventado
un departamento llamado "Providencia y Santa Catalina" con 13.102 contratos, y
nada habría fallado.

Y discrepa en el 34% de las filas, pero no es una contradicción: son tres
diferencias de nomenclatura.

| En la cadena | En la columna | Filas |
|---|---|---|
| `Bogotá` | `Distrito Capital de Bogotá` | 965.212 |
| `San Andrés` | `San Andrés, Providencia y...` | 16.044 |
| `Departamento del Amazonas` | `Amazonas` | 13.021 |

Bogotá explica el 97%, y el nombre largo es el correcto porque Bogotá no
pertenece a ningún departamento. Esto cierra la duda sobre `localizaci_n`, a
diferencia de `orden`, `rama` y `entidad_centralizada`, que siguen sin
explicación: las columnas son las confiables y la cadena usa otra convención.

Por lo tanto los 611.751 contratos sin ciudad no tienen ciudad. El dato no está
escondido en otra columna: la fuente no lo publica. Cualquier análisis por
municipio deja fuera el 21% de la contratación, y eso hay que decirlo en el
tablero, no compensarlo.

#### El 74% de la contratación pública colombiana es directa

De `dim_modalidad`, sobre las 2.902.163 observaciones:

| Modalidad | Contratos |
|---|---|
| Contratación directa | 2.141.401 |
| Contratación régimen especial | 486.517 |
| Mínima cuantía | 141.405 |
| Contratación Directa (con ofertas) | 30.303 |
| Selección Abreviada de Menor Cuantía | 29.083 |

Sumando directa, directa con ofertas y régimen especial, la contratación sin
licitación abierta supera el 90%. Es el dato de negocio más citable que salió del
modelo, y sale de una dimensión de 232 filas.

#### Valores imposibles en `valor_del_contrato`

La columna que justifica el proyecto entero tiene basura, de dos clases que hay
que mantener separadas porque se atrapan con herramientas distintas.

La que el sistema de tipos rechaza: un contrato trae `767747876936238525636`, 21
dígitos, unos 767 mil trillones de pesos. No entra en `decimal(20,2)` y
`try_cast` lo vuelve nulo. Es 1 sobre 2.902.163. Agrandar el decimal para que
entre sería lo peor que se puede hacer, porque el valor pasaría a contaminar toda
suma, promedio y máximo del proyecto. Que se rechace es el sistema funcionando.

La que el sistema de tipos deja pasar, y es peor: siete contratos distintos cuyo
valor supera el Presupuesto General de la Nación de 2026, que el Congreso aprobó
en 546,9 billones de pesos. Los siete castean limpio, con `castings_fallidos = 0`.

| Valor declarado | Veces el PGN | Estado | Entidad |
|---|---|---|---|
| 12.858 billones | 23,5 | En ejecución | Instituto municipal de deportes |
| 6.453 billones | 11,8 | En ejecución | Institución educativa |
| 3.247 billones | 5,9 | Modificado | Ministerio del Interior |
| 714 billones | 1,3 | Modificado | Ministerio del Interior |
| 601 billones | 1,1 | Modificado | Secretaría distrital |
| 579 billones | 1,1 | Modificado | DISAN-DMSOC |
| 577 billones | 1,1 | En ejecución | Hospital Central de la Policía |

Las entidades son lo que cierra la lectura: un megaproyecto de infraestructura
mal digitado sería discutible, un instituto municipal de deportes con 23,5 veces
el presupuesto del Estado no lo es.

Pero el dinero no se movió, y eso hay que decirlo. Seis de los siete declaran
`valor_pagado = 0`, y el séptimo 22,7 millones sobre 577 billones. Son errores de
digitación publicados sin ningún filtro, no desfalcos, y la afirmación sostenible
es que la fuente oficial no valida sus propios valores. Esa versión no necesita
adorno para ser fuerte.

`valor_pagado = 0` no sirve para detectarlos, porque la mayoría de los contratos
sanos también lo tiene en cero. Sirve para interpretarlos.

La distribución sugiere además dos fenómenos y no uno: los tres primeros están
órdenes de magnitud por encima, y los últimos cuatro apenas cruzan el techo. El
umbral del PGN parte ese segundo grupo por la mitad, lo que confirma que es el
nivel de lo imposible y apenas la punta: 32 contratos superan el billón de pesos
y el mínimo es 1,07 billones, que una obra de infraestructura grande puede valer.
Separar los legítimos de la basura es lo que RN13 tiene que resolver, y el umbral
de sospecha sigue sin fijar (pregunta abierta 15).

Es H33 otra vez, en otra columna: un valor con forma válida y contenido
imposible. Un casting que no falla no dice que el dato sea cierto.

Y una pérdida de precisión silenciosa: 3 contratos traen más de dos decimales,
como `51041037891.7566`, y `decimal(20,2)` los redondea sin avisar. Se anota y no
se cambia el tipo, porque dos decimales es lo correcto para pesos y son los datos
los que están raros.

#### `liquidaci_n` es booleana, no un hito

Este documento y `columnas.py` la ponían junto a las dos fechas de liquidación,
bajo el rótulo de "hitos que arrancan nulos y se llenan". No arranca nula nunca:
sobre las 2.902.163 observaciones hay 2.611.371 en `"No"`, 290.792 en `"Si"`, y
cero nulos o centinelas.

Sigue siendo material, y por un motivo mejor que el que tenía escrito: pasar de
`"No"` a `"Si"` es un cambio de estado real. Lo que se corrige es la razón, y eso
importa porque un motivo equivocado es el que después justifica la siguiente
decisión equivocada: acá habría llevado a esperar un `NULL → fecha` que no va a
ocurrir.

Y no calza con `fecha_inicio_liquidacion`: 290.792 contra 292.694, 1.902 de
diferencia. Si fueran lo mismo dicho de dos formas, coincidirían. Un casi-calce
pide explicación igual que un calce demasiado bueno (pregunta abierta 14).

#### Dos contratos terminan una liquidación que nunca empezó

| | Filas | Lectura |
|---|---|---|
| Inicio sí, fin no | 35 | Liquidaciones en curso. Normal |
| Fin sí, inicio no | 2 | Imposible |

Dos sobre 2.902.163 es 0,00007%. La rareza es lo que los hace interesantes: es
corrupción puntual, del mismo tipo que H33 encontró en una columna de fechas, y
no una categoría con significado. Es el origen de RN12, y una regla que falla con
dos incumplimientos es un test que sirve: se puede investigar en vez de ahogarse
en ruido.

#### Desagregación de financiación: son seis columnas, no cinco

`presupuesto_general_de_la_nacion_pgn`, `sistema_general_de_participaciones`,
`sistema_general_de_regal_as`, `recursos_propios_alcald_as_gobernaciones_y_...`,
`recursos_de_credito` y `recursos_propios`. La sexta se descubrió al enumerar el
esquema completo; este documento decía cinco.

Medido el 28/08/2026 con `scripts/medir_rn1.py` sobre las 2.824.446 filas del
barrido del 23, o sea el universo vivo entero. No contra la API: raw ya tenía las
seis columnas en disco, y en SoQL un nulo en cualquier sumando anula la suma.

| | Filas | % |
|---|---|---|
| La sexta con valor distinto de cero | 1.281.254 | 45,4% |
| Cierran igual con cinco o con seis | 1.449.900 | 51,3% |
| Cierran SOLO incluyendo la sexta | 1.280.989 | 45,4% |
| No cierran de ninguna forma | 93.557 | 3,3% |

RN1 son seis columnas: con cinco, la regla fallaría en casi la mitad del universo
vivo.

La expectativa era la contraria, y el error es instructivo. Se esperaba que la
sexta no apareciera casi nunca, razonando desde que ninguna muestra la había
mostrado. Pero la API omite las claves nulas, cosa que este mismo documento
advierte: "no apareció en las muestras" y "está casi siempre vacía" son
afirmaciones distintas, y de la primera no se sigue la segunda.

Las seis están presentes en las 2.824.446 filas, sin una sola ausencia ni un solo
centinela, así que son esquema estable y staging no tiene que rellenarlas. La
muestra es parte del resultado: esto mide el universo vivo, no el histórico.

Los 93.557 que no cierran son la pregunta abierta 13. Las diez diferencias
inspeccionadas son todas negativas, con montos de hasta 1.062 millones, y diez de
diez con el mismo signo no es casualidad. Hay tres explicaciones sin separar: que
exista una séptima fuente con otro nombre; que `valor_del_contrato` incluya algo
que las fuentes no, como adiciones ya aprobadas, y entonces RN1 haya que
formularla contra un valor base; o que sea un incumplimiento real de la fuente, y
entonces sea un hallazgo publicable. Antes de festejar la tercera hay que
descartar que el error sea nuestro, y la vía barata es cruzar esos contratos
contra Adiciones.

---

### H7: Datos personales sensibles

El dataset expone cédulas, nombres completos, género y domicilio residencial del
representante legal (por ejemplo `"AMBAR RESERVA APTO 1006 TORRE A"`), del
ordenador del gasto y del supervisor. Son datos legalmente abiertos, pero
republicarlos en un tablero público es una decisión distinta a consultarlos.

Son 18 columnas y se excluyen desde el diseño. El filtro corre en el `$select`,
no después: la exclusión más barata de auditar es la que hace que el dato no
viaje. Es la única exclusión que vive en la extracción; el corte de 2020 y los
estados pre-firma son filtros de negocio y viven en dbt, donde son reversibles.
Acá la irreversibilidad es la característica buscada.

---

### H8: `ultima_actualizacion` no es lo que su nombre sugiere

El campo tenía 42% de nulos, y un watermark con ese nivel de ausencia no se puede
usar sin entender qué significa el nulo. La hipótesis intuitiva era que los nulos
fueran los contratos en estado terminal.

```
?$select=estado_contrato,count(*) as n&$where=ultima_actualizacion IS NULL&$group=estado_contrato
```

| Estado | Nulos | Total | % nulo |
|---|---|---|---|
| En ejecución | 1.728.553 | 1.737.502 | 99,5% |
| Borrador | 245.385 | 245.385 | 100% |
| Aprobado | 213.109 | 214.615 | 99,3% |
| Cancelado | 110.625 | 110.665 | 99,9% |
| enviado Proveedor | 43.924 | 43.924 | 100% |
| En aprobación | 24.712 | 24.712 | 100% |
| Cerrado | 66.607 | 1.690.510 | 3,9% |
| Modificado | 41.953 | 1.081.413 | 3,9% |
| terminado | 33.864 | 774.500 | 4,4% |
| cedido | 846 | 28.557 | 3,0% |
| Suspendido | 126 | 6.650 | 1,9% |

La hipótesis era exactamente al revés. Los contratos que llegaron a un desenlace
casi todos tienen fecha; los que están simplemente en ejecución, casi ninguno.

Entonces no es un campo de auditoría técnica: es la fecha del último **evento
contractual**. Si a un contrato no le ha pasado nada desde su firma, el campo
queda vacío. El nombre es engañoso y la definición del diccionario ("Fecha de
última actualización del contrato electrónico") no lo aclara: solo se descubre
cruzando el diccionario con la distribución real.

Sirve como watermark para el flujo de eventos, no como watermark general. El nulo
no es un dato faltante, es información: significa "sin eventos posteriores a la
firma". El flujo mide ~2.065 eventos/día.

**Sobre `freshness`.** El máximo es 2026-08-17, igual que el de `fecha_de_firma`:
la fuente tiene ~1 día de rezago, y se había fijado el umbral en 48 horas para no
dar falsos positivos todos los días. Las 48 horas no alcanzan: el 28/08/2026 el
corte vivo era el del 25, o sea que una fuente sana llevaba tres días sin
regenerar y la alerta habría saltado. El umbral no se puede fijar hasta tener el
registro de sondeo de H34, y hay que decidir además contra qué se mide: contra
`ultima_actualizacion` (el negocio) o contra `:updated_at` (la regeneración). Son
dos preguntas distintas.

**Sobre la hora de regeneración.** Hay tres cortes fechados: `09:22:15Z`,
`09:41:20Z` y `09:05:54Z`, o sea 04:22, 04:41 y 04:06 hora de Colombia. Este
documento decía que 04:41 "define el `schedule` del DAG". No: es la más tardía de
tres observaciones, no un horario publicado, y H34 muestra que hay días sin
ninguna regeneración. Ningún `schedule` acierta contra un evento que a veces no
ocurre, así que el disparador es el corte (D11).

---

### H9: La ejecución financiera cambia sin dejar rastro

`valor_facturado`, `valor_pagado`, `valor_pendiente_de_pago` y `valor_amortizado`
son acumulados que se mueven durante la vida del contrato. Si se mueven sin que
ninguna fecha lo registre, existe un mecanismo de cambio invisible para todos los
watermarks.

```
?$select=count(*) as n&$where=estado_contrato='En ejecución' AND valor_pagado > 0 AND ultima_actualizacion IS NULL
```

Resultado: **735.809**. El 42% de los contratos en ejecución tienen pagos
registrados y ninguna columna de fecha lo refleja. El dinero se movió; el dataset
no lo dice.

Ningún watermark puede capturar esto, así que requiere el flujo 3: refresco del
universo vivo en cada regeneración.

**Este es el hallazgo que más justifica la plataforma.** La serie temporal de
ejecución financiera por contrato (cuánto se había pagado en cada momento) no
existe en ninguna fuente pública, y solo puede construirse tomando snapshots a lo
largo del tiempo. El SCD tipo 2 deja de ser un requisito de tutorial y pasa a ser
lo único que justifica que la plataforma exista.

Se buscó esa serie en todo el ecosistema y no está: no hay columna de valor en el
dataset de modificaciones (H17), su única fecha llega truncada a nivel de día en
el 83% de las filas (H33), y la publicación en OCDS que sí conservaba enmiendas
se apagó en abril de 2022 (H21). Tres verificaciones independientes.

El argumento no se apoya en la fecha: aunque `fecharegistro` estuviera intacta,
seguiría faltando el monto. La fecha truncada agrava, no sostiene. El único
candidato del ecosistema sin evaluar es `SECOP II - Ejecución de Contratos`
(pregunta abierta 8).

---

### H34: La fuente no se regenera todos los días (CRÍTICO)

Todo el proyecto se escribió sobre la frase "la fuente se regenera cada noche", y
nadie la comprobó. La ficha declara frecuencia diaria, y una frecuencia declarada
es una promesa, no una medición.

El 28/08/2026 a las ~10:00 COT, la misma consulta de H2 devolvía el corte del
**martes 25**. La consulta se hizo un **viernes**.

| Día | Evidencia | Lectura |
|---|---|---|
| mar 18 | corte fechado `09:22:15.735Z` | regeneró |
| jue 20 | corte fechado `09:41:20.358Z` | regeneró |
| vie 21 | a las ~09:37 COT el corte vivo era el del 20 | no regeneró |
| mar 25 | corte fechado `09:05:54.277Z` | regeneró |
| mié 26 | a las 20:30 COT el corte vivo era el del 25 | no regeneró |
| jue 27 | deducido: si hubiera regenerado, el corte del 28 sería suyo | no regeneró |
| vie 28 | a las ~10:00 COT el corte sigue siendo el del 25 | no regeneró |

Tres regeneraciones y cuatro días sin regenerar, tres consecutivos. Los saltos
observados son de dos días (18→20) y cinco (20→25): ningún par de cortes separado
por exactamente un día, en todo el registro. Ninguna regeneración en fin de
semana.

La calidad de cada fila es distinta y conviene no aplanarla: las del 21, 26 y 28
son observaciones directas, la del 27 es una deducción, y el resto son huecos
donde nadie miró.

**No es una caída de la plataforma.** El control es el dataset hermano de
Adiciones, que escribe en continuo (H23) y sirve de testigo: el 26/08 a las 20:30
marcaba `2026-08-26T11:21:12Z` y el 28/08 a las 10:00, `2026-08-28T09:51:29Z`. La
plataforma transaccional está viva; lo que no corre es el ETL que regenera la
vista publicada.

**El dato del 21 estaba en este documento desde el principio.** H2 anotaba
"Reconfirmado el 21/08/2026: min = max = 2026-08-20T09:41:20.358Z". Esa consulta
se hizo cerca de las 09:37 COT del viernes, cinco horas después del final de la
ventana de regeneración. La fuente llevaba un día sin regenerar y el documento lo
registró como confirmación de que todo iba bien. No es un dato nuevo: es un dato
que estaba mal leído.

**Qué se cae.** La palabra "noche" en todas las frases del proyecto; el
`schedule` del DAG contra las 04:41; el `freshness` de 48 h, que hoy alertaría
sobre una fuente sana; el delta de veinticuatro horas como cosa medible, que
exige un par de cortes separados por un día y no existe ninguno; y el ancho del
intervalo de la corrida del 25/08, que estaba anotado como dos días y está entre
dos y cinco, irrecuperable.

**Qué no se cae.** H2, que sale reforzado: el reemplazo total se observó cuatro
veces, y lo que cambia es cada cuánto ocurre, no qué ocurre. La premisa del
proyecto, porque cada regeneración destruye el estado anterior igual; si acaso al
revés, menos cortes significa menos oportunidades de capturar la historia y
perder una cuesta más. Y el diseño de la capa raw, que ya había decidido no
prometer resolución diaria: `observado_desde` y `observado_hasta` se llaman así
justamente porque un intervalo largo significa que no miramos, no que nada
cambió.

#### El supuesto que se adoptó, y se retiró

Se supuso que había al menos una regeneración por semana, como supuesto de
planificación y no como dato, con la condición explícita de volver acá si algún
intervalo pasaba de siete días.

Pasó. Comprobado el 01/09/2026: el corte vivo seguía siendo el del 25 de agosto,
una semana entera. Y no era la plataforma, porque el testigo escribió ese mismo
día a las 10:21 COT.

| | |
|---|---|
| Regeneraciones observadas | 3 (18, 20 y 25 de agosto) |
| Días comprobados sin regenerar | 7 |
| Saltos entre regeneraciones | 2 días, 5 días, y uno de 7 o más |

Lo que reemplaza al supuesto es no tener ninguno. No hay cota superior
establecida, y con tres regeneraciones no se puede estimar una: lo único que se
sabe es que el máximo observado crece cada vez que se mira.

Eso no obliga a rediseñar nada, y conviene decir por qué. El disparador es el
corte y no el calendario (D11), el DAG no lleva horario, y las columnas se llaman
`observado_*` a propósito. Lo que se cae es la planificación, no la arquitectura.
De las tres cosas que dependían del supuesto: el `freshness` sigue sin piso; el
margen del DAG no dependía de la cadencia sino de cuánto dura un barrido; y del
patrón de días hábiles no hay evidencia, salvo que las tres regeneraciones
cayeron en día hábil.

La consecuencia que sí duele es de producto: la población medible del mart crece
solo cuando la fuente regenera y se ingiere.

#### La segunda fase, del 3 al 8 de septiembre

Después de los siete días congelados, la fuente regeneró todos los días entre el
3 y el 8 de septiembre. El registro de cadencia lo tiene línea por línea. Eso no
restablece el supuesto retirado: agrega un régimen más a una fuente que ya mostró
dos, y refuerza que el disparador tenga que ser el corte.

---

## Reglas de negocio para tests de dbt

Derivadas de los hallazgos, no inventadas para llenar el requisito. La lista
canónica vive en `01_modelo_dimensional.md` sección 10; si las dos se
desincronizan, manda el modelo dimensional.

| ID | Regla | Origen |
|---|---|---|
| RN1 | La suma de las **seis** fuentes de financiación iguala `valor_del_contrato` | H6 |
| RN2 | Ningún registro del hecho tiene estado pre-firma | H4, H5 |
| RN3 | Ningún registro del hecho tiene `fecha_de_firma` nula | H3, H4 |
| RN4 | La fuente no tiene más de 48 horas de rezago (`freshness`) | H8 |
| RN5 | `valor_pagado` no decrece entre versiones consecutivas | H9: es un acumulado |
| RN6 | RN1 se cumple en toda versión histórica, no solo en la fila actual | RN1 + diseño SCD2 |
| RN7 | `dias_adicionados` y `fecha_de_fin_del_contrato` cambian juntos | Dominio |
| RN8 | `valor_de_pago_adelantado = valor_amortizado + valor_pendiente_de` | Diccionario oficial |
| RN9 | Si `el_contrato_puede_ser_prorrogado = "No"`, entonces `dias_adicionados = 0` | Coherencia interna |
| RN10 | Si `habilita_pago_adelantado = "No"`, entonces `valor_de_pago_adelantado = 0` | Coherencia interna |
| RN11 | Las adiciones no superan el 50% del valor inicial, en SMLMV a la firma | Ley 80 art. 40 |

RN5 es interesante en los dos resultados posibles: si decrece, o hubo reversión de
un pago o la fuente tiene un error, y los dos casos valen la pena. Protege
`valor_pagado`, que es acumulado, y no se generaliza a `valor_del_contrato`, que
sí puede bajar: el dataset de modificaciones tiene un tipo `REDUCCION EN EL VALOR`
(H27).

RN9 y RN10 tienen una trampa: `habilita_pago_adelantado` no es booleana. Se
observó en `"No Definido"`, o sea tres estados, y `"No Definido"` no equivale a
`"No"`.

---

## Lecciones de método

Aplicables a cualquier fuente futura, no solo a esta.

1. **Explorá antes de leer, pero leé antes de concluir.** Mirar los datos primero
   genera preguntas que hacen que el diccionario se lea en cinco minutos. Pero
   cerrar una conclusión de diseño sin haberlo consultado lleva a errores: H2
   estuvo mal escrita hasta que el diccionario reveló `ultima_actualizacion`.
2. **Las funciones de agregación ignoran los nulos en silencio.** `min/max`
   reportó un rango limpio ocultando 423.975 filas sin fecha. Hacé siempre el
   `GROUP BY` completo.
3. **Una fila no revela el esquema** cuando la API omite las claves nulas.
   Enumerá contra el endpoint de metadatos en vez de inferir desde los datos: fue
   así como apareció la sexta fuente de financiación.
4. **Probá la hipótesis obvia y aceptá cuando falla.** En H8 la explicación
   intuitiva de los nulos era la opuesta a la real, y verificarla fue lo que
   reveló la semántica verdadera del campo.
5. **El diccionario oficial puede estar equivocado.** Se contradice sobre el grano
   (H1) y define mal `nombre_representante_legal` (H6). Prevalece la evidencia,
   pero se deja constancia de la discrepancia.
6. **Buscá la misma realidad publicada dos veces.** Comparar dos datasets que
   cubren el mismo hecho revela defectos que ninguno confiesa por separado: H33
   solo fue visible cruzando Adiciones contra Suspensiones. Y si los conteos
   coinciden exactamente, no es coincidencia: son las mismas filas.

   El corolario costó aprenderlo: **el cruce descubre el defecto, no lo mide.**
   Ocho filas cruzadas revelaron el truncamiento de H33; hicieron falta seis
   consultas agregadas para saber que afecta a 26,5 millones de filas. Y una de
   esas seis salió mal la primera vez, por aplicarle al mes el umbral del día.
   Una muestra que revela un patrón invita a darlo por medido.
7. **Los tipos declarados no garantizan nada.** `fecharegistro` está declarada
   como fecha, parsea sin error, y está sistemáticamente mal.
8. **Las etiquetas de la fuente no son de fiar, ni las de afuera ni las de
   adentro.** "Adiciones" es un log de modificaciones donde las adiciones son
   minoría; la ficha de Suspensiones no declara ser una vista derivada, siéndolo;
   y el tipo `ADICION EN EL VALOR` existe como categoría pero no sirve como
   filtro. Que una categoría exista no significa que sea exhaustiva.
9. **Una frecuencia declarada no es una medición, y una confirmación puede tapar
   un hallazgo.** La evidencia de que la fuente no regeneraba a diario ya estaba
   en este documento, anotada como "reconfirmado" porque confirmaba lo que se le
   preguntaba (H2) mientras contradecía en silencio lo que no se le preguntaba.

   Una consulta hecha para confirmar A puede contener la refutación de B, y solo
   se ve mirando el dato entero. La defensa es barata: anotar siempre *cuándo* se
   hizo la consulta, no solo qué devolvió. Fue la hora de la corrida del 21,
   recuperada desde los datasets hermanos, lo que permitió releer ese dato ocho
   días después.

---

## Preguntas abiertas

Cerradas: `valor_pendiente_de` es Valor Pendiente de Amortización, según el
diccionario. Las modificaciones sí tienen un registro de eventos, el dataset
`SECOP II - Adiciones`, pero sin columna de valor y con la fecha truncada (H17,
H33). `fecha_fin_liquidacion` existe y es material; `fecha_de_inicio_de_ejecucion`
y `estado_bpin` no existen en la API (H6).

1. **¿`Cerrado` y `terminado` son sinónimos o estados distintos?** Son 1,69M y
   774K filas, y el diccionario no enumera los valores posibles. Se resuelve
   comparando `fecha_de_fin_del_contrato`, `fecha_fin_liquidacion` y
   `liquidaci_n` entre los dos grupos.
2. **¿Qué miden `orden` y `rama`?** El diccionario los define de forma circular y
   los valores no coinciden con la intuición: un hospital departamental figura
   como "Nacional".
3. **¿Los estados terminales realmente no cambian?** `ESTADOS_VIVOS` excluye
   Cerrado, terminado y Cancelado del flujo 3. Es razonable pero no está probado:
   un contrato Cerrado podría recibir pagos rezagados, y si el supuesto es falso
   el flujo 3 es ciego a esos pagos.
4. **¿Cuántas columnas documenta realmente el diccionario?** Dice 87 contra 85
   reales, o sea dos ausentes, pero H6 identifica cinco documentadas que no
   existen en la API. Se cierra recontando el PDF contra el endpoint de
   metadatos.
5. **¿`origen_de_los_recursos` es redundante con las seis fuentes de
   financiación?** En una fila coincidía, y una fila genera hipótesis, no
   conclusión. Se contesta contra raw.
6. **¿Por qué `saldo_cdp` no se consume con la ejecución?**
7. ~~¿La llave de `dim_proveedor` es `documento_proveedor` o `codigo_proveedor`?~~
   **Cerrada el 28/08/2026: `codigo_proveedor`.** Cero nulos contra 8.917 del
   documento; 15 códigos con más de un documento contra 1.297 al revés; y, lo que
   decidía, el código no se reusa entre proveedores distintos, comprobado
   revisando los 101 códigos con más de un nombre, que resultaron variantes de
   escritura del mismo. `documento_proveedor` queda como atributo: es el
   identificador legal y la vía hacia cruces externos.
8. **¿Aporta algo `SECOP II - Ejecución de Contratos`?** Sin evaluar. Es el
   candidato obvio para la serie de pagos que H9 demostró que no existe.
9. **¿Por qué la ANCP-CCE dejó de publicar OCDS en abril de 2022?** Si hay un
   anuncio público, es una cita para el README.
10. **¿La fuente regenera los fines de semana?** Ninguna observación. Lo contesta
    el registro de cadencia, no una consulta.
11. **¿Hay un anuncio público sobre interrupciones del ETL de la ANCP-CCE?** Tres
    días consecutivos sin regenerar, con la plataforma transaccional escribiendo,
    es lo bastante visible como para que alguien lo haya dicho.
12. **¿Contra qué se mide el `freshness` de dbt?** Contra `ultima_actualizacion`
    mide el rezago del negocio; contra `:updated_at`, si la fuente se regeneró.
    Son dos alertas distintas y hoy solo está contemplada la primera, con un
    umbral que H34 dejó sin piso.
13. **¿Por qué 93.557 contratos vivos no cierran RN1, y siempre por defecto?** El
    3,31% del universo vivo declara fuentes que suman menos que su propio
    `valor_del_contrato`, con diferencias de hasta 1.062 millones. No bloquea a
    `stg_contratos`: bloquea el umbral con el que RN1 falla en dbt.
14. **¿Por qué `liquidaci_n = "Si"` y `fecha_inicio_liquidacion` no coinciden?**
    290.792 contra 292.694, 1.902 de diferencia.
15. **¿Cuántos de los 32 contratos por encima del billón son reales?** El mínimo
    es 1,07 billones, que una obra grande puede valer; el máximo supera 23 veces
    el PGN. Es lo que RN13 tiene que resolver, y el umbral de sospecha todavía no
    está fijado.

---

## 2. Otras fuentes del ecosistema

| Dataset | ID | Veredicto |
|---|---|---|
| SECOP II - Adiciones | `cb9c-h8sn` | Evaluado, fuera de la v1. Log de modificaciones, 26.571.106 filas: 4,5 veces la fuente principal (H29). Cinco columnas, ninguna de valor. `fecharegistro` trunca mes y día (H33) |
| SECOP II - Suspensiones | `u99c-7mfm` | Es una vista derivada de Adiciones (H25), con las mismas filas y las etiquetas corregidas. No es fuente independiente |
| SECOP II - Ejecución de Contratos | - | Sin evaluar. Candidato prioritario: el único lugar donde podría estar la serie de pagos de H9 |
| SECOP II - Rubros Presupuestales | - | Sin evaluar |
| OCDS | `ocds-k50g02` | Existió y se apagó. 3.008.861 enmiendas, enero 2011 - abril 2022. La API devuelve 404 |

**Por qué los hermanos no entran a la v1.** Su valor ya se capturó como hallazgos
(H17 a H33) sin cargar una sola fila. Incorporarlos quintuplicaría el tamaño del
proyecto y exigiría un segundo patrón de ingesta, porque se actualizan en continuo
y tienen watermark propio (H23). La v1 se define por hacer una cosa
impecablemente.

**Pendientes de evaluar.** Procesos de Contratación es el candidato v2 más
valioso comercialmente, porque son oportunidades abiertas y no contratos ya
perdidos; su problema de llaves quedó resuelto con el `noticeUID` de `urlproceso`.
Facturas sube de prioridad tras H9. Y quedan TVEC (~150.673 órdenes de compra, un
canal de compra distinto), el Plan Anual de Adquisiciones y SECOP I - Proponentes.

**Advertencia sobre el catálogo.** Muchos datasets de `datos.gov.co` son vistas
derivadas, no fuentes distintas. Si la ficha dice "Vista en función de X" hay que
ir al maestro. Pero la señal no siempre está: la ficha de Suspensiones no declara
que sea derivado, y lo es. Cuando dos datasets cubren el mismo hecho, hay que
compararlos aunque ninguno se declare derivado.

**SECOP I vs SECOP II** son dos generaciones, no alternativas. SECOP I era un
tablón de anuncios con datos pobres y ya no crece; SECOP II es transaccional. Son
dos plataformas, no dos agencias: Colombia Compra Eficiente las administra, y la
tercera plataforma es TVEC. El marco normativo son la Ley 80 de 1993, la Ley 1150
de 2007 y la Ley 1712 de 2014.
