"""Tests de `scripts/cargar_raw.py`.

Prueban **lo que el orquestador decide**, no el contrato con la fuente. Esa
mitad la cubre `scripts/verificar_carga_raw.py`, que corre contra la API real.

El más importante es `test_el_indice_no_se_adelanta_al_archivo`: verifica el
invariante que hace que una caída a mitad de camino cueste un duplicado en vez
de una fila perdida para siempre.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from conftest import filas
from secop_analytics.escritura import NOMBRE_COMPLETO, NOMBRE_MANIFIESTO, leer_particion
from secop_analytics.indice import IndiceHashes


# --------------------------------------------------------------------------
# Coherencia de los propios dobles
# --------------------------------------------------------------------------

def test_los_dobles_no_divergieron():
    """Los valores del enum falso tienen que ser los del real.

    Si se separan, todos los tests pasan y la ruta en disco queda distinta.
    """
    from conftest import Flujo, valores_de_enum

    real = valores_de_enum("flujos", "Flujo")
    assert real is not None, "no se pudo leer flujos.py"
    assert {m.name: m.value for m in Flujo} == real


def test_los_flujos_reales_aceptan_el_cursor_de_reanudacion():
    """Los dobles usan `*args, **kwargs`, así que tragan cualquier cosa.

    Un parámetro nuevo —o uno mal escrito— pasa sin que nada falle. Cuando se
    agregó `desde_cursor`, el doble lo aceptó sin chistar; un `desde_curso` con
    typo también lo habría hecho. Este test lee lo que el módulo real declara.
    """
    from conftest import NOMBRES_DE_FLUJO, parametros_de

    esperados = {"limite", "sesion", "desde_cursor"}
    for nombre in NOMBRES_DE_FLUJO:
        parametros = parametros_de("flujos", nombre)
        assert parametros is not None, f"no se pudo leer {nombre}"
        faltan = esperados - parametros
        assert not faltan, f"{nombre} no acepta {sorted(faltan)}"


def test_paginar_acepta_el_cursor():
    """El otro extremo del circuito: sin esto, el cursor no llega a la API."""
    from conftest import parametros_de

    parametros = parametros_de("paginacion", "paginar")
    assert parametros is not None, "no se pudo leer paginacion.py"
    assert "desde_cursor" in parametros

MODULOS_DOBLADOS = ["paginacion", "flujos"]


@pytest.mark.parametrize("modulo", MODULOS_DOBLADOS)
def test_el_doble_exporta_todo_lo_que_el_orquestador_importa(modulo):
    """Los tres tests de arriba comparan lo que el doble TIENE. Este compara lo
    que el orquestador NECESITA, que es la pregunta que faltaba.

    Ya ocurrió: se agregó `from secop_analytics.paginacion import
    ErrorDeConfiguracion` a `cargar_raw.py`, el doble no lo exportaba, y 19
    tests reventaron con `ImportError` antes de correr una sola aserción. Esa
    vez salió barato porque el fallo fue ruidoso; el modo peligroso —el doble
    exporta el nombre con otro valor— lo cubre el test de abajo.
    """
    import importlib

    from conftest import nombres_importados_por

    pedidos = nombres_importados_por("cargar_raw", modulo)
    assert pedidos is not None, "no se pudo leer scripts/cargar_raw.py"

    doble = importlib.import_module(f"secop_analytics.{modulo}")
    faltan = sorted(n for n in pedidos if not hasattr(doble, n))
    assert not faltan, (
        f"el doble de {modulo} no exporta {faltan} y cargar_raw.py los importa"
    )


@pytest.mark.parametrize("modulo", MODULOS_DOBLADOS)
def test_las_constantes_del_doble_valen_lo_mismo_que_las_reales(modulo):
    """`valores_de_enum` cubre enums y `parametros_de` cubre firmas. Las
    constantes de módulo no las cubría nadie, y ahí vive `ESTADOS_VIVOS`.

    Define los cuatro estados que barre el flujo 3 — los 2.825.685 contratos
    que todavía pueden cambiar. Si el original gana un quinto estado y el doble
    no, todos los tests pasan y el barrido real cubre otro universo.
    """
    import importlib

    from conftest import constantes_de

    reales = constantes_de(modulo)
    assert reales is not None, f"no se pudo leer {modulo}.py"

    doble = importlib.import_module(f"secop_analytics.{modulo}")
    discrepan = {
        nombre: (valor_real, getattr(doble, nombre))
        for nombre, valor_real in reales.items()
        if hasattr(doble, nombre) and getattr(doble, nombre) != valor_real
    }
    assert not discrepan, (
        f"el doble de {modulo} divergió: {discrepan} (real, doble)"
    )

# --------------------------------------------------------------------------
# El invariante de orden
# --------------------------------------------------------------------------

def test_el_indice_no_se_adelanta_al_archivo(orquestador, fuente, rutas, hoy):
    """El invariante de orden de D2, probado sobre el fallo real.

    La API muere en la página 2. Todo lo que quedó en el índice tiene que estar
    también en disco. Al revés —índice adelantado— la fila se pierde para
    siempre, porque la fuente se sobrescribe esta noche.
    """
    fuente.programar("vivos", [filas(10), filas(10, desde=10), filas(10, desde=20)])
    fuente.explotar_en_pagina = 2

    with pytest.raises(RuntimeError):
        orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)

    with IndiceHashes(rutas["ruta_indice"], verboso=False) as indice:
        en_indice = indice.conocidos

    directorio = (
        rutas["raiz"] / "flujo=refresco_de_vivos" / f"fecha_extraccion={hoy}" / "particion=completo"
    )
    manifiesto = json.loads((directorio / NOMBRE_MANIFIESTO).read_text())

    assert manifiesto["lineas_totales"] >= en_indice, (
        "el índice quedó adelantado al archivo: esas filas se perdieron"
    )


def test_una_caida_no_deja_la_particion_legible(orquestador, fuente, rutas, hoy):
    fuente.programar("vivos", [filas(10), filas(10, desde=10)])
    fuente.explotar_en_pagina = 2

    with pytest.raises(RuntimeError):
        orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)

    directorio = (
        rutas["raiz"] / "flujo=refresco_de_vivos" / f"fecha_extraccion={hoy}" / "particion=completo"
    )
    assert not (directorio / NOMBRE_COMPLETO).exists()


# --------------------------------------------------------------------------
# C5 y C6: el guardarraíl del flujo 3
# --------------------------------------------------------------------------

def test_el_flujo_3_rechaza_una_fecha_pasada(orquestador, fuente, rutas):
    """R1: pregunta por el estado actual, y ese estado ya se destruyó."""
    fuente.programar("vivos", [filas(5)])
    ayer = (orquestador.hoy() - timedelta(days=1)).isoformat()

    with pytest.raises(ValueError, match="backfill"):
        orquestador.cargar_vivos(None, None, fecha_extraccion=ayer, **rutas)


def test_el_flujo_3_acepta_la_fecha_colombiana(orquestador, fuente, rutas, hoy):
    """R2: `date.today()` en un sistema en UTC rechazaría esto cinco horas al día."""
    fuente.programar("vivos", [filas(5)])
    resultado = orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)
    assert resultado.escritas == 5


def test_hoy_usa_la_zona_de_colombia(orquestador):
    """La única definición de hoy del pipeline. No `date.today()`."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    assert orquestador.hoy() == datetime.now(ZoneInfo("America/Bogota")).date()


