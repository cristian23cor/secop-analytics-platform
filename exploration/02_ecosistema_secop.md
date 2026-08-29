# El ecosistema SECOP más allá de la fuente principal

> Evaluación de los datasets hermanos de `jbjy-vk9h` y de lo que publica el
> Estado sobre contratación. Contiene los hallazgos H17 a H33.
>
> **Por qué existe este documento:** la exploración inicial se detuvo en la
> fuente principal. Al revisar el ecosistema completo aparecieron tres datasets
> que el inventario nunca había evaluado, y con ellos un defecto de datos que
> refuerza la tesis del proyecto en vez de debilitarla.
>
> **Veredicto general:** ninguno de estos datasets entra a la v1. Su valor ya se
> capturó como hallazgos, sin cargar una sola fila. El razonamiento está al
> final, en *Por qué no entran a la v1*.
>
> Documentos hermanos: `00_inventario_fuentes.md` (la fuente principal, H1–H9 y
> H34) y `03_decisiones_capa_raw.md` (las decisiones de diseño D1–D8, D10, D11 e
> I1–I5).
>
> Última verificación contra la API: 28 de agosto de 2026.

---

## 1. `SECOP II – Adiciones` (`cb9c-h8sn`)

El log de modificaciones contractuales. Es el dataset que podría haber
respondido la pregunta 7 —cuánto cuesta una prórroga en pesos— y no puede.

### H17 — `SECOP II – Adiciones` existe y NO trae el monto - verificado en muestra

Dataset `cb9c-h8sn`. Cinco columnas:

```
identificador CO1.CTRMOD.499720 ← llave propia de la modificación
id_contrato CO1.PCCNTR.285227 ← empata con jbjy-vk9h
tipo MODIFICACION GENERAL | CONCLUSION
descripcion texto libre
fecharegistro 2018-09-01T00:00:00.000
```

El monto **existe pero enterrado en prosa**:

> `...ADICIONAR EL VALOR ... EN LA SUMA DE QUINCE MILLONES SEISCIENTOS
> NOVENTA Y TRES MIL PESOS ($15'693.000) M/CTE Y PRORROGAR ... TRES (3)
> MESES...`

En letras y en números, en el mismo campo donde también se prorroga el
plazo. **H8 queda confirmado y reforzado:** no es que falte la columna en
`jbjy-vk9h`, es que no existe en ningún dataset del ecosistema.

**Cerrado por la FASE 0 (esquema enumerado, no inferido):** Adiciones tiene
exactamente 5 columnas y ninguna es una medida. Mismo método que destapó la sexta fuente de financiación en la fuente
principal: enumerar, no inferir. H8 confirmado con el mejor
argumento posible: el monto de una adición **no existe como dato
estructurado en ningún dataset del ecosistema SECOP**.

`fecharegistro` es de tipo `calendar_date`, no texto: fecha real, ordenable
y filtrable. Es lo que permite trocear las agregaciones (ver H32).

Ver también H26: existe un tipo `ADICION EN EL VALOR`, pero no es un filtro
exhaustivo.

### H18 — El dataset está mal nombrado

Se llama "Adiciones" pero incluye `CONCLUSION`, un cierre de expediente sin
plata. Es un **log de modificaciones contractuales** en general. El nombre
induce al error de creer que todas las filas son adiciones de valor.

### H26 — `tipo = 'ADICION EN EL VALOR'` es un piso, no un filtro - verificado

El tipo existe (141.217 filas hasta 2022). Pero la fila de muestra
`CO1.CTRMOD.499720` está clasificada como `MODIFICACION GENERAL` y su
descripción adiciona **$15.693.000**.

`MODIFICACION GENERAL` son 1.767.394 filas, **el 75% de las que respondieron
el troceado anual de H32 — o sea 2015 a 2022, no el dataset**. El numerador y
el denominador salen los dos de ese subconjunto, así que el porcentaje vale
para esos años y no se puede reexpresar contra el total de H29: dividir un
numerador parcial por un denominador completo no da nada. Hay adiciones de
valor escondidas ahí en proporción desconocida. Usar el tipo como filtro
exhaustivo subestima por un factor que no se puede acotar.

Mismo patrón que la hipótesis descartada de `dias_adicionados > 0` para
identificar contratos `Modificado`: la categoría existe y no es exhaustiva.

