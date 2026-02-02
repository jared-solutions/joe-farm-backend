"""
WSGI config for chicken_backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
import sys
import django

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chicken_backend.settings')

# Run migrations and collectstatic automatically on startup (for Render free tier)
if os.environ.get('RUN_MIGRATIONS', 'True').lower() in ('true', '1', 'yes'):
    from django.core.management import execute_from_command_line
    from django.db import connection
    
    # Delete old database if it exists and has incompatible schema
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db.sqlite3')
    if os.path.exists(db_path):
        try:
            # Test if the database has the required columns
            cursor = connection.cursor()
            cursor.execute("SELECT is_approved FROM authentication_user LIMIT 1")
        except Exception as e:
            print(f"Database schema incompatible: {e}")
            print("Deleting old database file...")
            try:
                os.remove(db_path)
                print("Old database deleted successfully!")
            except Exception as delete_error:
                print(f"Could not delete database: {delete_error}")
    
    # Run migrate
    try:
        print("Running database migrations...")
        execute_from_command_line(['manage.py', 'migrate', '--noinput'])
        print("Migrations completed successfully!")
    except Exception as e:
        print(f"Migration warning: {e}")
    
    # Collect static files
    try:
        print("Collecting static files...")
        execute_from_command_line(['manage.py', 'collectstatic', '--noinput'])
        print("Static files collected successfully!")
    except Exception as e:
        print(f"Static files warning: {e}")

application = get_wsgi_application()
