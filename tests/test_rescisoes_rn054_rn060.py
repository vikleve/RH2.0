# -*- coding: utf-8 -*-
"""
Suíte de Testes Automatizados para Rescisões Contratuais — RN-054 a RN-060
Testa de forma independente cada modalidade legal:
- RN-054: Rescisão Sem Justa Causa
- RN-055: Pedido de Demissão
- RN-056: Justa Causa
- RN-057: Acordo Trabalhista (Art. 484-A)
- RN-058: Rescisão Indireta
- RN-059: Culpa Recíproca (Art. 484 CLT, Súmula 14 TST, Lei 8.036/90 art. 18 § 2º)
- RN-060: Término de Contrato e Rescisões Antecipadas de Contrato a Prazo (Arts. 479 e 480 da CLT)
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")

from backend.database import init_db
from backend.rescisao_service import RescisaoService, MODALIDADES_CANONICAS
from backend.service import ColaboradorService
from backend.sst_service import SSTService as SstService


class TestRescisoesRN054RN060(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.db_path = tempfile.mkstemp(prefix="rh20_rn_rescisao_", suffix=".db")
        os.close(fd)
        init_db(cls.db_path)
        cls.rescisao_svc = RescisaoService(db_path=cls.db_path)
        cls.colab_svc = ColaboradorService(db_path=cls.db_path)
        cls.sst_svc = SstService(db_path=cls.db_path)

        # Cadastrar colaborador para os testes rescisórios com 2 anos de casa
        cls.colab = cls.colab_svc.cadastrar({
            "matricula": "RESC-001",
            "nome_completo": "Fernando Rescisório Silva",
            "cpf": "52998224725",
            "rg": "12.345.678-9",
            "data_nascimento": "1988-06-14",
            "email": "fernando.rescisao@empresa.com.br",
            "cargo": "Analista Pleno",
            "setor": "Operações",
            "departamento": "Operações",
            "salario_base": 6000.00,
            "data_admissao": "2024-01-15",
            "tipo_contrato": "CLT",
            "situacao": "ativo",
        })

        # Registrar ASO Demissional APTO prévio para permitir homologação
        cls.sst_svc.registrar_aso(
            colaborador_id=cls.colab["id"],
            tipo_aso="Demissional",
            data_emissao="2026-02-10",
            data_validade="2027-02-10",
            resultado="apto",
            medico_nome="Dr. Arnaldo Silva",
            medico_crm="123456",
            medico_uf="SP",
        )

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except OSError:
                pass

    def test_modalidades_canonicas_inclui_culpa_reciproca(self):
        """Verifica se a modalidade culpa_reciproca consta expressamente no mapeamento de modalidades canônicas."""
        self.assertIn("culpa_reciproca", MODALIDADES_CANONICAS)
        self.assertEqual(MODALIDADES_CANONICAS["culpa_reciproca"], "culpa_reciproca")

    def test_rn054_rescisao_sem_justa_causa(self):
        """RN-054: Rescisão Sem Justa Causa garante aviso integral proporcional (Lei 12.506/2011), multa 40% FGTS e seguro-desemprego."""
        sim = self.rescisao_svc._calcular_rescisao_detalhada(
            cur=self.rescisao_svc._conn().cursor(),
            colab=self.colab,
            tipo_norm="sem_justa_causa",
            data_afastamento="2026-02-15",
            tipo_aviso="indenizado",
            saldo_salario_dias=15,
            ferias_vencidas_dias=0,
            meses_trabalhados_ano=2,
            saldo_fgts=Decimal("10000.00"),
        )
        # Salário base: 6000. Valor dia: 200.
        # Saldo de salário (15 dias): R$ 3.000,00
        self.assertEqual(sim["saldo_salario"], Decimal("3000.00"))
        # 2 anos completos -> 30 + 6 = 36 dias de aviso prévio
        self.assertEqual(sim["dias_aviso_previo"], 36)
        self.assertEqual(sim["aviso_previo_indenizado"], Decimal("7200.00"))
        # Multa FGTS 40% de 10.000 = R$ 4.000,00
        self.assertEqual(sim["multa_fgts_percentual"], 40.0)
        self.assertEqual(sim["multa_fgts_valor"], Decimal("4000.00"))
        # Seguro desemprego habilitado e código saque 01
        self.assertTrue(sim["seguro_desemprego_elegivel"])
        self.assertEqual(sim["codigo_saque_fgts"], "01")

    def test_rn055_pedido_demissao(self):
        """RN-055: Pedido de Demissão não tem multa FGTS, desconta aviso prévio se não cumprido e não gera seguro-desemprego."""
        sim = self.rescisao_svc._calcular_rescisao_detalhada(
            cur=self.rescisao_svc._conn().cursor(),
            colab=self.colab,
            tipo_norm="pedido_demissao",
            data_afastamento="2026-02-15",
            tipo_aviso="indenizado", # não cumprido pelo empregado
            saldo_salario_dias=15,
            ferias_vencidas_dias=0,
            meses_trabalhados_ano=2,
            saldo_fgts=Decimal("10000.00"),
        )
        self.assertEqual(sim["saldo_salario"], Decimal("3000.00"))
        self.assertEqual(sim["aviso_previo_indenizado"], Decimal("0.00"))
        # Desconto de aviso prévio não cumprido (30 dias = R$ 6.000,00)
        self.assertEqual(sim["desconto_aviso_previo"], Decimal("6000.00"))
        self.assertEqual(sim["multa_fgts_percentual"], 0.0)
        self.assertEqual(sim["multa_fgts_valor"], Decimal("0.00"))
        self.assertFalse(sim["seguro_desemprego_elegivel"])
        self.assertEqual(sim["codigo_saque_fgts"], "NAO_AUTORIZADO")

    def test_rn056_justa_causa(self):
        """RN-056: Justa Causa perde aviso prévio, 13º proporcional, férias proporcionais e multa de FGTS."""
        sim = self.rescisao_svc._calcular_rescisao_detalhada(
            cur=self.rescisao_svc._conn().cursor(),
            colab=self.colab,
            tipo_norm="com_justa_causa",
            data_afastamento="2026-02-15",
            tipo_aviso="trabalhado",
            saldo_salario_dias=15,
            ferias_vencidas_dias=0,
            meses_trabalhados_ano=2,
            saldo_fgts=Decimal("10000.00"),
        )
        self.assertEqual(sim["saldo_salario"], Decimal("3000.00"))
        self.assertEqual(sim["aviso_previo_indenizado"], Decimal("0.00"))
        self.assertEqual(sim["decimo_terceiro_proporcional"], Decimal("0.00"))
        self.assertEqual(sim["ferias_proporcionais_com_terco"], Decimal("0.00"))
        self.assertEqual(sim["multa_fgts_valor"], Decimal("0.00"))
        self.assertFalse(sim["seguro_desemprego_elegivel"])
        self.assertEqual(sim["codigo_saque_fgts"], "NAO_AUTORIZADO")

    def test_rn057_acordo_trabalhista_art_484a(self):
        """RN-057: Acordo mútuo (art. 484-A) paga 50% do aviso prévio, 20% multa FGTS, saque FGTS cód 07 (80%) e verbas proporcionais integrais."""
        sim = self.rescisao_svc._calcular_rescisao_detalhada(
            cur=self.rescisao_svc._conn().cursor(),
            colab=self.colab,
            tipo_norm="acordo_484a",
            data_afastamento="2026-02-15",
            tipo_aviso="indenizado",
            saldo_salario_dias=15,
            ferias_vencidas_dias=0,
            meses_trabalhados_ano=2,
            saldo_fgts=Decimal("10000.00"),
        )
        # Aviso prévio pela metade: 36 dias = 7200 -> 50% = R$ 3.600,00
        self.assertEqual(sim["aviso_previo_indenizado"], Decimal("3600.00"))
        # Multa FGTS de 20% sobre saldo = R$ 2.000,00
        self.assertEqual(sim["multa_fgts_percentual"], 20.0)
        self.assertEqual(sim["multa_fgts_valor"], Decimal("2000.00"))
        # Código saque FGTS 07 (80% do saldo) e sem seguro-desemprego
        self.assertEqual(sim["codigo_saque_fgts"], "07")
        self.assertFalse(sim["seguro_desemprego_elegivel"])

    def test_rn058_rescisao_indireta(self):
        """RN-058: Rescisão Indireta (falta grave do empregador) tem direitos idênticos à dispensa sem justa causa."""
        sim = self.rescisao_svc._calcular_rescisao_detalhada(
            cur=self.rescisao_svc._conn().cursor(),
            colab=self.colab,
            tipo_norm="rescisao_indireta",
            data_afastamento="2026-02-15",
            tipo_aviso="indenizado",
            saldo_salario_dias=15,
            ferias_vencidas_dias=0,
            meses_trabalhados_ano=2,
            saldo_fgts=Decimal("10000.00"),
        )
        self.assertEqual(sim["aviso_previo_indenizado"], Decimal("7200.00"))
        self.assertEqual(sim["multa_fgts_percentual"], 40.0)
        self.assertEqual(sim["multa_fgts_valor"], Decimal("4000.00"))
        self.assertTrue(sim["seguro_desemprego_elegivel"])
        self.assertEqual(sim["codigo_saque_fgts"], "01")

    def test_rn059_culpa_reciproca(self):
        """RN-059: Culpa Recíproca (Art. 484 CLT, Súmula 14 TST, Lei 8.036/90 art. 18 § 2º) paga pela metade (50%) aviso, 13º e férias proporcionais."""
        sim = self.rescisao_svc._calcular_rescisao_detalhada(
            cur=self.rescisao_svc._conn().cursor(),
            colab=self.colab,
            tipo_norm="culpa_reciproca",
            data_afastamento="2026-02-15",
            tipo_aviso="indenizado",
            saldo_salario_dias=15,
            ferias_vencidas_dias=0,
            meses_trabalhados_ano=2,
            saldo_fgts=Decimal("10000.00"),
        )
        # 1. Saldo de Salário integral (100%): R$ 3.000,00
        self.assertEqual(sim["saldo_salario"], Decimal("3000.00"))
        # 2. Aviso prévio reduzido a 50% (Súmula 14 TST): 36 dias x 200 x 0.5 = R$ 3.600,00
        self.assertEqual(sim["aviso_previo_indenizado"], Decimal("3600.00"))
        # 3. 13º proporcional reduzido a 50% (Súmula 14 TST): 2 avos = (6000/12*2)*0.5 = R$ 500,00
        self.assertEqual(sim["decimo_terceiro_proporcional"], Decimal("500.00"))
        # 4. Férias proporcionais + 1/3 reduzidas a 50% (Súmula 14 TST)
        # Base normal 2 avos: (6000/12*2)*0.5 = 500. 1/3 = 166.67. Total = R$ 666.67
        self.assertEqual(sim["ferias_proporcionais_com_terco"], Decimal("666.67"))
        # 5. Multa FGTS de 20% (Lei 8.036/90 art. 18 § 2º)
        self.assertEqual(sim["multa_fgts_percentual"], 20.0)
        self.assertEqual(sim["multa_fgts_valor"], Decimal("2000.00"))
        # 6. Código saque FGTS: 02 (autorizado judicialmente/CLT)
        self.assertEqual(sim["codigo_saque_fgts"], "02")
        # 7. Seguro desemprego NÃO concedido
        self.assertFalse(sim["seguro_desemprego_elegivel"])

    def test_rn060_termino_contrato_experiencia(self):
        """RN-060: Término normal de contrato a prazo garante verbas proporcionais e saque código 04 sem aviso nem multa."""
        sim = self.rescisao_svc._calcular_rescisao_detalhada(
            cur=self.rescisao_svc._conn().cursor(),
            colab=self.colab,
            tipo_norm="termino_experiencia",
            data_afastamento="2026-02-15",
            tipo_aviso="trabalhado",
            saldo_salario_dias=15,
            ferias_vencidas_dias=0,
            meses_trabalhados_ano=2,
            saldo_fgts=Decimal("5000.00"),
        )
        self.assertEqual(sim["aviso_previo_indenizado"], Decimal("0.00"))
        self.assertEqual(sim["multa_fgts_valor"], Decimal("0.00"))
        self.assertEqual(sim["codigo_saque_fgts"], "04")

    def test_rn060_rescisao_antecipada_pelo_empregador_art_479(self):
        """RN-060: Rescisão antecipada pelo empregador (Art. 479 CLT) paga 50% dos dias faltantes e multa 40% FGTS."""
        sim = self.rescisao_svc._calcular_rescisao_detalhada(
            cur=self.rescisao_svc._conn().cursor(),
            colab=self.colab,
            tipo_norm="rescisao_antecipada_empregador",
            data_afastamento="2026-02-15",
            tipo_aviso="trabalhado",
            saldo_salario_dias=15,
            ferias_vencidas_dias=0,
            meses_trabalhados_ano=2,
            saldo_fgts=Decimal("5000.00"),
            dias_restantes_contrato_prazo=30, # Faltavam 30 dias para terminar o contrato
        )
        # Indenização art. 479 CLT: 50% de 30 dias x 200 = R$ 3.000,00
        self.assertEqual(sim["multa_art_479"], Decimal("3000.00"))
        self.assertEqual(sim["multa_fgts_percentual"], 40.0)
        self.assertEqual(sim["multa_fgts_valor"], Decimal("2000.00"))
        self.assertTrue(sim["seguro_desemprego_elegivel"])


if __name__ == "__main__":
    unittest.main()
