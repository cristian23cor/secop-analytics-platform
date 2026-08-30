{#
  Un contrato por fila, en su estado más reciente conocido.

  Sale de filtrar `es_version_vigente` sobre el snapshot, así que las dos tablas
  cuadran por construcción y no por coincidencia. Eso obligó a que el snapshot
  llevara `fecha_de_firma`, que no tenía.

  Lleva solo las medidas aditivas: el valor del contrato, las seis fuentes de
  financiación y el conteo. Las semiaditivas (lo pagado, lo facturado, los saldos)
  viven en el snapshot, que es donde está el eje temporal que las hace
  semiaditivas. El valor de hoy está a un filtro de distancia.

  `fecha_primer_snapshot` es la columna que justifica la tabla: sin ella no se
  distingue "no tuvo adiciones" de "tuvo adiciones que no vimos". Un contrato
  firmado en 2019 al que le vimos una sola versión no es un contrato sin
  modificaciones, es uno cuya historia empieza el día que encendimos el pipeline.
  `dias_hasta_el_primer_snapshot` mide ese hueco.

  El número duele: con margen de 7 días son 11.066 contratos, el 0,39%. La mediana
  del hueco es de 657 días. Y el margen no puede ser cero, porque la fuente publica
  con un día de rezago y ningún contrato se ve el mismo día en que se firma.

  El margen se fija en el mart y no acá, a propósito.

  sección 3 del modelo dimensional pide cargarla con MERGE. No se implementó porque ese
  MERGE protege contra duplicar al insertar deltas, y acá no se insertan deltas.
  Cuando el pipeline pase a incremental, esta tabla pasa con él.

  El filtro de 2020 tampoco está acá: es un filtro de negocio y va en los marts,
  donde se puede revisar.
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

    {#- Llaves hacia las dimensiones. Son IMPOSIBLES (no cambian nunca) así que
        leerlas de la versión vigente da lo mismo que de cualquier otra.

        `codigo_proveedor` es la excepción y por eso está acá y también en el
        snapshot: el proveedor SÍ cambia, con la cesión, así que acá está el
        actual y en el snapshot está el de cada momento. Es el hallazgo 1 de sección 9
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

    {#- Medidas ADITIVAS (sección 7). Las semiaditivas viven en el snapshot. -#}
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
