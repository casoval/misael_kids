from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import HitoDesarrollo, EvaluacionNino
from .serializers import HitoDesarrolloSerializer, EvaluacionNinoSerializer
from accounts.permissions import filtrar_por_tutor

class HitoDesarrolloViewSet(viewsets.ModelViewSet):
    queryset           = HitoDesarrollo.objects.filter(activo=True).order_by("edad_min_meses","area")
    serializer_class   = HitoDesarrolloSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    search_fields      = ["nombre"]
    filterset_fields   = ["area","activo"]

    @action(detail=False, methods=["get"], url_path="por-edad")
    def por_edad(self, request):
        """Filtra hitos por edad en meses."""
        edad = int(request.query_params.get("meses", 0))
        hitos = self.queryset.filter(edad_min_meses__lte=edad, edad_max_meses__gte=edad)
        serializer = HitoDesarrolloSerializer(hitos, many=True, context={"request": request})
        return Response(serializer.data)

class EvaluacionNinoViewSet(viewsets.ModelViewSet):
    queryset = EvaluacionNino.objects.select_related("nino","educadora__usuario","hito").all()
    serializer_class   = EvaluacionNinoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ["nino","hito","estado","alerta_rezago","educadora"]
    ordering           = ["-fecha"]

    def get_queryset(self):
        # Un tutor solo debe ver las evaluaciones de desarrollo de SU hijo,
        # no las de cualquier niño (antes bastaba con cambiar ?nino=<id>
        # en la URL para ver la evaluación de otro niño, incluida la
        # bandera de alerta de rezago).
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')

    @action(detail=False, methods=["get"], url_path="alertas-rezago")
    def alertas_rezago(self, request):
        evaluaciones = self.get_queryset().filter(alerta_rezago=True)
        serializer   = EvaluacionNinoSerializer(evaluaciones, many=True, context={"request": request})
        return Response(serializer.data)