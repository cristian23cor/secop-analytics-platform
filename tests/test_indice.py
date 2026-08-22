"""Tests de `indice.py`.

Usan un archivo temporal de DuckDB. Si alguno falla, la deduplicación por bytes
(D3) puede estar perdiendo observaciones — que es el error caro del diseño.
"""

from __future__ import annotations

import pytest

from secop_analytics.hashing import ALGORITMO_HASH, preparar
from secop_analytics.indice import IndiceHashes

FECHA = "2026-08-21"


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "indice.duckdb"


@pytest.fixture
def indice(ruta):
    with IndiceHashes(ruta, verboso=False) as i:
        yield i


# --------------------------------------------------------------------------
# Comportamiento básico
# --------------------------------------------------------------------------

def test_arranca_vacio_sin_archivo_previo(ruta):
    """Primera corrida: no puede fallar por abrir en solo lectura algo inexistente."""
    with IndiceHashes(ruta, verboso=False) as i:
        assert i.conocidos == 0


def test_un_contrato_nuevo_siempre_cambia(indice):
    assert indice.cambio("CO1.PCCNTR.1", "abc") is True


def test_la_misma_huella_no_cambia(indice):
    indice.registrar("CO1.PCCNTR.1", "abc", fecha_extraccion=FECHA, flujo="f")
    assert indice.cambio("CO1.PCCNTR.1", "abc") is False


def test_otra_huella_si_cambia(indice):
    indice.registrar("CO1.PCCNTR.1", "abc", fecha_extraccion=FECHA, flujo="f")
    assert indice.cambio("CO1.PCCNTR.1", "def") is True


def test_el_solape_entre_flujos_no_duplica(indice):
    """Los flujos 1 y 2 se solapan a propósito: un contrato firmado y modificado
    el mismo día llega por dos caminos. No puede escribirse dos veces."""
    indice.registrar("CO1.PCCNTR.1", "abc", fecha_extraccion=FECHA, flujo="contratos_nuevos")
    assert indice.cambio("CO1.PCCNTR.1", "abc") is False


# --------------------------------------------------------------------------
# Persistencia entre corridas
# --------------------------------------------------------------------------

def test_lo_registrado_sobrevive_a_la_corrida(ruta):
    with IndiceHashes(ruta, verboso=False) as primera:
        primera.registrar("CO1.PCCNTR.1", "abc", fecha_extraccion=FECHA, flujo="f")

    with IndiceHashes(ruta, verboso=False) as segunda:
        assert segunda.conocidos == 1
        assert segunda.cambio("CO1.PCCNTR.1", "abc") is False
        assert segunda.cambio("CO1.PCCNTR.1", "xyz") is True


def test_la_segunda_noche_pisa_la_huella(ruta):
    with IndiceHashes(ruta, verboso=False) as noche1:
        noche1.registrar("CO1.PCCNTR.1", "v1", fecha_extraccion="2026-08-21", flujo="f")
    with IndiceHashes(ruta, verboso=False) as noche2:
        noche2.registrar("CO1.PCCNTR.1", "v2", fecha_extraccion="2026-08-22", flujo="f")
    with IndiceHashes(ruta, verboso=False) as noche3:
        assert noche3.cambio("CO1.PCCNTR.1", "v2") is False
        assert noche3.cambio("CO1.PCCNTR.1", "v1") is True


def test_vuelca_aunque_haya_excepcion(ruta):
    """Lo ya escrito a disco tiene que quedar reflejado, o se duplica mañana."""
    with pytest.raises(RuntimeError):
        with IndiceHashes(ruta, verboso=False) as i:
            i.registrar("CO1.PCCNTR.1", "abc", fecha_extraccion=FECHA, flujo="f")
            raise RuntimeError("el extractor se cayó")

    with IndiceHashes(ruta, verboso=False) as despues:
        assert despues.cambio("CO1.PCCNTR.1", "abc") is False


def test_volcar_dos_veces_no_reescribe(indice):
    indice.registrar("CO1.PCCNTR.1", "abc", fecha_extraccion=FECHA, flujo="f")
    assert indice.volcar() == 1
    assert indice.volcar() == 0
    assert indice.cambio("CO1.PCCNTR.1", "abc") is False


def test_guarda_el_algoritmo(ruta):
    """Sin esto, cambiar de algoritmo sería una migración a ciegas (I2)."""
    import duckdb

    with IndiceHashes(ruta, verboso=False) as i:
        i.registrar("CO1.PCCNTR.1", "abc", fecha_extraccion=FECHA, flujo="f")

    con = duckdb.connect(str(ruta), read_only=True)
    assert con.execute("select algoritmo from indice_hashes").fetchone()[0] == ALGORITMO_HASH
    con.close()


# --------------------------------------------------------------------------
# Reconstrucción: el índice es caché, raw es la verdad
# --------------------------------------------------------------------------

def test_se_reconstruye_desde_raw(ruta):
    """Si el índice se pierde, raw lo rearma. Gana la última observación."""
    import json

    fila_v1 = {"id_contrato": "CO1.PCCNTR.1", "valor_pagado": "100"}
    fila_v2 = {"id_contrato": "CO1.PCCNTR.1", "valor_pagado": "200"}
    observaciones = []
    for fila, fecha in ((fila_v1, "2026-08-21"), (fila_v2, "2026-08-22")):
        _, _, linea = preparar(fila, flujo="f", fecha_extraccion=fecha)
        observaciones.append(json.loads(linea))

    with IndiceHashes(ruta, verboso=False) as i:
        i.reconstruir_desde_raw(iter(observaciones))

    _, huella_v2, _ = preparar(fila_v2, flujo="f", fecha_extraccion="2026-08-22")
    _, huella_v1, _ = preparar(fila_v1, flujo="f", fecha_extraccion="2026-08-21")
    with IndiceHashes(ruta, verboso=False) as despues:
        assert despues.cambio("CO1.PCCNTR.1", huella_v2) is False
        assert despues.cambio("CO1.PCCNTR.1", huella_v1) is True


