{#
  Un contrato por fila, en su estado más reciente conocido.

  Es el snapshot **acumulativo** del par: `fct_contratos_snapshot` guarda todas las
  versiones y ésta guarda solo la última, con lo que hace falta para saber cuánto de
  la historia de ese contrato alcanzamos a ver.

  ## Sale del snapshot y no de `staging`

  Filtrar `es_version_vigente` da una fila por contrato sin agregar nada, y hace que
  las dos tablas sean consistentes **por construcción** en vez de por coincidencia.
  Derivarla de `stg_contratos` por separado crearía dos caminos hasta "el estado
  actual" que pueden divergir sin que nada falle.

  Eso obligó a que el snapshot llevara `fecha_de_firma`, que no tenía: se agregó junto
  con `fecha_de_inicio_del_contrato` al generar la lista de imposibles desde el macro
  en vez de escribirla a mano.

  ## Por qué tabla y no `MERGE`

  §3 del modelo dimensional dice que esta tabla "se carga con `MERGE` sobre
  `id_contrato`; con `INSERT` se duplica". Ese `MERGE` protege contra duplicar cuando
  se insertan deltas, y acá no se insertan deltas: se filtra una tabla que ya se
  reconstruyó entera. La idempotencia sale de la construcción y no de la estrategia de
  carga, que es más fuerte.

  Cuando el pipeline entero pase a incremental (D5), esta tabla pasa con él y ahí sí
  la estrategia es `merge`, que existe en DuckDB y en Snowflake (D9).

  ## `fecha_primer_snapshot` y por qué es la columna que justifica la tabla

  Sin ella no se puede distinguir **"no tuvo adiciones"** de **"tuvo adiciones que no
  vimos"**. Un contrato firmado en 2019 al que le vimos una sola versión no es un
  contrato sin modificaciones: es uno cuya historia empieza el día que encendimos el
  pipeline, con todas sus adiciones previas ya incorporadas en la primera foto.

  `dias_hasta_el_primer_snapshot` mide exactamente ese hueco: cuántos días pasaron
  entre la firma y la primera vez que lo vimos. Cero o poco significa que lo
  observamos desde que nació.

  ⚠ **Medido el 29/08/2026, y el número es incómodo: con un margen de 7 días son
  11.066 contratos, el 0,39%.** Con margen cero son **cero**. El primer snapshot es
  del 2026-08-22 y la firma más reciente del 2026-08-24. El otro 99,6% tiene la
  historia truncada por la izquierda.

  Ese número **crece solo** con cada regeneración ingerida, y es la razón por la que
  §11 dice que `fct_contratos_snapshot` empieza vacía y madura con el tiempo. Lo que
  no se puede es esconderlo: un mart de sobrecosto que ignore esta columna mezcla dos
  poblaciones y **subestima** el resultado sin que nada falle.

  El margen no se fija acá a propósito. Es una decisión del mart —cuántos días de
  gracia se aceptan entre la firma y la primera observación— y hornearla en el hecho
  la volvería invisible.

  ## Las medidas son solo las aditivas

  `valor_del_contrato`, las seis fuentes de financiación y `conteo_contratos = 1`. Es
  lo que fija §7: un contrato aparece una sola vez y no hay eje temporal en el que
  pueda repetirse, así que todo esto se suma por cualquier corte.

  Las semiaditivas —`valor_pagado`, `valor_facturado`, `saldo_cdp` y las demás— viven
  en el snapshot, que es donde está el eje temporal que las hace semiaditivas. El
  valor de hoy está a un filtro de distancia: `where es_version_vigente`. Copiarlas
  acá daría dos lugares donde responder "cuánto se ha pagado".

  `conteo_contratos` existe para contar sin `COUNT(DISTINCT)`, que sobre una tabla de
  una fila por contrato es trabajo de más.

  ## El filtro de 2020 NO está acá

  H3 mostró que antes de 2020 la curva mide adopción de SECOP II y no gasto público, y
  decidió restringir **el análisis de los marts**. Esta tabla queda como el inventario
  completo de lo que el pipeline conoce —2.849.209 contratos, de los cuales 71.512 son
  anteriores a 2020— y cada mart declara su recorte, que es reversible.

  ⚠ La contracara: un mart que se olvide del recorte no falla, mezcla 2016 con 2025 y
  devuelve una comparación interanual inválida. Tiene que ir en la plantilla de los
  marts, no en la memoria de quien los escriba.
#}

{{ config(materialized="table") }}

{%- set fuentes = columnas_fuentes_de_financiacion() %}

with observacion as (

    {#- Cuánto de la historia de cada contrato alcanzamos a ver. Es lo único que
        no se puede leer de la versión vigente: hace falta mirar todas. -#}
    select
        id_contrato,
        min(observado_desde) as fecha_primer_snapshot,
        max(observado_desde) as fecha_ultima_version,
        count(*)             as versiones_observadas
    from {{ ref("fct_contratos_snapshot") }}
    group by id_contrato

),

vigente as (

    select * from {{ ref("fct_contratos_snapshot") }}
    where es_version_vigente

)

select
    v.id_contrato,

    {#- Llaves hacia las dimensiones. Son IMPOSIBLES —no cambian nunca— así que
        leerlas de la versión vigente da lo mismo que de cualquier otra.

        `codigo_proveedor` es la excepción y por eso está acá y también en el
        snapshot: el proveedor SÍ cambia, con la cesión, así que acá está el
        actual y en el snapshot está el de cada momento. Es el hallazgo 1 de §9
        del modelo dimensional. -#}
    v.codigo_entidad,
    v.nit_entidad,
    v.codigo_proveedor,
    v.documento_proveedor,
    v.codigo_de_categoria_principal,
    v.llave_modalidad,
    v.llave_geografia,
    v.proceso_de_compra,
    v.notice_uid,

    {#- Las fechas del contrato. Las dos primeras son imposibles; la tercera es
        material y se corre con cada prórroga. -#}
    v.fecha_de_firma,
    v.fecha_de_inicio_del_contrato,
    v.fecha_de_fin_del_contrato,

    v.estado_contrato,

    {#- Medidas ADITIVAS (§7). Las semiaditivas viven en el snapshot. -#}
    v.valor_del_contrato,
    {%- for fuente in fuentes %}
    v.{{ fuente }},
    {%- endfor %}
    1 as conteo_contratos,

    {#- Cuánto de la historia vimos. Sin esto no se distingue "no tuvo
        adiciones" de "tuvo adiciones que no vimos". -#}
    o.fecha_primer_snapshot,
    o.fecha_ultima_version,
    o.versiones_observadas,

    {#- El hueco entre la firma y la primera observación. Cero o poco significa
        que lo vimos desde que nació, y solo esos contratos tienen historia
        completa para un análisis de deltas.

        Vía la macro multiplataforma de dbt: `date_diff` y `datediff` se
        escriben distinto en DuckDB y en Snowflake (D9). -#}
    {{ dbt.datediff("v.fecha_de_firma",
                    "cast(o.fecha_primer_snapshot as date)", "day") }}
        as dias_hasta_el_primer_snapshot,

    {#- Por qué la versión vigente no tiene sucesora: si dice
        `fuera_de_observacion`, este contrato ya no se barre y su "estado más
        reciente conocido" no se va a actualizar más. -#}
    v.motivo_de_cierre

from vigente v
join observacion o using (id_contrato)
