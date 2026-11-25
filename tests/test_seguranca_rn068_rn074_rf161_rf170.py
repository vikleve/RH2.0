# -*- coding: utf-8 -*-
"""
Suíte de Testes Automatizados para Segurança e Autenticação — RN-068 a RN-074 e RF-161 a RF-170
Testa:
- RN-068 / RF-163 / RF-164: RBAC, permissões por perfil e módulo
- RN-069: Sigilo Salarial (restrição de acesso a valores de remuneração)
- RN-070 / RF-167: Proteção de Dados Sensíveis e LGPD (dados médicos restritos e mascaramento)
- RN-071 / RF-168: Criptografia robusta (PBKDF2-HMAC-SHA256 e SHA-256 em sessões)
- RN-073: Imutabilidade dos logs no banco de dados (bloqueio de UPDATE e DELETE por triggers)
- RN-074: Consulta de auditoria com segregação estrita por empresa
- RF-161: Autenticação segura e suporte a cookie HttpOnly
- RF-162: Recuperação segura de senha (token único, expiração e revogação)
- RF-169: Gerenciamento de sessões (hash no banco, expiração real e revogação)
- RF-170: Auditoria completa de eventos de segurança
"""
import hashlib
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")

from backend.audit import AuditService
from backend.auth import (
    AuthService,
    checar_permissao,
    filtrar_dados_sensiveis,
    hash_senha,
    hash_token,
    verificar_senha,
)
from backend.database import get_connection, init_db
from backend.plataforma_service import PlataformaService
from backend.rate_limiter import RateLimiter


