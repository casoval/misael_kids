from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import HitoDesarrollo, EvaluacionNino
from .serializers import HitoDesarrolloSerializer, EvaluacionNinoSerializer

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

    @action(detail=False, methods=["get"], url_path="alertas-rezago")
    def alertas_rezago(self, request):
        evaluaciones = self.queryset.filter(alerta_rezago=True)
        serializer   = EvaluacionNinoSerializer(evaluaciones, many=True, context={"request": request})
        return Response(serializer.data)