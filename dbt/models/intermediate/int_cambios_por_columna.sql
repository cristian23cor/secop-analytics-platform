{#
  Qué columna material cambió en cada versión del snapshot, y cuánto.

  Una fila por contrato, versión y columna. La versión 1 no aparece: no había nada
  antes, y "apareció por primera vez" no es un cambio.

  Está acá y no como columna del hecho porque no cabe en una columna. De los 32.431
  contratos con dos versiones, solo 12.838 cambiaron una sola material; el resto
  cambió hasta doce a la vez.

  Los dos deltas van separados porque pesos y días no se suman entre sí. Las 17
  columnas numéricas llenan `delta_valor`, las 5 fechas llenan `delta_dias`, y las 6
  de texto ninguno de los dos: ahí el cambio se lee en `valor_anterior` y
  `valor_nuevo`, que van como texto porque una tabla larga tiene una sola columna
  para valores de ocho tipos distintos.

  `delta_valor` puede ser negativo. El dataset oficial de modificaciones tiene un
  tipo REDUCCION EN EL VALOR, y medido son 101 de 1.925.

  El razonamiento completo, con las tres alternativas que se descartaron, está en
  sección 3 de `01_modelo_dimensional.md`.
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
