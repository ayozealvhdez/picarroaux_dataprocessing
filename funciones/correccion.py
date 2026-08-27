"""
Funciones de aplicación de calibraciones lineales al ambiente.

Fecha de creación: 27/08/2026
Fecha de última modificación: 27/08/2026

Listado de cambios:

"""

import csv
import os

from funciones.comunes import abrir_csv_temporal, construir_ruta_fecha
from funciones.comunes import convertir_fecha_decimal_a_epoch
from funciones.comunes import convertir_float, crear_directorio
from funciones.comunes import formatear_epoch_utc
from funciones.comunes import interpretar_booleano, obtener_fechas_periodo
from funciones.comunes import obtener_indice_processing_flag
from funciones.comunes import publicar_csv_temporal


# ==========================================================
# LECTURA DEL HISTÓRICO DE CALIBRACIONES LINEALES
# ==========================================================


def obtener_archivos_calibraciones(directorio_calibraciones):
    """
    Localiza los históricos diarios de calibraciones lineales.

    Devuelve una lista de rutas ordenadas cronológicamente.
    """
    archivos = []

    if not os.path.isdir(directorio_calibraciones):
        return archivos

    for ruta_actual, _, nombres in os.walk(directorio_calibraciones):
        for nombre in nombres:
            if nombre == "calibraciones_lineales.csv":
                archivos.append(os.path.join(ruta_actual, nombre))

    archivos.sort()
    return archivos


def existe_calibracion(calibraciones, epoch, gas):
    """
    Comprueba si una calibración y un gas ya están en el histórico leído.
    """
    for calibracion in calibraciones:
        if calibracion[0] == epoch and calibracion[1] == gas:
            return True
    return False


def leer_historico_calibraciones(directorio_calibraciones):
    """
    Lee todas las calibraciones lineales válidas disponibles.

    Cada registro conserva fecha, gas, pendiente y ordenada. Devuelve la lista
    ordenada por gas e instante de disponibilidad.
    """
    calibraciones = []

    for ruta_archivo in obtener_archivos_calibraciones(
            directorio_calibraciones
    ):
        try:
            with open(
                    ruta_archivo,
                    "r",
                    encoding="utf-8",
                    newline="",
            ) as archivo:
                lector = csv.reader(archivo, delimiter=";")
                cabecera = next(lector, None)
                if not cabecera or "decimal_date" not in cabecera:
                    continue

                indice_fecha_decimal = cabecera.index("decimal_date")

                for fila in lector:
                    if len(fila) != len(cabecera):
                        continue

                    epoch = convertir_fecha_decimal_a_epoch(
                        fila[indice_fecha_decimal]
                    )
                    if epoch is None:
                        continue

                    for gas in ("CO2", "CH4", "CO"):
                        nombre_gas = gas.lower()
                        pendiente = convertir_float(
                            fila[cabecera.index(f"{nombre_gas}_slope")]
                        )
                        ordenada = convertir_float(
                            fila[
                                cabecera.index(
                                    f"{nombre_gas}_intercept_ppm"
                                )
                            ]
                        )
                        if pendiente is None or ordenada is None:
                            continue
                        if existe_calibracion(calibraciones, epoch, gas):
                            continue

                        calibraciones.append(
                            [
                                epoch,
                                gas,
                                pendiente,
                                ordenada,
                                formatear_epoch_utc(epoch),
                            ]
                        )
        except (OSError, ValueError, csv.Error) as e:
            print(f"Error al leer calibraciones de {ruta_archivo}: {e}")

    calibraciones.sort(key=lambda registro: (registro[1], registro[0]))
    return calibraciones


def filtrar_calibraciones_gas(calibraciones, gas):
    """
    Selecciona y ordena las calibraciones correspondientes a un gas.
    """
    seleccion = []

    for calibracion in calibraciones:
        if calibracion[1] == gas:
            seleccion.append(calibracion)

    seleccion.sort(key=lambda fila: fila[0])
    return seleccion


# ==========================================================
# APLICACIÓN INCREMENTAL A UN ARCHIVO AMBIENTAL
# ==========================================================


