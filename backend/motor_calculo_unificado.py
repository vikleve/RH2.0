# -*- coding: utf-8 -*-
"""
Motor de Cálculo Unificado — RH2.0 Enterprise
Unifica e centraliza toda a lógica de cálculos da folha de pagamento, férias, 13º e rescisões.
Elimina duplicidades entre folha_calculos.py e folha_calculos_2026.py, provendo:
- Precisão Decimal estrita em conformidade com ABNT NBR 5891.
- Rastreabilidade total e Memória de Cálculo detalhada para cada rubrica.
- Versionamento legal por competência através de ParametrosTabelaLegal.
- Regras estritas de arredondamento ROUND_HALF_UP a 2 casas decimais.
"""
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple, Union

from .tabelas_legais import (
    ConversaoFinanceiraException,
    FaixaINSS,
    FaixaIRRF,
    ParametrosTabelaLegal,
    converter_decimal_estrito,
    obter_tabela_legal,
)


@dataclass
class ItemMemoriaCalculo:
    codigo_rubrica: str
    nome_rubrica: str
    tipo: str  # 'provento', 'desconto', 'informativo'
    referencia: str
    formula: str
    base_calculo: Decimal
    aliquota: Optional[Decimal]
    valor_calculado: Decimal
    detalhes: str = ""


@dataclass
class MemoriaCalculoCompleta:
    colaborador_id: Optional[int]
    competencia: str
    versao_tabela: str
    salario_base: Decimal
    total_proventos: Decimal
    total_descontos: Decimal
    salario_liquido: Decimal
    base_inss: Decimal
    valor_inss: Decimal
    base_irrf: Decimal
    valor_irrf: Decimal
    base_fgts: Decimal
    valor_fgts: Decimal
    itens: List[ItemMemoriaCalculo] = field(default_factory=list)

    def para_dicionario(self) -> Dict[str, Any]:
        return {
            "colaborador_id": self.colaborador_id,
            "competencia": self.competencia,
            "versao_tabela": self.versao_tabela,
            "salario_base": str(self.salario_base),
            "total_proventos": str(self.total_proventos),
            "total_descontos": str(self.total_descontos),
            "salario_liquido": str(self.salario_liquido),
            "base_inss": str(self.base_inss),
            "valor_inss": str(self.valor_inss),
            "base_irrf": str(self.base_irrf),
            "valor_irrf": str(self.valor_irrf),
            "base_fgts": str(self.base_fgts),
            "valor_fgts": str(self.valor_fgts),
            "itens": [
                {
                    "codigo": item.codigo_rubrica,
                    "nome": item.nome_rubrica,
                    "tipo": item.tipo,
                    "referencia": item.referencia,
                    "formula": item.formula,
                    "base": str(item.base_calculo),
                    "aliquota": str(item.aliquota) if item.aliquota is not None else None,
                    "valor": str(item.valor_calculado),
                    "detalhes": item.detalhes,
                }
                for item in self.itens
            ],
        }


# ─────────────────────────────────────────────────────────────
# 1. Base Salarial: Salário Proporcional, Horas e Dias
# ─────────────────────────────────────────────────────────────

