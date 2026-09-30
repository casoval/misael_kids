"""
accounts/permissions.py
Permisos reutilizables basados en rol, usados en varios módulos.

El README documenta reglas como "solo admin/directora pueden crear
sucursales" o "cobros: admin/directora/recepcionista", pero antes de este
fix ningún ViewSet las aplicaba: solo se exigía IsAuthenticated, así que
CUALQUIER usuario logueado (p.ej. una educadora o cocina) podía crear
usuarios con rol admin, sucursales, cobros, etc. via la API.
"""
from datetime import date

from django.db.models import Q
from rest_framework.permissions import BasePermission, SAFE_METHODS

# Personal que trabaja dentro de una sala: solo ve y toca lo de SUS salas.
ROLES_DE_SALA = ('educadora', 'ayudante')
# Personal de oficina: gestiona fichas, inscripciones, cobros y comunicación.
ROLES_OFICINA = ('admin', 'directora', 'recepcionista')


class EsAdminODirectora(BasePermission):
    """Lectura para cualquier autenticado; escritura solo admin/directora."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.rol in ('admin', 'directora')


class EsAdminDirectoraORecepcionista(BasePermission):
    """Lectura para cualquier autenticado; escritura admin/directora/recepcionista."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.rol in ('admin', 'directora', 'recepcionista')


