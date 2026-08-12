from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, viewsets, filters, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from ninos.models import Nino, Tutor, NinoTutor
from .models import Derivacion, VinculoCentroMisael
from .serializers import (
    DerivacionSerializer, VinculoCentroMisaelSerializer,
    NinoBusquedaCentroMisaelSerializer, NinoDetalleCentroMisaelSerializer,
    VinculoConDerivacionesSerializer,
)
from .import centro_misael_client as cm
from .authentication import CentroMisaelAPIKeyAuthentication
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

    def perform_create(self, serializer):
        # `solicitado_por` es opcional: cualquier cuenta con permiso puede
        # crear una derivación, tenga o no una ficha de Personal asociada.
        # Cuando sí existe, la guardamos para trazabilidad (quién lo pidió);
        # cuando no, queda vacía sin bloquear el guardado.
        serializer.save(solicitado_por=_personal_del_usuario(self.request.user))


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


def _obtener_vinculo_o_404(nino_id):
    try:
        return VinculoCentroMisael.objects.select_related('nino').get(nino_id=nino_id)
    except VinculoCentroMisael.DoesNotExist:
        return None


class PlanesTrabajoCentroMisaelView(APIView):
    """
    GET /api/misael-link/centro-misael/planes-trabajo/?nino_id=<uuid>

    Lista en vivo los planes de trabajo (modelo PlanTrabajo) que los
    profesionales del Centro Misael crearon para este paciente — cada
    uno con su propio profesional, área, fechas y documento adjunto.
    Solo lectura: no se descarga ni guarda nada en Misael Kids, se
    consulta la API de Centro Misael en cada request.
    """
    permission_classes = [IsAuthenticated, NoEsTutor]

    def get(self, request):
        nino_id = request.query_params.get('nino_id')
        vinculo = _obtener_vinculo_o_404(nino_id)
        if vinculo is None:
            return Response(
                {'detail': 'Este niño no está vinculado con Centro Misael todavía.'}, status=404
            )

        try:
            planes = cm.listar_planes_trabajo(vinculo.paciente_centro_id)
        except cm.CentroMisaelNoConfigurado as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except cm.CentroMisaelError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        vinculo.ultima_sincronizacion = timezone.now()
        vinculo.save(update_fields=['ultima_sincronizacion'])

        return Response({'planes': planes})


# ═══════════════════════════════════════════════════════════════════
# Endpoints ENTRANTES: Centro Misael consultando a Misael Kids
# ═══════════════════════════════════════════════════════════════════

