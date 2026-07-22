from datetime import datetime
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import Mensaje, Aviso
from .serializers import MensajeSerializer, AvisoSerializer

class MensajeViewSet(viewsets.ModelViewSet):
    serializer_class   = MensajeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ["leido","nino"]
    ordering           = ["-created_at"]

    def get_queryset(self):
        usuario = self.request.user
        from django.db.models import Q
        return Mensaje.objects.filter(
            Q(remitente=usuario) | Q(destinatario=usuario)
        ).select_related("remitente","destinatario","nino")

    def perform_create(self, serializer):
        serializer.save(remitente=self.request.user)

    @action(detail=True, methods=["post"], url_path="marcar-leido")
    def marcar_leido(self, request, pk=None):
        mensaje = self.get_object()
        if mensaje.destinatario == request.user:
            mensaje.leido    = True
            mensaje.leido_en = datetime.now()
            mensaje.save()
        return Response(MensajeSerializer(mensaje).data)

class AvisoViewSet(viewsets.ModelViewSet):
    queryset = Aviso.objects.select_related("autor","sucursal","sala","turno").all()
    serializer_class   = AvisoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ["sucursal","sala","importante"]
    ordering           = ["-publicado_en"]

    def perform_create(self, serializer):
        serializer.save(autor=self.request.user)