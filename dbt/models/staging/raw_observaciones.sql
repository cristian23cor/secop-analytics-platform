{#
  Este es el modelo frontera, el único de todo el proyecto que toca los archivos de
  `raw`. El resto lee esta tabla y no necesita saber que existe el disco físico. Es D9
  aplicado en SQL: cuando llegue el porte a Snowflake, este archivo y el de manifiestos
  se reescriben juntos y el resto no cambia.

  ## Por qué es tabla y no vista

  Es la excepción del `+materialized: view` de la carpeta. Como vista, cada modelo
  dependiente volvería a leer los 916 MB de `.jsonl.gz` desde cero. Como tabla, los
  archivos se leen una vez por corrida.

  ## Por qué el struct se declara y no se infiere

  Medido sobre 2,2 millones de filas con las 67 columnas reales y 3 GB de RAM, que es lo
  que tiene la máquina donde corre esto (R3):

  | Enfoque | Tiempo | Tabla | Memoria |
  |---|---|---|---|
  | `datos` como JSON, sin abrir | 46,6 s | 2.090 MB | pasa |
  | 67 llamadas a `json_extract_string` | n/a | n/a | se queda sin memoria |
  | STRUCT explícito desde `columnas.py` | 42,3 s | 224 MB | pasa |

  Guardar `datos` sin abrir escribe las 67 claves enteras en cada una de las 2,9 millones
  de filas, incluida `recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_`.
  Abrirlo con `json_extract_string` parsea el mismo documento 67 veces por fila y termina
  reventando.

  Que el struct sea explícito y no inferido es una decisión aparte, y esa importa más.
  `read_json_auto` deduce la forma de `datos` a partir de una muestra de filas, y la API
  omite las claves nulas (H6). Sobre una partición de prueba, el struct inferido no
  incluía `fecha_fin_liquidacion` porque ninguna fila muestreada la traía, y un modelo que
  la usara fallaría. Las columnas que arrancan nulas y después se llenan son justamente
  las materiales: las tres fechas de hito y `ultima_actualizacion`. El mismo error ya
  apareció con la sexta fuente de financiación de RN1: leímos "no apareció en la muestra"
  como "casi nunca tiene valor", y estaba en el 45% de los contratos.

  Por eso el struct viene de `struct_de_datos()`, generado desde `columnas.py`. Una clave
  ausente devuelve `NULL` en lugar de romper. Si la fuente agrega una clave que el struct
  no tiene, se ignora sin avisar, y eso es aceptable porque el `$select` ya pide solo
  estas 67 y quien detecta columnas nuevas es `validar_cobertura()`.

  ## Todo sale como texto, y hay que forzarlo

  D1 guarda todo como texto y deja los tipos para `stg_contratos`. Abrir una clave por
  nombre no es transformar, así que esto no rompe D1: no se castea, no se rellena, no se
  normaliza. Lo único que desaparece es la redundancia de los nombres de clave repetidos.

  Pero el lector castea por su cuenta: aun declarando `fecha_extraccion` como `VARCHAR`,
  DuckDB la devuelve como `DATE`. De ahí el cast explícito, para que la salida no dependa
  de las mañas del lector ni acá ni en Snowflake.

  ## El día del porte

  Snowflake no lee el disco. Hay que subir raw a un stage y cambiar la lectura por un
  `COPY INTO` o un `select ... from @stage`. La estructura de salida tiene que quedar
  idéntica, mismas columnas y mismos tipos. Si se respeta eso, `dbt run --target
  snowflake` no toca nada más.
#}

{#- La partición de la que vino cada observación. Se deriva de la ruta y no de los
    metadatos de la fila, a propósito: es la llave con la que se une la procedencia
    del manifiesto (D10). -#}

{#- Las 67 columnas, abiertas y como texto. La lista viene de `columnas.py` a través
    del macro generado: es lo que impide que el esquema que dbt lee se separe del que
    la ingesta le pide a la API. -#}

{{ config(materialized="table") }}

{#- Lo unico que cambia entre motores es de donde salen los archivos. La
    proyeccion de abajo es la misma para los dos, asi que las columnas y su orden
    coinciden por construccion y no porque alguien las haya mantenido a la par. -#}
with archivos as (

{%- if target.type == "snowflake" %}

    {#- Snowflake no lee el disco: los mismos `.jsonl.gz` viven en un stage
        interno, subidos con `scripts/subir_raw_a_snowflake.py`, que conserva la
        ruta `flujo=/fecha_extraccion=/particion=` porque de ahi salen las tres
        primeras columnas.

        `$1` es el documento JSON de cada linea, y el formato del stage ya declara
        gzip y una linea por fila. Las claves ausentes devuelven nulo, igual que
        el `STRUCT` de DuckDB: la API omite los nulos (H6) y eso no es un error. -#}
    select
        metadata$filename            as filename,
        $1:fecha_extraccion::varchar as fecha_extraccion,
        $1:flujo::varchar            as flujo,
        $1:hash::varchar             as hash,
        $1:datos                     as datos
    from @{{ var("stage_raw") }}

{%- else %}

    select
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

{%- endif %}

)

select
    {# La particion de la que vino cada observacion, sacada de la RUTA y no de
       los metadatos de la fila: si alguna vez las dos discreparan, queremos
       verlo. Los dos motores escriben distinto la extraccion de un grupo, y esa
       diferencia vive en un macro.

       Cierra sin guion a proposito: el guion se come el salto de linea y pega
       el `select` con lo que sigue. #}
    {{ extraer_grupo("filename", "flujo=([^/]+)") }}            as ruta_flujo,
    {{ extraer_grupo("filename", "fecha_extraccion=([^/]+)") }} as ruta_fecha_extraccion,
    {{ extraer_grupo("filename", "particion=([^/]+)") }}        as ruta_particion,

    {#- Metadatos de la envoltura, que la ingesta escribe FUERA del hash (I1). -#}
    cast(fecha_extraccion as varchar) as fecha_extraccion,
    cast(flujo as varchar)            as flujo,
    cast(hash as varchar)             as hash,

    {#- Las 67 columnas, como texto. La lista sale de `columnas.py` via el macro
        generado: es lo que impide que el esquema que dbt lee se separe del que la
        ingesta le pide a la API. -#}
    {%- for columna in columnas_extraidas() %}
    {{ campo_de_datos(columna) }} as {{ columna }}{{ "," if not loop.last }}
    {%- endfor %}

from archivos
