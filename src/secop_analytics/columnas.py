"""Catálogo de columnas de SECOP II – Contratos Electrónicos (`jbjy-vk9h`).

Fuente de verdad única para dos cosas que en otros proyectos se escriben dos
veces y se desincronizan:

1. **Qué se le pide a la API.** `COLUMNAS_EXTRAIDAS` arma el `$select`. Lo que
   no está acá no se descarga.
2. **Cómo se compara cada columna** entre dos observaciones consecutivas, según
   la clasificación de `01_modelo_dimensional.md` §5.

Advertencia sobre la palabra "cosmética": no quiere decir excluida. Una columna
cosmética se descarga, se guarda y alimenta las dimensiones. Lo único que no
hace es generar una versión nueva en `fct_contratos_snapshot`. El conjunto que
no se descarga es `PERSONALES`, y es un eje aparte.

Los 85 nombres se verificaron contra el endpoint de metadatos del dataset, no
contra una muestra de filas: la API omite las claves nulas, así que una muestra
subestima el esquema.

Los cuatro conjuntos cubren las 85 sin solaparse, y `tests/test_columnas.py` lo
verifica. Ese test importa más de lo que parece: una columna puesta en dos
conjuntos no rompe nada visible —el `$select` funciona igual— pero cambia con
qué criterio se compara, según el orden de los `if` en `clasificacion()`.

Referencias: `exploration/01_modelo_dimensional.md` §5 (la clasificación),
`00_inventario_fuentes.md` (H6 el esquema, H7 los datos personales) y
`03_decisiones_capa_raw.md` (D1 y D6, cómo se usa esta clasificación).

Dos advertencias para quien construya la detección de cambios encima:

1. **La API omite las claves nulas.** Una fila real trajo 81 de 85, y las
   cuatro ausentes eran `ultima_actualizacion` y las tres fechas de
   liquidación/prórroga: las cuatro son MATERIALES. Cuando el hito ocurre, la
   clave aparece. Comparar diccionarios crudos leería eso como cambio de
   esquema en vez de como el paso de nulo a fecha, que es el cambio más
   informativo del snapshot. La capa raw debe materializar las columnas de
   `COLUMNAS_EXTRAIDAS` completas, rellenando con nulo lo omitido, ANTES de
   comparar.

2. **Los nulos también vienen como centinela de texto**, y con dos
   capitalizaciones: "No definido" y "No Definido". No son nulos de verdad, así
   que el punto anterior no los cubre. Se normalizan en `staging`.
"""

from typing import Final

# --------------------------------------------------------------------------
# MATERIALES — cambió el contrato en el mundo real y una pregunta de negocio
# lo necesita. Genera versión nueva.
# --------------------------------------------------------------------------
MATERIALES: Final[frozenset[str]] = frozenset({
    "estado_contrato",
    # Bloque monetario. `valor_pagado` es la columna que justifica el proyecto:
    # si no genera versión, los 735.809 contratos con pagos se quedan sin serie
    # temporal y ningún test falla. Es el error más caro posible del diseño.
    "valor_del_contrato",
    "valor_pagado",
    "valor_facturado",
    "valor_pendiente_de_pago",
    "valor_pendiente_de_ejecucion",
    "valor_amortizado",
    "valor_de_pago_adelantado",
    # `valor_pendiente_de` está truncada por Socrata: es el valor pendiente de
    # AMORTIZACIÓN (resuelto con el diccionario oficial; cierra la pregunta
    # abierta 1 del inventario). Es el saldo vivo del pago adelantado, así que
    # se mueve cada vez que hay una amortización. Candidata a RN8:
    #   valor_de_pago_adelantado = valor_amortizado + valor_pendiente_de
    "valor_pendiente_de",
    "saldo_cdp",
    "saldo_vigencia",
    # Plazo. `dias_adicionados` y `fecha_de_fin_del_contrato` son el mismo
    # evento visto desde los dos lados (RN7).
    "dias_adicionados",
    "fecha_de_fin_del_contrato",
    "duraci_n_del_contrato",
    # Hitos que arrancan nulos y se llenan. Pasar de nulo a fecha es el cambio
    # más informativo que existe en un snapshot acumulativo.
    "fecha_inicio_liquidacion",
    "fecha_fin_liquidacion",
    "fecha_de_notificaci_n_de_prorrogaci_n",
    "liquidaci_n",
    # Fecha del último evento contractual. No es auditoría técnica: su nulo es
    # información. Además es el watermark del flujo 2.
    "ultima_actualizacion",
    # El trío del proveedor cambia con la cesión (28.557 contratos en `cedido`).
    "proveedor_adjudicado",
    "documento_proveedor",
    "codigo_proveedor",
    # Fuentes de financiación. Materiales porque RN1 exige que su suma iguale
    # `valor_del_contrato`; si el valor sube por una adición y las fuentes no
    # versionan, quedan versiones históricas donde RN1 no se cumple (RN6).
    #
    # ⚠ Son SEIS, no cinco. La última solo aparece enumerando el esquema
    # completo: ninguna muestra de filas la mostró. Se clasifica como material
    # por el mismo criterio que las otras cinco, pero la definición de RN1
    # queda pendiente de revisión (ver `00_inventario_fuentes.md`).
    "presupuesto_general_de_la_nacion_pgn",
    "sistema_general_de_participaciones",
    "sistema_general_de_regal_as",
    "recursos_de_credito",
    "recursos_propios",
    "recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_",
})

