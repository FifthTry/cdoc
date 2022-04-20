release: python manage.py migrate
web: gunicorn cdoc.wsgi
worker: python manage.py rqworker default