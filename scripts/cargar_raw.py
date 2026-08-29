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

from secop_analytics.escritura import ParticionRaw, ingestas_previas
from secop_analytics.flujos import (
    Flujo,
    contratos_nuevos,
    eventos_contractuales,
    refresco_de_vivos,
)
from secop_analytics.hashing import preparar
from secop_analytics.indice import IndiceHashes
from secop_analytics.paginacion import Corte, ErrorDeConfiguracion, Fila, corte

RAIZ_RAW = Path("datos/raw")
RUTA_INDICE = Path("datos/indice_hashes.duckdb")

# Umbrales del canario. Ver `_advertencia_de_descarte()`.
UMBRAL_DE_DESCARTE = 0.5
MINIMO_PARA_EL_CANARIO = 1_000

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
# La fuente se regenera de madrugada, en una ventana de ~35 minutos (H24), así
# que el día colombiano es además el que coincide con lo que un analista
# llamaría "el corte del 21".
#
# ⚠ Pero `fecha_extraccion` es cuándo bajamos los datos, NO qué estado vimos.
# La fuente no se regenera todos los días (H34), así que dos particiones con
# fechas distintas pueden contener el mismo estado. Qué se vio lo dice el corte,
# que va al manifiesto (D10) y decide si se corre (D11).
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
    # Cuántos contratos conocía el índice al arrancar. Informativo: sirve para
    # el mensaje del canario, no para decidir si canta.
    conocidos_al_inicio: int = 0
    # Cuántas de las filas RECIBIDAS ya estaban en el índice. Esta es la que
    # decide: un descarte del 0% significa cosas opuestas según si las filas
    # eran conocidas (los hashes dejaron de servir) o nuevas (partición nueva).
    conocidas: int = 0

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

        ⚠ **El razonamiento de arriba vale solo para el flujo 3.** En los flujos
        1 y 2 el descarte bajo es lo correcto: el flujo 1 trae contratos recién
        firmados, que el índice nunca vio, y el flujo 2 trae contratos a los que
        les pasó algo, o sea que alguna columna se movió. Los dos escriben casi
        todo lo que reciben y los dos superan las 1.000 filas diarias. Por eso
        `_advertencia_de_descarte()` no los mira.

        Al 100% durante varios días seguidos es lo contrario: puede que la
        fuente dejó de actualizarse y nadie se enteró. Eso **no se comprueba
        acá**: hace falta comparar contra corridas anteriores, y este objeto
        solo conoce la suya.
        """
        if not self.recibidas:
            return 0.0
        return 1 - (self.escritas / self.recibidas)

    def imprimir(self) -> None:
        print(f"\n  {'─' * 58}")
        print(f"  flujo:      {self.flujo}")
        print(f"  partición:  {self.particion}")
        print(f"  recibidas:  {self.recibidas:,} en {self.paginas} páginas")
        print(f"  conocidas:  {self.conocidas:,}")
        print(f"  escritas:   {self.escritas:,}")
        # Toda fila descartada es necesariamente conocida: `cambio()` solo da
        # falso si el contrato está en `_conocidos` o en `_pendientes`. Así que
        # `recibidas - escritas` son exactamente las conocidas que no cambiaron,
        # y esta segunda tasa no necesita ningún contador nuevo.
        #
        # Es la que dice algo cuando casi todas las filas son nuevas: la tasa
        # global se diluye, ésta no.
        if self.conocidas:
            sobre_conocidas = (self.recibidas - self.escritas) / self.conocidas
            print(
                f"  descarte:   {self.tasa_descarte:.1%}  "
                f"({sobre_conocidas:.2%} sobre las conocidas)"
            )
        else:
            print(f"  descarte:   {self.tasa_descarte:.1%}  (ninguna conocida)")
        print(f"  tiempo:     {self.segundos:.1f}s")
        print(f"  {'─' * 58}")


def _advertencia_de_descarte(resultado: Resultado) -> str | None:
    """El canario, con las tres corridas donde NO debe cantar.

    Una alerta ruidosa enseña a ignorarla, y esta protege la señal más
    importante del pipeline: que el esquema de la fuente cambió y todos los
    hashes quedaron inservibles. Las exclusiones son parte de la alerta, no
    concesiones.

    1. **Flujos 1 y 2.** El descarte bajo es su comportamiento correcto, y los
       dos pasan las 1.000 filas por día: sin esta exclusión la advertencia
       salía en las dos corridas diarias, todas las noches, sin que nada
       estuviera mal.
    2. **Ninguna fila conocida.** No hay nada contra qué comparar: estos
       contratos nunca se habían visto, así que escribirlos todos es correcto.
       Cubre la primera corrida y, sobre todo, **cada partición nueva del flujo
       3** — que la primera noche son tres de cuatro. Preguntar en cambio si el
       índice está vacío no alcanza: al barrer la segunda partición el índice ya
       tiene los contratos de la primera, que son otros.
    3. **Muestras chicas.** Bajo ese piso la tasa es ruido.
    """
    if resultado.flujo != Flujo.REFRESCO.value:
        return None
    if resultado.conocidas == 0:
        return None
    if resultado.recibidas <= MINIMO_PARA_EL_CANARIO:
        return None
    if resultado.tasa_descarte >= UMBRAL_DE_DESCARTE:
        return None

    return (
        f"\n⚠ Descarte del {resultado.tasa_descarte:.1%} en el flujo 3, cuando "
        f"debería rondar el 99%.\n"
        f"  {resultado.conocidas:,} de las {resultado.recibidas:,} filas "
        "recibidas YA estaban en el índice, así que no es una partición "
        "nueva.\n"
        "  Si no coincide con un día de actividad excepcional, revisá si cambió "
        "el esquema\n  de la fuente: una columna nueva o un formato distinto "
        "invalidan todos los hashes\n  anteriores y llenan raw de duplicados "
        "que parecen cambios."
    )


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
    corte_de_la_fuente: Corte | None = None,
    corte_anterior: str | None = None,
) -> Resultado:
    """Consume páginas, deduplica y escribe. El único lugar con el orden crítico.

    Recibe una **fábrica** de páginas y no un generador ya construido, porque el
    punto de arranque solo se conoce después de abrir la partición: si quedó a
    medias, se retoma desde el cursor que dejó anotado en su manifiesto.
    """
    resultado = Resultado(flujo=flujo.value, particion=particion)
    inicio = time.perf_counter()

    # D10: el corte se anota en los TRES flujos, aunque solo el 3 lo lea para
    # decidir si corre. Escribir es gratis —la consulta ya se hizo— y el día que
    # haga falta saber de qué estado venía una partición del flujo 1, el dato va
    # a estar. La asimetría es deliberada: se escribe en todas partes, se lee en
    # una sola.
    #
    # En `None` no se anota nada. Es el caso de quien llama a estas funciones
    # sin haber consultado la fuente —los tests, un script suelto— y vale la
    # misma regla de migración que para las particiones viejas: desconocido no
    # bloquea y no inventa.
    with IndiceHashes(ruta_indice) as indice, ParticionRaw(
        raiz,
        flujo=flujo.value,
        fecha_extraccion=fecha_extraccion,
        particion=particion,
        corte_al_iniciar=corte_de_la_fuente.mas_nuevo if corte_de_la_fuente else None,
        corte_anterior=corte_anterior,
        corte_confiable=corte_de_la_fuente.confiable if corte_de_la_fuente else True,
    ) as destino:
        resultado.conocidos_al_inicio = indice.conocidos

        if destino.esta_completa:
            print("  ya estaba completa, no se rehace", flush=True)
            # Los segundos se asignan igual: abrir el índice y la partición
            # tarda, y un `tiempo: 0.0s` en pantalla parece un error.
            resultado.segundos = time.perf_counter() - inicio
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
                if indice.conoce(id_contrato):
                    resultado.conocidas += 1

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

        destino.completar(corte_al_terminar=_corte_final(corte_de_la_fuente))

    resultado.segundos = time.perf_counter() - inicio
    return resultado


def _corte_final(corte_de_la_fuente: Corte | None) -> str | None:
    """Vuelve a preguntar el corte, ya terminado el recorrido (D10).

    Si difiere del inicial, la partición quedó a caballo de dos regeneraciones.
    De eso avisa `ParticionRaw.completar()`.

    ⚠ **Acá el fallo de red NO aborta, y al principio sí.** Son momentos
    distintos y la asimetría cambia de lado: al arrancar, un 429 cuesta volver a
    escribir el comando; acá cuesta cincuenta minutos de barrido que se quedan
    sin `_COMPLETO` y por lo tanto ilegibles para dbt. Perder la marca es el
    error que sobra; perder el barrido entero es el que falta.
    """
    if corte_de_la_fuente is None:
        return None
    try:
        return corte().mas_nuevo
    except Exception as error:  # noqa: BLE001 — cualquier fallo de red vale igual
        print(
            f"\n  ⚠ no se pudo releer el corte al terminar: "
            f"{type(error).__name__}: {error}\n"
            f"     La partición se completa igual. Lo que se pierde es saber si "
            f"la fuente se regeneró durante la corrida.",
            flush=True,
        )
        return None


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
    raiz: Path,
    corte_de_la_fuente: Corte | None = None,
    forzar_corte_repetido: bool = False,
    **comunes,
) -> Resultado:
    """Refresco del universo vivo. **NO reprocesable hacia atrás (R1).**

    Tiene dos guardarraíles y protegen cosas distintas:

    - **R1, sobre la fecha.** Escribir el hoy con fecha de ayer mete una mentira
      en raw. No es alcanzable desde la línea de comandos, porque `main()`
      siempre usa `hoy()`; está para el día que alguien agregue un `--fecha` o
      llame a esta función desde un DAG.
    - **D11, sobre el corte.** Correr contra un estado de la fuente que esta
      misma partición ya ingirió entero cuesta cincuenta minutos y escribe una
      partición vacía. No falla, no avisa, y con la fuente saltando días (H34)
      es lo que pasa cada vez que se corre dos veces entre dos regeneraciones.
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

    corte_anterior: str | None = None
    if corte_de_la_fuente is not None:
        previas = ingestas_previas(
            raiz,
            flujo=Flujo.REFRESCO.value,
            particion=particion,
            corte=corte_de_la_fuente.mas_nuevo,
        )
        _avisar_de_ingestas_previas(
            previas,
            forzar=forzar_corte_repetido,
            destino_ya_completo=(
                raiz
                / f"flujo={Flujo.REFRESCO.value}"
                / f"fecha_extraccion={fecha_extraccion}"
                / f"particion={particion}"
                / "_COMPLETO"
            ).is_file(),
        )
        if previas.ya_ingerido is not None and not forzar_corte_repetido:
            raise CorteYaIngerido(
                f"Este corte de la fuente ya se ingirió entero.\n"
                f"  corte:     {corte_de_la_fuente.mas_nuevo}\n"
                f"  ya está:   {previas.ya_ingerido.directorio}\n"
                f"  partición: {particion}\n\n"
                "La fuente no se regenera todos los días (H34), así que correr "
                "de nuevo\n  bajaría 2,8 millones de filas para descartarlas "
                "todas y escribir una\n  partición vacía — cincuenta minutos "
                "sin ganar una observación.\n\n"
                "Si de verdad querés rehacerla: --forzar-corte-repetido"
            )
        # Es el mismo dato que alimenta el guardarraíl, así que no se busca dos
        # veces: el extremo izquierdo del intervalo que esta partición cubre.
        if previas.ultima is not None:
            corte_anterior = previas.ultima.corte

    return _procesar_paginas(
        lambda cursor: refresco_de_vivos(
            firmados_desde=firmados_desde,
            firmados_hasta=firmados_hasta,
            desde_cursor=cursor,
        ),
        flujo=Flujo.REFRESCO,
        fecha_extraccion=fecha_extraccion,
        particion=particion,
        raiz=raiz,
        corte_de_la_fuente=corte_de_la_fuente,
        corte_anterior=corte_anterior,
        **comunes,
    )


