"""
core/serializers.py
Serializers para Sucursal, Sala y Turno.
"""
from rest_framework import serializers
from .models import Sucursal, Sala, Turno


class TurnoSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)

    class Meta:
        model  = Turno
        fields = [
            'id', 'sala', 'nombre', 'tipo', 'tipo_display',
            'hora_inicio', 'hora_fin',
            'costo_mensual', 'costo_diario',
            'descripcion', 'activo',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        if data.get('hora_inicio') and data.get('hora_fin'):
            if data['hora_inicio'] >= data['hora_fin']:
                raise serializers.ValidationError(
                    'La hora de inicio debe ser anterior a la hora de fin.'
                )
        return data


class SalaSerializer(serializers.ModelSerializer):
    turnos      = TurnoSerializer(many=True, read_only=True)
    rango_edad  = serializers.CharField(read_only=True)
    sucursal_nombre = serializers.CharField(source='sucursal.nombre', read_only=True)

    class Meta:
        model  = Sala
        fields = [
            'id', 'sucursal', 'sucursal_nombre', 'nombre',
            'edad_min_meses', 'edad_max_meses', 'rango_edad',
            'capacidad_maxima', 'descripcion', 'activa',
            'turnos',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        if data.get('edad_min_meses') and data.get('edad_max_meses'):
            if data['edad_min_meses'] >= data['edad_max_meses']:
                raise serializers.ValidationError(
                    'La edad mínima debe ser menor a la edad máxima.'
                )
        return data


class SalaResumenSerializer(serializers.ModelSerializer):
    """Versión compacta de Sala para usar dentro de Sucursal."""
    rango_edad = serializers.CharField(read_only=True)

    class Meta:
        model  = Sala
        fields = ['id', 'nombre', 'rango_edad', 'capacidad_maxima', 'activa']


class SucursalSerializer(serializers.ModelSerializer):
    salas           = SalaResumenSerializer(many=True, read_only=True)
    directora_nombre = serializers.CharField(
        source='directora.nombre_completo', read_only=True
    )

    class Meta:
        model  = Sucursal
        fields = [
            'id', 'nombre', 'direccion', 'telefono', 'ciudad',
            'descripcion', 'directora', 'directora_nombre',
            'activa', 'salas',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SucursalResumenSerializer(serializers.ModelSerializer):
    """Versión compacta para listas y selects."""
    class Meta:
        model  = Sucursal
        fields = ['id', 'nombre', 'ciudad', 'activa']
