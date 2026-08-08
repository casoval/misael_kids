from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from ninos.models import Nino, Tutor, NinoTutor
from .models import Derivacion, PlanTrabajoMisael, VinculoCentroMisael
from .serializers import (
    DerivacionSerializer, PlanTrabajoMisaelSerializer, VinculoCentroMisaelSerializer,
)
from .import centro_misael_client as cm
from accounts.permissions import filtrar_por_tutor, NoEsTutor

class DerivacionViewSet(viewsets.ModelViewSet):
    queryset = Derivacion.objects.select_related("nino","solicitado_por__usuario").all()
    serializer_class   = DerivacionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter]
    search_fields      = ["nino__nombres","nino__apellidos","area_derivacion"]
    filterset_fields   = ["estado","consentimiento_tutor"]

    def get_queryset(self):
        # Las derivaciones a Centro Misael son información sensible
        # (motivo, área de derivación, respuesta del centro). Sin este
        # filtro, CUALQUIER cuenta de tutor podía listar TODAS las
        # derivaciones de TODOS los niños, ni siquiera hacía falta
        # adivinar un ID — bastaba con llamar al endpoint sin filtros.
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')

class PlanTrabajoMisaelViewSet(viewsets.ModelViewSet):
    queryset = PlanTrabajoMisael.objects.select_related("nino","derivacion","plan_individual").all()
    serializer_class   = PlanTrabajoMisaelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends    = [DjangoFilterBackend]
    filterset_fields   = ["nino","activo","consentimiento_tutor"]

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')


# ═══════════════════════════════════════════════════════════════════
# Integración en vivo con Centro Misael (centro_terapias_v2)
# ═══════════════════════════════════════════════════════════════════

# Centro Misael usa 'tio'/'hermano' que Misael Kids no distingue; el
# resto mapea 1 a 1.
_MAPA_PARENTESCO = {
    'madre':   Tutor.PARENTESCO_MADRE,
    'padre':   Tutor.PARENTESCO_PADRE,
    'tutor':   Tutor.PARENTESCO_TUTOR,
    'abuelo':  Tutor.PARENTESCO_ABUELO,
    'tio':     Tutor.PARENTESCO_OTRO,
    'hermano': Tutor.PARENTESCO_OTRO,
    'otro':    Tutor.PARENTESCO_OTRO,
}


def _personal_del_usuario(usuario):
    return getattr(usuario, 'perfil_personal', None)


def _copiar_foto_si_falta(nino, paciente):
    """
    Copia la foto del paciente de Centro Misael al niño, solo si el
    niño todavía no tiene una propia (no pisa una foto ya subida a
    mano en Misael Kids). Si falla la descarga, no bloquea nada — el
    niño/vínculo se crea igual, simplemente sin foto.
    """
    if nino.foto:
        return
    foto_url = paciente.get('foto_url')
    if not foto_url:
        return
    try:
        contenido = cm.descargar_archivo(foto_url)
        nino.foto.save(f'centro_misael_{paciente.get("id","")}.jpg', ContentFile(contenido), save=True)
    except cm.CentroMisaelError:
        pass  # el niño igual se crea/vincula, solo queda sin foto