**Lo que se creía ganar, y se gana solo en parte:** se anotó que para 141.217
modificaciones habría "fecha exacta de una adición de valor sin parsear texto".
**H33 lo acota:** `fecharegistro` trunca mes y día, así que el año se conserva
siempre, el mes en el 79,0% de las filas y la fecha completa en el 13,6%. No
alcanza para fechar una adición de forma general, pero tampoco queda "solo el
año": queda el año, casi siempre el mes, y a veces la fecha entera — y se sabe
en cuáles filas.

### H27 — El valor del contrato puede BAJAR

Existe `REDUCCION EN EL VALOR` (145 filas hasta 2022). La lógica de deltas
no puede asumir monotonía. RN5 protege `valor_pagado`, que es acumulado;
`valor_del_contrato` no tiene esa garantía.

### H28 — El centinela `No definido` también está en la columna que clasifica

Segundo tipo más frecuente de Adiciones: **515.151 filas, el 22%** — con el
mismo denominador parcial que H26, los años 2015 a 2022. Con la misma
capitalización minúscula que H13. Un quinto de los eventos de modificación de
esos años no declara qué fueron.

### H29 — Volumen: Adiciones cuadruplica a la fuente principal - medido

**26.571.106 filas**, contra 5.958.553 de `jbjy-vk9h`. Medido el 25 de agosto
de 2026 con `?$select=count(*) as n`, que responde sin trocear aunque el
`GROUP BY` de H32 no pueda. Ninguna fila tiene `fecharegistro` nula: el conteo
de valores no nulos da el mismo número.

⚠ **Esto corrige la versión anterior de H29 por un factor de 4,4.** Decía "el
total supera con holgura los seis millones", extrapolando desde las 2.785.329
filas hasta diciembre de 2022 que devolvió el troceado anual. La extrapolación
subestimó, y la lección es la de siempre acá: un agregado que la API no puede
calcular entero no se completa razonando, se pide de otra forma.

Si estos datasets entran al alcance, no es agregar una fuente chica al
costado: es **quintuplicar** el proyecto. Decisión de alcance, no de
ingeniería.

Corroboración cruzada: OCDS reportaba 3.008.861 enmiendas hasta abril de
2022 (H21) y acá van 2.785.329 hasta diciembre de 2022. Los órdenes calzan,
lo que sugiere que OCDS se alimentaba de esta misma tabla.


---

## 2. `SECOP II – Suspensiones` (`u99c-7mfm`)

Parecía una segunda fuente y resultó ser una vista del mismo dataset.

### H25 — `Suspensiones` es una versión CORREGIDA de las mismas filas de `Adiciones` - verificado

Conteos por año, uno al lado del otro:

| Año | Adic. `SUSPENSIoN` | Adic. `REACTIVACIoN` | Susp. `Suspension` | Susp. `Reanudacion` |
|---|---|---|---|---|
| 2016 | 10 | 18 | 18 | 10 |
| 2017 | 129 | 210 | 210 | 129 |
| 2018 | 2.120 | 2.921 | 2.921 | 2.120 |
| 2019 | 3.565 | 4.186 | 4.186 | 3.565 |
| 2020 | 6.615 | 8.478 | 8.478 | 6.615 |
| 2021 | 9.353 | 11.188 | 11.188 | 9.353 |
| 2022 | 18.429 | 21.398 | 21.398 | 18.429 |

**Confirmado a nivel de fila** contra `CO1.PCCNTR.809547` y
`CO1.PCCNTR.1735835`, emparejando por el texto de la descripción (idéntico
entre ambos datasets):

| Texto dice | Adiciones `tipo` | Suspensiones `tipo` |
|---|---|---|
| "LA SUSPENSIoN SE REALIZA..." | `REACTIVACIoN` | `Suspension` |
| "LA REANUDACIoN DEL CONTRATO 1479..." | `SUSPENSIoN` | `Reanudacion` |
| "...HACER LA SUSPENSIoN ... DESDE EL 22/06/2019" | `REACTIVACIoN` | `Suspension` |
| "...HACER EL REINICIO DEL CONTRATO" | `SUSPENSIoN` | `Reanudacion` |
| "...REANUDAR ... DESDE EL 15 DE OCTUBRE" | `SUSPENSIoN` | `Reanudacion` |
| "...HACER LA SUSPENSIoN ... ARRENDAMIENTO PN" | `REACTIVACIoN` | `Suspension` |
| "...SUSPENDER ... DESDE EL 5 DE OCTUBRE" | `REACTIVACIoN` | `Suspension` |
| (texto corto, ambiguo) | `SUSPENSIoN` | `Reanudacion` |

Ocho de ocho invertidas. En las siete inequívocas, **Suspensiones coincide
con el texto y Adiciones lo contradice**: la etiqueta rota es la de
Adiciones. Esto explica la coincidencia cruzada de los conteos agregados.