# --------------------------------------------------------------------------
# IMPOSIBLES — no deberían cambiar nunca. No se comparan para versionar: si
# cambian, se dispara una alerta.
#
# El criterio de separación con MATERIALES es la pregunta: si esto cambia
# mañana, ¿quiero una alarma o quiero un registro?
# --------------------------------------------------------------------------
IMPOSIBLES: Final[frozenset[str]] = frozenset({
    "id_contrato",
    "fecha_de_firma",
    "fecha_de_inicio_del_contrato",
    "proceso_de_compra",
    "nit_entidad",
    "codigo_entidad",
    "codigo_de_categoria_principal",
})

# --------------------------------------------------------------------------
# COSMÉTICAS — cambió el registro, no el contrato. Se pisa el valor actual sin
# generar versión. Se descargan igual: acá viven casi todos los atributos de
# las dimensiones.
# --------------------------------------------------------------------------
COSMETICAS: Final[frozenset[str]] = frozenset({
    # --- dim_entidad. `orden`, `rama` y `sector` entran como atributos con la
    # advertencia documentada; no se construye lógica de negocio encima (H6).
    "nombre_entidad",
    "orden",
    "rama",
    "sector",
    "entidad_centralizada",
    # --- dim_proveedor. `tipodocproveedor` se conserva como evidencia pero no
    # se usa para derivar `tipo_persona`: falla en las dos direcciones — hay
    # S.A.S. marcadas como "Cédula de Ciudadanía" y personas naturales marcadas
    # como "NIT". Ver `01_modelo_dimensional.md` §6, `dim_proveedor`.
    "tipodocproveedor",
    "es_pyme",
    "es_grupo",
    # --- dim_modalidad.
    "modalidad_de_contratacion",
    "tipo_de_contrato",
    "justificacion_modalidad_de",
    # --- Texto libre. Pueden cambiar con una modificación de alcance, pero
    # traen saltos de línea embebidos y truncamiento: normalizar antes de
    # comparar, si alguna vez se decide compararlos.
    "objeto_del_contrato",
    "descripcion_del_proceso",
    "condiciones_de_entrega",
    "documentos_tipo",
    "descripcion_documentos_tipo",
    # --- Geografía. `localizaci_n` es redundante con las otras dos y trae
    # espacios dobles (H6); entra igual, se resuelve en `staging`.
    "departamento",
    "ciudad",
    "localizaci_n",
    # Cosmética por decisión explícita: el ruido supera la ganancia.
    "direcci_n_de_ejecuci_n_del_contrato",
    # --- Marcas de política pública. Atributos descriptivos, no medidas.
    "espostconflicto",
    "pilares_del_acuerdo",
    "puntos_del_acuerdo",
    "obligaci_n_ambiental",
    "obligaciones_postconsumo",
    "reversion",
    # --- LAS QUE HUBO QUE EVALUAR UNA POR UNA --------------------------
    # No clasificar por descarte: "el resto es cosmética" es una frase que se
    # escribe sin la lista de 85 delante. Las seis siguientes quedaron
    # cosméticas, pero **por razones distintas entre sí**, y dos con pendientes
    # abiertos. Una categoría definida como "todo lo demás" no está definida.
    #
    # `origen_de_los_recursos`: en la fila inspeccionada vale "Recursos
    #   Propios" y la única de las seis fuentes con valor es `recursos_propios`.
    #   Parece ser la etiqueta de cuál columna está poblada, o sea redundante
    #   con RN1. PENDIENTE: verificar con un cruce sobre el dataset completo
    #   antes de darlo por cerrado (una fila genera hipótesis, no conclusión).
    "origen_de_los_recursos",
    # `destino_gasto`: corte funcionamiento / inversión. Estable por contrato.
    #   Cosmética para comparación, pero comercialmente relevante: vender
    #   contra presupuesto de inversión y contra funcionamiento son negocios
    #   distintos. Candidata a atributo de mart.
    "destino_gasto",
    # Las dos siguientes cumplen la primera condición de "material" (una
    # modificación podría darlas vuelta) y fallan la segunda: ninguna pregunta
    # de negocio necesita saber CUÁNDO cambiaron. Sirven mejor como tests de
    # coherencia sobre la fila actual.
    #   RN9 candidata: puede_ser_prorrogado = "No" y dias_adicionados > 0
    #   RN10 candidata: habilita_pago_adelantado = "No" y adelantado > 0
    # OJO: `habilita_pago_adelantado` NO es booleana. Observada en "No
    # Definido". Tres estados, y "No Definido" no equivale a "No".
    "el_contrato_puede_ser_prorrogado",
    "habilita_pago_adelantado",
    # `referencia_del_contrato`: numeración interna de la entidad
    #   ("CPS-3548-2022" = tipo, consecutivo, año). No es identificador global
    #   —otra entidad usa el mismo string— y las entidades la editan a mano.
    #   Ponerla en IMPOSIBLES llenaría la alerta de ruido, y una alerta ruidosa
    #   enseña a ignorarla. Queda cosmética.
    "referencia_del_contrato",
    # `urlproceso`: objeto anidado `{"url": "..."}` (H6). NO se puede
    #   reconstruir desde `proceso_de_compra`: la URL trae
    #   `noticeUID=CO1.NTC.xxx` mientras que `proceso_de_compra` es
    #   `CO1.BDOS.xxx`. Es un tercer identificador que no aparece en ninguna
    #   otra columna, y probablemente la llave hacia el dataset de Procesos de
    #   Contratación (candidato v2). Se extrae; en `staging` se parsea el
    #   `noticeUID` a columna propia y se aplana el objeto.
    #
    #   ⚠ Raw NO aplana: guarda el objeto tal como llegó. Fue justamente esta
    #   columna la que descartó Parquet como formato de raw — aplanarla habría
    #   sido normalizar, y D1 prohíbe normalizar antes de comparar. Por eso raw
    #   es JSONL comprimido. Ver `03_decisiones_capa_raw.md`, D2.
    "urlproceso",
})

