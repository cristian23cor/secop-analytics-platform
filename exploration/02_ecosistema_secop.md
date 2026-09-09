# El ecosistema SECOP más allá de la fuente principal

Evaluación de los datasets hermanos de `jbjy-vk9h` y de lo que publica el Estado
sobre contratación. Contiene los hallazgos H17 a H33.

La exploración inicial se detuvo en la fuente principal. Al revisar el ecosistema
aparecieron tres datasets que el inventario nunca había evaluado, y con ellos un
defecto de datos que refuerza la tesis del proyecto en vez de debilitarla.

Ninguno entra a la v1. Su valor ya se capturó como hallazgos, sin cargar una sola
fila; el razonamiento está en la sección 8.

Documentos hermanos: `00_inventario_fuentes.md` (la fuente principal, H1-H9 y
H34) y `03_decisiones_capa_raw.md` (las decisiones D1-D11 e I1-I5).

Última verificación contra la API: 28 de agosto de 2026.

---

## 1. `SECOP II - Adiciones` (`cb9c-h8sn`)

El log de modificaciones contractuales. Es el dataset que podría haber respondido
la pregunta 7 —cuánto cuesta una prórroga en pesos— y no puede.

### H17: existe y NO trae el monto

Cinco columnas: `identificador` (llave propia de la modificación), `id_contrato`
(empata con `jbjy-vk9h`), `tipo`, `descripcion` y `fecharegistro`.

El monto existe, pero enterrado en prosa:

> `...ADICIONAR EL VALOR ... EN LA SUMA DE QUINCE MILLONES SEISCIENTOS NOVENTA Y
> TRES MIL PESOS ($15'693.000) M/CTE Y PRORROGAR ... TRES (3) MESES...`

En letras y en números, en el mismo campo donde también se prorroga el plazo.

El esquema se enumeró, no se infirió: son exactamente cinco columnas y ninguna es
una medida. Mismo método que destapó la sexta fuente de financiación en la fuente
principal. Con eso H9 queda confirmado con el mejor argumento posible: el monto de
una adición no existe como dato estructurado en ningún dataset del ecosistema.

`fecharegistro` es de tipo `calendar_date`, no texto: fecha real, ordenable y
filtrable, que es lo que permite trocear las agregaciones de H32.

### H18: El dataset está mal nombrado

Se llama "Adiciones" pero incluye `CONCLUSION`, un cierre de expediente sin plata.
Es un log de modificaciones en general, y el nombre induce a creer que todas las
filas son adiciones de valor.

### H26: `tipo = 'ADICION EN EL VALOR'` es un piso, no un filtro

El tipo existe, con 141.217 filas hasta 2022. Pero la fila de muestra
`CO1.CTRMOD.499720` está clasificada como `MODIFICACION GENERAL` y su descripción
adiciona $15.693.000.

`MODIFICACION GENERAL` son 1.767.394 filas, el 75% de las que respondieron el
troceado anual de H32 —o sea 2015 a 2022, no el dataset entero—. El numerador y el
denominador salen los dos de ese subconjunto, así que el porcentaje vale para esos
años y no se puede reexpresar contra el total de H29: dividir un numerador parcial
por un denominador completo no da nada.

Hay adiciones de valor escondidas ahí en proporción desconocida. Usar el tipo como
filtro exhaustivo subestima por un factor que no se puede acotar. Es el mismo
patrón que la hipótesis descartada de `dias_adicionados > 0`: la categoría existe
y no es exhaustiva.

Se había anotado que al menos para esas 141.217 filas habría fecha exacta sin
parsear texto. H33 lo acota: el año se conserva siempre, el mes en el 79,0% de las
filas y la fecha completa en el 13,6%.

### H27: El valor del contrato puede BAJAR

Existe `REDUCCION EN EL VALOR`, 145 filas hasta 2022. La lógica de deltas no puede
asumir monotonía. RN5 protege `valor_pagado`, que es acumulado;
`valor_del_contrato` no tiene esa garantía.

