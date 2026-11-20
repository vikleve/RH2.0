"""
Camada de Cálculos da Folha de Pagamento — RH / DP (RH2.0)
Módulo desacoplado, testável, estritamente parametrizado e em conformidade com CLT,
Previdência Social, Receita Federal e eSocial.

Contempla o Catálogo Oficial de 82 Eventos Trabalhistas divididos em 6 Grupos Funcionais:
- Grupo A: Remuneração e adicionais (0001 a 0075)
- Grupo B: Férias e 13º salário (0100 a 0113)
- Grupo C: Afastamentos e benefícios (0200 a 0204)
- Grupo D: Verbas rescisórias (0300 a 0306)
- Grupo E: Descontos (0501 a 0552)
- Grupo F: Eventos informativos e encargos (0901 a 0909)

Princípios Arquiteturais:
1. Precisão decimal estrita com Decimal e arredondamento financeiro (ROUND_HALF_UP)
2. Regras parametrizáveis vigência 2026 com suporte a tabelas personalizadas
3. Rastreabilidade com Memória de Cálculo detalhada para cada rubrica
4. Totalização estrita: Salário Líquido = Total Proventos - Total Descontos
5. Eventos informativos não impactam o salário líquido nem os totais de proventos/descontos
6. Respeito às notas de governança técnica (DP-08, DP-13, DP-14, DP-15 / ADR-004)
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from .catalogo_eventos import CATALOGO_EVENTOS_FOLHA
except ImportError:
    from backend.catalogo_eventos import CATALOGO_EVENTOS_FOLHA


# ─────────────────────────────────────────────────────────────────────────────
# Conversão e Arredondamento Monetário
# ─────────────────────────────────────────────────────────────────────────────

def _to_decimal(val: Any, estrito: bool = False) -> Decimal:
    """
    Conversão financeira estrita para Decimal.
    Valores ausentes são tratados como zero somente quando o chamador os omite;
    valores explicitamente malformados, NaN ou infinitos nunca viram zero.
    """
    from .tabelas_legais import ConversaoFinanceiraException
    if val is None or val == "":
        return Decimal("0.00")
    if isinstance(val, Decimal):
        resultado = val
    else:
        try:
            texto = str(val).strip().replace("R$", "").strip()
            if "," in texto and "." not in texto:
                texto = texto.replace(",", ".")
            elif "," in texto and "." in texto:
                texto = texto.replace(".", "").replace(",", ".")
            resultado = Decimal(texto)
        except Exception as exc:
            raise ConversaoFinanceiraException(
                f"Valor monetário inválido para cálculo: {val!r}"
            ) from exc
    if not resultado.is_finite():
        raise ConversaoFinanceiraException(f"Valor monetário não finito: {val!r}")
    return resultado

def arredondar_moeda(val: Any) -> Decimal:
    """Arredonda para 2 casas decimais no padrão financeiro bancário (ROUND_HALF_UP)."""
    d = _to_decimal(val)
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def formatar_moeda(val: Any) -> str:
    """Formata Decimal como string monetária R$ 0.000,00."""
    d = arredondar_moeda(val)
    val_str = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {val_str}"


# ─────────────────────────────────────────────────────────────────────────────
# Parâmetros e Tabelas Padrão Vigentes (CLT / Previdência / RFB 2026)
# Sujeitos à parametrização por competência e validação pelo DP responsável.
# ─────────────────────────────────────────────────────────────────────────────

SALARIO_MINIMO_PADRAO_2026 = Decimal("1518.00")
LIMITE_SALARIO_FAMILIA_2026 = Decimal("1906.00")
VALOR_COTA_SALARIO_FAMILIA_2026 = Decimal("65.00")

# Parâmetros oficiais da competência 2026, Portaria Interministerial MPS/MF nº 13/2026.
TABELA_INSS_PADRAO_2026 = [
    # Limites superiores inclusivos: a base de cada faixa é calculada por diferença,
    # sem lacunas artificiais de R$ 0,01 entre faixas.
    (Decimal("0.00"), Decimal("1518.00"), Decimal("7.5")),
    (Decimal("1518.00"), Decimal("2793.88"), Decimal("9.0")),
    (Decimal("2793.88"), Decimal("4190.83"), Decimal("12.0")),
    (Decimal("4190.83"), Decimal("8157.41"), Decimal("14.0")),
]
TETO_INSS_PADRAO_2026 = Decimal("8157.41")
TETO_CONTRIBUICAO_INSS_2026 = Decimal("988.09")

TABELA_IRRF_PADRAO_2026 = [
    # (limite_superior_inclusivo, alíquota, parcela a deduzir)
    (Decimal("2428.80"), Decimal("0.0"), Decimal("0.00")),
    (Decimal("2826.65"), Decimal("7.5"), Decimal("182.16")),
    (Decimal("3751.05"), Decimal("15.0"), Decimal("394.16")),
    (Decimal("4664.68"), Decimal("22.5"), Decimal("675.49")),
    (None, Decimal("27.5"), Decimal("908.73")),
]
DEDUCAO_DEPENDENTE_IRRF_PADRAO = Decimal("189.59")
DESCONTO_SIMPLIFICADO_IRRF_PADRAO = Decimal("607.20")

ALIQUOTA_FGTS_PADRAO = Decimal("8.0")
ALIQUOTA_INSS_PATRONAL_PADRAO = Decimal("20.0")
ALIQUOTA_RAT_PADRAO = Decimal("2.0")
FAP_PADRAO = Decimal("1.0000")
ALIQUOTA_TERCEIROS_PADRAO = Decimal("5.8")

# Índices do catálogo
CATALOGO_POR_CODIGO: Dict[str, Dict[str, Any]] = {
    str(e["codigo"]).strip(): e for e in CATALOGO_EVENTOS_FOLHA
}

# Mapa de compatibilidade de aliases legados para código do catálogo oficial
MAPA_ALIAS_LEGADO: Dict[str, str] = {
    "HE50": "0010",
    "HE_50": "0010",
    "101": "0010",
    "HE100": "0011",
    "HE_100": "0011",
    "102": "0011",
    "NOTURNO": "0020",
    "ADIC_NOTURNO": "0020",
    "103": "0020",
    "DSR_HE": "0012",
    "DSR_VARIAVEIS": "0012",
    "105": "0012",
    "FALTA": "0530",
    "FALTA_DIAS": "0530",
    "201": "0530",
    "ATRASO": "0532",
    "ATRASO_HORAS": "0532",
    "202": "0532",
    "DSR_FALTA": "0531",
    "INSS": "0501",
    "501": "0501",
    "IRRF": "0505",
    "502": "0505",
    "FGTS": "0904",
    "901": "0904",
    "001": "0001",
    "SALARIO": "0001",
    "SALARIO_BASE": "0001",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. Funções de Base: Salário Proporcional e Valor da Hora
# ─────────────────────────────────────────────────────────────────────────────

def calcular_salario_proporcional(
    salario_base: Any,
    dias_trabalhados: Any = 30,
    dias_mes: int = 30
) -> Tuple[Decimal, str]:
    """
    Calcula o salário-base proporcional aos dias trabalhados no mês comercial ou civil.
    Fórmula: (salário_base / dias_mes) * dias_trabalhados
    """
    sb = _to_decimal(salario_base)
    dt = _to_decimal(dias_trabalhados)
    dm = Decimal(str(dias_mes if dias_mes > 0 else 30))

    if sb <= Decimal("0.00") or dt <= Decimal("0.00"):
        return Decimal("0.00"), f"Salário ou dias zerados: R$ {sb} / {dm} x {dt} dias"

    if dt >= dm:
        valor = arredondar_moeda(sb)
        memoria = f"Salário integral: R$ {sb:,.2f} ({dm}/{dm} dias)".replace(".", ",")
        return valor, memoria

    valor_dia = sb / dm
    total = arredondar_moeda(valor_dia * dt)
    memoria = (
        f"R$ {sb:,.2f} / {dm} dias = R$ {valor_dia:,.4f}/dia x {dt} dias = R$ {total:,.2f}"
    ).replace(".", ",")
    return total, memoria


def calcular_valor_hora_normal(
    salario_base: Any,
    divisor_horas: Any = 220.0
) -> Tuple[Decimal, str]:
    """
    Calcula o valor da hora normal do colaborador com base no salário e divisor mensal.
    Fórmula: salário_base / divisor_horas
    """
    sb = _to_decimal(salario_base)
    div = _to_decimal(divisor_horas)
    if div <= Decimal("0.00"):
        div = Decimal("220.0")

    if sb <= Decimal("0.00"):
        return Decimal("0.00"), f"Salário base zerado / divisor {div}h"

    vh = (sb / div).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    memoria = f"R$ {sb:,.2f} / {div}h = R$ {vh:,.4f}/hora".replace(".", ",")
    return vh, memoria


# ─────────────────────────────────────────────────────────────────────────────
# 2. Grupo A — Remuneração e Adicionais
# ─────────────────────────────────────────────────────────────────────────────

def calcular_horas_extras(
    valor_hora_normal: Any,
    quantidade_horas: Any,
    percentual_adicional: Any = 50.0
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula horas extras com percentual configurável (CLT art. 59 § 1º).
    Fórmula: valor_hora_normal * (1 + percentual / 100) * quantidade_horas
    Retorna: (total_arredondado, valor_hora_extra_unitaria, memoria_calculo)
    """
    vh = _to_decimal(valor_hora_normal)
    qtd = _to_decimal(quantidade_horas)
    perc = _to_decimal(percentual_adicional)

    if vh <= Decimal("0.00") or qtd <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00"), "0 hora(s) extra(s) lançada(s)"

    fator = Decimal("1.00") + (perc / Decimal("100.00"))
    vh_extra = (vh * fator).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    total = arredondar_moeda(vh_extra * qtd)

    memoria = (
        f"{qtd}h x R$ {vh_extra:,.2f} (Hora normal R$ {vh:,.2f} + {perc}%): total R$ {total:,.2f}"
    ).replace(".", ",")
    return total, arredondar_moeda(vh_extra), memoria