class ConsultaVinculoCentroMisaelView(APIView):
    """
    GET /api/misael-link/consulta/vinculo/?paciente_centro_id=<id>

    Llamado por Centro Misael (con su propia API key) para saber si un
    paciente suyo ya está vinculado con algún niño de Misael Kids, sin
    necesidad de mantener una copia de la tabla de vínculos del otro
    lado — Misael Kids sigue siendo la única fuente de verdad.
    """
    authentication_classes = [CentroMisaelAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        paciente_centro_id = request.query_params.get('paciente_centro_id')
        if not paciente_centro_id:
            return Response({'detail': 'paciente_centro_id es requerido.'}, status=400)

        vinculo = VinculoCentroMisael.objects.select_related('nino').filter(
            paciente_centro_id=paciente_centro_id
        ).first()

        if vinculo is None:
            return Response({'vinculado': False})

        return Response({
            'vinculado': True,
            'nino_id': vinculo.nino_id,
            'nino_nombre': vinculo.nino.nombre_completo,
            'fecha_vinculacion': vinculo.fecha_vinculacion,
        })


class DerivacionesCentroMisaelView(APIView):
    """
    GET /api/misael-link/consulta/derivaciones/?paciente_centro_id=<id>

    Llamado por Centro Misael para ver las derivaciones que Misael Kids
    mandó sobre el paciente vinculado. Marca `vista_por_centro=True` en
    las que devuelve, para que Misael Kids pueda mostrar más adelante
    cuáles ya fueron revisadas del otro lado.
    """
    authentication_classes = [CentroMisaelAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        paciente_centro_id = request.query_params.get('paciente_centro_id')
        if not paciente_centro_id:
            return Response({'detail': 'paciente_centro_id es requerido.'}, status=400)

        try:
            vinculo = VinculoCentroMisael.objects.get(paciente_centro_id=paciente_centro_id)
        except VinculoCentroMisael.DoesNotExist:
            return Response({'detail': 'Ese paciente no está vinculado con ningún niño.'}, status=404)

        derivaciones = Derivacion.objects.filter(nino=vinculo.nino).order_by('-fecha_solicitud')
        data = DerivacionSerializer(derivaciones, many=True).data

        no_vistas = derivaciones.filter(vista_por_centro=False)
        if no_vistas.exists():
            no_vistas.update(vista_por_centro=True, fecha_vista_por_centro=timezone.now())

        return Response(data)


class NinosSinVincularCentroMisaelView(generics.ListAPIView):
    """
    GET /api/misael-link/consulta/ninos-sin-vincular/?q=<texto>

    Llamado por Centro Misael para buscar niños de Misael Kids que
    todavía NO tienen vínculo, desde su propia pantalla de
    vinculación (espejo de BuscarPacienteCentroMisaelView, pero en
    sentido inverso). Incluye niños activos e inactivos a propósito.
    """
    authentication_classes = [CentroMisaelAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = NinoBusquedaCentroMisaelSerializer

    def get_queryset(self):
        q = self.request.query_params.get('q', '').strip()
        qs = Nino.objects.filter(
            vinculo_centro_misael__isnull=True
        ).order_by('apellidos', 'nombres')
        if q:
            qs = qs.filter(
                Q(nombres__icontains=q) |
                Q(apellidos__icontains=q) |
                Q(tutores__tutor__nombres__icontains=q) |
                Q(tutores__tutor__apellidos__icontains=q)
            ).distinct()
        return qs[:25]


class NinoDetalleCentroMisaelView(generics.RetrieveAPIView):
    """
    GET /api/misael-link/consulta/ninos/<id>/

    Detalle completo del niño, para que Centro Misael copie los datos
    al crear el Paciente antes de vincular.
    """
    authentication_classes = [CentroMisaelAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = NinoDetalleCentroMisaelSerializer
    queryset = Nino.objects.all()

    def get_serializer_context(self):
        return {'request': self.request}


class VincularDesdeCentroMisaelView(APIView):
    """
    POST /api/misael-link/consulta/vincular/
    body: {"nino_id": "<uuid>", "paciente_centro_id": 123, "nombre_paciente_centro": "..."}

    Registra el vínculo cuando el flujo se inicia del lado de Centro
    Misael (a diferencia de VincularCentroMisaelView, acá el niño ya
    existe en Misael Kids y el Paciente ya existe o se acaba de crear
    del otro lado — este endpoint solo crea el VinculoCentroMisael).
    """
    authentication_classes = [CentroMisaelAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        nino_id = request.data.get('nino_id')
        paciente_centro_id = request.data.get('paciente_centro_id')
        nombre_paciente_centro = request.data.get('nombre_paciente_centro', '') or ''

        if not nino_id or not paciente_centro_id:
            return Response(
                {'detail': 'nino_id y paciente_centro_id son requeridos.'}, status=400
            )

        try:
            nino = Nino.objects.get(pk=nino_id)
        except (Nino.DoesNotExist, ValueError, TypeError):
            return Response({'detail': 'Niño no encontrado en Misael Kids.'}, status=404)

        if hasattr(nino, 'vinculo_centro_misael'):
            return Response(
                {'detail': 'Este niño ya está vinculado con Centro Misael.'}, status=409
            )

        if VinculoCentroMisael.objects.filter(paciente_centro_id=paciente_centro_id).exists():
            return Response(
                {'detail': 'Ese paciente ya está vinculado a otro niño en Misael Kids.'},
                status=409,
            )

        vinculo = VinculoCentroMisael.objects.create(
            nino=nino,
            paciente_centro_id=paciente_centro_id,
            nombre_paciente_centro=nombre_paciente_centro,
        )
        return Response(VinculoCentroMisaelSerializer(vinculo).data, status=201)


class VinculadosListCentroMisaelView(generics.ListAPIView):
    """
    GET /api/misael-link/consulta/vinculados/

    Lista todos los vínculos existentes con un resumen de sus
    derivaciones, para la pestaña "Niños vinculados" de la pantalla
    de vinculación en Centro Misael.
    """
    authentication_classes = [CentroMisaelAPIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = VinculoConDerivacionesSerializer
    queryset = (
        VinculoCentroMisael.objects
        .select_related('nino', 'vinculado_por')
        .order_by('-fecha_vinculacion')
    )


class VinculoCentroMisaelViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VinculoCentroMisael.objects.select_related('nino', 'vinculado_por').all()
    serializer_class = VinculoCentroMisaelSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['nino']

    def get_queryset(self):
        return filtrar_por_tutor(super().get_queryset(), self.request.user, 'nino')