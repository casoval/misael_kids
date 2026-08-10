from rest_framework import serializers
from .models import Derivacion, VinculoCentroMisael
class DerivacionSerializer(serializers.ModelSerializer):
    nino_nombre      = serializers.CharField(source="nino.nombre_completo", read_only=True)
    solicitado_por_nombre = serializers.CharField(source="solicitado_por.usuario.nombre_completo", read_only=True)
    estado_display   = serializers.CharField(source="get_estado_display", read_only=True)
    class Meta:
        model  = Derivacion
        fields = ["id","nino","nino_nombre","solicitado_por","solicitado_por_nombre","motivo","area_derivacion","estado","estado_display","fecha_solicitud","fecha_respuesta","respuesta_centro","consentimiento_tutor","vista_por_centro","fecha_vista_por_centro","created_at","updated_at"]
        read_only_fields = ["id","fecha_solicitud","vista_por_centro","fecha_vista_por_centro","created_at","updated_at"]

    def validate_nino(self, nino):
        if not hasattr(nino, 'vinculo_centro_misael'):
            raise serializers.ValidationError(
                'Este niño todavía no está vinculado con Centro Misael. '
                'Vincúlalo primero en la pestaña "Vincular con Centro Misael".'
            )
        return nino


class VinculoCentroMisaelSerializer(serializers.ModelSerializer):
    nino_nombre = serializers.CharField(source="nino.nombre_completo", read_only=True)

    class Meta:
        model  = VinculoCentroMisael
        fields = ["id","nino","nino_nombre","paciente_centro_id","nombre_paciente_centro",
                  "estado_centro_cache","vinculado_por","fecha_vinculacion",
                  "ultima_sincronizacion","created_at","updated_at"]
        read_only_fields = ["id","fecha_vinculacion","created_at","updated_at"]
