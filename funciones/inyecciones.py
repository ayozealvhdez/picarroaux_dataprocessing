"""
Funciones de detección y resumen de inyecciones target.

Fecha de creación: 27/08/2026
Fecha de última modificación: 27/08/2026

Listado de cambios:

"""

import csv
import os
from datetime import datetime, timezone

import numpy as np

from funciones.comunes import construir_ruta_fecha, convertir_float
from funciones.comunes import convertir_epoch_a_fecha_decimal
from funciones.comunes import convertir_fecha_decimal_a_epoch
from funciones.comunes import crear_directorio
from funciones.comunes import escribir_csv_atomico
from funciones.comunes import interpretar_booleano, obtener_fechas_periodo
from funciones.comunes import obtener_indice_processing_flag


# ==========================================================
# IDENTIFICACIÓN DE TARGETS MEDIANTE MPVPOSITION
# ==========================================================


# ==========================================================
# DETECCIÓN DE SEGMENTOS CONTINUOS POR MPVPOSITION
# ==========================================================


def obtener_posiciones_target(
        fecha_inicio,
        fecha_fin,
        directorio_preprocesado,
):
    """
    Localiza las posiciones target presentes en el periodo preprocesado.

    Devuelve una lista ordenada de enteros.
    """
    posiciones = []
    for fecha_trabajo in obtener_fechas_periodo(fecha_inicio, fecha_fin):
        ruta_fecha = os.path.join(
            construir_ruta_fecha(directorio_preprocesado, fecha_trabajo),
            "target",
        )
        if not os.path.isdir(ruta_fecha):
            continue

        for nombre in os.listdir(ruta_fecha):
            if not nombre.startswith("mpv_"):
                continue

            texto_posicion = nombre[4:]
            if not texto_posicion.isdigit():
                continue

            posicion = int(texto_posicion)
            if posicion not in posiciones:
                posiciones.append(posicion)

    posiciones.sort()
    return posiciones


def obtener_archivos_target(
        fecha_inicio,
        fecha_fin,
        directorio_preprocesado,
        posicion_mpv,
):
    """
    Obtiene los CSV target diarios para una posición MPV.

    Devuelve una lista cronológicamente ordenada.
    """
    archivos = []
    for fecha_trabajo in obtener_fechas_periodo(fecha_inicio, fecha_fin):
        ruta_fecha = os.path.join(
            construir_ruta_fecha(directorio_preprocesado, fecha_trabajo),
            "target",
        )
        ruta_archivo = os.path.join(
            ruta_fecha,
            f"mpv_{posicion_mpv:02d}",
            "preprocessed_co2ch4co_target_inj_picarroaux.csv",
        )
        if os.path.isfile(ruta_archivo):
            archivos.append(ruta_archivo)

    return archivos


def crear_segmento(gas, posicion_mpv, epoch):
    """
    Crea la representación mediante lista de un segmento target nuevo.

    La lista conserva gas, posición, límites y valores estables.
    """
    return [
        gas,
        posicion_mpv,
        epoch,
        epoch,
        None,
        None,
        [],
    ]


def obtener_columnas_target_gas(gas):
    """
    Devuelve la columna de concentración y el factor de conversión a ppm.
    """
    if gas == "CO2":
        return "co2_raw_ppm", 1.0
    if gas == "CH4":
        return "ch4_raw_ppb", 0.001
    if gas == "CO":
        return "co_raw_ppb", 0.001

    raise ValueError(f"Gas no compatible con la salida normalizada: {gas}")


def leer_archivo_target(
        ruta_archivo,
        gas,
        posicion_mpv,
        minutos_estabilizacion,
        segundos_maximos_entre_medidas,
        segmento_actual,
        segmentos_completos,
):
    """
    Incorpora un CSV target a una secuencia de segmentos continuos.

    Devuelve el segmento que permanece abierto al finalizar el archivo.
    """
    with open(ruta_archivo, "r", encoding="utf-8", newline="") as archivo:
        lector = csv.reader(archivo, delimiter=";")
        cabecera = next(lector, None)
        if not cabecera:
            return segmento_actual

        columna_gas, factor_a_ppm = (
            obtener_columnas_target_gas(gas)
        )
        indice_fecha_decimal = cabecera.index("decimal_date")
        indice_gas = cabecera.index(columna_gas)
        indice_processing_flag = obtener_indice_processing_flag(cabecera, gas)

        for fila in lector:
            if len(fila) != len(cabecera):
                continue

            epoch = convertir_fecha_decimal_a_epoch(
                fila[indice_fecha_decimal]
            )
            if epoch is None:
                continue

            inicia_segmento = segmento_actual is None
            if segmento_actual is not None:
                salto = epoch - segmento_actual[3]
                inicia_segmento = salto > segundos_maximos_entre_medidas

            if inicia_segmento:
                if segmento_actual is not None:
                    segmentos_completos.append(segmento_actual)
                segmento_actual = crear_segmento(gas, posicion_mpv, epoch)

            if segmento_actual is None:
                continue

            segmento_actual[3] = epoch
            epoch_estable = (
                    segmento_actual[2] + minutos_estabilizacion * 60
            )
            if epoch < epoch_estable:
                continue

            if not interpretar_booleano(fila[indice_processing_flag]):
                continue

            concentracion = convertir_float(fila[indice_gas])
            if concentracion is None:
                continue

            if segmento_actual[4] is None:
                segmento_actual[4] = epoch
            segmento_actual[5] = epoch
            segmento_actual[6].append(concentracion * factor_a_ppm)

    return segmento_actual


