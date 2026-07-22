from django.contrib import admin
from .models import ItemInventario, MovimientoInventario

class MovimientoInline(admin.TabularInline):
    model  = MovimientoInventario
    extra  = 0
    fields = ['fecha', 'tipo', 'cantidad', 'motivo', 'registrado_por']

@admin.register(ItemInventario)
class ItemInventarioAdmin(admin.ModelAdmin):
    list_display  = ['nombre', 'sucursal', 'categoria', 'stock_actual', 'stock_minimo', 'alerta_stock_bajo', 'activo']
    list_filter   = ['categoria', 'sucursal', 'activo']
    search_fields = ['nombre']
    inlines       = [MovimientoInline]

@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display   = ['item', 'tipo', 'cantidad', 'fecha', 'motivo', 'registrado_por']
    list_filter    = ['tipo', 'item__sucursal']
    date_hierarchy = 'fecha'
