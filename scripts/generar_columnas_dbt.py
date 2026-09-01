"""Genera el macro de dbt con el esquema, desde `columnas.py` y `flujos.py`.

## Por qué existe

`columnas.py` es la fuente de verdad de las 85 columnas y de su clasificación.
dbt necesita la misma información (para armar el `STRUCT` del modelo frontera y
para saber qué columnas comparar) y la única forma de que no se desincronicen es
que una se genere de la otra.

Es el mismo patrón que el proyecto ya usa con los dobles de `conftest.py`, y por
la misma razón: dos listas escritas a mano se separan, y cuando se separan los
tests siguen pasando. El defecto del conteo de tests (139 documentados contra 144
reales, invisible porque el desglose estaba incompleto) es la versión suave del
mismo problema.

## Por qué un macro y no variables ni un seed

Un macro es la forma natural de que dbt tenga una lista en **tiempo de
compilación**, que es cuando el modelo frontera la necesita para armar el
`STRUCT`. Las variables en `dbt_project.yml` meterían datos generados en el
archivo que nadie debe tocar; un seed sería una tabla consultable, disponible
recién en tiempo de consulta y con un `dbt seed` extra antes de cada corrida.

## Por qué también lee `flujos.py`

El nombre del script dice `columnas` y lee dos módulos. La lista de estados vivos
no es del esquema (no clasifica una columna) sino del universo que el flujo 3
barre, así que vive con el flujo. Pero dbt la necesita por el mismo motivo que
necesita la clasificación: `motivo_de_cierre` distingue una versión que sigue en
observación de una que salió del universo, y "salió" significa exactamente "ya no
está en el `$where` del flujo 3". Copiarla al modelo crearía dos definiciones del
universo vivo, y el día que se separen `motivo_de_cierre` diría "abierta" sobre
contratos que hace meses que nadie mira.

## El contrato con `verificar_columnas_dbt.py`

Este script **escribe**; el otro **comprueba**. Correr el segundo en CI es lo que
convierte "hay que acordarse de regenerar" en un fallo ruidoso.

Uso:

    uv run python scripts/generar_columnas_dbt.py
    uv run python scripts/generar_columnas_dbt.py --comprobar   # no escribe
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from secop_analytics.columnas import (
    CENTINELA_ES_VALOR,
    CENTINELAS,
    COLUMNAS_EXTRAIDAS,
    COSMETICAS,
    ENTERAS,
    FECHAS,
    FUENTES_DE_FINANCIACION,
    IMPOSIBLES,
    MATERIALES,
    MONETARIAS,
    clasificacion,
)

# `ESTADOS_VIVOS` no vive en `columnas.py` sino en `flujos.py`, porque no es
# una propiedad del esquema sino del universo que el flujo 3 barre. Se importa
# igual: es la misma lista con la que se arma el `$where`, y `motivo_de_cierre`
# tiene que decir "sigue en observación" sobre exactamente esos contratos.
from secop_analytics.flujos import ESTADOS_VIVOS

DESTINO = Path("dbt/macros/columnas_generado.sql")

# `urlproceso` es el único objeto anidado de las 67 (H6). En el `STRUCT` va como
# JSON y no como VARCHAR: declararla texto haría que DuckDB tuviera que decidir
# cómo serializar el objeto, y esa decisión es normalizar. Raw la guarda tal como
# llegó (D1, D2) y `staging` la aplana cuando corresponda.
ANIDADAS: frozenset[str] = frozenset({"urlproceso"})

CABECERA = """{#-
  ARCHIVO GENERADO. NO EDITAR A MANO.

  Lo escribe `scripts/generar_columnas_dbt.py` desde `src/secop_analytics/columnas.py`,
  que es la fuente de verdad del esquema, y desde `flujos.py`, que lo es del
  universo vivo. Editar acá crea una segunda lista que
  se va a separar de la primera, y cuando se separe los tests van a seguir
  pasando, que es exactamente el modo de fallo que este archivo existe para
  evitar.

  Para cambiar algo: tocá `columnas.py` y volvé a correr el generador.
  `scripts/verificar_columnas_dbt.py` lo comprueba en CI.

  Generado desde CANTIDAD columnas extraídas.
-#}
"""


def cuerpo() -> str:
    """El texto del macro. Determinista: mismo `columnas.py`, mismo archivo."""
    lista = ",\n".join(f'        "{c}"' for c in COLUMNAS_EXTRAIDAS)

    campos = ",\n".join(
        f"        {c} {'JSON' if c in ANIDADAS else 'VARCHAR'}"
        for c in COLUMNAS_EXTRAIDAS
    )

    def bloque(nombre: str, conjunto: frozenset[str]) -> str:
        # Solo las extraídas: PERSONALES no viaja y no tiene sentido en dbt.
        miembros = sorted(conjunto & set(COLUMNAS_EXTRAIDAS))
        cuerpo_lista = ",\n".join(f'        "{c}"' for c in miembros)
        return (
            f"{{% macro columnas_{nombre}() %}}\n"
            f"    {{{{ return([\n{cuerpo_lista}\n    ]) }}}}\n"
            f"{{% endmacro %}}\n"
        )

    return (
        CABECERA.replace("CANTIDAD", str(len(COLUMNAS_EXTRAIDAS)))
        + "\n"
        + "{#- Las 67 que se le piden a la API. El orden es el de `columnas.py`,\n"
        "    que las ordena alfabéticamente: importa para que el archivo\n"
        "    generado sea estable entre corridas. -#}\n"
        "{% macro columnas_extraidas() %}\n"
        f"    {{{{ return([\n{lista}\n    ]) }}}}\n"
        "{% endmacro %}\n"
        "\n"
        "{#- El `STRUCT` con el que el modelo frontera lee `datos`.\n\n"
        "    Se declara explícito y NO se deja inferir. `read_json_auto` deduce\n"
        "    la forma de una muestra de filas, y la API omite las claves nulas\n"
        "    (H6): una columna que ninguna fila muestreada traiga no entra al\n"
        "    struct, y el modelo que la use falla. Las que arrancan nulas y se\n"
        "    llenan son justo las materiales: las tres fechas de hito y\n"
        "    `ultima_actualizacion`.\n\n"
        "    Es el mismo error que se cometió con la sexta fuente de\n"
        "    financiación de RN1: 'no apareció en la muestra' se leyó como 'casi\n"
        "    nunca tiene valor', y estaba en el 45% de los contratos.\n\n"
        "    Una clave que la fuente agregue y este struct no tenga se ignora\n"
        "    EN SILENCIO. No es un agujero nuevo: el `$select` ya pide solo\n"
        "    estas 67, así que raw nunca las trae. Quien detecta columnas nuevas\n"
        "    es `columnas.validar_cobertura()`. -#}\n"
        "{% macro struct_de_datos() %}\n"
        f"    {{%- set campos %}}STRUCT(\n{campos}\n    ){{% endset -%}}\n"
        "    {{ return(campos | trim) }}\n"
        "{% endmacro %}\n"
        "\n"
        "{#- Clasificación de D6 / sección 5 del modelo dimensional. Decide qué genera\n"
        "    versión nueva en el SCD2, no qué se descarga.\n\n"
        "    Raw NO usa esto: ahí la comparación es de bytes y no distingue\n"
        "    categorías. Son dos filtros de finura distinta. -#}\n"
        + bloque("materiales", MATERIALES)
        + "\n"
        + bloque("imposibles", IMPOSIBLES)
        + "\n"
        + bloque("cosmeticas", COSMETICAS)
        + "\n"
        + "{#- Tipos de destino de `stg_contratos`. Eje DISTINTO de la\n"
        "    clasificación de arriba: aquella decide qué genera versión, ésta\n"
        "    decide a qué se castea. Lo que no está en ninguno queda texto. -#}\n"
        + bloque("monetarias", MONETARIAS)
        + "\n"
        + bloque("fechas", FECHAS)
        + "\n"
        + bloque("enteras", ENTERAS)
        + "\n"
        + "{#- Donde el centinela NO se convierte a nulo:\n"
        "    `habilita_pago_adelantado` tiene tres estados y 'No Definido'\n"
        "    significa 'no se declaró' (RN10). -#}\n"
        + bloque("centinela_es_valor", CENTINELA_ES_VALOR)
        + "\n"
        + "{% macro centinelas() %}\n"
        + "    {{ return([\n"
        + ",\n".join(f'        "{c}"' for c in CENTINELAS)
        + "\n    ]) }}\n"
        + "{% endmacro %}\n"
        + "\n"
        + "{#- Las columnas que llegan como objeto anidado y no como escalar.\n\n"
        "    Hoy es una sola, `urlproceso`, y por eso es tentador escribir ese\n"
        "    nombre a mano donde haga falta. Se genera porque hay ya dos lugares\n"
        "    que necesitan saberlo: el `STRUCT` del modelo frontera, que la\n"
        "    declara JSON en vez de VARCHAR, y la proyeccion de ese mismo modelo,\n"
        "    que no le puede aplicar el casteo a texto que le aplica a las otras\n"
        "    66. Dos lugares es donde empieza la desincronizacion. -#}\n"
        + "{% macro columnas_anidadas() %}\n"
        + "    {{ return([\n"
        + ",\n".join(f'        "{c}"' for c in sorted(ANIDADAS))
        + "\n    ]) }}\n"
        + "{% endmacro %}\n"
        + "\n"
        + "{#- Las seis fuentes de financiación del contrato.\n\n"
        "    Son un concepto, no una coincidencia de clasificación: RN1 exige\n"
        "    que sumen `valor_del_contrato` y RN6 que eso valga en toda versión\n"
        "    histórica. Están en MATERIALES y en MONETARIAS a la vez, así que\n"
        "    deducirlas de la intersección de esos dos macros sería frágil (hay\n"
        "    otras diez columnas en las dos). Van con nombre propio.\n\n"
        "    Son seis. La sexta no aparece en ninguna muestra de filas porque\n"
        "    la API omite las claves nulas, y sin embargo 1.280.989 contratos\n"
        "    cierran RN1 solo incluyéndola. -#}\n"
        + bloque("fuentes_de_financiacion", FUENTES_DE_FINANCIACION)
        + "\n"
        + "{#- Los estados en los que un contrato todavía puede cambiar (H5).\n\n"
        "    Sale de `flujos.py`, no de `columnas.py`: es la MISMA lista con la\n"
        "    que el flujo 3 arma su `$where`. Así, lo que `motivo_de_cierre`\n"
        "    llama 'sigue en observación' es exactamente lo que la ingesta sigue\n"
        "    barriendo. Copiarla al modelo daría dos definiciones del universo\n"
        "    vivo, y el día que se separen la tabla diría 'abierta' sobre\n"
        "    contratos que ya nadie mira.\n\n"
        "    Los valores van con la capitalización de la API. `staging` no\n"
        "    normaliza `estado_contrato` (comprobado el 29/08/2026: `terminado`\n"
        "    y `cedido` siguen en minúscula en el hecho), así que la\n"
        "    comparación es directa. Si algún día staging normaliza, esta lista\n"
        "    deja de calzar y `motivo_de_cierre` se vuelve todo\n"
        "    'fuera_de_observacion' sin que nada falle.\n\n"
        "    Y arrastra el supuesto sin verificar de la pregunta abierta 3 del\n"
        "    inventario: que los estados terminales ya no se mueven. -#}\n"
        + "{% macro estados_vivos() %}\n"
        + "    {{ return([\n"
        + ",\n".join(f'        "{e}"' for e in ESTADOS_VIVOS)
        + "\n    ]) }}\n"
        + "{% endmacro %}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--destino", type=Path, default=DESTINO)
    parser.add_argument(
        "--comprobar",
        action="store_true",
        help="No escribe: falla si el archivo en disco no es el que se generaría.",
    )
    args = parser.parse_args()

    # Comprobación de coherencia antes de generar nada. Si los conjuntos se
    # solapan, una columna quedaría clasificada dos veces y el macro diría dos
    # cosas distintas según cuál se consulte. `tests/test_columnas.py` ya lo
    # verifica, pero generar un archivo a partir de datos inconsistentes es
    # peor que fallar.
    for columna in COLUMNAS_EXTRAIDAS:
        clasificacion(columna)  # levanta KeyError si no está en ningún conjunto

    esperado = cuerpo()

    if args.comprobar:
        if not args.destino.is_file():
            print(f"ERROR Falta {args.destino}. Corré el generador.", file=sys.stderr)
            return 1
        actual = args.destino.read_text(encoding="utf-8")
        if actual != esperado:
            print(
                f"ERROR {args.destino} no coincide con `columnas.py`.\n"
                "   Alguien tocó uno de los dos sin regenerar el otro. dbt "
                "estaría usando\n   un esquema distinto del que la ingesta pide "
                "a la API.\n\n"
                "   Arreglo: uv run python scripts/generar_columnas_dbt.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK {args.destino} está sincronizado con columnas.py")
        return 0

    args.destino.parent.mkdir(parents=True, exist_ok=True)
    args.destino.write_text(esperado, encoding="utf-8")
    print(
        f"OK {args.destino}\n"
        f"   {len(COLUMNAS_EXTRAIDAS)} columnas / "
        f"{len(MATERIALES & set(COLUMNAS_EXTRAIDAS))} materiales / "
        f"{len(IMPOSIBLES & set(COLUMNAS_EXTRAIDAS))} imposibles / "
        f"{len(COSMETICAS & set(COLUMNAS_EXTRAIDAS))} cosméticas"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())