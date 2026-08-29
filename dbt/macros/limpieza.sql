{#-
  Ayudantes de `stg_contratos`. Escritos a mano, a diferencia de
  `columnas_generado.sql`: acá vive la LÓGICA de limpieza, allá los DATOS del
  esquema. Mezclarlas obligaría a regenerar el archivo cada vez que cambia una
  regla que no tiene nada que ver con las columnas.
-#}

{#-
  El valor sin el centinela de texto.

  "No definido" y "No Definido" son nulos disfrazados, en las dos
  capitalizaciones que la fuente usa (H6). Se limpian ANTES de castear: si no,
  "No definido" en una columna monetaria fallaría el cast y contaría como
  basura, cuando en realidad es un nulo.

  La lista de centinelas viene de `columnas.py` y no está escrita acá, para que
  agregar uno no requiera tocar dos archivos.
-#}
{#- ⚠ `namespace` y no un `set` suelto: en Jinja, una asignación hecha DENTRO
    de un bucle no sobrevive al bucle. Escrito de la forma obvia, este macro
    devolvía el nombre de la columna pelado y los centinelas no se limpiaban
    nunca — y el modelo seguía compilando y corriendo. Lo delató el contador de
    castings fallidos, que los contó como basura porque el `try_cast` los
    volvía nulos por la vía equivocada. -#}
{% macro sin_centinela(columna) -%}
    {%- set ns = namespace(valor=columna) -%}
    {%- for centinela in centinelas() -%}
        {%- set ns.valor = "nullif(" ~ ns.valor ~ ", '" ~ centinela ~ "')" -%}
    {%- endfor -%}
    {{ ns.valor }}
{%- endmacro %}

{#-
  El tipo al que va cada columna. Un solo lugar donde se decide, usado tanto
  por la proyección como por el contador de fallos: si estuvieran escritos por
  separado, podrían discrepar y el contador mediría otra cosa que lo que la
  columna guarda.

  Devuelve `none` para las que quedan como texto.
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