{#-
  Los dos hechos describen el mismo universo: uno con todas las versiones y el otro
  con la última. Los conjuntos de contratos tienen que ser el mismo, en los dos
  sentidos.

  El hecho actual une la versión vigente contra una agregación por contrato, y ese
  join es donde se rompe:

      falta en el hecho       un contrato del snapshot no llegó
      sobra en el hecho       un contrato que el snapshot no tiene
      duplicado en el hecho   el join multiplicó filas

  El tercero es el que importa y el que no avisa. Acá viven las medidas aditivas:
  si un contrato aparece dos veces, la suma del valor lo cuenta dos veces y el
  número sale mal sin que nada falle. Es el mismo fan-out que apareció al escribir
  a mano la consulta de la pregunta 7.

  Un unique sobre el identificador cubre solo el tercero. Los otros dos necesitan
  comparar contra el snapshot, que es de donde esta tabla sale.

  Medido el 29/08/2026: los tres dan cero, con 2.849.209 contratos en las dos
  tablas.
-#}


{{ config(severity="error") }}

select
    s.id_contrato,
    'falta en el hecho' as motivo

from (select distinct id_contrato from {{ ref("fct_contratos_snapshot") }}) s

where not exists (
    select 1 from {{ ref("fct_contratos") }} f
    where f.id_contrato = s.id_contrato
)

union all

select
    f.id_contrato,
    'sobra en el hecho' as motivo

from {{ ref("fct_contratos") }} f

where not exists (
    select 1 from {{ ref("fct_contratos_snapshot") }} s
    where s.id_contrato = f.id_contrato
)

union all

select
    id_contrato,
    'duplicado en el hecho' as motivo

from {{ ref("fct_contratos") }}

group by id_contrato

having count(*) > 1
