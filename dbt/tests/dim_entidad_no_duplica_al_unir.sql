{#-
  Unir el hecho con `dim_entidad` devuelve UNA fila por fila del hecho.

  Es el test que protege contra el error más probable de un modelo con
  dimensiones históricas: unir solo por llave y olvidar el rango de fechas.

  Ese error **no falla y no avisa**: duplica. Cada fila del hecho se cruza con
  todas las versiones de su entidad, y los conteos y las sumas quedan inflados
  sin que nada lo delate. Sobre los datos reales afectaría a las seis entidades
  reclasificadas y a sus 20.675 contratos — y daría el resultado correcto para
  las otras 5.156, que es lo que vuelve al error tan difícil de notar.

  Este test comprueba el invariante del lado de la dimensión: que para cada
  fecha de observación de cada entidad exista **como máximo una** versión
  vigente. Si eso se cumple, la unión con rango no puede duplicar.

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