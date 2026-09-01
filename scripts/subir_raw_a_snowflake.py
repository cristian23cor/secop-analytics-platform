"""Sube la capa cruda a un stage de Snowflake, conservando la ruta de particion.

## Por que existe

DuckDB lee los `.jsonl.gz` del disco local; Snowflake no puede. El porte necesita
que los mismos archivos esten del otro lado, y este script es esa frontera: es el
equivalente de lo que en local hace el sistema de archivos.

Sube preservando `flujo=.../fecha_extraccion=.../particion=.../`, porque el modelo
frontera deriva esas tres columnas de la ruta del archivo y no de los metadatos de
la fila. Si la ruta se aplana, el modelo pierde la particion de la que vino cada
observacion.

## Lo que NO sube

Los manifiestos y las marcas `_COMPLETO`. Hoy dbt no los lee en ningun motor; el
dia que exista el modelo de procedencia habra que subirlos tambien.

## Como sube

Un `PUT` por directorio de particion en vez de uno por archivo: son 6 sentencias
en lugar de 602, y cada `PUT` paraleliza internamente. Los archivos ya vienen
comprimidos, asi que se desactiva la compresion automatica y se declara la de
origen; sin eso Snowflake los volveria a comprimir encima.

`PUT` es idempotente con `OVERWRITE=FALSE`: un archivo que ya esta no se vuelve a
subir. Eso permite reanudar una subida cortada sin repetir lo hecho.

Uso:

    uv run python scripts/subir_raw_a_snowflake.py --solo fecha_extraccion=2026-08-25
    uv run python scripts/subir_raw_a_snowflake.py            # todo
    uv run python scripts/subir_raw_a_snowflake.py --listar   # que hay en el stage
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "datos" / "raw"
# Calificados con el esquema, no sueltos. Un nombre suelto lo resuelve Snowflake
# contra el esquema de la SESION, y ese contexto no es el mismo cuando lo lee el
# modelo de dbt: la capa de staging vive en `<esquema>_staging`, asi que un
# `@secop_raw` sin calificar la busca ahi y no la encuentra.
#
# Se rompio de esa forma el 01/09, y de la peor manera posible: funcionaba
# mientras el modelo se materializaba como `table` y dejo de funcionar al pasar a
# incremental, con el stage intacto y los 602 archivos en su lugar.
_ESQUEMA = os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC")
STAGE = f"{_ESQUEMA}.secop_raw"
FORMATO = f"{_ESQUEMA}.jsonl_gz"


def conectar():
    """Abre la conexion con autenticacion por par de claves.

    La contrasena no sirve: con MFA activo dispararia un push al telefono en cada
    corrida, lo que hace inviable cualquier ejecucion desatendida.
    """
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization
    from dotenv import load_dotenv

    load_dotenv(BASE / ".env")

    ruta = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", "")
    clave = Path(ruta)
    if not clave.is_absolute():
        # La ruta del `.env` esta escrita relativa a `dbt/`, que es desde donde
        # corre dbt. Este script vive en `scripts/`, asi que se resuelve contra
        # la raiz del proyecto en vez de contra el directorio actual.
        clave = (BASE / "dbt" / ruta).resolve()
    if not clave.is_file():
        raise SystemExit(f"No se encontro la clave privada en {clave}")

    with clave.open("rb") as f:
        pk = serialization.load_pem_private_key(f.read(), password=None)

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ.get("SNOWFLAKE_ROLE"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
        database=os.environ.get("SNOWFLAKE_DATABASE"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA"),
        private_key=pk.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def preparar(cur) -> None:
    """El formato y el stage. Idempotente: se puede correr siempre."""
    cur.execute(f"""
        create file format if not exists {FORMATO}
          type = json
          compression = gzip
          strip_outer_array = false
    """)
    cur.execute(f"create stage if not exists {STAGE} file_format = {FORMATO}")


def particiones(filtro: str | None) -> list[Path]:
    """Los directorios de particion que tienen trozos, en orden estable."""
    dirs = sorted({f.parent for f in RAW.rglob("*.jsonl.gz")})
    if filtro:
        dirs = [d for d in dirs if filtro in str(d)]
    return dirs


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo", help="Sube solo las particiones cuya ruta contenga este texto.")
    p.add_argument("--listar", action="store_true", help="No sube: muestra lo que ya esta.")
    p.add_argument("--paralelo", type=int, default=8, help="Hilos por PUT (por defecto 8).")
    args = p.parse_args()

    con = conectar()
    cur = con.cursor()
    preparar(cur)

    if args.listar:
        filas = cur.execute(f"list @{STAGE}").fetchall()
        total = sum(f[1] for f in filas)
        print(f"{len(filas)} archivos en @{STAGE}, {total / 1024 / 1024:.0f} MB")
        for f in filas[:5]:
            print(f"   {f[0]}  {f[1] / 1024:.0f} KB")
        if len(filas) > 5:
            print(f"   ... y {len(filas) - 5} mas")
        con.close()
        return 0

    dirs = particiones(args.solo)
    if not dirs:
        print(f"Ninguna particion coincide con {args.solo!r}", file=sys.stderr)
        return 1

    subidos = omitidos = 0
    arranque = time.time()
    for d in dirs:
        # La ruta relativa es lo que el modelo frontera lee para saber de que
        # particion vino cada fila. Se conserva tal cual.
        rel = d.relative_to(RAW).as_posix()
        n_local = len(list(d.glob("*.jsonl.gz")))
        mb = sum(f.stat().st_size for f in d.glob("*.jsonl.gz")) / 1024 / 1024
        print(f"  {rel}  ({n_local} archivos, {mb:.0f} MB) ... ", end="", flush=True)
        t = time.time()
        filas = cur.execute(
            f"put 'file://{d.as_posix()}/*.jsonl.gz' '@{STAGE}/{rel}/' "
            f"auto_compress = false source_compression = gzip "
            f"parallel = {args.paralelo} overwrite = false"
        ).fetchall()
        # La columna de estado dice UPLOADED o SKIPPED; el segundo caso es un
        # archivo que ya estaba, y es lo que hace reanudable la subida.
        s = sum(1 for f in filas if str(f[6]).upper() == "SKIPPED")
        subidos += len(filas) - s
        omitidos += s
        print(f"{len(filas) - s} subidos, {s} ya estaban  [{time.time() - t:.0f}s]")

    print(f"\nOK  {subidos} archivos subidos, {omitidos} omitidos, "
          f"{time.time() - arranque:.0f}s en total")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
