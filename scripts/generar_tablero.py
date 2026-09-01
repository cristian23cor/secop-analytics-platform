"""Genera el tablero como una sola página HTML, sin dependencias.

## Por qué un archivo y no una aplicación

El proyecto entero se apoya en que cualquiera pueda clonar el repositorio y abrir
un archivo de raw con la biblioteca estándar. El tablero sigue el mismo criterio:
este script consulta el modelo, escribe `docs/index.html` con los datos adentro,
esa página se abre con doble clic, se manda por correo o se publica en cualquier
lado. Sin servidor, sin proceso corriendo, sin instalar nada.

La otra razón es de tamaño. El archivo DuckDB pesa más de 6 GB, así que ninguna
herramienta que lea la base directo se puede publicar. Lo que se publica son los
agregados, que caben en unas pocas decenas de kilobytes.

Y como es un script, el tablero es reproducible: se vuelve a correr después de
cada ingesta y sale al día, con los mismos números que el modelo.

## Qué muestra, y qué se negó a mostrar

Muestra el estado del pipeline, la cadencia real de la fuente, las respuestas a
las preguntas 6 y 7, y los hallazgos que tienen número.

Lo que NO hace es elegir por el lector entre las dos poblaciones de contratos.
Los análisis de delta solo valen para los observados desde cerca de su firma, que
hoy son el 2,7% con un margen de treinta días. Un tablero que muestre solo la
población amplia da un número más grande y más falso; uno que muestre solo la
medible arranca casi vacío. Están las dos, con su tamaño al lado.

## La paleta

Salió de la guía de visualización del proyecto y se validó con su script: azul y
naranja, con separación para daltonismo de 24,7 en modo claro y 26,8 en oscuro
sobre un objetivo de 8. Los colores de estado de la tira de cadencia son los
reservados, y nunca cargan significado solos: van siempre con su etiqueta.

Uso:

    uv run python scripts/generar_tablero.py
    uv run python scripts/generar_tablero.py --salida /tmp/prueba.html
"""

from __future__ import annotations

import argparse
import html
import sys
from datetime import date
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cargar_raw import hoy

BASE = Path(__file__).resolve().parent.parent
DUCKDB = BASE / "datos" / "secop.duckdb"
RAW = BASE / "datos" / "raw"
# `docs/index.html` y no `tablero.html` en la raiz: GitHub Pages sirve el
# contenido de `docs/` en la raiz de la URL, asi que el tablero queda en
# usuario.github.io/repo/ en vez de .../repo/tablero.html. Se comparte mejor.
SALIDA = BASE / "docs" / "index.html"

# El registro de sondeo. No sale de la base: son observaciones de la fuente que
# no se cargaron, y por eso ningún manifiesto las tiene. Ver la pregunta abierta
# sobre dónde debería vivir este registro.
CADENCIA: list[tuple[str, str]] = [
    ("2026-08-18", "regenero"),
    ("2026-08-19", "sin observar"),
    ("2026-08-20", "regenero"),
    ("2026-08-21", "no regenero"),
    ("2026-08-22", "sin observar"),
    ("2026-08-23", "sin observar"),
    ("2026-08-24", "sin observar"),
    ("2026-08-25", "regenero"),
    ("2026-08-26", "no regenero"),
    ("2026-08-27", "no regenero"),
    ("2026-08-28", "no regenero"),
    ("2026-08-29", "no regenero"),
    ("2026-08-30", "sin observar"),
    ("2026-08-31", "no regenero"),
]
CORTE_VIVO = "2026-08-25T09:05:54.277Z"

# El margen con el que el mart separa las dos poblaciones. Se repite acá porque
# el tablero lo tiene que explicar, no porque lo decida: la fuente es el modelo.
MARGEN_DIAS = 30


