from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DerivacionViewSet, PlanTrabajoMisaelViewSet
router = DefaultRouter()
router.register(r"derivaciones",   DerivacionViewSet,       basename="derivacion")
router.register(r"planes-misael",  PlanTrabajoMisaelViewSet, basename="plan-misael")
urlpatterns = [path("", include(router.urls))]