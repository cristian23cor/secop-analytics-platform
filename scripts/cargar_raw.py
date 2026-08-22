"""Orquestador de la capa raw: une extracción, deduplicación y escritura.

Es punto de entrada, así que vive en `scripts/` y carga el `.env`. Ningún
módulo de `src/` lo hace.

## Lo único que este archivo agrega a los tres módulos

**El orden.** Primero se escribe la línea al archivo, después se registra en el
índice. Está en `_procesar_paginas()`, en dos líneas consecutivas, y es visible
de un vistazo. Al revés, un fallo a mitad dejaría el índice diciendo "ya vi este
contrato" con la fila en ninguna parte — y la fuente ya se sobrescribió esta
noche, así que se perdió para siempre.

Fue la razón de separar `indice.py` de `escritura.py` (I4): que el orden viva
acá y se pueda auditar leyendo veinte líneas, en vez de tener que confiar en que
un módulo no lo invirtió por dentro.

## Las tres cadencias no se unifican, a propósito

Los flujos 1 y 2 reciben una **ventana de cambio**: preguntan qué se movió entre
dos fechas, y la fuente devuelve lo mismo hoy que dentro de un mes.

El flujo 3 recibe una **partición del universo vivo**: pregunta cómo están AHORA
los contratos que todavía pueden cambiar. Sus parámetros de fecha sirven para
paralelizar, no para viajar en el tiempo.

Una interfaz común `orquestar(flujo, desde, hasta)` borraría esa distinción, y
`refresco_de_vivos` con fechas viejas **parecería** un backfill legítimo. Es la
clase de error que no falla: produce archivos. Por eso hay tres ramas
explícitas, y el guardarraíl vive acá — `flujos.py` no puede tenerlo porque ahí
no se sabe qué día se está escribiendo.

Uso:

    uv run python scripts/cargar_raw.py --flujo nuevos --desde 2026-08-20 --hasta 2026-08-21
    uv run python scripts/cargar_raw.py --flujo eventos --desde 2026-08-20 --hasta 2026-08-21
    uv run python scripts/cargar_raw.py --flujo vivos
    uv run python scripts/cargar_raw.py --flujo vivos --firmados-desde 2020-01-01 --firmados-hasta 2020-02-01

Referencias: `exploration/03_decisiones_capa_raw.md` — D1 a D8 para la
arquitectura, I1 a I4 para la implementación, R1 y R2 para las restricciones.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from secop_analytics.escritura import ParticionRaw
from secop_analytics.flujos import (
    Flujo,
    contratos_nuevos,
    eventos_contractuales,
    refresco_de_vivos,
)
from secop_analytics.hashing import preparar
from secop_analytics.indice import IndiceHashes
from secop_analytics.paginacion import Fila

RAIZ_RAW = Path("datos/raw")
RUTA_INDICE = Path("datos/indice_hashes.duckdb")

# `fecha_extraccion` es el día COLOMBIANO, no el del reloj del sistema.
#
# Colombia es UTC−5, así que entre las 19:00 y la medianoche hora local, UTC ya
# está en el día siguiente. Con `date.today()` —que devuelve la fecha del
# sistema, y en un contenedor o en Airflow eso suele ser UTC— una corrida a las
# 20:00 del 21 en Colombia escribiría en `fecha_extraccion` del 22, partiendo el
# mismo día de negocio en dos particiones sin avisar.
#
# El momento en que las dos convenciones divergen es justamente cuando alguien
# corre el cargador a mano por la tarde-noche: depurando, rehaciendo algo,
# probando. O sea cuando menos va a sospechar de la fecha.
#
# La fuente se regenera a las 04:41 COT (H24), así que el día colombiano es
# además el que coincide con lo que un analista llamaría "el corte del 21".
ZONA = ZoneInfo("America/Bogota")


def hoy() -> date:
    """La única definición de "hoy" del pipeline.

    Tiene que ser una sola función y no dos llamadas sueltas: el orquestador la
    usa para nombrar la partición y el guardarraíl del flujo 3 (R1) para decidir
    si una corrida es backfill. Si esas dos se calcularan con criterios distintos, el
    guardarraíl rechazaría corridas legítimas durante cinco horas al día.
    """
    return datetime.now(ZONA).date()


# --------------------------------------------------------------------------
# Resultado
# --------------------------------------------------------------------------

@dataclass
class Resultado:
    """Lo que hay que saber sin volver a correr."""

    flujo: str
    particion: str
    recibidas: int = 0
    escritas: int = 0
    paginas: int = 0
    segundos: float = 0.0

    @property
    def tasa_descarte(self) -> float:
        """Proporción de filas que no cambiaron. **Es un canario.**

        ⚠ En una corrida que retomó una partición a medias, `recibidas` cuenta
        solo lo bajado en este intento, no lo de antes. La tasa sigue siendo
        útil como señal, pero no es comparable contra una corrida completa.

        En el flujo 3 debería rondar el 99%. Una caída brusca no significa que
        medio país firmó contratos: significa que algo cambió en la fuente —una
        columna nueva, un formato de número, un reordenamiento— y eso invalida
        todos los hashes anteriores y llena raw de duplicados que parecen
        cambios.

        Al 100% durante varios días seguidos es lo contrario: puede que la
        fuente dejó de actualizarse y nadie se enteró.
        """
        if not self.recibidas:
            return 0.0
        return 1 - (self.escritas / self.recibidas)

    def imprimir(self) -> None:
        print(f"\n  {'─' * 58}")
        print(f"  flujo:      {self.flujo}")
        print(f"  partición:  {self.particion}")
        print(f"  recibidas:  {self.recibidas:,} en {self.paginas} páginas")
        print(f"  escritas:   {self.escritas:,}")
        print(f"  descarte:   {self.tasa_descarte:.1%}")
        print(f"  tiempo:     {self.segundos:.1f}s")
        print(f"  {'─' * 58}")


# --------------------------------------------------------------------------
# El bucle: idéntico para los tres flujos
# --------------------------------------------------------------------------

def _procesar_paginas(
    abrir_paginas: Callable[[str | None], Iterator[list[Fila]]],
    *,
    flujo: Flujo,
    fecha_extraccion: str,
    particion: str,
    raiz: Path,
    ruta_indice: Path,
) -> Resultado:
    """Consume páginas, deduplica y escribe. El único lugar con el orden crítico.

    Recibe una **fábrica** de páginas y no un generador ya construido, porque el
    punto de arranque solo se conoce después de abrir la partición: si quedó a
    medias, se retoma desde el cursor que dejó anotado en su manifiesto.
    """
    resultado = Resultado(flujo=flujo.value, particion=particion)
    inicio = time.perf_counter()

    with IndiceHashes(ruta_indice) as indice, ParticionRaw(
        raiz,
        flujo=flujo.value,
        fecha_extraccion=fecha_extraccion,
        particion=particion,
    ) as destino:
        if destino.esta_completa:
            print("  ya estaba completa, no se rehace", flush=True)
            return resultado

        if destino.cursor:
            print(
                f"  retomando desde {destino.cursor}: no se vuelven a bajar "
                f"las {destino.lineas_escritas:,} filas ya escritas",
                flush=True,
            )

        for pagina in abrir_paginas(destino.cursor):
            resultado.paginas += 1
            resultado.recibidas += len(pagina)
            ultimo_id: str | None = None

            for fila in pagina:
                id_contrato, huella, linea = preparar(
                    fila, flujo=flujo.value, fecha_extraccion=fecha_extraccion
                )
                ultimo_id = id_contrato

                if indice.cambio(id_contrato, huella):
                    # ── EL ORDEN. No invertir. ──────────────────────────
                    destino.escribir(linea)                        # 1. archivo
                    indice.registrar(                              # 2. índice
                        id_contrato,
                        huella,
                        fecha_extraccion=fecha_extraccion,
                        flujo=flujo.value,
                    )
                    # ────────────────────────────────────────────────────
                    resultado.escritas += 1

            destino.punto_de_control(cursor=ultimo_id)
            print(
                f"    página {resultado.paginas:>4}: "
                f"{resultado.recibidas:>8,} recibidas · "
                f"{resultado.escritas:>7,} escritas",
                flush=True,
            )

        destino.completar()

    resultado.segundos = time.perf_counter() - inicio
    return resultado


# --------------------------------------------------------------------------
# Las tres ramas
# --------------------------------------------------------------------------

def cargar_nuevos(desde: date, hasta: date, **comunes) -> Resultado:
    """Contratos firmados en la ventana. Reprocesable: la fuente no cambia."""
    return _procesar_paginas(
        lambda cursor: contratos_nuevos(desde, hasta, desde_cursor=cursor),
        flujo=Flujo.NUEVOS,
        particion=_nombrar(desde, hasta),
        **comunes,
    )


def cargar_eventos(desde: date, hasta: date, **comunes) -> Resultado:
    """Contratos con evento contractual en la ventana. También reprocesable."""
    return _procesar_paginas(
        lambda cursor: eventos_contractuales(desde, hasta, desde_cursor=cursor),
        flujo=Flujo.EVENTOS,
        particion=_nombrar(desde, hasta),
        **comunes,
    )


def cargar_vivos(
    firmados_desde: date | None,
    firmados_hasta: date | None,
    *,
    fecha_extraccion: str,
    **comunes,
) -> Resultado:
    """Refresco del universo vivo. **NO reprocesable hacia atrás (R1).**

    El guardarraíl no es alcanzable desde la línea de comandos, porque `main()`
    siempre usa `hoy()`. Está para el día que alguien agregue un `--fecha` o
    llame a esta función desde un DAG.
    """
    hoy_colombia = hoy().isoformat()
    if fecha_extraccion != hoy_colombia:
        raise ValueError(
            f"El flujo 3 no admite backfill. Se pidió escribir en "
            f"fecha_extraccion={fecha_extraccion} y hoy en Colombia es "
            f"{hoy_colombia}.\n"
            "Este flujo pregunta cómo están AHORA los contratos vivos; ese "
            "estado ya se destruyó. Correrlo con fecha vieja escribiría el hoy "
            "con fecha de ayer, que es peor que no correr nada: mete una "
            "mentira en raw."
        )

    if firmados_desde is None:
        particion = "completo"
    else:
        particion = _nombrar(firmados_desde, firmados_hasta)

    return _procesar_paginas(
        lambda cursor: refresco_de_vivos(
            firmados_desde=firmados_desde,
            firmados_hasta=firmados_hasta,
            desde_cursor=cursor,
        ),
        flujo=Flujo.REFRESCO,
        fecha_extraccion=fecha_extraccion,
        particion=particion,
        **comunes,
    )


def _nombrar(desde: date, hasta: date | None) -> str:
    """Nombre de partición legible: dice qué se pidió, sin abrir el manifiesto."""
    if hasta is None:
        return desde.isoformat()
    return f"{desde.isoformat()}_a_{hasta.isoformat()}"


# --------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Carga una partición de la capa raw.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--flujo", required=True, choices=["nuevos", "eventos", "vivos"])
    parser.add_argument("--desde", type=date.fromisoformat, help="Flujos nuevos/eventos.")
    parser.add_argument("--hasta", type=date.fromisoformat, help="Flujos nuevos/eventos.")
    parser.add_argument("--firmados-desde", type=date.fromisoformat, help="Partición del flujo vivos.")
    parser.add_argument("--firmados-hasta", type=date.fromisoformat, help="Partición del flujo vivos.")
    parser.add_argument("--raiz", type=Path, default=RAIZ_RAW)
    parser.add_argument("--indice", type=Path, default=RUTA_INDICE)
    args = parser.parse_args()

    load_dotenv()  # punto de entrada: acá sí

    fecha_extraccion = hoy().isoformat()  # día colombiano, ver `hoy()`
    comunes = {
        "fecha_extraccion": fecha_extraccion,
        "raiz": args.raiz,
        "ruta_indice": args.indice,
    }

    print(f"\ncarga raw · flujo={args.flujo} · extracción={fecha_extraccion}\n")

    try:
        if args.flujo == "vivos":
            if (args.firmados_desde is None) != (args.firmados_hasta is None):
                parser.error(
                    "La partición necesita ambos bordes, o ninguno. Un borde "
                    "suelto produce un recorrido que parece acotado y no lo está."
                )
            resultado = cargar_vivos(args.firmados_desde, args.firmados_hasta, **comunes)
        else:
            if args.desde is None or args.hasta is None:
                parser.error(f"El flujo {args.flujo} necesita --desde y --hasta.")
            cargar = cargar_nuevos if args.flujo == "nuevos" else cargar_eventos
            resultado = cargar(args.desde, args.hasta, **comunes)
    except ValueError as error:
        print(f"\n❌ {error}", file=sys.stderr)
        return 1

    resultado.imprimir()

    # El canario. Ver `Resultado.tasa_descarte`.
    if resultado.recibidas > 1000 and resultado.tasa_descarte < 0.5:
        print(
            "\n⚠ Descarte inusualmente bajo. Si esto no coincide con un día de "
            "actividad excepcional, revisá si cambió el esquema de la fuente: "
            "una columna nueva o un formato distinto invalidan todos los hashes "
            "anteriores y llenan raw de duplicados que parecen cambios.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())