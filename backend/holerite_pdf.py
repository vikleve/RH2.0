# -*- coding: utf-8 -*-
"""
Gerador Corporativo de Contracheque / Holerite em PDF (Padrão A4) — RH2.0 Enterprise
Implementação 100% Python puro (PDF 1.4, WinAnsiEncoding / cp1252) sem dependências binárias externas,
garantindo execução idêntica em ambiente local e Vercel Serverless.
"""
import hashlib
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List


A4_WIDTH = 595.28
A4_HEIGHT = 841.89


def _fmt_moeda(valor: Any) -> str:
    try:
        num = float(valor or 0.0)
    except (TypeError, ValueError):
        num = 0.0
    s = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _fmt_data_br(data_iso: Any) -> str:
    if not data_iso:
        return "--/--/----"
    s = str(data_iso).strip()[:10]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return s


def _mascarar_cpf(cpf: str) -> str:
    digs = re.sub(r"\D", "", str(cpf or ""))
    if len(digs) == 11:
        return f"***.{digs[3:6]}.{digs[6:9]}-**"
    return str(cpf or "--")


def _pdf_escape(texto: Any) -> bytes:
    """Converte string Unicode para bytes WinAnsi (cp1252) escapados para literal PDF."""
    s = str(texto if texto is not None else "")
    s = s.replace("\r", " ").replace("\n", " ")
    raw = s.encode("cp1252", errors="replace")
    out = bytearray()
    for b in raw:
        if b in (40, 41, 92):  # '(', ')', '\'
            out.append(92)
        out.append(b)
    return bytes(out)


def _trunc(texto: Any, max_chars: int) -> str:
    s = str(texto if texto is not None else "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 3)] + "..."


def nome_arquivo_contracheque(folha: Dict[str, Any]) -> str:
    """Gera nome de arquivo padronizado: CONTRACHEQUE_NOME_MM_AAAA.pdf."""
    nome = str(folha.get("colaborador_nome") or "COLABORADOR")
    nome_norm = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    nome_norm = re.sub(r"[^A-Za-z0-9]+", "_", nome_norm).strip("_").upper()
    comp = str(folha.get("competencia") or "0000-00").strip()
    partes = comp.split("-")
    comp_fmt = f"{partes[1]}_{partes[0]}" if len(partes) == 2 else comp.replace("-", "_")
    return f"CONTRACHEQUE_{nome_norm}_{comp_fmt}.pdf"


def calcular_codigo_autenticidade(folha: Dict[str, Any]) -> str:
    """Gera código determinístico SHA-256 truncado para validação de autenticidade do recibo."""
    base = "|".join([
        str(folha.get("id", "")),
        str(folha.get("competencia", "")),
        str(folha.get("colaborador_id", "")),
        f"{float(folha.get('salario_liquido') or 0.0):.2f}",
        str(folha.get("criado_em", "")),
    ])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16].upper()


def numero_recibo_folha(folha: Dict[str, Any]) -> str:
    comp = re.sub(r"\D", "", str(folha.get("competencia") or "000000"))
    fid = int(folha.get("id") or 0)
    return f"REC-{comp}-{fid:06d}"


