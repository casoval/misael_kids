#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# setup.sh — Configuración inicial de Misael Kids
# Ejecutar una sola vez al clonar el proyecto
# ─────────────────────────────────────────────────────────────────
set -e

echo ""
echo "🌟 Misael Kids — Configuración inicial"
echo "─────────────────────────────────────────────────────────────"

# 1. Entorno virtual
echo "📦 Creando entorno virtual..."
python3 -m venv venv
source venv/bin/activate

# 2. Dependencias
echo "📦 Instalando dependencias..."
pip install -r requirements.txt

# 3. Variables de entorno
if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  Archivo .env creado. Edítalo con tus datos antes de continuar."
  echo "   nano .env"
  exit 1
fi

# 4. Crear base de datos PostgreSQL
echo "🗄️  Creando base de datos..."
DB_NAME=$(grep DB_NAME .env | cut -d '=' -f2)
DB_USER=$(grep DB_USER .env | cut -d '=' -f2)
psql -U postgres -c "CREATE DATABASE ${DB_NAME};" 2>/dev/null || echo "   (Base de datos ya existe)"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" 2>/dev/null || true

# 5. Migraciones
echo "🔄 Aplicando migraciones..."
python manage.py migrate

# 6. Datos iniciales
echo "📥 Cargando datos iniciales..."
python manage.py loaddata core/fixtures/datos_iniciales.json
python manage.py loaddata evaluacion/fixtures/hitos_desarrollo.json

# 7. Superusuario
echo ""
echo "👤 Creando superusuario administrador..."
python manage.py createsuperuser --email admin@misaelkids.com

echo ""
echo "✅ ¡Instalación completada!"
echo "─────────────────────────────────────────────────────────────"
echo "   Iniciar servidor:  python manage.py runserver"
echo "   Panel admin:       http://localhost:8000/admin/"
echo "─────────────────────────────────────────────────────────────"
