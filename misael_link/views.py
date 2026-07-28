from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import Derivacion, PlanTrabajoMisael
from .serializers import DerivacionSerializer, PlanTrabajoMisaelSerializer
from accounts.permissions import filtrar_por_tutor

class DerivacionViewSet(viewsets.ModelViewSet):
    queryset = Derivacion.objects.select_related("nino","solicitado_por__usuario").all()
    serializer_class   = DerivacionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    search_fields      = ["nino__nombres","nino__apellidos","area_derivacion"]
    filterset_fields   = ["estado","consentimiento_tutor"]

    def get_queryset(self):
        # Las derivaciones a Centro Misael son información sensible
        # (motivo, área de derivación, respuesta del centro). Sin este
        # filtro, CUALQUIER cuenta de tutor podía listar TODAS las
        # derivaciones de TODOS los niños, ni siquiera hacía falta
        # adivinar un ID — bastaba con llamar al endpoint sin filtros.
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')

class PlanTrabajoMisaelViewSet(viewsets.ModelViewSet):
    queryset = PlanTrabajoMisael.objects.select_related("nino","derivacion","plan_individual").all()
    serializer_class   = PlanTrabajoMisaelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ["nino","activo","consentimiento_tutor"]

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')