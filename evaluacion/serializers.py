from rest_framework import serializers
from .models import HitoDesarrollo, EvaluacionNino
class HitoDesarrolloSerializer(serializers.ModelSerializer):
    area_display = serializers.CharField(source="get_area_display", read_only=True)
    class Meta:
        model  = HitoDesarrollo
        fields = ["id","nombre","area","area_display","edad_min_meses","edad_max_meses","descripcion","activo","created_at","updated_at"]
        read_only_fields = ["id","created_at","updated_at"]

class EvaluacionNinoSerializer(serializers.ModelSerializer):
    nino_nombre    = serializers.CharField(source="nino.nombre_completo", read_only=True)
    hito_nombre    = serializers.CharField(source="hito.nombre", read_only=True)
    hito_area      = serializers.CharField(source="hito.get_area_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    class Meta:
        model  = EvaluacionNino
        fields = ["id","nino","nino_nombre","educadora","hito","hito_nombre","hito_area","fecha","estado","estado_display","observacion","alerta_rezago","created_at","updated_at"]
        read_only_fields = ["id","created_at","updated_at"]