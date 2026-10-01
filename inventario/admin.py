from django.contrib import admin
from .models import ItemInventario, MovimientoInventario


class MovimientoInline(admin.TabularInline):
    model  = MovimientoInventario
    extra  = 0
    fields = ['fecha', 'tipo', 'cantidad', 'stock_anterior', 'stock_resultante', 'motivo', 'registrado_por']
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ItemInventario)
class ItemInventarioAdmin(admin.ModelAdmin):
    list_display  = ['nombre', 'sucursal', 'categoria', 'stock_actual', 'stock_minimo', 'alerta_stock_bajo', 'activo']
    list_filter   = ['categoria', 'sucursal', 'activo']
    search_fields = ['nombre']
    inlines       = [MovimientoInline]

    def get_readonly_fields(self, request, obj=None):
        # Al editar, el stock solo cambia registrando movimientos (queda historial).
        return ['stock_actual'] if obj else []


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display   = ['item', 'tipo', 'cantidad', 'stock_anterior', 'stock_resultante', 'fecha', 'motivo', 'registrado_por']
    list_filter    = ['tipo', 'item__sucursal']
    date_hierarchy = 'fecha'

    # Solo consulta: crear/editar/borrar aquí descuadraría el stock del ítem.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
