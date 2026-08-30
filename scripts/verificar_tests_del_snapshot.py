"""Verifica que los tests del SCD2 detecten los defectos que dicen detectar.

## Por qué existe

Los tests del hecho dan cero contra los datos reales, y eso no demuestra nada: un
test que solo se ve dar cero no demuestra que sepa dar otra cosa. Es la lección de
I5, donde `test_el_punto_de_control_guarda_el_cursor` **pasaba y afirmaba el
defecto**.

Este script arma tablas sintéticas con los defectos sembrados, corre los tests
reales —lee los `.sql`, les saca el jinja y los ejecuta, así verifica el archivo y
no una copia— y comprueba que cada defecto salga, que los casos sanos no salgan, y
que los tests no sean redundantes entre sí.

No toca la base real ni la red. Corre en menos de un segundo, así que puede ir a
CI tal como está.

    uv run python scripts/verificar_tests_del_snapshot.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb

TESTS = Path(__file__).resolve().parent.parent / "dbt" / "tests"

# Contratos que en cada escenario están sanos: si alguno sale en un test, el test
# marca de más y eso es peor que no detectar, porque enseña a ignorarlo.
SANOS = {"OK", "LIMPIO", "CONMOTIVO", "VIVO", "OK2", "OK3", "E_OK"}


def sql_de(nombre: str, tablas: dict[str, str]) -> str:
    """El SQL del test con el jinja resuelto.

    Se lee el archivo en vez de reescribir la consulta acá: si alguien cambia el
    test y se olvida de este script, lo que corre es el test cambiado.
    """
    s = TESTS.joinpath(nombre).read_text(encoding="utf-8")
    # Las cuatro combinaciones de guion: `{#`, `{#-`, `#}` y `-#}`. El guion
    # controla si jinja se come el espacio de al lado, y algunos tests lo
    # necesitan sin guion justamente para NO comerse el salto de línea.
    s = re.sub(r"\{#-?.*?-?#\}", "", s, flags=re.S)
    s = re.sub(r"\{\{\s*config\(.*?\)\s*\}\}", "", s)
    for modelo, tabla in tablas.items():
        s = re.sub(r'\{\{\s*ref\(\s*["\']%s["\']\s*\)\s*\}\}' % modelo, tabla, s)
    if "{{" in s or "{#" in s:
        raise AssertionError(f"quedó jinja sin resolver en {nombre}")
    return s


def fixtures(con: duckdb.DuckDBPyConnection) -> None:
    # ---- Escenario 1: la forma de los intervalos y de la vigencia -----------
    con.execute(
        """create table fct(
               id_contrato varchar, version bigint,
               observado_desde varchar, observado_hasta varchar,
               es_version_vigente boolean, estado_contrato varchar,
               motivo_de_cierre varchar)"""
    )
    con.execute(
        """insert into fct (id_contrato, version, observado_desde,
                            observado_hasta, es_version_vigente) values
        -- CONTROL sano: no debe salir en ningún test
        ('OK',      1, '2026-08-22', '2026-08-23', false),
        ('OK',      2, '2026-08-23', null,         true),

        -- dos versiones abiertas: la consulta de "estado de hoy" duplicaría
        ('DOSVIG',  1, '2026-08-22', null,         true),
        ('DOSVIG',  2, '2026-08-23', null,         true),

        -- ninguna abierta: el contrato desaparecería de esa misma consulta
        ('CEROVIG', 1, '2026-08-22', '2026-08-23', false),

        -- ancho cero: es lo que produce un empate de fecha_extraccion. La
        -- versión existe y ninguna consulta puntual puede seleccionarla
        ('ANCHO0',  1, '2026-08-22', '2026-08-22', false),
        ('ANCHO0',  2, '2026-08-22', null,         true),

        ('INVERT',  1, '2026-08-23', '2026-08-22', false),
        ('INVERT',  2, '2026-08-22', null,         true),

        -- hueco: el 23 y el 24 no pertenecen a ninguna versión
        ('HUECO',   1, '2026-08-22', '2026-08-23', false),
        ('HUECO',   2, '2026-08-25', null,         true),

        -- solape: el 23 y el 24 pertenecen a dos, y toda suma los cuenta doble
        ('SOLAPE',  1, '2026-08-22', '2026-08-25', false),
        ('SOLAPE',  2, '2026-08-23', null,         true),

        -- bandera incoherente CON los conteos cuadrando, para que solo la pueda
        -- ver el test de intervalos
        ('BANDERA', 1, '2026-08-22', '2026-08-23', true),
        ('BANDERA', 2, '2026-08-23', null,         false)
        """
    )

    # ---- Escenario 2: el empate en staging ---------------------------------
    con.execute(
        """create table stg(
               id_contrato varchar, ruta_fecha_extraccion varchar,
               ruta_flujo varchar, ruta_particion varchar)"""
    )
    con.execute(
        """insert into stg values
        -- el contrato cambió entre la corrida del flujo 1 y la del flujo 3 del
        -- mismo día. Las dos escrituras son correctas
        ('EMPATE', '2026-08-22', 'contratos_nuevos',  '2026-08-20_a_2026-08-21'),
        ('EMPATE', '2026-08-22', 'refresco_de_vivos', 'completo'),

        -- CONTROL: el mismo contrato en dos días distintos es lo normal
        ('LIMPIO', '2026-08-22', 'refresco_de_vivos', 'completo'),
        ('LIMPIO', '2026-08-23', 'refresco_de_vivos', 'completo')
        """
    )

    # ---- Escenario 3: el hecho contra el motivo ----------------------------
    con.execute("create table fct_mot as select * from fct where false")
    con.execute(
        """insert into fct_mot (id_contrato, version, observado_desde,
                                observado_hasta, es_version_vigente) values
        ('CONMOTIVO', 1, '2026-08-22', '2026-08-23', false),
        ('CONMOTIVO', 2, '2026-08-23', null,         true),
        -- el hecho dice que cambió y ninguna columna difiere
        ('SINMOTIVO', 1, '2026-08-22', '2026-08-23', false),
        ('SINMOTIVO', 2, '2026-08-23', null,         true)
        """
    )
    con.execute(
        """create table int_mot(
               id_contrato varchar, version bigint, observado_desde varchar,
               columna varchar, valor_anterior varchar, valor_nuevo varchar,
               delta_valor decimal(20,2), delta_dias bigint)"""
    )
    con.execute(
        """insert into int_mot (id_contrato, version, columna) values
        ('CONMOTIVO', 2, 'valor_pagado'),   -- correcto
        ('HUERFANO',  2, 'valor_pagado'),   -- versión que no existe en el hecho
        ('CONMOTIVO', 1, 'valor_pagado')    -- la primera versión no es un cambio
        """
    )

    # ---- Escenario 4: el cruce con ESTADOS_VIVOS se rompió -----------------
    # Simula que `staging` empezó a normalizar la capitalización: ningún estado
    # calza con `estados_vivos()` y todo cae en `fuera_de_observacion`.
    con.execute("create table fct_est as select * from fct where false")
    con.execute(
        """insert into fct_est (id_contrato, version, observado_desde,
                                observado_hasta, estado_contrato,
                                motivo_de_cierre) values
        ('ROTO1', 1, '2026-08-23', null, 'EN EJECUCIÓN', 'fuera_de_observacion'),
        ('ROTO2', 1, '2026-08-23', null, 'MODIFICADO',   'fuera_de_observacion'),
        ('ROTO3', 1, '2026-08-23', null, 'SUSPENDIDO',   'fuera_de_observacion'),
        ('VIVO',  1, '2026-08-23', null, 'En ejecución', 'abierta')
        """
    )
    # Y el mismo test contra un hecho SANO, que no debe cantar.
    con.execute("create table fct_est_sano as select * from fct where false")
    con.execute(
        """insert into fct_est_sano (id_contrato, version, observado_desde,
                                     observado_hasta, estado_contrato,
                                     motivo_de_cierre) values
        ('VIVO',  1, '2026-08-23', null, 'En ejecución', 'abierta'),
        ('VIVO2', 1, '2026-08-23', null, 'Modificado',   'abierta'),
        ('VIVO3', 1, '2026-08-23', null, 'Suspendido',   'abierta'),
        ('SALIO', 1, '2026-08-23', null, 'Cerrado', 'fuera_de_observacion')
        """
    )


    # ---- Escenario 5: los dos hechos describen el mismo universo -----------
    con.execute("create table snap_uni as select * from fct where false")
    con.execute(
        """insert into snap_uni (id_contrato, version, observado_desde) values
        ('OK2', 1, '2026-08-23'),
        ('FALTA', 1, '2026-08-23'),   -- está en el snapshot y no en el hecho
        ('DUP', 1, '2026-08-23'),
        -- Estos dos existen en las dos tablas: son el control del test de
        -- universo, y a la vez los casos del test de la fecha de firma.
        ('ANTES', 1, '2026-08-23'),
        ('OK3', 1, '2026-08-23')
        """
    )
    con.execute(
        """create table hecho_uni(
               id_contrato varchar, fecha_de_firma date,
               fecha_primer_snapshot varchar,
               dias_hasta_el_primer_snapshot bigint)"""
    )
    con.execute(
        """insert into hecho_uni values
        ('OK2',   date '2026-08-18', '2026-08-23',  5),
        ('SOBRA', date '2026-08-18', '2026-08-23',  5),   -- no está en el snapshot
        ('DUP',   date '2026-08-18', '2026-08-23',  5),   -- el join multiplicó:
        ('DUP',   date '2026-08-18', '2026-08-23',  5),   -- toda suma queda al doble
        -- observado ANTES de firmarse: imposible
        ('ANTES', date '2026-08-30', '2026-08-23', -7),
        ('OK3',   date '2026-08-18', '2026-08-23',  5)
        """
    )

    # ---- Escenario 6: las cuentas del mart no se contradicen ---------------
    con.execute(
        """create table mart_coh(
               codigo_entidad varchar, familia_unspsc varchar,
               historia_completa boolean, contratos_observados bigint,
               contratos_con_extension bigint, contratos_con_adicion bigint,
               extensiones bigint, adiciones bigint)"""
    )
    con.execute(
        """insert into mart_coh values
        ('E_OK',        '8011', true, 10, 3, 2, 5, 3),   -- CONTROL sano
        ('E_EXT',       '8011', true,  2, 5, 0, 5, 0),   -- el join multiplicó
        ('E_ADI',       '8011', true,  2, 0, 5, 0, 5),   -- ídem, del otro lado
        ('E_MENOSEXT',  '8011', true, 10, 3, 0, 1, 0),   -- imposible: 3 contratos, 1 extensión
        ('E_MENOSADI',  '8011', true, 10, 0, 3, 0, 1),   -- ídem
        ('E_DUP',       '8011', true,  5, 1, 1, 1, 1),   -- la misma celda
        ('E_DUP',       '8011', true,  5, 1, 1, 1, 1)    -- dos veces
        """
    )

    # ---- Escenario 7: el mart no pierde contratos --------------------------
    con.execute(
        "create table hecho_2020(id_contrato varchar, fecha_de_firma date)"
    )
    con.execute(
        """insert into hecho_2020 values
        ('A', date '2021-01-01'), ('B', date '2022-01-01'), ('C', date '2023-01-01')
        """
    )
    con.execute("create table mart_pierde as select * from mart_coh where false")
    con.execute(
        """insert into mart_pierde (codigo_entidad, contratos_observados)
           values ('E_OK', 2)"""   # el hecho tiene 3: falta uno
    )
    con.execute("create table mart_cuadra as select * from mart_coh where false")
    con.execute(
        """insert into mart_cuadra (codigo_entidad, contratos_observados)
           values ('E_OK', 3)"""   # CONTROL: cuadra
    )

# Cada escenario: el test, a qué tabla apunta cada `ref()`, y qué tiene que salir.
ESCENARIOS: list[dict] = [
    {
        "test": "fct_una_sola_version_vigente.sql",
        "tablas": {"fct_contratos_snapshot": "fct"},
        "ids": {"DOSVIG", "CEROVIG"},
    },
    {
        "test": "fct_intervalos_encajan.sql",
        "tablas": {"fct_contratos_snapshot": "fct"},
        "ids": {"ANCHO0", "INVERT", "HUECO", "SOLAPE", "DOSVIG", "BANDERA"},
        "motivos": {
            "ANCHO0": "ancho cero",
            "INVERT": "invertido",
            "HUECO": "hueco o solape",
            "SOLAPE": "hueco o solape",
            "DOSVIG": "abierta con siguiente",
            "BANDERA": "bandera incoherente",
        },
    },
    {
        "test": "fct_una_observacion_por_contrato_y_fecha.sql",
        "tablas": {"stg_contratos": "stg"},
        "ids": {"EMPATE"},
    },
    {
        "test": "int_toda_version_tiene_su_motivo.sql",
        "tablas": {
            "fct_contratos_snapshot": "fct_mot",
            "int_cambios_por_columna": "int_mot",
        },
        "ids": {"SINMOTIVO", "HUERFANO", "CONMOTIVO"},
        "motivos": {
            "SINMOTIVO": "version sin motivo",
            "HUERFANO": "motivo huérfano",
            "CONMOTIVO": "motivo en la versión 1",
        },
    },
    {
        "test": "fct_los_estados_vivos_siguen_calzando.sql",
        "tablas": {"fct_contratos_snapshot": "fct_est"},
        "filas": 1,
        "nota": "el cruce roto: 3 de 4 abiertas caen fuera de observación",
    },
    {
        "test": "fct_los_estados_vivos_siguen_calzando.sql",
        "tablas": {"fct_contratos_snapshot": "fct_est_sano"},
        "filas": 0,
        "nota": "CONTROL: un hecho sano no debe cantar",
    },
    {
        "test": "fct_contratos_cuadra_con_el_snapshot.sql",
        "tablas": {
            "fct_contratos_snapshot": "snap_uni",
            "fct_contratos": "hecho_uni",
        },
        "ids": {"FALTA", "SOBRA", "DUP"},
        "motivos": {
            "FALTA": "falta en el hecho",
            "SOBRA": "sobra en el hecho",
            "DUP": "duplicado en el hecho",
        },
    },
    {
        "test": "fct_contratos_no_se_observa_antes_de_la_firma.sql",
        "tablas": {"fct_contratos": "hecho_uni"},
        "ids": {"ANTES"},
    },
    {
        "test": "mart_extension_es_coherente.sql",
        "tablas": {"mart_extension_de_plazo": "mart_coh"},
        "columna_id": "codigo_entidad",
        "ids": {"E_EXT", "E_ADI", "E_MENOSEXT", "E_MENOSADI", "E_DUP"},
        "motivos": {
            "E_EXT": "mas contratos con extension que observados",
            "E_ADI": "mas contratos con adicion que observados",
            "E_MENOSEXT": "menos extensiones que contratos extendidos",
            "E_MENOSADI": "menos adiciones que contratos con adicion",
            "E_DUP": "grano duplicado",
        },
    },
    {
        "test": "mart_extension_cuadra_con_el_hecho.sql",
        "tablas": {
            "mart_extension_de_plazo": "mart_pierde",
            "fct_contratos": "hecho_2020",
        },
        "filas": 1,
        "nota": "el mart perdió un contrato entero",
    },
    {
        "test": "mart_extension_cuadra_con_el_hecho.sql",
        "tablas": {
            "mart_extension_de_plazo": "mart_cuadra",
            "fct_contratos": "hecho_2020",
        },
        "filas": 0,
        "nota": "CONTROL: cuando cuadra, no dice nada",
    },
]


def main() -> int:
    con = duckdb.connect()
    fixtures(con)

    fallas: list[str] = []
    salieron: dict[str, set[str]] = {}

    for esc in ESCENARIOS:
        nombre = esc["test"]
        filas = con.execute(sql_de(nombre, esc["tablas"])).fetchall()
        columnas = [d[0] for d in con.description]

        etiqueta = f"{nombre}{'  —  ' + esc['nota'] if 'nota' in esc else ''}"
        print(f"\n{etiqueta}")
        for f in filas:
            print("   ", dict(zip(columnas, f)))
        if not filas:
            print("    (ninguna fila)")

        if "filas" in esc:
            if len(filas) != esc["filas"]:
                fallas.append(f"{etiqueta}: devolvió {len(filas)} filas, se esperaban {esc['filas']}")
            continue

        col_id = esc.get("columna_id", "id_contrato")
        obtenido = {f[columnas.index(col_id)] for f in filas}
        salieron[nombre] = obtenido

        if faltaron := esc["ids"] - obtenido:
            fallas.append(f"{nombre}: NO detectó {sorted(faltaron)}")
        if sobraron := obtenido - esc["ids"]:
            fallas.append(f"{nombre}: marcó de más {sorted(sobraron)}")
        # Un contrato sano puede aparecer legítimamente si el escenario lo
        # sembró como defecto (CONMOTIVO en la versión 1); por eso se compara
        # contra lo esperado y no contra la lista de sanos a secas.
        if colados := (obtenido & SANOS) - esc["ids"]:
            fallas.append(f"{nombre}: marcó casos SANOS {sorted(colados)}")

        for f in filas:
            cid = f[columnas.index(col_id)]
            if "motivo" in columnas and cid in esc.get("motivos", {}):
                motivo = f[columnas.index("motivo")]
                if motivo != esc["motivos"][cid]:
                    fallas.append(
                        f"{nombre}: {cid} dio motivo {motivo!r}, se esperaba "
                        f"{esc['motivos'][cid]!r}"
                    )

    # Los dos tests del hecho tienen que aportar cada uno algo que el otro no ve,
    # o uno de los dos sobra.
    vigentes = salieron["fct_una_sola_version_vigente.sql"]
    intervalos = salieron["fct_intervalos_encajan.sql"]
    if not vigentes - intervalos:
        fallas.append("fct_una_sola_version_vigente no aporta nada que fct_intervalos_encajan no vea")
    if not intervalos - vigentes:
        fallas.append("fct_intervalos_encajan no aporta nada que fct_una_sola_version_vigente no vea")

    print(f"\n{'─' * 62}")
    if fallas:
        for f in fallas:
            print(f"  ✗ {f}")
        return 1

    sembrados = sum(len(e["ids"]) for e in ESCENARIOS if "ids" in e) + 1
    print(f"  ✓ {sembrados} defectos sembrados, {sembrados} detectados, con su motivo")
    print(f"  ✓ los casos sanos no salieron donde no correspondía")
    print(f"  ✓ el canario de estados no canta contra un hecho sano")
    print(f"  ✓ solo por vigencia: {sorted(vigentes - intervalos)}")
    print(f"  ✓ solo por intervalos: {sorted(intervalos - vigentes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