class _PDFCanvas:
    """Construtor de comandos gráficos PDF 1.4 para página A4."""

    def __init__(self):
        self.cmds: List[bytes] = []

    def rect(self, x: float, y: float, w: float, h: float, fill_rgb=None, stroke_rgb=(0.80, 0.84, 0.88), line_w: float = 0.6):
        self.cmds.append(f"q {line_w:.2f} w".encode("ascii"))
        if fill_rgb is not None:
            self.cmds.append(f"{fill_rgb[0]:.3f} {fill_rgb[1]:.3f} {fill_rgb[2]:.3f} rg".encode("ascii"))
        if stroke_rgb is not None:
            self.cmds.append(f"{stroke_rgb[0]:.3f} {stroke_rgb[1]:.3f} {stroke_rgb[2]:.3f} RG".encode("ascii"))
        op = "B" if (fill_rgb is not None and stroke_rgb is not None) else ("f" if fill_rgb is not None else "S")
        self.cmds.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re {op} Q".encode("ascii"))

    def line(self, x1: float, y1: float, x2: float, y2: float, rgb=(0.80, 0.84, 0.88), line_w: float = 0.6):
        self.cmds.append(
            f"q {line_w:.2f} w {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} RG {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q".encode("ascii")
        )

    def text(self, x: float, y: float, txt: Any, font: str = "F1", size: float = 9.0, rgb=(0.08, 0.12, 0.18), align: str = "left"):
        s = str(txt if txt is not None else "")
        # Estimativa de largura média para alinhamento à direita / centro em Helvetica
        avg_w = size * (0.51 if font == "F1" else 0.54)
        tx = x
        if align == "right":
            tx = x - (len(s) * avg_w)
        elif align == "center":
            tx = x - ((len(s) * avg_w) / 2.0)
        escaped = _pdf_escape(s)
        self.cmds.append(
            b"q BT /" + font.encode("ascii") + f" {size:.1f} Tf {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg {tx:.2f} {y:.2f} Td (".encode("ascii")
            + escaped + b") Tj ET Q"
        )

    def to_bytes(self) -> bytes:
        return b"\n".join(self.cmds)


