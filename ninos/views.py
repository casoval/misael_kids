"""
ninos/views.py
"""
from django.db import models
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from .models import Nino, Tutor, NinoTutor, PersonaAutorizada, Documento
from .serializers import (
    NinoSerializer, NinoResumenSerializer, TutorSerializer,
    NinoTutorSerializer, PersonaAutorizadaSerializer, DocumentoSerializer,
)
from accounts.permissions import filtrar_por_tutor


class NinoViewSet(viewsets.ModelViewSet):
    queryset = Nino.objects.prefetch_related(
        'tutores__tutor', 'autorizados', 'documentos'
    ).all()
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, DjangoFilterBackend]
    search_fields      = ['nombres', 'apellidos']
    filterset_fields   = ['genero', 'tiene_plan_misael', 'activo']

    def get_serializer_class(self):
        if self.action == 'list':
            return NinoResumenSerializer
        return NinoSerializer

    def get_queryset(self):
        qs      = super().get_queryset()
        usuario = self.request.user
        # Tutores solo ven a sus hijos
        if usuario.rol == 'tutor':
            qs = qs.filter(tutores__tutor__usuario=usuario)
        return qs

    @action(detail=True, methods=['get'], url_path='autorizados-activos')
    def autorizados_activos(self, request, pk=None):
        """Lista las personas autorizadas vigentes para retirar al niño."""
        from datetime import date
        nino       = self.get_object()
        hoy        = date.today()
        autorizados = nino.autorizados.filter(
            activa=True
        ).filter(
            vigencia_desde__lte=hoy
        ).filter(
            models.Q(vigencia_hasta__isnull=True) | models.Q(vigencia_hasta__gte=hoy)
        )
        serializer = PersonaAutorizadaSerializer(autorizados, many=True, context={'request': request})
        return Response(serializer.data)


class TutorViewSet(viewsets.ModelViewSet):
    queryset           = Tutor.objects.select_related('usuario').prefetch_related('ninos__nino').all()
    serializer_class   = TutorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['nombres', 'apellidos', 'ci', 'email']


class NinoTutorViewSet(viewsets.ModelViewSet):
    """
    Vínculo entre un niño y un tutor (quién puede retirarlo, quién es el
    contacto principal). Antes esta relación no tenía ViewSet ni ruta
    propia, por lo que /ninos/tutores-nino/ (usado por tutores.html para
    vincular) no existía y toda vinculación fallaba con 404.
    """
    queryset           = NinoTutor.objects.select_related('nino', 'tutor').all()
    serializer_class   = NinoTutorSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['nino', 'tutor']


class PersonaAutorizadaViewSet(viewsets.ModelViewSet):
    queryset           = PersonaAutorizada.objects.select_related('nino').all()
    serializer_class   = PersonaAutorizadaSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['nino', 'activa']

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')


class DocumentoViewSet(viewsets.ModelViewSet):
    queryset           = Documento.objects.select_related('nino').all()
    serializer_class   = DocumentoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ['nino', 'tipo', 'verificado']

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')