def consultar(con: duckdb.DuckDBPyConnection) -> dict:
    """Todos los agregados que el tablero necesita, en una sola pasada."""
    uno = lambda sql: con.execute(sql).fetchone()
    filas = lambda sql: con.execute(sql).fetchall()

    M = "mart_extension_de_plazo"
    I = "main_intermediate.int_cambios_por_columna"

    poblaciones = {}
    for completa, fila in [
        (True, uno(f"""select sum(contratos_observados), sum(contratos_con_extension),
                 sum(dias_extendidos), sum(contratos_con_adicion),
                 sum(pesos_adicionados), sum(acortamientos), sum(reducciones)
                 from {M} where historia_completa""")),
        (False, uno(f"""select sum(contratos_observados), sum(contratos_con_extension),
                 sum(dias_extendidos), sum(contratos_con_adicion),
                 sum(pesos_adicionados), sum(acortamientos), sum(reducciones)
                 from {M} where not historia_completa""")),
    ]:
        poblaciones["medible" if completa else "amplia"] = dict(
            zip(("contratos", "con_extension", "dias", "con_adicion",
                 "pesos", "acortamientos", "reducciones"), (int(x or 0) for x in fila))
        )

    return {
        # `hoy()` y no `date.today()`: R2. El reloj del sistema puede estar en
        # UTC, y entre las 19:00 y la medianoche colombiana eso da un dia de mas.
        # Acá no es cosmético: de esta fecha sale el conteo de días que la fuente
        # lleva congelada, que es una cifra que la pagina publica.
        "generado": hoy().isoformat(),
        "observaciones": uno("select count(*) from main_staging.raw_observaciones")[0],
        "contratos": uno("select count(*) from fct_contratos")[0],
        "versiones": uno("select count(*) from fct_contratos_snapshot")[0],
        "cambios": uno(f"select count(*) from {I}")[0],
        "entidades": uno("select count(distinct codigo_entidad) from dim_entidad")[0],
        "raw_mb": sum(f.stat().st_size for f in RAW.rglob("*.jsonl.gz")) // (1024 * 1024),
        "poblaciones": poblaciones,
        # Con qué margen se ve cuánta historia. Es la censura por la izquierda,
        # y es la limitación que el tablero no puede esconder.
        "margenes": [
            {"dias": d, "contratos": uno(
                f"select count(*) from fct_contratos where dias_hasta_el_primer_snapshot <= {d}")[0]}
            for d in (0, 7, 30, 90, 365)
        ],
        "columnas_que_cambian": [
            {"columna": c, "contratos": n} for c, n in filas(
                f"""select columna, count(distinct id_contrato) from {I}
                    group by 1 order by 2 desc limit 8""")
        ],
        "tramos_de_extension": [
            {"tramo": t, "n": n} for t, n in filas(
                f"""select case
                      when delta_dias <= 30 then '1 a 30 días'
                      when delta_dias <= 90 then '31 a 90'
                      when delta_dias <= 180 then '91 a 180'
                      when delta_dias <= 365 then '181 a 365'
                      else 'más de un año' end,
                    count(*)
                    from {I} where columna = 'fecha_de_fin_del_contrato'
                      and delta_dias > 0
                    group by 1 order by min(delta_dias)""")
        ],
        "modalidades": [
            {"modalidad": m, "n": n} for m, n in filas(
                """select modalidad_de_contratacion, sum(observaciones)
                   from dim_modalidad group by 1 order by 2 desc limit 6""")
        ],
        "ranking": [
            {"entidad": e, "familia": f, "observados": o, "extensiones": x, "dias": d}
            for e, f, o, x, d in filas(
                f"""select nombre_entidad, familia_unspsc, contratos_observados,
                      contratos_con_extension, dias_extendidos
                    from {M}
                    where historia_completa and contratos_observados >= 20
                      and contratos_con_extension > 0
                    order by contratos_con_extension * 1.0 / contratos_observados desc
                    limit 8""")
        ],
        "sin_ciudad": uno(
            "select sum(case when sin_ciudad then observaciones else 0 end) from dim_geografia")[0],
        "cambios_materiales": uno(
            "select count(*) from fct_contratos_snapshot where version > 1")[0],
    }


# ---------------------------------------------------------------------------
# Presentación
# ---------------------------------------------------------------------------

