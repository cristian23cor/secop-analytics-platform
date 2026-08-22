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
> Documentos hermanos: `00_inventario_fuentes.md` (la fuente principal, H1–H9) y
> `03_decisiones_capa_raw.md` (las decisiones de diseño D1–D8 e I1–I4).
>
> Última verificación contra la API: 21 de agosto de 2026.

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

`MODIFICACION GENERAL` son 1.767.394 filas — el 75% del dataset. Hay
adiciones de valor escondidas ahí en proporción desconocida. Usar el tipo
como filtro exhaustivo subestima por un factor que no se puede acotar.

Mismo patrón que la hipótesis descartada de `dias_adicionados > 0` para
identificar contratos `Modificado`: la categoría existe y no es exhaustiva.

**Lo que se creía ganar, y NO se gana:** se anotó que para 141.217
modificaciones habría "fecha exacta de una adición de valor sin parsear
texto". **H33 lo desmiente:** `fecharegistro` está corrupta y solo conserva
el año. Queda el evento y el año, nada más.

### H27 — El valor del contrato puede BAJAR

Existe `REDUCCION EN EL VALOR` (145 filas hasta 2022). La lógica de deltas
no puede asumir monotonía. RN5 protege `valor_pagado`, que es acumulado;
`valor_del_contrato` no tiene esa garantía.

### H28 — El centinela `No definido` también está en la columna que clasifica

Segundo tipo más frecuente de Adiciones: **515.151 filas, el 22%**. Con la
misma capitalización minúscula que H13. Un quinto de los eventos de
modificación no declara qué fueron.

### H29 — Volumen: Adiciones es más grande que la fuente principal

2.785.329 filas hasta diciembre de 2022, **sin** los cuatro años de mayor
volumen (2023-2026 no respondieron). El total supera con holgura los seis
millones, contra 5.958.553 de `jbjy-vk9h`.

Si estos datasets entran al alcance, no es agregar una fuente chica al
costado: es duplicar el proyecto. Decisión de alcance, no de ingeniería.

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

### H33 — `fecharegistro` de Adiciones está corrupta: mes y día truncados al primer dígito - 8/8, falta la prueba a escala

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

`21 → 2`, `15 → 1`, `12 → 1`, `09 → 9`. Ocho de ocho. **El año sobrevive
intacto.**

La columna está declarada `calendar_date`, parsea sin error, y un pipeline
la consumiría sin que nada fallara. **Fallo silencioso puro.**

**Consecuencias:**

- **Mata el consuelo de H26.** Para las 141.217 filas de `ADICION EN EL
 VALOR` se sabe el año y nada más. La fecha no es recuperable (la
 transformación es de muchos a uno) y esas filas no tienen dataset
 corregido, a diferencia de las suspensiones.
- **Salva los conteos de la FASE 2.** El año sobrevive, así que el troceado
 anual y los totales de H25 a H29 siguen siendo válidos.
- **Endurece la tesis del proyecto:** fechar una modificación en SECOP II
 solo es posible guardando cortes.

**Prueba a escala pendiente.** Si la hipótesis vale, en 2,7M de filas no
existe ninguna con día o mes mayor a 9:

```
.../cb9c-h8sn.json?$select=count(*) as n&$where=date_extract_d(fecharegistro) > 9
.../cb9c-h8sn.json?$select=count(*) as n&$where=date_extract_m(fecharegistro) > 9
```

Y el control, para descartar un defecto general del portal — tiene que dar
millones:

```
.../jbjy-vk9h.json?$select=count(*) as n&$where=date_extract_d(fecha_de_firma) > 9
```

Si el control diera cero, el problema no es de Adiciones sino de toda la
publicación, y cambia el proyecto entero.


---

## 4. Cómo se publican y se actualizan

### H23 — Los hermanos se actualizan en continuo; la fuente principal no - verificado

Resultado de la FASE 3:

| Dataset | min(`:updated_at`) | max(`:updated_at`) | Lectura |
|---|---|---|---|
| `jbjy-vk9h` (control) | 2026-08-20T09:41:20.358Z | idéntico | Reemplazo total. **H2 intacto.** |
| Adiciones | 2024-10-04T21:14:28.562Z | 2026-08-21T14:28:52.934Z | Escritura incremental |
| Suspensiones | 2025-06-04T05:53:26.885Z | 2026-08-21T14:36:58.027Z | Escritura incremental |

