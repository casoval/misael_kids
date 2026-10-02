"""
inscripciones/services.py

Lógica de generación de cobros de mensualidad, centralizada para que se
comporte igual sin importar desde dónde se dispare: creación de una
inscripción nueva, una transferencia, o la generación manual/masiva.
"""
import calendar
from datetime import date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from django.db import IntegrityError, transaction, models
from django.db.models import Count, Q, Sum

from .models import Cobro, Pago, Devolucion, Inscripcion, AbonoDiario, DiasContratados

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
            cobro = Cobro.objects.create(
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
            # Si la cuenta del niño tiene saldo a favor (p. ej. lo que sobró
            # al cambiar a un turno más barato), cubre el ciclo nuevo solo.
            # Sin saldo no hace nada: el comportamiento de siempre.
            if saldo_a_favor(inscripcion) > 0:
                aplicar_saldo(inscripcion, cobros=[cobro])
            return cobro
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
        'monto_condonado_inicial': (
            str(cobro.monto_condonado_inicial) if cobro.monto_condonado_inicial is not None else None
        ),
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


# ══════════════════════════════════════════════════════════════════════
# Modalidad "por día": saldo a favor (abonos), días contratados y traspasos
# ══════════════════════════════════════════════════════════════════════
CERO = Decimal('0')


def saldo_a_favor(inscripcion):
    """Dinero abonado que todavía no se aplicó a ningún cobro ni se devolvió."""
    ab = AbonoDiario.objects.filter(inscripcion=inscripcion).aggregate(t=Sum('monto'), d=Sum('devuelto'))
    aplicado = Pago.objects.filter(abono_origen__inscripcion=inscripcion).aggregate(t=Sum('monto'))['t'] or CERO
    return (ab['t'] or CERO) - aplicado - (ab['d'] or CERO)


class SaldoInsuficiente(ValueError):
    """Se intentó devolver más de lo que hay a favor (o un monto no válido)."""


@transaction.atomic
def devolver_saldo(inscripcion, monto, metodo_pago, motivo, usuario=None, fecha=None):
    """
    Devuelve en efectivo (o transferencia/QR) parte o todo el saldo a favor de
    la cuenta de un niño. Es la misma `Devolucion` de siempre, pero colgada de
    la inscripción en vez de un cobro: lleva su recibo, cuenta como egreso en
    caja y descuenta el saldo. Se descuenta de los abonos del más antiguo al
    más nuevo, para que ese dinero no se aplique después a ningún cobro.
    """
    monto = Decimal(str(monto))
    disponible = saldo_a_favor(inscripcion)
    if monto <= 0:
        raise SaldoInsuficiente('El monto a devolver debe ser mayor a cero.')
    if monto > disponible:
        raise SaldoInsuficiente(f'Solo hay {disponible} Bs. de saldo a favor para devolver.')
    dev = Devolucion.objects.create(
        inscripcion=inscripcion, cobro=None, monto=monto, metodo_pago=metodo_pago, motivo=motivo,
        registrado_por=usuario, fecha=fecha or date.today(),
    )
    asignar_numero_recibo(dev)
    restante = monto
    for abono in AbonoDiario.objects.filter(inscripcion=inscripcion).order_by('fecha_pago', 'created_at'):
        if restante <= 0:
            break
        tomar = min(restante, abono.monto_disponible)
        if tomar > 0:
            abono.devuelto += tomar
            abono.save(update_fields=['devuelto'])
            restante -= tomar
    return dev


def deuda_diaria(inscripcion):
    """Suma del saldo pendiente de los cobros diarios abiertos de la inscripción."""
    total = CERO
    for c in Cobro.objects.filter(
        inscripcion=inscripcion, tipo=Cobro.TIPO_DIARIO, estado__in=ESTADOS_ABIERTOS
    ).prefetch_related('pagos', 'devoluciones'):
        total += c.saldo_pendiente
    return total


def _sincronizar_ultimo_pago(cobro):
    """Refleja en el propio Cobro el último pago (compatibilidad con reportes)."""
    ultimo = cobro.pagos.order_by('-fecha_pago', '-created_at').first()
    cobro.fecha_pago  = ultimo.fecha_pago if ultimo else None
    cobro.metodo_pago = ultimo.metodo_pago if ultimo else ''
    cobro.save(update_fields=['fecha_pago', 'metodo_pago'])


@transaction.atomic
def aplicar_saldo(inscripcion, cobros=None):
    """
    Cubre cobros abiertos con el saldo a favor (abonos) de `inscripcion`,
    del cobro más antiguo al más nuevo y del abono más antiguo al más nuevo.
    Cada cobro cubierto recibe un `Pago` con `abono_origen` (sin recibo
    propio y sin sumar a caja: el dinero ya entró con el abono).

    - cobros=None → los cobros diarios abiertos de la propia inscripción.
    - cobros=[...] → esos cobros (se usa al pasar a mensualidad, para
      aplicar el saldo a la primera mensualidad de la inscripción nueva).

    Es solo aditiva: nunca reordena ni borra aplicaciones ya hechas (eso
    solo ocurre al anular un cobro, ver `liberar_aplicaciones`). Devuelve
    el monto total aplicado.
    """
    if cobros is None:
        cobros = Cobro.objects.filter(
            inscripcion=inscripcion, tipo=Cobro.TIPO_DIARIO, estado__in=ESTADOS_ABIERTOS,
        ).order_by('fecha_vencimiento', 'created_at')
    cobros = [c for c in cobros if c.estado in ESTADOS_ABIERTOS]
    if not cobros:
        return CERO

    abonos = [a for a in AbonoDiario.objects.filter(inscripcion=inscripcion).order_by('fecha_pago', 'created_at')
              if a.monto_disponible > 0]
    total = CERO
    for cobro in cobros:
        cobro.refresh_from_db()
        if cobro.estado not in ESTADOS_ABIERTOS:
            continue
        aplicado_a_este = False
        for abono in abonos:
            falta = cobro.saldo_pendiente
            if falta <= 0:
                break
            usable = abono.monto_disponible
            if usable <= 0:
                continue
            monto = min(falta, usable)
            Pago.objects.create(
                cobro=cobro, monto=monto, abono_origen=abono,
                # Fecha en que el día quedó efectivamente cubierto: el día mismo
                # (o hoy si es futuro) o la fecha del abono, lo que sea posterior.
                fecha_pago=max(abono.fecha_pago, min(cobro.fecha_vencimiento, date.today())),
                metodo_pago=abono.metodo_pago, registrado_por=abono.registrado_por,
                observacion=f'Aplicado del abono del {abono.fecha_pago:%d/%m/%Y}'
                            + (f' (recibo N° {abono.numero_recibo})' if abono.numero_recibo else ''),
            )
            total += monto
            aplicado_a_este = True
        if aplicado_a_este:
            _sincronizar_ultimo_pago(cobro)
            cobro.recalcular_estado()
    return total


@transaction.atomic
def liberar_aplicaciones(cobro):
    """
    Devuelve al saldo a favor lo que se había aplicado a `cobro` desde
    abonos (se usa al anular un cobro diario, p. ej. cuando una falta pasa
    a "justificada"). No toca pagos reales. Devuelve el monto liberado.
    """
    aplicaciones = cobro.pagos.filter(abono_origen__isnull=False)
    liberado = aplicaciones.aggregate(t=Sum('monto'))['t'] or CERO
    aplicaciones.delete()
    if liberado > 0:
        _sincronizar_ultimo_pago(cobro)
    return liberado


def dias_contratados_total(inscripcion):
    total = 0
    for d in inscripcion.dias_contratados.all():
        total += -d.cantidad if d.tipo == DiasContratados.TIPO_REDUCCION else d.cantidad
    return total


def registrar_dias_contratados(inscripcion, cantidad, tipo=None, nota='', usuario=None, fecha=None):
    """
    Anota días acordados. Si no se indica `tipo`: 'inicial' cuando es la
    primera vez y 'ampliacion' en adelante.
    """
    if tipo is None:
        tipo = (DiasContratados.TIPO_AMPLIACION if inscripcion.dias_contratados.exists()
                else DiasContratados.TIPO_INICIAL)
    return DiasContratados.objects.create(
        inscripcion=inscripcion, tipo=tipo, cantidad=cantidad, nota=nota,
        registrado_por=usuario, fecha=fecha or date.today(),
    )


def resumen_diario(inscripcion):
    """
    Estado de cuenta de una inscripción "por día": saldo a favor, deuda,
    días contratados (con su historial) frente a días cobrados, y alertas.
    """
    from asistencia.models import Asistencia

    asist = Asistencia.objects.filter(inscripcion=inscripcion)
    presentes    = asist.filter(estado=Asistencia.ESTADO_PRESENTE).count()
    justificados = asist.filter(estado=Asistencia.ESTADO_AUSENTE_JUSTIFICADO).count()
    ausentes     = asist.filter(estado=Asistencia.ESTADO_AUSENTE).count()
    cobrados = Cobro.objects.filter(inscripcion=inscripcion, tipo=Cobro.TIPO_DIARIO).exclude(
        estado=Cobro.ESTADO_ANULADO).count()
    ausentes_cobrados = max(cobrados - presentes, 0)

    contratados = dias_contratados_total(inscripcion)
    saldo = saldo_a_favor(inscripcion)
    deuda = deuda_diaria(inscripcion)
    costo = Decimal(str(inscripcion.costo_diario_final))
    abonado = AbonoDiario.objects.filter(inscripcion=inscripcion).aggregate(t=Sum('monto'))['t'] or CERO

    alertas = []
    if contratados > 0:
        if cobrados > contratados:
            alertas.append({'codigo': 'excedido', 'nivel': 'alto',
                            'mensaje': f'Ya se cobraron {cobrados} días y solo se acordaron {contratados}. '
                                       'Confirma con el tutor y registra la ampliación.'})
        elif cobrados == contratados:
            alertas.append({'codigo': 'completo', 'nivel': 'medio',
                            'mensaje': f'Se completaron los {contratados} días acordados. '
                                       'El próximo día que asista excederá lo acordado.'})
    if deuda > 0:
        alertas.append({'codigo': 'deuda', 'nivel': 'alto',
                        'mensaje': f'Hay días cobrados sin cubrir por Bs. {deuda}.'})
    elif abonado > 0 and saldo <= 0:
        alertas.append({'codigo': 'saldo_agotado', 'nivel': 'medio',
                        'mensaje': 'El saldo a favor se agotó; el próximo día quedará pendiente de pago.'})

    return {
        'saldo_a_favor': saldo,
        'deuda': deuda,
        'abonado_total': abonado,
        'costo_diario': costo,
        'dias_que_cubre_el_saldo': int(saldo // costo) if costo and costo > 0 else None,
        'dias_contratados': {
            'total': contratados,
            'cobrados': cobrados,
            'restantes': contratados - cobrados,
            'historial': [{
                'id': str(d.id), 'tipo': d.tipo, 'tipo_display': d.get_tipo_display(),
                'cantidad': d.cantidad, 'fecha': d.fecha.isoformat(), 'nota': d.nota,
                'registrado_por': d.registrado_por.nombre_completo if d.registrado_por else None,
            } for d in inscripcion.dias_contratados.select_related('registrado_por')],
        },
        'asistencia': {
            'presentes': presentes, 'ausentes_sin_aviso': ausentes,
            'ausentes_cobrados': ausentes_cobrados, 'justificados': justificados,
        },
        'abonos': [{
            'id': str(a.id), 'monto': a.monto, 'fecha_pago': a.fecha_pago.isoformat(),
            'metodo_pago': a.get_metodo_pago_display(), 'numero_recibo': a.numero_recibo,
            'aplicado': a.monto_aplicado, 'devuelto': a.devuelto, 'disponible': a.monto_disponible,
            'observacion': a.observacion,
        } for a in inscripcion.abonos.all()],
        'alertas': alertas,
    }


@transaction.atomic
def trasladar_cuenta_diaria(origen, destino, usuario=None):
    """
    Lleva la "cuenta" de una inscripción por día (`origen`) a la inscripción
    que la reemplaza (`destino`), al transferir o cambiar de modalidad.
    Devuelve un dict con lo que pasó, para mostrarlo en pantalla.

    - destino también por día  → los abonos pasan a `destino` (el saldo
      sigue siendo del niño) y los días acordados que no se consumieron se
      anotan como días iniciales de la nueva inscripción.
    - destino mensual → el saldo a favor se aplica a la primera mensualidad
      ya generada de `destino`; lo que sobre queda en `origen`.
    Los cobros y pagos de `origen` no se tocan: siguen siendo su historial.
    """
    resultado = {'saldo_aplicado': CERO, 'saldo_restante': CERO, 'dias_trasladados': 0}
    if origen.modalidad_pago != Inscripcion.MODALIDAD_DIARIA:
        mover_saldo_disponible(origen, destino)
        resultado['saldo_restante'] = saldo_a_favor(destino)
        return resultado

    if destino.modalidad_pago == Inscripcion.MODALIDAD_DIARIA:
        AbonoDiario.objects.filter(inscripcion=origen).update(inscripcion=destino)
        restantes = resumen_diario(origen)['dias_contratados']['restantes']
        if restantes > 0:
            registrar_dias_contratados(
                destino, restantes, tipo=DiasContratados.TIPO_INICIAL, usuario=usuario,
                nota='Días acordados que quedaban al transferir la inscripción.')
            resultado['dias_trasladados'] = restantes
        resultado['saldo_restante'] = saldo_a_favor(destino)
        return resultado

    primer_cobro = Cobro.objects.filter(
        inscripcion=destino, tipo=Cobro.TIPO_MENSUALIDAD, estado__in=ESTADOS_ABIERTOS
    ).order_by('periodo_inicio').first()
    if primer_cobro and saldo_a_favor(origen) > 0:
        resultado['saldo_aplicado'] = aplicar_saldo(origen, cobros=[primer_cobro])
    # Lo que sobre sigue siendo del niño: pasa a la cuenta de la inscripción
    # mensual y cubrirá sus próximas mensualidades.
    mover_saldo_disponible(origen, destino)
    resultado['saldo_restante'] = saldo_a_favor(destino)
    return resultado


def mover_saldo_disponible(origen, destino):
    """
    Pasa a `destino` los abonos de `origen` que aún tienen saldo sin usar
    (junto con lo que ya se aplicó de ellos, para que las cuentas cuadren).
    Devuelve cuántos abonos se movieron.
    """
    movidos = 0
    for abono in AbonoDiario.objects.filter(inscripcion=origen):
        if abono.monto_disponible > 0:
            abono.inscripcion = destino
            abono.save(update_fields=['inscripcion'])
            movidos += 1
    return movidos


@transaction.atomic
def trasladar_saldo_del_nino(nueva, usuario=None):
    """
    Un niño que se da de baja y vuelve más adelante tiene una inscripción
    nueva: el saldo a favor que dejó en inscripciones cerradas pasa a la
    nueva (y, si es mensual, cubre su primer ciclo). Devuelve el monto de
    saldo que quedó en la cuenta de la inscripción nueva.
    """
    cerradas = Inscripcion.objects.filter(nino=nueva.nino, activa=False).exclude(pk=nueva.pk)
    for vieja in cerradas:
        mover_saldo_disponible(vieja, nueva)
    if nueva.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL and saldo_a_favor(nueva) > 0:
        primer = Cobro.objects.filter(
            inscripcion=nueva, tipo=Cobro.TIPO_MENSUALIDAD, estado__in=ESTADOS_ABIERTOS
        ).order_by('periodo_inicio').first()
        if primer:
            aplicar_saldo(nueva, cobros=[primer])
    return saldo_a_favor(nueva)


def deuda_abierta(inscripcion):
    """Suma del saldo pendiente de TODOS los cobros abiertos de la inscripción."""
    total = CERO
    for c in Cobro.objects.filter(inscripcion=inscripcion, estado__in=ESTADOS_ABIERTOS
                                  ).prefetch_related('pagos', 'devoluciones'):
        total += c.saldo_pendiente
    return total


# ══════════════════════════════════════════════════════════════════════
# Cambio de turno / sala / sucursal en una mensualidad: el ciclo en curso
# continúa y solo se compensa la diferencia de precio
# ══════════════════════════════════════════════════════════════════════
def ciclo_vigente(inscripcion, fecha):
    """La mensualidad (no anulada) de `inscripcion` cuyo período contiene `fecha`."""
    return Cobro.objects.filter(
        inscripcion=inscripcion, tipo=Cobro.TIPO_MENSUALIDAD,
        periodo_inicio__lte=fecha, periodo_fin__gt=fecha,
    ).exclude(estado=Cobro.ESTADO_ANULADO).order_by('periodo_inicio').first()


def calcular_ajuste_precio(cobro, nuevo_final):
    """
    Qué pasa con un cobro ya (parcial o totalmente) pagado si su monto
    cambia a `nuevo_final`. No escribe nada.
      - igual precio → no cambia nada.
      - cuesta menos y sobra dinero → `a_favor` pasa a la cuenta del niño.
      - cuesta más o falta → `por_cobrar` es lo que queda por pagar.
      - un cobro ya cerrado con "cerrar con lo pagado" se respeta tal cual.
    """
    nuevo_final = Decimal(str(nuevo_final))
    base = {'monto_actual': cobro.monto_final, 'monto_nuevo': nuevo_final,
            'pagado': cobro.monto_pagado, 'a_favor': CERO, 'por_cobrar': CERO}
    if cobro.monto_condonado_inicial is not None:
        return {**base, 'cambia': False, 'motivo': 'cerrado_con_lo_pagado', 'monto_nuevo': cobro.monto_final}
    if nuevo_final == cobro.monto_final:
        # Mismo precio: no hay nada que compensar, pero lo que falte pagar sigue
        # siendo `por_cobrar` (por si se pide cerrar el ciclo con lo pagado).
        return {**base, 'cambia': False, 'motivo': 'mismo_precio',
                'por_cobrar': max(cobro.monto_final - cobro.monto_pagado, CERO)}
    pagado = cobro.monto_pagado
    return {**base, 'cambia': True, 'motivo': 'precio_distinto',
            'a_favor': max(pagado - nuevo_final, CERO),
            'por_cobrar': max(nuevo_final - pagado, CERO)}


@transaction.atomic
def reajustar_cobro_por_cambio_precio(cobro, nueva, usuario=None, cerrar_con_lo_pagado=False, motivo_cierre=''):
    """
    Pasa un cobro al precio de la inscripción `nueva` y compensa la diferencia
    contra lo ya pagado:
      - sobra dinero  → queda en la cuenta del niño (Devolucion a_cuenta +
        AbonoDiario es_traspaso: ninguno toca la caja);
      - falta dinero  → el cobro queda parcial por la diferencia, o se cierra
        con lo pagado si así se pide (con motivo).
    Devuelve el mismo dict de `calcular_ajuste_precio`.
    """
    plan = calcular_ajuste_precio(cobro, nueva.costo_mensual_final)
    if plan['cambia']:
        cobro.monto_base  = nueva.costo_mensual
        cobro.monto_final = plan['monto_nuevo']
        cobro.save(update_fields=['monto_base', 'monto_final'])

    if plan['a_favor'] > 0:
        Devolucion.objects.create(
            cobro=cobro, monto=plan['a_favor'], a_cuenta=True, registrado_por=usuario,
            motivo='Cambio de turno/sala: la diferencia de precio pasa a la cuenta del niño.')
        AbonoDiario.objects.create(
            inscripcion=nueva, monto=plan['a_favor'], es_traspaso=True, registrado_por=usuario,
            observacion=f'Sobrante del ciclo {etiqueta_periodo(cobro)} al cambiar a un precio menor.')
    cobro.refresh_from_db()
    if plan['cambia']:
        cobro.recalcular_estado()

    if cerrar_con_lo_pagado and plan['por_cobrar'] > 0:
        cobro.refresh_from_db()
        cobro.monto_condonado         = cobro.saldo_pendiente
        cobro.monto_condonado_inicial = cobro.saldo_pendiente
        cobro.motivo_condonacion      = motivo_cierre
        cobro.registrado_por          = usuario
        cobro.save(update_fields=['monto_condonado', 'monto_condonado_inicial',
                                  'motivo_condonacion', 'registrado_por'])
        cobro.recalcular_estado()
        plan['cerrado_con_lo_pagado'] = True
        plan['condonado'] = cobro.monto_condonado
    cobro.refresh_from_db()
    plan['estado'] = cobro.estado
    return plan


@transaction.atomic
def continuar_ciclos_en_inscripcion_nueva(actual, nueva, fecha, usuario=None,
                                          cerrar_con_lo_pagado=False, motivo_cierre=''):
    """
    Mensual → mensual: el ciclo en curso (y los ya generados por adelantado)
    pasan a la inscripción `nueva`, que se ancla a su fecha de inicio para
    que los ciclos siguientes queden alineados. Solo se corrige la diferencia
    de precio (ver `reajustar_cobro_por_cambio_precio`). Los ciclos
    anteriores se quedan en la inscripción cerrada como historial.
    Devuelve el plan aplicado, o None si no había ciclo en curso (en ese caso
    quien llama genera un ciclo nuevo como siempre).
    """
    vigente = ciclo_vigente(actual, fecha)
    if vigente is None:
        return None
    nueva.fecha_inicio = vigente.periodo_inicio     # ancla: los ciclos siguientes no se desfasan
    nueva.save(update_fields=['fecha_inicio'])

    ids = list(Cobro.objects.filter(
        inscripcion=actual, tipo=Cobro.TIPO_MENSUALIDAD, periodo_inicio__gte=vigente.periodo_inicio,
    ).exclude(estado=Cobro.ESTADO_ANULADO).values_list('pk', flat=True))
    Cobro.objects.filter(pk__in=ids).update(inscripcion=nueva)

    plan = reajustar_cobro_por_cambio_precio(
        Cobro.objects.get(pk=vigente.pk), nueva, usuario, cerrar_con_lo_pagado, motivo_cierre)
    plan['periodo_inicio'] = vigente.periodo_inicio
    plan['periodo_fin']    = vigente.periodo_fin

    # Ciclos futuros ya generados: si nadie pagó nada, pasan al precio nuevo.
    for futuro in Cobro.objects.filter(pk__in=ids).exclude(pk=vigente.pk):
        if not futuro.pagos.exists() and futuro.monto_condonado_inicial is None:
            futuro.monto_base, futuro.monto_final = nueva.costo_mensual, nueva.costo_mensual_final
            futuro.save(update_fields=['monto_base', 'monto_final'])
            futuro.recalcular_estado()
    # Si la cuenta ya tenía saldo a favor (de antes), cubre lo que haya quedado abierto.
    if saldo_a_favor(nueva) > 0:
        aplicar_saldo(nueva, cobros=list(Cobro.objects.filter(
            pk__in=ids, estado__in=ESTADOS_ABIERTOS).order_by('periodo_inicio')))
        plan['estado'] = Cobro.objects.get(pk=vigente.pk).estado
    return plan


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

    asistencias = {
        a.fecha: a.estado
        for a in inscripcion.asistencias.filter(fecha__gte=primer_dia, fecha__lte=ultimo_dia)
    }

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
            'esperado':     inscripcion.es_dia_esperado(dia),   # respeta inicio, fin y dias_semana
            'asistencia':   asistencias.get(dia),               # presente / ausente / ausente_justificado / None
            'cobro':        _serializar_cobro_resumen(cobro) if cobro else None,
            'bloqueado_por': bloqueado_por,
        })
    return {'anio': anio, 'mes': mes, 'etiqueta': f'{MESES_ES[mes]} {anio}', 'dias': dias}