def calcular_adicional_noturno(
    valor_hora_normal: Any,
    quantidade_horas: Any,
    percentual_adicional: Any = 20.0,
    aplicar_reducao_ficta: bool = False,
    fator_reducao: Any = 1.142857
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula adicional noturno urbano (CLT art. 73: 20%).
    Fórmula: valor_hora_normal * (percentual / 100) * horas_computadas
    Se aplicar_reducao_ficta=True: 52m30s (fator 60/52.5 = 1.142857)
    Retorna: (total_arredondado, valor_adicional_hora, memoria_calculo)
    """
    vh = _to_decimal(valor_hora_normal)
    qtd = _to_decimal(quantidade_horas)
    perc = _to_decimal(percentual_adicional)
    fator = _to_decimal(fator_reducao) if aplicar_reducao_ficta else Decimal("1.0")

    if vh <= Decimal("0.00") or qtd <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00"), "0 hora(s) noturna(s) lançada(s)"

    horas_computadas = qtd * fator
    valor_adic_hora = (vh * (perc / Decimal("100.00"))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    total = arredondar_moeda(valor_adic_hora * horas_computadas)

    obs_reducao = f" (com redução ficta x {fator:.4f} = {horas_computadas:.2f}h)" if aplicar_reducao_ficta else ""
    memoria = (
        f"{qtd}h{obs_reducao} x R$ {valor_adic_hora:,.2f} (Adicional {perc}% de R$ {vh:,.2f}): total R$ {total:,.2f}"
    ).replace(".", ",")

    return total, arredondar_moeda(valor_adic_hora), memoria


def calcular_dsr_sobre_variaveis(
    total_variaveis: Any,
    dias_uteis: int,
    domingos_feriados: int
) -> Tuple[Decimal, str]:
    """
    Calcula DSR (Descanso Semanal Remunerado) sobre variáveis (Lei 605/1949 / Súmula 172 TST).
    Fórmula: (total_variaveis / dias_uteis) * domingos_feriados
    """
    tv = _to_decimal(total_variaveis)
    if tv <= Decimal("0.00") or dias_uteis <= 0 or domingos_feriados <= 0:
        return Decimal("0.00"), "DSR não incidente ou variáveis zeradas"

    du = Decimal(str(dias_uteis))
    df = Decimal(str(domingos_feriados))
    valor_dsr = arredondar_moeda((tv / du) * df)

    memoria = (
        f"DSR: (R$ {tv:,.2f} / {du} dias úteis) x {df} domingos/feriados = R$ {valor_dsr:,.2f}"
    ).replace(".", ",")
    return valor_dsr, memoria


def calcular_insalubridade(
    grau_ou_percentual: Any = 20.0,
    salario_minimo: Any = SALARIO_MINIMO_PADRAO_2026,
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula Adicional de Insalubridade (CLT art. 192 / Súmula Vinculante 4 STF).
    Base: Salário Mínimo nacional vigente.
    Graus: Mínimo (10%), Médio (20%), Máximo (40%).
    Retorna: (total, percentual_aplicado, memoria)
    """
    sm = _to_decimal(salario_minimo) if salario_minimo else SALARIO_MINIMO_PADRAO_2026
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("0.00"), f"Insalubridade informada: R$ {val_m:,.2f}".replace(".", ",")

    ref = _to_decimal(grau_ou_percentual)
    if ref in (Decimal("1"), Decimal("10")):
        perc = Decimal("10.0")
        grau_nome = "Mínimo (10%)"
    elif ref in (Decimal("3"), Decimal("40")):
        perc = Decimal("40.0")
        grau_nome = "Máximo (40%)"
    else:
        perc = Decimal("20.0")
        grau_nome = "Médio (20%)"

    total = arredondar_moeda(sm * (perc / Decimal("100.00")))
    memoria = f"Insalubridade Grau {grau_nome}: R$ {sm:,.2f} x {perc}% = R$ {total:,.2f}".replace(".", ",")
    return total, perc, memoria


def calcular_periculosidade(
    salario_base: Any,
    percentual: Any = 30.0,
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula Adicional de Periculosidade (CLT art. 193 § 1º).
    Base: 30% sobre o salário-base contratual (sem outros adicionais).
    Retorna: (total, percentual_aplicado, memoria)
    """
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("0.00"), f"Periculosidade informada: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    perc = _to_decimal(percentual) if _to_decimal(percentual) > Decimal("0.00") else Decimal("30.0")
    total = arredondar_moeda(sb * (perc / Decimal("100.00")))
    memoria = f"Periculosidade ({perc}% sobre R$ {sb:,.2f}): R$ {total:,.2f}".replace(".", ",")
    return total, perc, memoria


def calcular_adicional_transferencia(
    salario_base: Any,
    percentual: Any = 25.0,
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula Adicional de Transferência Provisória (CLT art. 469 § 3º: mín. 25%).
    Retorna: (total, percentual_aplicado, memoria)
    """
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("0.00"), f"Adicional transferência informado: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    perc = _to_decimal(percentual) if _to_decimal(percentual) > Decimal("0.00") else Decimal("25.0")
    total = arredondar_moeda(sb * (perc / Decimal("100.00")))
    memoria = f"Adicional de Transferência ({perc}% sobre R$ {sb:,.2f}): R$ {total:,.2f}".replace(".", ",")
    return total, perc, memoria


def calcular_anuenio_quinquenio(
    salario_base: Any,
    percentual_ou_anos: Any = 0,
    tipo: str = "tempo_servico",
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula Adicional por Tempo de Serviço (Anuênio, Triênio, Quinquênio).
    Fórmula: salário_base * (percentual / 100)
    """
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("0.00"), f"Adicional tempo serviço informado: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    perc = _to_decimal(percentual_ou_anos)
    total = arredondar_moeda(sb * (perc / Decimal("100.00")))
    memoria = f"Adicional Tempo de Serviço ({perc}% sobre R$ {sb:,.2f}): R$ {total:,.2f}".replace(".", ",")
    return total, perc, memoria


def calcular_gratificacao_funcao(
    salario_base: Any,
    percentual: Any = 40.0,
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula Gratificação de Função / Cargo de Confiança (CLT art. 62, II: mín. 40%).
    """
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("0.00"), f"Gratificação de função informada: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    perc = _to_decimal(percentual) if _to_decimal(percentual) > Decimal("0.00") else Decimal("40.0")
    total = arredondar_moeda(sb * (perc / Decimal("100.00")))
    memoria = f"Gratificação de Função ({perc}% sobre R$ {sb:,.2f}): R$ {total:,.2f}".replace(".", ",")
    return total, perc, memoria


def calcular_quebra_caixa(
    salario_base: Any,
    percentual: Any = 10.0,
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """Calcula adicional de Quebra de Caixa (padrão habitual de 10% ou valor fixo)."""
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("0.00"), f"Quebra de caixa informada: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    perc = _to_decimal(percentual) if _to_decimal(percentual) > Decimal("0.00") else Decimal("10.0")
    total = arredondar_moeda(sb * (perc / Decimal("100.00")))
    memoria = f"Quebra de Caixa ({perc}% sobre R$ {sb:,.2f}): R$ {total:,.2f}".replace(".", ",")
    return total, perc, memoria


# ─────────────────────────────────────────────────────────────────────────────
# 3. Grupo B — Férias e 13º Salário
# ─────────────────────────────────────────────────────────────────────────────

def calcular_ferias_gozadas(
    salario_base: Any,
    dias_ferias: Any = 30,
    valor_manual: Any = None
) -> Tuple[Decimal, str]:
    """Calcula remuneração de férias gozadas: (salário_base / 30) * dias_gozo."""
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), f"Férias gozadas informadas: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    dias = _to_decimal(dias_ferias) if _to_decimal(dias_ferias) > Decimal("0.00") else Decimal("30.0")
    total = arredondar_moeda((sb / Decimal("30.0")) * dias)
    memoria = f"Férias ({dias} dias): (R$ {sb:,.2f} / 30) x {dias} = R$ {total:,.2f}".replace(".", ",")
    return total, memoria


def calcular_terco_constitucional(
    valor_base_ferias: Any,
    valor_manual: Any = None
) -> Tuple[Decimal, str]:
    """Calcula 1/3 constitucional de férias (CF/88 art. 7º, XVII): valor_ferias / 3."""
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), f"1/3 constitucional informado: R$ {val_m:,.2f}".replace(".", ",")

    base = _to_decimal(valor_base_ferias)
    total = arredondar_moeda(base / Decimal("3.0"))
    memoria = f"1/3 Constitucional de Férias: R$ {base:,.2f} / 3 = R$ {total:,.2f}".replace(".", ",")
    return total, memoria


def calcular_abono_pecuniario(
    salario_base: Any,
    dias_abono: Any = 10,
    valor_manual: Any = None
) -> Tuple[Decimal, str]:
    """Calcula Abono Pecuniário de Férias (CLT art. 143: até 10 dias)."""
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), f"Abono pecuniário informado: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    dias = min(Decimal("10.0"), _to_decimal(dias_abono) if _to_decimal(dias_abono) > Decimal("0.0") else Decimal("10.0"))
    total = arredondar_moeda((sb / Decimal("30.0")) * dias)
    memoria = f"Abono Pecuniário ({dias} dias): (R$ {sb:,.2f} / 30) x {dias} = R$ {total:,.2f}".replace(".", ",")
    return total, memoria


def calcular_decimo_terceiro(
    salario_base: Any,
    avos: Any = 12,
    parcela: int = 1,
    adiantamento_pago: Any = 0,
    valor_manual: Any = None
) -> Tuple[Decimal, str]:
    """
    Calcula 13º Salário (Lei 4.090/62 e Lei 4.749/65).
    1ª parcela: 50% de (salário_base / 12 * avos)
    2ª parcela: (salário_base / 12 * avos) - adiantamento_pago
    Proporcional (rescisão): (salário_base / 12 * avos)
    """
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), f"13º Salário informado: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    n_avos = min(Decimal("12.0"), _to_decimal(avos) if _to_decimal(avos) > Decimal("0.0") else Decimal("12.0"))
    integral = (sb / Decimal("12.0")) * n_avos

    if parcela == 1:
        total = arredondar_moeda(integral * Decimal("0.50"))
        memoria = f"13º 1ª Parcela (50% de {n_avos}/12 avos de R$ {sb:,.2f}): R$ {total:,.2f}".replace(".", ",")
    elif parcela == 2:
        adiant = _to_decimal(adiantamento_pago)
        total = arredondar_moeda(max(Decimal("0.00"), integral - adiant))
        memoria = (
            f"13º 2ª Parcela ({n_avos}/12 avos R$ {integral:,.2f} - Adiantamento R$ {adiant:,.2f}): R$ {total:,.2f}"
        ).replace(".", ",")
    else:
        # Proporcional
        total = arredondar_moeda(integral)
        memoria = f"13º Proporcional ({n_avos}/12 avos de R$ {sb:,.2f}): R$ {total:,.2f}".replace(".", ",")

    return total, memoria


# ─────────────────────────────────────────────────────────────────────────────
# 4. Grupo C — Afastamentos e Benefícios Previdenciários
# ─────────────────────────────────────────────────────────────────────────────

