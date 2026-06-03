"""WSGI entrypoint для продакшн-серверов (gunicorn, uwsgi).

Использование:
    gunicorn wsgi:app
"""
from app import create_app

app = create_app()
