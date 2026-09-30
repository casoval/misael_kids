from rest_framework import serializers
from .models import IncidenteSalud


class IncidenteSaludSerializer(serializers.ModelSerializer):
    tipo_display         = serializers.CharField(source="get_tipo_display", read_only=True)
    nino_nombre          = serializers.CharField(source="nino.nombre_completo", read_only=True)
    sucursal_nombre      = serializers.CharField(source="sucursal.nombre", read_only=True)
    reportado_por_nombre = serializers.SerializerMethodField()

    def get_reportado_por_nombre(self, obj):
        return obj.reportado_por.nombre_completo if obj.reportado_por else None

    class Meta:
        model  = IncidenteSalud
        fields = ["id","nino","nino_nombre","reportado_por","reportado_por_nombre","sucursal","sucursal_nombre","fecha","hora","tipo","tipo_display","descripcion","accion_tomada","notificado_tutor","hora_notificacion","requirio_atencion_medica","created_at","updated_at"]
        # reportado_por lo pone el servidor (no el formulario): antes el front enviaba
        # null y el guardado siempre fallaba con "este campo no puede ser nulo".
        read_only_fields = ["id","reportado_por","created_at","updated_at"]
