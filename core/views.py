"""
core/views.py
ViewSets para Sucursal, Sala y Turno.
"""
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import EsAdminODirectora
from .models import Sucursal, Sala, Turno
from .serializers import (
    SucursalSerializer, SucursalResumenSerializer,
    SalaSerializer, TurnoSerializer,
)


class SucursalViewSet(viewsets.ModelViewSet):
    """
    CRUD completo de sucursales.
    Solo directoras y admins pueden crear/editar.
    Todos los usuarios autenticados pueden listar.
    """
    queryset         = Sucursal.objects.all().order_by('nombre')
    serializer_class = SucursalSerializer
    permission_classes = [EsAdminODirectora]
    filter_backends  = [filters.SearchFilter, DjangoFilterBackend]
    search_fields    = ['nombre', 'ciudad', 'direccion']
    filterset_fields = ['activa', 'ciudad']

    def get_serializer_class(self):
        if self.action == 'list':
            return SucursalResumenSerializer
        return SucursalSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        usuario = self.request.user
        # Admin ve todas; directora solo las suyas
        if usuario.rol == 'directora':
            qs = qs.filter(directora=usuario)
        return qs

    @action(detail=True, methods=['get'], url_path='salas-activas')
    def salas_activas(self, request, pk=None):
        """Devuelve solo las salas activas de esta sucursal."""
        sucursal = self.get_object()
        salas    = sucursal.salas.filter(activa=True).order_by('edad_min_meses')
        from .serializers import SalaSerializer
        serializer = SalaSerializer(salas, many=True, context={'request': request})
        return Response(serializer.data)


class SalaViewSet(viewsets.ModelViewSet):
    """
    CRUD de salas. Filtrable por sucursal.
    """
    queryset         = Sala.objects.select_related('sucursal').prefetch_related('turnos').all()
    serializer_class = SalaSerializer
    permission_classes = [EsAdminODirectora]
    filter_backends  = [filters.SearchFilter, DjangoFilterBackend]
    search_fields    = ['nombre']
    filterset_fields = ['sucursal', 'activa']

    def get_queryset(self):
        qs      = super().get_queryset()
        usuario = self.request.user
        if usuario.rol == 'directora':
            qs = qs.filter(sucursal__directora=usuario)
        elif usuario.rol in ['educadora', 'ayudante']:
            # Solo las salas donde está asignada
            from personal.models import AsignacionPersonal
            salas_ids = AsignacionPersonal.objects.filter(
                personal__usuario=usuario, activa=True
            ).values_list('sala_id', flat=True)
            qs = qs.filter(id__in=salas_ids)
        return qs

    @action(detail=True, methods=['get'], url_path='turnos-activos')
    def turnos_activos(self, request, pk=None):
        """Devuelve los turnos activos de esta sala."""
        sala   = self.get_object()
        turnos = sala.turnos.filter(activo=True).order_by('hora_inicio')
        serializer = TurnoSerializer(turnos, many=True, context={'request': request})
        return Response(serializer.data)


class TurnoViewSet(viewsets.ModelViewSet):
    """
    CRUD de turnos. Filtrable por sala y tipo.
    """
    queryset         = Turno.objects.select_related('sala', 'sala__sucursal').all()
    serializer_class = TurnoSerializer
    permission_classes = [EsAdminODirectora]
    filter_backends  = [filters.SearchFilter, DjangoFilterBackend]
    search_fields    = ['nombre']
    filterset_fields = ['sala', 'tipo', 'activo']
