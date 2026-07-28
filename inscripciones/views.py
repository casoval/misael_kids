"""
inscripciones/views.py
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from dateutil.relativedelta import relativedelta
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import EsAdminDirectoraOAdministrativo
from .models import Inscripcion, Cobro, Pago
from .serializers import (
    InscripcionSerializer, InscripcionResumenSerializer, CobroSerializer, PagoSerializer
)
from .services import generar_ciclo_mensual


class InscripcionViewSet(viewsets.ModelViewSet):
    queryset = Inscripcion.objects.select_related(
        'nino', 'sucursal', 'sala', 'turno'
    ).prefetch_related('cobros').all()
    permission_classes = [EsAdminDirectoraOAdministrativo]
    filter_backends    = [filters.SearchFilter, DjangoFilterBackend]
    search_fields      = ['nino__nombres', 'nino__apellidos']
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

        Opcionalmente se puede pasar `ciclo` (entero, 0 = primer mes desde
        fecha_inicio) para generar un ciclo específico o regenerar uno que
        se haya anulado por error.
        """
        inscripcion = self.get_object()

        ciclo_param = request.data.get('ciclo')
        ciclo_num = None
        if ciclo_param is not None:
            try:
                ciclo_num = int(ciclo_param)
            except (TypeError, ValueError):
                return Response({'error': 'El ciclo debe ser un número entero.'}, status=status.HTTP_400_BAD_REQUEST)

        cobro = generar_ciclo_mensual(inscripcion, ciclo_num=ciclo_num, usuario=request.user)
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


class CobroViewSet(viewsets.ModelViewSet):
    queryset = Cobro.objects.select_related(
        'inscripcion__nino', 'inscripcion__sucursal', 'registrado_por'
    ).all()
    serializer_class   = CobroSerializer
    permission_classes = [EsAdminDirectoraOAdministrativo]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['tipo', 'estado', 'metodo_pago',
                          'inscripcion__sucursal', 'inscripcion__sala']
    ordering_fields    = ['fecha_emision', 'fecha_vencimiento', 'monto_final']
    ordering           = ['-fecha_emision']

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

        motivo = request.data.get('motivo', '').strip()
        if not motivo:
            return Response({'error': 'Debes indicar el motivo para cerrar el cobro con lo pagado.'},
                             status=status.HTTP_400_BAD_REQUEST)

        cobro.monto_condonado    = cobro.saldo_pendiente
        cobro.motivo_condonacion = motivo
        cobro.registrado_por     = request.user
        cobro.save(update_fields=['monto_condonado', 'motivo_condonacion', 'registrado_por'])
        cobro.recalcular_estado()
        cobro.refresh_from_db()

        return Response(CobroSerializer(cobro).data)
