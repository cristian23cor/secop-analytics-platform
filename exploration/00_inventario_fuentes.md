# Inventario de fuentes — SECOP

> Registro de evaluación de las fuentes candidatas del ecosistema SECOP.
> Cada hallazgo va acompañado de la consulta que lo demuestra, para que sea
> reproducible por cualquiera.
> Última actualización: 18 de agosto de 2026

**Endpoint base usado en todas las consultas:**

```
https://www.datos.gov.co/resource/jbjy-vk9h.json
```

---

## 1. SECOP II — Contratos Electrónicos ✅ ELEGIDA

### Ficha

| Campo | Valor |
|---|---|
| Identificador | `jbjy-vk9h` |
| Tipo | Dataset maestro (no vista derivada) |
| Publica | Agencia Nacional de Contratación Pública – Colombia Compra Eficiente |
| Filas | 5.958.553 |
| Columnas | 85 |
| Frecuencia declarada | Diaria |
| Rango temporal | 2015-06-11 a 2026-08-17 |
| Licencia | Datos abiertos (Ley 1712 de 2014) |

### Qué representa una fila

Un contrato estatal registrado en SECOP II, con su estado **actual**. No es un
registro histórico: la fila se sobrescribe cuando el contrato cambia.

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

**Implicación no obvia:** los contratos se modifican en la realidad (adiciones,
prórrogas, cesiones) pero no aparecen filas nuevas. Por lo tanto la fuente
**actualiza la fila en su lugar**. Esto lleva directo a H2.

---

### H2 — La fuente se reemplaza íntegramente cada noche ⚠️ CRÍTICO

**Por qué se validó:** sin una columna que indique qué cambió, no existe carga
incremental posible, y con ella se cae la mitad de la definición de terminado
del proyecto.

**Consulta 1 — ¿existen campos de sistema?**

```
?$select=:*,*&$limit=1
```

Resultado: existe `:updated_at`.

**Consulta 2 — ¿el campo distingue algo?**

```
?$select=min(:updated_at) as mas_viejo,max(:updated_at) as mas_nuevo
```

Resultado:

```json
{"mas_viejo":"2026-08-18T09:22:15.735Z","mas_nuevo":"2026-08-18T09:22:15.735Z"}
```

Mínimo y máximo idénticos **al milisegundo**, sobre 5,96 millones de filas.

**Conclusión:** Colombia Compra Eficiente no actualiza filas individuales;
reemplaza el dataset completo en una sola operación cada noche. `:updated_at` es
inútil como watermark.

**Consecuencias:**

1. **El historial de modificaciones no existe en el origen: se destruye cada
   noche.** Nadie puede consultar cuánto valía un contrato antes de una adición.
   Esta plataforma sí podrá, porque conservará lo que la fuente borra. El SCD
   tipo 2 deja de ser un requisito de tutorial y pasa a ser la razón de ser del
   proyecto.
2. La extracción incremental se basará en **ventanas de negocio** (fecha de firma
   + estado del contrato), no en una columna de auditoría.
3. Los contratos en estado terminal (Cerrado, terminado, Cancelado ≈ 43% del
   dataset) no pueden cambiar y no necesitan reextraerse a diario.

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

### H4 — Los nulos de fecha son todos pre-firma

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
técnico de partición como efecto colateral.

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

**Problema de modelado:** los valores pertenecen a dos ejes distintos.

- **Etapa del ciclo:** Borrador, En aprobación, enviado Proveedor, Aprobado,
  En ejecución, Cerrado, terminado
- **Qué le ocurrió al contrato:** Modificado, Prorrogado, cedido, Suspendido,
  Cancelado

Un contrato en ejecución que fue modificado tiene dos verdades, pero la columna
solo guarda una. `Modificado` (1,08M filas) probablemente esconde el estado real.

**Decisión:** derivar en la capa `intermediate` columnas propias
(`esta_vigente`, `fue_modificado`) con la lógica documentada. No usar
`estado_contrato` crudo como máquina de estados.

**Inconsistencia de formato:** `terminado`, `cedido` y `enviado Proveedor` no
respetan la capitalización de los demás, lo que sugiere orígenes o épocas
distintas dentro del sistema fuente. Se normaliza en `staging`.

**Anomalía menor:** `Borrador` suma 245.385 en total pero solo 244.947 tienen
fecha nula. Quedan **438 contratos en Borrador con fecha de firma**, lo cual es
contradictorio. No afecta el modelo (se excluyen igual), pero se documenta.

---

### H6 — Observaciones sobre el esquema

Obtenidas de inspeccionar una fila completa (`?$limit=1`).

