# -*- coding: utf-8 -*-
"""
Motor eSocial Admissional (S-2190 Admissão Preliminar & S-2200 Admissão Completa) — RF-015 / RN-010
Leiaute oficial eSocial v_S_01_02_00 (S-1.2).
Regras de conformidade:
- Determina aplicabilidade entre S-2190, S-2200 ou sequência S-2190 -> S-2200 sem duplicar eventos indevidamente.
- Valida campos obrigatórios e estrutura XML contra os elementos exigidos pelo leiaute S-1.2.
- Nunca gera recibos oficiais fictícios sem transmissão real com certificado digital ICP-Brasil A1/A3.
"""
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

NS_S2190 = "http://www.esocial.gov.br/schema/evt/evtAdmPrelim/v_S_01_02_00"
NS_S2200 = "http://www.esocial.gov.br/schema/evt/evtAdmissao/v_S_01_02_00"

MAPA_CATEGORIA_ESOCIAL = {
    "clt": "101",
    "experiencia": "101",
    "indeterminado": "101",
    "aprendiz": "103",
    "temporario": "106",
    "domestico": "104",
    "estagio": "901",
}


def _limpar_digitos(val: Any) -> str:
    return re.sub(r"\D", "", str(val or ""))


def _gerar_id_evento(cnpj_14: str) -> str:
    raiz_14 = _limpar_digitos(cnpj_14).ljust(14, "0")[:14]
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    suf = uuid.uuid4().hex[:5].upper()
    return f"ID1{raiz_14}{ts}{suf}"[:36]


def _tp_amb(ambiente: str) -> str:
    amb = str(ambiente or "homologacao").strip().lower()
    return "1" if amb == "producao" else "2"