def test_los_flujos_1_y_2_si_admiten_fecha_pasada(orquestador, fuente, rutas):
    """Preguntan por ventanas de negocio: la fuente devuelve lo mismo siempre."""
    fuente.programar("nuevos", [filas(5)])
    viejo = (orquestador.hoy() - timedelta(days=90)).isoformat()

    resultado = orquestador.cargar_nuevos(
        date(2020, 1, 1), date(2020, 2, 1), fecha_extraccion=viejo, **rutas
    )
    assert resultado.escritas == 5


# --------------------------------------------------------------------------
# Nombres de partición
# --------------------------------------------------------------------------

def test_la_particion_dice_que_se_pidio(orquestador, fuente, rutas, hoy):
    fuente.programar("nuevos", [filas(3)])
    resultado = orquestador.cargar_nuevos(
        date(2026, 8, 20), date(2026, 8, 21), fecha_extraccion=hoy, **rutas
    )
    assert resultado.particion == "2026-08-20_a_2026-08-21"


def test_el_barrido_sin_particion_se_llama_completo(orquestador, fuente, rutas, hoy):
    fuente.programar("vivos", [filas(3)])
    resultado = orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)
    assert resultado.particion == "completo"


def test_dos_particiones_del_flujo_3_no_se_pisan(orquestador, fuente, rutas, hoy):
    """El caso que obligó a agregar el nivel `particion=` a la ruta."""
    fuente.programar("vivos", [filas(10)])
    primera = orquestador.cargar_vivos(
        date(2020, 1, 1), date(2020, 2, 1), fecha_extraccion=hoy, **rutas
    )

    fuente.programar("vivos", [filas(10, desde=500)])
    segunda = orquestador.cargar_vivos(
        date(2020, 2, 1), date(2020, 3, 1), fecha_extraccion=hoy, **rutas
    )

    assert primera.particion != segunda.particion
    assert primera.escritas == segunda.escritas == 10


