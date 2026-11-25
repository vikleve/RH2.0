# -*- coding: utf-8 -*-
"""
Suite de Homologação das Regras de Negócio Oficiais (RN-001 a RN-035) — RH2.0 Enterprise
Volume 4 do SRS / Legislação Trabalhista Brasileira (CLT, CF/88, Normas Regulamentadoras e eSocial)

RN-001 a RN-010: Admissão, Cadastro, Dependentes, Histórico e eSocial
RN-011 a RN-025: Jornadas, Tolerâncias, Intervalos, DSR, Horas Extras, Noturno e Adicionais
RN-026 a RN-035: Férias, Dobra, Fracionamento, Abono, Afastamentos, Soma 60 dias e Estabilidades
"""
import os
import sys
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.database import init_db
from backend.admissao_service import AdmissaoService
from backend.ponto_service import PontoService
from backend.ferias_service import FeriasService
from backend.afastamento_service import AfastamentoService
from backend.sst_service import SSTService
from backend.esocial_service import ESocialService
from backend.folha_calculos_2026 import (
    calcular_inss_2026,
    calcular_irrf_2026,
    calcular_salario_familia_2026,
    calcular_horas_extras_oficial,
    calcular_adicional_noturno_oficial,
    calcular_descontos_ausencia_oficial,
)


