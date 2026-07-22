from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import Derivacion, PlanTrabajoMisael
from .serializers import DerivacionSerializer, PlanTrabajoMisaelSerializer

class DerivacionViewSet(viewsets.ModelViewSet):
    queryset = Derivacion.objects.select_related("nino","solicitado_por__usuario").all()
    serializer_class   = DerivacionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    search_fields      = ["nino__nombres","nino__apellidos","area_derivacion"]
    filterset_fields   = ["estado","consentimiento_tutor"]

class PlanTrabajoMisaelViewSet(viewsets.ModelViewSet):
    queryset = PlanTrabajoMisael.objects.select_related("nino","derivacion","plan_individual").all()
    serializer_class   = PlanTrabajoMisaelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ["nino","activo","consentimiento_tutor"]