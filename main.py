"""
Orquesta la copia y el procesado incremental de datos auxiliares del Picarro.

Fecha de creación: 27/08/2026
Fecha de última modificación: 27/08/2026

Listado de cambios:


Estructura:
1. Configuración común del flujo y referencias certificadas.
2. Definición del periodo terminado ayer.
3. Copia incremental de datos raw.
4. Preprocesado por tipo de muestra, posición y gas.
5. Resumen de inyecciones target.
6. Ajuste lineal con las referencias certificadas de los dos tanques.
7. Calibración de las medidas ambientales.
8. Limpieza de datos temporales fuera del periodo.

Los días y archivos ya existentes se omiten en todas las etapas. Ningún
resultado final se sobrescribe.
"""

import os

from funciones.calibracion import calcular_calibraciones_periodo
from funciones.copia import borrar_datos_fuera_periodo
from funciones.copia import copiar_datos_picarro
from funciones.correccion import calibrar_ambiente_periodo
from funciones.inyecciones import procesar_inyecciones_periodo
from funciones.periodo import calcular_periodo, obtener_parametros_ejecucion
from funciones.preprocesado import preprocesar_periodo


# ==========================================================
# 1. CONFIGURACIÓN COMÚN DEL FLUJO
# ==========================================================

# Días completos que se copian y procesan hasta ayer.
DIAS_PROCESADO = 80

# Gases que se extraen directamente de las columnas raw y se procesan.
GASES = ("CO2", "CH4", "CO")
# Posición MPV que identifica el aire ambiente frente a los targets.
POSICION_AMBIENTE = 1
# Posiciones MPV de los dos tanques que forman cada calibración lineal.
POSICIONES_TARGET = (2, 3)

# Valores de referencia de los tanques.
REFERENCIA_MPV03_CO2_PPM = 434.79
REFERENCIA_MPV03_CH4_PPB = 1972.48
REFERENCIA_MPV03_CO_PPB = 103.75
REFERENCIA_MPV02_CO2_PPM = 426.01
REFERENCIA_MPV02_CH4_PPB = 1968.70
REFERENCIA_MPV02_CO_PPB = 111.05

# Cada registro contiene posición, gas, valor, unidad y factor de conversión
# a ppm (es la unidad de las columnas originales del Picarro).
REFERENCIAS_TANQUES = (
    (2, "CO2", REFERENCIA_MPV02_CO2_PPM, "ppm", 1.0),
    (2, "CH4", REFERENCIA_MPV02_CH4_PPB, "ppb", 0.001),
    (2, "CO", REFERENCIA_MPV02_CO_PPB, "ppb", 0.001),
    (3, "CO2", REFERENCIA_MPV03_CO2_PPM, "ppm", 1.0),
    (3, "CH4", REFERENCIA_MPV03_CH4_PPB, "ppb", 0.001),
    (3, "CO", REFERENCIA_MPV03_CO_PPB, "ppb", 0.001),
)

# Minutos tras cada cambio a la posición ambiente que se descartan por estabilización.
MINUTOS_ESTABILIZACION_AMBIENTE = 10
# Minutos iniciales de cada inyección target que se descartan por estabilización.
MINUTOS_ESTABILIZACION_TARGET = 10
# Salto temporal máximo, en segundos, para considerar dos medidas como parte de la misma inyección target.
SEGUNDOS_MAXIMOS_ENTRE_MEDIDAS_TARGET = 100
# Número mínimo de medidas estables válidas para aceptar una inyección.
MINIMO_OBSERVACIONES_INYECCION = 100

DIRECTORIO_PROYECTO = os.path.dirname(os.path.abspath(__file__))
RUTA_DIRECTORIO_ORIGEN = os.path.join(
    DIRECTORIO_PROYECTO,
    "data_path",
    "directorio_origen.txt",
)
DIRECTORIO_RAW = os.path.join(DIRECTORIO_PROYECTO, "tmp", "raw_data")
DIRECTORIO_PREPROCESADO = os.path.join(
    DIRECTORIO_PROYECTO,
    "tmp",
    "preprocessed_data",
)
DIRECTORIO_PROCESADO = os.path.join(DIRECTORIO_PROYECTO, "processed_data")
DIRECTORIO_INYECCIONES = os.path.join(
    DIRECTORIO_PROCESADO,
    "injections",
)
DIRECTORIO_CALIBRACIONES = os.path.join(
    DIRECTORIO_PROCESADO,
    "calibrations",
)
DIRECTORIO_CURVAS_CALIBRACION = os.path.join(
    DIRECTORIO_PROCESADO,
    "calibration_curves",
)
DIRECTORIO_AMBIENTE_PROCESADO = os.path.join(
    DIRECTORIO_PROCESADO,
    "ambient",
)

