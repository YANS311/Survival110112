"""
core/asgi.py
============
Production-ready ASGI configuration for Beijing Postgraduate Simulator V2.0.

Deployment
----------
Start the server with Uvicorn (no more `runserver` loops):

    # Development (auto-reload):
    uvicorn core.asgi:application --host 127.0.0.1 --port 8000 --reload

    # Production (multi-worker, RTX 4080 host):
    uvicorn core.asgi:application --host 0.0.0.0 --port 8000 --workers 2 --loop uvloop

    # Or via the convenience script:
    python start_server.py

Notes
-----
- Django's get_asgi_application() returns a fully async ASGI app.
- django-ninja endpoints are natively async and handled by the same app.
- Static files in production should be served by Nginx / WhiteNoise, not Django.
"""

import os
import sys
import logging

# ── Ensure project root is on sys.path ───────────────────────────────────────
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── Django settings ───────────────────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# ── ASGI application ──────────────────────────────────────────────────────────
from django.core.asgi import get_asgi_application

# Trigger Django setup (loads models, middleware, etc.)
django_asgi_app = get_asgi_application()

logger = logging.getLogger(__name__)
logger.info(
    "ASGI application initialised. "
    "Deploy with: uvicorn core.asgi:application --host 0.0.0.0 --port 8000"
)

# The ASGI callable — Uvicorn will call this.
application = django_asgi_app
