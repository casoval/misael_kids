from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario

@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display  = ['identificador', 'nombres', 'apellidos', 'rol', 'activo']
    list_filter   = ['rol', 'activo']
    search_fields = ['email', 'username', 'nombres', 'apellidos']
    ordering      = ['apellidos', 'nombres']
    fieldsets = (
        (None,           {'fields': ('email', 'username', 'password')}),
        ('Datos personales', {'fields': ('nombres', 'apellidos', 'telefono', 'foto')}),
        ('Rol y acceso',  {'fields': ('rol', 'activo', 'is_staff', 'is_superuser')}),
        ('Permisos',      {'fields': ('groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'username', 'nombres', 'apellidos', 'rol', 'password1', 'password2')}),
    )
