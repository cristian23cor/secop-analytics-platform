"""Que el tablero no se publique con cifras viejas, ni con un banner viejo.

Dos guardarrailes distintos, y el segundo se agrego cuando el primero no
alcanzo:

1. `sin_ingerir()`: raw contra el modelo. Si dbt no reconstruyo, no publiques.
2. `registro_de_cadencia_atrasado()`: raw contra `cadencia.csv`. Si el registro
   local no llego a tener la ultima linea que Actions ya commiteo, el banner
   del tablero ("corte vivo: tal fecha") queda hablando de un corte viejo aunque
   el modelo ya sepa el nuevo.

## Por que existe el primero

Paso, y estuvo una semana asi. `docs/index.html` se genero el 1 de septiembre y
nadie lo regenero despues de la carga del 8: la pagina publicada decia 88.395
cambios mientras el modelo decia 863.951, un factor de diez, y las dos cifras
convivian en el mismo repositorio.

Nada fallo. El tablero estampa su fecha de generacion y **nadie la compara contra
la del modelo**, asi que la unica forma de enterarse era leer los dos numeros y
notar que no cuadraban.

Es el mismo agujero que tenia el informe de paridad, que dijo "38 de 38
coinciden" comparando una tabla local recien hecha contra una de Snowflake de dos
dias antes. Se arreglo igual: preguntando de cuando es cada lado.

## Por que se compara contenido y no fechas de archivo

Un `mtime` se mueve al copiar, al clonar el repositorio o con un `touch`, y no
distingue "el modelo es viejo" de "alguien abrio el archivo". La pregunta que
importa es **que particiones tiene cada lado**, y esa se contesta exacta.

## El caso que casi rompe la regla

Una particion completa puede estar legitimamente ausente del modelo si no
escribio ninguna fila. Paso el 28/08/2026: la corrida contra la fuente congelada
descarto el 100% por bytes identicos, asi que la particion tiene `_COMPLETO`, su
manifiesto dice `lineas_totales: 0`, y no tiene un solo `.jsonl.gz`.

Sin esa salvedad el guardarrail marcaria esa particion en cada corrida, para
siempre, sobre un modelo sano. Y **una regla que marca de mas se termina
desactivando entera**: es la misma leccion que dejo el test del jinja.
"""

from __future__ import annotations

import gzip
import importlib
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture
def tablero():
    if str(RAIZ / "scripts") not in sys.path:
        sys.path.insert(0, str(RAIZ / "scripts"))
    return importlib.import_module("generar_tablero")


def particion(raiz: Path, clave: str, *, completo: bool = True,
              con_datos: bool = True) -> Path:
    """Arma en disco una particion con la ruta estilo Hive del proyecto."""
    flujo, fecha, nombre = clave.split("/")
    d = (raiz / f"flujo={flujo}" / f"fecha_extraccion={fecha}"
         / f"particion={nombre}")
    d.mkdir(parents=True)
    if con_datos:
        with gzip.open(d / "parte-0001.jsonl.gz", "wt") as f:
            f.write('{"id_contrato":"CO1.PCCNTR.1"}\n')
    if completo:
        (d / "_COMPLETO").write_text("ok", encoding="utf-8")
    return d


# --------------------------------------------------------------------------
# Que cuenta como particion que el modelo debe tener
# --------------------------------------------------------------------------

def test_una_particion_completa_y_con_datos_cuenta(tablero, tmp_path):
    particion(tmp_path, "refresco_de_vivos/2026-09-08/completo")
    assert tablero.particiones_con_datos(tmp_path) == {
        "refresco_de_vivos/2026-09-08/completo"
    }


def test_una_particion_completa_y_vacia_NO_cuenta(tablero, tmp_path):
    """**El caso del 28/08/2026.** Descarto el 100% por bytes identicos, asi que
    no escribio ninguna fila y no tiene nada que ingerir. Marcarla seria una
    falsa alarma permanente sobre un modelo sano."""
    particion(tmp_path, "refresco_de_vivos/2026-08-28/completo", con_datos=False)
    assert tablero.particiones_con_datos(tmp_path) == set()


def test_una_particion_a_medio_escribir_NO_cuenta(tablero, tmp_path):
    """Sin `_COMPLETO` la ingesta todavia esta corriendo. dbt tampoco la lee."""
    particion(tmp_path, "refresco_de_vivos/2026-09-09/completo", completo=False)
    assert tablero.particiones_con_datos(tmp_path) == set()


