{#-
  Estos helper macros viven en `stg_contratos` porque representan la lógica de
  limpieza, mientras que `columnas_generado.sql` guarda la definición del esquema.
  Separarlos ayuda a mantener ambas capas estables: cuando una regla de limpieza
  cambia, no obliga a regenerar la lista de columnas ni a tocar el esquema.
-#}

{#-
  Esta limpieza quita los centinelas de texto antes del casteo.

  "No definido" y "No Definido" son nulos disfrazados en las dos capitalizaciones
  que usa la fuente (H6). Si no se eliminan antes del cast, un valor como "No
  definido" en una columna monetaria termina en un casting fallido que se cuenta
  como basura, aunque en realidad representa un nulo.

  La lista de centinelas viene desde `columnas.py`, y no se replica aquí para que
  agregar uno no requiera tocar dos archivos distintos.
-#}
{#- La forma con `namespace` aparece por un detalle de Jinja: una asignación hecha
    dentro de un bucle no sobrevive al ciclo si se usa un `set` simple. Cuando se
    escribió de la forma obvia, el macro devolvía el nombre de la columna sin
    transformar y los centinelas nunca se limpiaban. Esa falla quedó visible en el
    contador de castings fallidos, que registraba esos valores como basura aunque el
    problema venía del tratamiento previo. -#}
{% macro sin_centinela(columna) -%}
    {%- set ns = namespace(valor=columna) -%}
    {%- for centinela in centinelas() -%}
        {%- set ns.valor = "nullif(" ~ ns.valor ~ ", '" ~ centinela ~ "')" -%}
    {%- endfor -%}
    {{ ns.valor }}
{%- endmacro %}

{#-
  Este macro centraliza el tipo de cada columna. La misma decisión se usa tanto en
  la proyección como en el contador de fallos: si la clasificación se repitiera en
  varios puntos, podrían separarse las reglas y el contador mediría algo distinto a
  lo que realmente guarda la columna.

  Devuelve `none` para las columnas que se mantienen como texto.
-#}
{% macro tipo_de(columna) -%}
    {%- if columna in columnas_monetarias() -%}
        decimal(20, 2)
    {%- elif columna in columnas_fechas() -%}
        timestamp
    {%- elif columna in columnas_enteras() -%}
        integer
    {%- endif -%}
{%- endmacro %}

{#-
  Dos diferencias de dialecto que no se pueden esconder en el modelo frontera.

  D9 dice que un unico modelo toca los archivos, y eso se cumple. Lo que no dice,
  y hay que anotar, es que el modelo frontera no es el unico que habla dialecto:
  `stg_contratos` aplana `urlproceso` y le saca el `noticeUID`, y las dos cosas se
  escriben distinto en cada motor.

  Se resuelven aca, en un macro, y no con una rama dentro del modelo, por el mismo
  criterio con el que la clasificacion de columnas se genera en vez de copiarse: si
  la diferencia vive en un solo lugar, agregar un tercer motor es tocar ese lugar.
  Si vive esparcida entre modelos, cada uno se entera por su cuenta y alguno se
  olvida.

  El dia que dbt traiga macros multiplataforma para JSON y para expresiones
  regulares, estas dos desaparecen y los modelos no cambian.
-#}

{#-
  Un campo de un objeto JSON, como texto.

  DuckDB lo guarda como tipo JSON y se lee con `json_extract_string`; Snowflake lo
  guarda como VARIANT y se lee con la notacion de dos puntos. Las dos devuelven
  nulo si la clave no esta, que es lo que hace falta: la API omite las claves
  nulas (H6), asi que la ausencia es normal y no un error.
-#}
{% macro campo_json(columna, clave) -%}
    {%- if target.type == "snowflake" -%}
    {{ columna }}:{{ clave }}::varchar
    {%- else -%}
    json_extract_string({{ columna }}, '$.{{ clave }}')
    {%- endif -%}
{%- endmacro %}


{#-
  El primer grupo de captura de una expresion regular.

  `regexp_extract` en DuckDB toma el numero de grupo; `regexp_substr` en Snowflake
  necesita posicion, ocurrencia y la bandera 'e' para devolver el grupo en vez de
  la coincidencia entera. Olvidar esa bandera no falla: devuelve el texto completo,
  que es mas largo y parece un valor valido.
-#}
{% macro extraer_grupo(expresion, patron) -%}
    {%- if target.type == "snowflake" -%}
    regexp_substr({{ expresion }}, '{{ patron }}', 1, 1, 'e')
    {%- else -%}
    regexp_extract({{ expresion }}, '{{ patron }}', 1)
    {%- endif -%}
{%- endmacro %}


{#-
  Una de las 67 columnas de `datos`, tal como la lee cada motor.

  DuckDB abre el `STRUCT` con punto y ya viene tipada; Snowflake navega el VARIANT
  con dos puntos y hay que castear. La excepcion son las columnas anidadas, que en
  los dos motores se dejan como JSON para que `campo_json()` pueda entrar despues:
  castearlas a texto acá las convertiria en una cadena y el aplanado de `staging`
  dejaria de funcionar, sin fallar.

  Cuales son anidadas sale del macro generado desde `columnas.py`, no de una lista
  escrita acá. Hoy es una sola.
-#}
{% macro campo_de_datos(columna) -%}
    {%- if target.type == "snowflake" -%}
    datos:{{ columna }}{% if columna not in columnas_anidadas() %}::varchar{% endif %}
    {%- else -%}
    datos.{{ columna }}
    {%- endif -%}
{%- endmacro %}
