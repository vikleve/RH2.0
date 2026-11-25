# -*- coding: utf-8 -*-
"""
Gerador Corporativo de Documentos Trabalhistas em PDF (Padrão A4) — RH2.0 Enterprise
- Aviso de Férias (RF-056, CLT art. 135)
- Recibo de Férias (RF-056, CLT art. 145)
- Termo de Rescisão do Contrato de Trabalho — TRCT (RF-115, Portaria MTP 671/2021)
- Guias / Requerimento FGTS e Seguro-Desemprego (RF-116)

100% Python puro reutilizando _PDFCanvas / montar_pdf_paginas (PDF 1.4, WinAnsiEncoding).
"""
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.holerite_pdf import (
    A4_HEIGHT,
    A4_WIDTH,
    _PDFCanvas,
    _fmt_data_br,
    _fmt_moeda,
    _mascarar_cpf,
    _trunc,
    montar_pdf_paginas,
)


def _desenhar_cabecalho_doc(
    c: _PDFCanvas,
    titulo_doc: str,
    subtitulo: str,
    empresa: Optional[Dict[str, Any]] = None,
) -> float:
    ml = 34.0
    mr = A4_WIDTH - 34.0
    cw = mr - ml
    c.rect(ml, 36.0, cw, A4_HEIGHT - 72.0, fill_rgb=(1, 1, 1), stroke_rgb=(0.76, 0.80, 0.85), line_w=0.8)

    top_y = A4_HEIGHT - 36.0
    hdr_h = 62.0
    c.rect(ml, top_y - hdr_h, cw, hdr_h, fill_rgb=(0.95, 0.97, 0.99), stroke_rgb=(0.76, 0.80, 0.85), line_w=0.8)
    c.rect(ml + 10, top_y - 48, 34, 34, fill_rgb=(0.08, 0.36, 0.22), stroke_rgb=None)
    c.text(ml + 27, top_y - 35, "RH", font="F2", size=12.0, rgb=(1, 1, 1), align="center")

    emp = empresa or {}
    razao = _trunc(emp.get("razao_social") or emp.get("nome_fantasia") or "RH2.0 ENTERPRISE — EMPREGADORA S.A.", 50)
    cnpj = emp.get("cnpj") or "12.345.678/0001-90"
    c.text(ml + 54, top_y - 22, razao, font="F2", size=10.0, rgb=(0.06, 0.14, 0.24))
    c.text(ml + 54, top_y - 35, f"CNPJ: {cnpj}", font="F1", size=8.0, rgb=(0.30, 0.36, 0.44))
    c.text(mr - 10, top_y - 22, titulo_doc, font="F2", size=10.0, rgb=(0.09, 0.26, 0.52), align="right")
    c.text(mr - 10, top_y - 36, subtitulo, font="F1", size=8.0, rgb=(0.25, 0.32, 0.40), align="right")
    return top_y - hdr_h - 14.0


def _desenhar_identificacao_colab(c: _PDFCanvas, y_top: float, colab: Dict[str, Any]) -> float:
    ml = 34.0
    mr = A4_WIDTH - 34.0
    cw = mr - ml
    c.rect(ml, y_top - 48.0, cw, 48.0, fill_rgb=(1, 1, 1), stroke_rgb=(0.80, 0.84, 0.88), line_w=0.6)
    c.text(ml + 8, y_top - 15, f"Colaborador: {_trunc(colab.get('nome_completo') or '--', 44)}", font="F2", size=8.5)
    c.text(mr - 8, y_top - 15, f"CPF: {_mascarar_cpf(colab.get('cpf') or '')}", font="F1", size=8.2, align="right")
    c.text(ml + 8, y_top - 29, f"Matrícula: {colab.get('matricula') or '--'}  |  Cargo: {_trunc(colab.get('cargo') or '--', 28)}", font="F1", size=8.0)
    c.text(mr - 8, y_top - 29, f"Admissão: {_fmt_data_br(colab.get('data_admissao'))}", font="F1", size=8.0, align="right")
    c.text(ml + 8, y_top - 42, f"Setor: {_trunc(colab.get('setor') or '--', 28)}  |  PIS: {colab.get('pis_pasep') or '--'}", font="F1", size=8.0)
    return y_top - 58.0


