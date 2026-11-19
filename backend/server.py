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
from typing import Any
import urllib.parse

# Carrega variaveis de ambiente do arquivo .env (se existir)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(_env_path)
except ImportError:
    pass  # python-dotenv nao instalado; variaveis devem ser definidas manualmente
try:
    from .auth import AuthService, CredenciaisInvalidasException
    from .csrf import get_csrf_protector
    from .rate_limiter import get_rate_limiter
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
    from backend.auth import AuthService, CredenciaisInvalidasException
    from backend.csrf import get_csrf_protector
    from backend.rate_limiter import get_rate_limiter
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
                setattr(self.server, "colab_service", ColaboradorService())
            return getattr(self.server, "colab_service")

        if getattr(self, "_local_colab_service", None) is None:
            global _global_colab_service
            if _global_colab_service is None:
                _global_colab_service = ColaboradorService()
            self._local_colab_service = _global_colab_service
        return self._local_colab_service

    @property
    def auth_service(self) -> AuthService:
        """Garante acesso ao AuthService tanto em TCPServer quanto em Serverless Functions."""
        if hasattr(self, "server") and self.server is not None:
            if not hasattr(self.server, "auth_service"):
                db_path = getattr(self.service, "db_path", None)
                setattr(self.server, "auth_service", AuthService(db_path=db_path))
            return getattr(self.server, "auth_service")

        if getattr(self, "_local_auth_service", None) is None:
            global _global_auth_service
            if _global_auth_service is None:
                db_path = getattr(self.service, "db_path", None)
                _global_auth_service = AuthService(db_path=db_path)
            self._local_auth_service = _global_auth_service
        return self._local_auth_service

    @property
    def folha_service(self) -> FolhaService:
        """Garante acesso ao FolhaService tanto em TCPServer quanto em Serverless Functions."""
        if hasattr(self, "server") and self.server is not None:
            if not hasattr(self.server, "folha_service"):
                db_path = getattr(self.service, "db_path", None)
                setattr(self.server, "folha_service", FolhaService(db_path=db_path))
            return getattr(self.server, "folha_service")

        if getattr(self, "_local_folha_service", None) is None:
            global _global_folha_service
            if _global_folha_service is None:
                db_path = getattr(self.service, "db_path", None)
                _global_folha_service = FolhaService(db_path=db_path)
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
        Caso contrário, envia imediatamente resposta HTTP 401 Unauthorized e retorna None.
        """
        usuario = self._obter_usuario_autenticado()
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

    def _enviar_json(
        self,
        status_code: int,
        dados: dict[str, Any] | list[Any],
        set_cookie: str | None = None,
        delete_cookie: str | None = None,
        extra_headers: dict[str, Any] | None = None,
    ):
        """Envia resposta JSON com cabeçalhos de segurança, Cache-Control no-store e suporte a cookies HttpOnly."""
        corpo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
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

        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, str(v))

        if set_cookie:
            proto = self.headers.get("X-Forwarded-Proto", "")
            secure_flag = "; Secure" if proto == "https" else ""
            self.send_header("Set-Cookie", f"{set_cookie}; Path=/; HttpOnly; SameSite=Lax{secure_flag}")
        if delete_cookie:
            self.send_header("Set-Cookie", f"{delete_cookie}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")

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
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError("Corpo da requisição não é um JSON válido.")

    def do_GET(self):
        """Trata requisições GET para API e para arquivos estáticos."""
        path, query = self._obter_caminho_e_query()

        # Diagnostico publico: GET /api/health — confirma o banco em uso (sem expor credenciais)
        if path == "/api/health":
            try:
                return self._enviar_json(200, {"sucesso": True, **status_banco()})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        # Rota de verificação de sessão: GET /api/auth/me
        if path == "/api/auth/me":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            perfil = usuario.get("perfil", "colaborador")
            from .auth import PERMISSOES_RBAC
            permissoes = PERMISSOES_RBAC.get(perfil, [])
            return self._enviar_json(200, {
                "sucesso": True,
                "usuario": {
                    **usuario,
                    "permissoes": permissoes
                }
            })

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
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(colabs), "dados": colabs})

        # Rota protegida: Obter colaborador ou histórico GET /api/colaboradores/<id>[/historico]
        if path.startswith("/api/colaboradores/"):
            partes = path.strip("/").split("/")
            if len(partes) == 3 and partes[2].isdigit():
                usuario = self._exigir_autenticacao()
                if not usuario:
                    return
                colab_id = int(partes[2])
                try:
                    colab = self.service.obter_por_id(colab_id)
                    return self._enviar_json(200, {"sucesso": True, "dados": colab})
                except RecursoNaoEncontradoException as e:
                    return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            if len(partes) == 4 and partes[2].isdigit() and partes[3] == "historico":
                usuario = self._exigir_autenticacao()
                if not usuario:
                    return
                colab_id = int(partes[2])
                try:
                    historico = self.service.obter_historico(colab_id)
                    return self._enviar_json(200, {"sucesso": True, "total": len(historico), "dados": historico})
                except RecursoNaoEncontradoException as e:
                    return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

        # Rota protegida: Catálogo de eventos da folha GET /api/folha/eventos-catalogo
        if path == "/api/folha/eventos-catalogo":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            try:
                from .catalogo_eventos import CATALOGO_EVENTOS_FOLHA
            except ImportError:
                from backend.catalogo_eventos import CATALOGO_EVENTOS_FOLHA
            return self._enviar_json(200, {
                "sucesso": True,
                "total": len(CATALOGO_EVENTOS_FOLHA),
                "dados": CATALOGO_EVENTOS_FOLHA
            })

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
                cursor.execute(f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P}", (c["id"],))
                c["total_dependentes"] = cursor.fetchone()[0]
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

            folhas = self.folha_service.listar_folhas(
                competencia=comp,
                colaborador_id=int(colab_id) if colab_id and colab_id.isdigit() else None,
                situacao=situacao,
                setor=setor,
                termo=termo
            )
            return self._enviar_json(200, {"sucesso": True, "total": len(folhas), "dados": folhas})

        # Rota protegida: Obter folha por ID GET /api/folha/<id>
        if path.startswith("/api/folha/"):
            partes = path.strip("/").split("/")
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

        # Rotas da Plataforma de Gestão do Ciclo Trabalhista (Módulos 01 a 20)
        if path == "/api/admissoes":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            status = query.get("status", [None])[0]
            admissoes = self.plataforma_service.listar_admissoes(status=status)
            return self._enviar_json(200, {"sucesso": True, "total": len(admissoes), "dados": admissoes})

        if path.startswith("/api/admissoes/"):
            partes = path.strip("/").split("/")
            if len(partes) == 4 and partes[2] == "checklist" and partes[3].isdigit():
                usuario = self._exigir_autenticacao()
                if not usuario:
                    return
                adm_id = int(partes[3])
                try:
                    adm = self.plataforma_service.obter_admissao(adm_id)
                    return self._enviar_json(200, {"sucesso": True, "dados": adm.get("checklist", [])})
                except PlataformaRecursoNaoEncontradoException as e:
                    return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})
            if len(partes) == 3 and partes[2].isdigit():
                usuario = self._exigir_autenticacao()
                if not usuario:
                    return
                adm_id = int(partes[2])
                try:
                    adm = self.plataforma_service.obter_admissao(adm_id)
                    return self._enviar_json(200, {"sucesso": True, "dados": adm})
                except PlataformaRecursoNaoEncontradoException as e:
                    return self._enviar_json(404, {"sucesso": False, "mensagem": str(e)})

        if path == "/api/ponto/espelho":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            periodo = (query.get("periodo") or query.get("competencia") or [datetime.now().strftime("%Y-%m")])[0]
            if not colab_id or not colab_id.isdigit():
                return self._enviar_json(400, {"sucesso": False, "mensagem": "Parâmetro 'colaborador_id' obrigatório."})
            espelho = self.plataforma_service.obter_espelho_ponto(int(colab_id), periodo)
            return self._enviar_json(200, {"sucesso": True, "dados": espelho})

        if path == "/api/ferias":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            ferias = self.plataforma_service.listar_ferias(int(colab_id) if colab_id and colab_id.isdigit() else None)
            return self._enviar_json(200, {"sucesso": True, "total": len(ferias), "dados": ferias})

        if path == "/api/afastamentos":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            colab_id = query.get("colaborador_id", [None])[0]
            afast = self.plataforma_service.listar_afastamentos(int(colab_id) if colab_id and colab_id.isdigit() else None)
            return self._enviar_json(200, {"sucesso": True, "total": len(afast), "dados": afast})

        if path == "/api/rescisoes":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            resc = self.plataforma_service.listar_rescisoes()
            return self._enviar_json(200, {"sucesso": True, "total": len(resc), "dados": resc})

        if path == "/api/sst/resumo":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            resumo_sst = self.plataforma_service.listar_sst_resumo()
            return self._enviar_json(200, {"sucesso": True, "dados": resumo_sst})

        if path == "/api/esocial/eventos":
            usuario = self._exigir_autenticacao()
            if not usuario:
                return
            status = query.get("status", [None])[0]
            tipo = query.get("tipo", [None])[0]
            eventos = self.plataforma_service.listar_esocial_eventos(status=status, tipo=tipo)
            return self._enviar_json(200, {"sucesso": True, "total": len(eventos), "dados": eventos})

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
            mod = query.get("modulo", [None])[0]
            op = query.get("operacao", [None])[0]
            usr = query.get("usuario", [None])[0]
            logs = self.plataforma_service.listar_auditoria(modulo=mod, operacao=op, usuario=usr)
            return self._enviar_json(200, {"sucesso": True, "total": len(logs), "dados": logs})

        # Servir Frontend estático (index.html, styles.css, app.js) se arquivo existir
        return super().do_GET()

    def do_POST(self):
        """Trata requisições POST para autenticação e criação de colaboradores."""
        # 1. Validação de CSRF / Origem em requisições mutáveis (RF-LOGIN-005, AC-13)
        if not self._validar_csrf("POST"):
            return

        path, _ = self._obter_caminho_e_query()

        # Rota pública: Login POST /api/auth/login
        if path == "/api/auth/login":
            ip = self._obter_ip_cliente()
            limiter = get_rate_limiter()
            chave_limiter = f"ip:{ip}"

            # Verificação de Rate Limit (RF-LOGIN-005, AC-07)
            bloqueado, restante = limiter.esta_bloqueado(chave_limiter)
            if bloqueado:
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

                return self._enviar_json(200, {
                    "sucesso": True,
                    "mensagem": "Autenticação realizada com sucesso.",
                    "token": token,
                    "usuario": usuario
                }, set_cookie=f"session_token={token}")
            except CredenciaisInvalidasException as e:
                limiter.registrar_falha(chave_limiter)
                return self._enviar_json(401, {
                    "sucesso": False,
                    "mensagem": str(e)
                })
            except ValueError as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
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
                novo = self.service.cadastrar(dados, usuario=nome_responsavel)
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
                    usuario=nome_responsavel
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

        # Rota protegida: Ações na folha POST /api/folha/<id>/fechar ou /reabrir ou /calcular
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
                    if acao == "fechar":
                        fechada = self.folha_service.fechar_folha(folha_id, usuario=nome_responsavel)
                        return self._enviar_json(200, {
                            "sucesso": True,
                            "mensagem": f"Folha #{folha_id} homologada e fechada com sucesso!",
                            "dados": fechada
                        })
                    elif acao == "reabrir":
                        corpo = self._ler_json_body()
                        motivo = corpo.get("motivo", "")
                        reaberta = self.folha_service.reabrir_folha(folha_id, motivo=motivo, usuario=nome_responsavel)
                        return self._enviar_json(200, {
                            "sucesso": True,
                            "mensagem": f"Folha #{folha_id} reaberta para edição.",
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

        # Rotas POST da Plataforma de Gestão do Ciclo Trabalhista
        if path == "/api/admissoes":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                resp = self.plataforma_service.registrar_admissao(dados, usuario_auth["nome_completo"])
                return self._enviar_json(201, {"sucesso": True, "mensagem": "Admissão registrada com sucesso!", "dados": resp})
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path.startswith("/api/admissoes/") and path.endswith("/aprovar"):
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            partes = path.strip("/").split("/")
            if len(partes) == 4 and partes[2].isdigit():
                adm_id = int(partes[2])
                try:
                    resp = self.plataforma_service.aprovar_admissao(adm_id, aprovador=usuario_auth["nome_completo"])
                    return self._enviar_json(200, resp)
                except PlataformaAcessoNegadoException as e:
                    return self._enviar_json(403, {"sucesso": False, "mensagem": str(e)})
                except PlataformaValidacaoException as e:
                    return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
                except Exception as e:
                    return self._enviar_json(*erro_http(e))

        if path == "/api/ponto/marcacao":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
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
            if not usuario_auth:
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

        if path == "/api/ferias/programar":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                abono_flag = bool(dados.get("abono_pecuniario", False)) or int(dados.get("dias_abono") or 0) > 0
                adiantar_flag = bool(dados.get("adiantar_13", False) or dados.get("adiantamento_decimo_terceiro", False))
                resp = self.plataforma_service.programar_ferias(
                    colaborador_id=int(dados["colaborador_id"]),
                    data_inicio=dados.get("data_inicio") or dados.get("data_inicio_gozo"),
                    dias_gozo=int(dados["dias_gozo"]),
                    abono_pecuniario=abono_flag,
                    adiantar_13=adiantar_flag,
                    solicitante=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/afastamentos":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
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
                    usuario=usuario_auth["nome_completo"]
                )
                return self._enviar_json(201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        if path == "/api/rescisoes":
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
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
                    usuario=usuario_auth["nome_completo"],
                    simular=bool(dados.get("simular", False))
                )
                return self._enviar_json(200 if dados.get("simular") else 201, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
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
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                evento_ids = dados.get("evento_ids", [])
                resp = self.plataforma_service.transmitir_lote_esocial(evento_ids, usuario=usuario_auth["nome_completo"])
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
            if not usuario_auth:
                return
            try:
                dados = self._ler_json_body()
                comp = dados.get("competencia", datetime.now().strftime("%Y-%m"))
                banco = dados.get("banco_codigo") or dados.get("codigo_banco") or "001"
                resp = self.plataforma_service.gerar_arquivo_cnab240(comp, banco_codigo=banco, usuario=usuario_auth["nome_completo"])
                return self._enviar_json(200, resp)
            except PlataformaValidacaoException as e:
                return self._enviar_json(400, {"sucesso": False, "mensagem": str(e)})
            except Exception as e:
                return self._enviar_json(*erro_http(e))

        return self._enviar_json(404, {"sucesso": False, "mensagem": f"Rota não encontrada: {path}"})

    def do_PUT(self):
        """Trata atualização completa PUT /api/colaboradores/<id> ou /api/folha/<id>."""
        if not self._validar_csrf("PUT"):
            return
        path, _ = self._obter_caminho_e_query()
        partes = path.strip("/").split("/")

        if len(partes) == 3 and partes[1] == "colaboradores" and partes[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            colab_id = int(partes[2])
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                atualizado = self.service.atualizar(colab_id, dados, usuario=nome_responsavel)
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

        return self._enviar_json(404, {"sucesso": False, "mensagem": f"Rota não encontrada: {path}"})

    def do_DELETE(self):
        """Trata exclusão de folha: DELETE /api/folha/<id>."""
        if not self._validar_csrf("DELETE"):
            return
        path, _ = self._obter_caminho_e_query()
        partes = path.strip("/").split("/")

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

        return self._enviar_json(404, {"sucesso": False, "mensagem": f"Rota não encontrada: {path}"})

    def do_PATCH(self):
        """Trata atualização cadastral (RF-003), inativação e reativação: PATCH /api/colaboradores/<id>[/inativar|/reativar]."""
        if not self._validar_csrf("PATCH"):
            return
        path, _ = self._obter_caminho_e_query()
        partes = path.strip("/").split("/")

        if len(partes) == 3 and partes[1] == "colaboradores" and partes[2].isdigit():
            usuario_auth = self._exigir_autenticacao()
            if not usuario_auth:
                return
            colab_id = int(partes[2])
            try:
                dados = self._ler_json_body()
                nome_responsavel = f"{usuario_auth['nome_completo']} ({usuario_auth['perfil']})"
                atualizado = self.service.atualizar(colab_id, dados, usuario=nome_responsavel)
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
                    res = self.service.inativar(colab_id, motivo=motivo, usuario=nome_responsavel)
                    return self._enviar_json(200, {
                        "sucesso": True,
                        "mensagem": "Colaborador inativado com sucesso. Histórico preservado.",
                        "dados": res
                    })
                elif acao == "reativar":
                    res = self.service.reativar(colab_id, usuario=nome_responsavel)
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
            if not usuario_auth:
                return
            item_id = int(partes[3])
            try:
                dados = self._ler_json_body()
                st_raw = str(dados.get("status", "validado")).lower()
                if st_raw in ("aprovado", "entregue", "validado"):
                    status = "validado"
                elif st_raw in ("dispensado",):
                    status = "dispensado"
                else:
                    status = st_raw
                just = dados.get("justificativa_dispensa")
                resp = self.plataforma_service.atualizar_item_checklist(item_id, status=status, usuario=usuario_auth["nome_completo"], justificativa=just)
                return self._enviar_json(200, resp)
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
    setattr(httpd, "auth_service", AuthService(db_path=db_path))
    setattr(httpd, "folha_service", FolhaService(db_path=db_path))
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
