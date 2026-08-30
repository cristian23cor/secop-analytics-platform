{#-
  Un contrato aparece a lo sumo una vez por `fecha_extraccion`.

  Es un supuesto que `fct_contratos_snapshot` tiene y que nadie había escrito. La
  ventana ordena por `observado_en`, que es la `fecha_extraccion` sacada de la ruta, y
  con dos filas del mismo contrato y la misma fecha pasan dos cosas, las dos malas:

  1. **`lead()` produce un intervalo de ancho cero.** La primera versión queda con
     `observado_desde == observado_hasta` y bajo la semántica semiabierta de D8 no
     corresponde a ningún instante. Lo detecta `fct_intervalos_encajan` desde el otro
     lado.
  2. **El orden entre las dos empatadas no está definido.** `order by observado_en` con
     un empate no fija cuál es la versión 1, así que cuál sobrevive como estado más
     reciente puede cambiar entre corridas o entre motores. Eso toca D5 directamente:
     la propiedad de que el hecho sea **función de raw** —se borra, se corre
     `dbt build --full-refresh` y sale idéntico— deja de estar garantizada.

  ## No es suciedad de la fuente ni un error de la ingesta

  Las dos escrituras son correctas. El índice de hashes es global por `id_contrato`
  (D3), así que un contrato que el flujo 1 trae por la mañana no se reescribe esa
  noche... salvo que haya cambiado en el medio, que es precisamente cuando queremos
  guardarlo. Raw hace lo correcto; lo que falla es que el modelo tiene como resolución
  temporal el día, y dos estados dentro de un día no se pueden representar.

  El mecanismo está vivo hoy: el 2026-08-22 ya hubo tres particiones bajo la misma
  `fecha_extraccion`, una por flujo.

  ## Por qué es `error` aunque el estado sea legítimo

  Porque el daño ocurre aguas abajo y en silencio: una versión que ninguna consulta
  puntual puede ver, dentro de la tabla que alimenta los marts. Entre parar la
  construcción y dejar pasar un número que nadie puede auditar, se para.

  Cuando salte, la decisión —cuál de las dos observaciones sobrevive, y de dónde sale
  el orden entre particiones del mismo día— se toma con el caso real delante. El
  manifiesto de D10 lleva marcas de tiempo por partición y es el candidato natural
  para dar ese orden, pero el modelo que lo lee todavía no existe.

  Medido el 29/08/2026: cero incumplimientos sobre 2.902.163 observaciones.
-#}

{{ config(severity="error") }}

select
    id_contrato,
    ruta_fecha_extraccion,
    count(*)                     as observaciones,
    count(distinct ruta_flujo)   as flujos_distintos,
    {#- `min` y `max` en vez de agregar los valores en una cadena: `string_agg` es de
        DuckDB y `listagg` de Snowflake, y D9 pide que nada motor-específico se cuele
        fuera del modelo frontera. Con dos filas alcanzan para ver de dónde vienen. -#}
    min(ruta_flujo)              as un_flujo,
    max(ruta_flujo)              as otro_flujo,
    min(ruta_particion)          as una_particion,
    max(ruta_particion)          as otra_particion

from {{ ref("stg_contratos") }}

group by id_contrato, ruta_fecha_extraccion

having count(*) > 1