def test_la_clave_es_flujo_fecha_particion_sin_los_prefijos(tablero, tmp_path):
    """Tiene que coincidir con la que arma `clave_de_particion()` en dbt. Si una
    de las dos cambia de forma, el guardarrail compara contra otra cosa."""
    particion(tmp_path, "contratos_nuevos/2026-08-22/2026-08-20_a_2026-08-21")
    (clave,) = tablero.particiones_con_datos(tmp_path)
    assert clave == "contratos_nuevos/2026-08-22/2026-08-20_a_2026-08-21"
    assert "=" not in clave, "los prefijos estilo Hive no van en la clave"


def test_varias_particiones_del_mismo_dia_se_cuentan_por_separado(tablero, tmp_path):
    """El 22/08 hay dos particiones con la misma fecha y distinto flujo. Un
    guardarrail que las colapse pierde una sin fallar, que es el mismo defecto
    que tenia el filtro incremental antes de usar el triple."""
    particion(tmp_path, "contratos_nuevos/2026-08-22/2026-08-20_a_2026-08-21")
    particion(tmp_path, "eventos_contractuales/2026-08-22/2026-08-20_a_2026-08-21")
    assert len(tablero.particiones_con_datos(tmp_path)) == 2


# --------------------------------------------------------------------------
# La comparacion
# --------------------------------------------------------------------------

def test_al_dia_no_reporta_nada(tablero):
    unas = {"refresco_de_vivos/2026-09-08/completo"}
    assert tablero.sin_ingerir(unas, unas) == set()


def test_una_particion_nueva_en_disco_se_reporta(tablero):
    assert tablero.sin_ingerir(
        {"refresco_de_vivos/2026-09-08/completo", "refresco_de_vivos/2026-09-09/completo"},
        {"refresco_de_vivos/2026-09-08/completo"},
    ) == {"refresco_de_vivos/2026-09-09/completo"}


def test_un_modelo_con_mas_de_lo_que_hay_en_disco_no_es_este_problema(tablero):
    """Puede pasar si alguien borra raw y conserva la base. Es un problema, pero
    otro: publicar cifras viejas no es lo que ocurre, y esta regla contesta una
    sola pregunta."""
    assert tablero.sin_ingerir(
        {"refresco_de_vivos/2026-09-08/completo"},
        {"refresco_de_vivos/2026-09-08/completo", "refresco_de_vivos/2026-08-23/completo"},
    ) == set()


# --------------------------------------------------------------------------
# Contra la capa cruda real
# --------------------------------------------------------------------------

@pytest.mark.skipif(not (RAIZ / "datos" / "raw").is_dir(),
                    reason="no hay capa cruda en esta maquina")
def test_la_particion_vacia_real_no_se_marca(tablero):
    """Fija el caso concreto contra los datos de verdad, no solo sintetico."""
    claves = tablero.particiones_con_datos(RAIZ / "datos" / "raw")
    assert "refresco_de_vivos/2026-08-28/completo" not in claves, (
        "la corrida del 28/08 escribio cero filas: esta legitimamente ausente "
        "del modelo y no hay nada que reconstruir"
    )
    assert claves, "no se encontro ninguna particion con datos"


# --------------------------------------------------------------------------
# El segundo guardarrail: raw contra `cadencia.csv`
# --------------------------------------------------------------------------
#
# El caso real, 09/09/2026: se corrio el cargador y SI ingirio el corte del 9
# -esta en el manifiesto de la particion- pero la copia local de
# `cadencia.csv` (que GitHub Actions escribe por su cuenta) todavia no tenia
# esa linea. El tablero salio con el banner diciendo "corte vivo: 8 de
# septiembre" sobre un modelo que ya sabia que era el 9. Los numeros de arriba
# (contratos, versiones, cambios) eran correctos: solo el banner mentia, y
# solo se notaba leyendolo con cuidado.

def particion_con_corte(raiz: Path, fecha: str, corte: str) -> None:
    """Una particion de `refresco_de_vivos`, completa, con el corte dado."""
    d = raiz / "flujo=refresco_de_vivos" / f"fecha_extraccion={fecha}" / "particion=completo"
    d.mkdir(parents=True)
    (d / "_manifiesto.json").write_text(
        f'{{"corte_al_iniciar": "{corte}", "corte_al_terminar": "{corte}"}}',
        encoding="utf-8",
    )
    (d / "_COMPLETO").write_text("ok", encoding="utf-8")


