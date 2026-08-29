{#-
  Unir un hecho con una dimensión con historia, sin equivocarse.

  ## Por qué existe este macro

  La unión correcta es por llave **y** rango de fechas:

      on  h.codigo_entidad = d.codigo_entidad
      and h.observado_desde >= d.observado_desde
      and (d.observado_hasta is null or h.observado_desde < d.observado_hasta)

  Escribirla a mano en cada consulta es pedir que alguien olvide las dos últimas
  líneas. Y olvidarlas **no falla**: duplica filas.

  Medido sobre datos de prueba con una entidad reclasificada: 3 filas del hecho
  se convierten en 5 al unir solo por llave, porque cada una se cruza con las
  dos versiones de su entidad. Sobre los datos reales, las seis entidades
  reclasificadas arrastran 20.675 contratos, así que una consulta de "cuánto
  contrató cada entidad" devolvería casi el doble para esas seis.

  ⚠ **Y para las otras 5.156 entidades el resultado sería idéntico.** El error
  es silencioso en el 99,9% de los casos, que es justo lo que lo hace
  peligroso: se prueba con una entidad cualquiera, sale bien, y se da por buena
  la consulta.

  ## Uso

      select f.*, e.nombre_entidad
      from {{ ref('fct_contratos_snapshot') }} f
      join {{ ref('dim_entidad') }} e
        on {{ vigente_en(
                 hecho='f', dimension='e', llave='codigo_entidad'
             ) }}

  Sirve para cualquier dimensión con historia que use la convención de
  `observado_desde` / `observado_hasta` semiabiertos: `dim_proveedor`,
  `dim_modalidad` y las que vengan.
-#}

{% macro vigente_en(hecho, dimension, llave, fecha="observado_desde") -%}
    {{ hecho }}.{{ llave }} = {{ dimension }}.{{ llave }}
    and {{ hecho }}.{{ fecha }} >= {{ dimension }}.observado_desde
    and (
        {{ dimension }}.observado_hasta is null
        or {{ hecho }}.{{ fecha }} < {{ dimension }}.observado_hasta
    )
{%- endmacro %}


{#-
  La llave de `dim_modalidad`, calculada igual en los dos lados.

  ## Por qué un hash y no un número secuencial

  La combinación de modalidad no tiene una columna que la identifique: la llave
  **son** los tres valores. Hay que fabricarla, y hay dos formas.

  Un `row_number()` sobre las 232 combinaciones sería más legible y **dependería
  del orden de las filas**. Si ese orden cambiara entre corridas —por
  concurrencia, por una versión distinta del motor, por el porte a Snowflake—
  el hecho apuntaría a la modalidad equivocada y **ningún test lo notaría**: las
  llaves seguirían uniendo, solo que con la fila de al lado.

  Un hash de los valores es el mismo siempre y en cualquier motor. Ilegible, y
  correcto.

  ## Por qué vive en un macro

  Se calcula en dos lugares —`dim_modalidad` y `fct_contratos_snapshot`— y dos
  definiciones de lo mismo se separan. Es la lección del generador de
  `columnas.py` y la del conteo de tests: **una definición, no dos.**

  El `coalesce` con un marcador y el separador que no aparece en los datos son el
  mismo cuidado que `canonicalizar()` tiene en la ingesta: sin ellos,
  `('a', null)` y `('a', '')` producirían la misma llave.
-#}

{% macro llave_de_modalidad() -%}
    md5(concat_ws(
        chr(31),
        coalesce(modalidad_de_contratacion,  chr(0) || 'NULO'),
        coalesce(tipo_de_contrato,           chr(0) || 'NULO'),
        coalesce(justificacion_modalidad_de, chr(0) || 'NULO')
    ))
{%- endmacro %}