**Matiz importante:** Suspensiones no es una vista ingenua, es una versión
**corregida** — etiqueta buena, fechas buenas (ver H33). No se descarta:
para eventos de suspensión es la fuente preferible. Y las ~2 millones de
filas restantes de Adiciones (`MODIFICACION GENERAL`, `ADICION EN EL VALOR`,
etc.) **no tienen contraparte corregida en ninguna parte**.

Es justo la advertencia del propio inventario sobre vistas derivadas en
datos.gov.co — salvo que la ficha de este no lo declara, y hay que
descubrirlo comparando conteos.

### H20 — Suspensiones podría conservar un valor pasado - hipótesis de una fila

`SECOP II – Suspensiones` (`u99c-7mfm`) tiene siete columnas, y dos de
ellas son fechas del contrato, no de la modificación:

```
id_contrato, tipo (Suspension | Reanudacion), fecha_de_creacion,
fecha_de_aprobacion, proposito_de_la_modificacion,
fecha_de_inicio_del_contrato, fecha_de_fin_del_contrato
```

En `CO1.PCCNTR.1735835`: reanudación aprobada el **26-01-2021**,
`fecha_de_fin_del_contrato` = **24-01-2021**, y el texto dice que la
terminación queda el **2 de marzo de 2021**. La columna trae el valor
**viejo**.

`fecha_de_fin_del_contrato` es MATERIAL. Si se confirma, este dataset
conserva historia parcial de una columna material para los 6.650 contratos
suspendidos — utilizable como **verificación independiente del pipeline
propio**, que en un README vale más que otra métrica.

Una fila genera hipótesis, no conclusión. Lo prueba la FASE 4.

 **Suspendido por H25.** Si Suspensiones resulta ser una vista derivada de
Adiciones, este hallazgo cambia de significado: no sería "un segundo dataset
conserva historia", sino "la vista expone dos columnas que la tabla base no
publica". Sigue siendo útil, pero deja de ser una fuente independiente y no
sirve como verificación cruzada del pipeline. Resolver H25 primero.

### H30 — `Suspensiones` tiene una anomalía en 2026, sin explicar

406.240 filas con `fecha_de_creacion` en 2026 (año parcial), contra ~35-40
mil anuales en 2023, 2024 y 2025. Salto de diez veces sin explicación de
negocio obvia.

Sospecha: reescritura de `fecha_de_creacion` en la carga masiva de junio de
2025 (H23). Se contrasta comparando la distribución de `fecha_de_creacion`
contra la de `fecha_de_aprobacion`. **Es sospecha, no conclusión.**

### H31 — `Suspensiones` no tiene columna identificadora

Siete columnas y ni una llave. Sin llave no hay `MERGE` idempotente. El
candidato es la tripleta `(id_contrato, tipo, fecha_de_aprobacion)`, pero si
un contrato tiene dos suspensiones aprobadas el mismo día, colisiona y el
`MERGE` pierde una fila **en silencio**. Lo prueba la FASE 1b.

(Si H25 se confirma, esto se vuelve irrelevante: no se carga el dataset.)


---

## 3. El defecto que solo se vio cruzando los dos

### H33 — `fecharegistro` de Adiciones trunca mes y día al primer dígito significativo - confirmado sobre 26.571.106 filas

#### Cómo apareció: ocho filas cruzadas contra Suspensiones

Tomando la fecha real de Suspensiones y truncando mes y día a su **primer
dígito significativo**:

| Fecha real (`fecha_de_creacion`) | Truncada | `fecharegistro` |
|---|---|---|
| 2020-**12**-**14** | 2020-01-01 | 2020-01-01 ✓ |
| 2021-**01**-**13** | 2021-01-01 | 2021-01-01 ✓ |
| 2019-**06**-**21** | 2019-06-02 | 2019-06-02 ✓ |
| 2019-**07**-**15** | 2019-07-01 | 2019-07-01 ✓ |
| 2019-**10**-**15** | 2019-01-01 | 2019-01-01 ✓ |
| 2019-**04**-**16** | 2019-04-01 | 2019-04-01 ✓ |
| 2019-**10**-**09** | 2019-01-09 | 2019-01-09 ✓ |
| 2019-**04**-**23** | 2019-04-02 | 2019-04-02 ✓ |

`21 → 2`, `15 → 1`, `12 → 1`, `09 → 9`. Ocho de ocho.

La columna está declarada `calendar_date`, parsea sin error, y un pipeline la
consumiría sin que nada fallara. **Fallo silencioso puro.**