**Todos los valores llegan como texto.** `"valor_del_contrato":"8959088"`,
`"es_pyme":"No"`. Se descargará todo como string a propósito: si pandas infiere
tipos, convierte a `NaN` los valores mal formados y esconde la suciedad.

**Nombres de columna deformados por Socrata:**

- Acentos reemplazados por `_`: `localizaci_n`, `liquidaci_n`,
  `g_nero_representante_legal`, `duraci_n_del_contrato`,
  `direcci_n_de_ejecuci_n_del_contrato`
- Nombres truncados: `justificacion_modalidad_de`, `valor_pendiente_de`

El renombrado a nombres limpios se hace en `staging` y funciona como
documentación.

**`urlproceso` es un objeto anidado**, no un escalar:
`{"url": "https://..."}`. Hay que extraer `urlproceso.url` explícitamente o
rompe la conversión a Parquet.

**Suciedad detectable en una sola fila:**

- `nit_entidad` sin dígito de verificación — requiere normalización
- `localizaci_n` con espacios dobles y redundante con `departamento` y `ciudad`
- `direcci_n_de_ejecuci_n_del_contrato` contiene saltos de línea embebidos
- `duraci_n_del_contrato` es texto libre: `"2 Mes(es)"`
- `orden` = "Nacional" para un hospital **departamental**; `rama` = "Corporación
  Autónoma" para una ESE. Estas categorías no son confiables tal como vienen.
- Los proveedores mezclan personas naturales (cédula) y empresas (NIT). Hay que
  decidir si se separan en la dimensión.

**Columna clave para el caso de uso comercial:**
`codigo_de_categoria_principal` = `"V1.80111701"` es un código **UNSPSC**, el
clasificador estándar internacional de bienes y servicios. Responde la pregunta
"¿qué entidades compran lo que yo vendo?". Requiere quitar el prefijo `V1.` y
decidir el nivel de agregación de la jerarquía.

**Desagregación de financiación:** `presupuesto_general_de_la_nacion_pgn`,
`sistema_general_de_participaciones`, `sistema_general_de_regal_as`,
`recursos_de_credito`, `recursos_propios`. En la fila inspeccionada suman
exactamente `valor_del_contrato`. Base de la regla de negocio RN1.

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

## Reglas de negocio para tests de dbt

Derivadas de los hallazgos, no inventadas para llenar el requisito.

| ID | Regla | Origen |
|---|---|---|
| RN1 | La suma de las fuentes de financiación iguala `valor_del_contrato` | H6 |
| RN2 | Ningún registro de la tabla de hechos tiene estado pre-firma | H4, H5 |
| RN3 | Ningún registro de la tabla de hechos tiene `fecha_de_firma` nula | H3, H4 |

---

## Preguntas abiertas — requieren el diccionario de datos oficial

1. **¿Qué es `valor_pendiente_de`?** El nombre está truncado y conviven
   `valor_pendiente_de_pago` y `valor_pendiente_de_ejecucion`. No se puede
   adivinar.
2. **¿`Cerrado` y `terminado` son sinónimos?** Son 1,69M y 774K filas. Si se
   tratan mal, cualquier cálculo de ejecución queda desviado.
3. **¿Qué miden `orden` y `rama`?** Los valores observados no coinciden con la
   intuición.
4. **¿Cómo se representan las modificaciones?** Si la fila se sobrescribe,
   ¿existe algún campo que conserve rastro de la adición o la prórroga?
   `dias_adicionados` sugiere que sí, parcialmente.

---

## 2. Otras fuentes del ecosistema — pendientes de evaluar

| Dataset | Etapa del ciclo | Decisión preliminar |
|---|---|---|
| SECOP II – Procesos de Contratación | Proceso previo al contrato | **Candidato v2** — son oportunidades abiertas, no contratos ya perdidos. Más valioso comercialmente. Fuera del alcance v1 por tener múltiples etapas y estados, y porque cruzarlo con contratos es un problema de llaves no trivial. |
| SECOP II – Facturas | Ejecución y pago | Por evaluar |
| Plan Anual de Adquisiciones | Planeación | Por evaluar |
| SECOP I – Proponentes | Registro de proveedores | Por evaluar |

**Advertencia sobre el catálogo:** muchos datasets de `datos.gov.co` son vistas
derivadas, no fuentes distintas. Si la ficha dice "Vista en función de X" o
"creado por un miembro del público", hay que ignorarlo e ir al maestro. Ejemplos
de vistas encontradas: "…PYMES", "…ACTIVOS", "…del Departamento de Sucre",
"…INVIAS".

**SECOP I vs SECOP II** son dos generaciones, no alternativas. SECOP I era un
tablón de anuncios (datos pobres, ya no crece); SECOP II es transaccional. Se usa
SECOP II.
