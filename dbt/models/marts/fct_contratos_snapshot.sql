{#
  `fct_contratos_snapshot` — la serie temporal que la fuente destruye.

  Es el modelo que justifica el proyecto entero. La fuente se sobrescribe en
  cada regeneración, así que nadie puede saber cuánto valía un contrato antes de
  una adición ni cuánto se había pagado en marzo. Acá esa historia se
  reconstruye, con una fila por cada estado distinto que un contrato tuvo.

  ## Qué cuenta como cambio: las 28 columnas MATERIALES, no las 67

  Raw ya deduplicó por bytes, así que toda observación en disco cambió en algo.
  Pero pudo ser cosmético — un nombre de entidad corregido, un espacio doble en
  `localizaci_n`— y eso no es un cambio en el mundo, es un cambio en el
  registro. Versionar por las 67 llenaría la serie de filas donde lo único
  distinto es un espacio.

  La lista sale de `columnas.py` vía el macro generado, que es lo que impide que
  se separe de la clasificación que usa el resto del proyecto (D6).

  ⚠ **El valor cosmético queda CONGELADO en el de la observación que abrió la
  versión, no actualizado al último visto.** Si una entidad se renombra y el
  contrato no cambia nada material, esta tabla sigue mostrando el nombre viejo.

  Es deliberado, y la razón es que **una fila del snapshot dice "así se veía este
  contrato cuando lo observamos"**. Con las 67 columnas provenientes de la misma
  observación eso es literalmente cierto: se vieron juntas, el mismo día, en la
  misma respuesta de la API. Tomar las cosméticas de una observación posterior
  haría que la fila mezclara dos momentos sin que nada lo advirtiera.

  Y rompería la trazabilidad: `hash` es el hash de los bytes de UNA observación.
  Si las cosméticas vinieran de otra, la fila no correspondería a ningún hash
  real y se cortaría la cadena que hoy permite ir de un dato del tablero al
  `.jsonl.gz` que lo respalda.

  **Para el valor al día está `dim_entidad`**, que se une por `codigo_entidad`
  —clasificada IMPOSIBLE, o sea que no cambia—. El nombre viejo en la tabla de
  hechos no molesta porque nadie debería leerlo de ahí.

  ⚠ D6 decía que una cosmética "se pisa el valor actual". Esa frase describe un
  SCD2 de dimensiones, donde hay una sola fila por entidad y pisarla tiene
  sentido. Acá la tabla es un snapshot acumulativo: no existe "la fila actual"
  que pisar. Corregido en `01_modelo_dimensional.md`.

  Lo que sí se pierde: **cuándo** cambió una cosmética. Ninguna pregunta de
  negocio lo necesita, pero es una pérdida y no un efecto neutro.

  ## `observado_desde` / `observado_hasta`, y por qué no se llaman `vigente_*`

  La plataforma no sabe cuándo cambió el contrato: sabe cuándo el cambio se
  volvió **visible**. Un pago detectado el 25 pudo ocurrir cualquier día desde
  la observación anterior.

  ⚠ **Y con la fuente saltando días, el intervalo se estira sin que nada haya
  pasado.** La fuente no se regenera a diario (H34): entre los cortes conocidos
  hay saltos de dos y de cinco días, y al escribir esto lleva cinco congelada.
  Un intervalo de cinco días no significa que el contrato estuvo cinco días
  igual: significa que no lo miramos en cinco días. Los nombres de las columnas
  son la única defensa contra esa lectura, y por eso no se negocian.

  **El intervalo es semiabierto**, igual que `_rango()` en la ingesta:
  `observado_hasta` es la fecha de la observación SIGUIENTE, no la última en que
  se vio igual. Así no quedan huecos entre versiones consecutivas y
  `desde <= t < hasta` da exactamente una fila por instante.

  **El último intervalo cierra en NULL**, que es D8. No en 9999-12-31: eso
  inventa un dato para ahorrarse manejar nulos, y el nulo acá significa algo
  preciso —"es el último estado que vimos"— que una fecha falsa borraría.

  ## Por qué el hecho es ESTRECHO: 28 columnas materiales, no las 67

  Una tabla de hechos lleva llaves, fechas y medidas; los atributos descriptivos
  viven en las dimensiones. Eso ya estaba en el modelo dimensional, y acá se
  cumple: entran las 28 materiales —que son las medidas y los estados cuya
  historia el proyecto existe para reconstruir— y las 32 cosméticas se van a
  `dim_entidad`, `dim_proveedor` y `dim_modalidad`.

  **Y resultó ser también la diferencia entre 734 segundos y una fracción de
  eso.** La primera versión hacía `select *` y arrastraba las 73 columnas de
  staging: una copia entera de `stg_contratos` con cuatro columnas más, 1,2 GB
  duplicados en disco sin agregar información.

  Medido el 28/08/2026, sobre 2,9 millones de filas y con 3 GB de RAM (R3):

  | Etapa | Costo |
  |---|---|
  | Construir la huella de 28 columnas | 3,6 s |
  | Las dos ventanas (`lag` y `lead`) | 5,1 s |
  | Escribir **11** columnas con ventana | 8,9 s |
  | Escribir **73** columnas sin ventana | 109 s |
  | El modelo completo, con `select *` | **734 s** |

  Toda la lógica —la huella, el ordenamiento— suma nueve segundos: **el 98,8%
  del tiempo era escribir columnas anchas después de ordenar.** Y la relación no
  es lineal: seis veces más columnas costaban ochenta veces más tiempo, que es
  la firma del volcado a disco cuando el ancho deja de entrar en memoria.

  ⚠ **La lección es de método, no de SQL.** Antes de medir, el sospechoso era la
  huella de 28 columnas concatenadas, y optimizarla habría costado una tarde
  para ahorrar 3,6 segundos. Era el tercer caso del día en que la medición
  contradijo la hipótesis.

  Y R3 volvió a hacer lo que ya había hecho con el modelo frontera: la
  restricción de memoria empujó hacia el diseño correcto en vez de alejar de él.
  El problema de rendimiento y el de modelado eran el mismo.

  ## Sobre el orden y la memoria

  La ventana particiona por `id_contrato`. Medido el 28/08/2026: 2.849.209
  contratos, **máximo dos observaciones cada uno** y ninguno con más, así que
  hoy la ventana es barata y R3 no muerde.

  Eso es una foto de un momento muy temprano y va a cambiar: cada regeneración
  ingerida sube ese máximo. El modelo está escrito para que el número de
  observaciones por contrato no importe —la ventana no materializa el grupo
  entero— pero **el caso de muchas observaciones por contrato no está
  verificado contra datos reales**, porque todavía no existe.
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

    {#- Trazabilidad hasta el archivo. `notice_uid` es un tercer identificador
        que no aparece en ninguna otra columna (H6) y probablemente la llave
        hacia el dataset de Procesos de Contratación. -#}
    notice_uid,
    castings_fallidos

from cerradas