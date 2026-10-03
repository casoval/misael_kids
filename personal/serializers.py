"""
personal/serializers.py
"""
from django.db import transaction
from rest_framework import serializers
from .models import Personal, AsignacionPersonal, AsistenciaPersonal


class PersonalSerializer(serializers.ModelSerializer):
    """
    Ficha del personal. Igual que Tutor, el ACCESO al sistema es opcional:
    se crea la ficha y, si se quiere, se le "da acceso" indicando usuario y
    contraseña (al crear o luego al editar). También se puede vincular un
    usuario que ya existía enviando `usuario`.
    """
    nombre_completo  = serializers.CharField(read_only=True)
    email            = serializers.CharField(source='usuario.email', read_only=True, default=None)
    usuario_username = serializers.CharField(source='usuario.username', read_only=True, default=None)
    tiene_acceso     = serializers.SerializerMethodField()
    rol_display      = serializers.CharField(source='get_rol_display', read_only=True)

    # Solo escritura: "dar acceso" (se crea el Usuario y se vincula, atómicamente).
    username = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=50)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=8)

    class Meta:
        model  = Personal
        fields = [
            'id', 'usuario', 'tiene_acceso', 'nombre_completo', 'nombres', 'apellidos',
            'email', 'usuario_username', 'username', 'password',
            'ci', 'telefono', 'rol', 'rol_display', 'foto',
            'especialidad', 'fecha_ingreso', 'activo',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'usuario':   {'required': False, 'allow_null': True},
            'nombres':   {'required': False},
            'apellidos': {'required': False},
        }

    def get_tiene_acceso(self, obj):
        return obj.usuario_id is not None

    # ── Validación ─────────────────────────────────────────────────────
    def validate(self, data):
        instancia = self.instance
        usuario_actual = instancia.usuario if instancia else None
        usuario = data.get('usuario', usuario_actual)
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''

        if instancia is not None and 'usuario' in data and usuario_actual is not None \
                and data['usuario'] != usuario_actual:
            raise serializers.ValidationError(
                {'usuario': 'Esta ficha ya tiene un usuario; se gestiona desde Usuarios.'})

        if usuario is not None and usuario.rol in ('tutor', 'profesional'):
            raise serializers.ValidationError(
                {'usuario': 'Ese usuario es un tutor/profesional, no personal del centro.'})

        if username or password:
            if usuario is not None:
                raise serializers.ValidationError(
                    {'username': 'Esta persona ya tiene acceso; su usuario y contraseña '
                                 'se gestionan desde Usuarios.'})
            faltan = {c: 'Obligatorio para dar acceso al sistema.'
                      for c, v in (('username', username), ('password', password)) if not v}
            if faltan:
                raise serializers.ValidationError(faltan)

        # Nombres: propios de la ficha; al vincular un usuario se toman de él.
        nombres   = data.get('nombres',   instancia.nombres   if instancia else None)
        apellidos = data.get('apellidos', instancia.apellidos if instancia else None)
        if not nombres and usuario is not None:
            nombres = usuario.nombres
        if not apellidos and usuario is not None:
            apellidos = usuario.apellidos
        errores = {c: 'Este campo es obligatorio.'
                   for c, v in (('nombres', nombres), ('apellidos', apellidos)) if not v}
        if errores:
            raise serializers.ValidationError(errores)
        data['nombres'], data['apellidos'] = nombres, apellidos
        return data

    # ── Dar acceso (crear + vincular el usuario) ───────────────────────
    @staticmethod
    def _crear_usuario(datos, username, password):
        from accounts.serializers import UsuarioCreateSerializer
        ser = UsuarioCreateSerializer(data={
            'nombres': datos['nombres'], 'apellidos': datos['apellidos'],
            'telefono': datos.get('telefono', ''), 'rol': datos['rol'],
            'username': username, 'password': password, 'password2': password,
        })
        ser.is_valid(raise_exception=True)
        return ser.save()

    def create(self, validated_data):
        username = (validated_data.pop('username', '') or '').strip()
        password = validated_data.pop('password', '')
        with transaction.atomic():
            if username and validated_data.get('usuario') is None:
                validated_data['usuario'] = self._crear_usuario(validated_data, username, password)
            # Personal.save() alinea nombre y rol del usuario con los de la ficha.
            return super().create(validated_data)

    def update(self, instance, validated_data):
        username = (validated_data.pop('username', '') or '').strip()
        password = validated_data.pop('password', '')
        with transaction.atomic():
            if username and instance.usuario is None and validated_data.get('usuario') is None:
                datos = {'nombres': validated_data.get('nombres', instance.nombres),
                         'apellidos': validated_data.get('apellidos', instance.apellidos),
                         'telefono': validated_data.get('telefono', instance.telefono),
                         'rol': validated_data.get('rol', instance.rol)}
                validated_data['usuario'] = self._crear_usuario(datos, username, password)
            return super().update(instance, validated_data)


class AsignacionPersonalSerializer(serializers.ModelSerializer):
    personal_nombre = serializers.CharField(source='personal.nombre_completo', read_only=True)
    personal_foto   = serializers.ImageField(source='personal.foto', read_only=True)
    sucursal_nombre = serializers.CharField(source='sucursal.nombre', read_only=True)
    sala_nombre     = serializers.CharField(source='sala.nombre', read_only=True)
    turno_nombre    = serializers.CharField(source='turno.nombre', read_only=True)

    class Meta:
        model  = AsignacionPersonal
        fields = [
            'id', 'personal', 'personal_nombre', 'personal_foto',
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
    personal_nombre = serializers.CharField(source='personal.nombre_completo', read_only=True)
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
