# -*- coding: utf-8 -*-
"""
Suíte de Testes Automatizados para Benefícios — RN-036 a RN-038
Valida:
- RN-036: Elegibilidade (situação contratual, tipo de contrato, tempo mínimo, cargo, setor, faixa salarial, adesão/não adesão)
- RN-037: Participação do Colaborador (participação financeira, coparticipação, alteração de valores, suspensão, cancelamento)
- RN-038: Histórico de Benefícios (preservação temporal sem sobrescrever dados históricos, integração com folha, auditoria)
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")

from backend.database import init_db
from backend.plataforma_service import PlataformaService, PlataformaValidacaoException
from backend.service import ColaboradorService


class TestBeneficiosRN036RN038(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(prefix="rh20_rn_benef_", suffix=".db")
        os.close(fd)
        init_db(cls.db_path)
        cls.plataforma = PlataformaService(db_path=cls.db_path)
        cls.colab_svc = ColaboradorService(db_path=cls.db_path)

        # Cadastrar colaborador CLT Elegível
        cls.colab_clt = cls.colab_svc.cadastrar({
            "matricula": "BENEF-001",
            "nome_completo": "Carlos Roberto Elegível",
            "cpf": "52998224725",
            "rg": "12.345.678-9",
            "data_nascimento": "1990-05-15",
            "email": "carlos.elegivel@empresa.com.br",
            "cargo": "Analista de Sistemas",
            "setor": "Tecnologia",
            "departamento": "Tecnologia",
            "salario_base": 5000.00,
            "data_admissao": "2024-01-10",
            "tipo_contrato": "CLT",
            "situacao": "ativo",
        })

        # Cadastrar colaborador Inelegível (Estagiário, recente, outro setor)
        cls.colab_estagio = cls.colab_svc.cadastrar({
            "matricula": "BENEF-002",
            "nome_completo": "Mariana Estagiária Recente",
            "cpf": "39053344705",
            "rg": "98.765.432-1",
            "data_nascimento": "2003-08-20",
            "email": "mariana.estagio@empresa.com.br",
            "cargo": "Estagiário",
            "setor": "Marketing",
            "departamento": "Marketing",
            "salario_base": 1500.00,
            "data_admissao": (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d"),
            "tipo_contrato": "Estágio",
            "situacao": "ativo",
        })

        # Criar benefício no catálogo com regras configuráveis completas (RN-036)
        cls.benef_saude = cls.plataforma.criar_beneficio_catalogo({
            "codigo": "BEN-SAUDE-EXEC",
            "nome": "Plano de Saúde Executivo",
            "tipo": "plano_saude",
            "coparticipacao_tipo": "percentual",
            "coparticipacao_valor": 10.0,
            "valor_mensal_padrao": 600.0,
            "regra_elegibilidade": json.dumps({
                "situacoes_permitidas": ["ativo"],
                "tipos_contrato_permitidos": ["CLT"],
                "tempo_minimo_dias": 90,
                "setores_permitidos": ["Tecnologia", "Engenharia"],
                "cargos_permitidos": ["Analista de Sistemas", "Engenheiro"],
                "salario_minimo": 3000.00,
                "salario_maximo": 15000.00,
            }),
        })

        # Vínculo inicial criado no setUpClass para garantir independência entre testes (RN-037)
        cls.vinculo_base = cls.plataforma.vincular_beneficio_colaborador({
            "colaborador_id": cls.colab_clt["id"],
            "beneficio_id": cls.benef_saude["id"],
            "valor_mensal_base": 600.0,
            "coparticipacao_extra": 50.0,
            "vigencia_inicio": "2024-06-01",
        })
        cls.vinculo_id = cls.vinculo_base["id"]

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except OSError:
                pass

    def test_rn036_elegibilidade_colaborador_apto(self):
        """RN-036: Valida colaborador com situação, tipo de contrato, tempo de casa, setor, cargo e salário elegíveis."""
        res = self.plataforma.verificar_elegibilidade_beneficio(
            colaborador_id=self.colab_clt["id"],
            beneficio_id=self.benef_saude["id"],
        )
        self.assertTrue(res["elegivel"])
        self.assertEqual(len(res["motivos"]), 0)

    def test_rn036_elegibilidade_bloqueios_multiplos(self):
        """RN-036: Valida reprovação de elegibilidade por tipo de contrato, tempo mínimo, setor e salário."""
        res = self.plataforma.verificar_elegibilidade_beneficio(
            colaborador_id=self.colab_estagio["id"],
            beneficio_id=self.benef_saude["id"],
        )
        self.assertFalse(res["elegivel"])
        self.assertTrue(len(res["motivos"]) >= 3)
        motivos_txt = " ".join(res["motivos"])
        self.assertIn("Tipo de contrato", motivos_txt)
        self.assertIn("Tempo de casa", motivos_txt)
        self.assertIn("Setor", motivos_txt)

    def test_rn036_tentativa_vincular_colaborador_inelegivel_bloqueada(self):
        """RN-036: Bloqueia concessão de benefício se regras de elegibilidade forem violadas."""
        with self.assertRaises(PlataformaValidacaoException) as ctx:
            self.plataforma.vincular_beneficio_colaborador({
                "colaborador_id": self.colab_estagio["id"],
                "beneficio_id": self.benef_saude["id"],
                "valor_mensal_base": 600.0,
            })
        self.assertIn("inelegível", str(ctx.exception).lower())

    def test_rn037_participacao_financeira_e_coparticipacao(self):
        """RN-037: Calcula participação financeira do colaborador, coparticipação e custo da empresa."""
        vinc = self.vinculo_base
        self.assertIsNotNone(vinc["id"])
        self.assertEqual(vinc["custo_total_mes"], 600.0)
        # 10% de coparticipação (R$ 60,00) + R$ 50,00 coparticipação extra = R$ 110,00
        self.assertEqual(vinc["desconto_colaborador"], 110.0)
        self.assertEqual(vinc["custo_empresa"], 490.0)

    def test_rn037_alteracao_de_valores_com_historico(self):
        """RN-037 & RN-038: Alteração de valores recalcula custo e gera histórico sem sobrescrever dados anteriores."""
        vinc_atualizado = self.plataforma.atualizar_beneficio_colaborador(
            vinculo_id=self.vinculo_id,
            dados={
                "valor_mensal_base": 800.0,
                "coparticipacao_extra": 80.0,
                "motivo": "Reajuste anual da operadora de saúde",
            },
            usuario="Gestor_Beneficios",
        )
        self.assertEqual(vinc_atualizado["custo_total_mes"], 800.0)
        # 10% de R$ 800 = R$ 80 + R$ 80 = R$ 160
        self.assertEqual(vinc_atualizado["desconto_colaborador"], 160.0)
        self.assertEqual(vinc_atualizado["custo_empresa"], 640.0)

    def test_rn037_suspensao_beneficio(self):
        """RN-037: Suspende benefício mantendo registro histórico e alterando status para inativo."""
        vinc = self.plataforma.suspender_beneficio_colaborador(
            vinculo_id=self.vinculo_id,
            motivo="Licença não remunerada solicitada pelo colaborador",
            usuario="DP_Analista",
        )
        self.assertEqual(vinc["ativo"], 0)
        self.assertIsNotNone(vinc["vigencia_fim"])

    def test_rn037_cancelamento_beneficio(self):
        """RN-037: Cancela benefício com motivo de cancelamento registrado."""
        vinc = self.plataforma.cancelar_beneficio_colaborador(
            vinculo_id=self.vinculo_id,
            motivo="Solicitação formal de não adesão / cancelamento",
            usuario="DP_Analista",
        )
        self.assertEqual(vinc["ativo"], 0)
        self.assertEqual(vinc["optante"], 0)

    def test_rn038_historico_completo_preservado(self):
        """RN-038: Verifica que todo o ciclo de concessão, alteração, suspensão e cancelamento está na linha do tempo."""
        historico = self.plataforma.listar_historico_beneficios_colaborador(
            colaborador_id=self.colab_clt["id"],
            vinculo_id=self.vinculo_id,
        )
        self.assertTrue(len(historico) >= 4)
        operacoes = [h["operacao"] for h in historico]
        self.assertIn("CONCESSAO", operacoes)
        self.assertIn("ALTERACAO_VALOR", operacoes)
        self.assertIn("SUSPENSAO", operacoes)
        self.assertIn("CANCELAMENTO", operacoes)

        # Checar que os valores anteriores e novos foram preservados
        hist_alt = [h for h in historico if h["operacao"] == "ALTERACAO_VALOR"][0]
        self.assertEqual(hist_alt["valor_anterior"], 600.0)
        self.assertEqual(hist_alt["valor_novo"], 800.0)

    def test_rn038_auditoria_operacoes_beneficios(self):
        """RN-038: Comprova auditoria das operações de concessão e alteração de benefícios."""
        logs = self.plataforma.listar_auditoria(modulo="Beneficios")
        self.assertTrue(len(logs) >= 3)
        operacoes_auditadas = {l["operacao"] for l in logs}
        self.assertTrue({"inclusao", "alteracao", "suspensao"}.issubset(operacoes_auditadas))


if __name__ == "__main__":
    unittest.main()