### H28: El centinela `No definido` también está en la columna que clasifica

Es el segundo tipo más frecuente: 515.151 filas, el 22%, con el mismo denominador
parcial que H26. Un quinto de los eventos de modificación de esos años no declara
qué fueron.

### H29: Adiciones cuadruplica a la fuente principal

26.571.106 filas contra 5.958.553 de `jbjy-vk9h`, medido el 25/08/2026 con
`count(*)`, que responde sin trocear aunque el `GROUP BY` de H32 no pueda. Ninguna
fila tiene `fecharegistro` nula.

Esto corrige la versión anterior de H29 por un factor de 4,4. Decía "el total
supera con holgura los seis millones", extrapolando desde las 2.785.329 filas
hasta 2022 que devolvió el troceado anual. La extrapolación subestimó, y la
lección es la de siempre: un agregado que la API no puede calcular entero no se
completa razonando, se pide de otra forma.

Si estos datasets entran al alcance, no es agregar una fuente chica al costado: es
quintuplicar el proyecto. Decisión de alcance, no de ingeniería.

Corroboración cruzada: OCDS reportaba 3.008.861 enmiendas hasta abril de 2022
(H21) y acá van 2.785.329 hasta diciembre de 2022. Los órdenes calzan, lo que
sugiere que OCDS se alimentaba de esta misma tabla.

---

## 2. `SECOP II - Suspensiones` (`u99c-7mfm`)

Parecía una segunda fuente y resultó ser una vista del mismo dataset.

### H25: es una versión CORREGIDA de las mismas filas de Adiciones

Los conteos anuales calzan cruzados: las suspensiones de un dataset son las
reactivaciones del otro, año por año, exactamente.

| Año | Adic. `SUSPENSIoN` | Adic. `REACTIVACIoN` | Susp. `Suspension` | Susp. `Reanudacion` |
|---|---|---|---|---|
| 2016 | 10 | 18 | 18 | 10 |
| 2018 | 2.120 | 2.921 | 2.921 | 2.120 |
| 2020 | 6.615 | 8.478 | 8.478 | 6.615 |
| 2022 | 18.429 | 21.398 | 21.398 | 18.429 |

Confirmado a nivel de fila sobre ocho casos, emparejando por el texto de la
descripción, que es idéntico entre los dos datasets. Ocho de ocho invertidas, y en
las siete inequívocas Suspensiones coincide con el texto mientras Adiciones lo
contradice: la etiqueta rota es la de Adiciones.

Es un matiz importante: Suspensiones no es una vista ingenua, es una versión
corregida, con etiqueta buena y fechas buenas (H33). Para eventos de suspensión es
la fuente preferible. Y los ~2 millones de filas restantes de Adiciones
(`MODIFICACION GENERAL`, `ADICION EN EL VALOR`) no tienen contraparte corregida en
ninguna parte.

Es justo la advertencia del inventario sobre vistas derivadas, salvo que la ficha
de este no lo declara: hay que descubrirlo comparando conteos.

### H20: podría conservar un valor pasado (hipótesis de una fila)

Suspensiones tiene siete columnas, y dos son fechas del contrato y no de la
modificación: `fecha_de_inicio_del_contrato` y `fecha_de_fin_del_contrato`.

En `CO1.PCCNTR.1735835` la reanudación se aprobó el 26-01-2021,
`fecha_de_fin_del_contrato` dice 24-01-2021, y el texto dice que la terminación
queda el 2 de marzo. La columna trae el valor viejo.

`fecha_de_fin_del_contrato` es material. Si se confirma, este dataset conserva
historia parcial de una columna material para los 6.650 contratos suspendidos, lo
que serviría como verificación independiente del pipeline propio.

