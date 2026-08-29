{#-
  RN12 — Un contrato no puede terminar una liquidación que nunca empezó.

  El test devuelve las filas que incumplen, como es la convención en dbt.

  ## Nace con su incumplimiento medido: son 2

  Sobre 2.902.163 observaciones, medido el 28/08/2026. Esta característica lo
  hace útil de una forma que las otras reglas todavía no: falla, pero falla
  por poco. Un test que falla con dos casos se puede investigar; uno que falla
  con noventa mil se ignora.

  Por eso es `warn` y no `error`: los dos casos ya están en disco, y una suite
  roja permanente enseña a ignorar los tests. Lo interesante aquí es que el
  número se mantenga estable o baje, no que el test empiece en verde.

  ## La regla es en un solo sentido, y eso es deliberado

  35 contratos tienen inicio de liquidación sin fin, que es el estado normal de
  una liquidación en curso. Si la regla fuera simétrica —"si hay una, hay la
  otra"— el test fallaría 37 veces y confundiría lo normal con lo imposible.
-#}

{{ config(severity="warn") }}

select
    id_contrato,
    ruta_fecha_extraccion,
    fecha_inicio_liquidacion,
    fecha_fin_liquidacion

from {{ ref("stg_contratos") }}

where fecha_fin_liquidacion is not null
  and fecha_inicio_liquidacion is null