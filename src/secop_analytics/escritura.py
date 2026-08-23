"""Escritura de una partición de raw: trozos comprimidos, manifiesto y cierre.

Estructura que produce (D2):

    raw/flujo=refresco_de_vivos/fecha_extraccion=2026-08-21/particion=2020-01/
        _manifiesto.json          progreso: cursor, trozos cerrados, algoritmo
        parte-0001.jsonl.gz
        parte-0002.jsonl.gz
        _COMPLETO                 única señal de "terminado"

## Por qué existe el nivel `particion=`

Corrige un defecto encontrado al escribir el orquestador. Con la ruta original
—solo `flujo` y `fecha_extraccion`— dos casos reales colisionaban **sin fallar
ruidosamente**:

- El flujo 3 se paraleliza lanzando varias particiones del universo vivo a la
  vez. Las cuatro corren la misma noche con el mismo flujo, así que las cuatro
  escribían en el mismo directorio: se pisaban `parte-0001.jsonl.gz` y se
  machacaban el manifiesto.
- En un backfill, las ~80 particiones mensuales se extraen todas hoy, así que
  todas caían en la misma `fecha_extraccion`. Peor: la segunda leía el
  manifiesto de la primera, creía estar reanudando y salteaba trozos.
  Producía un directorio que parece válido y está incompleto.

La causa: la ruta decía **cuándo** se extrajo pero no **qué pedazo**. Como el
manifiesto y `_COMPLETO` son por directorio, la ruta tiene que identificar
unívocamente una unidad de trabajo. La regla ahora se sostiene:

    un directorio = una unidad de trabajo = un escritor = un manifiesto

`particion` es el día en corrida diaria de los flujos 1 y 2 (redundante pero
consistente), el mes en backfill, y el rango de `fecha_de_firma` que le tocó a
cada proceso del flujo 3. Beneficio colateral: el nombre dice qué se pidió, sin
abrir el manifiesto.

## Por qué trozos y no un archivo

El trabajo caro no es escribir —con la deduplicación de D3 son ~2 MB
comprimidos por noche— sino las ~566 llamadas a la API, veinte minutos.

Los límites de trozo son los puntos donde el stream de compresión **se cierra**.
Un `.gz` cortado a la mitad tiene la cola corrupta y el archivo entero se vuelve
sospechoso; por eso no se apendea a un archivo abierto y se reanuda (era la
opción 2 de D2, descartada).

## Cómo se reanuda

`punto_de_control()` anota el último `id_contrato` visto. Al reabrir la
partición, `_retomar()` lo recupera en `self.cursor`, y el orquestador se lo
pasa al flujo como `desde_cursor`. Morir en la página 550 no cuesta volver a
bajar las 550.

**El cursor del manifiesto nunca va por delante del disco.** Anotar una página
no la confirma: el cursor solo pasa al manifiesto cuando el buffer está vacío,
o sea cuando esas líneas ya están dentro de un `.gz` cerrado. Si no lo fuera,
una muerte dura —`SIGKILL`, corte de luz, OOM; no una excepción, que el `with`
sí alcanza a cubrir— dejaría el manifiesto diciendo "ya pasé por acá" con las
filas evaporadas en memoria, y la reanudación no volvería a pedirlas nunca.

Por eso el trozo se cierra por **dos** cotas, la que ocurra primero: líneas
acumuladas y páginas desde el último cierre. La segunda hace falta porque en el
flujo 3 la primera no acota nada — de cada página de 5.000 filas se escriben
unas 50, así que llenar un trozo lleva ~100 páginas.

Y la condición para confirmar es "el buffer está vacío", no "se acaba de cerrar
un trozo": en una corrida donde no cambió nada no se escribe ninguna línea y
nunca se cierra un trozo, y con la otra regla el cursor no avanzaría jamás.

El cursor es el mismo mecanismo que hace avanzar la paginación normal: retomar
es idéntico a pedir la página siguiente. No hay un camino especial de
reanudación que pueda pudrirse sin que nadie lo note.

## Los dos invariantes que este módulo hace cumplir

1. **La línea se escribe antes de que el índice se entere.** Este módulo no
   conoce el índice: el orquestador llama primero acá y después a `registrar()`.
   Al revés, un fallo a mitad dejaría el índice diciendo "ya vi este contrato"
   con la fila en ninguna parte — y la fuente ya se sobrescribió.
2. **`_COMPLETO` aparece solo al final.** dbt lee únicamente particiones que lo
   tengan, o un `dbt run` disparado durante la ingesta lee media noche y produce
   números que nadie va a poder explicar.

## Atomicidad

Cada archivo se escribe con sufijo `.tmp` y se renombra al terminar. En POSIX el
renombrado dentro del mismo sistema de archivos es atómico: un lector nunca ve
un archivo a medio escribir, solo lo ve o no lo ve.

Referencias: `exploration/03_decisiones_capa_raw.md` — D2 (formato y trozos),
D3 (deduplicación) e I3 (dónde vive el manifiesto).
"""