def avaliar_aplicabilidade_esocial(
    admissao: Dict[str, Any],
    eventos_existentes: Optional[List[Dict[str, Any]]] = None,
    cadastramento_completo_disponivel: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Determina tecnicamente qual evento admissional é aplicável (S-2190, S-2200 ou sequenciamento)
    e impede geração indiscriminada duplicada.
    """
    existentes = eventos_existentes or []
    s2190_ativos = [e for e in existentes if e.get("tipo_evento") == "S-2190" and e.get("status") not in ("rejeitado", "excluido")]
    s2200_ativos = [e for e in existentes if e.get("tipo_evento") == "S-2200" and e.get("status") not in ("rejeitado", "excluido")]

    status_adm = str(admissao.get("status") or "").lower()
    if cadastramento_completo_disponivel is None:
        tem_compl = bool(
            admissao.get("colaborador_id")
            or status_adm in ("aprovado", "aprovada", "efetivado", "aguardando_aprovacao")
        )
        tem_dados_s2200 = bool(
            admissao.get("candidato_nome")
            and admissao.get("candidato_cpf")
            and admissao.get("candidato_data_nascimento")
            and admissao.get("cargo")
            and admissao.get("salario_proposto")
            and admissao.get("data_prevista_admissao")
            and admissao.get("escala_id")
        )
        cadastramento_completo_disponivel = tem_compl and tem_dados_s2200

    if s2200_ativos:
        return {
            "evento_recomendado": "S-2200",
            "ja_possui_evento_ativo": True,
            "permite_preliminar_s2190": False,
            "permite_completo_s2200": False,
            "motivo": "Já existe evento S-2200 ativo para esta admissão; utilize reprocessamento apenas em caso de rejeição.",
        }

    if cadastramento_completo_disponivel:
        return {
            "evento_recomendado": "S-2200",
            "ja_possui_evento_ativo": False,
            "permite_preliminar_s2190": False,
            "permite_completo_s2200": True,
            "sequenciado_de_s2190": len(s2190_ativos) > 0,
            "motivo": (
                "Cadastramento completo disponível: gerar S-2200 em substituição/complementação ao S-2190 preliminar."
                if s2190_ativos
                else "Dados completos disponíveis para vínculo definitivo: gerar diretamente S-2200 (dispensa S-2190)."
            ),
        }

    if s2190_ativos:
        return {
            "evento_recomendado": "S-2200",
            "ja_possui_evento_ativo": True,
            "permite_preliminar_s2190": False,
            "permite_completo_s2200": False,
            "motivo": "S-2190 preliminar já gerado; conclua os dados admissionais completos (RF-013/RF-016/RF-017) para gerar o S-2200.",
        }

    return {
        "evento_recomendado": "S-2190",
        "ja_possui_evento_ativo": False,
        "permite_preliminar_s2190": True,
        "permite_completo_s2200": False,
        "motivo": "Admissão preliminar antes do envio integral das informações de vínculo: aplicável S-2190 (Admissão Preliminar).",
    }


def gerar_xml_s2190(
    admissao: Dict[str, Any],
    empresa: Dict[str, Any],
    ambiente: str = "homologacao",
    matricula_preliminar: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Gera XML do evento S-2190 no padrão eSocial v_S_01_02_00."""
    erros: List[str] = []
    cpf = _limpar_digitos(admissao.get("candidato_cpf"))
    if len(cpf) != 11:
        erros.append("CPF do trabalhador inválido para S-2190.")
    dt_nasc = str(admissao.get("candidato_data_nascimento") or "").strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", dt_nasc):
        erros.append("Data de nascimento (dtNascto) obrigatória no formato AAAA-MM-DD para S-2190.")
    dt_adm = str(admissao.get("data_prevista_admissao") or "").strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", dt_adm):
        erros.append("Data de admissão (dtAdm) obrigatória no formato AAAA-MM-DD para S-2190.")
    cnpj = _limpar_digitos((empresa or {}).get("cnpj"))
    if len(cnpj) < 8:
        erros.append("CNPJ do empregador inválido para ideEmpregador.")
    salario = float(admissao.get("salario_proposto") or 0.0)
    if salario <= 0:
        erros.append("Salário contratual (vrSalFx) deve ser maior que zero.")
    matricula = (matricula_preliminar or admissao.get("codigo_processo") or f"PRELIM-{admissao.get('id', '1')}").strip()
    if erros:
        return "", erros

    evt_id = _gerar_id_evento(cnpj)
    nr_insc = cnpj[:8]
    tipo_ctr_str = str(admissao.get("tipo_contrato") or "experiencia").strip().lower()
    cod_categ = MAPA_CATEGORIA_ESOCIAL.get(tipo_ctr_str, "101")
    tp_contr = "2" if tipo_ctr_str in ("experiencia", "temporario") else "1"
    cbo = escape(str(admissao.get("cbo_codigo") or "411010"))

    dt_term_xml = ""
    if tp_contr == "2":
        prazo = int(admissao.get("prazo_experiencia_dias") or 45)
        try:
            from datetime import timedelta
            dt_t = (datetime.strptime(dt_adm, "%Y-%m-%d") + timedelta(days=max(1, prazo) - 1)).strftime("%Y-%m-%d")
            dt_term_xml = f"<dtTerm>{dt_t}</dtTerm>"
        except Exception:
            dt_term_xml = ""

    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<eSocial xmlns="{NS_S2190}">'
        f'<evtAdmPrelim Id="{escape(evt_id)}">'
        f'<ideEvento>'
        f'<indRetif>1</indRetif>'
        f'<tpAmb>{_tp_amb(ambiente)}</tpAmb>'
        f'<procEmi>1</procEmi>'
        f'<verProc>RH2.0-ENTERPRISE</verProc>'
        f'</ideEvento>'
        f'<ideEmpregador>'
        f'<tpInsc>1</tpInsc>'
        f'<nrInsc>{escape(nr_insc)}</nrInsc>'
        f'</ideEmpregador>'
        f'<infoRegPrelim>'
        f'<cpfTrab>{escape(cpf)}</cpfTrab>'
        f'<dtNascto>{escape(dt_nasc)}</dtNascto>'
        f'<dtAdm>{escape(dt_adm)}</dtAdm>'
        f'<matricula>{escape(matricula)}</matricula>'
        f'<codCateg>{cod_categ}</codCateg>'
        f'<natAtividade>1</natAtividade>'
        f'<infoRegCTPS>'
        f'<CBOCargo>{cbo}</CBOCargo>'
        f'<vrSalFx>{salario:.2f}</vrSalFx>'
        f'<undSalFixo>5</undSalFixo>'
        f'<tpContr>{tp_contr}</tpContr>'
        f'{dt_term_xml}'
        f'</infoRegCTPS>'
        f'</infoRegPrelim>'
        f'</evtAdmPrelim>'
        f'</eSocial>'
    )
    return xml, []


