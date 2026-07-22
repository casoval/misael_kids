from django.contrib import admin
from .models import IncidenteSalud

@admin.register(IncidenteSalud)
class IncidenteSaludAdmin(admin.ModelAdmin):
    list_display   = ['nino', 'tipo', 'fecha', 'hora', 'sucursal', 'notificado_tutor', 'requirio_atencion_medica']
    list_filter    = ['tipo', 'notificado_tutor', 'requirio_atencion_medica', 'sucursal']
    search_fields  = ['nino__nombres', 'nino__apellidos']
    date_hierarchy = 'fecha'
