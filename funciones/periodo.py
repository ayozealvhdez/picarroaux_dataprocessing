"""
Funciones para definir el periodo de procesado.

Fecha de creación: 27/08/2026
Fecha de última modificación: 27/08/2026

Listado de cambios:

"""

import argparse
from datetime import datetime, timedelta


# ==========================================================
# LECTURA DEL NÚMERO DE DÍAS
# ==========================================================


def obtener_parametros_ejecucion(dias_por_defecto: int) -> int:
    """
    Lee el número común de días del flujo desde la línea de comandos.

    El valor de la cabecera del script actúa como predeterminado y --dias
    permite ajustarlo para una ejecución concreta. Devuelve el número de días.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Copia y procesa datos Picarro de días completos hasta ayer. "
            "Los resultados existentes se omiten sin sobrescribir."
        )
    )
    parser.add_argument(
        "--dias",
        type=int,
        default=dias_por_defecto,
        help=(
            "Número común de días para copia, procesado y referencia "
            f"(por defecto: {dias_por_defecto})."
        ),
    )
    argumentos = parser.parse_args()

    if argumentos.dias <= 0:
        raise ValueError("El número de días debe ser mayor que cero.")

    return argumentos.dias


# ==========================================================
# CÁLCULO DEL INTERVALO COMÚN DE DÍAS COMPLETOS
# ==========================================================


def calcular_periodo(
        dias_procesado: int,
        fecha_actual: datetime | None = None,
) -> tuple[datetime, datetime]:
    """
    Calcula un periodo inclusivo de días completos que termina ayer.

    dias_procesado es un parámetro de entrada común para copia y procesado.
    fecha_actual solo permite fijar el reloj durante las pruebas. Devuelve las
    fechas de inicio y fin a medianoche.
    """
    if dias_procesado <= 0:
        raise ValueError("El número de días debe ser mayor que cero.")

    if fecha_actual is None:
        fecha_actual = datetime.now()

    hoy = fecha_actual.replace(hour=0, minute=0, second=0, microsecond=0)
    fecha_fin = hoy - timedelta(days=1)
    fecha_inicio = fecha_fin - timedelta(days=dias_procesado - 1)

    return fecha_inicio, fecha_fin
