"""
Funciones de preprocesado diario de datos raw.

Fecha de creación: 27/08/2026
Fecha de última modificación: 27/08/2026

Listado de cambios:

"""

import os
import shutil
from datetime import datetime, timezone

from funciones.comunes import abrir_csv_temporal, construir_ruta_fecha
from funciones.comunes import convertir_epoch_a_fecha_decimal
from funciones.comunes import convertir_float, crear_directorio
from funciones.comunes import obtener_fechas_periodo
from funciones.comunes import publicar_csv_temporal

# ==========================================================
# DEFINICIÓN DE COLUMNAS DE SALIDA
# ==========================================================

COLUMNAS_AUXILIARES = (
    "ALARM_STATUS",
)


def crear_cabecera_medidas():
    """
    Devuelve la cabecera normalizada del archivo preprocesado.
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
        "processing_flag_co2",
        "ch4_raw_ppb",
        "processing_flag_ch4",
        "co_raw_ppb",
        "processing_flag_co",
    ]


def obtener_indices_columnas(cabecera, columnas, obligatorias):
    """
    Localiza columnas por nombre sin construir diccionarios auxiliares.

    Devuelve una lista de índices. Para columnas opcionales ausentes usa -1;
    para una columna obligatoria ausente genera ValueError.
    """
    indices = []

    for columna in columnas:
        try:
            indices.append(cabecera.index(columna))
        except ValueError:
            if obligatorias:
                raise ValueError(
                    f"Falta la columna obligatoria {columna} en el raw."
                )
            indices.append(-1)

    return indices


def obtener_valor_opcional(fila, indice):
    """
    Obtiene un valor mediante su índice o devuelve texto vacío si no existe.
    """
    if indice < 0 or indice >= len(fila):
        return ""
    return fila[indice]


# ==========================================================
# GESTIÓN INCREMENTAL DE ARCHIVOS CSV
# ==========================================================


def borrar_preprocesados_incompletos(directorio_preprocesado):
    """
    Elimina directorios diarios temporales e indicadores de estado obsoletos.

    Los directorios con sufijo '_en_progreso' nunca se consideran resultados
    válidos. Devuelve el número de directorios eliminados.
    """
    if not os.path.isdir(directorio_preprocesado):
        return 0

    directorios_borrados = 0
    ruta_estado = os.path.join(directorio_preprocesado, "_estado")

    try:
        if os.path.isdir(ruta_estado):
            shutil.rmtree(ruta_estado)
            print(f"Directorio de estado obsoleto eliminado: {ruta_estado}")
            directorios_borrados += 1

        for ruta_actual, directorios, _ in os.walk(
                directorio_preprocesado,
                topdown=True,
        ):
            for directorio in directorios[:]:
                if not directorio.endswith("_en_progreso"):
                    continue

                ruta_incompleta = os.path.join(ruta_actual, directorio)
                shutil.rmtree(ruta_incompleta)
                directorios.remove(directorio)
                print(
                    f"Preprocesado incompleto eliminado: {ruta_incompleta}"
                )
                directorios_borrados += 1
    except OSError as e:
        print(f"Error al limpiar preprocesados incompletos: {e}")

    return directorios_borrados


def construir_ruta_salida(
        directorio_fecha: str,
        tipo_muestra: str,
        posicion_mpv: int,
) -> str:
    """
    Construye la ruta del CSV diario para una muestra y una posición MPV.

    Los targets se particionan además por MPVPosition.
    """
    directorio_tipo = os.path.join(directorio_fecha, tipo_muestra)

    if tipo_muestra == "target":
        directorio_salida = os.path.join(
            directorio_tipo,
            f"mpv_{posicion_mpv:02d}",
        )
        nombre_archivo = "preprocessed_co2ch4co_target_inj_picarroaux.csv"
    else:
        directorio_salida = directorio_tipo
        nombre_archivo = "preprocessed_co2ch4co_picarroaux.csv"

    return os.path.join(
        directorio_salida,
        nombre_archivo,
    )


def buscar_salida(salidas, tipo_muestra, posicion_mpv):
    """
    Busca una salida abierta dentro de una lista de registros paralelos.

    Devuelve el registro encontrado o None.
    """
    for salida in salidas:
        coincide = (
                salida[0] == tipo_muestra
                and salida[1] == posicion_mpv
        )
        if coincide:
            return salida

    return None


def obtener_salida(
        salidas,
        directorio_fecha,
        tipo_muestra,
        posicion_mpv,
):
    """
    Recupera o abre la salida correspondiente a una medida.

    Si el CSV final ya existe, registra la salida como omitida y nunca lo
    sobrescribe. Devuelve una lista con los datos de control del archivo.
    """
    salida = buscar_salida(
        salidas,
        tipo_muestra,
        posicion_mpv,
    )
    if salida is not None:
        return salida

    ruta_final = construir_ruta_salida(
        directorio_fecha,
        tipo_muestra,
        posicion_mpv,
    )

    if os.path.exists(ruta_final):
        salida = [
            tipo_muestra,
            posicion_mpv,
            ruta_final,
            None,
            None,
            None,
        ]
        salidas.append(salida)
        return salida

    archivo, escritor, ruta_temporal = abrir_csv_temporal(
        ruta_final,
        crear_cabecera_medidas(),
        ";",
    )
    salida = [
        tipo_muestra,
        posicion_mpv,
        ruta_final,
        ruta_temporal,
        archivo,
        escritor,
    ]
    salidas.append(salida)
    return salida


def cerrar_salidas(salidas, publicar):
    """
    Cierra las salidas abiertas y, si procede, publica sus archivos temporales.

    Devuelve True si todas las publicaciones terminan correctamente.
    """
    resultado_correcto = True

    for salida in salidas:
        archivo = salida[4]
        if archivo is None:
            continue

        try:
            if publicar:
                publicar_csv_temporal(
                    archivo,
                    salida[3],
                    salida[2],
                )
            elif not archivo.closed:
                archivo.close()
        except OSError as e:
            if not archivo.closed:
                archivo.close()
            print(f"Error al cerrar la salida {salida[2]}: {e}")
            resultado_correcto = False

    return resultado_correcto


# ==========================================================
# LECTURA DIARIA DE DATOS RAW
# ==========================================================


def obtener_archivos_raw(directorio_fecha_raw: str) -> list[str]:
    """
    Localiza y ordena los archivos .dat de un directorio diario.

    Devuelve una lista de rutas completas.
    """
    archivos = []

    if not os.path.isdir(directorio_fecha_raw):
        return archivos

    for nombre in sorted(os.listdir(directorio_fecha_raw)):
        ruta = os.path.join(directorio_fecha_raw, nombre)
        if os.path.isfile(ruta) and nombre.lower().endswith(".dat"):
            archivos.append(ruta)

    return archivos


def construir_fila_salida(
        fila,
        indices_obligatorios,
        indices_auxiliares,
        indices_gases,
        gases,
        posicion_mpv,
):
    """
    Construye una fila normalizada y convierte CH4 y CO de ppm a ppb.

    Devuelve la fila resultante.
    """
    alarma = obtener_valor_opcional(fila, indices_auxiliares[0])
    alarma_valida = alarma in ("", "0", "0.0")
    epoch = convertir_float(fila[indices_obligatorios[0]])
    if epoch is None:
        return None

    instante = datetime.fromtimestamp(epoch, timezone.utc)
    concentraciones = []
    processing_flags = []

    for indice_gas, gas in enumerate(gases):
        concentracion = convertir_float(fila[indices_gases[indice_gas]])
        processing_flags.append(
            int(concentracion is not None and alarma_valida)
        )

        if concentracion is None:
            concentraciones.append("")
        elif gas in ("CH4", "CO"):
            concentraciones.append(f"{concentracion * 1000:.12g}")
        else:
            concentraciones.append(f"{concentracion:.12g}")

    return [
        str(instante.year),
        str(instante.month),
        str(instante.day),
        str(instante.hour),
        str(instante.minute),
        f"{convertir_epoch_a_fecha_decimal(epoch):.12f}",
        str(posicion_mpv),
        concentraciones[gases.index("CO2")],
        str(processing_flags[gases.index("CO2")]),
        concentraciones[gases.index("CH4")],
        str(processing_flags[gases.index("CH4")]),
        concentraciones[gases.index("CO")],
        str(processing_flags[gases.index("CO")]),
    ]


def preprocesar_archivo_raw(
        ruta_raw,
        directorio_fecha_salida,
        gases,
        posicion_ambiente,
        minutos_estabilizacion_ambiente,
        estado_valvula,
        salidas,
):
    """
    Lee un archivo raw y escribe sus medidas en las particiones necesarias.

    Ignora species y descarta la estabilización posterior a cada cambio a
    ambiente. Devuelve el número de filas de datos interpretadas.
    """
    filas_interpretadas = 0
    filas_descartadas = 0

    with open(ruta_raw, "r", encoding="ascii", errors="replace") as archivo:
        primera_linea = archivo.readline()
        if not primera_linea:
            return 0

        cabecera = primera_linea.split()
        columnas_obligatorias = ["EPOCH_TIME", "MPVPosition"]
        indices_obligatorios = obtener_indices_columnas(
            cabecera,
            columnas_obligatorias,
            True,
        )
        indices_gases = obtener_indices_columnas(cabecera, gases, True)
        indices_auxiliares = obtener_indices_columnas(
            cabecera,
            COLUMNAS_AUXILIARES,
            False,
        )

        for linea in archivo:
            fila = linea.split()
            if len(fila) != len(cabecera):
                filas_descartadas += 1
                continue

            posicion_numero = convertir_float(
                fila[indices_obligatorios[1]]
            )
            epoch = convertir_float(fila[indices_obligatorios[0]])
            if posicion_numero is None or epoch is None:
                filas_descartadas += 1
                continue

            posicion_mpv = int(posicion_numero)
            posicion_anterior = estado_valvula[0]

            if posicion_anterior is None:
                estado_valvula[0] = posicion_mpv
            elif posicion_mpv != posicion_anterior:
                estado_valvula[0] = posicion_mpv
                estado_valvula[1] = None
                if posicion_mpv == posicion_ambiente:
                    estado_valvula[1] = epoch

            if posicion_mpv == posicion_ambiente:
                tipo_muestra = "ambient"
                posicion_salida = posicion_ambiente

                inicio_ambiente = estado_valvula[1]
                if inicio_ambiente is not None:
                    segundos_estabilizacion = (
                        minutos_estabilizacion_ambiente * 60
                    )
                    if epoch < inicio_ambiente + segundos_estabilizacion:
                        filas_interpretadas += 1
                        continue
            else:
                tipo_muestra = "target"
                posicion_salida = posicion_mpv

            salida = obtener_salida(
                salidas,
                directorio_fecha_salida,
                tipo_muestra,
                posicion_salida,
            )
            escritor = salida[5]
            if escritor is not None:
                fila_salida = construir_fila_salida(
                    fila,
                    indices_obligatorios,
                    indices_auxiliares,
                    indices_gases,
                    gases,
                    posicion_mpv,
                )
                if fila_salida is not None:
                    escritor.writerow(fila_salida)

            filas_interpretadas += 1

    if filas_descartadas > 0:
        print(
            f"Filas raw descartadas en {ruta_raw}: {filas_descartadas}"
        )
    return filas_interpretadas


def preprocesar_fecha(
        fecha_trabajo,
        directorio_raw,
        directorio_preprocesado,
        gases,
        posicion_ambiente,
        minutos_estabilizacion_ambiente,
):
    """
    Preprocesa todos los raw de un día en un directorio temporal completo.

    El directorio diario solo se publica al terminar todas sus salidas. Devuelve
    True si el día se completa o ya estaba completo, y False si faltan datos
    raw o se produce un error.
    """
    ruta_fecha_final = construir_ruta_fecha(
        directorio_preprocesado,
        fecha_trabajo,
    )
    ruta_fecha_temporal = ruta_fecha_final + "_en_progreso"

    if os.path.isdir(ruta_fecha_final):
        print(
            f"Preprocesado del {fecha_trabajo:%Y-%m-%d} ya existente. "
            "Se omite sin sobrescribir."
        )
        return True

    directorio_fecha_raw = construir_ruta_fecha(
        directorio_raw,
        fecha_trabajo,
    )
    archivos_raw = obtener_archivos_raw(directorio_fecha_raw)
    if not archivos_raw:
        print(f"No hay archivos raw para {fecha_trabajo:%Y-%m-%d}.")
        return False

    if os.path.exists(ruta_fecha_temporal):
        try:
            shutil.rmtree(ruta_fecha_temporal)
            print(
                f"Preprocesado incompleto eliminado: {ruta_fecha_temporal}"
            )
        except OSError as e:
            print(
                f"Error al eliminar el preprocesado incompleto "
                f"{ruta_fecha_temporal}: {e}"
            )
            return False

    salidas = []
    estado_valvula = [None, None]
    filas_interpretadas = 0

    try:
        for ruta_raw in archivos_raw:
            filas_interpretadas += preprocesar_archivo_raw(
                ruta_raw,
                ruta_fecha_temporal,
                gases,
                posicion_ambiente,
                minutos_estabilizacion_ambiente,
                estado_valvula,
                salidas,
            )

        if not cerrar_salidas(salidas, True):
            if os.path.exists(ruta_fecha_temporal):
                shutil.rmtree(ruta_fecha_temporal)
            return False

        os.rename(ruta_fecha_temporal, ruta_fecha_final)

        print(
            f"Preprocesado completado para {fecha_trabajo:%Y-%m-%d}: "
            f"{filas_interpretadas} filas raw."
        )
        return True
    except (OSError, ValueError) as e:
        cerrar_salidas(salidas, False)
        if os.path.exists(ruta_fecha_temporal):
            shutil.rmtree(ruta_fecha_temporal)
        print(
            f"Error al preprocesar {fecha_trabajo:%Y-%m-%d}: {e}"
        )
        return False


# ==========================================================
# EJECUCIÓN DEL PREPROCESADO PARA UN PERIODO
# ==========================================================


def preprocesar_periodo(
        fecha_inicio,
        fecha_fin,
        directorio_raw,
        directorio_preprocesado,
        gases,
        posicion_ambiente,
        minutos_estabilizacion_ambiente,
):
    """
    Preprocesa todos los días disponibles del periodo solicitado.

    Crea el directorio base justo antes de iniciar la etapa. Los directorios
    diarios publicados se conservan y los temporales incompletos se eliminan.
    Devuelve True si no se producen errores en días con raw disponible.
    """
    if not crear_directorio(directorio_preprocesado):
        return False

    borrar_preprocesados_incompletos(directorio_preprocesado)
    errores = 0

    for fecha_trabajo in obtener_fechas_periodo(fecha_inicio, fecha_fin):
        directorio_fecha_raw = construir_ruta_fecha(
            directorio_raw,
            fecha_trabajo,
        )
        if not os.path.isdir(directorio_fecha_raw):
            print(
                f"Día raw no disponible; se omite: "
                f"{fecha_trabajo:%Y-%m-%d}"
            )
            continue

        if not preprocesar_fecha(
                fecha_trabajo,
                directorio_raw,
                directorio_preprocesado,
                gases,
                posicion_ambiente,
                minutos_estabilizacion_ambiente,
        ):
            errores += 1

    return errores == 0
