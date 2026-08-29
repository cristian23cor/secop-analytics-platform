"""RN1: ¿la suma de las fuentes de financiación iguala `valor_del_contrato`?

## Qué se está preguntando, exactamente

`columnas.py` clasifica **seis** columnas de financiación como materiales, y
anota una duda: la sexta —`recursos_propios_alcald_as_gobernaciones_y_
resguardos_ind_genas_`— solo aparece enumerando el esquema completo, y ninguna
muestra de filas la mostró. Entra como material por el mismo criterio que las
otras cinco, pero **la definición de RN1 quedó pendiente**: ¿la suma son cinco
columnas o seis?

De eso cuelgan RN1 y RN6, y `stg_contratos` no se puede escribir sin saberlo.

## Por qué contra raw y no contra la API

Raw tiene el universo vivo entero en disco, con las seis columnas. No hace falta
pedirle nada a la fuente, y hay tres razones para no hacerlo:

1. **Los nulos.** En SoQL, un nulo en cualquier sumando anula la suma entera, y
   estas columnas están nulas casi siempre. Una consulta agregada devolvería
   nulo o una respuesta silenciosamente parcial.
2. **Totales contra filas.** Comparar `sum(seis columnas)` contra
   `sum(valor_del_contrato)` no es comparar filas: dos errores de signo opuesto
   se cancelan y el total calza. Es exactamente la clase de calce que la tercera
   regla del proyecto manda mirar dos veces.
3. **La conversión.** Los valores llegan como texto (H6) y acá se controla cómo
   se parsean, incluidos los centinelas.

Es además la primera vez que raw se usa para lo que existe: contestar sin volver
a pedir.

## ⚠ La muestra, que es parte de la respuesta

El barrido completo es el **universo vivo** —los cuatro estados de
`ESTADOS_VIVOS`— y no el histórico. RN1 sobre contratos vivos puede comportarse
distinto que sobre cerrados o liquidados. Lo que este script mida hay que
enunciarlo con esa muestra al lado.

Uso:

    uv run python scripts/medir_rn1.py
    uv run python scripts/medir_rn1.py --particion datos/raw/flujo=.../particion=completo
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from secop_analytics.escritura import NOMBRE_COMPLETO, iterar_particion

RAIZ_RAW = Path("datos/raw")

# Las seis, en el orden en que las declara `columnas.py`. La sexta va aparte
# porque es justamente la que está en discusión.
CINCO: tuple[str, ...] = (
    "presupuesto_general_de_la_nacion_pgn",
    "sistema_general_de_participaciones",
    "sistema_general_de_regal_as",
    "recursos_de_credito",
    "recursos_propios",
)
SEXTA = "recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_"
VALOR = "valor_del_contrato"

# Cuánto se tolera al comparar. Los valores vienen como texto y se leen con
# `Decimal`, así que no hay error de coma flotante: la tolerancia es para
# redondeos del lado de la fuente, no del nuestro. Un peso colombiano es la
# unidad mínima con sentido.
TOLERANCIA = Decimal("1")

# Centinelas de texto observados en la fuente, en dos capitalizaciones (H6).
# NO son ceros: son "no se sabe", y contarlos como cero inventaría un dato.
CENTINELAS = {"no definido", "no aplica", ""}


def a_decimal(crudo: object) -> Decimal | None:
    """Texto → `Decimal`, o `None` si no se puede saber cuánto vale.

    Devuelve `None` en tres casos que hay que mantener separados de un cero:
    la clave ausente, el nulo explícito y el centinela de texto. Confundir
    "no se sabe" con "vale cero" es lo que haría que RN1 pareciera cumplirse
    en filas donde no hay con qué comprobarlo.
    """
    if crudo is None:
        return None
    texto = str(crudo).strip()
    if texto.lower() in CENTINELAS:
        return None
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def ubicar_particion(raiz: Path) -> Path:
    """El barrido completo del flujo 3, que es el que tiene el universo vivo."""
    candidatas = sorted(
        d
        for d in raiz.glob("flujo=refresco_de_vivos/*/particion=completo")
        if (d / NOMBRE_COMPLETO).is_file()
    )
    if not candidatas:
        raise SystemExit(
            f"No hay ninguna partición completa del barrido en {raiz}.\n"
            "Pasá una con --particion, o corré el flujo 3 primero."
        )
    # La más vieja: es el barrido completo original. Las posteriores son
    # incrementales y traen solo lo que cambió.
    return candidatas[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--raiz", type=Path, default=RAIZ_RAW)
    parser.add_argument("--particion", type=Path, default=None)
    args = parser.parse_args()

    directorio = args.particion or ubicar_particion(args.raiz)
    print(f"\nRN1 contra raw · {directorio}\n")

    total = 0
    presencia = Counter()          # cuántas filas traen cada columna con valor
    centinelas = Counter()         # cuántas traen centinela en cada columna
    veredicto = Counter()          # cómo cierra cada fila
    sexta_no_cero = 0
    diferencias: list[tuple[str, Decimal]] = []

    for observacion in iterar_particion(directorio):
        datos = observacion["datos"]
        total += 1

        valor = a_decimal(datos.get(VALOR))
        partes = {c: a_decimal(datos.get(c)) for c in (*CINCO, SEXTA)}

        for columna, monto in partes.items():
            if monto is not None:
                presencia[columna] += 1
            elif str(datos.get(columna, "")).strip().lower() in CENTINELAS - {""}:
                centinelas[columna] += 1

        if partes[SEXTA] is not None and partes[SEXTA] != 0:
            sexta_no_cero += 1

        if valor is None:
            veredicto["sin valor_del_contrato"] += 1
            continue

        # Un nulo no es un cero, pero para sumar hay que decidir algo. Se
        # suman las que tienen valor y se cuenta aparte el caso en que NINGUNA
        # lo tiene: ahí no hay nada que comprobar y decir que RN1 se cumple
        # sería inventar.
        con_valor = [m for m in partes.values() if m is not None]
        if not con_valor:
            veredicto["sin ninguna fuente poblada"] += 1
            continue

        suma_5 = sum((partes[c] for c in CINCO if partes[c] is not None), Decimal(0))
        suma_6 = suma_5 + (partes[SEXTA] or Decimal(0))

        calza_5 = abs(suma_5 - valor) <= TOLERANCIA
        calza_6 = abs(suma_6 - valor) <= TOLERANCIA

        if calza_5 and calza_6:
            veredicto["calzan las dos (la sexta es cero o nula)"] += 1
        elif calza_6:
            veredicto["solo calza con SEIS"] += 1
        elif calza_5:
            veredicto["solo calza con CINCO"] += 1
        else:
            veredicto["no calza con ninguna"] += 1
            if len(diferencias) < 10:
                diferencias.append((str(datos.get("id_contrato")), suma_6 - valor))

    # ---------------------------------------------------------------- salida

    print(f"filas leídas: {total:,}\n")

    print("PRESENCIA DE CADA COLUMNA (con valor numérico)")
    for columna in (*CINCO, SEXTA):
        marca = "  ← la que está en discusión" if columna == SEXTA else ""
        print(f"  {presencia[columna]:>10,}  {columna}{marca}")
    if centinelas:
        print("\n  centinelas de texto encontrados:")
        for columna, cuantos in centinelas.most_common():
            print(f"    {cuantos:>10,}  {columna}")

    print(f"\nLA SEXTA CON VALOR DISTINTO DE CERO: {sexta_no_cero:,}")

    print("\nCÓMO CIERRA CADA FILA")
    for caso, cuantos in veredicto.most_common():
        print(f"  {cuantos:>10,}  ({cuantos / total:6.2%})  {caso}")

    if diferencias:
        print("\n  primeras diferencias (suma de seis menos valor_del_contrato):")
        for id_contrato, delta in diferencias:
            print(f"    {id_contrato}: {delta:+,}")

    print("\nCÓMO LEER ESTO")
    if sexta_no_cero == 0:
        print("  La sexta columna nunca trae un valor distinto de cero en esta")
        print("  muestra, así que RN1 da lo mismo con cinco o con seis. La")
        print("  decisión hay que tomarla por definición y no por evidencia:")
        print("  incluirla no cuesta nada y cubre el día que aparezca.")
    elif veredicto["solo calza con SEIS"] > veredicto["solo calza con CINCO"]:
        print("  La sexta columna ENTRA en la suma: hay filas que solo cierran")
        print("  incluyéndola.")
    else:
        print("  Mirar el reparto de arriba antes de concluir: los casos no se")
        print("  reparten como se esperaba.")

    print("\n  ⚠ La muestra es el UNIVERSO VIVO (los cuatro estados de")
    print("    ESTADOS_VIVOS), no el histórico. RN1 sobre contratos cerrados o")
    print("    liquidados puede comportarse distinto, y esto no lo mide.")

    if veredicto["no calza con ninguna"]:
        cuantas = veredicto["no calza con ninguna"]
        print(f"\n  ⚠ {cuantas:,} filas no cierran de ninguna forma. RN1 es un")
        print("    test de calidad, así que incumplirla puede ser el hallazgo y")
        print("    no el error — pero antes hay que descartar que sea nuestro.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())