def _rodape_doc(c: _PDFCanvas, ref_id: str):
    ml = 34.0
    mr = A4_WIDTH - 34.0
    c.line(ml + 18, 92, ml + 228, 92, rgb=(0.35, 0.41, 0.49), line_w=0.7)
    c.text(ml + 123, 81, "Assinatura do Colaborador", font="F1", size=7.8, align="center")
    c.line(mr - 228, 92, mr - 18, 92, rgb=(0.35, 0.41, 0.49), line_w=0.7)
    c.text(mr - 123, 81, "Empregador / Recursos Humanos", font="F1", size=7.8, align="center")
    h = hashlib.sha256(f"{ref_id}|{datetime.now().strftime('%Y-%m-%d')}".encode("utf-8")).hexdigest()[:16].upper()
    c.text(ml + 10, 48, f"RH2.0 Enterprise  |  Ref: {ref_id}  |  Emitido: {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  Hash: {h}", font="F1", size=7.0, rgb=(0.42, 0.47, 0.54))


def gerar_pdf_aviso_ferias(
    ferias: Dict[str, Any],
    colaborador: Dict[str, Any],
    empresa: Optional[Dict[str, Any]] = None,
) -> bytes:
    """RF-056: Gera PDF A4 oficial de Aviso de Férias (CLT art. 135 — antecedência mínima 30 dias)."""
    c = _PDFCanvas()
    y = _desenhar_cabecalho_doc(c, "AVISO DE FÉRIAS", f"CLT Art. 135  |  Férias #{ferias.get('id')}", empresa)
    y = _desenhar_identificacao_colab(c, y, colaborador)

    ml = 42.0
    linhas = [
        "COMUNICAÇÃO FORMAL DE CONCESSÃO DE FÉRIAS",
        f"Período Aquisitivo: {_fmt_data_br(ferias.get('inicio_aquisitivo'))} a {_fmt_data_br(ferias.get('fim_aquisitivo'))}",
        f"Período de Gozo das Férias: {_fmt_data_br(ferias.get('data_inicio'))} a {_fmt_data_br(ferias.get('data_fim'))} ({ferias.get('dias_gozo')} dias corridos)",
        f"Abono Pecuniário (Art. 143 CLT): {'Sim (' + str(ferias.get('dias_abono') or 0) + ' dias)' if ferias.get('abono_pecuniario') else 'Não solicitado'}",
        f"Adiantamento 1ª Parcela 13º Salário: {'Sim' if ferias.get('adiantar_decimo') else 'Não'}",
        f"Data do Aviso Prévio Legal (30d): {_fmt_data_br(ferias.get('aviso_ferias_emitido'))}",
        f"Data Limite para Pagamento (Art. 145 CLT): {_fmt_data_br(ferias.get('data_pagamento_limite'))}",
        f"Retorno previsto ao trabalho: {_fmt_data_br(ferias.get('data_retorno_previsto') or ferias.get('data_fim'))}",
        "",
        "Nos termos do art. 135 da CLT, fica V. Sa. notificado(a) de que suas férias serão concedidas no período acima,",
        "devendo apresentar sua CTPS (física ou acompanhamento digital) para as anotações legais cabíveis.",
    ]
    for idx, ln in enumerate(linhas):
        c.text(ml, y - idx * 18, ln, font="F2" if idx == 0 else "F1", size=9.2 if idx == 0 else 8.5)

    _rodape_doc(c, f"AVISO-FERIAS-{ferias.get('id')}")
    return montar_pdf_paginas([c.to_bytes()])