def _crear_tutores_desde_paciente(nino, paciente, es_principal_solo_el_primero=True):
    """
    Crea (o reutiliza si ya hay uno con el mismo teléfono) los Tutor de
    Misael Kids a partir de los datos del tutor/es del paciente en
    Centro Misael, y los vincula al niño.

    Centro Misael no guarda CI del tutor (Misael Kids sí la requiere
    para retiro de niños), así que queda marcada como pendiente de
    completar por el jardín — no bloquea la vinculación.
    """
    creados = []
    datos_tutores = [
        {
            'nombre_completo': paciente.get('nombre_tutor', ''),
            'parentesco':      paciente.get('parentesco', 'otro'),
            'telefono':        paciente.get('telefono_tutor', ''),
            'email':           paciente.get('email_tutor', '') or '',
        },
    ]
    if paciente.get('nombre_tutor_2'):
        datos_tutores.append({
            'nombre_completo': paciente.get('nombre_tutor_2', ''),
            'parentesco':      paciente.get('parentesco_2', 'otro'),
            'telefono':        paciente.get('telefono_tutor_2', ''),
            'email':           paciente.get('email_tutor_2', '') or '',
        })

    for i, datos in enumerate(datos_tutores):
        nombre_completo = (datos['nombre_completo'] or '').strip()
        if not nombre_completo:
            continue
        partes = nombre_completo.split(' ', 1)
        nombres = partes[0]
        apellidos = partes[1] if len(partes) > 1 else ''

        # Reutiliza un tutor existente con el mismo teléfono, para no
        # duplicar si el mismo padre ya tiene cuenta en Misael Kids
        # (p.ej. por un hermano ya inscrito).
        tutor = None
        if datos['telefono']:
            tutor = Tutor.objects.filter(telefono=datos['telefono']).first()

        if tutor is None:
            tutor = Tutor.objects.create(
                nombres=nombres,
                apellidos=apellidos,
                ci=f'PENDIENTE-CM-{paciente["id"]}-{i}',
                telefono=datos['telefono'] or '',
                email=datos['email'],
                parentesco=_MAPA_PARENTESCO.get(datos['parentesco'], Tutor.PARENTESCO_OTRO),
            )
            creados.append(tutor)

        NinoTutor.objects.get_or_create(
            nino=nino, tutor=tutor,
            defaults={'es_principal': (i == 0), 'puede_retirar': True},
        )

    return creados


class BuscarPacienteCentroMisaelView(APIView):
    """GET /api/misael-link/centro-misael/buscar/?q=<texto>"""
    permission_classes = [IsAuthenticated, NoEsTutor]

    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if len(q) < 2:
            return Response({'detail': 'Escribe al menos 2 caracteres para buscar.'}, status=400)
        try:
            resultados = cm.buscar_pacientes(q)
        except cm.CentroMisaelNoConfigurado as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except cm.CentroMisaelError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(resultados)


class VincularCentroMisaelView(APIView):
    """
    POST /api/misael-link/centro-misael/vincular/
    body: { "paciente_centro_id": 123, "nino_id": 45 (opcional) }

    - Si se envía `nino_id`: vincula ese niño existente con el paciente
      de Centro Misael y completa los campos de salud que estén vacíos
      (no pisa datos que la educadora ya haya cargado a mano).
    - Si NO se envía `nino_id`: crea un niño nuevo con los datos
      copiados del paciente (y sus tutores), y lo vincula.

    El estado (activo/inactivo) del paciente en Centro Misael no se
    valida: si el tutor lo pide, se vincula igual.
    """
    permission_classes = [IsAuthenticated, NoEsTutor]

    @transaction.atomic
    def post(self, request):
        paciente_centro_id = request.data.get('paciente_centro_id')
        nino_id = request.data.get('nino_id')
        if not paciente_centro_id:
            return Response({'detail': 'paciente_centro_id es requerido.'}, status=400)

        try:
            paciente = cm.obtener_paciente(paciente_centro_id)
        except cm.CentroMisaelNoConfigurado as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except cm.CentroMisaelError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if paciente is None:
            return Response({'detail': 'No se encontró ese paciente en Centro Misael.'}, status=404)

        if VinculoCentroMisael.objects.filter(paciente_centro_id=paciente_centro_id).exists():
            return Response(
                {'detail': 'Ese paciente ya está vinculado a otro niño en Misael Kids.'}, status=409
            )

        condiciones = ' / '.join(filter(None, [
            paciente.get('diagnostico', ''), paciente.get('observaciones_medicas', ''),
        ]))

        if nino_id:
            try:
                nino = Nino.objects.get(pk=nino_id)
            except Nino.DoesNotExist:
                return Response({'detail': 'Niño no encontrado.'}, status=404)
            if hasattr(nino, 'vinculo_centro_misael'):
                return Response({'detail': 'Este niño ya está vinculado con Centro Misael.'}, status=409)

            # Solo completa lo que esté vacío — no pisa datos ya cargados.
            if not nino.alergias and paciente.get('alergias'):
                nino.alergias = paciente['alergias']
            if not nino.condiciones_medicas and condiciones:
                nino.condiciones_medicas = condiciones
            nino.save(update_fields=['alergias', 'condiciones_medicas'])
            _copiar_foto_si_falta(nino, paciente)
        else:
            genero = paciente.get('genero') or Nino.GENERO_OTRO
            if genero not in dict(Nino.GENEROS):
                genero = Nino.GENERO_OTRO
            nino = Nino.objects.create(
                nombres=paciente.get('nombre', ''),
                apellidos=paciente.get('apellido', ''),
                fecha_nacimiento=paciente['fecha_nacimiento'],
                genero=genero,
                alergias=paciente.get('alergias', '') or '',
                condiciones_medicas=condiciones,
            )
            _copiar_foto_si_falta(nino, paciente)

        _crear_tutores_desde_paciente(nino, paciente)

        vinculo = VinculoCentroMisael.objects.create(
            nino=nino,
            paciente_centro_id=paciente_centro_id,
            nombre_paciente_centro=paciente.get('nombre_completo', ''),
            estado_centro_cache=paciente.get('estado', ''),
            vinculado_por=_personal_del_usuario(request.user),
        )

        return Response({
            'nino_id': nino.id,
            'vinculo': VinculoCentroMisaelSerializer(vinculo).data,
            'creado_nuevo': not bool(nino_id),
        }, status=201)


