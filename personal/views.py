"""
personal/views.py
"""
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import Personal, AsignacionPersonal, AsistenciaPersonal
from .serializers import (
    PersonalSerializer, AsignacionPersonalSerializer, AsistenciaPersonalSerializer
)


class PersonalViewSet(viewsets.ModelViewSet):
    queryset = Personal.objects.select_related('usuario').all()
    serializer_class   = PersonalSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, DjangoFilterBackend]
    search_fields      = ['usuario__nombres', 'usuario__apellidos', 'ci']
    filterset_fields   = ['rol', 'activo']


class AsignacionPersonalViewSet(viewsets.ModelViewSet):
    queryset = AsignacionPersonal.objects.select_related(
        'personal__usuario', 'sucursal', 'sala', 'turno'
    ).all()
    serializer_class   = AsignacionPersonalSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['personal', 'sucursal', 'sala', 'turno', 'activa', 'es_titular']


class AsistenciaPersonalViewSet(viewsets.ModelViewSet):
    queryset = AsistenciaPersonal.objects.select_related(
        'personal__usuario', 'sucursal'
    ).all()
    serializer_class   = AsistenciaPersonalSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ['personal', 'sucursal', 'fecha', 'estado']
    ordering_fields    = ['fecha']
    ordering           = ['-fecha']