def test_el_indice_reconstruido_coincide_con_el_original(ruta, tmp_path):
    """Reconstruir desde raw tiene que dar el mismo estado que la corrida real."""
    import json

    filas = [{"id_contrato": f"CO1.PCCNTR.{n}", "valor_pagado": str(n)} for n in range(50)]
    observaciones = []
    with IndiceHashes(ruta, verboso=False) as original:
        for fila in filas:
            id_c, huella, linea = preparar(fila, flujo="f", fecha_extraccion=FECHA)
            assert original.cambio(id_c, huella)
            observaciones.append(json.loads(linea))
            original.registrar(id_c, huella, fecha_extraccion=FECHA, flujo="f")

    otra = tmp_path / "reconstruido.duckdb"
    with IndiceHashes(otra, verboso=False) as copia:
        copia.reconstruir_desde_raw(iter(observaciones))

    with IndiceHashes(ruta, verboso=False) as a, IndiceHashes(otra, verboso=False) as b:
        assert a.conocidos == b.conocidos == 50
        for fila in filas:
            _, huella, _ = preparar(fila, flujo="f", fecha_extraccion=FECHA)
            assert a.cambio(fila["id_contrato"], huella) is False
            assert b.cambio(fila["id_contrato"], huella) is False


# --------------------------------------------------------------------------
# Integración con hashing: el flujo real
# --------------------------------------------------------------------------

def test_dos_noches_sin_cambios_solo_guardan_una_vez(ruta):
    """El caso que justifica D3: el 99% de las filas no cambia entre noches."""
    fila = {"id_contrato": "CO1.PCCNTR.1", "valor_pagado": "100", "estado_contrato": "En ejecución"}
    guardadas = 0

    for fecha in ("2026-08-21", "2026-08-22", "2026-08-23"):
        with IndiceHashes(ruta, verboso=False) as i:
            id_c, huella, _ = preparar(fila, flujo="refresco_de_vivos", fecha_extraccion=fecha)
            if i.cambio(id_c, huella):
                guardadas += 1
                i.registrar(id_c, huella, fecha_extraccion=fecha, flujo="refresco_de_vivos")

    assert guardadas == 1, "una fila inmutable se guardó más de una vez"


def test_un_pago_nuevo_si_se_guarda(ruta):
    guardadas = 0
    for fecha, pagado in (("2026-08-21", "100"), ("2026-08-22", "100"), ("2026-08-23", "250")):
        fila = {"id_contrato": "CO1.PCCNTR.1", "valor_pagado": pagado}
        with IndiceHashes(ruta, verboso=False) as i:
            id_c, huella, _ = preparar(fila, flujo="f", fecha_extraccion=fecha)
            if i.cambio(id_c, huella):
                guardadas += 1
                i.registrar(id_c, huella, fecha_extraccion=fecha, flujo="f")

    assert guardadas == 2, "se perdió el avance de ejecución financiera (H9)"


# --------------------------------------------------------------------------
# `reconstruir_desde_raw`: fusión contra reconstrucción
# --------------------------------------------------------------------------

def _observacion(id_contrato: str, huella: str) -> dict:
    return {
        "fecha_extraccion": FECHA,
        "flujo": "f",
        "hash": huella,
        "datos": {"id_contrato": id_contrato},
    }


def test_por_defecto_fusiona_y_conserva_lo_que_no_venia(ruta):
    """Es lo correcto al alimentar el índice partición por partición."""
    with IndiceHashes(ruta, verboso=False) as i:
        i.registrar("VIEJO", "h1", fecha_extraccion=FECHA, flujo="f")

    with IndiceHashes(ruta, verboso=False) as i:
        i.reconstruir_desde_raw([_observacion("NUEVO", "h2")])

    with IndiceHashes(ruta, verboso=False) as despues:
        assert despues.conocidos == 2
        assert despues.cambio("VIEJO", "h1") is False


def test_desde_cero_borra_lo_que_raw_no_respalda(ruta):
    """La única forma de sacar entradas equivocadas de un índice corrupto.

    Una fusión las conservaría, y esos contratos no se volverían a guardar
    nunca: el índice diría conocerlos sin que raw los tenga.
    """
    with IndiceHashes(ruta, verboso=False) as i:
        i.registrar("FANTASMA", "h1", fecha_extraccion=FECHA, flujo="f")

    with IndiceHashes(ruta, verboso=False) as i:
        i.reconstruir_desde_raw([_observacion("REAL", "h2")], desde_cero=True)

    with IndiceHashes(ruta, verboso=False) as despues:
        assert despues.conocidos == 1
        assert despues.cambio("FANTASMA", "h1") is True   # ya no lo conoce
        assert despues.cambio("REAL", "h2") is False


def test_acepta_una_lista_ademas_de_un_generador(ruta):
    """El tipo es Iterable: no hace falta envolver en `iter()`."""
    with IndiceHashes(ruta, verboso=False) as i:
        assert i.reconstruir_desde_raw([_observacion("A", "h")]) == 1