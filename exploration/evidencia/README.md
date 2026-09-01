# Evidencia de la corrida en Snowflake

> Capturas del 1 de septiembre de 2026. La cuenta de Snowflake es de prueba y
> vence el **12 de septiembre de 2026**: después de esa fecha el objetivo
> `snowflake` no se puede ejecutar, y estas imágenes junto con
> [`../paridad_de_motores.md`](../paridad_de_motores.md) son lo que queda.
>
> El repositorio no depende de esa cuenta. La integración continua nunca la toca,
> `dbt build` apunta a DuckDB por defecto, y los tres macros con despacho por
> adaptador siguen en el código aunque nadie pueda ejecutarlos contra Snowflake.

---

## 1. El historial de consultas

`snowflake-historial-de-consultas.png`

La construcción corriendo de verdad, con los tiempos y las filas que devolvió
cada sentencia. Es la más fuerte de las cuatro porque no se puede fabricar sin la
plataforma delante: trae los identificadores de consulta que asigna Snowflake.

Lo que hay que mirar es la columna `ROWS`, porque se puede cotejar una por una
contra lo que afirma el README:

| | |
|---|---|
| `raw_observaciones` | 2.902.163 |
| `stg_contratos` | 2.902.163 |
| `fct_contratos_snapshot` | 2.881.640 |
| `dim_proveedor` | 930.071 |
| `dim_entidad` | 5.168 |
| `dim_geografia` | 958 |
| `dim_modalidad` | 232 |

Y las filas de `select count(*) as failures, count(*) != 0 as should_warn ...`
son los 46 tests de dbt ejecutándose allá. No se construyeron las tablas nomás:
se probaron.

## 2. Los once modelos, en sus tres esquemas

`snowflake-tablas-raw.png`, `snowflake-tablas-raw-staging.png`,
`snowflake-tablas-raw-intermediate.png`

Ocho marts en `RAW`, dos de staging en `RAW_STAGING` y uno intermedio en
`RAW_INTERMEDIATE`. Los once, cada uno en la capa que le corresponde.

La columna `BYTES` da un dato que no estaba medido en ningún otro lado:

```
RAW_STAGING        1.156,9 MB    las dos tablas anchas
RAW                  453,7 MB    los ocho marts
RAW_INTERMEDIATE       1,7 MB
                   -----------
                   ~1,61 GB      el modelo entero
```

Contra los 898 MB de la capa cruda comprimida en disco local.

Ahí también se ve por qué el hecho estrecho importó: `fct_contratos_snapshot`
ocupa 282 MB con 2,88 millones de versiones, y `stg_contratos` ocupa 594 MB con
2,90 millones de filas. Casi las mismas filas, menos de la mitad de espacio,
porque al hecho se le sacaron las 32 columnas cosméticas.

## 3. El stage, con el particionado intacto

`snowflake-stage-resumen.png`, `snowflake-stage-archivos.png`

Los **602 archivos** que subió `scripts/subir_raw_a_snowflake.py`, con la ruta
`flujo=/fecha_extraccion=/particion=` conservada. El particionado por
directorios estilo Hive sobrevivió el viaje desde el disco local, que es lo que
permite que el modelo frontera lea igual en los dos motores.

El reparto por flujo dice la tesis del proyecto en una pantalla:

```
flujo=refresco_de_vivos        893,0 MB
flujo=contratos_nuevos           1,5 MB
flujo=eventos_contractuales      1,4 MB
```

**El 99,7% del peso es el flujo 3.** Los pagos no dejan rastro en ninguna fecha
(H9), así que la única forma de detectarlos es volver a bajar 2,8 millones de
contratos enteros y compararlos. Ahí se va todo.

## 4. El mart respondiendo, con su limitación a la vista

`snowflake-mart-respondiendo.png`

Las diez entidades que más días extendieron, dentro de la población con historia
completa. Es la pregunta 6 del usuario objetivo, contestada en Snowflake.

Y muestra la honestidad del modelo mejor que cualquier párrafo. La tercera fila
dice:

```
Instituto Superior de Educacion Rural    1 contrato observado    1 extension    123 dias
```

Una extensión sobre **un** contrato observado: tasa del 100% con muestra de uno.
Y la primera fila es una entidad con 241 contratos observados y una sola
extensión, de 365 días. Sin la columna del denominador, cualquiera de las dos se
leería como un patrón.

La única fila con base suficiente es Cartagena: 435 contratos y 22 extensiones,
un 5%.

Eso es por qué el mart lleva `contratos_observados` al lado y por qué la palabra
"sistemáticamente" no se sostiene todavía: con 39 contratos en la población
medible, lo que hay son casos, no un patrón.

### Un detalle de lectura

`Instituto Superior de Educacion Rural` aparece dos veces, con 1 y con 3
contratos observados. **No es un duplicado.** El grano del mart es entidad ×
familia UNSPSC × historia completa, así que una entidad aparece una vez por cada
familia en la que contrata. Es el grano funcionando como está documentado en
`01_modelo_dimensional.md`.
