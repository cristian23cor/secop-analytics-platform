"""Tests de `columnas.py`.

Existen porque el docstring del módulo promete que "los cuatro conjuntos cubren
las 85 sin solaparse, y `test_columnas.py` lo verifica". Durante un tiempo esa
promesa fue falsa: el archivo no existía.

Eso importa más de lo que parece. `columnas.py` es la fuente de verdad única de
qué se descarga y de cómo se compara cada columna. Sin estos tests, alguien
puede poner una columna en dos conjuntos y nada falla: el `$select` sigue
funcionando, la ingesta corre, y la columna se compara con un criterio o con el
otro según el orden de los `if` en `clasificacion()`.
"""

from __future__ import annotations

import pytest

from secop_analytics.columnas import (
    CLASIFICADAS,
    COLUMNAS_EXTRAIDAS,
    COSMETICAS,
    IMPOSIBLES,
    MATERIALES,
    PERSONALES,
    clasificacion,
    clausula_select,
    validar_cobertura,
)

TOTAL_ESQUEMA = 85
CONJUNTOS = {
    "MATERIALES": MATERIALES,
    "IMPOSIBLES": IMPOSIBLES,
    "COSMETICAS": COSMETICAS,
    "PERSONALES": PERSONALES,
}


# --------------------------------------------------------------------------
# La promesa del docstring
# --------------------------------------------------------------------------

def test_los_cuatro_conjuntos_cubren_las_85():
    assert len(CLASIFICADAS) == TOTAL_ESQUEMA


def test_ningun_par_de_conjuntos_se_solapa():
    """Una columna en dos conjuntos no rompe nada visible.

    El `$select` sigue funcionando y la ingesta corre. Lo que cambia es con qué
    criterio se compara esa columna, y lo decide el orden de los `if` en
    `clasificacion()`. Es un fallo silencioso.
    """
    nombres = list(CONJUNTOS)
    for i, primero in enumerate(nombres):
        for segundo in nombres[i + 1:]:
            comun = CONJUNTOS[primero] & CONJUNTOS[segundo]
            assert not comun, f"{primero} y {segundo} comparten {sorted(comun)}"


def test_la_suma_de_los_tamanos_da_el_total():
    """Redundante con los dos anteriores a propósito: si este falla y los otros
    pasan, el error está en el test, no en el módulo."""
    assert sum(len(s) for s in CONJUNTOS.values()) == TOTAL_ESQUEMA


# --------------------------------------------------------------------------
# Qué se descarga y qué no
# --------------------------------------------------------------------------

def test_los_personales_no_se_descargan():
    """H7: el filtro corre en el `$select`, no después."""
    assert not (set(COLUMNAS_EXTRAIDAS) & PERSONALES)


def test_se_descarga_todo_lo_demas():
    assert set(COLUMNAS_EXTRAIDAS) == MATERIALES | IMPOSIBLES | COSMETICAS


def test_se_descargan_67_columnas():
    assert len(COLUMNAS_EXTRAIDAS) == TOTAL_ESQUEMA - len(PERSONALES) == 67


def test_las_extraidas_no_tienen_duplicados():
    """Es una tupla, no un conjunto: nada impide que se repita un nombre."""
    assert len(COLUMNAS_EXTRAIDAS) == len(set(COLUMNAS_EXTRAIDAS))


def test_las_extraidas_estan_ordenadas():
    """Orden estable = `$select` estable = URLs cacheables y diffs legibles."""
    assert list(COLUMNAS_EXTRAIDAS) == sorted(COLUMNAS_EXTRAIDAS)


# --------------------------------------------------------------------------
# La cláusula que viaja a la API
# --------------------------------------------------------------------------

def test_la_clausula_lista_las_67_separadas_por_coma():
    clausula = clausula_select()
    assert clausula.count(",") == len(COLUMNAS_EXTRAIDAS) - 1
    assert clausula.split(",") == list(COLUMNAS_EXTRAIDAS)


