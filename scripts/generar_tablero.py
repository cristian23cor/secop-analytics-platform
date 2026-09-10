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
import csv
import html
import json
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
# La cadencia y el corte vivo salen del registro, no de una lista escrita aca.
# Es el mismo criterio que con las columnas: un dato que existe en un archivo no
# se copia a otro, porque el dia que se separen nadie se entera.
REGISTRO = BASE / "exploration" / "cadencia.csv"

# El registro dice si/no/vacio; la tira necesita el nombre de su estado.
_ESTADO = {"si": "regenero", "no": "no regenero", "": "sin observar"}


def leer_cadencia() -> tuple[list[tuple[str, str]], str]:
    """Devuelve los dias con su estado, y el ultimo corte visto.

    El corte vivo es el de la ultima linea que lo trae: los dias deducidos y los
    que nadie miro lo dejan vacio, y eso no significa que la fuente no tuviera
    corte sino que ese dia no se consulto.
    """
    filas = [
        f for f in csv.DictReader(
            l for l in REGISTRO.read_text(encoding="utf-8").splitlines()
            if not l.startswith("#")
        )
    ]
    dias = [(f["fecha"], _ESTADO[f["regenero"]]) for f in filas]
    corte = next(f["corte_vivo"] for f in reversed(filas) if f["corte_vivo"])
    return dias, corte


CADENCIA, CORTE_VIVO = leer_cadencia()

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
    """Numero con punto de miles y coma decimal, como se escribe en Colombia."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def e(t: object) -> str:
    return html.escape(str(t))


def tarjeta(valor: str, etiqueta: str, nota: str = "") -> str:
    """Una cifra con su etiqueta. Va en una tabla, no en una tarjeta."""
    pie = f'<br><span class="nota">{e(nota)}</span>' if nota else ""
    return (f'<tr><td class="num"><b>{e(valor)}</b></td>'
            f"<td>{e(etiqueta)}{pie}</td></tr>")


def cifras(filas: list[str]) -> str:
    return f'<table class="datos"><tbody>{"".join(filas)}</tbody></table>'


def barras(datos: list[dict], clave: str, valor: str, *, destacar: int = 0,
           sufijo: str = "", detalle=None) -> str:
    """Barras horizontales: una tabla con un div de ancho variable en el medio.

    Cada barra lleva su nombre a la izquierda y su valor a la derecha, asi que
    el color nunca es lo unico que distingue una de otra.
    """
    if not datos:
        return '<p class="nota">Sin datos.</p>'
    tope = max(d[valor] for d in datos) or 1
    filas = "".join(
        f'<tr><td class="etiqueta">{e(d[clave])}</td>'
        f'<td><div class="barra{"" if i < destacar else " gris"}" '
        f'style="width:{max(d[valor] / tope * 100, 1):.0f}%"></div></td>'
        f'<td class="cifra">{e(n(d[valor]))}{e(sufijo)}</td></tr>'
        for i, d in enumerate(datos)
    )
    tabla = "".join(
        f'<tr><td>{e(d[clave])}</td><td class="num">{e(n(d[valor]))}{e(sufijo)}</td></tr>'
        for d in datos
    )
    return (f'<table class="barras"><tbody>{filas}</tbody></table>'
            f"<details><summary>Ver como tabla</summary>"
            f"<table><tbody>{tabla}</tbody></table></details>")


ESTADOS = {
    "regenero":     ("bien",   "se regeneró"),
    "no regenero":  ("mal",    "NO se regeneró"),
    "sin observar": ("neutro", "nadie miró"),
}


def tira_de_cadencia(dias: list[tuple[str, str]]) -> str:
    celdas = "".join(
        f'<span class="dia {ESTADOS[estado][0]}" title="{e(fecha)}: '
        f'{e(ESTADOS[estado][1])}">{e(fecha[-2:])}</span>'
        for fecha, estado in dias
    )
    return (f"<div>{celdas}</div>"
            '<p class="leyenda">verde: se regeneró &nbsp; rojo: no se regeneró'
            " &nbsp; gris: nadie miró</p>")


ESTILO = """
body {
  font-family: Arial, Helvetica, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  color: #222;
  background: #fff;
  margin: 0;
  padding: 20px;
}
.hoja { max-width: 900px; margin: 0 auto; }

