{#-
  Este archivo se genera automáticamente a partir de `src/secop_analytics/columnas.py`.
  La lista de columnas que aparece aquí refleja la fuente de verdad del esquema y
  se mantiene en sincronía con la generación que hace `scripts/generar_columnas_dbt.py`.

  La idea es evitar que el modelo y la definición del esquema queden desalineados,
  porque esa diferencia suele aparecer cuando una lista cambia en la fuente y no se
  reproduce el output generado. El chequeo de consistencia queda en
  `scripts/verificar_columnas_dbt.py` y sirve como referencia de revisión.

  Generado con 67 columnas extraídas.
-#}

{#- Esta lista corresponde a las 67 columnas solicitadas a la API. El orden sigue
    el de `columnas.py`, que las ordena alfabéticamente para mantener la salida
    generada estable entre ejecuciones. -#}
{% macro columnas_extraidas() %}
    {{ return([
        "ciudad",
        "codigo_de_categoria_principal",
        "codigo_entidad",
        "codigo_proveedor",
        "condiciones_de_entrega",
        "departamento",
        "descripcion_del_proceso",
        "descripcion_documentos_tipo",
        "destino_gasto",
        "dias_adicionados",
        "direcci_n_de_ejecuci_n_del_contrato",
        "documento_proveedor",
        "documentos_tipo",
        "duraci_n_del_contrato",
        "el_contrato_puede_ser_prorrogado",
        "entidad_centralizada",
        "es_grupo",
        "es_pyme",
        "espostconflicto",
        "estado_contrato",
        "fecha_de_fin_del_contrato",
        "fecha_de_firma",
        "fecha_de_inicio_del_contrato",
        "fecha_de_notificaci_n_de_prorrogaci_n",
        "fecha_fin_liquidacion",
        "fecha_inicio_liquidacion",
        "habilita_pago_adelantado",
        "id_contrato",
        "justificacion_modalidad_de",
        "liquidaci_n",
        "localizaci_n",
        "modalidad_de_contratacion",
        "nit_entidad",
        "nombre_entidad",
        "objeto_del_contrato",
        "obligaci_n_ambiental",
        "obligaciones_postconsumo",
        "orden",
        "origen_de_los_recursos",
        "pilares_del_acuerdo",
        "presupuesto_general_de_la_nacion_pgn",
        "proceso_de_compra",
        "proveedor_adjudicado",
        "puntos_del_acuerdo",
        "rama",
        "recursos_de_credito",
        "recursos_propios",
        "recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_",
        "referencia_del_contrato",
        "reversion",
        "saldo_cdp",
        "saldo_vigencia",
        "sector",
        "sistema_general_de_participaciones",
        "sistema_general_de_regal_as",
        "tipo_de_contrato",
        "tipodocproveedor",
        "ultima_actualizacion",
        "urlproceso",
        "valor_amortizado",
        "valor_de_pago_adelantado",
        "valor_del_contrato",
        "valor_facturado",
        "valor_pagado",
        "valor_pendiente_de",
        "valor_pendiente_de_ejecucion",
        "valor_pendiente_de_pago"
    ]) }}
{% endmacro %}

{#- El `STRUCT` con el que el modelo frontera lee `datos`.

    La decisión de dejarlo explícito es importante porque `read_json_auto` deduce la
    forma de una muestra de filas y la API omite las claves nulas (H6): una columna
    que ninguna fila muestreada traiga no entra al struct, y el modelo que la use
    falla. Las que arrancan nulas y después se llenan son justamente las materiales:
    las tres fechas de hito y `ultima_actualizacion`.

    Ese mismo patrón ya apareció con la sexta fuente de financiación de RN1: leímos
    'no apareció en la muestra' como 'casi nunca tiene valor', y estaba en el 45%
    de los contratos.

    Cuando la fuente agrega una clave que este struct no tiene, se ignora sin avisar.
    Esa limitación ya estaba presente porque el `$select` pide solo estas 67 columnas,
    y raw nunca las trae. Las columnas nuevas se detectan con
    `columnas.validar_cobertura()`. -#}
{% macro struct_de_datos() %}
    {%- set campos %}STRUCT(
        ciudad VARCHAR,
        codigo_de_categoria_principal VARCHAR,
        codigo_entidad VARCHAR,
        codigo_proveedor VARCHAR,
        condiciones_de_entrega VARCHAR,
        departamento VARCHAR,
        descripcion_del_proceso VARCHAR,
        descripcion_documentos_tipo VARCHAR,
        destino_gasto VARCHAR,
        dias_adicionados VARCHAR,
        direcci_n_de_ejecuci_n_del_contrato VARCHAR,
        documento_proveedor VARCHAR,
        documentos_tipo VARCHAR,
        duraci_n_del_contrato VARCHAR,
        el_contrato_puede_ser_prorrogado VARCHAR,
        entidad_centralizada VARCHAR,
        es_grupo VARCHAR,
        es_pyme VARCHAR,
        espostconflicto VARCHAR,
        estado_contrato VARCHAR,
        fecha_de_fin_del_contrato VARCHAR,
        fecha_de_firma VARCHAR,
        fecha_de_inicio_del_contrato VARCHAR,
        fecha_de_notificaci_n_de_prorrogaci_n VARCHAR,
        fecha_fin_liquidacion VARCHAR,
        fecha_inicio_liquidacion VARCHAR,
        habilita_pago_adelantado VARCHAR,
        id_contrato VARCHAR,
        justificacion_modalidad_de VARCHAR,
        liquidaci_n VARCHAR,
        localizaci_n VARCHAR,
        modalidad_de_contratacion VARCHAR,
        nit_entidad VARCHAR,
        nombre_entidad VARCHAR,
        objeto_del_contrato VARCHAR,
        obligaci_n_ambiental VARCHAR,
        obligaciones_postconsumo VARCHAR,
        orden VARCHAR,
        origen_de_los_recursos VARCHAR,
        pilares_del_acuerdo VARCHAR,
        presupuesto_general_de_la_nacion_pgn VARCHAR,
        proceso_de_compra VARCHAR,
        proveedor_adjudicado VARCHAR,
        puntos_del_acuerdo VARCHAR,
        rama VARCHAR,
        recursos_de_credito VARCHAR,
        recursos_propios VARCHAR,
        recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_ VARCHAR,
        referencia_del_contrato VARCHAR,
        reversion VARCHAR,
        saldo_cdp VARCHAR,
        saldo_vigencia VARCHAR,
        sector VARCHAR,
        sistema_general_de_participaciones VARCHAR,
        sistema_general_de_regal_as VARCHAR,
        tipo_de_contrato VARCHAR,
        tipodocproveedor VARCHAR,
        ultima_actualizacion VARCHAR,
        urlproceso JSON,
        valor_amortizado VARCHAR,
        valor_de_pago_adelantado VARCHAR,
        valor_del_contrato VARCHAR,
        valor_facturado VARCHAR,
        valor_pagado VARCHAR,
        valor_pendiente_de VARCHAR,
        valor_pendiente_de_ejecucion VARCHAR,
        valor_pendiente_de_pago VARCHAR
    ){% endset -%}
    {{ return(campos | trim) }}
{% endmacro %}

{#- Clasificación de D6 / §5 del modelo dimensional. Esta definición decide qué
    genera una versión nueva en el SCD2, no qué se descarga.

    En raw no se usa esta clasificación: ahí la comparación es por bytes y no
    distingue categorías. Son dos filtros de distinta finura. -#}
{% macro columnas_materiales() %}
    {{ return([
        "codigo_proveedor",
        "dias_adicionados",
        "documento_proveedor",
        "duraci_n_del_contrato",
        "estado_contrato",
        "fecha_de_fin_del_contrato",
        "fecha_de_notificaci_n_de_prorrogaci_n",
        "fecha_fin_liquidacion",
        "fecha_inicio_liquidacion",
        "liquidaci_n",
        "presupuesto_general_de_la_nacion_pgn",
        "proveedor_adjudicado",
        "recursos_de_credito",
        "recursos_propios",
        "recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_",
        "saldo_cdp",
        "saldo_vigencia",
        "sistema_general_de_participaciones",
        "sistema_general_de_regal_as",
        "ultima_actualizacion",
        "valor_amortizado",
        "valor_de_pago_adelantado",
        "valor_del_contrato",
        "valor_facturado",
        "valor_pagado",
        "valor_pendiente_de",
        "valor_pendiente_de_ejecucion",
        "valor_pendiente_de_pago"
    ]) }}
{% endmacro %}

{% macro columnas_imposibles() %}
    {{ return([
        "codigo_de_categoria_principal",
        "codigo_entidad",
        "fecha_de_firma",
        "fecha_de_inicio_del_contrato",
        "id_contrato",
        "nit_entidad",
        "proceso_de_compra"
    ]) }}
{% endmacro %}

{% macro columnas_cosmeticas() %}
    {{ return([
        "ciudad",
        "condiciones_de_entrega",
        "departamento",
        "descripcion_del_proceso",
        "descripcion_documentos_tipo",
        "destino_gasto",
        "direcci_n_de_ejecuci_n_del_contrato",
        "documentos_tipo",
        "el_contrato_puede_ser_prorrogado",
        "entidad_centralizada",
        "es_grupo",
        "es_pyme",
        "espostconflicto",
        "habilita_pago_adelantado",
        "justificacion_modalidad_de",
        "localizaci_n",
        "modalidad_de_contratacion",
        "nombre_entidad",
        "objeto_del_contrato",
        "obligaci_n_ambiental",
        "obligaciones_postconsumo",
        "orden",
        "origen_de_los_recursos",
        "pilares_del_acuerdo",
        "puntos_del_acuerdo",
        "rama",
        "referencia_del_contrato",
        "reversion",
        "sector",
        "tipo_de_contrato",
        "tipodocproveedor",
        "urlproceso"
    ]) }}
{% endmacro %}

{#- Tipos de destino de `stg_contratos`. Eje distinto de la clasificación de
    arriba: aquella decide qué genera versión, ésta decide a qué se castea. Lo
    que no está en ninguno queda texto. -#}
{% macro columnas_monetarias() %}
    {{ return([
        "presupuesto_general_de_la_nacion_pgn",
        "recursos_de_credito",
        "recursos_propios",
        "recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_",
        "saldo_cdp",
        "saldo_vigencia",
        "sistema_general_de_participaciones",
        "sistema_general_de_regal_as",
        "valor_amortizado",
        "valor_de_pago_adelantado",
        "valor_del_contrato",
        "valor_facturado",
        "valor_pagado",
        "valor_pendiente_de",
        "valor_pendiente_de_ejecucion",
        "valor_pendiente_de_pago"
    ]) }}
{% endmacro %}

{% macro columnas_fechas() %}
    {{ return([
        "fecha_de_fin_del_contrato",
        "fecha_de_firma",
        "fecha_de_inicio_del_contrato",
        "fecha_de_notificaci_n_de_prorrogaci_n",
        "fecha_fin_liquidacion",
        "fecha_inicio_liquidacion",
        "ultima_actualizacion"
    ]) }}
{% endmacro %}

{% macro columnas_enteras() %}
    {{ return([
        "dias_adicionados"
    ]) }}
{% endmacro %}

{#- Donde el centinela no se convierte a nulo:
    `habilita_pago_adelantado` tiene tres estados y 'No Definido'
    significa 'no se declaró' (RN10). -#}
{% macro columnas_centinela_es_valor() %}
    {{ return([
        "habilita_pago_adelantado"
    ]) }}
{% endmacro %}

{% macro centinelas() %}
    {{ return([
        "No definido",
        "No Definido"
    ]) }}
{% endmacro %}