#### El síntoma, sobre el dataset completo (25 de agosto de 2026)

```
?$select=count(*) as n                                        → 26.571.106
?$select=count(fecharegistro) as con_fecha                    → 26.571.106
?$select=count(*) as n&$where=date_extract_d(fecharegistro) > 9 → 0
?$select=count(*) as n&$where=date_extract_m(fecharegistro) > 9 → 0
```

Ninguna fila sin fecha, y **cero filas con día o mes mayor a 9** sobre 26,5
millones. Si las fechas fueran reales, unos 19,5 millones tendrían día mayor a
9. No es un margen estrecho: es estructural.

**Los controles hacen más que descartar un defecto general del portal.** Se
corrieron los dos sobre `jbjy-vk9h`, no solo el del día:

| Control sobre `fecha_de_firma` | Observado | Esperado si las fechas son reales |
|---|---|---|
| Día > 9 | 4.075.476 (73,6%) | 70,4% — los días 10 a 31 son 257 de los 365 del año |
| Mes > 9 | 963.145 (17,4%) | 25% si fuera uniforme |

El del día queda tres puntos por encima de lo que da la frecuencia del
calendario, que es una desviación chica y en la dirección de que las firmas se
apilen sobre el final del mes. Lo importante es que **da millones donde
Adiciones da cero**, y que eso prueba algo que el control no se proponía: que
`date_extract_d` se comporta como se cree sobre esta API. Sin él, un cero en
Adiciones podría ser la función y no los datos.

⚠ El 70,4% se calcula contando días del año, no como `22/30`. Esa
aproximación da 73,3% y hace parecer que el observado clava el esperado.

#### La distribución prueba el mecanismo, no solo el síntoma

Un cero demuestra que día y mes nunca superan 9. No demuestra **por qué**.
El truncamiento al primer dígito deja una huella muy particular: el balde 1
absorbe once días reales (1, 10–19), el 2 otros once (2, 20–29), el 3 solo tres
(3, 30, 31) y los baldes 4 a 9 uno cada uno.

```
?$select=date_extract_d(fecharegistro) as dia,count(*) as n&$group=dia&$order=dia
```

| Balde | Días reales que absorbe | Esperado | Observado |
|---|---|---|---|
| 1 | 1, 10–19 | 36,2% | 35,4% |
| 2 | 2, 20–29 | 35,9% | 39,4% |
| 3 | 3, 30, 31 | 8,2% | 8,4% |
| 4–9 | uno cada uno | 3,3% c/u | 2,4–3,1% |

Medido en unidades de "un día real" —el promedio de los baldes 4 a 9, 745.833
filas— el balde 1 vale **12,6 días**, el 2 vale **14,0** y el 3 vale **3,0**.
La hipótesis predice 11, 10,9 y 2,5.

**Ninguna lectura alternativa sobrevive.** Si las fechas fueran reales y las
modificaciones ocurrieran solo del 1 al 9, los nueve baldes serían comparables
entre sí. Que dos sean doce y catorce veces más grandes que los otros seis, y
que el tercero sea exactamente tres veces, solo se explica porque absorben once,
once y tres días respectivamente.

#### Cuánto sobrevive — esto corrige la versión anterior del hallazgo

Este documento decía **"solo el año sobrevive"**. Es falso para la mayoría de
las filas, y la versión correcta es más interesante:

| Qué sobrevive | Filas | Proporción |
|---|---|---|
| El año | 26.571.106 | 100% |
| El mes | 21.003.223 | **79,0%** |
| El día | 4.474.999 | 16,8% |
| La fecha entera | 3.619.047 | **13,6%** |

**El daño es tan desparejo por una razón estructural**, y no había motivo para
esperar simetría. Truncar destruye información solo cuando dos valores comparten
inicial. Los meses llegan hasta 12, así que **solo tres colapsan** —octubre,
noviembre y diciembre caen en el balde 1 junto con enero— y los otros ocho
quedan intactos. Los días llegan hasta 31: **veintidós de treinta y uno
colapsan**.

Corolario para quien escriba el `$where`: para el mes el umbral es
`date_extract_m > 1`, no `> 3`. Asumir la simetría con el día es el error
natural acá.

#### El daño es identificable fila por fila

La transformación es de muchos a uno **solo en los baldes 1, 2 y 3**. En los
demás es uno a uno: un día 7 solo pudo venir de un día 7, porque los días 70–79
no existen. Lo mismo con los meses 2 a 9.

