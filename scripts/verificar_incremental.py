"""Comprueba que la ruta incremental y la de `--full-refresh` dan la misma tabla.

## Por que hace falta un script y no alcanza con un test de dbt

`raw_observaciones` y `stg_contratos` pasaron a ser incrementales, y eso
introduce **estado acumulado**: la tabla de hoy depende de lo que habia ayer. D5
dice lo contrario, que el modelo es una funcion de la capa cruda, y esa propiedad
es la que permite corregir el pasado reprocesando.

La salida que dbt ofrece es `--full-refresh`, que ignora lo incremental y
reconstruye desde cero. La propiedad se conserva mientras las dos rutas den lo
mismo, y eso hay que **demostrarlo, no suponerlo**. Un test de dbt corre dentro
de una construccion; esto compara dos construcciones distintas, asi que vive
afuera.

## Que hace

Sobre la capa cruda sintetica, que trae tres particiones:

    1. construye con SOLO la particion del 23         (primera pasada)
    2. agrega la del 25 de refresco y construye INCREMENTAL
    3. agrega la del 25 de contratos_nuevos y construye INCREMENTAL
    4. construye todo de cero con --full-refresh      (en otra base)
    5. compara las dos tablas resultantes fila por fila

Las etapas 2 y 3 van separadas a proposito. Cargadas juntas, un filtro por fecha
sola las dejaria pasar a las dos y la prueba daria verde con el filtro roto: se
comprobo, y no lo detectaba. Separadas, la tercera llega cuando la tabla ya tiene
esa misma fecha, y ahi el filtro malo la pierde.

## El caso que esta prueba cuida en particular

Las dos particiones del 25 tienen la misma `fecha_extraccion` y distinto flujo.
Un filtro incremental escrito como `where fecha > (select max(fecha) from this)`
las tratraria como una sola y perderia la segunda **sin fallar**. Por eso la
clave es el triple (flujo, fecha, particion) y por eso el dato sintetico tiene
ese caso adentro.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELOS = ["raw_observaciones", "stg_contratos"]


def dbt(args: list[str], base: Path, raw: Path) -> None:
    entorno = {**os.environ, "SECOP_DUCKDB": str(base)}
    r = subprocess.run(
        ["uv", "run", "dbt", *args, "--select", *MODELOS,
         "--vars", f'{{"ruta_raw": "{raw}"}}'],
        cwd=RAIZ / "dbt", env=entorno, capture_output=True, text=True, check=False,
    )
    if r.returncode:
        print(r.stdout[-3000:], file=sys.stderr)
        raise SystemExit(f"dbt fallo: {' '.join(args)}")


# Las tres etapas, en orden de llegada. La tercera es la que da valor a esta
# prueba: llega DESPUES de otra particion con la misma `fecha_extraccion`, y un
# filtro escrito como `> max(fecha)` la perderia en silencio.
ETAPAS = [
    ["flujo=refresco_de_vivos/fecha_extraccion=2026-08-23"],
    ["flujo=refresco_de_vivos/fecha_extraccion=2026-08-25"],
    ["flujo=contratos_nuevos/fecha_extraccion=2026-08-25"],
    # La cuarta comparte fecha Y nombre de particion con la tercera: solo cambia
    # el flujo. Es la que obliga a que la clave lo incluya.
    ["flujo=eventos_contractuales/fecha_extraccion=2026-08-25"],
    # La quinta y la sexta son del mismo flujo y el mismo dia, y solo difieren
    # en el nombre de la particion: es lo que obliga a que la clave lo incluya.
    # Se cargan de a una para que la sexta llegue con su flujo y su fecha ya
    # presentes en la tabla.
    ["flujo=refresco_de_vivos/fecha_extraccion=2026-08-26/particion=2021-01-01_a_2021-02-01"],
    ["flujo=refresco_de_vivos/fecha_extraccion=2026-08-26/particion=2021-02-01_a_2021-03-01"],
]


def preparar_raw(origen: Path, destino: Path, hasta: int) -> None:
    """Deja en `destino` las particiones de las primeras `hasta` etapas."""
    if destino.exists():
        shutil.rmtree(destino)
    for etapa in ETAPAS[:hasta]:
        for rel in etapa:
            origen_p = origen / rel
            assert origen_p.is_dir(), f"falta la particion sintetica {rel}"
            shutil.copytree(origen_p, destino / rel)


def comparar(incremental: Path, completa: Path) -> int:
    import duckdb

    con = duckdb.connect(":memory:")
    con.execute(f"attach '{incremental}' as inc (read_only)")
    con.execute(f"attach '{completa}' as completa (read_only)")
    fallos = 0
    for modelo in MODELOS:
        a, b = f"inc.main_staging.{modelo}", f"completa.main_staging.{modelo}"
        n_a = con.execute(f"select count(*) from {a}").fetchone()[0]
        n_b = con.execute(f"select count(*) from {b}").fetchone()[0]
        # `except` en los dos sentidos: una sola direccion no detecta que a la
        # tabla incremental le sobre una fila que la completa no tiene.
        sobran = con.execute(f"select count(*) from (select * from {a} except select * from {b})").fetchone()[0]
        faltan = con.execute(f"select count(*) from (select * from {b} except select * from {a})").fetchone()[0]
        ok = n_a == n_b and sobran == 0 and faltan == 0
        fallos += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'MAL '} {modelo:22} "
              f"incremental {n_a:>6,} | completa {n_b:>6,} | "
              f"sobran {sobran} | faltan {faltan}")
    return fallos


def main() -> int:
    sintetico = Path("/tmp/raw_sintetico_eq")
    trabajo = Path("/tmp/raw_eq_trabajo")
    base_inc = Path("/tmp/eq_incremental.duckdb")
    base_full = Path("/tmp/eq_completa.duckdb")
    for f in (base_inc, base_full):
        f.unlink(missing_ok=True)

    subprocess.run([sys.executable, str(RAIZ / "scripts" / "generar_raw_sintetico.py"),
                    "--destino", str(sintetico)], check=True, capture_output=True)

    print(f"  construyendo en {len(ETAPAS)} etapas...")
    for n in range(1, len(ETAPAS) + 1):
        preparar_raw(sintetico, trabajo, hasta=n)
        dbt(["build"], base_inc, trabajo)

    print("  construyendo de cero, con todo...")
    dbt(["build", "--full-refresh"], base_full, trabajo)

    print()
    fallos = comparar(base_inc, base_full)
    print()
    if fallos:
        print(f"  FALLA: {fallos} modelo(s) difieren entre las dos rutas.")
        print("  La propiedad de D5 no se sostiene: reconstruir no da lo mismo.")
        return 1
    print("  ok   las dos rutas dan la misma tabla, fila por fila")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
