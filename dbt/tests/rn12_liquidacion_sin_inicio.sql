{#-
  RN12 — Un contrato no puede terminar una liquidación que nunca empezó.

  Devuelve las filas que INCUMPLEN, que es como dbt entiende un test singular.

  ## Nace con su incumplimiento medido: son 2

  Sobre 2.902.163 observaciones, medido el 28/08/2026. Eso es lo que la hace
  útil de una forma que las otras reglas todavía no: **falla, y falla por poco**.
  Un test que falla con dos casos se puede investigar; uno que falla con noventa
  mil se ignora.

  Por eso es `warn` y no `error`: los dos casos ya están en disco, y una suite
  roja permanente enseña a ignorar los tests. Lo que hay que vigilar no es que
  falle —ya sabemos que falla— sino que el número **cambie**.

  ## La regla es en un solo sentido, y eso importa

  35 contratos tienen inicio de liquidación sin fin, y eso NO incumple nada: son
  liquidaciones en curso. Escribir la regla simétrica —"si hay una, hay la
  otra"— la haría fallar 37 veces y confundiría lo normal con lo imposible.
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