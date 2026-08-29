{#-
  Este test asegura que unir el hecho con `dim_entidad` devuelva una fila por fila del
  hecho.

  Protege contra el error más probable en un modelo con dimensiones históricas: unir
  solo por llave y olvidar el rango de fechas.

  Ese error no falla y no avisa: duplica filas. Cada fila del hecho se cruza con todas
  las versiones de su entidad, y los conteos y las sumas quedan inflados sin que nada
  lo delate. En los datos reales, afecta a las seis entidades reclasificadas y a sus
  20.675 contratos; para las otras 5.156 entidades el resultado sigue pareciendo bien,
  y eso es lo que hace que el problema sea tan difícil de notar.

  El test comprueba la invariante del lado de la dimensión: para cada fecha de
  observación de cada entidad, existe como máximo una versión vigente. Si eso se cumple,
  la unión con rango no puede duplicar.

  Medido el 28/08/2026: cero incumplimientos.
-#}

{{ config(severity="error") }}

select
    f.id_contrato,
    f.version,
    count(*) as versiones_de_entidad

from {{ ref("fct_contratos_snapshot") }} f
join {{ ref("dim_entidad") }} e
  on {{ vigente_en(hecho="f", dimension="e", llave="codigo_entidad") }}

group by f.id_contrato, f.version
having count(*) > 1