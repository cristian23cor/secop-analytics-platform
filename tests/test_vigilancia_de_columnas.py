"""El vigia de columnas: que detecte deriva, y que avise UNA vez.

## Que se prueba

Dos mitades. La decision (`evaluar`, funcion pura) y el circuito completo
(`main`, con el doble de la fuente y un registro en `tmp_path`).

La mitad que importa no es "detecta una columna nueva". Es **que deje de
avisar despues del primer aviso sin dejar de reportar el problema**: son dos
cosas distintas y la version anterior de este proyecto las confundio en
`sondear.py`, con un costo medido de 20 issues en cuatro dias.

Por eso hay un test para cada estado del ciclo de vida de una columna nueva:
aparece (grita), sigue sin clasificar (calla, pero lo dice en el log), y se
clasifica (vuelve a la normalidad).

## Por que no alcanza con verlo dar cero

Hoy la fuente publica 85 columnas y el proyecto clasifica esas mismas 85, asi
que el vigia corriendo de verdad dice "todo bien" y seguiria diciendolo aunque
estuviera roto. Un test que solo lo ve dar cero no demuestra que sepa dar otra
cosa: de ahi que casi todos estos guionen deriva en vez de observar la realidad.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest
import requests

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO_REAL = RAIZ / "exploration" / "columnas_de_la_fuente.txt"


@pytest.fixture
def vigia():
    """`vigilar_columnas.py`, con los dobles de conftest ya instalados."""
    if str(RAIZ / "scripts") not in sys.path:
        sys.path.insert(0, str(RAIZ / "scripts"))
    return importlib.import_module("vigilar_columnas")


@pytest.fixture
def registro(vigia, tmp_path, monkeypatch):
    """Aparta el registro real: estos tests escriben, y no en el repositorio."""
    ruta = tmp_path / "columnas_de_la_fuente.txt"
    monkeypatch.setattr(vigia, "REGISTRO", ruta)
    monkeypatch.setattr(vigia, "RAIZ", tmp_path)
    return ruta


CATALOGO = {"nombre_entidad", "valor_pagado", "estado_contrato"}


# --------------------------------------------------------------------------
# La decision, aislada
# --------------------------------------------------------------------------

def test_sin_novedad_no_hay_nada_que_hacer(vigia, monkeypatch):
    monkeypatch.setattr(vigia, "validar_cobertura", _cobertura_contra(CATALOGO))
    v = vigia.evaluar(CATALOGO, CATALOGO)
    assert v.cobertura_intacta
    assert not v.cambio_el_esquema
    assert not v.vale_guardar


def test_una_columna_nueva_rompe_la_cobertura_y_es_un_cambio(vigia, monkeypatch):
    monkeypatch.setattr(vigia, "validar_cobertura", _cobertura_contra(CATALOGO))
    v = vigia.evaluar(CATALOGO | {"valor_reajustado"}, CATALOGO)
    assert v.sin_clasificar == {"valor_reajustado"}
    assert v.aparecieron == {"valor_reajustado"}
    assert v.cambio_el_esquema
    assert v.vale_guardar


def test_una_columna_que_desaparece_tambien_se_detecta(vigia, monkeypatch):
    monkeypatch.setattr(vigia, "validar_cobertura", _cobertura_contra(CATALOGO))
    v = vigia.evaluar(CATALOGO - {"valor_pagado"}, CATALOGO)
    assert v.desaparecidas == {"valor_pagado"}
    assert v.se_fueron == {"valor_pagado"}
    assert v.cambio_el_esquema


def test_la_columna_nueva_ya_avisada_sigue_rota_pero_ya_no_es_un_cambio(
    vigia, monkeypatch
):
    """**El test que justifica todo el diseño.**

    Segunda corrida con la misma columna nueva: el registro ya la tiene. La
    cobertura sigue rota —nadie la clasifico todavia— pero no hay cambio, asi
    que no se vuelve a gritar.

    Si estas dos afirmaciones se pudieran contestar con la misma comparacion,
    una de las dos estaria mal, y la que estaria mal es la que abre issues.
    """
    monkeypatch.setattr(vigia, "validar_cobertura", _cobertura_contra(CATALOGO))
    fuente = CATALOGO | {"valor_reajustado"}
    v = vigia.evaluar(fuente, fuente)
    assert not v.cobertura_intacta, "la columna sigue sin clasificar"
    assert v.sin_clasificar == {"valor_reajustado"}
    assert not v.cambio_el_esquema, "ya se aviso: no se avisa de nuevo"
    assert not v.vale_guardar


def test_la_primera_mirada_no_es_un_cambio(vigia, monkeypatch):
    """Un registro vacio contra 85 columnas daria "aparecieron 85". Es cierto
    en aritmetica y falso en lo que importa: nunca habiamos mirado."""
    monkeypatch.setattr(vigia, "validar_cobertura", _cobertura_contra(CATALOGO))
    v = vigia.evaluar(CATALOGO, set())
    assert v.primera_mirada
    assert not v.cambio_el_esquema
    assert v.vale_guardar, "hay que anotarla igual, o la proxima es otra primera vez"


def _cobertura_contra(catalogo: set[str]):
    """`validar_cobertura` acotada a un catalogo de tres columnas.

    Los tests de decision no deben depender de las 85 reales: si alguien
    clasifica una columna nueva manana, estos tests no tienen por que enterarse.
    """
    return lambda publicadas: {
        "sin_clasificar": publicadas - catalogo,
        "desaparecidas": catalogo - publicadas,
    }


# --------------------------------------------------------------------------
# El circuito completo
# --------------------------------------------------------------------------

def test_con_la_fuente_sana_sale_por_cero_y_anota(vigia, fuente, registro):
    assert vigia.main() == 0
    assert registro.exists(), "la primera mirada se anota aunque no haya cambio"
    from secop_analytics.columnas import CLASIFICADAS

    assert vigia.leer() == set(CLASIFICADAS)


def test_una_columna_nueva_sale_por_cinco_y_despues_se_calla(
    vigia, fuente, registro, capsys
):
    """El ciclo entero, de punta a punta: aparece, grita, calla, se arregla."""
    from secop_analytics.columnas import CLASIFICADAS

    # 1. Primera mirada, todo sano.
    assert vigia.main() == 0

    # 2. La fuente agrega una columna.
    fuente.columnas = set(CLASIFICADAS) | {"valor_reajustado"}
    assert vigia.main() == 5, "una columna nueva tiene que gritar"
    assert "valor_reajustado" in capsys.readouterr().out

    # 3. Sigue ahi, sin clasificar. Ya se aviso.
    assert vigia.main() == 0, "el segundo sondeo no puede volver a abrir issue"
    salida = capsys.readouterr().out
    assert "LA COBERTURA NO ESTA INTACTA" in salida, (
        "callarse en el codigo de salida no es callarse en el log: el problema "
        "sigue vivo y tiene que seguir viendose"
    )

    # 4. La fuente la vuelve a sacar: eso SI es un cambio nuevo.
    fuente.columnas = set(CLASIFICADAS)
    assert vigia.main() == 5


def test_si_no_se_pueden_leer_los_metadatos_sale_por_dos(vigia, fuente, registro):
    fuente.explotar_las_columnas = requests.ConnectionError("sin red")
    assert vigia.main() == 2
    assert not registro.exists(), "un fallo de red no puede pisar el registro"


def test_un_fallo_no_borra_lo_que_ya_estaba_anotado(vigia, fuente, registro):
    assert vigia.main() == 0
    antes = registro.read_text(encoding="utf-8")
    fuente.explotar_las_columnas = RuntimeError("la ficha cambio de forma")
    assert vigia.main() == 2
    assert registro.read_text(encoding="utf-8") == antes


def test_le_deja_a_actions_lo_que_actions_necesita(
    vigia, fuente, registro, tmp_path, monkeypatch
):
    """El workflow decide con estas salidas si commitea y si abre un issue."""
    from secop_analytics.columnas import CLASIFICADAS

    salida = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(salida))

    vigia.main()
    fuente.columnas = set(CLASIFICADAS) | {"valor_reajustado"}
    vigia.main()

    escrito = salida.read_text(encoding="utf-8")
    assert "columnas_cambio=true" in escrito
    assert "guardar_columnas=true" in escrito
    assert "aparecieron=valor_reajustado" in escrito


# --------------------------------------------------------------------------
# El registro, en el repositorio
# --------------------------------------------------------------------------

def test_el_registro_esta_versionado():
    """Misma trampa que se trago `exploration/cadencia.csv`: existe en disco,
    no en el repositorio, y el sondeo programado lo descubre en CI."""
    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "exploration/columnas_de_la_fuente.txt"],
        cwd=RAIZ, capture_output=True, text=True, check=False,
    )
    assert r.returncode == 0, (
        "exploration/columnas_de_la_fuente.txt NO esta versionado. Sin el, cada "
        "corrida en Actions es una primera mirada y nunca detecta un cambio.\n"
        "    git check-ignore -v exploration/columnas_de_la_fuente.txt"
    )


def test_el_registro_coincide_con_lo_que_el_proyecto_clasifica():
    """Si estos dos difieren, hay una columna sin clasificar esperando en el
    registro y el proyecto la esta ignorando en silencio."""
    from secop_analytics.columnas import CLASIFICADAS

    anotadas = {
        l.strip() for l in REGISTRO_REAL.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    }
    assert anotadas == set(CLASIFICADAS), (
        f"el registro y columnas.py divergieron.\n"
        f"  en la fuente y sin clasificar: {sorted(anotadas - set(CLASIFICADAS))}\n"
        f"  clasificadas y ya no en la fuente: {sorted(set(CLASIFICADAS) - anotadas)}"
    )
