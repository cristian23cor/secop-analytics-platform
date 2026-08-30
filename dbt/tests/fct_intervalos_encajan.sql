{#-
  Las versiones de un contrato encajan sin huecos ni solapes.

  D8 fijó intervalos **semiabiertos**: `observado_desde <= t < observado_hasta`. Esa
  semántica solo funciona si el `hasta` de una versión es exactamente el `desde` de la
  siguiente. Si sobra, hay un instante que no pertenece a ninguna versión; si falta,
  hay uno que pertenece a dos y cualquier suma lo cuenta dos veces. Es la trampa del
  `BETWEEN` que `01_modelo_dimensional.md` describe, vista desde el lado de los datos
  en vez del de la consulta.

  El test devuelve la fila que incumple con un `motivo`, porque los cuatro modos de
  fallo se arreglan distinto y agruparlos bajo "el SCD2 está mal" no ayuda a nadie.

  ## El caso que motivó escribirlo: `ancho cero`

  Un contrato observado dos veces con la misma `fecha_extraccion` —el flujo 1 por la
  mañana y el flujo 3 por la noche, habiendo cambiado en el medio— produce una versión
  con `observado_desde == observado_hasta`. Bajo la semántica semiabierta esa versión
  **no corresponde a ningún instante**: está en la tabla, la cuenta cualquier
  `count(*)`, y ninguna consulta puntual puede seleccionarla. Dos respuestas sobre el
  mismo contrato discrepan y nada falla.

  Verificado reproduciendo la lógica del modelo sobre un caso con empate, no deducido.
  La causa se comprueba aparte, en `fct_una_observacion_por_contrato_y_fecha`; este
  test cubre el síntoma, porque un intervalo de ancho cero podría llegar también por
  un cambio futuro en la ventana.

  ## Sobre la comparación

  `observado_desde` y `observado_hasta` son texto ISO (`2026-08-23`), no fechas. En ese
  formato el orden lexicográfico coincide con el cronológico, así que `<` y `=` dicen
  lo que parecen decir, acá y en Snowflake. Es la misma propiedad por la que el modelo
  ordena la ventana sin castear.

  ## Sobre `bandera incoherente`

  Hoy es tautológico: el modelo escribe `observado_hasta is null as es_version_vigente`
  en el mismo `select`, así que no puede fallar. Se escribe igual porque deja de serlo
  en cuanto el hecho pase a materialización incremental (D5), donde la bandera de una
  versión vieja se actualiza en una corrida distinta de la que la creó. Vale una línea
  y queda anotado que hoy no mide nada.

  Medido el 29/08/2026: cero incumplimientos sobre 2.881.640 versiones.
-#}

{{ config(severity="error") }}

with pares as (

    select
        id_contrato,
        version,
        observado_desde,
        observado_hasta,
        es_version_vigente,
        lead(observado_desde) over (
            partition by id_contrato order by version
        ) as desde_de_la_siguiente

    from {{ ref("fct_contratos_snapshot") }}

)

select
    id_contrato,
    version,
    observado_desde,
    observado_hasta,
    desde_de_la_siguiente,
    case
        when observado_hasta = observado_desde                then 'ancho cero'
        when observado_hasta < observado_desde                then 'invertido'
        when desde_de_la_siguiente is not null
             and observado_hasta is null                      then 'abierta con siguiente'
        when observado_hasta is distinct from
             desde_de_la_siguiente                            then 'hueco o solape'
        else                                                       'bandera incoherente'
    end as motivo

from pares

where observado_hasta <= observado_desde
   or (desde_de_la_siguiente is not null
       and observado_hasta is distinct from desde_de_la_siguiente)
   or es_version_vigente != (observado_hasta is null)