# --------------------------------------------------------------------------
# PERSONALES — no se descargan. Eje aparte, no una cuarta categoría de
# comparación: nunca llegan a compararse porque nunca entran.
#
# Legalmente son datos abiertos, pero republicarlos en un tablero es otra cosa
# (H7). El filtro corre en el `$select`, no después: la exclusión más barata de
# auditar es la que hace que el dato no viaje.
# --------------------------------------------------------------------------
PERSONALES: Final[frozenset[str]] = frozenset({
    # Representante legal — incluye domicilio residencial.
    "nombre_representante_legal",
    "identificaci_n_representante_legal",
    "tipo_de_identificaci_n_representante_legal",
    "domicilio_representante_legal",
    "g_nero_representante_legal",
    "nacionalidad_representante_legal",
    # Ordenador del gasto.
    "nombre_ordenador_del_gasto",
    "n_mero_de_documento_ordenador_del_gasto",
    "tipo_de_documento_ordenador_del_gasto",
    # Ordenador de pago.
    "nombre_ordenador_de_pago",
    "n_mero_de_documento_ordenador_de_pago",
    "tipo_de_documento_ordenador_de_pago",
    # Supervisor.
    "nombre_supervisor",
    "n_mero_de_documento_supervisor",
    "tipo_de_documento_supervisor",
    # Datos bancarios.
    "n_mero_de_cuenta",
    "tipo_de_cuenta",
    "nombre_del_banco",
})


CLASIFICADAS: Final[frozenset[str]] = (
    MATERIALES | IMPOSIBLES | COSMETICAS | PERSONALES
)

# Lo que efectivamente se le pide a la API.
COLUMNAS_EXTRAIDAS: Final[tuple[str, ...]] = tuple(
    sorted(MATERIALES | IMPOSIBLES | COSMETICAS)
)


def clausula_select() -> str:
    """Devuelve el valor del parámetro `$select` de SODA2."""
    return ",".join(COLUMNAS_EXTRAIDAS)


def validar_cobertura(columnas_de_la_fuente: set[str]) -> dict[str, set[str]]:
    """Compara lo que la fuente ofrece hoy contra lo que este módulo clasifica.

    Se corre como chequeo barato (una llamada al endpoint de metadatos), en su
    propia tarea, no en el camino caliente de la ingesta.

    - `sin_clasificar`: columnas nuevas en la fuente. Un `$select` con lista
      explícita las ignoraría en silencio; acá se vuelven ruidosas.
    - `desaparecidas`: columnas que clasificamos y la fuente ya no entrega. Si
      alguna es material, el `$select` va a fallar en la próxima corrida.
    """
    return {
        "sin_clasificar": columnas_de_la_fuente - CLASIFICADAS,
        "desaparecidas": CLASIFICADAS - columnas_de_la_fuente,
    }


def clasificacion(columna: str) -> str:
    """Categoría de comparación de una columna. Sirve a la capa raw."""
    if columna in IMPOSIBLES:
        return "imposible"
    if columna in MATERIALES:
        return "material"
    if columna in COSMETICAS:
        return "cosmetica"
    if columna in PERSONALES:
        return "personal"
    raise KeyError(f"Columna sin clasificar: {columna!r}")