SEPARADOR = "-------------------------------------------------------"


def leer_directorio_origen():
    """Lee la ruta local del origen de datos, fuera del repositorio."""
    try:
        with open(RUTA_DIRECTORIO_ORIGEN, "r", encoding="utf-8") as archivo:
            directorio_origen = archivo.read().strip()
    except OSError as error:
        raise RuntimeError(
            "No se pudo leer la configuración local del origen: "
            f"{RUTA_DIRECTORIO_ORIGEN}"
        ) from error

    if not directorio_origen:
        raise RuntimeError(
            "La configuración local del origen está vacía: "
            f"{RUTA_DIRECTORIO_ORIGEN}"
        )

    return directorio_origen


# ==========================================================
# 2. EJECUCIÓN DEL FLUJO
# ==========================================================

if __name__ == "__main__":
    copia_correcta = False
    preprocesado_correcto = False
    inyecciones_correctas = False
    calibraciones_correctas = False
    ambiente_correcto = False

    try:
        print("Paso 0: Leyendo la configuración común...")
        DIRECTORIO_ORIGEN = leer_directorio_origen()
        dias = obtener_parametros_ejecucion(DIAS_PROCESADO)
        print(SEPARADOR)

        fecha_inicio, fecha_fin = calcular_periodo(dias)
        print(
            f"Periodo común de copia y procesado: "
            f"{fecha_inicio.strftime('%Y-%m-%d')} a "
            f"{fecha_fin.strftime('%Y-%m-%d')}"
        )
        print(f"Número de días configurado: {dias}")
        print(SEPARADOR)

        print("Paso 1: Copiando datos raw que todavía no existen...")
        copia_correcta = copiar_datos_picarro(
            fecha_inicio,
            fecha_fin,
            DIRECTORIO_ORIGEN,
            DIRECTORIO_RAW,
        )
        print(SEPARADOR)

        print("Paso 2: Preprocesando ambiente y targets por gas...")
        preprocesado_correcto = preprocesar_periodo(
            fecha_inicio,
            fecha_fin,
            DIRECTORIO_RAW,
            DIRECTORIO_PREPROCESADO,
            GASES,
            POSICION_AMBIENTE,
            MINUTOS_ESTABILIZACION_AMBIENTE,
        )
        print(SEPARADOR)

        print("Paso 3: Calculando promedios de las inyecciones target...")
        inyecciones_correctas = procesar_inyecciones_periodo(
            fecha_inicio,
            fecha_fin,
            DIRECTORIO_PREPROCESADO,
            DIRECTORIO_INYECCIONES,
            POSICIONES_TARGET,
            GASES,
            MINUTOS_ESTABILIZACION_TARGET,
            SEGUNDOS_MAXIMOS_ENTRE_MEDIDAS_TARGET,
            MINIMO_OBSERVACIONES_INYECCION,
        )
        print(SEPARADOR)

        print("Paso 4: Ajustando las rectas de calibración...")
        calibraciones_correctas = calcular_calibraciones_periodo(
            fecha_inicio,
            fecha_fin,
            DIRECTORIO_INYECCIONES,
            DIRECTORIO_CALIBRACIONES,
            DIRECTORIO_CURVAS_CALIBRACION,
            POSICIONES_TARGET,
            GASES,
            REFERENCIAS_TANQUES,
        )
        print(SEPARADOR)

        print("Paso 5: Calibrando las medidas de aire ambiente...")
        ambiente_correcto = calibrar_ambiente_periodo(
            fecha_inicio,
            fecha_fin,
            DIRECTORIO_PREPROCESADO,
            DIRECTORIO_CALIBRACIONES,
            DIRECTORIO_AMBIENTE_PROCESADO,
            GASES,
        )
        print(SEPARADOR)

        if (
                preprocesado_correcto
                and inyecciones_correctas
                and calibraciones_correctas
                and ambiente_correcto
        ):
            print("Paso 6: Limpiando datos temporales fuera del periodo...")
            borrar_datos_fuera_periodo(
                fecha_inicio,
                fecha_fin,
                DIRECTORIO_RAW,
            )
            borrar_datos_fuera_periodo(
                fecha_inicio,
                fecha_fin,
                DIRECTORIO_PREPROCESADO,
            )
            print(SEPARADOR)
        else:
            print(
                "No se limpian temporales porque alguna etapa de procesado "
                "terminó con errores."
            )
            print(SEPARADOR)

        if (
                copia_correcta
                and preprocesado_correcto
                and inyecciones_correctas
                and calibraciones_correctas
                and ambiente_correcto
        ):
            print("Proceso completo finalizado correctamente.")
        else:
            print("Proceso finalizado con avisos o errores comunicados.")
    except Exception as e:
        print(f"Excepción no controlada durante la ejecución: {e}")