```
?$select=count(*) as n&$where=date_extract_d(fecharegistro) > 3
                             AND date_extract_m(fecharegistro) > 1   → 3.619.047
```

O sea que no es una columna que haya que descartar entera: es una columna donde
se puede decir exactamente de cuáles valores fiarse.

**Control de independencia, que salió sin consulta extra:** `P(día exacto)` es
16,84% y `P(día exacto | mes exacto)` es 17,23%. Prácticamente idénticas, así
que el truncamiento se aplica componente por componente y no a una fecha
compuesta.

#### Consecuencias

- **El consuelo de H26 queda a medias, no muerto.** Para las 141.217 filas de
  `ADICION EN EL VALOR` se conoce siempre el año, el mes en cuatro de cada
  cinco casos, y la fecha completa en algo más de una de cada ocho. Sigue sin
  alcanzar para fechar una adición de forma general, y esas filas no tienen
  dataset corregido, a diferencia de las suspensiones.
- **Salva los conteos de la FASE 2.** El año sobrevive siempre, así que el
  troceado anual y los totales de H25 a H29 siguen siendo válidos.
- **Endurece la tesis del proyecto:** fechar una modificación en SECOP II con
  precisión de día solo es posible guardando cortes.

#### Lo que queda sin explicar

El balde 1 del mes vale **2,1 meses** cuando debería valer 4,0: enero, octubre,
noviembre y diciembre están fuertemente subrepresentados. Dos explicaciones
candidatas, ninguna verificada: que 2026 esté a mitad de camino y no aporte
ningún cuarto trimestre, y la estacionalidad real de las modificaciones. El
control sobre `fecha_de_firma` empuja en la misma dirección (17,4% para meses
mayores a 9, contra 25% uniforme), lo que sugiere que es una propiedad de la
contratación y no del truncamiento.

**No amenaza la conclusión.** La prueba del truncamiento del mes no viene de la
distribución sino del cero: sobre 26,5 millones de filas no hay ni una con mes
10, 11 o 12, y eso es imposible en fechas reales.


---

## 4. Cómo se publican y se actualizan

### H23 — Los hermanos se actualizan en continuo; la fuente principal no - verificado

Resultado de la FASE 3, corrida el **viernes 21/08/2026 alrededor de las 09:37
COT** (14:37 UTC). La hora importa y no estaba anotada: se recupera de los
máximos de los hermanos, que caían minutos antes, y es lo que ocho días después
permitió releer la fila de control. Ver H34 en `00_inventario_fuentes.md`.

| Dataset | min(`:updated_at`) | max(`:updated_at`) | Lectura |
|---|---|---|---|
| `jbjy-vk9h` (control) | 2026-08-20T09:41:20.358Z | idéntico | Reemplazo total. **H2 intacto.** ⚠ Y el valor es **del día anterior**: ver abajo |
| Adiciones | 2024-10-04T21:14:28.562Z | 2026-08-21T14:28:52.934Z | Escritura incremental |
| Suspensiones | 2025-06-04T05:53:26.885Z | 2026-08-21T14:36:58.027Z | Escritura incremental |

Los máximos de los hermanos caen minutos antes de la corrida: **se alimentan en
continuo desde la plataforma transaccional**, no en un volcado nocturno.

⚠ **La fila de control decía más de lo que se le leyó.** El corte vivo de
`jbjy-vk9h` a las 09:37 del viernes 21 era el del jueves 20, cinco horas después
del final de la ventana de regeneración: **ese viernes la fuente no había
regenerado**. Se registró solo como confirmación de H2 —que lo es— y la
consecuencia sobre la cadencia quedó sin ver hasta el 28 de agosto. Es una de las
dos observaciones directas sobre las que se apoya H34.

⚠ **"Minutos antes de la corrida" tiene un contraejemplo y hay que anotarlo.**
El 28/08/2026 a las ~10:00 COT, el máximo de Adiciones era
`2026-08-28T09:51:29.013Z`, o sea de las 04:51 COT: **cinco horas antes**, no
minutos. Una observación no tumba H23 —el patrón de escritura continua se sostiene
sobre dos muestras y sobre los mínimos— pero "en continuo" no quiere decir "sin
pausas", y la afirmación no puede apoyarse en la distancia al reloj de la
consulta. Queda como verificación pendiente.

Los mínimos revelan otra cosa: Adiciones contiene filas con `fecharegistro`
de 2018 pero ninguna con `:updated_at` anterior a octubre de 2024. Hubo una
**carga masiva** en esa fecha y desde entonces las filas se tocan de a una.

 **`:updated_at` acá no es fecha de negocio**, es cuándo Socrata escribió
