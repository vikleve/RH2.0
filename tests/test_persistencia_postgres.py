"""
Testes de configuracao de persistencia (RF-01, RF-02, RF-07, Teste E).

Nao dependem de um PostgreSQL real nem do driver psycopg2: o driver e simulado
para validar (a) ausencia de fallback silencioso para SQLite em producao,
(b) falha explicita e sem vazamento de credenciais quando o banco esta indisponivel.
A escrita/leitura real em PostgreSQL deve ser validada em ambiente com banco (ver docs).
"""
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import database as db  # noqa: E402

_VARS = ["DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING",
         "PGHOST", "PGDATABASE", "VERCEL", "VERCEL_ENV", "APP_ENV", "ENVIRONMENT", "NODE_ENV", "ENV"]


def _env(**extra):
    base = {k: v for k, v in os.environ.items() if k not in _VARS}
    base.update(extra)
    return mock.patch.dict(os.environ, base, clear=True)


class TestConfiguracaoBanco(unittest.TestCase):
    def test_producao_sem_database_url_falha_explicitamente(self):
        with _env(VERCEL="1"):
            with self.assertRaises(db.DatabaseConfigError):
                db.get_connection()

    def test_producao_via_app_env_sem_url_falha(self):
        with _env(APP_ENV="production"):
            with self.assertRaises(db.DatabaseConfigError):
                db.init_db(auto_provision=False)

    def test_desenvolvimento_sem_url_usa_sqlite(self):
        with _env():
            self.assertFalse(db._usar_postgres())

    def test_db_path_explicito_sempre_sqlite_mesmo_em_producao(self):
        with _env(VERCEL="1", DATABASE_URL="postgresql://u:p@h/db"):
            self.assertFalse(db._usar_postgres("/tmp/x.db"))

    def test_com_url_usa_postgres(self):
        with _env(VERCEL="1", DATABASE_URL="postgresql://u:p@h/db"):
            self.assertTrue(db._usar_postgres())

    def test_falha_de_conexao_nao_vaza_credenciais_e_nao_cai_em_sqlite(self):
        segredo = "SenhaSuperSecreta123"

        class FakeOperationalError(Exception):
            pass

        fake = types.ModuleType("psycopg2")
        fake.OperationalError = FakeOperationalError
        fake.InterfaceError = type("InterfaceError", (Exception,), {})

        def _connect(dsn):
            raise FakeOperationalError(f"could not connect to server using {dsn}")

        fake.connect = _connect
        with _env(VERCEL="1", DATABASE_URL=f"postgresql://user:{segredo}@db.exemplo.supabase.co:5432/postgres"):
            with mock.patch.dict(sys.modules, {"psycopg2": fake}):
                with self.assertRaises(db.DatabaseUnavailableError) as ctx:
                    db.get_connection()
        self.assertNotIn(segredo, str(ctx.exception))
        self.assertNotIn("supabase", str(ctx.exception))

    def test_dsn_recebe_sslmode_e_timeout(self):
        capturado = {}
        fake = types.ModuleType("psycopg2")
        fake.OperationalError = type("OperationalError", (Exception,), {})
        fake.InterfaceError = type("InterfaceError", (Exception,), {})
        fake.connect = lambda dsn: capturado.setdefault("dsn", dsn) or object()
        with _env(VERCEL="1", DATABASE_URL="postgres://u:p@db.exemplo.supabase.co:5432/postgres"):
            with mock.patch.dict(sys.modules, {"psycopg2": fake}):
                db.get_connection()
        self.assertTrue(capturado["dsn"].startswith("postgresql://"))
        self.assertIn("sslmode=require", capturado["dsn"])
        self.assertIn("connect_timeout=", capturado["dsn"])

    def test_erro_http_mapeia_banco_indisponivel_para_503(self):
        status, corpo = db.erro_http(db.DatabaseUnavailableError("indisponivel"))
        self.assertEqual(status, 503)
        self.assertFalse(corpo["sucesso"])
        self.assertEqual(corpo["codigo"], "BANCO_INDISPONIVEL")
        self.assertEqual(db.erro_http(ValueError("x"))[0], 500)

    def test_status_banco_sqlite_local(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            caminho = os.path.join(d, "t.db")
            db.init_db(caminho, auto_provision=False)
            st = db.status_banco(caminho)
        self.assertEqual(st["banco"], "sqlite")
        self.assertTrue(st["conectado"])


if __name__ == "__main__":
    unittest.main()
