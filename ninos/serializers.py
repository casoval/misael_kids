"""
ninos/serializers.py
"""
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from .models import Nino, Tutor, NinoTutor, PersonaAutorizada, Documento


class TutorSerializer(serializers.ModelSerializer):
    parentesco_display = serializers.CharField(source='get_parentesco_display', read_only=True)
    ninos_resumen       = serializers.SerializerMethodField()

    class Meta:
        model  = Tutor
        fields = [
            'id', 'usuario', 'nombres', 'apellidos', 'ci',
            'telefono', 'telefono_alt', 'email',
            'parentesco', 'parentesco_display', 'activo',
            'ninos_resumen',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_ninos_resumen(self, obj):
        return [
            {
                'nino_id': nt.nino_id,
                'nombre': nt.nino.nombre_completo,
                'es_principal': nt.es_principal,
                'puede_retirar': nt.puede_retirar,
            }
            for nt in obj.ninos.all()
        ]


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


def _vinculo_misael(nino):
    """VinculoCentroMisael del niño o None (sin consulta extra si la vista hizo select_related)."""
    try:
        return nino.vinculo_centro_misael
    except ObjectDoesNotExist:
        return None


class NinoSerializer(serializers.ModelSerializer):
    edad_en_meses      = serializers.IntegerField(read_only=True)
    nombre_completo    = serializers.CharField(read_only=True)
    genero_display     = serializers.CharField(source='get_genero_display', read_only=True)
    tutores            = NinoTutorSerializer(many=True, read_only=True)
    autorizados        = PersonaAutorizadaSerializer(many=True, read_only=True)
    documentos         = DocumentoSerializer(many=True, read_only=True)
    # Vínculo REAL con Centro Misael (VinculoCentroMisael). `tiene_plan_misael` es solo
    # una casilla manual y puede no coincidir; el distintivo de la pantalla usa esto.
    vinculado_centro_misael = serializers.SerializerMethodField()
    centro_misael           = serializers.SerializerMethodField()

    def get_vinculado_centro_misael(self, obj):
        return _vinculo_misael(obj) is not None

    def get_centro_misael(self, obj):
        v = _vinculo_misael(obj)
        if v is None:
            return None
        return {'paciente_centro_id': v.paciente_centro_id, 'nombre_paciente': v.nombre_paciente_centro,
                'estado_centro': v.estado_centro_cache, 'fecha_vinculacion': v.fecha_vinculacion}

    class Meta:
        model  = Nino
        fields = [
            'id', 'nombres', 'apellidos', 'nombre_completo',
            'fecha_nacimiento', 'edad_en_meses',
            'genero', 'genero_display', 'foto',
            'alergias', 'condiciones_medicas', 'medicacion_habitual',
            'tiene_plan_misael', 'vinculado_centro_misael', 'centro_misael', 'observaciones', 'activo',
            'tutores', 'autorizados', 'documentos',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class NinoResumenSerializer(serializers.ModelSerializer):
    """Versión compacta para listas — pero con los datos que el listado
    realmente necesita mostrar (antes le faltaban 'genero' y 'alergias',
    por lo que la tabla de niños mostraba género y alergias incorrectos
    para TODOS los registros, ya que esos campos llegaban undefined)."""
    edad_en_meses   = serializers.IntegerField(read_only=True)
    nombre_completo = serializers.CharField(read_only=True)
    genero_display  = serializers.CharField(source='get_genero_display', read_only=True)
    tutores_resumen = serializers.SerializerMethodField()
    vinculado_centro_misael = serializers.SerializerMethodField()

    def get_vinculado_centro_misael(self, obj):
        return _vinculo_misael(obj) is not None

    class Meta:
        model  = Nino
        fields = [
            'id', 'nombre_completo', 'fecha_nacimiento',
            'edad_en_meses', 'genero', 'genero_display', 'foto',
            'alergias', 'tiene_plan_misael', 'vinculado_centro_misael', 'activo', 'tutores_resumen',
        ]

    def get_tutores_resumen(self, obj):
        return [
            {
                'tutor_id': nt.tutor_id,
                'nombre': str(nt.tutor),
                'es_principal': nt.es_principal,
            }
            for nt in obj.tutores.all()
        ]