def n(x: float, dec: int = 0) -> str:
    """Número con punto de miles y coma decimal, como se escribe en Colombia."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def e(t: object) -> str:
    return html.escape(str(t))


def tarjeta(valor: str, etiqueta: str, nota: str = "") -> str:
    pie = f'<p class="nota">{e(nota)}</p>' if nota else ""
    return (f'<div class="tarjeta"><p class="cifra">{e(valor)}</p>'
            f'<p class="etiqueta">{e(etiqueta)}</p>{pie}</div>')


def barras(datos: list[dict], clave: str, valor: str, *, destacar: int = 0,
           sufijo: str = "", detalle=None) -> str:
    """Barras horizontales con etiqueta directa en cada una.

    `destacar` cuántas de las primeras llevan el color de serie; el resto va en
    gris de contexto. La identidad nunca depende del color solo: cada barra
    lleva su nombre a la izquierda y su valor a la derecha.
    """
    if not datos:
        return '<p class="nota">Sin datos.</p>'
    tope = max(d[valor] for d in datos) or 1
    filas = []
    for i, d in enumerate(datos):
        ancho = max(d[valor] / tope * 100, 0.6)
        clase = "serie" if i < destacar else "contexto"
        det = e(detalle(d)) if detalle else ""
        filas.append(
            f'<div class="fila" data-detalle="{det}">'
            f'<span class="nombre">{e(d[clave])}</span>'
            f'<span class="pista"><span class="barra {clase}" style="width:{ancho:.1f}%"></span></span>'
            f'<span class="valor">{e(n(d[valor]))}{e(sufijo)}</span>'
            f"</div>"
        )
    tabla = "".join(
        f"<tr><td>{e(d[clave])}</td><td>{e(n(d[valor]))}{e(sufijo)}</td></tr>" for d in datos
    )
    return (f'<div class="barras">{"".join(filas)}</div>'
            f'<details class="tabla"><summary>Ver como tabla</summary>'
            f"<table><tbody>{tabla}</tbody></table></details>")


ESTADOS = {
    "regenero":     ("bien",   "se regeneró"),
    "no regenero":  ("mal",    "NO se regeneró"),
    "sin observar": ("neutro", "nadie miró"),
}


def tira_de_cadencia(dias: list[tuple[str, str]]) -> str:
    celdas = []
    for fecha, estado in dias:
        clase, texto = ESTADOS[estado]
        dia = fecha[-2:]
        celdas.append(
            f'<div class="dia {clase}" data-detalle="{e(fecha)}: {e(texto)}">'
            f'<span class="num">{e(dia)}</span></div>'
        )
    leyenda = "".join(
        f'<span class="clave"><span class="punto {c}"></span>{e(t)}</span>'
        for c, t in (("bien", "se regeneró"), ("mal", "no se regeneró"),
                     ("neutro", "sin observación"))
    )
    return f'<div class="tira">{"".join(celdas)}</div><div class="leyenda">{leyenda}</div>'


ESTILO = """
/* Tipografía. Newsreader para titulares: es una serif de texto pensada para
   lectura larga, con más carácter que una grotesca y sin el aire de folleto de
   una display. IBM Plex Sans para el cuerpo y la interfaz. IBM Plex Mono para
   cifras, fechas y etiquetas, porque el vocabulario de este tema es la marca de
   tiempo y el identificador de contrato. */
