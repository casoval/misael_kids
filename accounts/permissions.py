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


class NoEsTutor(BasePermission):
    """
    Lectura para cualquier autenticado; escritura (crear/editar/eliminar)
    solo para personal del centro, nunca para el rol 'tutor'.

    Sin este permiso, cualquier padre/madre con su propia cuenta podía
    publicar, editar o borrar un "Aviso" oficial dirigido a toda una sala
    o sucursal (el endpoint solo exigía estar autenticado).
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.rol != 'tutor'


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


def filtrar_por_tutor(queryset, usuario, ruta_a_nino='nino'):
    """
    Restringe un queryset para que, si el usuario autenticado es un tutor
    (padre/madre), solo vea los registros de SUS PROPIOS hijos — igual que
    ya hace NinoViewSet.get_queryset(). El resto de roles (staff) ve todo
    sin restricción, tal como antes.

    `ruta_a_nino` es la ruta de lookup de Django ORM hasta llegar al campo
    `nino` desde el modelo de este queryset. Ejemplos:
      - 'nino'                      → el modelo tiene un FK directo a Nino
      - 'inscripcion__nino'         → hay que pasar por Inscripcion primero
      - 'plan__nino'                → hay que pasar por PlanIndividual primero
      - 'objetivo__plan__nino'      → dos niveles de indirección

    Sin este filtro, cualquier cuenta de tutor podía consultar datos de
    CUALQUIER niño (salud, evaluaciones, derivaciones a Centro Misael,
    documentos, personas autorizadas, asistencia) con solo cambiar el
    parámetro `nino` en la URL de la API — no había ninguna verificación
    de que ese niño realmente fuera su hijo.
    """
    if not usuario or not usuario.is_authenticated:
        return queryset.none()
    if usuario.rol == 'tutor':
        filtro = {f'{ruta_a_nino}__tutores__tutor__usuario': usuario}
        queryset = queryset.filter(**filtro)
    return queryset
