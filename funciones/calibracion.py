"""
Funciones de cálculo y representación de calibraciones lineales.

Fecha de creación: 27/08/2026
Fecha de última modificación: 27/08/2026

Listado de cambios:

"""

import csv
import os
from datetime import datetime, timezone

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from funciones.comunes import construir_ruta_fecha, convertir_float
from funciones.comunes import convertir_epoch_a_fecha_decimal
from funciones.comunes import convertir_fecha_decimal_a_epoch
from funciones.comunes import crear_directorio, escribir_csv_atomico
from funciones.comunes import obtener_fechas_periodo


# ==========================================================
# LECTURA DEL HISTÓRICO DE INYECCIONES
# ==========================================================


def obtener_archivos_inyecciones(directorio_inyecciones):
    """
    Localiza los resúmenes diarios de inyecciones disponibles.

    Devuelve una lista de rutas ordenadas cronológicamente.
    """
    archivos = []

    if not os.path.isdir(directorio_inyecciones):
        return archivos

    for ruta_actual, _, nombres in os.walk(directorio_inyecciones):
        for nombre in nombres:
            if nombre == "inyecciones.csv":
                archivos.append(os.path.join(ruta_actual, nombre))

    archivos.sort()
    return archivos


def existe_inyeccion(inyecciones, identificador, gas):
    """
    Comprueba si una inyección y un gas ya están en el histórico leído.
    """
    for inyeccion in inyecciones:
        if inyeccion[0] == identificador and inyeccion[3] == gas:
            return True
    return False


def leer_historico_inyecciones(directorio_inyecciones):
    """
    Lee las medias estables de las inyecciones y elimina duplicados.

    Devuelve registros ordenados por inicio, posición y gas.
    """
    inyecciones = []

    for ruta_archivo in obtener_archivos_inyecciones(directorio_inyecciones):
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

                indice_posicion = cabecera.index("mpv")
                indice_inicio = cabecera.index("decimal_date")
                indice_fin = cabecera.index("end_decimal_date")

                for fila in lector:
                    if len(fila) != len(cabecera):
                        continue

                    inicio = convertir_fecha_decimal_a_epoch(
                        fila[indice_inicio]
                    )
                    fin = convertir_fecha_decimal_a_epoch(fila[indice_fin])
                    posicion = convertir_float(fila[indice_posicion])
                    if inicio is None or fin is None or posicion is None:
                        continue

                    posicion_entera = int(posicion)
                    identificador = (
                        f"inyeccion_{int(round(inicio * 1000))}_"
                        f"mpv_{posicion_entera:02d}"
                    )

                    for gas in ("CO2", "CH4", "CO"):
                        if gas == "CO2":
                            columna = "co2_raw_ppm"
                            factor_a_ppm = 1.0
                        elif gas == "CH4":
                            columna = "ch4_raw_ppb"
                            factor_a_ppm = 0.001
                        else:
                            columna = "co_raw_ppb"
                            factor_a_ppm = 0.001

                        media = convertir_float(
                            fila[cabecera.index(columna)]
                        )
                        if existe_inyeccion(
                                inyecciones,
                                identificador,
                                gas,
                        ):
                            continue

                        media_ppm = None
                        if media is not None:
                            media_ppm = media * factor_a_ppm

                        inyecciones.append(
                            [
                                identificador,
                                f"mpv_{posicion_entera:02d}",
                                posicion_entera,
                                gas,
                                inicio,
                                fin,
                                media_ppm,
                                media_ppm is not None,
                            ]
                        )
        except (OSError, ValueError, csv.Error) as e:
            print(f"Error al leer inyecciones de {ruta_archivo}: {e}")

    inyecciones.sort(
        key=lambda registro: (registro[4], registro[2], registro[3])
    )
    return inyecciones


# ==========================================================
# EMPAREJAMIENTO DE INYECCIONES CONSECUTIVAS
# ==========================================================


