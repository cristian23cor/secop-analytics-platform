{#-
  ¿Apareció basura nueva en la fuente?

  Hoy hay exactamente UNA observación con un casting fallido sobre 2.902.163
  —un `valor_del_contrato` de 21 dígitos— y ninguna con dos o más. Medido el
  28/08/2026.

  Este test no comprueba que no haya basura: comprueba que **no haya más de la
  que ya conocemos**. Si mañana son cincuenta mil, algo cambió en la fuente o en
  nuestro casteo, y en los dos casos hay que enterarse el mismo día.

  ⚠ **Y no dice nada sobre la basura que castea limpio**, que es la mayoría y la
  peor: el contrato de 12.858 billones de pesos tiene `castings_fallidos = 0`.
  Esa clase la atrapa RN13, no esto. El contador mide la forma, no la verdad.

  El umbral es 1 y no 0 a propósito: fijarlo en el valor medido hace que el test
  avise cuando el número cambia, en vez de gritar por lo que ya sabemos.
-#}

{{ config(severity="warn") }}

select
    'castings fallidos por encima de lo conocido' as motivo,
    count(*) as observaciones_con_fallos,
    1 as esperadas_al_28_08_2026

from {{ ref("stg_contratos") }}

where castings_fallidos > 0

having count(*) > 1