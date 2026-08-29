{#-
  Toda fila del hecho encuentra su geografía, y exactamente una.

  Es la misma invariante que en `dim_modalidad_cubre_todo_el_hecho` y el mismo modo de
  fallo: si los dos cálculos del hash divergieran, la unión omitiría filas en silencio.
  Un `join` sin pareja no falla: los totales bajan y hay que sospechar del número para
  notarlo.

  Medido el 28/08/2026: cero incumplimientos.
-#}

{{ config(severity="error") }}

select
    f.id_contrato,
    f.version,
    count(g.llave_geografia) as geografias_encontradas

from {{ ref("fct_contratos_snapshot") }} f
left join {{ ref("dim_geografia") }} g
       on f.llave_geografia = g.llave_geografia

group by f.id_contrato, f.version
having count(g.llave_geografia) != 1