def detectar_segmentos_target(
        fecha_inicio,
        fecha_fin,
        directorio_preprocesado,
        posiciones_target,
        gases,
        minutos_estabilizacion,
        segundos_maximos_entre_medidas,
):
    """
    Detecta segmentos target continuos para todas las posiciones y gases.

    La continuidad se mantiene entre archivos diarios cuando el salto temporal
    no supera el umbral. Devuelve una lista de segmentos.
    """
    segmentos = []

    for posicion_mpv in posiciones_target:
        for gas in gases:
            archivos = obtener_archivos_target(
                fecha_inicio,
                fecha_fin,
                directorio_preprocesado,
                posicion_mpv,
            )
            segmento_actual = None

            for ruta_archivo in archivos:
                segmento_actual = leer_archivo_target(
                    ruta_archivo,
                    gas,
                    posicion_mpv,
                    minutos_estabilizacion,
                    segundos_maximos_entre_medidas,
                    segmento_actual,
                    segmentos,
                )

            if segmento_actual is not None:
                segmentos.append(segmento_actual)

    return segmentos


# ==========================================================
# CÁLCULO DE ESTADÍSTICOS DE CADA INYECCIÓN
# ==========================================================


def crear_identificador_inyeccion(epoch_inicio, posicion_mpv):
    """
    Crea un identificador reproducible a partir del inicio y la posición.
    """
    milisegundos = int(round(epoch_inicio * 1000))
    return f"inyeccion_{milisegundos}_mpv_{posicion_mpv:02d}"


def resumir_segmento(segmento, minimo_observaciones):
    """
    Calcula media y desviación de un segmento target estabilizado.

    Devuelve un registro interno listo para agruparlo con los demás gases.
    """
    gas = segmento[0]
    posicion_mpv = segmento[1]
    inicio_epoch = segmento[2]
    fin_epoch = segmento[3]
    valores = segmento[6]
    identificador = crear_identificador_inyeccion(
        inicio_epoch,
        posicion_mpv,
    )
    if len(valores) >= minimo_observaciones:
        vector = np.asarray(valores, dtype=float)
        media = float(np.mean(vector))
        desviacion = float(np.std(vector))
    else:
        media = ""
        desviacion = ""

    return [
        identificador,
        posicion_mpv,
        inicio_epoch,
        fin_epoch,
        gas,
        media,
        desviacion,
    ]


def buscar_inyeccion_resumida(inyecciones, identificador):
    """
    Busca una inyección agrupada mediante su identificador interno.
    """
    for inyeccion in inyecciones:
        if inyeccion[0] == identificador:
            return inyeccion
    return None


def agrupar_resumenes_inyecciones(segmentos, minimo_observaciones):
    """
    Agrupa en una sola inyección los estadísticos de todos los gases.
    """
    inyecciones = []

    for segmento in segmentos:
        resumen = resumir_segmento(segmento, minimo_observaciones)
        inyeccion = buscar_inyeccion_resumida(inyecciones, resumen[0])

        if inyeccion is None:
            inyeccion = [
                resumen[0],
                resumen[1],
                resumen[2],
                resumen[3],
                [],
            ]
            inyecciones.append(inyeccion)

        inyeccion[2] = min(inyeccion[2], resumen[2])
        inyeccion[3] = max(inyeccion[3], resumen[3])
        inyeccion[4].append([resumen[4], resumen[5], resumen[6]])

    inyecciones.sort(key=lambda registro: (registro[2], registro[1]))
    return inyecciones


def buscar_estadistico_gas(inyeccion, gas):
    """
    Obtiene media y desviación de un gas dentro de una inyección.
    """
    for estadistico in inyeccion[4]:
        if estadistico[0] == gas:
            return estadistico[1], estadistico[2]
    return "", ""


def formatear_estadistico_inyeccion(valor, gas):
    """
    Expresa CO2 en ppm y CH4 y CO en ppb.
    """
    numero = convertir_float(valor)
    if numero is None:
        return ""
    if gas in ("CH4", "CO"):
        numero *= 1000
    return f"{numero:.12g}"


