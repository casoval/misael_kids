"""
agenda/filters.py
Filtros de la agenda pedagógica.
"""
import django_filters as df
from inscripciones.models import Inscripcion
from .models import PlanificacionGrupal, PlanIndividual


class PlanificacionFilter(df.FilterSet):
    # Rango de fechas resuelto en el servidor: antes el calendario descargaba
    # TODAS las planificaciones y filtraba el mes en el navegador.
    desde    = df.DateFilter(field_name='fecha', lookup_expr='gte')
    hasta    = df.DateFilter(field_name='fecha', lookup_expr='lte')
    sucursal = df.UUIDFilter(field_name='sala__sucursal')

    class Meta:
        model  = PlanificacionGrupal
        fields = ['sala', 'turno', 'fecha', 'visible_padres']


class PlanIndividualFilter(df.FilterSet):
    """
    Además de por niño/origen/activo, permite ver solo los planes de los niños
    inscritos (inscripción activa) en una sucursal, sala o turno concretos.
    """
    sucursal = df.UUIDFilter(method='por_sucursal')
    sala     = df.UUIDFilter(method='por_sala')
    turno    = df.UUIDFilter(method='por_turno')

    class Meta:
        model  = PlanIndividual
        fields = ['nino', 'origen', 'activo']

    @staticmethod
    def _inscritos(queryset, **filtro):
        return queryset.filter(
            nino__in=Inscripcion.objects.filter(activa=True, **filtro).values('nino')
        )

    def por_sucursal(self, queryset, name, value):
        return self._inscritos(queryset, sucursal=value)

    def por_sala(self, queryset, name, value):
        return self._inscritos(queryset, sala=value)

    def por_turno(self, queryset, name, value):
        return self._inscritos(queryset, turno=value)
