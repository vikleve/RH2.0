# -*- coding: utf-8 -*-
"""
Suíte de Testes Automatizados para Auditoria e Trilha de Rastreabilidade — RF-191 a RF-200
Testa:
- RF-191: Log de Inclusão
- RF-192: Log de Alteração (valor anterior vs novo / diff)
- RF-193: Log de Exclusão e inativação
- RF-194: Histórico de Cálculos (memória de cálculo)
- RF-195: Histórico de Integrações (eSocial, bancária)
- RF-196: Histórico de Aprovações e Reprovações
- RF-197: Histórico de Reabertura
- RF-198: Relatório de Auditoria estruturado
- RF-199: Pesquisa de Logs com filtros e paginação
- RF-200: Trilha Completa de Rastreabilidade com encadeamento criptográfico inviolável (hash chaining) e detecção de adulteração
"""
import os
import sqlite3
import sys
import tempfile
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")

from backend.audit import AuditService
from backend.database import get_connection, init_db
from backend.plataforma_service import PlataformaService


class TestAuditoriaRF191RF200(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(prefix="rh20_audit_suite_", suffix=".db")
        os.close(fd)
        init_db(cls.db_path)
        cls.audit_svc = AuditService(db_path=cls.db_path)
        cls.plataforma_svc = PlataformaService(db_path=cls.db_path)
        cls.empresa_teste = "empresa-audit-999"

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except OSError:
                pass

    def test_rf191_log_de_inclusao(self):
        """RF-191: Registra log de inclusão com identificador, usuário, módulo e hash criptográfico."""
        res = self.audit_svc.registrar_operacao(
            modulo="Colaboradores",
            operacao="inclusao",
            registro_tipo="colaborador",
            registro_id="COLAB-1001",
            usuario="Auditor_RH",
            valor_novo={"nome": "João Inclusão", "cargo": "Desenvolvedor"},
            empresa_id=self.empresa_teste,
            detalhes="Cadastro inicial de colaborador",
        )
        self.assertTrue(res["sucesso"])
        self.assertIsNotNone(res["hash_atual"])
        self.assertIsNotNone(res["hash_anterior"])

    def test_rf192_log_de_alteracao_com_diff(self):
        """RF-192: Registra log de alteração com valor_anterior e valor_novo preservados."""
        res = self.audit_svc.registrar_operacao(
            modulo="Cargos_Salarios",
            operacao="alteracao",
            registro_tipo="salario",
            registro_id="COLAB-1001",
            campo_alterado="salario_base",
            valor_anterior="5000.00",
            valor_novo="6500.00",
            usuario="Diretor_RH",
            empresa_id=self.empresa_teste,
            detalhes="Promoção para pleno",
        )
        self.assertTrue(res["sucesso"])

        logs = self.audit_svc.listar_auditoria(
            empresa_id=self.empresa_teste,
            modulo="Cargos_Salarios",
            operacao="alteracao",
        )
        self.assertTrue(logs["total"] >= 1)
        item = logs["itens"][0]
        self.assertEqual(item["valor_anterior"], "5000.00")
        self.assertEqual(item["valor_novo"], "6500.00")
        self.assertEqual(item["campo_alterado"], "salario_base")

    def test_rf193_log_de_exclusao(self):
        """RF-193: Registra exclusão ou inativação de registro com justificativa."""
        res = self.audit_svc.registrar_operacao(
            modulo="Beneficios",
            operacao="exclusao",
            registro_tipo="beneficio_colaborador",
            registro_id="VINC-55",
            usuario="DP_Analista",
            empresa_id=self.empresa_teste,
            detalhes="Exclusão de benefício por cancelamento formal",
        )
        self.assertTrue(res["sucesso"])

    def test_rf194_historico_de_calculos(self):
        """RF-194: Registra memória de cálculo detalhada em logs de auditoria."""
        memoria = {
            "salario_base": 6000.00,
            "dias_trabalhados": 30,
            "inss": 651.89,
            "irrf": 482.10,
            "fgts": 480.00,
            "liquido": 4866.01,
        }
        res = self.audit_svc.registrar_operacao(
            modulo="Folha",
            operacao="calculo_folha",
            registro_tipo="folha_pagamento",
            registro_id="FOLHA-2026-02-001",
            usuario="MotorCalculo",
            valor_novo=memoria,
            empresa_id=self.empresa_teste,
            detalhes="Cálculo mensal automatizado com tabelas 2026",
        )
        self.assertTrue(res["sucesso"])

    def test_rf195_historico_de_integracoes(self):
        """RF-195: Registra envios e retornos de integração externa (eSocial / Bancária)."""
        res = self.audit_svc.registrar_operacao(
            modulo="eSocial",
            operacao="transmissao_evento",
            registro_tipo="evento_s2200",
            registro_id="EVT-S2200-99",
            usuario="eSocial_Worker",
            valor_anterior="status: gerado",
            valor_novo="status: pendente_credenciais_oficiais",
            empresa_id=self.empresa_teste,
            detalhes="Tentativa de envio oficial S-2200",
        )
        self.assertTrue(res["sucesso"])

    def test_rf196_historico_de_aprovacoes(self):
        """RF-196: Registra workflow de aprovações e reprovações de gestores e RH."""
        res = self.audit_svc.registrar_operacao(
            modulo="Ponto",
            operacao="aprovacao_ajuste",
            registro_tipo="ajuste_ponto",
            registro_id="AJUSTE-77",
            usuario="Gestor_Operacoes",
            valor_anterior="pendente",
            valor_novo="aprovado",
            empresa_id=self.empresa_teste,
            detalhes="Aprovado ajuste de esquecimento de marcação",
        )
        self.assertTrue(res["sucesso"])

    def test_rf197_historico_de_reabertura(self):
        """RF-197: Registra formalmente reabertura de folhas ou períodos fechados."""
        res = self.audit_svc.registrar_operacao(
            modulo="Folha",
            operacao="reabertura_competencia",
            registro_tipo="competencia",
            registro_id="2026-01",
            usuario="Gerente_DP",
            valor_anterior="fechada",
            valor_novo="reaberta",
            empresa_id=self.empresa_teste,
            detalhes="Reabertura excepcional para retificação de rescisão",
        )
        self.assertTrue(res["sucesso"])

    def test_rf198_rf199_relatorio_e_pesquisa_de_logs_paginada(self):
        """RF-198 & RF-199: Pesquisa avançada de auditoria com filtros por módulo, operação, usuário e paginação."""
        relatorio = self.audit_svc.listar_auditoria(
            empresa_id=self.empresa_teste,
            modulo="Folha",
            pagina=1,
            limite=10,
        )
        self.assertTrue(relatorio["total"] >= 2)
        self.assertEqual(relatorio["pagina"], 1)
        self.assertEqual(relatorio["limite"], 10)
        self.assertTrue(len(relatorio["itens"]) >= 2)

        # Checar consistência dos campos retornados
        item = relatorio["itens"][0]
        for campo in ["id", "modulo", "operacao", "registro_tipo", "registro_id", "hash_anterior", "hash_atual", "criado_em"]:
            self.assertIn(campo, item)

    def test_rf200_trilha_rastreabilidade_e_deteccao_adulteracao(self):
        """RF-200: Valida cadeia criptográfica inviolável de logs (hash chaining) e capacidade de detectar violações."""
        # 1. A cadeia atual deve estar 100% íntegra
        verif_ok = self.audit_svc.verificar_integridade_trilha(empresa_id=self.empresa_teste)
        self.assertTrue(verif_ok["integro"])
        self.assertTrue(verif_ok["total_registros_verificados"] >= 5)

        # 2. Simular adulteração direta no banco (como se um atacante alterasse os valores no SQLite contornando a aplicação)
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        # Desativar trigger temporariamente na conexão do atacante para forçar adulteração de teste
        cur.execute("DROP TRIGGER IF EXISTS trg_auditoria_operacoes_no_update;")
        cur.execute(
            "UPDATE auditoria_operacoes SET valor_novo = '99999.99' WHERE registro_id = 'COLAB-1001' AND operacao = 'alteracao';"
        )
        conn.commit()
        conn.close()

        # 3. O verificador de integridade criptográfica DEVE detectar a violação imediatamente
        verif_tampered = self.audit_svc.verificar_integridade_trilha(empresa_id=self.empresa_teste)
        self.assertFalse(verif_tampered["integro"])
        self.assertIn("Adulteração detectada", verif_tampered["mensagem"])


if __name__ == "__main__":
    unittest.main()
