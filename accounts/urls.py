"""
accounts/urls.py
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import MiTokenObtainPairView, UsuarioViewSet

router = DefaultRouter()
router.register(r'usuarios', UsuarioViewSet, basename='usuario')

urlpatterns = [
    path('login/',          MiTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/',  TokenRefreshView.as_view(),      name='token_refresh'),
    path('', include(router.urls)),
]
