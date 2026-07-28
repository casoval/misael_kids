"""
inscripciones/services.py

Lógica de generación de cobros de mensualidad, centralizada para que se
comporte igual sin importar desde dónde se dispare: creación de una
inscripción nueva, una transferencia, o la generación manual/masiva.
"""
from dateutil.relativedelta import relativedelta

from .models import Cobro


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
