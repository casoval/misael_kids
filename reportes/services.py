"""
reportes/services.py
Cálculos y exportaciones de los reportes.

Todo se calcula en el SERVIDOR. Antes la pantalla armaba los reportes en el
navegador pidiendo listas por API: además de romperse por la paginación (solo
llegaban 25 registros), los totales no coincidían con los de Cobros y el filtro
de sucursal no se aplicaba a nada.
"""
import csv
from datetime import date
from decimal import Decimal

from django.db.models import Count, Q

from asistencia.models import Asistencia
from core.models import Sala
from inscripciones.models import Cobro, Inscripcion
from inscripciones.services import resumen_financiero
from inventario.models import ItemInventario

CERO = Decimal('0')


# ══════════════════════════════════════════════════════════════════
#  RESUMEN (tarjetas y gráficos)
# ══════════════════════════════════════════════════════════════════
def _pct(parte, total):
    return round(parte * 100 / total, 1) if total else None


def resumen_asistencia(anio, mes, sucursal=None):
    qs = Asistencia.objects.filter(fecha__year=anio, fecha__month=mes)
    if sucursal:
        qs = qs.filter(inscripcion__sucursal=sucursal)
    filas = qs.values('inscripcion__sala', 'inscripcion__sala__nombre').annotate(
        total=Count('id'),
        presentes=Count('id', filter=Q(estado=Asistencia.ESTADO_PRESENTE)),
        ausentes=Count('id', filter=Q(estado=Asistencia.ESTADO_AUSENTE)),
        justificados=Count('id', filter=Q(estado=Asistencia.ESTADO_AUSENTE_JUSTIFICADO)),
    ).order_by('inscripcion__sala__nombre')
    por_sala = [{
        'sala': str(f['inscripcion__sala']), 'sala_nombre': f['inscripcion__sala__nombre'],
        'total': f['total'], 'presentes': f['presentes'],
        'ausentes': f['ausentes'], 'justificados': f['justificados'],
        'porcentaje': _pct(f['presentes'], f['total']),
    } for f in filas]
    total = sum(f['total'] for f in por_sala)
    presentes = sum(f['presentes'] for f in por_sala)
    return {
        'total': total, 'presentes': presentes,
        'ausentes': sum(f['ausentes'] for f in por_sala),
        'justificados': sum(f['justificados'] for f in por_sala),
        'porcentaje': _pct(presentes, total),
        'por_sala': por_sala,
    }


def resumen_ocupacion(sucursal=None):
    """Niños con inscripción activa frente a la capacidad de cada sala activa."""
    salas = Sala.objects.filter(activa=True).select_related('sucursal').order_by('sucursal__nombre', 'nombre')
    inscritos_qs = Inscripcion.objects.filter(activa=True)
    if sucursal:
        salas = salas.filter(sucursal=sucursal)
        inscritos_qs = inscritos_qs.filter(sucursal=sucursal)
    inscritos = {f['sala']: f['n'] for f in inscritos_qs.values('sala').annotate(n=Count('id'))}
    por_sala = []
    for s in salas:
        n = inscritos.get(s.id, 0)
        por_sala.append({
            'sala': str(s.id), 'sala_nombre': s.nombre, 'sucursal_nombre': s.sucursal.nombre,
            'inscritos': n, 'capacidad': s.capacidad_maxima, 'porcentaje': _pct(n, s.capacidad_maxima),
        })
    ins  = sum(x['inscritos'] for x in por_sala)
    cap  = sum(x['capacidad'] for x in por_sala)
    return {'inscritos': ins, 'capacidad': cap, 'porcentaje': _pct(ins, cap), 'por_sala': por_sala}


