"""
Flask Agents Server

Exposes agent tools via HTTP/REST endpoints.
"""

import os

from dotenv import load_dotenv

load_dotenv()

from server.server import Server

import agents  # Import triggers agent auto-registration


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "6001"))
    environment = os.environ.get("ENVIRONMENT", "development")
    debug = environment != "production"
    server = Server.get_instance()
    server.start(host="0.0.0.0", port=port, debug=debug)
