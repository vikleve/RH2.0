"""
Servidor HTTP REST e Servidor de Arquivos Estáticos — Backend RH/DP
Atende aos requisitos de autenticação real (RF-40, RF-41, RF-43, RNF-01 a RNF-03),
persistência durável e controle de acesso a endpoints protegidos.
Executa de forma autônoma (localmente) e como Handler Serverless (Vercel).
"""
from datetime import datetime, timedelta
import http.cookies
import http.server
import json
import os
import socketserver
from typing import Any, Optional
import urllib.parse
from decimal import Decimal

# Carrega variaveis de ambiente do arquivo .env (se existir)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv nao instalado; variaveis devem ser definidas manualmente
try:
    from .auth import AuthService, CredenciaisInvalidasException, get_session_idle_seconds
    from .csrf import get_csrf_protector
    from .rate_limiter import get_rate_limiter
    from .observabilidade import (
        finalizar_contexto_requisicao,
        formatar_server_timing,
        iniciar_contexto_requisicao,
        obter_metricas_snapshot,
        registrar_evento as obs_registrar_evento,
    )
    from .folha_service import (
        FolhaBloqueadaException,
        FolhaNaoEncontradaException,
        FolhaService,
        FolhaValidacaoException,
    )
    from .service import ColaboradorService, RecursoNaoEncontradoException, ValidacaoException
    from .plataforma_service import (
        PlataformaService,
        PlataformaValidacaoException,
        PlataformaAcessoNegadoException,
        PlataformaRecursoNaoEncontradoException,
    )
    from .database import erro_http, status_banco
except ImportError:
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from backend.auth import AuthService, CredenciaisInvalidasException, get_session_idle_seconds
    from backend.csrf import get_csrf_protector
    from backend.rate_limiter import get_rate_limiter
    from backend.observabilidade import (
        finalizar_contexto_requisicao,
        formatar_server_timing,
        iniciar_contexto_requisicao,
        obter_metricas_snapshot,
        registrar_evento as obs_registrar_evento,
    )
    from backend.folha_service import (
        FolhaBloqueadaException,
        FolhaNaoEncontradaException,
        FolhaService,
        FolhaValidacaoException,
    )
    from backend.service import ColaboradorService, RecursoNaoEncontradoException, ValidacaoException
    from backend.plataforma_service import (
        PlataformaService,
        PlataformaValidacaoException,
        PlataformaAcessoNegadoException,
        PlataformaRecursoNaoEncontradoException,
    )
    from backend.database import erro_http, status_banco

PORT = 8000
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

_global_colab_service = None
_global_auth_service = None
_global_folha_service = None
_global_plataforma_service = None

class ApiColaboradorHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self._local_colab_service = None
        self._local_auth_service = None
        self._local_folha_service = None
        self._local_plataforma_service = None
        # Em ambientes serverless (Vercel), FRONTEND_DIR pode não existir no mesmo diretório local
        dir_to_serve = FRONTEND_DIR if os.path.exists(FRONTEND_DIR) else os.getcwd()
        super().__init__(*args, directory=dir_to_serve, **kwargs)

    @property
    def service(self) -> ColaboradorService:
        """Garante acesso ao ColaboradorService tanto em TCPServer quanto em Serverless Functions."""
        if hasattr(self, "server") and self.server is not None:
            if not hasattr(self.server, "colab_service"):
                setattr(self.server, "colab_service", ColaboradorService(auto_init=False))
            return getattr(self.server, "colab_service")

        if getattr(self, "_local_colab_service", None) is None:
            global _global_colab_service
            if _global_colab_service is None:
                _global_colab_service = ColaboradorService(auto_init=False)
            self._local_colab_service = _global_colab_service
        return self._local_colab_service

    @property
    def auth_service(self) -> AuthService:
        """Garante acesso ao AuthService tanto em TCPServer quanto em Serverless Functions."""
        if hasattr(self, "server") and self.server is not None:
            if not hasattr(self.server, "auth_service"):
                db_path = getattr(self.service, "db_path", None)
                setattr(self.server, "auth_service", AuthService(db_path=db_path, auto_init=False))
            return getattr(self.server, "auth_service")

        if getattr(self, "_local_auth_service", None) is None:
            global _global_auth_service
            if _global_auth_service is None:
                db_path = getattr(self.service, "db_path", None)
                _global_auth_service = AuthService(db_path=db_path, auto_init=False)
            self._local_auth_service = _global_auth_service
        return self._local_auth_service

    @property
    def folha_service(self) -> FolhaService:
        """Garante acesso ao FolhaService tanto em TCPServer quanto em Serverless Functions."""
        if hasattr(self, "server") and self.server is not None:
            if not hasattr(self.server, "folha_service"):
                db_path = getattr(self.service, "db_path", None)
                setattr(self.server, "folha_service", FolhaService(db_path=db_path, auto_init=False))
            return getattr(self.server, "folha_service")

        if getattr(self, "_local_folha_service", None) is None:
            global _global_folha_service
            if _global_folha_service is None:
                db_path = getattr(self.service, "db_path", None)
                _global_folha_service = FolhaService(db_path=db_path, auto_init=False)
            self._local_folha_service = _global_folha_service
        return self._local_folha_service

    @property
    def plataforma_service(self) -> PlataformaService:
        """Garante acesso ao PlataformaService para gestão do ciclo trabalhista."""
        if hasattr(self, "server") and self.server is not None:
            if not hasattr(self.server, "plataforma_service"):
                db_path = getattr(self.service, "db_path", None)
                setattr(self.server, "plataforma_service", PlataformaService(db_path=db_path))
            return getattr(self.server, "plataforma_service")

        if getattr(self, "_local_plataforma_service", None) is None:
            global _global_plataforma_service
            if _global_plataforma_service is None:
                db_path = getattr(self.service, "db_path", None)
                _global_plataforma_service = PlataformaService(db_path=db_path)
            self._local_plataforma_service = _global_plataforma_service
        return self._local_plataforma_service

    def _validar_escopo_empresa(self, usuario: dict, empresa_alvo: str = None) -> Optional[str]:
        """
        Valida isolamento multi-tenant por empresa (RT-12, RF-165, RF-166).
        Retorna o empresa_id validado ou None se superadmin/administrador sem restrição.
        Se usuário tentar acessar empresa não autorizada, envia 403 e retorna None.
        """
        if not usuario:
            return None
        perfil = usuario.get("perfil", "user")
        empresa_usuario = usuario.get("empresa_id")

        if perfil in ("superadmin", "administrador"):
            return str(empresa_alvo).strip() if empresa_alvo else None

        # Usuário regular só pode acessar sua própria empresa
        if not empresa_usuario:
            return None

        if empresa_alvo and str(empresa_alvo).strip() != str(empresa_usuario).strip():
            self._enviar_json(403, {
                "sucesso": False,
                "mensagem": "Acesso negado. Tentativa de acesso a dados de outra empresa (RT-12).",
                "codigo": "ACESSO_NEGADO_EMPRESA"
            })
            return None

        return str(empresa_usuario).strip()

    def _resolver_empresa_escopo(self, usuario: dict, empresa_alvo: str = None) -> tuple[bool, Optional[str]]:
        """Resolve escopo multi-tenant com segurança sem deixar requisição sem resposta HTTP."""
        empresa_valida = self._validar_escopo_empresa(usuario, empresa_alvo)
        if empresa_alvo and empresa_valida is None and usuario.get("perfil") not in ("superadmin", "administrador") and usuario.get("empresa_id"):
            return False, None
        return True, empresa_valida

    def _exigir_permissao(self, usuario: dict, permissao: str) -> bool:
        """Aplica checagem estrita de RBAC para operações sensíveis (HTTP 403)."""
        from .auth import checar_permissao
        if not checar_permissao(usuario.get("perfil", ""), permissao):
            self._enviar_json(403, {
                "sucesso": False,
                "mensagem": f"Acesso negado por RBAC: permissão '{permissao}' requerida.",
                "codigo": "RBAC_ACESSO_NEGADO",
            })
            return False
        return True

    def _enviar_binario(self, conteudo_bytes: bytes, mime: str, nome_arquivo: str, inline: bool = False):
        nome_safe = str(nome_arquivo or "documento").replace('"', "_")
        disp = "inline" if inline else "attachment"
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(conteudo_bytes)))
        self.send_header("Content-Disposition", f'{disp}; filename="{nome_safe}"')
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(conteudo_bytes)

    def _obter_caminho_e_query(self) -> tuple[str, dict]:
        """
        Extrai o caminho da requisição e os parâmetros de query.
        Suporta ambientes com proxy/rewrites (como Vercel) inspecionando cabeçalhos de rota original.
        """
        raw_uri = (
            self.headers.get("x-forwarded-uri") or
            self.headers.get("x-matched-path") or
            self.headers.get("x-invoke-path") or
            self.path
        )
        parsed = urllib.parse.urlparse(raw_uri)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Se houver parâmetro path na query (injetado por rewrite vercel: ?path=auth/login)
        if "path" in query:
            subpath = query["path"][0]
            path = f"/api/{subpath}" if not subpath.startswith("/") else subpath

        # 2. Remove sufixo .py caso o script seja invocado diretamente pela Vercel (ex: /api/auth/login.py)
        if path.endswith(".py"):
            path = path[:-3]

        # 3. Caso ainda seja /api/index ou /api, verificar route-matches legados
        if path in ("/api/index", "/api"):
            route_matches = self.headers.get("x-now-route-matches", "")
            if "1=" in route_matches:
                subroute = route_matches.split("1=")[-1].split("&")[0]
                path = f"/api/{subroute}"

        return path, query

    def _extrair_token_sessao(self) -> str | None:
        """Extrai o token de autenticação a partir do header Authorization ou Cookie de sessão."""
        # 1. Authorization: Bearer <token>
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token:
                return token

        # 2. Cookie: session_token=<token>
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

    def _obter_usuario_autenticado(self) -> dict | None:
        """Retorna os dados do usuário autenticado a partir do token de sessão."""
        token = self._extrair_token_sessao()
        if not token:
            return None
        return self.auth_service.validar_sessao(token)

    def _exigir_autenticacao(self) -> dict | None:
        """
        Verifica se a requisição possui autenticação válida.
        Falhas transitórias de banco retornam HTTP 503 (nunca 401 falso!).
        Caso a sessão seja inválida/expirada, envia HTTP 401 Unauthorized e retorna None.
        """
        try:
            usuario = self._obter_usuario_autenticado()
        except Exception as e:
            self._enviar_json(*erro_http(e))
            return None
        if not usuario:
            self._enviar_json(401, {
                "sucesso": False,
                "mensagem": "Acesso não autorizado. É necessário efetuar login para acessar este recurso.",
                "codigo": "NAO_AUTENTICADO"
            })
            return None
        return usuario

    def _obter_ip_cliente(self) -> str:
        """Extrai o IP do cliente considerando proxies confiáveis ou socket local."""
        xff = self.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        if hasattr(self, "client_address") and self.client_address:
            return str(self.client_address[0])
        return "127.0.0.1"

    def _validar_csrf(self, metodo: str) -> bool:
        """Valida proteção CSRF/Origin em métodos mutáveis (RF-LOGIN-005, AC-13)."""
        csrf = get_csrf_protector()
        host = self.headers.get("Host", "")
        valido, motivo = csrf.validar_requisicao(metodo, dict(self.headers), host_esperado=host)
        if not valido:
            self._enviar_json(403, {
                "sucesso": False,
                "mensagem": f"Requisição bloqueada por política de segurança de origem: {motivo}",
                "codigo": "ORIGEM_PROIBIDA"
            })
            return False
        return True

    def _enviar_json(self, status_code: int, dados: dict | list, set_cookie: str = None, delete_cookie: str = None, extra_headers: dict = None):
        """Envia resposta JSON compacta com cabeçalhos de segurança, cookies com Max-Age/Secure consistentes e Server-Timing."""
        def _json_serial(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            return str(obj)

        resumo_perf = finalizar_contexto_requisicao(status_code)
        corpo = json.dumps(dados, ensure_ascii=False, separators=(",", ":"), default=_json_serial).encode("utf-8")
        self.send_response(status_code)
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

        timing = formatar_server_timing(resumo_perf)
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
        """Suporte a pre-flight CORS com credenciais."""
        self.send_response(204)
        origem = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origem)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _ler_json_body(self) -> dict:
        """Lê e desserializa o corpo da requisição JSON."""
        cl = self.headers.get("Content-Length") or self.headers.get("content-length") or 0
        content_length = int(cl)
        if content_length == 0:
            self._body_lido = True
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        self._body_lido = True
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Corpo da requisição não é um JSON válido.")

    def do_GET(self):
        """Trata requisições GET para API e para arquivos estáticos."""
        path, query = self._obter_caminho_e_query()
        if path.startswith("/api/"):
            iniciar_contexto_requisicao(path, "GET")

        # Diagnostico publico: GET /api/health — confirma o banco em uso (sem expor credenciais)
        if path == "/api/health":
            try:
                return self._enviar_json(200, {"sucesso": True, **status_banco()})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Diagnostico protegido: GET /api/observabilidade/metricas
        if path == "/api/observabilidade/metricas":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            if usuario.get("perfil") not in ("superadmin", "administrador", "admin_empresa", "auditor"):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Acesso restrito a administradores/auditores.", "codigo": "ACESSO_NEGADO"})
            return self._enviar_json(200, {"sucesso": True, "metricas": obter_metricas_snapshot()})

        # Rota de verificação de sessão: GET /api/auth/me
        if path == "/api/auth/me":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            renovada = bool(usuario.pop("_sessao_renovada", False))
            perfil = usuario.get("perfil", "colaborador")
            from .auth import PERMISSOES_RBAC
            permissoes = PERMISSOES_RBAC.get(perfil, [])
            token_atual = self._extrair_token_sessao()
            cookie_refresh = f"session_token={token_atual}" if (renovada and token_atual) else None
            return self._enviar_json(200, {
                "sucesso": True,
                "sessao_renovada": renovada,
                "usuario": {
                    **usuario,
                    "permissoes": permissoes
                }
            }, set_cookie=cookie_refresh)

        # Rota de metadados: Listar perfis RBAC da plataforma GET /api/auth/perfis
        if path == "/api/auth/perfis":
            from .auth import PERFIS_ENTERPRISE
            return self._enviar_json(200, {
                "sucesso": True,
                "perfis": PERFIS_ENTERPRISE
            })

        # Rota protegida: Listar colaboradores GET /api/colaboradores
        if path == "/api/colaboradores":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            empresa_valida = self._validar_escopo_empresa(usuario, empresa_alvo)
            if empresa_valida is None and usuario.get("perfil") not in ("superadmin", "administrador"):
                return
            termo = (query.get("q") or query.get("search") or [None])[0]
            situacao = query.get("situacao", [None])[0]
            setor = (query.get("setor") or query.get("departamentoId") or [None])[0]
            cargo = (query.get("cargo") or query.get("cargoId") or [None])[0]
            nome = query.get("nome", [None])[0]
            matricula = query.get("matricula", [None])[0]
            cpf = query.get("cpf", [None])[0]
            colabs = self.service.listar(
                termo=termo,
                situacao=situacao,
                setor=setor,
                cargo=cargo,
                nome=nome,
                matricula=matricula,
                cpf=cpf,
                empresa_id=empresa_valida,
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(colabs), "dados": colabs})

        # Rota protegida: Próxima matrícula automática GET /api/colaboradores/proxima-matricula
        if path == "/api/colaboradores/proxima-matricula":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            return self._enviar_json(200, {
                "sucesso": True,
                "matricula": self.service.gerar_proxima_matricula()
            })

        # Rota protegida: Colaborador e submódulos RF-005 a RF-010 GET /api/colaboradores/<id>[/...]
        if path.startswith("/api/colaboradores/"):
            partes = path.strip("/").split("/")
            if len(partes) >= 3 and partes[2].isdigit():
                usuario = self._exigir_autenticacao()
                if not usuario:
                    return
                colab_id = int(partes[2])
                empresa_alvo = (query.get("empresa_id") or [None])[0]
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, empresa_alvo)
                if not ok_escopo:
                    return

                if len(partes) == 3:
                    try:
                        colab = self.service.obter_por_id(colab_id, empresa_id=empresa_valida)
                        return self._enviar_json(200, {"sucesso": True, "dados": colab})
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

                if len(partes) == 4 and partes[3] == "historico":
                    try:
                        historico = self.service.obter_historico(colab_id)
                        return self._enviar_json(200, {"sucesso": True, "total": len(historico), "dados": historico})
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

                if len(partes) == 4 and partes[3] == "dependentes":
                    try:
                        incluir_inativos = query.get("incluir_inativos", ["0"])[0] in ("1", "true", "sim")
                        deps = self.service.listar_dependentes(colab_id, incluir_inativos=incluir_inativos, empresa_id=empresa_valida)
                        return self._enviar_json(200, {"sucesso": True, "total": len(deps), "dados": deps})
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

                if len(partes) == 4 and partes[3] == "historico-funcional":
                    try:
                        tipo_mov = query.get("tipo", [None])[0] or query.get("tipo_movimentacao", [None])[0]
                        dt_ini = query.get("data_inicio", [None])[0]
                        dt_fim = query.get("data_fim", [None])[0]
                        movs = self.service.listar_historico_funcional(
                            colab_id, tipo_movimentacao=tipo_mov, data_inicio=dt_ini, data_fim=dt_fim, empresa_id=empresa_valida
                        )
                        return self._enviar_json(200, {"sucesso": True, "total": len(movs), "dados": movs})
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

                if len(partes) == 4 and partes[3] == "documentos":
                    try:
                        cat = query.get("categoria", [None])[0]
                        termo = (query.get("q") or query.get("termo") or [None])[0]
                        incluir_inativos = query.get("incluir_inativos", ["0"])[0] in ("1", "true", "sim")
                        docs = self.service.listar_documentos(
                            colab_id, categoria=cat, termo=termo, incluir_inativos=incluir_inativos, empresa_id=empresa_valida
                        )
                        return self._enviar_json(200, {"sucesso": True, "total": len(docs), "dados": docs})
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

                if len(partes) == 6 and partes[3] == "documentos" and partes[4].isdigit() and partes[5] == "versoes":
                    try:
                        versoes = self.service.listar_versoes_documento(colab_id, int(partes[4]), empresa_id=empresa_valida)
                        return self._enviar_json(200, {"sucesso": True, "total": len(versoes), "dados": versoes})
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

                if len(partes) == 6 and partes[3] == "documentos" and partes[4].isdigit() and partes[5] == "download":
                    try:
                        modo = (query.get("modo") or ["download"])[0]
                        acao = "visualizacao" if modo == "visualizar" else "download"
                        nome_resp = f"{usuario['nome_completo']} ({usuario['perfil']})"
                        res_doc = self.service.obter_documento_para_download(
                            colab_id,
                            int(partes[4]),
                            usuario=nome_resp,
                            empresa_id=empresa_valida,
                            ip_origem=self._obter_ip_cliente(),
                            acao=acao,
                        )
                        conteudo_bytes = res_doc["conteudo_bytes"]
                        mime = res_doc.get("mime_type") or "application/octet-stream"
                        nome_arq = str(res_doc.get("nome_arquivo") or f"documento_{partes[4]}").replace('"', "_")
                        disp = "inline" if modo == "visualizar" else "attachment"
                        self.send_response(200)
                        self.send_header("Content-Type", mime)
                        self.send_header("Content-Length", str(len(conteudo_bytes)))
                        self.send_header("Content-Disposition", f'{disp}; filename="{nome_arq}"')
                        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
                        self.send_header("Access-Control-Allow-Credentials", "true")
                        self.send_header("X-Content-Type-Options", "nosniff")
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        self.wfile.write(conteudo_bytes)
                        return
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
                    except Exception as e:
                        return self._enviar_json(*erro_http(e))

                if len(partes) == 4 and partes[3] == "dados-bancarios":
                    try:
                        incluir_inativos = query.get("incluir_inativos", ["0"])[0] in ("1", "true", "sim")
                        contas = self.service.listar_dados_bancarios(colab_id, incluir_inativos=incluir_inativos, empresa_id=empresa_valida)
                        return self._enviar_json(200, {"sucesso": True, "total": len(contas), "dados": contas})
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

                if len(partes) == 4 and partes[3] == "auditoria":
                    try:
                        entidade = query.get("entidade", [None])[0]
                        usr_filtro = query.get("usuario", [None])[0]
                        campo_filtro = query.get("campo", [None])[0]
                        dt_ini = query.get("data_inicio", [None])[0]
                        dt_fim = query.get("data_fim", [None])[0]
                        logs = self.service.listar_auditoria_cadastral(
                            colaborador_id=colab_id,
                            entidade=entidade,
                            usuario=usr_filtro,
                            campo=campo_filtro,
                            data_inicio=dt_ini,
                            data_fim=dt_fim,
                            empresa_id=empresa_valida,
                        )
                        return self._enviar_json(200, {"sucesso": True, "total": len(logs), "dados": logs})
                    except RecursoNaoEncontradoException as e:
                        return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

        # Rota protegida: Catálogo parametrizável de eventos da folha GET /api/folha/eventos-catalogo
        if path == "/api/folha/eventos-catalogo":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            tipo_rub = query.get("tipo", [None])[0]
            termo_rub = query.get("q", [None])[0]
            apenas_ativas = query.get("apenas_ativas", ["0"])[0] in ("1", "true", "True")
            rubricas = self.folha_service.listar_rubricas(
                tipo=tipo_rub,
                apenas_ativas=apenas_ativas,
                termo=termo_rub,
            )
            for r in rubricas:
                r.setdefault("evento", r.get("descricao", ""))
                r.setdefault("inss", r.get("incide_inss", 0))
                r.setdefault("irrf", r.get("incide_irrf", 0))
                r.setdefault("fgts", r.get("incide_fgts", 0))
            return self._enviar_json(200, {
                "sucesso": True,
                "total": len(rubricas),
                "dados": rubricas
            })

        # Rota protegida: Relatórios Gerenciais e Financeiros da Folha GET /api/folha/relatorios
        if path == "/api/folha/relatorios":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            empresa_valida = self._validar_escopo_empresa(usuario, empresa_alvo)
            if empresa_valida is None and usuario.get("perfil") not in ("superadmin", "administrador"):
                return
            comp = query.get("competencia", [None])[0]
            comp_ini = query.get("competencia_inicio", [None])[0]
            comp_fim = query.get("competencia_fim", [None])[0]
            filial_id = query.get("filial_id", [None])[0]
            setor = query.get("setor", [None])[0]
            colab_id = query.get("colaborador_id", [None])[0]
            rel = self.folha_service.obter_relatorios_folha(
                competencia=comp,
                empresa_id=empresa_valida,
                filial_id=filial_id,
                setor=setor,
                colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                competencia_inicio=comp_ini,
                competencia_fim=comp_fim,
            )
            return self._enviar_json(200, {"sucesso": True, "dados": rel})

        # Rota protegida: Download PDF em lote GET /api/folha/holerites-lote/pdf
        if path == "/api/folha/holerites-lote/pdf":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            empresa_valida = self._validar_escopo_empresa(usuario, empresa_alvo)
            if empresa_valida is None and usuario.get("perfil") not in ("superadmin", "administrador"):
                return
            comp = query.get("competencia", [None])[0]
            setor = query.get("setor", [None])[0]
            situacao = query.get("situacao", [None])[0]
            folhas_resumo = self.folha_service.listar_folhas(
                competencia=comp,
                setor=setor,
                situacao=situacao,
                empresa_id=empresa_valida,
            )
            holerites = [self.folha_service.obter_folha_por_id(f["id"]) for f in folhas_resumo]
            if not holerites:
                return self._enviar_json(404, {"sucesso": False, "mensagem": "Nenhum contracheque encontrado para gerar PDF em lote."})
            try:
                from .holerite_pdf import gerar_pdf_holerites_lote
            except ImportError:
                from backend.holerite_pdf import gerar_pdf_holerites_lote
            pdf_bytes = gerar_pdf_holerites_lote(holerites)
            comp_slug = (comp or "COMPETENCIA").replace("-", "_")
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'attachment; filename="CONTRACHEQUES_LOTE_{comp_slug}.pdf"')
            self.send_header("Content-Length", str(len(pdf_bytes)))
            self.end_headers()
            self.wfile.write(pdf_bytes)
            return

        # Rota protegida: Holerites em lote para impressão/PDF GET /api/folha/holerites-lote
        if path == "/api/folha/holerites-lote":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            empresa_valida = self._validar_escopo_empresa(usuario, empresa_alvo)
            if empresa_valida is None and usuario.get("perfil") not in ("superadmin", "administrador"):
                return
            comp = query.get("competencia", [None])[0]
            setor = query.get("setor", [None])[0]
            situacao = query.get("situacao", [None])[0]
            folhas_resumo = self.folha_service.listar_folhas(
                competencia=comp,
                setor=setor,
                situacao=situacao,
                empresa_id=empresa_valida,
            )
            holerites = [self.folha_service.obter_folha_por_id(f["id"]) for f in folhas_resumo]
            return self._enviar_json(200, {"sucesso": True, "total": len(holerites), "dados": holerites})

        # Rota protegida: Parâmetros de cálculo GET /api/folha/parametros
        if path == "/api/folha/parametros":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            param = self.folha_service.obter_parametro_vigente()
            return self._enviar_json(200, {"sucesso": True, "dados": param})

        # Rota protegida: Colaboradores elegíveis para folha GET /api/folha/colaboradores
        if path == "/api/folha/colaboradores":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            colabs = self.service.listar(situacao="ativo")
            # Adiciona total de dependentes para cálculo facilitado no frontend
            conn = self.service._conn()
            cursor = conn.cursor()
            P = self.service._ph()
            resultado = []
            for c in colabs:
                cursor.execute(f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo'", (c["id"],))
                c["total_dependentes"] = cursor.fetchone()[0]
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo' AND COALESCE(eh_dependente_irrf, 1) = 1", (c["id"],))
                    c["total_dependentes_irrf"] = cursor.fetchone()[0]
                    cursor.execute(f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo' AND COALESCE(eh_elegivel_salario_familia, 0) = 1", (c["id"],))
                    c["total_dependentes_salario_familia"] = cursor.fetchone()[0]
                    cursor.execute(f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo' AND COALESCE(eh_plano_saude, 0) = 1", (c["id"],))
                    c["total_dependentes_plano_saude"] = cursor.fetchone()[0]
                except Exception:
                    c["total_dependentes_irrf"] = c["total_dependentes"]
                    c["total_dependentes_salario_familia"] = 0
                    c["total_dependentes_plano_saude"] = 0
                resultado.append(c)
            conn.close()
            return self._enviar_json(200, {"sucesso": True, "total": len(resultado), "dados": resultado})

        # Rota protegida: Listar folhas GET /api/folha
        if path == "/api/folha":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            comp = query.get("competencia", [None])[0]
            colab_id = query.get("colaborador_id", [None])[0]
            situacao = query.get("situacao", [None])[0]
            setor = query.get("setor", [None])[0]
            termo = query.get("q", [None])[0]
            tipo_folha = query.get("tipo_folha", [None])[0]

            folhas = self.folha_service.listar_folhas(
                competencia=comp,
                colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                situacao=situacao,
                setor=setor,
                termo=termo,
                tipo_folha=tipo_folha,
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(folhas), "dados": folhas})

        # Rota protegida: Obter folha por ID ou PDF GET /api/folha/<id>[/pdf]
        if path.startswith("/api/folha/"):
            partes = path.strip("/").split("/")
            if len(partes) == 4 and partes[2].isdigit() and partes[3] == "pdf":
                usuario = self._exigir_autenticacao()
                if not usuario:
                    return
                folha_id = int(partes[2])
                try:
                    folha = self.folha_service.obter_folha_por_id(folha_id)
                    try:
                        from .holerite_pdf import gerar_pdf_holerite, nome_arquivo_contracheque
                    except ImportError:
                        from backend.holerite_pdf import gerar_pdf_holerite, nome_arquivo_contracheque
                    pdf_bytes = gerar_pdf_holerite(folha)
                    nome_arq = nome_arquivo_contracheque(folha)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", f'attachment; filename="{nome_arq}"')
                    self.send_header("Content-Length", str(len(pdf_bytes)))
                    self.end_headers()
                    self.wfile.write(pdf_bytes)
                    return
                except FolhaNaoEncontradaException as e:
                    return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            if len(partes) == 3 and partes[2].isdigit():
                usuario = self._exigir_autenticacao()
                if not usuario:
                    return
                folha_id = int(partes[2])
                try:
                    folha = self.folha_service.obter_folha_por_id(folha_id)
                    return self._enviar_json(200, {"sucesso": True, "dados": folha})
                except FolhaNaoEncontradaException as e:
                    return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

        # Rotas da Plataforma de Gestão do Ciclo Trabalhista (Módulo 02: Admissão RF-011 a RF-020)
        if path == "/api/admissoes":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "admissoes:visualizar"):
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, empresa_alvo)
            if not ok_escopo:
                return
            status = query.get("status", [None])[0]
            admissoes = self.plataforma_service.listar_admissoes(status=status, empresa_id=empresa_valida)
            return self._enviar_json(200, {"sucesso": True, "total": len(admissoes), "dados": admissoes})

        if path == "/api/admissoes/escalas":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "admissoes:visualizar"):
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, empresa_alvo)
            if not ok_escopo:
                return
            escalas = self.plataforma_service.listar_escalas_jornada(empresa_id=empresa_valida or "a0000000-0000-0000-0000-000000000001")
            return self._enviar_json(200, {"sucesso": True, "total": len(escalas), "dados": escalas})

        if path == "/api/admissoes/centros-custo":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "admissoes:visualizar"):
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, empresa_alvo)
            if not ok_escopo:
                return
            ccs = self.plataforma_service.listar_centros_custo(empresa_id=empresa_valida or "a0000000-0000-0000-0000-000000000001")
            return self._enviar_json(200, {"sucesso": True, "total": len(ccs), "dados": ccs})

        if path == "/api/admissoes/contratos/modelos":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "admissoes:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario)
            if not ok_escopo:
                return
            modelos = self.plataforma_service.listar_modelos_contrato(empresa_id=empresa_valida)
            return self._enviar_json(200, {"sucesso": True, "total": len(modelos), "dados": modelos})

        if path.startswith("/api/admissoes/"):
            partes = path.strip("/").split("/")
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario)
            if not ok_escopo:
                return
            perfil_u = usuario.get("perfil", "")
            nome_resp = f"{usuario['nome_completo']} ({perfil_u})"

            try:
                if len(partes) == 4 and partes[2] == "checklist" and partes[3].isdigit():
                    if not self._exigir_permissao(usuario, "admissoes:visualizar"):
                        return
                    adm = self.plataforma_service.obter_admissao(int(partes[3]), empresa_id=empresa_valida, perfil_usuario=perfil_u)
                    return self._enviar_json(200, {"sucesso": True, "dados": adm.get("checklist", [])})

                if len(partes) == 3 and partes[2].isdigit():
                    if not self._exigir_permissao(usuario, "admissoes:visualizar"):
                        return
                    adm = self.plataforma_service.obter_admissao(int(partes[2]), empresa_id=empresa_valida, perfil_usuario=perfil_u)
                    return self._enviar_json(200, {"sucesso": True, "dados": adm})

                if len(partes) == 4 and partes[2].isdigit() and partes[3] == "painel":
                    if not self._exigir_permissao(usuario, "admissoes:visualizar"):
                        return
                    painel = self.plataforma_service.obter_painel_admissao(int(partes[2]), empresa_id=empresa_valida, perfil_usuario=perfil_u)
                    return self._enviar_json(200, {"sucesso": True, "dados": painel})

                if len(partes) == 4 and partes[2].isdigit() and partes[3] == "beneficios-elegiveis":
                    if not self._exigir_permissao(usuario, "admissoes:visualizar"):
                        return
                    benefs = self.plataforma_service.listar_beneficios_elegiveis_admissao(int(partes[2]), empresa_id=empresa_valida)
                    return self._enviar_json(200, {"sucesso": True, "total": len(benefs), "dados": benefs})

                if len(partes) == 4 and partes[2].isdigit() and partes[3] == "aso":
                    from .auth import checar_permissao
                    if not (checar_permissao(perfil_u, "admissoes:visualizar") or checar_permissao(perfil_u, "sst:visualizar")):
                        return self._enviar_json(403, {"sucesso": False, "mensagem": "Acesso negado ao controle de ASO."})
                    aso = self.plataforma_service.consultar_aso_admissional(int(partes[2]), perfil_usuario=perfil_u, empresa_id=empresa_valida)
                    return self._enviar_json(200, {"sucesso": True, "dados": aso})

                if len(partes) == 5 and partes[2].isdigit() and partes[3] == "aso" and partes[4] == "download":
                    res_aso = self.plataforma_service.obter_documento_aso_download(int(partes[2]), usuario=nome_resp, perfil_usuario=perfil_u, empresa_id=empresa_valida)
                    return self._enviar_binario(res_aso["conteudo_bytes"], res_aso["mime_type"], res_aso["nome_arquivo"], inline=(query.get("modo", [""])[0] == "visualizar"))

                if len(partes) == 6 and partes[2].isdigit() and partes[3] == "checklist" and partes[4].isdigit() and partes[5] == "download":
                    if not self._exigir_permissao(usuario, "admissoes:visualizar"):
                        return
                    res_doc = self.plataforma_service.obter_documento_checklist_download(int(partes[2]), int(partes[4]), usuario=nome_resp, empresa_id=empresa_valida)
                    return self._enviar_binario(res_doc["conteudo_bytes"], res_doc["mime_type"], res_doc["nome_arquivo"], inline=(query.get("modo", [""])[0] == "visualizar"))

                if len(partes) == 6 and partes[2].isdigit() and partes[3] == "contratos" and partes[4].isdigit() and partes[5] == "download":
                    if not self._exigir_permissao(usuario, "admissoes:visualizar"):
                        return
                    res_ctr = self.plataforma_service.obter_contrato_pdf_download(int(partes[2]), int(partes[4]), usuario=nome_resp, empresa_id=empresa_valida)
                    return self._enviar_binario(res_ctr["conteudo_bytes"], res_ctr["mime_type"], res_ctr["nome_arquivo"], inline=(query.get("modo", [""])[0] == "visualizar"))
            except PlataformaAcessoNegadoException as e:
                return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/espelho":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            from .auth import checar_permissao
            perfil_u = usuario.get("perfil", "")
            if not (checar_permissao(perfil_u, "ponto:visualizar") or checar_permissao(perfil_u, "ponto:meu")):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Acesso negado ao espelho de ponto."})
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            periodo = (query.get("periodo") or query.get("competencia") or [datetime.now().strftime("%Y-%m")])[0]
            if not colab_id or not colab_id.isdigit():
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Parâmetro 'colaborador_id' obrigatório."})
            espelho = self.plataforma_service.obter_espelho_ponto(int(colab_id), periodo)
            return self._enviar_json(200, {"sucesso": True, "dados": espelho})

        if path == "/api/ponto/relatorio-ausencias":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "ponto:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            comp_q = (query.get("competencia") or [datetime.now().strftime("%Y-%m")])[0]
            setor_q = (query.get("setor") or [None])[0]
            rel = self.plataforma_service.ponto_service.relatorio_ausencias(competencia=comp_q, setor=setor_q, empresa_id=empresa_valida)
            return self._enviar_json(200, {"sucesso": True, "dados": rel})

        if path == "/api/ferias/periodos-aquisitivos":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            from .auth import checar_permissao
            perfil_u = usuario.get("perfil", "")
            if not (checar_permissao(perfil_u, "ferias:visualizar") or checar_permissao(perfil_u, "ferias:minhas")):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Acesso negado aos períodos aquisitivos."})
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            pas = self.plataforma_service.listar_periodos_aquisitivos(
                colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                empresa_id=empresa_valida,
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(pas), "dados": pas})

        if path.startswith("/api/ferias/") and path.endswith("/pdf"):
            partes_f = path.strip("/").split("/")
            if len(partes_f) == 4 and partes_f[2].isdigit():
                usuario = self._exigir_autenticacao()
                if not usuario:
                    return
                from .auth import checar_permissao
                perfil_u = usuario.get("perfil", "")
                if not (checar_permissao(perfil_u, "ferias:visualizar") or checar_permissao(perfil_u, "ferias:minhas")):
                    return self._enviar_json(403, {"sucesso": False, "mensagem": "Acesso negado aos documentos de férias."})
                tipo_doc = (query.get("tipo") or ["aviso"])[0]
                try:
                    res = self.plataforma_service.gerar_documentos_ferias_pdf(int(partes_f[2]), tipo_documento=tipo_doc)
                    return self._enviar_binario(res["pdf_bytes"], "application/pdf", res["filename"])
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/ferias":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            from .auth import checar_permissao
            perfil_u = usuario.get("perfil", "")
            if not (checar_permissao(perfil_u, "ferias:visualizar") or checar_permissao(perfil_u, "ferias:minhas")):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Acesso negado ao módulo de férias."})
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            ferias = self.plataforma_service.listar_ferias(
                colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                empresa_id=empresa_valida,
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(ferias), "dados": ferias})

        if path == "/api/afastamentos/relatorio":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "afastamentos:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            rel = self.plataforma_service.relatorio_afastamentos(
                empresa_id=empresa_valida,
                tipo=(query.get("tipo") or [None])[0],
                setor=(query.get("setor") or [None])[0],
            )
            return self._enviar_json(200, {"sucesso": True, "dados": rel})

        if path == "/api/afastamentos":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "afastamentos:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            afast = self.plataforma_service.listar_afastamentos(
                colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                empresa_id=empresa_valida,
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(afast), "dados": afast})

        if path.startswith("/api/rescisoes/") and path.endswith("/pdf"):
            partes_r = path.strip("/").split("/")
            if len(partes_r) == 4 and partes_r[2].isdigit():
                usuario = self._exigir_autenticacao()
                if not usuario or not self._exigir_permissao(usuario, "rescisoes:visualizar"):
                    return
                tipo_doc = (query.get("tipo") or ["trct"])[0]
                try:
                    res = self.plataforma_service.gerar_documentos_rescisao_pdf(int(partes_r[2]), tipo_documento=tipo_doc)
                    return self._enviar_binario(res["pdf_bytes"], "application/pdf", res["filename"])
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/rescisoes":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "rescisoes:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            resc = self.plataforma_service.listar_rescisoes(empresa_id=empresa_valida)
            return self._enviar_json(200, {"sucesso": True, "total": len(resc), "dados": resc})

        if path == "/api/sst/resumo":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            resumo_sst = self.plataforma_service.listar_sst_resumo()
            return self._enviar_json(200, {"sucesso": True, "dados": resumo_sst})

        if path == "/api/esocial/eventos":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "esocial:visualizar"):
                return
            status = query.get("status", [None])[0]
            tipo = query.get("tipo", [None])[0]
            eventos = self.plataforma_service.listar_esocial_eventos(status=status, tipo=tipo)
            return self._enviar_json(200, {"sucesso": True, "total": len(eventos), "dados": eventos})

        if path == "/api/relatorios/exportar-pdf":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            tipo = query.get("tipo", ["colaboradores"])[0]
            filtros = {k: v[0] for k, v in query.items() if k != "tipo"}
            try:
                from backend.relatorios_service import RelatoriosService
                rel_srv = RelatoriosService()
                pdf_bytes = rel_srv.exportar_relatorio_pdf(tipo_relatorio=tipo, filtros=filtros)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'inline; filename="relatorio_{tipo}.pdf"')
                self.send_header("Content-Length", str(len(pdf_bytes)))
                self._adicionar_cors_headers()
                self.end_headers()
                self.wfile.write(pdf_bytes)
                return
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/relatorios"):
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            tipo = query.get("tipo", ["colaboradores"])[0]
            filtros = {k: v[0] for k, v in query.items() if k != "tipo"}
            try:
                from backend.relatorios_service import RelatoriosService
                import inspect
                rel_srv = RelatoriosService()
                fn_map = {
                    "colaboradores": rel_srv.relatorio_colaboradores,
                    "jornadas_ponto": rel_srv.relatorio_jornadas_ponto,
                    "ferias": rel_srv.relatorio_ferias,
                    "afastamentos": rel_srv.relatorio_afastamentos,
                    "beneficios": rel_srv.relatorio_beneficios,
                    "encargos": rel_srv.relatorio_encargos_folha,
                    "sst": rel_srv.relatorio_sst,
                    "rescisoes": rel_srv.relatorio_rescisoes,
                    "financeiro": rel_srv.relatorio_financeiro_folha,
                }
                fn = fn_map.get(tipo, rel_srv.relatorio_colaboradores)
                sig = inspect.signature(fn)
                valid_params = {k: v for k, v in filtros.items() if k in sig.parameters}
                rel = fn(**valid_params)
                return self._enviar_json(200, {"sucesso": True, "relatorio": rel})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/pendencias":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            status = query.get("status", [None])[0]
            severidade = query.get("severidade", [None])[0]
            pendencias = self.plataforma_service.listar_pendencias(status=status, severidade=severidade)
            return self._enviar_json(200, {"sucesso": True, "total": len(pendencias), "dados": pendencias})

        if path == "/api/bi/indicadores":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            kpis = self.plataforma_service.obter_indicadores_bi()
            return self._enviar_json(200, {"sucesso": True, "dados": kpis})

        if path == "/api/multiempresa":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresas = self.plataforma_service.listar_empresas_e_filiais()
            return self._enviar_json(200, {"sucesso": True, "dados": empresas})

        if path == "/api/auditoria":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            # Isolamento multi-empresa estrito (RN-074): superadmin pode ver todas ou filtrar, demais veem apenas sua empresa
            empresa_id = usuario.get("empresa_id")
            if usuario.get("perfil") == "superadmin":
                empresa_id = query.get("empresa_id", [empresa_id])[0]
            mod = query.get("modulo", [None])[0]
            op = query.get("operacao", [None])[0]
            usr = query.get("usuario", [None])[0]
            logs = self.plataforma_service.listar_auditoria(modulo=mod, operacao=op, usuario=usr, empresa_id=empresa_id)
            return self._enviar_json(200, {"sucesso": True, "total": len(logs), "dados": logs})

        if path == "/api/auditoria/integridade":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresa_id = usuario.get("empresa_id") if usuario.get("perfil") != "superadmin" else query.get("empresa_id", [None])[0]
            res_integro = self.plataforma_service.verificar_integridade_auditoria(empresa_id=empresa_id)
            return self._enviar_json(200, {"sucesso": True, "dados": res_integro})

        if path == "/api/beneficios/historico":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            vinc_id = query.get("vinculo_id", [None])[0]
            cid = int(colab_id) if colab_id else None
            vid = int(vinc_id) if vinc_id else None
            hist = self.plataforma_service.listar_historico_beneficios_colaborador(colaborador_id=cid, vinculo_id=vid)
            return self._enviar_json(200, {"sucesso": True, "total": len(hist), "dados": hist})

        # Rotas de Gestão de Benefícios e Descontos (RF071 a RF080)
        if path == "/api/beneficios/catalogo":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            apenas_ativas = query.get("apenas_ativos", ["0"])[0] in ("1", "true", "sim")
            tipo = query.get("tipo", [None])[0]
            itens = self.plataforma_service.listar_beneficios_catalogo(apenas_ativos=apenas_ativas, tipo=tipo)
            return self._enviar_json(200, {"sucesso": True, "total": len(itens), "dados": itens})

        if path == "/api/beneficios/colaboradores":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            tipo = query.get("tipo", [None])[0]
            apenas_ativos = query.get("apenas_ativos", ["0"])[0] in ("1", "true", "sim")
            itens = self.plataforma_service.listar_beneficios_colaboradores(
                colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                tipo=tipo,
                apenas_ativos=apenas_ativos,
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(itens), "dados": itens})

        if path == "/api/beneficios/elegibilidade":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            benef_id = query.get("beneficio_id", [None])[0]
            data_ref = query.get("data_referencia", [None])[0]
            if not colab_id or not colab_id.isdigit():
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Parâmetro 'colaborador_id' é obrigatório."})
            try:
                if benef_id and benef_id.isdigit():
                    res = self.plataforma_service.verificar_elegibilidade_beneficio(int(colab_id), int(benef_id), data_referencia=data_ref)
                else:
                    res = self.plataforma_service.listar_elegibilidade_colaborador(int(colab_id), data_referencia=data_ref)
                return self._enviar_json(200, {"sucesso": True, "dados": res})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/beneficios/descontos-folha":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            comp = (query.get("competencia") or [datetime.now().strftime("%Y-%m")])[0]
            if not colab_id or not colab_id.isdigit():
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Parâmetro 'colaborador_id' é obrigatório."})
            try:
                res = self.plataforma_service.obter_descontos_beneficios_folha(int(colab_id), comp)
                return self._enviar_json(200, {"sucesso": True, "dados": res})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/beneficios/relatorio":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            comp = query.get("competencia", [None])[0]
            tipo = query.get("tipo", [None])[0]
            setor = query.get("setor", [None])[0]
            colab_id = query.get("colaborador_id", [None])[0]
            try:
                res = self.plataforma_service.gerar_relatorio_beneficios(
                    competencia=comp,
                    tipo=tipo,
                    setor=setor,
                    colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                )
                return self._enviar_json(200, {"sucesso": True, "dados": res})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # RF-008: Rotas de Controle de Documentação, Categorias e Config de Alertas
        if path == "/api/documentos/controle":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, empresa_alvo)
            if not ok_escopo:
                return
            situacao = query.get("situacao", [None])[0]
            cat = query.get("categoria", [None])[0]
            colab_id = query.get("colaborador_id", [None])[0]
            dt_ref = query.get("data_referencia", [None])[0]
            sync_pend = query.get("sincronizar", ["0"])[0] in ("1", "true", "sim")
            try:
                ctrl = self.service.obter_controle_documentacao(
                    empresa_id=empresa_valida,
                    situacao=situacao,
                    categoria=cat,
                    colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                    data_referencia=dt_ref,
                    sincronizar_pendencias=sync_pend,
                )
                return self._enviar_json(200, {"sucesso": True, "dados": ctrl})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/documentos/categorias":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, empresa_alvo)
            if not ok_escopo:
                return
            apenas_ativas = query.get("apenas_ativas", ["1"])[0] in ("1", "true", "sim")
            cats = self.service.listar_categorias_documentos(empresa_id=empresa_valida, apenas_ativas=apenas_ativas)
            return self._enviar_json(200, {"sucesso": True, "total": len(cats), "dados": cats})

        if path == "/api/documentos/config-alertas":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            empresa_alvo = (query.get("empresa_id") or [None])[0]
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, empresa_alvo)
            if not ok_escopo:
                return
            cfg = self.service.obter_config_alertas_documentos(empresa_id=empresa_valida)
            return self._enviar_json(200, {"sucesso": True, "dados": cfg})

        # Rotas GET Tabelas Legais, Feriados, 13º Salário, Rateio & Financeiro (RF-081..RF-105)
        if path == "/api/tabelas-legais":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "folha:visualizar"):
                return
            from .tabelas_legais_service import TabelasLegaisService
            tab_srv = TabelasLegaisService(db_path=getattr(self.service, "db_path", None), auto_init=False)
            comp_q = (query.get("competencia") or [None])[0]
            if comp_q:
                return self._enviar_json(200, {"sucesso": True, "dados": tab_srv.obter_tabela_vigente(comp_q)})
            return self._enviar_json(200, {"sucesso": True, "dados": tab_srv.listar_tabelas_legais()})

        if path == "/api/feriados":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            from .tabelas_legais_service import TabelasLegaisService
            ano_q = query.get("ano", [None])[0]
            fer = TabelasLegaisService(db_path=getattr(self.service, "db_path", None), auto_init=False).listar_feriados(
                empresa_id=empresa_valida, ano=int(ano_q) if ano_q and ano_q.isdigit() else None
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(fer), "dados": fer})

        if path == "/api/folha/decimo-terceiro":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "folha:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            ano_q = query.get("ano_base", [None])[0]
            cid_q = query.get("colaborador_id", [None])[0]
            lista = self.folha_service.listar_decimo_terceiro(
                ano_base=int(ano_q) if ano_q and ano_q.isdigit() else None,
                colaborador_id=int(cid_q) if cid_q and cid_q.isdigit() else None,
                empresa_id=empresa_valida,
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(lista), "dados": lista})

        if path == "/api/folha/provisao-decimo-terceiro":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "folha:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            comp_q = (query.get("competencia") or [datetime.now().strftime("%Y-%m")])[0]
            return self._enviar_json(200, {"sucesso": True, "dados": self.folha_service.calcular_provisao_decimo_terceiro(comp_q, empresa_id=empresa_valida)})

        if path == "/api/folha/conferencia-analitica":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "folha:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            comp_q = (query.get("competencia") or [datetime.now().strftime("%Y-%m")])[0]
            return self._enviar_json(200, {"sucesso": True, "dados": self.folha_service.conferencia_analitica_folha(comp_q, empresa_id=empresa_valida)})

        if path == "/api/folha/rateio-centro-custo":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "folha:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            comp_q = (query.get("competencia") or [datetime.now().strftime("%Y-%m")])[0]
            return self._enviar_json(200, {"sucesso": True, "dados": self.folha_service.listar_rateio_centro_custo(comp_q, empresa_id=empresa_valida)})

        if path == "/api/folha/integracao-financeira":
            usuario = self._exigir_autenticacao()
            if not usuario or not self._exigir_permissao(usuario, "folha:visualizar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario, (query.get("empresa_id") or [None])[0])
            if not ok_escopo:
                return
            comp_q = (query.get("competencia") or [None])[0]
            return self._enviar_json(200, {"sucesso": True, "dados": self.folha_service.listar_integracao_financeira(competencia=comp_q, empresa_id=empresa_valida)})

        # Servir Frontend estático (index.html, styles.css, app.js) se arquivo existir
        return super().do_GET()

    def do_POST(self):
        """Trata requisições POST para autenticação e criação de colaboradores."""
        # 1. Validação de CSRF / Origem em requisições mutáveis (RF-LOGIN-005, AC-13)
        if not self._validar_csrf("POST"):
            return

        path, _ = self._obter_caminho_e_query()
        if path.startswith("/api/"):
            iniciar_contexto_requisicao(path, "POST")

        # Rota pública: Login POST /api/auth/login
        if path == "/api/auth/login":
            ip = self._obter_ip_cliente()
            limiter = get_rate_limiter()
            chave_limiter = f"ip:{ip}"

            # Verificação de Rate Limit (RF-LOGIN-005, AC-07)
            bloqueado, restante = limiter.esta_bloqueado(chave_limiter)
            if bloqueado:
                obs_registrar_evento("auth_rate_limit")
                self.auth_service.audit_service.registrar_evento(
                    "BLOQUEIO_RATE_LIMIT",
                    identificador="anônimo",
                    ip_origem=ip,
                    detalhes=f"Bloqueio de taxa ativo ({restante}s restantes)",
                )
                return self._enviar_json(429, {
                    "sucesso": False,
                    "mensagem": "Excesso de tentativas de login. Tente novamente mais tarde.",
                    "codigo": "RATE_LIMIT_EXCEDIDO"
                }, extra_headers={"Retry-After": str(restante)})

            try:
                dados = self._ler_json_body()
                identificador = dados.get("identificador", "").strip()
                senha = dados.get("senha", "")

                if not identificador or not senha:
                    return self._enviar_json(400, {
                        "sucesso": False,
                        "mensagem": "E-mail e senha são obrigatórios."
                    })

                usuario, token = self.auth_service.autenticar(identificador, senha, ip_origem=ip)
                limiter.registrar_sucesso(chave_limiter)

                # RF-161 (Item 1): Suporte a autenticação segura com cookie HttpOnly sem expor o token no corpo quando solicitado
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
                limiter.registrar_falha(chave_limiter, ip_origem=ip)
                return self._enviar_json(401, {
                    "sucesso": False,
                    "mensagem": str(e)
                })
            except ValueError as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Recuperação de Senha (RF-162)
        if path == "/api/auth/recuperar-senha":
            ip = self._obter_ip_cliente()
            chave_limiter = f"recup:{ip}"
            bloqueado, restante = limiter.esta_bloqueado(chave_limiter)
            if bloqueado:
                return self._enviar_json(429, {
                    "sucesso": False,
                    "mensagem": "Excesso de tentativas de recuperação de senha. Aguarde.",
                    "codigo": "RATE_LIMIT_EXCEDIDO"
                }, extra_headers={"Retry-After": str(restante)})

            dados = self._ler_json_body()
            identificador = dados.get("identificador", "").strip()
            if not identificador:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Identificador é obrigatório."})

            res = self.auth_service.solicitar_recuperacao_senha(identificador, ip_origem=ip)
            return self._enviar_json(200, res)

        # Redefinição de Senha com Token Seguro (RF-162)
        if path == "/api/auth/redefinir-senha":
            ip = self._obter_ip_cliente()
            dados = self._ler_json_body()
            token_recup = dados.get("token_recuperacao", "").strip()
            nova_senha = dados.get("nova_senha", "")
            if not token_recup or not nova_senha:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Token e nova senha são obrigatórios."})
            try:
                res = self.auth_service.redefinir_senha_com_token(token_recup, nova_senha, ip_origem=ip)
                return self._enviar_json(200, res)
            except ValueError as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})

        # Suspensão e Cancelamento de Benefícios com Histórico (RN-037, RN-038)
        if path == "/api/beneficios/suspender":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            dados = self._ler_json_body()
            vinculo_id = int(dados.get("vinculo_id", 0))
            motivo = dados.get("motivo", "")
            dt_susp = dados.get("data_suspensao")
            if not vinculo_id or not motivo:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Vínculo e motivo são obrigatórios."})
            try:
                res = self.plataforma_service.suspender_beneficio_colaborador(
                    vinculo_id=vinculo_id,
                    motivo=motivo,
                    data_suspensao=dt_susp,
                    usuario=usuario_auth.get("nome_completo") or "DP",
                )
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Benefício suspenso com sucesso.", "dados": res})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/beneficios/cancelar":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            dados = self._ler_json_body()
            vinculo_id = int(dados.get("vinculo_id", 0))
            motivo = dados.get("motivo", "")
            dt_canc = dados.get("data_cancelamento")
            if not vinculo_id or not motivo:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Vínculo e motivo são obrigatórios."})
            try:
                res = self.plataforma_service.cancelar_beneficio_colaborador(
                    vinculo_id=vinculo_id,
                    motivo=motivo,
                    data_cancelamento=dt_canc,
                    usuario=usuario_auth.get("nome_completo") or "DP",
                )
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Benefício cancelado com sucesso.", "dados": res})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rota protegida: Logout POST /api/auth/logout
        if path == "/api/auth/logout":
            token = self._extrair_token_sessao()
            ip = self._obter_ip_cliente()
            if token:
                self.auth_service.encerrar_sessao(token, ip_origem=ip)
            return self._enviar_json(200, {
                "sucesso": True,
                "mensagem": "Sessão encerrada com sucesso."
            }, delete_cookie="session_token")

        # Rota protegida: Cadastrar colaborador POST /api/colaboradores
        if path == "/api/colaboradores":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                novo = self.service.cadastrar(
                    dados,
                    usuario=nome_responsavel,
                    origem="POST /api/colaboradores",
                    ip_origem=self._obter_ip_cliente(),
                )
                return self._enviar_json(201, {
                    "sucesso": True,
                    "mensagem": "Colaborador cadastrado com sucesso!",
                    "dados": novo
                })
            except ValidacaoException as e:
                return self._enviar_json(400, {
                    "sucesso": False,
                    "mensagem": "Existem inconsistências nos dados informados.",
                    "erros": e.erros
                })
            except ValueError as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rota protegida: Salvar parâmetros da folha POST /api/folha/parametros
        if path == "/api/folha/parametros":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                salvo = self.folha_service.salvar_parametros(dados, usuario=nome_responsavel)
                return self._enviar_json(200, {
                    "sucesso": True,
                    "mensagem": "Parâmetros de cálculo da folha atualizados com sucesso!",
                    "dados": salvo
                })
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rota protegida: Simular cálculo da folha em tempo real POST /api/folha/simular
        if path == "/api/folha/simular":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                colab_id = dados.get("colaborador_id")
                if not colab_id:
                    return self._enviar_json(400, {"sucesso": False, "mensagem": "Informe colaborador_id."})
                colab = self.folha_service.obter_dados_colaborador(int(colab_id))
                param = self.folha_service.obter_parametro_vigente()
                tipo_contrato = (colab.get("tipo_contrato") or "CLT").strip().lower()
                comp_sim = (dados.get("competencia") or datetime.now().strftime("%Y-%m")).strip()[:7]
                from .tabelas_legais_service import TabelasLegaisService
                tab_srv_sim = TabelasLegaisService(db_path=self.folha_service.db_path, auto_init=False)
                tab_sim = tab_srv_sim.obter_tabela_vigente(comp_sim)
                cal_sim = tab_srv_sim.contar_dias_uteis_dsr_competencia(comp_sim, colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001")
                aliquota_fgts = float(tab_sim.get("aliquota_fgts_aprendiz", 2.0)) if tipo_contrato == "aprendiz" else float(param.get("aliquota_fgts", tab_sim.get("aliquota_fgts_padrao", 8.0)))
                num_dep_irrf = int(colab.get("total_dependentes_irrf", colab.get("total_dependentes", 0)))
                dias_mes_sim = int(dados.get("dias_mes", 30))
                divisor_sim = float(dados.get("horas_divisor", colab.get("carga_horaria_mensal") or 220.0))
                eventos_brutos = list(dados.get("eventos", []))
                if dados.get("incluir_beneficios_ativos"):
                    res_ben = self.plataforma_service.obter_descontos_beneficios_folha(int(colab_id), comp_sim)
                    cods_ex = {str(e.get("codigo") or e.get("codigo_evento") or "").strip() for e in eventos_brutos}
                    for ev_b in res_ben.get("eventos_folha", []):
                        if str(ev_b.get("codigo") or "").strip() not in cods_ex:
                            eventos_brutos.append(ev_b)
                eventos_validados = self.folha_service._validar_e_hidratar_eventos(
                    eventos_brutos, horas_divisor=divisor_sim, dias_mes=dias_mes_sim
                )
                from .folha_calculos import processar_calculo_folha
                try:
                    calc = processar_calculo_folha(
                        salario_base=float(colab.get("salario_base", 0.0)),
                        dias_trabalhados=float(dados.get("dias_trabalhados", 30)),
                        dias_mes=dias_mes_sim,
                        divisor_horas=divisor_sim,
                        eventos_informados=eventos_validados,
                        numero_dependentes=num_dep_irrf,
                        parametros_config={
                            "percentual_noturno": param.get("percentual_adicional_noturno", 20.0),
                            "aplicar_reducao_noturna": bool(param.get("aplicar_reducao_noturna", 0)),
                            "fator_reducao_noturna": param.get("fator_reducao_noturna", "1.142857"),
                            "aplicar_inss": bool(param.get("aplicar_inss", 1)),
                            "aplicar_irrf": bool(param.get("aplicar_irrf", 1)),
                            "aliquota_fgts": aliquota_fgts,
                            "tabela_inss": tab_sim["tabela_inss_tuples"],
                            "teto_inss": tab_sim["teto_inss"],
                            "teto_contribuicao_inss": tab_sim["teto_contribuicao_inss"],
                            "tabela_irrf": tab_sim["tabela_irrf_tuples"],
                            "deducao_dependente_irrf": tab_sim["deducao_dependente_irrf"],
                            "desconto_simplificado_irrf": tab_sim["desconto_simplificado_irrf"],
                            "aplicar_reducao_lei_15270": bool(tab_sim.get("lei_15270_ativa", 1)),
                            "salario_minimo": tab_sim["salario_minimo"],
                            "limite_salario_familia": tab_sim["limite_salario_familia"],
                            "valor_cota_salario_familia": tab_sim["valor_cota_salario_familia"],
                            "dias_uteis": cal_sim["dias_uteis"],
                            "domingos_feriados": cal_sim["domingos_feriados"],
                        },
                    )
                except ValueError as ve:
                    raise FolhaValidacaoException({"eventos": str(ve)})
                itens = calc["itens"]
                inss_val = round(sum(float(it["valor_total"]) for it in itens if it["tipo"] == "desconto" and (it.get("codigo_catalogo") in ("0501", "0502") or it["codigo_evento"] in ("501", "0501", "0502"))), 2)
                irrf_val = round(sum(float(it["valor_total"]) for it in itens if it["tipo"] == "desconto" and (it.get("codigo_catalogo") in ("0505", "0506", "0507") or it["codigo_evento"] in ("502", "0505", "0506", "0507"))), 2)
                desc_lancados = round(sum(float(it["valor_total"]) for it in itens if it["tipo"] == "desconto" and it.get("codigo_catalogo") not in ("0501", "0502", "0505", "0506", "0507") and it["codigo_evento"] not in ("501", "0501", "0502", "502", "0505", "0506", "0507")), 2)
                calc["resumo"]["inss_descontado"] = inss_val
                calc["resumo"]["irrf_descontado"] = irrf_val
                calc["resumo"]["descontos_lancados"] = desc_lancados
                for k_res, v_res in calc["resumo"].items():
                    if k_res not in ("encargos_patronais",):
                        calc.setdefault(k_res, v_res)
                return self._enviar_json(200, {"sucesso": True, "dados": calc})
            except FolhaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e), "erros": e.erros})
            except FolhaNaoEncontradaException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rota protegida: Criar folha POST /api/folha
        if path == "/api/folha":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"

                colab_id = dados.get("colaborador_id")
                competencia = dados.get("competencia", "").strip()
                if not colab_id or not competencia:
                    return self._enviar_json(400, {
                        "sucesso": False,
                        "mensagem": "Informe o colaborador e a competência (AAAA-MM)."
                    })

                folha = self.folha_service.criar_ou_atualizar_folha(
                    colaborador_id=int(colab_id),
                    competencia=competencia,
                    periodo_inicio=dados.get("periodo_inicio", f"{competencia}-01"),
                    periodo_fim=dados.get("periodo_fim", f"{competencia}-30"),
                    data_pagamento=dados.get("data_pagamento"),
                    dias_trabalhados=float(dados.get("dias_trabalhados", 30)),
                    dias_mes=int(dados.get("dias_mes", 30)),
                    horas_divisor=float(dados.get("horas_divisor", 220.0)),
                    eventos=dados.get("eventos", []),
                    observacoes=dados.get("observacoes", ""),
                    usuario=nome_responsavel,
                    tipo_folha=dados.get("tipo_folha", "mensal"),
                    empresa_id=dados.get("empresa_id"),
                    filial_id=dados.get("filial_id"),
                    salvar_como_rascunho=bool(dados.get("salvar_como_rascunho", False)),
                    incluir_beneficios_ativos=bool(dados.get("incluir_beneficios_ativos", False)),
                )
                return self._enviar_json(201, {
                    "sucesso": True,
                    "mensagem": "Folha de pagamento gerada e calculada com sucesso!",
                    "dados": folha
                })
            except FolhaValidacaoException as e:
                return self._enviar_json(400, {
                    "sucesso": False,
                    "mensagem": "Inconsistência nos parâmetros da folha.",
                    "erros": e.erros
                })
            except FolhaNaoEncontradaException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except ValueError as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rota protegida: Processamento de folha em lote POST /api/folha/processar-lote
        if path == "/api/folha/processar-lote":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                competencia = (dados.get("competencia") or "").strip()
                if not competencia:
                    return self._enviar_json(400, {"sucesso": False, "mensagem": "Informe a competência (AAAA-MM)."})
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                empresa_valida = self._validar_escopo_empresa(usuario_auth, dados.get("empresa_id"))
                if empresa_valida is None and usuario_auth.get("perfil") not in ("superadmin", "administrador"):
                    return
                resultado = self.folha_service.processar_lote(
                    competencia=competencia,
                    periodo_inicio=dados.get("periodo_inicio", f"{competencia}-01"),
                    periodo_fim=dados.get("periodo_fim", f"{competencia}-28"),
                    data_pagamento=dados.get("data_pagamento"),
                    tipo_folha=dados.get("tipo_folha", "mensal"),
                    empresa_id=empresa_valida,
                    filial_id=dados.get("filial_id"),
                    colaboradores_ids=dados.get("colaboradores_ids"),
                    dias_trabalhados=float(dados.get("dias_trabalhados", 30)),
                    dias_mes=int(dados.get("dias_mes", 30)),
                    horas_divisor=float(dados.get("horas_divisor", 220.0)),
                    usuario=nome_responsavel,
                )
                return self._enviar_json(201, {
                    "sucesso": True,
                    "mensagem": f"Lote processado: {resultado['processadas']} folha(s) gerada(s), {resultado['ignoradas']} ignorada(s).",
                    "dados": resultado
                })
            except FolhaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e), "erros": e.erros})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rota protegida: Criar rubrica no catálogo POST /api/folha/eventos-catalogo
        if path == "/api/folha/eventos-catalogo":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            if usuario_auth.get("perfil") not in ("superadmin", "administrador", "admin_empresa", "gestor_rh", "analista_dp"):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Perfil sem permissão para parametrizar rubricas."})
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                salva = self.folha_service.salvar_rubrica(dados, usuario=nome_responsavel)
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Rubrica cadastrada com sucesso!", "dados": salva})
            except FolhaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e), "erros": e.erros})
            except FolhaBloqueadaException as e:
                return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rota protegida: Upload de documento do colaborador POST /api/colaboradores/<id>/documentos
        if path.startswith("/api/colaboradores/") and path.endswith("/documentos"):
            partes = path.strip("/").split("/")
            if len(partes) == 4 and partes[2].isdigit():
                usuario_auth = self._exigir_autenticacao()
                if not usuario_auth:
                    return
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
                if not ok_escopo:
                    return
                try:
                    dados = self._ler_json_body()
                    nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                    doc = self.service.adicionar_documento(
                        colaborador_id=int(partes[2]),
                        tipo_documento=dados.get("tipo_documento", "Documento"),
                        nome_arquivo=dados.get("nome_arquivo", ""),
                        conteudo_base64=dados.get("conteudo_base64", ""),
                        mime_type=dados.get("mime_type", "application/octet-stream"),
                        tamanho_bytes=int(dados.get("tamanho_bytes", 0) or 0),
                        observacao=dados.get("observacao", ""),
                        usuario=nome_responsavel,
                        categoria=dados.get("categoria"),
                        data_emissao=dados.get("data_emissao"),
                        data_validade=dados.get("data_validade"),
                        documento_raiz_id=dados.get("documento_raiz_id"),
                        empresa_id=empresa_valida,
                        origem="POST /api/colaboradores/documentos",
                        ip_origem=self._obter_ip_cliente(),
                    )
                    return self._enviar_json(201, {"sucesso": True, "mensagem": "Documento anexado com sucesso!", "dados": doc})
                except ValidacaoException as e:
                    return self._enviar_json(400, {"sucesso": False, "mensagem": "Erro de validação.", "erros": e.erros})
                except RecursoNaoEncontradoException as e:
                    return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        # Rota protegida: Ações na folha POST /api/folha/<id>/fechar ou /reabrir ou /calcular ou /aprovar
        if path.startswith("/api/folha/"):
            partes = path.strip("/").split("/")
            if len(partes) == 4 and partes[1] == "folha" and partes[2].isdigit():
                usuario_auth = self._exigir_autenticacao()
                if not usuario_auth:
                    return
                folha_id = int(partes[2])
                acao = partes[3]
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"

                try:
                    if acao == "aprovar":
                        aprovada = self.folha_service.aprovar_folha(folha_id, usuario=nome_responsavel)
                        return self._enviar_json(200, {
                            "sucesso": True,
                            "mensagem": f"Folha #{folha_id} aprovada para fechamento!",
                            "dados": aprovada
                        })
                    elif acao == "fechar":
                        fechada = self.folha_service.fechar_folha(folha_id, usuario=nome_responsavel)
                        return self._enviar_json(200, {
                            "sucesso": True,
                            "mensagem": f"Folha #{folha_id} homologada e fechada com sucesso!",
                            "dados": fechada
                        })
                    elif acao == "reabrir":
                        corpo = self._ler_json_body()
                        motivo = corpo.get("motivo", "")
                        apagar = bool(corpo.get("apagar_para_relancar", False))
                        reaberta = self.folha_service.reabrir_folha(
                            folha_id, motivo=motivo, usuario=nome_responsavel, apagar_para_relancar=apagar
                        )
                        msg_reab = (
                            f"Folha #{folha_id} reaberta e apagada para novo lançamento."
                            if apagar else f"Folha #{folha_id} reaberta para edição."
                        )
                        return self._enviar_json(200, {
                            "sucesso": True,
                            "mensagem": msg_reab,
                            "dados": reaberta
                        })
                    elif acao == "calcular":
                        corpo = self._ler_json_body()
                        folha_antiga = self.folha_service.obter_folha_por_id(folha_id)
                        atualizada = self.folha_service.criar_ou_atualizar_folha(
                            colaborador_id=folha_antiga["colaborador_id"],
                            competencia=folha_antiga["competencia"],
                            periodo_inicio=corpo.get("periodo_inicio", folha_antiga["periodo_inicio"]),
                            periodo_fim=corpo.get("periodo_fim", folha_antiga["periodo_fim"]),
                            data_pagamento=corpo.get("data_pagamento", folha_antiga.get("data_pagamento")),
                            dias_trabalhados=float(corpo.get("dias_trabalhados", folha_antiga["dias_trabalhados"])),
                            dias_mes=int(corpo.get("dias_mes", folha_antiga["dias_mes"])),
                            horas_divisor=float(corpo.get("horas_divisor", folha_antiga["horas_mensais_divisor"])),
                            eventos=corpo.get("eventos", []),
                            observacoes=corpo.get("observacoes", folha_antiga.get("observacoes", "")),
                            usuario=nome_responsavel,
                            folha_id_existente=folha_id
                        )
                        return self._enviar_json(200, {
                            "sucesso": True,
                            "mensagem": "Folha recalculada com sucesso!",
                            "dados": atualizada
                        })
                except FolhaBloqueadaException as e:
                    return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
                except FolhaValidacaoException as e:
                    return self._enviar_json(400, {"sucesso": False, "mensagem": str(e), "erros": e.erros})
                except FolhaNaoEncontradaException as e:
                    return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        # Rotas POST da Plataforma de Gestão do Ciclo Trabalhista (Módulo 02: Admissão RF-011 a RF-020)
        if path == "/api/admissoes":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "admissoes:criar"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                if empresa_valida:
                    dados["empresa_id"] = empresa_valida
                resp = self.plataforma_service.registrar_admissao(dados, usuario_auth["nome_completo"])
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Admissão registrada com sucesso!", "dados": resp})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/admissoes/escalas":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "admissoes:criar"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                res = self.plataforma_service.criar_escala_jornada(dados, usuario=usuario_auth["nome_completo"], empresa_id=empresa_valida)
                return self._enviar_json(201, {"sucesso": True, "dados": res})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/admissoes/centros-custo":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "admissoes:criar"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                res = self.plataforma_service.criar_centro_custo(dados, usuario=usuario_auth["nome_completo"], empresa_id=empresa_valida)
                return self._enviar_json(201, {"sucesso": True, "dados": res})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/admissoes/"):
            partes = path.strip("/").split("/")
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            perfil_u = usuario_auth.get("perfil", "")
            usr_nome = usuario_auth["nome_completo"]
            try:
                dados = self._ler_json_body()
                if len(partes) == 4 and partes[2].isdigit():
                    adm_id = int(partes[2])
                    acao = partes[3]
                    if acao == "aprovar":
                        if not self._exigir_permissao(usuario_auth, "admissoes:aprovar"):
                            return
                        resp = self.plataforma_service.aprovar_admissao(
                            adm_id,
                            aprovador=usr_nome,
                            justificativa=dados.get("justificativa", ""),
                            empresa_id=empresa_valida,
                            exigir_centro_custo=bool(dados.get("exigir_centro_custo", False)),
                        )
                        return self._enviar_json(200, resp)
                    if acao == "reprovar":
                        if not self._exigir_permissao(usuario_auth, "admissoes:aprovar"):
                            return
                        resp = self.plataforma_service.reprovar_admissao(adm_id, aprovador=usr_nome, motivo=dados.get("motivo", ""), empresa_id=empresa_valida)
                        return self._enviar_json(200, {"sucesso": True, "dados": resp})
                    if acao == "cancelar":
                        if not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                            return
                        resp = self.plataforma_service.cancelar_admissao(adm_id, motivo=dados.get("motivo", ""), usuario=usr_nome, empresa_id=empresa_valida)
                        return self._enviar_json(200, {"sucesso": True, "dados": resp})
                    if acao == "solicitar-aprovacao":
                        if not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                            return
                        resp = self.plataforma_service.solicitar_aprovacao_admissao(adm_id, usuario=usr_nome, justificativa=dados.get("justificativa", ""), empresa_id=empresa_valida)
                        return self._enviar_json(200, resp)
                    if acao == "validar":
                        if not self._exigir_permissao(usuario_auth, "admissoes:validar"):
                            return
                        resp = self.plataforma_service.validar_admissao(
                            adm_id, usuario=usr_nome, empresa_id=empresa_valida, exigir_centro_custo=bool(dados.get("exigir_centro_custo", False))
                        )
                        return self._enviar_json(200, {"sucesso": True, "dados": resp})
                    if acao == "checklist":
                        if not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                            return
                        resp = self.plataforma_service.configurar_item_checklist(adm_id, dados, usuario=usr_nome, empresa_id=empresa_valida)
                        return self._enviar_json(201, resp)
                    if acao == "aso":
                        from .auth import checar_permissao
                        if not (checar_permissao(perfil_u, "admissoes:editar") or checar_permissao(perfil_u, "sst:criar")):
                            return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para registrar ASO."})
                        resp = self.plataforma_service.registrar_aso_admissional(adm_id, dados, usuario=usr_nome, empresa_id=empresa_valida)
                        return self._enviar_json(201, {"sucesso": True, "dados": resp})
                    if acao == "jornada":
                        if not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                            return
                        resp = self.plataforma_service.definir_jornada_admissao(adm_id, dados, usuario=usr_nome, empresa_id=empresa_valida)
                        return self._enviar_json(200, {"sucesso": True, "dados": resp})
                    if acao == "centro-custo":
                        if not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                            return
                        resp = self.plataforma_service.definir_centro_custo_admissao(adm_id, dados, usuario=usr_nome, empresa_id=empresa_valida)
                        return self._enviar_json(200, {"sucesso": True, "dados": resp})
                    if acao == "beneficios":
                        if not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                            return
                        itens_b = dados.get("beneficios") if isinstance(dados.get("beneficios"), list) else dados.get("itens", [])
                        resp = self.plataforma_service.definir_beneficios_admissao(adm_id, itens_b, usuario=usr_nome, empresa_id=empresa_valida)
                        return self._enviar_json(200, resp)

                if len(partes) == 6 and partes[2].isdigit() and partes[3] == "checklist" and partes[4].isdigit() and partes[5] == "upload":
                    if not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                        return
                    resp = self.plataforma_service.upload_documento_checklist(
                        int(partes[2]), int(partes[4]),
                        nome_arquivo=dados.get("nome_arquivo", ""),
                        conteudo_base64=dados.get("conteudo_base64", ""),
                        mime_type=dados.get("mime_type", "application/octet-stream"),
                        usuario=usr_nome,
                        observacao=dados.get("observacao", ""),
                        empresa_id=empresa_valida,
                    )
                    return self._enviar_json(201, resp)

                if len(partes) == 5 and partes[2].isdigit() and partes[3] == "contratos" and partes[4] == "gerar":
                    if not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                        return
                    resp = self.plataforma_service.gerar_contrato_trabalho(
                        int(partes[2]),
                        usuario=usr_nome,
                        modelo_id=dados.get("modelo_id"),
                        condicoes_adicionais=dados.get("condicoes_adicionais", ""),
                        empresa_id=empresa_valida,
                    )
                    return self._enviar_json(201, {"sucesso": True, "dados": resp})

                if len(partes) == 6 and partes[2].isdigit() and partes[3] == "contratos" and partes[4].isdigit() and partes[5] == "formalizar":
                    if not self._exigir_permissao(usuario_auth, "admissoes:aprovar"):
                        return
                    resp = self.plataforma_service.formalizar_contrato(int(partes[2]), int(partes[4]), usuario=usr_nome, empresa_id=empresa_valida)
                    return self._enviar_json(200, {"sucesso": True, "dados": resp})

                if len(partes) == 5 and partes[2].isdigit() and partes[3] == "esocial" and partes[4] == "gerar":
                    from .auth import checar_permissao
                    if not (checar_permissao(perfil_u, "admissoes:editar") or checar_permissao(perfil_u, "esocial:gerar")):
                        return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para gerar evento eSocial."})
                    resp = self.plataforma_service.gerar_evento_esocial_admissao(
                        int(partes[2]),
                        tipo_evento=dados.get("tipo_evento"),
                        usuario=usr_nome,
                        ambiente=dados.get("ambiente", "homologacao"),
                        empresa_id=empresa_valida,
                    )
                    return self._enviar_json(201, {"sucesso": True, "dados": resp})

                if len(partes) == 6 and partes[2] == "esocial" and partes[3].isdigit() and partes[4] == "retorno":
                    pass  # handled below if 5 parts
                if len(partes) == 5 and partes[2] == "esocial" and partes[3].isdigit() and partes[4] == "retorno":
                    from .auth import checar_permissao
                    if not (checar_permissao(perfil_u, "admissoes:editar") or checar_permissao(perfil_u, "esocial:transmitir")):
                        return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para registrar retorno eSocial."})
                    resp = self.plataforma_service.registrar_retorno_esocial(
                        int(partes[3]),
                        status_retorno=dados.get("status_retorno", "rejeitado"),
                        codigo_resposta=dados.get("codigo_resposta", ""),
                        mensagem_resposta=dados.get("mensagem_resposta", ""),
                        protocolo_envio=dados.get("protocolo_envio"),
                        numero_recibo=dados.get("numero_recibo"),
                        usuario=usr_nome,
                        empresa_id=empresa_valida,
                    )
                    return self._enviar_json(200, {"sucesso": True, "dados": resp})

                if len(partes) == 5 and partes[2] == "esocial" and partes[3].isdigit() and partes[4] == "reprocessar":
                    from .auth import checar_permissao
                    if not (checar_permissao(perfil_u, "admissoes:editar") or checar_permissao(perfil_u, "esocial:gerar")):
                        return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para reprocessar eSocial."})
                    resp = self.plataforma_service.reprocessar_evento_esocial(int(partes[3]), usuario=usr_nome, empresa_id=empresa_valida)
                    return self._enviar_json(201, {"sucesso": True, "dados": resp})
            except PlataformaAcessoNegadoException as e:
                return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/marcacao":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            from .auth import checar_permissao
            perfil_u = usuario_auth.get("perfil", "")
            if not (checar_permissao(perfil_u, "ponto:registrar") or checar_permissao(perfil_u, "ponto:meu")):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para registrar marcação."})
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                dt_str = dados.get("data")
                hr_str = dados.get("hora")
                if not dt_str and dados.get("data_hora"):
                    dh = str(dados["data_hora"]).replace(" ", "T").split("T")
                    dt_str = dh[0]
                    hr_str = dh[1][:5] if len(dh) > 1 else "08:00"
                resp = self.plataforma_service.registrar_marcacao_ponto(
                    colaborador_id=int(dados["colaborador_id"]),
                    data=dt_str or datetime.now().strftime("%Y-%m-%d"),
                    hora=hr_str or datetime.now().strftime("%H:%M"),
                    tipo_registro=dados.get("tipo_registro") or dados.get("tipo_marcacao", "manual"),
                    coletor_id=dados.get("coletor_id")
                )
                return self._enviar_json(200 if resp.get("sucesso") else 400, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/ajuste":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            from .auth import checar_permissao
            perfil_u = usuario_auth.get("perfil", "")
            if not (checar_permissao(perfil_u, "ponto:registrar") or checar_permissao(perfil_u, "ponto:meu")):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para solicitar ajuste de ponto."})
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.solicitar_ajuste_ponto(
                    colaborador_id=int(dados["colaborador_id"]),
                    data=dados.get("data") or dados.get("data_ocorrencia") or datetime.now().strftime("%Y-%m-%d"),
                    hora_ajustada=dados.get("hora_ajustada") or dados.get("horario_proposto") or "08:00",
                    tipo_marcacao=dados.get("tipo_marcacao", "entrada"),
                    motivo=dados.get("motivo") or dados.get("justificativa") or "",
                    solicitante=usuario_auth["nome_completo"],
                    hora_original=dados.get("hora_original")
                )
                return self._enviar_json(201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/ponto/ajuste/") and path.endswith("/aprovar"):
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:aprovar"):
                return
            partes = path.strip("/").split("/")
            if len(partes) == 5 and partes[3].isdigit():
                ajuste_id = int(partes[3])
                try:
                    corpo = self._ler_json_body()
                    aprovar = corpo.get("aprovar", True)
                    motivo_rep = corpo.get("motivo_reprovacao")
                    resp = self.plataforma_service.aprovar_ajuste_ponto(ajuste_id, aprovador=usuario_auth["nome_completo"], aprovar=aprovar, motivo_reprovacao=motivo_rep)
                    return self._enviar_json(200, resp)
                except PlataformaAcessoNegadoException as e:
                    return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/importar-arquivo":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:editar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.ponto_service.importar_arquivo_ponto(
                    nome_arquivo=dados.get("nome_arquivo") or "marcacoes.csv",
                    conteudo_texto=dados.get("conteudo_texto") or "",
                    usuario=usuario_auth["nome_completo"],
                    empresa_id=empresa_valida,
                )
                return self._enviar_json(201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/importar-api":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:editar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.ponto_service.importar_marcacoes_api(
                    registros=dados.get("registros") or [],
                    idempotency_key=dados.get("idempotency_key"),
                    coletor_id=dados.get("coletor_id"),
                    usuario=usuario_auth["nome_completo"],
                    empresa_id=empresa_valida,
                )
                return self._enviar_json(200, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/validar":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:visualizar"):
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.ponto_service.validar_marcacoes_periodo(
                    int(dados["colaborador_id"]), dados.get("competencia") or datetime.now().strftime("%Y-%m")
                )
                return self._enviar_json(200, {"sucesso": True, "dados": resp})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/banco-horas":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:editar"):
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.ponto_service.movimentar_banco_horas(
                    colaborador_id=int(dados["colaborador_id"]),
                    data_movimento=dados.get("data_movimento") or datetime.now().strftime("%Y-%m-%d"),
                    tipo_movimento=dados.get("tipo_movimento") or "credito",
                    minutos=int(dados["minutos"]),
                    observacao=dados.get("observacao") or "",
                    usuario=usuario_auth["nome_completo"],
                )
                return self._enviar_json(201, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/fechar":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:aprovar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.ponto_service.fechar_ponto_periodo(
                    competencia=dados["competencia"],
                    usuario=usuario_auth["nome_completo"],
                    empresa_id=empresa_valida,
                )
                return self._enviar_json(200, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/reabrir":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:aprovar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.ponto_service.reabrir_ponto_periodo(
                    competencia=dados["competencia"],
                    motivo=dados.get("motivo") or "",
                    usuario=usuario_auth["nome_completo"],
                    empresa_id=empresa_valida,
                )
                return self._enviar_json(200, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/ocorrencias":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:editar"):
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.ponto_service.registrar_ocorrencia(
                    colaborador_id=int(dados["colaborador_id"]),
                    data_inicio=dados["data_inicio"],
                    data_fim=dados.get("data_fim") or dados["data_inicio"],
                    tipo_ocorrencia=dados["tipo_ocorrencia"],
                    descricao=dados.get("descricao") or "",
                    minutos_ausencia=int(dados.get("minutos_ausencia") or 0),
                    artigo_clt=dados.get("artigo_clt"),
                    cid=dados.get("cid"),
                    usuario=usuario_auth["nome_completo"],
                )
                return self._enviar_json(201, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/justificativas":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            from .auth import checar_permissao
            perfil_u = usuario_auth.get("perfil", "")
            if not (checar_permissao(perfil_u, "ponto:registrar") or checar_permissao(perfil_u, "ponto:meu")):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para enviar justificativa."})
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.ponto_service.registrar_justificativa(
                    colaborador_id=int(dados["colaborador_id"]),
                    data_ocorrencia=dados["data_ocorrencia"],
                    tipo_solicitado=dados["tipo_solicitado"],
                    motivo=dados["motivo"],
                    solicitante=usuario_auth["nome_completo"],
                    dias_abono=int(dados.get("dias_abono") or 1),
                    artigo_clt=dados.get("artigo_clt"),
                    cid=dados.get("cid"),
                )
                return self._enviar_json(201, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/ponto/justificativas/") and path.endswith("/decidir"):
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ponto:aprovar"):
                return
            partes_j = path.strip("/").split("/")
            if len(partes_j) == 5 and partes_j[3].isdigit():
                try:
                    dados = self._ler_json_body()
                    resp = self.plataforma_service.ponto_service.decidir_justificativa(
                        int(partes_j[3]),
                        aprovador=usuario_auth["nome_completo"],
                        aprovar=bool(dados.get("aprovar", True)),
                        motivo_decisao=dados.get("motivo_decisao") or "",
                    )
                    return self._enviar_json(200, resp)
                except PlataformaAcessoNegadoException as e:
                    return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/ferias/programar":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            from .auth import checar_permissao
            perfil_u = usuario_auth.get("perfil", "")
            if not (checar_permissao(perfil_u, "ferias:solicitar") or checar_permissao(perfil_u, "ferias:minhas")):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para programar férias."})
            try:
                dados = self._ler_json_body()
                dias_abono_q = int(dados.get("dias_abono") or 0)
                abono_flag = bool(dados.get("abono_pecuniario", False)) or dias_abono_q > 0
                adiantar_flag = bool(dados.get("adiantar_13", False) or dados.get("adiantamento_decimo_terceiro", False))
                resp = self.plataforma_service.programar_ferias(
                    colaborador_id=int(dados["colaborador_id"]),
                    data_inicio=dados.get("data_inicio") or dados.get("data_inicio_gozo"),
                    dias_gozo=int(dados["dias_gozo"]),
                    abono_pecuniario=abono_flag,
                    dias_abono=(dias_abono_q if dias_abono_q > 0 else None),
                    adiantar_13=adiantar_flag,
                    solicitante=usuario_auth["nome_completo"],
                    exigir_aviso_30d=bool(dados.get("exigir_aviso_30d", False)),
                )
                return self._enviar_json(201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/ferias/coletivas":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "ferias:editar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.programar_ferias_coletivas(
                    data_inicio=dados["data_inicio"],
                    dias_gozo=int(dados["dias_gozo"]),
                    setor=dados.get("setor"),
                    empresa_id=empresa_valida,
                    usuario=usuario_auth["nome_completo"],
                )
                return self._enviar_json(201, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/ferias/"):
            partes_fer = path.strip("/").split("/")
            if len(partes_fer) == 4 and partes_fer[2].isdigit():
                fid = int(partes_fer[2])
                acao_fer = partes_fer[3]
                usuario_auth = self._exigir_autenticacao()
                if not usuario_auth:
                    return
                try:
                    dados = self._ler_json_body()
                    if acao_fer == "aprovar":
                        if not self._exigir_permissao(usuario_auth, "ferias:aprovar"):
                            return
                        resp = self.plataforma_service.aprovar_ferias(fid, aprovador=usuario_auth["nome_completo"], aprovar=bool(dados.get("aprovar", True)), motivo=dados.get("motivo") or "")
                        return self._enviar_json(200, resp)
                    elif acao_fer == "cancelar":
                        if not self._exigir_permissao(usuario_auth, "ferias:editar"):
                            return
                        resp = self.plataforma_service.cancelar_ferias(fid, motivo=dados.get("motivo") or "", usuario=usuario_auth["nome_completo"])
                        return self._enviar_json(200, resp)
                    elif acao_fer == "pagar":
                        if not self._exigir_permissao(usuario_auth, "ferias:editar"):
                            return
                        resp = self.plataforma_service.registrar_pagamento_ferias(fid, data_pagamento=dados.get("data_pagamento") or datetime.now().strftime("%Y-%m-%d"), usuario=usuario_auth["nome_completo"])
                        return self._enviar_json(200, resp)
                    elif acao_fer == "integrar-folha":
                        if not self._exigir_permissao(usuario_auth, "folha:calcular"):
                            return
                        resp = self.plataforma_service.integrar_ferias_folha(fid, competencia=dados.get("competencia") or "", usuario=usuario_auth["nome_completo"])
                        return self._enviar_json(201, resp)
                except PlataformaAcessoNegadoException as e:
                    return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/afastamentos":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "afastamentos:registrar"):
                return
            try:
                dados = self._ler_json_body()
                tipo_raw = str(dados.get("tipo") or dados.get("motivo") or "doenca").lower()
                if "acidente" in tipo_raw or "b91" in tipo_raw:
                    tipo_val = "acidente_trabalho"
                elif "maternidade" in tipo_raw:
                    tipo_val = "maternidade"
                elif "paternidade" in tipo_raw:
                    tipo_val = "paternidade"
                elif "doenca" in tipo_raw or "b31" in tipo_raw:
                    tipo_val = "doenca"
                else:
                    tipo_val = dados.get("tipo") or dados.get("motivo") or "doenca"
                dt_ini_af = dados["data_inicio"]
                dt_fim_af = dados.get("data_fim_prevista") or (datetime.strptime(dt_ini_af, "%Y-%m-%d") + timedelta(days=15)).strftime("%Y-%m-%d")
                resp = self.plataforma_service.registrar_afastamento(
                    colaborador_id=int(dados["colaborador_id"]),
                    tipo=tipo_val,
                    data_inicio=dt_ini_af,
                    data_fim_prevista=dt_fim_af,
                    cid=dados.get("cid") or dados.get("codigo_cid"),
                    subtipo_licenca=dados.get("subtipo_licenca"),
                    observacoes=dados.get("observacoes"),
                    usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/afastamentos/"):
            partes_af = path.strip("/").split("/")
            if len(partes_af) == 4 and partes_af[2].isdigit():
                aid = int(partes_af[2])
                acao_af = partes_af[3]
                usuario_auth = self._exigir_autenticacao()
                if not usuario_auth:
                    return
                try:
                    dados = self._ler_json_body()
                    if acao_af == "prorrogar":
                        if not self._exigir_permissao(usuario_auth, "afastamentos:editar"):
                            return
                        resp = self.plataforma_service.prorrogar_afastamento(
                            aid, nova_data_fim=dados["nova_data_fim"], motivo=dados.get("motivo") or "",
                            cid=dados.get("cid"), documento_ref=dados.get("documento_ref"), usuario=usuario_auth["nome_completo"],
                        )
                        return self._enviar_json(200, resp)
                    elif acao_af == "retorno":
                        from .auth import checar_permissao
                        perfil_u = usuario_auth.get("perfil", "")
                        if not (checar_permissao(perfil_u, "afastamentos:editar") or checar_permissao(perfil_u, "sst:criar")):
                            return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para registrar retorno."})
                        resp = self.plataforma_service.registrar_retorno_afastamento(
                            aid, data_retorno=dados.get("data_retorno") or datetime.now().strftime("%Y-%m-%d"),
                            aso_id=int(dados["aso_id"]) if dados.get("aso_id") else None,
                            usuario=usuario_auth["nome_completo"],
                        )
                        return self._enviar_json(200, resp)
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/rescisoes":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "rescisoes:calcular"):
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.registrar_rescisao(
                    colaborador_id=int(dados["colaborador_id"]),
                    tipo_rescisao=dados["tipo_rescisao"],
                    data_afastamento=dados.get("data_afastamento") or dados.get("data_desligamento"),
                    tipo_aviso=dados.get("tipo_aviso", "indenizado"),
                    saldo_salario_dias=int(dados.get("saldo_salario_dias", 0)),
                    ferias_vencidas_dias=int(dados.get("ferias_vencidas_dias", 0)),
                    meses_trabalhados_ano=int(dados.get("meses_trabalhados_ano", 0)),
                    saldo_fgts=dados.get("saldo_fgts", 0.0),
                    dias_restantes_contrato_prazo=int(dados.get("dias_restantes_contrato_prazo", 0)),
                    exigir_aso_demissional=bool(dados.get("exigir_aso_demissional", False)),
                    usuario=usuario_auth["nome_completo"],
                    simular=bool(dados.get("simular", False))
                )
                return self._enviar_json(200 if dados.get("simular") else 201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/rescisoes/"):
            partes_res = path.strip("/").split("/")
            if len(partes_res) == 4 and partes_res[2].isdigit():
                rid = int(partes_res[2])
                acao_r = partes_res[3]
                usuario_auth = self._exigir_autenticacao()
                if not usuario_auth:
                    return
                try:
                    dados = self._ler_json_body()
                    if acao_r == "homologar":
                        if not self._exigir_permissao(usuario_auth, "rescisoes:homologar"):
                            return
                        resp = self.plataforma_service.homologar_rescisao(rid, homologador=usuario_auth["nome_completo"], usuario_dp_observacao=dados.get("observacao") or "")
                        return self._enviar_json(200, resp)
                    elif acao_r == "pagar":
                        from .auth import checar_permissao
                        perfil_u = usuario_auth.get("perfil", "")
                        if not (checar_permissao(perfil_u, "rescisoes:editar") or checar_permissao(perfil_u, "cnab:gerar")):
                            return self._enviar_json(403, {"sucesso": False, "mensagem": "Permissão insuficiente para registrar pagamento rescisório."})
                        resp = self.plataforma_service.registrar_pagamento_rescisao(rid, data_pagamento=dados.get("data_pagamento") or datetime.now().strftime("%Y-%m-%d"), usuario=usuario_auth["nome_completo"])
                        return self._enviar_json(200, resp)
                except PlataformaAcessoNegadoException as e:
                    return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/sst/aso":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.registrar_aso(
                    colaborador_id=int(dados["colaborador_id"]),
                    tipo_aso=dados.get("tipo_aso") or dados.get("tipo_exame") or "PERIODICO",
                    data_emissao=dados.get("data_emissao") or dados.get("data_exame"),
                    data_validade=dados["data_validade"],
                    resultado=dados.get("resultado") or dados.get("resultado_aptidao") or "APTO",
                    medico_nome=dados.get("medico_nome") or dados.get("medico_examinador_nome") or "Médico do Trabalho",
                    medico_crm=dados.get("medico_crm") or dados.get("medico_examinador_crm") or "CRM 12345",
                    medico_uf=dados.get("medico_uf", "SP"),
                    usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/sst/epi/entrega":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.registrar_entrega_epi(
                    colaborador_id=int(dados["colaborador_id"]),
                    epi_id=int(dados["epi_id"]),
                    quantidade=int(dados.get("quantidade", 1)),
                    usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/sst/cat":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                desc_cat = dados.get("descricao") or f"{dados.get('parte_corpo_atingida', 'Ocorrência')} - CID {dados.get('codigo_cid', 'N/A')}"
                resp = self.plataforma_service.registrar_cat(
                    colaborador_id=int(dados["colaborador_id"]),
                    tipo_acidente=dados["tipo_acidente"],
                    data_hora=dados.get("data_hora") or dados.get("data_hora_acidente") or datetime.now().strftime("%Y-%m-%d %H:%M"),
                    local_acidente=dados["local_acidente"],
                    descricao=desc_cat,
                    houve_obito=bool(dados.get("houve_obito", False)),
                    usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/esocial/transmitir":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "esocial:transmitir"):
                return
            try:
                dados = self._ler_json_body()
                evento_ids = dados.get("evento_ids", [])
                resp = self.plataforma_service.transmitir_lote_esocial(evento_ids, usuario=usuario_auth["nome_completo"])
                return self._enviar_json(200, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/esocial/retificar":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "esocial:transmitir"):
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.retificar_evento_esocial(
                    evento_id_original=int(dados["evento_id"]),
                    novo_xml_conteudo=dados.get("novo_xml", "<retificacao/>"),
                    numero_recibo_anterior=dados.get("numero_recibo_anterior", "REC-PREV-01"),
                    justificativa=dados.get("justificativa", "Retificação administrativa"),
                    usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(200, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/esocial/excluir":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "esocial:transmitir"):
                return
            try:
                dados = self._ler_json_body()
                from backend.esocial_service import ESocialService
                esoc = ESocialService()
                resp = esoc.gerar_evento_exclusao_s3000(
                    evento_excluir_id=int(dados["evento_id"]),
                    justificativa=dados.get("justificativa", "Cancelamento administrativo"),
                    usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(200, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/pendencias/") and path.endswith("/resolver"):
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            partes = path.strip("/").split("/")
            if len(partes) == 4 and partes[2].isdigit():
                pend_id = int(partes[2])
                try:
                    resp = self.plataforma_service.resolver_pendencia(pend_id, usuario=usuario_auth["nome_completo"])
                    return self._enviar_json(200, resp)
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/integracoes/cnab":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "cnab:gerar"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                comp = dados.get("competencia", datetime.now().strftime("%Y-%m"))
                banco = dados.get("banco_codigo") or dados.get("codigo_banco") or "001"
                tipo_pg = dados.get("tipo_pagamento") or "folha_mensal"
                resp = self.plataforma_service.gerar_arquivo_cnab240(
                    comp,
                    banco_codigo=banco,
                    usuario=usuario_auth["nome_completo"],
                    empresa_id=empresa_valida or "a0000000-0000-0000-0000-000000000001",
                    tipo_pagamento=tipo_pg,
                )
                return self._enviar_json(200, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/integracoes/cnab/retorno":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "cnab:gerar"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                resp = self.plataforma_service.processar_retorno_cnab240(
                    nome_arquivo=dados.get("nome_arquivo") or "retorno_cnab240.ret",
                    conteudo_retorno=dados.get("conteudo_retorno") or dados.get("conteudo") or "",
                    usuario=usuario_auth["nome_completo"],
                    empresa_id=empresa_valida or "a0000000-0000-0000-0000-000000000001",
                    arquivo_cnab_id=int(dados["arquivo_cnab_id"]) if dados.get("arquivo_cnab_id") else None,
                )
                return self._enviar_json(200, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rotas POST Tabelas Legais, Feriados, 13º Salário, Lote, Rateio & eSocial Periódicos (RF-081..RF-105)
        if path == "/api/tabelas-legais":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "folha:fechar"):
                return
            try:
                from .tabelas_legais_service import TabelasLegaisService
                dados = self._ler_json_body()
                salvo = TabelasLegaisService(db_path=getattr(self.service, "db_path", None), auto_init=False).salvar_tabela_legal(
                    dados, usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Tabela legal gravada com histórico normativo!", "dados": salvo})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/feriados":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "folha:calcular"):
                return
            try:
                from .tabelas_legais_service import TabelasLegaisService
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                feriado = TabelasLegaisService(db_path=getattr(self.service, "db_path", None), auto_init=False).cadastrar_feriado(
                    data_feriado=dados.get("data_feriado") or dados.get("data") or "",
                    descricao=dados.get("descricao") or "",
                    abrangencia=dados.get("abrangencia") or "municipal",
                    empresa_id=empresa_valida or "a0000000-0000-0000-0000-000000000001",
                    filial_id=dados.get("filial_id"),
                )
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Feriado cadastrado no calendário!", "dados": feriado})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/folha/decimo-terceiro":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "folha:calcular"):
                return
            try:
                from .folha_exceptions import FolhaValidacaoException
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                ano_b = int(dados.get("ano_base") or datetime.now().year)
                parcela = int(dados.get("parcela") or 1)
                if dados.get("colaborador_id"):
                    res = self.folha_service.calcular_decimo_terceiro_colaborador(
                        colaborador_id=int(dados["colaborador_id"]),
                        ano_base=ano_b,
                        parcela=parcela,
                        data_pagamento=dados.get("data_pagamento"),
                        usuario=usuario_auth["nome_completo"],
                        salvar=bool(dados.get("salvar", True)),
                    )
                else:
                    res = self.folha_service.calcular_decimo_terceiro_lote(
                        ano_base=ano_b,
                        parcela=parcela,
                        empresa_id=empresa_valida,
                        usuario=usuario_auth["nome_completo"],
                    )
                return self._enviar_json(201, {"sucesso": True, "mensagem": f"13º salário ({parcela}ª parcela/{ano_b}) processado!", "dados": res})
            except FolhaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Erro de validação no 13º salário.", "erros": getattr(e, "erros", {})})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/folha/fechar-lote":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "folha:fechar"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                comp = dados.get("competencia") or datetime.now().strftime("%Y-%m")
                res = self.folha_service.fechar_competencia_lote(
                    competencia=comp,
                    usuario=usuario_auth["nome_completo"],
                    empresa_id=empresa_valida,
                )
                return self._enviar_json(200, {"sucesso": True, "mensagem": f"Competência {comp} fechada em lote.", "dados": res})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/folha/rateio-centro-custo":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "folha:calcular"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                comp = dados.get("competencia") or datetime.now().strftime("%Y-%m")
                res = self.folha_service.gerar_rateio_centro_custo(competencia=comp, empresa_id=empresa_valida)
                return self._enviar_json(200, {"sucesso": True, "mensagem": f"Rateio por centro de custo ({comp}) consolidado!", "dados": res})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/folha/integracao-financeira":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "folha:fechar"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                comp = dados.get("competencia") or datetime.now().strftime("%Y-%m")
                res = self.folha_service.gerar_integracao_financeira(
                    competencia=comp, empresa_id=empresa_valida, usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, {"sucesso": True, "mensagem": f"Lançamentos financeiros e contábeis ({comp}) gerados!", "dados": res})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/folha/esocial-periodicos":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "esocial:transmitir"):
                return
            try:
                dados = self._ler_json_body()
                ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth, dados.get("empresa_id"))
                if not ok_escopo:
                    return
                comp = dados.get("competencia") or datetime.now().strftime("%Y-%m")
                res = self.folha_service.gerar_eventos_esocial_folha(
                    competencia=comp, empresa_id=empresa_valida, usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, {"sucesso": True, "mensagem": f"Eventos periódicos eSocial ({comp}) gerados na fila!", "dados": res})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/beneficios/catalogo":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                novo = self.plataforma_service.criar_beneficio_catalogo(dados, usuario=usuario_auth["nome_completo"])
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Benefício cadastrado no catálogo!", "dados": novo})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/beneficios/colaboradores":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                vinc = self.plataforma_service.vincular_beneficio_colaborador(dados, usuario=usuario_auth["nome_completo"])
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Benefício vinculado ao colaborador com sucesso!", "dados": vinc})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rotas RF-005 a RF-009 (POST)
        partes_post = path.strip("/").split("/")
        if len(partes_post) == 4 and partes_post[1] == "colaboradores" and partes_post[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            colab_id = int(partes_post[2])
            subrecurso = partes_post[3]
            nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
            ip_cli = self._obter_ip_cliente()
            try:
                dados = self._ler_json_body()
                if subrecurso == "dependentes":
                    dep = self.service.cadastrar_dependente(
                        colab_id, dados, usuario=nome_responsavel, origem="POST /api/colaboradores/dependentes", ip_origem=ip_cli, empresa_id=empresa_valida
                    )
                    return self._enviar_json(201, {"sucesso": True, "mensagem": "Dependente cadastrado com sucesso!", "dados": dep})
                if subrecurso == "historico-funcional":
                    mov = self.service.registrar_movimentacao_funcional(
                        colab_id, dados, usuario=nome_responsavel, origem="POST /api/colaboradores/historico-funcional", ip_origem=ip_cli, empresa_id=empresa_valida
                    )
                    return self._enviar_json(201, {"sucesso": True, "mensagem": "Movimentação funcional registrada com sucesso!", "dados": mov})
                if subrecurso == "dados-bancarios":
                    conta = self.service.cadastrar_dados_bancarios(
                        colab_id, dados, usuario=nome_responsavel, origem="POST /api/colaboradores/dados-bancarios", ip_origem=ip_cli, empresa_id=empresa_valida
                    )
                    return self._enviar_json(201, {"sucesso": True, "mensagem": "Conta bancária cadastrada com sucesso!", "dados": conta})
            except ValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Erro de validação.", "erros": e.erros})
            except RecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes_post) == 6 and partes_post[1] == "colaboradores" and partes_post[2].isdigit() and partes_post[3] == "documentos" and partes_post[4].isdigit() and partes_post[5] == "versoes":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                doc = self.service.adicionar_documento(
                    colaborador_id=int(partes_post[2]),
                    tipo_documento=dados.get("tipo_documento", "Documento"),
                    nome_arquivo=dados.get("nome_arquivo", ""),
                    conteudo_base64=dados.get("conteudo_base64", ""),
                    mime_type=dados.get("mime_type", "application/octet-stream"),
                    tamanho_bytes=int(dados.get("tamanho_bytes", 0) or 0),
                    observacao=dados.get("observacao", ""),
                    usuario=nome_responsavel,
                    categoria=dados.get("categoria"),
                    data_emissao=dados.get("data_emissao"),
                    data_validade=dados.get("data_validade"),
                    documento_raiz_id=int(partes_post[4]),
                    empresa_id=empresa_valida,
                    origem="POST /api/colaboradores/documentos/versoes",
                    ip_origem=self._obter_ip_cliente(),
                )
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Nova versão do documento anexada!", "dados": doc})
            except ValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Erro de validação.", "erros": e.erros})
            except RecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/documentos/categorias":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                cat = self.service.criar_categoria_documento(dados, usuario=nome_responsavel, empresa_id=empresa_valida)
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Categoria de documento criada com sucesso!", "dados": cat})
            except ValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Erro de validação.", "erros": e.erros})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        return self._enviar_json(404, {"sucesso": False, "mensagem": f"Rota não encontrada: {path}"})

    def do_PUT(self):
        """Trata atualização completa PUT /api/colaboradores/<id> ou /api/folha/<id>."""
        if not self._validar_csrf("PUT"):
            return
        path, _ = self._obter_caminho_e_query()
        partes = path.strip("/").split("/")

        if len(partes) == 5 and partes[1] == "folha" and partes[2] == "eventos-catalogo" and partes[3].isdigit() and partes[4] == "status":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            if usuario_auth.get("perfil") not in ("superadmin", "administrador", "admin_empresa", "gestor_rh", "analista_dp"):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Perfil sem permissão para ativar/inativar rubricas."})
            try:
                corpo = self._ler_json_body()
                ativo = bool(corpo.get("ativo", True))
                res = self.folha_service.alterar_status_rubrica(int(partes[3]), ativo)
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Status da rubrica atualizado.", "dados": res})
            except FolhaBloqueadaException as e:
                return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
            except FolhaNaoEncontradaException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 3 and partes[1] == "colaboradores" and partes[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            colab_id = int(partes[2])
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                atualizado = self.service.atualizar(
                    colab_id,
                    dados,
                    usuario=nome_responsavel,
                    origem="PUT /api/colaboradores",
                    ip_origem=self._obter_ip_cliente(),
                )
                return self._enviar_json(200, {
                    "sucesso": True,
                    "mensagem": "Colaborador atualizado com sucesso!",
                    "dados": atualizado
                })
            except ValidacaoException as e:
                return self._enviar_json(400, {
                    "sucesso": False,
                    "mensagem": "Existem inconsistências nos dados informados.",
                    "erros": e.erros
                })
            except RecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 3 and partes[1] == "folha" and partes[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            folha_id = int(partes[2])
            try:
                corpo = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                folha_antiga = self.folha_service.obter_folha_por_id(folha_id)
                atualizada = self.folha_service.criar_ou_atualizar_folha(
                    colaborador_id=folha_antiga["colaborador_id"],
                    competencia=folha_antiga["competencia"],
                    periodo_inicio=corpo.get("periodo_inicio", folha_antiga["periodo_inicio"]),
                    periodo_fim=corpo.get("periodo_fim", folha_antiga["periodo_fim"]),
                    data_pagamento=corpo.get("data_pagamento", folha_antiga.get("data_pagamento")),
                    dias_trabalhados=float(corpo.get("dias_trabalhados", folha_antiga["dias_trabalhados"])),
                    dias_mes=int(corpo.get("dias_mes", folha_antiga["dias_mes"])),
                    horas_divisor=float(corpo.get("horas_divisor", folha_antiga["horas_mensais_divisor"])),
                    eventos=corpo.get("eventos", []),
                    observacoes=corpo.get("observacoes", folha_antiga.get("observacoes", "")),
                    usuario=nome_responsavel,
                    folha_id_existente=folha_id
                )
                return self._enviar_json(200, {
                    "sucesso": True,
                    "mensagem": "Folha de pagamento atualizada com sucesso!",
                    "dados": atualizada
                })
            except FolhaBloqueadaException as e:
                return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
            except FolhaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e), "erros": e.erros})
            except FolhaNaoEncontradaException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 4 and partes[1] == "folha" and partes[2] == "eventos-catalogo" and partes[3].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            if usuario_auth.get("perfil") not in ("superadmin", "administrador", "admin_empresa", "gestor_rh", "analista_dp"):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Perfil sem permissão para editar rubricas."})
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                salva = self.folha_service.salvar_rubrica(dados, usuario=nome_responsavel, rubrica_id=int(partes[3]))
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Rubrica atualizada com sucesso!", "dados": salva})
            except FolhaBloqueadaException as e:
                return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
            except FolhaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e), "erros": e.erros})
            except FolhaNaoEncontradaException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 4 and partes[1] == "beneficios" and partes[2] == "catalogo" and partes[3].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                atual = self.plataforma_service.atualizar_beneficio_catalogo(int(partes[3]), dados, usuario=usuario_auth["nome_completo"])
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Benefício do catálogo atualizado!", "dados": atual})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 4 and partes[1] == "beneficios" and partes[2] == "colaboradores" and partes[3].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                atual = self.plataforma_service.atualizar_beneficio_colaborador(int(partes[3]), dados, usuario=usuario_auth["nome_completo"])
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Vínculo de benefício atualizado!", "dados": atual})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rotas RF-005, RF-006, RF-008, RF-009 (PUT)
        if len(partes) == 5 and partes[1] == "colaboradores" and partes[2].isdigit() and partes[4].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            colab_id = int(partes[2])
            sub_id = int(partes[4])
            subrecurso = partes[3]
            nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
            ip_cli = self._obter_ip_cliente()
            if subrecurso == "historico-funcional":
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Histórico funcional é imutável e não permite edição (RF-006)."})
            try:
                dados = self._ler_json_body()
                if subrecurso == "dependentes":
                    dep = self.service.editar_dependente(
                        colab_id, sub_id, dados, usuario=nome_responsavel, origem="PUT /api/colaboradores/dependentes", ip_origem=ip_cli, empresa_id=empresa_valida
                    )
                    return self._enviar_json(200, {"sucesso": True, "mensagem": "Dependente atualizado com sucesso!", "dados": dep})
                if subrecurso == "dados-bancarios":
                    conta = self.service.atualizar_dados_bancarios(
                        colab_id, sub_id, dados, usuario=nome_responsavel, origem="PUT /api/colaboradores/dados-bancarios", ip_origem=ip_cli, empresa_id=empresa_valida
                    )
                    return self._enviar_json(200, {"sucesso": True, "mensagem": "Conta bancária atualizada com sucesso!", "dados": conta})
            except ValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Erro de validação.", "erros": e.erros})
            except RecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/documentos/config-alertas":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                cfg = self.service.atualizar_config_alertas_documentos(dados, usuario=nome_responsavel, empresa_id=empresa_valida)
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Configuração de alertas atualizada!", "dados": cfg})
            except ValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Erro de validação.", "erros": e.erros})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 3 and partes[1] == "admissoes" and partes[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "admissoes:editar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                dados = self._ler_json_body()
                atual = self.plataforma_service.atualizar_admissao(int(partes[2]), dados, usuario=usuario_auth["nome_completo"], empresa_id=empresa_valida)
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Admissão atualizada com sucesso!", "dados": atual})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        return self._enviar_json(404, {"sucesso": False, "mensagem": f"Rota não encontrada: {path}"})

    def do_DELETE(self):
        """Trata exclusão de folha ou documento: DELETE /api/folha/<id> ou /api/colaboradores/<id>/documentos/<doc_id>."""
        if not self._validar_csrf("DELETE"):
            return
        path, _ = self._obter_caminho_e_query()
        partes = path.strip("/").split("/")

        if len(partes) == 5 and partes[1] == "colaboradores" and partes[2].isdigit() and partes[3] == "documentos" and partes[4].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            try:
                _, query_del = self._obter_caminho_e_query()
                corpo_del = self._ler_json_body()
                motivo_del = corpo_del.get("motivo") or (query_del.get("motivo") or [""])[0]
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                self.service.remover_documento(
                    int(partes[2]),
                    int(partes[4]),
                    usuario=nome_responsavel,
                    motivo=motivo_del,
                    empresa_id=empresa_valida,
                    origem="DELETE /api/colaboradores/documentos",
                    ip_origem=self._obter_ip_cliente(),
                )
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Documento inativado com sucesso (rastreabilidade preservada)."})
            except RecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 3 and partes[1] == "folha" and partes[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            folha_id = int(partes[2])
            nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
            try:
                self.folha_service.cancelar_folha(folha_id, usuario=nome_responsavel)
                return self._enviar_json(200, {
                    "sucesso": True,
                    "mensagem": f"Folha #{folha_id} cancelada com sucesso."
                })
            except FolhaBloqueadaException as e:
                return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
            except FolhaNaoEncontradaException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 4 and partes[1] == "beneficios" and partes[2] == "catalogo" and partes[3].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                _, query = self._obter_caminho_e_query()
                forcar = query.get("forcar_inativacao", ["0"])[0] in ("1", "true", "sim")
                res = self.plataforma_service.excluir_beneficio_catalogo(int(partes[3]), usuario=usuario_auth["nome_completo"], forcar_inativacao=forcar)
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Benefício do catálogo removido/inativado.", "dados": res})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 4 and partes[1] == "beneficios" and partes[2] == "colaboradores" and partes[3].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                res = self.plataforma_service.excluir_beneficio_colaborador(int(partes[3]), usuario=usuario_auth["nome_completo"])
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Vínculo de benefício excluído.", "dados": res})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rotas RF-005, RF-006, RF-009 (DELETE / Inativação Lógica / Bloqueio de Imutabilidade)
        if len(partes) == 5 and partes[1] == "colaboradores" and partes[2].isdigit() and partes[4].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            colab_id = int(partes[2])
            sub_id = int(partes[4])
            subrecurso = partes[3]
            nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
            ip_cli = self._obter_ip_cliente()
            if subrecurso == "historico-funcional":
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Histórico funcional é imutável e não permite exclusão física (RF-006)."})
            try:
                _, query_del = self._obter_caminho_e_query()
                corpo_del = self._ler_json_body()
                if subrecurso == "dependentes":
                    motivo_del = corpo_del.get("motivo") or (query_del.get("motivo") or [""])[0]
                    dt_enc = corpo_del.get("data_encerramento") or (query_del.get("data_encerramento") or [None])[0]
                    res = self.service.inativar_dependente(
                        colab_id, sub_id, motivo=motivo_del, data_encerramento=dt_enc, usuario=nome_responsavel,
                        origem="DELETE /api/colaboradores/dependentes", ip_origem=ip_cli, empresa_id=empresa_valida,
                    )
                    return self._enviar_json(200, {"sucesso": True, "mensagem": "Dependente inativado com sucesso.", "dados": res})
                if subrecurso == "dados-bancarios":
                    res = self.service.inativar_dados_bancarios(
                        colab_id, sub_id, usuario=nome_responsavel, origem="DELETE /api/colaboradores/dados-bancarios", ip_origem=ip_cli, empresa_id=empresa_valida
                    )
                    return self._enviar_json(200, {"sucesso": True, "mensagem": "Conta bancária inativada com sucesso.", "dados": res})
            except RecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        return self._enviar_json(404, {"sucesso": False, "mensagem": f"Rota não encontrada: {path}"})

    def do_PATCH(self):
        """Trata atualização cadastral (RF-003), inativação e reativação: PATCH /api/colaboradores/<id>[/inativar|/reativar]."""
        if not self._validar_csrf("PATCH"):
            return
        path, _ = self._obter_caminho_e_query()
        partes = path.strip("/").split("/")

        if len(partes) == 5 and partes[1] == "folha" and partes[2] == "eventos-catalogo" and partes[3].isdigit() and partes[4] == "status":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            if usuario_auth.get("perfil") not in ("superadmin", "administrador", "admin_empresa", "gestor_rh", "analista_dp"):
                return self._enviar_json(403, {"sucesso": False, "mensagem": "Perfil sem permissão para ativar/inativar rubricas."})
            try:
                corpo = self._ler_json_body()
                ativo = bool(corpo.get("ativo", True))
                res = self.folha_service.alterar_status_rubrica(int(partes[3]), ativo)
                return self._enviar_json(200, {"sucesso": True, "mensagem": "Status da rubrica atualizado.", "dados": res})
            except FolhaBloqueadaException as e:
                return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
            except FolhaNaoEncontradaException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 3 and partes[1] == "colaboradores" and partes[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            colab_id = int(partes[2])
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                atualizado = self.service.atualizar(
                    colab_id,
                    dados,
                    usuario=nome_responsavel,
                    origem="PATCH /api/colaboradores",
                    ip_origem=self._obter_ip_cliente(),
                )
                return self._enviar_json(200, {
                    "sucesso": True,
                    "mensagem": "Colaborador atualizado com sucesso!",
                    "dados": atualizado
                })
            except ValidacaoException as e:
                return self._enviar_json(400, {
                    "sucesso": False,
                    "mensagem": "Existem inconsistências nos dados informados.",
                    "erros": e.erros
                })
            except RecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 4 and partes[1] == "colaboradores" and partes[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            colab_id = int(partes[2])
            acao = partes[3]

            try:
                corpo = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                if acao == "inativar":
                    motivo = corpo.get("motivo", "")
                    res = self.service.inativar(
                        colab_id,
                        motivo=motivo,
                        usuario=nome_responsavel,
                        origem="PATCH /api/colaboradores/inativar",
                        ip_origem=self._obter_ip_cliente(),
                    )
                    return self._enviar_json(200, {
                        "sucesso": True,
                        "mensagem": "Colaborador inativado com sucesso. Histórico preservado.",
                        "dados": res
                    })
                elif acao == "reativar":
                    res = self.service.reativar(
                        colab_id,
                        usuario=nome_responsavel,
                        origem="PATCH /api/colaboradores/reativar",
                        ip_origem=self._obter_ip_cliente(),
                    )
                    return self._enviar_json(200, {
                        "sucesso": True,
                        "mensagem": "Colaborador reativado com sucesso.",
                        "dados": res
                    })
            except RecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 4 and partes[1] == "admissoes" and partes[2] == "checklist" and partes[3].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth or not self._exigir_permissao(usuario_auth, "admissoes:validar"):
                return
            ok_escopo, empresa_valida = self._resolver_empresa_escopo(usuario_auth)
            if not ok_escopo:
                return
            item_id = int(partes[3])
            try:
                dados = self._ler_json_body()
                st_raw = str(dados.get("status", "validado")).lower()
                if st_raw in ("aprovado", "entregue", "validado"):
                    status = "validado"
                else:
                    status = st_raw
                just = dados.get("justificativa") or dados.get("justificativa_dispensa") or dados.get("motivo_rejeicao")
                resp = self.plataforma_service.atualizar_item_checklist(
                    item_id, status=status, usuario=usuario_auth["nome_completo"], justificativa=just, empresa_id=empresa_valida
                )
                return self._enviar_json(200, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except PlataformaRecursoNaoEncontradoException as e:
                return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if len(partes) == 4 and partes[1] == "pendencias" and partes[2].isdigit() and partes[3] == "resolver":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            pend_id = int(partes[2])
            try:
                resp = self.plataforma_service.resolver_pendencia(pend_id, usuario=usuario_auth["nome_completo"])
                return self._enviar_json(200, resp)
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        return self._enviar_json(404, {"sucesso": False, "mensagem": f"Rota não encontrada: {path}"})

def run_server(port: int = PORT, db_path: str | None = None):
    """Inicia o servidor HTTP."""
    server_address = ("", port)
    httpd = socketserver.TCPServer(server_address, ApiColaboradorHandler)
    setattr(httpd, "colab_service", ColaboradorService(db_path=db_path))
    setattr(httpd, "auth_service", AuthService(db_path=db_path, auto_init=False))
    setattr(httpd, "folha_service", FolhaService(db_path=db_path, auto_init=False))
    setattr(httpd, "plataforma_service", PlataformaService(db_path=db_path))
    print(f"Servidor rodando em http://localhost:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        httpd.server_close()

if __name__ == "__main__":
    run_server()
