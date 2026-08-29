{#
  EL MODELO FRONTERA. Es el único de todo el proyecto que toca los archivos.

  Todo lo demás lee ESTA tabla y no sabe que raw existe. Es D9 hecho SQL: el
  día del porte a Snowflake se reescribe este archivo —y el de los
  manifiestos— y ningún otro modelo se entera.

  ## Por qué tabla y no vista

  Es la única excepción al `+materialized: view` de la carpeta, y la razón es
  concreta: como vista, cada modelo que dependa de ella releería los 916 MB de
  `.jsonl.gz` desde cero. Como tabla, los archivos se leen una vez por corrida.

  ## El STRUCT se declara explícito, y eso resolvió dos problemas de una vez

  MEDIDO sobre 2,2 millones de filas con las 67 columnas reales y 3 GB de RAM,
  que es lo que tiene la máquina donde corre esto (R3):

  | Enfoque | Tiempo | Tabla | Memoria |
  |---|---|---|---|
  | `datos` como JSON, sin abrir | 46,6 s | 2.090 MB | pasa |
  | 67 × `json_extract_string` | — | — | **se queda sin memoria** |
  | **STRUCT explícito desde `columnas.py`** | **42,3 s** | **224 MB** | **pasa** |

  Nueve veces más chico y algo más rápido. Guardar `datos` sin abrir escribe las
  67 claves enteras en cada una de los 2,9 millones de filas, incluida
  `recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_`; abrirlo con
  `json_extract_string` parsea el mismo documento 67 veces por fila y revienta.

  ## Y el struct NO se infiere. Esto no es un detalle.

  `read_json_auto` deduce la forma de `datos` de una muestra de filas, y **la API
  omite las claves nulas** (H6). Comprobado: sobre una partición de prueba, el
  struct inferido no incluía `fecha_fin_liquidacion` porque ninguna fila
  muestreada la traía. Un modelo que la usara fallaría — y las que arrancan
  nulas y se llenan son justo las materiales: las tres fechas de hito y
  `ultima_actualizacion`.

  Es el mismo error que se cometió con la sexta fuente de financiación de RN1:
  "no apareció en la muestra" se leyó como "casi nunca tiene valor", y estaba en
  el 45% de los contratos.

  Por eso el struct viene de `struct_de_datos()`, generado desde `columnas.py`.
  Comprobado que hace lo correcto en los dos bordes: **una clave ausente devuelve
  NULL** en vez de romper, y una clave que la fuente agregue y el struct no tenga
  **se ignora en silencio** — aceptable porque el `$select` ya pide solo estas 67
  y quien detecta columnas nuevas es `validar_cobertura()`.

  ## Todo sale como texto, y hay que forzarlo

  D1 guarda todo como texto y deja los tipos para `stg_contratos`. Abrir una
  clave por nombre no es transformar, así que esto no viola D1: no se castea, no
  se rellena, no se normaliza. Lo único que desaparece es la redundancia de los
  nombres de clave repetidos.

  Pero el lector castea por su cuenta: **aun declarando `fecha_extraccion` como
  VARCHAR, DuckDB la devuelve como DATE.** De ahí el cast explícito — es lo que
  hace que la salida no dependa de las mañas del lector, ni acá ni en Snowflake.

  ## El día del porte

  Snowflake no lee el disco. Hay que subir raw a un stage y cambiar la lectura
  por un `COPY INTO` o un `select ... from @stage`. La estructura de salida de
  este modelo tiene que quedar idéntica: mismas columnas, mismos tipos. Si se
  respeta eso, `dbt run --target snowflake` no toca nada más.
#}

{{ config(materialized="table") }}

with archivos as (

    select
        -- `filename` da la ruta del archivo de cada fila. Es lo que permite
        -- reconstruir la partición sin confiar en las columnas de adentro: si
        -- alguna vez la ruta y el contenido discreparan, queremos verlo.
        filename,
        fecha_extraccion,
        flujo,
        hash,
        datos

    from read_json(
        '{{ var("ruta_raw") }}/**/*.jsonl.gz',
        format = 'newline_delimited',
        filename = true,
        columns = {
            fecha_extraccion: 'VARCHAR',
            flujo: 'VARCHAR',
            hash: 'VARCHAR',
            datos: '{{ struct_de_datos() }}'
        }
    )

)

select
    -- La partición de la que vino cada observación. Se deriva de la ruta y no
    -- de los metadatos de la fila, a propósito: es la llave con la que se une
    -- la procedencia del manifiesto (D10).
    regexp_extract(filename, 'flujo=([^/]+)', 1)            as ruta_flujo,
    regexp_extract(filename, 'fecha_extraccion=([^/]+)', 1) as ruta_fecha_extraccion,
    regexp_extract(filename, 'particion=([^/]+)', 1)        as ruta_particion,

    -- Metadatos de la envoltura, que raw escribe FUERA del hash (I1).
    cast(fecha_extraccion as varchar) as fecha_extraccion,
    cast(flujo as varchar)            as flujo,
    cast(hash as varchar)             as hash,

    -- Las 67 columnas, abiertas y como texto. La lista viene de
    -- `columnas.py` vía el macro generado: es lo que impide que el esquema
    -- que dbt lee se separe del que la ingesta le pide a la API.
    {% for columna in columnas_extraidas() -%}
    datos.{{ columna }} as {{ columna }}{{ "," if not loop.last }}
    {% endfor %}

from archivos