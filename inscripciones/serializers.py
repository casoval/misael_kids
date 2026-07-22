"""
inscripciones/serializers.py
"""
from rest_framework import serializers
from .models import Inscripcion, Cobro


class CobroSerializer(serializers.ModelSerializer):
    tipo_display   = serializers.CharField(source='get_tipo_display', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)
    nino_nombre    = serializers.CharField(
        source='inscripcion.nino.nombre_completo', read_only=True
    )

    class Meta:
        model  = Cobro
        fields = [
            'id', 'inscripcion', 'nino_nombre',
            'tipo', 'tipo_display', 'periodo',
            'monto_base', 'monto_final',
            'fecha_emision', 'fecha_vencimiento',
            'estado', 'estado_display',
            'fecha_pago', 'metodo_pago', 'comprobante',
            'registrado_por', 'observacion',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'fecha_emision', 'created_at', 'updated_at']


class InscripcionSerializer(serializers.ModelSerializer):
    nino_nombre       = serializers.CharField(source='nino.nombre_completo', read_only=True)
    sucursal_nombre   = serializers.CharField(source='sucursal.nombre', read_only=True)
    sala_nombre       = serializers.CharField(source='sala.nombre', read_only=True)
    turno_nombre      = serializers.CharField(source='turno.nombre', read_only=True)
    tipo_ajuste_display   = serializers.CharField(source='get_tipo_ajuste_display', read_only=True)
    modalidad_display     = serializers.CharField(source='get_modalidad_pago_display', read_only=True)
    costo_mensual_final   = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    costo_diario_final    = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    cobros                = CobroSerializer(many=True, read_only=True)

    class Meta:
        model  = Inscripcion
        fields = [
            'id', 'nino', 'nino_nombre',
            'sucursal', 'sucursal_nombre',
            'sala', 'sala_nombre',
            'turno', 'turno_nombre',
            'modalidad_pago', 'modalidad_display',
            'fecha_inicio', 'fecha_fin',
            'costo_mensual', 'costo_diario',
            'tipo_ajuste', 'tipo_ajuste_display',
            'porcentaje_ajuste', 'monto_ajuste', 'motivo_ajuste',
            'costo_mensual_final', 'costo_diario_final',
            'activa', 'cobros',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        # Sala debe pertenecer a la sucursal
        sala     = data.get('sala')
        sucursal = data.get('sucursal')
        turno    = data.get('turno')
        if sala and sucursal and sala.sucursal != sucursal:
            raise serializers.ValidationError(
                {'sala': 'La sala no pertenece a la sucursal seleccionada.'}
            )
        if turno and sala and turno.sala != sala:
            raise serializers.ValidationError(
                {'turno': 'El turno no pertenece a la sala seleccionada.'}
            )
        # Verificar capacidad disponible en sala+turno
        if sala and turno:
            inscritos = Inscripcion.objects.filter(
                sala=sala, turno=turno, activa=True
            ).exclude(id=self.instance.id if self.instance else None).count()
            if inscritos >= sala.capacidad_maxima:
                raise serializers.ValidationError(
                    {'sala': f'La sala {sala.nombre} ya alcanzó su capacidad máxima ({sala.capacidad_maxima} niños).'}
                )
        return data

    def create(self, validated_data):
        # Si no se especifican costos, copiarlos del turno
        turno = validated_data.get('turno')
        if turno:
            if 'costo_mensual' not in validated_data or not validated_data.get('costo_mensual'):
                validated_data['costo_mensual'] = turno.costo_mensual
            if 'costo_diario' not in validated_data or not validated_data.get('costo_diario'):
                validated_data['costo_diario'] = turno.costo_diario
        return super().create(validated_data)


class InscripcionResumenSerializer(serializers.ModelSerializer):
    """Versión compacta para listas."""
    nino_nombre         = serializers.CharField(source='nino.nombre_completo', read_only=True)
    sala_nombre         = serializers.CharField(source='sala.nombre', read_only=True)
    turno_nombre        = serializers.CharField(source='turno.nombre', read_only=True)
    costo_mensual_final = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model  = Inscripcion
        fields = [
            'id', 'nino', 'nino_nombre',
            'sala_nombre', 'turno_nombre',
            'modalidad_pago', 'tipo_ajuste',
            'costo_mensual_final', 'activa', 'fecha_inicio',
        ]
