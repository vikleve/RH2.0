"""
Handler Vercel Serverless — POST /api/auth/logout
Encerra a sessao do usuario autenticado e limpa o cookie com atributos consistentes.
"""
import http.cookies
import json
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

from http.server import BaseHTTPRequestHandler

from backend.auth import AuthService
from backend.observabilidade import (
    finalizar_contexto_requisicao,
    formatar_server_timing,
    iniciar_contexto_requisicao,
)

_auth_service = None


def _get_auth():
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


class handler(BaseHTTPRequestHandler):

    def _enviar_json(self, status: int, dados: dict, delete_cookie: str = None):
        resumo = finalizar_contexto_requisicao(status)
        corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        origem = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")

        timing = formatar_server_timing(resumo)
        if timing:
            self.send_header("Server-Timing", timing)

        if delete_cookie:
            proto = (self.headers.get("X-Forwarded-Proto") or "").lower()
            is_https = proto == "https" or bool(os.environ.get("VERCEL"))
            secure_flag = "; Secure" if is_https else ""
            self.send_header("Set-Cookie", f"{delete_cookie}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure_flag}")
        self.end_headers()
        self.wfile.write(corpo)

    def _extrair_token(self) -> str:
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            t = auth_header[7:].strip()
            if t:
                return t
        cookie_header = self.headers.get("Cookie", "")
        if cookie_header:
            try:
                cookies = http.cookies.SimpleCookie()
                cookies.load(cookie_header)
                if "session_token" in cookies:
                    return cookies["session_token"].value
            except Exception:
                pass
        return None

    def do_OPTIONS(self):
        self.send_response(204)
        origem = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        iniciar_contexto_requisicao("/api/auth/logout", "POST")
        token = self._extrair_token()
        if token:
            try:
                ip_origem = (self.headers.get("X-Forwarded-For") or "127.0.0.1").split(",")[0].strip()
                _get_auth().encerrar_sessao(token, ip_origem=ip_origem)
            except Exception:
                pass
        self._enviar_json(200, {
            "sucesso": True,
            "mensagem": "Sessão encerrada com sucesso."
        }, delete_cookie="session_token")
