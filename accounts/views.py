"""
accounts/views.py
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Usuario
from .permissions import puede_gestionar_usuarios
from .serializers import (
    UsuarioSerializer, UsuarioCreateSerializer,
    CambiarPasswordSerializer, MiTokenObtainPairSerializer, TemaSerializer,
)


class MiTokenObtainPairView(TokenObtainPairView):
    """Login JWT con datos del usuario incluidos.

    Limitado por IP (scope 'login', ver REST_FRAMEWORK en settings) para
    frenar la fuerza bruta de contraseñas.
    """
    serializer_class = MiTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'


class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all().order_by('apellidos', 'nombres')
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields   = ['email', 'nombres', 'apellidos']

    def get_serializer_class(self):
        if self.action == 'create':
            return UsuarioCreateSerializer
        return UsuarioSerializer

    def create(self, request, *args, **kwargs):
        """
        Solo admin/directora pueden crear usuarios del sistema, y una
        directora no puede crear otro 'admin'. Antes de este fix, cualquier
        usuario autenticado (p.ej. una educadora) podía crear una cuenta
        con rol 'admin' llamando directamente a este endpoint.
        """
        rol_solicitado = request.data.get('rol')
        if not puede_gestionar_usuarios(request.user, rol_solicitado):
            return Response(
                {'detail': 'No tienes permiso para crear usuarios con ese rol.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instancia = self.get_object()
        # Cualquier usuario puede editar su propio perfil (nombres, teléfono, foto...)
        if instancia.id == request.user.id:
            # `request.data` es un QueryDict INMUTABLE con multipart (subida de
            # foto): hacer .pop() directamente lanzaba AttributeError (HTTP 500).
            # Se arma un dict nuevo SIN los campos que nadie puede cambiarse a sí
            # mismo: el rol (auto-ascenso) y `activo`. (No se usa QueryDict.copy()
            # porque hace deepcopy y falla con archivos grandes en disco temporal.)
            datos = {k: v for k, v in request.data.items() if k not in ('rol', 'activo')}
            serializer = self.get_serializer(
                instancia, data=datos, partial=kwargs.get('partial', False))
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data)
        rol_solicitado = request.data.get('rol', instancia.rol)
        if not puede_gestionar_usuarios(request.user, rol_solicitado):
            return Response(
                {'detail': 'No tienes permiso para editar este usuario.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instancia = self.get_object()
        if not puede_gestionar_usuarios(request.user, instancia.rol):
            return Response(
                {'detail': 'No tienes permiso para eliminar este usuario.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    def get_queryset(self):
        qs      = super().get_queryset().select_related('perfil_personal')
        usuario = self.request.user
        rol     = self.request.query_params.get('rol')
        if rol:
            qs = qs.filter(rol=rol)
        # ?sin_ficha=true -> usuarios de rol personal que aún no tienen ficha
        # de Personal (para vincularlos desde la pantalla de Personal).
        if self.request.query_params.get('sin_ficha') == 'true':
            qs = qs.filter(perfil_personal__isnull=True,
                           rol__in=UsuarioSerializer.ROLES_PERSONAL)
        # Solo admin ve todos; el resto solo se ve a sí mismo
        if usuario.rol not in ['admin', 'directora']:
            qs = qs.filter(id=usuario.id)
        return qs

    @action(detail=False, methods=['get'], url_path='yo')
    def yo(self, request):
        """Devuelve el perfil del usuario autenticado."""
        serializer = UsuarioSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['patch'], url_path='yo/tema')
    def yo_tema(self, request):
        """Guarda el tema visual del usuario autenticado (solo el suyo)."""
        serializer = TemaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.tema = serializer.validated_data['tema']
        request.user.save(update_fields=['tema'])
        return Response({'tema': request.user.tema})

    @action(detail=False, methods=['post'], url_path='cambiar-password')
    def cambiar_password(self, request):
        """Cambia la contraseña del usuario autenticado."""
        serializer = CambiarPasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        usuario = request.user
        if not usuario.check_password(serializer.validated_data['password_actual']):
            return Response(
                {'password_actual': 'La contraseña actual es incorrecta.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        usuario.set_password(serializer.validated_data['password_nuevo'])
        usuario.save()
        return Response({'mensaje': 'Contraseña actualizada correctamente.'})

    @action(detail=True, methods=['post'], url_path='resetear-password')
    def resetear_password(self, request, pk=None):
        """
        Restablece la contraseña de un usuario. Admin: cualquiera. Directora:
        cualquiera EXCEPTO un admin (si no, bastaba con resetearle la clave a
        un admin para quedarse con su cuenta: escalada de privilegios).
        Es la misma regla que ya se usa para crear/editar/eliminar usuarios.
        """
        usuario = self.get_object()
        if not puede_gestionar_usuarios(request.user, usuario.rol):
            return Response(
                {'detail': 'No tienes permiso para realizar esta acción.'},
                status=status.HTTP_403_FORBIDDEN
            )
        nueva = request.data.get('password')
        if not nueva:
            # Antes, si no se especificaba una contraseña, se usaba SIEMPRE
            # el mismo valor fijo ('MisaelKids2025!') para cualquier cuenta
            # — una contraseña adivinable y compartida por todos los
            # resets. Ahora se genera una aleatoria distinta cada vez.
            import secrets, string
            alfabeto = string.ascii_letters + string.digits
            nueva = ''.join(secrets.choice(alfabeto) for _ in range(12))
        if len(nueva) < 4:
            return Response(
                {'detail': 'La contraseña debe tener al menos 4 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if request.data.get('password'):
            # Solo se valida la que escribió una persona; la generada ya es aleatoria.
            try:
                validate_password(nueva, user=usuario)
            except DjangoValidationError as exc:
                return Response({'detail': ' '.join(exc.messages)},
                                status=status.HTTP_400_BAD_REQUEST)
        usuario.set_password(nueva)
        usuario.save()
        return Response({'mensaje': 'Contraseña restablecida correctamente.', 'password': nueva})
