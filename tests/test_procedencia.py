"""`ingestas_previas()`: qué corte de la fuente vio cada partición.

Es la base de D11. Lo que se prueba acá es la pregunta, no el guardarraíl: si
existe una partición completa, del mismo flujo y la misma partición, cuyo
manifiesto diga este corte, con cualquier `fecha_extraccion`.

Cada condición de esa frase descarta un modo de fallo distinto, y cada test de
acá corresponde a uno. Los dos que más importan son
`test_bloquea_el_mismo_corte_en_otra_fecha` —el caso del 26 de agosto, que hoy
no falla y no avisa— y `test_no_bloquea_una_particion_incompleta`, que es el que
impide que el guardarraíl convierta la reanudación de I5 en un callejón.

A diferencia de `test_cargar_raw.py`, esto corre contra el módulo real:
`conftest.py` eclipsa `paginacion` y `flujos`, no `escritura`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from secop_analytics.escritura import (
    NOMBRE_COMPLETO,
    NOMBRE_MANIFIESTO,
    ParticionRaw,
    ingestas_previas,
)

CORTE_DEL_25 = "2026-08-25T09:05:54.277Z"
CORTE_DEL_20 = "2026-08-20T09:41:20.358Z"


def particion_en_disco(
    base: Path,
    *,
    flujo: str = "refresco_de_vivos",
    fecha_extraccion: str,
    particion: str = "2020-01",
    corte: str | None = None,
    completa: bool = True,
) -> Path:
    """Fabrica una partición como la que deja `ParticionRaw`.

    Se escribe a mano y no con `ParticionRaw` a propósito: los casos que hacen
    falta incluyen manifiestos sin el campo del corte —los anteriores a D10— y
    manifiestos corruptos, que la clase no produce.
    """
    directorio = (
        base
        / f"flujo={flujo}"
        / f"fecha_extraccion={fecha_extraccion}"
        / f"particion={particion}"
    )
    directorio.mkdir(parents=True)

    manifiesto: dict[str, object] = {
        "flujo": flujo,
        "fecha_extraccion": fecha_extraccion,
        "particion": particion,
        "trozos_cerrados": 1,
        "lineas_totales": 10,
        "cursor": "CO1.PCCNTR.9",
    }
    if corte is not None:
        manifiesto["corte_al_iniciar"] = corte
    (directorio / NOMBRE_MANIFIESTO).write_text(
        json.dumps(manifiesto), encoding="utf-8"
    )

    if completa:
        (directorio / NOMBRE_COMPLETO).write_text("{}", encoding="utf-8")
    return directorio


# -- el caso que motivó todo -----------------------------------------------


def test_bloquea_el_mismo_corte_en_otra_fecha(tmp_path):
    """El caso del 26 de agosto: la fuente no regeneró y se corrió igual.

    Es el que el guardarraíl de `_solo_lectura` NO cubre, porque la ruta cambia
    con `fecha_extraccion` y el directorio es otro. Sin esto, la corrida baja
    2,8 millones de filas, descarta todo y escribe una partición vacía.
    """
    particion_en_disco(tmp_path, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25)

    previas = ingestas_previas(
        tmp_path,
        flujo="refresco_de_vivos",
        particion="2020-01",
        corte=CORTE_DEL_25,
    )

    assert previas.ya_ingerido is not None
    assert previas.ya_ingerido.fecha_extraccion == "2026-08-25"


def test_deja_pasar_un_corte_nuevo(tmp_path):
    """Con estado nuevo se corre, que es el caso normal."""
    particion_en_disco(tmp_path, fecha_extraccion="2026-08-20", corte=CORTE_DEL_20)

    previas = ingestas_previas(
        tmp_path,
        flujo="refresco_de_vivos",
        particion="2020-01",
        corte=CORTE_DEL_25,
    )

    assert previas.ya_ingerido is None
    assert previas.ultima is not None
    assert previas.ultima.corte == CORTE_DEL_20


# -- las tres condiciones de la pregunta -----------------------------------


def test_no_bloquea_una_particion_incompleta(tmp_path):
    """Sin `_COMPLETO` es trabajo a medias, y retomarlo es lo que I5 permite.

    Si esto bloqueara, una muerte dura a mitad de barrido dejaría la partición
    imposible de retomar contra el mismo corte — que es justamente cuando hay
    que retomarla.
    """
    particion_en_disco(
        tmp_path, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25, completa=False
    )

    previas = ingestas_previas(
        tmp_path,
        flujo="refresco_de_vivos",
        particion="2020-01",
        corte=CORTE_DEL_25,
    )

    assert previas.ya_ingerido is None
    assert previas.ultima is None


def test_no_bloquea_otra_particion_del_mismo_barrido(tmp_path):
    """El barrido partido: si terminaron tres de cuatro, la cuarta corre.

    Cada unidad de trabajo se pregunta por sí misma. Preguntar por el corte
    entero convertiría un barrido paralelo a medio terminar en uno que no se
    puede terminar.
    """
    for rango in ("2020-01", "2020-02", "2020-03"):
        particion_en_disco(
            tmp_path,
            fecha_extraccion="2026-08-25",
            particion=rango,
            corte=CORTE_DEL_25,
        )

    previas = ingestas_previas(
        tmp_path,
        flujo="refresco_de_vivos",
        particion="2020-04",
        corte=CORTE_DEL_25,
    )

    assert previas.ya_ingerido is None


def test_no_bloquea_otro_flujo(tmp_path):
    """Los flujos 1 y 2 anotan el corte pero no comparten unidad de trabajo."""
    particion_en_disco(
        tmp_path,
        flujo="contratos_nuevos",
        fecha_extraccion="2026-08-25",
        corte=CORTE_DEL_25,
    )

    previas = ingestas_previas(
        tmp_path,
        flujo="refresco_de_vivos",
        particion="2020-01",
        corte=CORTE_DEL_25,
    )

    assert previas.ya_ingerido is None


# -- lo anterior a D10 ------------------------------------------------------


def test_una_particion_sin_corte_anotado_no_bloquea(tmp_path):
    """Las particiones anteriores a D10 son desconocidas, no coincidentes.

    Tratarlas como si coincidieran bloquearía corridas legítimas sobre todo lo
    que ya está en disco: el error que falta.
    """
    particion_en_disco(tmp_path, fecha_extraccion="2026-08-23", corte=None)

    previas = ingestas_previas(
        tmp_path,
        flujo="refresco_de_vivos",
        particion="2020-01",
        corte=CORTE_DEL_25,
    )

    assert previas.ya_ingerido is None
    assert len(previas.sin_corte_anotado) == 1
    assert previas.sin_corte_anotado[0].fecha_extraccion == "2026-08-23"


def test_un_manifiesto_ilegible_es_desconocido_y_no_rompe(tmp_path):
    """Un manifiesto corrupto no puede hacer fallar la corrida.

    Es el mismo criterio que `_retomar()`: se sigue, sin dar por sabido nada.
    """
    directorio = particion_en_disco(
        tmp_path, fecha_extraccion="2026-08-23", corte=CORTE_DEL_25
    )
    (directorio / NOMBRE_MANIFIESTO).write_text("{no es json", encoding="utf-8")

    previas = ingestas_previas(
        tmp_path,
        flujo="refresco_de_vivos",
        particion="2020-01",
        corte=CORTE_DEL_25,
    )

    assert previas.ya_ingerido is None
    assert len(previas.sin_corte_anotado) == 1


# -- bordes -----------------------------------------------------------------


def test_sin_nada_en_disco(tmp_path):
    """La primera corrida de una partición. Ni raíz existe todavía."""
    previas = ingestas_previas(
        tmp_path / "no-existe",
        flujo="refresco_de_vivos",
        particion="2020-01",
        corte=CORTE_DEL_25,
    )

    assert previas.ya_ingerido is None
    assert previas.ultima is None
    assert previas.sin_corte_anotado == ()


def test_ultima_es_la_de_fecha_mayor(tmp_path):
    """`ultima` alimenta el mensaje: contra qué se está comparando.

    El orden es por `fecha_extraccion` y no por el del sistema de archivos, que
    no está garantizado.
    """
    particion_en_disco(tmp_path, fecha_extraccion="2026-08-20", corte=CORTE_DEL_20)
    particion_en_disco(tmp_path, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25)
    particion_en_disco(tmp_path, fecha_extraccion="2026-08-18", corte="2026-08-18T09:22:15.735Z")

    previas = ingestas_previas(
        tmp_path,
        flujo="refresco_de_vivos",
        particion="2020-01",
        corte="2026-08-28T09:00:00.000Z",
    )

    assert previas.ultima is not None
    assert previas.ultima.fecha_extraccion == "2026-08-25"


def test_sin_corte_no_se_puede_contestar(tmp_path):
    """Un corte vacío haría que `p.corte == corte` empatara con las viejas."""
    with pytest.raises(ValueError, match="corte"):
        ingestas_previas(
            tmp_path, flujo="refresco_de_vivos", particion="2020-01", corte=""
        )


# ==========================================================================
# D10: los tres campos en el manifiesto
# ==========================================================================


def manifiesto_de(directorio: Path) -> dict:
    return json.loads((directorio / NOMBRE_MANIFIESTO).read_text(encoding="utf-8"))


def test_el_manifiesto_lleva_los_dos_extremos_del_intervalo(tmp_path):
    """Sin los dos extremos, cuánto negocio cubre la partición no se sabe.

    Y no se recupera después: el corte anterior ya lo destruyó la fuente. Es
    exactamente lo que pasó con la corrida del 25 de agosto.
    """
    with ParticionRaw(
        tmp_path,
        flujo="refresco_de_vivos",
        fecha_extraccion="2026-08-28",
        particion="2020-01",
        corte_al_iniciar=CORTE_DEL_25,
        corte_anterior=CORTE_DEL_20,
        verboso=False,
    ) as destino:
        destino.escribir(b'{"a":1}')
        destino.completar(corte_al_terminar=CORTE_DEL_25)

    manifiesto = manifiesto_de(destino.directorio)
    assert manifiesto["corte_anterior"] == CORTE_DEL_20
    assert manifiesto["corte_al_iniciar"] == CORTE_DEL_25
    assert manifiesto["corte_al_terminar"] == CORTE_DEL_25


def test_sin_corte_anterior_el_intervalo_queda_abierto_por_la_izquierda(tmp_path):
    """Primera corrida de una partición, o anterior a D10. Se anota el nulo.

    Decirlo explícitamente vale más que omitir la clave: un nulo escrito es
    "no se sabe", una clave ausente es indistinguible de un manifiesto viejo.
    """
    with ParticionRaw(
        tmp_path,
        flujo="refresco_de_vivos",
        fecha_extraccion="2026-08-28",
        particion="2020-01",
        corte_al_iniciar=CORTE_DEL_25,
        verboso=False,
    ) as destino:
        destino.escribir(b'{"a":1}')
        destino.completar(corte_al_terminar=CORTE_DEL_25)

    manifiesto = manifiesto_de(destino.directorio)
    assert "corte_anterior" in manifiesto
    assert manifiesto["corte_anterior"] is None


def test_una_particion_a_caballo_queda_registrada_y_legible(tmp_path):
    """La fuente regeneró durante la corrida: los dos cortes difieren.

    Se anota y NO se deja ilegible: qué hacer con una partición a caballo está
    sin decidir, y negarle `_COMPLETO` sería tomar esa decisión de costado.
    """
    with ParticionRaw(
        tmp_path,
        flujo="refresco_de_vivos",
        fecha_extraccion="2026-08-28",
        particion="2020-01",
        corte_al_iniciar=CORTE_DEL_20,
        verboso=False,
    ) as destino:
        destino.escribir(b'{"a":1}')
        destino.completar(corte_al_terminar=CORTE_DEL_25)

    manifiesto = manifiesto_de(destino.directorio)
    assert manifiesto["corte_al_iniciar"] != manifiesto["corte_al_terminar"]
    assert destino.esta_completa


def test_un_corte_no_confiable_se_escribe_igual_y_queda_marcado(tmp_path):
    """`min != max`: o la fuente se estaba regenerando, o H2 se cayó.

    Este módulo no juzga cuál: anota el valor y la marca. Descartar la
    observación sería perder algo que no vuelve.
    """
    with ParticionRaw(
        tmp_path,
        flujo="refresco_de_vivos",
        fecha_extraccion="2026-08-28",
        particion="2020-01",
        corte_al_iniciar=CORTE_DEL_25,
        corte_confiable=False,
        verboso=False,
    ) as destino:
        destino.escribir(b'{"a":1}')
        destino.completar(corte_al_terminar=CORTE_DEL_25)

    assert manifiesto_de(destino.directorio)["corte_confiable"] is False


def test_el_manifiesto_del_corte_lo_lee_ingestas_previas(tmp_path):
    """Las dos mitades encajan: lo que D10 escribe es lo que D11 lee.

    Se prueba junto a propósito. Probadas por separado, un cambio en el nombre
    del campo pasaría las dos y rompería el guardarraíl.
    """
    with ParticionRaw(
        tmp_path,
        flujo="refresco_de_vivos",
        fecha_extraccion="2026-08-28",
        particion="2020-01",
        corte_al_iniciar=CORTE_DEL_25,
        verboso=False,
    ) as destino:
        destino.escribir(b'{"a":1}')
        destino.completar(corte_al_terminar=CORTE_DEL_25)

    previas = ingestas_previas(
        tmp_path, flujo="refresco_de_vivos", particion="2020-01", corte=CORTE_DEL_25
    )
    assert previas.ya_ingerido is not None
    assert previas.ya_ingerido.directorio == destino.directorio


# ==========================================================================
# D10: reanudar contra otro corte
# ==========================================================================


def test_no_retoma_progreso_de_otro_corte(tmp_path):
    """El caso que `fecha_extraccion` no protege: misma fecha, otro corte.

    Una corrida que arranca a las 04:00 y cruza la ventana de regeneración
    deja trozos de un estado y sigue con otro. Retomarlos mezclaría los dos en
    un directorio, y el manifiesto se reescribiría con el corte nuevo: el viejo
    se perdería sin dejar rastro.
    """
    argumentos = dict(
        flujo="refresco_de_vivos",
        fecha_extraccion="2026-08-28",
        particion="2020-01",
        verboso=False,
        lineas_por_trozo=1,
    )

    with ParticionRaw(tmp_path, corte_al_iniciar=CORTE_DEL_20, **argumentos) as primera:
        primera.escribir(b'{"a":1}')
        primera.punto_de_control(cursor="CO1.PCCNTR.5")

    assert manifiesto_de(primera.directorio)["cursor"] == "CO1.PCCNTR.5"

    with ParticionRaw(tmp_path, corte_al_iniciar=CORTE_DEL_25, **argumentos) as segunda:
        assert segunda.cursor is None, "retomó el cursor de otro corte"
        assert segunda.lineas_escritas == 0


def test_si_retoma_el_progreso_del_mismo_corte(tmp_path):
    """El control del anterior: con el mismo corte, la reanudación de I5 sigue
    funcionando. Sin este test, negarse a retomar siempre también pasaría."""
    argumentos = dict(
        flujo="refresco_de_vivos",
        fecha_extraccion="2026-08-28",
        particion="2020-01",
        verboso=False,
        lineas_por_trozo=1,
    )

    with ParticionRaw(tmp_path, corte_al_iniciar=CORTE_DEL_25, **argumentos) as primera:
        primera.escribir(b'{"a":1}')
        primera.punto_de_control(cursor="CO1.PCCNTR.5")

    with ParticionRaw(tmp_path, corte_al_iniciar=CORTE_DEL_25, **argumentos) as segunda:
        assert segunda.cursor == "CO1.PCCNTR.5"


def test_retoma_lo_anterior_a_d10_sin_corte_anotado(tmp_path):
    """Migración: el progreso viejo no tiene corte. Se retoma igual.

    Negarse dejaría sin retomar todo lo que ya está en disco, que es el error
    que falta. Desconocido no es distinto.
    """
    directorio = particion_en_disco(
        tmp_path, fecha_extraccion="2026-08-28", corte=None, completa=False
    )
    manifiesto = json.loads((directorio / NOMBRE_MANIFIESTO).read_text())
    manifiesto["cursor"] = "CO1.PCCNTR.5"
    (directorio / NOMBRE_MANIFIESTO).write_text(json.dumps(manifiesto))

    with ParticionRaw(
        tmp_path,
        flujo="refresco_de_vivos",
        fecha_extraccion="2026-08-28",
        particion="2020-01",
        corte_al_iniciar=CORTE_DEL_25,
        verboso=False,
    ) as destino:
        assert destino.cursor == "CO1.PCCNTR.5"