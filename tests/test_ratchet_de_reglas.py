"""Que el trinquete de RN12 y RN13 siga siendo un trinquete.

## Que problema resuelve un ratchet, y cual se crea

Las dos reglas nacen incumplidas: el incumplimiento ya esta en disco y no lo
puso este codigo. Ponerlas en `error` dejaria la suite roja desde el primer dia,
que es la forma mas segura de que la gente deje de mirarla. Ponerlas en `warn` a
secas las deja avisando para siempre sin que nadie note si el numero crece.

El trinquete es la salida: avisa mientras el numero sea el conocido, y falla si
sube. Pero introduce un modo de fallo propio, y es social: **la forma facil de
poner en verde un ratchet es subir el techo.**

Contra eso no hay test que valga por si solo, porque quien sube el techo puede
subir tambien lo que diga el numero. Lo que si se puede vigilar es la version
descuidada, que es la que de verdad pasa: cambiar el `config` y dejar la prosa
diciendo otra cosa. Un techo que no coincide con su justificacion escrita es un
techo que nadie justifico.

Es la misma idea que `verificar_columnas_dbt.py` aplica a las columnas: dos
lugares que tienen que decir lo mismo, comprobados byte a byte.

## Y el grano

Se vigila tambien el `group by id_contrato`. RN13 contaba una fila por
observacion y por eso paso de 7 a 9 sin un solo caso nuevo: los mismos dos
contratos, vistos en dos cortes. Volver a ese grano haria que el techo saltara
por ingerir datos, no por encontrar un problema, y la reaccion natural a una
alarma que suena sola es subir el techo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# regla -> techo que se acepta hoy, con la medicion que lo sostiene.
TRINQUETES = {
    "rn12_liquidacion_sin_inicio": 2,   # 08/09/2026, sobre 3.369.650 observaciones
    "rn13_valor_imposible": 7,          # 08/09/2026, sobre 3.369.650 observaciones
}


def _fuente(regla: str) -> str:
    ruta = RAIZ / "dbt" / "tests" / f"{regla}.sql"
    assert ruta.is_file(), f"falta {ruta.relative_to(RAIZ)}"
    return ruta.read_text(encoding="utf-8")


@pytest.mark.parametrize("regla", sorted(TRINQUETES))
def test_el_trinquete_sigue_puesto(regla: str):
    """Sin `error_if` esto vuelve a ser un aviso que nadie mira."""
    sql = _fuente(regla)
    config = re.search(r"\{\{\s*config\((.*?)\)\s*\}\}", sql, re.DOTALL)
    assert config, f"{regla} no tiene bloque config"
    cuerpo = config.group(1)
    assert "error_if" in cuerpo, (
        f"{regla} perdio su `error_if`: volvio a ser un warn permanente, que "
        f"es justo lo que el trinquete vino a arreglar"
    )
    assert 'warn_if=">0"' in cuerpo, (
        f"{regla} perdio su `warn_if`: el incumplimiento conocido tiene que "
        f"seguir viendose, aunque no rompa la construccion"
    )


@pytest.mark.parametrize("regla,techo", sorted(TRINQUETES.items()))
def test_el_techo_es_el_medido(regla: str, techo: int):
    sql = _fuente(regla)
    config = re.search(r"\{\{\s*config\((.*?)\)\s*\}\}", sql, re.DOTALL).group(1)
    puesto = re.search(r'error_if\s*=\s*">(\d+)"', config)
    assert puesto, f"{regla}: no se pudo leer el numero de `error_if`"
    assert int(puesto.group(1)) == techo, (
        f"{regla}: el techo del test dice {puesto.group(1)} y la medicion "
        f"registrada es {techo}.\n"
        f"Si el incumplimiento crecio, la respuesta no es subir el techo: es "
        f"mirar el caso nuevo. Si de verdad corresponde moverlo, se mueve aca "
        f"tambien y con la medicion que lo sostiene."
    )


@pytest.mark.parametrize("regla,techo", sorted(TRINQUETES.items()))
def test_la_prosa_dice_el_mismo_numero_que_el_config(regla: str, techo: int):
    """El caso descuidado: mover el `config` y dejar la explicacion vieja.

    Un techo cuya justificacion escrita dice otro numero es un techo que nadie
    justifico, y el proximo que lo lea va a creerle a la prosa.
    """
    sql = _fuente(regla)
    comentario = sql.split("-#}")[0]
    assert f'error_if=">{techo}"' in comentario, (
        f"{regla}: el bloque de documentacion no menciona `error_if=\">{techo}\"`.\n"
        f"El numero y su razon tienen que viajar juntos."
    )


@pytest.mark.parametrize("regla", sorted(TRINQUETES))
def test_el_grano_es_el_contrato(regla: str):
    """Con el grano en la observacion, el numero sube al ingerir un corte nuevo
    aunque no haya un caso nuevo. RN13 paso de 7 filas a 9 asi."""
    sql = _fuente(regla)
    consulta = sql.split("-#}")[1]
    assert "group by id_contrato" in consulta, (
        f"{regla} dejo de agrupar por contrato. Un contrato que incumple y "
        f"sigue vivo suma una fila por cada corte que lo vuelva a traer, y el "
        f"trinquete saltaria por ingerir datos en vez de por encontrar algo."
    )
