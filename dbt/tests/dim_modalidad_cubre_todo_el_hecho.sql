{#-
  Toda fila del hecho encuentra su modalidad, y encuentra exactamente una.

  Es el test que protege la decisión de fabricar la llave con un hash calculado
  en dos lugares. Si los dos cálculos divergieran —alguien toca uno y no el
  otro, o el orden de los argumentos cambia— las llaves dejarían de coincidir y
  la unión devolvería cero filas para las afectadas.

  ⚠ **Ese fallo NO se nota en una consulta normal.** Un `join` que no encuentra
  pareja simplemente omite la fila: los totales bajan, nada falla, y hay que
  sospechar del número para darse cuenta. Es el mismo modo de fallo que el de
  unir sin rango de fechas, pero al revés — aquel duplica, éste desaparece.

  El macro compartido `llave_de_modalidad()` hace la divergencia improbable.
  Este test la hace visible.

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