class SincronizarDocumentosCentroMisaelView(APIView):
    """
    POST /api/misael-link/centro-misael/sincronizar/
    body: { "nino_id": 45 }

    Trae los documentos que el profesional de Centro Misael marcó como
    "Compartir con Misael Kids" y los guarda como PlanTrabajoMisael,
    sin duplicar los que ya se hayan importado antes. Funciona igual
    si el paciente está inactivo en Centro Misael.
    """
    permission_classes = [IsAuthenticated, NoEsTutor]

    def post(self, request):
        nino_id = request.data.get('nino_id')
        try:
            vinculo = VinculoCentroMisael.objects.select_related('nino').get(nino_id=nino_id)
        except VinculoCentroMisael.DoesNotExist:
            return Response(
                {'detail': 'Este niño no está vinculado con Centro Misael todavía.'}, status=404
            )

        try:
            documentos = cm.listar_documentos_compartidos(vinculo.paciente_centro_id)
        except cm.CentroMisaelNoConfigurado as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except cm.CentroMisaelError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        ya_importados = set(
            PlanTrabajoMisael.objects.filter(nino=vinculo.nino, documento_centro_id__isnull=False)
            .values_list('documento_centro_id', flat=True)
        )

        creados = []
        for doc in documentos:
            if doc['id'] in ya_importados:
                continue
            fecha_str = (doc.get('fecha_subida') or '')[:10]
            plan = PlanTrabajoMisael(
                nino=vinculo.nino,
                profesional_email='',
                profesional_nombre=doc.get('subido_por_nombre', '') or 'Centro Misael',
                descripcion=doc.get('descripcion') or doc.get('titulo', ''),
                fecha_inicio=fecha_str or timezone.now().date(),
                origen='sincronizado',
                documento_centro_id=doc['id'],
            )
            if doc.get('archivo_url'):
                try:
                    contenido = cm.descargar_archivo(doc['archivo_url'])
                    plan.informe_pdf.save(
                        doc.get('nombre_archivo') or f'plan_misael_{doc["id"]}.pdf',
                        ContentFile(contenido), save=False,
                    )
                except cm.CentroMisaelError:
                    pass  # el registro igual se crea, sin archivo adjunto
            plan.save()
            creados.append(plan)

        if creados:
            vinculo.nino.tiene_plan_misael = True
            vinculo.nino.save(update_fields=['tiene_plan_misael'])
        vinculo.ultima_sincronizacion = timezone.now()
        vinculo.save(update_fields=['ultima_sincronizacion'])

        return Response({
            'importados': len(creados),
            'planes': PlanTrabajoMisaelSerializer(creados, many=True).data,
        })


class VinculoCentroMisaelViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VinculoCentroMisael.objects.select_related('nino', 'vinculado_por').all()
    serializer_class = VinculoCentroMisaelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['nino']

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')