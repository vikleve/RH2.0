"""
Handler Vercel Serverless — /api/auth/logout
Encaminha para ApiColaboradorHandler unificado, garantindo encerramento
auditado da sessão e destruição segura de cookie HttpOnly.
"""
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.server import ApiColaboradorHandler


class handler(ApiColaboradorHandler):
    pass