Una fila genera hipótesis, no conclusión. Y H25 le cambió el significado: si
Suspensiones es una vista de Adiciones, no sería "un segundo dataset conserva
historia" sino "la vista expone dos columnas que la tabla base no publica". Sigue
siendo útil, pero deja de servir como verificación cruzada.

### H30: una anomalía en 2026, sin explicar

406.240 filas con `fecha_de_creacion` en 2026, año parcial, contra ~35-40 mil
anuales en 2023, 2024 y 2025. Salto de diez veces sin explicación de negocio
obvia. La sospecha es una reescritura de `fecha_de_creacion` en la carga masiva de
junio de 2025 (H23), y se contrasta comparando su distribución contra la de
`fecha_de_aprobacion`. Es sospecha, no conclusión.

### H31: no tiene columna identificadora

Siete columnas y ni una llave. Sin llave no hay `MERGE` idempotente. El candidato
es la tripleta `(id_contrato, tipo, fecha_de_aprobacion)`, pero si un contrato
tiene dos suspensiones aprobadas el mismo día colisiona y el `MERGE` pierde una
fila en silencio.

---

## 3. El defecto que solo se vio cruzando los dos

### H33: `fecharegistro` trunca mes y día al primer dígito significativo

Confirmado sobre 26.571.106 filas.

**Cómo apareció.** Tomando la fecha real de Suspensiones y truncando mes y día a
su primer dígito significativo, ocho de ocho coinciden con `fecharegistro`:

| Fecha real | Truncada | `fecharegistro` |
|---|---|---|
| 2020-12-14 | 2020-01-01 | 2020-01-01 |
| 2019-06-21 | 2019-06-02 | 2019-06-02 |
| 2019-10-15 | 2019-01-01 | 2019-01-01 |
| 2019-10-09 | 2019-01-09 | 2019-01-09 |

El 21 pasa a 2, el 15 a 1, el 12 a 1 y el 09 a 9. La columna está declarada
`calendar_date`, parsea sin error, y un pipeline la consumiría sin que nada
fallara. Fallo silencioso puro.

**El síntoma, sobre el dataset completo.** Cero filas con día mayor a 9 y cero con
mes mayor a 9, sobre 26,5 millones. Si las fechas fueran reales, unos 19,5
millones tendrían día mayor a 9. No es un margen estrecho: es estructural.

Los controles se corrieron sobre `jbjy-vk9h`, y hacen más que descartar un defecto
general del portal:

| Control sobre `fecha_de_firma` | Observado | Esperado si son reales |
|---|---|---|
| Día > 9 | 4.075.476 (73,6%) | 70,4% (los días 10 a 31 son 257 de 365) |
| Mes > 9 | 963.145 (17,4%) | 25% si fuera uniforme |

El del día queda tres puntos por encima de la frecuencia del calendario, que es
una desviación chica en la dirección de que las firmas se apilen sobre el final
del mes. Lo importante es que da millones donde Adiciones da cero, y que prueba
algo que el control no se proponía: que `date_extract_d` se comporta como se cree
sobre esta API. Sin él, un cero en Adiciones podría ser la función y no los datos.

**La distribución prueba el mecanismo, no solo el síntoma.** Un cero demuestra que
día y mes nunca superan 9, no *por qué*. El truncamiento al primer dígito deja una
huella particular: el balde 1 absorbe once días reales (1, 10-19), el 2 otros once
(2, 20-29), el 3 solo tres (3, 30, 31) y los baldes 4 a 9 uno cada uno.

| Balde | Días que absorbe | Esperado | Observado |
|---|---|---|---|
| 1 | 1, 10-19 | 36,2% | 35,4% |
| 2 | 2, 20-29 | 35,9% | 39,4% |
| 3 | 3, 30, 31 | 8,2% | 8,4% |
| 4-9 | uno cada uno | 3,3% c/u | 2,4-3,1% |

