{#
  `dim_proveedor` — quién recibe el dinero, con historia.

  929.946 proveedores: **180 veces más grande que `dim_entidad`**, que tiene
  5.162. Es la dimensión que pone a prueba si el patrón sentado con la entidad
  escala.

  ## La llave es `codigo_proveedor`, y cierra a medias la pregunta abierta 7

  Esa pregunta —"¿la llave es `documento_proveedor` o `codigo_proveedor`?"— venía
  abierta desde la exploración. Medido el 28/08/2026 sobre 2.902.163
  observaciones, ninguna de las dos es perfecta:

  | | Valores | Nulos | Con más de un valor de la otra |
  |---|---|---|---|
  | `codigo_proveedor` | 929.946 | **0** | 15 con más de un documento |
  | `documento_proveedor` | 919.929 | **8.917** | 1.297 con más de un código |

  **Gana el código, por tres razones y en ese orden:**

  1. **Cero nulos.** Una llave con 8.917 nulos no es llave, y ahí termina la
     discusión.
  2. **15 excepciones contra 1.297**, dos órdenes de magnitud de diferencia. El
     0,0016% de los códigos.
  3. **No se reusa entre proveedores distintos.** Era la duda que importaba: si
     un mismo código apuntara a entidades diferentes, no serviría de llave. Se
     revisaron los 101 códigos con más de un nombre y son variantes de
     escritura del mismo —`"karen cruz"` y `"karen lisset cruz montoya"`,
     `"JAC AVENIDA CARACAS"` y `"JAC URBANIZACION AVENIDA CARACAS"`—, no
     proveedores distintos.

  ⚠ **`documento_proveedor` no queda descartado: queda como atributo.** Es el
  identificador legal y la vía hacia cualquier cruce con fuentes externas —el
  RUES, listas de sanciones, registros tributarios—. Lo que no es, es llave.

  ⚠ **Y los 1.297 documentos con varios códigos son duplicación de catálogo**:
  la fuente registró dos veces al mismo proveedor. Agrupar por
  `documento_proveedor` los uniría, y para preguntas de negocio del tipo
  "cuánto contrató esta empresa en total" eso es lo correcto. **Es una decisión
  del consumidor, no de la dimensión**, y por eso el documento está acá.

  ## ⚠ Las marcas de conflicto dan CERO, y hay que entender por qué

  Las columnas `tiene_documentos_en_conflicto` y `tiene_nombres_en_conflicto`
  marcan **cero filas** sobre 930.071. No es que estén rotas: es que detectan un
  caso que no ocurre.

  Los 15 códigos con varios documentos y los 101 con varios nombres se midieron
  agrupando **solo por código, sin la fecha**. O sea que esos conflictos son
  **entre observaciones distintas** —el mismo código traía un documento el 23 y
  otro el 25—, no dentro de una misma foto. La dimensión los captura
  correctamente como dos versiones, que es lo que son.

  Eso es un dato en sí mismo y bueno: **la fuente es internamente coherente
  dentro de cada partición.** Las columnas se conservan porque cuestan nada y el
  día que eso deje de ser cierto, avisan.

  ## Lo que la historia capturó, sin adornarlo

  **125 proveedores de 929.946 cambiaron algo en cinco días**, y la mayoría
  fueron correcciones de escritura, no cesiones:

      "Daniela Córdoba Murillo"      → "DANIELA CORDOBA MURILLO"
      "FRANCISCO  ROBLEDO  CASTRO"   → "FRANCISCO ROBLEDO CASTRO"
      "UTPA2025"                     → "UNIÓN TEMPORAL PRODUCTORES A…"

  Hay excepciones reales —uno cambió `es_pyme` de No a Sí— pero **todavía no hay
  ninguna cesión capturada**, y decir lo contrario sería adornar. La historia se
  justifica igual: el trío del proveedor es material, las cesiones existen —28.557
  contratos con estado `cedido`— y la ventana de observación son cinco días.

  ## Los 15 casos raros, que no son todos el mismo problema

  Se revisaron uno por uno y hay al menos tres fenómenos distintos:

  - **Digitación:** `830036667` y `8300366698` — el mismo NIT con un dígito de
    más.
  - **Uniones temporales:** un consorcio puede aparecer con el documento de uno
    u otro miembro.
  - **Y uno que no tiene explicación inocente:** el mismo código con un NIT de
    empresa y una cédula de persona natural, con nombres distintos
    —`"Serviteca la Bomba Sas"` y una persona—. El código apunta a dos entidades
    legales.

  Son 15 sobre 929.946. Se documentan y no se corrigen: corregirlos exigiría
  decidir cuál de los dos documentos es el bueno, y eso es inventar.

  ## Por qué tiene historia

  Mismo criterio que `dim_entidad`, más una razón propia: **el trío del proveedor
  es MATERIAL, no cosmético**, porque cambia con la cesión de contratos —28.557
  tienen estado `cedido`—. El hecho ya versiona cuando el proveedor cambia; la
  dimensión tiene que poder explicar qué cambió.

  ⚠ **`tipodocproveedor` NO sirve para derivar el tipo de persona.** Está medido
  y falla en las dos direcciones: hay S.A.S. marcadas como "Cédula de
  Ciudadanía" y personas naturales marcadas como "NIT". Se conserva como
  evidencia de lo que la fuente declara, no como dato utilizable.

  ## Cómo se une con el hecho

  Por `codigo_proveedor` **y rango de fechas**, con el macro `vigente_en()`.
  Unir solo por llave duplica filas sin fallar. Ver `macros/dimensiones.sql`.
#}

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