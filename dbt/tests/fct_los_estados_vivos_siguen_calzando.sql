{#-
  `motivo_de_cierre` compara el estado del contrato contra la lista de estados
  vivos que sale de `flujos.py`. Ese cruce puede romperse sin que nada falle, y de
  dos maneras: que staging empiece a normalizar la capitalización del estado, o que
  la fuente renombre alguno.

  Los dos casos dan el mismo síntoma. La columna se llena con un valor válido, los
  tipos calzan, la tabla se construye, y todas las versiones abiertas pasan a
  "fuera de observación".

  El umbral es un piso y no un valor calibrado: salta si eso supera la mitad de las
  versiones abiertas. Hoy es el 0,23% y una rotura lo lleva al 100%. Un umbral fino
  sobre un número que se mueve solo cantaría por motivos legítimos.

  Lo que no cubre: que falle uno solo de los cuatro estados. `Prorrogado` son 120
  versiones de 2,88 millones, así que perderlo no movería el porcentaje. Un test
  por estado sería lo correcto, pero `Prorrogado` puede llegar a cero
  legítimamente y ahí cantaría sin que nada esté roto. Queda anotado en vez de
  resuelto a medias.
-#}


{{ config(severity="error") }}

with abiertas as (

    select
        count(*) as versiones_abiertas,
        sum(case when motivo_de_cierre = 'fuera_de_observacion' then 1 else 0 end)
            as fuera_de_observacion
    from {{ ref("fct_contratos_snapshot") }}
    where observado_hasta is null

)

select
    versiones_abiertas,
    fuera_de_observacion,
    round(fuera_de_observacion * 100.0 / nullif(versiones_abiertas, 0), 2) as porcentaje

from abiertas

where fuera_de_observacion * 2 > versiones_abiertas
