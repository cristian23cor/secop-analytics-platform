"""Que el mapa del README nombre archivos que existen.

## Por que

El mapa del repositorio es por donde alguien navega el proyecto la primera vez.
Si nombra un archivo que no esta, lo manda a buscar algo que no existe, y encima
lo hace en el documento que mas se lee.

Y paso: el mapa listaba `scripts/medir_particiones.py` durante semanas. Ese
archivo **nunca existio en el repositorio**, ni siquiera borrado: `git log --all`
no lo encuentra. La documentacion describia trabajo que nadie habia hecho.

Es la regla 5 del proyecto en otra forma: un inventario copiado a mano se
desincroniza, y la defensa es publicar el desglose completo o no publicar nada.
Aca el desglose se comprueba solo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"

# El mapa vive en un bloque de codigo bajo "## El repositorio". Se lee solo de
# ahi: el resto del README menciona archivos dentro de frases, y una frase que
# nombra un archivo borrado es un problema distinto y menos grave.
def _mapa() -> str:
    t = README.read_text(encoding="utf-8")
    i = t.index("## El repositorio")
    return t[i : t.index("```", t.index("```", i) + 3)]


NOMBRADOS = sorted({
    n for n in re.findall(r"^\s+([a-zA-Z_0-9./]+\.\w{2,4})", _mapa(), re.MULTILINE)
})


@pytest.mark.parametrize("nombre", NOMBRADOS)
def test_el_archivo_del_mapa_existe(nombre: str):
    encontrados = [
        p for p in RAIZ.rglob(Path(nombre).name)
        if ".venv" not in p.parts and "target" not in p.parts and ".git" not in p.parts
    ]
    assert encontrados, (
        f"El mapa del README nombra `{nombre}` y no existe en el repositorio. "
        f"O se borro el archivo y quedo la linea, o la linea describe trabajo "
        f"que nunca se hizo."
    )


def test_el_mapa_tiene_entradas():
    """Si la extraccion dejara de encontrar el bloque, los tests de arriba
    pasarian todos sin mirar nada."""
    assert len(NOMBRADOS) >= 20, f"solo {len(NOMBRADOS)} archivos en el mapa"