def gerar_xml_s2200(
    admissao: Dict[str, Any],
    empresa: Dict[str, Any],
    matricula: str,
    filial: Optional[Dict[str, Any]] = None,
    escala: Optional[Dict[str, Any]] = None,
    ambiente: str = "homologacao",
) -> Tuple[str, List[str]]:
    """Gera XML do evento S-2200 (Cadastramento Inicial do Vínculo) no padrão eSocial v_S_01_02_00."""
    erros: List[str] = []
    cpf = _limpar_digitos(admissao.get("candidato_cpf"))
    if len(cpf) != 11:
        erros.append("CPF do trabalhador inválido para S-2200.")
    nome = str(admissao.get("candidato_nome") or "").strip()
    if len(nome) < 3:
        erros.append("Nome do trabalhador (nmTrab) inválido.")
    dt_nasc = str(admissao.get("candidato_data_nascimento") or "").strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", dt_nasc):
        erros.append("Data de nascimento (dtNascto) obrigatória no formato AAAA-MM-DD para S-2200.")
    dt_adm = str(admissao.get("data_prevista_admissao") or "").strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", dt_adm):
        erros.append("Data de admissão (dtAdm) obrigatória no formato AAAA-MM-DD para S-2200.")
    cargo = str(admissao.get("cargo") or "").strip()
    if not cargo:
        erros.append("Cargo (nmCargo) é obrigatório para S-2200.")
    salario = float(admissao.get("salario_proposto") or 0.0)
    if salario <= 0:
        erros.append("Salário contratual (vrSalFx) deve ser positivo.")
    if not matricula or not str(matricula).strip():
        erros.append("Matrícula do vínculo é obrigatória para S-2200.")
    cnpj = _limpar_digitos((empresa or {}).get("cnpj"))
    if len(cnpj) < 8:
        erros.append("CNPJ do empregador inválido para S-2200.")
    if erros:
        return "", erros

    evt_id = _gerar_id_evento(cnpj)
    nr_insc = cnpj[:8]
    nr_insc_estab = _limpar_digitos((filial or {}).get("cnpj") or cnpj).ljust(14, "0")[:14]
    tipo_ctr_str = str(admissao.get("tipo_contrato") or "experiencia").strip().lower()
    cod_categ = MAPA_CATEGORIA_ESOCIAL.get(tipo_ctr_str, "101")
    tp_contr = "2" if tipo_ctr_str in ("experiencia", "temporario") else "1"
    cbo = escape(str(admissao.get("cbo_codigo") or "411010"))
    qtd_hrs_sem = int(round(float((escala or {}).get("carga_semanal_horas") or 44)))
    email = escape(str(admissao.get("candidato_email") or ""))
    est_civ = str(admissao.get("candidato_estado_civil") or "").lower()
    cod_est_civ = "2" if "casad" in est_civ else ("3" if "divor" in est_civ else ("4" if "viuv" in est_civ else "1"))

    duracao_inner = f"<tpContr>{tp_contr}</tpContr>"
    if tp_contr == "2":
        prazo = int(admissao.get("prazo_experiencia_dias") or 45)
        try:
            from datetime import timedelta
            dt_t = (datetime.strptime(dt_adm, "%Y-%m-%d") + timedelta(days=max(1, prazo) - 1)).strftime("%Y-%m-%d")
            duracao_inner += f"<dtTerm>{dt_t}</dtTerm>"
        except Exception:
            pass

    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<eSocial xmlns="{NS_S2200}">'
        f'<evtAdmissao Id="{escape(evt_id)}">'
        f'<ideEvento>'
        f'<indRetif>1</indRetif>'
        f'<tpAmb>{_tp_amb(ambiente)}</tpAmb>'
        f'<procEmi>1</procEmi>'
        f'<verProc>RH2.0-ENTERPRISE</verProc>'
        f'</ideEvento>'
        f'<ideEmpregador>'
        f'<tpInsc>1</tpInsc>'
        f'<nrInsc>{escape(nr_insc)}</nrInsc>'
        f'</ideEmpregador>'
        f'<trabalhador>'
        f'<cpfTrab>{escape(cpf)}</cpfTrab>'
        f'<nmTrab>{escape(nome[:70])}</nmTrab>'
        f'<sexo>{escape(str(admissao.get("sexo") or "M")[:1].upper())}</sexo>'
        f'<racaCor>6</racaCor>'
        f'<estCiv>{cod_est_civ}</estCiv>'
        f'<grauInstr>07</grauInstr>'
        f'<nascimento><dtNascto>{escape(dt_nasc)}</dtNascto><paisNascto>105</paisNascto><paisNac>105</paisNac></nascimento>'
        f'<contato><emailPrinc>{email}</emailPrinc></contato>'
        f'</trabalhador>'
        f'<vinculo>'
        f'<matricula>{escape(str(matricula).strip())}</matricula>'
        f'<tpRegTrab>1</tpRegTrab>'
        f'<tpRegPrev>1</tpRegPrev>'
        f'<cadIni>N</cadIni>'
        f'<infoRegimeTrab>'
        f'<infoCeletista>'
        f'<dtAdm>{escape(dt_adm)}</dtAdm>'
        f'<tpAdmissao>1</tpAdmissao>'
        f'<indAdmissao>1</indAdmissao>'
        f'<tpRegJor>1</tpRegJor>'
        f'<natAtividade>1</natAtividade>'
        f'<cnpjSindCategProf>{escape(nr_insc_estab)}</cnpjSindCategProf>'
        f'</infoCeletista>'
        f'</infoRegimeTrab>'
        f'<infoContrato>'
        f'<nmCargo>{escape(cargo[:100])}</nmCargo>'
        f'<CBOCargo>{cbo}</CBOCargo>'
        f'<codCateg>{cod_categ}</codCateg>'
        f'<remuneracao><vrSalFx>{salario:.2f}</vrSalFx><undSalFixo>5</undSalFixo></remuneracao>'
        f'<duracao>{duracao_inner}</duracao>'
        f'<localTrabalho><localTrabGeral><tpInsc>1</tpInsc><nrInsc>{escape(nr_insc_estab)}</nrInsc></localTrabGeral></localTrabalho>'
        f'<horContratual><qtdHrsSem>{qtd_hrs_sem}</qtdHrsSem><tpJornada>2</tpJornada><tmpParc>0</tmpParc><horNoturno>N</horNoturno><dscJorn>{escape(str(admissao.get("jornada_descricao") or "Jornada Padrão"))[:999]}</dscJorn></horContratual>'
        f'</infoContrato>'
        f'</vinculo>'
        f'</evtAdmissao>'
        f'</eSocial>'
    )
    return xml, []