class CorteYaIngerido(RuntimeError):
    """D11: esta partición ya ingirió este estado de la fuente.

    Hereda de `RuntimeError` y no de `ValueError` a propósito. `main()` la
    atrapa aparte y devuelve un código distinto: no es un error del usuario ni
    del pipeline, es el guardarraíl haciendo su trabajo, y un DAG tiene que
    poder distinguir "no había nada nuevo" de "algo se rompió".
    """


def _avisar_de_ingestas_previas(
    previas, *, forzar: bool, destino_ya_completo: bool = False
) -> None:
    """Lo que hay que ver antes de esperar cincuenta minutos."""
    if previas.ultima is not None:
        print(
            f"  última ingesta de esta partición: "
            f"{previas.ultima.fecha_extraccion} · corte "
            f"{previas.ultima.corte or 'sin anotar'}",
            flush=True,
        )
    if previas.sin_corte_anotado:
        # Anteriores a D10. Se avisa y no se bloquea: tratarlas como
        # coincidentes frenaría corridas legítimas sobre todo lo que ya está en
        # disco, que es el error que falta.
        print(
            f"  ⚠ {len(previas.sin_corte_anotado)} partición(es) completas sin "
            f"corte anotado: son anteriores a D10 y no se pueden comparar.",
            flush=True,
        )
    if forzar and previas.ya_ingerido is not None:
        print(
            f"  ⚠ FORZADO: este corte ya estaba en "
            f"{previas.ya_ingerido.directorio}. Se corre igual.",
            flush=True,
        )

    if forzar and destino_ya_completo:
        # Hay DOS guardarraíles con la misma intención en capas distintas, y
        # esta bandera salta uno solo. `--forzar-corte-repetido` desactiva D11,
        # que mira el corte; `_solo_lectura` de `escritura.py` mira el
        # directorio y sigue en pie. La corrida no va a rehacer nada: baja cero
        # páginas y termina en segundos con salida normal.
        #
        # Decirlo es lo único que hace falta. Que la bandera no rehaga el mismo
        # directorio no es un defecto —ese caso lo cubre `_solo_lectura`, y
        # bien— pero terminar en cuatro segundos diciendo que corrió, cuando no
        # corrió, es el modo de fallo que este proyecto persigue en todas
        # partes: silencioso y con apariencia de éxito.
        #
        # Deliberadamente NO se ofrece rehacer el directorio desde acá.
        # Reescribir una partición completa borra observaciones que la fuente
        # ya no puede devolver, y eso no puede colgar de una bandera de línea
        # de comandos sin confirmación.
        print(
            "\n  ⚠ LA BANDERA NO ALCANZA, Y LA CORRIDA NO VA A REHACER NADA.\n"
            "     El corte se forzó, pero la partición de esta "
            "`fecha_extraccion` ya está\n     completa, y de eso se ocupa otro "
            "guardarraíl que la bandera no toca.\n"
            "     La corrida va a terminar en segundos sin bajar una página.\n\n"
            "     La bandera sirve para correr el MISMO corte en OTRO día, que "
            "es cuando\n     D11 muerde. Para rehacer esta partición hay que "
            "borrar su directorio\n     a mano — y eso destruye observaciones "
            "que la fuente ya no devuelve.",
            flush=True,
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
    parser.add_argument(
        "--forzar-corte-repetido",
        action="store_true",
        help=(
            "Corre el flujo 3 aunque esta partición ya haya ingerido este "
            "corte de la fuente. El nombre es largo a propósito: un `--forzar` "
            "a secas termina copiado en un DAG."
        ),
    )
    args = parser.parse_args()

    load_dotenv()  # punto de entrada: acá sí

    fecha_extraccion = hoy().isoformat()  # día colombiano, ver `hoy()`

    print(f"\ncarga raw · flujo={args.flujo} · extracción={fecha_extraccion}\n")

    # D10 y D11. Va antes de abrir el índice y la partición: si la fuente no se
    # puede consultar, no se sabe contra qué estado se estaría corriendo, y
    # arrancar cincuenta minutos sin saberlo es justo lo que D10 vino a
    # eliminar. Acá el fallo SÍ aborta — reintentar cuesta volver a escribir el
    # comando. Al terminar la asimetría se da vuelta: ver `_corte_final()`.
    try:
        corte_de_la_fuente = corte()
    except ErrorDeConfiguracion:
        raise
    except Exception as error:  # noqa: BLE001
        print(
            f"\n❌ No se pudo consultar el corte de la fuente: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 3

    print(f"  corte de la fuente: {corte_de_la_fuente.mas_nuevo}")
    if not corte_de_la_fuente.confiable:
        # `min != max`: o la consulta cayó mientras la fuente se regeneraba, o
        # H2 dejó de valer. No se distingue desde acá y no se aborta: la
        # observación se anota marcada, y descartarla sería perder algo que la
        # fuente ya no va a volver a ofrecer.
        print(
            f"  ⚠ EL CORTE NO ES CONFIABLE: los dos extremos difieren.\n"
            f"     más viejo: {corte_de_la_fuente.mas_viejo}\n"
            f"     más nuevo: {corte_de_la_fuente.mas_nuevo}\n"
            f"     O la fuente se está regenerando ahora mismo, o H2 dejó de "
            f"valer — lo\n     segundo tumbaría los tres flujos. Se corre "
            f"igual y queda marcado en el\n     manifiesto.",
            file=sys.stderr,
        )

    comunes = {
        "fecha_extraccion": fecha_extraccion,
        "raiz": args.raiz,
        "ruta_indice": args.indice,
        "corte_de_la_fuente": corte_de_la_fuente,
    }

    try:
        if args.flujo == "vivos":
            if (args.firmados_desde is None) != (args.firmados_hasta is None):
                parser.error(
                    "La partición necesita ambos bordes, o ninguno. Un borde "
                    "suelto produce un recorrido que parece acotado y no lo está."
                )
            resultado = cargar_vivos(
                args.firmados_desde,
                args.firmados_hasta,
                forzar_corte_repetido=args.forzar_corte_repetido,
                **comunes,
            )
        else:
            if args.desde is None or args.hasta is None:
                parser.error(f"El flujo {args.flujo} necesita --desde y --hasta.")
            cargar = cargar_nuevos if args.flujo == "nuevos" else cargar_eventos
            resultado = cargar(args.desde, args.hasta, **comunes)
    except CorteYaIngerido as error:
        # Código propio: no es un error del usuario ni del pipeline. Un DAG
        # tiene que poder distinguir "no había nada nuevo" de "algo se rompió".
        print(f"\n⏸  {error}", file=sys.stderr)
        return 4
    except ErrorDeConfiguracion as error:
        # Hereda de RuntimeError, así que el `except ValueError` de abajo no lo
        # veía y el fallo más probable de una primera corrida —falta el token en
        # el `.env`— salía como traza de Python en vez de como mensaje.
        print(f"\n❌ {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"\n❌ {error}", file=sys.stderr)
        return 1

    resultado.imprimir()

    # El canario. Ver `_advertencia_de_descarte()`.
    advertencia = _advertencia_de_descarte(resultado)
    if advertencia:
        print(advertencia, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())