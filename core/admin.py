from django.contrib import admin
from .models import Sucursal, Sala, Turno

@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display  = ['nombre', 'ciudad', 'directora', 'activa']
    list_filter   = ['activa', 'ciudad']
    search_fields = ['nombre', 'direccion']

class TurnoInline(admin.TabularInline):
    model  = Turno
    extra  = 1
    fields = ['nombre', 'tipo', 'hora_inicio', 'hora_fin', 'costo_mensual', 'costo_diario', 'activo']

@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display  = ['nombre', 'sucursal', 'rango_edad', 'capacidad_maxima', 'activa']
    list_filter   = ['sucursal', 'activa']
    search_fields = ['nombre']
    inlines       = [TurnoInline]

@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display  = ['nombre', 'sala', 'tipo', 'hora_inicio', 'hora_fin', 'costo_mensual', 'costo_diario', 'activo']
    list_filter   = ['tipo', 'sala__sucursal', 'activo']
    search_fields = ['nombre', 'sala__nombre']
