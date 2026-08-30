{#-
  Las versiones de un contrato encajan sin huecos ni solapes.

  Los intervalos son semiabiertos, así que el `hasta` de una versión tiene que ser
  exactamente el `desde` de la siguiente. Si sobra hay un instante que no
  pertenece a ninguna versión; si falta, hay uno que pertenece a dos y cualquier
  suma lo cuenta doble.

  Devuelve el motivo porque los cuatro modos de fallo se arreglan distinto:

      ancho cero              desde == hasta
      invertido               hasta < desde
      abierta con siguiente   cierra en nulo teniendo sucesora
      hueco o solape          el hasta no es el desde de la siguiente

  El que motivó escribirlo es el primero. Un contrato observado dos veces con la
  misma fecha de extracción produce una versión de ancho cero, que bajo la
  semántica semiabierta no corresponde a ningún instante: está en la tabla, la
  cuenta cualquier count(*), y ninguna consulta puntual puede seleccionarla. La
  causa se vigila aparte, en `fct_una_observacion_por_contrato_y_fecha`.

  `bandera incoherente` hoy no puede fallar, porque el modelo deriva la bandera de
  `observado_hasta` en el mismo select. Se escribe igual: deja de ser tautológico
  en cuanto el hecho pase a incremental, donde la bandera de una versión vieja se
  actualiza en otra corrida. Vale una línea y queda dicho que hoy no mide nada.

  Las dos fechas son texto ISO, no fechas. En ese formato el orden alfabético
  coincide con el cronológico, acá y en Snowflake.

  Medido el 29/08/2026: cero, sobre 2.881.640 versiones.
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
