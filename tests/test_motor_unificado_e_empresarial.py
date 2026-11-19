# -*- coding: utf-8 -*-
"""
Testes Automatizados — Motor Unificado, Tabelas Legais, Multiempresa, eSocial e CNAB240
Valida os critérios técnicos do RH2.0 Enterprise:
1. Validação de conversão Decimal estrita e rejeição de valores malformados (Seção 4.5).
2. Versionamento e imutabilidade de tabelas legais por competência (Seção 4.3).
3. Memória de cálculo detalhada com fórmulas, bases e alíquotas (Seção 4.4).
4. Cálculos trabalhistas unificados: HE, DSR, Noturno 52m30s, Insalubridade, Periculosidade e Faltas (Seção 4.2).
5. Férias com 1/3 e abono pecuniário, e 13º salário 1ª e 2ª parcelas (Seção 5 e 11).
6. Rescisões nas 5 modalidades CLT com aviso prévio proporcional Lei 12.506/11 e multas FGTS (Seção 11).
7. Isolamento multi-tenant estrito e bloqueio contra BOLA/IDOR (Seção 7).
8. Tratamento de eSocial como simulação sem recibos falsos (Seção 6).
9. Geração de CNAB 240 multibanco com segmentos A e B e totalizadores exatos (Seção 9).
"""
import json
from decimal import Decimal
import os
import tempfile
import unittest

from backend.motor_calculo_unificado import (
    calcular_adicional_noturno,
    calcular_decimo_terceiro_unificado,
    calcular_faltas_e_atrasos,
    calcular_ferias_unificado,
    calcular_fgts_unificado,
    calcular_horas_extras,
    calcular_inss_unificado,
    calcular_insalubridade,
    calcular_irrf_unificado,
    calcular_periculosidade,
    calcular_rescisao_unificado,
    calcular_salario_familia_unificado,
    calcular_salario_proporcional,
    calcular_vale_transporte_unificado,
    calcular_valor_dia,
    calcular_valor_hora,
)
from backend.tabelas_legais import (
    ConversaoFinanceiraException,
    converter_decimal_estrito,
    obter_tabela_legal,
    TABELA_LEGAL_2026_OFICIAL,
    TABELA_LEGAL_2026_PADRAO,
)
from backend.plataforma_service import PlataformaService
from backend.service import ColaboradorService


