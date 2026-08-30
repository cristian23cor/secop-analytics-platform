"""¿El macro de dbt sigue diciendo lo mismo que `columnas.py`? Corre en CI.

## Por qué es un script aparte y no un test de pytest

Podría ser un test, y de hecho sería más cómodo. Está aparte por una razón: el
generador vive en `scripts/` y escribe en `dbt/`, y un test que dependa de la
existencia de un árbol dbt falla en cualquier entorno donde solo se instale el
paquete de Python. Acá el fallo dice qué hacer en vez de dar una traza.

Si algún día el proyecto se reorganiza y `dbt/` pasa a ser parte del paquete,
esto se convierte en tres líneas dentro de `test_columnas.py`.

## Qué comprueba, y qué NO

Comprueba que el archivo en disco sea **byte a byte** el que el generador
produciría hoy. Eso cubre los dos sentidos de la deriva:

- Alguien tocó `columnas.py` y no regeneró. dbt estaría leyendo un esquema
  distinto del que la ingesta le pide a la API: el `$select` traería una columna
  que el `STRUCT` no tiene, y esa columna **se ignora en silencio**.
- Alguien editó el macro a mano. Existe una segunda fuente de verdad del esquema
  y nadie lo sabe.

**No comprueba que el esquema sea correcto**, solo que sea uno solo. Que las 67
columnas existan en la fuente lo verifica `columnas.validar_cobertura()`, que
todavía no tiene quién la llame.

## Por qué byte a byte y no una comparación semántica

Una comparación semántica (los mismos nombres, en cualquier orden y formato)
sería más tolerante y peor. El archivo es generado: si difiere en un byte,
alguien lo tocó o el generador cambió, y las dos cosas hay que verlas. Tolerar
diferencias de formato es cómo un archivo generado se convierte en uno editado a
mano sin que nadie lo decida.

Uso:

    uv run python scripts/verificar_columnas_dbt.py

Devuelve 0 si están sincronizados, 1 si no. Pensado para CI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GENERADOR = Path(__file__).with_name("generar_columnas_dbt.py")


def main() -> int:
    print("\nDeriva entre `columnas.py` y el macro de dbt\n")

    # Se delega en el propio generador con `--comprobar` en vez de reimplementar
    # la comparación. Reimplementarla crearía una tercera definición de lo mismo,
    # que es el problema que este script existe para detectar.
    resultado = subprocess.run(
        [sys.executable, str(GENERADOR), "--comprobar"],
        capture_output=True,
        text=True,
    )
    print(resultado.stdout, end="")
    print(resultado.stderr, end="", file=sys.stderr)

    if resultado.returncode != 0:
        print(
            "\n  Por qué importa: `columnas.py` arma el `$select` que se le pide"
            " a la API,\n  y el macro arma el `STRUCT` con el que dbt lee lo que"
            " llegó. Si divergen, una columna puede viajar y no leerse,"
            "\n  o leerse y no existir, sin que nada falle.",
            file=sys.stderr,
        )
    return resultado.returncode


if __name__ == "__main__":
    raise SystemExit(main())