Los máximos caen minutos antes de la corrida: **se alimentan en continuo
desde la plataforma transaccional**, no en un volcado nocturno.

Los mínimos revelan otra cosa: Adiciones contiene filas con `fecharegistro`
de 2018 pero ninguna con `:updated_at` anterior a octubre de 2024. Hubo una
**carga masiva** en esa fecha y desde entonces las filas se tocan de a una.

 **`:updated_at` acá no es fecha de negocio**, es cuándo Socrata escribió
la fila. Sirve como watermark de ingesta y para nada más. No confundir con
`fecharegistro`.

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

### H24 — Hora de regeneración de la fuente principal, y desfase entre tablas

`jbjy-vk9h` se regeneró el 2026-08-20 a las **09:41 UTC = 04:41 hora de
Colombia**. Primer dato duro sobre *cuándo* se rehace la fuente; define el
`schedule` del DAG. Programarlo a medianoche leería el corte del día
anterior todas las noches.

Es una observación de una corrida, no un horario publicado. Confirmar en
dos o tres días distintos antes de escribirlo en Airflow.

**Desfase entre tablas:** los hermanos están más frescos que la fuente
principal. Una modificación aprobada hoy a las 14:00 ya está en Adiciones,
pero su efecto sobre `valor_del_contrato` no aparece en `jbjy-vk9h` hasta
la mañana siguiente. Ventana de hasta un día donde el evento existe y su
consecuencia todavía no. Nota para el mart, no bug.

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
sola fila. Incorporarlos duplicaría el tamaño del proyecto: Adiciones supera los
seis millones de filas, más que la fuente principal (H29).

Y exigiría un **segundo patrón de ingesta**. Se actualizan en continuo y tienen
watermark propio (H23), a diferencia de la fuente principal que se regenera
entera cada noche. Serían dos mecanismos distintos conviviendo en la misma capa
raw. La v1 se define por hacer una cosa impecablemente.

---

## 9. Verificaciones pendientes

Script: `scripts/verificar_datasets_hermanos.py`. En orden de impacto:

| Fase | Pregunta | Qué decide | Estado |
|---|---|---|---|
| 0 | Esquema real de ambos datasets | Cierra H17 |  **hecho** — 5 y 7 columnas, sin medidas |
| 1 | Grano y volumen | Si `identificador` es llave |  timeout, repetir |
| 1b | Llave compuesta de Suspensiones | Idempotencia del `MERGE` | pendiente (→ H31) |
| 2 | Tipos de modificación | Estructura del dataset |  **hecho** — → H25 a H29, H32 |
| 3 | ¿`:updated_at` difiere? | Watermark |  **hecho** → H23, H24 |
| 3b | `:created_at != :updated_at` | Append puro vs. edición | pendiente |
| **V** | **¿Suspensiones es vista de Adiciones?** | Si sobra medio ecosistema |  **hecho** → H25, H33 |
| **T** | **Truncamiento de `fecharegistro` a escala** | Confirma H33 sobre 2,7M filas | **pendiente — LA PRÓXIMA** |
| 4 | ¿Suspensiones conserva el fin viejo? | Confirma o mata H20 | pendiente |
| 5 | Cobertura del cruce | Si son usables juntos | pendiente |
| 6 | Contraste con `dias_adicionados` | Si cuentan la misma historia | pendiente |

**La verificación T va antes que lo demás.** Tres consultas de navegador:

```
.../cb9c-h8sn.json?$select=count(*) as n&$where=date_extract_d(fecharegistro) > 9
.../cb9c-h8sn.json?$select=count(*) as n&$where=date_extract_m(fecharegistro) > 9
.../jbjy-vk9h.json?$select=count(*) as n&$where=date_extract_d(fecha_de_firma) > 9
```

Las dos primeras deben dar **0**; la tercera, **millones**. Si la tercera
diera 0, el defecto no es de Adiciones sino de toda la publicación.

H20 sigue vivo pero cambió de sentido: Suspensiones es la versión corregida
(H25), así que si conserva el `fecha_de_fin_del_contrato` viejo, es una
propiedad de la fuente buena, no de una vista sucia.

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

---