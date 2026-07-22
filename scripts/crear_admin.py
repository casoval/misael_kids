"""
scripts/crear_admin.py
Crea el superusuario administrador inicial sin interacción.
Uso: python manage.py shell < scripts/crear_admin.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from accounts.models import Usuario

if not Usuario.objects.filter(email='admin@misaelkids.com').exists():
    u = Usuario.objects.create_superuser(
        email='admin@misaelkids.com',
        password='Admin1234!',
        nombres='Administrador',
        apellidos='Misael Kids',
        rol=Usuario.ROL_ADMIN,
    )
    print(f'✅ Superusuario creado: {u.email}')
else:
    print('ℹ️  El superusuario ya existe.')