from __future__ import annotations

import gzip
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Any, Final

from .hashing import ALGORITMO_HASH

NOMBRE_MANIFIESTO: Final[str] = "_manifiesto.json"
NOMBRE_COMPLETO: Final[str] = "_COMPLETO"

# Nivel 6 es el de por defecto de gzip. El 9 gana ~2% a cambio del doble de
# tiempo (medido: 1,81 MB contra 1,77 MB sobre 30.000 filas).
NIVEL_COMPRESION: Final[int] = 6

# Líneas por trozo. Es un compromiso entre cuánto se rehace tras un fallo y
# cuántos archivos quedan por partición. Con ~30.000 líneas escritas en una
# noche típica, 5.000 da unos seis trozos.
LINEAS_POR_TROZO: Final[int] = 5_000

# Páginas por trozo. Es la MISMA cota que `LINEAS_POR_TROZO` —cuánto trabajo
# puede perderse— medida en la otra unidad, y hace falta porque en el flujo 3
# contar líneas no acota nada: de cada página de 5.000 filas se escriben unas
# 50, así que llenar un trozo lleva ~100 páginas y hasta entonces esas líneas
# viven solo en memoria.
#
# 20 es una estimación, no una medición: supone ~50 líneas por página, que a su
# vez supone el 1% de cambio. Medir el número real en la primera corrida.
PAGINAS_POR_TROZO: Final[int] = 20


def _validar_particion(particion: str) -> str:
    """La partición va en una ruta, así que no puede traer separadores.

    Un `particion="2020/01"` crearía un nivel extra de directorio en silencio y
    rompería la regla de un directorio por unidad de trabajo. Falla temprano.
    """
    if not particion:
        raise ValueError(
            "La partición no puede estar vacía: es lo que distingue dos "
            "unidades de trabajo del mismo flujo en la misma fecha."
        )
    prohibidos = set('/\\ =') & set(particion)
    if prohibidos:
        raise ValueError(
            f"La partición {particion!r} tiene caracteres que rompen la ruta: "
            f"{sorted(prohibidos)}. Usá guiones."
        )
    return particion