def construir_fila_inyeccion(inyeccion, gases):
    """
    Construye la fila pública de una inyección con los tres gases.
    """
    inicio_epoch = inyeccion[2]
    fin_epoch = inyeccion[3]
    instante = datetime.fromtimestamp(inicio_epoch, timezone.utc)
    valores = []

    for gas in gases:
        media, desviacion = buscar_estadistico_gas(inyeccion, gas)
        valores.append(
            [
                formatear_estadistico_inyeccion(media, gas),
                formatear_estadistico_inyeccion(desviacion, gas),
            ]
        )

    return [
        str(instante.year),
        str(instante.month),
        str(instante.day),
        str(instante.hour),
        str(instante.minute),
        f"{convertir_epoch_a_fecha_decimal(inicio_epoch):.12f}",
        f"{convertir_epoch_a_fecha_decimal(fin_epoch):.12f}",
        str(inyeccion[1]),
        valores[gases.index("CO2")][0],
        valores[gases.index("CO2")][1],
        valores[gases.index("CH4")][0],
        valores[gases.index("CH4")][1],
        valores[gases.index("CO")][0],
        valores[gases.index("CO")][1],
    ]


def crear_cabecera_inyecciones():
    """
    Devuelve la cabecera estable del resumen de inyecciones.
    """
    return [
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "decimal_date",
        "end_decimal_date",
        "mpv",
        "co2_raw_ppm",
        "co2_std_ppm",
        "ch4_raw_ppb",
        "ch4_std_ppb",
        "co_raw_ppb",
        "co_std_ppb",
    ]


# ==========================================================
# ESCRITURA INCREMENTAL DE RESÚMENES DIARIOS
# ==========================================================


def obtener_fecha_fila_inyeccion(fila):
    """
    Obtiene la fecha UTC de una fila de resumen mediante su fecha decimal.
    """
    epoch = convertir_fecha_decimal_a_epoch(fila[5])
    if epoch is None:
        raise ValueError("Fecha decimal no válida en el resumen de inyección.")
    return datetime.fromtimestamp(epoch, timezone.utc).date()


def procesar_inyecciones_periodo(
        fecha_inicio,
        fecha_fin,
        directorio_preprocesado,
        directorio_inyecciones,
        posiciones_target_configuradas,
        gases,
        minutos_estabilizacion,
        segundos_maximos_entre_medidas,
        minimo_observaciones,
):
    """
    Resume todas las inyecciones target del periodo en archivos diarios.

    Crea el directorio de resultados justo antes de la etapa. Un archivo diario
    ya existente se considera procesado y se omite sin sobrescribir.
    Devuelve True si todas las escrituras terminan correctamente.
    """
    if not crear_directorio(directorio_inyecciones):
        return False

    posiciones_detectadas = obtener_posiciones_target(
        fecha_inicio,
        fecha_fin,
        directorio_preprocesado,
    )
    posiciones_target = []

    for posicion in posiciones_target_configuradas:
        if posicion in posiciones_detectadas:
            posiciones_target.append(posicion)

    for posicion in posiciones_detectadas:
        if posicion not in posiciones_target:
            posiciones_target.append(posicion)

    segmentos = detectar_segmentos_target(
        fecha_inicio,
        fecha_fin,
        directorio_preprocesado,
        posiciones_target,
        gases,
        minutos_estabilizacion,
        segundos_maximos_entre_medidas,
    )
    inyecciones_resumidas = agrupar_resumenes_inyecciones(
        segmentos,
        minimo_observaciones,
    )
    filas_resumen = []
    for inyeccion in inyecciones_resumidas:
        filas_resumen.append(construir_fila_inyeccion(inyeccion, gases))
    resultado_correcto = True

    for fecha_trabajo in obtener_fechas_periodo(fecha_inicio, fecha_fin):
        ruta_preprocesado = construir_ruta_fecha(
            directorio_preprocesado,
            fecha_trabajo,
        )
        if not os.path.isdir(ruta_preprocesado):
            print(
                f"No se resumen inyecciones del {fecha_trabajo:%Y-%m-%d} "
                "porque su preprocesado todavía no está publicado."
            )
            continue

        ruta_fecha = construir_ruta_fecha(
            directorio_inyecciones,
            fecha_trabajo,
        )
        ruta_salida = os.path.join(ruta_fecha, "inyecciones.csv")

        if os.path.exists(ruta_salida):
            print(
                f"Inyecciones del {fecha_trabajo:%Y-%m-%d} ya procesadas. "
                "Se omiten sin sobrescribir."
            )
            continue

        filas_fecha = []
        for fila in filas_resumen:
            if obtener_fecha_fila_inyeccion(fila) == fecha_trabajo.date():
                filas_fecha.append(fila)

        if not escribir_csv_atomico(
                ruta_salida,
                crear_cabecera_inyecciones(),
                filas_fecha,
                ";",
        ):
            resultado_correcto = False
        else:
            print(
                f"Inyecciones resumidas para {fecha_trabajo:%Y-%m-%d}: "
                f"{len(filas_fecha)} registros."
            )

    return resultado_correcto