def crear_cabecera_ambiente_calibrado():
    """
    Devuelve la cabecera normalizada del archivo ambiental corregido.
    """
    return [
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "decimal_date",
        "mpv",
        "co2_raw_ppm",
        "co2_corr_ppm",
        "processing_flag_co2",
        "ch4_raw_ppb",
        "ch4_corr_ppb",
        "processing_flag_ch4",
        "co_raw_ppb",
        "co_corr_ppb",
        "processing_flag_co",
        "calib_date",
    ]


def obtener_columnas_ambiente_gas(gas):
    """
    Devuelve la columna de concentración y los factores entre salida y ppm.
    """
    if gas == "CO2":
        return "co2_raw_ppm", 1.0, 1.0
    if gas == "CH4":
        return "ch4_raw_ppb", 0.001, 1000.0
    if gas == "CO":
        return "co_raw_ppb", 0.001, 1000.0

    raise ValueError(f"Gas no compatible con la salida normalizada: {gas}")


def calibrar_archivo_ambiente(
        ruta_origen,
        ruta_destino,
        gases,
        calibraciones,
):
    """
    Calibra un CSV ambiental con la recta más reciente previa a cada medida.

    Aplica concentración_calibrada = pendiente * medida + ordenada_origen.
    El resultado se publica de forma atómica y no se sobrescribe si ya existe.
    """
    if os.path.exists(ruta_destino):
        print(f"Ambiente procesado ya existente. Se omite: {ruta_destino}")
        return True

    archivo_salida = None
    ruta_temporal = None

    try:
        with open(
                ruta_origen,
                "r",
                encoding="utf-8",
                newline="",
        ) as archivo_origen:
            lector = csv.reader(archivo_origen, delimiter=";")
            cabecera = next(lector, None)
            if not cabecera:
                print(f"Archivo ambiental vacío: {ruta_origen}")
                return False

            indice_fecha_decimal = cabecera.index("decimal_date")
            indices_gases = []
            indices_processing_flags = []
            factores_a_ppm = []
            factores_desde_ppm = []
            calibraciones_por_gas = []

            for gas in gases:
                columna_gas, factor_a_ppm, factor_salida = (
                    obtener_columnas_ambiente_gas(gas)
                )
                indices_gases.append(cabecera.index(columna_gas))
                indices_processing_flags.append(
                    obtener_indice_processing_flag(cabecera, gas)
                )
                factores_a_ppm.append(factor_a_ppm)
                factores_desde_ppm.append(factor_salida)
                calibraciones_por_gas.append(
                    filtrar_calibraciones_gas(calibraciones, gas)
                )

            archivo_salida, escritor, ruta_temporal = abrir_csv_temporal(
                ruta_destino,
                crear_cabecera_ambiente_calibrado(),
                ";",
            )
            if archivo_salida is None:
                return True

            indices_calibraciones_vigentes = []
            for _ in gases:
                indices_calibraciones_vigentes.append(-1)

            for fila in lector:
                if len(fila) != len(cabecera):
                    continue

                epoch = convertir_fecha_decimal_a_epoch(
                    fila[indice_fecha_decimal]
                )
                valores_corregidos = []
                calibraciones_aplicadas = []

                for indice_gas, _ in enumerate(gases):
                    calibraciones_gas = calibraciones_por_gas[indice_gas]
                    indice_vigente = indices_calibraciones_vigentes[
                        indice_gas
                    ]
                    concentracion = convertir_float(
                        fila[indices_gases[indice_gas]]
                    )

                    if epoch is not None:
                        siguiente = indice_vigente + 1
                        while (
                                siguiente < len(calibraciones_gas)
                                and calibraciones_gas[siguiente][0] <= epoch
                        ):
                            indice_vigente = siguiente
                            siguiente += 1

                    indices_calibraciones_vigentes[indice_gas] = (
                        indice_vigente
                    )
                    processing_flag = interpretar_booleano(
                        fila[indices_processing_flags[indice_gas]]
                    )

                    if not processing_flag or concentracion is None:
                        valores_corregidos.append("")
                    elif indice_vigente < 0:
                        valores_corregidos.append("")
                    else:
                        calibracion = calibraciones_gas[indice_vigente]
                        concentracion_calibrada = (
                                calibracion[2]
                                * concentracion
                                * factores_a_ppm[indice_gas]
                                + calibracion[3]
                        )
                        valores_corregidos.append(
                            f"{concentracion_calibrada * factores_desde_ppm[indice_gas]:.12g}"
                        )
                        calibraciones_aplicadas.append(calibracion)

                fecha_calibracion = ""
                if calibraciones_aplicadas:
                    calibracion_reciente = max(
                        calibraciones_aplicadas,
                        key=lambda registro: registro[0],
                    )
                    fecha_calibracion = calibracion_reciente[4]

                escritor.writerow(
                    [
                        fila[cabecera.index("year")],
                        fila[cabecera.index("month")],
                        fila[cabecera.index("day")],
                        fila[cabecera.index("hour")],
                        fila[cabecera.index("minute")],
                        fila[indice_fecha_decimal],
                        fila[cabecera.index("mpv")],
                        fila[cabecera.index("co2_raw_ppm")],
                        valores_corregidos[gases.index("CO2")],
                        fila[obtener_indice_processing_flag(cabecera, "CO2")],
                        fila[cabecera.index("ch4_raw_ppb")],
                        valores_corregidos[gases.index("CH4")],
                        fila[obtener_indice_processing_flag(cabecera, "CH4")],
                        fila[cabecera.index("co_raw_ppb")],
                        valores_corregidos[gases.index("CO")],
                        fila[obtener_indice_processing_flag(cabecera, "CO")],
                        fecha_calibracion,
                    ]
                )

        publicar_csv_temporal(
            archivo_salida,
            ruta_temporal,
            ruta_destino,
        )
        return True
    except (OSError, ValueError, csv.Error) as e:
        if archivo_salida is not None:
            archivo_salida.close()
        print(f"Error al calibrar el ambiente de {ruta_origen}: {e}")
        return False


