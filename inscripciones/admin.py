from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.admin.utils import unquote

from .models import Inscripcion, Cobro, Pago, AbonoDiario, DiasContratados, Devolucion


# ─────────────────────────────────────────────────────────────────────────────
# Protección contra borrados con movimientos de dinero
#
# Todas las relaciones de la cuenta del niño están en cascada: borrar una
# inscripción arrastra cobros, pagos, abonos y devoluciones, y un abono o pago
# puede estar ligado a OTRA inscripción del mismo niño (al borrarlo, esa otra
# cuenta pierde lo pagado). Por eso el administrador NO permite borrar nada que
# tenga dinero registrado: primero hay que borrar, uno por uno, los pagos,
# abonos y devoluciones.
#
# Pagos y abonos sí se pueden borrar desde aquí (recalculando el estado de los
# cobros que cubrían); lo que se bloquea es borrar la inscripción o el cobro
# que los contiene, para no arrastrarlos sin querer.
#
# Se bloquea en tres niveles:
#   1. has_delete_permission(obj): esconde el botón "Eliminar", frena el borrado
#      masivo y también el borrado en cascada desde el niño, la sala, el turno o
#      la sucursal (Django exige permiso sobre cada objeto que arrastra).
#   2. delete_view: si alguien entra a la URL de borrado, lo devuelve con el motivo.
#   3. get_deleted_objects: en el borrado masivo muestra el motivo en vez del
#      mensaje genérico de permisos.
# ─────────────────────────────────────────────────────────────────────────────
AYUDA_BORRADO_MANUAL = (
    'Si es un error de carga y hay que borrarlo igual, primero borre sus pagos y abonos '
    '(en Pagos y Abonos) y revise que ese dinero no esté aplicado a otra inscripción del mismo niño. '
    'Las devoluciones se borran a mano en la base de datos.'
)


def _plural(n, uno, varios):
    return f'{n} {uno if n == 1 else varios}'


def movimientos_de_inscripcion(insc):
    """Cuenta el dinero registrado que colgaría de una inscripción."""
    return {
        'pagos': Pago.objects.filter(cobro__inscripcion=insc).count(),
        'abonos': AbonoDiario.objects.filter(inscripcion=insc).count(),
        'devoluciones': Devolucion.objects.filter(
            Q(cobro__inscripcion=insc) | Q(inscripcion=insc)).count(),
    }


def motivo_bloqueo_inscripcion(insc):
    m = movimientos_de_inscripcion(insc)
    partes = []
    if m['pagos']:
        partes.append(_plural(m['pagos'], 'pago', 'pagos'))
    if m['abonos']:
        partes.append(_plural(m['abonos'], 'abono', 'abonos'))
    if m['devoluciones']:
        partes.append(_plural(m['devoluciones'], 'devolución', 'devoluciones'))
    if not partes:
        return None
    return f'No se puede borrar la inscripción de {insc.nino}: tiene {", ".join(partes)}. ' + AYUDA_BORRADO_MANUAL


def motivo_bloqueo_cobro(cobro):
    pagos = cobro.pagos.count()
    devs = cobro.devoluciones.count()
    if not pagos and not devs:
        return None
    partes = []
    if pagos:
        partes.append(_plural(pagos, 'pago', 'pagos'))
    if devs:
        partes.append(_plural(devs, 'devolución', 'devoluciones'))
    return f'No se puede borrar el cobro "{cobro}": tiene {" y ".join(partes)}. ' + AYUDA_BORRADO_MANUAL