la fila. Sirve como watermark de ingesta y para nada más. No confundir con
`fecharegistro`.

 **Los hermanos sirven de testigo de la fuente principal.** Como escriben en
continuo y `jbjy-vk9h` no, comparar los dos separa "la fuente no regeneró" de
"la plataforma está caída". Se usó así el 26 y el 28 de agosto, y es lo que
descarta la explicación de la caída en H34. Es un uso que no estaba previsto
cuando se midió esto.

 **Esto NO prueba que sean append-only.** Es compatible con append puro,
con inserción más edición posterior, y con upsert de sincronización. Las
tres sirven como watermark; lo que rompería el esquema es el **borrado**,
invisible para cualquier watermark. Lo separa una consulta:
`$where=:created_at != :updated_at`. Pendiente.

 Un resultado append-only **no abre una opción de arquitectura nueva** para
D1, aunque lo parezca. Lo que aparece es una **restricción** sobre las tres
existentes. La capa raw tendría que alojar dos patrones de ingesta
incompatibles — `jbjy-vk9h` por comparación de snapshots (no tiene
watermark), los hermanos por watermark propio con `MERGE` sobre
`identificador` (no necesitan comparación en absoluto). Eso mueve peso en
contra de la opción B de D1: acoplar ingesta y detección de cambios en el
cargador estorba cuando una fuente necesita la primera y no la segunda.

### H24 — La regeneración de la fuente principal cae en una ventana de madrugada, y los hermanos van más frescos

**Corregido el 28/08/2026.** Este hallazgo decía: *"`jbjy-vk9h` se regeneró el
2026-08-20 a las 09:41 UTC = 04:41 hora de Colombia. Primer dato duro sobre
cuándo se rehace la fuente; define el `schedule` del DAG"*. Las dos frases hay
que retirarlas, por razones distintas.

**Lo que sí se sabe.** Hay tres regeneraciones fechadas, y son todo lo que hay:

| Corte | UTC | Hora de Colombia |
|---|---|---|
| 2026-08-18 | 09:22:15.735Z | **04:22** |
| 2026-08-20 | 09:41:20.358Z | **04:41** |
| 2026-08-25 | 09:05:54.277Z | **04:06** |

Se mueven en una **ventana de ~35 minutos** de la madrugada colombiana. 04:41 es
la más tardía de las tres, no un horario publicado ni un límite.

⚠ **No define ningún `schedule`, por dos motivos independientes.** Primero,
porque tres observaciones sobre una ventana móvil no fijan una hora: el margen
que uno crea tener puede no existir. Y segundo, y decisivo, porque **hay días sin
ninguna regeneración** (H34, en `00_inventario_fuentes.md`): ningún horario
acierta contra un evento que a veces no ocurre. → *El disparador es el corte de la
fuente y no el calendario: ver D11 en* `03_decisiones_capa_raw.md`.

Sigue sin saberse si la ventana de 35 minutos aguanta con más observaciones o es
un artefacto de tener solo tres.

**Desfase entre tablas:** los hermanos están más frescos que la fuente
principal. Una modificación aprobada hoy a las 14:00 ya está en Adiciones,
pero su efecto sobre `valor_del_contrato` no aparece en `jbjy-vk9h` hasta
la siguiente regeneración. Nota para el mart, no bug.

⚠ **El desfase no es "de hasta un día".** Así estaba escrito, y suponía cadencia
diaria. Con H34, la ventana en la que el evento existe y su consecuencia todavía
no dura **hasta la próxima regeneración**, que puede ser al día siguiente o al
cabo de varios días: el salto máximo observado es de cinco. El mart no puede
prometer que un evento de Adiciones se refleje en el contrato al día siguiente.

### H19 — La llave empata sin trabajo

`id_contrato` en Adiciones y Suspensiones es el mismo `CO1.PCCNTR.xxx` de
`jbjy-vk9h`. Contrasta con el problema de llaves que el inventario temía
para Procesos de Contratación (resuelto aparte por H14 vía `noticeUID`).

### H22 — Suciedad de texto: es la misma tubería de exportación

Los textos de ambos datasets traen tres deformaciones sistemáticas:

- **Comillas rotas:** `\u0093` `\u0094` `\u0092` son comillas tipográficas
 de Windows-1252 leídas con la codificación equivocada.
 `$15\u0092693.000` es `$15'693.000`.
- **Mayúsculas a medias:** `RESOLUCIoN`, `PRESTACIoN`, `DiAS`. Todo en
 mayúsculas salvo las vocales acentuadas, que quedaron minúsculas y sin
 tilde.
