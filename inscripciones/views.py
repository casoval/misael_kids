"""
inscripciones/views.py
"""
from datetime import date
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import EsAdminDirectoraOAdministrativo
from .models import Inscripcion, Cobro
from .serializers import (
    InscripcionSerializer, InscripcionResumenSerializer, CobroSerializer
)


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

    @action(detail=True, methods=['post'], url_path='generar-cobro-mensual')
    def generar_cobro_mensual(self, request, pk=None):
        """Genera el cobro mensual de esta inscripción para el período indicado."""
        inscripcion = self.get_object()
        periodo     = request.data.get('periodo')  # Ej: '2025-06'
        if not periodo:
            from datetime import date
            hoy     = date.today()
            periodo = f'{hoy.year}-{hoy.month:02d}'

        # Verificar que no exista ya para ese período
        if Cobro.objects.filter(inscripcion=inscripcion, periodo=periodo, tipo='mensualidad').exists():
            return Response(
                {'error': f'Ya existe un cobro de mensualidad para el período {periodo}.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from datetime import date, timedelta
        hoy = date.today()
        cobro = Cobro.objects.create(
            inscripcion       = inscripcion,
            tipo              = Cobro.TIPO_MENSUALIDAD,
            periodo           = periodo,
            monto_base        = inscripcion.costo_mensual,
            monto_final       = inscripcion.costo_mensual_final,
            fecha_vencimiento = hoy.replace(day=10) if hoy.day <= 10 else (hoy + timedelta(days=30)).replace(day=10),
            registrado_por    = request.user,
        )
        return Response(CobroSerializer(cobro).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='cobros-pendientes')
    def cobros_pendientes(self, request, pk=None):
        """Lista los cobros pendientes y vencidos de esta inscripción."""
        inscripcion = self.get_object()
        cobros = inscripcion.cobros.filter(
            estado__in=[Cobro.ESTADO_PENDIENTE, Cobro.ESTADO_VENCIDO]
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
        """Marca el cobro como pagado."""
        cobro  = self.get_object()
        if cobro.estado == Cobro.ESTADO_PAGADO:
            return Response(
                {'error': 'Este cobro ya está pagado.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        cobro.estado       = Cobro.ESTADO_PAGADO
        cobro.fecha_pago   = date.today()
        cobro.metodo_pago  = request.data.get('metodo_pago', Cobro.METODO_EFECTIVO)
        cobro.observacion  = request.data.get('observacion', '')
        cobro.registrado_por = request.user
        cobro.save()
        return Response(CobroSerializer(cobro).data)
