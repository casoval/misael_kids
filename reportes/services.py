"""
reportes/services.py
Cálculos y exportaciones de los reportes.

Todo se calcula en el SERVIDOR. Antes la pantalla armaba los reportes en el
navegador pidiendo listas por API: además de romperse por la paginación (solo
llegaban 25 registros), los totales no coincidían con los de Cobros y el filtro
de sucursal no se aplicaba a nada.
"""
import calendar
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from asistencia.models import Asistencia
from core.models import Sala
from inscripciones.models import AbonoDiario, Cobro, Devolucion, Inscripcion, Pago
from inscripciones.services import estado_pago, etiqueta_periodo, resumen_financiero, resumen_financiero_rango
from inventario.models import ItemInventario

CERO = Decimal('0')
MAX_DIAS = 366          # un reporte no puede abarcar más de un año

METODOS = [(k, v) for k, v in Cobro.METODOS_PAGO]      # efectivo, transferencia, QR
MESES_ES = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
            'septiembre', 'octubre', 'noviembre', 'diciembre']


# ══════════════════════════════════════════════════════════════════
#  PERÍODOS (un mes, un día o un rango de fechas)
# ══════════════════════════════════════════════════════════════════
def rango_mes(anio, mes):
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def es_mes_completo(desde, hasta):
    return (desde.day == 1 and (desde.year, desde.month) == (hasta.year, hasta.month)
            and hasta == rango_mes(desde.year, desde.month)[1])


def etiqueta_rango(desde, hasta):
    """'Octubre 2026', '02/10/2026' o '01/10/2026 al 15/10/2026'."""
    if es_mes_completo(desde, hasta):
        return f'{MESES_ES[desde.month].capitalize()} {desde.year}'
    if desde == hasta:
        return f'{desde:%d/%m/%Y}'
    return f'{desde:%d/%m/%Y} al {hasta:%d/%m/%Y}'


def sufijo_archivo(desde, hasta):
    if es_mes_completo(desde, hasta):
        return f'{desde:%Y-%m}'
    if desde == hasta:
        return f'{desde:%Y-%m-%d}'
    return f'{desde:%Y-%m-%d}_a_{hasta:%Y-%m-%d}'


def dias_del_rango(desde, hasta):
    return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]


# ══════════════════════════════════════════════════════════════════
#  RESUMEN (tarjetas y gráficos)
# ══════════════════════════════════════════════════════════════════
def _edad_anios(meses):
    """Edad en años y meses para los reportes: 14 -> '1 año y 2 meses'."""
    a, r = divmod(meses, 12)
    if a == 0:
        return 'menos de 1 año'
    anios = '1 año' if a == 1 else f'{a} años'
    return anios if not r else f'{anios} y {r} mes' + ('' if r == 1 else 'es')


def _pct(parte, total):
    return round(parte * 100 / total, 1) if total else None


def resumen_asistencia(desde, hasta, sucursal=None, sala=None):
    qs = Asistencia.objects.filter(fecha__gte=desde, fecha__lte=hasta)
    if sucursal:
        qs = qs.filter(inscripcion__sucursal=sucursal)
    if sala:
        qs = qs.filter(inscripcion__sala=sala)
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


def resumen_cobros_del_periodo(desde, hasta, sucursal=None):
    """
    Cobros EMITIDOS en el período. Los montos excluyen los anulados y descuentan
    lo condonado: `cobrado` es lo efectivamente pagado (menos devoluciones)
    y `saldo` lo que aún falta, así que emitido = cobrado + condonado + saldo.
    """
    qs = Cobro.objects.filter(fecha_emision__gte=desde, fecha_emision__lte=hasta)
    if sucursal:
        qs = qs.filter(inscripcion__sucursal=sucursal)
    por_estado = {e: {'cantidad': 0, 'monto': CERO} for e, _ in Cobro.ESTADOS}
    por_tipo = {t: {'cantidad': 0, 'emitido': CERO} for t, _ in Cobro.TIPOS}
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
        por_tipo[c.tipo]['cantidad'] += 1
        por_tipo[c.tipo]['emitido']  += c.monto_final
    base = emitido - condonado
    return {
        'cantidad': sum(v['cantidad'] for v in por_estado.values()),
        'por_estado': por_estado, 'por_tipo': por_tipo,
        'emitido': emitido, 'cobrado': cobrado, 'condonado': condonado, 'saldo': saldo,
        'porcentaje_cobrado': _pct(cobrado, base) if base > 0 else None,
    }


