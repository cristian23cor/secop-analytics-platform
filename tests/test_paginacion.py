"""Los reintentos de `paginacion.py`.

## Por qué este archivo es raro

Es el primer test que tiene este módulo. Hasta acá `paginacion.py` se verificaba
solo a mano, contra la API real, con `verificar_carga_raw.py`. Eso estaba anotado
como decisión y no como olvido, con la nota de que se pagaría cuando llegaran los
reintentos. Este es ese momento.

Y hay un obstáculo concreto: `conftest.py` instala un doble de este módulo en
`sys.modules` **por asignación**, así que eclipsa al real durante toda la sesión.
Un `from secop_analytics.paginacion import _pedir` devolvería el doble, que no
tiene `_pedir`.

La salida es cargar el archivo real por ruta, bajo un nombre que declara el
paquete (para que `from .columnas import ...` resuelva) pero que **no pisa la
entrada del doble**. Así estos tests ven el código de verdad y los otros 177
siguen viendo su doble, sin que ninguno se entere del otro.

## Qué se prueba, y qué no

Se prueba la política de reintento: qué se reintenta, qué no, cuánto se espera y
cuándo se abandona. No se prueba la paginación por keyset ni la construcción de
la cláusula SoQL, que siguen verificándose contra la API real.

Ninguna de estas pruebas duerme: `time.sleep` se reemplaza por una función que
anota cuánto le pidieron. Eso además convierte la espera en algo observable, que
es lo que permite afirmar que crece.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import requests

RAIZ = Path(__file__).resolve().parent.parent


def _modulo_real():
    """El `paginacion.py` de verdad, sin tocar el doble de `conftest`."""
    ruta = RAIZ / "src" / "secop_analytics" / "paginacion.py"
    if str(RAIZ / "src") not in sys.path:
        sys.path.insert(0, str(RAIZ / "src"))
    import secop_analytics  # noqa: F401  el paquete real, para el import relativo

    spec = importlib.util.spec_from_file_location(
        "secop_analytics._paginacion_bajo_prueba", ruta
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


pag = _modulo_real()


def respuesta(codigo: int, *, retry_after: str | None = None) -> requests.Response:
    """Una `Response` de verdad, no un doble: `raise_for_status` tiene que ser
    el mismo que usa el código en producción."""
    r = requests.Response()
    r.status_code = codigo
    r.url = pag.URL_BASE
    if retry_after is not None:
        r.headers["Retry-After"] = retry_after
    return r


@pytest.fixture
def esperas(monkeypatch):
    """Reemplaza `time.sleep` por un registro de cuánto se pidió esperar."""
    anotadas: list[float] = []
    monkeypatch.setattr(pag.time, "sleep", anotadas.append)
    return anotadas


def de_a_una(*respuestas):
    """Devuelve una respuesta distinta por llamada. Una excepción se levanta."""
    cola = list(respuestas)

    def hacer():
        item = cola.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return hacer


# --------------------------------------------------------------------------
# Lo que NO se reintenta. Es la mitad de la política y la que se olvida.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", [200, 201])
def test_una_respuesta_buena_no_espera(codigo, esperas):
    r = pag._pedir(de_a_una(respuesta(codigo)), que="prueba")
    assert r.status_code == codigo
    assert esperas == []


@pytest.mark.parametrize("codigo", [400, 401, 403, 404, 422])
def test_un_error_del_cliente_no_se_reintenta(codigo, esperas):
    """Un `$where` mal armado o un token inválido no se arreglan esperando.

    Reintentarlos cinco veces es tardar medio minuto en dar el mismo mensaje, y
    encima gastar cupo de la API en peticiones que ya se sabía que fallaban.
    """
    with pytest.raises(requests.HTTPError):
        pag._pedir(de_a_una(respuesta(codigo)), que="prueba")
    assert esperas == [], "un error del cliente no debe hacer esperar ni una vez"


# --------------------------------------------------------------------------
# Lo que sí. Todos estos fallan contra el código sin reintentos.
# --------------------------------------------------------------------------


def test_un_429_pasajero_se_absorbe(esperas):
    r = pag._pedir(de_a_una(respuesta(429), respuesta(200)), que="prueba")
    assert r.status_code == 200
    assert esperas == [pag._ESPERA_INICIAL]


@pytest.mark.parametrize("codigo", [500, 502, 503, 504])
def test_los_cinco_xx_se_reintentan(codigo, esperas):
    r = pag._pedir(de_a_una(respuesta(codigo), respuesta(200)), que="prueba")
    assert r.status_code == 200
    assert len(esperas) == 1


@pytest.mark.parametrize("fallo", [requests.Timeout(), requests.ConnectionError()])
def test_un_fallo_de_red_se_reintenta(fallo, esperas):
    """Un timeout no trae respuesta, así que no hay código que mirar. Se trata
    igual que un 5xx: la API está con problemas y se le da otra oportunidad."""
    r = pag._pedir(de_a_una(fallo, respuesta(200)), que="prueba")
    assert r.status_code == 200
    assert len(esperas) == 1


def test_la_espera_crece(esperas):
    """Cuatro esperas de 2, 4, 8 y 16 segundos, y al quinto intento se rinde."""
    with pytest.raises(requests.HTTPError):
        pag._pedir(de_a_una(*[respuesta(503)] * pag._INTENTOS), que="prueba")
    assert esperas == [2.0, 4.0, 8.0, 16.0]
    assert sum(esperas) == pag._PRESUPUESTO_DE_ESPERA


def test_al_agotarse_levanta_el_error_original(esperas):
    """No un error propio.

    Los dos lugares que manejan esto capturan `Exception` y muestran el tipo.
    Envolverlo en un `RuntimeError` los dejaría diciendo "RuntimeError" donde
    antes decían "HTTPError 503", que es peor mensaje para quien lo lee.
    """
    with pytest.raises(requests.ConnectionError):
        pag._pedir(
            de_a_una(*[requests.ConnectionError("sin ruta")] * pag._INTENTOS),
            que="prueba",
        )


# --------------------------------------------------------------------------
# `Retry-After`
# --------------------------------------------------------------------------


def test_respeta_retry_after_cuando_pide_mas(esperas):
    """El servidor manda: si pide más que la espera creciente, se le hace caso."""
    pag._pedir(de_a_una(respuesta(429, retry_after="9"), respuesta(200)), que="x")
    assert esperas == [9.0]


def test_ignora_retry_after_cuando_pide_menos(esperas):
    """La espera creciente es el piso. Volver antes es gastar un intento en una
    petición que probablemente vuelva a ser rechazada."""
    pag._pedir(de_a_una(respuesta(429, retry_after="1"), respuesta(200)), que="x")
    assert esperas == [pag._ESPERA_INICIAL]


def test_retry_after_no_supera_el_presupuesto(esperas):
    """Una cabecera de una hora dejaría la corrida en silencio, y no habría cómo
    distinguir eso de un cuelgue. Se espera lo que queda y se abandona."""
    with pytest.raises(requests.HTTPError):
        pag._pedir(
            de_a_una(*[respuesta(429, retry_after="3600")] * pag._INTENTOS),
            que="x",
        )
    assert esperas == [pag._PRESUPUESTO_DE_ESPERA], (
        "la primera espera se come el presupuesto entero y no hay una segunda"
    )


def test_una_cabecera_ilegible_cae_en_la_espera_creciente(esperas):
    """No es un error: es lo que se haría igual si la cabecera no estuviera."""
    pag._pedir(de_a_una(respuesta(429, retry_after="ya mismo"), respuesta(200)), que="x")
    assert esperas == [pag._ESPERA_INICIAL]


def test_retry_after_como_fecha(esperas):
    """La norma admite segundos o fecha HTTP. Las dos formas se entienden."""
    from email.utils import format_datetime
    from datetime import datetime, timedelta, timezone

    cuando = datetime.now(timezone.utc) + timedelta(seconds=10)
    pag._pedir(
        de_a_una(respuesta(429, retry_after=format_datetime(cuando)), respuesta(200)),
        que="x",
    )
    assert esperas and 8.0 <= esperas[0] <= 11.0
