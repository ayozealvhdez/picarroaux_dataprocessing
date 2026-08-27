"""
Copia y limpia directorios raw diarios.

Fecha de creación: 27/08/2026
Fecha de última modificación: 27/08/2026

Listado de cambios:

"""

import os
import shutil
from datetime import datetime

from funciones.comunes import construir_ruta_fecha, crear_directorio
from funciones.comunes import obtener_fechas_periodo


# ==========================================================
# LIMPIEZA DE COPIAS INCOMPLETAS
# ==========================================================


def borrar_copias_incompletas(directorio_destino: str) -> int:
    """
    Borra directorios terminados en '_en_progreso' tras una copia interrumpida.

    Devuelve el número de directorios eliminados.
    """
    if not os.path.exists(directorio_destino):
        return 0

    directorios_borrados = 0

    try:
        for ruta_actual, directorios, _ in os.walk(directorio_destino):
            for directorio in directorios[:]:
                if not directorio.endswith("_en_progreso"):
                    continue

                ruta_incompleta = os.path.join(ruta_actual, directorio)
                shutil.rmtree(ruta_incompleta)
                directorios.remove(directorio)
                print(f"Copia incompleta eliminada: {ruta_incompleta}")
                directorios_borrados += 1
    except OSError as e:
        print(f"Error al limpiar copias incompletas: {e}")

    return directorios_borrados


# ==========================================================
# COPIA INCREMENTAL DE DIRECTORIOS DIARIOS
# ==========================================================


def copiar_datos_picarro(
        fecha_inicio: datetime,
        fecha_fin: datetime,
        directorio_origen: str,
        directorio_destino: str,
) -> bool:
    """
    Copia los directorios diarios comprendidos en el periodo, ambas fechas
    inclusive.

    Crea el directorio de destino justo antes de copiar. Cada día se publica
    después de completar una copia temporal. Los días que ya existen en el
    destino se omiten y nunca se recorren ni se sobrescriben.

    Devuelve True si existe al menos un día local utilizable y False si no se
    encuentra ninguno o no se puede preparar el destino.
    """
    if not crear_directorio(directorio_destino):
        return False

    borrar_copias_incompletas(directorio_destino)

    if not os.path.exists(directorio_origen):
        print(f"No se puede acceder al origen: {directorio_origen}")
        print("Se continuará con los datos raw que ya estén disponibles.")
        return comprobar_datos_locales(
            fecha_inicio,
            fecha_fin,
            directorio_destino,
        )

    directorios_copiados = 0
    directorios_existentes = 0
    errores_copia = 0

    for fecha_trabajo in obtener_fechas_periodo(fecha_inicio, fecha_fin):
        ruta_origen = construir_ruta_fecha(directorio_origen, fecha_trabajo)
        ruta_destino = construir_ruta_fecha(directorio_destino, fecha_trabajo)
        ruta_temporal = ruta_destino + "_en_progreso"

        if os.path.exists(ruta_destino):
            print(
                f"Datos raw del {fecha_trabajo:%Y-%m-%d} ya existentes. "
                "Se omiten sin sobrescribir."
            )
            directorios_existentes += 1
            continue

        if not os.path.exists(ruta_origen):
            print(f"No se encontró el directorio de origen: {ruta_origen}")
            continue

        try:
            print(f"Copiando datos raw del {fecha_trabajo:%Y-%m-%d}...")
            shutil.copytree(ruta_origen, ruta_temporal)
            os.rename(ruta_temporal, ruta_destino)
            directorios_copiados += 1
        except OSError as e:
            print(f"Error al copiar {ruta_origen}: {e}")
            errores_copia += 1

    print(f"Directorios diarios copiados: {directorios_copiados}")
    print(f"Directorios diarios omitidos por existir: {directorios_existentes}")
    print(f"Errores de copia: {errores_copia}")

    return directorios_copiados > 0 or directorios_existentes > 0


def comprobar_datos_locales(
        fecha_inicio: datetime,
        fecha_fin: datetime,
        directorio_raw: str,
) -> bool:
    """
    Comprueba si hay al menos un directorio diario local dentro del periodo.

    Devuelve True cuando encuentra datos y False en caso contrario.
    """
    for fecha_trabajo in obtener_fechas_periodo(fecha_inicio, fecha_fin):
        ruta_fecha = construir_ruta_fecha(directorio_raw, fecha_trabajo)
        if os.path.isdir(ruta_fecha):
            return True

    return False


# ==========================================================
# LIMPIEZA DE DATOS FUERA DEL PERIODO
# ==========================================================


def borrar_datos_fuera_periodo(
        fecha_inicio: datetime,
        fecha_fin: datetime,
        directorio_base: str,
) -> int:
    """
    Borra directorios YYYY/MM/DD anteriores o posteriores al periodo.

    Solo actúa sobre carpetas numéricas de tres niveles. Los directorios de
    plantilla, como YYYY/MM/DD, se ignoran. Devuelve el número de días borrados.
    """
    if not os.path.exists(directorio_base):
        return 0

    directorios_borrados = 0

    try:
        for anho in os.listdir(directorio_base):
            ruta_anho = os.path.join(directorio_base, anho)
            if not os.path.isdir(ruta_anho) or not anho.isdigit():
                continue

            for mes in os.listdir(ruta_anho):
                ruta_mes = os.path.join(ruta_anho, mes)
                if not os.path.isdir(ruta_mes) or not mes.isdigit():
                    continue

                for dia in os.listdir(ruta_mes):
                    ruta_dia = os.path.join(ruta_mes, dia)
                    if not os.path.isdir(ruta_dia) or not dia.isdigit():
                        continue

                    try:
                        fecha_directorio = datetime.strptime(
                            f"{anho}-{mes}-{dia}",
                            "%Y-%m-%d",
                        )
                    except ValueError:
                        continue

                    fuera_periodo = (
                            fecha_directorio.date() < fecha_inicio.date()
                            or fecha_directorio.date() > fecha_fin.date()
                    )
                    if fuera_periodo:
                        shutil.rmtree(ruta_dia)
                        print(f"Día temporal fuera del periodo eliminado: {ruta_dia}")
                        directorios_borrados += 1

                if os.path.isdir(ruta_mes) and not os.listdir(ruta_mes):
                    os.rmdir(ruta_mes)

            if os.path.isdir(ruta_anho) and not os.listdir(ruta_anho):
                os.rmdir(ruta_anho)
    except OSError as e:
        print(f"Error al limpiar datos temporales fuera del periodo: {e}")

    return directorios_borrados
