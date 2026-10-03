"""
personal/views.py
"""
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from accounts.permissions import EsAdminODirectora, SoloAdminODirectora
from .models import Personal, AsignacionPersonal, AsistenciaPersonal
from .serializers import (
    PersonalSerializer, AsignacionPersonalSerializer, AsistenciaPersonalSerializer
)


class PersonalViewSet(viewsets.ModelViewSet):
    queryset = Personal.objects.select_related('usuario').all()
    serializer_class   = PersonalSerializer
    permission_classes = [EsAdminODirectora]
    filter_backends    = [filters.SearchFilter, DjangoFilterBackend]
    search_fields      = ['usuario__nombres', 'usuario__apellidos', 'ci']
    filterset_fields   = ['rol', 'activo']


class AsignacionPersonalViewSet(viewsets.ModelViewSet):
    queryset = AsignacionPersonal.objects.select_related(
        'personal', 'sucursal', 'sala', 'turno'
    ).all()
    serializer_class   = AsignacionPersonalSerializer
    permission_classes = [EsAdminODirectora]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['personal', 'sucursal', 'sala', 'turno', 'activa', 'es_titular']


class AsistenciaPersonalViewSet(viewsets.ModelViewSet):
    queryset = AsistenciaPersonal.objects.select_related(
        'personal', 'sucursal'
    ).all()
    serializer_class   = AsistenciaPersonalSerializer
    # Antes solo IsAuthenticated: cualquier cuenta (incluido un tutor) podía leer,
    # crear, editar y borrar la asistencia del personal. Es información laboral
    # del equipo: lectura y escritura solo para admin/directora.
    permission_classes = [SoloAdminODirectora]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['personal', 'sucursal', 'fecha', 'estado']
    ordering_fields    = ['fecha']
    ordering           = ['-fecha']
