"""Fixtures compartidas y dobles de la capa de extracción.

## Qué dobla esto, y qué NO prueba

`cargar_raw.py` importa `flujos.py` y `paginacion.py`, que hablan con la API.
Acá se reemplazan por generadores que devuelven páginas controladas, para poder
probar en CI **lo que el orquestador decide**: el orden entre archivo e índice,
el guardarraíl del flujo 3, los nombres de partición, la reanudación por cursor
y la deduplicación entre corridas.

 **Los dobles no prueban el contrato con la fuente.** Devuelven las filas que
uno escribe, y uno las escribe desde lo que espera. Las rarezas que la
exploración encontró en la fuente real son la prueba de lo que eso deja afuera:
una columna de fecha corrupta, centinelas de texto en dos capitalizaciones,
`urlproceso` como objeto anidado. Ningún doble escrito a mano habría tenido esas
rarezas.

Esa mitad la cubre `scripts/verificar_carga_raw.py`, que corre contra la API de
verdad y se ejecuta a mano.

## Por qué los dobles se instalan antes de importar

`cargar_raw.py` hace `from secop_analytics.flujos import ...` en su cabecera, así
que los módulos falsos tienen que estar en `sys.modules` **antes** de importarlo.
De ahí el orden raro de este archivo.

 **Y por qué se instalan con asignación y no con `setdefault`.** `setdefault`
no hace nada si el módulo ya está importado, así que bastaba con que cualquier
test tocara el módulo real antes para que `cargar_raw` saliera a la red — un
fallo que depende del orden de recolección de pytest y por lo tanto aparece y
desaparece solo.

La contracara es que el doble **eclipsa** al módulo real durante toda la sesión.
Si algún día hace falta un `test_flujos.py` que pruebe el módulo de verdad,
tiene que cargarlo a mano desde su ruta. Para *comparar* los dobles contra los
originales alcanza con leer el árbol sintáctico: ver `valores_de_enum()` y
`parametros_de()`, que no ejecutan nada.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Any

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _arbol(nombre: str):
    """Parsea un módulo de `src/` sin ejecutarlo. `None` si no está.

    Se lee con `ast` y no se importa por dos razones. Los módulos reales usan
    imports relativos (`from .paginacion import ...`) que no resuelven fuera de
    su paquete — y ese paquete está eclipsado por los dobles de este archivo.
    Y ejecutar el módulo real tendría efectos: importaría `requests`, leería el
    entorno, y podría reemplazar al doble.

    Leer el árbol da lo que hace falta para comparar —nombres, valores
    literales, parámetros— sin ninguna de esas complicaciones.
    """
    import ast

    ruta = RAIZ / "src" / "secop_analytics" / f"{nombre}.py"
    if not ruta.is_file():
        return None
    return ast.parse(ruta.read_text(encoding="utf-8"))


def valores_de_enum(modulo: str, clase: str) -> dict[str, str] | None:
    """`{NOMBRE: "valor"}` de un enum declarado con literales de texto."""
    import ast

    arbol = _arbol(modulo)
    if arbol is None:
        return None
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ClassDef) and nodo.name == clase:
            return {
                item.targets[0].id: item.value.value
                for item in nodo.body
                if isinstance(item, ast.Assign)
                and isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            }
    return None


def parametros_de(modulo: str, funcion: str) -> set[str] | None:
    """Nombres de los parámetros de una función, leídos del archivo."""
    import ast

    arbol = _arbol(modulo)
    if arbol is None:
        return None
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == funcion:
            args = nodo.args
            return {
                a.arg
                for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]
            }
    return None

def nombres_importados_por(script: str, modulo: str) -> set[str] | None:
    """Qué nombres le pide un script de `scripts/` a un módulo de `src/`.

    Los otros dos ayudantes comparan lo que el doble **tiene**. Este compara lo
    que el orquestador **necesita**, que es la pregunta que faltaba: un doble
    puede estar perfectamente sincronizado con el original y aun así no exportar
    el nombre que el script importa, porque el original lo tiene y el doble no
    lo copió.
    """
    import ast

    ruta = RAIZ / "scripts" / f"{script}.py"
    if not ruta.is_file():
        return None
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    objetivo = f"secop_analytics.{modulo}"
    return {
        alias.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom) and nodo.module == objetivo
        for alias in nodo.names
    }


def constantes_de(modulo: str) -> dict[str, Any] | None:
    """Asignaciones de nivel superior con valor literal, del módulo real.

    `valores_de_enum()` cubre enums y `parametros_de()` cubre firmas. Las
    constantes de módulo no las cubría nadie, y ahí vive `ESTADOS_VIVOS`, que
    define el universo entero del flujo 3: si el doble y el original divergen,
    los tests pasan y el barrido nocturno cubre otro universo.

    Lee `Assign` y `AnnAssign`, porque el original las declara con `Final[...]`.
    """
    import ast

    arbol = _arbol(modulo)
    if arbol is None:
        return None

    encontradas: dict[str, Any] = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            nombre, valor = nodo.target.id, nodo.value
        elif (
            isinstance(nodo, ast.Assign)
            and len(nodo.targets) == 1
            and isinstance(nodo.targets[0], ast.Name)
        ):
            nombre, valor = nodo.targets[0].id, nodo.value
        else:
            continue
        if valor is None:
            continue
        try:
            encontradas[nombre] = ast.literal_eval(valor)
        except (ValueError, TypeError):
            continue  # `Fila = dict[str, Any]` y compañía: no son literales
    return encontradas

# --------------------------------------------------------------------------
# Dobles, instalados en sys.modules antes de que nadie importe el orquestador
# --------------------------------------------------------------------------

_paginacion = types.ModuleType("secop_analytics.paginacion")
_paginacion.Fila = dict
_paginacion.LIMITE_POR_DEFECTO = 5000


class ErrorDeConfiguracion(RuntimeError):
    """Copia de `ErrorDeConfiguracion` de `paginacion.py`.

    Hereda de `RuntimeError` igual que el original, y eso importa: el
    orquestador la atrapa **aparte** del `ValueError` precisamente porque no es
    uno. Si acá heredara de `ValueError`, el test del guardarraíl de R1 pasaría
    por el camino equivocado sin que nada lo delate.
    """


_paginacion.ErrorDeConfiguracion = ErrorDeConfiguracion
sys.modules["secop_analytics.paginacion"] = _paginacion


class Flujo(StrEnum):
    """Copia de `Flujo` de `flujos.py`.

    Es un `StrEnum` de verdad y no un stub, para que `.value` se comporte igual
    que en el original — el orquestador lo usa para armar la ruta en disco.

    ⚠ Si los valores divergen del original, los tests pasan y la ruta real
    queda distinta. `test_los_dobles_no_divergieron` lo compara.
    """

    NUEVOS = "contratos_nuevos"
    EVENTOS = "eventos_contractuales"
    REFRESCO = "refresco_de_vivos"


class _Fuente:
    """Guion de lo que la API devolverá, por flujo.

    ⚠ Es un objeto de módulo compartido por todos los tests, no una instancia
    por test. El fixture `fuente` lo limpia antes de cada uno. Funciona porque
    pytest corre en un solo proceso; con `pytest-xdist` habría que revisarlo.
    """

    def __init__(self) -> None:
        self.paginas: dict[str, list[list[dict[str, Any]]]] = {}
        self.llamadas: list[tuple[str, tuple, dict]] = []
        self.explotar_en_pagina: int | None = None

    def programar(self, clave: str, paginas: list[list[dict[str, Any]]]) -> None:
        self.paginas[clave] = paginas

    def _generador(self, clave: str):
        def flujo(*args, **kwargs) -> Iterator[list[dict[str, Any]]]:
            self.llamadas.append((clave, args, kwargs))
            for numero, pagina in enumerate(self.paginas.get(clave, []), start=1):
                if self.explotar_en_pagina == numero:
                    raise RuntimeError(f"la API devolvió 500 en la página {numero}")
                yield pagina

        return flujo


_fuente = _Fuente()

_flujos = types.ModuleType("secop_analytics.flujos")
_flujos.Flujo = Flujo
_flujos.ESTADOS_VIVOS = ("En ejecución", "Modificado", "Suspendido", "Prorrogado")
_flujos.contratos_nuevos = _fuente._generador("nuevos")
_flujos.eventos_contractuales = _fuente._generador("eventos")
_flujos.refresco_de_vivos = _fuente._generador("vivos")
sys.modules["secop_analytics.flujos"] = _flujos

# `cargar_raw.py` es punto de entrada y carga el `.env`. En tests no hay.
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", _dotenv)


# --------------------------------------------------------------------------
# Comprobación de que los dobles no se separaron del original
# --------------------------------------------------------------------------

NOMBRES_DE_FLUJO = {
    "contratos_nuevos": "nuevos",
    "eventos_contractuales": "eventos",
    "refresco_de_vivos": "vivos",
}


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def fuente():
    """Guion de la API. Se limpia entre tests."""
    _fuente.paginas.clear()
    _fuente.llamadas.clear()
    _fuente.explotar_en_pagina = None
    return _fuente


@pytest.fixture
def rutas(tmp_path):
    """`raiz` y `ruta_indice` para pasarle al orquestador."""
    return {"raiz": tmp_path / "raw", "ruta_indice": tmp_path / "indice.duckdb"}


@pytest.fixture
def orquestador():
    """`cargar_raw.py`, importado con los dobles ya instalados."""
    import importlib

    if str(RAIZ / "scripts") not in sys.path:
        sys.path.insert(0, str(RAIZ / "scripts"))
    return importlib.import_module("cargar_raw")


@pytest.fixture
def hoy(orquestador) -> str:
    """El hoy del pipeline en ISO: día colombiano, no del reloj del sistema."""
    return orquestador.hoy().isoformat()


def filas(cantidad: int, *, desde: int = 0, pagado: str = "0") -> list[dict[str, Any]]:
    """Contratos sintéticos. Deliberadamente simples: la suciedad real la
    verifica el script contra la API, no estos dobles."""
    return [
        {
            "id_contrato": f"CO1.PCCNTR.{n}",
            "valor_pagado": pagado,
            "estado_contrato": "En ejecución",
        }
        for n in range(desde, desde + cantidad)
    ]