{#-
  El mart no pierde ni inventa contratos.

  Los contratos observados sumados sobre todas las celdas tienen que dar los que el
  hecho tiene firmados desde 2020, que es el recorte que este mart declara.

  Es el control del denominador, y el denominador es lo que sostiene la palabra
  "sistemáticamente".

  El otro test mira cada celda por dentro. Éste mira el total, y atrapa lo que una
  celda sana no delata: que falten contratos enteros. El camino concreto es el join
  contra la dimensión de categoría, que es un join y no un left join a propósito
  (la dimensión se construye desde el mismo hecho, así que tiene que cubrirlo
  entero). Si alguna vez dejara de cubrirlo, los contratos sin categoría
  desaparecerían en silencio y todas las tasas subirían, porque el denominador
  sería más chico.

  Medido el 29/08/2026: 2.777.697 en las dos puntas.
-#}


{{ config(severity="error") }}

with cuentas as (

    select
        (select sum(contratos_observados)
         from {{ ref("mart_extension_de_plazo") }})            as en_el_mart,
        (select count(*)
         from {{ ref("fct_contratos") }}
         where fecha_de_firma >= '2020-01-01')                 as en_el_hecho

)

select
    en_el_mart,
    en_el_hecho,
    en_el_mart - en_el_hecho as diferencia

from cuentas

where en_el_mart is distinct from en_el_hecho
