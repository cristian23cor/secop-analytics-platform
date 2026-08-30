{#
  Las preguntas 6 y 7, que son las que justifican que esta plataforma exista.

      6. ¿Qué entidades y categorías extienden sistemáticamente el plazo, y cuántos días?
      7. ¿Y cuánto cuesta esa extensión en pesos?

  Ninguna se puede responder con datos públicos: la fuente sobrescribe el valor y el
  plazo del contrato en cada regeneración, y el dataset oficial de modificaciones no
  tiene columna de valor (H17) y trae la fecha truncada (H33). La respuesta sale de
  comparar observaciones nuestras, que es lo que hace `int_cambios_por_columna`.

  ## El grano: entidad × familia UNSPSC × si vimos la historia entera

  Los dos primeros ejes son los que la pregunta 6 nombra. El tercero es una
  advertencia convertida en columna, y es lo más importante de este modelo.

  ## Por qué `historia_completa` está en el GRANO y no en un `where`

  §9 del modelo dimensional dice que los análisis de delta se restringen a contratos
  observados desde su nacimiento, porque de los demás solo vimos un pedazo de su
  historia: **un contrato firmado en 2021 tiene sus adiciones anteriores ya
  incorporadas en la primera foto, y son invisibles**. Mezclarlos subestima el
  sobrecosto sin que nada falle.

  El problema es que hoy esa restricción deja casi nada. Medido el 29/08/2026, sobre
  contratos firmados desde 2020:

  | | Contratos | Entidades |
  |---|---|---|
  | Extendieron el plazo, sin restricción | 2.227 | 421 |
  | Extendieron el plazo, con historia completa | **193** | **88** |
  | Adicionaron valor, sin restricción | 1.925 | 358 |
  | Adicionaron valor, con historia completa | **39** | **29** |

  Con 39 contratos en 29 entidades —1,3 cada una— la palabra "sistemáticamente" no se
  sostiene. Y usar los 1.925 sin decir nada es exactamente lo que §9 advierte.

  Por eso las dos poblaciones están **separadas por grano**: cada celda declara a cuál
  pertenece, ninguna consulta las mezcla por descuido, y las dos traen su tamaño al
  lado. El tablero puede mostrar la cota inferior y la población medible juntas, que
  es la única lectura honesta que existe hoy.

  Y envejece bien: la población con historia completa **crece sola** con cada
  regeneración ingerida, sin que este modelo cambie. Es la limitación 1 de §11 —"la
  tabla madura con el tiempo"— hecha columna en vez de nota al pie.

  ## El margen es de 30 días, y no puede ser cero

  `historia_completa` es `dias_hasta_el_primer_snapshot <= 30`. El número es una
  decisión del mart, que es donde §9 dice que vive.

  ⚠ **Cero no es una opción.** El mínimo observado es de un día: ningún contrato se ve
  el mismo día en que se firma, porque la fuente publica con ~1 día de rezago (H8).
  Con margen cero el universo queda vacío por una propiedad de la fuente y no por
  falta de datos. Con 7 días serían 748 contratos con algún cambio; con 30, 1.616.

  ## El filtro de 2020 vive acá, y esto es lo que H3 quiso decir

  Antes de 2020 la curva de volumen mide la adopción de SECOP II y no el gasto
  público, así que cualquier comparación que cruce ese año es inválida (H3). El hecho
  no lleva el filtro —es el inventario completo— y cada mart declara el suyo.

  Hoy casi no muerde: de los 2.227 contratos que extendieron el plazo, **1.940 se
  firmaron en 2026 y 240 en 2025**. Uno solo es de 2020 y ninguno anterior. Tiene
  sentido — los contratos que se están modificando ahora son los recientes— pero
  conviene no leer eso como que el filtro sobra: la tabla madura y el histórico entra.

  ## Sobre las medidas

  `contratos_observados` es el denominador que hace falta para la palabra
  "sistemáticamente": sin él, una entidad con 3 extensiones sobre 4 contratos y otra
  con 3 sobre 4.000 se ven iguales.

  `sobrecosto` se calcula **después de agregar**, contra el valor estimado antes de
  las adiciones. Es la regla de §7: razones, porcentajes y promedios se calculan al
  final, o un contrato de $5.000 pesa igual que uno de $50.000 millones.

  ⚠ `pesos_adicionados` **puede ser negativo**: existe el tipo `REDUCCION EN EL VALOR`
  (H27), y medido son 101 de las 1.925. El `sobrecosto` de una celda dominada por
  reducciones es negativo y eso es correcto, no un error a filtrar.

  ## Lo que este modelo NO puede decir todavía

  - **Nombres de categoría.** La familia es el código de cuatro dígitos; traducirlo
    necesita el catálogo UNSPSC, que es dato externo pendiente. Agrupar sí se puede.
  - **Días de extensión desde `dias_adicionados`.** Se usa el corrimiento de
    `fecha_de_fin_del_contrato`, que es el mismo evento visto desde el otro lado y es
    una fecha de verdad. `dias_adicionados` entra como control, no como medida
    principal.
  - **Nada sobre contratos sin categoría.** Los 25.597 con `UNSPECIFIED` caen en una
    celda con `familia_unspsc` nula, visible en vez de repartida.
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
           2.131 alargaron el plazo (+134.296 días) y 96 lo ACORTARON (−2.351). La
           suma neta esconde las dos poblaciones, y una celda puede mostrar "12
           extensiones, −12 días" — que no es una extensión de nada.

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

    {#- Razones, DESPUÉS de agregar (§7). -#}
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
