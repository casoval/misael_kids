"""
inscripciones/services.py

Lógica de generación de cobros de mensualidad, centralizada para que se
comporte igual sin importar desde dónde se dispare: creación de una
inscripción nueva, una transferencia, o la generación manual/masiva.
"""
import calendar
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import IntegrityError, transaction

from .models import Cobro

MESES_ES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]


def generar_ciclo_mensual(inscripcion, ciclo_num=None, usuario=None):
    """
    Genera el Cobro de mensualidad para el ciclo indicado de una
    inscripción. El ciclo NO sigue el mes calendario: sigue la fecha de
    inicio de la inscripción (si empezó el 20, cada ciclo va de 20 a 20).

    - ciclo_num=None → calcula el siguiente ciclo pendiente automáticamente
      (cuántas mensualidades ya tiene generadas esa inscripción).
    - Si ya existe un cobro para ese ciclo exacto, no crea uno duplicado:
      devuelve None.
    """
    if ciclo_num is None:
        ciclo_num = Cobro.objects.filter(
            inscripcion=inscripcion, tipo=Cobro.TIPO_MENSUALIDAD
        ).count()

    periodo_inicio = inscripcion.fecha_inicio + relativedelta(months=ciclo_num)
    periodo_fin    = inscripcion.fecha_inicio + relativedelta(months=ciclo_num + 1)

    ya_existe = Cobro.objects.filter(
        inscripcion=inscripcion, tipo=Cobro.TIPO_MENSUALIDAD, periodo_inicio=periodo_inicio
    ).exists()
    if ya_existe:
        return None

    try:
        with transaction.atomic():
            return Cobro.objects.create(
                inscripcion       = inscripcion,
                tipo              = Cobro.TIPO_MENSUALIDAD,
                periodo           = f'{periodo_inicio.isoformat()} a {periodo_fin.isoformat()}',
                periodo_inicio    = periodo_inicio,
                periodo_fin       = periodo_fin,
                monto_base        = inscripcion.costo_mensual,
                monto_final       = inscripcion.costo_mensual_final,
                fecha_vencimiento = periodo_fin,
                registrado_por    = usuario,
            )
    except IntegrityError:
        # Dos requests casi simultáneos pasaron el chequeo de "ya_existe" a
        # la vez (ej. doble clic, o "generar masivo" corriendo dos veces).
        # El constraint de BD es la última línea de defensa: no hay
        # duplicado, simplemente no se crea uno nuevo.
        return None


def _serializar_cobro_resumen(cobro):
    return {
        'id':              cobro.id,
        'estado':          cobro.estado,
        'estado_display':  cobro.get_estado_display(),
        'monto_final':     str(cobro.monto_final),
        'monto_pagado':    str(cobro.monto_pagado),
        'saldo_pendiente': str(cobro.saldo_pendiente),
        'monto_condonado': str(cobro.monto_condonado),
        'fecha_vencimiento': cobro.fecha_vencimiento.isoformat(),
    }


def calendario_pagos_mensual(inscripcion):
    """
    Arma la lista de ciclos mensuales de una inscripción con modalidad
    "mensual", desde el ciclo 0 (mes de inicio) hasta el ciclo actual,
    incluyendo cualquier ciclo generado más adelante de lo normal.
    Cada entrada indica si ya tiene Cobro o si todavía falta generarlo,
    para que la UI pueda ofrecer "Generar" o "Registrar pago" según toque.
    """
    hoy = date.today()

    cobros_existentes = {
        c.periodo_inicio: c
        for c in Cobro.objects.filter(inscripcion=inscripcion, tipo=Cobro.TIPO_MENSUALIDAD)
    }

    # Ciclo actual = cuántos ciclos completos de un mes ya pasaron desde fecha_inicio.
    delta = relativedelta(hoy, inscripcion.fecha_inicio)
    ciclo_actual = delta.years * 12 + delta.months

    ciclo_max_generado = 0
    for periodo_inicio in cobros_existentes:
        n = relativedelta(periodo_inicio, inscripcion.fecha_inicio)
        ciclo_max_generado = max(ciclo_max_generado, n.years * 12 + n.months)

    ciclo_tope = min(max(ciclo_actual, ciclo_max_generado), 60)  # tope de seguridad: 5 años

    resultado = []
    for ciclo in range(0, ciclo_tope + 1):
        periodo_inicio = inscripcion.fecha_inicio + relativedelta(months=ciclo)
        periodo_fin    = inscripcion.fecha_inicio + relativedelta(months=ciclo + 1)
        cobro = cobros_existentes.get(periodo_inicio)
        resultado.append({
            'ciclo':           ciclo,
            'etiqueta':        f'{MESES_ES[periodo_inicio.month]} {periodo_inicio.year}',
            'periodo_inicio':  periodo_inicio.isoformat(),
            'periodo_fin':     periodo_fin.isoformat(),
            'es_actual':       ciclo == ciclo_actual,
            'cobro':           _serializar_cobro_resumen(cobro) if cobro else None,
        })
    return resultado


def calendario_pagos_diario(inscripcion, anio, mes):
    """
    Arma el calendario de un mes calendario (1-31) para una inscripción con
    modalidad "diaria", con el estado del cobro de cada día que ya tiene uno.
    Los días sin Cobro (fin de semana, no asistió, o día futuro) llegan con
    cobro=None; la UI decide cómo pintarlos (no es un bug, es esperado: el
    cobro diario solo nace cuando se marca asistencia presente).
    """
    primer_dia    = date(anio, mes, 1)
    ultimo_dia_n  = calendar.monthrange(anio, mes)[1]
    ultimo_dia    = date(anio, mes, ultimo_dia_n)

    cobros_existentes = {
        c.fecha_vencimiento: c
        for c in Cobro.objects.filter(
            inscripcion=inscripcion, tipo=Cobro.TIPO_DIARIO,
            fecha_vencimiento__gte=primer_dia, fecha_vencimiento__lte=ultimo_dia,
        )
    }

    dias = []
    for n in range(1, ultimo_dia_n + 1):
        dia = date(anio, mes, n)
        cobro = cobros_existentes.get(dia)
        dias.append({
            'dia':          n,
            'fecha':        dia.isoformat(),
            'dia_semana':   dia.weekday(),  # 0=lunes ... 6=domingo
            'cobro':        _serializar_cobro_resumen(cobro) if cobro else None,
        })
    return {'anio': anio, 'mes': mes, 'etiqueta': f'{MESES_ES[mes]} {anio}', 'dias': dias}
