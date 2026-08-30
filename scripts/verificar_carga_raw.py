"""Verificación de la capa raw contra la API real. Se corre a mano.

## Por qué existe, si ya hay una suite de tests

Los tests usan dobles de `flujos.py`: devuelven las filas que uno escribe, y uno
las escribe desde lo que espera. Prueban lo que el orquestador **decide** (el
orden, el guardarraíl, la reanudación, los nombres de partición) y no prueban
el contrato con la fuente.

Las rarezas que la exploración encontró en esta fuente son la prueba de lo que
eso deja afuera: una columna de fecha corrupta con una regla exacta, centinelas
de texto en dos capitalizaciones, `urlproceso` como objeto anidado,
`habilita_pago_adelantado` con tres estados y no dos.

Ningún doble escrito a mano habría tenido esas rarezas. Los dobles se escriben
desde la expectativa, y el punto es que la expectativa estaba mal.

Este script cubre la otra mitad: **que las filas reales sobrevivan el viaje**.

## Qué comprueba, en orden de importancia

  FASE 0 (Qué corte de la fuente está publicado ahora. Es precondición: si
           `corte()` no funciona contra la API real, D10 y D11 no tienen piso.
  FASE 1) Toda fila real pasa por `preparar()` sin explotar.
  FASE 2 (La ida y vuelta es exacta: lo escrito se relee idéntico.
           *** La que valida la deduplicación por bytes (D3). Si el rehasheo
           no coincide, está construida sobre arena. ***
  FASE 3) La tasa de descarte sobre datos reales. Dos corridas seguidas de la
           misma ventana deben dar ~100% de descarte en la segunda.
  FASE 4: Nada de lo que se guardó es un dato personal (H7).

## Por qué no está en CI

Depende de la red y de una API de terceros. Un test que falla porque
`datos.gov.co` está caído enseña a ignorar los tests. Se corre a mano cuando
cambia algo del extractor, de `columnas.py` o de la canonicalización.

## Por qué la ventana está cerrada en el pasado

`fecha_de_firma` tiene ~1 día de rezago de publicación, y llegó a observarse
hasta cuatro. Una ventana que termina hoy puede venir vacía sin que nada esté
roto, y sin filas **todos los chequeos pasan por vacuidad**: cero es igual a
cero, una lista vacía no tiene discrepancias y ninguna columna personal llegó
porque no llegó ninguna columna. Un script que aprueba sin haber verificado
nada da confianza falsa justo el día que algo se rompió.

Por eso la ventana por defecto es un día hábil ya cerrado, igual que en
`verificar_extraccion.py`, y **el script aborta si viene vacía**.

Uso:

    uv run python scripts/verificar_carga_raw.py
    uv run python scripts/verificar_carga_raw.py --paginas 3 --desde 2024-02-06 --dias 3

**Consume el doble de peticiones de lo que parece.** La fase 3 descarga la
misma ventana dos veces, a propósito: es la única forma de comprobar que la
segunda corrida descarta todo. Y a diferencia de la fase 1, **no está acotada
por `--paginas`**: baja la ventana entera. Por eso se mide el tamaño con un
`count(*)` antes de empezar.

Referencias: `exploration/03_decisiones_capa_raw.md`: D3 (deduplicación por
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
from secop_analytics.flujos import _rango, contratos_nuevos
from secop_analytics.hashing import canonicalizar, hashear, preparar, verificar_linea
from secop_analytics.paginacion import contar, corte

# Un día hábil ya cerrado, el mismo que usa `verificar_extraccion.py`. No se
# usa "ayer": `fecha_de_firma` tiene ~1 día de rezago y llegó a observarse
# hasta cuatro, así que una ventana pegada a hoy puede venir vacía sin que nada
# esté roto, y una ventana vacía aprueba todas las fases por vacuidad.
DESDE_POR_DEFECTO = date(2024, 2, 6)
DIAS_POR_DEFECTO = 1

# Cuántas filas se consideran demasiadas para la fase 3, que baja la ventana
# entera dos veces y no respeta `--paginas`.
MAXIMO_RAZONABLE = 20_000


def titulo(texto: str) -> None:
    print(f"\n{'=' * 68}\n{texto}\n{'=' * 68}", flush=True)


# --------------------------------------------------------------------------


def fase_0() -> tuple[bool, str | None]:
    """El corte de la fuente. Precondición de D10 y D11.

    Es la única fase que no verifica la capa raw sino la pregunta sobre la que
    D10 y D11 se apoyan. Va primera porque cuesta una petición y porque si
    falla, lo que sigue se puede leer igual pero las decisiones no tienen piso.

    Verifica tres cosas, en orden de qué tan probable es que se rompan:

    1. **Que la consulta funcione contra la API real.** `:updated_at` lleva dos
       puntos y `requests` lo codifica como %3A; los alias con `as` llevan
       espacios que se codifican como `+`. Nada de eso está probado contra
       Socrata y **ningún doble lo probaría**, porque el doble devolvería lo
       que uno espera. Es exactamente el hueco que este script existe para
       cubrir.
    2. **Que `min = max`**, o sea H2 una vez más, y sobre el universo completo.
    3. **Que dos lecturas seguidas coincidan.** Si difieren en segundos, la
       fuente se estaría regenerando justo ahora, que es el único caso donde
       `confiable` puede dar falso sin que H2 esté roto, y sería la primera
       observación del proyecto dentro de la ventana de regeneración.

    Devuelve el veredicto y el valor del corte, que hay que anotar en el
    registro de sondeo con la fecha y la hora colombiana.
    """
    titulo("FASE 0: Qué corte de la fuente está publicado")
    print("`:updated_at` es idéntico en las 5,96M de filas porque el dataset se")
    print("reemplaza entero (H2). Ese valor identifica al corte, y es lo que")
    print("dispara el flujo 3 (D11) y anota la procedencia en raw (D10).\n")

    try:
        primero = corte()
    except Exception as error:  # noqa: BLE001: acá interesa el mensaje, no el tipo
        print(f"  ERROR la consulta falló: {type(error).__name__}: {error}")
        print("     Si es un 400, sospechar de la codificación de `:updated_at`")
        print("     o de los alias del `$select`. Probar la URL a mano.")
        return False, None

    print(f"  más viejo: {primero.mas_viejo}")
    print(f"  más nuevo: {primero.mas_nuevo}")

    if not primero.confiable:
        print("  LOS DOS EXTREMOS DIFIEREN. Dos explicaciones posibles y este")
        print("    script no las distingue: o la consulta cayó mientras la")
        print("    fuente se regeneraba, o H2 dejó de valer. Lo segundo tumba")
        print("    los tres flujos. Repetir en unos minutos: si sigue distinto,")
        print("    es lo segundo.")
        return False, primero.mas_nuevo

    segundo = corte()
    if segundo.mas_nuevo != primero.mas_nuevo:
        print(f"  cambió entre dos lecturas seguidas: {segundo.mas_nuevo}")
        print("    La fuente se está regenerando AHORA. Es la primera")
        print("    observación del proyecto dentro de la ventana, y vale la")
        print("    pena anotarla: no hay ninguna igual.")
        return False, segundo.mas_nuevo

    print("  OK min = max, y estable entre dos lecturas")
    print(f"\n  ANOTAR EN EL REGISTRO DE SONDEO:  {hoy()}  /  {primero.mas_nuevo}")
    return True, primero.mas_nuevo


def fase_1(desde: date, hasta: date, paginas_max: int) -> tuple[list[dict], bool]:
    """Toda fila real pasa por `preparar()` sin explotar.

    Devuelve también el veredicto: es la fase más importante y antes no
    participaba del código de salida. Podía imprimir que fallaron mil filas y
    el script terminaba en 0.
    """
    titulo("FASE 1: Las filas reales sobreviven la canonicalización")

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
        print(f"  ERROR FALLARON {len(fallos)}:")
        for id_contrato, motivo in fallos[:5]:
            print(f"     {id_contrato}: {motivo[:120]}")
        return recogidas, False

    print("  OK ninguna falló")
    return recogidas, True


def fase_2(recogidas: list[dict]) -> tuple[bool, list[dict]]:
    """La ida y vuelta es exacta. Es la que valida D3.

    Devuelve también las observaciones releídas del disco: son lo que la fase 4
    necesita para comprobar sobre lo GUARDADO y no sobre lo recibido.
    """
    titulo("FASE 2: Ida y vuelta sobre datos reales")
    print("Si el hash de lo releído no coincide con el de lo escrito, la")
    print("deduplicación está construida sobre arena.\n")

    if not recogidas:
        print("  (sin filas que verificar)")
        return True, []

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
        print(f"  escritas {len(esperados):,} / releídas {len(observaciones):,}")

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
                    print(f"     ERROR {id_contrato}: {observacion['hash']} -> {rehasheado}")

        peso = sum(f.stat().st_size for f in destino.directorio.glob("*.gz"))
        print(f"  comprimido: {peso/1024:,.0f} KB ({peso/len(observaciones):.0f} bytes/fila)")

        if discrepancias:
            print(f"  ERROR {discrepancias} filas no rehashean igual")
            return False, observaciones
        print("  OK todas rehashean idéntico")
        return True, observaciones
    finally:
        shutil.rmtree(base)


def fase_3(desde: date, hasta: date) -> bool:
    """La tasa de descarte real. La segunda corrida no debe escribir nada."""
    titulo("FASE 3: Deduplicación sobre datos reales")
    print("Dos corridas seguidas de la MISMA ventana: la segunda debe descartar")
    print("todo. Si no, algo de la canonicalización no es determinista sobre")
    print("datos verdaderos, y eso ningún doble lo detecta.\n")

    base = Path(tempfile.mkdtemp())
    try:
        indice = base / "indice.duckdb"
        fecha = str(hasta)

        # Esta fase NO respeta `--paginas`: `cargar_nuevos` baja la ventana
        # entera, y acá se baja dos veces. Se mide antes con un `count(*)` del
        # servidor en vez de descubrirlo a mitad de camino.
        esperadas = contar(_rango("fecha_de_firma", desde, hasta))
        print(f"  la ventana tiene {esperadas:,} filas / se bajan dos veces")
        if esperadas > MAXIMO_RAZONABLE:
            print(
                f"  más de {MAXIMO_RAZONABLE:,} filas. El script SIGUE, pero "
                "considerá achicar la ventana: la garantía la da que la segunda "
                "corrida descarte, no cuántas filas se bajen."
            )

        primera = cargar_nuevos(
            desde, hasta, fecha_extraccion=fecha,
            raiz=base / "raw1", ruta_indice=indice,
        )
        print(f"  primera: {primera.recibidas:,} recibidas / {primera.escritas:,} escritas")

        # Misma ventana y **mismo índice**, pero otra raíz: sin eso, la segunda
        # corrida vería `_COMPLETO` de la primera y no haría nada, que es
        # justamente lo que este test no quiere demostrar.
        segunda = cargar_nuevos(
            desde, hasta, fecha_extraccion=fecha,
            raiz=base / "raw2", ruta_indice=indice,
        )
        print(f"  segunda: {segunda.recibidas:,} recibidas / {segunda.escritas:,} escritas")
        print(f"  descarte de la segunda: {segunda.tasa_descarte:.1%}")

        if segunda.recibidas and segunda.escritas:
            print(f"  ERROR escribió {segunda.escritas} filas que no cambiaron")
            return False
        print("  OK descarte total, como corresponde")
        return True
    finally:
        shutil.rmtree(base)


def fase_4(observaciones: list[dict]) -> bool:
    """Ningún dato personal quedó guardado. H7: el filtro corre en el `$select`.

    Mira lo que se releyó del disco, no lo que devolvió la API. El título decía
    "en lo guardado" y comprobaba lo recibido; hoy son lo mismo, pero el día que
    dejen de serlo el chequeo tiene que estar del lado correcto.
    """
    titulo("FASE 4: Ningún dato personal en lo guardado")
    print("H7: el filtro corre en el `$select`, no después. Esto verifica que")
    print("efectivamente no viajaron, en vez de confiar en que no viajaron.\n")

    if not observaciones:
        print("  (sin filas que verificar)")
        return True

    presentes = {
        c for o in observaciones for c in o["datos"] if c in PERSONALES
    }
    if presentes:
        print(f"  ERROR llegaron {len(presentes)} columnas personales: {sorted(presentes)}")
        return False
    print(f"  OK ninguna de las {len(PERSONALES)} columnas personales llegó")
    return True


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paginas", type=int, default=2,
                        help="Cuántas páginas traer como máximo en la fase 1 (defecto 2).")
    parser.add_argument("--desde", type=date.fromisoformat, default=DESDE_POR_DEFECTO,
                        help=f"Inicio de la ventana (defecto {DESDE_POR_DEFECTO}).")
    parser.add_argument("--dias", type=int, default=DIAS_POR_DEFECTO,
                        help=f"Ancho de la ventana en días (defecto {DIAS_POR_DEFECTO}).")
    args = parser.parse_args()

    if args.dias < 1:
        parser.error(
            "La ventana necesita al menos un día. Con cero, `_rango()` la "
            "rechaza por vacía y el error sale como traza a mitad de la fase 1."
        )

    load_dotenv()

    desde = args.desde
    hasta = desde + timedelta(days=args.dias)

    print("\nVerificación de la capa raw contra la API real")
    print(f"hoy en Colombia: {hoy()}  /  hoy del sistema: {date.today()}")
    if hoy() != date.today():
        print("  difieren: estás en la franja donde UTC ya cambió de día. La")
        print("    fecha que manda es la colombiana (ver R2).")

    # Va antes de la fase 1 y antes de la guarda de la ventana vacía: cuesta
    # una petición, no depende del rango, y su valor hay que anotarlo aunque el
    # resto del script no llegue a correr.
    ok_0, valor_del_corte = fase_0()

    recogidas, ok_1 = fase_1(desde, hasta, args.paginas)

    # La guarda contra el aprobado vacuo. Sin filas, las fases 2, 3 y 4 pasan
    # las tres: cero es igual a cero, una lista vacía no tiene discrepancias y
    # ninguna columna personal llegó porque no llegó ninguna columna. El script
    # diría que está todo bien sin haber verificado nada.
    if not recogidas:
        print(
            f"\nERROR La ventana {desde} a {hasta} no trajo filas.\n"
            "   No se puede verificar nada con cero filas: las otras tres fases\n"
            "   pasarían por vacuidad y el script aprobaría sin haber mirado.\n\n"
            "   Revisá si el rango cayó en un feriado, o si el filtro dejó de\n"
            "   funcionar contra la fuente. Probá otro día hábil con --desde.\n\n"
            f"   La fase 0 sí corrió: corte {valor_del_corte}, "
            f"{'ok' if ok_0 else 'CON PROBLEMAS'}.",
            file=sys.stderr,
        )
        return 1

    ok_2, observaciones = fase_2(recogidas)
    resultados = [
        ("0 / corte de la fuente", ok_0),
        ("1 / canonicalización", ok_1),
        ("2 / ida y vuelta", ok_2),
        ("3 / deduplicación", fase_3(desde, hasta)),
        ("4 / datos personales", fase_4(observaciones)),
    ]

    titulo("RESUMEN")
    for nombre, paso in resultados:
        print(f"  {'OK' if paso else 'ERROR'}  fase {nombre}")

    if all(paso for _, paso in resultados):
        print(f"\n  La capa raw se comporta igual contra datos reales que en los "
              f"tests, sobre {len(recogidas):,} filas.")
        return 0
    print("\n  Algo se comporta distinto con datos reales. Los dobles no bastan.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())