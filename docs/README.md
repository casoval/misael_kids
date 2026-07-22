# 🌟 Misael Kids — Sistema de gestión de jardín infantil

App Django integrada (backend + frontend) para la gestión integral del jardín infantil **Misael Kids** — La Paz, Bolivia.

---

## 📌 Estado actual del proyecto

| Componente | Estado |
|---|---|
| Estructura del proyecto Django | ✅ Completo |
| 13 apps Django | ✅ Completo |
| 28 modelos de base de datos | ✅ Completo |
| 97 endpoints API REST | ✅ Completo |
| Autenticación JWT | ✅ Configurado |
| Base de datos PostgreSQL migrada | ✅ En producción local |
| Datos iniciales cargados | ✅ 1 sucursal, 3 salas, 6 turnos, 32 hitos |
| **Frontend integrado (Opción A)** | ✅ Completo — 17 páginas HTML |
| **Sidebar dinámico** (components.js) | ✅ Todas las páginas |
| **CRUD completo con validaciones** | ✅ Todas las páginas |
| Serializers y ViewSets API | ✅ Completo |
| Admin Django | ✅ Funcionando |
| Módulos Fase 2 (galería, app móvil) | ⏳ Pendiente — Fase 2 |

---

## 🚀 Instalación rápida (Windows)

```bash
# 1. Ir a la carpeta del proyecto
cd C:\proyectos\misael_kids

# 2. Crear y activar entorno virtual
python -m venv venv
venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar .env (editar con tus datos de PostgreSQL)
notepad .env

# 5. Crear la BD en PostgreSQL
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE misael_kids_db;"

# 6. Aplicar migraciones
python manage.py migrate

# 7. Cargar datos iniciales
python manage.py loaddata core/fixtures/datos_iniciales.json
python manage.py loaddata evaluacion/fixtures/hitos_desarrollo.json

# 8. Crear superusuario
python manage.py createsuperuser

# 9. Levantar servidor
python manage.py runserver
```

Abrir el navegador en: **http://localhost:8000/**

---

## 🔑 Credenciales por defecto

| Dato | Valor |
|---|---|
| URL | http://localhost:8000/ |
| Email admin | admin@misaelkids.com |
| Contraseña inicial personal | MisaelKids2025! |
| Panel admin Django | http://localhost:8000/admin/ |

---

## ⚠️ Problemas conocidos y soluciones

### Error `UnicodeDecodeError` al iniciar el servidor
La contraseña en `.env` tiene caracteres especiales (ñ, ó, etc.).
**Solución:** Usar solo letras, números y guiones en `DB_PASSWORD`.

### Error `no se ha seleccionado ningún esquema`
El `settings/base.py` tiene `OPTIONS search_path=misael_kids` y el esquema no existe.
**Solución:** Eliminar el bloque `OPTIONS` de `DATABASES` en `base.py` (ya corregido en versión actual).

### Error `Las credenciales de autenticación no se proveyeron`
El backend no tenía `JWTAuthentication` como clase de autenticación.
**Solución:** Ya corregido — `config/settings/base.py` incluye `rest_framework_simplejwt.authentication.JWTAuthentication`.

---

## 🏗️ Arquitectura del sistema

### Integración Frontend (Opción A)
El frontend vive **dentro del proyecto Django** en la carpeta `frontend/`.
Django sirve los HTMLs como templates y los CSS/JS como archivos estáticos.
**No se necesita un servidor separado** — todo corre con `python manage.py runserver`.

```
http://localhost:8000/          → login.html
http://localhost:8000/panel/*   → páginas del panel interno
http://localhost:8000/portal/   → portal de padres
http://localhost:8000/api/*     → API REST
http://localhost:8000/admin/    → Admin Django
```

### Archivo JS central: `frontend/js/api.js`
Contiene:
- `Auth` — manejo de sesión JWT (login, logout, refresh automático, redirección por rol)
- `API` — cliente HTTP con `get/post/patch/delete` y autenticación automática
- `UI` — helpers de UI: toast, modal, loader, iniciales, fecha, moneda, chips

### Archivo JS de componentes: `frontend/js/components.js`
Contiene:
- `Validar` — validaciones de formulario con errores en pantalla
- `CRUD` — helpers genéricos para tablas, eliminación y guardado
- `renderSidebar(paginaActiva)` — genera el sidebar dinámico según el rol del usuario
- `initPanel(pagina, roles)` — inicializa toda página del panel: verifica auth, renderiza sidebar

---

