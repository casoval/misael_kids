from django.contrib import admin
from .models import Mensaje, Aviso

@admin.register(Mensaje)
class MensajeAdmin(admin.ModelAdmin):
    list_display  = ['remitente', 'destinatario', 'asunto', 'leido', 'created_at']
    list_filter   = ['leido']
    search_fields = ['asunto', 'remitente__nombres', 'destinatario__nombres']

@admin.register(Aviso)
class AvisoAdmin(admin.ModelAdmin):
    list_display  = ['titulo', 'autor', 'sucursal', 'sala', 'importante', 'publicado_en']
    list_filter   = ['importante', 'sucursal', 'sala']
    search_fields = ['titulo']