# --------------------------------------------------------------------------
# Deduplicación
# --------------------------------------------------------------------------

def test_la_segunda_noche_sin_cambios_no_escribe_nada(orquestador, fuente, rutas, hoy):
    """D3: el ~99% de las filas no cambia entre noches."""
    fuente.programar("vivos", [filas(50)])
    primera = orquestador.cargar_vivos(
        date(2020, 1, 1), date(2020, 2, 1), fecha_extraccion=hoy, **rutas
    )
    assert primera.escritas == 50

    fuente.programar("vivos", [filas(50)])
    segunda = orquestador.cargar_vivos(
        date(2020, 2, 1), date(2020, 3, 1), fecha_extraccion=hoy, **rutas
    )
    assert segunda.recibidas == 50
    assert segunda.escritas == 0
    assert segunda.tasa_descarte == 1.0


def test_un_pago_nuevo_si_se_escribe(orquestador, fuente, rutas, hoy):
    """H9: si esto falla, los 735.809 contratos con pagos no tienen serie."""
    fuente.programar("vivos", [filas(10, pagado="0")])
    orquestador.cargar_vivos(date(2020, 1, 1), date(2020, 2, 1), fecha_extraccion=hoy, **rutas)

    fuente.programar("vivos", [filas(10, pagado="500000")])
    segunda = orquestador.cargar_vivos(
        date(2020, 2, 1), date(2020, 3, 1), fecha_extraccion=hoy, **rutas
    )
    assert segunda.escritas == 10


def test_el_solape_entre_flujos_no_duplica(orquestador, fuente, rutas, hoy):
    """Un contrato firmado y modificado el mismo día llega por dos caminos."""
    fuente.programar("nuevos", [filas(20)])
    fuente.programar("eventos", [filas(20)])

    primero = orquestador.cargar_nuevos(
        date(2026, 8, 20), date(2026, 8, 21), fecha_extraccion=hoy, **rutas
    )
    segundo = orquestador.cargar_eventos(
        date(2026, 8, 20), date(2026, 8, 21), fecha_extraccion=hoy, **rutas
    )

    assert primero.escritas == 20
    assert segundo.recibidas == 20
    assert segundo.escritas == 0


# --------------------------------------------------------------------------
# Idempotencia y reanudación
# --------------------------------------------------------------------------

def test_repetir_una_particion_completa_no_rehace_nada(orquestador, fuente, rutas, hoy):
    fuente.programar("vivos", [filas(10)])
    orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)

    fuente.programar("vivos", [filas(10)])
    repetida = orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)
    assert repetida.recibidas == 0


