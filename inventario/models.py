"""
inventario/models.py
Control de stock de material didáctico y otros items por sucursal.
"""
from django.db import models
from core.models import ModeloBase


class ItemInventario(ModeloBase):
    CATEGORIA_DIDACTICO = 'didactico'
    CATEGORIA_JUGUETES  = 'juguetes'
    CATEGORIA_LIMPIEZA  = 'limpieza'
    CATEGORIA_MOBILIARIO = 'mobiliario'
    CATEGORIA_OTRO      = 'otro'
    CATEGORIAS = [
        (CATEGORIA_DIDACTICO,  'Material didáctico'),
        (CATEGORIA_JUGUETES,   'Juguetes'),
        (CATEGORIA_LIMPIEZA,   'Limpieza e higiene'),
        (CATEGORIA_MOBILIARIO, 'Mobiliario'),
        (CATEGORIA_OTRO,       'Otro'),
    ]

    sucursal      = models.ForeignKey('core.Sucursal', on_delete=models.CASCADE, related_name='inventario')
    nombre        = models.CharField(max_length=200)
    categoria     = models.CharField(max_length=20, choices=CATEGORIAS)
    descripcion   = models.TextField(blank=True)
    unidad        = models.CharField(max_length=50, help_text='Ej: unidades, cajas, litros')
    stock_actual  = models.PositiveIntegerField(default=0)
    stock_minimo  = models.PositiveIntegerField(default=1, help_text='Alerta cuando stock baje de este valor')
    activo        = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Item de inventario'
        verbose_name_plural = 'Inventario'
        ordering            = ['sucursal', 'categoria', 'nombre']

    def __str__(self):
        return f'{self.nombre} ({self.sucursal.nombre}) — Stock: {self.stock_actual}'

    @property
    def alerta_stock_bajo(self):
        return self.stock_actual <= self.stock_minimo


class MovimientoInventario(ModeloBase):
    TIPO_ENTRADA  = 'entrada'
    TIPO_SALIDA   = 'salida'
    TIPO_AJUSTE   = 'ajuste'
    TIPOS = [
        (TIPO_ENTRADA, 'Entrada (compra/donación)'),
        (TIPO_SALIDA,  'Salida (uso/pérdida)'),
        (TIPO_AJUSTE,  'Ajuste de inventario'),
    ]

    item         = models.ForeignKey(ItemInventario, on_delete=models.CASCADE, related_name='movimientos')
    registrado_por = models.ForeignKey('accounts.Usuario', on_delete=models.SET_NULL, null=True)
    fecha        = models.DateField()
    tipo         = models.CharField(max_length=10, choices=TIPOS)
    cantidad     = models.PositiveIntegerField()
    motivo       = models.CharField(max_length=300)

    class Meta:
        verbose_name = 'Movimiento de inventario'
        ordering     = ['-fecha']

    def __str__(self):
        return f'{self.item.nombre} — {self.get_tipo_display()} {self.cantidad} ({self.fecha})'
