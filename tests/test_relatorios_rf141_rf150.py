# -*- coding: utf-8 -*-
"""
Testes Automatizados para os Requisitos de Relatórios e Exportação PDF (RF-141 a RF-150)
- RF-141: Relatório de Colaboradores (Headcount, setores e média salarial)
- RF-142: Relatório de Jornadas / Ponto (Horas normais, extras, noturnas e faltas)
- RF-143: Relatório de Férias (Períodos aquisitivos, limite concessivo e dobra CLT 137)
- RF-144: Relatório de Afastamentos (CID-10, 15d empresa x INSS, estabilidades)
- RF-145: Relatório de Benefícios (Subsídio empresa vs desconto colaborador)
- RF-146: Relatório de Encargos (INSS Patronal, RATxFAP, Terceiros, FGTS)
- RF-147: Relatório de SST (ASOs, EPIs, Treinamentos e CATs)
- RF-148: Relatório de Rescisões (Desligamentos, verbas e multas FGTS)
- RF-149: Relatório Financeiro da Folha (Proventos, descontos, líquido e provisões)
- RF-150: Exportação Padronizada em PDF A4 Oficial (Layout corporativo e totalizadores)
"""
import os
import sys
import sqlite3
import shutil
import tempfile
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.database import init_db
from backend.relatorios_service import RelatoriosService


