# -*- coding: utf-8 -*-
"""
Motor eSocial Trabalhista — Leiaute Oficial v_S_01_02_00 (S-1.2)
Eventos suportados:
- S-2230: Afastamento Temporário (Férias codMotAfast=15, Doença, Acidente, Maternidade, Retorno)
- S-1200: Remuneração de Trabalhador vinculado ao RGPS
- S-1210: Pagamentos de Rendimentos do Trabalho
- S-1299: Fechamento dos Eventos Periódicos
- S-2299: Desligamento (TRCT / eSocial)

Gera XML estruturado com namespaces S-1.2 e realiza validação estrita via ElementTree.
Nunca gera recibos governamentais fictícios sem transmissão ICP-Brasil A1/A3.
"""
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

NS_S2230 = "http://www.esocial.gov.br/schema/evt/evtAfastTemp/v_S_01_02_00"
NS_S1200 = "http://www.esocial.gov.br/schema/evt/evtRemun/v_S_01_02_00"
NS_S1210 = "http://www.esocial.gov.br/schema/evt/evtPgtos/v_S_01_02_00"
NS_S1299 = "http://www.esocial.gov.br/schema/evt/evtFechaEvPer/v_S_01_02_00"
NS_S2299 = "http://www.esocial.gov.br/schema/evt/evtDeslig/v_S_01_02_00"
NS_S2210 = "http://www.esocial.gov.br/schema/evt/evtCAT/v_S_01_02_00"
NS_S2220 = "http://www.esocial.gov.br/schema/evt/evtMonit/v_S_01_02_00"
NS_S2240 = "http://www.esocial.gov.br/schema/evt/evtExpRisco/v_S_01_02_00"
NS_S3000 = "http://www.esocial.gov.br/schema/evt/evtExclusao/v_S_01_02_00"

MAPA_MOTIVO_AFAST_ESOCIAL: Dict[str, str] = {
    "acidente_trabalho": "01",
    "auxilio_doenca_acidentario": "01",
    "doenca": "03",
    "auxilio_doenca": "03",
    "doenca_nao_relacionada": "03",
    "ferias": "15",
    "maternidade": "17",
    "licenca_maternidade": "17",
    "licenca_nao_remunerada": "21",
    "suspensao_disciplinar": "21",
    "paternidade": "29",
    "servico_militar": "33",
    "maternidade_prorrogacao": "35",
}

MAPA_MOTIVO_DESLIGAMENTO_ESOCIAL: Dict[str, str] = {
    "com_justa_causa": "01",
    "sem_justa_causa": "02",
    "rescisao_indireta": "03",
    "rescisao_antecipada_empregador": "04",
    "rescisao_antecipada_empregado": "05",
    "termino_experiencia": "06",
    "pedido_demissao": "07",
    "falecimento": "10",
    "acordo_mutuo": "33",
}


def _dig(val: Any) -> str:
    return re.sub(r"\D", "", str(val or ""))


def _gerar_id(cnpj_14: str) -> str:
    raiz = _dig(cnpj_14).ljust(14, "0")[:14]
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    suf = uuid.uuid4().hex[:5].upper()
    return f"ID1{raiz}{ts}{suf}"[:36]


def _tp_amb(ambiente: str) -> str:
    return "1" if str(ambiente or "homologacao").strip().lower() == "producao" else "2"


def _ide_evento_per(ind_apuracao: str, per_apur: str, ambiente: str, ind_retif: int = 1) -> str:
    return (
        f"<ideEvento>"
        f"<indRetif>{ind_retif}</indRetif>"
        f"<indApuracao>{ind_apuracao}</indApuracao>"
        f"<perApur>{escape(per_apur)}</perApur>"
        f"<tpAmb>{_tp_amb(ambiente)}</tpAmb>"
        f"<procEmi>1</procEmi>"
        f"<verProc>RH2.0-ENTERPRISE</verProc>"
        f"</ideEvento>"
    )


