{#-
  `motivo_de_cierre` distingue `abierta` de `fuera_de_observacion` comparando
  `estado_contrato` contra `estados_vivos()`, que sale de `flujos.py`. Ese
  cruce puede romperse **sin que nada falle**, y de dos formas:

  1. **`staging` empieza a normalizar `estado_contrato`.** H5 dice que
     `terminado`, `cedido` y `enviado Proveedor` no respetan la capitalización de
     los demás, y que se normaliza en `staging`. Hoy no ocurre —comprobado el
     29/08/2026: en el hecho siguen en minúscula— pero está escrito como
     pendiente. El día que se haga, `'En ejecución'` deja de calzar con lo que
     sea que staging produzca, el `in (...)` no encuentra nada, y **todas** las
     versiones abiertas pasan a `fuera_de_observacion`.
  2. **La fuente renombra un estado.** El diccionario no enumera los valores
     posibles (H5), así que la única fuente de verdad sobre ellos son los datos.

  Los dos casos producen exactamente el mismo síntoma, y ninguno rompe nada: la
  columna se llena con un valor válido, los tipos calzan, la tabla se construye y
  el número está mal. Es la clase de fallo contra la que está diseñado todo este
  proyecto.

  ## El umbral es un piso, no un valor calibrado

  Se dispara si `fuera_de_observacion` pasa de la mitad de las versiones
  abiertas. Hoy es el **0,23%** — 6.649 de 2.849.209 — y una rotura del cruce lo
  lleva al 100%, no al 55%.

  Ese es el mismo criterio con el que se razona el umbral del canario del
  descarte en la ingesta: entre el nivel sano y el nivel roto hay un abismo, y un
  piso vive cómodo en el medio. Un umbral fino sobre un número que se mueve solo
  —contratos que van saliendo del universo vivo— cantaría por motivos legítimos y
  enseñaría a ignorarlo.

  ⚠ **Lo que este test NO cubre:** que uno solo de los cuatro estados deje de
  calzar. `Prorrogado` son 120 versiones de 2,88 millones, así que perderlo no
  movería el porcentaje de forma visible. Un test por estado sería lo correcto,
  pero `Prorrogado` puede llegar a cero legítimamente y ahí el test cantaría sin
  que nada esté roto. Queda anotado en vez de resuelto a medias.
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
