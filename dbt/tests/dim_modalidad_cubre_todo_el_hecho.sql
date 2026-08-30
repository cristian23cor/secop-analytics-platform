{#-
  Toda fila del hecho encuentra su modalidad, y exactamente una.

  Este test protege la decisión de fabricar la llave con un hash calculado en dos
  lugares. Si los dos cálculos divergieran (porque alguien toca uno y no el otro, o
  cambia el orden de los argumentos) las llaves dejarían de coincidir y la unión
  devolvería cero filas para las versiones afectadas.

  Ese fallo no se nota en una consulta normal. Un `join` que no encuentra pareja
  simplemente omite la fila: los totales bajan, nada falla y hay que sospechar del
  número para darse cuenta. Es el mismo tipo de fallo que el de unir sin rango de
  fechas, pero al revés: allí se duplica, aquí desaparece.

  El macro compartido `llave_de_modalidad()` hace que la divergencia sea muy poco
  probable, y este test la vuelve visible.

  Medido el 28/08/2026: cero incumplimientos sobre 2.881.640 versiones.
-#}

{{ config(severity="error") }}

select
    f.id_contrato,
    f.version,
    f.llave_modalidad,
    count(m.llave_modalidad) as modalidades_encontradas

from {{ ref("fct_contratos_snapshot") }} f
left join {{ ref("dim_modalidad") }} m
       on f.llave_modalidad = m.llave_modalidad

group by f.id_contrato, f.version, f.llave_modalidad
having count(m.llave_modalidad) != 1