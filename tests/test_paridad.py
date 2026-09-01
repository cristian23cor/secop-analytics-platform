"""La funcion que decide si dos motores dieron lo mismo.

Es una funcion de tres lineas y merece sus propios tests por una razon
concreta: **tiene que ser tolerante y no puede ser indulgente.**

Tolerante, porque Snowflake devuelve `Decimal` donde DuckDB devuelve `int` para
el mismo `count(*)`. Eso no es una divergencia de datos y contarlo como tal
llenaria el informe de falsos positivos hasta que nadie lo mire.

Indulgente seria peor: una comparacion que devuelve `True` de mas convierte el
informe entero en decoracion, y el informe es la evidencia que va a sobrevivir al
vencimiento de la cuenta de Snowflake. Se comprobo rompiendola a proposito y el
verificador NO lo detecta: no puede, porque es la pieza con la que verifica. Por
eso se prueba desde afuera.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from verificar_paridad_de_motores import iguales


@pytest.mark.parametrize(("a", "b"), [
    (2_902_163, Decimal(2902163)),   # count(*): int en DuckDB, Decimal en Snowflake
    (Decimal(134296), 134296),       # y al reves
    (0, Decimal(0)),
    (1.5, Decimal("1.5")),
    ("a1b2c3", "a1b2c3"),              # min(hash), texto en los dos
    (None, None),                      # sum() sobre cero filas
])
def test_tolera_que_los_motores_devuelvan_tipos_distintos(a, b):
    assert iguales(a, b)


@pytest.mark.parametrize(("a", "b"), [
    (2_902_163, 2_902_162),            # una fila de diferencia
    (Decimal(134296), Decimal(134295)),
    ("a1b2c3", "a1b2c4"),              # la huella minima cambio
    (None, 0),                         # "no hay filas" no es "la suma dio cero"
    (0, None),
    (None, "ERROR: ProgrammingError"), # una consulta que fallo de un solo lado
    (5, "ERROR: ProgrammingError"),
])
def test_no_es_indulgente(a, b):
    """El caso que mas importa: `None` contra `0`.

    `sum()` sobre cero filas devuelve nulo; `sum()` sobre filas que suman cero
    devuelve cero. Son cosas distintas, y confundirlas taparia justamente el caso
    en que un motor construyo una tabla vacia.
    """
    assert not iguales(a, b)


def test_dos_errores_iguales_no_son_un_acuerdo():
    """El verificador guarda el texto del error en vez de abortar, para que un
    modelo roto no impida medir los otros diez.

    Pero ese texto no puede comparar igual **ni siquiera contra si mismo**. Si
    una comprobacion falla en los dos motores, no coincidieron: son dos
    comprobaciones que no se hicieron, y contarlas infla el total que el informe
    existe para sostener.

    Salio de escribir este archivo: la primera version devolvia verdadero ahi.
    """
    assert not iguales("ERROR: ProgrammingError", "ERROR: ProgrammingError")
