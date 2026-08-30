{#-
  Las cuentas del mart no pueden contradecirse entre sí.

  El modelo agrega desde dos lados: el denominador sale de `fct_contratos` y los
  numeradores de `int_cambios_por_columna`, unidos por `id_contrato`. Ese join es
  donde se rompe, y **se rompe hacia arriba**: si `int_cambios_por_columna`
  tuviera dos filas por contrato y columna, el `left join` multiplicaría y los
  contratos con extensión superarían a los observados.

  Un mart inflado no explota. Devuelve una tasa mayor que 1, que en un tablero se
  ve como "142% de los contratos fueron extendidos" — y alguien lo lee como un
  dato raro de la fuente en vez de como un bug.

  | motivo | qué significa |
  |---|---|
  | `mas contratos con extension que observados` | el join multiplicó filas |
  | `mas contratos con adicion que observados` | ídem |
  | `menos extensiones que contratos extendidos` | imposible: cada contrato extendido aporta al menos una |
  | `menos adiciones que contratos con adicion` | ídem |
  | `grano duplicado` | la celda entidad × familia × historia aparece dos veces |

  El último es el que cubre el otro join, el de `dim_entidad`: se une por
  `codigo_entidad` tomando la versión vigente, y si una entidad tuviera dos
  vigentes el mart duplicaría la celda. `dim_entidad_una_sola_version_vigente` ya
  lo vigila desde la dimensión; esto lo vigila desde el consumo, que es donde
  hace daño.

  Medido el 29/08/2026: cero incumplimientos sobre 118.264 celdas.
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
