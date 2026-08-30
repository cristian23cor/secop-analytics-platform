{#-
  Un contrato no se puede ver antes de firmarse.

  `dias_hasta_el_primer_snapshot` mide cuántos días pasaron entre la firma y la
  primera vez que el pipeline vio el contrato. Un valor negativo significa una de
  dos cosas, y las dos hay que verlas:

  1. **La fuente publica una `fecha_de_firma` futura.** Es un imposible del mismo
     tipo que RN13: un valor con forma válida y contenido que no puede ser. Es lo
     que se espera si esto se dispara.
  2. **El `datediff` quedó al revés.** Ese fallo no daría un caso: daría los 2,8
     millones, porque la mediana del hueco es de 657 días. Un test que se
     dispara entero es un test que se lee.

  ## Por qué `warn` y no `error`

  Por el primer motivo: es suciedad de la fuente, que no controlamos, y el
  criterio de esta carpeta es que eso avisa en vez de detener la construcción. El
  segundo motivo se distingue del primero por el volumen, no por la severidad.

  ## Lo que este test dejó ver: el margen cero no existe

  Medido el 29/08/2026, el mínimo es **1 día** y no cero: **ningún contrato se
  observa el mismo día en que se firma**. No es casualidad ni un caso raro que
  falte — es H8, la fuente publica con ~1 día de rezago, así que el corte de hoy
  contiene lo firmado hasta ayer.

  Tiene una consecuencia sobre §9 del modelo dimensional, que restringe los
  análisis de delta a `fecha_primer_snapshot <= fecha_de_firma + margen`: **ese
  margen no puede ser cero**, o el universo queda vacío por construcción y no
  porque falten datos. Con margen 7 son 11.066 contratos (0,39%); con 30, 76.245
  (2,7%). La mediana del hueco es de 657 días y el máximo 3.876, o sea diez años
  y medio.

  Medido el 29/08/2026: cero incumplimientos sobre 2.849.209 contratos.
-#}

{{ config(severity="warn") }}

select
    id_contrato,
    fecha_de_firma,
    fecha_primer_snapshot,
    dias_hasta_el_primer_snapshot

from {{ ref("fct_contratos") }}

where dias_hasta_el_primer_snapshot < 0
