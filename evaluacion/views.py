import django_filters
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import (
    filtrar_por_alcance, exigir_nino_en_alcance, PermisoDesarrollo, PermisoCatalogoHitos,
)
from .models import HitoDesarrollo, EvaluacionNino
from .serializers import HitoDesarrolloSerializer, EvaluacionNinoSerializer


class HitoFilter(django_filters.FilterSet):
    # ?edad=14 → hitos que corresponden a un niño de 14 meses (mín ≤ edad ≤ máx).
    edad = django_filters.NumberFilter(method="filtrar_edad")

    class Meta:
        model  = HitoDesarrollo
        fields = ["area", "activo"]

    def filtrar_edad(self, queryset, name, valor):
        if valor is None:
            return queryset
        return queryset.filter(edad_min_meses__lte=valor, edad_max_meses__gte=valor)


class HitoDesarrolloViewSet(viewsets.ModelViewSet):
    serializer_class   = HitoDesarrolloSerializer
    permission_classes = [IsAuthenticated, PermisoCatalogoHitos]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class    = HitoFilter
    search_fields      = ["nombre", "descripcion"]
    ordering_fields    = ["edad_min_meses", "edad_max_meses", "area", "nombre"]
    ordering           = ["edad_min_meses", "area", "nombre"]

    def get_queryset(self):
        qs = HitoDesarrollo.objects.all()
        u = self.request.user
        gestiona = u.is_authenticated and u.rol in ("admin", "directora")
        # Por defecto solo los activos. Admin/directora pueden pedir ?activo=false
        # para ver los desactivados y reactivarlos; el resto nunca los ve.
        if not gestiona or (self.action == "list" and "activo" not in self.request.query_params):
            qs = qs.filter(activo=True)
        return qs

    def perform_destroy(self, instance):
        # Borrado lógico: un DELETE real arrastraría (CASCADE) las evaluaciones
        # de todos los niños que usaron este hito.
        instance.activo = False
        instance.save(update_fields=["activo", "updated_at"])

    @action(detail=False, methods=["get"], url_path="por-edad")
    def por_edad(self, request):
        """Hitos que corresponden a una edad: GET por-edad/?meses=14 (opcional &area=)."""
        try:
            meses = int(request.query_params.get("meses", ""))
            if meses < 0:
                raise ValueError
        except ValueError:
            return Response({"meses": "Indica la edad en meses como número entero (0 o más)."}, status=400)
        hitos = self.filter_queryset(self.get_queryset()).filter(
            activo=True, edad_min_meses__lte=meses, edad_max_meses__gte=meses)
        return Response(HitoDesarrolloSerializer(hitos, many=True, context={"request": request}).data)


class EvaluacionFilter(django_filters.FilterSet):
    fecha_desde = django_filters.DateFilter(field_name="fecha", lookup_expr="gte")
    fecha_hasta = django_filters.DateFilter(field_name="fecha", lookup_expr="lte")

    class Meta:
        model  = EvaluacionNino
        # `hito__area` lo usa la pantalla de desarrollo para filtrar por área;
        # antes no estaba declarado y el filtro se ignoraba en silencio.
        fields = ["nino", "hito", "estado", "alerta_rezago", "educadora", "hito__area"]


def _personal_de(usuario):
    """Ficha de personal del usuario (None si es admin/directora sin ficha)."""
    return getattr(usuario, "perfil_personal", None)


class EvaluacionNinoViewSet(viewsets.ModelViewSet):
    queryset           = EvaluacionNino.objects.select_related("nino", "educadora", "hito").all()
    serializer_class   = EvaluacionNinoSerializer
    permission_classes = [IsAuthenticated, PermisoDesarrollo]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class    = EvaluacionFilter
    ordering_fields    = ["fecha", "created_at"]
    ordering           = ["-fecha", "-created_at"]

    def get_queryset(self):
        # Tutor: solo su hijo. Educadora/ayudante: solo niños de sus salas.
        return filtrar_por_alcance(super().get_queryset(), self.request.user, "nino")

    def perform_create(self, serializer):
        exigir_nino_en_alcance(self.request.user, serializer.validated_data["nino"])
        serializer.save(educadora=_personal_de(self.request.user))

    def perform_update(self, serializer):
        # El filtro del queryset solo protege el registro original; si en el PATCH
        # se cambia `nino`, el destino también debe estar dentro del alcance.
        nino = serializer.validated_data.get("nino")
        if nino is not None:
            exigir_nino_en_alcance(self.request.user, nino)
        serializer.save(educadora=serializer.instance.educadora or _personal_de(self.request.user))

    @action(detail=False, methods=["get"], url_path="alertas-rezago")
    def alertas_rezago(self, request):
        """
        Alertas VIGENTES: por cada niño+hito cuenta solo la evaluación más reciente,
        y solo si sigue marcada como rezago. Una alerta antigua que luego se superó
        (hito logrado o alerta retirada) ya no aparece. Devuelve una lista simple
        (el dashboard la usa directamente).
        """
        base = self.get_queryset()
        ninos = set(base.filter(alerta_rezago=True).values_list("nino_id", flat=True))
        ultimas = {}
        for ev in base.filter(nino_id__in=ninos).order_by("fecha", "created_at"):
            ultimas[(ev.nino_id, ev.hito_id)] = ev          # la última en iterar es la más reciente
        vigentes = sorted((e for e in ultimas.values() if e.alerta_rezago),
                          key=lambda e: (e.fecha, e.created_at), reverse=True)
        return Response(EvaluacionNinoSerializer(vigentes, many=True, context={"request": request}).data)