# ══════════════════════════════════════════════════════════════════
#  DEUDAS (la misma regla "al día" que bloquea el cambio de modalidad)
# ══════════════════════════════════════════════════════════════════
def listar_deudas(sucursal=None, sala=None):
    """
    Niños con inscripción activa que NO están al día, según el mismo estado de
    pago que muestra la lista de inscripciones: por día cuenta los días
    acordados o asistidos sin pagar (se cobra por adelantado), mensual cuenta
    las mensualidades vencidas o ya iniciadas sin pagar, y en ambos la deuda
    de una inscripción anterior ya cerrada.
    """
    qs = Inscripcion.objects.filter(activa=True).select_related('nino', 'sala', 'turno', 'sucursal')
    if sucursal:
        qs = qs.filter(sucursal=sucursal)
    if sala:
        qs = qs.filter(sala=sala)
    qs = qs.prefetch_related('nino__tutores__tutor').order_by(
        'sucursal__nombre', 'sala__nombre', 'nino__apellidos', 'nino__nombres')
    filas = []
    for i in qs:
        est = estado_pago(i)
        debe = (est or {}).get('deuda_total', CERO) or CERO
        if debe <= 0:
            continue
        tutores = sorted(i.nino.tutores.all(), key=lambda t: not t.es_principal)
        t = tutores[0].tutor if tutores else None
        filas.append({
            'inscripcion': str(i.id), 'nino': i.nino.nombre_completo, 'sucursal': i.sucursal.nombre,
            'sala': i.sala.nombre, 'turno': i.turno.nombre, 'modalidad': i.get_modalidad_pago_display(),
            'debe': debe, 'propia': est.get('falta_pagar', CERO), 'anterior': est.get('deuda_anterior', CERO),
            'detalle': est.get('mensaje', ''),
            'tutor': f'{t.nombres} {t.apellidos}' if t else '', 'telefono': t.telefono if t else '',
        })
    filas.sort(key=lambda f: f['debe'], reverse=True)
    return {'cantidad': len(filas), 'monto': sum((f['debe'] for f in filas), CERO), 'filas': filas}


def resumen_deudas(sucursal=None):
    d = listar_deudas(sucursal)
    return {'cantidad': d['cantidad'], 'monto': d['monto'], 'mayores': d['filas'][:5]}


# ══════════════════════════════════════════════════════════════════
#  CIERRE DE CAJA: cuánto debe quedar en efectivo, transferencia y QR
# ══════════════════════════════════════════════════════════════════
def movimientos_de_caja(desde, hasta, sucursal=None, usuario=None, metodo=None):
    """
    Cada movimiento REAL de dinero del período, ordenado por fecha y hora.
    Cuenta lo mismo que la caja de Cobros: pagos recibidos y abonos (el dinero
    entra el día del abono), menos devoluciones. NO cuenta la aplicación de un
    abono a un día (el dinero ya entró con el abono), ni los traspasos entre
    cuentas del mismo niño (es_traspaso / a_cuenta): no mueven la caja.
    """
    pagos = Pago.objects.filter(fecha_pago__gte=desde, fecha_pago__lte=hasta, abono_origen__isnull=True
                                ).select_related('cobro__inscripcion__nino', 'registrado_por')
    abonos = AbonoDiario.objects.filter(fecha_pago__gte=desde, fecha_pago__lte=hasta, es_traspaso=False
                                        ).select_related('inscripcion__nino', 'registrado_por')
    devs = Devolucion.objects.filter(fecha__gte=desde, fecha__lte=hasta, a_cuenta=False
                                     ).select_related('cobro__inscripcion__nino', 'inscripcion__nino', 'registrado_por')
    if sucursal:
        pagos = pagos.filter(cobro__inscripcion__sucursal=sucursal)
        abonos = abonos.filter(inscripcion__sucursal=sucursal)
        devs = devs.filter(Q(cobro__inscripcion__sucursal=sucursal) | Q(inscripcion__sucursal=sucursal))
    if usuario:
        pagos, abonos, devs = (q.filter(registrado_por=usuario) for q in (pagos, abonos, devs))
    if metodo:
        pagos, abonos, devs = (q.filter(metodo_pago=metodo) for q in (pagos, abonos, devs))

    def quien(o):
        return o.registrado_por.nombre_completo if o.registrado_por else 'Sin registrar'

    movs = []
    for p in pagos:
        c = p.cobro
        movs.append({'fecha': p.fecha_pago, 'creado': p.created_at, 'tipo': 'pago', 'tipo_display': 'Pago',
                     'recibo': p.numero_recibo, 'nino': c.inscripcion.nino.nombre_completo,
                     'concepto': f'{c.get_tipo_display()} · {etiqueta_periodo(c)}', 'metodo': p.metodo_pago,
                     'monto': p.monto, 'signo': 1, 'usuario_id': p.registrado_por_id, 'usuario': quien(p)})
    for a in abonos:
        movs.append({'fecha': a.fecha_pago, 'creado': a.created_at, 'tipo': 'abono', 'tipo_display': 'Abono',
                     'recibo': a.numero_recibo, 'nino': a.inscripcion.nino.nombre_completo,
                     'concepto': 'Abono a cuenta (por día)', 'metodo': a.metodo_pago,
                     'monto': a.monto, 'signo': 1, 'usuario_id': a.registrado_por_id, 'usuario': quien(a)})
    for d in devs:
        insc = d.cobro.inscripcion if d.cobro_id else d.inscripcion
        movs.append({'fecha': d.fecha, 'creado': d.created_at, 'tipo': 'devolucion', 'tipo_display': 'Devolución',
                     'recibo': d.numero_recibo, 'nino': insc.nino.nombre_completo,
                     'concepto': f'Devolución · {d.motivo}'[:80], 'metodo': d.metodo_pago,
                     'monto': d.monto, 'signo': -1, 'usuario_id': d.registrado_por_id, 'usuario': quien(d)})
    movs.sort(key=lambda m: (m['fecha'], m['creado']))
    return movs


