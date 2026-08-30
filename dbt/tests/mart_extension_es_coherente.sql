{#-
  Las cuentas del mart no pueden contradecirse entre sí.

  El modelo agrega desde dos lados: el denominador sale del hecho y los numeradores
  de la capa de cambios, unidos por contrato. Ese join se rompe hacia arriba: si
  la capa de cambios tuviera filas repetidas, los contratos con extensión
  superarían a los observados.

  Un mart inflado no explota. Devuelve una tasa mayor que uno, que en un tablero se
  ve como "142% de los contratos fueron extendidos", y alguien lo lee como un dato
  raro de la fuente en vez de como un bug.

  El último motivo, el grano duplicado, cubre el otro join: el de la dimensión de
  entidad, que toma la versión vigente. Si una entidad tuviera dos vigentes, el
  mart duplicaría la celda. La dimensión ya lo vigila de su lado; esto lo vigila
  desde el consumo, que es donde hace daño.

  Medido el 29/08/2026: cero, sobre 118.264 celdas.
-#}


{{ config(severity="error") }}

select
    codigo_entidad,
    familia_unspsc,
    historia_completa,
    'mas contratos con extension que observados' as motivo
from {{ ref("mart_extension_de_plazo") }}
where contratos_con_extension > contratos_observados

union all

select codigo_entidad, familia_unspsc, historia_completa,
    'mas contratos con adicion que observados'
from {{ ref("mart_extension_de_plazo") }}
where contratos_con_adicion > contratos_observados

union all

select codigo_entidad, familia_unspsc, historia_completa,
    'menos extensiones que contratos extendidos'
from {{ ref("mart_extension_de_plazo") }}
where extensiones < contratos_con_extension

union all

select codigo_entidad, familia_unspsc, historia_completa,
    'menos adiciones que contratos con adicion'
from {{ ref("mart_extension_de_plazo") }}
where adiciones < contratos_con_adicion

union all

{# `group by` agrupa los nulos entre sí, que es lo que hace falta acá:
   `familia_unspsc` es nula en los contratos sin categoría y esas celdas también
   tienen que ser únicas. Un `unique` sobre una concatenación se equivocaría con
   esos nulos.

   Sin guiones en las llaves del comentario: se comen los saltos de línea de los
   dos lados y pegan `union all` con el `select`. #}
select codigo_entidad, familia_unspsc, historia_completa, 'grano duplicado'
from {{ ref("mart_extension_de_plazo") }}
group by codigo_entidad, familia_unspsc, historia_completa
having count(*) > 1