def buscar_evento_inyeccion(eventos, identificador):
    """
    Busca un evento de inyección por su identificador.

    Devuelve el evento encontrado o None.
    """
    for evento in eventos:
        if evento[0] == identificador:
            return evento
    return None


def agrupar_inyecciones_por_evento(inyecciones):
    """
    Agrupa las filas de los distintos gases que pertenecen a una inyección.

    Cada evento conserva identificador, tanque, posición, tiempos y medidas.
    """
    eventos = []

    for inyeccion in inyecciones:
        evento = buscar_evento_inyeccion(eventos, inyeccion[0])
        if evento is None:
            evento = [
                inyeccion[0],
                inyeccion[1],
                inyeccion[2],
                inyeccion[4],
                inyeccion[5],
                [],
            ]
            eventos.append(evento)

        if inyeccion[4] < evento[3]:
            evento[3] = inyeccion[4]
        if inyeccion[5] > evento[4]:
            evento[4] = inyeccion[5]

        evento[5].append(
            [
                inyeccion[3],
                inyeccion[6],
                inyeccion[7],
            ]
        )

    eventos.sort(key=lambda registro: (registro[3], registro[2]))
    return eventos


def emparejar_inyecciones_consecutivas(inyecciones, posiciones_target):
    """
    Empareja eventos consecutivos de las dos posiciones configuradas.

    Si se repite una posición antes de aparecer la otra, conserva el evento
    repetido más reciente. Devuelve una lista cronológica de parejas.
    """
    parejas = []
    evento_pendiente = None
    eventos = agrupar_inyecciones_por_evento(inyecciones)

    for evento in eventos:
        if evento[2] not in posiciones_target:
            continue

        if evento_pendiente is None:
            evento_pendiente = evento
            continue

        if evento[2] == evento_pendiente[2]:
            evento_pendiente = evento
            continue

        parejas.append([evento_pendiente, evento])
        evento_pendiente = None

    return parejas


def buscar_evento_posicion(pareja, posicion_mpv):
    """
    Busca dentro de una pareja el evento correspondiente a una posición MPV.
    """
    for evento in pareja:
        if evento[2] == posicion_mpv:
            return evento
    return None


def buscar_medicion_gas(evento, gas):
    """
    Busca la media estable y su validez para un gas dentro de un evento.
    """
    if evento is None:
        return None

    for medicion in evento[5]:
        if medicion[0] == gas:
            return medicion
    return None


# ==========================================================
# AJUSTE LINEAL CON REFERENCIAS CERTIFICADAS
# ==========================================================


def obtener_referencia_certificada(
        referencias_tanques,
        posicion_mpv,
        gas,
):
    """
    Obtiene valor, unidad y factor a ppm para un tanque y un gas.

    Cada referencia configurada debe contener posición, gas, valor certificado,
    unidad original y factor multiplicativo para expresarlo en ppm.
    """
    for referencia in referencias_tanques:
        if referencia[0] == posicion_mpv and referencia[1] == gas:
            return referencia[2], referencia[3], referencia[4]
    return None


def crear_cabecera_calibraciones(gases):
    """
    Construye la cabecera compacta del histórico de calibraciones lineales.
    """
    cabecera = [
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "decimal_date",
        "mpv_1",
        "mpv_2",
    ]

    for gas in gases:
        nombre_gas = gas.lower()
        unidad = "ppm" if gas == "CO2" else "ppb"
        cabecera.extend(
            [
                f"{nombre_gas}_mpv_1_raw_{unidad}",
                f"{nombre_gas}_mpv_2_raw_{unidad}",
                f"{nombre_gas}_slope",
                f"{nombre_gas}_intercept_ppm",
            ]
        )
    return cabecera


