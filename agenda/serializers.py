from rest_framework import serializers
from .models import PlanificacionGrupal, PlanIndividual, ObjetivoIndividual, RegistroObjetivo

class RegistroObjetivoSerializer(serializers.ModelSerializer):
    resultado_display = serializers.CharField(source="get_resultado_display", read_only=True)
    educadora_nombre  = serializers.CharField(source="educadora.usuario.nombre_completo", read_only=True, default=None)
    class Meta:
        model  = RegistroObjetivo
        fields = ["id","objetivo","educadora","educadora_nombre","fecha","resultado","resultado_display","observacion","created_at","updated_at"]
        read_only_fields = ["id","educadora","created_at","updated_at"]

class ObjetivoIndividualSerializer(serializers.ModelSerializer):
    area_display   = serializers.CharField(source="get_area_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    registros      = RegistroObjetivoSerializer(many=True, read_only=True)
    class Meta:
        model  = ObjetivoIndividual
        fields = ["id","plan","descripcion","area","area_display","estado","estado_display","orden","registros","created_at","updated_at"]
        read_only_fields = ["id","created_at","updated_at"]

class PlanIndividualSerializer(serializers.ModelSerializer):
    nino_nombre   = serializers.CharField(source="nino.nombre_completo", read_only=True)
    origen_display = serializers.CharField(source="get_origen_display", read_only=True)
    creado_por_nombre = serializers.CharField(source="creado_por.usuario.nombre_completo", read_only=True, default=None)
    objetivos     = ObjetivoIndividualSerializer(many=True, read_only=True)
    class Meta:
        model  = PlanIndividual
        fields = ["id","nino","nino_nombre","creado_por","creado_por_nombre","origen","origen_display","descripcion","fecha_inicio","fecha_fin","activo","objetivos","created_at","updated_at"]
        read_only_fields = ["id","creado_por","created_at","updated_at"]

class PlanificacionGrupalSerializer(serializers.ModelSerializer):
    sala_nombre      = serializers.CharField(source="sala.nombre", read_only=True)
    turno_nombre     = serializers.CharField(source="turno.nombre", read_only=True)
    educadora_nombre = serializers.CharField(source="educadora.usuario.nombre_completo", read_only=True, default=None)
    class Meta:
        model  = PlanificacionGrupal
        fields = ["id","sala","sala_nombre","turno","turno_nombre","educadora","educadora_nombre","fecha","actividades","areas_trabajadas","observaciones","visible_padres","created_at","updated_at"]
        read_only_fields = ["id","educadora","created_at","updated_at"]