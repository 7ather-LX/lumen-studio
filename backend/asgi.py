"""ASGI entry point used by the desktop sidecar."""

from backend.main import create_app

app = create_app()