def calcular_ajuste_gas(
        pareja,
        posiciones_target,
        gas,
        referencias_tanques,
):
    """
    Ajusta referencia_ppm = pendiente * medida_ppm + ordenada_origen.

    Devuelve las dos medias, la pendiente y la ordenada en el origen.
    """
    mediciones_ppm = []
    referencias_ppm = []

    for posicion in posiciones_target:
        evento = buscar_evento_posicion(pareja, posicion)
        medicion = buscar_medicion_gas(evento, gas)
        referencia = obtener_referencia_certificada(
            referencias_tanques,
            posicion,
            gas,
        )

        if evento is None or medicion is None or referencia is None:
            return ["", "", "", ""]
        if not medicion[2] or medicion[1] is None:
            return ["", "", "", ""]

        valor_certificado = convertir_float(referencia[0])
        factor_a_ppm = convertir_float(referencia[2])
        if valor_certificado is None or factor_a_ppm is None:
            return ["", "", "", ""]

        mediciones_ppm.append(float(medicion[1]))
        referencias_ppm.append(valor_certificado * factor_a_ppm)

    escala = max(float(np.max(np.abs(mediciones_ppm))), 1.0)
    diferencia_minima = np.finfo(float).eps * escala
    if abs(mediciones_ppm[1] - mediciones_ppm[0]) <= diferencia_minima:
        return ["", "", "", ""]

    coeficientes = np.polyfit(mediciones_ppm, referencias_ppm, 1)
    factor_salida = 1.0 if gas == "CO2" else 1000.0
    return [
        mediciones_ppm[0] * factor_salida,
        mediciones_ppm[1] * factor_salida,
        float(coeficientes[0]),
        float(coeficientes[1]),
    ]


def calcular_fila_calibracion(
        pareja,
        posiciones_target,
        gases,
        referencias_tanques,
):
    """
    Construye una fila compacta con los ajustes de los tres gases.
    """
    epoch_calibracion = float(max(evento[4] for evento in pareja))
    instante = datetime.fromtimestamp(epoch_calibracion, timezone.utc)
    fila = [
        str(instante.year),
        str(instante.month),
        str(instante.day),
        str(instante.hour),
        str(instante.minute),
        f"{convertir_epoch_a_fecha_decimal(epoch_calibracion):.12f}",
        str(posiciones_target[0]),
        str(posiciones_target[1]),
    ]

    for gas in gases:
        fila.extend(
            calcular_ajuste_gas(
                pareja,
                posiciones_target,
                gas,
                referencias_tanques,
            )
        )

    return fila


def calcular_calibraciones(
        parejas,
        posiciones_target,
        gases,
        referencias_tanques,
):
    """
    Calcula una fila con las rectas de cada pareja consecutiva.
    """
    filas = []

    for pareja in parejas:
        filas.append(
            calcular_fila_calibracion(
                pareja,
                posiciones_target,
                gases,
                referencias_tanques,
            )
        )

    filas.sort(key=lambda fila: float(fila[5]))
    return filas


# ==========================================================
# ESCRITURA INCREMENTAL Y GRÁFICAS DE CALIBRACIÓN
# ==========================================================


def obtener_fecha_fila_calibracion(fila):
    """
    Obtiene la fecha UTC correspondiente a una fila de calibración.
    """
    epoch = convertir_fecha_decimal_a_epoch(fila[5])
    if epoch is None:
        raise ValueError("Fecha decimal no válida en una calibración.")
    return datetime.fromtimestamp(epoch, timezone.utc).date()


def leer_archivo_calibraciones(ruta_archivo):
    """
    Lee un archivo de calibraciones para generar sus gráficas.

    Devuelve cabecera y filas; ambas quedan vacías si la lectura falla.
    """
    try:
        with open(ruta_archivo, "r", encoding="utf-8", newline="") as archivo:
            lector = csv.reader(archivo, delimiter=";")
            cabecera = next(lector, None)
            if not cabecera:
                return [], []
            return cabecera, list(lector)
    except (OSError, csv.Error) as e:
        print(f"Error al leer calibraciones de {ruta_archivo}: {e}")
        return [], []


