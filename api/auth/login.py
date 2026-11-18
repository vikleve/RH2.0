"""
Handler Vercel Serverless — /api/auth/login
Encaminha para ApiColaboradorHandler unificado, garantindo Rate Limiter, CSRF,
segurança de cookies HttpOnly e compatibilidade Neon PostgreSQL.
"""
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.server import ApiColaboradorHandler


class handler(ApiColaboradorHandler):
    pass