def calcular_salario_proporcional(salario_base: Any, dias_trabalhados: int, dias_mes: int = 30) -> Decimal:
    """Calcula salário proporcional aos dias trabalhados (CLT art. 64)."""
    sb = converter_decimal_estrito(salario_base, "salario_base")
    dias = max(0, min(dias_mes, int(dias_trabalhados)))
    if dias >= dias_mes:
        return sb
    val_dia = (sb / Decimal(str(dias_mes))).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    return (val_dia * Decimal(str(dias))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_valor_hora(salario_base: Any, carga_horaria: int = 220) -> Decimal:
    """Calcula o valor da hora de trabalho com base no divisor mensal padrão."""
    sb = converter_decimal_estrito(salario_base, "salario_base")
    divisor = Decimal(str(max(1, carga_horaria)))
    return (sb / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_valor_dia(salario_base: Any, dias_mes: int = 30) -> Decimal:
    """Calcula o valor diário do salário."""
    sb = converter_decimal_estrito(salario_base, "salario_base")
    divisor = Decimal(str(max(1, dias_mes)))
    return (sb / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────────────────────
# 2. Horas Extras e DSR sobre Variáveis
# ─────────────────────────────────────────────────────────────

def calcular_horas_extras(
    salario_base: Any,
    horas_50: Any = 0,
    horas_100: Any = 0,
    carga_horaria: int = 220,
    dias_uteis: int = 25,
    domingos_feriados: int = 5,
) -> Dict[str, Any]:
    """
    Calcula horas extras a 50%, horas extras a 100% e o reflexo no DSR (Lei 605/49, Súmula 172 TST).
    """
    sb = converter_decimal_estrito(salario_base, "salario_base")
    h50 = converter_decimal_estrito(horas_50, "horas_50", permitir_nulo=True)
    h100 = converter_decimal_estrito(horas_100, "horas_100", permitir_nulo=True)

    val_hora = calcular_valor_hora(sb, carga_horaria)

    val_he50 = (val_hora * Decimal("1.50") * h50).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    val_he100 = (val_hora * Decimal("2.00") * h100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    total_he = val_he50 + val_he100
    val_dsr = Decimal("0.00")
    if total_he > Decimal("0.00") and dias_uteis > 0:
        val_dsr = (total_he / Decimal(str(dias_uteis)) * Decimal(str(domingos_feriados))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return {
        "valor_hora_normal": val_hora,
        "valor_he50": val_he50,
        "valor_he100": val_he100,
        "valor_dsr_he": val_dsr,
        "total_he_com_dsr": val_he50 + val_he100 + val_dsr,
    }


# ─────────────────────────────────────────────────────────────
# 3. Adicional Noturno e Horas Fictas Noturnas
# ─────────────────────────────────────────────────────────────

def calcular_adicional_noturno(
    salario_base: Any,
    horas_noturnas: Any,
    carga_horaria: int = 220,
    percentual_adicional: Decimal = Decimal("20.00"),
    com_reducao_ficta: bool = True,
    dias_uteis: int = 25,
    domingos_feriados: int = 5,
) -> Dict[str, Any]:
    """
    Calcula adicional noturno urbano (art. 73 CLT) considerando hora ficta reduzida (52m30s = fator 60/52.5 = 1.142857).
    """
    sb = converter_decimal_estrito(salario_base, "salario_base")
    hn = converter_decimal_estrito(horas_noturnas, "horas_noturnas", permitir_nulo=True)

    val_hora = calcular_valor_hora(sb, carga_horaria)
    fator_reducao = (Decimal("60.0") / Decimal("52.5")) if com_reducao_ficta else Decimal("1.0")

    horas_computadas = (hn * fator_reducao).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    aliquota = percentual_adicional / Decimal("100.00")
    val_adicional = (val_hora * aliquota * horas_computadas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    val_dsr_noturno = Decimal("0.00")
    if val_adicional > Decimal("0.00") and dias_uteis > 0:
        val_dsr_noturno = (val_adicional / Decimal(str(dias_uteis)) * Decimal(str(domingos_feriados))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return {
        "valor_hora_normal": val_hora,
        "horas_computadas": horas_computadas,
        "valor_adicional_noturno": val_adicional,
        "valor_dsr_noturno": val_dsr_noturno,
        "total_noturno_com_dsr": val_adicional + val_dsr_noturno,
    }


# ─────────────────────────────────────────────────────────────
# 4. Insalubridade e Periculosidade
# ─────────────────────────────────────────────────────────────

def calcular_insalubridade(grau: str, tabela: Optional[ParametrosTabelaLegal] = None) -> Dict[str, Any]:
    """Calcula adicional de insalubridade sobre o salário mínimo (10%, 20% ou 40% conforme NR-15)."""
    tbl = tabela or obter_tabela_legal()
    sm = tbl.salario_minimo

    grau_str = str(grau).strip().lower()
    if grau_str in ("maximo", "máximo", "40", "40%"):
        aliq = Decimal("40.0")
    elif grau_str in ("medio", "médio", "20", "20%"):
        aliq = Decimal("20.0")
    elif grau_str in ("minimo", "mínimo", "10", "10%"):
        aliq = Decimal("10.0")
    else:
        aliq = Decimal("0.0")

    valor = (sm * (aliq / Decimal("100.0"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "grau": grau,
        "base_salario_minimo": sm,
        "aliquota": aliq,
        "valor": valor,
    }


def calcular_periculosidade(salario_base: Any, percentual: Decimal = Decimal("30.0")) -> Dict[str, Any]:
    """Calcula adicional de periculosidade sobre o salário-base sem adicionais (CLT art. 193, § 1º)."""
    sb = converter_decimal_estrito(salario_base, "salario_base")
    valor = (sb * (percentual / Decimal("100.0"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "base_salario": sb,
        "aliquota": percentual,
        "valor": valor,
    }


# ─────────────────────────────────────────────────────────────
# 5. Faltas, Atrasos e Perda do DSR
# ─────────────────────────────────────────────────────────────

def calcular_faltas_e_atrasos(
    salario_base: Any,
    faltas_dias: int = 0,
    atrasos_horas: Any = 0,
    carga_horaria: int = 220,
    dias_mes: int = 30,
    descontar_dsr_falta: bool = True,
) -> Dict[str, Any]:
    """
    Calcula desconto de faltas injustificadas, atrasos e perda do descanso semanal remunerado (art. 6º Lei 605/49).
    """
    sb = converter_decimal_estrito(salario_base, "salario_base")
    ah = converter_decimal_estrito(atrasos_horas, "atrasos_horas", permitir_nulo=True)
    fd = max(0, int(faltas_dias))

    val_dia = calcular_valor_dia(sb, dias_mes)
    val_hora = calcular_valor_hora(sb, carga_horaria)

    desc_faltas = (val_dia * Decimal(str(fd))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    desc_atrasos = (val_hora * ah).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 1 falta injustificada na semana acarreta a perda de 1 DSR correspondente
    desc_dsr = Decimal("0.00")
    if descontar_dsr_falta and fd > 0:
        desc_dsr = (val_dia * Decimal(str(fd))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "valor_dia": val_dia,
        "valor_hora": val_hora,
        "desconto_faltas": desc_faltas,
        "desconto_atrasos": desc_atrasos,
        "desconto_dsr_perdido": desc_dsr,
        "total_desconto": desc_faltas + desc_atrasos + desc_dsr,
    }


# ─────────────────────────────────────────────────────────────
# 6. INSS Progressivo Faixa a Faixa
# ─────────────────────────────────────────────────────────────

def calcular_inss_unificado(
    base_inss: Any,
    tabela: Optional[ParametrosTabelaLegal] = None,
) -> Tuple[Decimal, Decimal, str, List[Dict[str, Any]]]:
    """
    Calcula INSS progressivo faixa a faixa conforme a Emenda Constitucional 103/2019.
    Retorna (valor_inss, aliquota_efetiva, memoria_texto, faixas_detalhadas).
    """
    tbl = tabela or obter_tabela_legal()
    base = converter_decimal_estrito(base_inss, "base_inss", permitir_nulo=True)

    if base <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00"), "Base de cálculo zerada.", []

    base_tributavel = min(base, tbl.teto_inss)
    total_inss = Decimal("0.00")
    faixas_calc = []
    linhas_memoria = []

    for idx, faixa in enumerate(tbl.faixas_inss, start=1):
        f_min = faixa.faixa_min
        f_max = faixa.faixa_max
        aliq = faixa.aliquota

        if base_tributavel < f_min:
            continue

        limite_superior = min(base_tributavel, f_max) if f_max is not None else base_tributavel
        parcela_tributavel = limite_superior - f_min
        if parcela_tributavel <= Decimal("0.00"):
            continue

        valor_faixa = (parcela_tributavel * (aliq / Decimal("100.0"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_inss += valor_faixa

        faixas_calc.append({
            "faixa": idx,
            "faixa_min": f_min,
            "faixa_max": f_max,
            "aliquota": aliq,
            "base_na_faixa": parcela_tributavel,
            "valor_faixa": valor_faixa,
        })
        linhas_memoria.append(
            f"Faixa {idx} ({aliq}% sobre R$ {parcela_tributavel:.2f}): R$ {valor_faixa:.2f}"
        )

    # Limitar estritamente ao teto de contribuição da tabela
    total_inss = min(total_inss, tbl.teto_contribuicao_inss).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    aliq_efetiva = ((total_inss / base) * Decimal("100.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    memoria_str = " | ".join(linhas_memoria)
    if base > tbl.teto_inss:
        memoria_str += f" | Limitado ao Teto de Contribuição: R$ {tbl.teto_contribuicao_inss:.2f}"

    return total_inss, aliq_efetiva, memoria_str, faixas_calc


# ─────────────────────────────────────────────────────────────
# 7. IRRF com Comparativo Automático Mais Vantajoso
# ─────────────────────────────────────────────────────────────

def calcular_irrf_unificado(
    base_bruta: Any,
    valor_inss: Any = 0,
    dependentes: int = 0,
    pensao_alimenticia: Any = 0,
    outros_descontos_legais: Any = 0,
    tabela: Optional[ParametrosTabelaLegal] = None,
) -> Tuple[Decimal, str, str, Dict[str, Any]]:
    """
    Calcula IRRF mensal progressivo com apuração simultânea e aplicação da opção mais vantajosa:
    Opção A: Deduções Legais (INSS + dependentes + pensão alimentícia)
    Opção B: Desconto Simplificado Mensal
    Retorna (valor_irrf, metodo_escolhido, memoria_texto, detalhes).
    """
    tbl = tabela or obter_tabela_legal()
    bruto = converter_decimal_estrito(base_bruta, "base_bruta", permitir_nulo=True)
    inss = converter_decimal_estrito(valor_inss, "valor_inss", permitir_nulo=True)
    pensao = converter_decimal_estrito(pensao_alimenticia, "pensao_alimenticia", permitir_nulo=True)
    outros = converter_decimal_estrito(outros_descontos_legais, "outros_descontos", permitir_nulo=True)
    dep_count = max(0, int(dependentes))

    # Opção A: Deduções Legais
    deducao_dependentes = Decimal(str(dep_count)) * tbl.deducao_dependente_irrf
    total_deducoes_legais = inss + deducao_dependentes + pensao + outros
    base_legal = max(Decimal("0.00"), bruto - total_deducoes_legais)

    # Opção B: Desconto Simplificado
    base_simplificada = max(Decimal("0.00"), bruto - tbl.desconto_simplificado_irrf)

    def _calcular_faixa(base_calc: Decimal) -> Tuple[Decimal, Optional[Decimal], Decimal]:
        for faixa in tbl.faixas_irrf:
            f_min = faixa.faixa_min
            f_max = faixa.faixa_max
            aliq = faixa.aliquota
            ded = faixa.deducao

            if f_max is None or base_calc <= f_max:
                if aliq == Decimal("0.0"):
                    return Decimal("0.00"), aliq, Decimal("0.00")
                imposto = (base_calc * (aliq / Decimal("100.0")) - ded).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                return max(Decimal("0.00"), imposto), aliq, ded
        return Decimal("0.00"), Decimal("0.0"), Decimal("0.00")

    imposto_legal, aliq_legal, parc_legal = _calcular_faixa(base_legal)
    imposto_simplificado, aliq_simpl, parc_simpl = _calcular_faixa(base_simplificada)

    # Aplica a opção mais vantajosa (menor imposto a pagar para o colaborador)
    if imposto_simplificado < imposto_legal:
        metodo = "SIMPLIFICADO"
        imposto_final = imposto_simplificado
        base_utilizada = base_simplificada
        aliq_utilizada = aliq_simpl
        deducao_utilizada = tbl.desconto_simplificado_irrf
        memoria = f"Opção Desconto Simplificado R$ {tbl.desconto_simplificado_irrf:.2f} mais vantajosa. Base: R$ {base_simplificada:.2f}, Alíquota: {aliq_simpl}%, IRRF: R$ {imposto_final:.2f}."
    else:
        metodo = "DEDUCOES_LEGAIS"
        imposto_final = imposto_legal
        base_utilizada = base_legal
        aliq_utilizada = aliq_legal
        deducao_utilizada = total_deducoes_legais
        memoria = f"Opção Deduções Legais mais vantajosa. Deduções (INSS R$ {inss:.2f} + {dep_count} Dep R$ {deducao_dependentes:.2f}): R$ {total_deducoes_legais:.2f}. Base: R$ {base_legal:.2f}, Alíquota: {aliq_legal}%, IRRF: R$ {imposto_final:.2f}."

    detalhes = {
        "metodo": metodo,
        "base_bruta": bruto,
        "base_legal": base_legal,
        "imposto_legal": imposto_legal,
        "base_simplificada": base_simplificada,
        "imposto_simplificado": imposto_simplificado,
        "base_utilizada": base_utilizada,
        "aliquota_utilizada": aliq_utilizada,
        "imposto_final": imposto_final,
    }

    return imposto_final, metodo, memoria, detalhes


# ─────────────────────────────────────────────────────────────
# 8. FGTS e Salário Família
# ─────────────────────────────────────────────────────────────

def calcular_fgts_unificado(
    base_fgts: Any,
    tipo_contrato: str = "padrao",
    tabela: Optional[ParametrosTabelaLegal] = None,
) -> Tuple[Decimal, Decimal, str]:
    """Calcula FGTS informativo (8% padrão CLT ou 2% aprendiz conforme Lei 10.097/2000)."""
    tbl = tabela or obter_tabela_legal()
    base = converter_decimal_estrito(base_fgts, "base_fgts", permitir_nulo=True)
    tipo = str(tipo_contrato).strip().lower()

    aliq = tbl.aliquota_fgts_aprendiz if "aprendiz" in tipo else tbl.aliquota_fgts_padrao
    valor = (base * (aliq / Decimal("100.0"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    memoria = f"FGTS ({aliq}% sobre Base R$ {base:.2f}): R$ {valor:.2f}"
    return valor, aliq, memoria


def calcular_salario_familia_unificado(
    remuneracao_total: Any,
    qtd_filhos_menores_14: int = 0,
    tabela: Optional[ParametrosTabelaLegal] = None,
) -> Tuple[Decimal, str]:
    """Calcula cota de salário-família previdenciário se a remuneração estiver dentro do limite legal."""
    tbl = tabela or obter_tabela_legal()
    remun = converter_decimal_estrito(remuneracao_total, "remuneracao_total", permitir_nulo=True)
    filhos = max(0, int(qtd_filhos_menores_14))

    if filhos == 0:
        return Decimal("0.00"), "Nenhum dependente com direito ao Salário-Família."

    if remun > tbl.limite_salario_familia:
        return (
            Decimal("0.00"),
            f"Remuneração R$ {remun:.2f} superior ao teto do Salário-Família (R$ {tbl.limite_salario_familia:.2f}).",
        )

    total = (Decimal(str(filhos)) * tbl.valor_cota_salario_familia).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    memoria = f"{filhos} cota(s) de R$ {tbl.valor_cota_salario_familia:.2f} = R$ {total:.2f}"
    return total, memoria


# ─────────────────────────────────────────────────────────────
# 9. Vale-Transporte
# ─────────────────────────────────────────────────────────────

def calcular_vale_transporte_unificado(
    salario_base: Any,
    custo_total_passes: Any,
    percentual_maximo: Decimal = Decimal("6.00"),
) -> Tuple[Decimal, Decimal, str]:
    """Calcula desconto de vale-transporte (Lei 7.418/85): até 6% do salário-base, limitado ao custo dos passes."""
    sb = converter_decimal_estrito(salario_base, "salario_base")
    custo = converter_decimal_estrito(custo_total_passes, "custo_total_passes", permitir_nulo=True)

    teto_desconto = (sb * (percentual_maximo / Decimal("100.0"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    desconto = min(teto_desconto, custo)
    subsidio = max(Decimal("0.00"), custo - desconto)
    memoria = f"Custo total: R$ {custo:.2f} | Teto 6%: R$ {teto_desconto:.2f} | Desconto colaborador: R$ {desconto:.2f} | Subsídio empresa: R$ {subsidio:.2f}"
    return desconto, subsidio, memoria


# ─────────────────────────────────────────────────────────────
# 10. Férias com 1/3 Constitucional e Abono Pecuniário
# ─────────────────────────────────────────────────────────────

def calcular_ferias_unificado(
    salario_base: Any,
    dias_ferias: int = 30,
    dias_abono: int = 0,
    adiantamento_13: bool = False,
    tabela: Optional[ParametrosTabelaLegal] = None,
) -> Dict[str, Any]:
    """
    Calcula remuneração de férias (CLT art. 129 a 145):
    - Dias de gozo de férias + 1/3 constitucional
    - Abono pecuniário (venda de até 1/3 das férias = até 10 dias) + 1/3 constitucional do abono
    - Adiantamento da 1ª parcela do 13º salário (50%), se solicitado no prazo legal
    """
    tbl = tabela or obter_tabela_legal()
    sb = converter_decimal_estrito(salario_base, "salario_base")
    df = max(0, min(30, int(dias_ferias)))
    da = max(0, min(10, int(dias_abono)))

    val_dia = calcular_valor_dia(sb, 30)

    val_ferias = (val_dia * Decimal(str(df))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    terco_ferias = (val_ferias / Decimal("3.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    val_abono = (val_dia * Decimal(str(da))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    terco_abono = (val_abono / Decimal("3.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    adiant_13 = Decimal("0.00")
    if adiantamento_13:
        adiant_13 = (sb / Decimal("2.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Encargos incidem sobre férias gozadas + 1/3; abono pecuniário é verba indenizatória
    base_inss_ferias = val_ferias + terco_ferias
    inss_ferias, _, _, _ = calcular_inss_unificado(base_inss_ferias, tbl)

    base_irrf_ferias = base_inss_ferias - inss_ferias
    irrf_ferias, _, _, _ = calcular_irrf_unificado(base_irrf_ferias, valor_inss=Decimal("0.00"), dependentes=0, tabela=tbl)

    total_bruto = val_ferias + terco_ferias + val_abono + terco_abono + adiant_13
    total_descontos = inss_ferias + irrf_ferias
    total_liquido = total_bruto - total_descontos

    return {
        "salario_base": sb,
        "valor_dia": val_dia,
        "dias_gozo": df,
        "dias_abono": da,
        "valor_ferias": val_ferias,
        "terco_constitucional_ferias": terco_ferias,
        "valor_abono_pecuniario": val_abono,
        "terco_abono_pecuniario": terco_abono,
        "adiantamento_13": adiant_13,
        "base_tributavel": base_inss_ferias,
        "desconto_inss": inss_ferias,
        "desconto_irrf": irrf_ferias,
        "total_bruto": total_bruto,
        "total_descontos": total_descontos,
        "total_liquido": total_liquido,
    }


# ─────────────────────────────────────────────────────────────
# 11. Décimo Terceiro Salário (1ª e 2ª Parcelas)
# ─────────────────────────────────────────────────────────────

def calcular_decimo_terceiro_unificado(
    salario_base: Any,
    meses_trabalhados: int = 12,
    parcela: int = 1,
    adiantamento_pago: Any = 0,
    dependentes: int = 0,
    pensao_alimenticia: Any = 0,
    tabela: Optional[ParametrosTabelaLegal] = None,
) -> Dict[str, Any]:
    """
    Calcula 13º Salário (Lei 4.090/62 e Lei 4.749/65):
    - 1ª Parcela (Paga entre fev e nov): 50% do valor devido, sem retenção de encargos.
    - 2ª Parcela (Paga até 20 dez): Valor integral devido descontando a 1ª parcela, com incidência de INSS e IRRF exclusivo na fonte.
    """
    tbl = tabela or obter_tabela_legal()
    sb = converter_decimal_estrito(salario_base, "salario_base")
    meses = max(0, min(12, int(meses_trabalhados)))
    adiant = converter_decimal_estrito(adiantamento_pago, "adiantamento_pago", permitir_nulo=True)

    valor_integral = (sb * Decimal(str(meses)) / Decimal("12.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if parcela == 1:
        valor_1a = (valor_integral / Decimal("2.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        fgts_1a, _, _ = calcular_fgts_unificado(valor_1a, tabela=tbl)
        return {
            "parcela": 1,
            "meses_fracao": meses,
            "valor_bruto": valor_1a,
            "desconto_inss": Decimal("0.00"),
            "desconto_irrf": Decimal("0.00"),
            "desconto_adiantamento": Decimal("0.00"),
            "valor_liquido": valor_1a,
            "fgts_informativo": fgts_1a,
        }
    else:
        inss_2a, _, _, _ = calcular_inss_unificado(valor_integral, tbl)
        irrf_2a, _, _, _ = calcular_irrf_unificado(
            valor_integral,
            valor_inss=inss_2a,
            dependentes=dependentes,
            pensao_alimenticia=pensao_alimenticia,
            tabela=tbl,
        )
        total_descontos = inss_2a + irrf_2a + adiant
        valor_liquido = max(Decimal("0.00"), valor_integral - total_descontos)
        fgts_2a, _, _ = calcular_fgts_unificado(valor_integral - adiant, tabela=tbl)

        return {
            "parcela": 2,
            "meses_fracao": meses,
            "valor_integral": valor_integral,
            "desconto_adiantamento": adiant,
            "desconto_inss": inss_2a,
            "desconto_irrf": irrf_2a,
            "total_descontos": total_descontos,
            "valor_liquido": valor_liquido,
            "fgts_informativo": fgts_2a,
        }


# ─────────────────────────────────────────────────────────────
# 12. Rescisão de Contrato de Trabalho
# ─────────────────────────────────────────────────────────────

def calcular_rescisao_unificado(
    salario_base: Any,
    dias_saldo_salario: int,
    meses_13_proporcional: int,
    meses_ferias_proporcionais: int,
    ferias_vencidas: bool = False,
    tipo_desligamento: str = "SEM_JUSTA_CAUSA",
    anos_trabalhados: int = 0,
    aviso_previo_indenizado: bool = True,
    saldo_fgts: Any = 0,
    tabela: Optional[ParametrosTabelaLegal] = None,
) -> Dict[str, Any]:
    """
    Calcula verbas rescisórias conforme a CLT e a Lei 12.506/2011 (Aviso Prévio Proporcional).
    Modalidades:
    1. SEM_JUSTA_CAUSA: Aviso prévio, 13º prop, férias prop + vencidas + 1/3, saldo salário, multa FGTS 40%.
    2. COM_JUSTA_CAUSA: Saldo salário e férias vencidas + 1/3 (perde aviso, 13º prop, férias prop e multa FGTS).
    3. PEDIDO_DEMISSAO: Saldo salário, 13º prop, férias prop + vencidas + 1/3 (perde saque FGTS e multa 40%).
    4. ACORDO_MUTUO (Art. 484-A): Metade do aviso prévio indenizado, multa FGTS 20%, saque 80% FGTS.
    5. TERMINO_EXPERIENCIA: Saldo salário, 13º prop, férias prop + 1/3, saque FGTS sem multa.
    """
    tbl = tabela or obter_tabela_legal()
    sb = converter_decimal_estrito(salario_base, "salario_base")
    s_fgts = converter_decimal_estrito(saldo_fgts, "saldo_fgts", permitir_nulo=True)
    tipo = str(tipo_desligamento).strip().upper()

    val_dia = calcular_valor_dia(sb, 30)

    # 1. Saldo de salário
    dias_sal = max(0, min(30, int(dias_saldo_salario)))
    saldo_salario = (val_dia * Decimal(str(dias_sal))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 2. Aviso prévio proporcional (Lei 12.506/2011: 30 dias + 3 dias por ano completo, até 90)
    dias_aviso = min(90, 30 + (max(0, anos_trabalhados) * 3))
    val_aviso = Decimal("0.00")
    if aviso_previo_indenizado:
        if tipo == "SEM_JUSTA_CAUSA":
            val_aviso = (val_dia * Decimal(str(dias_aviso))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif tipo == "ACORDO_MUTUO":
            val_aviso = (val_dia * Decimal(str(dias_aviso)) / Decimal("2.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 3. 13º Proporcional
    val_13 = Decimal("0.00")
    if tipo in ("SEM_JUSTA_CAUSA", "PEDIDO_DEMISSAO", "ACORDO_MUTUO", "TERMINO_EXPERIENCIA"):
        m13 = max(0, min(12, int(meses_13_proporcional)))
        val_13 = (sb * Decimal(str(m13)) / Decimal("12.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 4. Férias Proporcionais + 1/3
    val_ferias_prop = Decimal("0.00")
    terco_ferias_prop = Decimal("0.00")
    if tipo in ("SEM_JUSTA_CAUSA", "PEDIDO_DEMISSAO", "ACORDO_MUTUO", "TERMINO_EXPERIENCIA"):
        mf = max(0, min(12, int(meses_ferias_proporcionais)))
        val_ferias_prop = (sb * Decimal(str(mf)) / Decimal("12.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        terco_ferias_prop = (val_ferias_prop / Decimal("3.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 5. Férias Vencidas + 1/3
    val_ferias_venc = Decimal("0.00")
    terco_ferias_venc = Decimal("0.00")
    if ferias_vencidas:
        val_ferias_venc = sb
        terco_ferias_venc = (val_ferias_venc / Decimal("3.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 6. Multa Rescisória do FGTS
    multa_fgts = Decimal("0.00")
    if tipo == "SEM_JUSTA_CAUSA":
        multa_fgts = (s_fgts * Decimal("0.40")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif tipo == "ACORDO_MUTUO":
        multa_fgts = (s_fgts * Decimal("0.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Encargos sobre verbas remuneratórias (saldo de salário e 13º proporcional)
    base_inss_rescisao = saldo_salario + val_13
    inss_rescisao, _, _, _ = calcular_inss_unificado(base_inss_rescisao, tbl)

    base_irrf_rescisao = base_inss_rescisao - inss_rescisao
    irrf_rescisao, _, _, _ = calcular_irrf_unificado(base_irrf_rescisao, valor_inss=Decimal("0.00"), dependentes=0, tabela=tbl)

    total_proventos = (
        saldo_salario + val_aviso + val_13 + val_ferias_prop + terco_ferias_prop + val_ferias_venc + terco_ferias_venc
    )
    total_descontos = inss_rescisao + irrf_rescisao
    total_liquido = total_proventos - total_descontos

    return {
        "tipo_desligamento": tipo,
        "saldo_salario": saldo_salario,
        "aviso_previo_indenizado": val_aviso,
        "dias_aviso_previo": dias_aviso if aviso_previo_indenizado else 0,
        "decimo_terceiro_proporcional": val_13,
        "ferias_proporcionais": val_ferias_prop,
        "terco_ferias_proporcionais": terco_ferias_prop,
        "ferias_vencidas": val_ferias_venc,
        "terco_ferias_vencidas": terco_ferias_venc,
        "multa_rescisoria_fgts": multa_fgts,
        "desconto_inss": inss_rescisao,
        "desconto_irrf": irrf_rescisao,
        "total_proventos": total_proventos,
        "total_descontos": total_descontos,
        "total_liquido": total_liquido,
    }
