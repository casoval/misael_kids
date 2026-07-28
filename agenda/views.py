from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from personal.models import Personal
from .models import PlanificacionGrupal, PlanIndividual, ObjetivoIndividual, RegistroObjetivo
from .serializers import PlanificacionGrupalSerializer, PlanIndividualSerializer, ObjetivoIndividualSerializer, RegistroObjetivoSerializer
from accounts.permissions import filtrar_por_tutor


def _personal_del_usuario(request):
    """
    Registro de Personal vinculado al usuario logueado, o None si no tiene
    uno (p. ej. una cuenta admin sin ficha de personal creada todavía).
    No bloquea la creación: si no hay Personal, el registro simplemente
    queda sin 'autor' asignado en vez de impedir guardar.
    """
    return Personal.objects.filter(usuario=request.user).first()


class PlanificacionGrupalViewSet(viewsets.ModelViewSet):
    queryset = PlanificacionGrupal.objects.select_related("sala","turno","educadora__usuario").all()
    serializer_class   = PlanificacionGrupalSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ["sala","turno","fecha","visible_padres"]
    ordering           = ["-fecha"]

    def get_queryset(self):
        qs = super().get_queryset()
        usuario = self.request.user
        if usuario.rol == 'tutor':
            # Un tutor solo debe ver la planificación de la sala/turno de
            # SU hijo, y solo lo que la educadora marcó como visible para
            # padres (visible_padres) — antes ni siquiera se respetaba esa
            # bandera: cualquier tutor veía TODA la planificación de TODAS
            # las salas, incluida la marcada como interna.
            from inscripciones.models import Inscripcion
            pares = Inscripcion.objects.filter(
                nino__tutores__tutor__usuario=usuario, activa=True
            ).values_list('sala_id', 'turno_id').distinct()
            if not pares:
                return qs.none()
            filtro = Q()
            for sala_id, turno_id in pares:
                filtro |= Q(sala_id=sala_id, turno_id=turno_id)
            qs = qs.filter(filtro, visible_padres=True)
        return qs

    def perform_create(self, serializer):
        serializer.save(educadora=_personal_del_usuario(self.request))

class PlanIndividualViewSet(viewsets.ModelViewSet):
    queryset = PlanIndividual.objects.select_related("nino","creado_por__usuario").prefetch_related("objetivos__registros").all()
    serializer_class   = PlanIndividualSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    search_fields      = ["nino__nombres","nino__apellidos"]
    filterset_fields   = ["nino","origen","activo"]

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')

    def perform_create(self, serializer):
        serializer.save(creado_por=_personal_del_usuario(self.request))

class ObjetivoIndividualViewSet(viewsets.ModelViewSet):
    queryset           = ObjetivoIndividual.objects.select_related("plan").prefetch_related("registros").all()
    serializer_class   = ObjetivoIndividualSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ["plan","area","estado"]

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'plan__nino')

class RegistroObjetivoViewSet(viewsets.ModelViewSet):
    queryset           = RegistroObjetivo.objects.select_related("objetivo","educadora__usuario").all()
    serializer_class   = RegistroObjetivoSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ["objetivo","educadora","fecha","resultado"]
    ordering           = ["-fecha"]

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'objetivo__plan__nino')

    def perform_create(self, serializer):
        serializer.save(educadora=_personal_del_usuario(self.request))