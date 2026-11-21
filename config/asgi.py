"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

import socketio
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')


def create_application():
    django_application = get_asgi_application()
    from qlmvt.realtime import socketio_server

    return socketio.ASGIApp(
        socketio_server,
        other_asgi_app=django_application,
    )


application = create_application()