def resumen_financiero(anio, mes, sucursal=None):
    """
    Caja y cartera de un mes (la misma contabilidad que muestran las tarjetas
    de Cobros y que usan los Reportes, para que nunca den números distintos).
    - pendiente: saldo por cobrar de todos los cobros abiertos (pendiente,
      parcial o vencido), NO anulados, ya descontando pagos, devoluciones y
      condonado. Incluye a los vencidos.
    - vencido: la parte de lo pendiente cuyo vencimiento ya pasó.
    - caja_mes: pagos con fecha del mes - devoluciones con fecha del mes.
    """
    hoy = date.today()
    cobros = Cobro.objects.all()
    # Los pagos con abono_origen son aplicaciones de un abono (dinero que ya
    # entró a caja el día del abono): no se cuentan dos veces.
    pagos  = Pago.objects.filter(fecha_pago__year=anio, fecha_pago__month=mes, abono_origen__isnull=True)
    # Un abono con es_traspaso o una devolución a_cuenta son movimientos
    # internos (el dinero no entra ni sale de caja): no se cuentan.
    abonos = AbonoDiario.objects.filter(fecha_pago__year=anio, fecha_pago__month=mes, es_traspaso=False)
    devs   = Devolucion.objects.filter(fecha__year=anio, fecha__month=mes, a_cuenta=False)
    if sucursal:
        cobros = cobros.filter(inscripcion__sucursal=sucursal)
        pagos  = pagos.filter(cobro__inscripcion__sucursal=sucursal)
        abonos = abonos.filter(inscripcion__sucursal=sucursal)
        devs   = devs.filter(Q(cobro__inscripcion__sucursal=sucursal) | Q(inscripcion__sucursal=sucursal))

    cero = Decimal('0')
    pend_monto = venc_monto = cero
    pend_n = venc_n = 0
    abiertos = cobros.filter(estado__in=ESTADOS_ABIERTOS).prefetch_related('pagos', 'devoluciones')
    for c in abiertos:
        pagado = sum((p.monto for p in c.pagos.all()), cero) - sum((d.monto for d in c.devoluciones.all()), cero)
        saldo = c.monto_final - pagado - c.monto_condonado
        if saldo <= 0:
            continue
        pend_monto += saldo
        pend_n += 1
        if c.fecha_vencimiento < hoy:
            venc_monto += saldo
            venc_n += 1

    p = pagos.aggregate(total=Sum('monto'), n=Count('id'))
    ab = abonos.aggregate(total=Sum('monto'), n=Count('id'))
    p = {'total': (p['total'] or cero) + (ab['total'] or cero), 'n': p['n'] + ab['n']}
    d = devs.aggregate(total=Sum('monto'), n=Count('id'))
    total_pagos = p['total'] or cero
    total_devs  = d['total'] or cero
    condonado = cobros.filter(
        monto_condonado__gt=0, fecha_pago__year=anio, fecha_pago__month=mes,
    ).aggregate(t=Sum('monto_condonado'))['t'] or cero

    return {
        'mes': f'{anio:04d}-{mes:02d}',
        'pendiente': {'monto': pend_monto, 'cantidad': pend_n},
        'vencido':   {'monto': venc_monto, 'cantidad': venc_n},
        'caja_mes': {
            'ingresos':            total_pagos,
            'cantidad_pagos':      p['n'],
            'devoluciones':        total_devs,
            'cantidad_devoluciones': d['n'],
            'neto':                total_pagos - total_devs,
            'condonado':           condonado,
        },
    }