def _ide_empregador(cnpj_14: str) -> str:
    cnpj = _dig(cnpj_14).ljust(14, "0")[:14]
    # Para PJ CNPJ envia os 8 dígitos raiz ou 14 completos no padrão interno S-1.2
    nr_insc = cnpj[:8] if len(cnpj) == 14 else cnpj
    return f"<ideEmpregador><tpInsc>1</tpInsc><nrInsc>{escape(nr_insc)}</nrInsc></ideEmpregador>"


def gerar_xml_s2230(
    colaborador: Dict[str, Any],
    cnpj_empregador: str,
    data_inicio: str,
    motivo: str,
    data_fim: Optional[str] = None,
    ambiente: str = "homologacao",
    cid: Optional[str] = None,
    ind_retif: int = 1,
) -> Tuple[str, List[str]]:
    """Gera XML S-2230 (Afastamento Temporário / Férias / Retorno) conforme v_S_01_02_00."""
    erros: List[str] = []
    cpf = _dig(colaborador.get("cpf"))
    if len(cpf) != 11:
        erros.append("CPF do colaborador inválido para S-2230 (exige 11 dígitos).")
    dt_ini = str(data_inicio or "").strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", dt_ini):
        erros.append("Data inicial inválida para S-2230 (AAAA-MM-DD).")
    matricula = str(colaborador.get("matricula") or "").strip()
    if not matricula:
        erros.append("Matrícula ausente para S-2230.")
    if erros:
        return "", erros

    cod_mot = MAPA_MOTIVO_AFAST_ESOCIAL.get(str(motivo or "").lower().strip(), "03")
    if cod_mot in ("01", "03") and str(motivo).lower() != "ferias":
        # Observação CID opcional se informado
        info_atestado = f"<infoAtestado><codCID>{escape(str(cid)[:10])}</codCID></infoAtestado>" if cid else ""
    else:
        info_atestado = ""

    fim_block = ""
    if data_fim and re.match(r"^\d{4}-\d{2}-\d{2}$", str(data_fim).strip()[:10]):
        fim_block = f"<fimAfastamento><dtTermAfast>{escape(str(data_fim).strip()[:10])}</dtTermAfast></fimAfastamento>"

    evt_id = _gerar_id(cnpj_empregador)
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<eSocial xmlns="{NS_S2230}">'
        f'<evtAfastTemp Id="{escape(evt_id)}">'
        f'<ideEvento><indRetif>{ind_retif}</indRetif><tpAmb>{_tp_amb(ambiente)}</tpAmb><procEmi>1</procEmi><verProc>RH2.0-ENTERPRISE</verProc></ideEvento>'
        f'{_ide_empregador(cnpj_empregador)}'
        f'<ideVinculo><cpfTrab>{cpf}</cpfTrab><matricula>{escape(matricula)}</matricula></ideVinculo>'
        f'<infoAfastamento>'
        f'<iniAfastamento><dtIniAfast>{escape(dt_ini)}</dtIniAfast><codMotAfast>{cod_mot}</codMotAfast>{info_atestado}</iniAfastamento>'
        f'{fim_block}'
        f'</infoAfastamento>'
        f'</evtAfastTemp>'
        f'</eSocial>'
    )
    return xml, []