# ==========================================================
# EJECUCIÓN DE LA CALIBRACIÓN PARA TODO EL PERIODO
# ==========================================================


def calibrar_ambiente_periodo(
        fecha_inicio,
        fecha_fin,
        directorio_preprocesado,
        directorio_calibraciones,
        directorio_ambiente_procesado,
        gases,
):
    """
    Calibra los CSV ambientales disponibles para todo el periodo solicitado.

    Cada archivo ya procesado se omite sin sobrescribir. Devuelve True si no
    se producen errores durante la etapa.
    """
    if not crear_directorio(directorio_ambiente_procesado):
        return False

    calibraciones = leer_historico_calibraciones(
        directorio_calibraciones
    )
    resultado_correcto = True
    for fecha_trabajo in obtener_fechas_periodo(fecha_inicio, fecha_fin):
        ruta_origen = os.path.join(
            construir_ruta_fecha(
                directorio_preprocesado,
                fecha_trabajo,
            ),
            "ambient",
            "preprocessed_co2ch4co_picarroaux.csv",
        )
        if not os.path.exists(ruta_origen):
            print(
                f"Ambiente del {fecha_trabajo:%Y-%m-%d} no disponible. "
                "Se omite porque falta su preprocesado."
            )
            continue

        ruta_destino = os.path.join(
            construir_ruta_fecha(
                directorio_ambiente_procesado,
                fecha_trabajo,
            ),
            "processed_co2ch4co_picarroaux.csv",
        )
        if os.path.exists(ruta_destino):
            print(
                f"Ambiente del {fecha_trabajo:%Y-%m-%d} ya procesado. "
                "Se omite sin sobrescribir."
            )
            continue

        print(f"Calibrando ambiente del {fecha_trabajo:%Y-%m-%d}...")
        if calibrar_archivo_ambiente(
                ruta_origen,
                ruta_destino,
                gases,
                calibraciones,
        ):
            print(
                f"Ambiente calibrado para "
                f"{fecha_trabajo:%Y-%m-%d}."
            )
        else:
            resultado_correcto = False

    return resultado_correcto