## 📁 Estructura del proyecto

```
misael_kids/
├── config/
│   ├── settings/
│   │   ├── base.py            ← JWT + DRF + CORS + STATIC configurados
│   │   ├── development.py
│   │   └── production.py
│   └── urls.py                ← 18 rutas frontend + 13 APIs + admin
│
├── accounts/        👤 Usuario personalizado con 8 roles
├── core/            🏢 Sucursal, Sala, Turno
├── personal/        👩‍🏫 Personal, AsignacionPersonal, AsistenciaPersonal
├── ninos/           👶 Nino, Tutor, NinoTutor, PersonaAutorizada, Documento
├── inscripciones/   📝 Inscripcion (con costos y ajustes), Cobro
├── asistencia/      📋 Asistencia diaria
├── agenda/          📔 PlanificacionGrupal, PlanIndividual, ObjetivoIndividual, RegistroObjetivo
├── salud/           🏥 IncidenteSalud
├── comunicacion/    📨 Mensaje, Aviso
├── inventario/      📦 ItemInventario, MovimientoInventario
├── evaluacion/      🌱 HitoDesarrollo, EvaluacionNino
├── misael_link/     🔗 Derivacion, PlanTrabajoMisael
├── reportes/        📊 (estructura base lista)
│
├── frontend/                  ← TODO el frontend vive aquí
│   ├── css/
│   │   ├── variables.css      ← Variables de diseño (colores, fuentes, espaciado)
│   │   └── base.css           ← Componentes globales + validaciones CSS
│   ├── js/
│   │   ├── api.js             ← Cliente API + Auth JWT + UI helpers
│   │   └── components.js      ← Validar + CRUD + renderSidebar + initPanel
│   ├── login.html             ← Login compartido (detecta rol → redirige)
│   ├── pages/
│   │   ├── panel/
│   │   │   ├── dashboard.html      ← Stats + asistencia hoy + alertas
│   │   │   ├── asistencia.html     ← Grid de niños + marcar masivo + cobro auto
│   │   │   ├── ninos.html          ← CRUD + perfil lateral + autorizados
│   │   │   ├── tutores.html        ← CRUD + vincular a niños
│   │   │   ├── inscripciones.html  ← CRUD + cascada sala/turno + preview costos
│   │   │   ├── cobros.html         ← CRUD + registrar pago + generar mensualidades
│   │   │   ├── personal.html       ← CRUD + asignaciones sala/turno
│   │   │   ├── agenda.html         ← Calendario + planif. grupal + planes individuales
│   │   │   ├── salud.html          ← CRUD incidentes + detalle modal
│   │   │   ├── comunicacion.html   ← Avisos + mensajería + tabs
│   │   │   ├── inventario.html     ← Grid stock + movimientos + alertas
│   │   │   ├── evaluacion.html     ← Evaluaciones por niño + alertas rezago + catálogo
│   │   │   ├── misael-link.html    ← Derivaciones + planes trabajo Centro Misael
│   │   │   ├── sucursales.html     ← CRUD sucursales + salas + turnos
│   │   │   └── reportes.html       ← Gráficos CSS + exportar CSV
│   │   └── portal/
│   │       └── inicio.html         ← Portal padres: bitácora+asistencia+cobros+mensajes+desarrollo
│
├── scripts/
│   └── setup.sh
├── media/
├── static/
├── templates/
├── logs/
├── requirements.txt
├── manage.py
├── .env                       ← NO subir al repo
└── .env.example
```

---

## 📋 Páginas del panel interno

| Página | URL | Roles | Funcionalidades |
|---|---|---|---|
| Login | `/` | Todos | Tabs Personal/Padres, JWT, redirige por rol |
| Dashboard | `/panel/dashboard/` | Todos | Stats tiempo real, asistencia hoy, alertas |
| Asistencia | `/panel/asistencia/` | Todos | Grid por sala/turno, marcar masivo, cobro auto, CSV |
| Niños | `/panel/ninos/` | Todos | CRUD, perfil lateral, autorizados, paginación |
| Tutores | `/panel/tutores/` | Todos | CRUD, vincular a niños, portal de padres |
| Inscripciones | `/panel/inscripciones/` | Admin/Dir/Admin | CRUD, cascada sala/turno, descuentos/becas |
| Cobros | `/panel/cobros/` | Admin/Dir/Admin | CRUD, registrar pago, generar mensualidades masivas |
| Personal | `/panel/personal/` | Admin/Dir | CRUD, asignaciones sala/turno |
| Agenda | `/panel/agenda/` | Todos | Calendario, planif. grupal, planes individuales, objetivos |
| Salud | `/panel/salud/` | Todos | CRUD incidentes, detalle, notificación tutor |
| Comunicación | `/panel/comunicacion/` | Todos | Avisos masivos, mensajes individuales, tabs |
| Inventario | `/panel/inventario/` | Todos | Grid stock, movimientos, alertas automáticas |
| Evaluación | `/panel/evaluacion/` | Todos | Por niño, alertas rezago, catálogo hitos |
| Centro Misael | `/panel/misael-link/` | Todos | Derivaciones, planes trabajo, flujo visual |
| Sucursales | `/panel/sucursales/` | Admin/Dir | CRUD sucursales+salas+turnos |
| Reportes | `/panel/reportes/` | Admin/Dir/Admin | Gráficos CSS, 4 exportaciones CSV |