def gerar_pdf_recibo_ferias(
    ferias: Dict[str, Any],
    colaborador: Dict[str, Any],
    empresa: Optional[Dict[str, Any]] = None,
) -> bytes:
    """RF-056: Gera PDF A4 do Recibo de Pagamento de Férias (CLT art. 145)."""
    c = _PDFCanvas()
    y = _desenhar_cabecalho_doc(c, "RECIBO DE FÉRIAS", f"CLT Art. 145  |  Férias #{ferias.get('id')}", empresa)
    y = _desenhar_identificacao_colab(c, y, colaborador)

    ml = 34.0
    mr = A4_WIDTH - 34.0
    c.text(ml + 8, y, f"Gozo: {_fmt_data_br(ferias.get('data_inicio'))} a {_fmt_data_br(ferias.get('data_fim'))} ({ferias.get('dias_gozo')}d)  |  Pgto até: {_fmt_data_br(ferias.get('data_pagamento_limite'))}", font="F2", size=8.5)
    y -= 20.0

    linhas = [
        ("0100", f"Férias Gozadas ({ferias.get('dias_gozo')} dias){' [EM DOBRO]' if ferias.get('em_dobro') else ''}", _fmt_moeda(ferias.get("valor_ferias")), ""),
        ("0101", "Adicional 1/3 Constitucional sobre Férias", _fmt_moeda(ferias.get("valor_terco")), ""),
    ]
    if float(ferias.get("valor_medias") or 0) > 0:
        linhas.append(("0100", "Médias de Horas Extras e Adicionais s/ Férias", _fmt_moeda(ferias.get("valor_medias")), ""))
    if float(ferias.get("valor_abono") or 0) > 0:
        linhas.append(("0102", f"Abono Pecuniário ({ferias.get('dias_abono')} dias)", _fmt_moeda(ferias.get("valor_abono")), ""))
        linhas.append(("0103", "1/3 Constitucional s/ Abono Pecuniário", _fmt_moeda(ferias.get("valor_terco_abono")), ""))
    if float(ferias.get("valor_adiantamento_13") or 0) > 0:
        linhas.append(("0110", "Adiantamento 1ª Parcela 13º Salário", _fmt_moeda(ferias.get("valor_adiantamento_13")), ""))

    linhas.append(("0501", "INSS sobre Férias", "", _fmt_moeda(ferias.get("desconto_inss"))))
    linhas.append(("0507", "IRRF sobre Férias", "", _fmt_moeda(ferias.get("desconto_irrf"))))

    c.rect(ml, y - 18, mr - ml, 18, fill_rgb=(0.12, 0.21, 0.34), stroke_rgb=(0.12, 0.21, 0.34))
    c.text(ml + 8, y - 12, "Cód.", font="F2", size=8.0, rgb=(1, 1, 1))
    c.text(ml + 54, y - 12, "Descrição da Rubrica", font="F2", size=8.0, rgb=(1, 1, 1))
    c.text(mr - 110, y - 12, "Proventos", font="F2", size=8.0, rgb=(1, 1, 1), align="right")
    c.text(mr - 10, y - 12, "Descontos", font="F2", size=8.0, rgb=(1, 1, 1), align="right")
    y -= 32.0

    for cod, desc, prov, desc_v in linhas:
        c.text(ml + 8, y, cod, font="F1", size=8.0)
        c.text(ml + 54, y, _trunc(desc, 48), font="F1", size=8.0)
        if prov:
            c.text(mr - 110, y, prov, font="F1", size=8.0, align="right")
        if desc_v:
            c.text(mr - 10, y, desc_v, font="F1", size=8.0, align="right")
        y -= 17.0

    y -= 14.0
    c.rect(ml, y - 28, mr - ml, 28, fill_rgb=(0.93, 0.96, 1.0), stroke_rgb=(0.68, 0.78, 0.92))
    c.text(ml + 12, y - 18, f"TOTAL LÍQUIDO DE FÉRIAS A RECEBER: {_fmt_moeda(ferias.get('valor_liquido'))}", font="F2", size=10.5, rgb=(0.08, 0.26, 0.50))

    _rodape_doc(c, f"RECIBO-FERIAS-{ferias.get('id')}")
    return montar_pdf_paginas([c.to_bytes()])


