# Paridad entre DuckDB y Snowflake

> Generado por `scripts/verificar_paridad_de_motores.py` el 2026-09-01.
> Los once modelos construidos por el mismo proyecto de dbt, sin un solo modelo
> duplicado, medidos en los dos motores.

**38 de 38 comprobaciones coinciden.**

| | Construido |
|---|---|
| DuckDB (`secop.duckdb`, fecha del archivo) | 2026-09-01 15:49 COT |
| Snowflake (`last_altered` de las tablas) | 2026-09-01 15:46 COT |

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
| filas | 2,902,163 | 2,902,163 | igual |
| huellas distintas | 2,902,163 | 2,902,163 | igual |
| huella minima | 0000153edaef26495fcd8315de620a10 | 0000153edaef26495fcd8315de620a10 | igual |
| huella maxima | fffff8fdbab43a799ebc1aa16a96f001 | fffff8fdbab43a799ebc1aa16a96f001 | igual |
| particiones | 5 | 5 | igual |

### `stg_contratos`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| filas | 2,902,163 | 2,902,163 | igual |
| contratos distintos | 2,849,209 | 2,849,209 | igual |
| castings fallidos | 1 | 1 | igual |
| sin ciudad | 611,751 | 611,751 | igual |

### `fct_contratos_snapshot`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| versiones | 2,881,640 | 2,881,640 | igual |
| contratos distintos | 2,849,209 | 2,849,209 | igual |
| suma de numeros de version | 2,914,071 | 2,914,071 | igual |
| versiones vigentes | 2,849,209 | 2,849,209 | igual |
| cerradas por version nueva | 32,431 | 32,431 | igual |
| fuera de observacion | 6,649 | 6,649 | igual |

### `fct_contratos`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| contratos | 2,849,209 | 2,849,209 | igual |
| entidades distintas | 5,162 | 5,162 | igual |
| suma de versiones observadas | 2,881,640 | 2,881,640 | igual |

### `int_cambios_por_columna`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| cambios | 88,395 | 88,395 | igual |
| columnas distintas que cambiaron | 28 | 28 | igual |
| suma de delta en dias | 259,841 | 259,841 | igual |
| columna mas temprana alfabeticamente | codigo_proveedor | codigo_proveedor | igual |

### `mart_extension_de_plazo`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| celdas | 118,264 | 118,264 | igual |
| contratos observados | 2,777,697 | 2,777,697 | igual |
| extensiones | 2,131 | 2,131 | igual |
| dias extendidos | 134,296 | 134,296 | igual |
| acortamientos | 96 | 96 | igual |
| dias acortados | -2,351 | -2,351 | igual |

### `dim_entidad`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| versiones | 5,168 | 5,168 | igual |
| entidades distintas | 5,162 | 5,162 | igual |

### `dim_proveedor`

| | DuckDB | Snowflake | |
|---|---:|---:|:--|
| versiones | 930,071 | 930,071 | igual |
| proveedores distintos | 929,946 | 929,946 | igual |

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
| codigos | 11,231 | 11,231 | igual |
| familias UNSPSC derivadas | 401 | 401 | igual |
| segmentos UNSPSC derivados | 56 | 56 | igual |
| sin especificar | 1 | 1 | igual |
