from rest_framework import serializers
from .models import IncidenteSalud
class IncidenteSaludSerializer(serializers.ModelSerializer):
    tipo_display  = serializers.CharField(source="get_tipo_display", read_only=True)
    nino_nombre   = serializers.CharField(source="nino.nombre_completo", read_only=True)
    reportado_por_nombre = serializers.CharField(source="reportado_por.usuario.nombre_completo", read_only=True)
    class Meta:
        model  = IncidenteSalud
        fields = ["id","nino","nino_nombre","reportado_por","reportado_por_nombre","sucursal","fecha","hora","tipo","tipo_display","descripcion","accion_tomada","notificado_tutor","hora_notificacion","requirio_atencion_medica","created_at","updated_at"]
        read_only_fields = ["id","created_at","updated_at"]