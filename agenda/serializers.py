from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator
from .models import PlanificacionGrupal, PlanIndividual, ObjetivoIndividual, RegistroObjetivo


class RegistroObjetivoSerializer(serializers.ModelSerializer):
    resultado_display = serializers.CharField(source="get_resultado_display", read_only=True)
    educadora_nombre  = serializers.CharField(source="educadora.nombre_completo", read_only=True, default=None)

    class Meta:
        model  = RegistroObjetivo
        fields = ["id","objetivo","educadora","educadora_nombre","fecha","resultado","resultado_display","observacion","created_at","updated_at"]
        read_only_fields = ["id","educadora","created_at","updated_at"]
        validators = [
            UniqueTogetherValidator(
                queryset=RegistroObjetivo.objects.all(),
                fields=["objetivo", "fecha"],
                message="Ya hay un avance registrado para ese objetivo en esa fecha. Edítalo en lugar de crear otro.",
            )
        ]


class ObjetivoIndividualSerializer(serializers.ModelSerializer):
    area_display   = serializers.CharField(source="get_area_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    registros      = RegistroObjetivoSerializer(many=True, read_only=True)

    class Meta:
        model  = ObjetivoIndividual
        fields = ["id","plan","descripcion","area","area_display","estado","estado_display","orden","registros","created_at","updated_at"]
        read_only_fields = ["id","created_at","updated_at"]


class PlanIndividualSerializer(serializers.ModelSerializer):
    nino_nombre       = serializers.CharField(source="nino.nombre_completo", read_only=True)
    nino_foto         = serializers.ImageField(source="nino.foto", read_only=True)
    nino_sala         = serializers.SerializerMethodField()
    origen_display    = serializers.CharField(source="get_origen_display", read_only=True)
    creado_por_nombre = serializers.CharField(source="creado_por.nombre_completo", read_only=True, default=None)
    objetivos         = ObjetivoIndividualSerializer(many=True, read_only=True)

    class Meta:
        model  = PlanIndividual
        fields = ["id","nino","nino_nombre","nino_foto","nino_sala","creado_por","creado_por_nombre","origen","origen_display","descripcion","fecha_inicio","fecha_fin","activo","objetivos","created_at","updated_at"]
        read_only_fields = ["id","creado_por","created_at","updated_at"]

    def get_nino_sala(self, obj):
        """'Sala · Turno' de la inscripción activa del niño (vacío si no tiene)."""
        insc = getattr(obj.nino, "inscripciones_activas", None)   # precargado en la lista
        if insc is None:
            insc = list(obj.nino.inscripciones.filter(activa=True).select_related("sala", "turno"))
        return f"{insc[0].sala.nombre} · {insc[0].turno.nombre}" if insc else ""

    def validate(self, data):
        inicio = data.get("fecha_inicio", getattr(self.instance, "fecha_inicio", None))
        fin    = data.get("fecha_fin",    getattr(self.instance, "fecha_fin", None))
        if inicio and fin and fin < inicio:
            raise serializers.ValidationError(
                {"fecha_fin": "La fecha de fin no puede ser anterior a la de inicio."})
        return data


class PlanificacionGrupalSerializer(serializers.ModelSerializer):
    sala_nombre      = serializers.CharField(source="sala.nombre", read_only=True)
    turno_nombre     = serializers.CharField(source="turno.nombre", read_only=True)
    educadora_nombre = serializers.CharField(source="educadora.nombre_completo", read_only=True, default=None)

    class Meta:
        model  = PlanificacionGrupal
        fields = ["id","sala","sala_nombre","turno","turno_nombre","educadora","educadora_nombre","fecha","actividades","areas_trabajadas","observaciones","visible_padres","created_at","updated_at"]
        read_only_fields = ["id","educadora","created_at","updated_at"]
        validators = [
            UniqueTogetherValidator(
                queryset=PlanificacionGrupal.objects.all(),
                fields=["sala", "turno", "fecha"],
                message="Ya existe una planificación para esa sala, turno y fecha. Edítala en lugar de crear otra.",
            )
        ]

    def validate(self, data):
        # Antes la API aceptaba un turno de OTRA sala (solo la pantalla lo evitaba).
        sala  = data.get("sala",  getattr(self.instance, "sala", None))
        turno = data.get("turno", getattr(self.instance, "turno", None))
        if sala and turno and turno.sala_id != sala.id:
            raise serializers.ValidationError({"turno": "El turno no pertenece a la sala seleccionada."})
        return data