class SoloAdminDirectoraORecepcionista(BasePermission):
    """
    Lectura Y escritura solo para admin/directora/recepcionista.
    A diferencia de EsAdminDirectoraORecepcionista (que deja LEER a cualquier
    autenticado, porque el tutor ve lo suyo), esta sirve para datos que no
    pueden verlos ni tutores ni educadoras, como los reportes: incluyen el
    listado de todos los niños con alergias y teléfonos de tutores, y las
    finanzas del centro.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.rol in ('admin', 'directora', 'recepcionista'))


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


# ─────────────────────────────────────────────────────────────────────────
#  Alcance por sala (educadora / ayudante)
# ─────────────────────────────────────────────────────────────────────────
def salas_asignadas(usuario, fecha=None):
    """
    IDs de las salas donde el usuario tiene una asignación VIGENTE: la
    asignación está activa, su ficha de personal está activa, ya empezó y
    no terminó (fecha_fin nula o futura). Una educadora que salió de una
    sala pierde el acceso en cuanto se cierra o desactiva su asignación.
    """
    from personal.models import AsignacionPersonal
    fecha = fecha or date.today()
    return set(
        AsignacionPersonal.objects.filter(
            personal__usuario=usuario, personal__activo=True,
            activa=True, fecha_inicio__lte=fecha,
        ).filter(
            Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha)
        ).values_list('sala_id', flat=True)
    )


def nino_en_mis_salas(usuario, nino_id):
    """True si el niño tiene inscripción activa en una sala del usuario."""
    from inscripciones.models import Inscripcion
    return Inscripcion.objects.filter(
        nino_id=nino_id, activa=True, sala_id__in=salas_asignadas(usuario)
    ).exists()


def filtrar_por_alcance(queryset, usuario, ruta_a_nino='nino'):
    """
    Restringe un queryset según quién pregunta:
      - tutor:               solo los registros de SUS hijos.
      - educadora/ayudante:  solo los registros de niños con inscripción
                             ACTIVA en una sala donde tienen asignación vigente.
      - resto (admin, directora, recepcionista, cocina...): sin restricción.

    `ruta_a_nino` es la ruta ORM hasta el niño ('' si el modelo ES Nino,
    'nino', 'inscripcion__nino', 'plan__nino', 'ninos__nino' para Tutor...).
    Reemplaza a `filtrar_por_tutor`, que solo conocía al tutor.
    """
    if not usuario or not usuario.is_authenticated:
        return queryset.none()
    prefijo = f'{ruta_a_nino}__' if ruta_a_nino else ''
    if usuario.rol == 'tutor':
        return queryset.filter(**{f'{prefijo}tutores__tutor__usuario': usuario})
    if usuario.rol in ROLES_DE_SALA:
        return queryset.filter(**{
            f'{prefijo}inscripciones__sala__in': list(salas_asignadas(usuario)),
            f'{prefijo}inscripciones__activa': True,
        }).distinct()
    return queryset


class PermisoFichaNino(BasePermission):
    """
    Ficha del niño. Lectura: cualquier autenticado (el alcance lo pone
    `filtrar_por_alcance`). Crear/eliminar: solo oficina (recepcionista,
    directora, admin). Editar: oficina y educadora (dentro de sus salas).
    La ayudante, cocina y demás roles solo leen. El tutor queda como estaba.
    """
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        if u.rol in ROLES_OFICINA or u.rol == 'tutor':
            return True
        if u.rol == 'educadora':
            return request.method in ('PUT', 'PATCH')
        return False


class PermisoDatosFamiliares(BasePermission):
    """
    Tutores, vínculos niño-tutor, personas autorizadas a retirar y documentos.
    Lectura: cualquier autenticado (con su alcance). Escritura: solo oficina
    (quién puede retirar a un niño no lo cambia una educadora). El tutor queda
    como estaba.
    """
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return u.rol in ROLES_OFICINA or u.rol == 'tutor'


class PermisoFinanzas(BasePermission):
    """
    Inscripciones (llevan montos) y cobros. Lectura: oficina y tutor (que ve
    lo suyo). Educadora, ayudante, cocina y demás NO ven dinero. Escritura:
    solo oficina.
    """
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return u.rol in ROLES_OFICINA or u.rol == 'tutor'
        return u.rol in ROLES_OFICINA


class PermisoDesarrollo(BasePermission):
    """
    Evaluación del desarrollo (evaluaciones de hitos por niño).
    Lectura: admin, directora, educadora, ayudante, cocina (tal como muestra el
    menú) y tutor (su hijo, por `filtrar_por_alcance`). NO la recepcionista ni
    el profesional: el README indica que no ven la parte de desarrollo.
    Escritura: solo quien evalúa — admin, directora, educadora y ayudante (estas
    dos, dentro de sus salas, lo controla `exigir_nino_en_alcance`). Antes
    cualquier usuario autenticado, incluido un tutor, podía crear, editar o
    borrar evaluaciones de cualquier niño.
    """
    ROLES_LECTURA   = ('admin', 'directora', 'educadora', 'ayudante', 'cocina', 'tutor')
    ROLES_ESCRITURA = ('admin', 'directora', 'educadora', 'ayudante')

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return u.rol in self.ROLES_LECTURA
        return u.rol in self.ROLES_ESCRITURA


class PermisoCatalogoHitos(BasePermission):
    """
    Catálogo de hitos. Lectura: los mismos roles que ven el desarrollo.
    Escritura (agregar, editar, desactivar hitos): solo admin y directora.
    """
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return u.rol in PermisoDesarrollo.ROLES_LECTURA
        return u.rol in ('admin', 'directora')


def exigir_nino_en_alcance(usuario, nino):
    """
    Para escrituras (POST/PUT/PATCH): educadora/ayudante solo pueden registrar
    cosas de niños de SUS salas. El filtro del queryset solo protege lecturas.
    `nino` puede ser instancia o id.
    """
    from rest_framework.exceptions import PermissionDenied
    if usuario.rol in ROLES_DE_SALA and not nino_en_mis_salas(usuario, getattr(nino, 'pk', nino)):
        raise PermissionDenied('Este niño no pertenece a tus salas asignadas.')


def exigir_sala_en_alcance(usuario, sala):
    """Igual que `exigir_nino_en_alcance`, pero para registros de una sala."""
    from rest_framework.exceptions import PermissionDenied
    if usuario.rol in ROLES_DE_SALA and getattr(sala, 'pk', sala) not in salas_asignadas(usuario):
        raise PermissionDenied('Esta sala no está entre tus asignaciones.')
