"""D11 en el orquestador: correr o no según el corte de la fuente.

`test_procedencia.py` prueba las piezas —leer los manifiestos y escribirlos—
contra los módulos reales. Acá se prueba lo que el orquestador **decide** con
ellas, que es la mitad que necesita los dobles.

El caso que motivó todo es `test_no_rehace_un_corte_ya_ingerido`: hasta hoy,
correr dos veces entre dos regeneraciones bajaba 2,8 millones de filas, las
descartaba todas y escribía una partición vacía, sin fallar y sin avisar. Con la
fuente saltando días (H34) eso dejó de ser un caso raro.

Los otros cubren el borde de cada guardarraíl, que es donde se rompen: que no
bloquee un corte nuevo, que no bloquee otra partición del mismo barrido, y que
la bandera de forzado funcione. Un guardarraíl sin esos tres es indistinguible
de uno que bloquea siempre.
"""

from __future__ import annotations

import json

import pytest

from conftest import Corte, filas

CORTE_DEL_25 = "2026-08-25T09:05:54.277Z"
CORTE_DEL_28 = "2026-08-28T09:51:29.013Z"


def correr(orquestador, rutas, hoy, *, corte, forzar=False, particion=None):
    """Una corrida del flujo 3 contra un corte dado."""
    desde = hasta = None
    if particion is not None:
        desde, hasta = particion
    return orquestador.cargar_vivos(
        desde,
        hasta,
        fecha_extraccion=hoy,
        corte_de_la_fuente=Corte(corte, corte),
        forzar_corte_repetido=forzar,
        **rutas,
    )


# -- el caso que motivó todo ------------------------------------------------
#
# Todos fabrican la ingesta previa EN DISCO, con otra `fecha_extraccion`. Es
# deliberado y es el punto entero de D11: dentro del mismo día el directorio es
# el mismo y `_solo_lectura` ya bloqueaba. Lo que no estaba cubierto es correr
# hoy y mañana contra el mismo estado de la fuente, que con H34 dejó de ser un
# caso raro. Un test que reusara la fecha de hoy pasaría por el guardarraíl
# viejo sin ejercitar el nuevo.


def ingesta_previa_en_disco(rutas, *, fecha_extraccion, corte, particion="completo"):
    """Una partición completa de otro día, como la dejaría una corrida real."""
    directorio = (
        rutas["raiz"]
        / "flujo=refresco_de_vivos"
        / f"fecha_extraccion={fecha_extraccion}"
        / f"particion={particion}"
    )
    directorio.mkdir(parents=True)
    (directorio / "_manifiesto.json").write_text(
        json.dumps(
            {
                "flujo": "refresco_de_vivos",
                "fecha_extraccion": fecha_extraccion,
                "particion": particion,
                "corte_al_iniciar": corte,
                "trozos_cerrados": 1,
                "lineas_totales": 3,
                "cursor": "CO1.PCCNTR.2",
            }
        ),
        encoding="utf-8",
    )
    (directorio / "_COMPLETO").write_text("{}", encoding="utf-8")
    return directorio


def test_no_rehace_un_corte_ya_ingerido(orquestador, fuente, rutas, hoy):
    """El caso del 26 de agosto: la fuente no regeneró y se corrió igual.

    Sin esto, la corrida baja 2,8 millones de filas, las descarta todas por el
    índice y escribe una partición vacía. No falla y no avisa.

    La aserción sobre `fuente.llamadas` es la que importa: el guardarraíl tiene
    que cortar ANTES de bajar una sola página. Bloquear después sería el mismo
    resultado y cincuenta minutos de diferencia.
    """
    ingesta_previa_en_disco(rutas, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25)
    fuente.programar("vivos", [filas(3)])

    with pytest.raises(orquestador.CorteYaIngerido):
        correr(orquestador, rutas, hoy, corte=CORTE_DEL_25)

    assert fuente.llamadas == [], "bajó páginas antes de decidir"


# -- los bordes: sin ellos, bloquear siempre también pasaría ----------------


def test_un_corte_nuevo_si_corre(orquestador, fuente, rutas, hoy):
    ingesta_previa_en_disco(rutas, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25)
    fuente.programar("vivos", [filas(3)])

    resultado = correr(orquestador, rutas, hoy, corte=CORTE_DEL_28)

    assert resultado.recibidas == 3


def test_otra_particion_del_mismo_barrido_si_corre(orquestador, fuente, rutas, hoy):
    """Barrido partido: que termine una no bloquea a las demás."""
    from datetime import date

    ingesta_previa_en_disco(
        rutas,
        fecha_extraccion="2026-08-25",
        corte=CORTE_DEL_25,
        particion="2020-01-01_a_2020-02-01",
    )
    fuente.programar("vivos", [filas(3)])

    resultado = correr(
        orquestador, rutas, hoy, corte=CORTE_DEL_25,
        particion=(date(2020, 2, 1), date(2020, 3, 1)),
    )

    assert resultado.recibidas == 3


