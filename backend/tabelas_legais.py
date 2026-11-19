# -*- coding: utf-8 -*-
"""
Módulo de Tabelas Legais e Parâmetros Trabalhistas Versionados — RH2.0 Enterprise
Centraliza os parâmetros fiscais, previdenciários e trabalhistas vigentes e históricos.
Fontes normativas: CLT, Portaria Interministerial MPS/MF nº 13/2026, Leis 15.191/2025 e 15.270/2025.
Garante total rastreabilidade, versionamento e imutabilidade dos parâmetros aplicados em folha.
"""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple


class ConversaoFinanceiraException(ValueError):
    """Exceção lançada quando um valor numérico ou monetário é inválido e não pode ser convertido."""
    pass


def converter_decimal_estrito(val: Any, campo: str = "valor", permitir_nulo: bool = False, permitir_negativo: bool = False) -> Decimal:
    """
    Converte com precisão estrita um valor para Decimal.
    Rejeita valores malformados ou inválidos lançando ConversaoFinanceiraException,
    eliminando conversões silenciosas para 0.00.
    """
    if val is None or val == "":
        if permitir_nulo:
            return Decimal("0.00")
        raise ConversaoFinanceiraException(f"O campo '{campo}' não pode ser nulo ou vazio.")

    if isinstance(val, Decimal):
        d = val
    elif isinstance(val, (int, float)):
        # Converte float via string para não herdar imprecisão binária
        d = Decimal(str(val))
    elif isinstance(val, str):
        s = val.strip().replace("R$", "").replace(" ", "")
        if not s:
            if permitir_nulo:
                return Decimal("0.00")
            raise ConversaoFinanceiraException(f"O campo '{campo}' contém texto vazio.")
        try:
            if "," in s and "." not in s:
                s = s.replace(",", ".")
            elif "," in s and "." in s:
                # Formato brasileiro com milhar: 1.234,56
                s = s.replace(".", "").replace(",", ".")
            d = Decimal(s)
        except (InvalidOperation, ValueError):
            raise ConversaoFinanceiraException(f"Valor monetário inválido no campo '{campo}': '{val}'")
    else:
        raise ConversaoFinanceiraException(f"Tipo incompatível para conversão monetária no campo '{campo}': {type(val)}")

    if not permitir_negativo and d < Decimal("0.00"):
        raise ConversaoFinanceiraException(f"O campo '{campo}' não pode ser negativo: {d}")

    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FaixaINSS:
    faixa_min: Decimal
    faixa_max: Optional[Decimal]
    aliquota: Decimal  # Ex: 7.5, 9.0, 12.0, 14.0


@dataclass(frozen=True)
class FaixaIRRF:
    faixa_min: Decimal
    faixa_max: Optional[Decimal]
    aliquota: Decimal  # Ex: 0.0, 7.5, 15.0, 22.5, 27.5
    deducao: Decimal   # Parcela a deduzir


@dataclass(frozen=True)
class ParametrosTabelaLegal:
    identificador: str
    descricao: str
    competencia_inicio: str
    competencia_fim: Optional[str]
    vigencia_inicio: str
    fonte_normativa: str
    salario_minimo: Decimal
    teto_inss: Decimal
    teto_contribuicao_inss: Decimal
    faixas_inss: Tuple[FaixaINSS, ...]
    faixas_irrf: Tuple[FaixaIRRF, ...]
    deducao_dependente_irrf: Decimal
    desconto_simplificado_irrf: Decimal
    limite_salario_familia: Decimal
    valor_cota_salario_familia: Decimal
    aliquota_fgts_padrao: Decimal = Decimal("8.00")
    aliquota_fgts_aprendiz: Decimal = Decimal("2.00")
    aliquota_inss_patronal: Decimal = Decimal("20.00")
    aliquota_rat_padrao: Decimal = Decimal("2.00")
    fap_padrao: Decimal = Decimal("1.0000")
    aliquota_terceiros_padrao: Decimal = Decimal("5.80")


# ─────────────────────────────────────────────────────────────
# Tabelas e Vigências Cadastradas no Sistema
# ─────────────────────────────────────────────────────────────

