from rest_framework import serializers
from .models import Derivacion, PlanTrabajoMisael, VinculoCentroMisael
class DerivacionSerializer(serializers.ModelSerializer):
    nino_nombre      = serializers.CharField(source="nino.nombre_completo", read_only=True)
    solicitado_por_nombre = serializers.CharField(source="solicitado_por.usuario.nombre_completo", read_only=True)
    estado_display   = serializers.CharField(source="get_estado_display", read_only=True)
    class Meta:
        model  = Derivacion
        fields = ["id","nino","nino_nombre","solicitado_por","solicitado_por_nombre","motivo","area_derivacion","estado","estado_display","fecha_solicitud","fecha_respuesta","respuesta_centro","consentimiento_tutor","created_at","updated_at"]
        read_only_fields = ["id","fecha_solicitud","created_at","updated_at"]

class PlanTrabajoMisaelSerializer(serializers.ModelSerializer):
    nino_nombre = serializers.CharField(source="nino.nombre_completo", read_only=True)
    class Meta:
        model  = PlanTrabajoMisael
        fields = ["id","nino","nino_nombre","derivacion","plan_individual",
                  "profesional_email","profesional_nombre","profesional_telefono",
                  "area_intervencion","frecuencia_sesiones",
                  "descripcion","notas_seguimiento","informe_pdf",
                  "fecha_inicio","fecha_fin","proxima_revision",
                  "activo","consentimiento_tutor","origen","documento_centro_id",
                  "created_at","updated_at"]
        read_only_fields = ["id","origen","documento_centro_id","created_at","updated_at"]


class VinculoCentroMisaelSerializer(serializers.ModelSerializer):
    nino_nombre = serializers.CharField(source="nino.nombre_completo", read_only=True)

    class Meta:
        model  = VinculoCentroMisael
        fields = ["id","nino","nino_nombre","paciente_centro_id","nombre_paciente_centro",
                  "estado_centro_cache","vinculado_por","fecha_vinculacion",
                  "ultima_sincronizacion","created_at","updated_at"]
        read_only_fields = ["id","fecha_vinculacion","created_at","updated_at"]