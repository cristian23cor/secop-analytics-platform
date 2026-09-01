"""Que el registro de cadencia este de verdad en el repositorio.

## Por que un test para esto

Porque ya fallo, y fallo en silencio. `.gitignore` tenia una regla general
`*.csv` —puesta con buen criterio, el repositorio guarda codigo y no datos— y se
tragaba `exploration/cadencia.csv`.

El archivo existia en la maquina de quien lo escribio. `git add -A` lo salteaba
sin decir nada, los commits salian bien, y todo parecia en orden. Se descubrio
cuando el sondeo programado corrio en GitHub Actions y murio con un
`FileNotFoundError`, porque alla el archivo nunca habia llegado.

Es el modo de fallo que este proyecto documenta una y otra vez: **algo que
termina con exito sin haber hecho nada.** Un commit que reporta haber guardado
todo, sobre un archivo que no guardo.

## Que comprueba

Que `git ls-files` lo vea. No que exista en disco: eso no distingue el caso malo,
porque en la maquina donde se escribio siempre va a existir.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# Archivos que el codigo lee en tiempo de ejecucion desde el repositorio. Si uno
# de estos no esta versionado, funciona en la maquina de quien lo escribio y
# falla en cualquier otra.
VERSIONADOS = [
    "exploration/cadencia.csv",   # lo lee sondear.py y generar_tablero.py
    "dags/secop_ingesta.py",
    "dbt/macros/columnas_generado.sql",
]


@pytest.mark.parametrize("relativa", VERSIONADOS)
def test_esta_versionado(relativa: str):
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relativa],
        cwd=RAIZ, capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, (
        f"{relativa} NO esta versionado. Existe en esta maquina y no en el "
        f"repositorio, asi que funciona aca y falla en cualquier otro lado.\n"
        f"Comproba si `.gitignore` se lo esta tragando:\n"
        f"    git check-ignore -v {relativa}"
    )


def test_el_registro_tiene_lo_que_el_tablero_espera():
    """El tablero lee este archivo para armar la tira de cadencia. Si le faltara
    una columna, el tablero se rompe al generarse y no antes."""
    import csv

    ruta = RAIZ / "exploration" / "cadencia.csv"
    filas = list(csv.DictReader(
        l for l in ruta.read_text(encoding="utf-8").splitlines()
        if not l.startswith("#")
    ))
    assert filas, "el registro no tiene ni una linea de datos"
    for columna in ("fecha", "hora_cot", "corte_vivo", "testigo", "regenero", "fuente"):
        assert columna in filas[0], f"al registro le falta la columna {columna}"
    for f in filas:
        assert f["regenero"] in ("si", "no", ""), (
            f"{f['fecha']}: `regenero` dice {f['regenero']!r}, y solo puede ser "
            "si, no, o vacio cuando no se sabe"
        )