Medido en unidades de "un día real" (el promedio de los baldes 4 a 9), el balde 1
vale 12,6 días, el 2 vale 14,0 y el 3 vale 3,0. La hipótesis predice 11, 10,9 y
2,5. Ninguna lectura alternativa sobrevive: si las modificaciones ocurrieran solo
del 1 al 9, los nueve baldes serían comparables entre sí.

**Cuánto sobrevive.** Este documento decía "solo el año sobrevive". Es falso para
la mayoría de las filas, y la versión correcta es más interesante:

| Qué sobrevive | Filas | Proporción |
|---|---|---|
| El año | 26.571.106 | 100% |
| El mes | 21.003.223 | 79,0% |
| El día | 4.474.999 | 16,8% |
| La fecha entera | 3.619.047 | 13,6% |

El daño es desparejo por una razón estructural: truncar destruye información solo
cuando dos valores comparten inicial. Los meses llegan hasta 12, así que solo tres
colapsan (octubre, noviembre y diciembre caen en el balde 1 junto con enero) y los
otros ocho quedan intactos. Los días llegan hasta 31: veintidós de treinta y uno
colapsan.

Corolario para quien escriba el `$where`: para el mes el umbral es
`date_extract_m > 1`, no `> 3`. Asumir la simetría con el día es el error natural.

**El daño es identificable fila por fila.** La transformación es de muchos a uno
solo en los baldes 1, 2 y 3; en los demás es uno a uno, porque un día 7 solo pudo
venir de un día 7. No es una columna que haya que descartar entera: es una columna
donde se puede decir exactamente de cuáles valores fiarse.

Un control de independencia salió sin consulta extra: la probabilidad de que el
día sea exacto es 16,84%, y condicionada a que el mes lo sea, 17,23%. Prácticamente
idénticas, así que el truncamiento se aplica componente por componente y no a una
fecha compuesta.

**Consecuencias.** El consuelo de H26 queda a medias: para las 141.217 filas de
`ADICION EN EL VALOR` se conoce siempre el año, el mes en cuatro de cada cinco
casos y la fecha completa en algo más de una de cada ocho. Los conteos anuales de
H25 a H29 se salvan, porque el año sobrevive siempre. Y endurece la tesis del
proyecto: fechar una modificación en SECOP II con precisión de día solo es posible
guardando cortes.

**Lo que queda sin explicar.** El balde 1 del mes vale 2,1 meses cuando debería
valer 4,0: enero, octubre, noviembre y diciembre están subrepresentados. Dos
candidatas sin verificar: que 2026 esté a mitad de camino y no aporte cuarto
trimestre, y la estacionalidad real de las modificaciones. El control sobre
`fecha_de_firma` empuja en la misma dirección, lo que sugiere que es una propiedad
de la contratación y no del truncamiento. No amenaza la conclusión, porque la
prueba del truncamiento del mes viene del cero y no de la distribución.

---

## 4. Cómo se publican y se actualizan

### H23: Los hermanos se actualizan en continuo; la fuente principal no

Corrido el viernes 21/08/2026 alrededor de las 09:37 COT. La hora importa y no
estaba anotada: se recupera de los máximos de los hermanos, y es lo que ocho días
después permitió releer la fila de control (H34).

| Dataset | min(`:updated_at`) | max(`:updated_at`) | Lectura |
|---|---|---|---|
| `jbjy-vk9h` | 2026-08-20T09:41:20.358Z | idéntico | Reemplazo total. H2 intacto |
| Adiciones | 2024-10-04T21:14:28.562Z | 2026-08-21T14:28:52.934Z | Escritura incremental |
| Suspensiones | 2025-06-04T05:53:26.885Z | 2026-08-21T14:36:58.027Z | Escritura incremental |

Los máximos de los hermanos caen minutos antes de la corrida: se alimentan en
continuo desde la plataforma transaccional, no en un volcado nocturno.