class TestRelatoriosRF141RF150(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.master_db_path = cls.master_tmp.name
        cls.master_tmp.close()
        init_db(cls.master_db_path, auto_provision=False)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.master_db_path):
            try:
                os.remove(cls.master_db_path)
            except Exception:
                pass

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        shutil.copyfile(self.master_db_path, self.db_path)
        self.service = RelatoriosService(db_path=self.db_path)

        # Insere dados de teste para colaboradores, folhas, férias, afastamentos
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Colaborador 1
        cur.execute(
            """
            INSERT INTO colaboradores (
                empresa_id, matricula, nome_completo, cpf, email, data_nascimento, cargo, setor,
                salario_base, data_admissao, situacao, criado_em, atualizado_em
            ) VALUES (
                'a0000000-0000-0000-0000-000000000001', 'REP-001', 'Ana Souza Relatórios',
                '11122233301', 'ana.rel@empresa.com', '1992-04-10', 'Analista Fiscal', 'Financeiro',
                5000.00, '2025-01-15', 'ativo', '2025-01-15 08:00:00', '2025-01-15 08:00:00'
            );
        """
        )
        self.colab1_id = cur.lastrowid

        # Colaborador 2
        cur.execute(
            """
            INSERT INTO colaboradores (
                empresa_id, matricula, nome_completo, cpf, email, data_nascimento, cargo, setor,
                salario_base, data_admissao, situacao, criado_em, atualizado_em
            ) VALUES (
                'a0000000-0000-0000-0000-000000000001', 'REP-002', 'Bruno Lima Relatórios',
                '11122233302', 'bruno.rel@empresa.com', '1988-11-20', 'Operador de Máquinas', 'Operações',
                3000.00, '2024-03-01', 'ativo', '2024-03-01 08:00:00', '2024-03-01 08:00:00'
            );
        """
        )
        self.colab2_id = cur.lastrowid

        # Folha de Pagamento para Colaborador 1
        cur.execute(
            """
            INSERT INTO folhas_pagamento (
                empresa_id, colaborador_id, competencia, periodo_inicio, periodo_fim,
                salario_base_contratual, salario_base_proporcional, total_proventos, total_descontos,
                salario_liquido, inss_descontado, irrf_descontado, encargos_patronais, situacao,
                criado_por, criado_em
            ) VALUES (
                'a0000000-0000-0000-0000-000000000001', ?, '2026-03', '2026-03-01', '2026-03-31',
                5000.00, 5000.00, 5000.00, 750.00, 4250.00, 550.00, 200.00, 1000.00, 'fechada',
                'DP', '2026-03-31 18:00:00'
            );
        """,
            (self.colab1_id,),
        )

        # Período Aquisitivo de Férias
        cur.execute(
            """
            INSERT INTO periodos_aquisitivos (
                empresa_id, colaborador_id, inicio_aquisitivo, fim_aquisitivo,
                limite_concessivo, dias_direito, saldo_dias, situacao, criado_em, atualizado_em
            ) VALUES (
                'a0000000-0000-0000-0000-000000000001', ?, '2024-03-01', '2025-02-28',
                '2026-02-28', 30, 30, 'adquirido', '2025-03-01 00:00:00', '2025-03-01 00:00:00'
            );
        """,
            (self.colab2_id,),
        )

        # Afastamento de 25 dias (15 dias empresa + 10 dias INSS)
        cur.execute(
            """
            INSERT INTO afastamentos (
                colaborador_id, tipo, motivo_esocial, cid, data_inicio, data_fim_prevista,
                data_retorno_efetivo, dias_empresa, dias_inss, status_esocial, criado_por, criado_em
            ) VALUES (
                ?, 'acidente_trabalho', '01', 'S82',
                '2026-01-10', '2026-02-03', '2026-02-03', 15, 10, 'processado', 'DP', '2026-01-10 10:00:00'
            );
        """,
            (self.colab2_id,),
        )

        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_rf141_relatorio_colaboradores(self):
        """RF-141: Relatório de colaboradores com métricas de headcount e médias salariais."""
        rel = self.service.relatorio_colaboradores()
        self.assertEqual(rel["totalizadores"]["total_colaboradores"], 2)
        self.assertEqual(rel["totalizadores"]["massa_salarial_base"], 8000.00)
        self.assertEqual(rel["totalizadores"]["media_salarial"], 4000.00)
        self.assertIn("Financeiro", rel["distribuicao_setor"])
        self.assertIn("Operações", rel["distribuicao_setor"])

    def test_rf142_relatorio_jornadas_ponto(self):
        """RF-142: Relatório analítico de apuração de jornadas e ponto eletrônico."""
        rel = self.service.relatorio_jornadas_ponto(colaborador_id=self.colab1_id)
        self.assertEqual(rel["totalizadores"]["total_colaboradores"], 1)
        self.assertGreaterEqual(rel["totalizadores"]["total_horas_normais"], 0.0)

    def test_rf143_relatorio_ferias(self):
        """RF-143: Relatório de férias com verificação de períodos aquisitivos e dobra legal (CLT 137)."""
        rel = self.service.relatorio_ferias()
        self.assertGreaterEqual(rel["totalizadores"]["total_periodos"], 1)
        # O período cadastrado venceu o limite concessivo em 2026-02-28, logo deve ser detectado como férias a dobrar
        self.assertGreaterEqual(rel["totalizadores"]["ferias_a_dobrar_clt137"], 1)

    def test_rf144_relatorio_afastamentos(self):
        """RF-144: Afastamentos com discriminação de 15 dias empresa x INSS e estabilidades."""
        rel = self.service.relatorio_afastamentos()
        self.assertGreaterEqual(rel["totalizadores"]["total_afastamentos"], 1)
        self.assertEqual(rel["totalizadores"]["total_dias_empresa"], 15)
        self.assertEqual(rel["totalizadores"]["total_dias_inss"], 10)
        # Acidente de trabalho gera estabilidade acidentária (B91)
        self.assertGreaterEqual(rel["totalizadores"]["casos_estabilidade"], 1)

    def test_rf145_relatorio_beneficios(self):
        """RF-145: Relatório de benefícios corporativos e rateio de custos."""
        # Cadastra benefício no catálogo e atribui
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO beneficios_catalogo (empresa_id, codigo, nome, tipo, valor_mensal_padrao, ativo, criado_em)
            VALUES ('a0000000-0000-0000-0000-000000000001', 'VA-01', 'Vale Alimentação', 'vale_alimentacao', 600.00, 1, '2026-01-01');
        """
        )
        ben_id = cur.lastrowid
        cur.execute(
            """
            INSERT INTO beneficios_colaborador (colaborador_id, beneficio_id, valor_mensal_base, custo_empresa, desconto_colaborador, vigencia_inicio, ativo, criado_em)
            VALUES (?, ?, 600.00, 480.00, 120.00, '2026-01-01', 1, '2026-01-01');
        """,
            (self.colab1_id, ben_id),
        )
        conn.commit()
        conn.close()

        rel = self.service.relatorio_beneficios()
        self.assertEqual(rel["totalizadores"]["total_concessoes"], 1)
        self.assertEqual(rel["totalizadores"]["custo_total_beneficios"], 600.00)
        self.assertEqual(rel["totalizadores"]["subsidio_total_empresa"], 480.00)
        self.assertEqual(rel["totalizadores"]["desconto_total_colaboradores"], 120.00)

    def test_rf146_relatorio_encargos_folha(self):
        """RF-146: Demonstrativo de encargos sociais, INSS patronal, RATxFAP, Terceiros e FGTS."""
        rel = self.service.relatorio_encargos_folha(competencia="2026-03")
        self.assertEqual(rel["totalizadores"]["base_calculo_inss"], 5000.00)
        self.assertEqual(rel["totalizadores"]["inss_segurados_retido"], 550.00)
        # 20% patronal = 1000.00
        self.assertEqual(rel["totalizadores"]["inss_patronal_20pct"], 1000.00)
        # 8% FGTS = 400.00
        self.assertEqual(rel["totalizadores"]["fgts_recolher_8pct"], 400.00)
        self.assertGreater(rel["totalizadores"]["total_encargos_patronais"], 1000.00)

    def test_rf147_relatorio_sst(self):
        """RF-147: Relatório consolidado de SST, exames, EPIs e CATs."""
        rel = self.service.relatorio_sst()
        self.assertIn("total_asos", rel["totalizadores"])
        self.assertIn("epis_em_uso", rel["totalizadores"])
        self.assertIn("total_cats_emitidas", rel["totalizadores"])

    def test_rf148_relatorio_rescisoes(self):
        """RF-148: Relatório de rescisões contratuais, verbas rescisórias e multas."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO rescisoes (
                colaborador_id, tipo_rescisao, data_comunicacao, data_afastamento, data_limite_pagamento,
                total_proventos, total_descontos, valor_liquido, multa_fgts_valor, status, criado_por, criado_em
            ) VALUES (
                ?, 'sem_justa_causa', '2026-02-01', '2026-02-15', '2026-02-25',
                8500.00, 1200.00, 7300.00, 6000.00, 'calculada', 'DP', '2026-02-15 10:00:00'
            );
        """,
            (self.colab2_id,),
        )
        conn.commit()
        conn.close()

        rel = self.service.relatorio_rescisoes()
        self.assertEqual(rel["totalizadores"]["total_rescisoes"], 1)
        self.assertEqual(rel["totalizadores"]["total_verbas_brutas"], 8500.00)
        self.assertEqual(rel["totalizadores"]["total_liquido_pago"], 7300.00)
        self.assertEqual(rel["totalizadores"]["total_multas_fgts"], 6000.00)

    def test_rf149_relatorio_financeiro_folha(self):
        """RF-149: Demonstrativo financeiro e contábil da folha com provisões."""
        rel = self.service.relatorio_financeiro_folha(competencia="2026-03")
        self.assertEqual(rel["totalizadores"]["total_colaboradores"], 1)
        self.assertEqual(rel["totalizadores"]["total_proventos_brutos"], 5000.00)
        self.assertEqual(rel["totalizadores"]["total_descontos"], 750.00)
        self.assertEqual(rel["totalizadores"]["total_liquido_disponivel"], 4250.00)
        # Provisão de férias (1/12 + 1/3): 5000/12 * 4/3 = 555.56
        self.assertAlmostEqual(rel["totalizadores"]["provisao_mensal_ferias_terco"], 555.56, places=1)
        # Provisão de 13º (1/12): 5000/12 = 416.67
        self.assertAlmostEqual(rel["totalizadores"]["provisao_mensal_decimo_terceiro"], 416.67, places=1)

    def test_rf150_exportacao_pdf_a4_oficial(self):
        """RF-150: Exportação oficial de relatórios em PDF A4 padronizado."""
        pdf_bytes = self.service.exportar_relatorio_pdf(
            tipo_relatorio="colaboradores",
            filtros={"setor": "Financeiro"},
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 500)
        # Validação do cabeçalho PDF padrão
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        # Verifica se o PDF contém o rodapé padronizado
        self.assertIn(b"RH2.0 Enterprise", pdf_bytes)


if __name__ == "__main__":
    unittest.main()