class BloqueoBorradoMixin:
    """Bloquea el borrado de objetos según `motivo_bloqueo(obj)` (None = se puede)."""

    def motivo_bloqueo(self, obj):
        raise NotImplementedError

    def has_delete_permission(self, request, obj=None):
        if obj is not None and self.motivo_bloqueo(obj):
            return False
        return super().has_delete_permission(request, obj)

    def delete_view(self, request, object_id, extra_context=None):
        obj = self.get_object(request, unquote(object_id))
        motivo = self.motivo_bloqueo(obj) if obj is not None else None
        if motivo:
            messages.error(request, motivo)
            opts = self.model._meta
            return redirect(reverse(f'admin:{opts.app_label}_{opts.model_name}_change', args=[obj.pk]))
        return super().delete_view(request, object_id, extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        if request.method == 'GET':
            obj = self.get_object(request, unquote(object_id))
            motivo = self.motivo_bloqueo(obj) if obj is not None else None
            if motivo:
                messages.warning(request, motivo)
        return super().change_view(request, object_id, form_url, extra_context)

    def get_deleted_objects(self, objs, request):
        deletable, model_count, perms_needed, protected = super().get_deleted_objects(objs, request)
        for o in objs:
            motivo = self.motivo_bloqueo(o)
            if motivo:
                protected.append(motivo)
        if protected:
            perms_needed = set()  # el motivo concreto reemplaza al aviso genérico de permisos
        return deletable, model_count, perms_needed, protected


class RecalculaCobrosAlBorrarMixin:
    """Pagos y abonos SÍ se pueden borrar desde el administrador, pero al hacerlo
    se recalcula el estado de los cobros afectados (si no, un cobro quedaría
    "pagado" o "parcial" sin tener ya el dinero que lo cubría)."""

    def _cobros_afectados(self, objs):
        raise NotImplementedError

    def delete_model(self, request, obj):
        self.delete_queryset(request, self.model.objects.filter(pk=obj.pk))

    def delete_queryset(self, request, queryset):
        with transaction.atomic():
            cobros = {c.pk: c for c in self._cobros_afectados(queryset)}
            queryset.delete()
            for c in cobros.values():
                c.refresh_from_db()
                c.recalcular_estado()


class CobroInline(admin.TabularInline):
    model  = Cobro
    extra  = 0
    can_delete = False  # los cobros se borran desde su propia pantalla, que revisa que no tengan pagos
    fields = ['tipo', 'periodo', 'monto_final', 'fecha_vencimiento', 'estado', 'fecha_pago', 'metodo_pago']
    readonly_fields = ['fecha_vencimiento']

class PagoInline(admin.TabularInline):
    model  = Pago
    extra  = 0
    can_delete = False
    fields = ['monto', 'fecha_pago', 'metodo_pago', 'registrado_por', 'observacion']

@admin.register(Inscripcion)
class InscripcionAdmin(BloqueoBorradoMixin, admin.ModelAdmin):
    def motivo_bloqueo(self, obj):
        return motivo_bloqueo_inscripcion(obj)

    list_display  = ['nino', 'sucursal', 'sala', 'turno', 'modalidad_pago', 'dias_semana', 'tipo_ajuste', 'costo_mensual_final', 'activa']
    list_filter   = ['sucursal', 'sala', 'modalidad_pago', 'tipo_ajuste', 'activa']
    search_fields = ['nino__nombres', 'nino__apellidos']
    inlines       = [CobroInline]

@admin.register(Cobro)
class CobroAdmin(BloqueoBorradoMixin, admin.ModelAdmin):
    def motivo_bloqueo(self, obj):
        return motivo_bloqueo_cobro(obj)

    list_display   = ['__str__', 'tipo', 'monto_final', 'monto_pagado', 'saldo_pendiente',
                       'fecha_vencimiento', 'estado', 'fecha_pago', 'metodo_pago']
    list_filter    = ['tipo', 'estado', 'metodo_pago']
    search_fields  = ['inscripcion__nino__nombres', 'inscripcion__nino__apellidos']
    date_hierarchy = 'fecha_emision'
    readonly_fields = ['fecha_emision']
    inlines        = [PagoInline]

@admin.register(Pago)
class PagoAdmin(RecalculaCobrosAlBorrarMixin, admin.ModelAdmin):
    def _cobros_afectados(self, qs):
        return Cobro.objects.filter(pagos__in=qs).distinct()

    list_display  = ['cobro', 'monto', 'fecha_pago', 'metodo_pago', 'registrado_por']
    list_filter   = ['metodo_pago', 'fecha_pago']
    date_hierarchy = 'fecha_pago'


@admin.register(AbonoDiario)
class AbonoDiarioAdmin(RecalculaCobrosAlBorrarMixin, admin.ModelAdmin):
    def _cobros_afectados(self, qs):
        # borrar un abono borra también sus aplicaciones (pagos) sobre los cobros
        return Cobro.objects.filter(pagos__abono_origen__in=qs).distinct()

    list_display   = ['inscripcion', 'monto', 'fecha_pago', 'metodo_pago', 'numero_recibo', 'registrado_por']
    list_filter    = ['metodo_pago', 'fecha_pago']
    date_hierarchy = 'fecha_pago'

@admin.register(DiasContratados)
class DiasContratadosAdmin(admin.ModelAdmin):
    list_display = ['inscripcion', 'tipo', 'cantidad', 'fecha', 'registrado_por']
    list_filter  = ['tipo']