def resumen_cobros_del_mes(anio, mes, sucursal=None):
    """
    Cobros EMITIDOS en el mes. Los montos excluyen los anulados y descuentan
    lo condonado: `cobrado` es lo efectivamente pagado (menos devoluciones)
    y `saldo` lo que aún falta, así que emitido = cobrado + condonado + saldo.
    """
    qs = Cobro.objects.filter(fecha_emision__year=anio, fecha_emision__month=mes)
    if sucursal:
        qs = qs.filter(inscripcion__sucursal=sucursal)
    por_estado = {e: {'cantidad': 0, 'monto': CERO} for e, _ in Cobro.ESTADOS}
    emitido = cobrado = condonado = saldo = CERO
    for c in qs.prefetch_related('pagos', 'devoluciones'):
        por_estado[c.estado]['cantidad'] += 1
        por_estado[c.estado]['monto']    += c.monto_final
        if c.estado == Cobro.ESTADO_ANULADO:
            continue
        pagado = sum((p.monto for p in c.pagos.all()), CERO) - sum((d.monto for d in c.devoluciones.all()), CERO)
        emitido   += c.monto_final
        condonado += c.monto_condonado
        cobrado   += pagado
        saldo     += max(c.monto_final - pagado - c.monto_condonado, CERO)
    base = emitido - condonado
    return {
        'cantidad': sum(v['cantidad'] for v in por_estado.values()),
        'por_estado': por_estado,
        'emitido': emitido, 'cobrado': cobrado, 'condonado': condonado, 'saldo': saldo,
        'porcentaje_cobrado': _pct(cobrado, base) if base > 0 else None,
    }


def resumen_general(anio, mes, sucursal=None):
    return {
        'mes': f'{anio:04d}-{mes:02d}',
        'sucursal': str(sucursal) if sucursal else None,
        'asistencia': resumen_asistencia(anio, mes, sucursal),
        'ocupacion':  resumen_ocupacion(sucursal),
        'cobros_mes': resumen_cobros_del_mes(anio, mes, sucursal),
        'caja':       resumen_financiero(anio, mes, sucursal),
    }


# ══════════════════════════════════════════════════════════════════
#  EXPORTACIONES CSV
# ══════════════════════════════════════════════════════════════════
_INICIOS_PELIGROSOS = ('=', '+', '-', '@', '\t', '\r')


def celda(valor):
    """
    Valor listo para escribir en un CSV.
    - Los textos que empiezan con = + - @ (o tab/CR) se prefijan con ' para que
      Excel/Sheets no los ejecute como fórmula (un niño llamado "=HYPERLINK(...)"
      sería una inyección de fórmulas). Los números no se tocan, así que los
      montos negativos siguen siendo números.
    - El escapado de comas, comillas y saltos de línea lo hace csv.writer; antes
      se armaba a mano con "…" y un nombre con comillas rompía toda la fila.
    """
    if valor is None:
        return ''
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if isinstance(valor, (int, float, Decimal)):
        return valor
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor)
    return "'" + texto if texto and texto[0] in _INICIOS_PELIGROSOS else texto


def _hora(t):
    return t.strftime('%H:%M') if t else ''


def export_asistencia(anio, mes, sucursal=None):
    qs = Asistencia.objects.filter(fecha__year=anio, fecha__month=mes).select_related(
        'inscripcion__nino', 'inscripcion__sala', 'inscripcion__turno', 'inscripcion__sucursal')
    if sucursal:
        qs = qs.filter(inscripcion__sucursal=sucursal)
    qs = qs.order_by('fecha', 'inscripcion__sala__nombre', 'inscripcion__nino__apellidos', 'inscripcion__nino__nombres')
    cabecera = ['Fecha', 'Niño', 'Sucursal', 'Sala', 'Turno', 'Estado', 'Hora entrada', 'Hora salida',
                'Entregó', 'Retiró', 'Retiro autorizado', 'Motivo de ausencia', 'Observación de entrada']

    def filas():
        for a in qs.iterator(chunk_size=500):
            i = a.inscripcion
            yield [a.fecha, i.nino.nombre_completo, i.sucursal.nombre, i.sala.nombre, i.turno.nombre,
                   a.get_estado_display(), _hora(a.hora_entrada), _hora(a.hora_salida),
                   a.entregado_por, a.retirado_por,
                   a.retiro_autorizado if a.retirado_por else None,
                   a.motivo_ausencia, a.obs_entrada]
    return f'asistencia_{anio:04d}-{mes:02d}.csv', cabecera, filas()