:root {
  color-scheme: light;
  --plano:      #f9f9f7;
  --superficie: #fcfcfb;
  --tinta:      #0b0b0b;
  --tinta-2:    #52514e;
  --tinta-3:    #898781;
  --linea:      #e1e0d9;
  --borde:      rgba(11,11,11,.10);
  --serie-1:    #2a78d6;
  --serie-2:    #eb6834;
  --contexto:   #c9c8bf;
  --bien:       #0ca30c;
  --mal:        #d03b3b;
  --neutro:     #d5d4cc;
  --chip:       rgba(208,59,59,.10);

  --titular: "Newsreader", Georgia, "Times New Roman", serif;
  --texto:   "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --dato:    "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --plano: #0d0d0d; --superficie: #1a1a19; --tinta: #ffffff; --tinta-2: #c3c2b7;
    --tinta-3: #898781; --linea: #2c2c2a; --borde: rgba(255,255,255,.10);
    --serie-1: #3987e5; --serie-2: #d95926; --contexto: #46453f; --neutro: #33322e;
    --chip: rgba(208,59,59,.18);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --plano: #0d0d0d; --superficie: #1a1a19; --tinta: #ffffff; --tinta-2: #c3c2b7;
  --tinta-3: #898781; --linea: #2c2c2a; --borde: rgba(255,255,255,.10);
  --serie-1: #3987e5; --serie-2: #d95926; --contexto: #46453f; --neutro: #33322e;
  --chip: rgba(208,59,59,.18);
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--plano); color: var(--tinta);
  font: 400 15.5px/1.65 var(--texto);
  -webkit-font-smoothing: antialiased;
}
.hoja { max-width: 860px; margin: 0 auto; padding: 0 24px 96px; }

/* La banda de estado. Va arriba de todo porque en un tablero lo primero es en
   qué estado está la fuente, no cuántas filas hay. */
.banda {
  display: flex; flex-wrap: wrap; gap: 10px 28px; align-items: baseline;
  border-bottom: 1px solid var(--linea); padding: 14px 0 13px; margin-bottom: 40px;
  font-family: var(--dato); font-size: 12px; letter-spacing: .01em;
  color: var(--tinta-3);
}
.banda b { color: var(--tinta); font-weight: 500; }
.chip {
  background: var(--chip); color: var(--mal); border-radius: 4px;
  padding: 2px 7px; font-weight: 600; letter-spacing: .02em;
}

h1 { font: 400 clamp(30px, 5.2vw, 44px)/1.12 var(--titular); margin: 0 0 16px;
     letter-spacing: -.015em; text-wrap: balance; max-width: 18ch; }
h2 { font: 400 24px/1.2 var(--titular); margin: 0 0 8px; letter-spacing: -.01em;
     text-wrap: balance; }
h3 { font-family: var(--texto); font-size: 12px; font-weight: 600; margin: 28px 0 10px;
     color: var(--tinta-3); text-transform: uppercase; letter-spacing: .07em; }
p { margin: 0 0 14px; }
.entrada { color: var(--tinta-2); font-size: 17px; line-height: 1.6; max-width: 62ch; }
.nota { color: var(--tinta-3); font-size: 13px; line-height: 1.55; margin: 10px 0 0;
        max-width: 68ch; }
.pie { color: var(--tinta-3); font-size: 12.5px; border-top: 1px solid var(--linea);
       margin-top: 56px; padding-top: 22px; max-width: 68ch; }
code { font-family: var(--dato); font-size: .92em; }

section { background: var(--superficie); border: 1px solid var(--borde);
          border-radius: 3px; padding: 28px; margin: 20px 0; }
section > p:last-child, section > div:last-child { margin-bottom: 0; }
.encabezado { border: 0; background: none; padding: 0; margin: 0 0 36px; }

.rejilla { display: grid; gap: 1px; background: var(--borde);
           border: 1px solid var(--borde); border-radius: 3px;
           grid-template-columns: repeat(auto-fit, minmax(158px, 1fr)); }