def gerar_xml_s1200(
    colaborador: Dict[str, Any],
    cnpj_empregador: str,
    competencia: str,
    itens_remuneracao: List[Dict[str, Any]],
    ind_apuracao: str = "1",
    ambiente: str = "homologacao",
) -> Tuple[str, List[str]]:
    """Gera XML S-1200 (Remuneração RGPS) para folha mensal ('1') ou 13º anual ('2')."""
    erros: List[str] = []
    cpf = _dig(colaborador.get("cpf"))
    if len(cpf) != 11:
        erros.append("CPF do colaborador inválido para S-1200.")
    per_apur = str(competencia or "").strip()[:4] if ind_apuracao == "2" else str(competencia or "").strip()[:7]
    if not per_apur:
        erros.append("Período de apuração ausente para S-1200.")
    if not itens_remuneracao:
        erros.append("S-1200 requer ao menos uma rubrica de remuneração.")
    if erros:
        return "", erros

    cnpj_estab = _dig(cnpj_empregador).ljust(14, "0")[:14]
    cod_lot = str(colaborador.get("centro_custo") or colaborador.get("setor") or "01")[:30]
    matricula = str(colaborador.get("matricula") or "").strip() or cpf

    itens_xml = []
    for it in itens_remuneracao:
        cod_rub = str(it.get("codigo") or it.get("codigo_catalogo") or "0001").strip()[:30]
        val = abs(float(it.get("valor_total") or it.get("valor") or 0.0))
        if val <= 0:
            continue
        itens_xml.append(
            f"<itensRemun>"
            f"<codRubr>{escape(cod_rub)}</codRubr>"
            f"<ideTabRubr>RH20</ideTabRubr>"
            f"<vrRubr>{val:.2f}</vrRubr>"
            f"<indApurIR>0</indApurIR>"
            f"</itensRemun>"
        )
    if not itens_xml:
        itens_xml.append("<itensRemun><codRubr>0001</codRubr><ideTabRubr>RH20</ideTabRubr><vrRubr>0.01</vrRubr><indApurIR>0</indApurIR></itensRemun>")

    evt_id = _gerar_id(cnpj_empregador)
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<eSocial xmlns="{NS_S1200}">'
        f'<evtRemun Id="{escape(evt_id)}">'
        f'{_ide_evento_per(ind_apuracao, per_apur, ambiente)}'
        f'{_ide_empregador(cnpj_empregador)}'
        f'<ideTrabalhador><cpfTrab>{cpf}</cpfTrab></ideTrabalhador>'
        f'<dmDev>'
        f'<ideDmDev>DM-{escape(per_apur)}-{escape(matricula)}</ideDmDev>'
        f'<codCateg>101</codCateg>'
        f'<infoPerApur><ideEstabLot><tpInsc>1</tpInsc><nrInsc>{cnpj_estab}</nrInsc><codLotacao>{escape(cod_lot)}</codLotacao>'
        f'<remunPerApur><matricula>{escape(matricula)}</matricula>{"".join(itens_xml)}</remunPerApur>'
        f'</ideEstabLot></infoPerApur>'
        f'</dmDev>'
        f'</evtRemun>'
        f'</eSocial>'
    )
    return xml, []


def gerar_xml_s1210(
    colaborador: Dict[str, Any],
    cnpj_empregador: str,
    competencia: str,
    data_pagamento: str,
    valor_liquido: float,
    ind_apuracao: str = "1",
    ambiente: str = "homologacao",
) -> Tuple[str, List[str]]:
    """Gera XML S-1210 (Pagamentos de Rendimentos do Trabalho) para competência fechada ou 13º."""
    cpf = _dig(colaborador.get("cpf"))
    if len(cpf) != 11:
        return "", ["CPF inválido para S-1210."]
    per_apur = str(competencia or "").strip()[:7]
    dt_pg = str(data_pagamento or datetime.now().strftime("%Y-%m-%d")).strip()[:10]
    matricula = str(colaborador.get("matricula") or "").strip() or cpf
    evt_id = _gerar_id(cnpj_empregador)
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<eSocial xmlns="{NS_S1210}">'
        f'<evtPgtos Id="{escape(evt_id)}">'
        f'<ideEvento><indRetif>1</indRetif><perApur>{escape(per_apur)}</perApur><tpAmb>{_tp_amb(ambiente)}</tpAmb><procEmi>1</procEmi><verProc>RH2.0-ENTERPRISE</verProc></ideEvento>'
        f'{_ide_empregador(cnpj_empregador)}'
        f'<ideBenef><cpfBenef>{cpf}</cpfBenef>'
        f'<infoPgto>'
        f'<dtPgto>{escape(dt_pg)}</dtPgto>'
        f'<tpPgto>{ "4" if str(ind_apuracao) == "2" else "1" }</tpPgto>'
        f'<perRef>{escape(per_apur[:4] if str(ind_apuracao) == "2" else per_apur)}</perRef>'
        f'<ideDmDev>DM-{escape(per_apur)}-{escape(matricula)}</ideDmDev>'
        f'<vrLiq>{max(0.0, float(valor_liquido or 0.0)):.2f}</vrLiq>'
        f'</infoPgto>'
        f'</ideBenef>'
        f'</evtPgtos>'
        f'</eSocial>'
    )
    return xml, []


