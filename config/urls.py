"""
Misael Kids — URLs raíz del proyecto
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    # ── Raíz → login ──────────────────────────────────────────────
    path('', TemplateView.as_view(template_name='login.html'), name='login'),

    # ── Admin Django ───────────────────────────────────────────────
    path('admin/', admin.site.urls),

    # ── APIs REST ──────────────────────────────────────────────────
    path('api/auth/',          include('accounts.urls')),
    path('api/core/',          include('core.urls')),
    path('api/personal/',      include('personal.urls')),
    path('api/ninos/',         include('ninos.urls')),
    path('api/inscripciones/', include('inscripciones.urls')),
    path('api/asistencia/',    include('asistencia.urls')),
    path('api/agenda/',        include('agenda.urls')),
    path('api/salud/',         include('salud.urls')),
    path('api/comunicacion/',  include('comunicacion.urls')),
    path('api/inventario/',    include('inventario.urls')),
    path('api/evaluacion/',    include('evaluacion.urls')),
    path('api/misael-link/',   include('misael_link.urls')),
    path('api/reportes/',      include('reportes.urls')),

    # ── Páginas del frontend (panel interno) ───────────────────────
    path('panel/dashboard/',    TemplateView.as_view(template_name='pages/panel/dashboard.html'),    name='panel-dashboard'),
    path('panel/asistencia/',   TemplateView.as_view(template_name='pages/panel/asistencia.html'),   name='panel-asistencia'),
    path('panel/ninos/',        TemplateView.as_view(template_name='pages/panel/ninos.html'),        name='panel-ninos'),
    path('panel/cobros/',       TemplateView.as_view(template_name='pages/panel/cobros.html'),       name='panel-cobros'),
    path('panel/inventario/',   TemplateView.as_view(template_name='pages/panel/inventario.html'),   name='panel-inventario'),
    path('panel/agenda/',       TemplateView.as_view(template_name='pages/panel/agenda.html'),       name='panel-agenda'),
    path('panel/personal/',     TemplateView.as_view(template_name='pages/panel/personal.html'),     name='panel-personal'),
    path('panel/salud/',        TemplateView.as_view(template_name='pages/panel/salud.html'),        name='panel-salud'),
    path('panel/comunicacion/', TemplateView.as_view(template_name='pages/panel/comunicacion.html'), name='panel-comunicacion'),
    path('panel/evaluacion/',   TemplateView.as_view(template_name='pages/panel/evaluacion.html'),   name='panel-evaluacion'),
    path('panel/inscripciones/',TemplateView.as_view(template_name='pages/panel/inscripciones.html'),name='panel-inscripciones'),
    path('panel/sucursales/',   TemplateView.as_view(template_name='pages/panel/sucursales.html'),   name='panel-sucursales'),
    path('panel/reportes/',     TemplateView.as_view(template_name='pages/panel/reportes.html'),     name='panel-reportes'),


    # ── Páginas adicionales del frontend ──────────────────────────────────────
    path('panel/tutores/',      TemplateView.as_view(template_name='pages/panel/tutores.html'),      name='panel-tutores'),
    path('panel/personal/nuevo/', TemplateView.as_view(template_name='pages/panel/personal.html'),  name='panel-personal-nuevo'),


    path('panel/misael-link/', TemplateView.as_view(template_name='pages/panel/misael-link.html'), name='panel-misael-link'),

    path('panel/usuarios/',    TemplateView.as_view(template_name='pages/panel/usuarios.html'),    name='panel-usuarios'),

    # ── Páginas del frontend (portal de padres) ────────────────────
    path('portal/',             TemplateView.as_view(template_name='pages/portal/inicio.html'),      name='portal-inicio'),
]

# Archivos media y estáticos en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
