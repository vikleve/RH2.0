"""
Testes Unitários da Camada de Cálculos da Folha de Pagamento
Testa isoladamente cada função matemática e regra de negócio:
- Proporcionalidade de dias
- Valor da hora normal
- Horas extras (50%, 100%, percentuais arbitrários)
- Adicional noturno (normal e com redução ficta)
- Desconto de faltas e atrasos
- DSR sobre variáveis
- INSS e IRRF progressivos
- Valores zerados e limites
- Arredondamentos comerciais (ROUND_HALF_UP)
- Bloqueio de rubricas duplicadas
- Totalizadores: Salário Líquido = Proventos - Descontos
"""
import os
import sys
import unittest
from decimal import Decimal

# Adiciona o diretório base
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.folha_calculos import (
    calcular_adicional_noturno,
    calcular_desconto_atrasos,
    calcular_desconto_faltas,
    calcular_dsr_sobre_variaveis,
    calcular_horas_extras,
    calcular_inss_progressivo,
    calcular_irrf_progressivo,
    calcular_salario_proporcional,
    calcular_valor_hora_normal,
    processar_calculo_folha,
)


class TestFolhaCalculos(unittest.TestCase):

    def test_salario_proporcional_mes_completo(self):
        """Mês completo (30 dias) deve retornar o salário-base integral."""
        valor, mem = calcular_salario_proporcional(salario_base=3000.00, dias_trabalhados=30, dias_mes=30)
        self.assertEqual(valor, Decimal("3000.00"))
        self.assertIn("30/30 dias", mem)

    def test_salario_proporcional_dias_parciais(self):
        """Trabalhou 15 dias de um mês de 30 dias: deve receber exatamente metade."""
        valor, mem = calcular_salario_proporcional(salario_base=3000.00, dias_trabalhados=15, dias_mes=30)
        self.assertEqual(valor, Decimal("1500.00"))
        self.assertIn("15 dias", mem)

    def test_salario_proporcional_admissao_no_mes(self):
        """Trabalhou 10 dias em salário fracionado (ex: R$ 3.456,78)."""
        valor, mem = calcular_salario_proporcional(salario_base=3456.78, dias_trabalhados=10, dias_mes=30)
        # 3456.78 / 30 * 10 = 1152.26
        self.assertEqual(valor, Decimal("1152.26"))

    def test_salario_proporcional_valores_zerados(self):
        """Salário zerado ou dias zerados deve retornar 0.00 sem quebrar."""
        valor, _ = calcular_salario_proporcional(salario_base=0.00, dias_trabalhados=15)
        self.assertEqual(valor, Decimal("0.00"))

        valor2, _ = calcular_salario_proporcional(salario_base=3000.00, dias_trabalhados=0)
        self.assertEqual(valor2, Decimal("0.00"))

    def test_valor_hora_normal(self):
        """Divisor padrão de 220 horas mensais."""
        # R$ 2.200,00 / 220 = R$ 10,00/h
        vh, mem = calcular_valor_hora_normal(salario_base=2200.00, divisor_horas=220.0)
        self.assertEqual(vh, Decimal("10.0000"))
        self.assertIn("220", mem)

        # Divisor 200 horas (jornada de 40h semanais)
        vh200, _ = calcular_valor_hora_normal(salario_base=3000.00, divisor_horas=200.0)
        self.assertEqual(vh200, Decimal("15.0000"))

    def test_horas_extras_50_porcento(self):
        """Hora extra com 50% de acréscimo."""
        # Hora normal: R$ 10,00. HE 50%: R$ 15,00. 10 horas = R$ 150,00.
        total, vh_extra, mem = calcular_horas_extras(valor_hora_normal=10.00, quantidade_horas=10, percentual_adicional=50.0)
        self.assertEqual(vh_extra, Decimal("15.00"))
        self.assertEqual(total, Decimal("150.00"))
        self.assertIn("50", mem)

    def test_horas_extras_100_porcento(self):
        """Hora extra de 100% (domingos e feriados)."""
        # Hora normal: R$ 20,00. HE 100%: R$ 40,00. 5 horas = R$ 200,00.
        total, vh_extra, _ = calcular_horas_extras(valor_hora_normal=20.00, quantidade_horas=5, percentual_adicional=100.0)
        self.assertEqual(vh_extra, Decimal("40.00"))
        self.assertEqual(total, Decimal("200.00"))

    def test_horas_extras_percentual_customizado(self):
        """Hora extra com percentual acordado em CCT (ex: 75%)."""
        # Hora normal: R$ 16,00. Fator 1.75 = R$ 28,00. 4 horas = R$ 112,00.
        total, vh_extra, _ = calcular_horas_extras(valor_hora_normal=16.00, quantidade_horas=4, percentual_adicional=75.0)
        self.assertEqual(vh_extra, Decimal("28.00"))
        self.assertEqual(total, Decimal("112.00"))

    def test_adicional_noturno_padrao_20_porcento(self):
        """Adicional noturno urbano (20% sobre a hora normal)."""
        # Hora normal: R$ 20,00. Adicional 20%: R$ 4,00/h. 25 horas = R$ 100,00.
        total, vh_adic, mem = calcular_adicional_noturno(valor_hora_normal=20.00, quantidade_horas=25, percentual_adicional=20.0)
        self.assertEqual(vh_adic, Decimal("4.00"))
        self.assertEqual(total, Decimal("100.00"))
        self.assertIn("20", mem)

    def test_adicional_noturno_com_reducao_ficta(self):
        """Adicional noturno com hora ficta reduzida (52m30s / fator ~1.142857)."""
        # 35 horas relógio * 1.142857 = 40 horas noturnas computadas
        # Hora normal: R$ 10,00. 20% = R$ 2,00. 40h = R$ 80,00.
        total, vh_adic, mem = calcular_adicional_noturno(
            valor_hora_normal=10.00,
            quantidade_horas=35,
            percentual_adicional=20.0,
            aplicar_reducao_ficta=True,
            fator_reducao=Decimal("1.142857")
        )
        self.assertEqual(vh_adic, Decimal("2.00"))
        self.assertEqual(total, Decimal("80.00"))
        self.assertIn("redução ficta", mem)

    def test_desconto_faltas(self):
        """Desconto de 2 faltas integrais em salário de R$ 3.000,00 (mês 30 dias)."""
        # Valor dia: R$ 100,00. 2 faltas = R$ 200,00.
        total, mem = calcular_desconto_faltas(salario_base=3000.00, dias_falta=2, dias_mes=30)
        self.assertEqual(total, Decimal("200.00"))
        self.assertIn("2 dia(s)", mem)

    def test_desconto_atrasos(self):
        """Desconto de 3.5 horas de atraso com hora normal de R$ 12,00."""
        # 3.5 * 12.00 = R$ 42,00
        total, mem = calcular_desconto_atrasos(valor_hora_normal=12.00, horas_atraso=3.5)
        self.assertEqual(total, Decimal("42.00"))
        self.assertTrue("3,5h" in mem or "3.5h" in mem)

    def test_dsr_sobre_variaveis(self):
        """Cálculo do DSR sobre horas extras (25 dias úteis e 5 domingos/feriados)."""
        # Variáveis: R$ 500,00. DSR: (500 / 25) * 5 = R$ 100,00.
        dsr, mem = calcular_dsr_sobre_variaveis(total_variaveis=500.00, dias_uteis=25, domingos_feriados=5)
        self.assertEqual(dsr, Decimal("100.00"))
        self.assertIn("DSR", mem)

    def test_inss_progressivo_primeira_faixa(self):
        """Salário dentro da 1ª faixa de INSS (7.5%)."""
        # R$ 1.500,00 x 7.5% = R$ 112,50
        inss, aliq_efetiva, mem, faixas = calcular_inss_progressivo(base_inss=1500.00)
        self.assertEqual(inss, Decimal("112.50"))
        self.assertEqual(aliq_efetiva, Decimal("7.50"))
        self.assertEqual(len(faixas), 1)

    def test_inss_progressivo_multiplas_faixas(self):
        """Salário de R$ 3.000,00 incide na 1ª, 2ª e parte da 3ª faixa."""
        inss, aliq, mem, faixas = calcular_inss_progressivo(base_inss=3000.00)
        # Faixa 1 (1518 * 0.075) = 113.85
        # Faixa 2 ((2793.88 - 1518.01) * 0.09 = 1275.87 * 0.09) = 114.83
        # Faixa 3 ((3000 - 2793.89) * 0.12 = 206.11 * 0.12) = 24.73
        # Total esperado: 113.85 + 114.83 + 24.73 = 253.41
        self.assertGreater(inss, Decimal("250.00"))
        self.assertLess(inss, Decimal("260.00"))
        self.assertEqual(len(faixas), 3)

    def test_irrf_isencao(self):
        """Salário abaixo do piso de IRRF deve ser isento (R$ 0,00 de imposto)."""
        irrf, base, mem = calcular_irrf_progressivo(base_bruta_irrf=2500.00, desconto_inss=200.00)
        # Base: 2500 - 200 = 2300 (abaixo de 2826.65, mas acima de 2259.20? 2300 * 0.075 = 172.50 - 169.44 = 3.06)
        # Testando com base líquida bem abaixo de 2259.20:
        irrf_isento, _, _ = calcular_irrf_progressivo(base_bruta_irrf=2000.00, desconto_inss=150.00)
        self.assertEqual(irrf_isento, Decimal("0.00"))

    def test_irrf_deducao_dependentes(self):
        """Dependentes devem reduzir a base de cálculo tributável do IRRF."""
        # Base bruta 4000, inss 400. Sem dependentes: base 3600.
        irrf_sem_dep, base_sem, _ = calcular_irrf_progressivo(base_bruta_irrf=4000.00, desconto_inss=400.00, numero_dependentes=0)
        # Com 2 dependentes (2 * 189.59 = 379.18 a deduzir da base)
        irrf_com_dep, base_com, _ = calcular_irrf_progressivo(base_bruta_irrf=4000.00, desconto_inss=400.00, numero_dependentes=2)
        self.assertLess(base_com, base_sem)
        self.assertLess(irrf_com_dep, irrf_sem_dep)

    def test_processar_folha_completa_totalizadores(self):
        """Valida que: Salário Líquido = Total de Proventos - Total de Descontos."""
        eventos = [
            {"codigo": "HE50", "quantidade": 10, "percentual": 50.0},
            {"codigo": "HE100", "quantidade": 4, "percentual": 100.0},
            {"codigo": "NOTURNO", "quantidade": 20, "percentual": 20.0},
            {"codigo": "FALTA", "quantidade": 1},
            {"codigo": "DESC_CONV", "descricao": "Convênio Farmácia", "tipo": "desconto", "valor_total": 85.50},
            {"codigo": "BONUS", "descricao": "Bônus Desempenho", "tipo": "provento", "valor_total": 500.00}
        ]

        resultado = processar_calculo_folha(
            salario_base=4400.00,
            dias_trabalhados=30,
            dias_mes=30,
            divisor_horas=220.0,
            eventos_informados=eventos,
            numero_dependentes=1,
            parametros_config={"aplicar_inss": True, "aplicar_irrf": True}
        )

        resumo = resultado["resumo"]
        proventos = Decimal(str(resumo["total_proventos"]))
        descontos = Decimal(str(resumo["total_descontos"]))
        liquido = Decimal(str(resumo["salario_liquido"]))

        # Verifica consistência estrita: Liquido == Proventos - Descontos
        self.assertEqual(liquido, proventos - descontos)
        self.assertGreater(proventos, Decimal("4400.00"))  # Salário base + HEs + Noturno + Bônus
        self.assertGreater(descontos, Decimal("0.00"))

        # Verifica presença de itens com memória de cálculo
        for item in resultado["itens"]:
            self.assertTrue(len(item["memoria_calculo"]) > 0)
            self.assertIn(item["tipo"], ("provento", "desconto", "informativo"))

    def test_bloqueio_duplicidade_de_rubrica(self):
        """Não permite lançar duas vezes a mesma rubrica com o mesmo código e tipo na folha."""
        eventos_duplicados = [
            {"codigo": "HE50", "quantidade": 5},
            {"codigo": "HE50", "quantidade": 3}
        ]
        with self.assertRaises(ValueError) as ctx:
            processar_calculo_folha(
                salario_base=3000.00,
                eventos_informados=eventos_duplicados
            )
        self.assertIn("Evento duplicado", str(ctx.exception))

    # ─────────────────────────────────────────────────────────────────────────
    # Novos Testes: Grupo A — Remuneração e Adicionais
    # ─────────────────────────────────────────────────────────────────────────

    def test_grupo_a_insalubridade_graus(self):
        """Testa Adicional de Insalubridade (0030) nos três graus: 10%, 20% e 40% sobre Salário Mínimo R$ 1.518,00."""
        # Grau mínimo 10% = R$ 151,80
        res10 = processar_calculo_folha(salario_base=3000.00, eventos_informados=[{"codigo": "0030", "referencia": 10}])
        item10 = next(it for it in res10["itens"] if it["codigo_catalogo"] == "0030")
        self.assertEqual(Decimal(str(item10["valor_total"])), Decimal("151.80"))

        # Grau médio 20% (padrão) = R$ 303,60
        res20 = processar_calculo_folha(salario_base=3000.00, eventos_informados=[{"codigo": "0030", "referencia": 20}])
        item20 = next(it for it in res20["itens"] if it["codigo_catalogo"] == "0030")
        self.assertEqual(Decimal(str(item20["valor_total"])), Decimal("303.60"))

        # Grau máximo 40% = R$ 607,20
        res40 = processar_calculo_folha(salario_base=3000.00, eventos_informados=[{"codigo": "0030", "referencia": 40}])
        item40 = next(it for it in res40["itens"] if it["codigo_catalogo"] == "0030")
        self.assertEqual(Decimal(str(item40["valor_total"])), Decimal("607.20"))

    def test_grupo_a_periculosidade_e_transferencia(self):
        """Testa Periculosidade 30% (0031) e Transferência 25% (0032) sobre salário-base."""
        res = processar_calculo_folha(
            salario_base=4000.00,
            eventos_informados=[
                {"codigo": "0031"},  # 30% de 4000 = 1200.00
                {"codigo": "0032"}   # 25% de 4000 = 1000.00
            ]
        )
        it_peric = next(it for it in res["itens"] if it["codigo_catalogo"] == "0031")
        it_transf = next(it for it in res["itens"] if it["codigo_catalogo"] == "0032")
        self.assertEqual(Decimal(str(it_peric["valor_total"])), Decimal("1200.00"))
        self.assertEqual(Decimal(str(it_transf["valor_total"])), Decimal("1000.00"))

    def test_grupo_a_gratificacao_funcao_e_quebra_caixa(self):
        """Testa Gratificação de Função 40% (0040) e Quebra de Caixa 10% (0041)."""
        res = processar_calculo_folha(
            salario_base=5000.00,
            eventos_informados=[
                {"codigo": "0040"},  # 40% CLT art. 62 = 2000.00
                {"codigo": "0041"}   # 10% = 500.00
            ]
        )
        it_grat = next(it for it in res["itens"] if it["codigo_catalogo"] == "0040")
        it_qc = next(it for it in res["itens"] if it["codigo_catalogo"] == "0041")
        self.assertEqual(Decimal(str(it_grat["valor_total"])), Decimal("2000.00"))
        self.assertEqual(Decimal(str(it_qc["valor_total"])), Decimal("500.00"))

    def test_grupo_a_plr_isencao_previdenciaria_e_fgts(self):
        """PLR (0061) tem tributação exclusiva e não incide em INSS nem FGTS."""
        res = processar_calculo_folha(
            salario_base=3000.00,
            eventos_informados=[{"codigo": "0061", "valor_total": 5000.00}]
        )
        # Base de INSS deve ser apenas o salário-base R$ 3000.00, sem o PLR
        self.assertEqual(Decimal(str(res["resumo"]["base_inss"])), Decimal("3000.00"))
        self.assertEqual(Decimal(str(res["resumo"]["base_fgts"])), Decimal("3000.00"))
        # Proventos deve somar salário (3000) + PLR (5000) = 8000
        self.assertEqual(Decimal(str(res["resumo"]["total_proventos"])), Decimal("8000.00"))

    # ─────────────────────────────────────────────────────────────────────────
    # Novos Testes: Grupo B — Férias e 13º Salário
    # ─────────────────────────────────────────────────────────────────────────

    def test_grupo_b_ferias_gozadas_e_terco(self):
        """Testa férias gozadas 30 dias (0100) e 1/3 constitucional (0101)."""
        res = processar_calculo_folha(
            salario_base=3600.00,
            eventos_informados=[
                {"codigo": "0100", "referencia": 30},
                {"codigo": "0101"}
            ]
        )
        it_f = next(it for it in res["itens"] if it["codigo_catalogo"] == "0100")
        it_t = next(it for it in res["itens"] if it["codigo_catalogo"] == "0101")
        self.assertEqual(Decimal(str(it_f["valor_total"])), Decimal("3600.00"))
        self.assertEqual(Decimal(str(it_t["valor_total"])), Decimal("1200.00"))  # 3600 / 3

    def test_grupo_b_abono_pecuniario_e_terco_sem_inss(self):
        """Abono pecuniário (0102) e 1/3 (0103) não integram base de INSS/FGTS."""
        res = processar_calculo_folha(
            salario_base=3000.00,
            eventos_informados=[
                {"codigo": "0102", "referencia": 10},  # 10 dias abono = 1000.00
                {"codigo": "0103"}                      # 1/3 abono = 333.33
            ]
        )
        it_ab = next(it for it in res["itens"] if it["codigo_catalogo"] == "0102")
        it_tab = next(it for it in res["itens"] if it["codigo_catalogo"] == "0103")
        self.assertEqual(Decimal(str(it_ab["valor_total"])), Decimal("1000.00"))
        self.assertEqual(Decimal(str(it_tab["valor_total"])), Decimal("333.33"))
        # Base de INSS deve permanecer 3000.00
        self.assertEqual(Decimal(str(res["resumo"]["base_inss"])), Decimal("3000.00"))

    def test_grupo_b_decimo_terceiro_adiantamento(self):
        """13º salário 1ª parcela (0110) corresponde a 50% e não sofre desconto de INSS nem IRRF."""
        res = processar_calculo_folha(
            salario_base=6000.00,
            eventos_informados=[{"codigo": "0110", "referencia": 12}]
        )
        it_13 = next(it for it in res["itens"] if it["codigo_catalogo"] == "0110")
        self.assertEqual(Decimal(str(it_13["valor_total"])), Decimal("3000.00"))  # 50% de 6000
        # 0110 incide FGTS, mas não incide INSS
        self.assertEqual(Decimal(str(res["resumo"]["base_inss"])), Decimal("6000.00"))  # salário base normal

    # ─────────────────────────────────────────────────────────────────────────
    # Novos Testes: Grupo C — Afastamentos e Benefícios
    # ─────────────────────────────────────────────────────────────────────────

    def test_grupo_c_salario_familia_elegivel_e_inelegivel(self):
        """Salário-Família (0202) é devido apenas para remuneração até o teto (R$ 1.906,00)."""
        # Colaborador elegível: Salário R$ 1.500,00 com 2 filhos (2 x R$ 65,00 = R$ 130,00)
        res_elegivel = processar_calculo_folha(
            salario_base=1500.00,
            numero_dependentes=2,
            eventos_informados=[{"codigo": "0202", "referencia": 2}]
        )
        it_sf = next(it for it in res_elegivel["itens"] if it["codigo_catalogo"] == "0202")
        self.assertEqual(Decimal(str(it_sf["valor_total"])), Decimal("130.00"))

        # Colaborador com salário acima do teto: Salário R$ 3.000,00 -> R$ 0,00 com memória explicativa
        res_acima_teto = processar_calculo_folha(
            salario_base=3000.00,
            numero_dependentes=2,
            eventos_informados=[{"codigo": "0202", "referencia": 2}]
        )
        it_sf2 = next(it for it in res_acima_teto["itens"] if it["codigo_catalogo"] == "0202")
        self.assertEqual(Decimal(str(it_sf2["valor_total"])), Decimal("0.00"))
        self.assertIn("excede teto legal", it_sf2["memoria_calculo"])

    def test_grupo_c_auxilio_doenca_primeiros_15_dias(self):
        """Auxílio-doença primeiros 15 dias empresa (0200): limitado a 15 dias."""
        # Informado 20 dias -> empresa paga apenas os primeiros 15 dias
        res = processar_calculo_folha(
            salario_base=3000.00,
            eventos_informados=[{"codigo": "0200", "referencia": 20}]
        )
        it_aux = next(it for it in res["itens"] if it["codigo_catalogo"] == "0200")
        # 3000 / 30 * 15 = 1500.00
        self.assertEqual(Decimal(str(it_aux["valor_total"])), Decimal("1500.00"))
        self.assertIn("15", it_aux["memoria_calculo"])

    # ─────────────────────────────────────────────────────────────────────────
    # Novos Testes: Grupo D — Verbas Rescisórias
    # ─────────────────────────────────────────────────────────────────────────

    def test_grupo_d_aviso_previo_proporcional_lei_12506(self):
        """Aviso Prévio (0300): 30 dias + 3 dias por ano de serviço, limitado a 90 dias."""
        # 5 anos de serviço: 30 + 5*3 = 45 dias
        res = processar_calculo_folha(
            salario_base=3000.00,
            eventos_informados=[{"codigo": "0300", "referencia": 5}]
        )
        it_ap = next(it for it in res["itens"] if it["codigo_catalogo"] == "0300")
        # (3000 / 30) * 45 = 4500.00
        self.assertEqual(Decimal(str(it_ap["valor_total"])), Decimal("4500.00"))
        self.assertEqual(it_ap["referencia"], 45.0)

        # 25 anos de serviço: 30 + 75 = 105 -> limitado a 90 dias
        res_teto = processar_calculo_folha(
            salario_base=3000.00,
            eventos_informados=[{"codigo": "0300", "referencia": 25}]
        )
        it_ap_teto = next(it for it in res_teto["itens"] if it["codigo_catalogo"] == "0300")
        # (3000 / 30) * 90 = 9000.00
        self.assertEqual(Decimal(str(it_ap_teto["valor_total"])), Decimal("9000.00"))
        self.assertEqual(it_ap_teto["referencia"], 90.0)

    def test_grupo_d_multa_art_477_e_479_clt(self):
        """Multa art. 477 (1 salário mensal) e Multa art. 479 (50% dos dias faltantes)."""
        res = processar_calculo_folha(
            salario_base=4000.00,
            eventos_informados=[
                {"codigo": "0302"},                     # Multa art. 477: 4000.00
                {"codigo": "0303", "referencia": 20}   # Multa art. 479: 50% de 20 dias = (4000/30)*20*0.5 = 1333.33
            ]
        )
        it_477 = next(it for it in res["itens"] if it["codigo_catalogo"] == "0302")
        it_479 = next(it for it in res["itens"] if it["codigo_catalogo"] == "0303")
        self.assertEqual(Decimal(str(it_477["valor_total"])), Decimal("4000.00"))
        self.assertEqual(Decimal(str(it_479["valor_total"])), Decimal("1333.33"))

    # ─────────────────────────────────────────────────────────────────────────
    # Novos Testes: Grupo E — Descontos
    # ─────────────────────────────────────────────────────────────────────────

    def test_grupo_e_vale_transporte_teto_6_porcento(self):
        """Vale-Transporte (0510): limitado a 6% do salário-base."""
        # Salário R$ 3.000,00 -> 6% = R$ 180,00
        res = processar_calculo_folha(
            salario_base=3000.00,
            eventos_informados=[{"codigo": "0510"}]
        )
        it_vt = next(it for it in res["itens"] if it["codigo_catalogo"] == "0510")
        self.assertEqual(Decimal(str(it_vt["valor_total"])), Decimal("180.00"))

        # Custo real informado R$ 150,00 (menor que o teto R$ 180,00) -> desconta R$ 150,00
        res_menor = processar_calculo_folha(
            salario_base=3000.00,
            eventos_informados=[{"codigo": "0510", "valor_total": 150.00}]
        )
        it_vt_menor = next(it for it in res_menor["itens"] if it["codigo_catalogo"] == "0510")
        self.assertEqual(Decimal(str(it_vt_menor["valor_total"])), Decimal("150.00"))

    def test_grupo_e_adiantamento_salarial_40_porcento(self):
        """Adiantamento Salarial quinzenal (0520): padrão 40% do salário-base."""
        res = processar_calculo_folha(
            salario_base=5000.00,
            eventos_informados=[{"codigo": "0520"}]
        )
        it_adiant = next(it for it in res["itens"] if it["codigo_catalogo"] == "0520")
        self.assertEqual(Decimal(str(it_adiant["valor_total"])), Decimal("2000.00"))  # 40% de 5000

    def test_grupo_e_faltas_reduzem_base_inss_e_fgts(self):
        """Faltas injustificadas (0530) reduzem a remuneração e a base de cálculo de INSS e FGTS."""
        # Sem falta: base = 3000.00
        res_sem_falta = processar_calculo_folha(salario_base=3000.00)
        # Com 3 faltas: 3 x (3000/30) = 300.00 de desconto
        res_com_falta = processar_calculo_folha(
            salario_base=3000.00,
            eventos_informados=[{"codigo": "0530", "referencia": 3}]
        )
        self.assertEqual(Decimal(str(res_sem_falta["resumo"]["base_inss"])), Decimal("3000.00"))
        self.assertEqual(Decimal(str(res_com_falta["resumo"]["base_inss"])), Decimal("2700.00"))
        self.assertEqual(Decimal(str(res_com_falta["resumo"]["base_fgts"])), Decimal("2700.00"))

    def test_grupo_e_pensao_alimenticia_dedutivel_irrf(self):
        """Pensão alimentícia judicial (0540) deduz da base de cálculo do IRRF."""
        res_sem_pensao = processar_calculo_folha(salario_base=6000.00)
        res_com_pensao = processar_calculo_folha(
            salario_base=6000.00,
            eventos_informados=[{"codigo": "0540", "valor_total": 800.00}]
        )
        # Base de IRRF com pensão deve ser menor
        self.assertLess(
            res_com_pensao["resumo"]["base_irrf"],
            res_sem_pensao["resumo"]["base_irrf"]
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Novos Testes: Grupo F — Informativos e Encargos Patronais
    # ─────────────────────────────────────────────────────────────────────────

    def test_grupo_f_encargos_patronais_e_nao_impacto_no_salario_liquido(self):
        """Eventos informativos (0901 a 0907) não alteram proventos, descontos ou salário líquido."""
        # Folha sem encargos patronais informativos
        res_base = processar_calculo_folha(salario_base=4000.00)

        # Folha com encargos patronais solicitados
        res_encargos = processar_calculo_folha(
            salario_base=4000.00,
            eventos_informados=[
                {"codigo": "0905"},  # INSS Patronal 20%
                {"codigo": "0906"},  # RAT/FAP
                {"codigo": "0907"}   # Terceiros 5.8%
            ]
        )

        # Valida que total_proventos, total_descontos e salario_liquido são EXATAMENTE IDÊNTICOS
        self.assertEqual(res_base["resumo"]["total_proventos"], res_encargos["resumo"]["total_proventos"])
        self.assertEqual(res_base["resumo"]["total_descontos"], res_encargos["resumo"]["total_descontos"])
        self.assertEqual(res_base["resumo"]["salario_liquido"], res_encargos["resumo"]["salario_liquido"])

        # Valida cálculo dos encargos patronais informativos
        it_patronal = next(it for it in res_encargos["itens"] if it["codigo_catalogo"] == "0905")
        self.assertEqual(it_patronal["tipo"], "informativo")
        # 20% de 4000 = 800.00
        self.assertEqual(Decimal(str(it_patronal["valor_total"])), Decimal("800.00"))

    def test_folha_completa_integrada_todos_os_grupos(self):
        """Folha ampla com rubricas dos Grupos A, B, C, D, E e F simultaneamente."""
        eventos = [
            {"codigo": "0010", "referencia": 10},     # HE 50%
            {"codigo": "0031"},                       # Periculosidade 30%
            {"codigo": "0100", "referencia": 10},     # Férias 10 dias
            {"codigo": "0101"},                       # 1/3 sobre férias
            {"codigo": "0510"},                       # Vale transporte 6%
            {"codigo": "0520"},                       # Adiantamento salarial 40%
            {"codigo": "0905"}                        # INSS patronal 20% (informativo)
        ]
        res = processar_calculo_folha(
            salario_base=5000.00,
            eventos_informados=eventos,
            numero_dependentes=1
        )
        resumo = res["resumo"]
        proventos = Decimal(str(resumo["total_proventos"]))
        descontos = Decimal(str(resumo["total_descontos"]))
        liquido = Decimal(str(resumo["salario_liquido"]))

        # Regra de ouro da folha: Líquido = Proventos - Descontos
        self.assertEqual(liquido, proventos - descontos)
        self.assertGreater(liquido, Decimal("0.00"))

        # Valida que o evento informativo 0905 foi registrado como informativo
        it_info = next(it for it in res["itens"] if it["codigo_catalogo"] == "0905")
        self.assertEqual(it_info["tipo"], "informativo")


if __name__ == "__main__":
    unittest.main()
