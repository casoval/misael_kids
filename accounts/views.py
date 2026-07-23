"""
accounts/views.py
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Usuario
from .permissions import puede_gestionar_usuarios
from .serializers import (
    UsuarioSerializer, UsuarioCreateSerializer,
    CambiarPasswordSerializer, MiTokenObtainPairSerializer,
)


class MiTokenObtainPairView(TokenObtainPairView):
    """Login JWT con datos del usuario incluidos."""
    serializer_class = MiTokenObtainPairSerializer


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
            request.data.pop('rol', None)  # no puede auto-ascenderse de rol
            return super().update(request, *args, **kwargs)
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
        qs      = super().get_queryset()
        usuario = self.request.user
        rol     = self.request.query_params.get('rol')
        if rol:
            qs = qs.filter(rol=rol)
        # Solo admin ve todos; el resto solo se ve a sí mismo
        if usuario.rol not in ['admin', 'directora']:
            qs = qs.filter(id=usuario.id)
        return qs

    @action(detail=False, methods=['get'], url_path='yo')
    def yo(self, request):
        """Devuelve el perfil del usuario autenticado."""
        serializer = UsuarioSerializer(request.user, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='cambiar-password')
    def cambiar_password(self, request):
        """Cambia la contraseña del usuario autenticado."""
        serializer = CambiarPasswordSerializer(data=request.data)
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
        """Restablece la contraseña de cualquier usuario. Solo admin/directora."""
        if request.user.rol not in ['admin', 'directora']:
            return Response(
                {'detail': 'No tienes permiso para realizar esta acción.'},
                status=status.HTTP_403_FORBIDDEN
            )
        usuario = self.get_object()
        nueva = request.data.get('password') or 'MisaelKids2025!'
        if len(nueva) < 8:
            return Response(
                {'detail': 'La contraseña debe tener al menos 8 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        usuario.set_password(nueva)
        usuario.save()
        return Response({'mensaje': 'Contraseña restablecida correctamente.', 'password': nueva})
