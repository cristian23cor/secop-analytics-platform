"""Canonicalización y hash de una fila, para la deduplicación por bytes (D3).

Todo acá es **función pura**: no toca disco, ni red, ni reloj. Es donde vive la
lógica más delicada del cargador, así que se testea sin infraestructura.

La propiedad que sostiene todo el diseño:

    El hash es el hash de los bytes que quedan en disco.

Se serializa **una sola vez**. Esa cadena se hashea y esa misma cadena se
escribe. Así "los bytes cambiaron" y "el archivo habría sido distinto" son la
misma afirmación, y no hay dos rutas que puedan divergir en silencio.

Por eso `envolver()` **empalma bytes** en vez de volver a serializar: si armara
el diccionario completo y lo pasara por `json.dumps`, habría dos
serializaciones y la promesa se rompería justo donde nadie la va a mirar.

## Lo que este módulo NO promete

La promesa es sobre `datos`, no sobre la línea entera. La línea envuelta lleva
las claves en orden `fecha_extraccion, flujo, hash, datos`, y alfabéticamente
`datos` iría primero: **la línea completa no está canonicalizada**, aunque su
carga útil sí. Quien quiera deduplicar líneas enteras, o releerlas y compararlas
byte a byte tras un `sort_keys=True`, va a obtener algo distinto de lo que hay
en disco.

Referencias: `exploration/03_decisiones_capa_raw.md` — D1 (raw no normaliza),
D3 (deduplicación por bytes), I1 (la forma canónica) e I2 (el algoritmo).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

# Nombre del algoritmo tal como se escribe en el manifiesto de cada partición.
# Si algún día cambia, hay que poder distinguir hashes viejos de nuevos sin
# adivinar (I2).
ALGORITMO_HASH: Final[str] = "blake2b-128"

# 16 bytes = 128 bits. Ni 64 (colisión ~1 en 100.000 sobre 20M de
# observaciones) ni 256 (el doble de índice sin ganancia). La colisión es el
# ÚNICO error del diseño que va en la dirección cara: el cargador concluiría
# "no cambió nada", no guardaría la fila, y la observación se perdería para
# siempre porque la fuente ya se sobrescribió.
_TAMANO_DIGEST: Final[int] = 16

# Estos tres argumentos de `json.dumps` son el contrato del índice. Cambiar
# cualquiera invalida TODOS los hashes ya guardados.
#
#   sort_keys     — el orden de las claves no es información: {"a":1,"b":2} y
#                   {"b":2,"a":1} son el mismo objeto JSON. Ordenar no es
#                   normalizar, así que no rompe D1. Aplica también dentro de
#                   `urlproceso`, el único objeto anidado (H6).
#   ensure_ascii  — en False la eñe se escribe como eñe. Archivo más chico y
#                   legible. Consistencia importa más que cuál se elija.
#   separators    — sin esto json.dumps mete un espacio tras cada coma y cada
#                   dos puntos. Sobre 2,8M de filas es volumen que no dice nada.
_OPCIONES_JSON: Final[dict[str, Any]] = {
    "sort_keys": True,
    "ensure_ascii": False,
    "separators": (",", ":"),
}


def canonicalizar(fila: dict[str, Any]) -> bytes:
    """Serializa la fila a su forma canónica. Determinista.

    Dos diccionarios con las mismas claves y valores producen los mismos bytes,
    sin importar en qué orden los devolvió la API.

    ⚠ NO rellena las claves que la API omitió. D1 prohíbe normalizar en raw.

    La consecuencia hay que conocerla antes de "arreglarla": si una noche la API
    omite `ultima_actualizacion` y a la siguiente la manda como `null` sin que
    nada haya cambiado, el hash cambia y se guarda una fila de más. Es el error
    que SOBRA, o sea el aceptable — el diseño entero está construido sobre
    preferir el error que sobra al que falta. Rellenar acá lo convertiría en un
    error que falta, y además rompería D1.
    """
    try:
        return json.dumps(fila, **_OPCIONES_JSON).encode("utf-8")
    except (TypeError, ValueError) as error:
        # Falla ruidosa con el identificador puesto. Saltarse la fila en
        # silencio sería perderla: la fuente se sobrescribe esta noche.
        raise ValueError(
            f"No se pudo serializar la fila "
            f"{fila.get('id_contrato', '(sin id_contrato)')!r}: {error}"
        ) from error


def hashear(linea_canonica: bytes) -> str:
    """Hash hexadecimal de 32 caracteres sobre los bytes canónicos.

    En hexadecimal y no en bytes crudos: 90 MB contra 45 MB para 2,8M de
    contratos —irrelevante— a cambio de poder leerlo en una consulta de DuckDB
    mientras se depura.

    No comprueba que la entrada sea canónica: espera la salida de
    `canonicalizar()`. Hashear cualquier otra cosa produce un hash válido y
    sin sentido.
    """
    return hashlib.blake2b(linea_canonica, digest_size=_TAMANO_DIGEST).hexdigest()


def envolver(
    linea_canonica: bytes,
    *,
    huella: str,
    flujo: str,
    fecha_extraccion: str,
) -> bytes:
    """Arma la línea que va al archivo, sin volver a serializar la carga útil.

    Resultado:

        {"fecha_extraccion":"…","flujo":"…","hash":"…","datos":{…}}

    Los metadatos van FUERA del hash y por eso se agregan acá y no antes:
    `fecha_extraccion` y `flujo` cambian todas las noches por definición, así
    que si entraran al hash nada se deduplicaría jamás.

    El empalme de bytes es deliberado. Construir el diccionario completo y
    pasarlo por `json.dumps` sería más legible y serializaría dos veces: los
    bytes de `datos` en el archivo serían una reserialización que *casualmente*
    coincide con lo hasheado, en vez de ser literalmente lo hasheado.
    """
    cabecera = json.dumps(
        {"fecha_extraccion": fecha_extraccion, "flujo": flujo, "hash": huella},
        **_OPCIONES_JSON,
    )
    # Se le quita la llave de cierre para pegarle `datos` y cerrarla al final.
    # El assert documenta la suposición: si alguien cambia la cabecera por algo
    # que no termine en `}`, el resultado sería JSON inválido en disco y solo
    # se descubriría al leerlo.
    assert cabecera.endswith("}"), f"cabecera inesperada: {cabecera!r}"
    return cabecera[:-1].encode("utf-8") + b',"datos":' + linea_canonica + b"}"


def verificar_linea(linea: bytes) -> bool:
    """¿La línea escrita tiene el hash que dice tener?

    Relee la línea, vuelve a canonicalizar `datos` y compara contra el `hash`
    guardado. Es la comprobación que sostiene D3: si falla, la deduplicación
    está construida sobre arena.

    Vive acá y no en el script de verificación porque el invariante es de este
    módulo. Reimplementarla afuera crea dos definiciones de lo mismo.

    ⚠ **Depende de que todos los valores sean texto** (H6). El viaje de ida y
    vuelta por `json.loads` preserva los strings exactamente, pero no
    necesariamente los números: un `1.10` volvería como `1.1` y esta función
    reportaría una discrepancia sin que nada esté roto. Hoy la fuente entrega
    todo como texto; si eso cambiara, hay que revisar esta comprobación antes
    de creerle.
    """
    observacion = json.loads(linea)
    return hashear(canonicalizar(observacion["datos"])) == observacion["hash"]


def preparar(
    fila: dict[str, Any], *, flujo: str, fecha_extraccion: str
) -> tuple[str, str, bytes]:
    """Canonicaliza, hashea y envuelve en un solo paso.

    Devuelve `(id_contrato, huella, linea_para_escribir)`.

    El `id_contrato` sale acá porque es la llave del índice de hashes. Si
    faltara, la fila no se puede deduplicar ni unir con nada: es un fallo del
    `$select` o de la fuente, y en los dos casos hay que enterarse en el
    momento, no descubrirlo en dbt tres capas después.
    """
    id_contrato = fila.get("id_contrato")
    if not id_contrato:
        raise ValueError(
            "Fila sin `id_contrato`. Es la llave del índice y de todo el "
            f"modelo. Claves recibidas: {sorted(fila)[:10]}"
        )

    linea_canonica = canonicalizar(fila)
    huella = hashear(linea_canonica)
    linea = envolver(
        linea_canonica,
        huella=huella,
        flujo=flujo,
        fecha_extraccion=fecha_extraccion,
    )
    return str(id_contrato), huella, linea