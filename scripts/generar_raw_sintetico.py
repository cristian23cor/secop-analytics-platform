"""Escribe una capa cruda sintetica y chica, para que CI pueda correr dbt.

## Por que existe

CI no puede usar la capa cruda real: son 898 MB que no van al repositorio, porque
el repositorio guarda codigo y no datos. Pero sin datos, el paso de dbt se queda
en `compile`, que renderiza la plantilla y no ejecuta el SQL. Los dos errores que
aparecieron al escribir estos modelos eran jinja valido y SQL roto, asi que
`compile` no los habria visto.

La salida es generar datos. Sinteticos y no una muestra de los reales, por dos
razones: no entra ni un byte de datos al repositorio, y se puede decidir a
proposito que casos aparecen.

## Que casos siembra, y por que cada uno

- **Contratos con dos observaciones**, para que el SCD2 produzca versiones y la
  capa de cambios tenga filas. Sin esto, la mitad del modelo no se ejecuta.
- **Cambios materiales de los tres signos**: valor que sube, valor que baja,
  plazo que se extiende y plazo que se acorta. Es lo que ejercita las cuatro
  columnas separadas del mart.
- **Cambios solo cosmeticos**, que cambian los bytes y no generan version. Sin
  ellos no se prueba que la clasificacion de D6 haga algo.
- **Los centinelas** en sus tres formas: los dos en espanol y `UNSPECIFIED`.
- **Claves ausentes**, porque la API omite los nulos (H6) y el modelo frontera
  tiene que devolver nulo en vez de romper.

## Lo que NO hace

No pretende parecerse a los datos reales en sus proporciones. Un test que dependa
de que el 74% sea contratacion directa esta midiendo la fuente, no el codigo, y
ese test no existe: los 46 de dbt son invariantes del modelo.

Uso:

    uv run python scripts/generar_raw_sintetico.py --destino /tmp/raw_ci
"""

from __future__ import annotations

import argparse
import gzip
import random
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))

from secop_analytics.columnas import (
    COLUMNAS_EXTRAIDAS,
    ENTERAS,
    FECHAS,
    MONETARIAS,
)
from secop_analytics.hashing import preparar

ESTADOS = ("En ejecución", "Modificado", "Suspendido", "Prorrogado", "Cerrado")
MODALIDADES = ("Contratación directa", "Mínima cuantía", "Contratación régimen especial")
DEPARTAMENTOS = ("Antioquia", "Distrito Capital de Bogotá", "Valle del Cauca")


def fila(rng: random.Random, i: int) -> dict:
    """La primera observacion de un contrato, con las 67 columnas."""
    d: dict[str, str] = {}
    for c in COLUMNAS_EXTRAIDAS:
        if c in MONETARIAS:
            d[c] = str(rng.randrange(1_000_000, 900_000_000))
        elif c in ENTERAS:
            d[c] = str(rng.randrange(0, 120))
        elif c in FECHAS:
            d[c] = f"2026-0{rng.randrange(1, 9)}-1{rng.randrange(0, 9)}T00:00:00.000"
        elif c == "urlproceso":
            d[c] = {"url": f"https://x/Index?noticeUID=CO1.NTC.{700000 + i}&isModal=true"}
        else:
            d[c] = f"texto {c} {i}"

    d["id_contrato"] = f"CO1.PCCNTR.{100000 + i}"
    d["codigo_entidad"] = f"70000{i % 7}"
    d["nit_entidad"] = f"8000000{i % 7}"
    d["codigo_proveedor"] = f"PROV{i % 23:04d}"
    d["documento_proveedor"] = f"{900000000 + i % 23}"
    d["proveedor_adjudicado"] = f"PROVEEDOR {i % 23}"
    d["proceso_de_compra"] = f"CO1.BDOS.{500000 + i}"
    d["estado_contrato"] = ESTADOS[i % len(ESTADOS)]
    d["modalidad_de_contratacion"] = MODALIDADES[i % len(MODALIDADES)]
    d["departamento"] = DEPARTAMENTOS[i % len(DEPARTAMENTOS)]
    d["liquidaci_n"] = "Si" if i % 5 == 0 else "No"

    # Los tres centinelas. El tercero es el que la limpieza NO convierte a nulo,
    # y por eso `dim_categoria` tiene que marcarlo aparte.
    if i % 11 == 0:
        d["codigo_de_categoria_principal"] = "UNSPECIFIED"
    else:
        d["codigo_de_categoria_principal"] = f"V1.{80111700 + i % 40:08d}"
    if i % 7 == 0:
        d["ciudad"] = "No Definido"
    if i % 13 == 0:
        d["departamento"] = "No definido"

    # La API omite las claves nulas (H6). El modelo frontera tiene que devolver
    # nulo, no romper.
    if i % 3 == 0:
        d.pop("fecha_fin_liquidacion", None)
        d.pop("fecha_inicio_liquidacion", None)

    return d


