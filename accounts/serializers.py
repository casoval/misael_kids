"""
accounts/serializers.py
Login JWT, registro y perfil de usuario.
"""
from rest_framework import serializers
from django.db import models
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import Usuario


class UsuarioSerializer(serializers.ModelSerializer):
    rol_display = serializers.CharField(source='get_rol_display', read_only=True)
    nombre_completo = serializers.CharField(read_only=True)
    identificador = serializers.CharField(read_only=True)
    # Enlace con la ficha de Personal (como Tutor.usuario, pero hacia el otro lado).
    ficha_personal = serializers.SerializerMethodField()
    requiere_ficha = serializers.SerializerMethodField()

    ROLES_PERSONAL = ('educadora', 'ayudante', 'directora', 'recepcionista', 'cocina')

    def get_ficha_personal(self, obj):
        ficha = getattr(obj, 'perfil_personal', None)
        return str(ficha.id) if ficha else None

    def get_requiere_ficha(self, obj):
        # Rol de personal pero sin ficha: no se le puede asignar a una sala.
        return obj.rol in self.ROLES_PERSONAL and getattr(obj, 'perfil_personal', None) is None

    class Meta:
        model  = Usuario
        fields = [
            'id', 'email', 'username', 'identificador', 'nombres', 'apellidos', 'nombre_completo',
            'telefono', 'rol', 'rol_display', 'foto', 'activo', 'tema',
            'ficha_personal', 'requiere_ficha',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tema', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        # Validar unicidad de email y username excluyendo el usuario actual
        email    = validated_data.get('email')
        username = validated_data.get('username')
        if email and Usuario.objects.filter(email__iexact=email).exclude(pk=instance.pk).exists():
            raise serializers.ValidationError({'email': 'Ese email ya está registrado por otro usuario.'})
        if username and Usuario.objects.filter(username__iexact=username).exclude(pk=instance.pk).exists():
            raise serializers.ValidationError({'username': 'Ese nombre de usuario ya está en uso.'})

        # Si ya tiene ficha de personal, su rol debe seguir siendo de personal
        # y la ficha se alinea (evita usuario 'educadora' con ficha 'ayudante').
        nuevo_rol = validated_data.get('rol')
        ficha = getattr(instance, 'perfil_personal', None)
        if nuevo_rol and ficha and nuevo_rol != instance.rol:
            if nuevo_rol not in self.ROLES_PERSONAL:
                raise serializers.ValidationError({'rol': 'Este usuario tiene ficha de personal; '
                    'elimina la ficha antes de cambiarlo a un rol que no es de personal.'})
            ficha.rol = nuevo_rol
            ficha.save()

        instance = super().update(instance, validated_data)
        # Nombre/teléfono editados aquí también se reflejan en la ficha de personal.
        if ficha and any(k in validated_data for k in ('nombres', 'apellidos', 'telefono')):
            ficha.nombres, ficha.apellidos = instance.nombres, instance.apellidos
            if instance.telefono:
                ficha.telefono = instance.telefono
            ficha.save()
        # Igual para tutores: el teléfono editado aquí llega a la tarjeta del niño.
        tutor = getattr(instance, 'perfil_tutor', None)
        if tutor and any(k in validated_data for k in ('nombres', 'apellidos', 'telefono')):
            tutor.nombres, tutor.apellidos = instance.nombres, instance.apellidos
            if instance.telefono:
                tutor.telefono = instance.telefono
            tutor.save()
        if 'activo' in validated_data:
            instance.is_active = validated_data['activo']
            instance.save(update_fields=['is_active'])
        return instance


class UsuarioCreateSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, label='Confirmar contraseña')
    email     = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    username  = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=50)

    class Meta:
        model  = Usuario
        fields = [
            'id', 'email', 'username', 'nombres', 'apellidos', 'telefono',
            'rol', 'password', 'password2',
        ]
        read_only_fields = ['id']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password2': 'Las contraseñas no coinciden.'})

        email    = (data.get('email') or '').strip()
        username = (data.get('username') or '').strip()

        if not email and not username:
            raise serializers.ValidationError(
                {'username': 'Debes indicar un nombre de usuario.'})

        if username and Usuario.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError(
                {'username': 'Ese nombre de usuario ya está en uso.'})

        if email and Usuario.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({'email': 'Ese email ya está registrado.'})

        data['email']    = email or None
        data['username'] = username or None
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = Usuario(**validated_data)
        user.set_password(password)
        user.save()
        return user


class TemaSerializer(serializers.Serializer):
    """Tema visual propio. Se valida el formato, no la lista: los temas
    nuevos viven en el frontend (js/tema.js) y no deben exigir tocar esto."""
    tema = serializers.RegexField(r'^[a-z0-9_-]{1,30}$', allow_blank=True)


class CambiarPasswordSerializer(serializers.Serializer):
    password_actual = serializers.CharField(write_only=True)
    password_nuevo  = serializers.CharField(write_only=True, min_length=8)
    password_nuevo2 = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['password_nuevo'] != data['password_nuevo2']:
            raise serializers.ValidationError({'password_nuevo2': 'Las contraseñas no coinciden.'})
        return data


class MiTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT personalizado: acepta login por email o por nombre de usuario,
    e incluye los datos del usuario en la respuesta."""

    def validate(self, attrs):
        identificador = attrs.get(self.username_field, '').strip()
        password = attrs.get('password', '')

        usuario = Usuario.objects.filter(
            models.Q(email__iexact=identificador) | models.Q(username__iexact=identificador)
        ).first()

        if usuario is None or not usuario.check_password(password):
            raise serializers.ValidationError(
                {'detail': 'Credenciales incorrectas. Verifica tu email/usuario y contraseña.'}
            )
        if not usuario.activo or not usuario.is_active:
            raise serializers.ValidationError(
                {'detail': 'Esta cuenta está desactivada. Contacta a la administración.'}
            )

        refresh = self.get_token(usuario)
        return {
            'refresh': str(refresh),
            'access':  str(refresh.access_token),
            'usuario': UsuarioSerializer(usuario).data,
        }