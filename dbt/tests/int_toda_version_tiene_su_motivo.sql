{#-
  El hecho y el motivo dicen lo mismo sobre qué cambió.

  Son dos cálculos independientes de la misma pregunta. El hecho decide que hay
  versión nueva comparando una huella concatenada de las 28 materiales; la capa
  intermedia decide qué cambió comparándolas una por una.

  Que coincidan no es gratis. Se descartó el hash de las materiales justamente
  porque concatenar tiene dos modos de fallo silencioso: un nulo que se propaga
  por toda la cadena, y un separador que aparezca en los datos y haga que dos
  tuplas distintas den la misma huella. El hecho terminó usando una concatenación
  igual, con coalesce a un centinela y \x1f de separador. Esto comprueba que esa
  defensa funcione.

  Cubre los tres sentidos: una versión sin motivo, un motivo huérfano, y un motivo
  sobre la versión 1.

  El tercero protege una lectura y no solo una tabla. La primera versión de cada
  contrato no sirve para calcular deltas: no había nada antes, y su huella anterior
  nula significa "apareció", no "cambió". Si se colara, las preguntas 6 y 7
  contarían como adición el valor inicial de cada contrato.

  Gana valor cuando el hecho pase a incremental: ahí los dos modelos se construyen
  en corridas distintas sobre ventanas distintas, y quedar desfasados deja de ser
  imposible.

  Medido el 29/08/2026: cero, sobre 2.881.640 versiones y 88.395 cambios.
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
