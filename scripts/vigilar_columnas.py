"""Pregunta que columnas declara la fuente y avisa si dejaron de coincidir.

## Por que existe

La ingesta pide una lista explicita de 85 columnas. Esa decision es la que da
fidelidad, y tiene un precio que no se ve: **un `$select` explicito ignora en
silencio todo lo que la fuente agregue**. Una columna nueva no rompe nada, no
sale en ningun log y no queda en raw, porque raw guarda los bytes de lo que
pedimos. Se pierde con la misma cara que tiene una corrida perfecta.

Y no se recupera despues. La fuente se sobrescribe: para cuando alguien note
que existe una columna nueva, los estados en los que aparecio ya no estan.

El caso simetrico (una columna que desaparece) si es ruidoso, pero se entera
tarde: el `$select` la nombra y la API contesta 400 a mitad de un barrido de
cincuenta minutos.

`columnas.validar_cobertura()` sabia contestar las dos preguntas desde el
principio y estaba probada, pero nadie la podia llamar porque `paginacion.py` no
exponia el endpoint de metadatos. Esto es lo que cierra ese circuito.

## Las dos preguntas que NO hay que mezclar

Esta es la misma leccion que costo 20 issues en el sondeo, aplicada antes de
volver a pagarla:

**"La cobertura esta rota"** se contesta contra `columnas.py`. Es el veredicto, y
sigue siendo verdadero todos los dias hasta que un humano clasifique la columna
nueva. Se imprime siempre.

**"El esquema cambio desde que mire"** se contesta contra el registro de la
observacion anterior. Es lo que decide si vale escribir y si vale gritar, y solo
es verdadero una vez por cambio.

Si se contestaran las dos con la misma comparacion, una columna nueva sin
clasificar abriria un issue cada tres horas, para siempre.

## El registro

`exploration/columnas_de_la_fuente.txt` guarda las columnas que la fuente
declaraba la ultima vez. Se versiona a proposito: su historial de git es la
unica evidencia de cuando el esquema de la fuente cambio, y como la fuente se
sobrescribe, no hay forma de reconstruirlo despues.

La primera observacion no cuenta como cambio. Sin esa salvedad, un registro
vacio haria aparecer las 85 columnas como recien llegadas.

## Codigos de salida

    0   se pregunto y el esquema NO se movio
    5   se pregunto y el esquema CAMBIO: hay que clasificar a mano
    2   no se pudo consultar

El 5 es propio y distinto de un error por la misma razon que en `sondear.py` y
en el cargador: quien orqueste esto tiene que poder separar "hay trabajo" de
"algo se rompio".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from secop_analytics.columnas import validar_cobertura
from secop_analytics.paginacion import ErrorDeConfiguracion, columnas_publicadas

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "exploration" / "columnas_de_la_fuente.txt"

CABECERA = """\
# Las columnas que la fuente (jbjy-vk9h) declaraba la ultima vez que se le
# pregunto, una por linea y ordenadas.
#
# Lo escribe scripts/vigilar_columnas.py. No se edita a mano: es el registro de
# lo que la FUENTE publica, no de lo que el proyecto clasifica. Eso ultimo vive
# en src/secop_analytics/columnas.py, y que los dos dejen de coincidir es
# exactamente lo que este archivo sirve para detectar.
#
# Se versiona porque su historial de git es la unica evidencia de cuando el
# esquema de la fuente cambio. La fuente se sobrescribe: si esto no queda
# escrito, no se reconstruye.
"""


class Veredicto(NamedTuple):
    """Las dos preguntas, contestadas por separado y sin mezclarse."""

    # Contra columnas.py. Persiste hasta que alguien clasifique a mano.
    sin_clasificar: frozenset[str]
    desaparecidas: frozenset[str]
    # Contra la observacion anterior. Verdadero una sola vez por cambio.
    aparecieron: frozenset[str]
    se_fueron: frozenset[str]
    primera_mirada: bool

    @property
    def cobertura_intacta(self) -> bool:
        return not self.sin_clasificar and not self.desaparecidas

    @property
    def cambio_el_esquema(self) -> bool:
        return bool(self.aparecieron or self.se_fueron)

    @property
    def vale_guardar(self) -> bool:
        return self.primera_mirada or self.cambio_el_esquema


def leer() -> set[str]:
    """Las columnas del registro anterior. Vacio si el archivo no existe todavia."""
    if not REGISTRO.exists():
        return set()
    return {
        linea.strip()
        for linea in REGISTRO.read_text(encoding="utf-8").splitlines()
        if linea.strip() and not linea.startswith("#")
    }


def escribir(publicadas: set[str]) -> None:
    REGISTRO.write_text(
        CABECERA + "\n".join(sorted(publicadas)) + "\n", encoding="utf-8"
    )


def evaluar(publicadas: set[str], registradas: set[str]) -> Veredicto:
    """Decide que pasa. Funcion pura: no toca la red ni el disco.

    La primera mirada no es un cambio. Un registro vacio contra 85 columnas
    publicadas daria "aparecieron 85", que es cierto en aritmetica y falso en lo
    que importa: la fuente no agrego nada, es que nunca habiamos mirado.
    """
    cobertura = validar_cobertura(publicadas)
    primera = not registradas
    return Veredicto(
        sin_clasificar=frozenset(cobertura["sin_clasificar"]),
        desaparecidas=frozenset(cobertura["desaparecidas"]),
        aparecieron=frozenset() if primera else frozenset(publicadas - registradas),
        se_fueron=frozenset() if primera else frozenset(registradas - publicadas),
        primera_mirada=primera,
    )


def _lista(nombres: frozenset[str]) -> str:
    return ", ".join(sorted(nombres))


def main() -> int:
    try:
        publicadas = columnas_publicadas(verboso=False)
    except ErrorDeConfiguracion as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001  cualquier fallo es "no se pudo"
        print(
            f"ERROR no se pudieron leer los metadatos: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 2

    v = evaluar(publicadas, leer())
    if v.vale_guardar:
        escribir(publicadas)

    print(f"  la fuente declara:  {len(publicadas)} columnas")
    print(f"  el proyecto cubre:  {len(publicadas) - len(v.sin_clasificar)}")
    print(f"  registro:           {REGISTRO.relative_to(RAIZ)}")

    # El veredicto se imprime SIEMPRE, se haya movido algo o no. El codigo de
    # salida calla despues del primer aviso para no repetir el issue; el log no
    # tiene por que callarse, y es lo unico que queda si el issue se cerro sin
    # arreglar nada.
    if not v.cobertura_intacta:
        print()
        print("  LA COBERTURA NO ESTA INTACTA:")
        if v.sin_clasificar:
            print(f"    sin clasificar: {_lista(v.sin_clasificar)}")
            print("      la fuente las publica y el $select no las pide.")
        if v.desaparecidas:
            print(f"    desaparecidas:  {_lista(v.desaparecidas)}")
            print("      el $select las pide y la fuente ya no las tiene:")
            print("      la proxima corrida se va a caer con HTTP 400.")
        print("    Se arregla clasificandolas en src/secop_analytics/columnas.py")

    if salida := os.environ.get("GITHUB_OUTPUT"):
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"columnas_cambio={'true' if v.cambio_el_esquema else 'false'}\n")
            f.write(f"guardar_columnas={'true' if v.vale_guardar else 'false'}\n")
            f.write(f"aparecieron={_lista(v.aparecieron)}\n")
            f.write(f"se_fueron={_lista(v.se_fueron)}\n")

    if v.cambio_el_esquema:
        print()
        print("  EL ESQUEMA DE LA FUENTE CAMBIO.")
        if v.aparecieron:
            print(f"    aparecieron: {_lista(v.aparecieron)}")
        if v.se_fueron:
            print(f"    se fueron:   {_lista(v.se_fueron)}")
        return 5

    if v.primera_mirada:
        print("  (primera observacion: se anoto, no cuenta como cambio)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
