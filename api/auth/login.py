"""
Handler Vercel Serverless — POST /api/auth/login
Autentica o usuario com CSRF, Rate Limit distribuído, observabilidade e cookie seguro com Max-Age.
"""
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
from backend.auth import AuthService, CredenciaisInvalidasException, get_session_idle_seconds
from backend.csrf import get_csrf_protector
from backend.rate_limiter import get_rate_limiter
from backend.observabilidade import (
    finalizar_contexto_requisicao,
    formatar_server_timing,
    iniciar_contexto_requisicao,
    registrar_evento as obs_registrar_evento,
)

_auth_service = None


def _get_auth():
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


class handler(BaseHTTPRequestHandler):

    def _enviar_json(self, status: int, dados: dict, set_cookie: str = None, delete_cookie: str = None, extra_headers: dict = None):
        resumo = finalizar_contexto_requisicao(status)
        corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        origem = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")

        timing = formatar_server_timing(resumo)
        if timing:
            self.send_header("Server-Timing", timing)

        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, str(v))

        proto = (self.headers.get("X-Forwarded-Proto") or "").lower()
        is_https = proto == "https" or bool(os.environ.get("VERCEL"))
        secure_flag = "; Secure" if is_https else ""

        if set_cookie:
            cookie_base = set_cookie.split(";")[0].strip()
            max_age = get_session_idle_seconds()
            self.send_header("Set-Cookie", f"{cookie_base}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax{secure_flag}")
        if delete_cookie:
            self.send_header("Set-Cookie", f"{delete_cookie}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure_flag}")
        self.end_headers()
        self.wfile.write(corpo)

    def do_OPTIONS(self):
        self.send_response(204)
        origem = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        iniciar_contexto_requisicao("/api/auth/login", "POST")

        # Proteção CSRF/Origin consistente com backend/server.py
        csrf = get_csrf_protector()
        valido_csrf, motivo_csrf = csrf.validar_requisicao("POST", dict(self.headers), host_esperado=self.headers.get("Host", ""))
        if not valido_csrf:
            return self._enviar_json(403, {
                "sucesso": False,
                "mensagem": f"Requisição bloqueada por política de segurança de origem: {motivo_csrf}",
                "codigo": "ORIGEM_PROIBIDA",
            })

        ip_origem = (self.headers.get("X-Forwarded-For") or "127.0.0.1").split(",")[0].strip()
        limiter = get_rate_limiter()
        chave_limiter = f"ip:{ip_origem}"

        bloqueado, restante = limiter.esta_bloqueado(chave_limiter)
        if bloqueado:
            obs_registrar_evento("auth_rate_limit")
            try:
                _get_auth().audit_service.registrar_evento(
                    "BLOQUEIO_RATE_LIMIT",
                    identificador="anônimo",
                    ip_origem=ip_origem,
                    detalhes=f"Bloqueio de taxa ativo ({restante}s restantes)",
                )
            except Exception:
                pass
            return self._enviar_json(429, {
                "sucesso": False,
                "mensagem": "Excesso de tentativas de login. Tente novamente mais tarde.",
                "codigo": "RATE_LIMIT_EXCEDIDO",
            }, extra_headers={"Retry-After": str(restante)})

        try:
            cl = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(cl).decode("utf-8") if cl > 0 else "{}"
            dados = json.loads(raw) if raw.strip() else {}
        except Exception:
            return self._enviar_json(400, {"sucesso": False, "mensagem": "JSON inválido."})

        identificador = (dados.get("identificador") or "").strip()
        senha = dados.get("senha") or ""

        if not identificador or not senha:
            return self._enviar_json(400, {
                "sucesso": False,
                "mensagem": "Preencha o identificador (e-mail ou usuário) e a senha."
            })

        try:
            usuario, token = _get_auth().autenticar(identificador, senha, ip_origem=ip_origem)
            limiter.registrar_sucesso(chave_limiter)

            auth_mode = self.headers.get("X-Auth-Mode", "").lower()
            cookie_only = auth_mode == "cookie" or dados.get("cookie_only", False)
            resp_dados = {
                "sucesso": True,
                "mensagem": "Autenticação realizada com sucesso.",
                "usuario": usuario,
            }
            if not cookie_only:
                resp_dados["token"] = token

            return self._enviar_json(200, resp_dados, set_cookie=f"session_token={token}")
        except CredenciaisInvalidasException as e:
            limiter.registrar_falha(chave_limiter, ip_origem=ip_origem)
            return self._enviar_json(401, {"sucesso": False, "mensagem": str(e)})
        except Exception as e:
            return self._enviar_json(*erro_http(e))
