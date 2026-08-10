"""
misael_link/authentication.py

Autenticación por API key para consumo servicio-a-servicio, en el
sentido ENTRANTE: Centro Misael (repo centro_terapias_v2) consultando
esta API para saber si un paciente ya está vinculado, o para leer sus
planes de trabajo.

Espeja MisaelKidsAPIKeyAuthentication del otro repo. Usa la misma
clave compartida (settings.CENTRO_MISAEL_API_KEY == MISAEL_KIDS_API_KEY
del lado de Centro Misael), ya que es un secreto simétrico entre los
dos únicos servicios que se hablan.
"""
import hmac

from django.conf import settings
from rest_framework import authentication, exceptions


class CentroMisaelAPIKeyAuthentication(authentication.BaseAuthentication):
    """
    Espera el header:  Authorization: ApiKey <clave>
    """

    keyword = 'ApiKey'

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode('utf-8')
        if not auth_header or not auth_header.startswith(self.keyword + ' '):
            return None

        clave_recibida = auth_header[len(self.keyword) + 1:].strip()
        clave_esperada = getattr(settings, 'CENTRO_MISAEL_API_KEY', '')

        if not clave_esperada:
            raise exceptions.AuthenticationFailed(
                'CENTRO_MISAEL_API_KEY no está configurada en el servidor.'
            )

        if not clave_recibida or not hmac.compare_digest(clave_recibida, clave_esperada):
            raise exceptions.AuthenticationFailed('API key inválida.')

        return (_UsuarioServicioCentroMisael(), None)

    def authenticate_header(self, request):
        return self.keyword


class _UsuarioServicioCentroMisael:
    """Usuario "falso" mínimo para que IsAuthenticated pase y quede claro en logs quién llamó."""
    is_authenticated = True
    is_active = True
    is_staff = False
    is_superuser = False
    pk = None
    id = None

    def __str__(self):
        return 'servicio:centro_misael'
