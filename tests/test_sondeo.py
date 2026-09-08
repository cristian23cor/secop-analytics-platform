"""La decision del sondeo: que anotar, cuando escribir y cuando avisar.

## Por que existe este archivo

Porque el defecto que arregla costo caro y era invisible desde adentro.

`sondear.py` corre cada tres horas. Su primera version contestaba "se movio la
fuente" comparando contra el ultimo corte de un dia **anterior**. En un dia en
que la fuente si se movio, ese contraste seguia siendo verdadero en los ocho
sondeos, asi que cada uno reescribia el registro, commiteaba y **abria otro
issue**.

Medido entre el 3 y el 8 de septiembre de 2026: **20 issues y hasta seis commits
en un mismo dia**, cuando lo correcto era uno por regeneracion.

Nada fallo. El workflow salio verde las 40 veces.

## Las dos preguntas que no hay que mezclar

**"Se movio desde la ultima vez que mire"** decide si vale escribir y avisar.

**"Regenero la fuente en esta fecha"** es el campo del registro, y una vez que
dice `si` no vuelve atras.

Solo coinciden si sondeas una vez por dia. Sondeando ocho, se separan.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from sondear import evaluar

AYER = "2026-09-07"
HOY = "2026-09-08"
CORTE_VIEJO = "2026-09-07T12:33:23.138Z"
CORTE_NUEVO = "2026-09-08T07:48:06.713Z"


def fila(fecha, corte, regenero="no", testigo="T", hora="08:00"):
    return {"fecha": fecha, "hora_cot": hora, "corte_vivo": corte,
            "testigo": testigo, "regenero": regenero, "fuente": "sondeo"}


def test_la_primera_observacion_del_dia_se_guarda():
    _, cambio, guardar = evaluar(CORTE_VIEJO, "T", [fila(AYER, CORTE_VIEJO)], HOY, "09:00")
    assert guardar, "un dia nuevo siempre merece su linea"
    assert not cambio, "el corte es el mismo: no hay nada que avisar"


def test_el_segundo_sondeo_del_dia_no_toca_nada():
    """El caso que costo 20 issues.

    Ya se anoto hoy que la fuente regenero. El sondeo siguiente ve el mismo
    corte que se anoto, asi que no cambio nada desde que mire.
    """
    filas = [fila(AYER, CORTE_VIEJO), fila(HOY, CORTE_NUEVO, regenero="si")]
    _, cambio, guardar = evaluar(CORTE_NUEVO, "T", filas, HOY, "12:00")
    assert not cambio, "no se movio desde el ultimo sondeo: no debe avisar"
    assert not guardar, "y no debe reescribir el archivo"


def test_si_se_mueve_dos_veces_el_mismo_dia_avisa_las_dos():
    """Lo contrario del anterior, y hace falta: la fuente puede regenerar dos
    veces en un dia, y la segunda tambien hay que capturarla."""
    filas = [fila(AYER, CORTE_VIEJO), fila(HOY, CORTE_NUEVO, regenero="si")]
    otro = "2026-09-08T19:00:00.000Z"
    linea, cambio, guardar = evaluar(otro, "T", filas, HOY, "20:00")
    assert cambio and guardar
    assert linea["corte_vivo"] == otro


def test_el_si_del_dia_no_vuelve_atras():
    """El campo del registro contesta 'regenero en esta fecha'. Un sondeo
    posterior que vea el mismo corte no puede bajarlo a 'no'."""
    filas = [fila(AYER, CORTE_VIEJO), fila(HOY, CORTE_NUEVO, regenero="si")]
    linea, _, _ = evaluar(CORTE_NUEVO, "T", filas, HOY, "23:00")
    assert linea["regenero"] == "si"


def test_un_testigo_vacio_no_pisa_al_que_ya_estaba():
    """La consulta al testigo puede fallar sin abortar el sondeo. Un fallo
    pasajero al mediodia no puede borrar el dato bueno de la manana."""
    filas = [fila(HOY, CORTE_NUEVO, testigo="2026-09-08T11:00:00Z")]
    linea, _, _ = evaluar(CORTE_NUEVO, "", filas, HOY, "15:00")
    assert linea["testigo"] == "2026-09-08T11:00:00Z"


def test_conseguir_un_testigo_que_faltaba_si_amerita_escribir():
    filas = [fila(HOY, CORTE_NUEVO, testigo="")]
    _, _, guardar = evaluar(CORTE_NUEVO, "T", filas, HOY, "15:00")
    assert guardar, "ganamos informacion que antes no estaba"


def test_un_testigo_que_falla_siempre_no_escribe_en_cada_sondeo():
    """Sin esto, un testigo caido convertiria los ocho sondeos diarios en ocho
    commits: la condicion tiene que exigir haberlo CONSEGUIDO, no que falte."""
    filas = [fila(HOY, CORTE_NUEVO, testigo="")]
    _, _, guardar = evaluar(CORTE_NUEVO, "", filas, HOY, "15:00")
    assert not guardar


def test_el_primer_sondeo_de_la_historia_no_inventa_una_regeneracion():
    """Sin corte anterior no hay con que comparar. Decir que regenero seria
    afirmar algo que nadie observo."""
    linea, cambio, guardar = evaluar(CORTE_NUEVO, "T", [], HOY, "08:00")
    assert not cambio
    assert linea["regenero"] == "no"
    assert guardar


@pytest.mark.parametrize("sondeos", [2, 5, 8])
def test_muchos_sondeos_sin_cambios_escriben_una_sola_vez(sondeos):
    """La prueba de fuego: simula un dia entero de sondeos cada tres horas."""
    filas = [fila(AYER, CORTE_VIEJO)]
    escrituras = 0
    for i in range(sondeos):
        linea, _, guardar = evaluar(CORTE_VIEJO, "T", filas, HOY, f"{i * 3:02d}:00")
        if guardar:
            escrituras += 1
            hoy = next((f for f in filas if f["fecha"] == HOY), None)
            if hoy:
                filas[filas.index(hoy)] = linea
            else:
                filas.append(linea)
    assert escrituras == 1, f"{sondeos} sondeos produjeron {escrituras} escrituras"
