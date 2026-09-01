"""Un comentario de jinja no puede pegarse a una palabra clave de SQL.

## El defecto que cierra, y por que merece su propio archivo

En dbt, un comentario `{#- ... -#}` con guiones borra el espacio en blanco de los
dos lados, saltos de linea incluidos. Puesto entre la ultima columna de un
`select` y el `from`, el SQL compilado dice `ultima_columnafrom tabla`.

**Ha pasado tres veces en este proyecto**, y las tres se descubrieron corriendo la
construccion: `dias_adicionados_declaradosfrom`, `selectregexp_substr`,
`union allselect`, y la ultima `as datosfrom @RAW.secop_raw`. La nota que lo
documenta decia que iba a volver a pasar, y volvio.

No lo puede atrapar la integracion continua compilando: el modelo frontera tiene
una rama para Snowflake que exige credenciales, y CI no las tiene ni debe
tenerlas. Pero el defecto es **estatico**: se ve en el archivo, sin compilar
nada.

## Que comprueba

Que ningun comentario de jinja que termine con `-#}` sea seguido, en la linea de
abajo, por una palabra clave de SQL. Ahi el guion se come el salto y la pega a lo
que haya quedado arriba.

No prohibe los guiones: en el 90% de los casos son correctos y necesarios para
que el SQL generado no quede lleno de lineas en blanco. Solo los prohibe en la
posicion donde rompen.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Solo lo escrito a mano. `dbt/target/` son 118 archivos generados: revisarlos
# seria comprobar la salida del compilador en vez de la fuente, y ademas no
# existen hasta que alguien construye.
MODELOS = sorted(
    p for p in (Path(__file__).resolve().parent.parent / "dbt").rglob("*.sql")
    if "target" not in p.parts
)

# Las palabras que abren una clausula. Si una de estas queda pegada a lo de
# arriba, el SQL no compila o, peor, compila significando otra cosa.
CLAUSULAS = (
    "from", "select", "where", "group", "order", "having", "union",
    "left", "inner", "join", "on", "with", "limit", "qualify",
)


def contexto(lineas: list[str], i: int) -> tuple[str, str]:
    """Lo que queda pegado si el guion se come el salto: (lo de arriba, lo de abajo).

    "Lo de arriba" NO es la linea anterior a `-#}`: un comentario de jinja ocupa
    varias lineas, asi que esa suele ser el propio cuerpo del comentario. Hay que
    retroceder hasta donde el comentario abre.

    La primera version de este test no lo hacia y marcaba tres modelos sanos.
    """
    inicio = i
    while inicio > 0 and "{#" not in lineas[inicio]:
        inicio -= 1
    arriba = next((l for l in reversed(lineas[:inicio]) if l.strip()), "").rstrip()
    abajo = next((l for l in lineas[i + 1:] if l.strip()), "").strip().lower()
    return arriba, abajo


@pytest.mark.parametrize("ruta", MODELOS, ids=lambda p: p.name)
def test_ningun_comentario_se_come_una_clausula(ruta: Path):
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    for i, linea in enumerate(lineas):
        if not linea.rstrip().endswith("-#}"):
            continue
        arriba, abajo = contexto(lineas, i)
        primera = re.split(r"[\s(]", abajo)[0] if abajo else ""
        if primera not in CLAUSULAS:
            continue
        # Que lo de arriba termine en identificador es la otra mitad. Si termina
        # en `(` o en `,`, pegar es inofensivo (`(select` es SQL valido), y un
        # `{{ config(...) }}` renderiza vacio. Sin esta mitad la regla marcaba
        # tres modelos sanos, y una regla que marca de mas se desactiva entera.
        peligroso = bool(arriba) and (arriba[-1].isalnum() or arriba.endswith("_"))
        assert not peligroso, (
            f"{ruta.name}:{i + 1}: el comentario cierra con `-#}}`, arriba queda "
            f"`...{arriba[-28:].strip()}` y abajo empieza `{primera}`. El guion se "
            f"come el salto y los dos se funden en un solo token. Cerra sin guion: "
            f"`#}}`."
        )


def test_hay_modelos_que_revisar():
    """Si el glob dejara de encontrar archivos, el test de arriba pasaria sin
    mirar nada."""
    assert len(MODELOS) >= 25, f"solo {len(MODELOS)} archivos .sql encontrados"