def calcular_salario_familia(
    salario_base: Any,
    numero_dependentes: int = 0,
    limite_teto: Any = LIMITE_SALARIO_FAMILIA_2026,
    valor_cota: Any = VALOR_COTA_SALARIO_FAMILIA_2026
) -> Tuple[Decimal, str]:
    """
    Calcula Salário-Família (Lei 8.213/91 art. 65 / Portaria MPS/MF vigência 2026).
    Elegibilidade: remuneração do segurado <= limite_teto (R$ 1.906,00).
    Cota por filho até 14 anos ou inválido de qualquer idade: R$ 65,00.
    """
    sb = _to_decimal(salario_base)
    teto = _to_decimal(limite_teto) if limite_teto else LIMITE_SALARIO_FAMILIA_2026
    cota = _to_decimal(valor_cota) if valor_cota else VALOR_COTA_SALARIO_FAMILIA_2026
    dep = max(0, int(numero_dependentes))

    if dep <= 0:
        return Decimal("0.00"), "Sem dependentes elegíveis para Salário-Família"

    if sb > teto:
        memoria = (
            f"Salário-Família não concedido: Remuneração R$ {sb:,.2f} excede teto legal de R$ {teto:,.2f}"
        ).replace(".", ",")
        return Decimal("0.00"), memoria

    total = arredondar_moeda(Decimal(str(dep)) * cota)
    memoria = (
        f"Salário-Família: {dep} cota(s) x R$ {cota:,.2f} (Salário R$ {sb:,.2f} <= Teto R$ {teto:,.2f}) = R$ {total:,.2f}"
    ).replace(".", ",")
    return total, memoria


def calcular_auxilio_doenca_primeiros_dias(
    salario_base: Any,
    dias_afastamento: Any = 15,
    valor_manual: Any = None
) -> Tuple[Decimal, str]:
    """
    Calcula primeiros 15 dias de afastamento pagos pelo empregador (Lei 8.213/91 art. 60 § 3º).
    Fórmula: (salário_base / 30) * min(dias, 15)
    """
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), f"Auxílio-doença informado: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    dias = min(Decimal("15.0"), _to_decimal(dias_afastamento) if _to_decimal(dias_afastamento) > Decimal("0.0") else Decimal("15.0"))
    total = arredondar_moeda((sb / Decimal("30.0")) * dias)
    memoria = f"Auxílio-doença primeiros {dias} dias empresa: (R$ {sb:,.2f} / 30) x {dias} = R$ {total:,.2f}".replace(".", ",")
    return total, memoria


# ─────────────────────────────────────────────────────────────────────────────
# 5. Grupo D — Verbas Rescisórias
# ─────────────────────────────────────────────────────────────────────────────

