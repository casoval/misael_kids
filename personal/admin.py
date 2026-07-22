from django.contrib import admin
from .models import Personal, AsignacionPersonal, AsistenciaPersonal

@admin.register(Personal)
class PersonalAdmin(admin.ModelAdmin):
    list_display  = ['__str__', 'ci', 'telefono', 'fecha_ingreso', 'activo']
    list_filter   = ['rol', 'activo']
    search_fields = ['usuario__nombres', 'usuario__apellidos', 'ci']

@admin.register(AsignacionPersonal)
class AsignacionPersonalAdmin(admin.ModelAdmin):
    list_display  = ['personal', 'sucursal', 'sala', 'turno', 'es_titular', 'fecha_inicio', 'fecha_fin', 'activa']
    list_filter   = ['sucursal', 'sala', 'activa', 'es_titular']
    search_fields = ['personal__usuario__nombres', 'personal__usuario__apellidos']

@admin.register(AsistenciaPersonal)
class AsistenciaPersonalAdmin(admin.ModelAdmin):
    list_display  = ['personal', 'sucursal', 'fecha', 'estado', 'hora_entrada', 'hora_salida']
    list_filter   = ['estado', 'sucursal', 'fecha']
    date_hierarchy = 'fecha'
