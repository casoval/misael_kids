from rest_framework import serializers
from .models import Asistencia


class AsistenciaSerializer(serializers.ModelSerializer):
    nino_nombre    = serializers.CharField(source='inscripcion.nino.nombre_completo', read_only=True)
    sala_nombre    = serializers.CharField(source='inscripcion.sala.nombre', read_only=True)
    turno_nombre   = serializers.CharField(source='inscripcion.turno.nombre', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model  = Asistencia
        fields = [
            'id', 'inscripcion', 'nino_nombre', 'sala_nombre', 'turno_nombre',
            'fecha', 'estado', 'estado_display',
            'hora_entrada', 'hora_salida',
            'entregado_por', 'retirado_por', 'retiro_autorizado',
            'obs_entrada', 'obs_salida', 'motivo_ausencia',
            'registrado_por', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
