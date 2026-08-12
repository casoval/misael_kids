from rest_framework import serializers
from ninos.models import Nino
from .models import Derivacion, VinculoCentroMisael
class DerivacionSerializer(serializers.ModelSerializer):
    nino_nombre      = serializers.CharField(source="nino.nombre_completo", read_only=True)
    solicitado_por_nombre = serializers.SerializerMethodField()
    estado_display   = serializers.CharField(source="get_estado_display", read_only=True)
    class Meta:
        model  = Derivacion
        fields = ["id","nino","nino_nombre","solicitado_por","solicitado_por_nombre","motivo","area_derivacion","estado","estado_display","fecha_solicitud","fecha_respuesta","respuesta_centro","consentimiento_tutor","vista_por_centro","fecha_vista_por_centro","created_at","updated_at"]
        read_only_fields = ["id","solicitado_por","fecha_solicitud","vista_por_centro","fecha_vista_por_centro","created_at","updated_at"]

    def get_solicitado_por_nombre(self, obj):
        # solicitado_por ahora puede ser None (cuentas sin ficha de
        # Personal asociada también pueden derivar) — sin este chequeo,
        # obj.solicitado_por.usuario rompía con AttributeError.
        if obj.solicitado_por_id and obj.solicitado_por:
            return obj.solicitado_por.usuario.nombre_completo
        return None

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


# ═══════════════════════════════════════════════════════════════════
# Para la pantalla de vinculación del lado de Centro Misael: buscar
# niños de Misael Kids sin vincular todavía, ver su detalle para
# copiar datos, y listar los ya vinculados con sus derivaciones.
# ═══════════════════════════════════════════════════════════════════

class NinoBusquedaCentroMisaelSerializer(serializers.ModelSerializer):
    """Resultado liviano para el buscador de vinculación desde Centro Misael."""
    nombre_completo = serializers.CharField(read_only=True)
    tutor_principal = serializers.SerializerMethodField()

    class Meta:
        model = Nino
        fields = [
            "id", "nombre_completo", "nombres", "apellidos",
            "fecha_nacimiento", "genero", "activo", "tutor_principal",
        ]

    def get_tutor_principal(self, obj):
        rel = obj.tutores.filter(es_principal=True).select_related("tutor").first() \
            or obj.tutores.select_related("tutor").first()
        if not rel:
            return None
        return {
            "nombre": f"{rel.tutor.nombres} {rel.tutor.apellidos}",
            "parentesco": rel.tutor.parentesco,
            "parentesco_display": rel.tutor.get_parentesco_display(),
            "telefono": rel.tutor.telefono,
            "email": rel.tutor.email,
        }


class NinoDetalleCentroMisaelSerializer(NinoBusquedaCentroMisaelSerializer):
    """Detalle completo, para copiar datos al crear el Paciente en Centro Misael."""
    foto_url = serializers.SerializerMethodField()
    tutores = serializers.SerializerMethodField()

    class Meta(NinoBusquedaCentroMisaelSerializer.Meta):
        fields = NinoBusquedaCentroMisaelSerializer.Meta.fields + [
            "alergias", "condiciones_medicas", "medicacion_habitual",
            "foto_url", "tutores",
        ]

    def get_foto_url(self, obj):
        request = self.context.get("request")
        try:
            url = obj.foto.url if obj.foto else None
        except Exception:
            return None
        return request.build_absolute_uri(url) if (url and request) else url

    def get_tutores(self, obj):
        salida = []
        for rel in obj.tutores.select_related("tutor").order_by("-es_principal"):
            t = rel.tutor
            salida.append({
                "nombre_completo": f"{t.nombres} {t.apellidos}",
                "parentesco": t.parentesco,
                "telefono": t.telefono,
                "email": t.email,
                "es_principal": rel.es_principal,
            })
        return salida


class VinculoConDerivacionesSerializer(VinculoCentroMisaelSerializer):
    """VinculoCentroMisael + resumen de derivaciones, para el listado de vinculados."""
    derivaciones_count = serializers.SerializerMethodField()
    ultima_derivacion_estado = serializers.SerializerMethodField()

    class Meta(VinculoCentroMisaelSerializer.Meta):
        fields = VinculoCentroMisaelSerializer.Meta.fields + [
            "derivaciones_count", "ultima_derivacion_estado",
        ]

    def get_derivaciones_count(self, obj):
        return obj.nino.derivaciones.count()

    def get_ultima_derivacion_estado(self, obj):
        d = obj.nino.derivaciones.order_by("-fecha_solicitud").first()
        return d.get_estado_display() if d else None
