#!/usr/bin/env bash
# Envoltorio de Airflow, para no exportar cuatro variables cada vez.
#
# Airflow decide donde guarda su configuracion, su base de metadatos y sus logs
# segun AIRFLOW_HOME. Por defecto seria ~/airflow, fuera del proyecto. Se pone
# adentro y se ignora en git: todo lo del proyecto en un lugar, y borrar
# .airflow/ reinicia Airflow por completo sin tocar nada mas.
#
#   ./scripts/airflow.sh dags list        que DAGs ve
#   ./scripts/airflow.sh standalone       levanta todo (Ctrl-C para parar)
#
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export AIRFLOW_HOME="$RAIZ/.airflow"

# El DAG vive en el repositorio, no en .airflow/dags, que es donde Airflow lo
# buscaria por defecto. Es lo que permite que este versionado y que CI lo pruebe.
export AIRFLOW__CORE__DAGS_FOLDER="$RAIZ/dags"

# Sin los DAGs de ejemplo. Son varias decenas y esconden el unico que importa.
export AIRFLOW__CORE__LOAD_EXAMPLES=False

# SQLite y LocalExecutor, que es lo que trae standalone. Para un DAG con una
# tarea que corre cada tres horas sobra: postgres y Celery existen para el
# paralelismo que aca no hay, y el DAG ya declara max_active_runs=1 porque dos
# corridas pelearian por el indice de hashes.

cd "$RAIZ"
exec uv run --group airflow airflow "$@"