def gerar_xml_s1299(
    cnpj_empregador: str,
    competencia: str,
    possui_remuneracao: bool = True,
    possui_pagamentos: bool = True,
    ind_apuracao: str = "1",
    ambiente: str = "homologacao",
) -> Tuple[str, List[str]]:
    """Gera XML S-1299 (Fechamento dos Eventos Periódicos) conforme v_S_01_02_00."""
    per_apur = str(competencia or "").strip()[:4] if ind_apuracao == "2" else str(competencia or "").strip()[:7]
    if not per_apur:
        return "", ["Competência obrigatória para S-1299."]
    evt_id = _gerar_id(cnpj_empregador)
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<eSocial xmlns="{NS_S1299}">'
        f'<evtFechaEvPer Id="{escape(evt_id)}">'
        f'{_ide_evento_per(ind_apuracao, per_apur, ambiente)}'
        f'{_ide_empregador(cnpj_empregador)}'
        f'<infoFech>'
        f'<evtRemun>{"S" if possui_remuneracao else "N"}</evtRemun>'
        f'<evtPgtos>{"S" if possui_pagamentos else "N"}</evtPgtos>'
        f'<evtComProd>N</evtComProd>'
        f'<evtContratAvNP>N</evtContratAvNP>'
        f'<evtInfoComplPer>N</evtInfoComplPer>'
        f'</infoFech>'
        f'</evtFechaEvPer>'
        f'</eSocial>'
    )
    return xml, []


def gerar_xml_s2299(
    colaborador: Dict[str, Any],
    rescisao: Dict[str, Any],
    cnpj_empregador: str,
    ambiente: str = "homologacao",
) -> Tuple[str, List[str]]:
    """Gera XML S-2299 (Desligamento) com verbas rescisórias conforme v_S_01_02_00."""
    erros: List[str] = []
    cpf = _dig(colaborador.get("cpf"))
    if len(cpf) != 11:
        erros.append("CPF do colaborador inválido para S-2299.")
    dt_deslig = str(rescisao.get("data_afastamento") or rescisao.get("data_desligamento") or "").strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", dt_deslig):
        erros.append("Data de desligamento inválida para S-2299.")
    matricula = str(colaborador.get("matricula") or "").strip() or cpf
    if erros:
        return "", erros

    tipo_key = str(rescisao.get("tipo_rescisao") or "sem_justa_causa").lower().strip()
    mtv = MAPA_MOTIVO_DESLIGAMENTO_ESOCIAL.get(tipo_key, "02")
    dt_proj = str(rescisao.get("data_aviso_previo_projetada") or dt_deslig)[:10]
    dt_pgto = str(rescisao.get("data_limite_pagamento") or dt_deslig)[:10]
    cnpj_estab = _dig(cnpj_empregador).ljust(14, "0")[:14]
    vlr_bruto = float(rescisao.get("total_bruto") or 0.0)
    aviso_ind = float(rescisao.get("aviso_previo_indenizado") or 0.0) > 0

    verbas_block = (
        f"<verbasResc>"
        f"<dmDev>"
        f"<ideDmDev>RESC-{escape(str(rescisao.get('id') or '1'))}</ideDmDev>"
        f"<infoPerApur><ideEstabLot><tpInsc>1</tpInsc><nrInsc>{cnpj_estab}</nrInsc><codLotacao>01</codLotacao>"
        f"<detVerbas><codRubr>0600</codRubr><ideTabRubr>RH20</ideTabRubr><vrRubr>{max(0.01, vlr_bruto):.2f}</vrRubr></detVerbas>"
        f"</ideEstabLot></infoPerApur>"
        f"</dmDev>"
        f"</verbasResc>"
    )

    evt_id = _gerar_id(cnpj_empregador)
    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<eSocial xmlns="{NS_S2299}">'
        f'<evtDeslig Id="{escape(evt_id)}">'
        f'<ideEvento><indRetif>1</indRetif><tpAmb>{_tp_amb(ambiente)}</tpAmb><procEmi>1</procEmi><verProc>RH2.0-ENTERPRISE</verProc></ideEvento>'
        f'{_ide_empregador(cnpj_empregador)}'
        f'<ideVinculo><cpfTrab>{cpf}</cpfTrab><matricula>{escape(matricula)}</matricula></ideVinculo>'
        f'<infoDeslig>'
        f'<mtvDeslig>{mtv}</mtvDeslig>'
        f'<dtDeslig>{escape(dt_deslig)}</dtDeslig>'
        f'<indPagtoAPI>{"S" if aviso_ind else "N"}</indPagtoAPI>'
        f'<dtProjFimAPI>{escape(dt_proj)}</dtProjFimAPI>'
        f'<pensAlim>0</pensAlim>'
        f'<dtPgto>{escape(dt_pgto)}</dtPgto>'
        f'{verbas_block}'
        f'</infoDeslig>'
        f'</evtDeslig>'
        f'</eSocial>'
    )
    return xml, []