def gerar_pdf_trct(
    rescisao: Dict[str, Any],
    colaborador: Dict[str, Any],
    empresa: Optional[Dict[str, Any]] = None,
) -> bytes:
    """RF-115: Gera Termo de Rescisão do Contrato de Trabalho (TRCT) em PDF A4."""
    c = _PDFCanvas()
    y = _desenhar_cabecalho_doc(
        c,
        "TERMO DE RESCISÃO CONTRATUAL (TRCT)",
        f"Rescisão #{rescisao.get('id')}  |  {str(rescisao.get('tipo_rescisao') or '').upper()}",
        empresa,
    )
    y = _desenhar_identificacao_colab(c, y, colaborador)

    ml = 34.0
    mr = A4_WIDTH - 34.0
    c.text(
        ml + 8,
        y,
        f"Desligamento: {_fmt_data_br(rescisao.get('data_afastamento'))}  |  Projeção Aviso: {_fmt_data_br(rescisao.get('data_aviso_previo_projetada') or rescisao.get('data_afastamento'))}  |  Prazo Art. 477: {_fmt_data_br(rescisao.get('data_limite_pagamento'))}",
        font="F2",
        size=8.2,
    )
    y -= 18.0

    calc = rescisao.get("calculo") if isinstance(rescisao.get("calculo"), dict) else {}
    proventos = [
        ("50", f"Saldo de Salário ({rescisao.get('saldo_salario_dias') or 0} dias)", rescisao.get("saldo_salario")),
        ("63", "13º Salário Proporcional", rescisao.get("decimo_terceiro_proporcional")),
        ("65", "Férias Proporcionais + 1/3", (float(rescisao.get("ferias_proporcionais") or 0) + float(rescisao.get("terco_ferias_proporcionais") or 0))),
        ("66", "Férias Vencidas (+ Dobro se aplicável)", rescisao.get("ferias_vencidas")),
        ("69", f"Aviso Prévio Indenizado ({rescisao.get('dias_aviso_previo') or 0}d)", rescisao.get("aviso_previo_indenizado")),
        ("95", "Outras Verbas / Médias Variáveis / Multa Art. 477/479", (float(rescisao.get("medias_variaveis") or 0) + float(rescisao.get("multa_art_477") or 0) + float(rescisao.get("multa_art_479") or 0))),
    ]
    descontos = [
        ("112.1", "Previdência Social (INSS Rescisório)", rescisao.get("desconto_inss")),
        ("114.1", "IRRF sobre Verbas Rescisórias", rescisao.get("desconto_irrf")),
        ("115", "Aviso Prévio / Outros Descontos (Art. 480 CLT)", rescisao.get("desconto_aviso_empregado") or calc.get("desconto_aviso_empregado")),
    ]

    c.rect(ml, y - 18, mr - ml, 18, fill_rgb=(0.12, 0.21, 0.34), stroke_rgb=(0.12, 0.21, 0.34))
    c.text(ml + 8, y - 12, "Rubr.", font="F2", size=8.0, rgb=(1, 1, 1))
    c.text(ml + 54, y - 12, "Discriminação das Verbas Rescisórias", font="F2", size=8.0, rgb=(1, 1, 1))
    c.text(mr - 110, y - 12, "Proventos", font="F2", size=8.0, rgb=(1, 1, 1), align="right")
    c.text(mr - 10, y - 12, "Descontos", font="F2", size=8.0, rgb=(1, 1, 1), align="right")
    y -= 30.0

    for cod, desc, val in proventos:
        v = float(val or 0.0)
        if v <= 0:
            continue
        c.text(ml + 8, y, cod, font="F1", size=8.0)
        c.text(ml + 54, y, _trunc(desc, 52), font="F1", size=8.0)
        c.text(mr - 110, y, _fmt_moeda(v), font="F1", size=8.0, align="right")
        y -= 16.0
    for cod, desc, val in descontos:
        v = float(val or 0.0)
        if v <= 0:
            continue
        c.text(ml + 8, y, cod, font="F1", size=8.0)
        c.text(ml + 54, y, _trunc(desc, 52), font="F1", size=8.0)
        c.text(mr - 10, y, _fmt_moeda(v), font="F1", size=8.0, align="right")
        y -= 16.0

    y -= 12.0
    c.rect(ml, y - 42, mr - ml, 42, fill_rgb=(0.95, 0.97, 0.99), stroke_rgb=(0.74, 0.80, 0.88))
    c.text(ml + 12, y - 16, f"Total Bruto: {_fmt_moeda(rescisao.get('total_bruto'))}   |   Total Descontos: {_fmt_moeda(rescisao.get('total_descontos'))}", font="F1", size=8.5)
    c.text(ml + 12, y - 32, f"VALOR RESCISÓRIO LÍQUIDO: {_fmt_moeda(rescisao.get('valor_liquido'))}   |   Multa FGTS (GRRF): {_fmt_moeda(rescisao.get('multa_fgts_valor'))}", font="F2", size=9.2, rgb=(0.08, 0.26, 0.50))

    _rodape_doc(c, f"TRCT-{rescisao.get('id')}")
    return montar_pdf_paginas([c.to_bytes()])


