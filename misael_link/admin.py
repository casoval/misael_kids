from django.contrib import admin
from .models import Derivacion, PlanTrabajoMisael

@admin.register(Derivacion)
class DerivacionAdmin(admin.ModelAdmin):
    list_display  = ['nino', 'area_derivacion', 'estado', 'solicitado_por', 'fecha_solicitud', 'consentimiento_tutor']
    list_filter   = ['estado', 'consentimiento_tutor']
    search_fields = ['nino__nombres', 'nino__apellidos', 'area_derivacion']

@admin.register(PlanTrabajoMisael)
class PlanTrabajoMisaelAdmin(admin.ModelAdmin):
    list_display  = ['nino', 'profesional_nombre', 'fecha_inicio', 'fecha_fin', 'activo', 'consentimiento_tutor']
    list_filter   = ['activo', 'consentimiento_tutor']
    search_fields = ['nino__nombres', 'profesional_nombre']
