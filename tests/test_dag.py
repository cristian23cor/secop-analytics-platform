"""Que el DAG importe, y que lo que decidimos siga decidido.

## Por que un test que casi no afirma nada vale la pena

El fallo mas comun de un DAG no es logico sino de importacion: un modulo que se
movio, un operador que cambio de paquete entre versiones de Airflow, una
dependencia que no esta. Y es invisible: el archivo se ve bien, `python -c
"import"` lo carga si tenes suerte con el entorno, y recien se descubre cuando
alguien levanta un Airflow de verdad y ve el DAG en rojo con un error de import.

Importarlo desde CI cuesta segundos y cierra esa clase entera.

## Y tres afirmaciones que no son cosmeticas

Las otras tres cuidan decisiones que estan escritas y que un refactor distraido
puede invertir sin que nada mas se queje. Cada una tiene su motivo al lado, porque
un test sin motivo es lo primero que alguien borra cuando estorba.

## Por que se salta si Airflow no esta

Airflow vive en su propio grupo de dependencias y `uv sync` a secas no lo instala:
son 127 paquetes que quien clone el repositorio para leer el codigo no tiene por
que bajarse. Sin el salto, `pytest` fallaria en una instalacion normal por algo
que no esta roto.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Airflow escribe su configuracion en `AIRFLOW_HOME` al importarse. Sin esto la
# deja en el home del usuario, o peor, en el directorio del proyecto.
os.environ.setdefault("AIRFLOW_HOME", "/tmp/airflow_home_tests")

pytest.importorskip(
    "airflow", reason="Airflow va en su propio grupo: `uv sync --group airflow`"
)

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def dag():
    sys.path.insert(0, str(RAIZ / "dags"))
    import secop_ingesta

    return secop_ingesta.dag


def test_el_dag_importa(dag):
    """El fallo mas comun y el mas invisible. Si esto pasa, el archivo es un DAG."""
    assert dag.dag_id == "secop_ingesta"
    assert dag.tasks, "un DAG sin tareas importa igual y no hace nada"


def test_no_rellena_corridas_pasadas(dag):
    """`catchup=False` no es una preferencia, es R1.

    Airflow rellena por defecto las corridas que cree que faltaron desde
    `start_date`. Contra el flujo 3 eso es lo que R1 prohibe: reejecutarlo sobre
    una fecha pasada no reconstruye esa fecha, escribe el estado de hoy con
    etiqueta de ayer. Es peor que no hacer nada, porque mete una mentira en la
    capa cruda que despues nadie puede distinguir de una observacion real.

    Y con la fuente saltando dias, esa lista de corridas a rellenar es larga.
    """
    assert dag.catchup is False


def test_no_corren_dos_a_la_vez(dag):
    """Dos corridas simultaneas escribirian en la misma particion y pelearian por
    el indice de hashes, que es un unico archivo DuckDB y no admite dos
    escritores."""
    assert dag.max_active_runs == 1


def test_el_corte_repetido_salta_y_no_falla(dag):
    """El cargador devuelve 4 cuando el corte ya estaba ingerido, y eso NO es un
    error: con cadencia irregular es la respuesta correcta la mayoria de los dias.

    Si el DAG lo tratara como fallo, la alerta sonaria casi todos los dias y en
    dos semanas nadie la mira. Es el mismo argumento por el que las reglas de
    negocio sucias avisan en vez de romper la construccion.
    """
    tarea = dag.get_task("cargar_vivos")
    assert 99 in tarea.skip_on_exit_code, "el codigo de salto tiene que estar mapeado"
    assert "-eq 4" in tarea.bash_command, (
        "el DAG tiene que leer el codigo 4 del cargador, no reimplementar la "
        "pregunta de si hay un corte nuevo"
    )


def test_el_limite_de_tiempo_cubre_el_peor_caso(dag):
    """Hay tres barridos medidos entre 4,20 y 5,22 segundos por pagina, y una
    pagina suelta que tardo 28. Sobre 570 paginas eso es la diferencia entre
    cincuenta minutos y cuatro horas.

    El limite se pone contra el peor caso conocido. Ponerlo contra el promedio
    mataria una corrida sana el dia que la API vaya lenta, y con la fuente
    regenerando dos veces por semana, perder una corrida cuesta una observacion
    que no vuelve.
    """
    tarea = dag.get_task("cargar_vivos")
    assert tarea.execution_timeout is not None, "sin limite, una corrida colgada cuelga el DAG"
    assert tarea.execution_timeout.total_seconds() >= 4 * 3600


def test_la_raiz_apunta_al_proyecto(dag):
    """El DAG deduce donde vive el proyecto a partir de su propio archivo.

    Es lo que permite que no haya NADA que configurar en la interfaz de Airflow:
    sin esto haria falta definir una variable, y un DAG que necesita que alguien
    toque una interfaz antes de correr no se puede probar ni reproducir.

    El modo de fallo es que apunte a un directorio que no es el proyecto. No
    avisa: el `cd` falla recien cuando la tarea corre, cincuenta minutos despues
    de que alguien la lanzo esperando un barrido.
    """
    from secop_ingesta import _AQUI

    assert (_AQUI / "scripts" / "cargar_raw.py").is_file(), (
        f"{_AQUI} no parece la raiz del proyecto: no tiene scripts/cargar_raw.py"
    )
    assert (_AQUI / "dags" / "secop_ingesta.py").is_file()


def test_no_hay_rutas_absolutas_escritas_a_mano(dag):
    """Una ruta absoluta en el archivo funciona en una maquina y en ninguna otra,
    y como funciona, nadie se entera de que hay algo que configurar."""
    from pathlib import Path

    fuente = (Path(__file__).resolve().parent.parent / "dags"
              / "secop_ingesta.py").read_text(encoding="utf-8")
    for linea in fuente.splitlines():
        codigo = linea.split("#")[0]
        assert "'/home/" not in codigo and '"/home/' not in codigo, (
            f"ruta absoluta en el DAG: {linea.strip()}"
        )
