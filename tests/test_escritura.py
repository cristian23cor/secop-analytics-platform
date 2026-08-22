"""Tests de `escritura.py`.

Los que más importan son los de reanudación y los de `_COMPLETO`: cubren lo que
pasa cuando el proceso muere a mitad de camino, que es el caso que no se puede
reproducir a mano y sí ocurre en producción.
"""

from __future__ import annotations

import gzip
import json

import pytest

from secop_analytics.escritura import (
    NOMBRE_COMPLETO,
    NOMBRE_MANIFIESTO,
    ParticionRaw,
    leer_particion,
)
from secop_analytics.hashing import preparar

FECHA = "2026-08-21"
FLUJO = "refresco_de_vivos"
PARTICION = "2020-01"


def linea_de(n: int) -> bytes:
    fila = {"id_contrato": f"CO1.PCCNTR.{n}", "valor_pagado": str(n * 100)}
    return preparar(fila, flujo=FLUJO, fecha_extraccion=FECHA)[2]


@pytest.fixture
def base(tmp_path):
    return tmp_path / "raw"


def abrir(base, particion=PARTICION, **kwargs):
    return ParticionRaw(
        base,
        flujo=FLUJO,
        fecha_extraccion=FECHA,
        particion=particion,
        verboso=False,
        **kwargs,
    )


# --------------------------------------------------------------------------
# Estructura en disco (D2)
# --------------------------------------------------------------------------

def test_el_particionado_es_flujo_fecha_y_particion(base):
    """Flujo primero: los tres tienen cadencias y políticas distintas."""
    with abrir(base) as p:
        p.escribir(linea_de(1))
        p.completar()

    esperado = (
        base / f"flujo={FLUJO}" / f"fecha_extraccion={FECHA}" / f"particion={PARTICION}"
    )
    assert esperado.is_dir()


# --------------------------------------------------------------------------
# El nivel `particion=`: aislamiento entre escritores concurrentes
# --------------------------------------------------------------------------

def test_dos_particiones_de_la_misma_noche_no_se_pisan(base):
    """El flujo 3 lanza varias particiones en paralelo, misma noche, mismo flujo.

    Sin el nivel `particion=` escribían todas en el mismo directorio: se
    pisaban `parte-0001.jsonl.gz` y se machacaban el manifiesto, sin fallar.
    """
    for particion, rango in (("2020-01", range(0, 10)), ("2020-02", range(100, 115))):
        with abrir(base, particion=particion) as p:
            for n in rango:
                p.escribir(linea_de(n))
            p.completar()

    raiz = base / f"flujo={FLUJO}" / f"fecha_extraccion={FECHA}"
    primera = leer_particion(raiz / "particion=2020-01")
    segunda = leer_particion(raiz / "particion=2020-02")

    assert len(primera) == 10
    assert len(segunda) == 15
    assert {o["datos"]["id_contrato"] for o in primera}.isdisjoint(
        {o["datos"]["id_contrato"] for o in segunda}
    )


def test_el_backfill_no_reanuda_la_particion_equivocada(base):
    """En backfill todas las particiones comparten `fecha_extraccion`.

    Sin el nivel `particion=`, la segunda leía el manifiesto de la primera,
    creía estar reanudando y salteaba trozos: un directorio que parece válido
    y está incompleto.
    """
    with abrir(base, particion="2020-01", lineas_por_trozo=5) as primera:
        for n in range(10):
            primera.escribir(linea_de(n))
        primera.completar()

    with abrir(base, particion="2020-02", lineas_por_trozo=5) as segunda:
        assert segunda.lineas_escritas == 0, "leyó el manifiesto de otra partición"
        for n in range(100, 103):
            segunda.escribir(linea_de(n))
        segunda.completar()

    assert len(leer_particion(segunda.directorio)) == 3


@pytest.mark.parametrize("mala", ["", "2020/01", "2020\\01", "a=b", "con espacio"])
def test_una_particion_que_rompe_la_ruta_falla_temprano(base, mala):
    """`2020/01` crearía un nivel extra en silencio y rompería la regla de
    un directorio por unidad de trabajo."""
    with pytest.raises(ValueError):
        abrir(base, particion=mala)


