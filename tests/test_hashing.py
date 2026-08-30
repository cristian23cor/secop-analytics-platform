"""Tests de `hashing.py`.

Sin disco, sin red, sin reloj: todo el módulo es puro. Si alguno de estos falla,
la deduplicación por bytes (D3) no se puede confiar.
"""

from __future__ import annotations

import json

import pytest

from secop_analytics.hashing import (
    ALGORITMO_HASH,
    canonicalizar,
    envolver,
    hashear,
    preparar,
)

FILA = {
    "id_contrato": "CO1.PCCNTR.1735835",
    "valor_del_contrato": "8959088",
    "estado_contrato": "En ejecución",
    "urlproceso": {"url": "https://community.secop.gov.co/x?noticeUID=CO1.NTC.1"},
}


# --------------------------------------------------------------------------
# Determinismo
# --------------------------------------------------------------------------

def test_el_orden_de_las_claves_no_cambia_los_bytes():
    """Si Socrata reordena las claves, la deduplicación no debe romperse."""
    revertida = dict(reversed(list(FILA.items())))
    assert canonicalizar(FILA) == canonicalizar(revertida)


def test_ordena_tambien_dentro_del_objeto_anidado():
    """`urlproceso` es el único anidado (H6) y también tiene que canonicalizar."""
    a = {"id_contrato": "X", "urlproceso": {"b": 2, "a": 1}}
    b = {"id_contrato": "X", "urlproceso": {"a": 1, "b": 2}}
    assert canonicalizar(a) == canonicalizar(b)


def test_no_deja_espacios_de_relleno():
    """`separators` compacto: sobre 2,8M de filas los espacios son volumen."""
    assert b", " not in canonicalizar(FILA)
    assert b": " not in canonicalizar(FILA)


def test_no_escapa_los_no_ascii():
    """`ensure_ascii=False`: la eñe se escribe como eñe."""
    assert "ó".encode("utf-8") in canonicalizar(FILA)


# --------------------------------------------------------------------------
# D1: raw no normaliza
# --------------------------------------------------------------------------

def test_la_clave_ausente_no_se_rellena():
    """Ausente y `null` producen hashes distintos, y así debe ser.

    Se guarda una fila de más cuando la API pasa de omitir a mandar `null`. Es
    el error que SOBRA. Rellenar acá lo volvería un error que falta, y rompería
    D1. Si este test falla, alguien "arregló" algo que no estaba roto.
    """
    sin_clave = {"id_contrato": "X", "valor_pagado": "10"}
    con_nulo = {"id_contrato": "X", "valor_pagado": "10", "ultima_actualizacion": None}
    assert canonicalizar(sin_clave) != canonicalizar(con_nulo)


# --------------------------------------------------------------------------
# El hash cubre los datos y nada más
# --------------------------------------------------------------------------

def test_los_metadatos_no_entran_al_hash():
    """Si entraran, nada se deduplicaría jamás: cambian todas las noches."""
    _, primero, _ = preparar(FILA, flujo="contratos_nuevos", fecha_extraccion="2026-08-21")
    _, segundo, _ = preparar(FILA, flujo="refresco_de_vivos", fecha_extraccion="2026-09-30")
    assert primero == segundo


def test_un_cambio_material_cambia_el_hash():
    movida = {**FILA, "valor_del_contrato": "9000000"}
    assert hashear(canonicalizar(FILA)) != hashear(canonicalizar(movida))


def test_el_hash_tiene_32_caracteres_hexadecimales():
    huella = hashear(canonicalizar(FILA))
    assert len(huella) == 32
    assert set(huella) <= set("0123456789abcdef")


def test_el_nombre_del_algoritmo_esta_declarado():
    """Va al manifiesto: sin él, cambiar de algoritmo es una migración a ciegas."""
    assert ALGORITMO_HASH == "blake2b-128"


# --------------------------------------------------------------------------
# La propiedad central de I1
# --------------------------------------------------------------------------

def test_los_bytes_del_archivo_son_los_que_se_hashearon():
    """El test que sostiene el diseño.

    Se relee la línea escrita, se extrae `datos`, se rehashea, y tiene que dar
    el mismo hash. Si `envolver()` reserializara en vez de empalmar bytes, esto
    podría pasar por casualidad hoy y fallar el día que cambie una opción de
    `json.dumps`.
    """
    _, huella, linea = preparar(FILA, flujo="f", fecha_extraccion="2026-08-21")
    releida = json.loads(linea)

    assert releida["hash"] == huella
    assert hashear(canonicalizar(releida["datos"])) == huella


