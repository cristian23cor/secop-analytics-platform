{#
  `fct_contratos_snapshot` es la serie temporal que la fuente destruye cuando se
  sobrescribe en cada regeneración. Este modelo reconstruye la historia de cada
  contrato con una fila por cada estado distinto que tuvo.

  ## Qué cuenta como cambio

  Raw ya deduplicó por bytes, así que cada observación en disco cambió en algo. Pero
  ese cambio puede ser cosmético, un nombre de entidad corregido o un espacio doble en
  `localizaci_n`, y eso no es un cambio en el mundo sino en el registro. Versionar por
  las 67 columnas llenaría la serie con filas donde lo único que cambia es un espacio.
  Por eso versiona sobre las 28 materiales, y la lista sale de `columnas.py` a través
  del macro generado, para que D6 y la definición del esquema no se separen.

  El valor cosmético queda congelado en la observación que abrió la versión y no se
  actualiza con el último valor visto. Una fila del snapshot dice "así se veía este
  contrato cuando lo observamos", y con las 67 columnas de la misma observación eso es
  literalmente cierto: se vieron juntas, el mismo día, en la misma respuesta de la API.
  Tomar las cosméticas de una observación posterior mezclaría dos momentos sin dar
  ninguna señal. Y rompería la trazabilidad, porque `hash` es el hash de los bytes de
  una observación: si las cosméticas vinieran de otra fila, la tupla no correspondería
  a ningún hash real y se cortaría la cadena que va de un dato del tablero al
  `.jsonl.gz` que lo respalda.

  El valor al día vive en `dim_entidad`, que se une por `codigo_entidad`, una columna
  clasificada como imposible. El nombre viejo en la tabla de hechos no molesta porque
  no debería leerse desde ahí.

  D6 decía que una cosmética "se pisa el valor actual". Esa frase describe un SCD2 de
  dimensiones, donde hay una sola fila por entidad y pisar tiene sentido. Acá la tabla
  es un snapshot acumulativo y no existe "la fila actual" que pisar. La distinción
  quedó documentada en `01_modelo_dimensional.md`.

  Lo que sí se pierde es cuándo cambió una cosmética. Ninguna pregunta de negocio lo
  necesita, pero es una pérdida real.

  ## `observado_desde` / `observado_hasta`, y por qué no se llaman `vigente_*`

  La plataforma no sabe cuándo cambió el contrato. Sabe cuándo el cambio se volvió
  visible. Un pago detectado el 25 pudo ocurrir cualquier día desde la observación
  anterior.

  Con la fuente saltando días, el intervalo se estira sin que nada haya pasado. No se
  regenera a diario (H34): entre cortes conocidos hay saltos de dos y de cinco días, y
  al momento de escribir esto lleva cinco congelada. Un intervalo de cinco días no
  significa que el contrato estuvo cinco días igual, significa que no lo miramos.

  El intervalo es semiabierto, igual que `_rango()` en la ingesta: `observado_hasta` es
  la fecha de la observación siguiente, no la última en que se vio igual. Así no quedan
  huecos entre versiones consecutivas y `desde <= t < hasta` da exactamente una fila
  por instante.

  El último cierra en NULL, que es D8. No se usa 9999-12-31, que inventa un dato para
  no manejar nulos: acá el nulo significa "es el último estado que vimos", y una fecha
  falsa borraría eso.

  ## Por qué el hecho es estrecho

  Una tabla de hechos lleva llaves, fechas y medidas; los atributos descriptivos viven
  en las dimensiones. Las 32 cosméticas se van a `dim_entidad`, `dim_proveedor` y
  `dim_modalidad`.

  Eso también fue la diferencia entre 734 segundos y una fracción de eso. La primera
  versión hacía `select *` y arrastraba las 73 columnas de staging: una copia entera de
  `stg_contratos` con cuatro columnas más, 1,2 GB duplicados en disco sin agregar
  información. Medido el 28/08/2026 sobre 2,9 millones de filas y con 3 GB de RAM (R3):

  | Etapa | Costo |
  |---|---|
  | Construir la huella de 28 columnas | 3,6 s |
  | Las dos ventanas (`lag` y `lead`) | 5,1 s |
  | Escribir 11 columnas con ventana | 8,9 s |
  | Escribir 73 columnas sin ventana | 109 s |
  | El modelo completo, con `select *` | 734 s |

  La huella y el ordenamiento suman nueve segundos: el 98,8% del tiempo era escribir
  columnas anchas después de ordenar. Y la relación no es lineal, seis veces más
  columnas costaban ochenta veces más tiempo, que es la firma del volcado a disco
  cuando el ancho deja de entrar en memoria.

  Antes de medir, el sospechoso era la huella de 28 columnas concatenadas. Optimizarla
  habría costado una tarde para ahorrar 3,6 segundos. Era el tercer caso del día en que
  la medición contradijo la hipótesis. R3 volvió a hacer lo que ya había hecho con el
  modelo frontera: la restricción de memoria empujó hacia el diseño correcto en vez de
  alejarlo, porque el problema de rendimiento y el de modelado eran el mismo.

  ## Sobre el orden y la memoria

  La ventana particiona por `id_contrato`. Medido el 28/08/2026 hay 2.849.209
  contratos, con máximo dos observaciones cada uno, así que hoy la ventana es barata y
  R3 no se queja.

  Es una foto de un momento muy temprano y va a cambiar: cada regeneración ingresada
  sube ese máximo. El modelo está escrito para que el número de observaciones por
  contrato no importe, porque la ventana no materializa el grupo entero, pero ese caso
  no está verificado contra datos reales porque todavía no existe.
#}

{#- La fecha de extracción como texto ISO ordena igual que como fecha y evita un cast
    que no hace falta. Sale de la ruta y no de los metadatos de la fila: es la
    partición de la que vino la observación. -#}

{#- La huella de solo lo material. Comparar la huella contra la observación anterior del
    mismo contrato es lo que decide si hay una versión nueva.

    Se concatena con un separador que no aparece en los datos y con los nulos marcados
    aparte. Sin eso, `('a', null)` y `('a', '')` producirían la misma huella, y un valor
    que pasa de vacío a nulo, o al revés, no generaría versión. Es el mismo cuidado que
    `canonicalizar()` tiene en la ingesta. -#}

{#- La observación anterior del mismo contrato, en orden de extracción. -#}

{#- Solo las que cambiaron algo material. La primera observación de cada contrato entra
    siempre: `huella_anterior` es nula y ese nulo significa "no había nada antes",
    no "no cambió". -#}

{#- Semiabierto: cierra donde empieza la siguiente versión. El último intervalo queda en
    NULL, que es el estado vigente hasta donde sabemos. -#}

{#- El flujo que trajo esta observación. Eso significa "quién la trajo primero", no
    "por qué caminos podía llegar": la deduplicación por bytes se queda con la etiqueta
    del primero que la vio. -#}

{#- Solo las columnas materiales. Las cosméticas viven en las dimensiones: son
    atributos descriptivos, no medidas, y repetirlas acá duplicaría 1,2 GB sin aportar
    información. -#}

{#- Las imposibles que son llaves hacia las dimensiones. No son medidas, no cambian
    nunca, pero sin ellas el hecho no se puede unir con nada y la tabla queda
    inservible. -#}

{#- La llave hacia `dim_modalidad`. Se calcula con el mismo macro que la dimensión,
    porque dos definiciones de lo mismo se separan.

    Que una columna no genere versión (D6) no la excluye del hecho: son dos ejes
    distintos, y la modalidad es cosmética justamente porque nunca cambia, lo que la
    vuelve un atributo estable para agrupar. -#}

{#- Trazabilidad hasta el archivo. `notice_uid` es un tercer identificador que no
    aparece en ninguna otra columna (H6) y probablemente es la llave hacia el dataset
    de procesos de contratación. -#}

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
    huella, y un valor que pasa de vacío a nulo —o al revés— no generaría
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
            queda en NULL — es el estado vigente hasta donde sabemos. -#}
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

    {#- El flujo que trajo esta observación. ⚠ Significa "quién la trajo
        primero", no "por qué caminos podía llegar": la deduplicación por bytes
        se queda con la etiqueta del primero que la vio. -#}
    flujo,
    hash,

    {#- Solo las MATERIALES. Las cosméticas viven en las dimensiones: son
        atributos descriptivos, no medidas, y repetirlas acá duplicaría 1,2 GB
        sin agregar información. Ver arriba. -#}
    {%- for columna in columnas_materiales() %}
    {{ columna }},
    {%- endfor %}

    {#- Las IMPOSIBLES que son llaves hacia las dimensiones. No son medidas
        —no cambian nunca, ese es su punto— pero sin ellas el hecho no se puede
        unir con nada y la tabla queda inservible. -#}
    codigo_entidad,
    nit_entidad,
    proceso_de_compra,
    codigo_de_categoria_principal,

    {#- La llave hacia `dim_modalidad`. Se calcula con el mismo macro que la
        dimensión: dos definiciones de lo mismo se separan.

        ⚠ Las tres columnas de modalidad son COSMÉTICAS y aun así el hecho las
        lleva, en forma de llave. Que una columna no genere versión (D6) no la
        excluye del hecho: son dos ejes distintos, y la modalidad es cosmética
        justamente porque nunca cambia — lo que la vuelve un atributo estable
        con el que agrupar. Ver `dim_modalidad`. -#}
    {{ llave_de_modalidad() }} as llave_modalidad,
    {{ llave_de_geografia() }} as llave_geografia,

    {#- Trazabilidad hasta el archivo. `notice_uid` es un tercer identificador
        que no aparece en ninguna otra columna (H6) y probablemente la llave
        hacia el dataset de Procesos de Contratación. -#}
    notice_uid,
    castings_fallidos

from cerradas