"""
inscripciones/views.py
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from dateutil.relativedelta import relativedelta
from django.db.models import Count, Q, Sum
from rest_framework import viewsets, filters, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import EsAdminDirectoraOAdministrativo, filtrar_por_tutor
from .models import Inscripcion, Cobro, Pago, Devolucion
from .serializers import (
    InscripcionSerializer, InscripcionResumenSerializer, CobroSerializer,
    PagoSerializer, DevolucionSerializer,
)
from .services import (
    generar_ciclo_mensual, calendario_pagos_mensual, calendario_pagos_diario,
    cobro_anterior_pendiente, etiqueta_periodo, asignar_numero_recibo,
    ESTADOS_ABIERTOS,
)


class InscripcionViewSet(viewsets.ModelViewSet):
    queryset = Inscripcion.objects.select_related(
        'nino', 'sucursal', 'sala', 'turno'
    ).prefetch_related('cobros').all()
    permission_classes = [EsAdminDirectoraOAdministrativo]
    filter_backends    = [filters.SearchFilter, DjangoFilterBackend]
    search_fields      = ['nino__nombres', 'nino__apellidos']

    def get_queryset(self):
        # Sin este filtro, cualquier cuenta de tutor podía ver (y, vía las
        # acciones de detalle: cobros-pendientes, calendario-pagos,
        # registrar-pago...) tocar la inscripción de CUALQUIER niño con
        # solo cambiar el id en la URL — no solo la de su propio hijo.
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')
    filterset_fields   = ['sucursal', 'sala', 'turno', 'modalidad_pago', 'tipo_ajuste', 'activa']

    def get_serializer_class(self):
        if self.action == 'list':
            return InscripcionResumenSerializer
        return InscripcionSerializer

    def perform_create(self, serializer):
        """
        Al crear una inscripción con modalidad mensual, se genera de una
        vez el primer cobro (el del mes/ciclo en que se está inscribiendo),
        para no obligar a un paso manual aparte. La modalidad diaria no
        necesita esto: su cobro se genera solo al marcar asistencia.
        """
        inscripcion = serializer.save()
        if inscripcion.activa and inscripcion.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
            generar_ciclo_mensual(inscripcion, ciclo_num=0, usuario=self.request.user)

    @action(detail=True, methods=['post'], url_path='generar-cobro-mensual')
    def generar_cobro_mensual(self, request, pk=None):
        """
        Genera el siguiente cobro de mensualidad de esta inscripción
        (normalmente para renovar el ciclo del mes siguiente; el primer
        ciclo ya se genera solo al crear la inscripción).

        Se puede pasar `ciclo` (entero, 0 = primer mes desde fecha_inicio)
        para generar un ciclo específico de la grilla automática, o
        `periodo_inicio` (fecha YYYY-MM-DD) para arrancar un ciclo nuevo
        con una fecha elegida a mano —pensado para reanudar después de una
        pausa, sin arrastrar los meses en que el niño no vino. Si se manda
        `periodo_inicio`, tiene prioridad sobre `ciclo`.
        """
        inscripcion = self.get_object()

        periodo_inicio_param = request.data.get('periodo_inicio')
        periodo_inicio = None
        if periodo_inicio_param:
            try:
                periodo_inicio = date.fromisoformat(periodo_inicio_param)
            except ValueError:
                return Response({'error': 'La fecha de inicio no es válida, usa formato YYYY-MM-DD.'},
                                 status=status.HTTP_400_BAD_REQUEST)

        ciclo_num = None
        if periodo_inicio is None:
            ciclo_param = request.data.get('ciclo')
            if ciclo_param is not None:
                try:
                    ciclo_num = int(ciclo_param)
                except (TypeError, ValueError):
                    return Response({'error': 'El ciclo debe ser un número entero.'}, status=status.HTTP_400_BAD_REQUEST)

        cobro = generar_ciclo_mensual(
            inscripcion, ciclo_num=ciclo_num, periodo_inicio=periodo_inicio, usuario=request.user
        )
        if cobro is None:
            return Response(
                {'error': 'Ya existe un cobro de mensualidad para ese ciclo.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return Response(CobroSerializer(cobro).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='transferir')
    def transferir(self, request, pk=None):
        """
        Transfiere al niño de esta inscripción a otra sala/turno/sucursal.
        Cierra la inscripción actual (activa=False, fecha_fin) y crea una
        inscripción nueva enlazada, sin dejar nunca dos inscripciones activas
        para el mismo niño al mismo tiempo. El historial de cobros de la
        inscripción anterior se conserva intacto.
        """
        from core.models import Sala, Turno, Sucursal

        inscripcion_actual = self.get_object()
        if not inscripcion_actual.activa:
            return Response(
                {'error': 'Esta inscripción ya no está activa; no se puede transferir.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data        = request.data
        sucursal_id = data.get('sucursal', inscripcion_actual.sucursal_id)
        sala_id     = data.get('sala')
        turno_id    = data.get('turno')
        if not sala_id or not turno_id:
            return Response(
                {'error': 'Debes indicar la nueva sala y turno de destino.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            sucursal = Sucursal.objects.get(pk=sucursal_id)
            sala     = Sala.objects.get(pk=sala_id)
            turno    = Turno.objects.get(pk=turno_id)
        except (Sucursal.DoesNotExist, Sala.DoesNotExist, Turno.DoesNotExist):
            return Response({'error': 'Sucursal, sala o turno no válidos.'}, status=status.HTTP_400_BAD_REQUEST)

        if sala.sucursal_id != sucursal.id:
            return Response({'error': 'La sala no pertenece a la sucursal seleccionada.'}, status=status.HTTP_400_BAD_REQUEST)
        if turno.sala_id != sala.id:
            return Response({'error': 'El turno no pertenece a la sala seleccionada.'}, status=status.HTTP_400_BAD_REQUEST)

        # Si es la misma sala+turno actual, no tiene sentido "transferir"
        if sala.id == inscripcion_actual.sala_id and turno.id == inscripcion_actual.turno_id:
            return Response(
                {'error': 'El destino es la misma sala y turno actuales.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verificar cupo en el destino (sin contar la inscripción que se va a cerrar)
        ocupados = Inscripcion.objects.filter(
            sala=sala, turno=turno, activa=True
        ).exclude(id=inscripcion_actual.id).count()
        if ocupados >= sala.capacidad_maxima:
            return Response(
                {'error': f'La sala {sala.nombre} ya alcanzó su capacidad máxima ({sala.capacidad_maxima} niños).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        hoy = date.today()
        fecha_transferencia = data.get('fecha_transferencia') or hoy.isoformat()

        # Cerrar la inscripción actual (el historial de cobros queda intacto, ligado a ella)
        inscripcion_actual.activa    = False
        inscripcion_actual.fecha_fin = fecha_transferencia
        inscripcion_actual.save()

        # Crear la nueva inscripción activa, heredando lo que no se indique explícitamente
        nueva = Inscripcion.objects.create(
            nino                = inscripcion_actual.nino,
            sucursal            = sucursal,
            sala                = sala,
            turno               = turno,
            modalidad_pago      = data.get('modalidad_pago', inscripcion_actual.modalidad_pago),
            fecha_inicio        = fecha_transferencia,
            costo_mensual       = data.get('costo_mensual') or turno.costo_mensual,
            costo_diario        = data.get('costo_diario') or turno.costo_diario,
            tipo_ajuste         = data.get('tipo_ajuste', inscripcion_actual.tipo_ajuste),
            porcentaje_ajuste   = data.get('porcentaje_ajuste', inscripcion_actual.porcentaje_ajuste),
            monto_ajuste        = data.get('monto_ajuste', inscripcion_actual.monto_ajuste),
            motivo_ajuste       = data.get(
                'motivo_transferencia',
                f'Transferido desde {inscripcion_actual.sala} / {inscripcion_actual.turno} el {fecha_transferencia}.'
            ),
            activa              = True,
            inscripcion_origen  = inscripcion_actual,
        )
        if nueva.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
            generar_ciclo_mensual(nueva, ciclo_num=0, usuario=request.user)
        return Response(InscripcionSerializer(nueva).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='cobros-pendientes')
    def cobros_pendientes(self, request, pk=None):
        """Lista los cobros pendientes, parciales y vencidos de esta inscripción."""
        inscripcion = self.get_object()
        cobros = inscripcion.cobros.filter(
            estado__in=[Cobro.ESTADO_PENDIENTE, Cobro.ESTADO_PARCIAL, Cobro.ESTADO_VENCIDO]
        ).order_by('fecha_vencimiento')
        serializer = CobroSerializer(cobros, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='calendario-pagos')
    def calendario_pagos(self, request, pk=None):
        """
        Todo lo necesario para pintar la vista visual de "Pagos" de esta
        inscripción en una sola llamada: si es modalidad mensual, devuelve
        los ciclos mes a mes; si es diaria, el calendario del mes pedido
        (por defecto el mes actual, o ?anio=YYYY&mes=M).
        """
        inscripcion = self.get_object()

        if inscripcion.modalidad_pago == Inscripcion.MODALIDAD_MENSUAL:
            return Response({
                'modalidad': 'mensual',
                'ciclos':    calendario_pagos_mensual(inscripcion),
            })

        hoy  = date.today()
        anio = int(request.query_params.get('anio', hoy.year))
        mes  = int(request.query_params.get('mes', hoy.month))
        if not (1 <= mes <= 12):
            return Response({'error': 'El mes debe estar entre 1 y 12.'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'modalidad':  'diaria',
            'calendario': calendario_pagos_diario(inscripcion, anio, mes),
        })


class CobroViewSet(viewsets.ModelViewSet):
    queryset = Cobro.objects.select_related(
        'inscripcion__nino', 'inscripcion__sucursal', 'registrado_por'
    ).all()
    serializer_class   = CobroSerializer
    permission_classes = [EsAdminDirectoraOAdministrativo]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['inscripcion', 'tipo', 'estado', 'metodo_pago',
                          'inscripcion__sucursal', 'inscripcion__sala']
    ordering_fields    = ['fecha_emision', 'fecha_vencimiento', 'monto_final']
    ordering           = ['-fecha_emision']

    def get_queryset(self):
        # Mismo motivo que en InscripcionViewSet: sin esto, un tutor podía
        # leer (y, vía registrar-pago/registrar-devolucion/cerrar-con-lo-
        # pagado si alguna vez se relaja el permiso de escritura) el cobro
        # de cualquier niño, no solo el suyo.
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'inscripcion__nino')

    # ── Estadísticas y movimientos de caja ────────────────────────────────
    # Se calculan aquí (servidor) y no en el navegador: la paginación de DRF
    # ignora `page_size` (fija 25), así que sumar desde el front truncaba los
    # totales en cuanto había más de 25 cobros.
    ROLES_CAJA = ('admin', 'directora', 'administrativo')

    def _exigir_rol_caja(self, request):
        if request.user.rol not in self.ROLES_CAJA:
            raise PermissionDenied('No tienes permiso para ver la caja.')

    @action(detail=False, methods=['get'], url_path='resumen')
    def resumen(self, request):
        """
        Tarjetas de la pantalla de Cobros.
        - pendiente: saldo por cobrar de todos los cobros abiertos (pendiente,
          parcial o vencido), NO anulados, ya descontando pagos, devoluciones
          y condonado. Incluye a los vencidos.
        - vencido: la parte de lo pendiente cuyo vencimiento ya pasó.
        - mes: caja real del mes = pagos con fecha del mes - devoluciones con
          fecha del mes (en cualquier cobro, sin importar su estado).
        Parámetros opcionales: `mes` (YYYY-MM, por defecto el actual), `sucursal`.
        """
        self._exigir_rol_caja(request)
        hoy = date.today()
        sucursal = request.query_params.get('sucursal')
        try:
            anio, mes = (int(x) for x in (request.query_params.get('mes') or hoy.strftime('%Y-%m')).split('-'))
            date(anio, mes, 1)
        except (ValueError, TypeError):
            return Response({'error': 'El mes debe tener formato YYYY-MM.'}, status=status.HTTP_400_BAD_REQUEST)

        cobros = Cobro.objects.all()
        pagos  = Pago.objects.filter(fecha_pago__year=anio, fecha_pago__month=mes)
        devs   = Devolucion.objects.filter(fecha__year=anio, fecha__month=mes)
        if sucursal:
            cobros = cobros.filter(inscripcion__sucursal=sucursal)
            pagos  = pagos.filter(cobro__inscripcion__sucursal=sucursal)
            devs   = devs.filter(cobro__inscripcion__sucursal=sucursal)

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
        d = devs.aggregate(total=Sum('monto'), n=Count('id'))
        total_pagos = p['total'] or cero
        total_devs  = d['total'] or cero
        condonado = cobros.filter(
            monto_condonado__gt=0, fecha_pago__year=anio, fecha_pago__month=mes,
        ).aggregate(t=Sum('monto_condonado'))['t'] or cero

        return Response({
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
        })

    @action(detail=False, methods=['get'], url_path='movimientos')
    def movimientos(self, request):
        """
        Libro de caja: pagos (ingresos) y devoluciones (egresos) mezclados en
        orden cronológico inverso, con totales de TODO el filtro (no solo de
        la página). Filtros: desde, hasta (YYYY-MM-DD), tipo (pago|devolucion),
        metodo_pago, sucursal, search (nombre del niño). Paginado con
        `page` y `page_size` (máx. 100).
        """
        self._exigir_rol_caja(request)
        qp = request.query_params
        try:
            desde = date.fromisoformat(qp['desde']) if qp.get('desde') else None
            hasta = date.fromisoformat(qp['hasta']) if qp.get('hasta') else None
            page      = max(int(qp.get('page', 1)), 1)
            page_size = min(max(int(qp.get('page_size', 25)), 1), 100)
        except ValueError:
            return Response({'error': 'Fechas (YYYY-MM-DD) o paginación inválidas.'},
                            status=status.HTTP_400_BAD_REQUEST)
        tipo, metodo = qp.get('tipo', ''), qp.get('metodo_pago', '')
        sucursal, search = qp.get('sucursal', ''), qp.get('search', '').strip()

        def filtrar(qs, campo_fecha):
            if desde:    qs = qs.filter(**{f'{campo_fecha}__gte': desde})
            if hasta:    qs = qs.filter(**{f'{campo_fecha}__lte': hasta})
            if metodo:   qs = qs.filter(metodo_pago=metodo)
            if sucursal: qs = qs.filter(cobro__inscripcion__sucursal=sucursal)
            for palabra in search.split():
                qs = qs.filter(
                    Q(cobro__inscripcion__nino__nombres__icontains=palabra) |
                    Q(cobro__inscripcion__nino__apellidos__icontains=palabra)
                )
            return qs

        rel = ('cobro__inscripcion__nino', 'registrado_por')
        pagos = filtrar(Pago.objects.select_related(*rel), 'fecha_pago')
        devs  = filtrar(Devolucion.objects.select_related(*rel), 'fecha')
        if tipo == 'pago':
            devs = devs.none()
        elif tipo == 'devolucion':
            pagos = pagos.none()

        cero = Decimal('0')
        tp = pagos.aggregate(t=Sum('monto'), n=Count('id'))
        td = devs.aggregate(t=Sum('monto'), n=Count('id'))
        por_metodo = {}
        for m, _ in Cobro.METODOS_PAGO:
            por_metodo[m] = {'ingresos': cero, 'devoluciones': cero, 'neto': cero}
        for fila in pagos.values('metodo_pago').annotate(t=Sum('monto')):
            por_metodo.setdefault(fila['metodo_pago'], {'ingresos': cero, 'devoluciones': cero, 'neto': cero})['ingresos'] = fila['t']
        for fila in devs.values('metodo_pago').annotate(t=Sum('monto')):
            por_metodo.setdefault(fila['metodo_pago'], {'ingresos': cero, 'devoluciones': cero, 'neto': cero})['devoluciones'] = fila['t']
        for v in por_metodo.values():
            v['neto'] = v['ingresos'] - v['devoluciones']

        # Se traen solo las filas necesarias de cada lado (hasta el final de la
        # página pedida) y se mezclan por fecha.
        limite = page * page_size
        filas = []
        for x in pagos.order_by('-fecha_pago', '-created_at')[:limite]:
            filas.append(('pago', x, x.fecha_pago, x.observacion))
        for x in devs.order_by('-fecha', '-created_at')[:limite]:
            filas.append(('devolucion', x, x.fecha, x.motivo))
        filas.sort(key=lambda f: (f[2], f[1].created_at), reverse=True)
        pagina = filas[(page - 1) * page_size: page * page_size]

        results = []
        for kind, x, fecha, detalle in pagina:
            c = x.cobro
            results.append({
                'tipo':           kind,
                'id':             str(x.id),
                'fecha':          fecha.isoformat(),
                'monto':          x.monto,
                'nino_nombre':    c.inscripcion.nino.nombre_completo,
                'concepto':       f'{c.get_tipo_display()} {c.periodo}'.strip(),
                'metodo_pago':    x.metodo_pago,
                'metodo_display': x.get_metodo_pago_display(),
                'detalle':        detalle,
                'numero_recibo':  x.numero_recibo,
                'registrado_por': x.registrado_por.nombre_completo if x.registrado_por else None,
            })

        count = (tp['n'] or 0) + (td['n'] or 0)
        return Response({
            'count': count, 'page': page, 'page_size': page_size,
            'total_pages': max((count + page_size - 1) // page_size, 1),
            'results': results,
            'totales': {
                'ingresos':              tp['t'] or cero,
                'cantidad_pagos':        tp['n'],
                'devoluciones':          td['t'] or cero,
                'cantidad_devoluciones': td['n'],
                'neto':                  (tp['t'] or cero) - (td['t'] or cero),
                'por_metodo':            por_metodo,
            },
        })

    @action(detail=True, methods=['post'], url_path='registrar-pago')
    def registrar_pago(self, request, pk=None):
        """
        Registra un abono/cuota sobre este cobro. Puede ser el pago completo
        o un pago parcial: se acepta un `monto` explícito (si no se manda,
        se asume que se está cubriendo TODO el saldo pendiente, para no
        romper compatibilidad con quien ya llamaba este endpoint sin monto).

        Un mismo cobro puede recibir varios pagos parciales hasta llegar a
        monto_final (ej. 2 pagos de 200 sobre una mensualidad de 650: el
        cobro queda en estado "parcial" con saldo_pendiente = 250).
        """
        cobro = self.get_object()
        if cobro.estado == Cobro.ESTADO_ANULADO:
            return Response({'error': 'Este cobro está anulado, no se le pueden registrar pagos.'},
                             status=status.HTTP_400_BAD_REQUEST)
        if cobro.saldo_pendiente <= 0:
            return Response({'error': 'Este cobro ya está cubierto por completo.'},
                             status=status.HTTP_400_BAD_REQUEST)

        anterior = cobro_anterior_pendiente(cobro)
        if anterior:
            return Response({
                'error': f'Primero hay que cerrar {etiqueta_periodo(anterior)}, que sigue abierto. '
                         'Los cobros se cierran en orden.'
            }, status=status.HTTP_400_BAD_REQUEST)

        monto_raw = request.data.get('monto')
        if monto_raw in (None, ''):
            monto = cobro.saldo_pendiente  # comportamiento anterior: pagar todo lo que falta
        else:
            try:
                monto = Decimal(str(monto_raw))
            except InvalidOperation:
                return Response({'error': 'El monto no es un número válido.'}, status=status.HTTP_400_BAD_REQUEST)

        if monto <= 0:
            return Response({'error': 'El monto del pago debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto > cobro.saldo_pendiente:
            return Response(
                {'error': f'El monto ({monto}) supera el saldo pendiente ({cobro.saldo_pendiente}).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        pago = Pago.objects.create(
            cobro          = cobro,
            monto          = monto,
            fecha_pago     = request.data.get('fecha_pago') or date.today(),
            metodo_pago    = request.data.get('metodo_pago', Cobro.METODO_EFECTIVO),
            observacion    = request.data.get('observacion', ''),
            registrado_por = request.user,
        )
        asignar_numero_recibo(pago)

        # Reflejar el último pago también en el propio Cobro (compatibilidad con reportes)
        cobro.fecha_pago  = pago.fecha_pago
        cobro.metodo_pago = pago.metodo_pago
        cobro.save(update_fields=['fecha_pago', 'metodo_pago'])
        cobro.recalcular_estado()
        cobro.refresh_from_db()

        return Response(CobroSerializer(cobro).data)

    @action(detail=True, methods=['post'], url_path='cerrar-con-lo-pagado')
    def cerrar_con_lo_pagado(self, request, pk=None):
        """
        Da por saldado el cobro con lo que ya se pagó, condonando el resto.
        Útil cuando por alguna circunstancia (acuerdo con la familia, caso
        social, error de cobro, etc.) se decide que la mensualidad queda
        "pagada" aunque no se haya cubierto el 100% del monto original.
        Requiere `motivo`. Queda registrado el monto condonado para auditoría.
        """
        cobro = self.get_object()
        if cobro.estado in (Cobro.ESTADO_PAGADO, Cobro.ESTADO_ANULADO):
            return Response({'error': 'Este cobro ya está cerrado (pagado o anulado).'},
                             status=status.HTTP_400_BAD_REQUEST)

        anterior = cobro_anterior_pendiente(cobro)
        if anterior:
            return Response({
                'error': f'Primero hay que cerrar {etiqueta_periodo(anterior)}, que sigue abierto. '
                         'Los cobros se cierran en orden.'
            }, status=status.HTTP_400_BAD_REQUEST)

        motivo = request.data.get('motivo', '').strip()
        if not motivo:
            return Response({'error': 'Debes indicar el motivo para cerrar el cobro con lo pagado.'},
                             status=status.HTTP_400_BAD_REQUEST)

        cobro.monto_condonado         = cobro.saldo_pendiente
        cobro.monto_condonado_inicial = cobro.saldo_pendiente
        cobro.motivo_condonacion      = motivo
        cobro.registrado_por          = request.user
        cobro.save(update_fields=[
            'monto_condonado', 'monto_condonado_inicial',
            'motivo_condonacion', 'registrado_por',
        ])
        cobro.recalcular_estado()
        cobro.refresh_from_db()

        return Response(CobroSerializer(cobro).data)

    @action(detail=True, methods=['post'], url_path='registrar-devolucion')
    def registrar_devolucion(self, request, pk=None):
        """
        Registra una devolución de dinero sobre este cobro (ej. se cobró de
        más, la familia se dio de baja y hay saldo a favor, un error de
        cobro). Resta de lo pagado: si el cobro estaba "pagado" por pago
        real (sin condonación) y se devuelve una parte, recalcular_estado()
        lo reabre solo — y a partir de ahí vuelve a aplicar la regla de
        "cerrar en orden" con los cobros posteriores, como corresponde.

        Excepción: si el cobro ya se había cerrado con "Cerrar con lo
        pagado" (monto_condonado > 0), la devolución NO reabre el mes —
        el monto condonado se incrementa en el mismo monto devuelto para
        que el mes se mantenga "pagado" (ver ajuste más abajo).

        No se puede devolver más de lo que efectivamente se pagó (lo
        condonado nunca fue dinero real, no hay nada que devolver de eso).
        Requiere `motivo`.
        """
        cobro = self.get_object()

        monto_raw = request.data.get('monto')
        try:
            monto = Decimal(str(monto_raw))
        except (InvalidOperation, TypeError):
            return Response({'error': 'El monto no es un número válido.'}, status=status.HTTP_400_BAD_REQUEST)

        if monto <= 0:
            return Response({'error': 'El monto a devolver debe ser mayor a cero.'}, status=status.HTTP_400_BAD_REQUEST)
        if monto > cobro.monto_pagado:
            return Response(
                {'error': f'No se puede devolver más de lo pagado ({cobro.monto_pagado} Bs.).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        motivo = request.data.get('motivo', '').strip()
        if not motivo:
            return Response({'error': 'Debes indicar el motivo de la devolución.'}, status=status.HTTP_400_BAD_REQUEST)

        devolucion = Devolucion.objects.create(
            cobro          = cobro,
            monto          = monto,
            fecha          = request.data.get('fecha') or date.today(),
            metodo_pago    = request.data.get('metodo_pago', Cobro.METODO_EFECTIVO),
            motivo         = motivo,
            registrado_por = request.user,
        )
        asignar_numero_recibo(devolucion)

        # Si el mes ya se había cerrado con "Cerrar con lo pagado" (tiene
        # condonación), esta devolución NO debe reabrirlo: la decisión de
        # darlo por saldado ya se tomó. El monto condonado absorbe la
        # diferencia devuelta, así el mes se mantiene "pagado" y no vuelve
        # a pedir un pago que ya se había perdonado.
        if cobro.monto_condonado > 0 or cobro.monto_condonado_inicial is not None:
            # Se recalcula el condonado para que pagado neto + condonado siga
            # sumando el monto final (en vez de sumar a ciegas lo devuelto,
            # que dejaba el mes en "parcial" si los números ya estaban desfasados).
            nuevo_condonado = max(cobro.monto_final - cobro.monto_pagado, 0)
            nota_ajuste = (
                f'Ajuste {date.today().isoformat()}: condonado {cobro.monto_condonado} → '
                f'{nuevo_condonado} Bs. por devolución de {monto} Bs. '
                f'(motivo devolución: {motivo}).'
            )
            cobro.monto_condonado    = nuevo_condonado
            cobro.motivo_condonacion = (
                f'{cobro.motivo_condonacion}\n{nota_ajuste}'.strip()
                if cobro.motivo_condonacion else nota_ajuste
            )
            cobro.save(update_fields=['monto_condonado', 'motivo_condonacion'])

        cobro.recalcular_estado()
        cobro.refresh_from_db()

        return Response(CobroSerializer(cobro).data, status=status.HTTP_201_CREATED)
