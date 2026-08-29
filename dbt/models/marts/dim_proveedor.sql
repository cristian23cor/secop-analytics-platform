{#
  `dim_proveedor` describe quién recibe el dinero y conserva la historia de ese
  cambio.

  Tiene 929.946 proveedores, unas 180 veces más que `dim_entidad`, que tiene 5.162.
  Es la dimensión que prueba si el patrón construido con la entidad escala.

  ## La llave es `codigo_proveedor`, y cierra a medias la pregunta abierta 7

  Esa pregunta, si la llave es `documento_proveedor` o `codigo_proveedor`, venía
  abierta desde la exploración. Medido el 28/08/2026 sobre 2.902.163 observaciones,
  ninguna de las dos es perfecta:

  | | Valores | Nulos | Con más de un valor de la otra |
  |---|---|---|---|
  | `codigo_proveedor` | 929.946 | 0 | 15 con más de un documento |
  | `documento_proveedor` | 919.929 | 8.917 | 1.297 con más de un código |

  Una llave con 8.917 nulos no es una llave, y eso solo ya cierra la discusión. Las
  excepciones además son 15 contra 1.297, dos órdenes de magnitud, el 0,0016% de los
  códigos. Y sobre todo el código no se reutiliza entre proveedores distintos, que
  era la duda que importaba: los 101 códigos con más de un nombre se revisaron y son
  variantes de escritura del mismo proveedor, como `"karen cruz"` y `"karen lisset
  cruz montoya"`, o `"JAC AVENIDA CARACAS"` y `"JAC URBANIZACION AVENIDA CARACAS"`.

  `documento_proveedor` no queda descartado. Es el identificador legal y la vía hacia
  cruces con fuentes externas como el RUES, listas de sanciones y registros
  tributarios. Lo que no es, es la llave del modelo.

  Los 1.297 documentos con varios códigos son duplicación de catálogo: la fuente
  registró dos veces al mismo proveedor. Agrupar por `documento_proveedor` daría la
  respuesta correcta a preguntas como "cuánto contrató esta empresa en total", pero
  esa es una decisión del consumidor, no de la dimensión.

  ## Las marcas de conflicto dan cero

  `tiene_documentos_en_conflicto` y `tiene_nombres_en_conflicto` marcan cero filas
  sobre 930.071. El detector no está roto: detecta un caso que no ocurre.

  Los 15 códigos con varios documentos y los 101 con varios nombres se midieron
  agrupando solo por código, sin la fecha. Esos conflictos son entre observaciones
  distintas: el mismo código tenía un documento el 23 y otro el 25, y nunca dos
  valores en la misma foto. La dimensión los captura como dos versiones, que es lo
  que son. O sea que la fuente es internamente coherente dentro de cada partición.
  Las columnas se conservan porque no cuestan nada, y si algún día deja de serlo, son
  la señal.

  ## Lo que la historia capturó

  125 proveedores de 929.946 cambiaron algo en cinco días, y la mayoría fueron
  correcciones de escritura:

      "Daniela Córdoba Murillo"      → "DANIELA CORDOBA MURILLO"
      "FRANCISCO  ROBLEDO  CASTRO"   → "FRANCISCO ROBLEDO CASTRO"
      "UTPA2025"                     → "UNIÓN TEMPORAL PRODUCTORES A…"

  Uno cambió `es_pyme` de No a Sí. Cesiones todavía no hay ninguna capturada.

  ## Los 15 casos raros, que no son todos el mismo problema

  Se revisaron uno por uno y hay al menos tres fenómenos distintos:

  - Digitación: `830036667` y `8300366698`, el mismo NIT con un dígito de más.
  - Uniones temporales: un consorcio puede aparecer con el documento de uno u otro
    miembro.
  - Y uno donde el mismo código tiene un NIT de empresa y una cédula de persona
    natural, con nombres distintos: `"Serviteca la Bomba Sas"` y una persona. Ese
    código apunta a dos entidades legales.

  Son 15 sobre 929.946. Se documentan y no se corrigen: corregirlos exigiría elegir
  cuál de los dos documentos es el bueno, y eso es inventar una verdad que la fuente
  no tiene.

  ## Por qué tiene historia

  El criterio es el mismo que en `dim_entidad`, con una razón propia: el trío del
  proveedor es material, no cosmético, porque cambia con la cesión de contratos.
  28.557 tienen estado `cedido`. Que en cinco días no se haya capturado ninguna dice
  más sobre el largo de la ventana que sobre las cesiones. El hecho ya versiona
  cuando el proveedor cambia, y la dimensión tiene que poder explicar qué cambió.

  `tipodocproveedor` no sirve para derivar el tipo de persona. Falla en las dos
  direcciones: hay S.A.S. marcadas como "Cédula de Ciudadanía" y personas naturales
  marcadas como "NIT". Se conserva como evidencia de lo que la fuente declara, no
  como dato utilizable.

  ## Cómo se une con el hecho

  Por `codigo_proveedor` y rango de fechas, con el macro `vigente_en()`. Unir solo
  por llave duplica filas sin fallar; eso está explicado en `macros/dimensiones.sql`.
#}

{#- Una fila por proveedor y observación. De cada atributo se toma `min()`, no un
    valor cualquiera, para que el resultado sea determinista: hay 101 códigos cuyos
    contratos traen nombres distintos en la misma partición (variantes de escritura
    del mismo proveedor), y un `any_value()` elegiría uno distinto en cada corrida. -#}

{#- Marcas de los casos raros. `true` significa "esta fila necesita una mirada", no
    "esta fila está mal". -#}

{{ config(materialized="table") }}

with observaciones as (

    select
        codigo_proveedor,
        ruta_fecha_extraccion as observado_en,
        documento_proveedor,
        proveedor_adjudicado,
        tipodocproveedor,
        es_pyme,
        es_grupo
    from {{ ref("stg_contratos") }}
    where codigo_proveedor is not null

),

{#- Una fila por proveedor y observación. `min()` y no un valor cualquiera, para
    que el resultado sea determinista: hay 101 códigos cuyos contratos traen
    nombres distintos en la misma partición —variantes de escritura del mismo
    proveedor— y un `any_value()` elegiría uno distinto en cada corrida sin que
    nada falle. -#}
por_observacion as (

    select
        codigo_proveedor,
        observado_en,
        min(documento_proveedor)  as documento_proveedor,
        min(proveedor_adjudicado) as proveedor_adjudicado,
        min(tipodocproveedor)     as tipodocproveedor,
        min(es_pyme)              as es_pyme,
        min(es_grupo)             as es_grupo,
        count(*)                  as contratos_en_la_observacion,
        {#- Las señales de los casos raros, calculadas donde se pueden calcular.
            No se corrigen: se marcan, para que quien consuma la dimensión sepa
            que esas filas necesitan mirarse. -#}
        count(distinct documento_proveedor)  as documentos_distintos,
        count(distinct proveedor_adjudicado) as nombres_distintos
    from observaciones
    group by codigo_proveedor, observado_en

),

huellas as (

    select
        *,
        concat_ws(
            '\x1f',
            coalesce(documento_proveedor,  '\x00NULO'),
            coalesce(proveedor_adjudicado, '\x00NULO'),
            coalesce(tipodocproveedor,     '\x00NULO'),
            coalesce(es_pyme,              '\x00NULO'),
            coalesce(es_grupo,             '\x00NULO')
        ) as huella
    from por_observacion

),

con_anterior as (

    select
        *,
        lag(huella) over (
            partition by codigo_proveedor order by observado_en
        ) as huella_anterior
    from huellas

),

versiones as (

    select * from con_anterior
    where huella_anterior is null
       or huella != huella_anterior

)

select
    codigo_proveedor,
    row_number() over (
        partition by codigo_proveedor order by observado_en
    ) as version,

    observado_en as observado_desde,
    lead(observado_en) over (
        partition by codigo_proveedor order by observado_en
    ) as observado_hasta,
    lead(observado_en) over (
        partition by codigo_proveedor order by observado_en
    ) is null as es_version_vigente,

    documento_proveedor,
    proveedor_adjudicado,
    tipodocproveedor,
    es_pyme,
    es_grupo,
    contratos_en_la_observacion,

    {#- Marcas de los casos raros. `true` significa "esta fila necesita que la
        mires", no "esta fila está mal". -#}
    documentos_distintos > 1 as tiene_documentos_en_conflicto,
    nombres_distintos > 1    as tiene_nombres_en_conflicto

from versiones