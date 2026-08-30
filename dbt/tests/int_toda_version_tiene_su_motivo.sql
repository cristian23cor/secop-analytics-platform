{#-
  El hecho y el motivo dicen lo mismo sobre qué cambió.

  Son dos cálculos independientes de la misma pregunta, y este test los cruza:

  - `fct_contratos_snapshot` decide que hay versión nueva comparando una
    **huella concatenada** de las 28 materiales contra la de la observación
    anterior.
  - `int_cambios_por_columna` decide qué cambió comparando las 28 **una por una**
    con `IS DISTINCT FROM`.

  Que los dos caminos coincidan no es gratis. D6 descartó el hash de las
  materiales justamente porque concatenar tiene dos modos de fallo silencioso:
  `NULL` propagándose por toda la cadena, y un separador que aparezca en los
  datos y haga que `('a', 'b')` y `('ab', '')` produzcan la misma huella. El
  hecho terminó usando una concatenación igual, con `coalesce` a un centinela y
  `\x1f` de separador. **Este test es la comprobación de que esa defensa
  funciona**: si la huella se equivoca en cualquiera de las dos direcciones, las
  dos tablas dejan de cuadrar.

  Cubre los tres modos de discrepancia:

  | motivo | qué pasó |
  |---|---|
  | `version sin motivo` | el hecho generó versión y ninguna columna difiere |
  | `motivo huérfano` | hay un cambio anotado para una versión que no existe |
  | `motivo en la versión 1` | la primera versión no es un cambio y no debe aparecer |

  El tercero protege una lectura, no solo una tabla. La primera versión de cada
  contrato **no sirve para calcular deltas**: no había nada antes, y su
  `huella_anterior` nula significa "apareció", no "cambió". Si se colara acá, las
  preguntas 6 y 7 contarían como adición el valor inicial de cada contrato. Es el
  hallazgo 2 de §9 del modelo dimensional convertido en test.

  Y gana valor cuando el hecho pase a materialización incremental (D5): ahí los
  dos modelos se construyen en corridas distintas sobre ventanas distintas, y
  quedar desfasados deja de ser imposible.

  Medido el 29/08/2026: cero discrepancias sobre 2.881.640 versiones y 88.395
  cambios anotados.
-#}

{{ config(severity="error") }}

select
    f.id_contrato,
    f.version,
    'version sin motivo' as motivo

from {{ ref("fct_contratos_snapshot") }} f

where f.version > 1
  and not exists (
      select 1
      from {{ ref("int_cambios_por_columna") }} c
      where c.id_contrato = f.id_contrato
        and c.version     = f.version
  )

union all

select distinct
    c.id_contrato,
    c.version,
    'motivo huérfano' as motivo

from {{ ref("int_cambios_por_columna") }} c

where not exists (
    select 1
    from {{ ref("fct_contratos_snapshot") }} f
    where f.id_contrato = c.id_contrato
      and f.version     = c.version
)

union all

select distinct
    id_contrato,
    version,
    'motivo en la versión 1' as motivo

from {{ ref("int_cambios_por_columna") }}

where version = 1
