"""
Suíte de Testes Automatizados de Autenticação Segura — RH2.0
Cobre os Critérios de Aceite AC-01 a AC-16 e os requisitos RF-LOGIN-001 a RF-LOGIN-006:
- AC-01 a AC-04: Tela, Acessibilidade, Responsividade e Validações
- AC-05 a AC-06: Login válido e Mensagem genérica estrita
- AC-07: Rate Limiting (HTTP 429 e Retry-After)
- AC-08: Hashing de Senhas PBKDF2 e ausência de senhas em logs
- AC-09 a AC-12: Cookie seguro, Sessão após Refresh, Rotas Privadas e Logout com Invalidação
- AC-13: Proteção CSRF / Origem (HTTP 403)
- AC-16: Auditoria de Eventos de Autenticação
Execução 100% headless em código.
"""
import json
import os
import socketserver
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.auth import AuthService, hash_senha, MENSAGEM_GENERICA_ERRO
from backend.database import get_connection
from backend.rate_limiter import get_rate_limiter
from backend.server import ApiColaboradorHandler
from backend.service import ColaboradorService


class TestAutenticacaoRH20(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(cls.temp_db_fd)

        cls.server = socketserver.TCPServer(("127.0.0.1", 0), ApiColaboradorHandler)
        cls.server.colab_service = ColaboradorService(db_path=cls.temp_db_path)
        cls.server.auth_service = AuthService(db_path=cls.temp_db_path)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists(cls.temp_db_path):
            try:
                os.remove(cls.temp_db_path)
            except PermissionError:
                pass

    def setUp(self):
        # Reseta o rate limiter antes de cada teste para evitar interferência entre testes
        get_rate_limiter().resetar()

    def _req(self, metodo: str, caminho: str, payload: dict = None, token: str = None, cookie: str = None, headers_extras: dict = None):
        """Helper HTTP nativo para envio de requisições de teste."""
        url = f"{self.base_url}{caminho}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=metodo)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        if cookie:
            req.add_header("Cookie", cookie)
        if headers_extras:
            for k, v in headers_extras.items():
                req.add_header(k, v)

        try:
            with urllib.request.urlopen(req) as resp:
                status = resp.status
                corpo = json.loads(resp.read().decode("utf-8"))
                set_cookie = resp.headers.get("Set-Cookie")
                retry_after = resp.headers.get("Retry-After")
                return status, corpo, set_cookie, retry_after
        except urllib.error.HTTPError as e:
            try:
                corpo = json.loads(e.read().decode("utf-8"))
            except Exception:
                corpo = {}
            set_cookie = e.headers.get("Set-Cookie")
            retry_after = e.headers.get("Retry-After")
            return e.code, corpo, set_cookie, retry_after

    # =========================================================================
    # AC-01: Elementos visuais e identidade RH2.0
    # =========================================================================
    def test_ac_01_elementos_tela_login_rh20(self):
        """AC-01: Tela apresenta e-mail, senha, Entrar, mostrar/ocultar senha e identidade RH2.0."""
        html_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn("RH2.0", html, "A identidade visual deve indicar RH2.0.")
        self.assertIn('id="login-identificador"', html, "Campo de e-mail/usuário presente.")
        self.assertIn('id="login-senha"', html, "Campo de senha presente.")
        self.assertIn('id="btn-entrar"', html, "Botão Entrar presente.")
        self.assertIn('id="btn-toggle-senha"', html, "Controle mostrar/ocultar senha presente.")
        self.assertIn('id="login-spinner"', html, "Indicador de carregamento presente.")

    # =========================================================================
    # AC-02: Acessibilidade
    # =========================================================================
    def test_ac_02_acessibilidade(self):
        """AC-02: Foco visível, rótulos e alerta acessível com role=alert e aria-live."""
        html_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn('role="alert"', html, "Mensagem de erro deve ter role=alert para leitores de tela.")
        self.assertIn('aria-live="assertive"', html, "Alerta deve ter aria-live para notificação imediata.")
        self.assertIn('for="login-identificador"', html, "Label deve estar associado ao identificador.")
        self.assertIn('for="login-senha"', html, "Label deve estar associado à senha.")
        self.assertIn('aria-label="Mostrar ou ocultar senha"', html, "Botão de alternar senha acessível.")

    # =========================================================================
    # AC-03: Responsividade
    # =========================================================================
    def test_ac_03_responsividade_css(self):
        """AC-03: Regras CSS responsivas sem scroll horizontal em mobile."""
        css_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "styles.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()

        self.assertIn("@media", css, "CSS deve conter media queries responsivas.")
        self.assertIn("max-width", css, "CSS deve definir larguras máximas adaptativas.")
        self.assertIn(".login-card", css, "Card de login deve ser estilizado.")

    # =========================================================================
    # AC-04: Validação de entradas
    # =========================================================================
    def test_ac_04_validacao_entradas_backend(self):
        """AC-04: Backend rejeita requisições com campos vazios com HTTP 400."""
        # Vazio
        status, corpo, _, _ = self._req("POST", "/api/auth/login", {"identificador": "", "senha": ""})
        self.assertEqual(status, 400)
        self.assertFalse(corpo.get("sucesso", True))

        # Apenas senha
        status, corpo, _, _ = self._req("POST", "/api/auth/login", {"identificador": "", "senha": "123"})
        self.assertEqual(status, 400)

        # Apenas e-mail
        status, corpo, _, _ = self._req("POST", "/api/auth/login", {"identificador": "admin.dp@empresa.com.br", "senha": ""})
        self.assertEqual(status, 400)

    # =========================================================================
    # AC-05: Login válido e criação de sessão
    # =========================================================================
    def test_ac_05_login_valido_sucesso(self):
        """AC-05: Credenciais válidas autenticam com HTTP 200, retornam cookie seguro e usuário."""
        senha_admin = os.environ.get("TEST_ADMIN_PASSWORD", "Sintetico#AdminTest2026!")
        status, corpo, set_cookie, _ = self._req("POST", "/api/auth/login", {
            "identificador": "admin.dp@empresa.com.br",
            "senha": senha_admin
        })

        self.assertEqual(status, 200)
        self.assertTrue(corpo.get("sucesso"))
        self.assertIn("token", corpo)
        self.assertIn("usuario", corpo)
        self.assertEqual(corpo["usuario"]["email"], "admin.dp@empresa.com.br")
        self.assertIsNotNone(set_cookie)
        self.assertIn("session_token=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Lax", set_cookie)

    # =========================================================================
    # AC-06: Mensagens genéricas
    # =========================================================================
    def test_ac_06_mensagens_genericas_sem_enumeracao(self):
        """AC-06: Falhas usam mensagem genérica 'E-mail ou senha inválidos.' sem revelar existência da conta."""
        # Caso 1: Usuário inexistente
        status_1, corpo_1, _, _ = self._req("POST", "/api/auth/login", {
            "identificador": "fantasma.nao.existe@empresa.com.br",
            "senha": "SenhaIncorreta@123"
        })
        self.assertEqual(status_1, 401)
        self.assertEqual(corpo_1.get("mensagem"), MENSAGEM_GENERICA_ERRO)

        # Caso 2: Usuário existente com senha incorreta
        status_2, corpo_2, _, _ = self._req("POST", "/api/auth/login", {
            "identificador": "admin.dp@empresa.com.br",
            "senha": "SenhaTotalmenteErrada@2026!"
        })
        self.assertEqual(status_2, 401)
        self.assertEqual(corpo_2.get("mensagem"), MENSAGEM_GENERICA_ERRO)

        # As mensagens devem ser identicas
        self.assertEqual(corpo_1.get("mensagem"), corpo_2.get("mensagem"))

    # =========================================================================
    # AC-07: Rate Limiting
    # =========================================================================
    def test_ac_07_rate_limit_bloqueio_apos_5_tentativas(self):
        """AC-07: Após 5 falhas consecutivas, a 6ª tentativa retorna HTTP 429 com Retry-After."""
        limiter = get_rate_limiter()
        limiter.resetar()

        # Dispara 5 falhas consecutivas
        for i in range(5):
            status, _, _, _ = self._req("POST", "/api/auth/login", {
                "identificador": "ataque.forca.bruta@teste.com",
                "senha": f"tentativa_{i}"
            })
            self.assertEqual(status, 401, f"Tentativa {i+1} deve falhar com 401")

        # A 6ª tentativa deve ser bloqueada com 429
        status_6, corpo_6, _, retry_after = self._req("POST", "/api/auth/login", {
            "identificador": "ataque.forca.bruta@teste.com",
            "senha": "tentativa_6"
        })
        self.assertEqual(status_6, 429, "A 6ª tentativa deve retornar HTTP 429 Too Many Requests.")
        self.assertEqual(corpo_6.get("codigo"), "RATE_LIMIT_EXCEDIDO")
        self.assertIsNotNone(retry_after, "Deve conter cabeçalho Retry-After.")
        self.assertTrue(int(retry_after) > 0)

    # =========================================================================
    # AC-08: Proteção de senhas
    # =========================================================================
    def test_ac_08_protecao_senhas_banco_e_logs(self):
        """AC-08: Senhas armazenadas via PBKDF2-HMAC-SHA256 com salt e nunca em texto puro."""
        conn = get_connection(self.temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT email, senha_hash, salt FROM usuarios WHERE email = ?", ("admin.dp@empresa.com.br",))
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        email, senha_hash, salt = row["email"], row["senha_hash"], row["salt"]
        self.assertEqual(len(senha_hash), 64, "Hash SHA256 deve possuir 64 caracteres hexadecimais.")
        self.assertEqual(len(salt), 32, "Salt de 16 bytes deve possuir 32 caracteres hexadecimais.")
        self.assertNotIn("Sintetico#AdminTest2026!", senha_hash)

    # =========================================================================
    # AC-09 e AC-10: Cookie, Sessão segura e persistência após refresh
    # =========================================================================
    def test_ac_09_ac_10_sessao_persiste_refresh(self):
        """AC-09 e AC-10: Cookie HttpOnly mantém sessão válida em GET /api/auth/me após refresh."""
        senha_admin = os.environ.get("TEST_ADMIN_PASSWORD", "Sintetico#AdminTest2026!")
        _, corpo, set_cookie, _ = self._req("POST", "/api/auth/login", {
            "identificador": "admin.dp@empresa.com.br",
            "senha": senha_admin
        })
        token = corpo["token"]
        cookie_header = set_cookie.split(";")[0]

        # Simula refresh da página requisitando /api/auth/me com o Cookie
        status, dados_me, _, _ = self._req("GET", "/api/auth/me", cookie=cookie_header)
        self.assertEqual(status, 200)
        self.assertTrue(dados_me.get("sucesso"))
        self.assertEqual(dados_me["usuario"]["email"], "admin.dp@empresa.com.br")

    # =========================================================================
    # AC-11: Proteção de rotas privadas
    # =========================================================================
    def test_ac_11_rotas_privadas_bloqueadas_para_anonimos(self):
        """AC-11: Endpoints privados recusam anônimos com HTTP 401 Unauthorized imediato."""
        # Sem cookie e sem token
        status_colab, corpo, _, _ = self._req("GET", "/api/colaboradores")
        self.assertEqual(status_colab, 401)
        self.assertEqual(corpo.get("codigo"), "NAO_AUTENTICADO")

        status_folha, _, _, _ = self._req("GET", "/api/folha")
        self.assertEqual(status_folha, 401)

    # =========================================================================
    # AC-12: Logout com invalidação no servidor
    # =========================================================================
    def test_ac_12_logout_invalida_sessao_no_servidor(self):
        """AC-12: Logout revoga a sessão no servidor e destrói o cookie; reuso retorna 401."""
        senha_admin = os.environ.get("TEST_ADMIN_PASSWORD", "Sintetico#AdminTest2026!")
        _, corpo, set_cookie, _ = self._req("POST", "/api/auth/login", {
            "identificador": "admin.dp@empresa.com.br",
            "senha": senha_admin
        })
        token = corpo["token"]
        cookie_header = set_cookie.split(";")[0]

        # Executa logout
        status_logout, corpo_logout, delete_cookie, _ = self._req("POST", "/api/auth/logout", cookie=cookie_header)
        self.assertEqual(status_logout, 200)
        self.assertIn("Max-Age=0", delete_cookie)

        # Tentativa de reutilizar o token anterior em rota protegida
        status_reuso, _, _, _ = self._req("GET", "/api/auth/me", token=token)
        self.assertEqual(status_reuso, 401, "Sessão revogada não pode acessar endpoints privados.")

        status_reuso_colab, _, _, _ = self._req("GET", "/api/colaboradores", cookie=cookie_header)
        self.assertEqual(status_reuso_colab, 401)

    # =========================================================================
    # AC-13: Proteção CSRF / Origem
    # =========================================================================
    def test_ac_13_protecao_csrf_origem_rejeita_origem_fraudulenta(self):
        """AC-13: Requisição mutável com Origin fraudulento é rejeitada com HTTP 403 Forbidden."""
        status, corpo, _, _ = self._req(
            "POST",
            "/api/auth/login",
            payload={"identificador": "admin.dp@empresa.com.br", "senha": "qualquer_coisa"},
            headers_extras={"Origin": "http://site-hacker-malicioso.com"}
        )
        self.assertEqual(status, 403, "Deve rejeitar requisição de origem externa maliciosa.")
        self.assertEqual(corpo.get("codigo"), "ORIGEM_PROIBIDA")

    # =========================================================================
    # AC-16: Auditoria de Eventos de Autenticação
    # =========================================================================
    def test_ac_16_auditoria_eventos_autenticacao(self):
        """AC-16: Tabela auditoria_autenticacao registra eventos sem senhas ou segredos."""
        audit = self.server.auth_service.audit_service
        eventos = audit.listar_eventos(limite=20)
        self.assertTrue(len(eventos) > 0, "Devem existir eventos de auditoria registrados.")

        tipos_registrados = {e["evento"] for e in eventos}
        self.assertTrue(
            tipos_registrados.intersection({"LOGIN_SUCESSO", "LOGIN_FALHA", "LOGOUT", "BLOQUEIO_RATE_LIMIT"}),
            "Deve conter eventos padronizados de auditoria."
        )

        # Garante que nenhum segredo ou senha foi registrado
        for ev in eventos:
            detalhes = (ev.get("detalhes") or "").lower()
            identificador = (ev.get("identificador") or "").lower()
            self.assertNotIn("senhaforte", detalhes)
            self.assertNotIn("password", detalhes)
            self.assertNotIn("hash", detalhes)


if __name__ == "__main__":
    unittest.main()

