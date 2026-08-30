{#
  Las preguntas 6 y 7, que son las que justifican que esta plataforma exista:
  qué entidades y categorías extienden sistemáticamente el plazo, cuántos días, y
  cuánto cuesta eso en pesos.

  Ninguna de las dos se puede responder con datos públicos. La fuente sobrescribe
  el valor y el plazo en cada regeneración, y el dataset oficial de modificaciones
  no tiene columna de valor. La respuesta sale de comparar fotos nuestras.

  Los deltas vienen calculados desde la capa intermedia, así que acá no hay ningún
  lag(). Es lo que se compró al comparar columna por columna en vez de guardar un
  hash.

  Grano: entidad, familia UNSPSC y si vimos la historia entera del contrato.

  ## Por qué la historia está en el grano y no en un where

  Los análisis de delta solo valen para contratos observados desde su firma: de los
  demás vimos un pedazo, y sus adiciones anteriores ya venían incorporadas en la
  primera foto. Mezclarlos subestima el sobrecosto y no falla nada.

  El problema es que esa restricción hoy deja casi nada. Sobre contratos firmados
  desde 2020, la pregunta 7 pasa de 1.925 contratos a 39, repartidos en 29
  entidades. Con 1,3 contratos por entidad la palabra "sistemáticamente" no se
  sostiene; y usar los 1.925 sin decir nada es justamente el error que se quería
  evitar.

  Ninguna de las dos poblaciones responde bien hoy, y esa es la respuesta honesta.
  Por eso van separadas por grano: cada celda declara a cuál pertenece, ninguna
  consulta las mezcla por descuido, y las dos traen su tamaño al lado. La población
  medible crece sola con cada corte ingerido, sin que este modelo cambie.

  El margen es de treinta días. No puede ser cero: la fuente publica con un día de
  rezago, así que ningún contrato se observa el mismo día en que se firma.

  ## Los cuatro conteos, y por qué no son dos

  El plazo también se acorta y el valor también baja. De los 2.227 cambios de fecha
  de fin, 2.131 alargaron y 96 acortaron; de los 1.925 de valor, 1.824 adicionaron
  y 101 redujeron. Sumarlos en neto bajo un nombre que afirma el signo produce
  celdas que dicen "12 extensiones, -12 días", que no es una extensión de nada.
  Fue un defecto real de la primera versión de este modelo y lo destapó su primer
  resultado.

  El neto queda aparte y es el que alimenta el sobrecosto, porque la pregunta 7 es
  cuánto se encareció el contrato y una reducción posterior sí lo abarata.

  ## Lo demás

  El denominador (contratos observados) es lo que hace falta para decir
  "sistemáticamente": sin él, tres extensiones sobre cuatro contratos y tres sobre
  cuatro mil se ven iguales.

  Las razones se calculan después de agregar. Al revés, un contrato de cinco mil
  pesos pesaría igual que uno de cincuenta mil millones.

  El filtro de 2020 vive acá porque los años anteriores miden la adopción de la
  plataforma y no el gasto. Hoy casi no muerde: de los 2.227 contratos que
  extendieron el plazo, 1.940 se firmaron en 2026. La tabla madura y el histórico
  entra.

  Falta traducir la familia a un nombre legible, que espera el catálogo UNSPSC.
#}


{{ config(materialized="table") }}

{#- El margen de gracia entre la firma y la primera observación. Ver arriba: no
    puede ser cero. -#}
{%- set margen_dias = 30 %}

{#- Desde cuándo los años son comparables entre sí (H3). -#}
{%- set desde = "'2020-01-01'" %}

with contratos as (

    select
        f.id_contrato,
        f.codigo_entidad,
        c.familia_unspsc,
        f.valor_del_contrato,
        f.dias_hasta_el_primer_snapshot <= {{ margen_dias }} as historia_completa

    from {{ ref("fct_contratos") }} f
    join {{ ref("dim_categoria") }} c using (codigo_de_categoria_principal)

    where f.fecha_de_firma >= {{ desde }}

),

{#- Los cambios ya vienen con su delta calculado desde la capa intermedia: acá no
    se recalcula ninguna ventana. Es lo que D6 compró al comparar columna por
    columna en vez de guardar un hash. -#}
cambios as (

    select
        id_contrato,
        {# Positivos y negativos POR SEPARADO, y no una suma neta.

           Medido el 29/08/2026: de los 2.227 cambios de `fecha_de_fin_del_contrato`,
           2.131 alargaron el plazo (+134.296 días) y 96 lo ACORTARON (-2.351). La
           suma neta esconde las dos poblaciones, y una celda puede mostrar "12
           extensiones, -12 días", que no es una extensión de nada.

           Es H27 en el otro eje: el dataset oficial de modificaciones tiene un tipo
           `REDUCCION EN EL VALOR`, y para el valor eso ya estaba anotado. Que el
           plazo también se acorte no lo estaba. #}
        sum(case when columna = 'fecha_de_fin_del_contrato' and delta_dias > 0
                 then 1 else 0 end)                          as extensiones,
        sum(case when columna = 'fecha_de_fin_del_contrato' and delta_dias > 0
                 then delta_dias else 0 end)                 as dias_extendidos,
        sum(case when columna = 'fecha_de_fin_del_contrato' and delta_dias < 0
                 then 1 else 0 end)                          as acortamientos,
        sum(case when columna = 'fecha_de_fin_del_contrato' and delta_dias < 0
                 then delta_dias else 0 end)                 as dias_acortados,

        sum(case when columna = 'valor_del_contrato' and delta_valor > 0
                 then 1 else 0 end)                          as adiciones,
        sum(case when columna = 'valor_del_contrato' and delta_valor > 0
                 then delta_valor else 0 end)                as pesos_adicionados,
        sum(case when columna = 'valor_del_contrato' and delta_valor < 0
                 then 1 else 0 end)                          as reducciones,
        sum(case when columna = 'valor_del_contrato' and delta_valor < 0
                 then delta_valor else 0 end)                as pesos_reducidos,

        {# El neto es el que responde "cuánto se encareció", que es la pregunta 7.
           Va aparte de los dos anteriores en vez de reemplazarlos. #}
        sum(case when columna = 'valor_del_contrato'
                 then delta_valor else 0 end)                as pesos_netos,

        sum(case when columna = 'dias_adicionados' then delta_valor else 0 end)
            as dias_adicionados_declarados

    from {{ ref("int_cambios_por_columna") }}
    group by id_contrato

),

por_celda as (

    select
        c.codigo_entidad,
        c.familia_unspsc,
        c.historia_completa,

        {#- El denominador. Sin él, "sistemáticamente" no se puede afirmar. -#}
        count(*)                                          as contratos_observados,
        sum(c.valor_del_contrato)                         as valor_actual_total,

        sum(case when d.extensiones > 0 then 1 else 0 end)   as contratos_con_extension,
        coalesce(sum(d.extensiones), 0)                      as extensiones,
        coalesce(sum(d.dias_extendidos), 0)                  as dias_extendidos,
        sum(case when d.acortamientos > 0 then 1 else 0 end) as contratos_con_acortamiento,
        coalesce(sum(d.acortamientos), 0)                    as acortamientos,
        coalesce(sum(d.dias_acortados), 0)                   as dias_acortados,

        sum(case when d.adiciones > 0 then 1 else 0 end)     as contratos_con_adicion,
        coalesce(sum(d.adiciones), 0)                        as adiciones,
        coalesce(sum(d.pesos_adicionados), 0)                as pesos_adicionados,
        sum(case when d.reducciones > 0 then 1 else 0 end)   as contratos_con_reduccion,
        coalesce(sum(d.reducciones), 0)                      as reducciones,
        coalesce(sum(d.pesos_reducidos), 0)                  as pesos_reducidos,
        coalesce(sum(d.pesos_netos), 0)                      as pesos_netos,

        coalesce(sum(d.dias_adicionados_declarados), 0)    as dias_adicionados_declarados

    from contratos c
    left join cambios d using (id_contrato)

    group by 1, 2, 3

)

select
    p.codigo_entidad,
    {#- El nombre de HOY. La dimensión tiene historia y el mart describe el
        presente, así que se toma la versión vigente. Un mart que quisiera "cómo
        se llamaba cuando ocurrió la adición" uniría por rango con
        `vigente_en()`, que es otra pregunta. -#}
    e.nombre_entidad,
    e.orden,
    e.sector,

    p.familia_unspsc,
    p.historia_completa,

    p.contratos_observados,
    p.valor_actual_total,

    p.contratos_con_extension,
    p.extensiones,
    p.dias_extendidos,
    p.contratos_con_acortamiento,
    p.acortamientos,
    p.dias_acortados,
    p.dias_adicionados_declarados,

    p.contratos_con_adicion,
    p.adiciones,
    p.pesos_adicionados,
    p.contratos_con_reduccion,
    p.reducciones,
    p.pesos_reducidos,
    p.pesos_netos,

    {#- Razones, DESPUÉS de agregar (sección 7). -#}
    p.contratos_con_extension * 1.0
        / nullif(p.contratos_observados, 0)            as tasa_de_extension,
    p.contratos_con_adicion * 1.0
        / nullif(p.contratos_observados, 0)            as tasa_de_adicion,
    p.dias_extendidos * 1.0
        / nullif(p.contratos_con_extension, 0)         as dias_por_contrato_extendido,

    {#- El sobrecosto se mide contra el valor ANTES de las adiciones, que es lo
        que la pregunta 7 quiere saber: cuánto se encareció respecto de lo
        contratado. Puede ser negativo si dominan las reducciones (H27). -#}
    {# El sobrecosto usa el NETO: la pregunta 7 es cuánto se encareció el
       contrato, y una reducción posterior a una adición sí lo abarata. Los dos
       componentes quedan expuestos aparte para que se pueda ver de qué está
       hecho. Puede dar negativo donde dominan las reducciones (H27). #}
    p.pesos_netos
        / nullif(p.valor_actual_total - p.pesos_netos, 0) as sobrecosto

from por_celda p
left join {{ ref("dim_entidad") }} e
       on e.codigo_entidad = p.codigo_entidad
      and e.es_version_vigente