def test_los_trozos_se_numeran_y_se_cierran_por_tamano(base):
    with abrir(base, lineas_por_trozo=10) as p:
        for n in range(25):
            p.escribir(linea_de(n))
        p.completar()

    trozos = sorted(p.directorio.glob("parte-*.jsonl.gz"))
    assert [t.name for t in trozos] == [
        "parte-0001.jsonl.gz",
        "parte-0002.jsonl.gz",
        "parte-0003.jsonl.gz",
    ]


def test_cada_trozo_es_un_gzip_valido_por_si_solo(base):
    """El argumento que descartó apendear a un archivo abierto (D2, opción 2)."""
    with abrir(base, lineas_por_trozo=10) as p:
        for n in range(25):
            p.escribir(linea_de(n))
        p.completar()

    for trozo in sorted(p.directorio.glob("parte-*.jsonl.gz")):
        with gzip.open(trozo, "rt", encoding="utf-8") as f:
            for linea in f:
                json.loads(linea)  # no lanza


def test_no_quedan_temporales(base):
    with abrir(base, lineas_por_trozo=10) as p:
        for n in range(25):
            p.escribir(linea_de(n))
        p.completar()
    assert list(p.directorio.glob("*.tmp")) == []


# --------------------------------------------------------------------------
# `_COMPLETO`: el invariante 2 de D2
# --------------------------------------------------------------------------

def test_sin_completar_no_hay_marca(base):
    with abrir(base) as p:
        p.escribir(linea_de(1))
    assert not (p.directorio / NOMBRE_COMPLETO).exists()
    assert p.esta_completa is False


def test_completar_pone_la_marca(base):
    with abrir(base) as p:
        p.escribir(linea_de(1))
        p.completar()
    assert p.esta_completa is True


def test_leer_una_particion_incompleta_falla(base):
    """Un recuento parcial que parece total es peor que un error."""
    with abrir(base) as p:
        for n in range(5):
            p.escribir(linea_de(n))

    with pytest.raises(ValueError, match=NOMBRE_COMPLETO):
        leer_particion(p.directorio)


def test_una_excepcion_no_deja_la_particion_legible(base):
    """El caso real: el extractor se cae. dbt no debe leer media noche."""
    with pytest.raises(RuntimeError):
        with abrir(base) as p:
            p.escribir(linea_de(1))
            raise RuntimeError("la API devolvió 500")

    assert p.esta_completa is False
    with pytest.raises(ValueError):
        leer_particion(p.directorio)


def test_pero_lo_escrito_sobrevive_a_la_excepcion(base):
    """Esas líneas ya pueden estar registradas en el índice: perderlas sería el error caro."""
    with pytest.raises(RuntimeError):
        with abrir(base) as p:
            for n in range(5):
                p.escribir(linea_de(n))
            raise RuntimeError("caída")

    assert p.directorio.glob("parte-*.jsonl.gz")
    manifiesto = json.loads((p.directorio / NOMBRE_MANIFIESTO).read_text())
    assert manifiesto["lineas_totales"] == 5
    assert manifiesto["trozos_cerrados"] == 1


# --------------------------------------------------------------------------
# Reanudación
# --------------------------------------------------------------------------

def test_retoma_desde_el_ultimo_trozo_cerrado(base):
    with pytest.raises(RuntimeError):
        with abrir(base, lineas_por_trozo=10) as primera:
            for n in range(20):
                primera.escribir(linea_de(n))
            primera.punto_de_control(cursor="CO1.PCCNTR.19")
            raise RuntimeError("murió en la página siguiente")

    with abrir(base, lineas_por_trozo=10) as segunda:
        assert segunda.cursor == "CO1.PCCNTR.19"
        assert segunda.lineas_escritas == 20
        for n in range(20, 30):
            segunda.escribir(linea_de(n))
        segunda.completar()

    assert len(leer_particion(segunda.directorio)) == 30


def test_el_punto_de_control_guarda_el_cursor(base):
    with abrir(base) as p:
        p.escribir(linea_de(1))
        p.punto_de_control(cursor="CO1.PCCNTR.1")
        manifiesto = json.loads((p.directorio / NOMBRE_MANIFIESTO).read_text())
        assert manifiesto["cursor"] == "CO1.PCCNTR.1"
        p.completar()


def test_un_manifiesto_ilegible_no_rompe_la_corrida(base):
    """Empezar de cero reescribe trozos; abortar pierde la noche."""
    with abrir(base) as p:
        p.escribir(linea_de(1))
        p.punto_de_control(cursor="x")
    (p.directorio / NOMBRE_MANIFIESTO).write_text("{esto no es json")

    with abrir(base) as segunda:
        assert segunda.lineas_escritas == 0
        segunda.escribir(linea_de(2))
        segunda.completar()
    assert segunda.esta_completa


