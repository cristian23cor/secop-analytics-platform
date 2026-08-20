"""Verificación de la extracción contra la API real.

Se corre a mano, una vez, sobre una partición chica. No es un test de pytest:
depende de la red y de la fuente, así que no puede vivir en CI.

    uv run python scripts/verificar_extraccion.py

Lo que responde, en orden de importancia:

1. **¿El keyset recorre todo?** Es el supuesto no verificado de la pieza 2. El
   cursor asume que el `>` de SoQL sobre texto ordena igual que el `ORDER BY`
   de SoQL sobre texto. Si las colaciones difirieran, el recorrido se saltaría
   filas **en silencio**, que es el peor modo de fallo posible. Se descarta
   comparando contra un `count(*)` del lado del servidor.
2. **¿Hay duplicados entre páginas?** El otro modo de fallo de la paginación.
3. **¿Se filtraron los datos personales?** La decisión de H7, verificada sobre
   lo que efectivamente llegó, no sobre lo que creemos haber pedido.
4. **¿Los tres flujos traen lo que dicen traer?**

Se usa un límite chico a propósito (100): fuerza muchas páginas sobre pocos
datos, que es donde los errores de cursor aparecen.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

from secop_analytics import columnas, flujos
from secop_analytics.paginacion import contar, paginar

# El `.env` vive en la raíz del repo. Se resuelve desde la ubicación de este
# archivo y no desde el directorio actual, para que el script funcione sin
# importar desde dónde se lo invoque.
RAIZ = Path(__file__).resolve().parents[1]

# Un día hábil cualquiera, ya cerrado. La verificación necesita MUCHAS páginas
# sobre POCAS filas: las páginas ejercitan el cursor, las filas solo cuestan
# tiempo. Un día son ~2.900 contratos, o sea ~29 páginas de 100. Un mes son
# ~128.000, o sea 1.284 peticiones que no prueban nada que las 29 no prueben.
DESDE = date(2024, 2, 6)
HASTA = date(2024, 2, 7)
LIMITE = 100


def _recorrer(paginas, *, avisar: bool = False) -> tuple[list[str], int, set[str]]:
    """Consume un generador de páginas y devuelve ids, conteo y claves vistas.

    `avisar` imprime el avance. Un recorrido silencioso no se distingue de un
    proceso colgado, y esa ambigüedad hace que alguien lo mate justo antes de
    que termine.
    """
    ids: list[str] = []
    claves: set[str] = set()
    n_paginas = 0
    for pagina in paginas:
        n_paginas += 1
        for fila in pagina:
            ids.append(fila["id_contrato"])
            claves.update(fila)
        if avisar:
            print(f"\r  página {n_paginas} · {len(ids):,} filas", end="", flush=True)
    if avisar and n_paginas:
        print()
    return ids, n_paginas, claves


def main() -> None:
    load_dotenv(RAIZ / ".env")

    sesion = requests.Session()
    fallos: list[str] = []

    # ---------------------------------------------------------------- 1 y 2
    # Se reconstruye el filtro del flujo para poder contar con la misma
    # condición. Es la única razón por la que este script toca un helper
    # privado; si hiciera falta en más lugares, el filtro debería ser público.
    filtro = flujos._rango("fecha_de_firma", DESDE, HASTA)

    esperadas = contar(filtro, sesion=sesion)
    peticiones = -(-esperadas // LIMITE)  # división hacia arriba
    print(
        f"El servidor dice que hay {esperadas:,} contratos firmados en el rango.\n"
        f"Recorrerlos de a {LIMITE} son ~{peticiones:,} peticiones."
    )
    if peticiones > 100:
        print(
            "  Eso es mucho para una verificación. Achicá el rango o subí LIMITE:\n"
            "  la garantía la dan las páginas, no las filas."
        )

    ids, n_paginas, claves = _recorrer(
        paginar(filtro, limite=LIMITE, sesion=sesion), avisar=True
    )
    print(f"El recorrido trajo {len(ids):,} filas en {n_paginas} páginas.")

    if len(ids) != esperadas:
        fallos.append(
            f"CONTEO: se esperaban {esperadas:,} y llegaron {len(ids):,}. "
            "Si llegaron menos, el cursor se está saltando filas."
        )
    else:
        print("  OK — el keyset recorre el conjunto completo.")

    duplicados = len(ids) - len(set(ids))
    if duplicados:
        fallos.append(f"DUPLICADOS: {duplicados:,} id_contrato repetidos entre páginas.")
    else:
        print("  OK — sin duplicados entre páginas.")

    if ids != sorted(ids):
        fallos.append("ORDEN: las filas no llegaron ordenadas por id_contrato.")
    else:
        print("  OK — el orden se respeta a lo largo de todo el recorrido.")

    # -------------------------------------------------------------------- 3
    filtradas = claves & columnas.PERSONALES
    if filtradas:
        fallos.append(f"DATOS PERSONALES: llegaron {sorted(filtradas)}")
    else:
        print(f"  OK — ninguna de las {len(columnas.PERSONALES)} columnas personales llegó.")

    inesperadas = claves - set(columnas.COLUMNAS_EXTRAIDAS)
    if inesperadas:
        fallos.append(f"COLUMNAS INESPERADAS: {sorted(inesperadas)}")

    # Las ausentes se esperan: la API omite las claves nulas. Se informan
    # porque son el insumo del relleno con nulo en la capa raw.
    ausentes = set(columnas.COLUMNAS_EXTRAIDAS) - claves
    if ausentes:
        print(f"\n  Nunca llegaron (nulas en todas las filas del rango): {len(ausentes)}")
        for c in sorted(ausentes):
            print(f"     {c:45} -> {columnas.clasificacion(c)}")

    # -------------------------------------------------------------------- 4
    print("\nLos tres flujos, sobre el mismo rango:")

    nuevos, _, _ = _recorrer(
        flujos.contratos_nuevos(DESDE, HASTA, limite=LIMITE, sesion=sesion)
    )
    print(f"  contratos_nuevos:      {len(nuevos):,}")

    eventos, _, _ = _recorrer(
        flujos.eventos_contractuales(DESDE, HASTA, limite=LIMITE, sesion=sesion)
    )
    print(f"  eventos_contractuales: {len(eventos):,}")

    vivos, _, _ = _recorrer(
        flujos.refresco_de_vivos(
            firmados_desde=DESDE, firmados_hasta=HASTA, limite=LIMITE, sesion=sesion
        )
    )
    print(f"  refresco_de_vivos:     {len(vivos):,}  (partición del universo vivo)")

    solape = len(set(nuevos) & set(eventos))
    print(f"\n  Contratos que llegan por los flujos 1 y 2 a la vez: {solape:,}")
    print("  (Se espera solape. Lo resuelve el MERGE de la capa raw.)")

    # -------------------------------------------------------------------------
    print()
    if fallos:
        print("FALLÓ:")
        for f in fallos:
            print(f"  - {f}")
        raise SystemExit(1)
    print("Todo verificado.")


if __name__ == "__main__":
    main()