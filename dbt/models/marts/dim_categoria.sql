{#
  Qué se compra. Es la dimensión que responde la pregunta 1 —"¿qué entidades compran
  lo que yo vendo?"— y la que le da el eje de categoría a las preguntas 6 y 7.

  `codigo_de_categoria_principal` es un código **UNSPSC**, el clasificador estándar
  internacional de bienes y servicios, con jerarquía de cuatro niveles:

      V1.80111701  ->  segmento 80  ->  familia 8011  ->  clase 801117  ->  producto 80111701

  ## La jerarquía se deriva del código; lo que falta son los nombres

  El inventario apunta al catálogo de colombiacompra.gov.co como dato externo
  pendiente, y sigue haciendo falta — pero solo para **traducir códigos a nombres**.
  La estructura está adentro del propio código y no necesita nada de afuera. Medido
  el 29/08/2026: 11.231 códigos distintos, **402 familias** y **57 segmentos**.

  Esa distinción importa porque cambia qué bloquea qué: sin el clasificador la
  pregunta 1 no se puede *leer*, pero sí se puede *agrupar*. El usuario objetivo
  —una empresa que le vende al Estado— conoce su propia familia UNSPSC.

  Cuando llegue el catálogo, se agrega como `seed` y esta tabla gana columnas de
  nombre sin que nada más cambie.

  ## `UNSPECIFIED` es un tercer centinela y no estaba documentado

  La columna tiene **cero nulos** y aun así 25.597 contratos —el 0,9%— traen el valor
  literal `UNSPECIFIED`. En inglés, así que la limpieza de `staging` no lo toca:
  `columnas.py` declara `CENTINELAS = ("No definido", "No Definido")` y nada más.
  Aparece **solo** en esta columna, comprobado sobre las 67.

  Es el mismo patrón que `localizaci_n`: cero nulos que no significan cero ausencias.
  Acá se marca con `es_sin_especificar` y los cuatro niveles quedan nulos, para que
  un `group by familia` no invente una familia llamada `ECIF`, que es lo que da
  `substr('UNSPECIFIED', 4, 4)`. Meterlo en `CENTINELAS` afectaría a las 67 columnas y
  obliga a reconstruir todo: es una decisión aparte, todavía sin tomar.

  ## Sin historia, y esta vez medido sobre la columna misma

  `codigo_de_categoria_principal` está clasificada como IMPOSIBLE, o sea que no
  debería cambiar nunca. Eso era una afirmación de diseño; ahora es una medición:
  **cero cambios** entre versiones consecutivas, sobre los 32.431 contratos que
  tienen más de una. Igual que `dim_modalidad` y `dim_geografia`.

  ⚠ La misma consulta encontró que **`fecha_de_inicio_del_contrato` sí cambia**, en
  685 contratos, y también está clasificada como IMPOSIBLE. Ver `01_modelo_dimensional.md`.
#}

{{ config(materialized="table") }}

{#- El centinela en inglés. Se nombra una vez acá porque es el único lugar del
    proyecto donde aparece; el día que se decida meterlo en `CENTINELAS` de
    `columnas.py`, esta constante desaparece y el `case` de abajo con ella. -#}
{%- set sin_especificar = "'UNSPECIFIED'" %}

with observaciones as (

    select
        codigo_de_categoria_principal,
        count(*) as contratos
    from {{ ref("fct_contratos") }}
    group by codigo_de_categoria_principal

)

select
    codigo_de_categoria_principal,

    codigo_de_categoria_principal = {{ sin_especificar }} as es_sin_especificar,

    {#- Los cuatro niveles, nulos cuando no hay código. El prefijo `V1.` ocupa
        tres caracteres, así que el segmento arranca en la posición 4.

        Se exige además la forma completa antes de cortar: `substr` sobre una
        cadena corta no falla, devuelve lo que haya. Ese es justamente el modo
        de fallo que produjo la familia inventada `ECIF`. -#}
    {%- for nivel, largo in [("segmento", 2), ("familia", 4), ("clase", 6), ("producto", 8)] %}
    case
        when codigo_de_categoria_principal like 'V1.________'
        then substr(codigo_de_categoria_principal, 4, {{ largo }})
    end as {{ nivel }}_unspsc,
    {%- endfor %}

    contratos

from observaciones
