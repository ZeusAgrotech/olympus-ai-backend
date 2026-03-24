"""
WSGI entrypoint for production (e.g. gunicorn on Cloud Run).
"""

from dotenv import load_dotenv

load_dotenv()

from server.server import Server

import agents  # noqa: F401  # Triggers agent auto-registration

server = Server.get_instance()
app = server.app
