{#
  `dim_geografia` — dónde se ejecuta el contrato.

  958 combinaciones de departamento y ciudad. Sin historia: cero contratos
  cambiaron de geografía en 2.902.163 observaciones. Un contrato no se muda.

  ## Por qué `localizaci_n` NO entra, aunque parezca la mejor columna

  A primera vista es la candidata obvia: **cero nulos**, contra 56.335 en
  `departamento` y **611.751 en `ciudad`** —el 21% de las observaciones—. Parece
  la columna completa que rellena a las otras dos.

  Tres mediciones del 28/08/2026 la descartan:

  **1. No hay casi nada que recuperar.** De los 611.751 nulos de `ciudad`, la
  cadena permite recuperar **2.875**: el 0,47%. Los otros 608.876 traen
  `"No Definido"` dentro de la cadena, así que parsearla lleva al mismo nulo por
  un camino más largo. De departamento se recuperan **cero**.

  ⚠ Y ese `"No Definido"` embebido es un caso que la limpieza de centinelas de
  `stg_contratos` no cubre: ahí se limpian valores que **son** el centinela, no
  que lo **contienen**. Por eso `localizaci_n` tiene cero nulos — su ausencia de
  dato viene escrita adentro del texto.

  **2. El formato no es fijo.** 2.885.078 filas tienen tres campos separados por
  coma y **17.085 tienen cuatro**. La causa es que un departamento se llama
  *San Andrés, Providencia y Santa Catalina*: **tiene comas en el nombre**.
  Partir por comas lo rompe en pedazos, y un parseo ingenuo habría creado un
  departamento fantasma llamado "Providencia y Santa Catalina" con 13.102
  contratos.

  **3. Discrepa con las columnas en el 34% de las filas** — 994.277 de ellas.
  Pero eso resultó **no ser una contradicción**: son tres diferencias de
  nomenclatura y nada más.

  | En la cadena | En la columna | Filas |
  |---|---|---|
  | `Bogotá` | `Distrito Capital de Bogotá` | 965.212 |
  | `San Andrés` | `San Andrés, Providencia y…` | 16.044 |
  | `Departamento del Amazonas` | `Amazonas` | 13.021 |

  Bogotá explica el 97%, y el nombre largo es el correcto: Bogotá no pertenece a
  ningún departamento, es Distrito Capital. **Las columnas son las confiables.**

  Esto **cierra** la duda sobre `localizaci_n` en vez de dejarla abierta: no
  contradice a las otras dos columnas, usa otra convención de nombres. A
  diferencia de `orden`, `rama` y `entidad_centralizada`, que siguen sin
  explicación.

  ⚠ **Y por lo tanto los 611.751 contratos sin ciudad no tienen ciudad.** No es
  que el dato esté escondido en otra columna: la fuente no lo publica. Cualquier
  análisis geográfico por municipio deja fuera el 21% de la contratación, y eso
  hay que decirlo en el tablero — no compensarlo.

  ## La llave

  Un hash de departamento y ciudad, con `llave_de_geografia()`. Mismo patrón que
  `dim_modalidad`, y por la misma razón: no hay columna que identifique la
  combinación, y un número secuencial dependería del orden de las filas.
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