def test_la_bandera_de_forzado_deja_correr(orquestador, fuente, rutas, hoy):
    """Un guardarraíl que no se puede saltar, en un pipeline que corre a mano,
    es un pipeline que un día no corre."""
    ingesta_previa_en_disco(rutas, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25)
    fuente.programar("vivos", [filas(3)])

    resultado = correr(orquestador, rutas, hoy, corte=CORTE_DEL_25, forzar=True)

    assert resultado.recibidas == 3


def test_sin_corte_no_bloquea(orquestador, fuente, rutas, hoy):
    """Quien llama sin haber consultado la fuente no queda bloqueado.

    Es la regla de migración: desconocido no bloquea. Cubre a los tests que ya
    existían y a cualquier script que llame a estas funciones sin pasar por
    `main()`.
    """
    ingesta_previa_en_disco(rutas, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25)
    fuente.programar("vivos", [filas(3)])

    resultado = orquestador.cargar_vivos(None, None, fecha_extraccion=hoy, **rutas)

    assert resultado.recibidas == 3


def test_una_ingesta_previa_sin_corte_anotado_no_bloquea(orquestador, fuente, rutas, hoy):
    """Lo anterior a D10 es desconocido, no coincidente. Bloquear ahí frenaría
    corridas legítimas sobre todo lo que ya está en disco."""
    directorio = ingesta_previa_en_disco(
        rutas, fecha_extraccion="2026-08-23", corte=CORTE_DEL_25
    )
    manifiesto = json.loads((directorio / "_manifiesto.json").read_text())
    del manifiesto["corte_al_iniciar"]
    (directorio / "_manifiesto.json").write_text(json.dumps(manifiesto))
    fuente.programar("vivos", [filas(3)])

    resultado = correr(orquestador, rutas, hoy, corte=CORTE_DEL_25)

    assert resultado.recibidas == 3


def test_los_flujos_1_y_2_no_tienen_guardarrail_de_corte(orquestador, fuente, rutas):
    """El flujo 3 pregunta por el estado vivo; los otros por ventanas de fecha
    de negocio, que son reproducibles hacia atrás (R1). Un corte repetido ahí no
    es el mismo tipo de error."""
    from datetime import date

    fuente.programar("nuevos", [filas(3)])
    orquestador.cargar_nuevos(
        date(2024, 2, 6), date(2024, 2, 7),
        fecha_extraccion="2024-02-07",
        corte_de_la_fuente=Corte(CORTE_DEL_25, CORTE_DEL_25),
        **rutas,
    )

    fuente.programar("nuevos", [filas(3)])
    resultado = orquestador.cargar_nuevos(
        date(2024, 2, 6), date(2024, 2, 8),
        fecha_extraccion="2024-02-07",
        corte_de_la_fuente=Corte(CORTE_DEL_25, CORTE_DEL_25),
        **rutas,
    )

    assert resultado.recibidas == 3


# -- D10 de punta a punta ---------------------------------------------------


def manifiesto_de(rutas, hoy, *, flujo="refresco_de_vivos", particion="completo"):
    directorio = (
        rutas["raiz"]
        / f"flujo={flujo}"
        / f"fecha_extraccion={hoy}"
        / f"particion={particion}"
    )
    return json.loads((directorio / "_manifiesto.json").read_text(encoding="utf-8"))


def test_la_corrida_anota_el_corte_en_el_manifiesto(orquestador, fuente, rutas, hoy):
    fuente.programar("vivos", [filas(3)])
    fuente.programar_cortes(CORTE_DEL_25)

    correr(orquestador, rutas, hoy, corte=CORTE_DEL_25)

    manifiesto = manifiesto_de(rutas, hoy)
    assert manifiesto["corte_al_iniciar"] == CORTE_DEL_25
    assert manifiesto["corte_al_terminar"] == CORTE_DEL_25
    assert manifiesto["corte_anterior"] is None


def test_la_segunda_corrida_anota_el_corte_anterior(orquestador, fuente, rutas, hoy):
    """Los dos extremos del intervalo, que es lo que faltó en la corrida del 25
    y ya no se puede recuperar.

    Sale de la misma consulta a raw que alimenta el guardarraíl: `corte_anterior`
    es el corte de la última ingesta completa de esta partición, así que no se
    busca dos veces.
    """
    ingesta_previa_en_disco(rutas, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25)
    fuente.programar("vivos", [filas(3)])
    fuente.programar_cortes(CORTE_DEL_28)

    correr(orquestador, rutas, hoy, corte=CORTE_DEL_28)

    manifiesto = manifiesto_de(rutas, hoy)
    assert manifiesto["corte_anterior"] == CORTE_DEL_25
    assert manifiesto["corte_al_iniciar"] == CORTE_DEL_28


