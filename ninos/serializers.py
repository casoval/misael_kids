"""
ninos/serializers.py
"""
from rest_framework import serializers
from .models import Nino, Tutor, NinoTutor, PersonaAutorizada, Documento


class TutorSerializer(serializers.ModelSerializer):
    parentesco_display = serializers.CharField(source='get_parentesco_display', read_only=True)

    class Meta:
        model  = Tutor
        fields = [
            'id', 'usuario', 'nombres', 'apellidos', 'ci',
            'telefono', 'telefono_alt', 'email',
            'parentesco', 'parentesco_display', 'activo',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PersonaAutorizadaSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PersonaAutorizada
        fields = [
            'id', 'nino', 'nombres', 'apellidos', 'ci',
            'telefono', 'parentesco', 'foto',
            'vigencia_desde', 'vigencia_hasta', 'activa',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        if data.get('vigencia_desde') and data.get('vigencia_hasta'):
            if data['vigencia_desde'] > data['vigencia_hasta']:
                raise serializers.ValidationError(
                    'La fecha de inicio de vigencia debe ser anterior a la fecha de fin.'
                )
        return data


class DocumentoSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)

    class Meta:
        model  = Documento
        fields = [
            'id', 'nino', 'tipo', 'tipo_display', 'nombre',
            'archivo', 'fecha_subida', 'verificado', 'observacion',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'fecha_subida', 'created_at', 'updated_at']


class NinoTutorSerializer(serializers.ModelSerializer):
    tutor_nombre = serializers.CharField(
        source='tutor.__str__', read_only=True
    )

    class Meta:
        model  = NinoTutor
        fields = ['id', 'nino', 'tutor', 'tutor_nombre', 'es_principal', 'puede_retirar']
        read_only_fields = ['id']


class NinoSerializer(serializers.ModelSerializer):
    edad_en_meses      = serializers.IntegerField(read_only=True)
    nombre_completo    = serializers.CharField(read_only=True)
    genero_display     = serializers.CharField(source='get_genero_display', read_only=True)
    tutores            = NinoTutorSerializer(many=True, read_only=True)
    autorizados        = PersonaAutorizadaSerializer(many=True, read_only=True)
    documentos         = DocumentoSerializer(many=True, read_only=True)

    class Meta:
        model  = Nino
        fields = [
            'id', 'nombres', 'apellidos', 'nombre_completo',
            'fecha_nacimiento', 'edad_en_meses',
            'genero', 'genero_display', 'foto',
            'alergias', 'condiciones_medicas', 'medicacion_habitual',
            'tiene_plan_misael', 'observaciones', 'activo',
            'tutores', 'autorizados', 'documentos',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NinoResumenSerializer(serializers.ModelSerializer):
    """Versión compacta para listas."""
    edad_en_meses   = serializers.IntegerField(read_only=True)
    nombre_completo = serializers.CharField(read_only=True)

    class Meta:
        model  = Nino
        fields = [
            'id', 'nombre_completo', 'fecha_nacimiento',
            'edad_en_meses', 'foto', 'tiene_plan_misael', 'activo',
        ]
