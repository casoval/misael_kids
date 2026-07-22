from django.contrib import admin
from .models import HitoDesarrollo, EvaluacionNino

@admin.register(HitoDesarrollo)
class HitoDesarrolloAdmin(admin.ModelAdmin):
    list_display  = ['nombre', 'area', 'edad_min_meses', 'edad_max_meses', 'activo']
    list_filter   = ['area', 'activo']
    search_fields = ['nombre']

@admin.register(EvaluacionNino)
class EvaluacionNinoAdmin(admin.ModelAdmin):
    list_display   = ['nino', 'hito', 'estado', 'fecha', 'alerta_rezago', 'educadora']
    list_filter    = ['estado', 'alerta_rezago', 'hito__area']
    search_fields  = ['nino__nombres', 'nino__apellidos']
    date_hierarchy = 'fecha'
