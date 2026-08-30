{#
  `dim_geografia` describe dónde se ejecuta el contrato.

  Hay 958 combinaciones de departamento y ciudad. No hay historia: en 2.902.163
  observaciones ningún contrato cambió de geografía, así que esta dimensión no
  necesita rangos de validez ni versión histórica.

  ## Por qué `localizaci_n` no entra, aunque parezca la mejor columna

  A primera vista es la candidata obvia. Tiene cero nulos, frente a 56.335 en
  `departamento` y 611.751 en `ciudad`, que es el 21% de las observaciones. Parece
  la columna que completa a las otras dos. Las mediciones del 28/08/2026 dicen otra
  cosa.

  Hay muy poco para recuperar. De los 611.751 nulos de `ciudad`, la cadena permite
  recuperar 2.875, el 0,47%. Los otros 608.876 traen `"No Definido"` dentro del
  texto, así que parsearla lleva al mismo nulo por un camino más largo. De
  departamento no se recupera nada. Ese `"No Definido"` embebido es justamente lo
  que la limpieza de centinelas de `stg_contratos` no cubre, porque allí se limpian
  los valores que son exactamente el centinela, no los que lo contienen. Por eso
  `localizaci_n` tiene cero nulos: la ausencia de dato viene escrita dentro del
  texto.

  El formato tampoco es fijo. 2.885.078 filas tienen tres campos separados por coma
  y 17.085 tienen cuatro, porque un departamento se llama *San Andrés, Providencia y
  Santa Catalina* y tiene comas en el nombre. Partir por comas rompe ese valor en
  pedazos, y un parseo ingenuo habría creado un departamento fantasma llamado
  "Providencia y Santa Catalina" con 13.102 contratos.

  Y discrepa con las columnas en 994.277 filas, el 34%. Esa diferencia no fue
  contradicción: son tres variaciones de nomenclatura.

  | En la cadena | En la columna | Filas |
  |---|---|---|
  | `Bogotá` | `Distrito Capital de Bogotá` | 965.212 |
  | `San Andrés` | `San Andrés, Providencia y...` | 16.044 |
  | `Departamento del Amazonas` | `Amazonas` | 13.021 |

  Bogotá explica el 97% del caso, y el nombre largo es el correcto, porque Bogotá no
  pertenece a ningún departamento: es Distrito Capital. Las columnas son las
  confiables. A diferencia de `orden`, `rama` y `entidad_centralizada`, acá no hay
  un patrón oculto detrás de la diferencia.

  Por eso los 611.751 contratos sin ciudad no tienen ciudad. No está escondido en
  otra columna, la fuente no lo publica. Cualquier análisis geográfico por municipio
  deja fuera el 21% de la contratación, y eso hay que decirlo en el tablero, no
  compensarlo.

  ## La llave

  Es un hash de departamento y ciudad calculado con `llave_de_geografia()`. Mismo
  patrón que en `dim_modalidad`: no hay una columna que identifique la combinación,
  y un número secuencial dependería del orden de las filas.
#}

{{ config(materialized="table") }}

select
    {{ llave_de_geografia() }} as llave_geografia,

    departamento,
    ciudad,
    ciudad is null as sin_ciudad,

    count(*) as observaciones

from {{ ref("stg_contratos") }}
group by departamento, ciudad