## 📱 Portal de padres

| Página | URL | Funcionalidades |
|---|---|---|
| Portal | `/portal/` | Bitácora, asistencia, cobros, mensajes, desarrollo, justificar ausencias |

---

## 🔑 Roles del sistema

| Rol | Acceso |
|---|---|
| `admin` | Todo el sistema |
| `directora` | Su sucursal completa + admin |
| `educadora` | Su sala, agenda, asistencia, comunicación |
| `ayudante` | Asistencia y agenda (lectura cobros) |
| `tutor` | Solo portal de padres — su hijo/a |
| `profesional` | Planes de trabajo (Centro Misael) |
| `administrativo` | Cobros, reportes |
| `cocina` | Solo inventario/menús |

---

## 🌐 API REST — Endpoints principales

| Módulo | Base URL | Endpoints destacados |
|---|---|---|
| Auth | `/api/auth/` | `POST /login/`, `POST /login/refresh/`, `GET /usuarios/yo/` |
| Core | `/api/core/` | Sucursales, Salas, Turnos |
| Personal | `/api/personal/` | Personal, Asignaciones, Asistencia personal |
| Niños | `/api/ninos/` | Niños, Tutores, Autorizados, Documentos |
| Inscripciones | `/api/inscripciones/` | Inscripciones, Cobros, `POST cobros/{id}/registrar-pago/` |
| Asistencia | `/api/asistencia/` | `GET asistencia/hoy/`, `GET asistencia/resumen-mensual/` |
| Agenda | `/api/agenda/` | Planificaciones, Planes individuales, Objetivos, Registros |
| Salud | `/api/salud/` | Incidentes de salud |
| Comunicación | `/api/comunicacion/` | Mensajes, Avisos, `POST mensajes/{id}/marcar-leido/` |
| Inventario | `/api/inventario/` | Items, Movimientos, `GET items/alertas-stock/` |
| Evaluación | `/api/evaluacion/` | Hitos, Evaluaciones, `GET evaluaciones/alertas-rezago/`, `GET hitos/por-edad/` |
| Misael Link | `/api/misael-link/` | Derivaciones, Planes de trabajo |
| Reportes | `/api/reportes/` | (estructura lista) |

---

## 🔧 Configuración importante en `config/settings/base.py`

```python
# JWT — tokens Bearer
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        ...
    ],
}

# Duración de tokens
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=8),   # Un turno completo
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
}

# Frontend integrado
TEMPLATES = [{'DIRS': [BASE_DIR / 'templates', BASE_DIR / 'frontend']}]
STATICFILES_DIRS = [BASE_DIR / 'static', BASE_DIR / 'frontend']
```

---

## 🔗 Conexión con Centro Misael

Ambos sistemas son apps Django **independientes** con su propia BD.
Configurar en `.env`:
```env
CENTRO_MISAEL_API_URL=http://localhost:8000/api/
CENTRO_MISAEL_API_KEY=clave-compartida-entre-sistemas
```

Flujo:
1. Educadora detecta señal → crea `Derivacion` con consentimiento del tutor
2. Profesional del centro crea `PlanTrabajoMisael` con objetivos
3. Se vincula a `PlanIndividual` en la app `agenda`
4. Educadora registra avances diarios → profesional los consulta

---

## 📦 Fase 2 (pendiente)

- 📷 Galería de fotos por actividad/sala
- 📝 Encuestas de satisfacción a padres
- 📱 App móvil (PWA o React Native)
- 🔔 Push notifications
- 🖨️ Reportes en PDF (con ReportLab, ya instalado)

---

*Misael Kids — La Paz, Bolivia · 2026*
