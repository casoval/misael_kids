from django.utils import timezone
from rest_framework import serializers

from .models import HitoDesarrollo, EvaluacionNino


class HitoDesarrolloSerializer(serializers.ModelSerializer):
    area_display = serializers.CharField(source="get_area_display", read_only=True)

    class Meta:
        model  = HitoDesarrollo
        fields = ["id", "nombre", "area", "area_display", "edad_min_meses", "edad_max_meses",
                  "descripcion", "activo", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        inst = self.instance
        minimo = attrs.get("edad_min_meses", getattr(inst, "edad_min_meses", None))
        maximo = attrs.get("edad_max_meses", getattr(inst, "edad_max_meses", None))
        if minimo is not None and maximo is not None and minimo > maximo:
            raise serializers.ValidationError(
                {"edad_max_meses": "La edad máxima no puede ser menor que la mínima."})
        nombre = attrs.get("nombre", getattr(inst, "nombre", None))
        area   = attrs.get("area", getattr(inst, "area", None))
        if nombre and area:
            repetido = HitoDesarrollo.objects.filter(nombre__iexact=nombre.strip(), area=area)
            if inst:
                repetido = repetido.exclude(pk=inst.pk)
            if repetido.exists():
                raise serializers.ValidationError(
                    {"nombre": "Ya existe un hito con ese nombre en esta área."})
        return attrs


class EvaluacionNinoSerializer(serializers.ModelSerializer):
    nino_nombre      = serializers.CharField(source="nino.nombre_completo", read_only=True)
    nino_foto        = serializers.ImageField(source="nino.foto", read_only=True)
    nino_genero      = serializers.CharField(source="nino.genero", read_only=True)
    hito_nombre      = serializers.CharField(source="hito.nombre", read_only=True)
    hito_area        = serializers.CharField(source="hito.get_area_display", read_only=True)
    # Código del área (p. ej. "lenguaje"): `hito_area` es el texto para mostrar, y el
    # frontend necesita el código para agrupar y elegir el ícono.
    hito_area_codigo = serializers.CharField(source="hito.area", read_only=True)
    estado_display   = serializers.CharField(source="get_estado_display", read_only=True)
    educadora_nombre = serializers.SerializerMethodField()

    class Meta:
        model  = EvaluacionNino
        fields = ["id", "nino", "nino_nombre", "nino_foto", "nino_genero", "educadora", "educadora_nombre", "hito", "hito_nombre",
                  "hito_area", "hito_area_codigo", "fecha", "estado", "estado_display", "observacion",
                  "alerta_rezago", "created_at", "updated_at"]
        # La educadora NUNCA la decide el cliente: la pone el servidor según quién inicia sesión.
        read_only_fields = ["id", "educadora", "created_at", "updated_at"]

    def get_educadora_nombre(self, obj):
        return obj.educadora.nombre_completo if obj.educadora_id else None

    def validate_fecha(self, valor):
        # Hora de Bolivia (TIME_ZONE del proyecto), no la del sistema del servidor.
        if valor > timezone.localdate():
            raise serializers.ValidationError("La fecha de evaluación no puede ser futura.")
        return valor

    def validate_hito(self, hito):
        # Un hito desactivado no se puede evaluar, salvo que sea el que ya tenía esta evaluación.
        mismo = self.instance is not None and self.instance.hito_id == hito.pk
        if not hito.activo and not mismo:
            raise serializers.ValidationError("Este hito está desactivado y no se puede evaluar.")
        return hito

    def validate(self, attrs):
        estado = attrs.get("estado", getattr(self.instance, "estado", None))
        # Un hito ya logrado no puede seguir marcado como rezago.
        if estado == EvaluacionNino.ESTADO_LOGRADO:
            attrs["alerta_rezago"] = False
        return attrs
