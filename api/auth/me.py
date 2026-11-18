"""
Handler Vercel Serverless — /api/auth/me
Encaminha para ApiColaboradorHandler unificado, garantindo verificação
de sessão e retorno de dados do usuário autenticado.
"""
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.server import ApiColaboradorHandler


class handler(ApiColaboradorHandler):
    pass