def segunda_observacion(anterior: dict, i: int) -> dict:
    """La misma fila con UN cambio, no una fila nueva al azar.

    Copiar y mutar es lo que hace que el caso cosmetico signifique algo. Si se
    regenerara la fila entera, las 67 columnas cambiarian y todas las segundas
    observaciones generarian version: el filtro de D6 quedaria sin probar
    justamente en el caso que existe para probarlo.
    """
    d = dict(anterior)
    resto = i % 5
    if resto == 0:      # el valor sube
        d["valor_del_contrato"] = str(int(d["valor_del_contrato"]) + 5_000_000)
    elif resto == 1:    # el valor baja: existe REDUCCION EN EL VALOR (H27)
        d["valor_del_contrato"] = str(max(1, int(d["valor_del_contrato"]) - 3_000_000))
    elif resto == 2:    # el plazo se extiende
        d["fecha_de_fin_del_contrato"] = "2026-12-31T00:00:00.000"
        d["dias_adicionados"] = str(int(d["dias_adicionados"]) + 90)
    elif resto == 3:    # el plazo se acorta
        d["fecha_de_fin_del_contrato"] = "2026-01-05T00:00:00.000"
    else:               # SOLO cosmetico: cambian los bytes y no el contrato
        d["nombre_entidad"] = f"ENTIDAD {i % 7} RENOMBRADA"
    return d


def escribir(destino: Path, flujo: str, fecha: str, particion: str,
             filas: list[dict]) -> int:
    d = destino / f"flujo={flujo}" / f"fecha_extraccion={fecha}" / f"particion={particion}"
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / "parte-0001.jsonl.gz", "wt", encoding="utf-8") as f:
        for fila_cruda in filas:
            # Se prepara con la misma funcion que usa la ingesta real, para que
            # el hash y la canonicalizacion sean los de verdad y no una imitacion.
            _, _, linea = preparar(fila_cruda, flujo=flujo, fecha_extraccion=fecha)
            f.write(linea.decode("utf-8") + "\n")
    (d / "_COMPLETO").write_text("", encoding="utf-8")
    return len(filas)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--destino", type=Path, default=Path("/tmp/raw_ci"))
    p.add_argument("--contratos", type=int, default=400)
    p.add_argument("--semilla", type=int, default=20260831)
    args = p.parse_args()

    rng = random.Random(args.semilla)
    n = args.contratos

    # Primer corte: todos los contratos.
    primero = [fila(rng, i) for i in range(n)]
    # Segundo corte: la mitad vuelve a aparecer, con un solo cambio cada una.
    segundo = [segunda_observacion(primero[i], i) for i in range(n // 2)]

    total = 0
    total += escribir(args.destino, "refresco_de_vivos", "2026-08-23", "completo", primero)
    total += escribir(args.destino, "refresco_de_vivos", "2026-08-25", "completo", segundo)
    # Los flujos 1 y 2 corren juntos sobre la MISMA ventana, asi que escriben
    # dos particiones que solo se distinguen por el flujo: misma
    # `fecha_extraccion` y mismo nombre de particion. Esta en la capa cruda real
    # (el 22/08 hay dos asi) y hay que reproducirla, porque es lo que obliga a
    # que la clave de una particion incluya el flujo.
    #
    # Sin este caso, `verificar_incremental.py` daba verde con una clave que
    # ignoraba el flujo. Se comprobo rompiendola a proposito.
    ventana = "2026-08-24_a_2026-08-25"
    total += escribir(args.destino, "contratos_nuevos", "2026-08-25", ventana,
                      [fila(rng, n + i) for i in range(20)])
    total += escribir(args.destino, "eventos_contractuales", "2026-08-25", ventana,
                      [fila(rng, n + 100 + i) for i in range(20)])

    # Y un mismo flujo con DOS particiones el mismo dia, que es lo que produce
    # un barrido del flujo 3 partido por rangos de fecha. Hoy no hay ninguno asi
    # en la capa cruda real, pero el diseno lo soporta (para eso existe
    # `medir_particiones.py`) y es lo que obliga a que la clave incluya el
    # nombre de la particion y no solo el flujo y la fecha.
    # Los rangos llevan contratos DISJUNTOS, y el desplazamiento es una
    # constante y no `hash(rango)`: el hash de las cadenas de Python cambia en
    # cada proceso, asi que la salida dejaba de ser reproducible pese al
    # `--semilla`, y de tanto en tanto los dos rangos se solapaban y metian el
    # mismo contrato dos veces bajo la misma `fecha_extraccion`. Eso viola el
    # supuesto que `fct_una_observacion_por_contrato_y_fecha` vigila, y el test
    # lo atrapo.
    for desplazamiento, rango in ((300, "2021-01-01_a_2021-02-01"),
                                  (400, "2021-02-01_a_2021-03-01")):
        total += escribir(args.destino, "refresco_de_vivos", "2026-08-26", rango,
                          [fila(rng, n + desplazamiento + i) for i in range(10)])

    peso = sum(f.stat().st_size for f in args.destino.rglob("*.jsonl.gz"))
    print(f"OK {args.destino}  {total} observaciones, {peso / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