def _bolsa():
    return {'ingresos': CERO, 'cantidad_ingresos': 0, 'devoluciones': CERO, 'cantidad_devoluciones': 0}


def _sumar(bolsa, m):
    if m['signo'] > 0:
        bolsa['ingresos'] += m['monto']
        bolsa['cantidad_ingresos'] += 1
    else:
        bolsa['devoluciones'] += m['monto']
        bolsa['cantidad_devoluciones'] += 1
    return bolsa


def _cerrar(bolsa):
    bolsa['neto'] = bolsa['ingresos'] - bolsa['devoluciones']
    return bolsa


def cierre_caja(desde, hasta, sucursal=None, usuario=None, metodo=None, con_detalle=False):
    """
    Cierre de caja del período. `metodos[*].neto` es lo que debe quedar en cada
    medio: efectivo (en la caja física), transferencia y QR (a verificar en el
    banco). Una devolución en efectivo resta del efectivo, no de los demás.
    """
    movs = movimientos_de_caja(desde, hasta, sucursal, usuario, metodo)
    claves = [k for k, _ in METODOS]
    extra = sorted({m['metodo'] for m in movs} - set(claves))     # por si hubiera un método antiguo
    etiquetas = dict(METODOS)
    por_metodo = {k: _bolsa() for k in claves + extra}
    total = _bolsa()
    por_dia, por_usuario = {}, {}
    for m in movs:
        _sumar(por_metodo[m['metodo']], m)
        _sumar(total, m)
        dia = por_dia.setdefault(m['fecha'], {'metodos': {k: _bolsa() for k in claves + extra}, 'total': _bolsa()})
        _sumar(dia['metodos'][m['metodo']], m)
        _sumar(dia['total'], m)
        u = por_usuario.setdefault(m['usuario_id'], {'id': m['usuario_id'], 'usuario': m['usuario'], 'metodos': {k: _bolsa() for k in claves + extra},
                                                      'total': _bolsa()})
        _sumar(u['metodos'][m['metodo']], m)
        _sumar(u['total'], m)

    metodos = [{'metodo': k, 'etiqueta': etiquetas.get(k, k.capitalize()), **_cerrar(b)} for k, b in por_metodo.items()]
    resultado = {
        'desde': desde.isoformat(), 'hasta': hasta.isoformat(),
        'sucursal': str(sucursal) if sucursal else None,
        'metodos': metodos,
        'a_dejar': {x['metodo']: x['neto'] for x in metodos},
        'total': _cerrar(total),
        'por_dia': [{'fecha': f.isoformat(), 'total': _cerrar(d['total']),
                     'metodos': {k: _cerrar(b)['neto'] for k, b in d['metodos'].items()}}
                    for f, d in sorted(por_dia.items())],
        'por_usuario': sorted(
            [{'usuario_id': str(u['id']) if u['id'] else None, 'usuario': u['usuario'], 'total': _cerrar(u['total']),
              'metodos': {k: _cerrar(b)['neto'] for k, b in u['metodos'].items()}} for u in por_usuario.values()],
            key=lambda u: u['usuario']),
    }
    if con_detalle:
        resultado['movimientos'] = movs
    return resultado


