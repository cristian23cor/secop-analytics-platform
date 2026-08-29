{#
  `dim_modalidad` describe cómo se contrató.

  Tiene 232 filas, es la dimensión más pequeña del proyecto y la única que no lleva
  historia.

  ## Por qué no tiene historia y cómo lo sabemos

  En 2.902.163 observaciones ningún contrato cambió de modalidad, tipo o
  justificación. Tiene sentido: la modalidad se decide al adjudicar y no se revisa
  después. La evidencia se midió sobre cinco días, igual que en `dim_entidad`, pero
  allí hubo cambios y acá ninguno. Si algún día aparece uno, el esquema se copia
  desde las otras dimensiones.

  ## La llave es un hash de los tres valores

  Se fabrica con `llave_de_modalidad()`, el mismo macro que usa el hecho. Por qué
  hash y no un número secuencial está en `macros/dimensiones.sql`.

  ## Por qué las tres columnas volvieron al hecho

  Cuando se construyó el hecho estrecho salieron las 32 columnas cosméticas en
  bloque, y estas tres iban en el paquete. Se mezclaron dos ejes: acá "cosmética" es
  la regla D6, o sea que no genera versión nueva en el SCD2, y eso no dice nada sobre
  si pertenece al hecho. La modalidad es cosmética justamente porque nunca cambia, y
  eso la vuelve un atributo estable de la contratación, que es lo que un hecho
  necesita para agruparse.

  El hecho lleva la llave de 32 caracteres y no las tres columnas de texto, porque el
  ancho era el costo real del modelo.

  ## Un dato de negocio que sale de acá

  El 74% de los contratos son contratación directa: 2.141.401 de 2.902.163. Sumando
  "Contratación Directa (con ofertas)" y el régimen especial, la contratación sin
  licitación abierta supera el 90%. Es una de las preguntas que este mart tiene que
  responder.
#}

{{ config(materialized="table") }}

select
    {{ llave_de_modalidad() }} as llave_modalidad,

    modalidad_de_contratacion,
    tipo_de_contrato,
    justificacion_modalidad_de,

    count(*) as observaciones

from {{ ref("stg_contratos") }}
group by
    modalidad_de_contratacion,
    tipo_de_contrato,
    justificacion_modalidad_de