- **Comas convertidas en punto y coma**, casi con certeza para no romper el
 CSV de exportación.

Explica de dónde sale la basura que H6 detectó en `jbjy-vk9h`: mismo
origen. Si alguna vez se normaliza texto, la regla es una sola para todo el
ecosistema.

### H32 — Socrata no sirve para agregar sobre texto no indexado

Un `GROUP BY tipo` sobre el dataset completo revienta el timeout de 60 s. Con
troceado anual y 180 s, respondieron 2015-2022 y fallaron 2023-2026 — los
años de más volumen. Para esos hay que bajar a partición mensual.

Refuerza la decisión de keyset y de partir por rangos de fecha ya tomada
para el extractor: no es una preferencia estética, la API no aguanta otra
cosa.

---


---

## 5. Lo que el Estado publicó y dejó de publicar

### H21 — El historial existió y lo apagaron

Colombia publicó SECOP en **OCDS** (Open Contracting Data Standard), que
modela enmiendas explícitamente. El registro de Open Contracting
Partnership reporta:

- **3.008.861 enmiendas**
- Rango **enero 2011 – abril 2022**
- Marcado como **ya no actualizado por el publicador**
- Última obtención: marzo de 2023
- Prefijo OCID `ocds-k50g02`, licencia PDDL

La API de OCDS de la agencia devolvió 404 en la prueba.

Reformula el argumento del proyecto y lo mejora: **no es que el historial
nunca haya existido, es que Colombia lo publicaba y dejó de hacerlo hace
cuatro años.** La brecha es concreta y fechable.

### C4 — Cobertura real de los tableros oficiales

La ANCP-CCE mantiene ~20 visualizaciones en Power BI. Contra las siete
preguntas de negocio:

| Pregunta | ¿Cubierta? |
|---|---|
| 1. Qué entidades compran mi categoría | Sí — demanda y oferta, UNSPSC |
| 2. Proveedor dominante y concentración | Parcial |
| 3. Valor típico en mi sector | Sí |
| 4. Estacionalidad de apertura | Parcial, en informes cerrados |
| 5. Directa vs. licitación | Sí — batería de indicadores |
| 6. Quién extiende el plazo y cuántos días | **No** |
| 7. Cuánto cuesta esa extensión en pesos | **No** |

Todo lo oficial es **tablero, no plataforma**: Power BI embebido, sin API,
sin modelo expuesto, sin histórico consultable. Va al README como
"trabajo relacionado", que es una sección que casi ningún portafolio tiene.

---


---

## 6. Una regla de negocio que salió de la ley

### RN11 — Límite legal de adición

> El artículo 40 de la Ley 80 de 1993 establece que las adiciones no pueden
> superar el **50% del valor inicial** del contrato, expresado en salarios
> mínimos legales mensuales vigentes al momento de la suscripción.

Buena regla por tres razones: sale del dominio y no del esquema; solo se
puede testear si se conserva el valor inicial, o sea que **justifica la
tabla de snapshots desde la normativa**; y su incumplimiento es un hallazgo
publicable.

Ojo con la implementación: el límite es en **SMLMV al momento de la firma**,
no en pesos corrientes. Necesita una tabla de salario mínimo por año, que
hoy no existe en el modelo. Es una dimensión chica, o una columna de
`dim_tiempo`.

---


---

## 7. Una vía que se descartó

### Parsear el monto de `descripcion` — NO en la v1

Se puede sacar el monto del texto con expresiones regulares o con un modelo
de lenguaje. Se descarta:

- Viene en letras **y** en números, con separadores rotos (`\u0092`).
- Está mezclado con prórrogas de plazo en la misma frase.
- Lo redacta a mano cada una de miles de entidades.

Una tasa de acierto desconocida sobre la columna que sostiene la pregunta 7
es **peor que no tener la columna**: convierte un vacío honesto en un número
que nadie puede auditar. Va a "qué haría con más tiempo", junto al scraping
de PDFs, descartado por el mismo criterio.

---


---

## 8. Por qué no entran a la v1

Su valor ya se capturó como hallazgos —son material de README— sin cargar una
sola fila. Incorporarlos multiplicaría el tamaño del proyecto: Adiciones tiene
26.571.106 filas, **4,5 veces la fuente principal** (H29).

Y exigiría un **segundo patrón de ingesta**. Se actualizan en continuo y tienen
watermark propio (H23), a diferencia de la fuente principal, que se regenera
entera y de forma irregular (H2, H34). Serían dos mecanismos distintos
conviviendo en la misma capa raw. La v1 se define por hacer una cosa impecablemente.

