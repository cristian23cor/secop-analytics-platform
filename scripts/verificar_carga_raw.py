"""Verificación de la capa raw contra la API real. Se corre a mano.

## Por qué existe, si ya hay una suite de tests

Los tests usan dobles de `flujos.py`: devuelven las filas que uno escribe, y uno
las escribe desde lo que espera. Prueban lo que el orquestador **decide** — el
orden, el guardarraíl, la reanudación, los nombres de partición — y no prueban
el contrato con la fuente.

Las rarezas que la exploración encontró en esta fuente son la prueba de lo que
eso deja afuera: una columna de fecha corrupta con una regla exacta, centinelas
de texto en dos capitalizaciones, `urlproceso` como objeto anidado,
`habilita_pago_adelantado` con tres estados y no dos.

Ningún doble escrito a mano habría tenido esas rarezas. Los dobles se escriben
desde la expectativa, y el punto es que la expectativa estaba mal.

Este script cubre la otra mitad: **que las filas reales sobrevivan el viaje**.

## Qué comprueba, en orden de importancia

  FASE 1 — Toda fila real pasa por `preparar()` sin explotar.
  FASE 2 — La ida y vuelta es exacta: lo escrito se relee idéntico.
           *** La que valida la deduplicación por bytes (D3). Si el rehasheo
           no coincide, está construida sobre arena. ***
  FASE 3 — La tasa de descarte sobre datos reales. Dos corridas seguidas de la
           misma ventana deben dar ~100% de descarte en la segunda.
  FASE 4 — Nada de lo que se guardó es un dato personal (H7).

## Por qué no está en CI

Depende de la red y de una API de terceros. Un test que falla porque
`datos.gov.co` está caído enseña a ignorar los tests. Se corre a mano cuando
cambia algo del extractor, de `columnas.py` o de la canonicalización.

Uso:

    uv run python scripts/verificar_carga_raw.py
    uv run python scripts/verificar_carga_raw.py --paginas 3 --dias 3

⚠ **Consume el doble de peticiones de lo que parece.** La fase 3 descarga la
misma ventana dos veces, a propósito: es la única forma de comprobar que la
segunda corrida descarta todo.

Referencias: `exploration/03_decisiones_capa_raw.md` — D3 (deduplicación por
bytes) y R2 (la fecha colombiana).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from cargar_raw import cargar_nuevos, hoy
from secop_analytics.columnas import PERSONALES
from secop_analytics.escritura import leer_particion
from secop_analytics.flujos import contratos_nuevos
from secop_analytics.hashing import canonicalizar, hashear, preparar, verificar_linea

# Ventana chica y reciente: suficiente para ver filas reales sin bajar medio
# dataset. ~2.900 contratos por día (H3).
#
# Es solo el valor por defecto de `--dias`. El ancho real viaja como parámetro
# hasta cada fase: una global que `main()` reescribe hace que el comportamiento
# de una función dependa de quién la llamó antes.
DIAS_POR_DEFECTO = 1


def titulo(texto: str) -> None:
    print(f"\n{'=' * 68}\n{texto}\n{'=' * 68}", flush=True)


# --------------------------------------------------------------------------


def fase_1(paginas_max: int, dias: int) -> list[dict]:
    """Toda fila real pasa por `preparar()` sin explotar."""
    titulo("FASE 1 — Las filas reales sobreviven la canonicalización")

    hasta = hoy()
    desde = hasta - timedelta(days=dias)
    print(f"Ventana: {desde} a {hasta} (semiabierta)\n")

    recogidas: list[dict] = []
    fallos: list[tuple[str, str]] = []

    for numero, pagina in enumerate(contratos_nuevos(desde, hasta), start=1):
        if numero > paginas_max:
            break
        for fila in pagina:
            try:
                preparar(fila, flujo="contratos_nuevos", fecha_extraccion=str(hasta))
                recogidas.append(fila)
            except ValueError as error:
                fallos.append((fila.get("id_contrato", "?"), str(error)))
        print(f"  página {numero}: {len(pagina)} filas", flush=True)

    print(f"\n  procesadas: {len(recogidas):,}")
    if fallos:
        print(f"  ❌ FALLARON {len(fallos)}:")
        for id_contrato, motivo in fallos[:5]:
            print(f"     {id_contrato}: {motivo[:120]}")
    else:
        print("  ✅ ninguna falló")

    if not recogidas:
        print("\n  ⚠ Sin filas en la ventana. Ampliá --dias o revisá el rezago.")
    return recogidas


def fase_2(recogidas: list[dict]) -> bool:
    """La ida y vuelta es exacta. Es la que valida D3."""
    titulo("FASE 2 — Ida y vuelta sobre datos reales")
    print("Si el hash de lo releído no coincide con el de lo escrito, la")
    print("deduplicación está construida sobre arena.\n")

    if not recogidas:
        print("  (sin filas que verificar)")
        return True

    base = Path(tempfile.mkdtemp())
    try:
        from secop_analytics.escritura import ParticionRaw

        esperados: dict[str, str] = {}
        with ParticionRaw(
            base, flujo="contratos_nuevos", fecha_extraccion=str(hoy()),
            particion="verificacion", lineas_por_trozo=500, verboso=False,
        ) as destino:
            for fila in recogidas:
                id_contrato, huella, linea = preparar(
                    fila, flujo="contratos_nuevos", fecha_extraccion=str(hoy())
                )
                esperados[id_contrato] = huella
                destino.escribir(linea)
            destino.completar()

        observaciones = leer_particion(destino.directorio)
        print(f"  escritas {len(esperados):,} · releídas {len(observaciones):,}")

        discrepancias = 0
        for observacion in observaciones:
            id_contrato = observacion["datos"]["id_contrato"]
            rehasheado = hashear(canonicalizar(observacion["datos"]))
            # Dos comprobaciones distintas: que la línea sea internamente
            # coherente, y que además coincida con lo que se calculó ANTES de
            # escribirla. La segunda es la que detecta una pérdida en el viaje
            # a disco; la primera sola no lo haría.
            coherente = verificar_linea(json.dumps(observacion).encode("utf-8"))
            if not coherente or rehasheado != esperados[id_contrato]:
                discrepancias += 1
                if discrepancias <= 3:
                    print(f"     ❌ {id_contrato}: {observacion['hash']} → {rehasheado}")

        peso = sum(f.stat().st_size for f in destino.directorio.glob("*.gz"))
        print(f"  comprimido: {peso/1024:,.0f} KB ({peso/len(observaciones):.0f} bytes/fila)")

        if discrepancias:
            print(f"  ❌ {discrepancias} filas no rehashean igual")
            return False
        print("  ✅ todas rehashean idéntico")
        return True
    finally:
        shutil.rmtree(base)


def fase_3(dias: int) -> bool:
    """La tasa de descarte real. La segunda corrida no debe escribir nada."""
    titulo("FASE 3 — Deduplicación sobre datos reales")
    print("Dos corridas seguidas de la MISMA ventana: la segunda debe descartar")
    print("todo. Si no, algo de la canonicalización no es determinista sobre")
    print("datos verdaderos — y eso ningún doble lo detecta.\n")

    base = Path(tempfile.mkdtemp())
    try:
        indice = base / "indice.duckdb"
        hasta = hoy()
        desde = hasta - timedelta(days=dias)
        fecha = str(hasta)

        primera = cargar_nuevos(
            desde, hasta, fecha_extraccion=fecha,
            raiz=base / "raw1", ruta_indice=indice,
        )
        print(f"  primera: {primera.recibidas:,} recibidas · {primera.escritas:,} escritas")

        # Misma ventana y **mismo índice**, pero otra raíz: sin eso, la segunda
        # corrida vería `_COMPLETO` de la primera y no haría nada, que es
        # justamente lo que este test no quiere demostrar.
        segunda = cargar_nuevos(
            desde, hasta, fecha_extraccion=fecha,
            raiz=base / "raw2", ruta_indice=indice,
        )
        print(f"  segunda: {segunda.recibidas:,} recibidas · {segunda.escritas:,} escritas")
        print(f"  descarte de la segunda: {segunda.tasa_descarte:.1%}")

        if segunda.recibidas and segunda.escritas:
            print(f"  ❌ escribió {segunda.escritas} filas que no cambiaron")
            return False
        print("  ✅ descarte total, como corresponde")
        return True
    finally:
        shutil.rmtree(base)


def fase_4(recogidas: list[dict]) -> bool:
    """Ningún dato personal viajó. H7 dice que el filtro corre en el `$select`."""
    titulo("FASE 4 — Ningún dato personal en lo guardado")
    print("H7: el filtro corre en el `$select`, no después. Esto verifica que")
    print("efectivamente no viajaron, en vez de confiar en que no viajaron.\n")

    if not recogidas:
        print("  (sin filas que verificar)")
        return True

    presentes = {c for fila in recogidas for c in fila if c in PERSONALES}
    if presentes:
        print(f"  ❌ llegaron {len(presentes)} columnas personales: {sorted(presentes)}")
        return False
    print(f"  ✅ ninguna de las {len(PERSONALES)} columnas personales llegó")
    return True


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paginas", type=int, default=2,
                        help="Cuántas páginas traer como máximo (defecto 2).")
    parser.add_argument("--dias", type=int, default=DIAS_POR_DEFECTO,
                        help=f"Ancho de la ventana en días (defecto {DIAS_POR_DEFECTO}).")
    args = parser.parse_args()

    load_dotenv()

    print("\nVerificación de la capa raw contra la API real")
    print(f"hoy en Colombia: {hoy()}  ·  hoy del sistema: {date.today()}")
    if hoy() != date.today():
        print("  ⚠ difieren: estás en la franja donde UTC ya cambió de día. La")
        print("    fecha que manda es la colombiana (ver R2).")

    recogidas = fase_1(args.paginas, args.dias)
    resultados = [
        ("2 · ida y vuelta", fase_2(recogidas)),
        ("3 · deduplicación", fase_3(args.dias)),
        ("4 · datos personales", fase_4(recogidas)),
    ]

    titulo("RESUMEN")
    for nombre, paso in resultados:
        print(f"  {'✅' if paso else '❌'}  fase {nombre}")

    if all(paso for _, paso in resultados):
        print("\n  La capa raw se comporta igual contra datos reales que en los tests.")
        return 0
    print("\n  ⚠ Algo se comporta distinto con datos reales. Los dobles no bastan.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())