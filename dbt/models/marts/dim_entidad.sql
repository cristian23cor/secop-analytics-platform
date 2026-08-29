{#
  `dim_entidad` representa a quién contrata y conserva la historia de esos cambios.

  Hay 5.162 entidades. Esta dimensión es el patrón base del proyecto y sirve como
  referencia para `dim_proveedor`, `dim_modalidad` y `dim_geografia`.

  ## Por qué la historia importa aunque casi nada cambie

  Medido el 28/08/2026 sobre 2.902.163 observaciones, las entidades con al menos un
  cambio por atributo quedaron así:

      nombre_entidad          0
      orden                   0
      rama                    0
      sector                  0
      entidad_centralizada    6

  Cuatro atributos son estables y uno cambió en seis entidades. Con ese nivel de
  cambio una dimensión tipo 1, que pisa el valor sin guardar historia, parecería
  suficiente.

  Pero el cambio existe y está medido: esas seis entidades pasaron de "Centralizada"
  a "Descentralizada" entre el 23 y el 25 de agosto, y arrastraron 20.675 contratos.
  Con un tipo 1 ese evento se pierde, y esta vez no lo destruiría la fuente sino la
  decisión del modelo. Sumado a eso, la estabilidad se midió en cinco días: que
  `sector` no haya cambiado en dos regeneraciones no dice casi nada sobre un año. Y
  el error no es simétrico. Si sobra historia, quedan columnas de fecha que nadie
  usa; si falta, el estado anterior se pierde para siempre.

  ## La llave es `codigo_entidad`, y está medida

  - `codigo_entidad`: 5.162 valores, cada uno con exactamente un NIT y exactamente
    un nombre, sin excepciones. Es la llave natural.
  - `nit_entidad`: 4.475 valores, y 281 de ellos tienen más de un código. Son
    entidades jurídicas con varias unidades ejecutoras que contratan por separado,
    como el SENA y sus regionales. Usarlo colapsaría unidades distintas.
  - `nombre_entidad`: cosmético, y además hay 5.140 nombres para 5.162 códigos, o
    sea que 22 se repiten entre entidades distintas. Puede ser homonimia real o
    suciedad; en cualquier caso no sirve como llave.

  ## Cómo se une con el hecho

  La unión se hace por `codigo_entidad` y por rango de fechas: el `observado_desde`
  del hecho debe caer dentro del intervalo de la versión de la entidad.

  La alternativa de Kimball, una llave sustituta en el hecho para apuntar a la
  versión correcta, se descartó. El hecho ya es un SCD2 y sus `observado_desde` /
  `observado_hasta` representan el mismo tiempo que la dimensión; dos
  representaciones del tiempo en el mismo modelo son una fuente clásica de
  inconsistencias. Daría además precisión falsa: con la fuente saltando días (H34),
  una versión del hecho puede abarcar un intervalo en el que la entidad cambió, y el
  hecho no se entera, porque los atributos de entidad son cosméticos y no generan
  versión. Y contradiría lo que ya está decidido: el hecho congela las cosméticas en
  la observación que abrió la versión, para que cada fila sea una foto real y
  trazable hasta su hash. La llave sustituta reintroduciría la mezcla de momentos
  que se quiso evitar.

  Si la dimensión cambia mucho más adelante, la llave sustituta se puede agregar
  encima sin rehacer nada: el hecho ya guarda `codigo_entidad` y las fechas, que es
  todo lo que hace falta para calcularla.

  Para 5.156 de las 5.162 entidades, unir solo por `codigo_entidad` da el mismo
  resultado que unir por llave y fecha. La diferencia aparece solo en las seis
  reclasificadas. Ver `vigente_en()`.
#}

{#- Los atributos. `nit_entidad` es imposible como cambio y no se usa para la
    versión, pero entra porque es el identificador legal y la llave hacia fuentes
    externas. -#}

{#- Una fila por entidad y observación. `stg_contratos` tiene una fila por
    contrato, así que la misma entidad aparece miles de veces por partición.

    De cada atributo se toma `min()`, no un valor cualquiera, para que el resultado
    sea determinista. Si dos contratos de la misma entidad en la misma partición
    trajeran atributos distintos (no debería pasar, pero nada lo impide), un
    `any_value()` devolvería algo distinto en cada corrida y el modelo dejaría de
    ser reproducible. -#}

{#- Semiabierto, y NULL en la vigente. Este criterio coincide con el hecho y con
    `_rango()` en la ingesta: `desde <= t < hasta` selecciona una sola fila y evita
    superposiciones. -#}

{{ config(materialized="table") }}

with observaciones as (

    select
        codigo_entidad,
        ruta_fecha_extraccion as observado_en,

        {#- Los atributos. `nit_entidad` es IMPOSIBLE y no cambia, pero entra
            igual: es el identificador legal y la llave hacia cualquier fuente
            externa. -#}
        nit_entidad,
        nombre_entidad,
        orden,
        rama,
        sector,
        entidad_centralizada

    from {{ ref("stg_contratos") }}
    where codigo_entidad is not null

),

{#- Una fila por entidad y observación. `stg_contratos` tiene una fila por
    contrato, así que la misma entidad aparece miles de veces por partición.

    De cada atributo se toma `min()`, no un valor cualquiera, para que el resultado
    sea determinista. Si dos contratos de la misma entidad en la misma partición
    trajeran atributos distintos (no debería pasar, pero nada lo impide), un
    `any_value()` devolvería algo distinto en cada corrida y el modelo dejaría de
    ser reproducible. -#}
por_observacion as (

    select
        codigo_entidad,
        observado_en,
        min(nit_entidad)        as nit_entidad,
        min(nombre_entidad)     as nombre_entidad,
        min(orden)              as orden,
        min(rama)               as rama,
        min(sector)             as sector,
        min(entidad_centralizada) as entidad_centralizada,
        count(*)                as contratos_en_la_observacion
    from observaciones
    group by codigo_entidad, observado_en

),

huellas as (

    select
        *,
        concat_ws(
            '\x1f',
            coalesce(nit_entidad, '\x00NULO'),
            coalesce(nombre_entidad, '\x00NULO'),
            coalesce(orden, '\x00NULO'),
            coalesce(rama, '\x00NULO'),
            coalesce(sector, '\x00NULO'),
            coalesce(entidad_centralizada, '\x00NULO')
        ) as huella
    from por_observacion

),

con_anterior as (

    select
        *,
        lag(huella) over (
            partition by codigo_entidad order by observado_en
        ) as huella_anterior
    from huellas

),

versiones as (

    select * from con_anterior
    where huella_anterior is null
       or huella != huella_anterior

)

select
    codigo_entidad,
    row_number() over (
        partition by codigo_entidad order by observado_en
    ) as version,

    observado_en as observado_desde,
    {#- Semiabierto, y NULL en la vigente. Mismo criterio que el hecho y que
        `_rango()` en la ingesta: `desde <= t < hasta` selecciona una fila y
        solo una. -#}
    lead(observado_en) over (
        partition by codigo_entidad order by observado_en
    ) as observado_hasta,
    lead(observado_en) over (
        partition by codigo_entidad order by observado_en
    ) is null as es_version_vigente,

    nit_entidad,
    nombre_entidad,
    orden,
    rama,
    sector,
    entidad_centralizada,
    contratos_en_la_observacion

from versiones