{#-
  `fct_contratos` y `fct_contratos_snapshot` describen el mismo universo: uno con
  todas las versiones y el otro con la última. Los dos conjuntos de contratos
  tienen que ser **exactamente el mismo**, en los dos sentidos.

  ## Qué modo de fallo cubre

  `fct_contratos` une la versión vigente contra una agregación por contrato. Ese
  join es donde puede romperse:

  | motivo | qué pasó |
  |---|---|
  | `falta en el hecho` | un contrato del snapshot no llegó: el join lo perdió, o quedó sin versión vigente |
  | `sobra en el hecho` | un contrato que el snapshot no tiene |
  | `duplicado en el hecho` | el join multiplicó filas y toda suma quedó inflada |

  El tercero es el que importa y el que no avisa. `fct_contratos` es donde viven
  las medidas **aditivas** (§7): si un contrato aparece dos veces,
  `sum(valor_del_contrato)` lo cuenta dos veces y el número sale mal sin que nada
  falle. Es el mismo *fan-out* que §9 encontró al escribir la consulta de la
  pregunta 7, y la razón por la que existe `vigente_en()`.

  Un `unique` sobre `id_contrato` cubre solo el tercero. Los otros dos necesitan
  comparar contra el snapshot, que es de donde esta tabla sale.

  Medido el 29/08/2026: los tres dan cero. 2.849.209 contratos en las dos tablas,
  y la suma de `versiones_observadas` da 2.881.640, que es el total de versiones
  del snapshot.
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