def representar_gas_calibracion(
        eje,
        fila,
        cabecera,
        gas,
):
    """
    Representa los dos puntos certificados y su recta ajustada para un gas.
    """
    nombre_gas = gas.lower()
    unidad = "ppm" if gas == "CO2" else "ppb"
    columna_mpv_1 = f"{nombre_gas}_mpv_1_raw_{unidad}"
    columna_mpv_2 = f"{nombre_gas}_mpv_2_raw_{unidad}"
    mediciones = [
        convertir_float(fila[cabecera.index(columna_mpv_1)]),
        convertir_float(fila[cabecera.index(columna_mpv_2)]),
    ]
    pendiente = convertir_float(
        fila[cabecera.index(f"{nombre_gas}_slope")]
    )
    ordenada_ppm = convertir_float(
        fila[cabecera.index(f"{nombre_gas}_intercept_ppm")]
    )

    if None in mediciones or pendiente is None or ordenada_ppm is None:
        eje.text(
            0.5,
            0.5,
            "Calibración no válida",
            ha="center",
            va="center",
            transform=eje.transAxes,
        )
        eje.set_title(gas)
        eje.set_axis_off()
        return False

    factor_a_ppm = 1.0 if gas == "CO2" else 0.001
    ordenada_salida = ordenada_ppm / factor_a_ppm
    referencias = []
    for medicion in mediciones:
        referencias.append(pendiente * medicion + ordenada_salida)

    minimo = min(mediciones)
    maximo = max(mediciones)
    margen = max((maximo - minimo) * 0.15, abs(minimo) * 0.01, 1e-6)
    eje_x = np.linspace(minimo - margen, maximo + margen, 100)
    eje_y = pendiente * eje_x + ordenada_salida

    eje.plot(eje_x, eje_y, color="tab:blue", label="Ajuste lineal")
    for indice in range(len(mediciones)):
        eje.scatter(
            mediciones[indice],
            referencias[indice],
            s=55,
            label=f"MPV{fila[cabecera.index(f'mpv_{indice + 1}')]} ",
            zorder=3,
        )

    eje.set_title(
        f"{gas}\ny = {pendiente:.8g} x + {ordenada_salida:.8g}"
    )
    eje.set_xlabel(f"Media de la inyección ({unidad})")
    eje.set_ylabel(f"Valor de referencia ({unidad})")
    eje.grid(alpha=0.25)
    eje.legend(fontsize=8)
    return True


def guardar_grafica_calibracion(
        fila,
        cabecera,
        directorio_curvas,
        gases,
):
    """
    Guarda un PNG con una subgráfica por gas para una pareja de inyecciones.

    No sobrescribe una gráfica existente. Devuelve True si queda disponible.
    """
    epoch = convertir_fecha_decimal_a_epoch(
        fila[cabecera.index("decimal_date")]
    )
    if epoch is None:
        return False

    posicion_1 = int(float(fila[cabecera.index("mpv_1")]))
    posicion_2 = int(float(fila[cabecera.index("mpv_2")]))
    identificador = (
        f"calibracion_{int(round(epoch * 1000))}_"
        f"mpv_{posicion_1:02d}_mpv_{posicion_2:02d}"
    )
    fecha = datetime.fromtimestamp(epoch, timezone.utc)
    ruta_fecha = construir_ruta_fecha(directorio_curvas, fecha)
    ruta_final = os.path.join(ruta_fecha, f"{identificador}.png")
    if os.path.exists(ruta_final):
        return True
    if not crear_directorio(ruta_fecha):
        return False

    figura = None
    ruta_temporal = os.path.join(
        ruta_fecha,
        f"{identificador}_en_progreso.png",
    )

    try:
        figura, matriz_ejes = plt.subplots(
            1,
            len(gases),
            figsize=(5.2 * len(gases), 4.7),
            squeeze=False,
        )
        ejes = matriz_ejes[0]

        for indice, gas in enumerate(gases):
            representar_gas_calibracion(
                ejes[indice],
                fila,
                cabecera,
                gas,
            )

        figura.suptitle(
            f"Calibración disponible desde "
            f"{fecha.isoformat(timespec='milliseconds').replace('+00:00', 'Z')}"
        )
        figura.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
        figura.savefig(ruta_temporal, dpi=160, bbox_inches="tight")
        plt.close(figura)
        figura = None

        if os.path.exists(ruta_final):
            os.remove(ruta_temporal)
        else:
            os.rename(ruta_temporal, ruta_final)
        return True
    except (OSError, ValueError, RuntimeError) as e:
        if figura is not None:
            plt.close(figura)
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)
        print(f"Error al guardar la gráfica {ruta_final}: {e}")
        return False


