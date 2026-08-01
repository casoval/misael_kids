"""
inscripciones/services.py

Lógica de generación de cobros de mensualidad, centralizada para que se
comporte igual sin importar desde dónde se dispare: creación de una
inscripción nueva, una transferencia, o la generación manual/masiva.
"""
import calendar
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import IntegrityError, transaction, models

from .models import Cobro

MESES_ES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]


def asignar_numero_recibo(instancia):
    """
    Asigna el siguiente número de recibo correlativo a un Pago o una
    Devolucion (cada modelo lleva su propia numeración: recibos de pago
    van 1, 2, 3... y recibos de devolución por su lado 1, 2, 3...).

    Usa reintento en vez de un lock porque numero_recibo tiene un
    UniqueConstraint implícito (unique=True): si dos pagos casi
    simultáneos calculan el mismo "siguiente número", el segundo choca
    contra la restricción de BD y simplemente vuelve a intentar con el
    número ya actualizado — mismo patrón que usamos contra cobros
    duplicados.
    """
    Modelo = type(instancia)
    for _ in range(5):
        ultimo = Modelo.objects.exclude(pk=instancia.pk).aggregate(
            models.Max('numero_recibo')
        )['numero_recibo__max'] or 0
        instancia.numero_recibo = ultimo + 1
        try:
            with transaction.atomic():
                instancia.save(update_fields=['numero_recibo'])
            return instancia.numero_recibo
        except IntegrityError:
            continue
    raise RuntimeError('No se pudo asignar un número de recibo tras varios intentos.')


def generar_ciclo_mensual(inscripcion, ciclo_num=None, periodo_inicio=None, usuario=None):
    """
    Genera el Cobro de mensualidad para el ciclo indicado de una
    inscripción. El ciclo NO sigue el mes calendario: sigue la fecha de
    inicio de la inscripción (si empezó el 20, cada ciclo va de 20 a 20).

    - ciclo_num=None y periodo_inicio=None → calcula el siguiente ciclo
      pendiente automáticamente (cuántas mensualidades ya tiene esa
      inscripción).
    - periodo_inicio explícito → para reanudar después de una pausa, con
      una fecha de arranque distinta a la que tocaría en la grilla
      automática (ej. el niño faltó 3 meses y se reincorpora hoy; no tiene
      sentido facturar los 3 meses que no vino). Si se pasa, tiene
      prioridad sobre ciclo_num.
    - Si ya existe un cobro para ese periodo_inicio exacto, no crea uno
      duplicado: devuelve None.
    """
    if periodo_inicio is None:
        if ciclo_num is None:
            ciclo_num = Cobro.objects.filter(
                inscripcion=inscripcion, tipo=Cobro.TIPO_MENSUALIDAD
            ).count()
        periodo_inicio = inscripcion.fecha_inicio + relativedelta(months=ciclo_num)

    periodo_fin = periodo_inicio + relativedelta(months=1)

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


ESTADOS_ABIERTOS = (Cobro.ESTADO_PENDIENTE, Cobro.ESTADO_PARCIAL, Cobro.ESTADO_VENCIDO)


def etiqueta_periodo(cobro):
    """Etiqueta legible de un cobro, para mensajes de error: 'Julio 2026' o la fecha del día."""
    if cobro.tipo == Cobro.TIPO_MENSUALIDAD and cobro.periodo_inicio:
        return f'{MESES_ES[cobro.periodo_inicio.month]} {cobro.periodo_inicio.year}'
    return cobro.fecha_vencimiento.strftime('%d/%m/%Y')


def cobro_anterior_pendiente(cobro):
    """
    Devuelve el cobro anterior más antiguo (mismo tipo, misma inscripción,
    con periodo/fecha anterior a este) que todavía esté abierto (pendiente,
    parcial o vencido), o None si no hay ninguno bloqueando.

    Solo aplica a mensualidad y diario: no tiene sentido para "extra" (un
    paseo, un material) que son cargos puntuales sin orden cronológico
    obligatorio entre ellos.

    Se usa para exigir que los cobros se cierren en orden: no se puede
    pagar o condonar octubre si septiembre sigue abierto.
    """
    if cobro.tipo == Cobro.TIPO_EXTRA:
        return None

    qs = Cobro.objects.filter(
        inscripcion=cobro.inscripcion, tipo=cobro.tipo, estado__in=ESTADOS_ABIERTOS,
    ).exclude(pk=cobro.pk)

    if cobro.tipo == Cobro.TIPO_MENSUALIDAD:
        qs = qs.filter(periodo_inicio__lt=cobro.periodo_inicio).order_by('periodo_inicio')
    else:
        qs = qs.filter(fecha_vencimiento__lt=cobro.fecha_vencimiento).order_by('fecha_vencimiento')

    return qs.first()


