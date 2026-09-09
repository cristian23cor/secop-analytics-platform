"""Que el tablero no se publique con cifras viejas.

## Por que existe

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
