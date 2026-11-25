"""
Handler Vercel Serverless — GET /api/auth/me
Valida o token de sessao, aplica renovacao deslizante controlada e atualiza cookie se renovada.
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

from backend.database import erro_http
from backend.auth import AuthService, PERMISSOES_RBAC, get_session_idle_seconds
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

    def _enviar_json(self, status: int, dados: dict, set_cookie: str = None):
        resumo = finalizar_contexto_requisicao(status)
        corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        origem = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")

        timing = formatar_server_timing(resumo)
        if timing:
            self.send_header("Server-Timing", timing)

        if set_cookie:
            proto = (self.headers.get("X-Forwarded-Proto") or "").lower()
            is_https = proto == "https" or bool(os.environ.get("VERCEL"))
            secure_flag = "; Secure" if is_https else ""
            cookie_base = set_cookie.split(";")[0].strip()
            max_age = get_session_idle_seconds()
            self.send_header("Set-Cookie", f"{cookie_base}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax{secure_flag}")

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
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        iniciar_contexto_requisicao("/api/auth/me", "GET")
        token = self._extrair_token()
        if not token:
            return self._enviar_json(401, {
                "sucesso": False,
                "mensagem": "Não autenticado.",
                "codigo": "NAO_AUTENTICADO"
            })
        try:
            usuario = _get_auth().validar_sessao(token, renovar=True)
        except Exception as e:
            return self._enviar_json(*erro_http(e))

        if not usuario:
            return self._enviar_json(401, {
                "sucesso": False,
                "mensagem": "Sessão inválida ou expirada.",
                "codigo": "NAO_AUTENTICADO"
            })

        renovada = bool(usuario.pop("_sessao_renovada", False))
        perfil = usuario.get("perfil", "colaborador")
        permissoes = PERMISSOES_RBAC.get(perfil, [])
        cookie_refresh = f"session_token={token}" if renovada else None

        return self._enviar_json(200, {
            "sucesso": True,
            "sessao_renovada": renovada,
            "usuario": {
                **usuario,
                "permissoes": permissoes,
            }
        }, set_cookie=cookie_refresh)
