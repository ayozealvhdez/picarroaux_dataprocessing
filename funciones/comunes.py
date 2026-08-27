"""
Funciones comunes de rutas, conversiones y escritura atómica.

Fecha de creación: 27/08/2026
Fecha de última modificación: 27/08/2026

Listado de cambios:

"""

import csv
import math
import os
from datetime import datetime, timedelta, timezone


# ==========================================================
# GESTIÓN DE DIRECTORIOS Y FECHAS
# ==========================================================


def crear_directorio(directorio: str) -> bool:
    """
    Crea un directorio cuando todavía no existe.

    Devuelve True si el directorio queda disponible y False si falla la
    operación.
    """
    try:
        os.makedirs(directorio, exist_ok=True)
        return True
    except OSError as e:
        print(f"Error al crear el directorio {directorio}: {e}")
        return False


def obtener_fechas_periodo(
        fecha_inicio: datetime,
        fecha_fin: datetime,
) -> list[datetime]:
    """
    Construye la lista de fechas comprendidas entre dos límites inclusivos.

    Devuelve una lista ordenada de objetos datetime a medianoche.
    """
    fechas = []
    fecha_actual = fecha_inicio

    while fecha_actual.date() <= fecha_fin.date():
        fechas.append(fecha_actual)
        fecha_actual += timedelta(days=1)

    return fechas


def construir_ruta_fecha(
        directorio_base: str,
        fecha_trabajo: datetime,
) -> str:
    """
    Construye una ruta diaria con la estructura YYYY/MM/DD.

    Devuelve la ruta resultante.
    """
    return os.path.join(
        directorio_base,
        fecha_trabajo.strftime("%Y"),
        fecha_trabajo.strftime("%m"),
        fecha_trabajo.strftime("%d"),
    )


def formatear_epoch_utc(epoch: float) -> str:
    """
    Convierte un instante Unix a texto ISO 8601 en UTC.

    Devuelve una cadena terminada en Z.
    """
    instante = datetime.fromtimestamp(float(epoch), timezone.utc)
    return instante.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def convertir_epoch_a_fecha_decimal(epoch):
    """
    Convierte un instante Unix UTC en su año decimal.
    """
    instante = datetime.fromtimestamp(float(epoch), timezone.utc)
    inicio_anho = datetime(instante.year, 1, 1, tzinfo=timezone.utc)
    fin_anho = datetime(instante.year + 1, 1, 1, tzinfo=timezone.utc)
    duracion_anho = fin_anho.timestamp() - inicio_anho.timestamp()

    return instante.year + (
        (instante.timestamp() - inicio_anho.timestamp()) / duracion_anho
    )


def convertir_fecha_decimal_a_epoch(fecha_decimal):
    """
    Convierte un año decimal en un instante Unix UTC.

    Devuelve None si el valor no es finito o su fracción queda fuera del año.
    """
    valor = convertir_float(fecha_decimal)
    if valor is None:
        return None

    anho = int(math.floor(valor))
    fraccion = valor - anho
    if anho < 1 or fraccion < 0 or fraccion >= 1:
        return None

    try:
        inicio_anho = datetime(anho, 1, 1, tzinfo=timezone.utc)
        fin_anho = datetime(anho + 1, 1, 1, tzinfo=timezone.utc)
    except ValueError:
        return None

    duracion_anho = fin_anho.timestamp() - inicio_anho.timestamp()
    return inicio_anho.timestamp() + fraccion * duracion_anho


# ==========================================================
# CONVERSIÓN DE VALORES
# ==========================================================


def convertir_float(valor):
    """
    Convierte un valor a float y rechaza infinitos y valores NaN.

    Devuelve el número convertido o None cuando no es válido.
    """
    try:
        numero = float(valor)
        if not math.isfinite(numero):
            return None
        return numero
    except (TypeError, ValueError):
        return None


def interpretar_booleano(valor):
    """
    Interpreta las representaciones habituales de un valor booleano.

    Devuelve True únicamente para valores afirmativos reconocidos.
    """
    return str(valor).strip().lower() in ("true", "1", "sí", "si")


def obtener_indice_processing_flag(cabecera, gas):
    """
    Localiza la bandera de procesado de un gas en una cabecera CSV.

    Prioriza el nombre normalizado ``processing_flag_<gas>`` y acepta el
    antiguo ``sig<gas>`` únicamente para poder leer resultados ya generados.
    """
    nombre_gas = gas.lower()
    nombre_actual = f"processing_flag_{nombre_gas}"
    if nombre_actual in cabecera:
        return cabecera.index(nombre_actual)

    nombre_anterior = f"sig{nombre_gas}"
    if nombre_anterior in cabecera:
        return cabecera.index(nombre_anterior)

    raise ValueError(
        f"Falta la columna obligatoria {nombre_actual} en el CSV."
    )


# ==========================================================
# ESCRITURA ATÓMICA DE CSV
# ==========================================================


def abrir_csv_temporal(ruta_final, cabecera, delimitador=","):
    """
    Abre un CSV temporal junto a su destino y escribe la cabecera.

    Si el archivo final ya existe, no lo sobrescribe y devuelve tres valores
    None. En caso contrario devuelve archivo, escritor y ruta temporal.
    """
    if os.path.exists(ruta_final):
        return None, None, None

    directorio = os.path.dirname(ruta_final)
    if not crear_directorio(directorio):
        raise OSError(f"No se pudo preparar el directorio {directorio}")

    ruta_temporal = ruta_final + "_en_progreso"
    if os.path.exists(ruta_temporal):
        os.remove(ruta_temporal)

    archivo = open(
        ruta_temporal,
        "w",
        encoding="utf-8",
        newline="",
    )
    escritor = csv.writer(archivo, delimiter=delimitador)
    escritor.writerow(cabecera)

    return archivo, escritor, ruta_temporal


def publicar_csv_temporal(archivo, ruta_temporal, ruta_final):
    """
    Cierra y publica un CSV temporal sin reemplazar un resultado existente.

    Devuelve True si se publica y False si otro resultado ya estaba presente.
    """
    archivo.close()

    if os.path.exists(ruta_final):
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)
        return False

    os.rename(ruta_temporal, ruta_final)
    return True


def escribir_csv_atomico(ruta_final, cabecera, filas, delimitador=","):
    """
    Escribe una colección pequeña de filas mediante un archivo temporal.

    No sobrescribe resultados existentes. Devuelve True si publica el archivo
    o si este ya existía, y False si ocurre un error.
    """
    if os.path.exists(ruta_final):
        print(f"Resultado ya existente. Se omite: {ruta_final}")
        return True

    archivo = None

    try:
        archivo, escritor, ruta_temporal = abrir_csv_temporal(
            ruta_final,
            cabecera,
            delimitador,
        )
        if archivo is None:
            return True

        escritor.writerows(filas)
        publicar_csv_temporal(archivo, ruta_temporal, ruta_final)
        return True
    except (OSError, csv.Error) as e:
        if archivo is not None:
            archivo.close()
        print(f"Error al escribir el archivo {ruta_final}: {e}")
        return False
