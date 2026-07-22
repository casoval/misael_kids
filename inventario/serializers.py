from rest_framework import serializers
from .models import ItemInventario, MovimientoInventario
class MovimientoInventarioSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    class Meta:
        model  = MovimientoInventario
        fields = ["id","item","registrado_por","fecha","tipo","tipo_display","cantidad","motivo","created_at","updated_at"]
        read_only_fields = ["id","created_at","updated_at"]

class ItemInventarioSerializer(serializers.ModelSerializer):
    categoria_display = serializers.CharField(source="get_categoria_display", read_only=True)
    sucursal_nombre   = serializers.CharField(source="sucursal.nombre", read_only=True)
    alerta_stock_bajo = serializers.BooleanField(read_only=True)
    movimientos       = MovimientoInventarioSerializer(many=True, read_only=True)
    class Meta:
        model  = ItemInventario
        fields = ["id","sucursal","sucursal_nombre","nombre","categoria","categoria_display","descripcion","unidad","stock_actual","stock_minimo","alerta_stock_bajo","activo","movimientos","created_at","updated_at"]
        read_only_fields = ["id","created_at","updated_at"]