def resumen_general(desde, hasta, sucursal=None):
    return {
        'desde': desde.isoformat(), 'hasta': hasta.isoformat(),
        'mes': f'{desde:%Y-%m}' if es_mes_completo(desde, hasta) else None,
        'etiqueta': etiqueta_rango(desde, hasta),
        'sucursal': str(sucursal) if sucursal else None,
        'asistencia': resumen_asistencia(desde, hasta, sucursal),
        'ocupacion':  resumen_ocupacion(sucursal),
        'cobros_mes': resumen_cobros_del_periodo(desde, hasta, sucursal),
        # Un mes completo da EXACTAMENTE el mismo diccionario que la pantalla de Cobros.
        'caja':       (resumen_financiero(desde.year, desde.month, sucursal) if es_mes_completo(desde, hasta)
                       else resumen_financiero_rango(desde, hasta, sucursal)),
        'cierre':     cierre_caja(desde, hasta, sucursal),
        'deudas':     resumen_deudas(sucursal),
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


@dataclass
class Filtros:
    """Filtros que acepta cualquier reporte (los que no aplican a un reporte se ignoran)."""
    desde: date
    hasta: date
    sucursal: object = None      # UUID de la sucursal
    sala: object = None          # UUID de la sala
    estado: str = None           # estado del cobro (cobros) o de la asistencia (asistencia)
    tipo: str = None             # tipo de cobro: mensualidad / diario / extra
    usuario: object = None       # UUID de quien registró el dinero (cierre de caja)
    metodo: str = None           # efectivo / transferencia / qr (cierre de caja)

    @property
    def etiqueta(self):
        return etiqueta_rango(self.desde, self.hasta)

    @property
    def sufijo(self):
        return sufijo_archivo(self.desde, self.hasta)


def consulta_asistencia(f):
    qs = Asistencia.objects.filter(fecha__gte=f.desde, fecha__lte=f.hasta).select_related(
        'inscripcion__nino', 'inscripcion__sala', 'inscripcion__turno', 'inscripcion__sucursal')
    if f.sucursal:
        qs = qs.filter(inscripcion__sucursal=f.sucursal)
    if f.sala:
        qs = qs.filter(inscripcion__sala=f.sala)
    if f.estado:
        qs = qs.filter(estado=f.estado)
    return qs.order_by('fecha', 'inscripcion__sala__nombre', 'inscripcion__nino__apellidos', 'inscripcion__nino__nombres')


def consulta_cobros(f):
    qs = Cobro.objects.filter(fecha_emision__gte=f.desde, fecha_emision__lte=f.hasta).select_related(
        'inscripcion__nino', 'inscripcion__sala', 'inscripcion__sucursal').prefetch_related('pagos', 'devoluciones')
    if f.sucursal:
        qs = qs.filter(inscripcion__sucursal=f.sucursal)
    if f.sala:
        qs = qs.filter(inscripcion__sala=f.sala)
    if f.estado:
        qs = qs.filter(estado=f.estado)
    if f.tipo:
        qs = qs.filter(tipo=f.tipo)
    return qs.order_by('fecha_emision', 'inscripcion__nino__apellidos', 'inscripcion__nino__nombres')


def pagado_y_saldo(c):
    """(pagado neto de devoluciones, saldo que falta) de un cobro."""
    pagado = sum((p.monto for p in c.pagos.all()), CERO) - sum((d.monto for d in c.devoluciones.all()), CERO)
    saldo = CERO if c.estado == Cobro.ESTADO_ANULADO else max(c.monto_final - pagado - c.monto_condonado, CERO)
    return pagado, saldo


def consulta_ninos(f):
    """Niños con inscripción activa (foto del momento: no depende de las fechas)."""
    qs = Inscripcion.objects.filter(activa=True).select_related(
        'nino', 'sala', 'turno', 'sucursal').prefetch_related('nino__tutores__tutor')
    if f.sucursal:
        qs = qs.filter(sucursal=f.sucursal)
    if f.sala:
        qs = qs.filter(sala=f.sala)
    return qs.order_by('sucursal__nombre', 'sala__nombre', 'nino__apellidos', 'nino__nombres')


def consulta_inventario(f):
    qs = ItemInventario.objects.filter(activo=True).select_related('sucursal')
    if f.sucursal:
        qs = qs.filter(sucursal=f.sucursal)
    return qs.order_by('sucursal__nombre', 'categoria', 'nombre')


def export_asistencia(f):
    qs = consulta_asistencia(f)
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
    return f'asistencia_{f.sufijo}.csv', cabecera, filas()


def export_cobros(f):
    qs = consulta_cobros(f)
    cabecera = ['Niño', 'Sucursal', 'Sala', 'Tipo', 'Período', 'Emisión', 'Vencimiento', 'Monto base',
                'Monto final', 'Pagado (neto)', 'Condonado', 'Saldo', 'Estado', 'Último método de pago', 'Fecha de último pago']

    def filas():
        for c in qs:
            i = c.inscripcion
            pagado, saldo = pagado_y_saldo(c)
            yield [i.nino.nombre_completo, i.sucursal.nombre, i.sala.nombre, c.get_tipo_display(), c.periodo,
                   c.fecha_emision, c.fecha_vencimiento, c.monto_base, c.monto_final, pagado, c.monto_condonado,
                   saldo, c.get_estado_display(), c.get_metodo_pago_display() if c.metodo_pago else '', c.fecha_pago]
    return f'cobros_{f.sufijo}.csv', cabecera, filas()


def export_ninos(f):
    qs = consulta_ninos(f)
    cabecera = ['Nombres', 'Apellidos', 'Fecha de nacimiento', 'Edad (meses)', 'Edad (años)', 'Género', 'Sucursal', 'Sala',
                'Turno', 'Modalidad de pago', 'Alergias', 'Plan Misael', 'Tutores (nombre · parentesco · teléfono)']

    def filas():
        for i in qs:
            n = i.nino
            tutores = ' | '.join(
                f'{t.tutor.nombres} {t.tutor.apellidos} · {t.tutor.get_parentesco_display()} · {t.tutor.telefono}'
                for t in sorted(n.tutores.all(), key=lambda x: not x.es_principal))
            yield [n.nombres, n.apellidos, n.fecha_nacimiento, n.edad_en_meses, _edad_anios(n.edad_en_meses), n.get_genero_display(),
                   i.sucursal.nombre, i.sala.nombre, i.turno.nombre, i.get_modalidad_pago_display(),
                   n.alergias, n.tiene_plan_misael, tutores]
    return f'ninos_{date.today():%Y-%m-%d}.csv', cabecera, filas()


def export_inventario(f):
    qs = consulta_inventario(f)
    cabecera = ['Sucursal', 'Ítem', 'Categoría', 'Unidad', 'Stock actual', 'Stock mínimo', 'Stock bajo']

    def filas():
        for it in qs:
            yield [it.sucursal.nombre, it.nombre, it.get_categoria_display(), it.unidad,
                   it.stock_actual, it.stock_minimo, it.alerta_stock_bajo]
    return f'inventario_{date.today():%Y-%m-%d}.csv', cabecera, filas()


def export_deudas(f):
    d = listar_deudas(f.sucursal, f.sala)
    cabecera = ['Niño', 'Sucursal', 'Sala', 'Turno', 'Modalidad', 'Debe (total)', 'De la inscripción actual',
                'De una inscripción anterior', 'Tutor', 'Teléfono', 'Detalle']

    def filas():
        for x in d['filas']:
            yield [x['nino'], x['sucursal'], x['sala'], x['turno'], x['modalidad'], x['debe'], x['propia'],
                   x['anterior'], x['tutor'], x['telefono'], x['detalle']]
    return f'deudas_{date.today():%Y-%m-%d}.csv', cabecera, filas()


def export_cierre_caja(f):
    cierre = cierre_caja(f.desde, f.hasta, f.sucursal, f.usuario, f.metodo, con_detalle=True)
    nombres = dict(METODOS)
    cabecera = ['Fecha', 'Hora', 'Tipo', 'Recibo', 'Niño', 'Concepto', 'Método', 'Ingreso', 'Devolución', 'Registró']

    def filas():
        for m in cierre['movimientos']:
            hora = timezone.localtime(m['creado']).strftime('%H:%M') if m['creado'] else ''
            yield [m['fecha'], hora, m['tipo_display'], m['recibo'], m['nino'], m['concepto'],
                   nombres.get(m['metodo'], m['metodo']),
                   m['monto'] if m['signo'] > 0 else '', m['monto'] if m['signo'] < 0 else '', m['usuario']]
    return f'cierre_caja_{f.sufijo}.csv', cabecera, filas()


EXPORTADORES = {
    'asistencia': export_asistencia,
    'cobros':     export_cobros,
    'ninos':      export_ninos,
    'inventario': export_inventario,
    'deudas':     export_deudas,
    'cierre-caja': export_cierre_caja,
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
