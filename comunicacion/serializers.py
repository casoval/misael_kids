from rest_framework import serializers
from .models import Mensaje, Aviso
class MensajeSerializer(serializers.ModelSerializer):
    remitente_nombre    = serializers.CharField(source="remitente.nombre_completo", read_only=True)
    destinatario_nombre = serializers.CharField(source="destinatario.nombre_completo", read_only=True)
    nino_nombre         = serializers.CharField(source="nino.nombre_completo", read_only=True)
    class Meta:
        model  = Mensaje
        fields = ["id","remitente","remitente_nombre","destinatario","destinatario_nombre","nino","nino_nombre","asunto","cuerpo","leido","leido_en","created_at","updated_at"]
        read_only_fields = ["id","leido_en","created_at","updated_at"]

class AvisoSerializer(serializers.ModelSerializer):
    autor_nombre    = serializers.CharField(source="autor.nombre_completo", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    sala_nombre     = serializers.CharField(source="sala.nombre", read_only=True)
    class Meta:
        model  = Aviso
        fields = ["id","autor","autor_nombre","sucursal","sucursal_nombre","sala","sala_nombre","turno","titulo","cuerpo","importante","publicado_en","created_at","updated_at"]
        read_only_fields = ["id","publicado_en","created_at","updated_at"]