from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import IncidenteSalud
from .serializers import IncidenteSaludSerializer
class IncidenteSaludViewSet(viewsets.ModelViewSet):
    queryset = IncidenteSalud.objects.select_related("nino","reportado_por__usuario","sucursal").all()
    serializer_class   = IncidenteSaludSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ["nino__nombres","nino__apellidos"]
    filterset_fields   = ["nino","tipo","sucursal","notificado_tutor","requirio_atencion_medica"]
    ordering           = ["-fecha","-hora"]