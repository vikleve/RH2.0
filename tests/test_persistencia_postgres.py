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

_VARS = ["DATABASE_URL", "NEON_DATABASE_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING",
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

    def test_neon_database_url_reconhecida_com_provedor_e_pooling(self):
        url_neon = "postgresql://neondb_owner:npg_secretPass123@ep-cool-fog-123456-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
        with _env(VERCEL="1", DATABASE_URL=url_neon):
            self.assertTrue(db._usar_postgres())
            self.assertEqual(db.get_database_url(), url_neon)

            fake_conn = mock.MagicMock()
            fake_cursor = mock.MagicMock()
            fake_cursor.fetchone.return_value = [1]
            fake_conn.cursor.return_value = fake_cursor

            fake = types.ModuleType("psycopg2")
            fake.OperationalError = type("OperationalError", (Exception,), {})
            fake.InterfaceError = type("InterfaceError", (Exception,), {})
            fake.connect = lambda dsn: fake_conn

            with mock.patch.dict(sys.modules, {"psycopg2": fake}):
                st = db.status_banco()
            self.assertEqual(st["banco"], "postgresql")
            self.assertEqual(st["provedor"], "neon")
            self.assertTrue(st["pooled"])
            self.assertTrue(st["conectado"])
            self.assertTrue(st["producao"])

    def test_neon_database_url_variavel_alternativa(self):
        url_neon = "postgresql://neondb_owner:pass@ep-shiny-dew-654321-pooler.us-east-1.aws.neon.tech/neondb"
        with _env(VERCEL="1", NEON_DATABASE_URL=url_neon):
            self.assertTrue(db._usar_postgres())
            self.assertEqual(db.get_database_url(), url_neon)

    def test_neon_falha_de_conexao_nao_vaza_credenciais_nem_host(self):
        senha_neon = "SuperSecretNeonPass#2026"
        host_neon = "ep-cool-fog-123456-pooler.us-east-2.aws.neon.tech"

        class FakeOperationalError(Exception):
            pass

        fake = types.ModuleType("psycopg2")
        fake.OperationalError = FakeOperationalError
        fake.InterfaceError = type("InterfaceError", (Exception,), {})

        def _connect(dsn):
            raise FakeOperationalError(f"connection to server at '{host_neon}' failed: timeout with password {senha_neon}")

        fake.connect = _connect
        with _env(VERCEL="1", DATABASE_URL=f"postgresql://neondb_owner:{senha_neon}@{host_neon}/neondb?sslmode=require"):
            with mock.patch.dict(sys.modules, {"psycopg2": fake}):
                with self.assertRaises(db.DatabaseUnavailableError) as ctx:
                    db.get_connection()
                self.assertNotIn(senha_neon, str(ctx.exception))
                self.assertNotIn("neon.tech", str(ctx.exception))
                self.assertNotIn(host_neon, str(ctx.exception))

    def test_row_to_dict_converte_decimal_para_float(self):
        """Verifica que objetos Decimal retornados pelo PostgreSQL são convertidos para float."""
        from decimal import Decimal
        import json

        # Mock cursor com description e row com Decimals
        mock_cursor = mock.MagicMock()
        mock_cursor.description = [("id",), ("salario_base",), ("total_descontos",)]
        row = (1, Decimal("4500.50"), Decimal("612.35"))

        with mock.patch.object(db, "_usar_postgres", return_value=True):
            d = db.row_to_dict(mock_cursor, row)

        self.assertIsInstance(d["salario_base"], float)
        self.assertIsInstance(d["total_descontos"], float)
        self.assertEqual(d["salario_base"], 4500.50)
        self.assertEqual(d["total_descontos"], 612.35)

        # Garante que json.dumps serializa sem lançar TypeError
        serializado = json.dumps(d)
        self.assertIn('"salario_base": 4500.5', serializado)

    def test_init_db_cache_evita_overhead(self):
        """init_db utiliza cache para evitar reexecução desnecessária de DDL no mesmo banco."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            caminho = os.path.join(d, "cache_teste.db")
            db.init_db(caminho, auto_provision=False, force=True)
            self.assertIn(caminho, db._INITIALIZED_TARGETS)

            # Segunda chamada não reconecta para DDL se já inicializado
            with mock.patch.object(db, "get_connection") as mock_conn:
                db.init_db(caminho, auto_provision=False)
                mock_conn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
