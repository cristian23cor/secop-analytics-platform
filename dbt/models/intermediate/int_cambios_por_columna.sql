{#
  Qué columna material cambió en cada versión del snapshot, y cuánto.

  Es `motivo_del_cambio` de D6, y está acá y no en el hecho por una medición: de
  los 32.431 contratos que hoy tienen dos versiones, **solo 12.838 —el 39,6%—
  cambiaron exactamente una columna**. El resto cambió entre 2 y **12 a la vez**.
  Un motivo escalar no describe eso, así que el grano es una fila por contrato,
  versión y columna que cambió.

  ## Por qué una tabla larga y no columnas en el hecho

  Tres alternativas, y la razón de cada descarte:

  - **Texto concatenado con los nombres.** Descartada por una trampa concreta:
    `valor_pendiente_de` es prefijo de `valor_pendiente_de_pago` y de
    `valor_pendiente_de_ejecucion`, así que filtrar con `like '%valor_pendiente_de%'`
    devuelve tres columnas distintas y no avisa. Es el mismo modo de fallo que el
    separador mal elegido de I1.
  - **28 booleanas en el hecho.** El hecho pasaría de 43 a 71 columnas, que es
    deshacer a medias el adelgazamiento que lo llevó de 734 s a 52 s (R3). Y una
    tabla de hechos lleva llaves, fechas y medidas: 28 banderas no son ninguna de
    las tres.
  - **Seis banderas de negocio.** Fijaría hoy la lista de categorías y perdería
    qué columna se movió. Acá se guarda el dato crudo y las categorías se derivan
    en el mart, donde cambiarlas no obliga a reconstruir nada.

  El costo que se acepta es un join más para preguntar "esta versión, ¿por qué se
  generó?".

  ## El grano y lo que NO está

  Una fila por `(id_contrato, version, columna)`, y **la versión 1 de cada
  contrato no aparece**. No es una omisión: su `huella_anterior` es nula porque
  no había nada antes, y "apareció por primera vez" no es un cambio. Es el
  hallazgo 2 de §9 del modelo dimensional — el universo medible son los contratos
  que cambiaron *mientras los observábamos*, y eso hay que decirlo en el mart o
  el número se lee como un total nacional.

  ## Los dos deltas, y por qué son dos columnas y no una

  17 de las 28 materiales son numéricas (16 monetarias más `dias_adicionados`) y
  5 son fechas. Las dos cosas se pueden restar, pero **pesos y días no se suman
  entre sí**: una sola columna de delta invitaría a un `sum()` que no
  corresponde a nada, que es exactamente el error que §7 describe para las
  medidas semiaditivas.

  Con las dos separadas, las preguntas que justifican el proyecto salen de acá
  sin recalcular:

      pregunta 6 — cuántos días extienden el plazo:
        where columna = 'dias_adicionados'            -> delta_valor
        where columna = 'fecha_de_fin_del_contrato'   -> delta_dias

      pregunta 7 — cuánto cuesta esa extensión en pesos:
        where columna = 'valor_del_contrato'          -> delta_valor

  ⚠ `delta_valor` **puede ser negativo** y ninguna lógica debe asumir monotonía:
  existe el tipo `REDUCCION EN EL VALOR` en el dataset oficial de modificaciones
  (H27). La que sí es acumulada es `valor_pagado`, y eso lo protege RN5.

  Las 6 restantes —`estado_contrato`, `duraci_n_del_contrato`, `liquidaci_n` y el
  trío del proveedor— son texto: los dos deltas quedan nulos y el cambio se lee
  en `valor_anterior` / `valor_nuevo`.

  ⚠ `duraci_n_del_contrato` parece numérica y no lo es: trae la unidad pegada
  (`"6 Mes(es)"`, `"180 Dia(s)"`) y cinco unidades conviven en la misma columna,
  así que el número solo no significa nada. Para duración real están las dos
  fechas del contrato.

  ## Sobre `valor_anterior` y `valor_nuevo`

  Van como texto porque una tabla larga tiene una sola columna para valores de
  ocho tipos distintos. Es el único lugar del proyecto donde se vuelve a texto
  algo que `staging` ya había casteado, y se acepta a cambio del grano largo: los
  deltas ya vienen calculados, así que nadie tiene que castear de vuelta para
  responder las preguntas de negocio. Quedan para leer el cambio, no para
  operarlo.

  ## Lo que este modelo hace visible y todavía no está resuelto

  Medido el 29/08/2026, las cuatro columnas que más cambian son
  `valor_pendiente_de_pago` (18.510), `valor_pendiente_de_ejecucion` (18.431),
  `valor_facturado` (18.123) y `valor_pagado` (16.539): **son las cuatro de la
  ejecución financiera de H9**, el mecanismo que el inventario probó que no deja
  rastro en ninguna fecha. Y `valor_facturado` sola explica 10.419 de los 12.838
  cambios de columna única. El evento más frecuente que el pipeline captura es
  justo el que la fuente no registra.

  ⚠ Y hace visible un defecto de clasificación: `proveedor_adjudicado` cambió en
  513 contratos, `documento_proveedor` en 61 y `codigo_proveedor` —la llave, o
  sea una cesión de verdad— en **1**. 498 cambiaron solo el nombre, con el mismo
  código y el mismo documento: `'LARJ'` → `'LUIS ANTONIO RIVADENEIRA JOJOA'`,
  `'RCN Radio S.A.S'` → `'RADIO CADENA NACIONAL SAS'`. El modelo dimensional dice
  que el trío es material porque "cambia con la cesión", y el trío no se mueve
  junto. Queda como pregunta abierta 11 de `01_modelo_dimensional.md`: hay que
  revisar los 498 antes de reclasificar, porque un renombre y una cesión donde la
  fuente no actualizó el código se ven igual desde acá.
#}

{{ config(materialized="table") }}

{%- set materiales = columnas_materiales() %}
{%- set numericas = columnas_monetarias() + columnas_enteras() %}
{%- set fechas = columnas_fechas() %}

with nuevas as (

    {#- Solo las versiones que tienen una anterior. Son 32.431 de 2.881.640, así
        que filtrar acá es lo que hace que el join de abajo sea barato: el lado
        chico de la construcción entra en memoria sin volcar a disco (R3). -#}
    select
        id_contrato,
        version,
        observado_desde
        {%- for columna in materiales %},
        {{ columna }}
        {%- endfor %}
    from {{ ref("fct_contratos_snapshot") }}
    where version > 1

),

pares as (

    {#- La versión anterior de cada una, por número de versión y no por fecha.
        Las versiones ya están numeradas sin huecos por `row_number()`, así que
        `version - 1` es exacta y no depende de volver a ordenar por fecha. -#}
    select
        n.id_contrato,
        n.version,
        n.observado_desde
        {%- for columna in materiales %},
        a.{{ columna }} as antes_{{ columna }},
        n.{{ columna }} as ahora_{{ columna }}
        {%- endfor %}
    from nuevas n
    join {{ ref("fct_contratos_snapshot") }} a
      on  a.id_contrato = n.id_contrato
      and a.version     = n.version - 1

)

{% for columna in materiales %}
select
    id_contrato,
    version,
    observado_desde,
    '{{ columna }}' as columna,
    cast(antes_{{ columna }} as varchar) as valor_anterior,
    cast(ahora_{{ columna }} as varchar) as valor_nuevo,
    {%- if columna in numericas %}
    cast(ahora_{{ columna }} as decimal(20, 2))
      - cast(antes_{{ columna }} as decimal(20, 2)) as delta_valor,
    cast(null as bigint) as delta_dias
    {%- elif columna in fechas %}
    cast(null as decimal(20, 2)) as delta_valor,
    {#- Vía la macro multiplataforma de dbt y no `date_diff`: DuckDB y Snowflake
        la escriben distinto, y D9 pide que nada motor-específico se cuele fuera
        del modelo frontera. -#}
    {{ dbt.datediff("antes_" ~ columna, "ahora_" ~ columna, "day") }} as delta_dias
    {%- else %}
    cast(null as decimal(20, 2)) as delta_valor,
    cast(null as bigint) as delta_dias
    {%- endif %}
from pares
where antes_{{ columna }} is distinct from ahora_{{ columna }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
