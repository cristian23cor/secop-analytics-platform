# Paridad entre DuckDB y Snowflake

> Generado por `scripts/verificar_paridad_de_motores.py` el 2026-09-08.
> Los once modelos construidos por el mismo proyecto de dbt, sin un solo modelo
> duplicado, medidos en los dos motores.

**38 de 38 comprobaciones coinciden.**

| | Construido |
|---|---|
| DuckDB (`secop.duckdb`, fecha del archivo) | 2026-09-08 15:57 COT |
| Snowflake (`last_altered` de las tablas) | 2026-09-08 16:21 COT |

Las dos en hora colombiana: vienen de relojes distintos y se normalizan antes de
mostrarlas.

Esas dos fechas son lo primero que hay que mirar. Si estan lejos una de otra, el
informe compara dos fotos de momentos distintos y no dice nada sobre el codigo de
hoy.

Contar filas no alcanza: dos tablas del mismo tamano pueden tener contenidos
distintos. Estas comprobaciones apuntan a donde los motores hablan dialectos
distintos, que es donde una divergencia aparecería: las huellas de la ingesta,
los castings, las ventanas del SCD2, los `datediff` de la capa intermedia, la
jerarquia UNSPSC derivada con `substr`, y los cuatro contadores de signo del mart.

Los tres macros con despacho por adaptador (`campo_json`, `extraer_grupo`,
`campo_de_datos`) son los unicos lugares del proyecto que conocen el motor. Todo
lo demas es el mismo SQL.

### `raw_observaciones`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| filas | 3,369,650 | 3,369,650 | igual |
| huellas distintas | 3,363,463 | 3,363,463 | igual |
| huella minima | 0000153edaef26495fcd8315de620a10 | 0000153edaef26495fcd8315de620a10 | igual |
| huella maxima | fffff8fdbab43a799ebc1aa16a96f001 | fffff8fdbab43a799ebc1aa16a96f001 | igual |
| particiones | 6 | 6 | igual |

### `stg_contratos`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| filas | 3,369,650 | 3,369,650 | igual |
| contratos distintos | 2,896,782 | 2,896,782 | igual |
| castings fallidos | 1 | 1 | igual |
| sin ciudad | 827,485 | 827,485 | igual |

### `fct_contratos_snapshot`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| versiones | 3,148,643 | 3,148,643 | igual |
| contratos distintos | 2,896,782 | 2,896,782 | igual |
| suma de numeros de version | 3,410,297 | 3,410,297 | igual |
| versiones vigentes | 2,896,782 | 2,896,782 | igual |
| cerradas por version nueva | 251,861 | 251,861 | igual |
| fuera de observacion | 3,882 | 3,882 | igual |

### `fct_contratos`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| contratos | 2,896,782 | 2,896,782 | igual |
| entidades distintas | 5,169 | 5,169 | igual |
| suma de versiones observadas | 3,148,643 | 3,148,643 | igual |

### `int_cambios_por_columna`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| cambios | 863,951 | 863,951 | igual |
| columnas distintas que cambiaron | 28 | 28 | igual |
| suma de delta en dias | 5,962,413 | 5,962,413 | igual |
| columna mas temprana alfabeticamente | codigo_proveedor | codigo_proveedor | igual |

### `mart_extension_de_plazo`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| celdas | 121,836 | 121,836 | igual |
| contratos observados | 2,825,266 | 2,825,266 | igual |
| extensiones | 36,558 | 36,558 | igual |
| dias extendidos | 3,575,988 | 3,575,988 | igual |
| acortamientos | 694 | 694 | igual |
| dias acortados | -23,738 | -23,738 | igual |

### `dim_entidad`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| versiones | 5,244 | 5,244 | igual |
| entidades distintas | 5,169 | 5,169 | igual |

### `dim_proveedor`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| versiones | 937,900 | 937,900 | igual |
| proveedores distintos | 937,019 | 937,019 | igual |

### `dim_modalidad`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| filas | 232 | 232 | igual |

### `dim_geografia`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| filas | 958 | 958 | igual |

### `dim_categoria`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| codigos | 11,279 | 11,279 | igual |
| familias UNSPSC derivadas | 401 | 401 | igual |
| segmentos UNSPSC derivados | 56 | 56 | igual |
| sin especificar | 1 | 1 | igual |
