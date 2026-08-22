"""Paginación contra SODA2 de Socrata.

Este es el único módulo del proyecto que conoce `$limit`, `$offset`, `$where`,
`$order` y el header `X-App-Token`. Todo lo demás —los tres flujos de ingesta,
la capa raw— habla en términos de "traeme los contratos que cumplen tal
condición" y nunca ve una URL.

El aislamiento es a propósito: SODA3 es el default de la plataforma desde
octubre de 2025, y la v1 eligió SODA2 por depurabilidad. Migrar debe ser
reescribir este archivo, no buscar cadenas por todo el repo.

Estrategia: **keyset**, no offset.

Con offset, para servir la página 500 el motor ordena y descarta 2,5 millones
de filas antes de llegar a las tuyas. El flujo 3 barre el universo vivo todas
las noches, así que esa degradación no se paga una vez sino a diario. Keyset
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
from typing import Any

import requests

from .columnas import COLUMNAS_EXTRAIDAS, clausula_select

URL_BASE = "https://www.datos.gov.co/resource/jbjy-vk9h.json"
VARIABLE_TOKEN = "SOCRATA_APP_TOKEN"
LIMITE_POR_DEFECTO = 5_000

# El cursor avanza sobre esta columna. Tiene que estar entre las extraídas o la
# última fila de cada página no trae el valor con el que pedir la siguiente.
COLUMNA_CURSOR = "id_contrato"

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
        # ⚠ Esto asume que la API devuelve exactamente `limite` filas cuando
        # hay al menos esas. Si algún día capara el `$limit` por debajo de lo
        # pedido —por ejemplo a 1.000 cuando se piden 5.000— **cada página
        # parecería la última** y el recorrido terminaría tras la primera, sin
        # error y sin aviso.
        #
        # La red que cubre eso es `scripts/verificar_extraccion.py`, que
        # compara el total recorrido contra un `count(*)` del servidor. Si esa
        # verificación se borra, este atajo se queda sin respaldo.
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


# TODO(pieza 3): reintentos con espera creciente ante 429 y 5xx.
#
# El argumento para postergarlo era que un reintento mal hecho convierte un
# fallo ruidoso en una corrida lenta que nadie mira. Sigue en pie, pero ahora
# hay un contrapeso: sin reintento, un solo 429 en la página 550 aborta la
# corrida. Con `desde_cursor` ya implementado eso cuesta mucho menos que antes
# —se retoma desde el manifiesto— así que la urgencia bajó, no subió.
#
# Cuando se agregue, mirar `indice.py::_abrir()`: ahí ya hay un reintento con
# espera creciente que resolvió el mismo problema para los bloqueos de DuckDB,
# y conviene que los dos se comporten igual.