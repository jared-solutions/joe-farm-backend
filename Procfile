release: python manage.py migrate
web: gunicorn chicken_backend.wsgi:application --workers 4 --threads 8 --timeout 120
