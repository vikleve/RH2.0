"""
Handler Vercel Serverless — /api/colaboradores (e subrecursos)
Encaminha para ApiColaboradorHandler unificado, garantindo autenticação,
validação de regras de negócio, auditoria e isolamento multiempresa.
"""
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.server import ApiColaboradorHandler


class handler(ApiColaboradorHandler):
    pass
