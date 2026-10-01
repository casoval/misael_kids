from datetime import date

import django_filters
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from accounts.permissions import PermisoInventario
from .models import ItemInventario, MovimientoInventario
from .serializers import ItemInventarioSerializer, MovimientoInventarioSerializer


class ItemFilter(django_filters.FilterSet):
    # ?bajo_stock=true → solo ítems con stock igual o menor al mínimo (se filtra en el servidor
    # para que funcione con paginación; antes la pantalla filtraba solo lo que ya había cargado).
    bajo_stock = django_filters.BooleanFilter(method="filtrar_bajo_stock")

    class Meta:
        model  = ItemInventario
        fields = ["sucursal", "categoria", "activo"]

    def filtrar_bajo_stock(self, queryset, name, valor):
        if valor is None:
            return queryset
        bajo = {"stock_actual__lte": F("stock_minimo")}
        return queryset.filter(**bajo) if valor else queryset.exclude(**bajo)


class ItemInventarioViewSet(viewsets.ModelViewSet):
    queryset           = ItemInventario.objects.select_related("sucursal").all()
    serializer_class   = ItemInventarioSerializer
    permission_classes = [IsAuthenticated, PermisoInventario]
    filter_backends    = [filters.SearchFilter, DjangoFilterBackend]
    search_fields      = ["nombre"]
    filterset_class    = ItemFilter

    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        gestiona = u.is_authenticated and u.rol in PermisoInventario.ROLES_GESTION
        # Por defecto solo los activos. Oficina puede pedir ?activo=false para ver los desactivados.
        if not gestiona or (self.action == "list" and "activo" not in self.request.query_params):
            qs = qs.filter(activo=True)
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            item = serializer.save()
            if item.stock_actual > 0:        # el stock inicial también queda en el historial
                MovimientoInventario.objects.create(
                    item=item, registrado_por=self.request.user, fecha=timezone.localdate(),
                    tipo=MovimientoInventario.TIPO_ENTRADA, cantidad=item.stock_actual,
                    motivo="Stock inicial", stock_anterior=0, stock_resultante=item.stock_actual)

    def perform_destroy(self, instance):
        # Borrado lógico: un DELETE real arrastraría (CASCADE) todo el historial de movimientos.
        instance.activo = False
        instance.save(update_fields=["activo", "updated_at"])

    @action(detail=False, methods=["get"], url_path="alertas-stock")
    def alertas_stock(self, request):
        """Ítems con stock igual o menor al mínimo. Respeta ?sucursal=, ?categoria= y ?search=."""
        items = self.filter_queryset(self.get_queryset()).filter(
            stock_actual__lte=F("stock_minimo"), activo=True)
        return Response(ItemInventarioSerializer(items, many=True, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="registrar-movimiento")
    def registrar_movimiento(self, request, pk=None):
        item = self.get_object()
        error = lambda campo, msg: Response({campo: [msg]}, status=status.HTTP_400_BAD_REQUEST)

        tipo = request.data.get("tipo")
        if tipo not in dict(MovimientoInventario.TIPOS):
            return error("tipo", "Tipo de movimiento no válido: usa entrada, salida o ajuste.")
        try:
            cantidad = int(request.data.get("cantidad"))
        except (TypeError, ValueError):
            return error("cantidad", "La cantidad debe ser un número entero.")
        # Entrada/salida mueven al menos 1; un ajuste fija el stock total y puede ser 0 (se agotó).
        if cantidad < (0 if tipo == MovimientoInventario.TIPO_AJUSTE else 1):
            return error("cantidad", "La cantidad debe ser mayor a 0." if tipo != "ajuste"
                         else "El stock no puede ser negativo.")
        motivo = str(request.data.get("motivo") or "").strip()
        if not motivo:
            return error("motivo", "Indica el motivo del movimiento.")
        if len(motivo) > 300:
            return error("motivo", "El motivo no puede superar los 300 caracteres.")
        try:
            fecha = date.fromisoformat(request.data.get("fecha") or timezone.localdate().isoformat())
        except (TypeError, ValueError):
            return error("fecha", "Fecha inválida, usa AAAA-MM-DD.")
        if fecha > timezone.localdate():
            return error("fecha", "La fecha del movimiento no puede ser futura.")

        with transaction.atomic():
            # Se bloquea la fila: dos movimientos simultáneos no pueden pisarse el stock.
            item = ItemInventario.objects.select_for_update().get(pk=item.pk)
            if not item.activo:
                return error("item", "Este ítem está desactivado.")
            anterior = item.stock_actual
            if tipo == MovimientoInventario.TIPO_ENTRADA:
                nuevo = anterior + cantidad
            elif tipo == MovimientoInventario.TIPO_SALIDA:
                if cantidad > anterior:
                    return error("cantidad", f"No hay suficiente stock: hay {anterior} {item.unidad} "
                                             f"y quieres retirar {cantidad}.")
                nuevo = anterior - cantidad
            else:
                nuevo = cantidad
            mov = MovimientoInventario.objects.create(
                item=item, registrado_por=request.user, fecha=fecha, tipo=tipo, cantidad=cantidad,
                motivo=motivo, stock_anterior=anterior, stock_resultante=nuevo)
            item.stock_actual = nuevo
            item.save(update_fields=["stock_actual", "updated_at"])
        return Response({**MovimientoInventarioSerializer(mov).data, "stock_actual": nuevo,
                         "alerta_stock_bajo": item.alerta_stock_bajo}, status=status.HTTP_201_CREATED)


class MovimientoInventarioViewSet(viewsets.ReadOnlyModelViewSet):
    """Historial de solo lectura: editar o borrar movimientos descuadraría el stock."""
    queryset           = MovimientoInventario.objects.select_related("item", "registrado_por").all()
    serializer_class   = MovimientoInventarioSerializer
    permission_classes = [IsAuthenticated, PermisoInventario]
    filter_backends    = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields   = ["item", "tipo", "fecha"]
    ordering           = ["-fecha", "-created_at"]
