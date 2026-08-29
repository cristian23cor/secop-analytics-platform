{#-
  Cada entidad tiene exactamente una versión vigente.

  Mismo invariante que en el hecho y por la misma razón: si el `lead()`
  estuviera mal particionado, habría entidades con dos versiones vigentes o con
  ninguna, y las dos cosas son invisibles hasta que alguien nota que los
  conteos no cuadran.

  Con dos vigentes, además, la unión por rango duplicaría — que es exactamente
  lo que `dim_entidad_no_duplica_al_unir` intenta evitar desde el otro lado.

  Medido el 28/08/2026: cero incumplimientos sobre 5.162 entidades.
-#}

{{ config(severity="error") }}

select
    codigo_entidad,
    count(*) as versiones,
    sum(case when es_version_vigente then 1 else 0 end) as vigentes

from {{ ref("dim_entidad") }}

group by codigo_entidad
having sum(case when es_version_vigente then 1 else 0 end) != 1