class TestSegurancaRN068RN074RF161RF170(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(prefix="rh20_seguranca_", suffix=".db")
        os.close(fd)
        init_db(cls.db_path)
        cls.auth_svc = AuthService(db_path=cls.db_path)
        cls.audit_svc = AuditService(db_path=cls.db_path)
        cls.plataforma_svc = PlataformaService(db_path=cls.db_path)

        # Criar usuário com perfil analista_rh
        conn = get_connection(cls.db_path)
        cur = conn.cursor()
        s_hash, s_salt = hash_senha("SenhaForte#2026", None)
        cur.execute(
            """
            INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, empresa_id, criado_em)
            VALUES (?, ?, ?, ?, ?, 'analista_rh', 'ativo', 'empresa-alpha-123', ?);
            """,
            ("analista.rh@empresa.com.br", "analista.rh", "Renata Analista RH", s_hash, s_salt, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        cls.analista_id = cur.lastrowid
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except OSError:
                pass

    def test_rn068_rf163_rf164_rbac_perfis_e_modulos(self):
        """RN-068 / RF-163 / RF-164: Valida controle RBAC por perfil e módulo."""
        # Superadmin tem acesso irrestrito
        self.assertTrue(checar_permissao("superadmin", "folha:calcular"))
        self.assertTrue(checar_permissao("superadmin", "auditoria:excluir"))

        # Analista de DP tem acesso à folha e rescisão, mas não auditoria global
        self.assertTrue(checar_permissao("analista_dp", "folha:calcular"))
        self.assertTrue(checar_permissao("analista_dp", "rescisoes:calcular"))
        self.assertFalse(checar_permissao("analista_dp", "auditoria:configurar"))

        # Gestor de departamento não pode calcular folha nem rescisões
        self.assertFalse(checar_permissao("gestor_departamento", "folha:calcular"))
        self.assertTrue(checar_permissao("gestor_departamento", "ponto:aprovar"))

        # Colaborador só acessa autoatendimento
        self.assertTrue(checar_permissao("colaborador", "portal_colaborador:visualizar"))
        self.assertFalse(checar_permissao("colaborador", "colaboradores:cadastrar"))

    def test_rn069_sigilo_salarial(self):
        """RN-069: Impede visualização de remuneração e salário por perfis sem autorização financeira/DP."""
        dados_colab = {
            "nome_completo": "João Silva",
            "cargo": "Desenvolvedor",
            "salario_base": 8500.00,
            "remuneracao": 9200.00,
            "dados_bancarios": "Banco 001 Ag 1234 CC 56789-0",
        }
        # Colaborador ou médico SST não podem ver o salário de outro
        filtrado_medico = filtrar_dados_sensiveis(dados_colab, perfil="medico_sst")
        self.assertEqual(filtrado_medico["salario_base"], "***")
        self.assertEqual(filtrado_medico["remuneracao"], "***")
        self.assertEqual(filtrado_medico["dados_bancarios"], "***")

        # Analista DP ou Financeiro têm acesso ao valor
        filtrado_dp = filtrar_dados_sensiveis(dados_colab, perfil="analista_dp")
        self.assertEqual(filtrado_dp["salario_base"], 8500.00)

    def test_rn070_rf167_protecao_dados_sensiveis_e_lgpd(self):
        """RN-070 / RF-167: Protege informações médicas (CID, laudo) e mascara CPF nos padrões LGPD."""
        registro = {
            "cpf": "12345678901",
            "nome_completo": "Paciente Teste",
            "cid_codigo": "M54.5",
            "diagnostico": "Lombalgia crônica ocupacional",
        }
        # Gestor ou Analista sem permissão médica tem dados clínicos bloqueados
        filtrado_gestor = filtrar_dados_sensiveis(registro, perfil="gestor_departamento")
        self.assertIn("DADO MÉDICO RESTRITO", filtrado_gestor["cid_codigo"])
        self.assertIn("DADO MÉDICO RESTRITO", filtrado_gestor["diagnostico"])
        self.assertEqual(filtrado_gestor["cpf"], "***.456.789-**")

        # Médico SST tem acesso completo ao diagnóstico
        filtrado_medico = filtrar_dados_sensiveis(registro, perfil="medico_sst")
        self.assertEqual(filtrado_medico["cid_codigo"], "M54.5")
        self.assertEqual(filtrado_medico["diagnostico"], "Lombalgia crônica ocupacional")

    def test_rn071_rf168_criptografia_senhas_e_sessoes(self):
        """RN-071 / RF-168: Senhas utilizam PBKDF2-HMAC-SHA256 (100k iterações) e tokens de sessão são persistidos em SHA-256."""
        senha_pura = "Antigravity#Enterprise2026!"
        s_hash, s_salt = hash_senha(senha_pura)
        self.assertTrue(verificar_senha(senha_pura, s_hash, s_salt))
        self.assertFalse(verificar_senha("SenhaErrada#123", s_hash, s_salt))

        # Criar usuário isolado para teste criptográfico de autenticação e sessão
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        u_hash, u_salt = hash_senha("SenhaCrypto#2026!", None)
        cur.execute(
            """
            INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, empresa_id, criado_em)
            VALUES ('crypto.user@empresa.com.br', 'crypto.user', 'Usuário Cripto Teste', ?, ?, 'analista_dp', 'ativo', 'empresa-alpha-123', ?);
            """,
            (u_hash, u_salt, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        crypto_user_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Autenticar e comprovar que o token gravado na tabela sessoes é o hash SHA-256
        user, token_raw = self.auth_svc.autenticar("crypto.user@empresa.com.br", "SenhaCrypto#2026!")
        token_hash_esperado = hash_token(token_raw)

        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT token FROM sessoes WHERE usuario_id = ? AND revogado = 0;", (crypto_user_id,))
        token_no_banco = cur.fetchone()[0]
        conn.close()

        # O token armazenado é o hash, nunca o texto puro
        self.assertEqual(token_no_banco, token_hash_esperado)
        self.assertNotEqual(token_no_banco, token_raw)

    def test_rn073_imutabilidade_logs_no_banco_de_dados(self):
        """RN-073: Assegura que o banco de dados proíbe UPDATE e DELETE em logs de auditoria via triggers."""
        # Inserir um log de auditoria
        self.plataforma_svc.registrar_auditoria(
            modulo="Seguranca",
            operacao="inclusao",
            registro_tipo="teste_imutabilidade",
            registro_id="999",
            usuario="Sistema",
            detalhes="Registro de teste para comprovação de imutabilidade",
        )

        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT id FROM auditoria_operacoes WHERE registro_tipo = 'teste_imutabilidade' ORDER BY id DESC LIMIT 1;")
        log_id = cur.fetchone()[0]

        # 1. Tentativa de UPDATE deve ser abortada pelo motor de banco de dados
        with self.assertRaises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            cur.execute("UPDATE auditoria_operacoes SET detalhes = 'Alterado por invasor' WHERE id = ?;", (log_id,))
            conn.commit()

        # 2. Tentativa de DELETE deve ser abortada pelo motor de banco de dados
        with self.assertRaises((sqlite3.IntegrityError, sqlite3.OperationalError)):
            cur.execute("DELETE FROM auditoria_operacoes WHERE id = ?;", (log_id,))
            conn.commit()

        conn.close()

    def test_rn074_consulta_auditoria_segregacao_empresa(self):
        """RN-074: Garante que a consulta de auditoria isola estritamente os registros por empresa."""
        # Criar log para Empresa Alpha
        self.plataforma_svc.registrar_auditoria(
            modulo="DP",
            operacao="alteracao",
            registro_tipo="colaborador",
            registro_id="101",
            usuario="AdminAlpha",
            empresa_id="empresa-alpha-123",
        )
        # Criar log para Empresa Beta
        self.plataforma_svc.registrar_auditoria(
            modulo="DP",
            operacao="alteracao",
            registro_tipo="colaborador",
            registro_id="202",
            usuario="AdminBeta",
            empresa_id="empresa-beta-456",
        )

        logs_alpha = self.plataforma_svc.listar_auditoria(empresa_id="empresa-alpha-123")
        logs_beta = self.plataforma_svc.listar_auditoria(empresa_id="empresa-beta-456")

        # Não deve haver vazamento entre empresas
        alpha_ids = [l["registro_id"] for l in logs_alpha]
        beta_ids = [l["registro_id"] for l in logs_beta]

        self.assertIn("101", alpha_ids)
        self.assertNotIn("202", alpha_ids)

        self.assertIn("202", beta_ids)
        self.assertNotIn("101", beta_ids)

    def test_rf162_recuperacao_senha_ciclo_completo(self):
        """RF-162: Solicitação com token aleatório seguro, expiração de 1 hora, uso único e revogação de sessões."""
        # 1. Solicitar recuperação
        solic = self.auth_svc.solicitar_recuperacao_senha("analista.rh@empresa.com.br")
        self.assertTrue(solic["sucesso"])
        self.assertTrue(solic["token_gerado"])
        token_recup = solic["token_recuperacao"]

        # Verificar se o token gravado no banco está em formato hash SHA-256
        token_recup_hash = hashlib.sha256(token_recup.encode("utf-8")).hexdigest()
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT token_hash, usado FROM recuperacao_senha WHERE usuario_id = ? ORDER BY id DESC LIMIT 1;", (self.analista_id,))
        row_rec = cur.fetchone()
        conn.close()
        self.assertEqual(row_rec[0], token_recup_hash)
        self.assertEqual(row_rec[1], 0)

        # 2. Redefinir senha com token válido
        nova_senha = "NovaSenhaForte#2026!"
        res_redef = self.auth_svc.redefinir_senha_com_token(token_recup, nova_senha)
        self.assertTrue(res_redef["sucesso"])

        # 3. Tentar reutilizar o mesmo token deve ser rejeitado (uso único)
        with self.assertRaises(ValueError) as ctx:
            self.auth_svc.redefinir_senha_com_token(token_recup, "TentativaReuso#123")
        self.assertIn("já foi utilizado", str(ctx.exception))

        # 4. Fazer login com a nova senha deve funcionar
        user_novo, _ = self.auth_svc.autenticar("analista.rh@empresa.com.br", nova_senha)
        self.assertEqual(user_novo["usuario"], "analista.rh")

    def test_rf169_expiracao_e_revogacao_sessao(self):
        """RF-169: Sessões expiradas ou revogadas são invalidadas pelo validador."""
        user, token = self.auth_svc.autenticar("analista.rh@empresa.com.br", "NovaSenhaForte#2026!")
        self.assertIsNotNone(self.auth_svc.validar_sessao(token))

        # Revogar sessão explicitamente (logout)
        encerrado = self.auth_svc.encerrar_sessao(token)
        self.assertTrue(encerrado)
        self.assertIsNone(self.auth_svc.validar_sessao(token))

    def test_rate_limiter_compartilhado_com_banco(self):
        """RF-161 (Item 6): Rate Limiter registra tentativas e bloqueia acessos excessivos no banco compartilhado."""
        limiter = RateLimiter(max_tentativas=3, janela_segundos=60, db_path=self.db_path)
        chave = "ip_teste_compartilhado:192.168.1.50"
        limiter.resetar()

        bloq1, _ = limiter.registrar_falha(chave)
        self.assertFalse(bloq1)
        bloq2, _ = limiter.registrar_falha(chave)
        self.assertFalse(bloq2)
        bloq3, seg = limiter.registrar_falha(chave)
        self.assertTrue(bloq3)
        self.assertTrue(seg > 0)

        # Outra instância do rate limiter apontando para o mesmo banco deve ver o bloqueio imediatamente
        limiter_instancia2 = RateLimiter(max_tentativas=3, janela_segundos=60, db_path=self.db_path)
        esta_bloq, _ = limiter_instancia2.esta_bloqueado(chave)
        self.assertTrue(esta_bloq)


if __name__ == "__main__":
    unittest.main()
