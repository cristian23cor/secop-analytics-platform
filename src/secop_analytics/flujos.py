"""Los tres flujos de ingesta de SECOP II.

Cada mecanismo de cambio de la fuente necesita su propia forma de detectarlo.
Del inventario (H2) y de la sesión 3:

| Mecanismo                      | Columna que lo detecta | Volumen           |
|--------------------------------|------------------------|-------------------|
| Contrato nuevo                 | `fecha_de_firma`       | ~2.900/día        |
| Evento contractual             | `ultima_actualizacion` | ~2.065/día        |
| Avance de ejecución financiera | ninguna                | 735.809 contratos |

El tercero es la razón de ser del proyecto: los pagos ocurren y **ninguna fecha
los acompaña**, así que la única forma de detectarlos es volver a mirar el
contrato entero y comparar contra la observación anterior.

Principio de la capa de extracción: **lo único que se excluye acá son los datos
personales.** Ni el corte de 2020, ni los estados pre-firma. Esos son filtros de
negocio y viven en dbt, donde son testeables y reversibles; metidos acá,
cambiar de opinión cuesta un backfill completo. La exclusión personal es
distinta en naturaleza: es sobre lo que no queremos poseer, y su
irreversibilidad es la característica buscada.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from enum import StrEnum

import requests

from .paginacion import LIMITE_POR_DEFECTO, Fila, paginar

# Estados en los que un contrato todavía puede cambiar (H5).
#
# SUPUESTO SIN VERIFICAR (pregunta abierta 4): que los estados terminales
# —Cerrado, terminado, Cancelado— ya no se mueven. Es razonable pero no está
# probado: un contrato Cerrado podría recibir pagos rezagados. Si el supuesto
# es falso, el flujo 3 es ciego a esos pagos. Verificar antes de confiar.
ESTADOS_VIVOS: tuple[str, ...] = (
    "En ejecución",
    "Modificado",
    "Suspendido",
    "Prorrogado",
)


class Flujo(StrEnum):
    """Etiqueta que viaja con cada fila hasta la capa raw.

    Los flujos se solapan a propósito: un contrato firmado y modificado el
    mismo día llega por dos caminos. No se deduplica acá —raw resuelve con
    MERGE sobre `id_contrato`— pero saber por qué llegó cada fila es lo que
    después permite depurar un conteo que no cuadra.
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
    particiones consecutivas no se pisen. Con ambos bordes cerrados, un
    contrato firmado el 31 de enero entra en la partición de enero y en la de
    febrero, y el backfill deja de ser idempotente.
    """
    if desde >= hasta:
        raise ValueError(f"Rango vacío o invertido: {desde} .. {hasta}")
    return f"{columna} >= {_literal(desde)} AND {columna} < {_literal(hasta)}"


def _en_estados_vivos() -> str:
    valores = ", ".join(f"'{e}'" for e in ESTADOS_VIVOS)
    return f"estado_contrato in({valores})"


def contratos_nuevos(
    desde: date,
    hasta: date,
    *,
    limite: int = LIMITE_POR_DEFECTO,
    sesion: requests.Session | None = None,
) -> Iterator[list[Fila]]:
    """Contratos firmados en el rango. ~2.900 por día.

    Efecto colateral útil: filtrar por `fecha_de_firma` descarta solo por eso
    las 423.975 filas sin fecha, que H4 demostró que son todas pre-firma
    (Borrador, Cancelado, enviado Proveedor, En aprobación). No es un filtro de
    negocio disfrazado: es que un contrato sin fecha de firma no puede caer en
    ningún rango de fechas de firma. Esas filas llegan igual por el flujo 2 si
    tienen actividad.
    """
    yield from paginar(
        _rango("fecha_de_firma", desde, hasta), limite=limite, sesion=sesion
    )


def eventos_contractuales(
    desde: date,
    hasta: date,
    *,
    limite: int = LIMITE_POR_DEFECTO,
    sesion: requests.Session | None = None,
) -> Iterator[list[Fila]]:
    """Contratos con un evento contractual en el rango. ~2.065 por día.

    `ultima_actualizacion` no es auditoría técnica: es la fecha del último
    evento contractual (modificación, cesión, cierre). Está nula en el 99,5% de
    los contratos "En ejecución" porque a esos no les pasó nada desde la firma.
    El nulo es información, no ausencia — y por eso este flujo no reemplaza al
    tercero: un contrato que solo recibió pagos no aparece acá.
    """
    yield from paginar(
        _rango("ultima_actualizacion", desde, hasta), limite=limite, sesion=sesion
    )


def refresco_de_vivos(
    *,
    firmados_desde: date | None = None,
    firmados_hasta: date | None = None,
    limite: int = LIMITE_POR_DEFECTO,
    sesion: requests.Session | None = None,
) -> Iterator[list[Fila]]:
    """Vuelve a mirar los contratos que todavía pueden cambiar.

    Este es el flujo que alimenta `fct_contratos_snapshot`, y el único que
    justifica la arquitectura: detecta los avances de ejecución financiera, que
    no tienen ninguna columna de fecha que los delate.

    Sus parámetros de fecha **no son una ventana de cambio** como en los otros
    dos flujos —no existe tal ventana, ese es el punto— sino una partición del
    universo vivo. Sirven para trabajar con un pedazo en desarrollo y para
    paralelizar el barrido nocturno lanzando varias particiones a la vez. Sin
    ellos, recorre los ~2,8 millones de contratos vivos.
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
        " AND ".join(f"({c})" for c in condiciones), limite=limite, sesion=sesion
    )