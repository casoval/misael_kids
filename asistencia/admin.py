from django.contrib import admin
from .models import Asistencia

@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display   = ['inscripcion', 'fecha', 'estado', 'hora_entrada', 'hora_salida', 'retiro_autorizado']
    list_filter    = ['estado', 'retiro_autorizado', 'inscripcion__sucursal', 'inscripcion__sala']
    search_fields  = ['inscripcion__nino__nombres', 'inscripcion__nino__apellidos']
    date_hierarchy = 'fecha'
