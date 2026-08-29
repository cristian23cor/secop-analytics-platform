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