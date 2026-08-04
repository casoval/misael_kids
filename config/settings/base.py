"""
Misael Kids — Configuración base
Compartida por development y production
"""
import os
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = env('DJANGO_DEBUG')
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost'])

# ─── Apps instaladas ──────────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

# Cloudinary va después de staticfiles (mismo orden que usa Centro Misael,
# para que las fotos de niños/personal se guarden en la misma cuenta).
CLOUDINARY_APPS = [
    'cloudinary_storage',
    'cloudinary',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'django_filters',
    'corsheaders',
]

LOCAL_APPS = [
    'accounts',       # Usuarios, roles y permisos
    'core',           # Sucursales, Salas, Turnos
    'personal',       # Educadoras, asignaciones, RRHH
    'ninos',          # Niños, tutores, documentos
    'inscripciones',  # Inscripciones y cobros
    'asistencia',     # Asistencia diaria y autorizados
    'agenda',         # Planificación grupal e individual
    'salud',          # Incidentes y medicamentos
    'comunicacion',   # Mensajes y avisos
    'inventario',     # Stock por sucursal
    'evaluacion',     # Hitos y evaluación del desarrollo
    'misael_link',    # Conexión con Centro Misael
    'reportes',       # Reportes y exportaciones
]

INSTALLED_APPS = DJANGO_APPS + CLOUDINARY_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ───────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', BASE_DIR / 'frontend'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ─── Base de datos ────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='5432'),
        'OPTIONS': {
            'options': '-c search_path=misael_kids',
        },
    }
}

# ─── Modelo de usuario personalizado ─────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.Usuario'

# Permite loguearse (incluido el /admin/ de Django) con email O con
# nombre de usuario indistintamente. Se mantiene también el ModelBackend
# estándar como respaldo.
AUTHENTICATION_BACKENDS = [
    'accounts.backends.EmailOUsernameBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# ─── Internacionalización ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-bo'
TIME_ZONE = 'America/La_Paz'
USE_I18N = True
USE_TZ = True

# ─── Cloudinary (fotos de niños/personal — misma cuenta que Centro Misael) ────
# Mismos 3 nombres de variable que usa Centro Misael, para poder usar
# exactamente las mismas credenciales/cuenta.
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': env('CLOUDINARY_CLOUD_NAME', default=''),
    'API_KEY':    env('CLOUDINARY_API_KEY', default=''),
    'API_SECRET': env('CLOUDINARY_API_SECRET', default=''),
}
CLOUDINARY_CONFIGURADO = bool(
    CLOUDINARY_STORAGE['CLOUD_NAME'] and CLOUDINARY_STORAGE['API_KEY'] and CLOUDINARY_STORAGE['API_SECRET']
)

# ─── Archivos estáticos y media ───────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
    BASE_DIR / 'frontend',   # Archivos estáticos del frontend (CSS, JS, HTML)
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if CLOUDINARY_CONFIGURADO:
    # A diferencia de Centro Misael (que activa Cloudinary solo si
    # IS_PRODUCTION), acá lo activamos según si las credenciales están
    # presentes, en cualquier entorno: así un desarrollador puede probarlo
    # en local con las mismas credenciales, y si en producción alguien
    # olvida configurar las variables, el sitio sigue funcionando con
    # disco local en vez de romperse.
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── Django REST Framework ────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # JWT Bearer token
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S',
    'DATE_FORMAT': '%Y-%m-%d',
}


# ─── JWT ─────────────────────────────────────────────────────────────────────
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# ─── CORS ────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'http://localhost:3000',
    'http://localhost:5173',
])

# ─── Email ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = 'Misael Kids <no-reply@misaelkids.com>'

# ─── Conexión Centro Misael ───────────────────────────────────────────────────
CENTRO_MISAEL_API_URL = env('CENTRO_MISAEL_API_URL', default='')
CENTRO_MISAEL_API_KEY = env('CENTRO_MISAEL_API_KEY', default='')

# ─── Logging ─────────────────────────────────────────────────────────────────
# La carpeta logs/ no siempre viene en el repo (está en .gitignore vía *.log).
# La creamos automáticamente para que el proyecto nunca falle al arrancar por esto.
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'misael_kids.log',
            'formatter': 'verbose',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}

# ─── Páginas adicionales del frontend ────────────────────────────────────────
# (Agregadas en integración Opción A)