def test_la_particion_a_caballo_queda_registrada(orquestador, fuente, rutas, hoy):
    """La fuente regeneró durante la corrida: 50 minutos cruzan una ventana de
    35. Sin la segunda consulta esto sería invisible."""
    fuente.programar("vivos", [filas(3)])
    fuente.programar_cortes(CORTE_DEL_28)  # la del final devuelve otro valor

    correr(orquestador, rutas, hoy, corte=CORTE_DEL_25)

    manifiesto = manifiesto_de(rutas, hoy)
    assert manifiesto["corte_al_iniciar"] == CORTE_DEL_25
    assert manifiesto["corte_al_terminar"] == CORTE_DEL_28


def test_un_fallo_al_releer_el_corte_no_cuesta_la_particion(
    orquestador, fuente, rutas, hoy
):
    """Al terminar, la asimetría se da vuelta: perder la marca es el error que
    sobra; perder `_COMPLETO` de un barrido de 50 minutos es el que falta."""
    fuente.programar("vivos", [filas(3)])
    fuente.explotar_el_corte = RuntimeError("429 desde el otro lado")

    correr(orquestador, rutas, hoy, corte=CORTE_DEL_25)

    manifiesto = manifiesto_de(rutas, hoy)
    assert manifiesto["corte_al_terminar"] is None
    assert manifiesto["corte_al_iniciar"] == CORTE_DEL_25
    directorio = (
        rutas["raiz"] / "flujo=refresco_de_vivos"
        / f"fecha_extraccion={hoy}" / "particion=completo"
    )
    assert (directorio / "_COMPLETO").is_file(), "se perdió el barrido entero"


def test_un_corte_no_confiable_se_escribe_marcado(orquestador, fuente, rutas, hoy):
    """`min != max`. No se aborta: la observación no vuelve a estar disponible."""
    fuente.programar("vivos", [filas(3)])
    resultado = orquestador.cargar_vivos(
        None, None, fecha_extraccion=hoy,
        corte_de_la_fuente=Corte(CORTE_DEL_25, CORTE_DEL_28),
        **rutas,
    )

    assert resultado.recibidas == 3
    assert manifiesto_de(rutas, hoy)["corte_confiable"] is False


def test_los_tres_flujos_anotan_el_corte(orquestador, fuente, rutas):
    """Se escribe en los tres, se lee en uno. La asimetría es deliberada."""
    from datetime import date

    fuente.programar("nuevos", [filas(3)])
    orquestador.cargar_nuevos(
        date(2024, 2, 6), date(2024, 2, 7),
        fecha_extraccion="2024-02-07",
        corte_de_la_fuente=Corte(CORTE_DEL_25, CORTE_DEL_25),
        **rutas,
    )

    manifiesto = manifiesto_de(
        rutas, "2024-02-07",
        flujo="contratos_nuevos", particion="2024-02-06_a_2024-02-07",
    )
    assert manifiesto["corte_al_iniciar"] == CORTE_DEL_25


def test_avisa_cuando_forzar_no_alcanza(orquestador, fuente, rutas, hoy, capsys):
    """Hay dos guardarraíles con la misma intención en capas distintas.

    `--forzar-corte-repetido` salta D11, que mira el corte. `_solo_lectura` mira
    el directorio y sigue en pie. Forzar sobre la partición de HOY no rehace
    nada: baja cero páginas y termina en segundos con salida normal.

    Eso es peor que negarse — dice que hizo algo cuando no hizo nada — y es el
    modo de fallo que este proyecto persigue en todas partes. La corrida sigue
    sin rehacer nada, a propósito; lo que se agrega es que lo diga.
    """
    fuente.programar("vivos", [filas(3)])
    correr(orquestador, rutas, hoy, corte=CORTE_DEL_25)  # deja la de hoy completa

    fuente.programar("vivos", [filas(3)])
    resultado = correr(orquestador, rutas, hoy, corte=CORTE_DEL_25, forzar=True)

    assert resultado.recibidas == 0, "rehizo la partición; eso es destructivo"
    salida = capsys.readouterr().out
    assert "LA BANDERA NO ALCANZA" in salida


def test_forzar_en_otro_dia_si_rehace(orquestador, fuente, rutas, hoy):
    """El caso para el que la bandera existe: mismo corte, otro día.

    Sin este test, avisar siempre también pasaría — y la bandera quedaría
    documentada como inútil cuando no lo es.
    """
    ingesta_previa_en_disco(rutas, fecha_extraccion="2026-08-25", corte=CORTE_DEL_25)
    fuente.programar("vivos", [filas(3)])

    resultado = correr(orquestador, rutas, hoy, corte=CORTE_DEL_25, forzar=True)

    assert resultado.recibidas == 3