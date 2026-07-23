"""
accounts/permissions.py
Permisos reutilizables basados en rol, usados en varios módulos.

El README documenta reglas como "solo admin/directora pueden crear
sucursales" o "cobros: admin/directora/administrativo", pero antes de este
fix ningún ViewSet las aplicaba: solo se exigía IsAuthenticated, así que
CUALQUIER usuario logueado (p.ej. una educadora o cocina) podía crear
usuarios con rol admin, sucursales, cobros, etc. via la API.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class EsAdminODirectora(BasePermission):
    """Lectura para cualquier autenticado; escritura solo admin/directora."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.rol in ('admin', 'directora')


class EsAdminDirectoraOAdministrativo(BasePermission):
    """Lectura para cualquier autenticado; escritura admin/directora/administrativo."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.rol in ('admin', 'directora', 'administrativo')


class SoloAdmin(BasePermission):
    """Solo el rol admin puede usar la vista (lectura y escritura)."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.rol == 'admin')


def puede_gestionar_usuarios(usuario, rol_objetivo=None):
    """
    Reglas de negocio para crear/editar usuarios del sistema:
    - admin: puede gestionar cualquier rol.
    - directora: puede gestionar todo excepto crear otros 'admin'.
    - el resto de roles no puede crear ni editar usuarios de otras personas.
    """
    if not usuario or not usuario.is_authenticated:
        return False
    if usuario.rol == 'admin':
        return True
    if usuario.rol == 'directora':
        return rol_objetivo != 'admin'
    return False
