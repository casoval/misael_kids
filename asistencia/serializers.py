from rest_framework import serializers
from .models import Asistencia


class AsistenciaSerializer(serializers.ModelSerializer):
    nino_nombre    = serializers.CharField(source='inscripcion.nino.nombre_completo', read_only=True)
    nino_foto      = serializers.ImageField(source='inscripcion.nino.foto', read_only=True)
    nino_genero    = serializers.CharField(source='inscripcion.nino.genero', read_only=True)
    sala_nombre    = serializers.CharField(source='inscripcion.sala.nombre', read_only=True)
    turno_nombre   = serializers.CharField(source='inscripcion.turno.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model  = Asistencia
        fields = [
            'id', 'inscripcion', 'nino_nombre', 'nino_foto', 'nino_genero', 'sala_nombre', 'turno_nombre',
            'fecha', 'estado', 'estado_display',
            'hora_entrada', 'hora_salida',
            'entregado_por', 'retirado_por', 'retiro_autorizado',
            'obs_entrada', 'obs_salida', 'motivo_ausencia',
            'registrado_por', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        # En un PATCH parcial, el campo que no viene en `attrs` hay que
        # tomarlo de la instancia ya guardada (si existe), si no un cambio
        # de una sola hora podría comparase contra None y nunca detectar
        # una salida antes que la entrada ya guardada.
        hora_entrada = attrs.get('hora_entrada', getattr(self.instance, 'hora_entrada', None))
        hora_salida  = attrs.get('hora_salida',  getattr(self.instance, 'hora_salida', None))
        if hora_entrada and hora_salida and hora_salida <= hora_entrada:
            raise serializers.ValidationError({
                'hora_salida': 'La hora de salida debe ser posterior a la hora de entrada.'
            })
        return attrs