def gerar_pdf_guias_fgts_sd(
    rescisao: Dict[str, Any],
    colaborador: Dict[str, Any],
    empresa: Optional[Dict[str, Any]] = None,
) -> bytes:
    """RF-116: Gera documento consolidado de Chave FGTS / GRRF e Requerimento de Seguro-Desemprego."""
    c = _PDFCanvas()
    y = _desenhar_cabecalho_doc(c, "GUIA FGTS & SEGURO-DESEMPREGO", f"Rescisão #{rescisao.get('id')}", empresa)
    y = _desenhar_identificacao_colab(c, y, colaborador)

    ml = 42.0
    tipo = str(rescisao.get("tipo_rescisao") or "")
    direito_sd = "SIM" if tipo in ("sem_justa_causa", "rescisao_antecipada_empregador", "rescisao_indireta") else "NÃO APLICÁVEL"
    saque_fgts = "INTEGRAL (CÓD. 01)" if tipo in ("sem_justa_causa", "rescisao_antecipada_empregador", "rescisao_indireta", "termino_experiencia", "falecimento") else ("80% ACORDO (CÓD. 07)" if tipo == "acordo_mutuo" else "NÃO AUTORIZADO")

    linhas = [
        "1. COMUNICAÇÃO DE MOVIMENTAÇÃO FGTS DIGITAL / GRRF",
        f"Modalidade de Desligamento: {tipo.upper()}",
        f"Enquadramento Saque FGTS: {saque_fgts}",
        f"Saldo Base FGTS Informado: {_fmt_moeda(rescisao.get('saldo_fgts'))}",
        f"Multa Rescisória FGTS ({rescisao.get('multa_fgts_percentual') or 0}%): {_fmt_moeda(rescisao.get('multa_fgts_valor'))}",
        "",
        "2. REQUERIMENTO DE SEGURO-DESEMPREGO (WEB / EMPREGADOR WEB)",
        f"Elegibilidade Formal à Guia CD/SD: {direito_sd}",
        f"Chave / Protocolo Interno: {rescisao.get('chave_fgts') or ('FGTS-' + str(rescisao.get('id') or 0).zfill(6))}",
        f"Data de Dispensa: {_fmt_data_br(rescisao.get('data_afastamento'))}",
    ]
    for idx, ln in enumerate(linhas):
        c.text(ml, y - idx * 18, ln, font="F2" if idx in (0, 6) else "F1", size=9.0 if idx in (0, 6) else 8.4)

    _rodape_doc(c, f"FGTS-SD-{rescisao.get('id')}")
    return montar_pdf_paginas([c.to_bytes()])
