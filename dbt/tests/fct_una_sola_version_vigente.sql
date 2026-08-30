{#-
  Cada contrato tiene exactamente una versión vigente.

  Es el mismo invariante que `dim_entidad_una_sola_version_vigente` comprueba del lado
  de la dimensión, y por la misma razón: si el `lead()` quedara mal particionado habría
  contratos con dos versiones abiertas o con ninguna, y las dos cosas son invisibles
  hasta que alguien nota que un conteo no cuadra.

  Con dos vigentes, cualquier consulta que pida "el estado de hoy" devuelve dos filas
  por contrato y toda suma queda al doble. Con ninguna, el contrato desaparece de esa
  misma consulta sin que nada avise. Los dos errores son del tipo que este proyecto
  persigue: producen una tabla que se ve bien.

  ## Por qué es `error` y no `warn`

  Esto no mide la calidad del dato de la fuente, mide si el SCD2 quedó bien construido.
  Un incumplimiento es un fallo nuestro y tiene que detener la construcción, que es el
  criterio con el que están escritos los demás tests de esta carpeta.

  Medido el 29/08/2026: cero incumplimientos sobre 2.849.209 contratos y 2.881.640
  versiones. La distribución es 2.816.778 contratos con una versión y 32.431 con dos;
  ninguno con tres.
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
