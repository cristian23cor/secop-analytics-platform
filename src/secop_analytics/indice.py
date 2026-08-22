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

El flujo 3 se paraleliza lanzando varias particiones a la vez
(`refresco_de_vivos()`), así que si cada una escribiera durante el recorrido,
pelearían por el archivo todo el tiempo. Leer al arrancar y escribir al cerrar
reduce la ventana de conflicto a unos segundos por proceso.

Funciona porque las particiones del flujo 3 son rangos **disjuntos** de
`fecha_de_firma`: dos procesos nunca compiten por el mismo `id_contrato`, así
que una foto del índice tomada al inicio alcanza.

### El bloqueo de DuckDB es más estricto de lo que parece

Medido con procesos reales, no con hilos del mismo proceso:

- Dos escritores simultáneos: el segundo recibe `IOException` — *"Could not set
  lock on file"*.
- **Un lector mientras hay un escritor: también falla.** Esto contradice la
  intuición de "muchos lectores, un escritor": mientras alguien tiene el
  archivo abierto para escribir, **nadie más puede ni siquiera leerlo**.

Por eso `_abrir()` reintenta con espera creciente en vez de fallar de una. Sin
reintento, una partición que arranca justo cuando otra está volcando no podría
ni cargar el índice, y moriría por una colisión de dos segundos.

El reintento es la razón por la que este esquema funciona en paralelo. No es un
detalle defensivo: es lo que hace cierto el párrafo de arriba.

Medición de carga, con 2.825.685 contratos (ver I4):

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
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

import duckdb

from .hashing import ALGORITMO_HASH

TABLA: Final[str] = "indice_hashes"

# Reintentos al abrir. Ver `_abrir()`.
_INTENTOS_DE_APERTURA: Final[int] = 6
_ESPERA_INICIAL: Final[float] = 0.5

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

    # -- ciclo de vida ----------------------------------------------------

    def __enter__(self) -> IndiceHashes:
        self.cargar()
        return self

    def __exit__(self, tipo, valor, traza) -> None:
        # Se vuelca incluso si hubo excepción: lo ya escrito a disco tiene que
        # quedar reflejado, o la próxima corrida lo duplica.
        #
        # Este objeto no mantiene una conexión abierta entre llamadas: cada
        # operación abre, hace lo suyo y cierra. Es lo que mantiene corta la
        # ventana en que otro proceso encuentra el archivo bloqueado.
        self.volcar()

    def _abrir(self, *, solo_lectura: bool) -> duckdb.DuckDBPyConnection:
        """Abre el índice, esperando si otro proceso lo tiene tomado.

        El reintento no es defensivo, es necesario: con varias particiones en
        paralelo, la que llega mientras otra vuelca encuentra el archivo
        bloqueado — y para **leer** también, no solo para escribir.

        Espera creciente: 0,5 s, 1 s, 2 s, 4 s... Un volcado típico dura menos
        de un segundo (0,2 s para ~30.000 hashes), así que con dos o tres
        intentos alcanza. Los seis intentos cubren hasta ~30 s de espera, que
        es más que el peor volcado medido (13,9 s, cuando cambia todo).
        """
        self.ruta.parent.mkdir(parents=True, exist_ok=True)

        ultimo: Exception | None = None
        for intento in range(_INTENTOS_DE_APERTURA):
            try:
                if solo_lectura and not self.ruta.exists():
                    # No se puede abrir en solo lectura algo que no existe:
                    # primera corrida. Se crea vacío y se cierra.
                    duckdb.connect(str(self.ruta)).execute(_ESQUEMA).close()
                conexion = duckdb.connect(str(self.ruta), read_only=solo_lectura)
                if not solo_lectura:
                    conexion.execute(_ESQUEMA)
                return conexion
            except (duckdb.IOException, duckdb.ConnectionException) as error:
                ultimo = error
                if intento == _INTENTOS_DE_APERTURA - 1:
                    break
                espera = _ESPERA_INICIAL * (2 ** intento)
                if self.verboso:
                    modo = "lectura" if solo_lectura else "escritura"
                    print(
                        f"  índice ocupado por otro proceso ({modo}); "
                        f"reintento en {espera:.1f}s",
                        flush=True,
                    )
                time.sleep(espera)

        raise RuntimeError(
            f"No se pudo abrir el índice {self.ruta} tras "
            f"{_INTENTOS_DE_APERTURA} intentos. Otro proceso lo tiene tomado "
            f"hace demasiado tiempo, o quedó un bloqueo huérfano de una corrida "
            f"que murió. Último error: {ultimo}"
        ) from ultimo

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
        self,
        observaciones: Iterable[dict[str, Any]],
        *,
        desde_cero: bool = False,
    ) -> int:
        """Rearma el índice desde los archivos de raw.

        Existe porque el índice es **derivado**: raw es la fuente de verdad. Se
        usa si el archivo se pierde o si se cambia el algoritmo de hash.

        Espera las observaciones en orden cronológico; la última gana. Se
        confía en `hash` tal como quedó escrito en el archivo, sin recalcularlo:
        el objetivo es reproducir el estado del índice, no reauditar raw. Para
        eso segundo está `hashing.verificar_linea()`.

        ⚠ **`desde_cero` cambia el significado de la operación.**

        En `False` —el defecto— esto es una **fusión**: los contratos que estén
        en la tabla y no en las observaciones **sobreviven**. Es lo correcto si
        se está alimentando el índice partición por partición.

        En `True` se vacía la tabla antes de escribir, y el resultado refleja
        exactamente lo que traen las observaciones. Es lo correcto si se está
        rehaciendo el índice entero desde todo raw, y es la única forma de
        sacar entradas equivocadas de un índice corrupto: una fusión las
        conservaría.

        Elegir mal no falla ni avisa. Deja un índice que dice conocer contratos
        que raw no respalda, y esos contratos no se vuelven a guardar nunca.
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

        if desde_cero:
            self._vaciar()
        return self.volcar()

    def _vaciar(self) -> None:
        """Borra la tabla. Solo lo llama `reconstruir_desde_raw(desde_cero=True)`."""
        conexion = self._abrir(solo_lectura=False)
        try:
            conexion.execute(f"delete from {TABLA}")
        finally:
            conexion.close()

    # -- introspección ----------------------------------------------------

    @property
    def pendientes(self) -> int:
        return len(self._pendientes)

    @property
    def conocidos(self) -> int:
        return len(self._conocidos)