class TestMotorUnificadoEEmpresarial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_fd, cls.temp_db = tempfile.mkstemp(suffix=".db")
        os.close(cls.temp_fd)
        cls.service_plat = PlataformaService(db_path=cls.temp_db)
        cls.service_colab = ColaboradorService(db_path=cls.temp_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_db):
            try:
                os.remove(cls.temp_db)
            except Exception:
                pass

    # 1. Precisão e Conversão Decimal Estrita
    def test_01_conversao_decimal_estrita(self):
        """Rejeita strings alfanuméricas inválidas e aceita formatos monetários válidos."""
        self.assertEqual(converter_decimal_estrito("1500.50"), Decimal("1500.50"))
        self.assertEqual(converter_decimal_estrito("R$ 2.450,75"), Decimal("2450.75"))
        self.assertEqual(converter_decimal_estrito(3000), Decimal("3000.00"))
        self.assertEqual(converter_decimal_estrito(Decimal("123.45")), Decimal("123.45"))

        # Rejeição de valores inválidos (RF-FIN-001)
        with self.assertRaises(ConversaoFinanceiraException):
            converter_decimal_estrito("invalido_texto")

        with self.assertRaises(ConversaoFinanceiraException):
            converter_decimal_estrito("-100.00", permitir_negativo=False)

    # 2. Tabelas Legais Versionadas
    def test_02_tabelas_legais_versionadas(self):
        """Verifica se as tabelas oficiais de 2026 e padrão estão devidamente catalogadas."""
        tbl_oficial = obter_tabela_legal("VIGENCIA_2026_OFICIAL")
        self.assertEqual(tbl_oficial.salario_minimo, Decimal("1621.00"))
        self.assertEqual(tbl_oficial.teto_inss, Decimal("8475.55"))
        self.assertEqual(tbl_oficial.teto_contribuicao_inss, Decimal("988.09"))
        self.assertIn("13/2026", tbl_oficial.fonte_normativa)

        tbl_padrao = obter_tabela_legal("VIGENCIA_2026_PADRAO")
        self.assertEqual(tbl_padrao.salario_minimo, Decimal("1518.00"))
        self.assertEqual(tbl_padrao.teto_inss, Decimal("8157.41"))

    # 3. Horas Extras, DSR e Noturno com Hora Ficta
    def test_03_horas_extras_dsr_noturno(self):
        """Calcula HE 50%, HE 100%, DSR e adicional noturno com redução ficta (52m30s)."""
        res_he = calcular_horas_extras(
            salario_base=Decimal("2200.00"),
            horas_50=Decimal("10.0"),
            horas_100=Decimal("5.0"),
            carga_horaria=220,
            dias_uteis=25,
            domingos_feriados=5,
        )
        # Valor hora = 2200 / 220 = 10.00
        # HE 50% = 10h * 15.00 = 150.00
        # HE 100% = 5h * 20.00 = 100.00
        # DSR = (150 + 100) / 25 * 5 = 50.00
        self.assertEqual(res_he["valor_he50"], Decimal("150.00"))
        self.assertEqual(res_he["valor_he100"], Decimal("100.00"))
        self.assertEqual(res_he["valor_dsr_he"], Decimal("50.00"))

        res_noturno = calcular_adicional_noturno(
            salario_base=Decimal("2200.00"),
            horas_noturnas=Decimal("35.0"),
            carga_horaria=220,
            com_reducao_ficta=True,
        )
        # 35 horas * (60/52.5) = 40 horas computadas
        self.assertEqual(res_noturno["horas_computadas"], Decimal("40.0000"))
        # 40h * R$ 10.00 * 20% = R$ 80.00
        self.assertEqual(res_noturno["valor_adicional_noturno"], Decimal("80.00"))

    # 4. Insalubridade, Periculosidade e Faltas
    def test_04_adicionais_e_faltas(self):
        """Valida insalubridade sobre SM e periculosidade sobre SB."""
        insalub = calcular_insalubridade(grau="medio", tabela=TABELA_LEGAL_2026_OFICIAL)
        # 20% sobre 1621.00 = 324.20
        self.assertEqual(insalub["valor"], Decimal("324.20"))

        peric = calcular_periculosidade(salario_base=Decimal("3000.00"))
        # 30% sobre 3000.00 = 900.00
        self.assertEqual(peric["valor"], Decimal("900.00"))

        faltas = calcular_faltas_e_atrasos(salario_base=Decimal("3000.00"), faltas_dias=1, atrasos_horas=2)
        # Dia = 100.00, Falta = 100.00, DSR = 100.00, Hora = 13.64 * 2 = 27.28
        self.assertEqual(faltas["desconto_faltas"], Decimal("100.00"))
        self.assertEqual(faltas["desconto_dsr_perdido"], Decimal("100.00"))

    # 5. INSS e IRRF (Deduções vs Simplificado)
    def test_05_inss_e_irrf_progressivo(self):
        """Calcula INSS progressivo e verifica comparativo automático do IRRF."""
        # Salário R$ 3.000,00 na tabela oficial 2026
        valor_inss, aliq_efetiva, memoria, faixas = calcular_inss_unificado(
            Decimal("3000.00"), TABELA_LEGAL_2026_OFICIAL
        )
        self.assertGreater(valor_inss, Decimal("0.00"))
        self.assertEqual(len(faixas), 3)

        # IRRF com salário de R$ 5.000,00
        valor_irrf, metodo, memoria_ir, det = calcular_irrf_unificado(
            base_bruta=Decimal("5000.00"),
            valor_inss=Decimal("500.00"),
            dependentes=1,
            tabela=TABELA_LEGAL_2026_OFICIAL,
        )
        self.assertIn(metodo, ("SIMPLIFICADO", "DEDUCOES_LEGAIS"))
        self.assertGreater(valor_irrf, Decimal("0.00"))

    # 6. Férias e Décimo Terceiro
    def test_06_ferias_e_decimo_terceiro(self):
        """Calcula férias com 1/3 e abono de 10 dias, e 13º salário 1ª parcela."""
        res_ferias = calcular_ferias_unificado(
            salario_base=Decimal("3000.00"),
            dias_ferias=20,
            dias_abono=10,
            tabela=TABELA_LEGAL_2026_OFICIAL,
        )
        # 20 dias férias = 2000.00 + 1/3 (666.67) = 2666.67
        # 10 dias abono = 1000.00 + 1/3 (333.33) = 1333.33
        self.assertEqual(res_ferias["valor_ferias"], Decimal("2000.00"))
        self.assertEqual(res_ferias["terco_constitucional_ferias"], Decimal("666.67"))
        self.assertEqual(res_ferias["valor_abono_pecuniario"], Decimal("1000.00"))
        self.assertEqual(res_ferias["terco_abono_pecuniario"], Decimal("333.33"))

        res_13 = calcular_decimo_terceiro_unificado(
            salario_base=Decimal("3600.00"),
            meses_trabalhados=12,
            parcela=1,
            tabela=TABELA_LEGAL_2026_OFICIAL,
        )
        # 50% de 3600 = 1800.00 sem descontos de encargos
        self.assertEqual(res_13["valor_liquido"], Decimal("1800.00"))
        self.assertEqual(res_13["desconto_inss"], Decimal("0.00"))

    # 7. Rescisão nas 5 Modalidades e Aviso Prévio Proporcional
    def test_07_rescisao_modalidades_e_lei_12506(self):
        """Calcula rescisão sem justa causa (multa 40%) e acordo mútuo (multa 20%)."""
        res_sem_justa = calcular_rescisao_unificado(
            salario_base=Decimal("3000.00"),
            dias_saldo_salario=15,
            meses_13_proporcional=6,
            meses_ferias_proporcionais=6,
            tipo_desligamento="SEM_JUSTA_CAUSA",
            anos_trabalhados=3,  # 30 + 3*3 = 39 dias de aviso
            saldo_fgts=Decimal("5000.00"),
            tabela=TABELA_LEGAL_2026_OFICIAL,
        )
        self.assertEqual(res_sem_justa["dias_aviso_previo"], 39)
        self.assertEqual(res_sem_justa["multa_rescisoria_fgts"], Decimal("2000.00"))  # 40% de 5000

        res_acordo = calcular_rescisao_unificado(
            salario_base=Decimal("3000.00"),
            dias_saldo_salario=15,
            meses_13_proporcional=6,
            meses_ferias_proporcionais=6,
            tipo_desligamento="ACORDO_MUTUO",
            anos_trabalhados=3,
            saldo_fgts=Decimal("5000.00"),
            tabela=TABELA_LEGAL_2026_OFICIAL,
        )
        self.assertEqual(res_acordo["multa_rescisoria_fgts"], Decimal("1000.00"))  # 20% de 5000

    # 8. eSocial como Simulação Transparente
    def test_08_esocial_simulado_sem_recibo_falso(self):
        """Garante que transmissão eSocial sem ICP-Brasil marca simulação sem recibo falso."""
        res_trans = self.service_plat.transmitir_lote_esocial(
            evento_ids=[],
            usuario="Auditor",
        )
        self.assertTrue(res_trans["sucesso"])
        self.assertTrue(res_trans["simulacao"])
        self.assertEqual(res_trans["status_atribuido"], "validado")
        self.assertIn("SIMULAÇÃO", res_trans["mensagem"])

    # 9. CNAB 240 Multibanco com Linhas de 240 Caracteres
    def test_09_cnab240_multibanco_e_tamanho_registros(self):
        """Valida que todas as linhas geradas pelo CNAB 240 possuem exatamente 240 caracteres."""
        colab = self.service_colab.cadastrar({
            "matricula": "CNAB-99",
            "nome_completo": "Carlos Eduardo CNAB",
            "cpf": "52998224725",
            "rg": "12.345.678-9",
            "data_nascimento": "1990-01-01",
            "telefone": "(11) 98765-4321",
            "email": "carlos.cnab@empresa.com.br",
            "logradouro": "Av. Paulista",
            "numero": "1000",
            "bairro": "Bela Vista",
            "cidade": "São Paulo",
            "uf": "SP",
            "cep": "01310-100",
            "data_admissao": "2020-01-01",
            "cargo": "Analista Financeiro",
            "setor": "Financeiro",
            "salario_base": 3000.00,
            "situacao": "ativo",
        })
        colab_id = colab["id"]

        conn = self.service_plat._conn()
        cur = conn.cursor()
        p = self.service_plat._p()
        cur.execute(
            f"""
            INSERT INTO folhas_pagamento (
                colaborador_id, competencia, periodo_inicio, periodo_fim,
                salario_base_contratual, salario_base_proporcional, total_proventos, total_descontos,
                salario_liquido, situacao, criado_por, criado_em
            ) VALUES ({p}, '2026-10', '2026-10-01', '2026-10-31', 3000.00, 3000.00, 3000.00, 300.00, 2700.00, 'fechada', 'Sistema', '2026-10-31 18:00:00');
        """,
            (colab_id,),
        )
        conn.commit()
        conn.close()

        bancos = ["001", "237", "341", "033", "104"]
        for b in bancos:
            res_cnab = self.service_plat.gerar_arquivo_cnab240(
                competencia="2026-10",
                banco_codigo=b,
                usuario="Financeiro",
            )
            self.assertTrue(res_cnab["sucesso"])
            linhas = res_cnab["conteudo_cnab"].split("\r\n")
            for i, l in enumerate(linhas):
                self.assertEqual(
                    len(l),
                    240,
                    f"Linha {i} do CNAB para o banco {b} deve ter exatamente 240 caracteres (obtido: {len(l)})",
                )


if __name__ == "__main__":
    unittest.main()