def gerar_xml_s3000(
    cnpj_empregador: str,
    tp_evento: str,
    nr_rec_evt: str,
    cpf_trabalhador: Optional[str] = None,
    per_apur: Optional[str] = None,
    ambiente: str = "homologacao",
) -> Tuple[str, List[str]]:
    """Gera o evento S-3000 (Exclusão de Eventos) conforme leiaute oficial v_S_01_02_00."""
    erros = []
    cnpj = _dig(cnpj_empregador)
    rec = str(nr_rec_evt or "").strip()
    if not rec:
        erros.append("Número do recibo do evento a ser excluído (nrRecEvt) é obrigatório.")
    tipo = str(tp_evento or "").strip().upper()
    if not tipo:
        erros.append("Tipo do evento a ser excluído (tpEvento) é obrigatório.")
    if erros:
        return "", erros

    id_evt = _gerar_id(cnpj)
    tp_amb = _tp_amb(ambiente)
    cpf_node = ""
    if cpf_trabalhador:
        cpf_dig = _dig(cpf_trabalhador).zfill(11)
        cpf_node = f"      <ideTrabalhador><cpfTrab>{cpf_dig}</cpfTrab></ideTrabalhador>\n"
    per_node = ""
    if per_apur:
        per_node = f"      <idePeriodo><perApur>{per_apur}</perApur></idePeriodo>\n"

    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<eSocial xmlns="{NS_S3000}">\n'
        f'  <evtExclusao Id="{id_evt}">\n'
        f'    <ideEvento>\n'
        f'      <tpAmb>{tp_amb}</tpAmb>\n'
        f'      <procEmi>1</procEmi>\n'
        f'      <verProc>RH2.0-Enterprise-2026</verProc>\n'
        f'    </ideEvento>\n'
        f'    {_ide_empregador(cnpj)}\n'
        f'    <infoExclusao>\n'
        f'      <tpEvento>{tipo}</tpEvento>\n'
        f'      <nrRecEvt>{escape(rec)}</nrRecEvt>\n'
        f'{cpf_node}'
        f'{per_node}'
        f'    </infoExclusao>\n'
        f'  </evtExclusao>\n'
        f'</eSocial>'
    )
    return xml, []


