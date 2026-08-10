from django.contrib import admin
from .models import Derivacion

@admin.register(Derivacion)
class DerivacionAdmin(admin.ModelAdmin):
    list_display  = ['nino', 'area_derivacion', 'estado', 'solicitado_por', 'fecha_solicitud', 'consentimiento_tutor', 'vista_por_centro']
    list_filter   = ['estado', 'consentimiento_tutor', 'vista_por_centro']
    search_fields = ['nino__nombres', 'nino__apellidos', 'area_derivacion']
