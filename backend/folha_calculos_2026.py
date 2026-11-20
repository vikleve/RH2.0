"""
Motor Oficial de Cálculos Trabalhistas — Vigência 2026
Base legal: CLT, Portaria Interministerial MPS/MF nº 13/2026, Leis 15.191/2025 e 15.270/2025.
Implementa as Regras de Negócio RN-001 a RN-083 (Volume 4) e Casos de Teste Oficiais.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

def to_d(val: Any, estrito: bool = False) -> Decimal:
    """Converte para Decimal com precisão estrita, sem silenciar valores malformados (RF-FIN-001)."""
    if val is None or val == "":
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val
    try:
        s = str(val).strip().replace("R$", "").strip()
        if "," in s and "." not in s:
            s = s.replace(",", ".")
        elif "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        return Decimal(s)
    except Exception as e:
        from .tabelas_legais import ConversaoFinanceiraException
        raise ConversaoFinanceiraException(f"Erro de conversão numérica para Decimal no valor '{val}'") from e

def round2(val: Any) -> Decimal:
    """Arredonda para 2 casas decimais no padrão financeiro (ROUND_HALF_UP)."""
    return to_d(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# ─────────────────────────────────────────────────────────────────────────────
# Parâmetros Oficiais de 2026 (Portaria MPS/MF 13/2026 e Leis 15.191/25 e 15.270/25)
# ─────────────────────────────────────────────────────────────────────────────
SALARIO_MINIMO_2026 = Decimal("1621.00")
TETO_INSS_2026 = Decimal("8475.55")
TETO_CONTRIBUICAO_INSS_2026 = Decimal("988.09")
LIMITE_SALARIO_FAMILIA_2026 = Decimal("1980.38")
VALOR_COTA_SALARIO_FAMILIA_2026 = Decimal("67.54")
DEDUCAO_DEPENDENTE_IRRF_2026 = Decimal("189.59")
DESCONTO_SIMPLIFICADO_IRRF_2026 = Decimal("607.20")
ALIQUOTA_FGTS_PADRAO = Decimal("8.00")

TABELA_INSS_2026 = [
    # Limites superiores inclusivos; cálculo por faixas contínuas.
    (Decimal("0.00"), Decimal("1621.00"), Decimal("7.5")),
    (Decimal("1621.00"), Decimal("2902.84"), Decimal("9.0")),
    (Decimal("2902.84"), Decimal("4354.27"), Decimal("12.0")),
    (Decimal("4354.27"), Decimal("8475.55"), Decimal("14.0")),
]

TABELA_IRRF_2026 = [
    # (faixa_min, faixa_max, aliquota_percentual, parcela_a_deduzir)
    (Decimal("0.00"), Decimal("2428.80"), Decimal("0.0"), Decimal("0.00")),
    (Decimal("2428.81"), Decimal("2826.65"), Decimal("7.5"), Decimal("182.16")),
    (Decimal("2826.66"), Decimal("3751.05"), Decimal("15.0"), Decimal("394.16")),
    (Decimal("3751.06"), Decimal("4664.68"), Decimal("22.5"), Decimal("675.49")),
    (Decimal("4664.69"), None, Decimal("27.5"), Decimal("908.73")),
]

# ─────────────────────────────────────────────────────────────────────────────
# 1. Cálculo de INSS Progressivo 2026 (RN-044, RN-045)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_inss_2026(base_inss: Any) -> Tuple[Decimal, Decimal, str, List[Dict[str, Any]]]:
    """
    Calcula INSS progressivo faixa a faixa conforme tabela oficial 2026.
    Retorna: (valor_inss, aliquota_efetiva, memoria_calculo, faixas_detalhadas)
    """
    base = to_d(base_inss)
    if base <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00"), "Base de cálculo zerada.", []

    base_tributavel = min(base, TETO_INSS_2026)
    total_inss = Decimal("0.000000")
    faixas_det = []
    mem_linhas = [f"Base INSS: R$ {base_tributavel:.2f} (Teto: R$ {TETO_INSS_2026:.2f})"]

    for i, (f_min, f_max, aliq) in enumerate(TABELA_INSS_2026, start=1):
        if base_tributavel <= f_min:
            break

        limite_superior = min(base_tributavel, f_max)
        base_na_faixa = limite_superior - f_min
        fator = aliq / Decimal("100.00")
        valor_faixa = base_na_faixa * fator
        total_inss += valor_faixa

        faixas_det.append({
            "faixa": i,
            "minimo": float(f_min),
            "maximo": float(f_max),
            "base_tributada": float(round2(base_na_faixa)),
            "aliquota": float(aliq),
            "valor": float(round2(valor_faixa))
        })
        mem_linhas.append(f"Faixa {i} ({aliq}% sobre R$ {base_na_faixa:.2f}): R$ {round2(valor_faixa):.2f}")

    inss_arredondado = min(round2(total_inss), TETO_CONTRIBUICAO_INSS_2026)
    aliq_efetiva = round2((inss_arredondado / base) * Decimal("100.00")) if base > 0 else Decimal("0.00")
    mem_linhas.append(f"Total INSS a recolher: R$ {inss_arredondado:.2f} (Alíquota efetiva: {aliq_efetiva}%)")

    return inss_arredondado, aliq_efetiva, " | ".join(mem_linhas), faixas_det

# ─────────────────────────────────────────────────────────────────────────────
# 2. Redução do IRRF — Lei 15.270/2025 (RN Seção 2.4)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_reducao_lei_15270(rendimento_bruto: Any, imposto_apurado: Any) -> Tuple[Decimal, str]:
    """
    Aplica a redução da Lei 15.270/2025 sobre o IRRF:
    - Até R$ 5.000,00: Até R$ 312,89, limitada ao imposto apurado (zera o IRRF)
    - De R$ 5.000,01 a R$ 7.350,00: R$ 978,62 - (0,133145 * rendimento_bruto), limitada ao imposto
    - Acima de R$ 7.350,00: Sem redução
    """
    bruto = to_d(rendimento_bruto)
    imposto = to_d(imposto_apurado)

    if imposto <= Decimal("0.00") or bruto <= Decimal("0.00"):
        return Decimal("0.00"), "Sem redução aplicável."

    if bruto <= Decimal("5000.00"):
        red_calculada = Decimal("312.89")
    elif bruto <= Decimal("7350.00"):
        fator = Decimal("0.133145")
        red_calculada = Decimal("978.62") - (fator * bruto)
        if red_calculada < Decimal("0.00"):
            red_calculada = Decimal("0.00")
    else:
        red_calculada = Decimal("0.00")

    reducao_efetiva = min(round2(red_calculada), imposto)
    mem = f"Redução Lei 15.270/25 sobre bruto R$ {bruto:.2f}: R$ {reducao_efetiva:.2f} (calculada: R$ {red_calculada:.2f})"
    return reducao_efetiva, mem

# ─────────────────────────────────────────────────────────────────────────────
# 3. Cálculo de IRRF Oficial 2026 (RN-046, RN-047, Seções 2.3, 2.4, 3.1)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_irrf_2026(
    rendimento_bruto: Any,
    desconto_inss: Any,
    numero_dependentes: int = 0,
    pensao_judicial: Any = Decimal("0.00"),
    outras_deducoes: Any = Decimal("0.00")
) -> Tuple[Decimal, Decimal, Decimal, Decimal, str]:
    """
    Calcula IRRF mensal com comparação obrigatória: Deduções Legais vs Desconto Simplificado (R$ 607,20).
    Aplica tabela progressiva 2026 e em seguida a Redução da Lei 15.270/2025.
    Retorna: (irrf_final, base_utilizada, imposto_tabela, reducao_lei, memoria_calculo)
    """
    bruto = to_d(rendimento_bruto)
    inss = to_d(desconto_inss)
    pensao = to_d(pensao_judicial)
    outras = to_d(outras_deducoes)
    n_dep = int(numero_dependentes or 0)

    # 1. Deduções legais
    deducao_dep = Decimal(str(n_dep)) * DEDUCAO_DEPENDENTE_IRRF_2026
    total_deducoes_legais = inss + deducao_dep + pensao + outras
    base_legal = max(Decimal("0.00"), bruto - total_deducoes_legais)

    # 2. Desconto simplificado
    base_simplificado = max(Decimal("0.00"), bruto - DESCONTO_SIMPLIFICADO_IRRF_2026)

    # 3. Escolhe a opção mais favorável (menor base de cálculo tributável)
    if base_simplificado < base_legal:
        base_escolhida = base_simplificado
        modo_deducao = f"Desconto Simplificado R$ {DESCONTO_SIMPLIFICADO_IRRF_2026:.2f}"
    else:
        base_escolhida = base_legal
        modo_deducao = f"Deduções Legais (INSS: R$ {inss:.2f}, {n_dep} Dep: R$ {deducao_dep:.2f}, Pensão: R$ {pensao:.2f})"

    # 4. Tabela progressiva
    aliquota = Decimal("0.00")
    deduzir = Decimal("0.00")
    for f_min, f_max, aliq, parcela in TABELA_IRRF_2026:
        if f_max is None or base_escolhida <= f_max:
            aliquota = aliq
            deduzir = parcela
            break

    imposto_bruto_tabela = max(Decimal("0.00"), (base_escolhida * (aliquota / Decimal("100.00"))) - deduzir)
    imposto_bruto_arred = round2(imposto_bruto_tabela)

    # 5. Redução da Lei 15.270/2025
    reducao, mem_red = calcular_reducao_lei_15270(bruto, imposto_bruto_arred)
    irrf_final = max(Decimal("0.00"), imposto_bruto_arred - reducao)

    mem = (
        f"Base IRRF ({modo_deducao}): R$ {base_escolhida:.2f} | "
        f"Alíquota: {aliquota}% (Parcela a deduzir: R$ {deduzir:.2f}) -> Imposto tabela: R$ {imposto_bruto_arred:.2f} | "
        f"{mem_red} | IRRF Final retido: R$ {irrf_final:.2f}"
    )

    return irrf_final, round2(base_escolhida), imposto_bruto_arred, reducao, mem

# ─────────────────────────────────────────────────────────────────────────────
# 4. Salário-Família 2026 (RN Seção 2.1)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_salario_familia_2026(remuneracao_total: Any, filhos_elegiveis: int) -> Tuple[Decimal, str]:
    """
    R$ 67,54 por filho elegível (até 14 anos ou inválido), se remuneração total <= R$ 1.980,38.
    """
    rem = to_d(remuneracao_total)
    qtd = int(filhos_elegiveis or 0)
    if qtd <= 0:
        return Decimal("0.00"), "Sem filhos elegíveis para salário-família."

    if rem <= LIMITE_SALARIO_FAMILIA_2026:
        valor = round2(Decimal(str(qtd)) * VALOR_COTA_SALARIO_FAMILIA_2026)
        mem = f"{qtd} cota(s) x R$ {VALOR_COTA_SALARIO_FAMILIA_2026:.2f} (Remuneração R$ {rem:.2f} <= teto R$ {LIMITE_SALARIO_FAMILIA_2026:.2f}): R$ {valor:.2f}"
        return valor, mem
    else:
        return Decimal("0.00"), f"Remuneração R$ {rem:.2f} excede teto legal de R$ {LIMITE_SALARIO_FAMILIA_2026:.2f}."

# ─────────────────────────────────────────────────────────────────────────────
# 5. Vale-Transporte (RN-037, Seção 2.1)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_vale_transporte(salario_base: Any, custo_total_vt: Any, optante: bool = True) -> Tuple[Decimal, Decimal, str]:
    """
    Desconto limitado ao menor valor entre 6% do salário-base e o custo total do benefício.
    Retorna: (desconto_colaborador, custo_empresa, memoria_calculo)
    """
    if not optante:
        return Decimal("0.00"), Decimal("0.00"), "Colaborador não optante de Vale-Transporte."

    sb = to_d(salario_base)
    custo = to_d(custo_total_vt)
    teto_6_porcento = round2(sb * Decimal("0.06"))
    desconto = min(teto_6_porcento, custo)
    custo_empresa = max(Decimal("0.00"), custo - desconto)

    mem = f"Custo VT: R$ {custo:.2f} | Teto 6% s/ salário R$ {sb:.2f}: R$ {teto_6_porcento:.2f} -> Desconto: R$ {desconto:.2f} | Custo Empresa: R$ {custo_empresa:.2f}"
    return desconto, custo_empresa, mem

# ─────────────────────────────────────────────────────────────────────────────
# 6. Horas Extras e DSR (RN-020, RN-021, RN-022, Seção 3.2)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_horas_extras_oficial(
    salario_base: Any,
    divisor_horas: Any,
    horas_50: Any = Decimal("0.00"),
    horas_100: Any = Decimal("0.00"),
    adicionais_salariais: Any = Decimal("0.00")
) -> Dict[str, Any]:
    """
    Calcula valor-hora normal e horas extras com fator 1.50 (50%) e 2.00 (100%).
    """
    sb = to_d(salario_base)
    div = to_d(divisor_horas) if to_d(divisor_horas) > 0 else Decimal("220.00")
    adic = to_d(adicionais_salariais)
    base_hora = sb + adic
    valor_hora = base_hora / div

    h50 = to_d(horas_50)
    h100 = to_d(horas_100)

    val_he50 = round2(h50 * valor_hora * Decimal("1.50"))
    val_he100 = round2(h100 * valor_hora * Decimal("2.00"))
    total_he = val_he50 + val_he100

    return {
        "valor_hora": round2(valor_hora),
        "horas_50": float(h50),
        "valor_he50": val_he50,
        "horas_100": float(h100),
        "valor_he100": val_he100,
        "total_horas_extras": total_he,
        "memoria": f"Valor-hora: R$ {valor_hora:.4f} (Base R$ {base_hora:.2f} / {div}h) | HE 50%: {h50}h x 1,5 = R$ {val_he50:.2f} | HE 100%: {h100}h x 2,0 = R$ {val_he100:.2f}"
    }

def calcular_dsr_sobre_variaveis_oficial(
    total_variaveis: Any,
    dias_uteis: int = 25,
    domingos_feriados: int = 5
) -> Tuple[Decimal, str]:
    """
    DSR = (Total de variáveis do período ÷ dias úteis) × (domingos + feriados)
    """
    var = to_d(total_variaveis)
    if var <= Decimal("0.00") or dias_uteis <= 0:
        return Decimal("0.00"), "Sem variáveis para reflexo de DSR."

    dsr = round2((var / Decimal(str(dias_uteis))) * Decimal(str(domingos_feriados)))
    mem = f"(Variáveis R$ {var:.2f} ÷ {dias_uteis} dias úteis) × {domingos_feriados} DSR/feriados = R$ {dsr:.2f}"
    return dsr, mem

# ─────────────────────────────────────────────────────────────────────────────
# 7. Adicional Noturno e Redução Ficta (RN-023, RN-024, RN-025)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_adicional_noturno_oficial(
    valor_hora: Any,
    minutos_noturnos: Any,
    percentual_adicional: Any = Decimal("20.00")
) -> Tuple[Decimal, Decimal, str]:
    """
    Apurado com hora ficta reduzida (52min30s = 52.5min).
    Horas apuradas = minutos reais / 52.5.
    Adicional = Horas apuradas * valor_hora * (percentual / 100).
    """
    vh = to_d(valor_hora)
    mins = to_d(minutos_noturnos)
    perc = to_d(percentual_adicional) / Decimal("100.00")

    horas_noturnas_computadas = mins / Decimal("52.5")
    valor = round2(horas_noturnas_computadas * vh * perc)
    mem = f"{mins} min noturnos ÷ 52,5min = {horas_noturnas_computadas:.2f}h noturnas x R$ {vh:.2f} x {percentual_adicional}% = R$ {valor:.2f}"
    return valor, round2(horas_noturnas_computadas), mem

# ─────────────────────────────────────────────────────────────────────────────
# 8. Faltas, Atrasos e Perda de DSR (RN-017, RN-018, RN-019)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_descontos_ausencia_oficial(
    salario_base: Any,
    valor_hora: Any,
    dias_falta_injustificada: int = 0,
    minutos_atraso: int = 0,
    semanas_com_falta: int = 0
) -> Dict[str, Any]:
    """
    Falta injustificada = dias * (salario / 30) + 1 dia de DSR por semana com falta.
    Atraso = minutos / 60 * valor_hora (se minutos no dia passarem da tolerância de 10min).
    """
    sb = to_d(salario_base)
    vh = to_d(valor_hora)
    valor_dia = round2(sb / Decimal("30.00"))

    dias_falta = int(dias_falta_injustificada or 0)
    semanas = int(semanas_com_falta or 0)
    if dias_falta > 0 and semanas == 0:
        semanas = max(1, dias_falta)

    val_faltas = round2(Decimal(str(dias_falta)) * valor_dia)
    val_dsr_perdido = round2(Decimal(str(semanas)) * valor_dia)

    mins = int(minutos_atraso or 0)
    val_atrasos = round2((Decimal(str(mins)) / Decimal("60.00")) * vh) if mins > 10 else Decimal("0.00")

    total_desconto = val_faltas + val_dsr_perdido + val_atrasos
    mem = (
        f"Falta ({dias_falta}d x R$ {valor_dia:.2f}): R$ {val_faltas:.2f} | "
        f"Perda DSR ({semanas} sem x R$ {valor_dia:.2f}): R$ {val_dsr_perdido:.2f} | "
        f"Atrasos ({mins}min x R$ {vh:.2f}/h): R$ {val_atrasos:.2f}"
    )

    return {
        "valor_dia": valor_dia,
        "desconto_faltas": val_faltas,
        "desconto_dsr_perdido": val_dsr_perdido,
        "desconto_atrasos": val_atrasos,
        "total_desconto_ausencias": total_desconto,
        "memoria": mem
    }

# ─────────────────────────────────────────────────────────────────────────────
# 9. Cálculo de Rescisão (RN-054 a RN-060, RF-106 a RF-120)
# ─────────────────────────────────────────────────────────────────────────────
def calcular_rescisao_oficial(
    tipo_rescisao: str,
    salario_base: Any,
    data_admissao: str,
    data_afastamento: str,
    tipo_aviso: str = "indenizado",
    saldo_salario_dias: int = 0,
    ferias_vencidas_dias: int = 0,
    meses_trabalhados_ano: int = 0,
    saldo_fgts_estimado: Any = Decimal("0.00"),
    adicionais_medios: Any = Decimal("0.00")
) -> Dict[str, Any]:
    """
    Calcula as verbas rescisórias conforme tipo legal:
    - sem_justa_causa: saldo, aviso prévio proporcional (30 + 3/ano até 90), férias vencidas + 1/3, férias prop + 1/3, 13º prop, multa FGTS 40%, seguro desemprego
    - pedido_demissao: saldo, férias vencidas + 1/3, férias prop + 1/3, 13º prop (aviso indenizado gera desconto, sem multa FGTS, sem seguro)
    - justa_causa: saldo de salário e férias vencidas + 1/3 apenas
    - acordo_484a: aviso 50%, multa FGTS 20%, saque 80%, saldo, férias, 13º, sem seguro
    - rescisao_indireta: igual a sem justa causa
    - culpa_reciproca: aviso 50%, férias prop 50%, 13º prop 50%, multa FGTS 20%
    - termino_contrato: saldo, férias prop + 1/3, 13º prop, sem aviso e sem multa FGTS
    """
    from datetime import datetime
    sb = to_d(salario_base)
    adic = to_d(adicionais_medios)
    remuneracao = sb + adic
    valor_dia = remuneracao / Decimal("30.00")

    # Calcula anos de serviço para aviso prévio proporcional
    try:
        dt_adm = datetime.strptime(data_admissao[:10], "%Y-%m-%d")
        dt_afast = datetime.strptime(data_afastamento[:10], "%Y-%m-%d")
        dias_totais = (dt_afast - dt_adm).days
        anos_completos = max(0, dias_totais // 365)
    except Exception:
        anos_completos = 0

    dias_aviso = min(90, 30 + (anos_completos * 3))

    # Determina avos de 13º e férias proporcionais
    avos = max(0, min(12, int(meses_trabalhados_ano or 0)))

    # Verbas
    saldo_salario = round2(Decimal(str(saldo_salario_dias)) * valor_dia)
    aviso_previo_valor = Decimal("0.00")
    desconto_aviso_valor = Decimal("0.00")
    ferias_vencidas_val = round2((Decimal(str(ferias_vencidas_dias)) * valor_dia) * Decimal("1.333333"))
    ferias_prop_val = round2(((remuneracao / Decimal("12.00")) * Decimal(str(avos))) * Decimal("1.333333"))
    decimo_prop_val = round2((remuneracao / Decimal("12.00")) * Decimal(str(avos)))
    multa_fgts_val = Decimal("0.00")
    multa_fgts_perc = Decimal("0.00")
    seguro_desemprego = False

    tipo = tipo_rescisao.lower().strip()

    if tipo in ("sem_justa_causa", "rescisao_indireta"):
        if tipo_aviso == "indenizado":
            aviso_previo_valor = round2(Decimal(str(dias_aviso)) * valor_dia)
        multa_fgts_perc = Decimal("40.00")
        multa_fgts_val = round2(to_d(saldo_fgts_estimado) * Decimal("0.40"))
        seguro_desemprego = True

    elif tipo == "pedido_demissao":
        if tipo_aviso == "indenizado":
            # Desconto do aviso não cumprido
            desconto_aviso_valor = round2(Decimal(str(30)) * valor_dia)
        multa_fgts_perc = Decimal("0.00")
        seguro_desemprego = False

    elif tipo == "justa_causa":
        ferias_prop_val = Decimal("0.00")
        decimo_prop_val = Decimal("0.00")
        multa_fgts_perc = Decimal("0.00")
        seguro_desemprego = False

    elif tipo == "acordo_484a":
        if tipo_aviso == "indenizado":
            aviso_previo_valor = round2((Decimal(str(dias_aviso)) * valor_dia) * Decimal("0.50"))
        multa_fgts_perc = Decimal("20.00")
        multa_fgts_val = round2(to_d(saldo_fgts_estimado) * Decimal("0.20"))
        seguro_desemprego = False

    elif tipo == "culpa_reciproca":
        aviso_previo_valor = round2((Decimal(str(dias_aviso)) * valor_dia) * Decimal("0.50"))
        ferias_prop_val = round2(ferias_prop_val * Decimal("0.50"))
        decimo_prop_val = round2(decimo_prop_val * Decimal("0.50"))
        multa_fgts_perc = Decimal("20.00")
        multa_fgts_val = round2(to_d(saldo_fgts_estimado) * Decimal("0.20"))
        seguro_desemprego = False

    elif tipo == "termino_contrato":
        multa_fgts_perc = Decimal("0.00")
        seguro_desemprego = False

    total_proventos = saldo_salario + aviso_previo_valor + ferias_vencidas_val + ferias_prop_val + decimo_prop_val + multa_fgts_val
    total_descontos = desconto_aviso_valor

    # INSS sobre saldo e 13º
    inss_saldo, _, _, _ = calcular_inss_2026(saldo_salario)
    inss_decimo, _, _, _ = calcular_inss_2026(decimo_prop_val)
    total_inss = inss_saldo + inss_decimo
    total_descontos += total_inss

    liquido = max(Decimal("0.00"), total_proventos - total_descontos)

    # Data limite de pagamento: 10 dias corridos do término do contrato (art. 477 da CLT)
    try:
        from datetime import timedelta
        dt_limite = (dt_afast + timedelta(days=10)).strftime("%Y-%m-%d")
    except Exception:
        dt_limite = data_afastamento

    return {
        "tipo_rescisao": tipo,
        "dias_aviso_previo": dias_aviso,
        "saldo_salario": saldo_salario,
        "aviso_previo_indenizado": aviso_previo_valor,
        "desconto_aviso_previo": desconto_aviso_valor,
        "ferias_vencidas_com_terco": ferias_vencidas_val,
        "ferias_proporcionais_com_terco": ferias_prop_val,
        "decimo_terceiro_proporcional": decimo_prop_val,
        "multa_fgts_percentual": float(multa_fgts_perc),
        "multa_fgts_valor": multa_fgts_val,
        "desconto_inss": total_inss,
        "total_proventos": total_proventos,
        "total_descontos": total_descontos,
        "valor_liquido": liquido,
        "seguro_desemprego_elegivel": seguro_desemprego,
        "data_limite_pagamento": dt_limite,
        "memoria": f"Rescisão {tipo}: Proventos R$ {total_proventos:.2f} - Descontos R$ {total_descontos:.2f} = Líquido R$ {liquido:.2f} (Prazo CLT art. 477: {dt_limite})"
    }
