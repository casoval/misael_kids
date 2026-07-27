"""
accounts/backends.py

Backend de autenticación que permite iniciar sesión con el email O el
nombre de usuario indistintamente — la misma lógica que ya usa el login
JWT del panel (ver accounts/serializers.py). Se registra en
AUTHENTICATION_BACKENDS para que también funcione en el /admin/ de
Django, que por defecto solo reconoce el USERNAME_FIELD del modelo
(email) y por eso antes exigía un email válido para crear o loguear
superusuarios.
"""
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import Usuario


class EmailOUsernameBackend(ModelBackend):
    """
    Autentica buscando coincidencia exacta (sin distinguir mayúsculas)
    contra `email` o `username`, lo que el usuario haya escrito.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        identificador = username or kwargs.get(Usuario.USERNAME_FIELD)
        if identificador is None or password is None:
            return None
        try:
            usuario = Usuario.objects.get(
                Q(email__iexact=identificador) | Q(username__iexact=identificador)
            )
        except Usuario.DoesNotExist:
            return None
        except Usuario.MultipleObjectsReturned:
            # Caso borde: email de uno coincide con username de otro.
            return None

        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None