def validar_xml_esocial(tipo_evento: str, xml_str: str) -> Tuple[bool, List[str]]:
    """
    Valida estrutura XML, namespace oficial eSocial v_S_01_02_00 e campos obrigatórios do evento.
    """
    erros: List[str] = []
    if not xml_str or not xml_str.strip():
        return False, ["Conteúdo XML vazio."]
    try:
        root = ET.fromstring(xml_str.strip())
    except ET.ParseError as e:
        return False, [f"XML malformado: {e}"]

    tipo = str(tipo_evento or "").upper().strip()
    ns_esperado = NS_S2190 if tipo == "S-2190" else (NS_S2200 if tipo == "S-2200" else "")
    if not ns_esperado:
        return False, [f"Tipo de evento não suportado para validação admissional: {tipo_evento}"]

    expected_root = f"{{{ns_esperado}}}eSocial"
    if root.tag != expected_root:
        erros.append(f"Namespace ou tag raiz inválida: esperado {expected_root}, obtido {root.tag}.")
        return False, erros

    def _find_txt(node: ET.Element, path_tags: List[str]) -> Optional[str]:
        cur_node = node
        for tag in path_tags:
            cur_node = cur_node.find(f"{{{ns_esperado}}}{tag}")
            if cur_node is None:
                return None
        return (cur_node.text or "").strip()

    evt_tag = "evtAdmPrelim" if tipo == "S-2190" else "evtAdmissao"
    evt_node = root.find(f"{{{ns_esperado}}}{evt_tag}")
    if evt_node is None or not evt_node.attrib.get("Id"):
        erros.append(f"Elemento {evt_tag} ausente ou sem atributo Id obrigatório.")
        return False, erros

    obrigatorios = (
        [
            ["ideEvento", "tpAmb"],
            ["ideEmpregador", "nrInsc"],
            ["infoRegPrelim", "cpfTrab"],
            ["infoRegPrelim", "dtNascto"],
            ["infoRegPrelim", "dtAdm"],
            ["infoRegPrelim", "matricula"],
            ["infoRegPrelim", "codCateg"],
            ["infoRegPrelim", "infoRegCTPS", "vrSalFx"],
        ]
        if tipo == "S-2190"
        else [
            ["ideEvento", "tpAmb"],
            ["ideEmpregador", "nrInsc"],
            ["trabalhador", "cpfTrab"],
            ["trabalhador", "nmTrab"],
            ["trabalhador", "nascimento", "dtNascto"],
            ["vinculo", "matricula"],
            ["vinculo", "infoRegimeTrab", "infoCeletista", "dtAdm"],
            ["vinculo", "infoContrato", "nmCargo"],
            ["vinculo", "infoContrato", "remuneracao", "vrSalFx"],
            ["vinculo", "infoContrato", "horContratual", "qtdHrsSem"],
        ]
    )
    for caminho in obrigatorios:
        val = _find_txt(evt_node, caminho)
        if not val:
            erros.append(f"Campo obrigatório ausente no XML {tipo}: {'/'.join(caminho)}.")

    cpf_val = _find_txt(evt_node, ["infoRegPrelim" if tipo == "S-2190" else "trabalhador", "cpfTrab"])
    if cpf_val and len(_limpar_digitos(cpf_val)) != 11:
        erros.append("cpfTrab deve conter 11 dígitos numéricos.")

    return len(erros) == 0, erros