def calcular_aviso_previo_indenizado(
    salario_base: Any,
    anos_servico: Any = 0,
    dias_aviso: Any = None,
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula Aviso Prévio Indenizado Proporcional (Lei 12.506/2011).
    30 dias + 3 dias por ano de serviço completo na empresa (máximo de 90 dias).
    Retorna: (total, dias_apurados, memoria)
    """
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("30.0"), f"Aviso prévio informado: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    if dias_aviso and _to_decimal(dias_aviso) >= Decimal("30.0"):
        dias = min(Decimal("90.0"), _to_decimal(dias_aviso))
    else:
        anos = max(Decimal("0.0"), _to_decimal(anos_servico))
        dias = min(Decimal("90.0"), Decimal("30.0") + (anos * Decimal("3.0")))

    total = arredondar_moeda((sb / Decimal("30.0")) * dias)
    memoria = f"Aviso Prévio Indenizado ({dias} dias): (R$ {sb:,.2f} / 30) x {dias} = R$ {total:,.2f}".replace(".", ",")
    return total, dias, memoria


def calcular_multa_art_477(
    salario_base: Any,
    valor_manual: Any = None
) -> Tuple[Decimal, str]:
    """Multa art. 477 § 8º CLT por atraso na quitação das verbas rescisórias: 1 salário mensal."""
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), f"Multa art. 477 informada: R$ {val_m:,.2f}".replace(".", ",")
    sb = _to_decimal(salario_base)
    total = arredondar_moeda(sb)
    memoria = f"Multa art. 477 CLT: 1 salário mensal = R$ {total:,.2f}".replace(".", ",")
    return total, memoria


def calcular_multa_art_479(
    salario_base: Any,
    dias_restantes: Any = 0,
    valor_manual: Any = None
) -> Tuple[Decimal, str]:
    """Multa art. 479 CLT (rescisão antecipada contrato a termo): 50% dos dias faltantes."""
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), f"Multa art. 479 informada: R$ {val_m:,.2f}".replace(".", ",")
    sb = _to_decimal(salario_base)
    dias = _to_decimal(dias_restantes)
    total = arredondar_moeda((sb / Decimal("30.0")) * dias * Decimal("0.50"))
    memoria = f"Multa art. 479 CLT (50% de {dias} dias restantes): R$ {total:,.2f}".replace(".", ",")
    return total, memoria


# ─────────────────────────────────────────────────────────────────────────────
# 6. Grupo E — Descontos
# ─────────────────────────────────────────────────────────────────────────────

def calcular_desconto_faltas(
    salario_base: Any,
    dias_falta: Any,
    dias_mes: int = 30
) -> Tuple[Decimal, str]:
    """
    Calcula desconto de faltas integrais em dias (CLT art. 473).
    Fórmula: (salário_base / dias_mes) * dias_falta
    """
    sb = _to_decimal(salario_base)
    dias = _to_decimal(dias_falta)
    dm = Decimal(str(dias_mes if dias_mes > 0 else 30))

    if sb <= Decimal("0.00") or dias <= Decimal("0.00"):
        return Decimal("0.00"), "Sem faltas a descontar"

    valor_dia = sb / dm
    total = arredondar_moeda(valor_dia * dias)
    memoria = (
        f"{dias} dia(s) de falta x R$ {valor_dia:,.2f}/dia (R$ {sb:,.2f} / {dm}): total R$ {total:,.2f}"
    ).replace(".", ",")
    return total, memoria


def calcular_desconto_atrasos(
    valor_hora_normal: Any,
    horas_atraso: Any
) -> Tuple[Decimal, str]:
    """
    Calcula o desconto de atrasos ou saídas antecipadas em horas decimais.
    Fórmula: valor_hora_normal * horas_atraso
    """
    vh = _to_decimal(valor_hora_normal)
    horas = _to_decimal(horas_atraso)

    if vh <= Decimal("0.00") or horas <= Decimal("0.00"):
        return Decimal("0.00"), "Sem atrasos a descontar"

    total = arredondar_moeda(vh * horas)
    memoria = (
        f"{horas}h de atraso x R$ {vh:,.2f}/hora normal: total R$ {total:,.2f}"
    ).replace(".", ",")
    return total, memoria


def calcular_desconto_vale_transporte(
    salario_base: Any,
    custo_total_vt: Any = None,
    percentual_maximo: Any = 6.0,
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula desconto de Vale-Transporte (Lei 7.418/1985 art. 4º).
    Desconto limitado a 6% do salário-base, ou ao custo real fornecido (o que for menor).
    Retorna: (total, percentual, memoria)
    """
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("0.00"), f"Vale-transporte informado: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    perc = _to_decimal(percentual_maximo) if _to_decimal(percentual_maximo) > Decimal("0.00") else Decimal("6.0")
    teto_legal = arredondar_moeda(sb * (perc / Decimal("100.00")))

    custo = _to_decimal(custo_total_vt)
    if custo > Decimal("0.00"):
        total = min(teto_legal, arredondar_moeda(custo))
        memoria = f"VT: menor valor entre custo real (R$ {custo:,.2f}) e teto 6% (R$ {teto_legal:,.2f}) = R$ {total:,.2f}".replace(".", ",")
    else:
        total = teto_legal
        memoria = f"VT teto legal 6% sobre salário-base R$ {sb:,.2f}: R$ {total:,.2f}".replace(".", ",")

    return total, perc, memoria


def calcular_desconto_adiantamento_salarial(
    salario_base: Any,
    percentual: Any = 40.0,
    valor_manual: Any = None
) -> Tuple[Decimal, Decimal, str]:
    """Calcula Desconto de Adiantamento Salarial quinzenal (vale - padrão 40%)."""
    val_m = _to_decimal(valor_manual)
    if val_m > Decimal("0.00"):
        return arredondar_moeda(val_m), Decimal("0.00"), f"Adiantamento informado: R$ {val_m:,.2f}".replace(".", ",")

    sb = _to_decimal(salario_base)
    perc = _to_decimal(percentual) if _to_decimal(percentual) > Decimal("0.00") else Decimal("40.0")
    total = arredondar_moeda(sb * (perc / Decimal("100.00")))
    memoria = f"Adiantamento Salarial ({perc}% sobre R$ {sb:,.2f}): R$ {total:,.2f}".replace(".", ",")
    return total, perc, memoria


def calcular_inss_progressivo(
    base_inss: Any,
    tabela_faixas: Optional[List[Tuple[Decimal, Decimal, Decimal]]] = None,
    teto_maximo: Optional[Decimal] = None
) -> Tuple[Decimal, Decimal, str, List[Dict[str, Any]]]:
    """
    Calcula o INSS progressivo por competência.
    Os limites das faixas são superiores inclusivos; a base de cada faixa
    é a diferença entre o limite atingido e o limite anterior.
    """
    base = _to_decimal(base_inss)
    if base <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00"), "Base de INSS zerada", []

    faixas = tabela_faixas if tabela_faixas is not None else TABELA_INSS_PADRAO_2026
    teto = _to_decimal(teto_maximo) if teto_maximo is not None else TETO_INSS_PADRAO_2026
    base_tributavel = min(base, teto)
    total_inss = Decimal("0.00")
    detalhes = []
    linhas_memoria = []
    limite_inferior_anterior = Decimal("0.00")

    for idx, (limite_inferior_config, limite_superior, aliq) in enumerate(faixas, start=1):
        # Aceita o formato histórico com limites mínimos separados por 0,01,
        # mas calcula sobre a faixa contínua, sem criar lacuna ou sobreposição.
        limite_superior = _to_decimal(limite_superior)
        if base_tributavel <= limite_inferior_anterior:
            break
        limite_aplicado = min(base_tributavel, limite_superior)
        base_faixa = max(Decimal("0.00"), limite_aplicado - limite_inferior_anterior)
        if base_faixa > 0:
            valor_faixa = base_faixa * _to_decimal(aliq) / Decimal("100.00")
            total_inss += valor_faixa
            detalhes.append({
                "faixa": idx,
                "de": float(limite_inferior_anterior),
                "ate": float(limite_aplicado),
                "base_faixa": float(base_faixa),
                "aliquota": float(aliq),
                "desconto": float(arredondar_moeda(valor_faixa))
            })
            linhas_memoria.append(
                f"Faixa {idx} ({aliq}% sobre R$ {base_faixa:.2f}) = R$ {arredondar_moeda(valor_faixa):.2f}"
            )
        limite_inferior_anterior = limite_superior
        if base_tributavel <= limite_superior:
            break

    total_inss = arredondar_moeda(total_inss)
    if base_tributavel >= teto and teto == TETO_INSS_PADRAO_2026:
        total_inss = min(total_inss, TETO_CONTRIBUICAO_INSS_2026)
    aliquota_efetiva = (
        (total_inss / base * Decimal("100.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if base > 0 else Decimal("0.00")
    )
    memoria = " | ".join(linhas_memoria) + (
        f" | Total INSS: R$ {total_inss:.2f} (Efetiva: {aliquota_efetiva}%)"
    )
    return total_inss, aliquota_efetiva, memoria, detalhes

def calcular_irrf_progressivo(
    base_bruta_irrf: Any,
    desconto_inss: Any,
    numero_dependentes: int = 0,
    deducao_por_dependente: Optional[Decimal] = None,
    outras_deducoes: Any = 0,
    tabela_faixas: Optional[List[Tuple[Decimal, Optional[Decimal], Decimal, Decimal]]] = None,
    desconto_simplificado: Optional[Decimal] = None,
    rendimento_tributavel: Any = None,
    aplicar_reducao_lei_15270: bool = False
) -> Tuple[Decimal, Decimal, str]:
    """
    Calcula IRRF mensal comparando deduções legais e desconto simplificado,
    aplica a tabela progressiva e a redução da Lei 15.270/2025 para 2026.
    Retorna (IRRF, base escolhida, memória de cálculo).
    """
    bruta = _to_decimal(base_bruta_irrf)
    inss = _to_decimal(desconto_inss)
    deducao_dep_unit = (
        _to_decimal(deducao_por_dependente)
        if deducao_por_dependente is not None
        else DEDUCAO_DEPENDENTE_IRRF_PADRAO
    )
    total_deducao_dep = Decimal(str(max(0, int(numero_dependentes or 0)))) * deducao_dep_unit
    outras = _to_decimal(outras_deducoes)
    base_legal = max(Decimal("0.00"), bruta - inss - total_deducao_dep - outras)

    # O simplificado substitui as deduções legais (não deve ser somado ao INSS).
    simplificado = (
        _to_decimal(desconto_simplificado)
        if desconto_simplificado is not None
        else Decimal("607.20")
    )
    base_simplificada = max(Decimal("0.00"), bruta - simplificado)
    if base_simplificada < base_legal:
        base_tributavel = base_simplificada
        metodo = f"Desconto simplificado de R$ {simplificado:.2f}"
    else:
        base_tributavel = base_legal
        metodo = (
            f"Deduções legais (INSS R$ {inss:.2f}, dependentes R$ "
            f"{total_deducao_dep:.2f}, outras R$ {outras:.2f})"
        )

    faixas = tabela_faixas if tabela_faixas is not None else TABELA_IRRF_PADRAO_2026
    aliquota = Decimal("0.00")
    parcela = Decimal("0.00")
    if faixas is TABELA_IRRF_PADRAO_2026 or (
        tabela_faixas is None and faixas == TABELA_IRRF_PADRAO_2026
    ):
        # Padrão oficial 2026 representado por limites superiores inclusivos.
        for limite_superior, aliq, deduc in faixas:
            if limite_superior is None or base_tributavel <= limite_superior:
                aliquota, parcela = aliq, deduc
                break
    else:
        # Compatibilidade com tabelas personalizadas no formato legado de quatro colunas.
        for f_min, f_max, aliq, deduc in faixas:
            if base_tributavel >= f_min and (f_max is None or base_tributavel <= f_max):
                aliquota, parcela = aliq, deduc
                break

    imposto_tabela = max(
        Decimal("0.00"),
        base_tributavel * aliquota / Decimal("100.00") - parcela
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Em 2026 a redução é calculada sobre rendimentos tributáveis mensais,
    # e limitada ao imposto calculado pela tabela progressiva.
    # Aplica quando rendimento_tributavel é informado ou aplicar_reducao_lei_15270 é True
    deve_aplicar_reducao = aplicar_reducao_lei_15270 or (rendimento_tributavel is not None)
    rendimento = _to_decimal(rendimento_tributavel) if rendimento_tributavel is not None else bruta
    reducao = Decimal("0.00")
    if deve_aplicar_reducao and imposto_tabela > 0:
        if rendimento <= Decimal("5000.00"):
            reducao = min(Decimal("312.89"), imposto_tabela)
        elif rendimento <= Decimal("7350.00"):
            reducao_calculada = max(
                Decimal("0.00"),
                Decimal("978.62") - Decimal("0.133145") * rendimento
            )
            reducao = min(
                reducao_calculada.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                imposto_tabela
            )

    total_irrf = max(Decimal("0.00"), imposto_tabela - reducao).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    memoria = (
        f"{metodo}; base IRRF R$ {base_tributavel:.2f}; alíquota {aliquota}%; "
        f"imposto pela tabela R$ {imposto_tabela:.2f}; redução Lei 15.270/2025 "
        f"R$ {reducao:.2f}; IRRF final R$ {total_irrf:.2f}"
    )
    return total_irrf, arredondar_moeda(base_tributavel), memoria

# ─────────────────────────────────────────────────────────────────────────────
# 7. Grupo F — Eventos Informativos e Encargos Patronais
# ─────────────────────────────────────────────────────────────────────────────

def calcular_encargos_patronais(
    base_inss: Any,
    aliquota_patronal: Any = ALIQUOTA_INSS_PATRONAL_PADRAO,
    aliquota_rat: Any = ALIQUOTA_RAT_PADRAO,
    fap: Any = FAP_PADRAO,
    aliquota_terceiros: Any = ALIQUOTA_TERCEIROS_PADRAO
) -> Dict[str, Any]:
    """
    Calcula encargos patronais (INSS Patronal 20%, RAT x FAP, Terceiros/Sistema S).
    Todos são informativos para a empresa e NÃO impactam o salário do empregado.
    """
    base = _to_decimal(base_inss)
    aliq_pat = _to_decimal(aliquota_patronal)
    aliq_r = _to_decimal(aliquota_rat)
    fap_val = _to_decimal(fap)
    aliq_terc = _to_decimal(aliquota_terceiros)

    inss_pat = arredondar_moeda(base * (aliq_pat / Decimal("100.00")))
    rat_fap_aliq = (aliq_r * fap_val).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    rat_fap_val = arredondar_moeda(base * (rat_fap_aliq / Decimal("100.00")))
    terceiros = arredondar_moeda(base * (aliq_terc / Decimal("100.00")))
    total_encargos = inss_pat + rat_fap_val + terceiros

    return {
        "base_inss": float(arredondar_moeda(base)),
        "inss_patronal": float(inss_pat),
        "inss_patronal_memoria": f"INSS Patronal ({aliq_pat}% sobre R$ {base:,.2f}) = R$ {inss_pat:,.2f}".replace(".", ",")
        if base > 0 else "Base INSS zerada",
        "rat_fap": float(rat_fap_val),
        "rat_fap_memoria": f"RAT/FAP ({aliq_r}% x FAP {fap_val} = {rat_fap_aliq}% sobre R$ {base:,.2f}) = R$ {rat_fap_val:,.2f}".replace(".", ",")
        if base > 0 else "Base INSS zerada",
        "terceiros": float(terceiros),
        "terceiros_memoria": f"Terceiros / Sistema S ({aliq_terc}% sobre R$ {base:,.2f}) = R$ {terceiros:,.2f}".replace(".", ",")
        if base > 0 else "Base INSS zerada",
        "total_encargos_patronais": float(total_encargos)
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Motor de Consolidação de Eventos da Folha (Core Engine)
# ─────────────────────────────────────────────────────────────────────────────

def processar_calculo_folha(
    salario_base: Any,
    dias_trabalhados: Any = 30,
    dias_mes: int = 30,
    divisor_horas: Any = 220.0,
    eventos_informados: Optional[List[Dict[str, Any]]] = None,
    numero_dependentes: int = 0,
    parametros_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Processa a folha de pagamento completa com o motor unificado dos 82 eventos.
    Garante:
    1. Identificação precisa de cada evento por código do catálogo (0001 a 0909) ou alias legado
    2. Execução da fórmula correspondente com memória de cálculo auditável
    3. Respeito às incidências oficiais de INSS, IRRF e FGTS
    4. Totalização estrita: Salário Líquido = Total Proventos - Total Descontos
    5. Eventos informativos não alteram proventos, descontos ou líquido
    6. Bloqueio de duplicidade de rubricas com o mesmo código e tipo
    """
    params = parametros_config or {}
    sb = _to_decimal(salario_base)
    dm = int(dias_mes) if int(dias_mes) > 0 else 30
    dt = _to_decimal(dias_trabalhados) if dias_trabalhados is not None else Decimal(str(dm))
    div_h = _to_decimal(divisor_horas) if divisor_horas else Decimal("220.0")

    salario_minimo = _to_decimal(params.get("salario_minimo", SALARIO_MINIMO_PADRAO_2026))

    # Salário proporcional e valor da hora
    salario_prop, mem_salario_prop = calcular_salario_proporcional(sb, dt, dm)
    vh_normal, mem_vh = calcular_valor_hora_normal(sb, div_h)

    itens_consolidados: List[Dict[str, Any]] = []
    codigos_processados = set()

    def adicionar_item(
        codigo: str,
        descricao: str,
        tipo: str,
        referencia: Any,
        unidade: str,
        valor_unit: Any,
        valor_total: Any,
        memoria: str,
        origem: str = "sistema",
        codigo_catalogo: Optional[str] = None,
        incidencias: Optional[Dict[str, int]] = None
    ):
        """Adiciona item assegurando que não haja duplicidade de evento idêntico."""
        chave = (str(codigo).strip(), tipo)
        if chave in codigos_processados:
            raise ValueError(
                f"Evento duplicado na mesma folha: {codigo} ({descricao}). Não é permitido duplicar rubricas."
            )
        codigos_processados.add(chave)

        val_total_dec = arredondar_moeda(valor_total)
        inc = incidencias or {"inss": 1 if tipo == "provento" else 0, "irrf": 1 if tipo == "provento" else 0, "fgts": 1 if tipo == "provento" else 0}
        if tipo == "informativo":
            inc = {"inss": 0, "irrf": 0, "fgts": 0}

        itens_consolidados.append({
            "codigo_evento": codigo,
            "codigo_catalogo": codigo_catalogo or codigo,
            "descricao": descricao,
            "tipo": tipo,  # 'provento', 'desconto', 'informativo'
            "referencia": float(_to_decimal(referencia)),
            "unidade_referencia": unidade,
            "valor_unitario": float(arredondar_moeda(valor_unit)),
            "valor_total": float(val_total_dec),
            "origem": origem,
            "memoria_calculo": memoria,
            "inss": inc.get("inss", 0),
            "irrf": inc.get("irrf", 0),
            "fgts": inc.get("fgts", 0)
        })

    # Verificar se o usuário informou explicitamente o Salário Mensal (0001 / 001)
    eventos = list(eventos_informados or [])
    tem_salario_base_informado = False
    for ev in eventos:
        raw_cod = str(ev.get("codigo", "") or ev.get("codigo_evento", "")).strip().upper()
        if raw_cod in ("0001", "001", "SALARIO", "SALARIO_BASE"):
            tem_salario_base_informado = True
            break

    # Se não foi fornecido explicitamente, inclui o item padrão de Salário Base Proporcional
    if not tem_salario_base_informado:
        adicionar_item(
            codigo="001",
            descricao="Salário Base Mensal",
            tipo="provento",
            referencia=dt,
            unidade="dias",
            valor_unit=sb / Decimal(str(dm)),
            valor_total=salario_prop,
            memoria=mem_salario_prop,
            origem="sistema",
            codigo_catalogo="0001",
            incidencias={"inss": 1, "irrf": 1, "fgts": 1}
        )

    # Variáveis acumuladoras para DSR sobre variáveis
    total_he_para_dsr = Decimal("0.00")
    total_noturno_para_dsr = Decimal("0.00")
    total_comissoes_para_dsr = Decimal("0.00")
    eventos_informativos_informados: List[Dict[str, Any]] = []

    # Mapeamento e cálculo de cada evento informado
    for ev in eventos:
        raw_cod = str(ev.get("codigo", "") or ev.get("codigo_evento", "")).strip().upper()
        # Normalização com aliases legados
        cod_oficial = MAPA_ALIAS_LEGADO.get(raw_cod, raw_cod)
        info_cat = CATALOGO_POR_CODIGO.get(cod_oficial)

        desc = ev.get("descricao") or (info_cat["evento"] if info_cat else f"Evento {raw_cod}")
        tipo = (info_cat["tipo"] if info_cat else str(ev.get("tipo", "provento"))).strip().lower()
        if tipo not in ("provento", "desconto", "informativo"):
            tipo = "provento"

        incidencias = {
            "inss": info_cat["inss"] if info_cat else (1 if tipo == "provento" else 0),
            "irrf": info_cat["irrf"] if info_cat else (1 if tipo == "provento" else 0),
            "fgts": info_cat["fgts"] if info_cat else (1 if tipo == "provento" else 0),
        }

        qtd = _to_decimal(ev.get("quantidade") or ev.get("referencia") or 0)
        perc = _to_decimal(ev.get("percentual") or 0)
        val_manual = _to_decimal(ev.get("valor_total") or 0)
        val_unit_informado = _to_decimal(ev.get("valor_unitario") or 0)

        # Código de saída: se o usuário passou um alias legado (ex: HE50, FALTA), emite código legado histórico (101, 201)
        # Se passou o código oficial de 4 dígitos do catálogo (ex: 0010, 0530), emite o código oficial
        mapa_codigos_legados_saida = {
            "HE50": "101", "HE_50": "101", "101": "101",
            "HE100": "102", "HE_100": "102", "102": "102",
            "NOTURNO": "103", "ADIC_NOTURNO": "103", "103": "103",
            "DSR_HE": "105", "105": "105",
            "FALTA": "201", "FALTA_DIAS": "201", "201": "201",
            "ATRASO": "202", "ATRASO_HORAS": "202", "202": "202",
            "INSS": "501", "501": "501",
            "IRRF": "502", "502": "502",
            "FGTS": "901", "901": "901",
            "001": "001"
        }
        codigo_saida = mapa_codigos_legados_saida.get(raw_cod, (cod_oficial if info_cat else raw_cod))

        # ── DISPATCHER POR CÓDIGO DO CATÁLOGO ───────────────────────────────

        # 0001: Salário mensal
        if cod_oficial == "0001":
            dias_calc = qtd if qtd > Decimal("0.00") else dt
            tot, mem = calcular_salario_proporcional(sb, dias_calc, dm)
            if val_manual > Decimal("0.00"):
                tot = val_manual
                mem = f"Salário mensal informado manualmente: R$ {val_manual:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", dias_calc, "dias", sb / Decimal(str(dm)), tot, mem, "calculado", "0001", incidencias)

        # 0002: Salário horista
        elif cod_oficial == "0002":
            vh_usada = val_unit_informado if val_unit_informado > Decimal("0.00") else vh_normal
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda(vh_usada * qtd)
            mem = f"Salário horista: {qtd}h x R$ {vh_usada:,.4f}/h = R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", qtd, "horas", vh_usada, tot, mem, "calculado", "0002", incidencias)

        # 0003: Saldo de salário (rescisão)
        elif cod_oficial == "0003":
            dias_saldo = qtd if qtd > Decimal("0.00") else dt
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda((sb / Decimal("30.0")) * dias_saldo)
            mem = f"Saldo de salário rescisório: (R$ {sb:,.2f} / 30) x {dias_saldo} dias = R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", dias_saldo, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0003", incidencias)

        # 0010: Horas extras 50%
        elif cod_oficial == "0010":
            p = perc if perc > Decimal("0.00") else Decimal("50.0")
            if val_manual > Decimal("0.00"):
                tot_he = val_manual
                vh_extra = arredondar_moeda(val_manual / qtd) if qtd > 0 else Decimal("0.00")
                mem_he = f"Horas extras 50% informadas: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                tot_he, vh_extra, mem_he = calcular_horas_extras(vh_normal, qtd, p)
            adicionar_item(codigo_saida, desc, "provento", qtd, "horas", vh_extra, tot_he, mem_he, "calculado", "0010", incidencias)
            total_he_para_dsr += tot_he

        # 0011: Horas extras 100%
        elif cod_oficial == "0011":
            p = perc if perc > Decimal("0.00") else Decimal("100.0")
            if val_manual > Decimal("0.00"):
                tot_he = val_manual
                vh_extra = arredondar_moeda(val_manual / qtd) if qtd > 0 else Decimal("0.00")
                mem_he = f"Horas extras 100% informadas: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                tot_he, vh_extra, mem_he = calcular_horas_extras(vh_normal, qtd, p)
            adicionar_item(codigo_saida, desc, "provento", qtd, "horas", vh_extra, tot_he, mem_he, "calculado", "0011", incidencias)
            total_he_para_dsr += tot_he

        # 0012: DSR sobre horas extras
        elif cod_oficial == "0012":
            d_uteis = int(params.get("dias_uteis", 25))
            d_dom = int(params.get("domingos_feriados", 5))
            if val_manual > Decimal("0.00"):
                tot_dsr = val_manual
                mem_dsr = f"DSR sobre HE informado: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                base_calc = qtd if qtd > Decimal("0.00") else total_he_para_dsr
                tot_dsr, mem_dsr = calcular_dsr_sobre_variaveis(base_calc, d_uteis, d_dom)
            adicionar_item(codigo_saida, desc, "provento", d_dom, "dias", tot_dsr / Decimal(str(d_dom if d_dom > 0 else 1)), tot_dsr, mem_dsr, "calculado", "0012", incidencias)

        # 0015: Banco de horas pago
        elif cod_oficial == "0015":
            p = perc if perc > Decimal("0.00") else Decimal("50.0")
            if val_manual > Decimal("0.00"):
                tot = val_manual
                mem = f"Banco de horas pago informado: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                tot, vh_extra, mem = calcular_horas_extras(vh_normal, qtd, p)
            adicionar_item(codigo_saida, desc, "provento", qtd, "horas", vh_normal, tot, mem, "calculado", "0015", incidencias)

        # 0020: Adicional noturno
        elif cod_oficial == "0020":
            p = perc if perc > Decimal("0.00") else Decimal(str(params.get("percentual_noturno", 20.0)))
            reducao = bool(params.get("aplicar_reducao_noturna", False))
            fator_red = params.get("fator_reducao_noturna", 1.142857)
            if val_manual > Decimal("0.00"):
                tot_not = val_manual
                vh_not = arredondar_moeda(val_manual / qtd) if qtd > 0 else Decimal("0.00")
                mem_not = f"Adicional noturno informado: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                tot_not, vh_not, mem_not = calcular_adicional_noturno(vh_normal, qtd, p, reducao, fator_red)
            adicionar_item(codigo_saida, desc, "provento", qtd, "horas", vh_not, tot_not, mem_not, "calculado", "0020", incidencias)
            total_noturno_para_dsr += tot_not

        # 0021: DSR sobre adicional noturno
        elif cod_oficial == "0021":
            d_uteis = int(params.get("dias_uteis", 25))
            d_dom = int(params.get("domingos_feriados", 5))
            if val_manual > Decimal("0.00"):
                tot_dsr = val_manual
                mem_dsr = f"DSR sobre noturno informado: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                base_calc = qtd if qtd > Decimal("0.00") else total_noturno_para_dsr
                tot_dsr, mem_dsr = calcular_dsr_sobre_variaveis(base_calc, d_uteis, d_dom)
            adicionar_item(codigo_saida, desc, "provento", d_dom, "dias", tot_dsr / Decimal(str(d_dom if d_dom > 0 else 1)), tot_dsr, mem_dsr, "calculado", "0021", incidencias)

        # 0030: Adicional de insalubridade
        elif cod_oficial == "0030":
            ref_grau = qtd if qtd > Decimal("0.00") else perc
            tot, p_aplic, mem = calcular_insalubridade(ref_grau, salario_minimo, val_manual)
            adicionar_item(codigo_saida, desc, "provento", p_aplic, "%", salario_minimo, tot, mem, "calculado", "0030", incidencias)

        # 0031: Adicional de periculosidade
        elif cod_oficial == "0031":
            p = perc if perc > Decimal("0.00") else (qtd if qtd > Decimal("0.00") else Decimal("30.0"))
            tot, p_aplic, mem = calcular_periculosidade(sb, p, val_manual)
            adicionar_item(codigo_saida, desc, "provento", p_aplic, "%", sb, tot, mem, "calculado", "0031", incidencias)

        # 0032: Adicional de transferência
        elif cod_oficial == "0032":
            p = perc if perc > Decimal("0.00") else (qtd if qtd > Decimal("0.00") else Decimal("25.0"))
            tot, p_aplic, mem = calcular_adicional_transferencia(sb, p, val_manual)
            adicionar_item(codigo_saida, desc, "provento", p_aplic, "%", sb, tot, mem, "calculado", "0032", incidencias)

        # 0033: Anuênio / Quinquênio
        elif cod_oficial == "0033":
            p = perc if perc > Decimal("0.00") else qtd
            tot, p_aplic, mem = calcular_anuenio_quinquenio(sb, p, "tempo_servico", val_manual)
            adicionar_item(codigo_saida, desc, "provento", p_aplic, "%", sb, tot, mem, "calculado", "0033", incidencias)

        # 0040: Gratificação de função
        elif cod_oficial == "0040":
            p = perc if perc > Decimal("0.00") else (qtd if qtd > Decimal("0.00") else Decimal("40.0"))
            tot, p_aplic, mem = calcular_gratificacao_funcao(sb, p, val_manual)
            adicionar_item(codigo_saida, desc, "provento", p_aplic, "%", sb, tot, mem, "calculado", "0040", incidencias)

        # 0041: Quebra de caixa
        elif cod_oficial == "0041":
            p = perc if perc > Decimal("0.00") else (qtd if qtd > Decimal("0.00") else Decimal("10.0"))
            tot, p_aplic, mem = calcular_quebra_caixa(sb, p, val_manual)
            adicionar_item(codigo_saida, desc, "provento", p_aplic, "%", sb, tot, mem, "calculado", "0041", incidencias)

        # 0042: Gratificação ajustada
        elif cod_oficial == "0042":
            p = perc if perc > Decimal("0.00") else qtd
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda(sb * (p / Decimal("100.00")))
            mem = f"Gratificação ajustada ({p}% sobre R$ {sb:,.2f}): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", p, "%", sb, tot, mem, "calculado", "0042", incidencias)

        # 0050: Comissões
        elif cod_oficial == "0050":
            tot = val_manual if val_manual > Decimal("0.00") else qtd
            mem = f"Comissões auferidas no mês: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", 1, "un", tot, tot, mem, "calculado", "0050", incidencias)
            total_comissoes_para_dsr += tot

        # 0051: DSR sobre comissões
        elif cod_oficial == "0051":
            d_uteis = int(params.get("dias_uteis", 25))
            d_dom = int(params.get("domingos_feriados", 5))
            if val_manual > Decimal("0.00"):
                tot_dsr = val_manual
                mem_dsr = f"DSR sobre comissões informado: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                base_calc = qtd if qtd > Decimal("0.00") else total_comissoes_para_dsr
                tot_dsr, mem_dsr = calcular_dsr_sobre_variaveis(base_calc, d_uteis, d_dom)
            adicionar_item(codigo_saida, desc, "provento", d_dom, "dias", tot_dsr / Decimal(str(d_dom if d_dom > 0 else 1)), tot_dsr, mem_dsr, "calculado", "0051", incidencias)

        # 0060: Prêmios / Bônus habituais
        elif cod_oficial == "0060":
            tot = val_manual if val_manual > Decimal("0.00") else qtd
            mem = f"Prêmios / bônus apurados na competência: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", 1, "un", tot, tot, mem, "calculado", "0060", incidencias)

        # 0061: PLR (tributação exclusiva - sem INSS/FGTS)
        elif cod_oficial == "0061":
            tot = val_manual if val_manual > Decimal("0.00") else qtd
            mem = f"PLR Lei 10.101/2000 (tributação exclusiva na fonte): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", 1, "un", tot, tot, mem, "calculado", "0061", {"inss": 0, "irrf": 0, "fgts": 0})

        # 0070 a 0075: Gorjetas, Retroativos, Diárias, Ajuda de custo, Reembolsos, Abono indenizatório
        elif cod_oficial in ("0070", "0071", "0072", "0073", "0074", "0075"):
            tot = val_manual if val_manual > Decimal("0.00") else qtd
            mem = f"{desc}: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", 1, "un", tot, tot, mem, "calculado", cod_oficial, incidencias)

        # 0100: Férias gozadas
        elif cod_oficial == "0100":
            d_ferias = qtd if qtd > Decimal("0.00") else Decimal("30.0")
            tot, mem = calcular_ferias_gozadas(sb, d_ferias, val_manual)
            adicionar_item(codigo_saida, desc, "provento", d_ferias, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0100", incidencias)

        # 0101: 1/3 constitucional de férias
        elif cod_oficial == "0101":
            # Procura férias gozadas 0100 se já adicionadas
            base_terco = sb
            for it in itens_consolidados:
                if it["codigo_evento"] in ("0100", "100") or it["codigo_catalogo"] == "0100":
                    base_terco = _to_decimal(it["valor_total"])
                    break
            tot, mem = calcular_terco_constitucional(base_terco, val_manual)
            adicionar_item(codigo_saida, desc, "provento", Decimal("33.33"), "%", base_terco, tot, mem, "calculado", "0101", incidencias)

        # 0102: Abono pecuniário
        elif cod_oficial == "0102":
            d_abono = qtd if qtd > Decimal("0.00") else Decimal("10.0")
            tot, mem = calcular_abono_pecuniario(sb, d_abono, val_manual)
            adicionar_item(codigo_saida, desc, "provento", d_abono, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0102", incidencias)

        # 0103: 1/3 sobre abono pecuniário
        elif cod_oficial == "0103":
            base_abono = (sb / Decimal("30.0")) * Decimal("10.0")
            for it in itens_consolidados:
                if it["codigo_catalogo"] == "0102":
                    base_abono = _to_decimal(it["valor_total"])
                    break
            tot, mem = calcular_terco_constitucional(base_abono, val_manual)
            adicionar_item(codigo_saida, desc, "provento", Decimal("33.33"), "%", base_abono, tot, mem, "calculado", "0103", incidencias)

        # 0104: Férias proporcionais / indenizadas
        elif cod_oficial == "0104":
            avos = qtd if qtd > Decimal("0.00") else Decimal("12.0")
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda((sb / Decimal("12.0")) * avos)
            mem = f"Férias indenizadas ({avos}/12 avos de R$ {sb:,.2f}): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", avos, "avos", sb / Decimal("12.0"), tot, mem, "calculado", "0104", incidencias)

        # 0105: 1/3 sobre férias indenizadas
        elif cod_oficial == "0105":
            base_f = sb
            for it in itens_consolidados:
                if it["codigo_catalogo"] == "0104":
                    base_f = _to_decimal(it["valor_total"])
                    break
            tot, mem = calcular_terco_constitucional(base_f, val_manual)
            adicionar_item(codigo_saida, desc, "provento", Decimal("33.33"), "%", base_f, tot, mem, "calculado", "0105", incidencias)

        # 0110: 13º salário 1ª parcela
        elif cod_oficial == "0110":
            avos = qtd if qtd > Decimal("0.00") else Decimal("12.0")
            tot, mem = calcular_decimo_terceiro(sb, avos, parcela=1, valor_manual=val_manual)
            adicionar_item(codigo_saida, desc, "provento", avos, "avos", sb / Decimal("12.0"), tot, mem, "calculado", "0110", incidencias)

        # 0111: 13º salário 2ª parcela
        elif cod_oficial == "0111":
            avos = qtd if qtd > Decimal("0.00") else Decimal("12.0")
            adiant = _to_decimal(params.get("adiantamento_13_pago", 0))
            tot, mem = calcular_decimo_terceiro(sb, avos, parcela=2, adiantamento_pago=adiant, valor_manual=val_manual)
            adicionar_item(codigo_saida, desc, "provento", avos, "avos", sb / Decimal("12.0"), tot, mem, "calculado", "0111", incidencias)

        # 0112: 13º proporcional
        elif cod_oficial == "0112":
            avos = qtd if qtd > Decimal("0.00") else Decimal("12.0")
            tot, mem = calcular_decimo_terceiro(sb, avos, parcela=3, valor_manual=val_manual)
            adicionar_item(codigo_saida, desc, "provento", avos, "avos", sb / Decimal("12.0"), tot, mem, "calculado", "0112", incidencias)

        # 0113: Média de variáveis no 13º
        elif cod_oficial == "0113":
            tot = val_manual if val_manual > Decimal("0.00") else qtd
            mem = f"Média de variáveis computada no 13º salário: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", 1, "un", tot, tot, mem, "calculado", "0113", incidencias)

        # 0200: Auxílio-doença (15 primeiros dias)
        elif cod_oficial == "0200":
            d_afast = qtd if qtd > Decimal("0.00") else Decimal("15.0")
            tot, mem = calcular_auxilio_doenca_primeiros_dias(sb, d_afast, val_manual)
            adicionar_item(codigo_saida, desc, "provento", d_afast, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0200", incidencias)

        # 0201: Salário-maternidade
        elif cod_oficial == "0201":
            d_mat = qtd if qtd > Decimal("0.00") else Decimal("30.0")
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda((sb / Decimal("30.0")) * d_mat)
            mem = f"Salário-maternidade ({d_mat} dias): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", d_mat, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0201", incidencias)

        # 0202: Salário-família
        elif cod_oficial == "0202":
            n_filhos = int(qtd) if qtd > Decimal("0.00") else numero_dependentes
            tot, mem = calcular_salario_familia(sb, n_filhos)
            adicionar_item(codigo_saida, desc, "provento", n_filhos, "cotas", VALOR_COTA_SALARIO_FAMILIA_2026, tot, mem, "calculado", "0202", incidencias)

        # 0203: Licença remunerada
        elif cod_oficial == "0203":
            d_lic = qtd if qtd > Decimal("0.00") else Decimal("1.0")
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda((sb / Decimal("30.0")) * d_lic)
            mem = f"Licença remunerada ({d_lic} dias): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", d_lic, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0203", incidencias)

        # 0204: Licença-paternidade
        elif cod_oficial == "0204":
            d_pat = qtd if qtd > Decimal("0.00") else Decimal("5.0")
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda((sb / Decimal("30.0")) * d_pat)
            mem = f"Licença-paternidade ({d_pat} dias): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", d_pat, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0204", incidencias)

        # 0300: Aviso prévio indenizado
        elif cod_oficial == "0300":
            tot, dias_ap, mem = calcular_aviso_previo_indenizado(sb, anos_servico=qtd, dias_aviso=qtd if qtd >= Decimal("30") else None, valor_manual=val_manual)
            adicionar_item(codigo_saida, desc, "provento", dias_ap, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0300", incidencias)

        # 0301: Aviso prévio trabalhado
        elif cod_oficial == "0301":
            d_av = qtd if qtd > Decimal("0.00") else Decimal("30.0")
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda((sb / Decimal("30.0")) * d_av)
            mem = f"Aviso prévio trabalhado ({d_av} dias): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", d_av, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0301", incidencias)

        # 0302: Multa art. 477 CLT
        elif cod_oficial == "0302":
            tot, mem = calcular_multa_art_477(sb, val_manual)
            adicionar_item(codigo_saida, desc, "provento", 1, "salario", sb, tot, mem, "calculado", "0302", incidencias)

        # 0303: Multa art. 479 CLT
        elif cod_oficial == "0303":
            tot, mem = calcular_multa_art_479(sb, qtd, val_manual)
            adicionar_item(codigo_saida, desc, "provento", qtd, "dias", sb / Decimal("30.0"), tot, mem, "calculado", "0303", incidencias)

        # 0304 a 0306: Indenizações adicionais / estabilidade / licença-prêmio
        elif cod_oficial in ("0304", "0305", "0306"):
            tot = val_manual if val_manual > Decimal("0.00") else (sb if cod_oficial == "0304" else (sb * qtd if qtd > 0 else sb))
            mem = f"{desc}: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "provento", qtd if qtd > 0 else 1, "un", sb, tot, mem, "calculado", cod_oficial, incidencias)

        # 0510: Vale-transporte
        elif cod_oficial == "0510":
            tot, p_aplic, mem = calcular_desconto_vale_transporte(sb, custo_total_vt=val_manual or qtd, percentual_maximo=perc or 6.0)
            adicionar_item(codigo_saida, desc, "desconto", p_aplic, "%", sb, tot, mem, "calculado", "0510", incidencias)

        # 0511 a 0515: Vale-refeição, Saúde, Odonto, Seguro de vida, Previdência privada
        elif cod_oficial in ("0511", "0512", "0513", "0514", "0515"):
            tot = val_manual if val_manual > Decimal("0.00") else (arredondar_moeda(sb * (perc / Decimal("100.00"))) if perc > 0 else qtd)
            mem = f"{desc}: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "desconto", perc if perc > 0 else 1, "%" if perc > 0 else "un", tot, tot, mem, "calculado", cod_oficial, incidencias)

        # 0520: Adiantamento salarial
        elif cod_oficial == "0520":
            p = perc if perc > Decimal("0.00") else (qtd if qtd > Decimal("0.00") else Decimal("40.0"))
            tot, p_aplic, mem = calcular_desconto_adiantamento_salarial(sb, p, val_manual)
            adicionar_item(codigo_saida, desc, "desconto", p_aplic, "%", sb, tot, mem, "calculado", "0520", incidencias)

        # 0521 e 0522: Adiantamento 13º / férias compensação
        elif cod_oficial in ("0521", "0522"):
            tot = val_manual if val_manual > Decimal("0.00") else qtd
            mem = f"{desc}: compensação de R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "desconto", 1, "un", tot, tot, mem, "calculado", cod_oficial, incidencias)

        # 0530: Faltas injustificadas
        elif cod_oficial == "0530":
            if val_manual > Decimal("0.00"):
                tot_falta = val_manual
                mem_falta = f"Faltas informadas: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                tot_falta, mem_falta = calcular_desconto_faltas(sb, qtd, dm)
            adicionar_item(codigo_saida, desc, "desconto", qtd, "dias", sb / Decimal(str(dm)), tot_falta, mem_falta, "calculado", "0530", incidencias)

        # 0531: DSR sobre faltas
        elif cod_oficial == "0531":
            d_dsr = qtd if qtd > Decimal("0.00") else Decimal("1.0")
            tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda((sb / Decimal(str(dm))) * d_dsr)
            mem = f"Perda DSR por faltas ({d_dsr} dias): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "desconto", d_dsr, "dias", sb / Decimal(str(dm)), tot, mem, "calculado", "0531", incidencias)

        # 0532: Atrasos / saídas antecipadas
        elif cod_oficial == "0532":
            if val_manual > Decimal("0.00"):
                tot_atraso = val_manual
                mem_atraso = f"Atrasos informados: R$ {val_manual:,.2f}".replace(".", ",")
            else:
                tot_atraso, mem_atraso = calcular_desconto_atrasos(vh_normal, qtd)
            adicionar_item(codigo_saida, desc, "desconto", qtd, "horas", vh_normal, tot_atraso, mem_atraso, "calculado", "0532", incidencias)

        # 0535 a 0552: Sindicato, Pensão, Consignado, Danos, Aviso não cumprido, Multas
        elif cod_oficial in ("0535", "0536", "0540", "0541", "0545", "0550", "0551", "0552"):
            if cod_oficial == "0551":
                d_av = qtd if qtd > Decimal("0.00") else Decimal("30.0")
                tot = val_manual if val_manual > Decimal("0.00") else arredondar_moeda((sb / Decimal("30.0")) * d_av)
                mem = f"Aviso prévio não cumprido ({d_av} dias): R$ {tot:,.2f}".replace(".", ",")
            else:
                tot = val_manual if val_manual > Decimal("0.00") else (arredondar_moeda(sb * (perc / Decimal("100.00"))) if perc > 0 else qtd)
                mem = f"{desc}: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "desconto", qtd or perc or 1, "%" if perc > 0 else "un", tot, tot, mem, "calculado", cod_oficial, incidencias)

        # 0501: INSS explícito ou 0505: IRRF explícito
        elif cod_oficial in ("0501", "0502", "0505", "0506", "0507"):
            tot = val_manual if val_manual > Decimal("0.00") else qtd
            mem = f"{desc}: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(codigo_saida, desc, "desconto", 1, "%", tot, tot, mem, "calculado", cod_oficial, incidencias)

        # 0901 a 0909: Eventos informativos (coleta para cálculo posterior com bases apuradas)
        elif cod_oficial in ("0901", "0902", "0903", "0904", "0905", "0906", "0907", "0908", "0909"):
            eventos_informativos_informados.append({
                "codigo_saida": codigo_saida,
                "cod_oficial": cod_oficial,
                "desc": desc,
                "qtd": qtd,
                "perc": perc,
                "val_manual": val_manual
            })

        else:
            # Rubrica personalizada/genérica informada
            unit = val_unit_informado or (val_manual / qtd if qtd > 0 else val_manual)
            unid_ref = ev.get("unidade_referencia") or ("horas" if "HORA" in desc.upper() else "un")
            mem = ev.get("memoria_calculo") or f"Lançamento {tipo}: {desc} = R$ {val_manual:,.2f}".replace(".", ",")
            adicionar_item(
                codigo=codigo_saida or f"EV_{len(itens_consolidados)+1}",
                descricao=desc,
                tipo=tipo,
                referencia=qtd or 1,
                unidade=unid_ref,
                valor_unit=unit,
                valor_total=val_manual,
                memoria=mem,
                origem="manual",
                codigo_catalogo=cod_oficial,
                incidencias=incidencias
            )

    # ── DSR Automático se configurado e não lançado explicitamente ───────────
    dias_uteis = int(params.get("dias_uteis", 0))
    domingos_feriados = int(params.get("domingos_feriados", 0))
    if dias_uteis > 0 and domingos_feriados > 0 and (total_he_para_dsr + total_noturno_para_dsr) > Decimal("0.00"):
        # Checa se já houve evento de DSR cadastrado
        dsr_ja_existe = any(it["codigo_catalogo"] in ("0012", "0021") for it in itens_consolidados)
        if not dsr_ja_existe:
            val_dsr, mem_dsr = calcular_dsr_sobre_variaveis(
                total_he_para_dsr + total_noturno_para_dsr, dias_uteis, domingos_feriados
            )
            if val_dsr > Decimal("0.00"):
                adicionar_item(
                    codigo="105",
                    descricao="DSR sobre Variáveis",
                    tipo="provento",
                    referencia=domingos_feriados,
                    unidade="dias",
                    valor_unit=val_dsr / Decimal(str(domingos_feriados)),
                    valor_total=val_dsr,
                    memoria=mem_dsr,
                    origem="calculado",
                    codigo_catalogo="0012",
                    incidencias={"inss": 1, "irrf": 1, "fgts": 1}
                )

    # ── APURAÇÃO DINÂMICA DE BASES E ENCARGOS ────────────────────────────────

    # Base de INSS: soma dos proventos que incidem INSS - faltas/atrasos que reduzem a base
    proventos_inss = Decimal("0.00")
    descontos_redutores_inss = Decimal("0.00")
    for it in itens_consolidados:
        if it["tipo"] == "provento" and it.get("inss", 0) == 1:
            proventos_inss += _to_decimal(it["valor_total"])
        elif it["tipo"] == "desconto" and it["codigo_catalogo"] in ("0530", "0531", "0532"):
            descontos_redutores_inss += _to_decimal(it["valor_total"])

    base_inss = max(Decimal("0.00"), proventos_inss - descontos_redutores_inss)

    # Base de FGTS: proventos com incidência de FGTS - redutores
    proventos_fgts = Decimal("0.00")
    for it in itens_consolidados:
        if it["tipo"] == "provento" and it.get("fgts", 0) == 1:
            proventos_fgts += _to_decimal(it["valor_total"])
    base_fgts = max(Decimal("0.00"), proventos_fgts - descontos_redutores_inss)

    # Cálculo do INSS (se não foi lançado manualmente)
    tem_inss_cadastrado = any(it["codigo_catalogo"] in ("0501",) or it["codigo_evento"] in ("501", "0501") for it in itens_consolidados)
    val_inss = Decimal("0.00")
    aliq_inss = Decimal("0.00")

    if not tem_inss_cadastrado and params.get("aplicar_inss", True):
        tabela_inss = params.get("tabela_inss")
        teto_inss = _to_decimal(params.get("teto_inss")) if params.get("teto_inss") else None
        val_inss, aliq_inss, mem_inss, _ = calcular_inss_progressivo(base_inss, tabela_inss, teto_inss)

        if val_inss > Decimal("0.00"):
            adicionar_item(
                codigo="501",
                descricao="INSS Retido",
                tipo="desconto",
                referencia=aliq_inss,
                unidade="%",
                valor_unit=base_inss,
                valor_total=val_inss,
                memoria=mem_inss,
                origem="calculado",
                codigo_catalogo="0501",
                incidencias={"inss": 0, "irrf": 0, "fgts": 0}
            )
    elif tem_inss_cadastrado:
        for it in itens_consolidados:
            if it["codigo_catalogo"] == "0501" or it["codigo_evento"] in ("501", "0501"):
                val_inss = _to_decimal(it["valor_total"])
                break

    # Outras deduções do IRRF: Pensão alimentícia (0540) e Previdência Privada (0515)
    outras_deducoes_irrf = Decimal("0.00")
    for it in itens_consolidados:
        if it["codigo_catalogo"] in ("0540", "0515") and it["tipo"] == "desconto":
            outras_deducoes_irrf += _to_decimal(it["valor_total"])

    # Base Bruta de IRRF: proventos com incidência de IRRF - redutores
    proventos_irrf = Decimal("0.00")
    for it in itens_consolidados:
        if it["tipo"] == "provento" and it.get("irrf", 0) == 1:
            proventos_irrf += _to_decimal(it["valor_total"])
    base_bruta_irrf = max(Decimal("0.00"), proventos_irrf - descontos_redutores_inss)

    # Cálculo do IRRF (se não foi lançado manualmente)
    tem_irrf_cadastrado = any(it["codigo_catalogo"] in ("0505",) or it["codigo_evento"] in ("502", "0505") for it in itens_consolidados)
    val_irrf = Decimal("0.00")
    base_irrf_apurada = Decimal("0.00")

    if not tem_irrf_cadastrado and params.get("aplicar_irrf", True):
        tabela_irrf = params.get("tabela_irrf")
        deducao_dep = _to_decimal(params.get("deducao_dependente_irrf")) if params.get("deducao_dependente_irrf") else None
        val_irrf, base_irrf_apurada, mem_irrf = calcular_irrf_progressivo(
            base_bruta_irrf=base_bruta_irrf,
            desconto_inss=val_inss,
            numero_dependentes=numero_dependentes,
            deducao_por_dependente=deducao_dep,
            outras_deducoes=outras_deducoes_irrf,
            tabela_faixas=tabela_irrf,
            desconto_simplificado=_to_decimal(
                params.get("desconto_simplificado_irrf", DESCONTO_SIMPLIFICADO_IRRF_PADRAO)
            ),
            rendimento_tributavel=base_bruta_irrf,
            aplicar_reducao_lei_15270=True
        )

        if val_irrf > Decimal("0.00"):
            adicionar_item(
                codigo="502",
                descricao="IRRF Retido na Fonte",
                tipo="desconto",
                referencia=numero_dependentes,
                unidade="dep",
                valor_unit=base_irrf_apurada,
                valor_total=val_irrf,
                memoria=mem_irrf,
                origem="calculado",
                codigo_catalogo="0505",
                incidencias={"inss": 0, "irrf": 0, "fgts": 0}
            )

    # Item Informativo: FGTS do Mês (Depósito da Empresa - 8%)
    aliquota_fgts = _to_decimal(params.get("aliquota_fgts", ALIQUOTA_FGTS_PADRAO))
    valor_fgts = arredondar_moeda(base_fgts * (aliquota_fgts / Decimal("100.00")))
    tem_fgts_cadastrado = any(it["codigo_catalogo"] in ("0904",) or it["codigo_evento"] in ("901", "0904") for it in itens_consolidados)
    if not tem_fgts_cadastrado:
        adicionar_item(
            codigo="901",
            descricao="FGTS do Mês (Depósito da Empresa)",
            tipo="informativo",
            referencia=aliquota_fgts,
            unidade="%",
            valor_unit=base_fgts,
            valor_total=valor_fgts,
            memoria=f"Base FGTS R$ {base_fgts:,.2f} x {aliquota_fgts}% = R$ {valor_fgts:,.2f} (não descontado do colaborador)".replace(".", ","),
            origem="calculado",
            codigo_catalogo="0904",
            incidencias={"inss": 0, "irrf": 0, "fgts": 0}
        )

    # Encargos Patronais Informativos (INSS Patronal 20%, RAT/FAP, Terceiros)
    encargos = calcular_encargos_patronais(
        base_inss=base_inss,
        aliquota_patronal=params.get("aliquota_patronal", ALIQUOTA_INSS_PATRONAL_PADRAO),
        aliquota_rat=params.get("aliquota_rat", ALIQUOTA_RAT_PADRAO),
        fap=params.get("fap", FAP_PADRAO),
        aliquota_terceiros=params.get("aliquota_terceiros", ALIQUOTA_TERCEIROS_PADRAO)
    )

    if params.get("incluir_encargos_patronais", False):
        if not any(it["codigo_catalogo"] == "0905" for it in itens_consolidados):
            adicionar_item("0905", "INSS patronal (20%)", "informativo", 20.0, "%", base_inss, encargos["inss_patronal"], encargos["inss_patronal_memoria"], "calculado", "0905")
        if not any(it["codigo_catalogo"] == "0906" for it in itens_consolidados):
            adicionar_item("0906", "RAT / FAP", "informativo", params.get("aliquota_rat", 2.0), "%", base_inss, encargos["rat_fap"], encargos["rat_fap_memoria"], "calculado", "0906")
        if not any(it["codigo_catalogo"] == "0907" for it in itens_consolidados):
            adicionar_item("0907", "Contribuição a terceiros", "informativo", 5.8, "%", base_inss, encargos["terceiros"], encargos["terceiros_memoria"], "calculado", "0907")

    # Processar eventos informativos solicitados explicitamente no formulário/importação
    for ev_info in eventos_informativos_informados:
        c_oficial = ev_info["cod_oficial"]
        c_saida = ev_info["codigo_saida"]
        d_info = ev_info["desc"]
        q_info = ev_info["qtd"]
        p_info = ev_info["perc"]
        v_man = ev_info["val_manual"]

        if c_oficial == "0901":
            tot = v_man if v_man > Decimal("0.00") else base_inss
            mem = f"Base de cálculo do INSS apurada: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(c_saida, d_info, "informativo", 1, "R$", tot, tot, mem, "calculado", "0901")
        elif c_oficial == "0902":
            tot = v_man if v_man > Decimal("0.00") else base_irrf_apurada
            mem = f"Base de cálculo do IRRF apurada: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(c_saida, d_info, "informativo", 1, "R$", tot, tot, mem, "calculado", "0902")
        elif c_oficial == "0903":
            tot = v_man if v_man > Decimal("0.00") else base_fgts
            mem = f"Base de cálculo do FGTS apurada: R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(c_saida, d_info, "informativo", 1, "R$", tot, tot, mem, "calculado", "0903")
        elif c_oficial == "0904":
            tot = v_man if v_man > Decimal("0.00") else valor_fgts
            mem = f"FGTS do mês (8% sobre R$ {base_fgts:,.2f}): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(c_saida, d_info, "informativo", aliquota_fgts, "%", base_fgts, tot, mem, "calculado", "0904")
        elif c_oficial == "0905":
            tot = v_man if v_man > Decimal("0.00") else Decimal(str(encargos["inss_patronal"]))
            mem = encargos["inss_patronal_memoria"]
            adicionar_item(c_saida, d_info, "informativo", 20.0, "%", base_inss, tot, mem, "calculado", "0905")
        elif c_oficial == "0906":
            tot = v_man if v_man > Decimal("0.00") else Decimal(str(encargos["rat_fap"]))
            mem = encargos["rat_fap_memoria"]
            adicionar_item(c_saida, d_info, "informativo", params.get("aliquota_rat", 2.0), "%", base_inss, tot, mem, "calculado", "0906")
        elif c_oficial == "0907":
            tot = v_man if v_man > Decimal("0.00") else Decimal(str(encargos["terceiros"]))
            mem = encargos["terceiros_memoria"]
            adicionar_item(c_saida, d_info, "informativo", 5.8, "%", base_inss, tot, mem, "calculado", "0907")
        elif c_oficial == "0908":
            saldo = q_info if q_info > Decimal("0.00") else v_man
            tot = v_man if v_man > Decimal("0.00") else arredondar_moeda(saldo * Decimal("0.40"))
            mem = f"Multa rescisória de 40% do FGTS sobre R$ {saldo:,.2f} = R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(c_saida, d_info, "informativo", 40.0, "%", saldo, tot, mem, "calculado", "0908")
        elif c_oficial == "0909":
            dep_count = int(q_info) if q_info > Decimal("0.00") else numero_dependentes
            tot = v_man if v_man > Decimal("0.00") else arredondar_moeda(Decimal(str(dep_count)) * DEDUCAO_DEPENDENTE_IRRF_PADRAO)
            mem = f"Dedução por dependentes no IRRF ({dep_count} dep. x R$ {DEDUCAO_DEPENDENTE_IRRF_PADRAO}): R$ {tot:,.2f}".replace(".", ",")
            adicionar_item(c_saida, d_info, "informativo", dep_count, "dep", DEDUCAO_DEPENDENTE_IRRF_PADRAO, tot, mem, "calculado", "0909")

    # ── TOTALIZAÇÃO ESTRITA ──────────────────────────────────────────────────
    # Eventos informativos são estritamente excluídos dos proventos e descontos.
    total_proventos = Decimal("0.00")
    total_descontos = Decimal("0.00")

    for it in itens_consolidados:
        if it["tipo"] == "provento":
            total_proventos += _to_decimal(it["valor_total"])
        elif it["tipo"] == "desconto":
            total_descontos += _to_decimal(it["valor_total"])

    total_proventos = arredondar_moeda(total_proventos)
    total_descontos = arredondar_moeda(total_descontos)
    salario_liquido = arredondar_moeda(total_proventos - total_descontos)

    return {
        "resumo": {
            "salario_base_contratual": float(arredondar_moeda(sb)),
            "salario_base_proporcional": float(salario_prop),
            "valor_hora_normal": float(arredondar_moeda(vh_normal)),
            "dias_trabalhados": float(dt),
            "dias_mes": dm,
            "divisor_horas": float(div_h),
            "total_proventos": float(total_proventos),
            "total_descontos": float(total_descontos),
            "salario_liquido": float(salario_liquido),
            "base_inss": float(arredondar_moeda(base_inss)),
            "base_fgts": float(arredondar_moeda(base_fgts)),
            "valor_fgts_informativo": float(valor_fgts),
            "base_irrf": float(arredondar_moeda(base_irrf_apurada)),
            "numero_dependentes": numero_dependentes,
            "encargos_patronais": encargos
        },
        "itens": itens_consolidados,
        "validacoes": [
            "Os percentuais e faixas de INSS/IRRF devem ser validados pelo responsável da folha conforme a tabela da competência.",
            "Não aplique descontos duplicados ou eventos com o mesmo código e tipo na mesma folha.",
            "Eventos informativos (bases de cálculo e encargos) não integram proventos, descontos ou salário líquido."
        ]
    }
