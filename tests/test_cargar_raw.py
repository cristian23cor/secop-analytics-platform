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

    Un parámetro nuevo (o uno mal escrito) pasa sin que nada falle. Cuando se
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
    vez salió barato porque el fallo fue ruidoso; el modo peligroso (el doble
    exporta el nombre con otro valor) lo cubre el test de abajo.
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

    Define los cuatro estados que barre el flujo 3: los 2.825.685 contratos
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
    también en disco. Al revés (índice adelantado) la fila se pierde para
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
    repetían todas, que es justamente el costo que los trozos existían para
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

# --------------------------------------------------------------------------
# El canario del descarte
#
# Vigila que la deduplicacion siga funcionando, y su modo de fallo es el que
# no produce ningun error: si la canonicalizacion se rompe, ningun hash calza,
# el cargador escribe los 2,8 millones de filas y la corrida termina "bien".
#
# Estos tests construyen el `Resultado` a mano en vez de correr el pipeline,
# porque lo que se prueba es la decision y las cifras que la disparan son las
# de corridas reales de cincuenta minutos que no se pueden reproducir aca.
# --------------------------------------------------------------------------

# Las tres corridas reales del flujo 3, con sus cifras medidas. Las tres son
# SANAS: en ninguna debe cantar el canario.
CORRIDAS_SANAS = [
    pytest.param(2_835_895, 2_824_446, 11_449, id="barrido-completo-23-08"),
    pytest.param(2_840_337, 58_971, 2_834_320, id="incremental-25-08"),
    pytest.param(2_840_337, 0, 2_840_337, id="intervalo-nulo-28-08"),
]


def resultado_del_flujo_3(recibidas, escritas, conocidas):
    from cargar_raw import Resultado

    return Resultado(
        flujo="refresco_de_vivos",
        particion="completo",
        recibidas=recibidas,
        escritas=escritas,
        conocidas=conocidas,
    )


def canta(recibidas, escritas, conocidas) -> bool:
    from cargar_raw import _advertencia_de_descarte

    r = resultado_del_flujo_3(recibidas, escritas, conocidas)
    return _advertencia_de_descarte(r) is not None


@pytest.mark.parametrize(("recibidas", "escritas", "conocidas"), CORRIDAS_SANAS)
def test_ninguna_corrida_real_hace_cantar_al_canario(recibidas, escritas, conocidas):
    """Las tres corridas del flujo 3 que existen son sanas.

    **El barrido completo del 23/08 es el que importa**, y es el que falla
    contra el codigo viejo: descarto el 0,4% de lo RECIBIDO, porque casi todo
    era nuevo y habia que escribirlo, y con el denominador global el canario
    cantaba "descarte del 0,4%, deberia rondar el 99%".

    Estaba perfecto: de las 11.449 filas que el indice ya conocia descarto las
    11.449. La misma corrida se leia como catastrofe o como exito segun que
    denominador se mirara.

    Una alerta que canta cuando todo esta bien ensena a ignorarla, que es peor
    que no tenerla.
    """
    assert not canta(recibidas, escritas, conocidas)


def test_la_tasa_sobre_conocidas_no_es_la_global():
    """El barrido completo, con los dos denominadores al lado.

    Si estos dos numeros fueran parecidos, todo lo anterior seria una discusion
    sin consecuencias. Se separan por 99,6 puntos.
    """
    r = resultado_del_flujo_3(2_835_895, 2_824_446, 11_449)
    assert r.tasa_descarte == pytest.approx(0.004, abs=0.001)
    assert r.tasa_sobre_conocidas == pytest.approx(1.0)


def test_sin_conocidas_la_tasa_es_None_y_no_cero():
    """Cero seria "todo lo conocido cambio"; None es "no hay con que comparar".

    Confundir esas dos cosas es exactamente el error que el arreglo corrige, y
    devolver 0.0 lo reintroduciria por otro lado: un cero comparado contra el
    umbral hace cantar al canario en cada particion nueva.
    """
    r = resultado_del_flujo_3(5_000, 5_000, 0)
    assert r.tasa_sobre_conocidas is None


# La rotura que el canario existe para detectar: la canonicalizacion cambia
# (una clave que se ordena distinto, un separador, una columna nueva) y los
# hashes viejos dejan de calzar, asi que se escribe lo que no cambio.
@pytest.mark.parametrize("escritas", [2_840_337, 1_420_168, 426_050],
                         ids=["rotura-total", "rotura-50", "rotura-15"])
def test_una_rotura_de_la_canonicalizacion_hace_cantar_al_canario(escritas):
    """Con el umbral en 0,90 se atrapa toda rotura de mas del 10% de los hashes."""
    assert canta(2_840_337, escritas, 2_834_320)


def test_una_rotura_chica_se_le_escapa_al_canario():
    """Y esto es deliberado, no un defecto. Es el limite del umbral elegido.

    Una rotura que invalide el 5% de los hashes deja la tasa en 95,2%, por
    encima del 0,90. El canario no la ve.

    El umbral se eligio con las tres anclas medidas (98,13% y 100,00% dos
    veces) y deja ocho puntos de margen. Apretarlo mas atraparia roturas mas
    chicas y a cambio cantaria el dia que el intervalo entre cortes se alargue,
    porque entonces cambian mas contratos de verdad y la tasa baja sin que nada
    este roto. Al 31/08/2026 la fuente lleva seis dias congelada, asi que la
    proxima corrida sana va a tener el intervalo mas largo observado.

    Este test existe para que ese limite este escrito y no se descubra el dia
    que haga falta. Si algun dia se decide apretar el umbral, este test falla y
    obliga a actualizar la cifra a conciencia.
    """
    assert not canta(2_840_337, 142_016, 2_834_320)


def test_el_canario_no_mira_los_flujos_1_y_2():
    """En ellos el descarte bajo es lo correcto: el flujo 1 trae contratos que
    el indice nunca vio y el flujo 2 trae contratos a los que les paso algo.

    Sin esta exclusion la advertencia saldria en las dos corridas diarias,
    todas las noches, sin que nada estuviera mal.
    """
    from cargar_raw import Resultado, _advertencia_de_descarte

    for flujo in ("contratos_nuevos", "eventos_contractuales"):
        r = Resultado(flujo=flujo, particion="x", recibidas=5_000,
                      escritas=5_000, conocidas=4_000)
        assert _advertencia_de_descarte(r) is None, flujo


def test_una_muestra_chica_no_hace_cantar_al_canario():
    """Bajo mil filas la tasa es ruido."""
    assert not canta(500, 500, 400)


def test_el_mensaje_nombra_la_tasa_que_decidio():
    """Quien lea la alerta a las tres de la manana tiene que ver el numero que
    la disparo, no otro. El mensaje viejo mostraba la tasa global, que era
    justamente la que no habia decidido nada."""
    from cargar_raw import _advertencia_de_descarte

    aviso = _advertencia_de_descarte(
        resultado_del_flujo_3(2_840_337, 2_840_337, 2_834_320)
    )
    assert aviso is not None
    assert "sobre las filas ya conocidas" in aviso
    assert "0.0%" in aviso or "0,0%" in aviso
