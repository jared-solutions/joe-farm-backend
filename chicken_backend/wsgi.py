"""
WSGI config for chicken_backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
import sys

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chicken_backend.settings')

# Run migrations automatically on startup (for Render free tier)
if os.environ.get('RUN_MIGRATIONS', 'True').lower() in ('true', '1', 'yes'):
    from django.core.management import execute_from_command_line
    # Only run migrate, not makemigrations (migrations should be committed)
    try:
        print("Running database migrations...")
        execute_from_command_line(['manage.py', 'migrate', '--noinput'])
        print("Migrations completed successfully!")
    except Exception as e:
        print(f"Migration warning: {e}")

application = get_wsgi_application()
