{#
  Qué se compra. El código es UNSPSC, con una jerarquía de cuatro niveles metida
  adentro del propio valor:

      V1.80111701 -> segmento 80 -> familia 8011 -> clase 801117 -> producto 80111701

  Falta el catálogo oficial para traducir esos códigos a nombres, y eso cambia
  menos de lo que parece: sin él la pregunta 1 no se puede leer, pero sí agrupar.
  Son 402 familias y 57 segmentos. Cuando llegue, entra como seed y la dimensión
  gana columnas de nombre sin que nada más cambie.

  Sin historia, y esta vez medido: el código no cambió ni una vez entre versiones.

  25.597 contratos traen el literal UNSPECIFIED, que es un tercer centinela en
  inglés y que la limpieza de staging no toca. Por eso la columna reporta cero
  nulos y aun así el 0,9% no tiene categoría. Acá se marca aparte y los cuatro
  niveles quedan nulos, para que agrupar por familia no invente una llamada ECIF:
  que es lo que sale de cortar la palabra por donde iría el código.
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
