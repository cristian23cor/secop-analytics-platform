"""Los tres flujos de ingesta de SECOP II.

Cada mecanismo de cambio de la fuente necesita su propia forma de detectarlo
(H2):

| Mecanismo                      | Columna que lo detecta | Volumen           |
|--------------------------------|------------------------|-------------------|
| Contrato nuevo                 | `fecha_de_firma`       | ~2.900/día        |
| Evento contractual             | `ultima_actualizacion` | ~2.065/día        |
| Avance de ejecución financiera | ninguna                | 735.809 contratos |

El tercero es la razón de ser del proyecto: los pagos ocurren y **ninguna fecha
los acompaña**, así que la única forma de detectarlos es volver a mirar el
contrato entero y comparar contra la observación anterior.

## Qué se excluye acá, y qué queda afuera sin ser excluido

**Por regla, solo los datos personales.** Ni el corte de 2020, ni los estados
pre-firma. Esos son filtros de negocio y viven en dbt, donde son testeables y
reversibles; metidos acá, cambiar de opinión cuesta un backfill completo. La
exclusión personal es distinta en naturaleza: es sobre lo que no queremos
poseer, y su irreversibilidad es la característica buscada.

**Pero hay una población que queda afuera por construcción**, y conviene saberlo
antes de buscarla en raw y no encontrarla. Las 423.975 filas sin
`fecha_de_firma` (todas pre-firma, según H4) no entran por ningún flujo:

- Flujo 1 las descarta porque una fila sin fecha de firma no cae en ningún
  rango de fechas de firma.
- Flujo 2 casi tampoco: H8 muestra que `Borrador`, `enviado Proveedor` y
  `En aprobación` tienen `ultima_actualizacion` nula en el **100%** de los
  casos, y `Cancelado` en el 99,9%.
- Flujo 3 tampoco: ninguno de esos estados está en `ESTADOS_VIVOS`.

No es un problema (el negocio las excluye igual (RN2)) pero sí una diferencia
que hay que nombrar: los personales quedan afuera **por regla**, estas quedan
afuera **por construcción**. Y una consecuencia práctica: los tests de dbt que
filtran estados pre-firma no van a tener nada que filtrar.

Referencias: `00_inventario_fuentes.md` (H2, H4, H5, H8, H9) y
`03_decisiones_capa_raw.md` (cómo consume esto la capa raw).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from enum import StrEnum
from typing import Final

import requests

from .paginacion import LIMITE_POR_DEFECTO, Fila, paginar

# Estados en los que un contrato todavía puede cambiar (H5).
#
# SUPUESTO SIN VERIFICAR (pregunta abierta 3 del inventario): que los estados
# terminales (Cerrado, terminado, Cancelado) ya no se mueven. Es razonable pero
# no está probado: un contrato Cerrado podría recibir pagos rezagados. Si el
# supuesto es falso, el flujo 3 es ciego a esos pagos y nada lo delata.
ESTADOS_VIVOS: Final[tuple[str, ...]] = (
    "En ejecución",
    "Modificado",
    "Suspendido",
    "Prorrogado",
)


class Flujo(StrEnum):
    """Etiqueta de por qué se pidió cada fila.

    Este módulo no la agrega a las filas. Los tres flujos devuelven lo
    que la API entregó, sin tocar nada; etiquetar es trabajo del cargador. Acá
    solo viven los nombres, para que el cargador y la ruta en disco usen los
    mismos.

    Los flujos se solapan a propósito: un contrato firmado y modificado el
    mismo día llega por dos caminos. No se deduplica acá.

    Una consecuencia de la deduplicación por bytes: cuando dos flujos traen
    la misma fila idéntica, solo se guarda una vez, con la etiqueta del que
    llegó primero. O sea que en raw la etiqueta significa "quién lo trajo
    antes", no "por qué caminos podía llegar". Si algún día hace falta lo
    segundo, se cuenta en el cargador antes de deduplicar y se anota en el
    manifiesto.
    """

    NUEVOS = "contratos_nuevos"
    EVENTOS = "eventos_contractuales"
    REFRESCO = "refresco_de_vivos"


def _literal(momento: date) -> str:
    """Formatea una fecha como literal de SoQL (floating timestamp)."""
    return f"'{momento.isoformat()}T00:00:00.000'"


def _rango(columna: str, desde: date, hasta: date) -> str:
    """Intervalo semiabierto: `>= desde AND < hasta`.

    El borde cerrado a la izquierda y abierto a la derecha es lo que hace que
    ventanas consecutivas no se pisen. Con ambos bordes cerrados, un contrato
    firmado el 31 de enero entra en la ventana de enero y en la de febrero, y
    el backfill deja de ser idempotente.

    Es el mismo criterio que usan `observado_desde` / `observado_hasta` en la
    tabla de snapshots: semiabierto en los dos extremos del pipeline.
    """
    if desde >= hasta:
        raise ValueError(f"Rango vacío o invertido: {desde} .. {hasta}")
    return f"{columna} >= {_literal(desde)} AND {columna} < {_literal(hasta)}"


def _en_estados_vivos() -> str:
    """Filtro `in(...)` sobre `ESTADOS_VIVOS`.

    Los valores no se escapan porque son constantes de este módulo, no entrada
    de usuario. Si alguna vez `ESTADOS_VIVOS` pasara a leerse de afuera, hay
    que escaparlos con el mismo helper que usa `paginacion.py`.
    """
    valores = ", ".join(f"'{e}'" for e in ESTADOS_VIVOS)
    return f"estado_contrato in({valores})"


def contratos_nuevos(
    desde: date,
    hasta: date,
    *,
    limite: int = LIMITE_POR_DEFECTO,
    sesion: requests.Session | None = None,
    desde_cursor: str | None = None,
) -> Iterator[list[Fila]]:
    """Contratos firmados en el rango. ~2.900 por día.

    Filtrar por `fecha_de_firma` descarta de paso las 423.975 filas sin fecha,
    que H4 demostró que son todas pre-firma. No es un filtro de negocio
    disfrazado: es que una fila sin fecha de firma no puede caer en ningún
    rango de fechas de firma.

    Pero esas filas tampoco llegan por los otros dos flujos: ver el aviso del
    encabezado del módulo. En la práctica no entran a raw.
    """
    yield from paginar(
        _rango("fecha_de_firma", desde, hasta),
        limite=limite, sesion=sesion, desde_cursor=desde_cursor,
    )


def eventos_contractuales(
    desde: date,
    hasta: date,
    *,
    limite: int = LIMITE_POR_DEFECTO,
    sesion: requests.Session | None = None,
    desde_cursor: str | None = None,
) -> Iterator[list[Fila]]:
    """Contratos con un evento contractual en el rango. ~2.065 por día.

    `ultima_actualizacion` no es auditoría técnica: es la fecha del último
    evento contractual (modificación, cesión, cierre). Está nula en el 99,5% de
    los contratos "En ejecución" porque a esos no les pasó nada desde la firma.

    El nulo es información, no ausencia, y por eso este flujo no reemplaza al
    tercero: un contrato que solo recibió pagos no aparece acá.
    """
    yield from paginar(
        _rango("ultima_actualizacion", desde, hasta),
        limite=limite, sesion=sesion, desde_cursor=desde_cursor,
    )


def refresco_de_vivos(
    *,
    firmados_desde: date | None = None,
    firmados_hasta: date | None = None,
    limite: int = LIMITE_POR_DEFECTO,
    sesion: requests.Session | None = None,
    desde_cursor: str | None = None,
) -> Iterator[list[Fila]]:
    """Vuelve a mirar los contratos que todavía pueden cambiar.

    Este es el flujo que alimenta `fct_contratos_snapshot`, y el único que
    justifica la arquitectura: detecta los avances de ejecución financiera, que
    no tienen ninguna columna de fecha que los delate (H9).

    Sus parámetros de fecha no son una ventana de cambio como en los otros
    dos flujos (no existe tal ventana, ese es el punto) sino una partición de
    paralelismo: un reparto del universo vivo entre varios procesos de la
    misma corrida. Sin ellos, recorre los ~2.825.685 contratos vivos.

    La corrida ocurre una vez por cada regeneración de la fuente, que no es
    todos los días (H34). Qué dispara el flujo lo decide el corte, no el
    calendario: ver D11 en `03_decisiones_capa_raw.md`.

    Los parámetros de fecha no son una ventana de backfill. Darle fechas
    viejas no reprocesa el pasado: devuelve el estado de hoy de los contratos
    firmados entonces. El guardarraíl que lo impide vive en el orquestador, no
    acá: este módulo no sabe con qué fecha se está escribiendo. Ver R1 en
    `03_decisiones_capa_raw.md`.
    """
    condiciones = [_en_estados_vivos()]

    if firmados_desde is not None and firmados_hasta is not None:
        condiciones.append(_rango("fecha_de_firma", firmados_desde, firmados_hasta))
    elif firmados_desde is not None or firmados_hasta is not None:
        raise ValueError(
            "La partición necesita ambos bordes, o ninguno. Un borde suelto "
            "produce un recorrido que parece acotado y no lo está."
        )

    yield from paginar(
        " AND ".join(f"({c})" for c in condiciones),
        limite=limite, sesion=sesion, desde_cursor=desde_cursor,
    )