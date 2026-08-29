{#-
  RN13 — Un contrato no puede valer más que el presupuesto del Estado entero.

  ## El techo sale de una cifra pública y verificable

  El Presupuesto General de la Nación de 2026, aprobado por el Congreso en
  octubre de 2025, es de **546,9 billones de pesos**: todo lo que el Estado
  colombiano gasta en un año. Un contrato individual no puede superarlo.

  El número está escrito acá y no puesto a ojo, que es la diferencia entre una
  regla que se defiende y una intuición con formato de test.

  ## Es el nivel de lo IMPOSIBLE, no el de lo sospechoso

  Medido el 28/08/2026 sobre 2.902.163 observaciones: **SIETE** contratos
  distintos —no siete observaciones del mismo—, todos con `castings_fallidos = 0`
  porque castean limpio a `decimal(20,2)`.

      12.858 billones  x23,5 PGN  En ejecución  Instituto municipal de deportes
       6.453 billones  x11,8 PGN  En ejecución  Institución educativa
       3.247 billones   x5,9 PGN  Modificado    Ministerio del Interior
         714 billones   x1,3 PGN  Modificado    Ministerio del Interior
         601 billones   x1,1 PGN  Modificado    Secretaría distrital
         579 billones   x1,1 PGN  Modificado    DISAN-DMSOC
         577 billones   x1,1 PGN  En ejecución  Hospital Central de la Policía

  Esa es la razón de ser de esta regla: el sistema de tipos atrapa UN valor con
  forma inválida en 2,9 millones, y toda la demás basura pasa limpia. Los
  valores imposibles solo los detecta una regla de negocio.

  ⚠ **El dinero no se movió.** Seis de los siete declaran `valor_pagado = 0` y el
  séptimo, 22,7 millones sobre 577 billones. Son errores de digitación
  publicados sin filtro, no desfalcos, y así hay que enunciarlo: la afirmación
  sostenible es que la fuente oficial no valida sus propios valores.

  Y `valor_pagado = 0` no sirve para DETECTARLOS: la mayoría de los contratos
  sanos también lo tiene en cero. Sirve para interpretarlos.

  ⚠ **Y deja pasar 32 contratos por encima del billón de pesos.** No todos son
  basura: el mínimo es 1,07 billones y una obra de infraestructura grande puede
  valer eso. Separar los legítimos pide un segundo umbral —contra el presupuesto
  de inversión anual, 88,4 billones para 2026— que todavía no está fijado. Ver
  la pregunta abierta 15 del inventario.

  `warn` y no `error`: el incumplimiento ya está en disco, y una construcción
  roja desde el primer día enseña a ignorar los tests.
-#}

{{ config(severity="warn") }}

{%- set pgn_2026 = 546900000000000 %}

select
    id_contrato,
    ruta_fecha_extraccion,
    valor_del_contrato,
    valor_del_contrato / {{ pgn_2026 }} as veces_el_presupuesto_nacional

from {{ ref("stg_contratos") }}

where valor_del_contrato > {{ pgn_2026 }}
   or valor_del_contrato < 0