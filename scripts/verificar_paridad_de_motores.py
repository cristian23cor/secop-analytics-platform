"""Comprueba que los once modelos dan lo mismo en DuckDB y en Snowflake.

## Por que existe, y por que ahora

El porte a Snowflake (D9) demostro que el proyecto compila y corre contra los dos
motores. Eso no es lo mismo que demostrar que **producen los mismos resultados**.
Un macro de despacho mal escrito compila en los dos lados y devuelve numeros
distintos, y ninguna construccion falla.

Y hay una razon de plazo: la cuenta de Snowflake es de prueba y vence. Lo que
sobrevive al vencimiento no es la cuenta sino la **medicion fechada**, si se
captura antes. Despues del vencimiento este script no se puede correr, y su
informe queda como la evidencia.

## Que compara, y por que eso y no otra cosa

Contar filas es el minimo y no alcanza: dos tablas con la misma cantidad de filas
pueden tener contenidos distintos. Las comprobaciones apuntan a donde los motores
SI hablan dialectos distintos, que es exactamente donde una divergencia
aparecería:

- **La huella de cada observacion.** `raw_observaciones` trae el hash blake2b que
  calculo la ingesta. Comparar cuantas hay, cuantas distintas, la minima y la
  maxima sobre 2,9 millones de huellas es evidencia fuerte de que estan las
  mismas filas: si una sola difiriera, el conjunto de huellas cambiaria.
- **Los castings.** `stg_contratos` cuenta cuantos valores no se pudieron
  convertir. Es el resultado directo de `try_cast`, que cada motor implementa por
  su cuenta.
- **Las ventanas del SCD2.** `lag`, `lead` y `row_number` deciden que observacion
  genera version y donde cierra cada intervalo. Si los motores ordenaran distinto
  ante un empate, los conteos de versiones vigentes se separarian.
- **La capa intermedia.** Sus 28 ramas salen del macro generado y usan
  `dbt.datediff`, que se compila distinto en cada motor.
- **La jerarquia UNSPSC.** Se deriva con `substr` y una condicion `like`, y se
  construye con `extraer_grupo()`, uno de los tres macros de despacho.
- **Los cuatro contadores de signo del mart**, que son la respuesta a las
  preguntas 6 y 7.

## Lo que NO demuestra

No es una comparacion fila por fila: eso exigiria mover una de las dos tablas
enteras al otro motor. Es un conjunto de agregados elegidos para que una
divergencia real tenga que esconderse de todos a la vez.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

# La fecha colombiana, no la del reloj del sistema (R2). Se importa en vez de
# llamar a `date.today()`: es la tercera vez que un script nuevo del proyecto
# cae en eso, y las tres las atrapo el linter y no una revision. Ver el defecto
# de que `hoy()` viva en `scripts/` y no en `src/`.
from cargar_raw import hoy

BASE_LOCAL = os.environ.get("SECOP_DUCKDB", str(RAIZ / "datos" / "secop.duckdb"))
INFORME = RAIZ / "exploration" / "paridad_de_motores.md"

# Los esquemas donde dbt deja cada capa, en cada motor.
DUCK = {"marts": "main", "staging": "main_staging", "inter": "main_intermediate"}
SNOW = {"marts": "RAW", "staging": "RAW_STAGING", "inter": "RAW_INTERMEDIATE"}

# (modelo, capa, [(que mide, expresion SQL portable)])
COMPROBACIONES: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("raw_observaciones", "staging", [
        ("filas", "count(*)"),
        ("huellas distintas", "count(distinct hash)"),
        ("huella minima", "min(hash)"),
        ("huella maxima", "max(hash)"),
        ("particiones", "count(distinct ruta_flujo || ruta_fecha_extraccion || ruta_particion)"),
    ]),
    ("stg_contratos", "staging", [
        ("filas", "count(*)"),
        ("contratos distintos", "count(distinct id_contrato)"),
        ("castings fallidos", "sum(castings_fallidos)"),
        ("sin ciudad", "sum(case when ciudad is null then 1 else 0 end)"),
    ]),
    ("fct_contratos_snapshot", "marts", [
        ("versiones", "count(*)"),
        ("contratos distintos", "count(distinct id_contrato)"),
        ("suma de numeros de version", "sum(version)"),
        ("versiones vigentes", "sum(case when es_version_vigente then 1 else 0 end)"),
        ("cerradas por version nueva",
         "sum(case when motivo_de_cierre = 'version_nueva' then 1 else 0 end)"),
        ("fuera de observacion",
         "sum(case when motivo_de_cierre = 'fuera_de_observacion' then 1 else 0 end)"),
    ]),
    ("fct_contratos", "marts", [
        ("contratos", "count(*)"),
        ("entidades distintas", "count(distinct codigo_entidad)"),
        ("suma de versiones observadas", "sum(versiones_observadas)"),
    ]),
    ("int_cambios_por_columna", "inter", [
        ("cambios", "count(*)"),
        ("columnas distintas que cambiaron", "count(distinct columna)"),
        ("suma de delta en dias", "sum(delta_dias)"),
        ("columna mas temprana alfabeticamente", "min(columna)"),
    ]),
    ("mart_extension_de_plazo", "marts", [
        ("celdas", "count(*)"),
        ("contratos observados", "sum(contratos_observados)"),
        ("extensiones", "sum(extensiones)"),
        ("dias extendidos", "sum(dias_extendidos)"),
        ("acortamientos", "sum(acortamientos)"),
        ("dias acortados", "sum(dias_acortados)"),
    ]),
    ("dim_entidad", "marts", [
        ("versiones", "count(*)"),
        ("entidades distintas", "count(distinct codigo_entidad)"),
    ]),
    ("dim_proveedor", "marts", [
        ("versiones", "count(*)"),
        ("proveedores distintos", "count(distinct codigo_proveedor)"),
    ]),
    ("dim_modalidad", "marts", [("filas", "count(*)")]),
    ("dim_geografia", "marts", [("filas", "count(*)")]),
    ("dim_categoria", "marts", [
        ("codigos", "count(*)"),
        ("familias UNSPSC derivadas", "count(distinct familia_unspsc)"),
        ("segmentos UNSPSC derivados", "count(distinct segmento_unspsc)"),
        ("sin especificar", "sum(case when es_sin_especificar then 1 else 0 end)"),
    ]),
]


def medir_duckdb() -> dict[tuple[str, str], object]:
    con = duckdb.connect(BASE_LOCAL, read_only=True)
    out: dict[tuple[str, str], object] = {}
    for modelo, capa, checks in COMPROBACIONES:
        for etiqueta, expr in checks:
            try:
                v = con.execute(f"select {expr} from {DUCK[capa]}.{modelo}").fetchone()[0]
            except Exception as error:  # noqa: BLE001
                v = f"ERROR: {type(error).__name__}"
            out[(modelo, etiqueta)] = v
    con.close()
    return out


def medir_snowflake() -> dict[tuple[str, str], object]:
    from subir_raw_a_snowflake import conectar

    con = conectar()
    cur = con.cursor()
    out: dict[tuple[str, str], object] = {}
    for modelo, capa, checks in COMPROBACIONES:
        for etiqueta, expr in checks:
            try:
                cur.execute(f"select {expr} from {SNOW[capa]}.{modelo}")
                v = cur.fetchone()[0]
            except Exception as error:  # noqa: BLE001
                v = f"ERROR: {type(error).__name__}"
            out[(modelo, etiqueta)] = v
    con.close()
    return out


def iguales(a: object, b: object) -> bool:
    """Compara tolerando que los motores devuelvan tipos numericos distintos.

    Snowflake devuelve `Decimal` donde DuckDB devuelve `int`. Eso no es una
    divergencia de datos y no debe contarse como tal.
    """
    # Una consulta que fallo NUNCA cuenta como acuerdo, ni siquiera si fallo
    # igual en los dos motores. Dos errores no son una coincidencia: son dos
    # comprobaciones que no se hicieron, y sumarlas al total lo infla justo en el
    # numero que este informe existe para sostener.
    if any(isinstance(v, str) and v.startswith("ERROR:") for v in (a, b)):
        return False
    if a is None or b is None:
        return a is b
    if isinstance(a, str) or isinstance(b, str):
        return str(a) == str(b)
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a == b


def main() -> int:
    print("  midiendo en DuckDB...")
    duck = medir_duckdb()
    print("  midiendo en Snowflake...")
    snow = medir_snowflake()

    lineas: list[str] = []
    fallos = 0
    for modelo, _capa, checks in COMPROBACIONES:
        lineas.append(f"\n### `{modelo}`\n")
        lineas.append("| | DuckDB | Snowflake | |")
        lineas.append("|---|---:|---:|:--|")
        for etiqueta, _ in checks:
            a, b = duck[(modelo, etiqueta)], snow[(modelo, etiqueta)]
            ok = iguales(a, b)
            fallos += 0 if ok else 1
            fmt = lambda v: f"{v:,}" if isinstance(v, int) else str(v)
            lineas.append(f"| {etiqueta} | {fmt(a)} | {fmt(b)} | {'igual' if ok else '**DIFIEREN**'} |")
        print(f"  {'ok  ' if all(iguales(duck[(modelo, e)], snow[(modelo, e)]) for e, _ in checks) else 'MAL '} {modelo}")

    total = sum(len(c) for _, _, c in COMPROBACIONES)
    encabezado = f"""# Paridad entre DuckDB y Snowflake

> Generado por `scripts/verificar_paridad_de_motores.py` el {hoy().isoformat()}.
> Los once modelos construidos por el mismo proyecto de dbt, sin un solo modelo
> duplicado, medidos en los dos motores.

**{total - fallos} de {total} comprobaciones coinciden.**

Contar filas no alcanza: dos tablas del mismo tamano pueden tener contenidos
distintos. Estas comprobaciones apuntan a donde los motores hablan dialectos
distintos, que es donde una divergencia aparecería: las huellas de la ingesta,
los castings, las ventanas del SCD2, los `datediff` de la capa intermedia, la
jerarquia UNSPSC derivada con `substr`, y los cuatro contadores de signo del mart.

Los tres macros con despacho por adaptador (`campo_json`, `extraer_grupo`,
`campo_de_datos`) son los unicos lugares del proyecto que conocen el motor. Todo
lo demas es el mismo SQL.
"""
    INFORME.write_text(encabezado + "\n".join(lineas) + "\n", encoding="utf-8")
    print()
    print(f"  {total - fallos} de {total} comprobaciones coinciden")
    print(f"  informe: {INFORME.relative_to(RAIZ)}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