def test_la_carga_util_aparece_literal_dentro_de_la_linea():
    """Más fuerte que el anterior: los bytes canónicos están tal cual, no re-armados."""
    canonica = canonicalizar(FILA)
    linea = envolver(canonica, huella="abc", flujo="f", fecha_extraccion="2026-08-21")
    assert b',"datos":' + canonica + b"}" in linea


def test_sobrevive_el_texto_sucio_de_la_fuente():
    """H22: comillas de Windows-1252 mal decodificadas, más comillas y barras reales."""
    sucia = {
        "id_contrato": "X",
        "objeto_del_contrato": 'RESOLUCIoN \u0093MANUAL\u0094 con "comillas" y \\ barra',
        "descripcion": "salto\nembebido y punto;coma",
    }
    _, _, linea = preparar(sucia, flujo="f", fecha_extraccion="2026-08-21")
    assert json.loads(linea)["datos"] == sucia


def test_cada_linea_ocupa_un_solo_renglon():
    """JSONL: un salto de línea embebido no puede partir el registro en dos."""
    sucia = {"id_contrato": "X", "direcci_n": "calle 1\ncasa 2"}
    _, _, linea = preparar(sucia, flujo="f", fecha_extraccion="2026-08-21")
    assert b"\n" not in linea


# --------------------------------------------------------------------------
# Fallas ruidosas
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fila", [{"valor": "1"}, {"id_contrato": ""}, {"id_contrato": None}])
def test_sin_id_contrato_falla(fila):
    """Es la llave del índice. Sin ella la fila no se deduplica ni se une."""
    with pytest.raises(ValueError, match="id_contrato"):
        preparar(fila, flujo="f", fecha_extraccion="2026-08-21")


def test_lo_no_serializable_falla_con_el_id_puesto():
    """Saltarse la fila en silencio sería perderla: la fuente se sobrescribe hoy."""
    with pytest.raises(ValueError, match="CO1.PCCNTR.1"):
        canonicalizar({"id_contrato": "CO1.PCCNTR.1", "raro": {1, 2}})


# --------------------------------------------------------------------------
# `verificar_linea()`
# --------------------------------------------------------------------------

def test_una_linea_recien_escrita_se_verifica():
    from secop_analytics.hashing import verificar_linea

    _, _, linea = preparar(FILA, flujo="f", fecha_extraccion="2026-08-21")
    assert verificar_linea(linea) is True


def test_una_linea_manipulada_no_se_verifica():
    """Si alguien edita `datos` a mano, el hash deja de corresponder."""
    from secop_analytics.hashing import verificar_linea

    _, _, linea = preparar(FILA, flujo="f", fecha_extraccion="2026-08-21")
    manipulada = json.loads(linea)
    manipulada["datos"]["valor_del_contrato"] = "99999999"
    assert verificar_linea(json.dumps(manipulada).encode("utf-8")) is False


def test_los_metadatos_no_afectan_la_verificacion():
    """Cambiar el envoltorio no invalida la línea: el hash es solo de `datos`."""
    from secop_analytics.hashing import verificar_linea

    _, _, linea = preparar(FILA, flujo="f", fecha_extraccion="2026-08-21")
    con_otros = json.loads(linea)
    con_otros["flujo"] = "otro_flujo"
    con_otros["fecha_extraccion"] = "2030-01-01"
    assert verificar_linea(json.dumps(con_otros).encode("utf-8")) is True


def test_la_linea_envuelta_no_esta_canonicalizada():
    """Documenta lo que el módulo NO promete.

    `datos` va al final, pero alfabéticamente iría primero. Si este test
    empezara a fallar, alguien canonicalizó la línea entera, y eso rompería la
    propiedad de I1, porque los bytes de `datos` dejarían de ser literalmente
    los que se hashearon.
    """
    _, _, linea = preparar(FILA, flujo="f", fecha_extraccion="2026-08-21")
    recanonicalizada = json.dumps(
        json.loads(linea), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    assert linea != recanonicalizada