.tarjeta { background: var(--superficie); padding: 16px 18px; }
.cifra { font-family: var(--dato); font-size: 25px; font-weight: 500; margin: 0;
         letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.etiqueta { font-size: 12.5px; color: var(--tinta-2); margin: 3px 0 0; line-height: 1.4; }
.tarjeta .nota { font-size: 12px; margin-top: 8px; }

.barras { margin: 6px 0 0; }
.fila { display: grid; grid-template-columns: minmax(120px, 16em) 1fr 5.5em;
        gap: 14px; align-items: center; padding: 3px 0; position: relative; }
.nombre { font-size: 12.5px; color: var(--tinta-2); overflow: hidden;
          text-overflow: ellipsis; white-space: nowrap; }
.pista { height: 14px; display: block; }
.barra { display: block; height: 14px; border-radius: 0 4px 4px 0; }
.barra.serie { background: var(--serie-1); }
.barra.contexto { background: var(--contexto); }
.valor { font-family: var(--dato); font-size: 12.5px; color: var(--tinta);
         text-align: right; font-variant-numeric: tabular-nums; }

.fila[data-detalle]:hover::after, .dia[data-detalle]:hover::after {
  content: attr(data-detalle); position: absolute; left: 0; top: 100%;
  transform: translateY(3px); z-index: 5;
  background: var(--tinta); color: var(--superficie);
  font-family: var(--texto); font-size: 12px; line-height: 1.45;
  padding: 7px 10px; border-radius: 4px;
  white-space: normal; max-width: 34em; pointer-events: none;
  box-shadow: 0 3px 14px rgba(0,0,0,.20);
}

.tira { display: flex; gap: 3px; flex-wrap: wrap; margin: 12px 0 0; }
.dia { position: relative; width: 46px; height: 46px; border-radius: 3px;
       display: flex; align-items: center; justify-content: center; }
.dia .num { font-family: var(--dato); font-size: 12px; font-weight: 500;
            font-variant-numeric: tabular-nums; }
.dia.bien   { background: var(--bien);   color: #fff; }
.dia.mal    { background: var(--mal);    color: #fff; }
.dia.neutro { background: var(--neutro); color: var(--tinta-3); }
.leyenda { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 12px;
           font-size: 12px; color: var(--tinta-2); }
.clave { display: flex; align-items: center; gap: 7px; }
.punto { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.punto.bien { background: var(--bien); } .punto.mal { background: var(--mal); }
.punto.neutro { background: var(--neutro); }

.dos { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(272px, 1fr)); }
.caja { border: 1px solid var(--borde); border-radius: 3px; padding: 18px; }
.caja h3 { margin-top: 0; }
.caja.medible { border-color: var(--serie-1); border-width: 1px 1px 1px 3px; }
.par { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0;
       border-bottom: 1px solid var(--linea); font-size: 13.5px; }
.par:last-of-type { border-bottom: 0; }
.par b { font-family: var(--dato); font-variant-numeric: tabular-nums; font-weight: 500; }

.tabla { margin-top: 14px; }
.tabla summary { font-size: 12px; color: var(--tinta-3); cursor: pointer; }
.tabla summary:focus-visible { outline: 2px solid var(--serie-1); outline-offset: 2px; }
.tabla > table { border-collapse: collapse; margin-top: 10px; font-size: 13px; width: 100%; }
.tabla td { border-bottom: 1px solid var(--linea); padding: 5px 8px; }
.tabla td:last-child { text-align: right; font-family: var(--dato);
                       font-variant-numeric: tabular-nums; }

.aviso { border-left: 2px solid var(--serie-2); padding-left: 16px; color: var(--tinta-2);
         font-size: 14.5px; }
.envoltura { overflow-x: auto; }
table.ranking { border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 10px; }
table.ranking th { text-align: left; font-weight: 600; color: var(--tinta-3);
                   font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
                   padding: 5px 8px; border-bottom: 1px solid var(--linea); white-space: nowrap; }
table.ranking td { padding: 6px 8px; border-bottom: 1px solid var(--linea); }
table.ranking td.num { text-align: right; font-family: var(--dato);
                       font-variant-numeric: tabular-nums; white-space: nowrap; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
@media (max-width: 620px) {
  .fila { grid-template-columns: minmax(88px, 9em) 1fr 4.5em; gap: 10px; }
  .hoja { padding: 0 16px 64px; }
  section { padding: 20px; }
}
"""


def pagina(d: dict) -> str:
    med, amp = d["poblaciones"]["medible"], d["poblaciones"]["amplia"]
    total_ext = med["con_extension"] + amp["con_extension"]
    total_adic = med["con_adicion"] + amp["con_adicion"]
    total_dias = med["dias"] + amp["dias"]
    total_pesos = (med["pesos"] + amp["pesos"]) / 1e9
    acort = med["acortamientos"] + amp["acortamientos"]
    reduc = med["reducciones"] + amp["reducciones"]
    congelada = (date.fromisoformat(d["generado"]) - date(2026, 8, 25)).days
    pct_ciudad = d["sin_ciudad"] / d["observaciones"] * 100
    pct_material = d["cambios_materiales"] / 52954 * 100

    ranking = "".join(
        f'<tr><td>{e(r["entidad"][:52])}</td><td class="num">{e(n(r["observados"]))}</td>'
        f'<td class="num">{e(n(r["extensiones"]))}</td>'
        f'<td class="num">{e(n(r["extensiones"] / r["observados"] * 100, 1))}%</td>'
        f'<td class="num">{e(n(r["dias"]))}</td></tr>'
        for r in d["ranking"]
    )
    margenes = "".join(
        f'<div class="par"><span>Dentro de {e(n(x["dias"]))} días de la firma</span>'
        f'<b>{e(n(x["contratos"]))} &nbsp;({e(n(x["contratos"] / d["contratos"] * 100, 2))}%)</b></div>'
        for x in d["margenes"]
    )

    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>La historia que SECOP borra</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap">
<style>{ESTILO}</style>
</head><body>
<div class="hoja">

<div class="banda">
  <span>corte vivo de la fuente <b>{e(CORTE_VIVO[:10])}</b></span>
  <span>sin regenerarse <span class="chip">{e(congelada)} días</span></span>
  <span>contratos versionados <b>{e(n(d["contratos"]))}</b></span>
  <span>tablero generado <b>{e(d["generado"])}</b></span>
</div>

<header class="encabezado">
  <h1>La historia que SECOP borra cada vez que publica</h1>
  <p class="entrada">
    Colombia publica todos sus contratos públicos como datos abiertos. Cada vez que
    regenera el conjunto lo reemplaza entero, así que nadie puede saber cuánto valía
    un contrato antes de una adición, ni cuántas veces le corrieron el plazo. Este
    proyecto guarda una foto de cada corte y reconstruye esa serie.
  </p>
</header>

<section>
  <h2>Lo que hay guardado</h2>
  <div class="rejilla">
    {tarjeta(n(d["observaciones"]), "observaciones en la capa cruda")}
    {tarjeta(n(d["contratos"]), "contratos distintos")}
    {tarjeta(n(d["versiones"]), "versiones en la serie")}
    {tarjeta(n(d["cambios"]), "cambios anotados columna por columna")}
    {tarjeta(n(d["entidades"]), "entidades contratantes")}
    {tarjeta(n(d["raw_mb"]) + " MB", "en disco, comprimido")}
  </div>
  <p class="nota">Frente a guardar la foto entera sin comprimir en cada corte, la
    reducción es de al menos 428 veces: 8,9 los pone la compresión y 48,2 la
    deduplicación por huella antes de escribir.</p>
</section>

<section>
  <h2>La fuente declara frecuencia diaria y no la cumple</h2>
  <p class="entrada">La ficha oficial dice que el conjunto se actualiza a diario. Se
    comprobó con una petición de dos segundos, repetida todos los días, y es falso.</p>
  {tira_de_cadencia(CADENCIA)}
  <p class="nota">Cada celda es un día de agosto de 2026. Tres regeneraciones y cinco
    días sin regenerar, entre los días en que alguien miró.</p>
  <p class="aviso">Al generar este tablero la fuente lleva <b>{e(congelada)} días</b>
    sin regenerarse. No es una caída de la plataforma: un conjunto hermano que escribe
    en continuo registró escrituras esa misma mañana. Lo que está detenido es el
    proceso que rehace la vista publicada.</p>
  <p class="nota">De ahí sale una decisión de ingeniería: el pipeline no se puede
    disparar por reloj, porque ningún horario acierta contra un evento que a veces no
    ocurre. Se dispara por el estado de la fuente.</p>
</section>

<section>
  <h2>El evento más frecuente es el que la fuente no registra</h2>
  <p class="entrada">De las 28 columnas que cuentan como cambio real, estas son las que
    más se movieron. Las cuatro primeras son ejecución financiera: pagos y facturación.
    Ninguna fecha las acompaña, así que la única manera de detectarlas es volver a
    bajar el contrato entero y compararlo con la observación anterior.</p>
  {barras(d["columnas_que_cambian"], "columna", "contratos", destacar=4,
          detalle=lambda x: f'{x["columna"]}: {n(x["contratos"])} contratos')}
  <p class="nota">Esas cuatro son la razón por la que el pipeline barre 2,8 millones de
    contratos en cada corte en lugar de pedir solo lo que cambió.</p>
</section>

<section>
  <h2>Cuánto se extiende el plazo, y cuánto cuesta</h2>
  <p class="entrada">Son las dos preguntas que no se pueden responder con datos
    públicos, porque exigen comparar el contrato de hoy contra el de antes.</p>
  <div class="rejilla">
    {tarjeta(n(total_ext), "contratos con el plazo extendido")}
    {tarjeta(n(total_dias), "días de extensión en total")}
    {tarjeta(n(total_adic), "contratos con adición de valor")}
    {tarjeta(n(total_pesos, 1), "mil millones de pesos adicionados")}
  </div>
  <p class="aviso">El plazo también se acorta y el valor también baja:
    <b>{e(n(acort))}</b> contratos redujeron su plazo y <b>{e(n(reduc))}</b> bajaron su
    valor. Los cuatro conteos van separados a propósito. Sumarlos en neto y llamar al
    resultado extensiones esconde una población detrás del nombre de la otra, y fue un
    defecto real de la primera versión de este modelo.</p>
  <h3>Cuánto se extienden</h3>
  {barras(d["tramos_de_extension"], "tramo", "n", destacar=5,
          detalle=lambda x: f'{x["n"]} contratos se extendieron {x["tramo"]}')}
</section>

<section>
  <h2>Lo que este tablero todavía no puede decir</h2>
  <p class="entrada">Un análisis de sobrecosto solo vale para los contratos que
    observamos desde cerca de su firma. De los demás vimos un pedazo: sus adiciones
    anteriores ya venían incorporadas en la primera foto y son invisibles. Mezclar las
    dos poblaciones subestima el resultado sin que nada falle.</p>

  <div class="dos">
    <div class="caja medible">
      <h3>Población medible</h3>
      <div class="par"><span>Contratos</span><b>{e(n(med["contratos"]))}</b></div>
      <div class="par"><span>Con el plazo extendido</span><b>{e(n(med["con_extension"]))}</b></div>
      <div class="par"><span>Días de extensión</span><b>{e(n(med["dias"]))}</b></div>
      <div class="par"><span>Con adición de valor</span><b>{e(n(med["con_adicion"]))}</b></div>
      <p class="nota">Observados dentro de los {MARGEN_DIAS} días de su firma. Tienen
        historia completa, así que el número es correcto.</p>
    </div>
    <div class="caja">
      <h3>Cota inferior</h3>
      <div class="par"><span>Contratos</span><b>{e(n(amp["contratos"]))}</b></div>
      <div class="par"><span>Con el plazo extendido</span><b>{e(n(amp["con_extension"]))}</b></div>
      <div class="par"><span>Días de extensión</span><b>{e(n(amp["dias"]))}</b></div>
      <div class="par"><span>Con adición de valor</span><b>{e(n(amp["con_adicion"]))}</b></div>
      <p class="nota">Historia truncada por la izquierda. El número es más grande y es
        un piso, no una medición.</p>
    </div>
  </div>

  <h3>Cuánta historia alcanzamos a ver</h3>
  {margenes}
  <p class="nota">El margen no puede ser cero: la fuente publica con un día de rezago,
    así que ningún contrato se observa el mismo día en que se firma. La mediana del
    hueco entre la firma y la primera observación es de 657 días.</p>
  <p class="nota">Este número <b>crece solo</b> con cada corte ingerido. No es un
    defecto del modelo: es que el pipeline lleva una semana de vida contra una fuente
    que publica desde 2015.</p>

  <h3>Quién extiende más, dentro de la población medible</h3>
  <div class="envoltura">
  <table class="ranking"><thead><tr>
    <th>Entidad</th><th class="num">Contratos</th><th class="num">Extendidos</th>
    <th class="num">Tasa</th><th class="num">Días</th>
  </tr></thead><tbody>{ranking}</tbody></table>
  </div>
  <p class="nota">Solo entidades con veinte contratos o más, para que la tasa signifique
    algo. Aun así son pocos casos: la palabra sistemáticamente todavía no se sostiene, y
    por eso el ranking va con su denominador a la vista.</p>
</section>

<section>
  <h2>Otras cosas que aparecieron en el camino</h2>
  <h3>El 74% de la contratación pública es directa</h3>
  {barras(d["modalidades"], "modalidad", "n", destacar=2,
          detalle=lambda x: f'{x["modalidad"]}: {n(x["n"])} observaciones')}
  <p class="nota">Sumando contratación directa, directa con ofertas y régimen especial,
    la contratación sin licitación abierta supera el 90%.</p>
  <div class="rejilla" style="margin-top:26px">
    {tarjeta("7", "contratos por encima del presupuesto nacional",
             "El mayor lo supera 23 veces y es de un instituto municipal de deportes. Los siete tienen forma válida: el sistema de tipos no los atrapa.")}
    {tarjeta(n(pct_ciudad, 0) + "%", "de los contratos no tiene ciudad",
             "El dato no está escondido en otra columna: la fuente no lo publica. Un análisis por municipio deja fuera esa quinta parte.")}
    {tarjeta(n(100 - pct_material, 1) + "%", "de los cambios no cambian el contrato",
             "Cuatro de cada diez veces que la fuente publica un contrato como modificado, al contrato no le pasó nada.")}
    {tarjeta("26,5 M", "filas con la fecha truncada",
             "En un conjunto oficial hermano, ni el día ni el mes superan nunca el 9. La columna está tipada como fecha y parsea sin error.")}
  </div>
</section>

<p class="pie">
  Datos públicos de la Agencia Nacional de Contratación Pública, Colombia Compra
  Eficiente, consultados desde datos.gov.co bajo la Ley 1712 de 2014. Este tablero lo
  genera <code>scripts/generar_tablero.py</code> a partir del modelo, así que se rehace
  después de cada ingesta y no se edita a mano.
</p>

</div></body></html>
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument(
        "--sin-envoltura", action="store_true",
        help="Emite solo el contenido, sin las etiquetas html/head/body. Sirve "
             "para publicar la pagina dentro de un contenedor que ya las aporta.")
    p.add_argument("--base", type=Path, default=DUCKDB)
    args = p.parse_args()

    if not args.base.is_file():
        print(f"No existe {args.base}. Corre `dbt build` primero.", file=sys.stderr)
        return 1

    con = duckdb.connect(str(args.base), read_only=True)
    # El mismo techo que usa dbt (R3): el tablero no puede pedir mas memoria que
    # el pipeline que lo alimenta.
    con.execute("set memory_limit='2GB'")
    con.execute("set threads=1")
    datos = consultar(con)
    con.close()

    html_completo = pagina(datos)
    if args.sin_envoltura:
        # Se conservan el titulo, los enlaces a las fuentes y el estilo: lo unico
        # que se quita es el esqueleto del documento, que el contenedor aporta.
        html_completo = (
            html_completo[html_completo.index("<title>"):html_completo.rindex("</body>")]
            .replace("</head><body>", "")
        )
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(html_completo, encoding="utf-8")
    kb = args.salida.stat().st_size // 1024
    print(f"OK {args.salida}  ({kb} KB)")
    print(f"   {n(datos['contratos'])} contratos / {n(datos['versiones'])} versiones "
          f"/ {n(datos['cambios'])} cambios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
