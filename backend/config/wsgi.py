"""
WSGI · servido por Gunicorn en el contenedor `backend`.

Este contenedor atiende exclusivamente HTTP. Los WebSockets NO pasan por aquí.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