def _serializar_cobro_resumen(cobro):
    return {
        'id':                cobro.id,
        'estado':            cobro.estado,
        'estado_display':    cobro.get_estado_display(),
        'monto_final':       str(cobro.monto_final),
        'monto_pagado':      str(cobro.monto_pagado),
        'saldo_pendiente':   str(cobro.saldo_pendiente),
        'monto_condonado':   str(cobro.monto_condonado),
        'motivo_condonacion': cobro.motivo_condonacion,
        'fecha_emision':     cobro.fecha_emision.isoformat(),
        'fecha_vencimiento': cobro.fecha_vencimiento.isoformat(),
        'fecha_pago':        cobro.fecha_pago.isoformat() if cobro.fecha_pago else None,
        'registrado_por':    cobro.registrado_por.nombre_completo if cobro.registrado_por else None,
        'pagos': [
            {
                'id':             p.id,
                'numero_recibo':  p.numero_recibo,
                'monto':          str(p.monto),
                'fecha_pago':     p.fecha_pago.isoformat(),
                'metodo_pago':    p.get_metodo_pago_display(),
                'registrado_por': p.registrado_por.nombre_completo if p.registrado_por else None,
                'observacion':    p.observacion,
            }
            for p in cobro.pagos.order_by('fecha_pago', 'created_at')
        ],
        'devoluciones': [
            {
                'id':             d.id,
                'numero_recibo':  d.numero_recibo,
                'monto':          str(d.monto),
                'fecha':          d.fecha.isoformat(),
                'metodo_pago':    d.get_metodo_pago_display(),
                'motivo':         d.motivo,
                'registrado_por': d.registrado_por.nombre_completo if d.registrado_por else None,
            }
            for d in cobro.devoluciones.order_by('fecha', 'created_at')
        ],
    }


def calendario_pagos_mensual(inscripcion):
    """
    Arma la lista de ciclos mensuales de una inscripción con modalidad
    "mensual", desde el ciclo 0 (mes de inicio) hasta el ciclo actual,
    incluyendo cualquier ciclo generado más adelante de lo normal, y
    cualquier mensualidad con fecha de inicio "personalizada" (botón
    "Nueva mensualidad" con fecha elegida a mano, ej. al reanudar tras una
    pausa) — todo mezclado en un único orden cronológico.

    Cada entrada trae `bloqueado_por`: la etiqueta del primer mes anterior
    que sigue abierto, o None si este mes ya se puede pagar/cerrar. La UI
    usa esto para exigir que se cierre en orden (no saltar a pagar
    Octubre si Septiembre sigue pendiente).
    """
    hoy = date.today()

    cobros_existentes = {
        c.periodo_inicio: c
        for c in Cobro.objects.filter(inscripcion=inscripcion, tipo=Cobro.TIPO_MENSUALIDAD)
            .select_related('registrado_por').prefetch_related('pagos', 'pagos__registrado_por', 'devoluciones', 'devoluciones__registrado_por')
    }

    # Ciclo actual = cuántos ciclos completos de un mes ya pasaron desde fecha_inicio.
    delta = relativedelta(hoy, inscripcion.fecha_inicio)
    ciclo_actual = min(delta.years * 12 + delta.months, 60)  # tope de seguridad: 5 años

    # Ciclo (número) de cada periodo_inicio de la grilla automática, hasta el ciclo actual...
    ciclo_por_periodo = {
        inscripcion.fecha_inicio + relativedelta(months=c): c
        for c in range(0, ciclo_actual + 1)
    }
    # ...más cualquier cobro ya generado por adelantado que SÍ coincide con la grilla
    # (mismo día del mes que fecha_inicio), aunque esté más allá del ciclo actual.
    for periodo_inicio in cobros_existentes:
        if periodo_inicio in ciclo_por_periodo:
            continue
        n = relativedelta(periodo_inicio, inscripcion.fecha_inicio)
        ciclo_equivalente = n.years * 12 + n.months
        if inscripcion.fecha_inicio + relativedelta(months=ciclo_equivalente) == periodo_inicio:
            ciclo_por_periodo[periodo_inicio] = ciclo_equivalente

    # Unión cronológica de todo: grilla + cobros con fecha personalizada.
    todos_los_periodos = sorted(set(ciclo_por_periodo) | set(cobros_existentes))

    resultado = []
    bloqueado_por = None  # etiqueta del primer mes abierto encontrado, en orden cronológico
    for periodo_inicio in todos_los_periodos:
        ciclo = ciclo_por_periodo.get(periodo_inicio)
        personalizado = ciclo is None
        cobro = cobros_existentes.get(periodo_inicio)
        periodo_fin = cobro.periodo_fin if cobro else periodo_inicio + relativedelta(months=1)
        etiqueta = f'{MESES_ES[periodo_inicio.month]} {periodo_inicio.year}'

        resultado.append({
            'ciclo':           ciclo,
            'etiqueta':        etiqueta + (' (personalizado)' if personalizado else ''),
            'periodo_inicio':  periodo_inicio.isoformat(),
            'periodo_fin':     periodo_fin.isoformat(),
            'es_actual':       ciclo == ciclo_actual,
            'personalizado':   personalizado,
            'cobro':           _serializar_cobro_resumen(cobro) if cobro else None,
            'bloqueado_por':   bloqueado_por,
        })

        if cobro and cobro.estado in ESTADOS_ABIERTOS and bloqueado_por is None:
            bloqueado_por = etiqueta
    return resultado