**La fila de control decía más de lo que se le leyó.** El corte vivo de
`jbjy-vk9h` a las 09:37 del viernes 21 era el del jueves 20, cinco horas después
del final de la ventana de regeneración: ese viernes la fuente no había
regenerado. Se registró solo como confirmación de H2, que lo es, y la consecuencia
sobre la cadencia quedó sin ver hasta el 28 de agosto.

**"Minutos antes de la corrida" tiene un contraejemplo.** El 28/08 a las ~10:00
COT el máximo de Adiciones era de las 04:51 COT: cinco horas antes, no minutos.
Una observación no tumba H23, porque el patrón se sostiene sobre dos muestras y
sobre los mínimos, pero "en continuo" no quiere decir "sin pausas".

Los mínimos revelan otra cosa: Adiciones contiene filas con `fecharegistro` de
2018 pero ninguna con `:updated_at` anterior a octubre de 2024. Hubo una carga
masiva en esa fecha, y desde entonces las filas se tocan de a una.

Acá `:updated_at` no es fecha de negocio, es cuándo Socrata escribió la fila.
Sirve como watermark de ingesta y para nada más; no confundir con `fecharegistro`.

**Los hermanos sirven de testigo.** Como escriben en continuo y `jbjy-vk9h` no,
compararlos separa "la fuente no regeneró" de "la plataforma está caída". Se usó
así el 26 y el 28 de agosto, y es lo que descarta la explicación de la caída en
H34. Es un uso que no estaba previsto cuando se midió esto.

Esto no prueba que sean append-only: es compatible con append puro, con inserción
más edición posterior, y con upsert de sincronización. Las tres sirven como
watermark, y lo que rompería el esquema es el borrado, invisible para cualquiera.

Y un resultado append-only no abriría una opción de arquitectura nueva para D1,
aunque lo parezca: lo que aparece es una restricción. La capa raw tendría que
alojar dos patrones incompatibles —`jbjy-vk9h` por comparación de snapshots, los
hermanos por watermark propio con `MERGE`— y eso mueve peso en contra de la opción
B de D1, porque acoplar ingesta y detección de cambios estorba cuando una fuente
necesita la primera y no la segunda.

### H24: la regeneración cae en una ventana de madrugada

Este hallazgo decía que las 04:41 "definen el `schedule` del DAG". Hay que
retirarlo. Lo que sí se sabe son tres regeneraciones fechadas, y son todo lo que
hay:

| Corte | UTC | Hora de Colombia |
|---|---|---|
| 2026-08-18 | 09:22:15.735Z | 04:22 |
| 2026-08-20 | 09:41:20.358Z | 04:41 |
| 2026-08-25 | 09:05:54.277Z | 04:06 |

Se mueven en una ventana de ~35 minutos. 04:41 es la más tardía de las tres, no un
horario publicado ni un límite.

No define ningún `schedule`, por dos motivos independientes. Tres observaciones
sobre una ventana móvil no fijan una hora, así que el margen que uno crea tener
puede no existir. Y, decisivo, hay días sin ninguna regeneración (H34): ningún
horario acierta contra un evento que a veces no ocurre. El disparador es el corte
(D11).

**Desfase entre tablas.** Los hermanos están más frescos: una modificación
aprobada hoy a las 14:00 ya está en Adiciones, pero su efecto sobre
`valor_del_contrato` no aparece en `jbjy-vk9h` hasta la siguiente regeneración. Y
ese desfase no es "de hasta un día", como estaba escrito suponiendo cadencia
diaria: dura hasta la próxima regeneración, que puede ser al día siguiente o al
cabo de varios. El mart no puede prometer que un evento se refleje al día
siguiente.

### H19: La llave empata sin trabajo

`id_contrato` en Adiciones y Suspensiones es el mismo `CO1.PCCNTR.xxx` de
`jbjy-vk9h`.

### H22: Suciedad de texto: es la misma tubería de exportación

Tres deformaciones sistemáticas en ambos datasets.

