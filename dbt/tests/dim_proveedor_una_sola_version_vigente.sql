{#-
  Cada proveedor tiene exactamente una versión vigente.

  Mismo invariante que en `dim_entidad` y en el hecho. Acá importa más por
  escala: son 929.946 proveedores contra 5.162 entidades, así que un `lead()`
  mal particionado produciría cientos de miles de filas mal cerradas y ninguna
  consulta fallaría — solo devolverían de más.

  Medido el 28/08/2026: cero incumplimientos.
-#}

{{ config(severity="error") }}

select
    codigo_proveedor,
    count(*) as versiones,
    sum(case when es_version_vigente then 1 else 0 end) as vigentes

from {{ ref("dim_proveedor") }}

group by codigo_proveedor
having sum(case when es_version_vigente then 1 else 0 end) != 1