# 1. Tabela 2026 - Oficial Lei 15.191/25, Lei 15.270/25 e Portaria MPS/MF 13/2026 (RN-044/RN-045)
TABELA_LEGAL_2026_OFICIAL = ParametrosTabelaLegal(
    identificador="VIGENCIA_2026_OFICIAL",
    descricao="Tabela Oficial eSocial 2026 — Leis 15.191/2025 e 15.270/2025, Portaria MPS/MF 13/2026",
    competencia_inicio="2026-01",
    competencia_fim=None,
    vigencia_inicio="2026-01-01",
    fonte_normativa="Portaria Interministerial MPS/MF nº 13/2026 e Leis Federais 15.191 e 15.270",
    salario_minimo=Decimal("1621.00"),
    teto_inss=Decimal("8475.55"),
    teto_contribuicao_inss=Decimal("988.09"),
    faixas_inss=(
        FaixaINSS(Decimal("0.00"), Decimal("1621.00"), Decimal("7.5")),
        FaixaINSS(Decimal("1621.01"), Decimal("2902.84"), Decimal("9.0")),
        FaixaINSS(Decimal("2902.85"), Decimal("4354.27"), Decimal("12.0")),
        FaixaINSS(Decimal("4354.28"), Decimal("8475.55"), Decimal("14.0")),
    ),
    faixas_irrf=(
        FaixaIRRF(Decimal("0.00"), Decimal("2428.80"), Decimal("0.0"), Decimal("0.00")),
        FaixaIRRF(Decimal("2428.81"), Decimal("2826.65"), Decimal("7.5"), Decimal("182.16")),
        FaixaIRRF(Decimal("2826.66"), Decimal("3751.05"), Decimal("15.0"), Decimal("394.16")),
        FaixaIRRF(Decimal("3751.06"), Decimal("4664.68"), Decimal("22.5"), Decimal("675.49")),
        FaixaIRRF(Decimal("4664.69"), None, Decimal("27.5"), Decimal("908.73")),
    ),
    deducao_dependente_irrf=Decimal("189.59"),
    desconto_simplificado_irrf=Decimal("607.20"),
    limite_salario_familia=Decimal("1980.38"),
    valor_cota_salario_familia=Decimal("67.54"),
)

# 2. Tabela 2026 - Padrão de Referência Geral CLT / RFB 2026 (Salário Mínimo R$ 1.518,00)
TABELA_LEGAL_2026_PADRAO = ParametrosTabelaLegal(
    identificador="VIGENCIA_2026_PADRAO",
    descricao="Tabela Padrão de Referência Geral 2026 — SM R$ 1.518,00 / Teto R$ 8.157,41",
    competencia_inicio="2026-01",
    competencia_fim=None,
    vigencia_inicio="2026-01-01",
    fonte_normativa="Portaria Interministerial MTP/MF 2026 e Instruções Normativas RFB",
    salario_minimo=Decimal("1518.00"),
    teto_inss=Decimal("8157.41"),
    teto_contribuicao_inss=Decimal("951.64"),
    faixas_inss=(
        FaixaINSS(Decimal("0.00"), Decimal("1518.00"), Decimal("7.5")),
        FaixaINSS(Decimal("1518.01"), Decimal("2793.88"), Decimal("9.0")),
        FaixaINSS(Decimal("2793.89"), Decimal("4190.83"), Decimal("12.0")),
        FaixaINSS(Decimal("4190.84"), Decimal("8157.41"), Decimal("14.0")),
    ),
    faixas_irrf=(
        FaixaIRRF(Decimal("0.00"), Decimal("2259.20"), Decimal("0.0"), Decimal("0.00")),
        FaixaIRRF(Decimal("2259.21"), Decimal("2826.65"), Decimal("7.5"), Decimal("169.44")),
        FaixaIRRF(Decimal("2826.66"), Decimal("3751.05"), Decimal("15.0"), Decimal("381.44")),
        FaixaIRRF(Decimal("3751.06"), Decimal("4664.68"), Decimal("22.5"), Decimal("662.77")),
        FaixaIRRF(Decimal("4664.69"), None, Decimal("27.5"), Decimal("896.00")),
    ),
    deducao_dependente_irrf=Decimal("189.59"),
    desconto_simplificado_irrf=Decimal("607.40"),
    limite_salario_familia=Decimal("1906.00"),
    valor_cota_salario_familia=Decimal("65.00"),
)

# Catálogo em memória indexado por identificador
REPOSITORIO_TABELAS_LEGAIS: Dict[str, ParametrosTabelaLegal] = {
    TABELA_LEGAL_2026_OFICIAL.identificador: TABELA_LEGAL_2026_OFICIAL,
    TABELA_LEGAL_2026_PADRAO.identificador: TABELA_LEGAL_2026_PADRAO,
}


def obter_tabela_legal(versao_ou_competencia: str = "VIGENCIA_2026_OFICIAL") -> ParametrosTabelaLegal:
    """
    Retorna a tabela legal parametrizada correspondente à versão ou competência.
    Garante acesso seguro com fallback para a tabela oficial vigente.
    """
    if not versao_ou_competencia:
        return TABELA_LEGAL_2026_OFICIAL

    v = str(versao_ou_competencia).strip().upper()
    if v in REPOSITORIO_TABELAS_LEGAIS:
        return REPOSITORIO_TABELAS_LEGAIS[v]

    # Mapeamento por chave de competência (Ex: '2026-01' -> Oficial 2026)
    if "2026" in v:
        if "PADRAO" in v or "REF" in v:
            return TABELA_LEGAL_2026_PADRAO
        return TABELA_LEGAL_2026_OFICIAL

    return TABELA_LEGAL_2026_OFICIAL
