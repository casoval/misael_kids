from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated, BasePermission, SAFE_METHODS
from django_filters.rest_framework import DjangoFilterBackend
from .models import IncidenteSalud
from .serializers import IncidenteSaludSerializer
from accounts.permissions import filtrar_por_alcance, exigir_nino_en_alcance
from personal.models import Personal


class LecturaTodosEscrituraPersonal(BasePermission):
    """Lectura: cualquier autenticado (con su alcance). Registrar/editar/eliminar
    incidentes: solo el personal del centro, nunca una cuenta de tutor."""
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return request.method in SAFE_METHODS or u.rol != 'tutor'


class IncidenteSaludViewSet(viewsets.ModelViewSet):
    queryset = IncidenteSalud.objects.select_related("nino","reportado_por","sucursal").all()
    serializer_class   = IncidenteSaludSerializer
    permission_classes = [IsAuthenticated, LecturaTodosEscrituraPersonal]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ["nino__nombres","nino__apellidos"]
    filterset_fields   = ["nino","tipo","sucursal","notificado_tutor","requirio_atencion_medica"]
    ordering           = ["-fecha","-hora"]

    def get_queryset(self):
        # Sin esto, cualquier tutor podía consultar el historial de
        # incidentes de salud (golpes, fiebre, alergias...) de CUALQUIER
        # niño, no solo del suyo, con solo cambiar ?nino=<id>.
        return filtrar_por_alcance(super().get_queryset(), self.request.user, 'nino')

    def perform_create(self, serializer):
        exigir_nino_en_alcance(self.request.user, serializer.validated_data['nino'])
        # Quien reporta = la ficha de Personal del usuario logueado (None si no tiene).
        serializer.save(reportado_por=Personal.objects.filter(usuario=self.request.user).first())

    def perform_update(self, serializer):
        if 'nino' in serializer.validated_data:
            exigir_nino_en_alcance(self.request.user, serializer.validated_data['nino'])
        serializer.save()
