"""Pregunta que corte esta publicado y lo anota. Dos segundos.

## Por que existe

El registro de cadencia es **el unico insumo del proyecto que no se recupera
hacia atras**. La fuente se sobrescribe, asi que un dia que nadie miro es un dia
perdido: no hay forma de averiguar despues si el 30 de agosto regenero.

De ese registro dependen tres cosas que hoy no se pueden fijar con fundamento: el
umbral de `freshness`, cada cuanto conviene sondear, y si hay patron de dias
habiles.

## Por que no lo hace el DAG

El DAG corre el cargador, que sale por codigo 4 cuando el corte ya se ingirio y
no deja rastro de haber preguntado. Y sobre todo, el DAG vive en una maquina que
se apaga. Esto esta pensado para correr en GitHub Actions, que no.

## Que hace

Una consulta al corte y otra al testigo, y escribe o actualiza **la linea de hoy**
en `exploration/cadencia.csv`. Una linea por dia, no una por corrida.

Y solo toca el archivo si hay algo que guardar: la primera observacion del dia, un
corte que cambio, o un testigo que la consulta anterior no habia podido leer. Los
sondeos frecuentes existen para detectar rapido; el registro necesita una linea
por dia. Sin esa distincion, sondear cada tres horas serian ocho commits diarios
de ruido.

`regenero` se decide contra el ultimo corte conocido de un dia ANTERIOR, no
contra la linea de hoy, para que sondear dos veces el mismo dia no borre un
cambio ya detectado.

## Codigos de salida

    0   se sondeo y la fuente NO se movio
    5   se sondeo y la fuente REGENERO: hay que correr el cargador
    2   no se pudo consultar

El 5 es propio y distinto de un error a proposito: quien orqueste esto tiene que
poder separar "hay trabajo" de "algo se rompio", que es el mismo argumento por el
que el cargador devuelve 4.
"""

from __future__ import annotations

import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from secop_analytics.paginacion import ErrorDeConfiguracion, corte

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "exploration" / "cadencia.csv"
ZONA = ZoneInfo("America/Bogota")

# El dataset hermano que escribe en continuo. Sirve para separar "la fuente no
# regenero" de "toda la plataforma esta caida": son dos sistemas y solo uno se
# detiene. Ver la pregunta abierta sobre que tan buen testigo es.
TESTIGO = "https://www.datos.gov.co/resource/cb9c-h8sn.json"

CAMPOS = ["fecha", "hora_cot", "corte_vivo", "testigo", "regenero", "fuente"]


def leer() -> tuple[list[str], list[dict[str, str]]]:
    """Devuelve las lineas de comentario y las filas. Los comentarios se
    conservan: explican la deduccion y el formato, y se perderian al reescribir."""
    texto = REGISTRO.read_text(encoding="utf-8").splitlines()
    comentarios = [l for l in texto if l.startswith("#")]
    filas = list(csv.DictReader(l for l in texto if not l.startswith("#")))
    return comentarios, filas


def escribir(comentarios: list[str], filas: list[dict[str, str]]) -> None:
    with REGISTRO.open("w", encoding="utf-8", newline="") as f:
        for c in comentarios:
            f.write(c + "\n")
        w = csv.DictWriter(f, fieldnames=CAMPOS, lineterminator="\n")
        w.writeheader()
        w.writerows(filas)


def consultar_testigo() -> str:
    """Devuelve cadena vacia si falla. Es un control, no un dato del que se
    dependa: perder el testigo no vale abortar el sondeo."""
    try:
        r = requests.get(
            TESTIGO,
            params={"$select": "max(:updated_at) as testigo"},
            headers={"X-App-Token": os.environ["SOCRATA_APP_TOKEN"]},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()[0]["testigo"] or ""
    except Exception as error:  # noqa: BLE001  el control es opcional
        print(f"  (no se pudo leer el testigo: {type(error).__name__})")
        return ""


def main() -> int:
    ahora = datetime.now(ZONA)
    fecha, hora = ahora.date().isoformat(), ahora.strftime("%H:%M")

    try:
        vivo = corte(verboso=False).mas_nuevo
    except ErrorDeConfiguracion as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001
        print(f"ERROR no se pudo consultar el corte: "
              f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2

    comentarios, filas = leer()

    # Contra el ultimo corte conocido de un dia ANTERIOR. Comparar contra la
    # linea de hoy borraria un cambio ya detectado esta misma manana.
    anterior = next(
        (f["corte_vivo"] for f in reversed(filas)
         if f["corte_vivo"] and f["fecha"] < fecha),
        "",
    )
    regenero = bool(anterior) and vivo != anterior

    linea = {
        "fecha": fecha, "hora_cot": hora, "corte_vivo": vivo,
        "testigo": consultar_testigo(),
        "regenero": "si" if regenero else "no",
        "fuente": "sondeo",
    }
    # Si el registro cambio de forma que valga la pena guardar. Los sondeos son
    # frecuentes para DETECTAR rapido; el registro necesita una linea por dia.
    # Sin esta distincion, sondear cada tres horas serian ocho commits diarios de
    # ruido en un historial que alguien va a leer.
    hoy_ya_esta = next((f for f in filas if f["fecha"] == fecha), None)
    vale_guardar = hoy_ya_esta is None or regenero or not hoy_ya_esta["testigo"]
    if hoy_ya_esta is not None:
        # Un `si` ya anotado hoy no se pisa: la fuente se movio, aunque la
        # consulta siguiente vea el mismo corte que la anterior.
        if hoy_ya_esta["regenero"] == "si":
            linea["regenero"] = "si"
        # Y un testigo ya capturado tampoco. La consulta al testigo puede fallar
        # sin abortar el sondeo, y sin esto un fallo pasajero al mediodia borra
        # el dato bueno de la manana. Vale la regla general: un sondeo posterior
        # agrega informacion, nunca la quita.
        if not linea["testigo"]:
            linea["testigo"] = hoy_ya_esta["testigo"]
        filas[filas.index(hoy_ya_esta)] = linea
    else:
        filas.append(linea)
    if vale_guardar:
        escribir(comentarios, filas)

    dias = (ahora.date() - datetime.fromisoformat(vivo[:10]).date()).days
    print(f"  corte vivo:  {vivo}")
    print(f"  congelada:   {dias} dia(s)")
    print(f"  anotado en:  {REGISTRO.relative_to(RAIZ)}")

    if salida := os.environ.get("GITHUB_OUTPUT"):
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"regenero={'true' if regenero else 'false'}\n")
            f.write(f"guardar={'true' if vale_guardar else 'false'}\n")
            f.write(f"corte={vivo}\n")
            f.write(f"dias={dias}\n")

    if regenero:
        print()
        print(f"  LA FUENTE REGENERO. El corte anterior era {anterior}.")
        print("  Hay que correr: uv run python scripts/cargar_raw.py --flujo vivos")
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