---

## 9. Verificaciones pendientes

Script: `scripts/verificar_datasets_hermanos.py`. En orden de impacto:

| Fase | Pregunta | Qué decide | Estado |
|---|---|---|---|
| 0 | Esquema real de ambos datasets | Cierra H17 |  **hecho** — 5 y 7 columnas, sin medidas |
| 1 | Grano y volumen | Si `identificador` es llave |  **volumen hecho** (26.571.106, → H29); el grano sigue pendiente |
| 1b | Llave compuesta de Suspensiones | Idempotencia del `MERGE` | pendiente (→ H31) |
| 2 | Tipos de modificación | Estructura del dataset |  **hecho** — → H25 a H29, H32 |
| 3 | ¿`:updated_at` difiere? | Watermark |  **hecho** → H23, H24 |
| 3b | `:created_at != :updated_at` | Append puro vs. edición | pendiente |
| **3c** | **¿Los hermanos escriben todos los días?** | Si sirven como testigo de H34 | **pendiente** — hay un contraejemplo de "minutos antes de la corrida" el 28/08 |
| **V** | **¿Suspensiones es vista de Adiciones?** | Si sobra medio ecosistema |  **hecho** → H25, H33 |
| **T** | **Truncamiento de `fecharegistro` a escala** | Confirma H33 | **hecho** — 26.571.106 filas, síntoma y mecanismo → H33 |
| 4 | ¿Suspensiones conserva el fin viejo? | Confirma o mata H20 | **pendiente — LA PRÓXIMA** |
| 5 | Cobertura del cruce | Si son usables juntos | pendiente |
| 6 | Contraste con `dias_adicionados` | Si cuentan la misma historia | pendiente |

**La verificación T está hecha**, con seis consultas y no con las tres que
este documento planeaba. Las tres que faltaban no eran adorno y conviene
anotar por qué, porque el patrón se repite:

- **El denominador.** Un cero no significa nada sin saber sobre cuántas filas
  se tomó. `count(*)` fue lo que convirtió "no hay ninguna" en "no hay ninguna
  entre 26,5 millones", y de paso corrigió H29.
- **El segundo control.** El plan traía un solo control, sobre el día. Un
  control asimétrico deja abierto que el portal trunque meses en todas partes y
  días en ninguna.
- **La distribución.** Las dos consultas del plan prueban el **síntoma** —día y
  mes nunca superan 9—, no el **mecanismo**. El `GROUP BY` por día es lo que
  demuestra que los baldes 1 y 2 absorben once días cada uno.

Y una consulta que se corrió mal antes de correrse bien: para el mes el umbral
es `date_extract_m > 1`, no `> 3`. Los meses llegan hasta 12, así que solo
colapsan tres; asumir la simetría con el día es el error natural.

H20 sigue vivo y cambió de sentido: Suspensiones es la versión corregida
(H25), así que si conserva el `fecha_de_fin_del_contrato` viejo, es una
propiedad de la fuente buena, no de una vista sucia. Es la próxima.

La 3b sigue pendiente. Dos consultas por dataset:

```
?$select=count(*) as n&$where=:created_at != :updated_at
?$select=min(:created_at) as primera, max(:created_at) as ultima
```

---

## 10. Preguntas abiertas

1. ¿`SECOP II – Ejecución de Contratos` y `SECOP II – Rubros
 Presupuestales` aportan algo? No evaluados. El de Ejecución es el
 candidato obvio para la serie de pagos que hoy no existe.
2. ¿Por qué la ANCP-CCE dejó de publicar OCDS en abril de 2022? Si hay un
 anuncio público, es una cita valiosa para el README.
3. ¿Los archivos históricos de OCDS (2011–2022, ~5,4 GB en JSONL) sirven
 para backfillear algo? Probablemente no para SECOP II, pero conviene
 saberlo antes de escribir "el histórico no se puede backfillear" en las
 limitaciones.
4. Con RN11: ¿cuántos contratos superan el 50% legal? Es un hallazgo
 concreto con número, del tipo que pide el punto 8 de la definición de
 terminado.
5. ¿Qué tan buen testigo es Adiciones? (H34) Se lo usa para descartar que la
 fuente principal esté detenida por una caída de plataforma, y ese uso supone
 que el hermano escribe todos los días. Es plausible y no está medido. Si
 Adiciones también pausara los fines de semana, el testigo callaría justo
 cuando más falta hace.

---