Comillas rotas: los bytes 0x92, 0x93 y 0x94 son comillas tipográficas de
Windows-1252 leídas con la codificación equivocada, así que un monto escrito como
`$15'693.000` llega con un carácter de control en lugar del apóstrofo.

Mayúsculas a medias: `RESOLUCIoN`, `PRESTACIoN`, `DiAS`. Todo en mayúsculas salvo
las vocales acentuadas, que quedaron minúsculas y sin tilde.

Y comas convertidas en punto y coma, casi con certeza para no romper el CSV de
exportación.

Explica de dónde sale la basura que H6 detectó en `jbjy-vk9h`: mismo origen. Si
alguna vez se normaliza texto, la regla es una sola para todo el ecosistema.

### H32: Socrata no sirve para agregar sobre texto no indexado

Un `GROUP BY tipo` sobre el dataset completo revienta el timeout de 60 s. Con
troceado anual y 180 s respondieron 2015-2022 y fallaron 2023-2026, que son los
años de más volumen; para esos hay que bajar a partición mensual.

Refuerza la decisión de keyset y de partir por rangos de fecha ya tomada para el
extractor: no es una preferencia estética, la API no aguanta otra cosa.

---

## 5. Lo que el Estado publicó y dejó de publicar

### H21: El historial existió y lo apagaron

Colombia publicaba SECOP en OCDS (Open Contracting Data Standard), que modela
enmiendas explícitamente. El registro de Open Contracting Partnership reporta
3.008.861 enmiendas, entre enero de 2011 y abril de 2022, marcado como ya no
actualizado por el publicador, con prefijo OCID `ocds-k50g02` y licencia PDDL. La
API de la agencia devolvió 404.

Reformula el argumento del proyecto y lo mejora: no es que el historial nunca haya
existido, es que Colombia lo publicaba y dejó de hacerlo hace cuatro años. La
brecha es concreta y fechable.

### C4: Cobertura real de los tableros oficiales

La ANCP-CCE mantiene ~20 visualizaciones en Power BI. Contra las siete preguntas
de negocio:

| Pregunta | ¿Cubierta? |
|---|---|
| 1. Qué entidades compran mi categoría | Sí, demanda y oferta por UNSPSC |
| 2. Proveedor dominante y concentración | Parcial |
| 3. Valor típico en mi sector | Sí |
| 4. Estacionalidad de apertura | Parcial, en informes cerrados |
| 5. Directa vs. licitación | Sí |
| 6. Quién extiende el plazo y cuántos días | No |
| 7. Cuánto cuesta esa extensión en pesos | No |

Todo lo oficial es tablero, no plataforma: Power BI embebido, sin API, sin modelo
expuesto, sin histórico consultable.

---

## 6. Una regla de negocio que salió de la ley

### RN11: Límite legal de adición

El artículo 40 de la Ley 80 de 1993 establece que las adiciones no pueden superar
el 50% del valor inicial del contrato, expresado en salarios mínimos legales
mensuales vigentes al momento de la suscripción.

Es una buena regla por tres razones: sale del dominio y no del esquema; solo se
puede testear si se conserva el valor inicial, o sea que justifica la tabla de
snapshots desde la normativa; y su incumplimiento es un hallazgo publicable.

Ojo con la implementación: el límite es en SMLMV al momento de la firma, no en
pesos corrientes. Necesita una tabla de salario mínimo por año que hoy no existe
en el modelo.

---

## 7. Una vía que se descartó

Se puede sacar el monto del texto de `descripcion` con expresiones regulares o con
un modelo de lenguaje. Se descarta: viene en letras y en números, con separadores
rotos; está mezclado con prórrogas de plazo en la misma frase; y lo redacta a mano
cada una de miles de entidades.

Una tasa de acierto desconocida sobre la columna que sostiene la pregunta 7 es
peor que no tener la columna: convierte un vacío honesto en un número que nadie
puede auditar.