h1 { font-size: 26px; margin: 0 0 10px; }
h2 { font-size: 19px; margin: 30px 0 8px; border-bottom: 1px solid #ddd;
     padding-bottom: 4px; }
h3 { font-size: 15px; margin: 20px 0 6px; }
p  { margin: 0 0 12px; }
.intro { color: #444; }
.nota  { color: #666; font-size: 13px; }
.aviso { background: #fff8e6; border: 1px solid #e6d9b0; padding: 10px 12px; }
code   { background: #f2f2f2; padding: 1px 4px; font-size: 13px; }
a      { color: #1a5fb4; }

table { border-collapse: collapse; margin: 10px 0; }
th, td { border: 1px solid #ddd; padding: 5px 9px; text-align: left;
         vertical-align: top; }
th { background: #f2f2f2; font-size: 13px; }
td.num, th.num { text-align: right; white-space: nowrap; }
table.datos { width: 100%; }

/* Las barras son una tabla con un div de ancho variable en la celda del medio.
   No es elegante, pero se entiende y no necesita ninguna libreria. */
table.barras { width: 100%; }
table.barras td { border: none; padding: 2px 6px 2px 0; }
table.barras td.etiqueta { width: 250px; font-size: 13px; color: #444; }
table.barras td.cifra { width: 80px; text-align: right; font-size: 13px; }
.barra { background: #1a5fb4; height: 14px; }
.barra.gris { background: #bbb; }

.dia { display: inline-block; width: 42px; height: 34px; line-height: 34px;
       text-align: center; font-size: 12px; margin: 0 2px 2px 0; color: #fff; }
.dia.bien   { background: #2e7d32; }
.dia.mal    { background: #c62828; }
.dia.neutro { background: #ddd; color: #666; }
.leyenda { font-size: 13px; color: #444; margin-top: 6px; }

.caja { border: 1px solid #ddd; padding: 12px 14px; margin-bottom: 12px; }
.caja h3 { margin-top: 0; }

details { margin: 8px 0; }
summary { font-size: 13px; color: #666; cursor: pointer; }

.pie { border-top: 1px solid #ddd; margin-top: 30px; padding-top: 12px;
       color: #666; font-size: 13px; }
"""


def pagina(d: dict) -> str:
    med, amp = d["poblaciones"]["medible"], d["poblaciones"]["amplia"]
    total_ext = med["con_extension"] + amp["con_extension"]
    total_adic = med["con_adicion"] + amp["con_adicion"]
    total_dias = med["dias"] + amp["dias"]
    total_pesos = (med["pesos"] + amp["pesos"]) / 1e9
    acort = med["acortamientos"] + amp["acortamientos"]
    reduc = med["reducciones"] + amp["reducciones"]
    # Contra el corte vivo y no contra una fecha escrita aparte: el dia que la
    # fuente regenere, `CORTE_VIVO` cambia y esta cuenta lo sigue sola.
    regenero = sum(1 for _, e_ in CADENCIA if e_ == "regenero")
    no_regenero = sum(1 for _, e_ in CADENCIA if e_ == "no regenero")
    congelada = (date.fromisoformat(d["generado"])
                 - date.fromisoformat(CORTE_VIVO[:10])).days
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
        f'<tr><td>Dentro de {e(n(x["dias"]))} días de la firma</td>'
        f'<td class="num">{e(n(x["contratos"]))}</td>'
        f'<td class="num">{e(n(x["contratos"] / d["contratos"] * 100, 2))}%</td></tr>'
        for x in d["margenes"]
    )

    def par(etiqueta: str, valor: int) -> str:
        return f'<tr><td>{e(etiqueta)}</td><td class="num">{e(n(valor))}</td></tr>'

    return f"""<!doctype html>
<html lang="es"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>La historia que SECOP borra</title>
<style>{ESTILO}</style>
</head><body>
<div class="hoja">

<h1>La historia que SECOP borra cada vez que publica</h1>

<p class="intro">
  Colombia publica todos sus contratos públicos como datos abiertos. Cada vez que
  regenera el conjunto lo reemplaza entero, así que nadie puede saber cuánto valía
  un contrato antes de una adición, ni cuántas veces le corrieron el plazo. Este
  proyecto guarda una foto de cada corte y reconstruye esa serie.
</p>

<p class="nota">
  Corte vivo de la fuente: {e(CORTE_VIVO[:10])} &nbsp;|&nbsp;
  lleva {e(congelada)} días sin regenerarse &nbsp;|&nbsp;
  tablero generado el {e(d["generado"])}
</p>

<h2>Lo que hay guardado</h2>
{cifras([
    tarjeta(n(d["observaciones"]), "observaciones en la capa cruda"),
    tarjeta(n(d["contratos"]), "contratos distintos"),
    tarjeta(n(d["versiones"]), "versiones en la serie"),
    tarjeta(n(d["cambios"]), "cambios anotados columna por columna"),
    tarjeta(n(d["entidades"]), "entidades contratantes"),
    tarjeta(n(d["raw_mb"]) + " MB", "en disco, comprimido"),
])}
<p class="nota">Frente a guardar la foto entera sin comprimir en cada corte, la
  reducción es de al menos 428 veces: 8,9 los pone la compresión y 48,2 la
  deduplicación por huella antes de escribir.</p>

<h2>La fuente declara frecuencia diaria y no la cumple</h2>
<p class="intro">La ficha oficial dice que el conjunto se actualiza a diario. Se
  comprobó con una petición de dos segundos, repetida todos los días, y es falso.</p>
{tira_de_cadencia(CADENCIA)}
<p class="nota">Cada celda es un día observado. {e(n(regenero))} regeneraciones y
  {e(n(no_regenero))} días sin regenerar, sobre {e(n(regenero + no_regenero))} días
  en que alguien miró; los grises nadie los comprobó.</p>
<p class="aviso">Al generar este tablero la fuente lleva <b>{e(congelada)} días</b>
  sin regenerarse. No es una caída de la plataforma: un conjunto hermano que escribe
  en continuo registró escrituras esa misma mañana. Lo que está detenido es el
  proceso que rehace la vista publicada.</p>
<p class="nota">De ahí sale una decisión de ingeniería: el pipeline no se puede
  disparar por reloj, porque ningún horario acierta contra un evento que a veces no
  ocurre. Se dispara por el estado de la fuente.</p>

<h2>El evento más frecuente es el que la fuente no registra</h2>
<p class="intro">De las 28 columnas que cuentan como cambio real, estas son las que
  más se movieron. Las cuatro primeras son ejecución financiera: pagos y facturación.
  Ninguna fecha las acompaña, así que la única manera de detectarlas es volver a
  bajar el contrato entero y compararlo con la observación anterior.</p>
{barras(d["columnas_que_cambian"], "columna", "contratos", destacar=4)}
<p class="nota">Esas cuatro son la razón por la que el pipeline barre 2,8 millones de
  contratos en cada corte en lugar de pedir solo lo que cambió.</p>

<h2>Cuánto se extiende el plazo, y cuánto cuesta</h2>
<p class="intro">Son las dos preguntas que no se pueden responder con datos
  públicos, porque exigen comparar el contrato de hoy contra el de antes.</p>
{cifras([
    tarjeta(n(total_ext), "contratos con el plazo extendido"),
    tarjeta(n(total_dias), "días de extensión en total"),
    tarjeta(n(total_adic), "contratos con adición de valor"),
    tarjeta(n(total_pesos, 1), "mil millones de pesos adicionados"),
])}
<p class="aviso">El plazo también se acorta y el valor también baja:
  <b>{e(n(acort))}</b> contratos redujeron su plazo y <b>{e(n(reduc))}</b> bajaron su
  valor. Los cuatro conteos van separados a propósito. Sumarlos en neto y llamar al
  resultado extensiones esconde una población detrás del nombre de la otra, y fue un
  defecto real de la primera versión de este modelo.</p>

<h3>Cuánto se extienden</h3>
{barras(d["tramos_de_extension"], "tramo", "n", destacar=5)}

<h2>Lo que este tablero todavía no puede decir</h2>
<p class="intro">Un análisis de sobrecosto solo vale para los contratos que
  observamos desde cerca de su firma. De los demás vimos un pedazo: sus adiciones
  anteriores ya venían incorporadas en la primera foto y son invisibles. Mezclar las
  dos poblaciones subestima el resultado sin que nada falle.</p>

<div class="caja">
  <h3>Población medible</h3>
  <table>
    <tbody>
      {par("Contratos", med["contratos"])}
      {par("Con el plazo extendido", med["con_extension"])}
      {par("Días de extensión", med["dias"])}
      {par("Con adición de valor", med["con_adicion"])}
    </tbody>
  </table>
  <p class="nota">Observados dentro de los {MARGEN_DIAS} días de su firma. Tienen
    historia completa, así que el número es correcto.</p>
</div>

<div class="caja">
  <h3>Cota inferior</h3>
  <table>
    <tbody>
      {par("Contratos", amp["contratos"])}
      {par("Con el plazo extendido", amp["con_extension"])}
      {par("Días de extensión", amp["dias"])}
      {par("Con adición de valor", amp["con_adicion"])}
    </tbody>
  </table>
  <p class="nota">Historia truncada por la izquierda. El número es más grande y es
    un piso, no una medición.</p>
</div>

<h3>Cuánta historia alcanzamos a ver</h3>
<table>
  <thead><tr><th>Margen</th><th class="num">Contratos</th><th class="num">%</th></tr></thead>
  <tbody>{margenes}</tbody>
</table>
<p class="nota">El margen no puede ser cero: la fuente publica con un día de rezago,
  así que ningún contrato se observa el mismo día en que se firma. La mediana del
  hueco entre la firma y la primera observación es de 657 días.</p>
<p class="nota">Este número <b>crece solo</b> con cada corte ingerido. No es un
  defecto del modelo: es que el pipeline lleva una semana de vida contra una fuente
  que publica desde 2015.</p>

<h3>Quién extiende más, dentro de la población medible</h3>
<table>
  <thead><tr>
    <th>Entidad</th><th class="num">Contratos</th><th class="num">Extendidos</th>
    <th class="num">Tasa</th><th class="num">Días</th>
  </tr></thead>
  <tbody>{ranking}</tbody>
</table>
<p class="nota">Solo entidades con veinte contratos o más, para que la tasa signifique
  algo. Aun así son pocos casos: la palabra sistemáticamente todavía no se sostiene, y
  por eso el ranking va con su denominador a la vista.</p>

<h2>Otras cosas que aparecieron en el camino</h2>
<h3>El 74% de la contratación pública es directa</h3>
{barras(d["modalidades"], "modalidad", "n", destacar=2)}
<p class="nota">Sumando contratación directa, directa con ofertas y régimen especial,
  la contratación sin licitación abierta supera el 90%.</p>

{cifras([
    tarjeta("7", "contratos por encima del presupuesto nacional",
            "El mayor lo supera 23 veces y es de un instituto municipal de deportes. Los siete tienen forma válida: el sistema de tipos no los atrapa."),
    tarjeta(n(pct_ciudad, 0) + "%", "de los contratos no tiene ciudad",
            "El dato no está escondido en otra columna: la fuente no lo publica."),
    tarjeta(n(100 - pct_material, 1) + "%", "de los cambios no cambian el contrato",
            "Cuatro de cada diez veces que la fuente publica un contrato como modificado, al contrato no le pasó nada."),
    tarjeta("26,5 M", "filas con la fecha truncada",
            "En un conjunto oficial hermano, ni el día ni el mes superan nunca el 9. La columna está tipada como fecha y parsea sin error."),
])}

<p class="pie">
  Datos públicos de la Agencia Nacional de Contratación Pública, Colombia Compra
  Eficiente, consultados desde datos.gov.co bajo la Ley 1712 de 2014. Este tablero lo
  genera <code>scripts/generar_tablero.py</code> a partir del modelo, así que se rehace
  después de cada ingesta y no se edita a mano.
</p>

</div></body></html>
"""


def particiones_con_datos(raiz: Path) -> set[str]:
    """Las particiones de raw que el modelo TIENE que contener.

    Una particion cuenta solo si cumple **las dos** condiciones: estar completa y
    haber escrito algo.

    La segunda no es un detalle. La corrida del 28/08/2026 corrio contra una
    fuente congelada, descarto el 100% por bytes identicos y escribio **cero
    filas**: la particion tiene `_COMPLETO` y su manifiesto dice
    `lineas_totales: 0`, pero no tiene un solo `.jsonl.gz`. Esta legitimamente
    ausente del modelo, y no hay nada que reconstruir.

    Sin esa condicion, el guardarrail marcaria esa particion en cada corrida,
    para siempre, sobre un modelo sano. Y una regla que marca de mas se termina
    desactivando entera.
    """
    encontradas: set[str] = set()
    for completo in raiz.rglob("_COMPLETO"):
        directorio = completo.parent
        if not any(directorio.glob("*.jsonl.gz")):
            continue
        # `flujo=x/fecha_extraccion=y/particion=z` -> `x/y/z`, la misma clave
        # que arma `clave_de_particion()` para el filtro incremental de dbt.
        encontradas.add(
            "/".join(p.split("=", 1)[-1]
                     for p in directorio.relative_to(raiz).parts)
        )
    return encontradas


def corte_mas_reciente_ingerido(raiz: Path) -> str | None:
    """El corte mas nuevo que raw ya conoce, leido de los manifiestos.

    Solo el flujo 3 (`refresco_de_vivos`) pregunta por el corte de la fuente
    (D10, D11): los flujos 1 y 2 preguntan por ventanas de fecha de negocio y sus
    manifiestos no tienen `corte_al_iniciar`/`corte_al_terminar`.

    Cuenta toda particion **completa**, tenga o no filas escritas. La del
    28/08/2026 escribio cero filas y aun asi confirmo, con su propio manifiesto,
    que el corte vivo en ese momento era el del 25. Esa confirmacion vale igual
    que si hubiera escrito algo: es la razon de ser de D10.

    Los cortes son cadenas ISO 8601 con milisegundos y sufijo `Z`
    (`2026-09-09T09:55:38.989Z`), de ancho fijo, asi que el orden lexicografico
    coincide con el cronologico y `max()` sobre las cadenas alcanza.
    """
    cortes: list[str] = []
    for completo in raiz.glob("flujo=refresco_de_vivos/*/*/_COMPLETO"):
        manifiesto = completo.parent / "_manifiesto.json"
        if not manifiesto.is_file():
            continue
        m = json.loads(manifiesto.read_text(encoding="utf-8"))
        corte = m.get("corte_al_terminar") or m.get("corte_al_iniciar")
        if corte:
            cortes.append(corte)
    return max(cortes) if cortes else None


def registro_de_cadencia_atrasado(corte_del_registro: str, raiz: Path) -> str | None:
    """Si `cadencia.csv` esta detras de lo que raw YA sabe, el corte que le falta.
    `None` si esta al dia o mas adelante. Funcion pura sobre lo que le pasan.

    ## El defecto que esto cierra

    `CORTE_VIVO`, el que se muestra en el banner, sale de `cadencia.csv` (ver
    `leer_cadencia()`) y no de raw: es la unica fuente que trae la cadencia dia
    por dia. Pero `cadencia.csv` lo escribe GitHub Actions con su propio sondeo,
    independiente de cuando alguien corre `cargar_raw.py` a mano.

    Paso de verdad el 09/09/2026: se corrio el cargador y **si** ingirio el
    corte del 9 -esta en el manifiesto de la particion-, pero la copia LOCAL de
    `cadencia.csv` todavia no tenia la linea que Actions habia commiteado para
    ese mismo corte. El tablero salio diciendo "corte vivo: 8 de septiembre,
    lleva 1 dia sin regenerarse" sobre un modelo que ya reflejaba el corte del
    9. Los numeros de arriba (contratos, versiones, cambios) eran correctos: la
    inconsistencia era solo en el banner, y solo se veia leyendolo con cuidado.

    ## Por que se compara contra raw y no se corrige leyendo la fuente de nuevo

    Preguntarle otra vez a la API duplicaria una consulta que el cargador ya
    hizo, y en el peor caso (la fuente regenero justo en el medio) daria un
    tercer valor que ninguno de los dos archivos tiene. Raw ya sabe la respuesta
    -esta en el manifiesto de la particion que se acaba de construir- y
    preguntarle de nuevo a la fuente seria una segunda respuesta a una pregunta
    que D10 ya contesto.
    """
    ingerido = corte_mas_reciente_ingerido(raiz)
    if ingerido is not None and ingerido > corte_del_registro:
        return ingerido
    return None


def particiones_del_modelo(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Lo que el modelo ya ingirio, por la misma clave."""
    return {
        "/".join(fila) for fila in con.execute(
            "select distinct ruta_flujo, ruta_fecha_extraccion, ruta_particion "
            "from main_staging.raw_observaciones"
        ).fetchall()
    }


def sin_ingerir(en_disco: set[str], en_el_modelo: set[str]) -> set[str]:
    """Particiones que estan en raw y no en el modelo. Funcion pura.

    La comparacion es de **contenido y no de fechas de archivo**. Un `mtime` se
    mueve al copiar, al clonar el repositorio o con un `touch`, y ademas no
    distingue "el modelo es viejo" de "alguien abrio el archivo". Preguntar que
    particiones tiene cada lado contesta exactamente la pregunta que importa.

    Es la misma leccion que dejo el informe de paridad: una comparacion entre dos
    sistemas tiene que decir de cuando es cada lado, y la forma robusta de
    decirlo es comparar lo que contienen.
    """
    return en_disco - en_el_modelo


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument(
        "--sin-envoltura", action="store_true",
        help="Emite solo el contenido, sin las etiquetas html/head/body. Sirve "
             "para publicar la pagina dentro de un contenedor que ya las aporta.")
    p.add_argument("--base", type=Path, default=DUCKDB)
    p.add_argument(
        "--aunque-el-modelo-este-viejo", action="store_true",
        help="Genera el tablero aunque haya particiones de raw sin ingerir. El "
             "nombre es largo a proposito: publica cifras que no son las "
             "ultimas.")
    args = p.parse_args()

    if not args.base.is_file():
        print(f"No existe {args.base}. Corre `dbt build` primero.", file=sys.stderr)
        return 1

    con = duckdb.connect(str(args.base), read_only=True)
    # El mismo techo que usa dbt (R3): el tablero no puede pedir mas memoria que
    # el pipeline que lo alimenta.
    con.execute("set memory_limit='2GB'")
    con.execute("set threads=1")

    # El guardarrail va ANTES de consultar: si el modelo esta atrasado, todo lo
    # que se consulte despues es viejo, y publicarlo con la fecha de hoy es peor
    # que no publicar nada. Paso de verdad: el tablero estuvo una semana
    # mostrando 88.395 cambios cuando el modelo ya decia 863.951, y nada lo
    # noto, porque nadie compara la fecha del tablero contra la del modelo.
    faltan = sin_ingerir(particiones_con_datos(RAW), particiones_del_modelo(con))

    # Segundo guardarrail, distinto del primero: no compara raw contra el
    # modelo, compara raw contra `cadencia.csv`. Paso el 09/09/2026: el modelo
    # ya tenia el corte del 9, pero la copia LOCAL del registro -que GitHub
    # Actions escribe por su cuenta- todavia no habia llegado, y el banner del
    # tablero salio diciendo "corte vivo: 8 de septiembre" sobre un modelo que
    # ya sabia que era el 9.
    atraso_registro = registro_de_cadencia_atrasado(CORTE_VIVO, RAW)

    if (faltan or atraso_registro) and not args.aunque_el_modelo_este_viejo:
        con.close()
        mensaje = ""
        if faltan:
            mensaje += (
                f"ERROR el modelo esta atrasado respecto de la capa cruda.\n"
                f"  {len(faltan)} particion(es) de raw todavia no se ingirieron:\n"
                + "".join(f"      {c}\n" for c in sorted(faltan))
                + "  Se arregla construyendo el modelo:\n"
                "      cd dbt && uv run dbt build\n"
            )
        if atraso_registro:
            mensaje += (
                f"ERROR el registro de cadencia esta atrasado.\n"
                f"  Dice que el ultimo corte visto es "
                f"{CORTE_VIVO!r}, pero raw ya ingirio uno mas nuevo: "
                f"{atraso_registro!r}.\n"
                "  El banner del tablero saldria hablando de un corte que ya se "
                "quedo viejo.\n"
                "  Se arregla trayendo la version mas reciente del registro:\n"
                "      git pull\n"
            )
        mensaje += (
            "  El tablero saldria con fecha de hoy y algo adentro que no es lo "
            "ultimo.\n"
            "  Y si de verdad querias publicarlo asi:\n"
            "      uv run python scripts/generar_tablero.py --aunque-el-modelo-este-viejo"
        )
        print(mensaje, file=sys.stderr)
        return 3

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