def _desenhar_pagina_holerite(folha: Dict[str, Any], mascarar_cpf: bool = True) -> bytes:
    c = _PDFCanvas()
    ml = 34.0
    mr = A4_WIDTH - 34.0
    cw = mr - ml  # 527.28 pt

    # Fundo branco e moldura externa discreta
    c.rect(ml, 36.0, cw, A4_HEIGHT - 72.0, fill_rgb=(1, 1, 1), stroke_rgb=(0.76, 0.80, 0.85), line_w=0.8)

    # ── 1. CABEÇALHO DA EMPRESA ──────────────────────────────────────────────
    top_y = A4_HEIGHT - 36.0
    hdr_h = 64.0
    c.rect(ml, top_y - hdr_h, cw, hdr_h, fill_rgb=(0.96, 0.97, 0.99), stroke_rgb=(0.76, 0.80, 0.85), line_w=0.8)

    # Emblema corporativo (vetorizado)
    c.rect(ml + 10, top_y - 48, 34, 34, fill_rgb=(0.08, 0.36, 0.22), stroke_rgb=None)
    c.text(ml + 27, top_y - 35, "RH", font="F2", size=12.0, rgb=(1, 1, 1), align="center")

    razao = _trunc(folha.get("empresa_razao_social") or "FORÇAVERDE USINA DE ENERGIA E BIOCOMBUSTÍVEIS S.A.", 52)
    cnpj = folha.get("empresa_cnpj") or "12.345.678/0001-90"
    end_emp = _trunc(folha.get("empresa_endereco") or "Fazenda Boa Esperança, s/n - Sertãozinho / SP", 64)

    c.text(ml + 54, top_y - 22, razao, font="F2", size=10.5, rgb=(0.06, 0.14, 0.24))
    c.text(ml + 54, top_y - 35, f"CNPJ: {cnpj}", font="F1", size=8.0, rgb=(0.30, 0.36, 0.44))
    c.text(ml + 54, top_y - 47, end_emp, font="F1", size=7.8, rgb=(0.35, 0.41, 0.49))

    # Bloco direito: RECIBO DE PAGAMENTO + Competência + Nº Recibo
    comp_raw = str(folha.get("competencia") or "")
    comp_parts = comp_raw.split("-")
    comp_br = f"{comp_parts[1]}/{comp_parts[0]}" if len(comp_parts) == 2 else comp_raw
    tipo_folha = str(folha.get("tipo_folha") or "mensal").upper()
    recibo_num = numero_recibo_folha(folha)

    c.text(mr - 10, top_y - 20, "RECIBO DE PAGAMENTO", font="F2", size=10.5, rgb=(0.09, 0.26, 0.52), align="right")
    c.text(mr - 10, top_y - 33, f"Competência: {comp_br} ({tipo_folha})", font="F2", size=8.5, rgb=(0.12, 0.18, 0.26), align="right")
    c.text(mr - 10, top_y - 46, f"Recibo Nº: {recibo_num}", font="F1", size=7.8, rgb=(0.35, 0.41, 0.49), align="right")

    # ── 2. IDENTIFICAÇÃO DO COLABORADOR ──────────────────────────────────────
    box_y = top_y - hdr_h - 62.0
    c.rect(ml, box_y, cw, 56.0, fill_rgb=(1, 1, 1), stroke_rgb=(0.80, 0.84, 0.88), line_w=0.6)

    cpf_txt = _mascarar_cpf(folha.get("colaborador_cpf", "")) if mascarar_cpf else (folha.get("colaborador_cpf") or "--")
    nome_colab = _trunc(folha.get("colaborador_nome") or "--", 42)
    mat_colab = _trunc(folha.get("colaborador_matricula") or "--", 16)
    cargo_colab = _trunc(folha.get("colaborador_cargo") or "--", 28)
    depto_colab = _trunc(folha.get("colaborador_setor") or "--", 24)
    adm_colab = _fmt_data_br(folha.get("colaborador_data_admissao"))
    sal_base = _fmt_moeda(folha.get("salario_base_contratual"))
    dep_irrf = int(folha.get("total_dependentes_irrf", folha.get("total_dependentes", 0)) or 0)

    c.text(ml + 8, box_y + 42, f"Matrícula: {mat_colab}", font="F2", size=8.2)
    c.text(ml + 125, box_y + 42, f"Nome: {nome_colab}", font="F2", size=8.2)
    c.text(mr - 8, box_y + 42, f"CPF: {cpf_txt}", font="F1", size=8.2, align="right")

    c.text(ml + 8, box_y + 26, f"Cargo/Função: {cargo_colab}", font="F1", size=8.0)
    c.text(ml + 235, box_y + 26, f"Departamento: {depto_colab}", font="F1", size=8.0)
    c.text(mr - 8, box_y + 26, f"Admissão: {adm_colab}", font="F1", size=8.0, align="right")

    c.text(ml + 8, box_y + 10, f"Salário-Base Contratual: {sal_base}", font="F1", size=8.0)
    c.text(ml + 235, box_y + 10, f"Dependentes IRRF: {dep_irrf}", font="F1", size=8.0)
    c.text(mr - 8, box_y + 10, f"Pagto: {_fmt_data_br(folha.get('data_pagamento'))}", font="F1", size=8.0, align="right")

    # ── 3. TABELA DE PROVENTOS E DESCONTOS ───────────────────────────────────
    tbl_top = box_y - 8.0
    tbl_hdr_h = 20.0
    c.rect(ml, tbl_top - tbl_hdr_h, cw, tbl_hdr_h, fill_rgb=(0.12, 0.21, 0.34), stroke_rgb=(0.12, 0.21, 0.34))

    col_cod = ml + 8
    col_desc = ml + 56
    col_ref = ml + 318
    col_prov = ml + 426
    col_desc_val = mr - 8

    c.text(col_cod, tbl_top - 13, "Cód.", font="F2", size=8.2, rgb=(1, 1, 1))
    c.text(col_desc, tbl_top - 13, "Descrição do Evento", font="F2", size=8.2, rgb=(1, 1, 1))
    c.text(col_ref, tbl_top - 13, "Referência", font="F2", size=8.2, rgb=(1, 1, 1), align="center")
    c.text(col_prov, tbl_top - 13, "Vencimentos (R$)", font="F2", size=8.2, rgb=(1, 1, 1), align="right")
    c.text(col_desc_val, tbl_top - 13, "Descontos (R$)", font="F2", size=8.2, rgb=(1, 1, 1), align="right")

    itens = [it for it in (folha.get("itens") or []) if it.get("tipo") in ("provento", "desconto")]
    row_h = 17.0
    max_rows_area = 390.0
    body_h = max(180.0, min(max_rows_area, max(len(itens), 1) * row_h + 10.0))
    tbl_bot = tbl_top - tbl_hdr_h - body_h
    c.rect(ml, tbl_bot, cw, body_h, fill_rgb=(1, 1, 1), stroke_rgb=(0.80, 0.84, 0.88))

    cur_y = tbl_top - tbl_hdr_h - 13.0
    for idx, it in enumerate(itens):
        if cur_y < tbl_bot + 6.0:
            break
        if idx % 2 == 1:
            c.rect(ml + 0.5, cur_y - 4.0, cw - 1.0, row_h, fill_rgb=(0.98, 0.99, 1.0), stroke_rgb=None)
        ref_val = float(it.get("referencia") or 0.0)
        ref_str = f"{ref_val:g} {it.get('unidade_referencia') or ''}".strip() if ref_val > 0 else "--"
        is_prov = it.get("tipo") == "provento"
        val_fmt = _fmt_moeda(it.get("valor_total"))

        c.text(col_cod, cur_y, _trunc(it.get("codigo_evento"), 8), font="F2", size=8.0)
        c.text(col_desc, cur_y, _trunc(it.get("descricao"), 44), font="F1", size=8.0)
        c.text(col_ref, cur_y, _trunc(ref_str, 16), font="F1", size=7.8, align="center")
        if is_prov:
            c.text(col_prov, cur_y, val_fmt, font="F1", size=8.0, rgb=(0.06, 0.40, 0.20), align="right")
        else:
            c.text(col_desc_val, cur_y, val_fmt, font="F1", size=8.0, rgb=(0.65, 0.12, 0.12), align="right")
        cur_y -= row_h

    # ── 4. TOTAIS E VALOR LÍQUIDO DESTACADO ──────────────────────────────────
    tot_h = 46.0
    tot_y = tbl_bot - tot_h - 6.0
    col3_w = cw / 3.0

    c.rect(ml, tot_y, col3_w - 3, tot_h, fill_rgb=(0.97, 0.98, 0.99), stroke_rgb=(0.80, 0.84, 0.88))
    c.text(ml + 10, tot_y + 30, "Total de Vencimentos", font="F1", size=8.0, rgb=(0.35, 0.41, 0.49))
    c.text(ml + col3_w - 12, tot_y + 11, _fmt_moeda(folha.get("total_proventos")), font="F2", size=10.5, rgb=(0.06, 0.40, 0.20), align="right")

    c.rect(ml + col3_w + 1.5, tot_y, col3_w - 3, tot_h, fill_rgb=(0.97, 0.98, 0.99), stroke_rgb=(0.80, 0.84, 0.88))
    c.text(ml + col3_w + 11.5, tot_y + 30, "Total de Descontos", font="F1", size=8.0, rgb=(0.35, 0.41, 0.49))
    c.text(ml + (col3_w * 2) - 10, tot_y + 11, _fmt_moeda(folha.get("total_descontos")), font="F2", size=10.5, rgb=(0.65, 0.12, 0.12), align="right")

    c.rect(ml + (col3_w * 2) + 3, tot_y, col3_w - 3, tot_h, fill_rgb=(0.91, 0.98, 0.94), stroke_rgb=(0.08, 0.55, 0.34), line_w=1.1)
    c.text(ml + (col3_w * 2) + 13, tot_y + 30, "VALOR LÍQUIDO A RECEBER", font="F2", size=8.2, rgb=(0.03, 0.38, 0.23))
    c.text(mr - 10, tot_y + 10, _fmt_moeda(folha.get("salario_liquido")), font="F2", size=13.0, rgb=(0.03, 0.38, 0.23), align="right")

    # ── 5. INFORMAÇÕES COMPLEMENTARES (BASES E FGTS INFORMATIVO) ─────────────
    bases_h = 36.0
    bases_y = tot_y - bases_h - 6.0
    c.rect(ml, bases_y, cw, bases_h, fill_rgb=(0.98, 0.99, 1.0), stroke_rgb=(0.80, 0.84, 0.88))
    col5_w = cw / 5.0
    bases_info = [
        ("Salário-Base", _fmt_moeda(folha.get("salario_base_contratual"))),
        ("Base Cálc. INSS", _fmt_moeda(folha.get("base_inss"))),
        ("Base Cálc. IRRF", _fmt_moeda(folha.get("base_irrf"))),
        ("Base Cálc. FGTS", _fmt_moeda(folha.get("base_fgts"))),
        ("FGTS do Mês (Info)", _fmt_moeda(folha.get("valor_fgts_informativo"))),
    ]
    for i, (lbl, val) in enumerate(bases_info):
        bx = ml + (i * col5_w) + 8
        c.text(bx, bases_y + 22, lbl, font="F1", size=7.4, rgb=(0.35, 0.41, 0.49))
        c.text(bx, bases_y + 9, val, font="F2", size=8.4, rgb=(0.08, 0.12, 0.18))

    # ── 6. RODAPÉ, ASSINATURAS E AUTENTICIDADE DIGITAL ───────────────────────
    foot_y = 48.0
    c.line(ml + 10, foot_y + 60, mr - 10, foot_y + 60, rgb=(0.85, 0.88, 0.92))
    c.text(ml + 10, foot_y + 46, "Declaro ter recebido a importância líquida discriminada neste recibo, correspondente à quitação das verbas do período.", font="F1", size=7.5, rgb=(0.30, 0.36, 0.44))

    c.line(ml + 10, foot_y + 22, ml + 230, foot_y + 22, rgb=(0.35, 0.41, 0.49), line_w=0.7)
    c.text(ml + 120, foot_y + 12, "Assinatura do Colaborador", font="F1", size=7.6, rgb=(0.30, 0.36, 0.44), align="center")

    c.line(mr - 230, foot_y + 22, mr - 10, foot_y + 22, rgb=(0.35, 0.41, 0.49), line_w=0.7)
    c.text(mr - 120, foot_y + 12, _trunc(razao, 36), font="F1", size=7.6, rgb=(0.30, 0.36, 0.44), align="center")

    emissao = datetime.now().strftime("%d/%m/%Y %H:%M")
    auth_hash = calcular_codigo_autenticidade(folha)
    c.text(
        ml + 10,
        foot_y + 1,
        f"Emissão: {emissao}  |  Recibo: {recibo_num}  |  Situação: {(folha.get('situacao') or 'calculada').upper()}  |  Autenticidade SHA-256: {auth_hash}",
        font="F1",
        size=7.0,
        rgb=(0.42, 0.47, 0.54),
    )

    return c.to_bytes()


