from rest_framework import serializers
from .models import ItemInventario, MovimientoInventario


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    """Solo lectura: los movimientos se crean únicamente con `items/<id>/registrar-movimiento/`."""
    tipo_display          = serializers.CharField(source="get_tipo_display", read_only=True)
    registrado_por_nombre = serializers.CharField(source="registrado_por.nombre_completo", read_only=True, default=None)

    class Meta:
        model  = MovimientoInventario
        fields = ["id", "item", "registrado_por", "registrado_por_nombre", "fecha", "tipo", "tipo_display",
                  "cantidad", "motivo", "stock_anterior", "stock_resultante", "created_at", "updated_at"]
        read_only_fields = fields


class ItemInventarioSerializer(serializers.ModelSerializer):
    categoria_display = serializers.CharField(source="get_categoria_display", read_only=True)
    sucursal_nombre   = serializers.CharField(source="sucursal.nombre", read_only=True)
    alerta_stock_bajo = serializers.BooleanField(read_only=True)

    class Meta:
        model  = ItemInventario
        fields = ["id", "sucursal", "sucursal_nombre", "nombre", "categoria", "categoria_display", "descripcion",
                  "unidad", "stock_actual", "stock_minimo", "alerta_stock_bajo", "activo", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_nombre(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("El nombre es obligatorio.")
        return valor

    def validate_unidad(self, valor):
        valor = valor.strip()
        if not valor:
            raise serializers.ValidationError("La unidad de medida es obligatoria.")
        return valor

    def validate(self, attrs):
        inst = self.instance
        # El stock solo cambia con movimientos (queda historial). Se acepta como stock INICIAL al crear;
        # al editar un ítem, cambiarlo por aquí dejaría el stock sin explicación en el historial.
        if inst is not None and "stock_actual" in attrs and attrs["stock_actual"] != inst.stock_actual:
            raise serializers.ValidationError(
                {"stock_actual": "El stock no se edita directamente: registra una entrada, salida o ajuste."})
        nombre   = attrs.get("nombre", getattr(inst, "nombre", None))
        sucursal = attrs.get("sucursal", getattr(inst, "sucursal", None))
        if nombre and sucursal:
            repetido = ItemInventario.objects.filter(sucursal=sucursal, nombre__iexact=nombre.strip())
            if inst:
                repetido = repetido.exclude(pk=inst.pk)
            existente = repetido.first()
            if existente:
                raise serializers.ValidationError({"nombre": (
                    "Ya existe un ítem con ese nombre en esta sucursal"
                    + (" (está desactivado)." if not existente.activo else "."))})
        return attrs