def test_sin_particiones_no_hay_corte_que_reportar(tablero, tmp_path):
    assert tablero.corte_mas_reciente_ingerido(tmp_path) is None


def test_el_corte_mas_nuevo_es_el_que_cuenta(tablero, tmp_path):
    particion_con_corte(tmp_path, "2026-09-08", "2026-09-08T07:48:06.713Z")
    particion_con_corte(tmp_path, "2026-09-09", "2026-09-09T09:55:38.989Z")
    assert (tablero.corte_mas_reciente_ingerido(tmp_path)
            == "2026-09-09T09:55:38.989Z")


def test_una_particion_vacia_igual_confirma_su_corte(tablero, tmp_path):
    """El caso del 28/08: cero filas escritas, y aun asi el manifiesto confirma
    que el corte vivo en ese momento era el que dice. Esa confirmacion cuenta
    igual, es la razon de ser de D10."""
    d = tmp_path / "flujo=refresco_de_vivos" / "fecha_extraccion=2026-08-28" / "particion=completo"
    d.mkdir(parents=True)
    (d / "_manifiesto.json").write_text(
        '{"corte_al_iniciar": "2026-08-25T09:05:54.277Z",'
        ' "corte_al_terminar": "2026-08-25T09:05:54.277Z"}',
        encoding="utf-8",
    )
    (d / "_COMPLETO").write_text("ok", encoding="utf-8")
    assert (tablero.corte_mas_reciente_ingerido(tmp_path)
            == "2026-08-25T09:05:54.277Z")


def test_los_flujos_1_y_2_no_tienen_corte_y_se_ignoran(tablero, tmp_path):
    """Solo el flujo 3 pregunta por el corte de la fuente (D10, D11): los
    flujos 1 y 2 preguntan por ventanas de fecha y sus manifiestos no traen
    estos campos."""
    d = tmp_path / "flujo=contratos_nuevos" / "fecha_extraccion=2026-08-22" / "particion=x"
    d.mkdir(parents=True)
    (d / "_manifiesto.json").write_text(
        '{"cursor": "CO1.PCCNTR.1"}', encoding="utf-8")
    (d / "_COMPLETO").write_text("ok", encoding="utf-8")
    assert tablero.corte_mas_reciente_ingerido(tmp_path) is None


def test_el_registro_al_dia_no_reporta_atraso(tablero, tmp_path):
    particion_con_corte(tmp_path, "2026-09-09", "2026-09-09T09:55:38.989Z")
    assert tablero.registro_de_cadencia_atrasado(
        "2026-09-09T09:55:38.989Z", tmp_path
    ) is None


def test_el_registro_por_delante_del_modelo_no_es_este_problema(tablero, tmp_path):
    """El registro puede ir adelante si el sondeo vio un corte que el cargador
    todavia no bajo. Es trabajo pendiente, no un banner mintiendo."""
    particion_con_corte(tmp_path, "2026-09-08", "2026-09-08T07:48:06.713Z")
    assert tablero.registro_de_cadencia_atrasado(
        "2026-09-09T09:55:38.989Z", tmp_path
    ) is None


def test_el_caso_real_del_09_09_2026(tablero, tmp_path):
    """El registro dice 8, raw ya ingirio el 9. El banner mentiria."""
    particion_con_corte(tmp_path, "2026-09-09", "2026-09-09T09:55:38.989Z")
    assert tablero.registro_de_cadencia_atrasado(
        "2026-09-08T07:48:06.713Z", tmp_path
    ) == "2026-09-09T09:55:38.989Z"


@pytest.mark.skipif(not (RAIZ / "datos" / "raw").is_dir(),
                    reason="no hay capa cruda en esta maquina")
def test_contra_la_capa_cruda_real_el_registro_no_esta_atrasado(tablero):
    """Si esto falla, `exploration/cadencia.csv` esta detras de lo que raw ya
    sabe: falta un `git pull`, o falta anotar la linea del dia."""
    _, corte_del_registro = tablero.leer_cadencia()
    atraso = tablero.registro_de_cadencia_atrasado(
        corte_del_registro, RAIZ / "datos" / "raw"
    )
    assert atraso is None, (
        f"cadencia.csv dice {corte_del_registro!r} pero raw ya tiene "
        f"{atraso!r}. Corre `git pull`."
    )