def generar_graficas_calibraciones(
        ruta_calibraciones,
        directorio_curvas,
        gases,
):
    """
    Genera todas las gráficas todavía ausentes de un archivo diario.
    """
    cabecera, filas = leer_archivo_calibraciones(ruta_calibraciones)
    if not cabecera:
        return False

    resultado_correcto = True
    for fila in filas:
        if len(fila) != len(cabecera):
            continue
        if not guardar_grafica_calibracion(
                fila,
                cabecera,
                directorio_curvas,
                gases,
        ):
            resultado_correcto = False

    return resultado_correcto


def calcular_calibraciones_periodo(
        fecha_inicio,
        fecha_fin,
        directorio_inyecciones,
        directorio_calibraciones,
        directorio_curvas,
        posiciones_target,
        gases,
        referencias_tanques,
):
    """
    Ajusta y publica las calibraciones de todas las parejas del periodo.

    Requiere exactamente dos posiciones target. Los resultados diarios y las
    gráficas existentes se conservan sin sobrescribir. Devuelve True si todas
    las salidas quedan disponibles.
    """
    if len(posiciones_target) != 2:
        print("La calibración lineal requiere exactamente dos targets.")
        return False
    if not crear_directorio(directorio_calibraciones):
        return False
    if not crear_directorio(directorio_curvas):
        return False

    inyecciones = leer_historico_inyecciones(directorio_inyecciones)
    parejas = emparejar_inyecciones_consecutivas(
        inyecciones,
        posiciones_target,
    )
    filas = calcular_calibraciones(
        parejas,
        posiciones_target,
        gases,
        referencias_tanques,
    )
    cabecera = crear_cabecera_calibraciones(gases)
    resultado_correcto = True

    for fecha_trabajo in obtener_fechas_periodo(fecha_inicio, fecha_fin):
        ruta_inyecciones = os.path.join(
            construir_ruta_fecha(directorio_inyecciones, fecha_trabajo),
            "inyecciones.csv",
        )
        if not os.path.exists(ruta_inyecciones):
            print(
                f"No se calculan calibraciones del "
                f"{fecha_trabajo:%Y-%m-%d} porque todavía no existe su "
                "resumen de inyecciones."
            )
            continue

        filas_fecha = []
        for fila in filas:
            if obtener_fecha_fila_calibracion(fila) == fecha_trabajo.date():
                filas_fecha.append(fila)

        ruta_salida = os.path.join(
            construir_ruta_fecha(directorio_calibraciones, fecha_trabajo),
            "calibraciones_lineales.csv",
        )
        salida_existente = os.path.exists(ruta_salida)

        if not escribir_csv_atomico(
                ruta_salida,
                cabecera,
                filas_fecha,
                ";",
        ):
            resultado_correcto = False
            continue

        if not salida_existente:
            print(
                f"Calibraciones calculadas para "
                f"{fecha_trabajo:%Y-%m-%d}: {len(filas_fecha)} registros."
            )

        if not generar_graficas_calibraciones(
                ruta_salida,
                directorio_curvas,
                gases,
        ):
            resultado_correcto = False

    return resultado_correcto
