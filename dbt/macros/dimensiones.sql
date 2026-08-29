{#-
  Para unir un hecho con una dimensión con historia no alcanza la llave. Hay que
  comparar también contra el rango de validez:

      on  h.codigo_entidad = d.codigo_entidad
      and h.observado_desde >= d.observado_desde
      and (d.observado_hasta is null or h.observado_desde < d.observado_hasta)

  Escrito a mano, las dos últimas condiciones se olvidan fácil, y la unión no
  falla: duplica filas.

  En un caso de prueba con una entidad reclasificada, 3 filas del hecho salen 5 si
  unís solo por llave, porque cada una cruza con las dos versiones de la entidad.
  En los datos reales hay seis entidades reclasificadas y arrastran 20.675
  contratos, así que un "cuánto contrató cada entidad" devuelve casi el doble para
  esas seis.

  Para las otras 5.156 el resultado está bien, que es de donde sale el daño:
  probás con una entidad cualquiera, sale bien, y das la consulta por correcta.

  Uso:

      select f.*, e.nombre_entidad
      from {{ ref('fct_contratos_snapshot') }} f
      join {{ ref('dim_entidad') }} e
        on {{ vigente_en(
                 hecho='f', dimension='e', llave='codigo_entidad'
             ) }}

  Sirve para cualquier dimensión que use `observado_desde` / `observado_hasta`
  semiabiertos: `dim_proveedor`, `dim_modalidad`.
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
  La llave de `dim_modalidad` se calcula igual en los dos lados.

  La combinación de modalidad no tiene una columna que la identifique sola: la
  llave son los tres valores que la describen.

  Un `row_number()` sobre las 232 combinaciones sería más legible, pero depende
  del orden de las filas. Si ese orden cambia entre corridas, por concurrencia o
  por una versión distinta del motor o por el porte a Snowflake, el hecho apunta a
  la modalidad equivocada y ningún test lo nota: las llaves siguen uniendo, con la
  fila de al lado. Por eso va un hash de los valores, que es estable en cualquier
  motor.

  El cálculo vive en un macro porque se usa en `dim_modalidad` y en
  `fct_contratos_snapshot`. Misma razón por la que `columnas.py` tiene generador:
  una definición, no dos.

  El `coalesce` con un marcador y el separador que no aparece en los datos son el
  mismo cuidado que `canonicalizar()` en la ingesta. Sin eso, `('a', null)` y
  `('a', '')` dan la misma llave.
-#}

{% macro llave_de_modalidad() -%}
    md5(concat_ws(
        chr(31),
        coalesce(modalidad_de_contratacion,  chr(0) || 'NULO'),
        coalesce(tipo_de_contrato,           chr(0) || 'NULO'),
        coalesce(justificacion_modalidad_de, chr(0) || 'NULO')
    ))
{%- endmacro %}


{#-
  La llave de `dim_geografia` sigue el mismo criterio que `llave_de_modalidad()`:
  un hash determinista calculado tanto en la dimensión como en el hecho.

  `localizaci_n` no participa en esta clave, aunque describa el mismo lugar y tenga
  cero nulos frente a los 611.751 de `ciudad`. Esa decisión quedó respaldada por las
  tres mediciones documentadas en `dim_geografia`.
-#}

{% macro llave_de_geografia() -%}
    md5(concat_ws(
        chr(31),
        coalesce(departamento, chr(0) || 'NULO'),
        coalesce(ciudad,       chr(0) || 'NULO')
    ))
{%- endmacro %}