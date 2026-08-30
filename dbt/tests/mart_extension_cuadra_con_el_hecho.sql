{#-
  El mart no pierde ni inventa contratos.

  `contratos_observados` sumado sobre todas las celdas tiene que dar exactamente
  la cantidad de contratos de `fct_contratos` firmados desde 2020, que es el
  recorte que este mart declara (H3).

  Es el control del denominador, y el denominador es lo que sostiene la palabra
  "sistemáticamente": sin él, una entidad con 3 extensiones sobre 4 contratos y
  otra con 3 sobre 4.000 se ven iguales.

  ## Qué modo de fallo cubre, y por qué no lo cubre el otro test

  `mart_extension_es_coherente` mira cada celda por dentro. Este mira el total, y
  atrapa lo que una celda sana no delata: que falten contratos enteros.

  El camino concreto es el `join` contra `dim_categoria`. Es un `join` y no un
  `left join`, a propósito —la dimensión se construye desde el mismo hecho, así
  que tiene que cubrirlo entero— pero si alguna vez dejara de cubrirlo, los
  contratos sin categoría desaparecerían del mart **en silencio** y todas las
  tasas subirían, porque el denominador sería más chico. Es exactamente el mismo
  riesgo que `dim_geografia_cubre_todo_el_hecho` vigila del otro lado.

  Medido el 29/08/2026: 2.777.697 en las dos puntas.
-#}

{{ config(severity="error") }}

with cuentas as (

    select
        (select sum(contratos_observados)
         from {{ ref("mart_extension_de_plazo") }})            as en_el_mart,
        (select count(*)
         from {{ ref("fct_contratos") }}
         where fecha_de_firma >= '2020-01-01')                 as en_el_hecho

)

select
    en_el_mart,
    en_el_hecho,
    en_el_mart - en_el_hecho as diferencia

from cuentas

where en_el_mart is distinct from en_el_hecho
