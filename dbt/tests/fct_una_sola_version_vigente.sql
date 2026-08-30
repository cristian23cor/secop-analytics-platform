{#-
  Cada contrato tiene exactamente una versión vigente.

  Con dos, cualquier consulta de "estado de hoy" devuelve dos filas por contrato y
  toda suma queda al doble. Con ninguna, el contrato desaparece de esa misma
  consulta. Los dos errores producen una tabla que se ve bien.

  Esto no mide la calidad del dato de la fuente, mide si el SCD2 quedó bien
  construido, y por eso es error y no aviso.

  Medido el 29/08/2026: cero, sobre 2.849.209 contratos y 2.881.640 versiones.
  La distribución es 2.816.778 contratos con una versión y 32.431 con dos.
-#}


{{ config(severity="error") }}

select
    id_contrato,
    count(*)                                                as versiones,
    sum(case when es_version_vigente then 1 else 0 end)      as vigentes,
    sum(case when observado_hasta is null then 1 else 0 end) as sin_cierre

from {{ ref("fct_contratos_snapshot") }}

group by id_contrato

having sum(case when es_version_vigente then 1 else 0 end) != 1
    or sum(case when observado_hasta is null then 1 else 0 end) != 1
