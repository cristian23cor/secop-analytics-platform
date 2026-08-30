{#
  La serie temporal que la fuente destruye cada vez que se regenera. Una fila por
  cada estado distinto que tuvo cada contrato.

  ## Qué cuenta como cambio

  La capa cruda ya deduplicó por bytes, así que cada observación en disco cambió en
  algo. Pero ese algo puede ser un nombre de entidad corregido o un espacio doble,
  y eso no es un cambio en el mundo sino en el registro. Por eso versiona sobre las
  28 columnas materiales, y la lista sale del macro generado desde `columnas.py`.

  El valor cosmético queda congelado en la observación que abrió la versión. Una
  fila del snapshot dice "así se veía este contrato cuando lo observamos", y con
  las 67 columnas viniendo de la misma respuesta de la API eso es literalmente
  cierto. Tomar las cosméticas de una observación posterior mezclaría dos momentos
  sin dar ninguna señal, y rompería la trazabilidad con el hash, que es el hash de
  los bytes de una observación.

  El valor al día vive en las dimensiones. El nombre viejo acá no molesta porque
  nadie debería leerlo de acá.

  Lo que sí se pierde es cuándo cambió una cosmética. Ninguna pregunta de negocio
  lo necesita, pero es una pérdida y no un efecto neutro.

  ## Por qué las fechas no se llaman `vigente_desde`

  La plataforma no sabe cuándo cambió el contrato, sabe cuándo el cambio se volvió
  visible. Y con la fuente saltando días, el intervalo se estira sin que haya
  pasado nada: uno de cinco días no significa que el contrato estuvo cinco días
  igual, significa que no lo miramos.

  El intervalo es semiabierto, igual que el rango de la ingesta: el `hasta` es la
  fecha de la observación siguiente, no la última en que se vio igual. Así no
  quedan huecos y `desde <= t < hasta` da exactamente una fila por instante. El
  último cierra en nulo, y no en una fecha futura falsa: acá el nulo significa "es
  el último estado que vimos", y una fecha inventada borraría eso.

  ## Por qué el hecho es estrecho

  Una tabla de hechos lleva llaves, fechas y medidas; los atributos descriptivos
  van en las dimensiones. Las 32 cosméticas se fueron a `dim_entidad`,
  `dim_proveedor` y `dim_modalidad`.

  Eso fue además la diferencia entre 734 segundos y unos 60. La primera versión
  hacía `select *` y arrastraba las 73 columnas de staging, o sea una copia entera
  de `stg_contratos` con cuatro columnas más. Medido: construir la huella cuesta
  3,6 s, las dos ventanas 5,1 s, escribir 11 columnas con ventana 8,9 s, y escribir
  73 columnas sin ventana 109 s. Toda la lógica sospechada sumaba nueve segundos.

  Antes de medir, el sospechoso era la huella de 28 columnas concatenadas.
  Optimizarla habría costado una tarde para ahorrar 3,6 segundos.

  ## Sobre el orden y la memoria

  La ventana particiona por contrato. Hoy hay 2.849.209 contratos con máximo dos
  observaciones cada uno, así que es barata. Es una foto de un momento muy temprano
  y va a cambiar: cada regeneración ingerida sube ese máximo. El modelo está
  escrito para que el número de observaciones por contrato no importe, pero eso no
  está verificado contra datos reales porque todavía no existen.
#}

{{ config(materialized="table") }}

with observaciones as (

    select
        *,
        {#- La fecha de extracción como texto ISO ordena igual que como fecha, y
            evita un cast que no hace falta. Sale de la RUTA y no de los
            metadatos de la fila: es la partición de la que vino. -#}
        ruta_fecha_extraccion as observado_en
    from {{ ref("stg_contratos") }}

),

{#- Una huella de solo lo material. Comparar la huella contra la de la
    observación anterior del mismo contrato es lo que decide si hay versión
    nueva.

    Se concatena con un separador que no aparece en los datos y con los nulos
    marcados aparte: sin eso, ('a', null) y ('a', '') producirían la misma
    huella, y un valor que pasa de vacío a nulo (o al revés) no generaría
    versión. Es el mismo cuidado que `canonicalizar()` tiene en la ingesta. -#}
huellas as (

    select
        *,
        {%- set materiales = columnas_materiales() %}
        concat_ws(
            '\x1f'
            {%- for columna in materiales %},
            coalesce(cast({{ columna }} as varchar), '\x00NULO')
            {%- endfor %}
        ) as huella_material
    from observaciones

),

{#- La observación anterior del mismo contrato, por orden de extracción. -#}
con_anterior as (

    select
        *,
        lag(huella_material) over (
            partition by id_contrato order by observado_en
        ) as huella_anterior
    from huellas

),

{#- Solo las que cambiaron algo material. La primera observación de cada
    contrato entra siempre: `huella_anterior` es nula y ese nulo significa "no
    había nada antes", no "no cambió". -#}
versiones as (

    select *
    from con_anterior
    where huella_anterior is null
       or huella_material != huella_anterior

),

cerradas as (

    select
        *,
        observado_en as observado_desde,
        {#- Semiabierto: cierra donde empieza la siguiente versión. El último
            queda en NULL: es el estado vigente hasta donde sabemos. -#}
        lead(observado_en) over (
            partition by id_contrato order by observado_en
        ) as observado_hasta,
        row_number() over (
            partition by id_contrato order by observado_en
        ) as version
    from versiones

)

select
    id_contrato,
    version,
    observado_desde,
    observado_hasta,
    observado_hasta is null as es_version_vigente,

    {#- `motivo_de_cierre` existe porque un `observado_hasta` nulo significa
        TRES cosas distintas, y un nulo que significa tres cosas es un fallo
        silencioso esperando (D8).

        Un contrato que pasa a estado terminal deja de ser barrido por el flujo
        3, así que su última versión queda abierta para siempre: honesto ("es
        lo último que observé") pero un lector lo va a leer como "sigue
        activo".

        Medido el 29/08/2026 sobre 2.881.640 versiones, y la suma cierra exacta:

        | valor | versiones |
        |---|---|
        | `version_nueva`        |    32.431 |
        | `abierta`              | 2.842.560 |
        | `fuera_de_observacion` |     6.649 |

        La lista de estados sale del macro generado, que la toma de `flujos.py`:
        es la misma con la que el flujo 3 arma su filtro, así que "sigue en
        observación" significa exactamente "la ingesta lo sigue barriendo".
        Escribirla acá a mano daría dos definiciones del universo vivo, y el día
        que se separen esta columna mentiría sin fallar.

        Hereda además el supuesto sin verificar de la pregunta abierta 3: que los
        estados terminales ya no se mueven. Si un contrato cerrado recibe pagos
        rezagados, esta columna dice "fuera de observación" sobre algo que sí
        cambió y que nadie está mirando.

        Un `estado_contrato` nulo cae en `fuera_de_observacion`: `null in (...)`
        no da verdadero. Hoy no hay ninguno, y es la lectura prudente. -#}
    case
        when observado_hasta is not null then 'version_nueva'
        when estado_contrato in (
            {%- for estado in estados_vivos() %}
            '{{ estado }}'{{ "," if not loop.last }}
            {%- endfor %}
        ) then 'abierta'
        else 'fuera_de_observacion'
    end as motivo_de_cierre,

    {#- El flujo que trajo esta observación. Significa "quién la trajo primero",
        no "por qué caminos podía llegar": la deduplicación por bytes se queda
        con la etiqueta del primero que la vio. -#}
    flujo,
    hash,

    {#- Solo las MATERIALES. Las cosméticas viven en las dimensiones: son
        atributos descriptivos, no medidas, y repetirlas acá duplicaría 1,2 GB
        sin agregar información. Ver arriba. -#}
    {%- for columna in columnas_materiales() %}
    {{ columna }},
    {%- endfor %}

    {#- Las IMPOSIBLES. No son medidas (no cambian nunca, ese es su punto) pero
        sin ellas el hecho no se puede unir con nada y la tabla queda
        inservible.

        La lista sale del macro y no se escribe acá. Antes estaban las cuatro que
        son llaves hacia dimensiones, elegidas a mano, y faltaban
        `fecha_de_firma` y `fecha_de_inicio_del_contrato`. Lo destapó
        `fct_contratos`, que necesita la fecha de firma. Una lista a mano se
        separa de la de `columnas.py` y nadie se entera; generada, agregar una
        imposible allá la trae hasta acá sola.

        `id_contrato` se excluye porque ya está arriba como llave. -#}
    {%- for columna in columnas_imposibles() if columna != "id_contrato" %}
    {{ columna }},
    {%- endfor %}

    {#- La llave hacia `dim_modalidad`. Se calcula con el mismo macro que la
        dimensión: dos definiciones de lo mismo se separan.

        Las tres columnas de modalidad son cosméticas y aun así el hecho las
        lleva, en forma de llave. Que una columna no genere versión no la excluye
        del hecho: son dos ejes distintos, y la modalidad es cosmética justamente
        porque nunca cambia, que es lo que la vuelve un atributo estable con el
        que agrupar. -#}
    {{ llave_de_modalidad() }} as llave_modalidad,
    {{ llave_de_geografia() }} as llave_geografia,

    {#- Trazabilidad hasta el archivo. `notice_uid` es un tercer identificador
        que no aparece en ninguna otra columna (H6) y probablemente la llave
        hacia el dataset de Procesos de Contratación. -#}
    notice_uid,
    castings_fallidos

from cerradas