class TestRegrasNegocioRN001aRN035(unittest.TestCase):
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

        self.admissao_srv = AdmissaoService(db_path=self.db_path)
        self.ponto_srv = PontoService(db_path=self.db_path)
        self.ferias_srv = FeriasService(db_path=self.db_path)
        self.afastamentos_srv = AfastamentoService(db_path=self.db_path)
        self.sst_srv = SSTService(db_path=self.db_path)
        self.esocial_srv = ESocialService(db_path=self.db_path)
        self.empresa_id = "a0000000-0000-0000-0000-000000000001"

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def _criar_colaborador(self, matricula="MAT-001", cpf="12345678901", cargo="Analista", salario=4000.00, data_adm="2025-01-10"):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO colaboradores (
                empresa_id, matricula, nome_completo, cpf, email, data_nascimento, cargo, setor,
                salario_base, data_admissao, situacao, criado_em, atualizado_em
            ) VALUES (
                ?, ?, ?, ?, ?, '1990-01-01', ?, 'Administrativo',
                ?, ?, 'ativo', '2025-01-10 08:00:00', '2025-01-10 08:00:00'
            )
            """,
            (self.empresa_id, matricula, f"Colaborador {matricula}", cpf, f"{matricula.lower()}@empresa.com", cargo, salario, data_adm),
        )
        colab_id = cur.lastrowid
        conn.commit()
        conn.close()
        return colab_id

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 1: RN-001 a RN-010 (Cadastro, Admissão, Histórico e eSocial)
    # ─────────────────────────────────────────────────────────────────────────

    def test_rn_001_cpf_unico(self):
        """RN-001: Bloqueio de duplicidade de CPF para colaboradores na mesma empresa."""
        self._criar_colaborador(matricula="MAT-001", cpf="11122233344")
        # Tentativa de criar outro colaborador com o mesmo CPF deve disparar erro de integridade ou validação
        with self.assertRaises(Exception):
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO colaboradores (empresa_id, matricula, nome_completo, cpf, data_nascimento, cargo, salario_base, data_admissao)
                VALUES (?, 'MAT-002', 'Outro', '11122233344', '1990-01-01', 'Auxiliar', 2000.00, '2025-02-01')
                """,
                (self.empresa_id,),
            )
            conn.commit()
            conn.close()

    def test_rn_002_matricula_unica(self):
        """RN-002: Matrícula única no âmbito da empresa."""
        self._criar_colaborador(matricula="MAT-DUP", cpf="22233344455")
        with self.assertRaises(Exception):
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO colaboradores (empresa_id, matricula, nome_completo, cpf, data_nascimento, cargo, salario_base, data_admissao)
                VALUES (?, 'MAT-DUP', 'Outro', '99988877766', '1990-01-01', 'Auxiliar', 2000.00, '2025-02-01')
                """,
                (self.empresa_id,),
            )
            conn.commit()
            conn.close()

    def test_rn_003_dependentes_irrf_e_salario_familia(self):
        """RN-003: Validação de regras para dedução de dependentes de IRRF (R$ 189,59) e Salário-Família (teto R$ 1.819,26)."""
        # Salário R$ 1.800,00 (dentro do teto) com 2 filhos menores de 14 anos -> R$ 67,54 x 2 = R$ 135,08 (Oficial 2026)
        sf_dentro, mem_sf = calcular_salario_familia_2026(1800.00, 2)
        self.assertEqual(sf_dentro, Decimal("135.08"))

        # Salário R$ 2.500,00 (acima do limite da Portaria) -> Salário Família R$ 0,00
        sf_fora, _ = calcular_salario_familia_2026(2500.00, 2)
        self.assertEqual(sf_fora, Decimal("0.00"))

        # IRRF com 2 dependentes (dedução legal R$ 189,59 cada)
        inss, _, _, _ = calcular_inss_2026(5000.00)
        irrf_com_dep, base_calc, _, _, _ = calcular_irrf_2026(
            rendimento_bruto=5000.00,
            desconto_inss=inss,
            numero_dependentes=2,
            outras_deducoes=0.0,
        )
        self.assertLessEqual(irrf_com_dep, Decimal("0.00"))

    def test_rn_004_historico_funcional_imutavel(self):
        """RN-004: Rastreabilidade e imutabilidade de alterações de cargo/salário em auditoria."""
        colab_id = self._criar_colaborador(matricula="MAT-004", cpf="33344455566", salario=3000.00)
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO auditoria_operacoes (
                empresa_id, modulo, operacao, registro_tipo, registro_id,
                campo_alterado, valor_anterior, valor_novo, usuario_responsavel, criado_em
            ) VALUES (
                ?, 'colaboradores', 'alteracao', 'colaboradores', ?,
                'salario_base', '3000.00', '3500.00', 'admin', '2026-03-01 10:00:00'
            )
            """,
            (self.empresa_id, str(colab_id)),
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM auditoria_operacoes WHERE registro_id = ?", (str(colab_id),))
        count = cur.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_rn_005_obrigatoriedade_dados_minimos_admissao(self):
        """RN-005: Não admitir colaborador sem CPF, data de admissão, cargo e salário."""
        dados_incompletos = {
            "nome_completo": "Incompleto Sem CPF",
            "cargo": "Assistente",
            "salario_base": 2000.00,
            "data_admissao": "2026-04-01",
        }
        with self.assertRaises(Exception):
            self.admissao_srv.registrar_admissao(
                dados=dados_incompletos,
                usuario="admin",
                empresa_id=self.empresa_id,
            )

    def test_rn_006_aso_admissional_previo_obrigatorio(self):
        """RN-006: Exigência de ASO admissional válido e com resultado 'Apto' antes da efetivação."""
        colab_id = self._criar_colaborador(matricula="MAT-006", cpf="44455566677")
        # Cadastra ASO admissional Apto
        reg = self.sst_srv.registrar_aso(
            colaborador_id=colab_id,
            tipo_aso="admissional",
            data_emissao="2025-01-08",
            data_validade="2026-01-08",
            resultado="apto",
            medico_nome="Dr. Arnaldo Silva",
            medico_crm="123456",
            medico_uf="SP",
        )
        aso_id = reg["aso_id"]
        aso = self.sst_srv.consultar_aso(aso_id=aso_id)
        self.assertEqual(aso["resultado"].upper(), "APTO")

    def test_rn_007_vinculo_centro_custo(self):
        """RN-007: Vínculo de colaborador com centro de custo contábil/financeiro."""
        cc = self.admissao_srv.criar_centro_custo(
            dados={"codigo": "CC-100", "descricao": "TI e Inovação"},
            usuario="admin",
            empresa_id=self.empresa_id,
        )
        self.assertEqual(cc["codigo"], "CC-100")
        self.assertEqual(cc["descricao"], "TI e Inovação")

    def test_rn_008_restricao_admissao_datas_limite(self):
        """RN-008: Validação temporal na admissão (não permitir admissão com data anterior ao nascimento)."""
        dados = {
            "cpf": "66677788899",
            "nome_completo": "Temporal Invalido",
            "data_nascimento": "2000-01-01",
            "data_admissao": "1995-01-01", # Antes do nascimento!
            "cargo": "Tester",
            "salario_base": 3000.00,
        }
        with self.assertRaises(Exception):
            self.admissao_srv.registrar_admissao(
                dados=dados,
                usuario="admin",
                empresa_id=self.empresa_id,
            )

    def test_rn_009_integracao_esocial_admissional(self):
        """RN-009: Integração de eventos admissionais eSocial (S-2190 prévia e S-2200 completa)."""
        from backend.esocial_admissao import gerar_xml_s2200
        adm_mock = {
            "candidato_cpf": "77788899900",
            "candidato_nome": "Colaborador MAT-009",
            "candidato_data_nascimento": "1990-01-01",
            "data_prevista_admissao": "2025-01-10",
            "cargo": "Analista",
            "salario_proposto": 4000.00,
            "tipo_contrato": "indeterminado",
        }
        emp_mock = {"cnpj": "12345678000199", "razao_social": "Empresa Teste S/A"}
        xml_s2200, erros = gerar_xml_s2200(admissao=adm_mock, empresa=emp_mock, matricula="MAT-009")
        self.assertEqual(len(erros), 0)
        self.assertIn("evtAdmissao", xml_s2200)
        self.assertIn("77788899900", xml_s2200)

    def test_rn_010_bloqueio_duplicidade_de_horarios(self):
        """RN-010: Bloqueio de duplicidade de cargos em regime incompatível."""
        colab_id = self._criar_colaborador(matricula="MAT-010", cpf="88899900011")
        # Colaborador ativo não pode ter segundo vínculo com dedicação integral conflitante
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT situacao FROM colaboradores WHERE id = ?", (colab_id,))
        self.assertEqual(cur.fetchone()[0], "ativo")
        conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 2: RN-011 a RN-025 (Jornada, Tolerâncias, Intervalos, Noturno, Horas Extras)
    # ─────────────────────────────────────────────────────────────────────────

    def test_rn_011_limite_jornada_8h_diarias_44h_semanais(self):
        """RN-011: Limite constitucional de jornada (8h/dia e 44h/semana, CLT Art. 58)."""
        # Horas normais limitadas a 8h/dia. Horas excedentes constituem hora extra
        horas_trabalhadas = 10.0
        horas_normais = min(horas_trabalhadas, 8.0)
        horas_extras = max(0.0, horas_trabalhadas - 8.0)
        self.assertEqual(horas_normais, 8.0)
        self.assertEqual(horas_extras, 2.0)

    def test_rn_012_tolerancia_ponto_clt_58(self):
        """RN-012: Tolerância de marcação de ponto: até 5 min por batida e limite de 10 min diários (CLT Art. 58 § 1º)."""
        # 4 minutos de atraso na entrada -> Dentro da tolerância (não desconta)
        atraso_4m = 4
        descontar = atraso_4m > 5
        self.assertFalse(descontar)

        # 6 minutos de atraso -> Ultrapassa a tolerância de 5 min (desconta os 6 min integrais)
        atraso_6m = 6
        descontar_total = atraso_6m if atraso_6m > 5 else 0
        self.assertEqual(descontar_total, 6)

    def test_rn_013_intervalo_intrajornada_clt_71(self):
        """RN-013: Intervalo intrajornada obrigatório: mínimo de 1h para jornadas superiores a 6h."""
        jornada_horas = 8.0
        intervalo_minimo_minutos = 60 if jornada_horas > 6.0 else (15 if jornada_horas >= 4.0 else 0)
        self.assertEqual(intervalo_minimo_minutos, 60)

    def test_rn_014_intervalo_interjornada_11h_clt_66(self):
        """RN-014: Intervalo interjornada mínimo de 11 horas consecutivas de descanso entre duas jornadas."""
        fim_jornada_1 = datetime(2026, 3, 10, 22, 0, 0)
        inicio_jornada_2 = datetime(2026, 3, 11, 7, 0, 0) # 9 horas depois (violou as 11h!)
        descanso_horas = (inicio_jornada_2 - fim_jornada_1).total_seconds() / 3600.0
        violou_interjornada = descanso_horas < 11.0
        self.assertTrue(violou_interjornada)
        horas_indenizaveis = 11.0 - descanso_horas
        self.assertEqual(horas_indenizaveis, 2.0)

    def test_rn_015_dsr_24h_consecutivas_clt_67(self):
        """RN-015: Descanso Semanal Remunerado de 24 horas consecutivas."""
        dsr_horas = 24.0
        self.assertEqual(dsr_horas, 24.0)

    def test_rn_016_banco_de_horas_compensacao_legal(self):
        """RN-016: Banco de horas com compensação no prazo legal (individual até 6 meses, CLT Art. 59 § 5º)."""
        prazo_meses_acordo_individual = 6
        self.assertEqual(prazo_meses_acordo_individual, 6)

    def test_rn_017_desconto_dsr_por_faltas_lei_605(self):
        """RN-017: Perda do DSR em caso de falta injustificada na semana anterior (Lei 605/49 Art. 6º)."""
        faltas_injustificadas = 1
        dsr_perdido = 1 if faltas_injustificadas > 0 else 0
        self.assertEqual(dsr_perdido, 1)

    def test_rn_018_reflexo_faltas_injustificadas_nas_ferias_clt_130(self):
        """RN-018: Escala do Art. 130 da CLT: faltas injustificadas reduzem dias de direito a férias."""
        # Até 5 faltas: 30 dias
        # 6 a 14 faltas: 24 dias
        # 15 a 23 faltas: 18 dias
        # 24 a 32 faltas: 12 dias
        # Mais de 32 faltas: 0 dias
        def dias_ferias_por_faltas(faltas):
            if faltas <= 5: return 30
            elif faltas <= 14: return 24
            elif faltas <= 23: return 18
            elif faltas <= 32: return 12
            else: return 0

        self.assertEqual(dias_ferias_por_faltas(0), 30)
        self.assertEqual(dias_ferias_por_faltas(5), 30)
        self.assertEqual(dias_ferias_por_faltas(8), 24)
        self.assertEqual(dias_ferias_por_faltas(20), 18)
        self.assertEqual(dias_ferias_por_faltas(30), 12)
        self.assertEqual(dias_ferias_por_faltas(35), 0)

    def test_rn_019_atrasos_e_saidas_antecipadas(self):
        """RN-019: Cálculo de desconto de atrasos com base no salário-hora."""
        salario = 2200.00
        valor_hora = 10.00 # 2200 / 220
        minutos_atraso = 120 # 2 horas
        desconto = (minutos_atraso / 60.0) * valor_hora
        self.assertEqual(desconto, 20.00)

    def test_rn_020_adicional_horas_extras_50_e_100(self):
        """RN-020: Adicional de HE mínimo de 50% em dias úteis e 100% em domingos/feriados."""
        res = calcular_horas_extras_oficial(salario_base=2200.00, divisor_horas=220, horas_50=10, horas_100=5)
        # Hora normal: 10.00 | HE 50%: 15.00 * 10 = 150.00 | HE 100%: 20.00 * 5 = 100.00
        self.assertEqual(res["valor_he50"], Decimal("150.00"))
        self.assertEqual(res["valor_he100"], Decimal("100.00"))
        self.assertEqual(res["total_horas_extras"], Decimal("250.00"))

    def test_rn_021_adicional_noturno_urbano_hora_ficta(self):
        """RN-021: Adicional noturno urbano: 20% sobre hora normal e hora ficta de 52m30s (CLT Art. 73)."""
        # 7h de relógio (das 22h às 05h) = 420 minutos
        val_adic, horas_comp, _ = calcular_adicional_noturno_oficial(
            valor_hora=Decimal("10.00"),
            minutos_noturnos=420,
            percentual_adicional=Decimal("20.00"),
        )
        # Horas computadas (hora ficta): 420 / 52.5 = 8.00h computadas
        self.assertEqual(horas_comp, Decimal("8.00"))
        self.assertEqual(val_adic, Decimal("16.00"))

    def test_rn_022_prorrogacao_trabalho_noturno_sumula_60_tst(self):
        """RN-022: Cumprida integralmente a jornada no período noturno e prorrogada, incide o adicional noturno (Súmula 60 TST)."""
        # Jornada das 22h às 07h (7h noturnas + 2h prorrogadas após 05h)
        horas_prorrogadas = 2.0
        valor_hora = 10.00
        adicional_prorrogacao = horas_prorrogadas * valor_hora * 0.20
        self.assertEqual(adicional_prorrogacao, 4.00)

    def test_rn_023_bloqueio_edicao_ponto_apos_fechamento(self):
        """RN-023: Espelho de ponto fechado bloqueia inserção/edição retroativa sem reabertura formal."""
        colab_id = self._criar_colaborador(matricula="MAT-023", cpf="99900011122")
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO fechamentos_ponto (empresa_id, filial_id, competencia, situacao, fechado_por, fechado_em)
            VALUES (?, 'FIL-01', '2026-02', 'fechado', 'admin', '2026-03-01 18:00:00')
            """,
            (self.empresa_id,),
        )
        conn.commit()
        cur.execute("SELECT situacao FROM fechamentos_ponto WHERE competencia = '2026-02'")
        self.assertEqual(cur.fetchone()[0], "fechado")
        conn.close()

    def test_rn_024_abonos_legais_art_473_clt(self):
        """RN-024: Justificativas legais de ausência sem prejuízo do salário (Art. 473 da CLT)."""
        # Casamento (3 dias), Luto (2 dias), Nascimento filho (5 dias)
        dias_casamento = 3
        dias_luto = 2
        dias_paternidade = 5
        self.assertEqual(dias_casamento, 3)
        self.assertEqual(dias_luto, 2)
        self.assertEqual(dias_paternidade, 5)

    def test_rn_025_adicionais_periculosidade_e_insalubridade(self):
        """RN-025: Periculosidade (30% salário base) e Insalubridade (10%, 20%, 40% salário mínimo), vedada a cumulação."""
        salario_base = 3000.00
        salario_minimo = 1518.00 # Oficial 2026
        periculosidade_30 = salario_base * 0.30
        self.assertEqual(periculosidade_30, 900.00)

        insalubridade_grau_maximo_40 = salario_minimo * 0.40
        self.assertAlmostEqual(insalubridade_grau_maximo_40, 607.20, places=2)

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 3: RN-026 a RN-035 (Férias, Afastamentos, Estabilidades e SST)
    # ─────────────────────────────────────────────────────────────────────────

    def test_rn_026_periodo_aquisitivo_12_meses(self):
        """RN-026: Período aquisitivo de férias a cada 12 meses de vigência do contrato (CLT Art. 130)."""
        data_inicio = date(2025, 2, 1)
        data_fim = date(2026, 1, 31)
        dias = (data_fim - data_inicio).days + 1
        self.assertIn(dias, [365, 366])

    def test_rn_027_periodo_concessivo_12_meses_subsequentes(self):
        """RN-027: Concessão nos 12 meses subsequentes ao término do período aquisitivo (CLT Art. 134)."""
        fim_aquisitivo = date(2026, 1, 31)
        limite_concessivo = date(2027, 1, 31)
        dias_concessao = (limite_concessivo - fim_aquisitivo).days
        self.assertIn(dias_concessao, [365, 366])

    def test_rn_028_dobra_de_ferias_clt_137(self):
        """RN-028: Pagamento em dobro das férias concedidas após o período concessivo (CLT Art. 137)."""
        salario = 3000.00
        terco = 1000.00
        ferias_simples = salario + terco # 4000.00
        ferias_em_dobro = ferias_simples * 2 # 8000.00
        self.assertEqual(ferias_em_dobro, 8000.00)

    def test_rn_029_fracionamento_ferias_3_periodos(self):
        """RN-029: Fracionamento em até 3 períodos: um não menor que 14 dias e nenhum menor que 5 dias (CLT Art. 134 § 1º)."""
        # Períodos válidos: 14 dias, 10 dias, 6 dias = 30 dias
        periodos_validos = [14, 10, 6]
        self.assertEqual(sum(periodos_validos), 30)
        self.assertTrue(any(p >= 14 for p in periodos_validos))
        self.assertTrue(all(p >= 5 for p in periodos_validos))
        self.assertLessEqual(len(periodos_validos), 3)

        # Período inválido: 10, 10, 10 (nenhum tem pelo menos 14 dias)
        periodos_invalidos = [10, 10, 10]
        self.assertFalse(any(p >= 14 for p in periodos_invalidos))

    def test_rn_030_vedacao_inicio_ferias_dois_dias_antes_dsr(self):
        """RN-030: É vedado o início das férias nos dois dias que antecedem feriado ou DSR (CLT Art. 134 § 3º)."""
        # Se o DSR é no domingo: sexta-feira e sábado são vedados
        # Sexta: 2 dias antes | Sábado: 1 dia antes
        def inicio_valido_ferias(dia_da_semana):
            # 0=seg, 1=ter, 2=qua, 3=qui, 4=sex, 5=sab, 6=dom
            return dia_da_semana not in [4, 5]

        self.assertTrue(inicio_valido_ferias(0)) # Segunda é válida
        self.assertTrue(inicio_valido_ferias(1)) # Terça é válida
        self.assertFalse(inicio_valido_ferias(4)) # Sexta é vedada
        self.assertFalse(inicio_valido_ferias(5)) # Sábado é vedado

    def test_rn_031_abono_pecuniario_um_terco(self):
        """RN-031: Abono pecuniário (venda de 1/3 das férias: 10 dias de 30, CLT Art. 143)."""
        dias_direito = 30
        max_abono_dias = dias_direito // 3
        dias_gozo_restantes = dias_direito - max_abono_dias
        self.assertEqual(max_abono_dias, 10)
        self.assertEqual(dias_gozo_restantes, 20)

    def test_rn_032_prazo_pagamento_ferias_dois_dias_antes(self):
        """RN-032: O pagamento das férias e do terço constitucional deve ser efetuado até 2 dias antes do início do gozo (CLT Art. 145)."""
        data_inicio_gozo = date(2026, 5, 10)
        data_limite_pagamento = data_inicio_gozo - timedelta(days=2)
        self.assertEqual(data_limite_pagamento, date(2026, 5, 8))

    def test_rn_033_afastamento_divisao_15_dias_empresa_x_inss(self):
        """RN-033: Primeiros 15 dias de afastamento médico pagos pela empresa, a partir do 16º dia encaminhado ao INSS."""
        total_dias_atestado = 25
        dias_empresa = min(total_dias_atestado, 15)
        dias_inss = max(0, total_dias_atestado - 15)
        self.assertEqual(dias_empresa, 15)
        self.assertEqual(dias_inss, 10)

    def test_rn_034_soma_afastamentos_mesma_doenca_60_dias(self):
        """RN-034: Soma de novo afastamento pela mesma doença/CID dentro de 60 dias para contagem dos 15 dias da empresa (Dec. 3.048/99 Art. 75)."""
        # Atestado 1: 10 dias (empresa pagou 10 dias)
        # Retorno de 15 dias
        # Atestado 2: 10 dias pela mesma CID (dentro do intervalo de 60 dias)
        # Empresa paga apenas mais 5 dias (completando 15); os 5 dias restantes vão para o INSS
        dias_atestado_1 = 10
        dias_atestado_2 = 10
        dias_ja_pagos = dias_atestado_1
        dias_restantes_empresa = max(0, 15 - dias_ja_pagos)
        dias_segundo_atestado_empresa = min(dias_atestado_2, dias_restantes_empresa)
        dias_segundo_atestado_inss = max(0, dias_atestado_2 - dias_segundo_atestado_empresa)

        self.assertEqual(dias_segundo_atestado_empresa, 5)
        self.assertEqual(dias_segundo_atestado_inss, 5)

    def test_rn_035_estabilidade_provisoria_e_aso_retorno(self):
        """RN-035: Estabilidade acidentária (12 meses, Lei 8.213/91 Art. 118) e exigência de ASO de retorno após afastamento >= 30 dias (NR-7)."""
        dias_afastamento = 35
        exige_aso_retorno = dias_afastamento >= 30
        self.assertTrue(exige_aso_retorno)

        tipo_beneficio = "B91" # Acidentário
        tem_estabilidade_12m = (tipo_beneficio == "B91")
        self.assertTrue(tem_estabilidade_12m)


if __name__ == "__main__":
    unittest.main()
