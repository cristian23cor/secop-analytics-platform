{#
  `dim_modalidad` — cómo se contrató.

  **232 filas.** Es la dimensión más chica del proyecto y la única sin historia.

  ## Por qué no tiene historia, y está medido

  Cero contratos cambiaron de modalidad, tipo o justificación en las 2.902.163
  observaciones. Tiene sentido: la modalidad se decide al adjudicar y no se
  revisa después. A diferencia de `dim_entidad` y `dim_proveedor`, acá no hay
  nada que versionar.

  ⚠ **"Sin cambios" se midió sobre cinco días**, igual que en la entidad. La
  diferencia es que allá el atributo sí cambió —seis entidades— y acá no cambió
  ninguno de 2,9 millones. Con esa evidencia, agregar historia sería maquinaria
  para un caso que no existe. Si algún día aparece, el patrón está sentado en las
  otras dos dimensiones y se copia.

  ## La llave es un hash de los tres valores

  No hay columna que identifique la combinación: la llave **son** los tres
  valores. Se fabrica con `llave_de_modalidad()`, un hash determinista que el
  hecho calcula con el mismo macro. Ver `macros/dimensiones.sql` para por qué un
  hash y no un número secuencial.

  ## Por qué las tres columnas volvieron al hecho

  Al hacer el hecho estrecho salieron las 32 cosméticas en bloque, y estas tres
  iban en el paquete. Fue un error de criterio: **se confundieron dos ejes.**

  "Cosmética" en este proyecto significa algo preciso —*no genera versión nueva
  en el SCD2*, que es D6—. No significa "no pertenece al hecho". La modalidad es
  cosmética justamente porque **nunca cambia**, y eso la vuelve un atributo
  estable de la contratación: exactamente lo que un hecho debe llevar para poder
  agruparse.

  Qué versiona y qué pertenece al hecho son preguntas distintas.

  El hecho lleva la llave —32 caracteres— y no las tres columnas de texto, que
  es lo que importa después de descubrir que el ancho era el costo real.

  ## Un dato de negocio que sale de acá

  **El 74% de los contratos son contratación directa** (2.141.401 de 2.902.163).
  Sumando "Contratación Directa (con ofertas)" y el régimen especial, la
  contratación sin licitación abierta supera el 90%. Es una de las preguntas que
  el mart tiene que responder, y ya se sabe que hay respuesta.
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