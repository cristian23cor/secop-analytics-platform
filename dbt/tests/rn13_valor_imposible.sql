{#-
  RN13: Un contrato no puede valer más que el presupuesto del Estado entero.

  ## El techo sale de una cifra pública y verificable

  El Presupuesto General de la Nación de 2026, aprobado por el Congreso en
  octubre de 2025, es de **546,9 billones de pesos**: todo lo que el Estado
  colombiano gasta en un año. Un contrato individual no puede superarlo.

  Este número está escrito acá en lugar de puesto a ojo, que es la diferencia
  entre una regla que se defiende y una intuición con formato de test.

  ## Es el nivel de lo IMPOSIBLE, no el de lo sospechoso

  Medido el 28/08/2026 sobre 2.902.163 observaciones: siete contratos distintos,
  todos con `castings_fallidos = 0` porque castean limpio a `decimal(20,2)`.

      12.858 billones  x23,5 PGN  En ejecución  Instituto municipal de deportes
       6.453 billones  x11,8 PGN  En ejecución  Institución educativa
       3.247 billones   x5,9 PGN  Modificado    Ministerio del Interior
         714 billones   x1,3 PGN  Modificado    Ministerio del Interior
         601 billones   x1,1 PGN  Modificado    Secretaría distrital
         579 billones   x1,1 PGN  Modificado    DISAN-DMSOC
         577 billones   x1,1 PGN  En ejecución  Hospital Central de la Policía

  Esta es la razón de ser de esta regla: el sistema de tipos atrapa un valor
  con forma inválida en 2,9 millones de observaciones, y toda la demás basura
  pasa limpia. Los valores imposibles solo los detecta una regla de negocio.

  ## La interpretación del hallazgo

  El dinero no se movió: seis de los siete declaran `valor_pagado = 0` y el
  séptimo, 22,7 millones sobre 577 billones. Son errores de digitación
  publicados sin filtro, no desfalcos. La afirmación sostenible es que la
  fuente oficial no valida sus propios valores.

  El `valor_pagado = 0` no sirve para detectarlos: la mayoría de los contratos
  sanos también lo tienen en cero. Sirve para interpretarlos.

  Y la regla deja pasar 32 contratos por encima del billón de pesos. No todos
  son basura: el mínimo es 1,07 billones y una obra de infraestructura grande
  puede valer eso. Separar los legítimos pediría un segundo umbral (contra el
  presupuesto de inversión anual, 88,4 billones para 2026) que todavía no está
  fijado. Ver pregunta abierta 15 del inventario.

  ## El grano es el CONTRATO, no la observación

  Este test contaba una fila por observación, y ese conteo miente hacia arriba
  sin que nada empeore. Medido el 08/09/2026 sobre 3.369.650 observaciones:

      7 contratos distintos    los mismos siete del 28/08
      9 filas                  dos de ellos se volvieron a observar el 08/09

  Los dos contratos siguen vivos y siguen mal, así que cada corte nuevo que los
  vuelva a traer suma otra fila. Con el grano en la observación, el número sube
  solo con ingerir, y un techo puesto sobre él saltaría por una causa que no es
  la que interesa. Agrupando por contrato, el número solo se mueve cuando
  aparece un contrato imposible nuevo, que es exactamente el evento a vigilar.

  ## El ratchet

  `warn_if=">0"` deja el aviso visible: el incumplimiento ya está en disco y
  una suite roja permanente enseña a ignorar los tests.

  `error_if=">7"` es el trinquete. Siete es lo conocido y medido, no un margen
  de cortesía: el octavo contrato imposible rompe la construcción. Y si alguna
  vez bajan, este número baja con ellos —un trinquete que no se aprieta es un
  número que envejece hasta volver a no decir nada.
-#}

{{ config(severity="error", error_if=">7", warn_if=">0") }}

{%- set pgn_2026 = 546900000000000 %}

select
    id_contrato,
    count(*) as observaciones,
    min(ruta_fecha_extraccion) as visto_desde,
    max(ruta_fecha_extraccion) as visto_hasta,
    max(valor_del_contrato) as valor_del_contrato,
    max(valor_del_contrato) / {{ pgn_2026 }} as veces_el_presupuesto_nacional

from {{ ref("stg_contratos") }}

where valor_del_contrato > {{ pgn_2026 }}
   or valor_del_contrato < 0

group by id_contrato
order by veces_el_presupuesto_nacional desc