def calendario_pagos_diario(inscripcion, anio, mes):
    """
    Arma el calendario de un mes calendario (1-31) para una inscripción con
    modalidad "diaria", con el estado del cobro de cada día que ya tiene uno.
    Los días sin Cobro (fin de semana, no asistió, o día futuro) llegan con
    cobro=None; la UI decide cómo pintarlos (no es un bug, es esperado: el
    cobro diario solo nace cuando se marca asistencia presente).

    Igual que en la vista mensual, cada día trae `bloqueado_por`: la fecha
    del primer día abierto (pendiente/parcial/vencido) de TODA la
    inscripción, sin importar si cae en un mes anterior al que se está
    mirando — el orden de cierre es global, no por mes calendario.
    """
    primer_dia    = date(anio, mes, 1)
    ultimo_dia_n  = calendar.monthrange(anio, mes)[1]
    ultimo_dia    = date(anio, mes, ultimo_dia_n)

    cobros_existentes = {
        c.fecha_vencimiento: c
        for c in Cobro.objects.filter(
            inscripcion=inscripcion, tipo=Cobro.TIPO_DIARIO,
            fecha_vencimiento__gte=primer_dia, fecha_vencimiento__lte=ultimo_dia,
        ).select_related('registrado_por').prefetch_related('pagos', 'pagos__registrado_por', 'devoluciones', 'devoluciones__registrado_por')
    }

    primer_abierto = Cobro.objects.filter(
        inscripcion=inscripcion, tipo=Cobro.TIPO_DIARIO, estado__in=ESTADOS_ABIERTOS,
    ).order_by('fecha_vencimiento').first()

    dias = []
    for n in range(1, ultimo_dia_n + 1):
        dia = date(anio, mes, n)
        cobro = cobros_existentes.get(dia)
        bloqueado_por = None
        if (cobro and cobro.estado in ESTADOS_ABIERTOS
                and primer_abierto and cobro.id != primer_abierto.id):
            bloqueado_por = primer_abierto.fecha_vencimiento.isoformat()
        dias.append({
            'dia':          n,
            'fecha':        dia.isoformat(),
            'dia_semana':   dia.weekday(),  # 0=lunes ... 6=domingo
            'cobro':        _serializar_cobro_resumen(cobro) if cobro else None,
            'bloqueado_por': bloqueado_por,
        })
    return {'anio': anio, 'mes': mes, 'etiqueta': f'{MESES_ES[mes]} {anio}', 'dias': dias}
