{#-
  RN12: Un contrato no puede terminar una liquidación que nunca empezó.

  El test devuelve los contratos que incumplen, como es la convención en dbt.

  ## Nace con su incumplimiento medido: son 2

  Sobre 2.902.163 observaciones, medido el 28/08/2026. Esta característica lo
  hace útil de una forma que las otras reglas todavía no: falla, pero falla
  por poco. Un test que falla con dos casos se puede investigar; uno que falla
  con noventa mil se ignora.

  Confirmado el 08/09/2026 sobre 3.369.650 observaciones: siguen siendo 2
  contratos y 2 filas. A diferencia de RN13, acá ninguno de los dos volvió a
  aparecer en un corte posterior.

  ## La regla es en un solo sentido, y eso es deliberado

  35 contratos tienen inicio de liquidación sin fin, que es el estado normal de
  una liquidación en curso. Si la regla fuera simétrica ("si hay una, hay la
  otra") el test fallaría 37 veces y confundiría lo normal con lo imposible.

  ## El grano es el CONTRATO, no la observación

  Hoy los dos números coinciden, y por eso mismo conviene fijar el grano ahora:
  un contrato que incumple y sigue vivo suma una fila en cada corte que lo
  vuelva a traer, sin que nada haya empeorado. Es lo que ya le pasó a RN13, que
  pasó de 7 filas a 9 sin un solo caso nuevo. Contar contratos hace que el
  número solo se mueva cuando aparece un incumplimiento de verdad.

  ## El ratchet

  `warn_if=">0"` mantiene el aviso a la vista: los dos casos ya están en disco
  y una suite roja permanente enseña a ignorar los tests.

  `error_if=">2"` es el trinquete. El tercer contrato con una liquidación que
  termina sin haber empezado rompe la construcción, en vez de sumarse en
  silencio a un aviso que nadie mira. Si alguna vez bajan, este número baja con
  ellos.
-#}

{{ config(severity="error", error_if=">2", warn_if=">0") }}

select
    id_contrato,
    count(*) as observaciones,
    min(ruta_fecha_extraccion) as visto_desde,
    max(ruta_fecha_extraccion) as visto_hasta,
    max(fecha_fin_liquidacion) as fecha_fin_liquidacion

from {{ ref("stg_contratos") }}

where fecha_fin_liquidacion is not null
  and fecha_inicio_liquidacion is null

group by id_contrato