---

## 8. Por qué no entran a la v1

Su valor ya se capturó como hallazgos, sin cargar una sola fila. Incorporarlos
multiplicaría el tamaño del proyecto: Adiciones tiene 26.571.106 filas, 4,5 veces
la fuente principal (H29).

Y exigiría un segundo patrón de ingesta. Se actualizan en continuo y tienen
watermark propio (H23), a diferencia de la fuente principal, que se regenera
entera y de forma irregular (H2, H34). Serían dos mecanismos distintos conviviendo
en la misma capa raw. La v1 se define por hacer una cosa impecablemente.

---

## 9. Verificaciones pendientes

Script: `scripts/verificar_datasets_hermanos.py`.

| Fase | Pregunta | Estado |
|---|---|---|
| 0 | Esquema real de ambos datasets | hecho: 5 y 7 columnas, sin medidas (H17) |
| 1 | Grano y volumen | volumen hecho (H29); el grano sigue pendiente |
| 1b | Llave compuesta de Suspensiones | pendiente (H31) |
| 2 | Tipos de modificación | hecho (H25 a H29, H32) |
| 3 | ¿`:updated_at` difiere? | hecho (H23, H24) |
| 3b | `:created_at != :updated_at` | pendiente |
| 3c | ¿Los hermanos escriben todos los días? | pendiente: hay un contraejemplo el 28/08 |
| V | ¿Suspensiones es vista de Adiciones? | hecho (H25, H33) |
| T | Truncamiento de `fecharegistro` a escala | hecho: 26.571.106 filas (H33) |
| 4 | ¿Suspensiones conserva el fin viejo? | pendiente: la próxima (H20) |
| 5 | Cobertura del cruce | pendiente |
| 6 | Contraste con `dias_adicionados` | pendiente |

La verificación T se hizo con seis consultas y no con las tres que este documento
planeaba. Las tres que faltaban no eran adorno, y el patrón se repite. Faltaba el
**denominador**, porque un cero no significa nada sin saber sobre cuántas filas se
tomó: `count(*)` fue lo que convirtió "no hay ninguna" en "no hay ninguna entre
26,5 millones", y de paso corrigió H29. Faltaba el **segundo control**, porque uno
asimétrico deja abierto que el portal trunque meses en todas partes y días en
ninguna. Y faltaba la **distribución**, porque las dos consultas del plan prueban
el síntoma y no el mecanismo.

Y una consulta se corrió mal antes de correrse bien: para el mes el umbral es
`date_extract_m > 1`, no `> 3`.

H20 sigue vivo y cambió de sentido: como Suspensiones es la versión corregida, si
conserva el `fecha_de_fin_del_contrato` viejo es una propiedad de la fuente buena
y no de una vista sucia.

---

## 10. Preguntas abiertas

1. ¿`SECOP II - Ejecución de Contratos` y `SECOP II - Rubros Presupuestales`
   aportan algo? No evaluados. El de Ejecución es el candidato obvio para la serie
   de pagos que hoy no existe.
2. ¿Por qué la ANCP-CCE dejó de publicar OCDS en abril de 2022? Si hay un anuncio
   público, es una cita valiosa para el README.
3. ¿Los archivos históricos de OCDS (2011-2022, ~5,4 GB en JSONL) sirven para
   backfillear algo? Probablemente no para SECOP II, pero conviene saberlo antes
   de escribir "el histórico no se puede backfillear" en las limitaciones.
4. Con RN11: ¿cuántos contratos superan el 50% legal? Es un hallazgo concreto con
   número.
5. ¿Qué tan buen testigo es Adiciones? Se lo usa para descartar que la fuente
   principal esté detenida por una caída de plataforma, y ese uso supone que el
   hermano escribe todos los días. Es plausible y no está medido: si Adiciones
   también pausara los fines de semana, el testigo callaría justo cuando más falta
   hace.
