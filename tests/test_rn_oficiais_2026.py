"""
Validação Automatizada dos Casos de Teste Oficiais de 2026 (Volume 4, Seção 5)
Verifica conformidade estrita das fórmulas e tabelas legais de 2026.
"""
import unittest
from decimal import Decimal
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.folha_calculos_2026 import (
    calcular_inss_2026,
    calcular_irrf_2026,
    calcular_horas_extras_oficial,
    calcular_descontos_ausencia_oficial,
    calcular_salario_familia_2026,
    calcular_vale_transporte,
    calcular_rescisao_oficial,
)


class TestRegrasNegocioOficiais2026(unittest.TestCase):

    def test_caso_1_salario_3000(self):
        """Caso 1: R$ 3.000,00 -> INSS R$ 248,60; Base IRRF 2.392,80 (simplificado); IRRF final R$ 0,00"""
        inss, aliq, mem_inss, _ = calcular_inss_2026(3000.00)
        self.assertEqual(inss, Decimal("248.60"))

        irrf_final, base_irrf, imp_tabela, reducao, mem_irrf = calcular_irrf_2026(
            rendimento_bruto=3000.00,
            desconto_inss=inss
        )
        self.assertEqual(base_irrf, Decimal("2392.80"))
        self.assertEqual(imp_tabela, Decimal("0.00"))
        self.assertEqual(reducao, Decimal("0.00"))
        self.assertEqual(irrf_final, Decimal("0.00"))

    def test_caso_2_salario_5000(self):
        """Caso 2: R$ 5.000,00 -> INSS R$ 501,51; Base IRRF 4.392,80 (simplificado); Imposto tabela 312,89; Redução 312,89; IRRF final R$ 0,00"""
        inss, aliq, mem_inss, _ = calcular_inss_2026(5000.00)
        self.assertEqual(inss, Decimal("501.51"))

        irrf_final, base_irrf, imp_tabela, reducao, mem_irrf = calcular_irrf_2026(
            rendimento_bruto=5000.00,
            desconto_inss=inss
        )
        self.assertEqual(base_irrf, Decimal("4392.80"))
        self.assertEqual(imp_tabela, Decimal("312.89"))
        self.assertEqual(reducao, Decimal("312.89"))
        self.assertEqual(irrf_final, Decimal("0.00"))

    def test_caso_3_salario_6000(self):
        """Caso 3: R$ 6.000,00 -> INSS R$ 641,51; Base IRRF 5.358,49 (INSS); Imposto tabela 564,85; Redução 179,75; IRRF final R$ 385,10"""
        inss, aliq, mem_inss, _ = calcular_inss_2026(6000.00)
        self.assertEqual(inss, Decimal("641.51"))

        irrf_final, base_irrf, imp_tabela, reducao, mem_irrf = calcular_irrf_2026(
            rendimento_bruto=6000.00,
            desconto_inss=inss
        )
        self.assertEqual(base_irrf, Decimal("5358.49"))
        self.assertEqual(imp_tabela, Decimal("564.85"))
        self.assertEqual(reducao, Decimal("179.75"))
        self.assertEqual(irrf_final, Decimal("385.10"))

    def test_caso_4_salario_6500(self):
        """Caso 4: R$ 6.500,00 -> INSS R$ 711,51; Base IRRF 5.788,49 (INSS); Imposto tabela 683,10; Redução 113,18; IRRF final R$ 569,92"""
        inss, aliq, mem_inss, _ = calcular_inss_2026(6500.00)
        self.assertEqual(inss, Decimal("711.51"))

        irrf_final, base_irrf, imp_tabela, reducao, mem_irrf = calcular_irrf_2026(
            rendimento_bruto=6500.00,
            desconto_inss=inss
        )
        self.assertEqual(base_irrf, Decimal("5788.49"))
        self.assertEqual(imp_tabela, Decimal("683.10"))
        self.assertEqual(reducao, Decimal("113.18"))
        self.assertEqual(irrf_final, Decimal("569.92"))

    def test_caso_5_salario_9000_teto_inss(self):
        """Caso 5: R$ 9.000,00 -> INSS R$ 988,09 (teto); Base IRRF 8.011,91 (INSS); Imposto tabela 1.294,55; Redução 0,00; IRRF final R$ 1.294,55"""
        inss, aliq, mem_inss, _ = calcular_inss_2026(9000.00)
        self.assertEqual(inss, Decimal("988.09"))

        irrf_final, base_irrf, imp_tabela, reducao, mem_irrf = calcular_irrf_2026(
            rendimento_bruto=9000.00,
            desconto_inss=inss
        )
        self.assertEqual(base_irrf, Decimal("8011.91"))
        self.assertEqual(imp_tabela, Decimal("1294.55"))
        self.assertEqual(reducao, Decimal("0.00"))
        self.assertEqual(irrf_final, Decimal("1294.55"))

    def test_secao_5_2_horas_extras(self):
        """Seção 5.2: HE 50% e 100% com divisor 220 (salário R$ 2.200,00 -> valor-hora R$ 10,00)"""
        res = calcular_horas_extras_oficial(
            salario_base=2200.00,
            divisor_horas=220.0,
            horas_50=10,
            horas_100=10
        )
        self.assertEqual(res["valor_hora"], Decimal("10.00"))
        self.assertEqual(res["valor_he50"], Decimal("150.00")) # 10 x 10,00 x 1,50 = 150,00
        self.assertEqual(res["valor_he100"], Decimal("200.00")) # 10 x 10,00 x 2,00 = 200,00

    def test_secao_5_2_atraso_e_falta(self):
        """Seção 5.2: Atraso 45 min = R$ 7,50; Falta injustificada R$ 3.000,00 (1 falta + 1 DSR = R$ 200,00)"""
        # Atraso 45 min com valor-hora R$ 10,00 -> 45/60 * 10 = 7.50
        res = calcular_descontos_ausencia_oficial(
            salario_base=3000.00,
            valor_hora=10.00,
            dias_falta_injustificada=1,
            minutos_atraso=45,
            semanas_com_falta=1
        )
        self.assertEqual(res["desconto_atrasos"], Decimal("7.50"))
        self.assertEqual(res["desconto_faltas"], Decimal("100.00"))
        self.assertEqual(res["desconto_dsr_perdido"], Decimal("100.00"))
        self.assertEqual(res["desconto_faltas"] + res["desconto_dsr_perdido"], Decimal("200.00"))

    def test_secao_5_2_salario_familia(self):
        """Seção 5.2: Salário-família R$ 1.900,00 (2 filhos) = R$ 135,08; R$ 2.000,00 (2 filhos) = R$ 0,00"""
        val1, _ = calcular_salario_familia_2026(1900.00, 2)
        self.assertEqual(val1, Decimal("135.08")) # 2 x 67,54 = 135,08

        val2, _ = calcular_salario_familia_2026(2000.00, 2)
        self.assertEqual(val2, Decimal("0.00")) # Acima do teto R$ 1.980,38

    def test_vale_transporte_regra_teto(self):
        """VT: Menor entre 6% do salário-base e custo total do vale."""
        # Salário 3.000 -> 6% = 180,00. Custo 250,00 -> Desconto 180,00, Empresa 70,00
        desc1, emp1, _ = calcular_vale_transporte(3000.00, 250.00, optante=True)
        self.assertEqual(desc1, Decimal("180.00"))
        self.assertEqual(emp1, Decimal("70.00"))

        # Custo 100,00 < 6% (180,00) -> Desconto 100,00, Empresa 0,00
        desc2, emp2, _ = calcular_vale_transporte(3000.00, 100.00, optante=True)
        self.assertEqual(desc2, Decimal("100.00"))
        self.assertEqual(emp2, Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
