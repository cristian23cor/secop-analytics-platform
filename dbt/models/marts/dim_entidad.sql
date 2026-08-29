{#
  `dim_entidad` — quién contrata, con historia.

  5.162 entidades. Es la primera dimensión del proyecto y sienta el patrón para
  `dim_proveedor`, `dim_modalidad` y `dim_geografia`.

  ## Por qué tiene historia, si casi nada cambia

  Medido el 28/08/2026 sobre las 2.902.163 observaciones, contando entidades con
  al menos un cambio por atributo:

      nombre_entidad          0
      orden                   0
      rama                    0
      sector                  0
      entidad_centralizada    6

  Cuatro atributos estables y uno que se movió en seis entidades. Con eso, una
  dimensión de tipo 1 —pisar el valor y no guardar historia— parece suficiente.
  No lo es, por tres razones:

  1. **El cambio existe y está medido.** Esas seis entidades pasaron de
     "Centralizada" a "Descentralizada" entre el 23 y el 25 de agosto,
     arrastrando 20.675 contratos. Con tipo 1 ese evento se pierde, y esta vez
     no lo destruiría la fuente sino nosotros. Es el error que falta, que es el
     que este proyecto evita en cada decisión.
  2. **"Estable" se midió sobre cinco días.** Que `sector` no haya cambiado
     entre dos regeneraciones no dice casi nada sobre un año. Diseñar tipo 1 es
     apostar a una estabilidad observada en una ventana que ya sabemos corta.
  3. **La asimetría del error.** Si sobra historia, quedan columnas de fecha que
     nadie usa. Si falta, el estado anterior se pierde para siempre.

  ## La llave es `codigo_entidad`, y está medido

  De las tres candidatas:

  - **`codigo_entidad`** — 5.162 valores, cada uno con **exactamente un** NIT y
    **exactamente un** nombre. Cero excepciones. Es la llave.
  - `nit_entidad` — 4.475 valores, y **281 tienen más de un código**. Son
    entidades jurídicas con varias unidades ejecutoras que contratan por
    separado: el SENA y sus regionales, por ejemplo. Usarlo colapsaría unidades
    distintas.
  - `nombre_entidad` — cosmética, y además 5.140 nombres para 5.162 códigos:
    **22 nombres se repiten entre entidades distintas**. Puede ser homonimia
    real —dos hospitales San José en departamentos distintos— o suciedad. En
    cualquier caso, no es llave. ⚠ Y es una advertencia para cualquiera que
    quiera agrupar por nombre en un tablero.

  ## Cómo se une con el hecho

  Por `codigo_entidad` **más rango de fechas**: el `observado_desde` del hecho
  tiene que caer dentro del intervalo de la versión de la entidad.

  Se evaluó la alternativa de Kimball —una llave sustituta en el hecho que
  apunte a la versión correcta— y se descartó por tres motivos:

  - **El hecho ya es un SCD2.** Sus `observado_desde` / `observado_hasta` son el
    mismo tiempo que la dimensión representa. Dos representaciones del tiempo en
    el mismo modelo es como se producen las inconsistencias que nadie detecta.
  - **Daría precisión falsa.** Con la fuente saltando días (H34), una versión del
    hecho puede abarcar un intervalo dentro del cual la entidad cambió — y el
    hecho no se entera, porque los atributos de entidad son cosméticos y no
    generan versión. La llave sustituta contestaría con exactitud una pregunta
    cuya respuesta real es ambigua.
  - **Contradiría lo ya decidido.** El hecho congela las cosméticas en la
    observación que abrió la versión, para que cada fila sea una foto real
    trazable hasta su hash. La llave sustituta reintroduciría la mezcla de
    momentos que ahí se evitó.

  Si algún día la dimensión resulta cambiar mucho más, la llave sustituta se
  agrega encima sin rehacer nada: el hecho ya guarda `codigo_entidad` y las
  fechas, que es todo lo que hace falta para calcularla.

  ⚠ **Para 5.156 de las 5.162 entidades, unir solo por `codigo_entidad` da el
  mismo resultado que unir por llave y fecha.** La diferencia aparece únicamente
  en las seis reclasificadas. Eso hace que el error —olvidar el rango— sea
  silencioso en el 99,9% de los casos, que es exactamente lo que lo vuelve
  peligroso.
#}

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
    CONTRATO, así que la misma entidad aparece miles de veces por partición.

    ⚠ Se toma `min()` de cada atributo y no un valor cualquiera, para que el
    resultado sea determinista. Si dos contratos de la misma entidad en la misma
    partición trajeran atributos distintos —que no debería pasar, pero nada lo
    impide— un `any_value()` daría un resultado que cambia entre corridas y el
    modelo dejaría de ser reproducible sin que nada falle. -#}
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