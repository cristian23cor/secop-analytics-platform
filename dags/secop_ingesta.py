"""El DAG que corre el flujo 3 cuando la fuente se mueve.

## Por que no lleva un horario

La tentacion es programarlo contra la madrugada, porque las tres regeneraciones
conocidas de la fuente cayeron entre las 04:06 y las 04:41 hora de Colombia. No
sirve, por dos razones independientes.

Tres observaciones sobre una ventana movil de treinta y cinco minutos no fijan un
horario: el margen que uno cree tener puede no existir. Y sobre todo, **hay dias
sin ninguna regeneracion** (H34). Al escribir esto la fuente lleva siete dias
congelada. Ningun horario acierta contra un evento que a veces no ocurre.

Asi que el DAG no pregunta que hora es. Pregunta que estado esta publicado, y esa
pregunta cuesta una peticion de dos segundos contra 5,96 millones de filas, porque
la agregacion corre del lado del servidor.

## Por que la logica vive en el cargador y no aca

`cargar_raw.py` ya consulta el corte y se planta si ese corte ya se ingirio entero
(D11). El DAG **hereda** esa decision en vez de reimplementarla: llama al cargador
y lee su codigo de salida.

Si la logica viviera solo aca, correr el pipeline a mano la perderia, y el pipeline
se corre a mano. Y si viviera en los dos lados, el dia que se separen habria dos
respuestas a la pregunta de si hay algo nuevo.

De ahi que el cargador devuelva **codigo 4** cuando el corte ya estaba ingerido, un
codigo propio distinto del 1 y del 2. Un orquestador tiene que poder separar "no
habia nada nuevo" de "algo se rompio", y con cadencia irregular el primero va a ser
la mayoria de los dias.

## Las tres cosas que hay que escribir bien, y por que

**`catchup=False`, y no es una preferencia.** Airflow rellena por defecto las
corridas que cree que faltaron desde `start_date`. Contra el flujo 3 eso es
exactamente lo que R1 prohibe: reejecutarlo sobre una fecha pasada no reconstruye
esa fecha, escribe el estado de hoy con etiqueta de ayer, que es peor que no hacer
nada porque mete una mentira en la capa cruda. Con la fuente saltando dias, esa
lista de corridas a rellenar seria larga.

**`logical_date` no se usa para nada.** Airflow nombra cada ejecucion por un
intervalo de calendario. Aca la identidad de una corrida es el corte de la fuente,
que no tiene relacion con el calendario: dos corridas de dias distintos pueden ver
el mismo estado, y eso no es un error sino lo normal.

**El margen del tiempo limite no sale de un promedio.** Hay tres barridos medidos a
4,20, 5,22 y 5,00 segundos por pagina, y una particion suelta que tardo 28 segundos
en una pagina sin explicacion. Sobre 570 paginas eso es la diferencia entre
cincuenta minutos y cuatro horas. El limite se pone contra el peor caso conocido y
no contra el promedio.

## Que NO hace todavia

No corre dbt. La construccion completa son unos seis minutos en la maquina local y
depende de un archivo DuckDB de varios gigabytes que no tiene sentido mover a un
worker. Cuando los modelos sean incrementales, o cuando el destino sea Snowflake,
la tarea se agrega aca abajo con una sola dependencia.

Tampoco sondea sin cargar. El registro de cadencia (que dia se regenero y que dia
no) sigue siendo a mano, porque todavia no se decidio donde vive sin crear un
segundo lugar autoritativo.
"""

from __future__ import annotations

from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

# Donde vive el proyecto, desde el punto de vista de quien ejecuta la tarea.
#
# Sale del propio archivo y no de una ruta escrita a mano: este DAG esta en
# `<proyecto>/dags/`, asi que el proyecto es dos niveles arriba. Antes tenia una
# ruta absoluta como valor por defecto de una variable de Airflow, y eso es lo
# peor de las dos opciones: funcionaba en una sola maquina, y como funcionaba,
# nadie se enteraba de que habia una variable que definir.
#
# Asi el DAG no necesita que se configure NADA en la interfaz de Airflow para
# correr, que es lo que permite que CI lo pruebe sin levantar un scheduler.
#
# La variable sigue existiendo como escape, para el caso en que la carpeta de
# DAGs sea una copia y no el repositorio: si esta definida, manda.
_AQUI = Path(__file__).resolve().parent.parent
RAIZ = f"{{{{ var.value.get('secop_raiz', '{_AQUI}') }}}}"

# Codigo con el que el cargador dice "el corte ya estaba ingerido". No es un
# error: es la respuesta correcta la mayoria de los dias.
CORTE_YA_INGERIDO = 4

with DAG(
    dag_id="secop_ingesta",
    description="Baja el universo vivo cuando la fuente publica un corte nuevo",
    # Cada tres horas. No apunta a un horario: es cada cuanto se pregunta si hay
    # algo nuevo. La ventana de regeneracion conocida es de madrugada, pero como
    # hay dias sin regenerar, preguntar seguido y barato es mejor que acertarle
    # a una hora.
    schedule="0 */3 * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="America/Bogota"),
    # Ver el encabezado. Esto no se toca.
    catchup=False,
    # Dos corridas a la vez escribirian en la misma particion y pelearian por el
    # indice de hashes, que es un unico archivo DuckDB.
    max_active_runs=1,
    default_args={
        "retries": 0,  # los reintentos de red viven en `paginacion.py`, no aca
    },
    tags=["secop", "ingesta"],
) as dag:

    # Una sola tarea, a proposito. El cargador ya decide si hay algo que hacer,
    # asi que partirlo en "preguntar" y "cargar" duplicaria la pregunta y abriria
    # una ventana entre las dos en la que la fuente puede regenerar.
    cargar_vivos = BashOperator(
        task_id="cargar_vivos",
        # El codigo 4 se traduce a "saltar" y no a "fallar". Airflow entiende el
        # 99 como skip, asi que se mapea; cualquier otro codigo distinto de cero
        # sube tal cual y la tarea falla, que es lo que debe pasar.
        bash_command=(
            f"cd {RAIZ} && "
            "uv run python scripts/cargar_raw.py --flujo vivos; "
            f"codigo=$?; "
            f"if [ $codigo -eq {CORTE_YA_INGERIDO} ]; then "
            '  echo "El corte ya estaba ingerido: no hay nada nuevo."; exit 99; '
            "fi; "
            "exit $codigo"
        ),
        skip_on_exit_code=99,
        # Cuatro horas. Sale del peor caso conocido y no del promedio: 570 paginas
        # a los 28 segundos que tardo una pagina suelta. Con el promedio medido
        # (unos 5 segundos) el barrido son cincuenta minutos.
        execution_timeout=pendulum.duration(hours=4),
    )