class ParticionRaw:
    """Escribe una partición de raw. Reanudable y atómica.

        with ParticionRaw(base, flujo="refresco_de_vivos",
                          fecha_extraccion="2026-08-21",
                          particion="2020-01") as p:
            for pagina in flujo:
                for fila in pagina:
                    id_c, huella, linea = preparar(fila, ...)
                    if indice.cambio(id_c, huella):
                        p.escribir(linea)                    # 1. el archivo
                        indice.registrar(id_c, huella, ...)  # 2. el índice
                p.punto_de_control(cursor=ultimo_id)
            p.completar()

    Si `completar()` no se llama, la partición queda sin `_COMPLETO` y dbt la
    ignora. Eso es deliberado: una partición a medias no debe ser legible.
    """

    def __init__(
        self,
        base: Path | str,
        *,
        flujo: str,
        fecha_extraccion: str,
        particion: str,
        lineas_por_trozo: int = LINEAS_POR_TROZO,
        paginas_por_trozo: int = PAGINAS_POR_TROZO,
        verboso: bool = True,
    ) -> None:
        self.base = Path(base)
        self.flujo = flujo
        self.fecha_extraccion = fecha_extraccion
        self.particion = _validar_particion(particion)
        self.lineas_por_trozo = lineas_por_trozo
        if paginas_por_trozo < 1:
            raise ValueError(
                "`paginas_por_trozo` tiene que ser al menos 1. En cero el trozo "
                "no se cerraría nunca por páginas y volvería el problema que "
                "este parámetro existe para acotar."
            )
        self.paginas_por_trozo = paginas_por_trozo
        self.verboso = verboso

        self.directorio = (
            self.base
            / f"flujo={flujo}"
            / f"fecha_extraccion={fecha_extraccion}"
            / f"particion={self.particion}"
        )

        self._buffer: list[bytes] = []
        self._trozos_cerrados: int = 0
        self._lineas_totales: int = 0
        # Dos cursores, no uno. `_cursor` es el que va al manifiesto y solo
        # puede apuntar a un punto cuyas líneas YA están en disco;
        # `_cursor_pendiente` es la última página vista, que puede tener líneas
        # todavía en memoria. Confundirlos es el defecto que I5 corrige: el
        # manifiesto decía "ya pasé por acá" mientras las filas seguían en el
        # buffer, así que una muerte dura las perdía y la reanudación no las
        # volvía a pedir. La fuente ya se había sobrescrito.
        self._cursor: str | None = None
        self._cursor_pendiente: str | None = None
        self._paginas_desde_cierre: int = 0
        self._inicio: float = 0.0
        # Si la partición ya estaba completa al abrirla, este objeto no debe
        # tocar nada: sus contadores están en cero y guardar el manifiesto lo
        # pisaría con ceros, dejándolo mintiendo sobre los trozos que sí están
        # en disco. No falla y no avisa.
        self._solo_lectura: bool = False

    # -- ciclo de vida ----------------------------------------------------

    def __enter__(self) -> ParticionRaw:
        self.directorio.mkdir(parents=True, exist_ok=True)
        self._inicio = time.perf_counter()
        self._limpiar_temporales()
        self._retomar()
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        valor: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        if self._solo_lectura:
            return
        # Se cierra el trozo pendiente incluso si hubo excepción: esas líneas
        # ya se contaron como escritas y el índice puede haberlas registrado.
        # Perderlas sería el error caro.
        if self._buffer:
            self._cerrar_trozo()
        self._guardar_manifiesto()

    # -- reanudación ------------------------------------------------------

    def _limpiar_temporales(self) -> None:
        """Borra `.tmp` de una corrida que murió a mitad de escritura."""
        for restos in self.directorio.glob("*.tmp"):
            restos.unlink()

    def _retomar(self) -> None:
        """Lee el manifiesto y se posiciona después del último trozo cerrado.

        Se confía en el manifiesto y no en listar el directorio: un archivo
        puede existir sin estar registrado (murió entre renombrar y actualizar
        el manifiesto), y en ese caso se sobrescribe. Es preferible reescribir
        un trozo a saltearlo.
        """
        if self.esta_completa:
            self._solo_lectura = True
            if self.verboso:
                print(f"  partición ya completa: {self.directorio}", flush=True)
            return

        ruta = self.directorio / NOMBRE_MANIFIESTO
        if not ruta.is_file():
            return

        try:
            manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            # Un manifiesto ilegible no puede hacer fallar la corrida: se
            # empieza de cero, que a lo sumo reescribe trozos.
            if self.verboso:
                print(f"  manifiesto ilegible, se reinicia: {error}", flush=True)
            return

        self._trozos_cerrados = manifiesto.get("trozos_cerrados", 0)
        self._lineas_totales = manifiesto.get("lineas_totales", 0)
        self._cursor = manifiesto.get("cursor")
        # Lo leído del manifiesto está confirmado por definición: sus líneas
        # están en los trozos que ya se cerraron.
        self._cursor_pendiente = self._cursor
        if self.verboso and self._trozos_cerrados:
            print(
                f"  retomando: {self._trozos_cerrados} trozos, "
                f"{self._lineas_totales:,} líneas, cursor={self._cursor}",
                flush=True,
            )

    # -- escritura --------------------------------------------------------

    def escribir(self, linea: bytes) -> None:
        """Encola una línea. Se vuelca a disco al completarse el trozo."""
        if self._solo_lectura:
            raise RuntimeError(
                f"La partición {self.directorio} ya está completa. Escribir "
                "acá mezclaría datos de dos corridas en un directorio que dbt "
                "ya considera legible. Borrá `_COMPLETO` si de verdad querés "
                "rehacerla."
            )
        self._buffer.append(linea)
        self._lineas_totales += 1
        if len(self._buffer) >= self.lineas_por_trozo:
            self._cerrar_trozo()

    def punto_de_control(self, *, cursor: str | None = None) -> None:
        """Cierra el trozo pendiente y anota el cursor. Se llama por página.

        El cursor es el último `id_contrato` de la página confirmada: el punto
        desde el que `paginar()` reanuda el keyset si la partición se retoma.

        Anotarlo acá **no** lo confirma. Solo pasa al manifiesto cuando el
        buffer está vacío, o sea cuando sus líneas ya están en disco; de eso se
        encarga `_guardar_manifiesto()`. El trozo se cierra al llenarse por
        líneas o al cumplirse `paginas_por_trozo`, lo que ocurra primero (I5).
        """
        if cursor is not None:
            self._cursor_pendiente = cursor

        self._paginas_desde_cierre += 1
        if self._buffer and (
            len(self._buffer) >= self.lineas_por_trozo
            or self._paginas_desde_cierre >= self.paginas_por_trozo
        ):
            self._cerrar_trozo()

        self._guardar_manifiesto()

    def _cerrar_trozo(self) -> None:
        """Escribe el buffer como un `.gz` completo y válido, atómicamente."""
        numero = self._trozos_cerrados + 1
        destino = self.directorio / f"parte-{numero:04d}.jsonl.gz"
        temporal = destino.with_suffix(destino.suffix + ".tmp")

        contenido = b"\n".join(self._buffer) + b"\n"
        with gzip.open(temporal, "wb", compresslevel=NIVEL_COMPRESION) as salida:
            salida.write(contenido)

        os.replace(temporal, destino)  # atómico en el mismo sistema de archivos
        self._trozos_cerrados = numero
        self._buffer.clear()
        self._paginas_desde_cierre = 0

    # -- manifiesto y cierre ----------------------------------------------

    def _guardar_manifiesto(self) -> None:
        # EL INVARIANTE DE I5, y vive acá porque este es el único punto donde el
        # cursor llega al disco. El manifiesto nunca puede anunciar un avance
        # mayor que lo efectivamente escrito: si quedan líneas en el buffer, el
        # cursor se queda donde estaba y la próxima corrida rebaja esas páginas.
        # Reescribir filas es el error que sobra; perderlas es el que falta, y
        # la fuente se sobrescribe cada noche.
        #
        # La condición es "el buffer está vacío", no "se acaba de cerrar un
        # trozo": en una corrida donde no cambió nada no se escribe ni una
        # línea, nunca se cierra un trozo, y con la regla del trozo el cursor
        # no avanzaría jamás.
        if not self._buffer:
            self._cursor = self._cursor_pendiente

        contenido = {
            "flujo": self.flujo,
            "fecha_extraccion": self.fecha_extraccion,
            "particion": self.particion,
            "algoritmo_hash": ALGORITMO_HASH,
            "compresion": f"gzip-{NIVEL_COMPRESION}",
            "trozos_cerrados": self._trozos_cerrados,
            "lineas_totales": self._lineas_totales,
            "cursor": self._cursor,
            "actualizado": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        ruta = self.directorio / NOMBRE_MANIFIESTO
        temporal = ruta.with_suffix(".json.tmp")
        temporal.write_text(
            json.dumps(contenido, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporal, ruta)

    def completar(self) -> None:
        """Marca la partición como legible. Es lo último que ocurre.

        El contenido del archivo es informativo; **lo que dbt consulta es su
        existencia**. Un archivo presente es más barato de comprobar que un
        JSON que hay que parsear.
        """
        if self._buffer:
            self._cerrar_trozo()
        self._guardar_manifiesto()

        resumen = {
            "lineas_totales": self._lineas_totales,
            "trozos": self._trozos_cerrados,
            "segundos": round(time.perf_counter() - self._inicio, 1),
        }
        ruta = self.directorio / NOMBRE_COMPLETO
        temporal = ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps(resumen, ensure_ascii=False), encoding="utf-8")
        os.replace(temporal, ruta)

        if self.verboso:
            print(
                f"  partición completa: {self._lineas_totales:,} líneas en "
                f"{self._trozos_cerrados} trozos ({resumen['segundos']}s)",
                flush=True,
            )

    # -- introspección ----------------------------------------------------

    @property
    def esta_completa(self) -> bool:
        return (self.directorio / NOMBRE_COMPLETO).is_file()

    @property
    def lineas_escritas(self) -> int:
        return self._lineas_totales

    @property
    def cursor(self) -> str | None:
        return self._cursor


def iterar_particion(directorio: Path | str) -> Iterator[dict[str, Any]]:
    """Recorre una partición completa sin cargarla entera en memoria.

    Es la forma que hay que usar para reconstruir el índice desde raw: la
    primera corrida guarda los 2.825.685 contratos, y materializar eso como
    lista son varios GB de diccionarios de Python.

    Falla si la partición no está completa: leer una a medias es exactamente lo
    que `_COMPLETO` existe para impedir. Y falla **antes** de devolver la
    primera fila, no en el medio del recorrido — un generador que explota en la
    fila 900.000 deja al que lo consume sin saber qué hacer con las 899.999 que
    ya procesó.
    """
    directorio = Path(directorio)
    if not (directorio / NOMBRE_COMPLETO).is_file():
        raise ValueError(
            f"Partición incompleta (falta {NOMBRE_COMPLETO}): {directorio}. "
            "Leerla daría un recuento parcial que parece total."
        )
    return _iterar_trozos(directorio)


def _iterar_trozos(directorio: Path) -> Iterator[dict[str, Any]]:
    """El generador propiamente dicho, ya validado el directorio."""
    for trozo in sorted(directorio.glob("parte-*.jsonl.gz")):
        with gzip.open(trozo, "rt", encoding="utf-8") as entrada:
            for linea in entrada:
                if linea.strip():
                    yield json.loads(linea)


def leer_particion(directorio: Path | str) -> list[dict[str, Any]]:
    """Igual que `iterar_particion()`, pero materializa la lista.

    Cómoda para tests y para particiones chicas. Para reconstruir el índice
    desde una partición grande, usar `iterar_particion()`.
    """
    return list(iterar_particion(directorio))