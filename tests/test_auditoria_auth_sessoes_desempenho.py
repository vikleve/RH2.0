"""
Suíte de Testes — Auditoria e Otimização de Autenticação, Sessões e Desempenho (RH2.0)
Cobre integralmente a Seção 8:
- Autenticação (credenciais corretas/incorretas, usuário inexistente, rate limit, falha temporária do banco, latência)
- Sessões (persistência, navegação entre módulos, renovação deslizante, expiração por inatividade,
  expiração máxima absoluta, logout, sessão revogada, sessões simultâneas, concorrência)
- Desempenho (tempo de resposta, contagem de queries por operação, cache de init_db/schema, Server-Timing)
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import http.client
import json
import os
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")

from backend.auth import AuthService, hash_token, resetar_cache_provisionamento
from backend.database import DatabaseUnavailableError, get_connection, init_db, resetar_cache_init_db
from backend.observabilidade import (
    finalizar_contexto_requisicao,
    iniciar_contexto_requisicao,
    obter_metricas_snapshot,
    resetar_metricas,
)
from backend.plataforma_service import PlataformaService
from backend.rate_limiter import get_rate_limiter
from backend.server import ApiColaboradorHandler
from backend.service import ColaboradorService


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class TestAuditoriaAuthSessoesDesempenho(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(prefix="rh20_audit_perf_", suffix=".db")
        os.close(fd)
        resetar_cache_init_db()
        resetar_cache_provisionamento()
        resetar_metricas()

        init_db(cls.db_path, auto_provision=True, force=True)
        cls.auth_service = AuthService(db_path=cls.db_path, auto_init=False)
        cls.colab_service = ColaboradorService(db_path=cls.db_path)
        cls.plat_service = PlataformaService(db_path=cls.db_path)

        cls.server = _ThreadedHTTPServer(("127.0.0.1", 0), ApiColaboradorHandler)
        cls.server.colab_service = cls.colab_service
        cls.server.auth_service = cls.auth_service
        cls.server.plataforma_service = cls.plat_service
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        try:
            os.remove(cls.db_path)
        except OSError:
            pass

    def setUp(self):
        get_rate_limiter().resetar()

    def _req(self, method: str, path: str, body: dict = None, headers: dict = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdrs = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"}
        if headers:
            hdrs.update(headers)
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        resp_headers = dict(resp.getheaders())
        conn.close()
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {"_raw": raw}
        return resp.status, data, resp_headers

    # ── 1. AUTENTICAÇÃO ───────────────────────────────────────────────────────

    def test_01_login_sucesso_cookie_seguro_e_server_timing(self):
        t0 = time.perf_counter()
        status, data, hdrs = self._req(
            "POST",
            "/api/auth/login",
            {"identificador": "admin.dp@empresa.com.br", "senha": os.environ["ADMIN_INITIAL_PASSWORD"]},
        )
        dur_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(status, 200)
        self.assertTrue(data.get("sucesso"))
        self.assertTrue(data.get("token"))
        self.assertIn("Server-Timing", hdrs)

        cookie = hdrs.get("Set-Cookie", "")
        self.assertIn("session_token=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Max-Age=", cookie)
        # Garante que não há duplicação de atributos no Set-Cookie
        self.assertEqual(cookie.count("HttpOnly"), 1)
        self.assertEqual(cookie.count("Path=/"), 1)
        self.assertLess(dur_ms, 2000.0, f"Login excedeu tempo esperado: {dur_ms:.1f}ms")

    def test_02_login_credenciais_incorretas_e_usuario_inexistente_sem_enumeracao(self):
        s1, d1, _ = self._req("POST", "/api/auth/login", {"identificador": "admin.dp@empresa.com.br", "senha": "errada"})
        s2, d2, _ = self._req("POST", "/api/auth/login", {"identificador": "naoexiste@empresa.com.br", "senha": "errada"})
        self.assertEqual(s1, 401)
        self.assertEqual(s2, 401)
        self.assertEqual(d1.get("mensagem"), d2.get("mensagem"))

    def test_03_rate_limit_bloqueia_com_429_e_retry_after(self):
        for _ in range(5):
            st, _, _ = self._req(
                "POST",
                "/api/auth/login",
                {"identificador": "admin.dp@empresa.com.br", "senha": "senha_invalida"},
                headers={"X-Forwarded-For": "198.51.100.77"},
            )
            self.assertEqual(st, 401)

        st_bloq, data_bloq, hdrs_bloq = self._req(
            "POST",
            "/api/auth/login",
            {"identificador": "admin.dp@empresa.com.br", "senha": os.environ["ADMIN_INITIAL_PASSWORD"]},
            headers={"X-Forwarded-For": "198.51.100.77"},
        )
        self.assertEqual(st_bloq, 429)
        self.assertEqual(data_bloq.get("codigo"), "RATE_LIMIT_EXCEDIDO")
        self.assertIn("Retry-After", hdrs_bloq)

    def test_04_falha_temporaria_banco_retorna_503_json_e_nao_401(self):
        _, token = self.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        with patch.object(self.auth_service, "validar_sessao", side_effect=DatabaseUnavailableError("Banco indisponível temporariamente.")):
            st, data, _ = self._req("GET", "/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(st, 503)
        self.assertEqual(data.get("codigo"), "BANCO_INDISPONIVEL")
        self.assertFalse(data.get("sucesso"))

    # ── 2. SESSÕES ────────────────────────────────────────────────────────────

    def test_05_persistencia_navegacao_e_renovacao_deslizante(self):
        _, token = self.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        token_hash = hash_token(token)

        # Simula 20 minutos transcorridos desde o login (acima do threshold padrão de 15 min)
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        vinte_min_atras = (datetime.now() - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
        expira_antigo = (datetime.now() + timedelta(minutes=100)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "UPDATE sessoes SET ultima_atividade = ?, expira_em = ? WHERE token = ?",
            (vinte_min_atras, expira_antigo, token_hash),
        )
        conn.commit()
        expira_antes = expira_antigo
        conn.close()

        # Recarrega /api/auth/me (como F5 ou monitoramento de atividade)
        st, data, hdrs = self._req("GET", "/api/auth/me", headers={"Cookie": f"session_token={token}"})
        self.assertEqual(st, 200)
        self.assertTrue(data.get("sessao_renovada"))
        self.assertIn("Set-Cookie", hdrs)

        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT expira_em FROM sessoes WHERE token = ?", (token_hash,))
        expira_depois = cur.fetchone()[0]
        conn.close()
        self.assertGreater(expira_depois, expira_antes)

        # Navegação entre módulos mantém a sessão válida
        for rota in ("/api/colaboradores", "/api/bi/indicadores"):
            st_mod, d_mod, _ = self._req("GET", rota, headers={"Cookie": f"session_token={token}"})
            self.assertEqual(st_mod, 200, f"Falha na rota {rota}: {d_mod}")

    def test_06_expiracao_por_inatividade_e_expiracao_maxima_absoluta(self):
        # Caso A: Expiração por inatividade (expira_em no passado)
        _, tok_idle = self.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        conn = get_connection(self.db_path)
        passado = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE sessoes SET expira_em = ? WHERE token = ?", (passado, hash_token(tok_idle)))
        conn.commit()
        conn.close()
        self.assertIsNone(self.auth_service.validar_sessao(tok_idle))

        # Caso B: Expiração máxima absoluta (expira_em ainda no futuro, mas expira_absoluto_em vencido)
        _, tok_abs = self.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        conn = get_connection(self.db_path)
        futuro = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE sessoes SET expira_em = ?, expira_absoluto_em = ? WHERE token = ?",
            (futuro, passado, hash_token(tok_abs)),
        )
        conn.commit()
        conn.close()
        self.assertIsNone(self.auth_service.validar_sessao(tok_abs))

    def test_07_logout_e_bloqueio_de_sessao_revogada(self):
        _, token = self.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        st_out, data_out, hdrs_out = self._req("POST", "/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(st_out, 200)
        self.assertTrue(data_out.get("sucesso"))
        self.assertIn("Max-Age=0", hdrs_out.get("Set-Cookie", ""))

        st_reuso, _, _ = self._req("GET", "/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(st_reuso, 401)

    def test_08_multiplas_sessoes_e_requisicoes_simultaneas(self):
        # Duas abas/dispositivos do mesmo usuário não se derrubam mutuamente
        _, tok1 = self.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        _, tok2 = self.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        self.assertIsNotNone(self.auth_service.validar_sessao(tok1))
        self.assertIsNotNone(self.auth_service.validar_sessao(tok2))

        def chamar_me(tok):
            st, data, _ = self._req("GET", "/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
            return st, data.get("sucesso")

        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = [ex.submit(chamar_me, tok1 if i % 2 == 0 else tok2) for i in range(12)]
            resultados = [f.result() for f in futs]

        for st, ok in resultados:
            self.assertEqual(st, 200)
            self.assertTrue(ok)

    # ── 3. DESEMPENHO E CONTAGEM DE QUERIES ───────────────────────────────────

    def test_09_otimizacao_init_db_bi_e_listagem_colaboradores(self):
        # 1. init_db em processo já inicializado deve ser instantâneo (0 queries!)
        iniciar_contexto_requisicao("bench_init_db", "INTERNAL")
        t0 = time.perf_counter()
        init_db(self.db_path)
        dur_init_ms = (time.perf_counter() - t0) * 1000.0
        res_init = finalizar_contexto_requisicao(200)
        self.assertEqual(res_init["sql_count"], 0)
        self.assertLess(dur_init_ms, 5.0)

        # 2. BI consolidado deve executar no máximo 3 queries (antes: 13 queries!)
        iniciar_contexto_requisicao("bench_bi", "GET")
        bi = self.plat_service.obter_indicadores_bi()
        res_bi = finalizar_contexto_requisicao(200)
        self.assertIn("total_colaboradores_ativos", bi)
        self.assertLessEqual(res_bi["sql_count"], 3, f"BI executou queries demais: {res_bi['sql_count']}")

        # 3. ColaboradorService.listar() após warm-up de cache de coluna deve executar 1 única query
        self.colab_service.listar()  # aquece cache _COLUNA_CACHE
        iniciar_contexto_requisicao("bench_listar", "GET")
        self.colab_service.listar()
        res_list = finalizar_contexto_requisicao(200)
        self.assertEqual(res_list["sql_count"], 1, f"Listar executou {res_list['sql_count']} queries")

        # 4. Endpoint de observabilidade retorna métricas sem expor dados sensíveis
        _, tok = self.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        st_m, data_m, _ = self._req("GET", "/api/observabilidade/metricas", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(st_m, 200)
        self.assertIn("metricas", data_m)
        payload_str = json.dumps(data_m)
        self.assertNotIn(tok, payload_str)
        self.assertNotIn(os.environ["ADMIN_INITIAL_PASSWORD"], payload_str)

    def test_10_csrf_compativel_com_proxy_vercel_e_bloqueia_cross_site(self):
        from backend.csrf import get_csrf_protector
        csrf = get_csrf_protector()

        # Proxy Vercel: Origin corresponde a X-Forwarded-Host mesmo quando Host interno difere
        ok_vercel, _ = csrf.validar_requisicao(
            "POST",
            {
                "Origin": "https://rh2-0.vercel.app",
                "Host": "127.0.0.1:3000",
                "X-Forwarded-Host": "rh2-0.vercel.app",
                "Sec-Fetch-Site": "same-origin",
            },
            host_esperado="127.0.0.1:3000",
        )
        self.assertTrue(ok_vercel)

        # Ataque cross-site continua rigorosamente bloqueado
        ok_evil, _ = csrf.validar_requisicao(
            "POST",
            {
                "Origin": "https://atacante.evil.com",
                "Host": "rh2-0.vercel.app",
                "X-Forwarded-Host": "rh2-0.vercel.app",
                "Sec-Fetch-Site": "cross-site",
            },
            host_esperado="rh2-0.vercel.app",
        )
        self.assertFalse(ok_evil)


if __name__ == "__main__":
    unittest.main(verbosity=2)
