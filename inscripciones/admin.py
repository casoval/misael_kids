from django.contrib import admin
from .models import Inscripcion, Cobro, Pago

class CobroInline(admin.TabularInline):
    model  = Cobro
    extra  = 0
    fields = ['tipo', 'periodo', 'monto_final', 'fecha_vencimiento', 'estado', 'fecha_pago', 'metodo_pago']
    readonly_fields = ['fecha_vencimiento']

class PagoInline(admin.TabularInline):
    model  = Pago
    extra  = 0
    fields = ['monto', 'fecha_pago', 'metodo_pago', 'registrado_por', 'observacion']

@admin.register(Inscripcion)
class InscripcionAdmin(admin.ModelAdmin):
    list_display  = ['nino', 'sucursal', 'sala', 'turno', 'modalidad_pago', 'tipo_ajuste', 'costo_mensual_final', 'activa']
    list_filter   = ['sucursal', 'sala', 'modalidad_pago', 'tipo_ajuste', 'activa']
    search_fields = ['nino__nombres', 'nino__apellidos']
    inlines       = [CobroInline]

@admin.register(Cobro)
class CobroAdmin(admin.ModelAdmin):
    list_display   = ['__str__', 'tipo', 'monto_final', 'monto_pagado', 'saldo_pendiente',
                       'fecha_vencimiento', 'estado', 'fecha_pago', 'metodo_pago']
    list_filter    = ['tipo', 'estado', 'metodo_pago']
    search_fields  = ['inscripcion__nino__nombres', 'inscripcion__nino__apellidos']
    date_hierarchy = 'fecha_emision'
    readonly_fields = ['fecha_emision']
    inlines        = [PagoInline]

@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display  = ['cobro', 'monto', 'fecha_pago', 'metodo_pago', 'registrado_por']
    list_filter   = ['metodo_pago', 'fecha_pago']
    date_hierarchy = 'fecha_pago'
