"""Índice de hashes: qué se guardó por última vez de cada contrato.

Es el estado que hace posible la deduplicación por bytes (D3). Guarda una fila
por `id_contrato` con el hash de la última observación **que se escribió a
raw**, no de la última que se vio.

**El índice es caché, no fuente de verdad.** Si se pierde o se corrompe, se
reconstruye releyendo los archivos de raw y tomando el último hash por contrato
(`reconstruir_desde_raw()`). Los archivos mandan. Por eso este módulo puede
permitirse ser rápido y no durable: lo peor que pasa si se pierde una tanda es
que la próxima corrida guarde de nuevo filas que no cambiaron — duplicados en
raw, que dbt resuelve tomando la última observación por contrato.

## Por qué se lee todo al arrancar y se escribe todo al cerrar

DuckDB admite **muchos lectores** simultáneos y **un solo escritor**. El flujo 3
se paraleliza lanzando varias particiones a la vez (`refresco_de_vivos()`), así
que si cada una escribiera durante el recorrido, pelearían por el archivo.

Leer al arrancar y escribir al cerrar serializa solo las escrituras. Funciona
porque las particiones del flujo 3 son rangos **disjuntos** de `fecha_de_firma`:
dos procesos nunca compiten por el mismo `id_contrato`, así que una foto del
índice tomada al inicio alcanza.

Medido el 21/08/2026 con 2.825.685 contratos (ver §8 del registro de hallazgos):

| | Memoria | Tiempo |
|---|---|---|
| Cargar todo en un dict | 185 MB | 2,1 s |
| Consultar por lotes de 5.000 | constante | 95,4 s |

La opción "prudente" resultó 47× más lenta para proteger 185 MB. Se carga todo.

⚠ Cuatro particiones en paralelo son cuatro copias: ~740 MB. Manejable hoy; si
el dataset se duplica, reevaluar.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import duckdb

from .hashing import ALGORITMO_HASH

TABLA: Final[str] = "indice_hashes"

_ESQUEMA: Final[str] = f"""
create table if not exists {TABLA} (
    id_contrato        varchar primary key,
    huella             varchar not null,
    algoritmo          varchar not null,
    fecha_extraccion   varchar not null,
    flujo              varchar not null
)
"""


class IndiceHashes:
    """Foto del índice al arrancar, más lo que se acumula durante la corrida.

    Uso previsto, con `with` para que la tanda se escriba pase lo que pase:

        with IndiceHashes(ruta) as indice:
            for fila in filas:
                id_c, huella, linea = preparar(fila, ...)
                if indice.cambio(id_c, huella):
                    escribir(linea)                 # 1. primero el archivo
                    indice.registrar(id_c, huella, ...)   # 2. después el índice

    Ese orden es el invariante 1 de D2 y no es negociable. Al revés, un fallo a
    mitad deja el índice diciendo "ya vi este contrato" con la fila en ninguna
    parte — y la fuente ya se sobrescribió, así que se perdió para siempre.
    """

    def __init__(self, ruta: Path | str, *, verboso: bool = True) -> None:
        self.ruta = Path(ruta)
        self.verboso = verboso
        self._conocidos: dict[str, str] = {}
        self._pendientes: dict[str, tuple[str, str, str]] = {}
        self._conexion: duckdb.DuckDBPyConnection | None = None

    # -- ciclo de vida ----------------------------------------------------

    def __enter__(self) -> IndiceHashes:
        self.cargar()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        # Se vuelca incluso si hubo excepción: lo ya escrito a disco tiene que
        # quedar reflejado, o la próxima corrida lo duplica.
        try:
            self.volcar()
        finally:
            if self._conexion is not None:
                self._conexion.close()
                self._conexion = None

    def _abrir(self, *, solo_lectura: bool) -> duckdb.DuckDBPyConnection:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        if solo_lectura and not self.ruta.exists():
            # No se puede abrir en solo lectura algo que no existe: primera
            # corrida. Se crea vacío y se cierra.
            duckdb.connect(str(self.ruta)).execute(_ESQUEMA).close()
        conexion = duckdb.connect(str(self.ruta), read_only=solo_lectura)
        if not solo_lectura:
            conexion.execute(_ESQUEMA)
        return conexion

    # -- lectura ----------------------------------------------------------

    def cargar(self) -> int:
        """Trae el índice entero a memoria. Abre en solo lectura, sin bloquear."""
        inicio = time.perf_counter()
        conexion = self._abrir(solo_lectura=True)
        try:
            filas = conexion.execute(
                f"select id_contrato, huella from {TABLA}"
            ).fetchall()
        finally:
            conexion.close()

        self._conocidos = dict(filas)
        if self.verboso:
            print(
                f"  índice: {len(self._conocidos):,} contratos conocidos "
                f"({time.perf_counter() - inicio:.1f}s)",
                flush=True,
            )
        return len(self._conocidos)

    def cambio(self, id_contrato: str, huella: str) -> bool:
        """¿Hay que guardar esta observación?

        Verdadero si el contrato es nuevo o si sus bytes difieren de la última
        observación guardada. Un contrato registrado en esta misma corrida ya
        cuenta: el flujo 1 y el flujo 2 se solapan a propósito, y sin esto el
        mismo contrato se escribiría dos veces la misma noche.
        """
        if id_contrato in self._pendientes:
            return self._pendientes[id_contrato][0] != huella
        return self._conocidos.get(id_contrato) != huella

    # -- escritura --------------------------------------------------------

    def registrar(
        self, id_contrato: str, huella: str, *, fecha_extraccion: str, flujo: str
    ) -> None:
        """Anota en memoria. **Llamar DESPUÉS de escribir la línea al archivo.**"""
        self._pendientes[id_contrato] = (huella, fecha_extraccion, flujo)

    def volcar(self) -> int:
        """Escribe la tanda acumulada. Es el único momento que toma el escritor."""
        if not self._pendientes:
            return 0

        inicio = time.perf_counter()
        ids = list(self._pendientes)
        huellas = [self._pendientes[i][0] for i in ids]
        fechas = [self._pendientes[i][1] for i in ids]
        flujos = [self._pendientes[i][2] for i in ids]

        conexion = self._abrir(solo_lectura=False)
        try:
            conexion.execute(
                f"""
                insert into {TABLA}
                select unnest($1), unnest($2), $3, unnest($4), unnest($5)
                on conflict (id_contrato) do update set
                    huella           = excluded.huella,
                    algoritmo        = excluded.algoritmo,
                    fecha_extraccion = excluded.fecha_extraccion,
                    flujo            = excluded.flujo
                """,
                [ids, huellas, ALGORITMO_HASH, fechas, flujos],
            )
        finally:
            conexion.close()

        cantidad = len(ids)
        # Lo volcado pasa a ser conocido: permite volcar varias veces en una
        # misma corrida sin reescribir lo mismo.
        self._conocidos.update(zip(ids, huellas))
        self._pendientes.clear()

        if self.verboso:
            print(
                f"  índice: {cantidad:,} hashes actualizados "
                f"({time.perf_counter() - inicio:.1f}s)",
                flush=True,
            )
        return cantidad

    # -- recuperación -----------------------------------------------------

    def reconstruir_desde_raw(
        self, observaciones: Iterator[dict[str, Any]]
    ) -> int:
        """Rearma el índice desde los archivos de raw.

        Existe porque el índice es **derivado**: raw es la fuente de verdad. Se
        usa si el archivo se pierde o si se cambia el algoritmo de hash.

        Espera las observaciones en orden cronológico; la última gana. Se
        confía en `hash` tal como quedó escrito en el archivo, sin recalcularlo:
        el objetivo es reproducir el estado del índice, no reauditar raw. Para
        lo segundo hay un test que rehashea `datos` y compara.
        """
        self._conocidos.clear()
        self._pendientes.clear()
        for observacion in observaciones:
            datos = observacion["datos"]
            self._pendientes[str(datos["id_contrato"])] = (
                observacion["hash"],
                observacion["fecha_extraccion"],
                observacion["flujo"],
            )
        return self.volcar()

    # -- introspección ----------------------------------------------------

    @property
    def pendientes(self) -> int:
        return len(self._pendientes)

    @property
    def conocidos(self) -> int:
        return len(self._conocidos)