def export_cobros(anio, mes, sucursal=None):
    qs = Cobro.objects.filter(fecha_emision__year=anio, fecha_emision__month=mes).select_related(
        'inscripcion__nino', 'inscripcion__sala', 'inscripcion__sucursal').prefetch_related('pagos', 'devoluciones')
    if sucursal:
        qs = qs.filter(inscripcion__sucursal=sucursal)
    qs = qs.order_by('fecha_emision', 'inscripcion__nino__apellidos', 'inscripcion__nino__nombres')
    cabecera = ['Niño', 'Sucursal', 'Sala', 'Tipo', 'Período', 'Emisión', 'Vencimiento', 'Monto base',
                'Monto final', 'Pagado (neto)', 'Condonado', 'Saldo', 'Estado', 'Último método de pago', 'Fecha de último pago']

    def filas():
        for c in qs:
            i = c.inscripcion
            pagado = sum((p.monto for p in c.pagos.all()), CERO) - sum((d.monto for d in c.devoluciones.all()), CERO)
            saldo = CERO if c.estado == Cobro.ESTADO_ANULADO else max(c.monto_final - pagado - c.monto_condonado, CERO)
            yield [i.nino.nombre_completo, i.sucursal.nombre, i.sala.nombre, c.get_tipo_display(), c.periodo,
                   c.fecha_emision, c.fecha_vencimiento, c.monto_base, c.monto_final, pagado, c.monto_condonado,
                   saldo, c.get_estado_display(), c.get_metodo_pago_display() if c.metodo_pago else '', c.fecha_pago]
    return f'cobros_{anio:04d}-{mes:02d}.csv', cabecera, filas()


def export_ninos(anio, mes, sucursal=None):
    """Niños con inscripción activa (foto del momento: no depende del mes)."""
    qs = Inscripcion.objects.filter(activa=True).select_related(
        'nino', 'sala', 'turno', 'sucursal').prefetch_related('nino__tutores__tutor')
    if sucursal:
        qs = qs.filter(sucursal=sucursal)
    qs = qs.order_by('sucursal__nombre', 'sala__nombre', 'nino__apellidos', 'nino__nombres')
    cabecera = ['Nombres', 'Apellidos', 'Fecha de nacimiento', 'Edad (meses)', 'Género', 'Sucursal', 'Sala',
                'Turno', 'Modalidad de pago', 'Alergias', 'Plan Misael', 'Tutores (nombre · parentesco · teléfono)']

    def filas():
        for i in qs:
            n = i.nino
            tutores = ' | '.join(
                f'{t.tutor.nombres} {t.tutor.apellidos} · {t.tutor.get_parentesco_display()} · {t.tutor.telefono}'
                for t in sorted(n.tutores.all(), key=lambda x: not x.es_principal))
            yield [n.nombres, n.apellidos, n.fecha_nacimiento, n.edad_en_meses, n.get_genero_display(),
                   i.sucursal.nombre, i.sala.nombre, i.turno.nombre, i.get_modalidad_pago_display(),
                   n.alergias, n.tiene_plan_misael, tutores]
    return f'ninos_{date.today():%Y-%m-%d}.csv', cabecera, filas()


def export_inventario(anio, mes, sucursal=None):
    qs = ItemInventario.objects.filter(activo=True).select_related('sucursal')
    if sucursal:
        qs = qs.filter(sucursal=sucursal)
    qs = qs.order_by('sucursal__nombre', 'categoria', 'nombre')
    cabecera = ['Sucursal', 'Ítem', 'Categoría', 'Unidad', 'Stock actual', 'Stock mínimo', 'Stock bajo']

    def filas():
        for it in qs:
            yield [it.sucursal.nombre, it.nombre, it.get_categoria_display(), it.unidad,
                   it.stock_actual, it.stock_minimo, it.alerta_stock_bajo]
    return f'inventario_{date.today():%Y-%m-%d}.csv', cabecera, filas()


EXPORTADORES = {
    'asistencia': export_asistencia,
    'cobros':     export_cobros,
    'ninos':      export_ninos,
    'inventario': export_inventario,
}


def escribir_csv(respuesta, cabecera, filas):
    """CSV para Excel: BOM UTF-8 (tildes y ñ) y comillas/comas escapadas por csv.writer."""
    respuesta.write('\ufeff')
    w = csv.writer(respuesta, lineterminator='\r\n')
    w.writerow([celda(c) for c in cabecera])
    n = 0
    for fila in filas:
        w.writerow([celda(v) for v in fila])
        n += 1
    return n
