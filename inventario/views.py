from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from .models import ItemInventario, MovimientoInventario
from .serializers import ItemInventarioSerializer, MovimientoInventarioSerializer

class ItemInventarioViewSet(viewsets.ModelViewSet):
    queryset = ItemInventario.objects.select_related("sucursal").prefetch_related("movimientos").all()
    serializer_class   = ItemInventarioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, DjangoFilterBackend]
    search_fields      = ["nombre"]
    filterset_fields   = ["sucursal","categoria","activo"]

    @action(detail=False, methods=["get"], url_path="alertas-stock")
    def alertas_stock(self, request):
        """Devuelve items con stock por debajo del mínimo."""
        from django.db.models import F
        items = self.queryset.filter(stock_actual__lte=F("stock_minimo"), activo=True)
        serializer = ItemInventarioSerializer(items, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="registrar-movimiento")
    def registrar_movimiento(self, request, pk=None):
        item = self.get_object()
        tipo     = request.data.get("tipo")
        cantidad = int(request.data.get("cantidad", 0))
        motivo   = request.data.get("motivo", "")
        from datetime import date
        mov = MovimientoInventario.objects.create(
            item=item, registrado_por=request.user,
            fecha=date.today(), tipo=tipo, cantidad=cantidad, motivo=motivo,
        )
        if tipo == "entrada":
            item.stock_actual += cantidad
        elif tipo == "salida":
            item.stock_actual = max(0, item.stock_actual - cantidad)
        elif tipo == "ajuste":
            item.stock_actual = cantidad
        item.save()
        return Response(MovimientoInventarioSerializer(mov).data)

class MovimientoInventarioViewSet(viewsets.ModelViewSet):
    queryset           = MovimientoInventario.objects.select_related("item","registrado_por").all()
    serializer_class   = MovimientoInventarioSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ["item","tipo","fecha"]
    ordering           = ["-fecha"]