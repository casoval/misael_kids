"""
personal/serializers.py
"""
from rest_framework import serializers
from .models import Personal, AsignacionPersonal, AsistenciaPersonal


class PersonalSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.CharField(source='usuario.nombre_completo', read_only=True)
    email           = serializers.CharField(source='usuario.email', read_only=True)
    rol_display     = serializers.CharField(source='get_rol_display', read_only=True)

    class Meta:
        model  = Personal
        fields = [
            'id', 'usuario', 'nombre_completo', 'email',
            'ci', 'telefono', 'rol', 'rol_display',
            'especialidad', 'fecha_ingreso', 'activo',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AsignacionPersonalSerializer(serializers.ModelSerializer):
    personal_nombre = serializers.CharField(source='personal.usuario.nombre_completo', read_only=True)
    sucursal_nombre = serializers.CharField(source='sucursal.nombre', read_only=True)
    sala_nombre     = serializers.CharField(source='sala.nombre', read_only=True)
    turno_nombre    = serializers.CharField(source='turno.nombre', read_only=True)

    class Meta:
        model  = AsignacionPersonal
        fields = [
            'id', 'personal', 'personal_nombre',
            'sucursal', 'sucursal_nombre',
            'sala', 'sala_nombre',
            'turno', 'turno_nombre',
            'fecha_inicio', 'fecha_fin',
            'es_titular', 'activa',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        # Sala debe pertenecer a la sucursal
        if data.get('sala') and data.get('sucursal'):
            if data['sala'].sucursal != data['sucursal']:
                raise serializers.ValidationError(
                    'La sala no pertenece a la sucursal seleccionada.'
                )
        # Turno debe pertenecer a la sala
        if data.get('turno') and data.get('sala'):
            if data['turno'].sala != data['sala']:
                raise serializers.ValidationError(
                    'El turno no pertenece a la sala seleccionada.'
                )
        return data


class AsistenciaPersonalSerializer(serializers.ModelSerializer):
    personal_nombre = serializers.CharField(source='personal.usuario.nombre_completo', read_only=True)
    sucursal_nombre = serializers.CharField(source='sucursal.nombre', read_only=True)
    estado_display  = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model  = AsistenciaPersonal
        fields = [
            'id', 'personal', 'personal_nombre',
            'sucursal', 'sucursal_nombre',
            'fecha', 'hora_entrada', 'hora_salida',
            'estado', 'estado_display', 'observacion',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
