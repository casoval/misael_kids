from django.contrib import admin
from .models import Nino, Tutor, NinoTutor, PersonaAutorizada, Documento

class NinoTutorInline(admin.TabularInline):
    model  = NinoTutor
    extra  = 1
    fields = ['tutor', 'es_principal', 'puede_retirar']

class PersonaAutorizadaInline(admin.TabularInline):
    model  = PersonaAutorizada
    extra  = 0
    fields = ['nombres', 'apellidos', 'ci', 'telefono', 'parentesco', 'vigencia_desde', 'vigencia_hasta', 'activa']

class DocumentoInline(admin.TabularInline):
    model  = Documento
    extra  = 0
    fields = ['tipo', 'nombre', 'archivo', 'verificado']

@admin.register(Nino)
class NinoAdmin(admin.ModelAdmin):
    list_display  = ['nombre_completo', 'fecha_nacimiento', 'edad_en_meses', 'tiene_plan_misael', 'activo']
    list_filter   = ['genero', 'tiene_plan_misael', 'activo']
    search_fields = ['nombres', 'apellidos']
    inlines       = [NinoTutorInline, PersonaAutorizadaInline, DocumentoInline]

@admin.register(Tutor)
class TutorAdmin(admin.ModelAdmin):
    list_display  = ['__str__', 'ci', 'telefono', 'email']
    search_fields = ['nombres', 'apellidos', 'ci']