def test_los_temporales_huerfanos_se_limpian(base):
    with abrir(base) as p:
        p.escribir(linea_de(1))
        p.completar()
    basura = p.directorio / "parte-0099.jsonl.gz.tmp"
    basura.write_bytes(b"restos de una corrida muerta")

    with abrir(base):
        pass
    assert not basura.exists()


# --------------------------------------------------------------------------
# Ida y vuelta
# --------------------------------------------------------------------------

def test_lo_que_se_escribe_es_lo_que_se_lee(base):
    with abrir(base, lineas_por_trozo=7) as p:
        for n in range(20):
            p.escribir(linea_de(n))
        p.completar()

    observaciones = leer_particion(p.directorio)
    assert len(observaciones) == 20
    assert [o["datos"]["id_contrato"] for o in observaciones] == [
        f"CO1.PCCNTR.{n}" for n in range(20)
    ]
    assert {o["flujo"] for o in observaciones} == {FLUJO}
    assert {o["fecha_extraccion"] for o in observaciones} == {FECHA}


def test_el_manifiesto_declara_algoritmo_y_compresion(base):
    """Sin esto, cambiar de algoritmo o de compresor es una migración a ciegas."""
    with abrir(base) as p:
        p.escribir(linea_de(1))
        p.completar()

    manifiesto = json.loads((p.directorio / NOMBRE_MANIFIESTO).read_text())
    assert manifiesto["algoritmo_hash"] == "blake2b-128"
    assert manifiesto["compresion"].startswith("gzip")
    assert manifiesto["particion"] == PARTICION


def test_una_particion_vacia_se_puede_completar(base):
    """Una noche sin cambios es un resultado válido, no un error."""
    with abrir(base) as p:
        p.completar()
    assert p.esta_completa
    assert leer_particion(p.directorio) == []


# --------------------------------------------------------------------------
# Reabrir una partición ya completa
# --------------------------------------------------------------------------

def test_reabrir_una_particion_completa_no_pisa_su_manifiesto(base):
    """El bug: el orquestador abre la partición antes de saber si está completa.

    Al reabrirla, `_retomar()` salía sin cargar los contadores y `__exit__`
    guardaba el manifiesto con ceros, dejándolo mintiendo sobre los trozos que
    sí estaban en disco. No fallaba y no avisaba.
    """
    with abrir(base, lineas_por_trozo=5) as p:
        for n in range(10):
            p.escribir(linea_de(n))
        p.completar()

    antes = json.loads((p.directorio / NOMBRE_MANIFIESTO).read_text())

    with abrir(base) as reabierta:
        assert reabierta.esta_completa

    despues = json.loads((p.directorio / NOMBRE_MANIFIESTO).read_text())
    assert despues["lineas_totales"] == antes["lineas_totales"] == 10
    assert despues["trozos_cerrados"] == antes["trozos_cerrados"] == 2


def test_escribir_en_una_particion_completa_falla(base):
    """Mezclaría dos corridas en un directorio que dbt ya considera legible."""
    with abrir(base) as p:
        p.escribir(linea_de(1))
        p.completar()

    with abrir(base) as reabierta:
        with pytest.raises(RuntimeError, match="ya está completa"):
            reabierta.escribir(linea_de(2))


def test_iterar_no_carga_la_particion_en_memoria(base):
    """`iterar_particion` es lo que hay que usar para reconstruir el índice."""
    from secop_analytics.escritura import iterar_particion

    with abrir(base, lineas_por_trozo=4) as p:
        for n in range(10):
            p.escribir(linea_de(n))
        p.completar()

    recorrido = iterar_particion(p.directorio)
    assert not isinstance(recorrido, list)
    assert [o["datos"]["id_contrato"] for o in recorrido] == [
        f"CO1.PCCNTR.{n}" for n in range(10)
    ]


def test_iterar_falla_antes_de_la_primera_fila(base):
    """Un generador que explota en la fila 900.000 deja al consumidor colgado."""
    from secop_analytics.escritura import iterar_particion

    with abrir(base) as p:
        p.escribir(linea_de(1))

    with pytest.raises(ValueError, match=NOMBRE_COMPLETO):
        iterar_particion(p.directorio)  # sin consumir nada