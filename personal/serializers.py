"""
personal/serializers.py
"""
from django.db import transaction
from rest_framework import serializers
from .models import Personal, AsignacionPersonal, AsistenciaPersonal


class PersonalSerializer(serializers.ModelSerializer):
    nombre_completo  = serializers.CharField(source='usuario.nombre_completo', read_only=True)
    email            = serializers.CharField(source='usuario.email', read_only=True)
    usuario_nombres  = serializers.CharField(source='usuario.nombres', read_only=True)
    usuario_apellidos= serializers.CharField(source='usuario.apellidos', read_only=True)
    usuario_username = serializers.CharField(source='usuario.username', read_only=True)
    rol_display      = serializers.CharField(source='get_rol_display', read_only=True)

    # Solo de escritura: permiten crear el usuario junto con la ficha, en UNA
    # sola operación (si algo falla no queda un usuario huérfano), o editar
    # los datos personales que viven en el usuario.
    nombres   = serializers.CharField(write_only=True, required=False, max_length=100)
    apellidos = serializers.CharField(write_only=True, required=False, max_length=100)
    username  = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=50)
    password  = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model  = Personal
        fields = [
            'id', 'usuario', 'nombre_completo', 'email',
            'usuario_nombres', 'usuario_apellidos', 'usuario_username',
            'nombres', 'apellidos', 'username', 'password',
            'ci', 'telefono', 'rol', 'rol_display', 'foto',
            'especialidad', 'fecha_ingreso', 'activo',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        # `usuario` es opcional al crear: si no viene, se crea uno nuevo con
        # username/password; si viene, se VINCULA ese usuario existente.
        extra_kwargs = {'usuario': {'required': False}}

    def validate(self, data):
        if self.instance is not None:
            if 'usuario' in data and data['usuario'] != self.instance.usuario:
                raise serializers.ValidationError(
                    {'usuario': 'No se puede cambiar el usuario de una ficha existente.'})
            return data

        usuario = data.get('usuario')
        if usuario is not None:
            if usuario.rol in ('tutor', 'profesional'):
                raise serializers.ValidationError(
                    {'usuario': 'Ese usuario es un tutor/profesional, no personal del centro.'})
        else:
            faltan = [c for c in ('nombres', 'apellidos', 'username', 'password') if not data.get(c)]
            if faltan:
                raise serializers.ValidationError(
                    {c: 'Obligatorio para crear el acceso al sistema.' for c in faltan})
        return data

    def create(self, validated_data):
        nombres   = validated_data.pop('nombres', None)
        apellidos = validated_data.pop('apellidos', None)
        username  = validated_data.pop('username', None)
        password  = validated_data.pop('password', None)
        with transaction.atomic():
            if validated_data.get('usuario') is None:
                from accounts.serializers import UsuarioCreateSerializer
                ser = UsuarioCreateSerializer(data={
                    'nombres': nombres, 'apellidos': apellidos,
                    'telefono': validated_data.get('telefono', ''),
                    'rol': validated_data['rol'], 'username': username,
                    'password': password, 'password2': password,
                })
                ser.is_valid(raise_exception=True)
                validated_data['usuario'] = ser.save()
            # Personal.save() alinea el rol del usuario con el de la ficha.
            return super().create(validated_data)

    def update(self, instance, validated_data):
        nombres   = validated_data.pop('nombres', None)
        apellidos = validated_data.pop('apellidos', None)
        validated_data.pop('username', None)   # el acceso se gestiona en Usuarios
        validated_data.pop('password', None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            u, campos = instance.usuario, []
            if nombres is not None:
                u.nombres = nombres; campos.append('nombres')
            if apellidos is not None:
                u.apellidos = apellidos; campos.append('apellidos')
            if 'telefono' in validated_data:
                u.telefono = validated_data['telefono']; campos.append('telefono')
            if campos:
                u.save(update_fields=campos)
        return instance


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
