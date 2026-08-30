{#-
  Un contrato aparece a lo sumo una vez por fecha de extracción.

  Es un supuesto que el snapshot tiene y que nadie había escrito. La ventana ordena
  por fecha de extracción, y con dos filas del mismo contrato y la misma fecha
  pasan dos cosas: la primera versión queda con un intervalo de ancho cero, y el
  orden entre las dos empatadas no está definido, así que cuál sobrevive como
  estado más reciente puede cambiar entre corridas o entre motores. Lo segundo
  rompe la propiedad de que el hecho sea función de raw.

  No es suciedad de la fuente ni un error de la ingesta. El índice de hashes es
  global por contrato, así que uno que el flujo 1 trajo por la mañana no se
  reescribe esa noche salvo que haya cambiado en el medio, que es exactamente
  cuando queremos guardarlo. Las dos escrituras son correctas; lo que falla es que
  el modelo tiene resolución de día y dos estados dentro de un día no se pueden
  representar.

  El mecanismo está vivo: el 22 de agosto ya hubo tres particiones bajo la misma
  fecha de extracción, una por flujo.

  Es error aunque el estado sea legítimo, porque el daño ocurre aguas abajo y en
  silencio. Cuando salte, la decisión de cuál observación sobrevive se toma con el
  caso real delante; el manifiesto lleva marcas de tiempo por partición y es el
  candidato natural para dar ese orden.

  Medido el 29/08/2026: cero, sobre 2.902.163 observaciones.
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
