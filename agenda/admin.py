from django.contrib import admin
from .models import PlanificacionGrupal, PlanIndividual, ObjetivoIndividual, RegistroObjetivo

@admin.register(PlanificacionGrupal)
class PlanificacionGrupalAdmin(admin.ModelAdmin):
    list_display  = ['sala', 'turno', 'educadora', 'fecha', 'visible_padres']
    list_filter   = ['sala__sucursal', 'sala', 'turno', 'visible_padres']
    date_hierarchy = 'fecha'

class ObjetivoInline(admin.TabularInline):
    model  = ObjetivoIndividual
    extra  = 1
    fields = ['descripcion', 'area', 'estado', 'orden']

@admin.register(PlanIndividual)
class PlanIndividualAdmin(admin.ModelAdmin):
    list_display  = ['nino', 'origen', 'creado_por', 'fecha_inicio', 'fecha_fin', 'activo']
    list_filter   = ['origen', 'activo']
    search_fields = ['nino__nombres', 'nino__apellidos']
    inlines       = [ObjetivoInline]

@admin.register(RegistroObjetivo)
class RegistroObjetivoAdmin(admin.ModelAdmin):
    list_display   = ['objetivo', 'educadora', 'fecha', 'resultado']
    list_filter    = ['resultado']
    date_hierarchy = 'fecha'