def validar_xml_esocial_trabalhista(tipo_evento: str, xml_str: str) -> Tuple[bool, List[str]]:
    """Valida estrutura XML, namespace v_S_01_02_00 e elementos obrigatórios dos eventos trabalhistas."""
    tipo = str(tipo_evento or "").upper().strip()
    if tipo in ("S-2190", "S-2200"):
        from backend.esocial_admissao import validar_xml_esocial
        return validar_xml_esocial(tipo, xml_str)

    if not xml_str or not str(xml_str).strip():
        return False, ["Conteúdo XML vazio."]
    try:
        root = ET.fromstring(str(xml_str).strip())
    except ET.ParseError as exc:
        return False, [f"XML malformado: {exc}"]

    mapa_ns = {
        "S-2230": (NS_S2230, "evtAfastTemp", [["ideEvento", "tpAmb"], ["ideEmpregador", "nrInsc"], ["ideVinculo", "cpfTrab"], ["infoAfastamento", "iniAfastamento", "dtIniAfast"], ["infoAfastamento", "iniAfastamento", "codMotAfast"]]),
        "S-1200": (NS_S1200, "evtRemun", [["ideEvento", "perApur"], ["ideEmpregador", "nrInsc"], ["ideTrabalhador", "cpfTrab"], ["dmDev", "ideDmDev"]]),
        "S-1210": (NS_S1210, "evtPgtos", [["ideEvento", "perApur"], ["ideEmpregador", "nrInsc"], ["ideBenef", "cpfBenef"], ["ideBenef", "infoPgto", "dtPgto"], ["ideBenef", "infoPgto", "vrLiq"]]),
        "S-1299": (NS_S1299, "evtFechaEvPer", [["ideEvento", "perApur"], ["ideEmpregador", "nrInsc"], ["infoFech", "evtRemun"], ["infoFech", "evtPgtos"]]),
        "S-2299": (NS_S2299, "evtDeslig", [["ideEvento", "tpAmb"], ["ideEmpregador", "nrInsc"], ["ideVinculo", "cpfTrab"], ["infoDeslig", "mtvDeslig"], ["infoDeslig", "dtDeslig"]]),
        "S-2210": (NS_S2210, "evtCAT", [["ideEmpregador", "nrInsc"], ["cat", "dtAcid"], ["cat", "tpAcid"]]),
        "S-2220": (NS_S2220, "evtMonit", [["ideEmpregador", "nrInsc"], ["aso", "dtAso"], ["aso", "resAso"], ["aso", "medico", "nrCRM"]]),
        "S-2240": (NS_S2240, "evtExpRisco", [["ideEmpregador", "nrInsc"], ["infoExpRisco", "dtIniCondicao"], ["infoExpRisco", "agNoc", "codAgNoc"]]),
        "S-3000": (NS_S3000, "evtExclusao", [["ideEmpregador", "nrInsc"], ["infoExclusao", "tpEvento"], ["infoExclusao", "nrRecEvt"]]),
    }
    if tipo not in mapa_ns:
        return False, [f"Tipo de evento não suportado na validação v_S_01_02_00: {tipo_evento}"]

    ns, evt_tag, obrigatorios = mapa_ns[tipo]
    expected_root = f"{{{ns}}}eSocial"
    if root.tag != expected_root:
        return False, [f"Namespace/raiz inválida para {tipo}: esperado {expected_root}, obtido {root.tag}."]

    evt_node = root.find(f"{{{ns}}}{evt_tag}")
    if evt_node is None or not evt_node.attrib.get("Id"):
        return False, [f"Elemento {evt_tag} ausente ou sem atributo Id obrigatório."]

    erros: List[str] = []
    for path_tags in obrigatorios:
        cur = evt_node
        for tg in path_tags:
            cur = cur.find(f"{{{ns}}}{tg}")
            if cur is None:
                break
        if cur is None or not (cur.text or "").strip():
            erros.append(f"Elemento obrigatório ausente ou vazio em {tipo}: {'/'.join(path_tags)}.")

    return len(erros) == 0, erros
