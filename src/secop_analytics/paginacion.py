"""Paginación contra SODA2 de Socrata.

Este es el único módulo del proyecto que conoce `$limit`, `$offset`, `$where`,
`$order` y el header `X-App-Token`. Todo lo demás (los tres flujos de ingesta,
la capa raw) habla en términos de "traeme los contratos que cumplen tal
condición" y nunca ve una URL.

No todo lo que se le pregunta a la fuente son filas. `contar()` pregunta
cuántas hay y `corte()` pregunta qué estado está publicado; las dos existen
acá por la misma razón de aislamiento, y las dos son una sola petición sin
paginar. La tercera pregunta de esa familia todavía falta: el endpoint de
metadatos que `columnas.validar_cobertura()` necesita y que nadie puede llamar
porque este módulo no lo expone.

El aislamiento es a propósito: SODA3 es el default de la plataforma desde
octubre de 2025, y la v1 eligió SODA2 por depurabilidad. Migrar debe ser
reescribir este archivo, no buscar cadenas por todo el repo.

Estrategia: **keyset**, no offset.

Con offset, para servir la página 500 el motor ordena y descarta 2,5 millones
de filas antes de llegar a las tuyas. El flujo 3 barre el universo vivo entero
en cada corrida, así que esa degradación no se paga una vez sino en cada
regeneración de la fuente. Keyset
pide "las siguientes N con `id_contrato` mayor al último que vi", el servidor va
al índice y cada página cuesta lo mismo.

El keyset además elimina por construcción el problema que obligaba a poner
`$order` explícito: no depende de que el conjunto se quede quieto entre
peticiones, solo de que `id_contrato` sea único, que H1 verificó por dos
métodos. El `$order` se manda igual, porque el avance por cursor lo necesita
para ser correcto.

Lo que se pierde: keyset es estrictamente secuencial. La paralelización se
recupera un nivel más arriba, partiendo por rango de fechas y corriendo varias
particiones a la vez; cada una pagina secuencialmente adentro.

## Reanudar a mitad de camino

`paginar()` acepta `desde_cursor`, que es lo que permite retomar un recorrido
interrumpido sin volver a bajar lo ya bajado. La capa raw guarda ese valor en
el manifiesto de cada partición cada vez que confirma una página.

Sirve porque el cursor es el mismo mecanismo que hace avanzar la paginación
normal: retomar desde el último `id_contrato` confirmado es idéntico a pedir la
página siguiente. No hay un camino especial de reanudación que pueda pudrirse
sin que nadie lo note.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, NamedTuple

import requests

from .columnas import COLUMNAS_EXTRAIDAS, clausula_select

URL_BASE = "https://www.datos.gov.co/resource/jbjy-vk9h.json"
VARIABLE_TOKEN = "SOCRATA_APP_TOKEN"
LIMITE_POR_DEFECTO = 5_000

# El cursor avanza sobre esta columna. Tiene que estar entre las extraídas o la
# última fila de cada página no trae el valor con el que pedir la siguiente.
COLUMNA_CURSOR = "id_contrato"

# Campo de sistema de Socrata: cuándo se escribió la fila. En esta fuente es
# idéntico en las 5,96M de filas porque el dataset se reemplaza entero, y por
# eso identifica al corte (H2). Lleva dos puntos adelante; `requests` lo
# codifica como %3A y la API lo acepta así.
COLUMNA_DEL_CORTE = ":updated_at"

Fila = dict[str, Any]  # los valores llegan como str, salvo `urlproceso` (dict)


class ErrorDeConfiguracion(RuntimeError):
    """Falta algo del entorno. Se lanza antes de la primera petición."""


def _token() -> str:
    """Lee el app token, o falla temprano y ruidoso.

    Sin token la API responde igual, en modo anónimo y con un cupo mucho más
    bajo. Eso es peor que no funcionar: el backfill arrancaría bien y moriría
    con HTTP 429 a mitad de camino, después de horas.
    """
    token = os.environ.get(VARIABLE_TOKEN)
    if not token:
        raise ErrorDeConfiguracion(
            f"Falta la variable de entorno {VARIABLE_TOKEN}. "
            f"Copiá .env.example a .env y poné el token de datos.gov.co."
        )
    return token


def _combinar_where(filtro: str | None, cursor: str | None) -> str | None:
    """Une el filtro de negocio con la condición del cursor."""
    condiciones = [c for c in (filtro, _condicion_cursor(cursor)) if c]
    if not condiciones:
        return None
    return " AND ".join(f"({c})" for c in condiciones)


def _condicion_cursor(cursor: str | None) -> str | None:
    if cursor is None:
        return None
    # SoQL usa comillas simples para literales de texto; se duplican para
    # escapar. Los `id_contrato` observados son alfanuméricos con puntos, pero
    # no se confía en eso: el escape va igual.
    literal = cursor.replace("'", "''")
    return f"{COLUMNA_CURSOR} > '{literal}'"


def paginar(
    filtro: str | None = None,
    *,
    limite: int = LIMITE_POR_DEFECTO,
    sesion: requests.Session | None = None,
    tiempo_limite: int = 60,
    desde_cursor: str | None = None,
) -> Iterator[list[Fila]]:
    """Recorre el dataset en páginas, aplicando un filtro SoQL opcional.

    Devuelve un **generador de páginas**, no una lista. El universo vivo son
    2,8 millones de filas: quien llama escribe cada página a disco y sigue, en
    vez de acumular todo en memoria.

    Args:
        filtro: cláusula `$where` en SoQL, sin la palabra WHERE. Por ejemplo
            `"fecha_de_firma >= '2024-01-01' AND fecha_de_firma < '2024-02-01'"`.
            Si es None, recorre el dataset completo.
        limite: filas por página. Parámetro y no constante para poder subirlo
            si la API lo aguanta, sin tocar esta lógica.
        sesion: `requests.Session` para reusar la conexión TCP entre páginas.
            Sobre cientos de peticiones seguidas la diferencia se nota.
        tiempo_limite: segundos antes de abandonar una petición.
        desde_cursor: último `id_contrato` ya procesado. El recorrido arranca
            **después** de él. Es lo que permite retomar una partición
            interrumpida sin volver a bajar lo que ya se bajó.

    Yields:
        Listas de filas. Los valores vienen como texto a propósito: si se
        dejara que pandas infiera tipos, los valores mal formados se
        convertirían en NaN y esconderían la suciedad que queremos ver.
    """
    if COLUMNA_CURSOR not in COLUMNAS_EXTRAIDAS:
        raise ErrorDeConfiguracion(
            f"{COLUMNA_CURSOR} no está en COLUMNAS_EXTRAIDAS; el cursor no puede avanzar."
        )
    if limite < 1:
        raise ValueError("El límite tiene que ser al menos 1.")

    http = sesion or requests.Session()
    cabeceras = {"X-App-Token": _token()}
    cursor: str | None = desde_cursor

    while True:
        parametros: dict[str, str | int] = {
            "$select": clausula_select(),
            "$order": COLUMNA_CURSOR,
            "$limit": limite,
        }
        where = _combinar_where(filtro, cursor)
        if where:
            parametros["$where"] = where

        respuesta = http.get(
            URL_BASE, params=parametros, headers=cabeceras, timeout=tiempo_limite
        )
        respuesta.raise_for_status()
        pagina: list[Fila] = respuesta.json()

        if not pagina:
            return

        yield pagina

        # Una página incompleta significa que no hay más: evita una petición
        # de más por cada recorrido.
        #
        # El diseño asume que la API devuelve exactamente `limite` filas cuando
        # hay al menos esas cantidades disponibles. Si en el futuro capara el
        # `$limit` por debajo de lo pedido (por ejemplo limitándose a 1.000
        # cuando se solicitan 5.000) cada página parecería ser la última y el
        # recorrido terminaría tras la primera sin error ni aviso, perdiendo el
        # resto del dataset en silencio.
        #
        # El respaldo que sostiene este atajo es `scripts/verificar_extraccion.py`,
        # que compara el total de filas recorridas contra un `count(*)` del servidor.
        # Si esa verificación se borra, este razonamiento queda sin fundamento y
        # habría que revisar la lógica de terminación.
        if len(pagina) < limite:
            return

        cursor = pagina[-1][COLUMNA_CURSOR]


def contar(
    filtro: str | None = None,
    *,
    sesion: requests.Session | None = None,
    tiempo_limite: int = 60,
) -> int:
    """Cuenta filas del lado del servidor, con el mismo filtro que `paginar`.

    Existe para verificar el recorrido: si paginar un rango devuelve menos
    filas que esto, el cursor se está saltando algo en silencio, que es
    exactamente el modo de fallo que hay que descartar.
    """
    http = sesion or requests.Session()
    parametros: dict[str, str] = {"$select": "count(*) as n"}
    if filtro:
        parametros["$where"] = filtro

    respuesta = http.get(
        URL_BASE,
        params=parametros,
        headers={"X-App-Token": _token()},
        timeout=tiempo_limite,
    )
    respuesta.raise_for_status()
    return int(respuesta.json()[0]["n"])


class Corte(NamedTuple):
    """El estado de la fuente que produjo una regeneración.

    `jbjy-vk9h` se reemplaza entero en cada regeneración, así que todas sus
    filas comparten el mismo `:updated_at` (H2, confirmado cuatro veces sobre
    5,96M de filas). Ese valor idéntico es lo que identifica al corte: no es una
    etiqueta nuestra sino el sello que la propia fuente le puso al estado.

    Los dos extremos se guardan por separado a propósito. Ver `confiable`.
    """

    mas_viejo: str
    mas_nuevo: str

    @property
    def confiable(self) -> bool:
        """Si los dos extremos coinciden, y por lo tanto hay un corte único.

        Cuando difieren hay **dos** explicaciones posibles y este módulo no
        puede distinguirlas:

        1. La consulta cayó **mientras la fuente se regeneraba**. Escribir 5,96
           millones de filas no es instantáneo, y a mitad el dataset estaría
           mezclado. Nadie observó nunca la fuente dentro de su ventana de
           regeneración, así que no se sabe qué se ve ahí.
        2. **H2 dejó de valer** y la fuente pasó a actualizar filas sueltas. Eso
           tumbaría los tres flujos, D10 y D11 de una vez.

        Por eso `corte()` no aborta ni descarta: devuelve los dos valores y esta
        marca, y quien llama decide. Abortar trataría el caso 1 como una
        catástrofe; ignorarlo escribiría la mezcla como si fuera un corte
        limpio. Registrar los dos valores deja que el dato decida después.
        """
        return self.mas_viejo == self.mas_nuevo


def corte(
    *,
    sesion: requests.Session | None = None,
    tiempo_limite: int = 60,
) -> Corte:
    """Qué estado de la fuente está publicado ahora mismo.

    Es la única pregunta del proyecto que no es por filas, y cuesta una
    petición de segundos contra 5,96 millones de filas: la agregación corre del
    lado del servidor.

    Para qué sirve, que son dos cosas distintas:

    - **Saber si hay estado nuevo.** La fuente declara frecuencia diaria y no la
      cumple: en nueve días observados hubo tres regeneraciones y cuatro días
      sin ninguna, con saltos de dos y de cinco días (H34). Correr el flujo 3
      contra un corte ya ingerido cuesta ~50 minutos y escribe una partición
      vacía, así que el disparador es este valor y no el calendario (D11).
    - **Anotar de dónde vino cada observación.** Raw se particiona por
      `fecha_extraccion`, que es cuándo bajamos los datos, no qué vimos. Con la
      fuente saltando días, dos particiones con fechas distintas pueden
      contener el mismo estado (D10).

    ## `:updated_at` como llave del corte, no como watermark de fila

    Estos son usos opuestos que es fácil confundir. El inventario descarta
    `:updated_at` como watermark para detectar cambios, y con razón: es idéntico
    en todas las filas de un corte. Pero esa misma propiedad (el hecho de que
    sea invariante dentro de un estado) es precisamente lo que lo hace funcionar
    como llave única de ese estado. Son dos cosas que se contradicen solo si
    uno olvida que las usa en contextos opuestos.

    Si la petición falla (429, 5xx, timeout) la excepción sube y la corrida se
    aborta. Es deliberado: reintentar es volver a escribir el comando y no se
    pierde nada, mientras que arrancar cincuenta minutos sin saber contra qué
    corte se está corriendo es exactamente lo que D10 vino a eliminar.

    Args:
        sesion: `requests.Session` para reusar la conexión. Conviene pasar la
            misma que va a usar el recorrido.
        tiempo_limite: segundos antes de abandonar la petición.

    Returns:
        Un `Corte` con los dos extremos. Ver `Corte.confiable`.
    """
    http = sesion or requests.Session()
    respuesta = http.get(
        URL_BASE,
        params={
            "$select": (
                f"min({COLUMNA_DEL_CORTE}) as mas_viejo,"
                f"max({COLUMNA_DEL_CORTE}) as mas_nuevo"
            )
        },
        headers={"X-App-Token": _token()},
        timeout=tiempo_limite,
    )
    respuesta.raise_for_status()

    cuerpo = respuesta.json()
    # Un dataset vacío devuelve la fila con los agregados en nulo, y un cambio
    # en la forma de la respuesta la devuelve sin las claves. Los dos casos son
    # indistinguibles acá y los dos significan lo mismo: no hay corte que leer.
    # Se levanta en vez de devolver algo vacío, porque un corte inventado
    # contamina la procedencia de todo lo que se escriba después.
    if not cuerpo or not cuerpo[0].get("mas_viejo") or not cuerpo[0].get("mas_nuevo"):
        raise RuntimeError(
            f"La consulta del corte no devolvió los dos extremos: {cuerpo!r}. "
            f"O el dataset vino vacío, o la respuesta cambió de forma."
        )

    return Corte(mas_viejo=cuerpo[0]["mas_viejo"], mas_nuevo=cuerpo[0]["mas_nuevo"])


# TODO(pieza 3): reintentos con espera creciente ante 429 y 5xx.
#
# El argumento para postergarlo era que un reintento mal hecho convierte un
# fallo ruidoso en una corrida lenta que nadie mira. Sigue en pie, pero ahora
# hay un contrapeso: sin reintento, un solo 429 en la página 550 aborta la
# corrida. Con `desde_cursor` ya implementado eso cuesta mucho menos que antes
# (se retoma desde el manifiesto) así que la urgencia bajó, no subió.
#
# Cuando se agregue, mirar `indice.py::_abrir()`: ahí ya hay un reintento con
# espera creciente que resolvió el mismo problema para los bloqueos de DuckDB,
# y conviene que los dos se comporten igual.