def test_la_clausula_no_trae_espacios():
    """Un espacio en el `$select` viaja como `%20` y algunos proxies lo cortan."""
    assert " " not in clausula_select()


@pytest.mark.parametrize("personal", sorted(PERSONALES))
def test_ninguna_personal_aparece_en_la_clausula(personal):
    """Uno por columna: si falla, el nombre del test dice cuál se filtró."""
    assert personal not in clausula_select().split(",")


# --------------------------------------------------------------------------
# `clasificacion()`
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("columna", "esperada"),
    [
        ("valor_pagado", "material"),
        ("id_contrato", "imposible"),
        ("nombre_entidad", "cosmetica"),
        ("nombre_representante_legal", "personal"),
    ],
)
def test_clasifica_un_caso_de_cada_categoria(columna, esperada):
    assert clasificacion(columna) == esperada


def test_toda_columna_clasificada_devuelve_una_categoria():
    for columna in CLASIFICADAS:
        assert clasificacion(columna) in {"material", "imposible", "cosmetica", "personal"}


def test_una_columna_desconocida_falla():
    """Ruidoso a propósito: una columna nueva en la fuente tiene que doler."""
    with pytest.raises(KeyError, match="sin clasificar"):
        clasificacion("columna_que_no_existe")


# --------------------------------------------------------------------------
# `validar_cobertura()`
# --------------------------------------------------------------------------

def test_una_fuente_identica_no_reporta_nada():
    resultado = validar_cobertura(set(CLASIFICADAS))
    assert resultado == {"sin_clasificar": set(), "desaparecidas": set()}


def test_detecta_una_columna_nueva_en_la_fuente():
    resultado = validar_cobertura(set(CLASIFICADAS) | {"columna_nueva"})
    assert resultado["sin_clasificar"] == {"columna_nueva"}
    assert resultado["desaparecidas"] == set()


def test_detecta_una_columna_que_la_fuente_dejo_de_entregar():
    resultado = validar_cobertura(set(CLASIFICADAS) - {"valor_pagado"})
    assert resultado["desaparecidas"] == {"valor_pagado"}
    assert resultado["sin_clasificar"] == set()


# --------------------------------------------------------------------------
# Invariantes de contenido que costaron trabajo descubrir
# --------------------------------------------------------------------------

def test_las_seis_fuentes_de_financiacion_son_materiales():
    """Son SEIS, no cinco. La sexta solo aparece enumerando el esquema completo,
    y RN1 depende de que estén todas."""
    fuentes = {
        "presupuesto_general_de_la_nacion_pgn",
        "sistema_general_de_participaciones",
        "sistema_general_de_regal_as",
        "recursos_de_credito",
        "recursos_propios",
        "recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_",
    }
    assert len(fuentes) == 6
    assert fuentes <= MATERIALES


def test_valor_pagado_es_material():
    """Si deja de serlo, los 735.809 contratos con pagos se quedan sin serie
    temporal, la tabla de snapshots queda casi vacía, y ningún otro test falla."""
    assert "valor_pagado" in MATERIALES


def test_las_fechas_que_arrancan_nulas_son_materiales():
    """Pasar de nulo a fecha es el cambio más informativo del snapshot."""
    assert {
        "fecha_inicio_liquidacion",
        "fecha_fin_liquidacion",
        "fecha_de_notificaci_n_de_prorrogaci_n",
        "ultima_actualizacion",
    } <= MATERIALES


def test_el_trio_del_proveedor_es_material():
    """Cambia con la cesión: 28.557 contratos en estado `cedido`."""
    assert {"proveedor_adjudicado", "documento_proveedor", "codigo_proveedor"} <= MATERIALES


def test_referencia_del_contrato_no_es_imposible():
    """Las entidades la editan a mano y no es un identificador global. En
    IMPOSIBLES llenaría la alerta de ruido, y una alerta ruidosa se ignora."""
    assert "referencia_del_contrato" in COSMETICAS