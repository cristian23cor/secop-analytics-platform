{#-
  Un contrato no se puede ver antes de firmarse.

  Un valor negativo significa una de dos cosas. O la fuente publica una fecha de
  firma futura, que es un imposible del mismo tipo que un contrato por encima del
  presupuesto nacional. O el datediff quedó al revés, y eso no daría un caso sino
  los 2,8 millones, porque la mediana del hueco es de 657 días. Las dos se
  distinguen por el volumen.

  Es aviso y no error por el primer motivo: suciedad de la fuente avisa, no detiene
  la construcción.

  Lo que este test dejó ver es que el mínimo es un día y no cero. Ningún contrato
  se observa el mismo día en que se firma, porque la fuente publica con un día de
  rezago. Eso tiene consecuencia sobre la restricción de los análisis de delta: el
  margen no puede ser cero, o el universo queda vacío por una propiedad de la
  fuente y no por falta de datos. Con margen de 7 días son 11.066 contratos; con
  30, 76.245. El máximo del hueco es de 3.876 días, diez años y medio.

  Medido el 29/08/2026: cero, sobre 2.849.209 contratos.
-#}


{{ config(severity="warn") }}

select
    id_contrato,
    fecha_de_firma,
    fecha_primer_snapshot,
    dias_hasta_el_primer_snapshot

from {{ ref("fct_contratos") }}

where dias_hasta_el_primer_snapshot < 0
