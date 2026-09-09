#!/usr/bin/env bash
# Los tres pasos que van juntos, en el unico orden en que dan un resultado
# coherente.
#
#   cargar_raw.py     escribe  datos/raw/       (JSONL comprimido)
#   dbt build         lee raw  escribe          datos/secop.duckdb, 11 modelos
#   generar_tablero   lee la base  escribe      docs/index.html
#
# Existe porque los tres se corrian a mano y el ultimo se olvidaba. El tablero
# publicado estuvo una semana mostrando 88.395 cambios cuando el modelo ya decia
# 863.951, y nada lo noto.
#
# ## Por que el tablero NO cuelga del cargador
#
# El cargador escribe raw; el tablero lee la base. Entre los dos esta dbt. Si el
# tablero se disparara al terminar la ingesta, leeria un modelo que todavia no
# tiene los datos nuevos: saldria con la fecha de hoy y las cifras de ayer, que
# es peor que quedarse viejo, porque la fecha vieja al menos delata el desfase.
#
# El orden no es una convencion: es la unica forma de que la pagina publicada
# diga lo mismo que el modelo.
#
# ## Que pasa si la fuente no se movio
#
# El cargador devuelve 4 y no baja nada (D11). Aun asi se sigue con dbt y con el
# tablero, a proposito: ese es exactamente el caso en el que el modelo puede
# estar atrasado por una carga anterior que nadie construyo. Cuesta unos 90
# segundos y es el error que sobra.
#
#   ./scripts/actualizar.sh                 el flujo 3, que es el caso normal
#   ./scripts/actualizar.sh --sin-cargar    solo reconstruir y republicar
#
set -euo pipefail
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

if [ "${1:-}" != "--sin-cargar" ]; then
  echo "== 1/3  bajando el corte nuevo (~50 min si hay algo)"
  set +e
  uv run python scripts/cargar_raw.py --flujo vivos
  codigo=$?
  set -e
  case "$codigo" in
    0) echo "   se ingirio un corte nuevo." ;;
    # 4 no es un fallo: es "la fuente no se movio". Mismo criterio que usa el
    # DAG, que lo traduce a saltar y no a fallar.
    4) echo "   la fuente no se movio. Se reconstruye igual, por si el modelo"
       echo "   quedo atrasado de una carga anterior." ;;
    *) echo "   el cargador fallo con codigo $codigo. Se aborta." >&2
       exit "$codigo" ;;
  esac
else
  echo "== 1/3  omitido (--sin-cargar)"
fi

echo
echo "== 2/3  construyendo los once modelos"
( cd dbt && uv run dbt build )

echo
echo "== 3/3  regenerando el tablero"
# Si el modelo quedara atrasado igual, este paso se planta con codigo 3 en vez
# de publicar cifras viejas con la fecha de hoy.
uv run python scripts/generar_tablero.py

echo
echo "Listo. Para publicarlo:  git add -A && git commit && git push"