def test_lo_escrito_antes_de_la_caida_se_conserva(orquestador, fuente, rutas, hoy):
    """Reanudar tiene que ver los trozos que la corrida anterior alcanzó a cerrar."""
    fuente.programar("vivos", [filas(10), filas(10, desde=10), filas(10, desde=20)])
    fuente.explotar_en_pagina = 3

    with pytest.raises(RuntimeError):
        orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)

    directorio = (
        rutas["raiz"] / "flujo=refresco_de_vivos" / f"fecha_extraccion={hoy}" / "particion=completo"
    )
    manifiesto = json.loads((directorio / NOMBRE_MANIFIESTO).read_text())
    assert manifiesto["lineas_totales"] == 20
    assert manifiesto["cursor"] == "CO1.PCCNTR.19"


# --------------------------------------------------------------------------
# El canario
# --------------------------------------------------------------------------

def test_la_tasa_de_descarte_se_calcula(orquestador, fuente, rutas, hoy):
    """Una caída brusca no es actividad excepcional: es un cambio de esquema."""
    fuente.programar("vivos", [filas(100)])
    orquestador.cargar_vivos(date(2020, 1, 1), date(2020, 2, 1), fecha_extraccion=hoy, **rutas)

    fuente.programar("vivos", [filas(50) + filas(50, desde=1000)])
    segunda = orquestador.cargar_vivos(
        date(2020, 2, 1), date(2020, 3, 1), fecha_extraccion=hoy, **rutas
    )
    assert segunda.tasa_descarte == pytest.approx(0.5)


def test_sin_filas_la_tasa_no_divide_por_cero(orquestador, fuente, rutas, hoy):
    fuente.programar("vivos", [])
    resultado = orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)
    assert resultado.tasa_descarte == 0.0
    assert resultado.recibidas == 0


# --------------------------------------------------------------------------
# Ida y vuelta
# --------------------------------------------------------------------------

def test_lo_escrito_se_puede_releer_con_su_etiqueta(orquestador, fuente, rutas, hoy):
    fuente.programar("nuevos", [filas(7)])
    resultado = orquestador.cargar_nuevos(
        date(2026, 8, 20), date(2026, 8, 21), fecha_extraccion=hoy, **rutas
    )

    directorio = (
        rutas["raiz"]
        / "flujo=contratos_nuevos"
        / f"fecha_extraccion={hoy}"
        / f"particion={resultado.particion}"
    )
    observaciones = leer_particion(directorio)

    assert len(observaciones) == 7
    assert {o["flujo"] for o in observaciones} == {"contratos_nuevos"}
    assert {o["fecha_extraccion"] for o in observaciones} == {hoy}


# --------------------------------------------------------------------------
# Reanudación: el cursor guardado vuelve al flujo
# --------------------------------------------------------------------------

def test_al_retomar_se_le_pasa_el_cursor_al_flujo(orquestador, fuente, rutas, hoy):
    """El circuito completo: se guarda el cursor, se relee, y se usa.

    Sin esto, reanudar significaba volver a bajar la ventana entera. La
    deduplicación evitaba escribir de más, pero las llamadas a la API se
    repetían todas — que es justamente el costo que los trozos existían para
    evitar.
    """
    fuente.programar("vivos", [filas(10), filas(10, desde=10), filas(10, desde=20)])
    fuente.explotar_en_pagina = 3

    with pytest.raises(RuntimeError):
        orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)

    primera_llamada = fuente.llamadas[-1]
    assert primera_llamada[2].get("desde_cursor") is None, "arrancó con cursor"

    # Segundo intento: la partición quedó a medias con su cursor anotado.
    fuente.programar("vivos", [filas(10, desde=20)])
    fuente.explotar_en_pagina = None
    orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)

    segunda_llamada = fuente.llamadas[-1]
    assert segunda_llamada[2].get("desde_cursor") == "CO1.PCCNTR.19", (
        "el flujo arrancó de cero: el cursor del manifiesto no llegó"
    )


def test_sin_manifiesto_previo_el_cursor_va_en_none(orquestador, fuente, rutas, hoy):
    fuente.programar("nuevos", [filas(5)])
    orquestador.cargar_nuevos(
        date(2026, 8, 20), date(2026, 8, 21), fecha_extraccion=hoy, **rutas
    )
    assert fuente.llamadas[-1][2].get("desde_cursor") is None