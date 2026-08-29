{#
  `stg_contratos` es la capa donde se paga el costo de haber dejado la fuente tal cual
  llegó en raw. Raw guarda lo que la API devolvió sin tocar un carácter, que era lo
  correcto porque la fuente ya se sobrescribió, y el costo de esa elección se ve acá.

  Este modelo hace tres cosas y ninguna más:

  1. Castea 16 columnas monetarias, 7 fechas y 2 enteras. Las 42 restantes quedan como
     texto: castear de más inventa estructura, castear de menos posterga el problema.
  2. Convierte los centinelas a nulo. "No definido" y "No Definido" son nulos
     disfrazados, en las dos capitalizaciones que usa la fuente (H6).
  3. Aplana `urlproceso` y le saca el `noticeUID`, un tercer identificador que no
     aparece en ninguna otra columna.

  No filtra. El corte de 2020 y los estados pre-firma son reglas de negocio y viven más
  arriba, donde son reversibles.

  ## `try_cast` y un contador

  Un valor que no se puede castear tiene tres respuestas posibles y las tres son malas:

  - `cast` a secas: una fila basura en 2,9 millones tumba la corrida.
  - `try_cast` a secas: la corrupción entra disfrazada de nulo y ya no se distingue de un
    nulo legítimo.
  - No castear: se lo pasa a quien consuma esto.

  Acá se usa `try_cast` junto con una columna que cuenta cuántos castings fallaron en esa
  fila. Nada rompe la corrida, nada queda perdido en silencio, y de paso se responde una
  pregunta que no se contesta de otra forma: cuánta basura tiene esta fuente. Es el mismo
  patrón que el canario del descarte, contar en vez de abortar, y que RN12, que nace con
  sus incumplimientos ya medidos.

  Un casting que no falla no significa que el dato esté bien. `valor_del_contrato` trae un
  contrato de 12.858.450.316.000.000 pesos, veintitrés veces el Presupuesto General de la
  Nación, y castea limpio a `decimal(20,2)`, con `castings_fallidos = 0`. Es H33 otra vez:
  una columna sistemáticamente corrupta que parsea sin quejarse. El contador mide la forma,
  no la verdad, y los valores imposibles los tiene que atrapar una regla de negocio con un
  techo defendible (RN13).

  En la otra punta, otro contrato trae 21 dígitos y `try_cast` lo rechaza. Agrandar el
  `decimal` para que entre sería lo peor: el valor pasaría a contaminar toda suma, promedio
  y máximo. Que se rechace es el sistema funcionando.

  ## De dónde salen las listas

  De `columnas.py`, a través del macro generado. Las cuatro listas de tipo son un eje
  distinto de la clasificación material/cosmética: aquella decide qué genera versión nueva
  en el SCD2, esta decide a qué se castea. Una columna puede ser monetaria y cosmética a
  la vez.
#}

{#- El centinela a nulo, salvo donde es un valor con significado. -#}

{#- Objeto anidado. Se aplana acá porque raw no puede (D2): aplanar es normalizar, y raw
    guarda lo que llegó. El `noticeUID` sale como columna propia porque no se puede
    reconstruir desde `proceso_de_compra`: son dos identificadores distintos (H6). -#}

{#- Tres estados: "No Definido" no equivale a "No" (RN10). -#}

{#- El contador. Una columna falló el casting si tenía valor, ya sin el centinela, y el
    `try_cast` dio nulo. Usa los mismos ayudantes que la proyección de arriba: escritos
    por separado, el contador podría medir algo distinto de lo que la columna guarda. -#}

{{ config(materialized="table") }}

with origen as (
    select * from {{ ref("raw_observaciones") }}
),

limpio as (

    select
        -- Procedencia. `fecha_extraccion` es CUÁNDO se bajó, no qué estado se
        -- vio; qué corte de la fuente vio esta partición vive en su manifiesto
        -- (D10) y se une más arriba.
        ruta_flujo,
        ruta_fecha_extraccion,
        ruta_particion,
        fecha_extraccion,
        flujo,
        hash,

        {#- El centinela a nulo, salvo donde es un valor con significado. -#}
        {%- for columna in columnas_extraidas() %}
        {%- if columna == "urlproceso" %}
        {#- Objeto anidado. Se aplana acá porque raw no puede (D2): aplanar es
            normalizar, y raw guarda lo que llegó. El `noticeUID` sale a columna
            propia porque NO se puede reconstruir desde `proceso_de_compra` —
            son dos identificadores distintos (H6). -#}
        json_extract_string(urlproceso, '$.url') as url_proceso,
        regexp_extract(
            json_extract_string(urlproceso, '$.url'), 'noticeUID=([^&]+)', 1
        ) as notice_uid,
        {%- elif columna in columnas_centinela_es_valor() %}
        {#- Tres estados: "No Definido" no equivale a "No" (RN10). -#}
        {{ columna }} as {{ columna }},
        {%- else %}
        {%- set limpio = sin_centinela(columna) %}
        {%- set tipo = tipo_de(columna) %}
        {%- if tipo %}
        try_cast({{ limpio }} as {{ tipo }}) as {{ columna }},
        {%- else %}
        {{ limpio }} as {{ columna }},
        {%- endif %}
        {%- endif %}
        {%- endfor %}

        {#- El contador. Una columna falló el casting si tenía valor —después de
            sacarle el centinela— y el `try_cast` dio nulo. Usa los MISMOS
            ayudantes que la proyección de arriba: si se escribieran por
            separado, el contador podría medir algo distinto de lo que la
            columna guarda. -#}
        (
        {%- for columna in columnas_monetarias() + columnas_fechas() + columnas_enteras() %}
            case when {{ sin_centinela(columna) }} is not null
                  and try_cast({{ sin_centinela(columna) }} as {{ tipo_de(columna) }}) is null
                 then 1 else 0 end{{ " +" if not loop.last }}
        {%- endfor %}
        ) as castings_fallidos

    from origen

)

select * from limpio