def montar_pdf_paginas(streams_paginas: List[bytes]) -> bytes:
    """Empacota uma ou mais páginas A4 em um documento PDF 1.4 válido com tabela xref."""
    if not streams_paginas:
        streams_paginas = [_PDFCanvas().to_bytes()]

    objs: List[bytes] = []
    # 1: Catalog, 2: Pages, 3: Font F1 (Helvetica), 4: Font F2 (Helvetica-Bold)
    qtd_pags = len(streams_paginas)
    kids_refs = " ".join(f"{5 + i * 2} 0 R" for i in range(qtd_pags))

    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids_refs}] /Count {qtd_pags} >>".encode("ascii"))
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    for i, stream in enumerate(streams_paginas):
        page_id = 5 + i * 2
        content_id = page_id + 1
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {A4_WIDTH:.2f} {A4_HEIGHT:.2f}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")
        )
        objs.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, obj in enumerate(objs, start=1):
        offsets.append(len(buf))
        buf.extend(f"{idx} 0 obj\n".encode("ascii"))
        buf.extend(obj)
        buf.extend(b"\nendobj\n")

    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(objs) + 1}\n".encode("ascii"))
    buf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    buf.extend(
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(buf)


def gerar_pdf_holerite(folha: Dict[str, Any], mascarar_cpf: bool = True) -> bytes:
    """Gera um PDF A4 individual do contracheque."""
    return montar_pdf_paginas([_desenhar_pagina_holerite(folha, mascarar_cpf=mascarar_cpf)])


def gerar_pdf_holerites_lote(folhas: List[Dict[str, Any]], mascarar_cpf: bool = True) -> bytes:
    """Gera um único PDF A4 multi-página com todos os contracheques informados."""
    paginas = [_desenhar_pagina_holerite(f, mascarar_cpf=mascarar_cpf) for f in folhas]
    return montar_pdf_paginas(paginas)
