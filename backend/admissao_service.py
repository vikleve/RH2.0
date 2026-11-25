# -*- coding: utf-8 -*-
"""
Serviço Dedicado do Módulo 02 — Processo Admissional Enterprise (SRS Vol. 3 — RF-011 a RF-020)
Implementa:
- RF-011: Registro completo da admissão (sem defaults fictícios, multi-tenant, CPF e e-mail reais)
- RF-012: Checklist documental configurável, anexos privados SHA-256, rejeição/dispensa e histórico
- RF-013: Validação admissional formal (RN-008, RN-009, empresa/filial, centro de custo, checklist)
- RF-014: Geração real de Contrato Individual de Trabalho em PDF com versionamento e formalização
- RF-015: Integração eSocial S-2190 e S-2200 (v_S_01_02_00) com aplicabilidade e schema validation
- RF-016: Controle de Exame Admissional (ASO real em sst_asos) com sigilo médico
- RF-017: Cadastro de Jornada Inicial (escalas_jornada) com vigência e histórico
- RF-018: Definição de Centro de Custo ativo compatível com empresa/filial e integração contábil/folha
- RF-019: Definição e ativação de Benefícios elegíveis (beneficios_catalogo -> beneficios_colaborador)
- RF-020: Fluxo de Aprovação (RN-080, dupla aprovação opcional) e Efetivação Transacional Atômica
"""
import base64
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from .contrato_pdf import calcular_hash_contrato_dados, gerar_pdf_contrato_trabalho
from .database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, init_db, insert_returning_id, ph
from .esocial_admissao import (
    avaliar_aplicabilidade_esocial,
    gerar_xml_s2190,
    gerar_xml_s2200,
    validar_xml_esocial,
)
from .folha_calculos_2026 import SALARIO_MINIMO_2026, to_d
from .holerite_pdf import _mascarar_cpf
from .plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaRecursoNaoEncontradoException,
    PlataformaValidacaoException,
)
from .validators import (
    converter_para_data,
    normalizar_cpf,
    validar_arquivo_documento,
    validar_cpf,
    validar_data_nascimento,
    validar_email,
)

STATUS_PROCESSO_VALIDOS = {
    "rascunho",
    "em_andamento",
    "aguardando_documentos",
    "aguardando_validacao",
    "aguardando_aprovacao",
    "aprovado",
    "aprovada",
    "reprovado",
    "cancelado",
    "efetivado",
}

STATUS_CHECKLIST_VALIDOS = {
    "pendente",
    "enviado",
    "em_analise",
    "validado",
    "rejeitado",
    "dispensado",
}

STATUS_ASO_VALIDOS = {
    "pendente",
    "agendado",
    "realizado",
    "apto",
    "inapto",
    "pendente_analise",
}

PERFIS_SIGILO_MEDICO_LIBERADO = {
    "superadmin",
    "administrador",
    "admin_empresa",
    "medico_sst",
    "gestor_rh",
    "analista_dp",
}

ITENS_CHECKLIST_PADRAO = [
    ("RG_CNH", "Documento de Identidade com Foto (RG / CNH)", 1),
    ("CPF", "Cadastro de Pessoa Física (CPF)", 1),
    ("CTPS_DIGITAL", "Carteira de Trabalho Digital (CTPS)", 1),
    ("COMPROVANTE_RESIDENCIA", "Comprovante de Residência Atualizado", 1),
    ("COMPROVANTE_ESCOLARIDADE", "Comprovante de Escolaridade", 1),
    ("ASO_ADMISSIONAL", "Atestado de Saúde Ocupacional (ASO Admissional Apto)", 1),
    ("CERTIDAO_CIVIL", "Certidão de Nascimento ou Casamento", 0),
    ("DOCUMENTOS_DEPENDENTES", "Documentos dos Dependentes (IRRF / Salário-Família)", 0),
]


class AdmissaoService:
    def __init__(
        self,
        db_path: Optional[str] = None,
        auditoria_cb: Optional[Callable[..., None]] = None,
        calcular_beneficio_cb: Optional[Callable[..., Dict[str, Any]]] = None,
    ):
        self.db_path = db_path
        self._auditoria_cb = auditoria_cb
        self._calcular_beneficio_cb = calcular_beneficio_cb

    def _conn(self):
        return get_connection(self.db_path)

    def _pg(self) -> bool:
        return _usar_postgres(self.db_path)

    def _p(self) -> str:
        return ph(self.db_path)

    def _storage_dir(self, subpasta: str = "admissoes") -> str:
        if os.environ.get("PRIVATE_DOCS_DIR"):
            base = os.path.join(os.environ["PRIVATE_DOCS_DIR"], subpasta)
        elif os.environ.get("VERCEL"):
            base = os.path.join(tempfile.gettempdir(), "rh20_private_docs", subpasta)
        elif self.db_path and str(self.db_path) != ":memory:":
            base = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "rh20_private_docs", subpasta)
        else:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "private_docs", subpasta))
        os.makedirs(base, exist_ok=True)
        return base

    def _decodificar_base64(self, conteudo_base64: str) -> bytes:
        raw = (conteudo_base64 or "").strip()
        if not raw:
            return b""
        if "," in raw and raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            return base64.b64decode(raw, validate=True)
        except Exception:
            try:
                return base64.b64decode(raw, validate=False)
            except Exception:
                return b""

    def _registrar_auditoria(
        self,
        modulo: str,
        operacao: str,
        registro_tipo: str,
        registro_id: Any,
        usuario: str,
        campo_alterado: Optional[str] = None,
        valor_anterior: Optional[str] = None,
        valor_novo: Optional[str] = None,
        ip_origem: Optional[str] = None,
        detalhes: Optional[str] = None,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
    ):
        if self._auditoria_cb:
            self._auditoria_cb(
                modulo=modulo,
                operacao=operacao,
                registro_tipo=registro_tipo,
                registro_id=registro_id,
                usuario=usuario,
                campo_alterado=campo_alterado,
                valor_anterior=valor_anterior,
                valor_novo=valor_novo,
                ip_origem=ip_origem,
                detalhes=detalhes,
                empresa_id=empresa_id,
            )
            return
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                INSERT INTO auditoria_operacoes (
                    empresa_id, modulo, operacao, registro_tipo, registro_id,
                    campo_alterado, valor_anterior, valor_novo, usuario_responsavel,
                    ip_origem, detalhes, criado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p});
            """,
                (
                    empresa_id,
                    modulo,
                    operacao,
                    registro_tipo,
                    str(registro_id),
                    campo_alterado,
                    valor_anterior,
                    valor_novo,
                    usuario or "Sistema",
                    ip_origem,
                    detalhes,
                    agora,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _buscar_admissao_cursor(self, cur, admissao_id: int, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        p = self._p()
        sql = f"SELECT * FROM admissoes WHERE id = {p}"
        params: List[Any] = [int(admissao_id)]
        if empresa_id:
            sql += f" AND empresa_id = {p}"
            params.append(str(empresa_id).strip())
        cur.execute(sql + ";", tuple(params))
        adm = fetchone_dict(cur, self.db_path)
        if not adm:
            raise PlataformaRecursoNaoEncontradoException("Processo de admissão não encontrado para a empresa autorizada.")
        return adm

    def _validar_referencias_vinculo(
        self,
        cur,
        empresa_id: str,
        filial_id: Optional[str],
        escala_id: Optional[int],
        centro_custo_id: Optional[str],
    ) -> Dict[str, Any]:
        p = self._p()
        cur.execute(f"SELECT * FROM empresas WHERE id = {p} AND ativo = 1;", (empresa_id,))
        emp = fetchone_dict(cur, self.db_path)
        if not emp:
            raise PlataformaValidacaoException("Empresa informada inexistente ou inativa (RF-011/RF-013).")

        filial = None
        if filial_id:
            cur.execute(
                f"SELECT * FROM filiais WHERE id = {p} AND empresa_id = {p} AND ativo = 1;",
                (str(filial_id).strip(), empresa_id),
            )
            filial = fetchone_dict(cur, self.db_path)
            if not filial:
                raise PlataformaValidacaoException("Filial inválida, inativa ou pertencente a outra empresa (RF-011).")

        escala = None
        if escala_id is not None and str(escala_id).strip() != "":
            cur.execute(
                f"SELECT * FROM escalas_jornada WHERE id = {p} AND empresa_id = {p} AND ativo = 1;",
                (int(escala_id), empresa_id),
            )
            escala = fetchone_dict(cur, self.db_path)
            if not escala:
                raise PlataformaValidacaoException("Jornada/Escala selecionada não existe, está inativa ou pertence a outra empresa (RF-017).")

        cc = None
        if centro_custo_id and str(centro_custo_id).strip() != "":
            cur.execute(
                f"SELECT * FROM centros_custo WHERE (id = {p} OR UPPER(codigo) = UPPER({p})) AND empresa_id = {p} AND ativo = 1;",
                (str(centro_custo_id).strip(), str(centro_custo_id).strip(), empresa_id),
            )
            cc = fetchone_dict(cur, self.db_path)
            if not cc:
                raise PlataformaValidacaoException("Centro de custo inexistente, inativo ou incompatível com a empresa (RF-018).")

        return {"empresa": emp, "filial": filial, "escala": escala, "centro_custo": cc}

    def _sincronizar_status_processo(self, cur, admissao_id: int) -> str:
        """Recalcula o status operacional real da admissão sem sobrescrever estados deliberados/finais."""
        p = self._p()
        cur.execute(f"SELECT * FROM admissoes WHERE id = {p};", (admissao_id,))
        adm = fetchone_dict(cur, self.db_path)
        if not adm:
            return "em_andamento"
        st_atual = str(adm.get("status") or "em_andamento").lower()
        if st_atual in ("aprovado", "aprovada", "efetivado", "reprovado", "cancelado"):
            return st_atual

        cur.execute(f"SELECT obrigatorio, status FROM checklist_admissional WHERE admissao_id = {p};", (admissao_id,))
        itens = fetchall_dict(cur, self.db_path)
        tem_rej_ou_pend = any(i["obrigatorio"] and i["status"] not in ("validado", "dispensado") for i in itens)

        cur.execute(
            f"SELECT resultado, status_exame, data_validade FROM sst_asos WHERE admissao_id = {p} ORDER BY id DESC LIMIT 1;",
            (admissao_id,),
        )
        aso = fetchone_dict(cur, self.db_path)
        hoje = date.today().strftime("%Y-%m-%d")
        aso_ok = bool(
            aso
            and str(aso.get("resultado") or "").lower() == "apto"
            and str(aso.get("status_exame") or "realizado").lower() in ("realizado", "apto")
            and str(aso.get("data_validade") or "") >= hoje
        )

        if tem_rej_ou_pend or not aso_ok:
            novo_st = "aguardando_documentos" if any(i["status"] in ("pendente", "rejeitado") for i in itens if i["obrigatorio"]) else "em_andamento"
        else:
            cur.execute(
                f"SELECT apto_efetivacao FROM admissao_validacoes WHERE admissao_id = {p} ORDER BY id DESC LIMIT 1;",
                (admissao_id,),
            )
            val_row = fetchone_dict(cur, self.db_path)
            if val_row and int(val_row.get("apto_efetivacao") or 0) == 1:
                novo_st = "aguardando_aprovacao"
            else:
                novo_st = "aguardando_validacao"

        if st_atual == "rascunho" and novo_st == "aguardando_documentos":
            return "rascunho"
        if novo_st != st_atual:
            cur.execute(
                f"UPDATE admissoes SET status = {p}, atualizado_em = {p} WHERE id = {p};",
                (novo_st, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), admissao_id),
            )
        return novo_st

    # ─────────────────────────────────────────────────────────────────────────
    # RF-011: Registro e Gestão do Processo Admissional
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_admissao(self, dados: Dict[str, Any], usuario: str) -> Dict[str, Any]:
        """RF-011 / RF-013: Abre processo admissional sem valores fictícios ou e-mails inventados."""
        dados = dict(dados or {})
        if not dados.get("candidato_nome") and dados.get("nome_candidato"):
            dados["candidato_nome"] = dados["nome_candidato"]
        if not dados.get("candidato_cpf") and dados.get("cpf"):
            dados["candidato_cpf"] = dados["cpf"]
        if not dados.get("candidato_email") and dados.get("email"):
            dados["candidato_email"] = dados["email"]
        if not dados.get("cargo") and dados.get("cargo_proposto"):
            dados["cargo"] = dados["cargo_proposto"]
        if not dados.get("data_prevista_admissao") and dados.get("data_admissao_prevista"):
            dados["data_prevista_admissao"] = dados["data_admissao_prevista"]
        if not dados.get("candidato_data_nascimento") and dados.get("data_nascimento"):
            dados["candidato_data_nascimento"] = dados["data_nascimento"]
        if not dados.get("candidato_telefone") and dados.get("telefone"):
            dados["candidato_telefone"] = dados["telefone"]
        if not dados.get("candidato_endereco") and dados.get("endereco"):
            dados["candidato_endereco"] = dados["endereco"]

        obrigatorios = [
            ("candidato_nome", "Nome completo do candidato"),
            ("candidato_cpf", "CPF do candidato"),
            ("candidato_email", "E-mail do candidato"),
            ("cargo", "Cargo"),
            ("setor", "Setor"),
            ("salario_proposto", "Salário contratual"),
            ("data_prevista_admissao", "Data prevista de admissão"),
        ]
        for campo, rotulo in obrigatorios:
            if not dados.get(campo) or str(dados.get(campo)).strip() == "":
                raise PlataformaValidacaoException(
                    f"O campo obrigatório '{rotulo}' ({campo}) deve ser informado sem valores fictícios (RF-011)."
                )

        salario = to_d(dados.get("salario_proposto"))
        if salario < SALARIO_MINIMO_2026:
            raise PlataformaValidacaoException(
                f"Salário proposto (R$ {salario:.2f}) não pode ser inferior ao salário mínimo legal vigente de R$ {SALARIO_MINIMO_2026:.2f} (RN-008, RF-013)."
            )

        cpf_limpo = normalizar_cpf(str(dados["candidato_cpf"]))
        if len(cpf_limpo) != 11 or not validar_cpf(cpf_limpo):
            raise PlataformaValidacaoException("CPF do candidato inválido (RT-07 / RF-011).")

        email_cand = str(dados["candidato_email"]).strip()
        if not validar_email(email_cand):
            raise PlataformaValidacaoException("E-mail do candidato inválido (RF-011).")

        dt_adm_obj = converter_para_data(str(dados["data_prevista_admissao"]).strip())
        if not dt_adm_obj:
            raise PlataformaValidacaoException("Data prevista de admissão inválida. Use AAAA-MM-DD (RF-011).")
        dt_adm_str = dt_adm_obj.strftime("%Y-%m-%d")

        dt_nasc_str = None
        if dados.get("candidato_data_nascimento"):
            ok_nasc, msg_nasc = validar_data_nascimento(str(dados["candidato_data_nascimento"]))
            if not ok_nasc:
                raise PlataformaValidacaoException(msg_nasc)
            dt_nasc_obj = converter_para_data(str(dados["candidato_data_nascimento"]))
            dt_nasc_str = dt_nasc_obj.strftime("%Y-%m-%d")
            idade_adm = dt_adm_obj.year - dt_nasc_obj.year - ((dt_adm_obj.month, dt_adm_obj.day) < (dt_nasc_obj.month, dt_nasc_obj.day))
            if idade_adm < 14:
                raise PlataformaValidacaoException("Data de admissão incompatível com a idade mínima legal (14 anos).")

        empresa_id = str(dados.get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()
        filial_id = str(dados.get("filial_id") or "b0000000-0000-0000-0000-000000000001").strip()
        escala_id = int(dados["escala_id"]) if dados.get("escala_id") not in (None, "") else None
        cc_id = str(dados["centro_custo_id"]).strip() if dados.get("centro_custo_id") not in (None, "") else None

        status_inicial = str(dados.get("status") or "em_andamento").strip().lower()
        if status_inicial not in ("rascunho", "em_andamento"):
            status_inicial = "em_andamento"

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()

            refs = self._validar_referencias_vinculo(cur, empresa_id, filial_id, escala_id, cc_id)
            escala = refs["escala"]
            cc = refs["centro_custo"]

            # Impedir processo admissional duplicado em aberto ou colaborador já ativo com mesmo CPF na empresa
            cur.execute(
                f"""
                SELECT id, status FROM admissoes
                WHERE empresa_id = {p} AND candidato_cpf = {p}
                  AND status NOT IN ('cancelado', 'reprovado', 'efetivado', 'aprovada');
            """,
                (empresa_id, cpf_limpo),
            )
            dup = fetchone_dict(cur, self.db_path)
            if dup:
                raise PlataformaValidacaoException(
                    f"Já existe um processo admissional ativo (#{dup['id']} - {dup['status']}) para este CPF nesta empresa."
                )

            cpf_fmt = f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:11]}"
            cur.execute(
                f"""
                SELECT id, matricula FROM colaboradores
                WHERE (cpf = {p} OR cpf = {p}) AND COALESCE(situacao, 'ativo') = 'ativo'
                  AND COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p};
            """,
                (cpf_limpo, cpf_fmt, empresa_id),
            )
            colab_ativo = fetchone_dict(cur, self.db_path)
            if colab_ativo:
                raise PlataformaValidacaoException(
                    f"CPF já vinculado a colaborador ativo (Matrícula {colab_ativo['matricula']}) nesta empresa."
                )

            j_desc = escala["descricao"] if escala else (dados.get("jornada_descricao") or None)
            j_ent = escala["entrada_padrao"] if escala else dados.get("jornada_entrada")
            j_sai = escala["saida_padrao"] if escala else dados.get("jornada_saida")
            j_int = int(escala["intervalo_minutos"]) if escala else int(dados.get("jornada_intervalo_min") or 60)
            j_dias = escala["tipo_regime"] if escala else dados.get("jornada_dias_semana")
            j_carga = float(escala["divisor_mensal"]) if escala else float(dados.get("jornada_carga_mensal") or 220.0)
            j_vig = dados.get("jornada_vigencia_inicio") or (dt_adm_str if escala else None)
            cc_id_final = cc["id"] if cc else None
            cc_vig = dados.get("centro_custo_vigencia") or (dt_adm_str if cc else None)

            sql_pg = f"""
                INSERT INTO admissoes (
                    empresa_id, filial_id, candidato_nome, candidato_cpf, candidato_email,
                    candidato_data_nascimento, candidato_telefone, candidato_endereco, candidato_estado_civil,
                    candidato_rg, candidato_pis, cargo, setor, salario_proposto, tipo_contrato,
                    prazo_experiencia_dias, prorrogacao_experiencia_dias, data_prevista_admissao,
                    escala_id, jornada_descricao, jornada_entrada, jornada_saida, jornada_intervalo_min,
                    jornada_dias_semana, jornada_carga_mensal, jornada_vigencia_inicio,
                    centro_custo_id, centro_custo_vigencia, gestor_responsavel, local_trabalho,
                    status, aso_admissional_status, contrato_gerado, dupla_aprovacao_exigida,
                    criado_por, criado_em, atualizado_em
                ) VALUES ({','.join([p]*30)}, {p}, 'pendente', 0, {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO admissoes (
                    empresa_id, filial_id, candidato_nome, candidato_cpf, candidato_email,
                    candidato_data_nascimento, candidato_telefone, candidato_endereco, candidato_estado_civil,
                    candidato_rg, candidato_pis, cargo, setor, salario_proposto, tipo_contrato,
                    prazo_experiencia_dias, prorrogacao_experiencia_dias, data_prevista_admissao,
                    escala_id, jornada_descricao, jornada_entrada, jornada_saida, jornada_intervalo_min,
                    jornada_dias_semana, jornada_carga_mensal, jornada_vigencia_inicio,
                    centro_custo_id, centro_custo_vigencia, gestor_responsavel, local_trabalho,
                    status, aso_admissional_status, contrato_gerado, dupla_aprovacao_exigida,
                    criado_por, criado_em, atualizado_em
                ) VALUES ({','.join([p]*30)}, {p}, 'pendente', 0, {p}, {p}, {p}, {p});
            """
            params = (
                empresa_id,
                filial_id,
                str(dados["candidato_nome"]).strip(),
                cpf_limpo,
                email_cand,
                dt_nasc_str,
                (dados.get("candidato_telefone") or "").strip() or None,
                (dados.get("candidato_endereco") or "").strip() or None,
                (dados.get("candidato_estado_civil") or "").strip() or None,
                (dados.get("candidato_rg") or "").strip() or None,
                (dados.get("candidato_pis") or "").strip() or None,
                str(dados["cargo"]).strip(),
                str(dados["setor"]).strip(),
                float(salario),
                str(dados.get("tipo_contrato") or "experiencia").strip().lower(),
                int(dados.get("prazo_experiencia_dias", 45)),
                int(dados.get("prorrogacao_experiencia_dias", 45)),
                dt_adm_str,
                escala["id"] if escala else None,
                j_desc,
                j_ent,
                j_sai,
                j_int,
                j_dias,
                j_carga,
                j_vig,
                cc_id_final,
                cc_vig,
                (dados.get("gestor_responsavel") or "").strip() or None,
                (dados.get("local_trabalho") or "").strip() or None,
                status_inicial,
                1 if dados.get("dupla_aprovacao_exigida") in (1, True, "1", "true") else 0,
                usuario,
                agora,
                agora,
            )
            adm_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            cod_proc = f"ADM-{agora[:4]}-{adm_id:05d}"
            cur.execute(f"UPDATE admissoes SET codigo_processo = {p} WHERE id = {p};", (cod_proc, adm_id))

            # Histórico inicial de jornada e centro de custo caso já informados na abertura
            if escala:
                cur.execute(
                    f"""
                    INSERT INTO admissao_jornadas_historico (
                        empresa_id, admissao_id, escala_id, descricao, entrada, saida,
                        intervalo_min, dias_semana, carga_mensal, vigencia_inicio, definido_por, definido_em
                    ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p});
                """,
                    (empresa_id, adm_id, escala["id"], j_desc, j_ent, j_sai, j_int, j_dias, j_carga, j_vig, usuario, agora),
                )
            if cc:
                cur.execute(
                    f"""
                    INSERT INTO admissao_centros_custo_historico (
                        empresa_id, admissao_id, centro_custo_id, filial_id, vigencia_inicio, definido_por, definido_em
                    ) VALUES ({p},{p},{p},{p},{p},{p},{p});
                """,
                    (empresa_id, adm_id, cc["id"], filial_id, cc_vig, usuario, agora),
                )

            # Gera os 8 itens estruturados do checklist admissional (RF-012: 6 obrigatórios + 2 opcionais)
            for cod_doc, desc_doc, obrig in ITENS_CHECKLIST_PADRAO:
                cur.execute(
                    f"""
                    INSERT INTO checklist_admissional (
                        admissao_id, codigo_documento, item_descricao, obrigatorio, status, versao, atualizado_por, atualizado_em
                    ) VALUES ({p},{p},{p},{p},'pendente',1,{p},{p});
                """,
                    (adm_id, cod_doc, desc_doc, obrig, usuario, agora),
                )

            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="inclusao",
            registro_tipo="admissoes",
            registro_id=adm_id,
            usuario=usuario,
            detalhes=f"Processo {cod_proc} aberto para {dados['candidato_nome']} - Cargo: {dados['cargo']}",
            empresa_id=empresa_id,
        )
        return self.obter_admissao(adm_id, empresa_id=empresa_id)

    def atualizar_admissao(
        self,
        admissao_id: int,
        dados: Dict[str, Any],
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atualiza dados cadastrais ou contratuais de uma admissão antes da efetivação (RF-011 / RF-013)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            if str(adm["status"]).lower() in ("efetivado", "aprovada", "cancelado"):
                raise PlataformaValidacaoException("Não é possível editar um processo admissional já efetivado ou cancelado.")

            dados = dict(dados or {})
            novo_nome = str(dados.get("candidato_nome") if dados.get("candidato_nome") is not None else adm["candidato_nome"]).strip()
            novo_email = str(dados.get("candidato_email") if dados.get("candidato_email") is not None else adm["candidato_email"]).strip()
            if not validar_email(novo_email):
                raise PlataformaValidacaoException("E-mail do candidato inválido.")

            novo_cpf = adm["candidato_cpf"]
            if dados.get("candidato_cpf") is not None:
                cpf_limpo = normalizar_cpf(str(dados["candidato_cpf"]))
                if len(cpf_limpo) != 11 or not validar_cpf(cpf_limpo):
                    raise PlataformaValidacaoException("CPF do candidato inválido.")
                novo_cpf = cpf_limpo

            novo_sal = to_d(dados.get("salario_proposto") if dados.get("salario_proposto") is not None else adm["salario_proposto"])
            if novo_sal < SALARIO_MINIMO_2026:
                raise PlataformaValidacaoException(
                    f"Salário proposto (R$ {novo_sal:.2f}) inferior ao mínimo legal (R$ {SALARIO_MINIMO_2026:.2f})."
                )

            dt_adm_raw = dados.get("data_prevista_admissao") or adm["data_prevista_admissao"]
            dt_adm_obj = converter_para_data(str(dt_adm_raw))
            if not dt_adm_obj:
                raise PlataformaValidacaoException("Data prevista de admissão inválida.")
            dt_adm_str = dt_adm_obj.strftime("%Y-%m-%d")

            dt_nasc_raw = dados.get("candidato_data_nascimento") if dados.get("candidato_data_nascimento") is not None else adm.get("candidato_data_nascimento")
            dt_nasc_str = None
            if dt_nasc_raw:
                ok_n, msg_n = validar_data_nascimento(str(dt_nasc_raw))
                if not ok_n:
                    raise PlataformaValidacaoException(msg_n)
                dt_nasc_obj = converter_para_data(str(dt_nasc_raw))
                dt_nasc_str = dt_nasc_obj.strftime("%Y-%m-%d")

            nova_filial = str(dados.get("filial_id") if dados.get("filial_id") is not None else (adm.get("filial_id") or "")).strip() or None
            self._validar_referencias_vinculo(cur, adm["empresa_id"], nova_filial, None, None)

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"""
                UPDATE admissoes SET
                    filial_id={p}, candidato_nome={p}, candidato_cpf={p}, candidato_email={p},
                    candidato_data_nascimento={p}, candidato_telefone={p}, candidato_endereco={p},
                    candidato_estado_civil={p}, candidato_rg={p}, candidato_pis={p},
                    cargo={p}, setor={p}, salario_proposto={p}, tipo_contrato={p},
                    prazo_experiencia_dias={p}, prorrogacao_experiencia_dias={p},
                    data_prevista_admissao={p}, gestor_responsavel={p}, local_trabalho={p},
                    atualizado_em={p}
                WHERE id={p};
            """,
                (
                    nova_filial,
                    novo_nome,
                    novo_cpf,
                    novo_email,
                    dt_nasc_str,
                    dados.get("candidato_telefone") if dados.get("candidato_telefone") is not None else adm.get("candidato_telefone"),
                    dados.get("candidato_endereco") if dados.get("candidato_endereco") is not None else adm.get("candidato_endereco"),
                    dados.get("candidato_estado_civil") if dados.get("candidato_estado_civil") is not None else adm.get("candidato_estado_civil"),
                    dados.get("candidato_rg") if dados.get("candidato_rg") is not None else adm.get("candidato_rg"),
                    dados.get("candidato_pis") if dados.get("candidato_pis") is not None else adm.get("candidato_pis"),
                    str(dados.get("cargo") if dados.get("cargo") is not None else adm["cargo"]).strip(),
                    str(dados.get("setor") if dados.get("setor") is not None else adm["setor"]).strip(),
                    float(novo_sal),
                    str(dados.get("tipo_contrato") if dados.get("tipo_contrato") is not None else adm["tipo_contrato"]).strip().lower(),
                    int(dados.get("prazo_experiencia_dias") if dados.get("prazo_experiencia_dias") is not None else (adm.get("prazo_experiencia_dias") or 45)),
                    int(dados.get("prorrogacao_experiencia_dias") if dados.get("prorrogacao_experiencia_dias") is not None else (adm.get("prorrogacao_experiencia_dias") or 45)),
                    dt_adm_str,
                    dados.get("gestor_responsavel") if dados.get("gestor_responsavel") is not None else adm.get("gestor_responsavel"),
                    dados.get("local_trabalho") if dados.get("local_trabalho") is not None else adm.get("local_trabalho"),
                    agora,
                    admissao_id,
                ),
            )
            self._sincronizar_status_processo(cur, admissao_id)
            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="alteracao",
            registro_tipo="admissoes",
            registro_id=admissao_id,
            usuario=usuario,
            detalhes=f"Dados do processo admissional #{admissao_id} atualizados.",
            empresa_id=adm["empresa_id"],
        )
        return self.obter_admissao(admissao_id, empresa_id=empresa_id)

    def cancelar_admissao(
        self,
        admissao_id: int,
        motivo: str,
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not motivo or not str(motivo).strip():
            raise PlataformaValidacaoException("Informe o motivo do cancelamento do processo admissional.")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            if str(adm["status"]).lower() in ("efetivado", "aprovada"):
                raise PlataformaValidacaoException("Admissão já efetivada não pode ser cancelada; utilize o módulo de rescisão.")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"""
                UPDATE admissoes
                SET status = 'cancelado', cancelado_por = {p}, cancelado_em = {p}, motivo_cancelamento = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (usuario, agora, str(motivo).strip(), agora, admissao_id),
            )
            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="cancelamento",
            registro_tipo="admissoes",
            registro_id=admissao_id,
            usuario=usuario,
            valor_anterior=adm["status"],
            valor_novo="cancelado",
            detalhes=f"Admissão #{admissao_id} cancelada: {motivo}",
            empresa_id=adm["empresa_id"],
        )
        return self.obter_admissao(admissao_id, empresa_id=empresa_id)

    def obter_admissao(
        self,
        admissao_id: int,
        empresa_id: Optional[str] = None,
        perfil_usuario: str = "gestor_rh",
    ) -> Dict[str, Any]:
        """Obtém o dossiê completo da admissão (checklist, ASO, contratos, jornada, CC, benefícios e eSocial)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            adm["candidato_cpf_mascarado"] = _mascarar_cpf(adm["candidato_cpf"])

            cur.execute(f"SELECT * FROM checklist_admissional WHERE admissao_id = {p} ORDER BY id ASC;", (admissao_id,))
            adm["checklist"] = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"SELECT * FROM checklist_admissional_historico WHERE admissao_id = {p} ORDER BY id DESC;",
                (admissao_id,),
            )
            adm["checklist_historico"] = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"SELECT * FROM admissao_validacoes WHERE admissao_id = {p} ORDER BY id DESC LIMIT 5;",
                (admissao_id,),
            )
            adm["validacoes"] = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"""
                SELECT ac.*, m.codigo AS modelo_codigo, m.nome AS modelo_nome
                FROM admissao_contratos ac
                LEFT JOIN admissao_contratos_modelos m ON m.id = ac.modelo_id
                WHERE ac.admissao_id = {p}
                ORDER BY ac.versao DESC, ac.id DESC;
            """,
                (admissao_id,),
            )
            adm["contratos"] = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"SELECT * FROM sst_asos WHERE admissao_id = {p} ORDER BY id DESC LIMIT 1;",
                (admissao_id,),
            )
            aso_row = fetchone_dict(cur, self.db_path)
            adm["aso"] = self._filtrar_aso_sigilo(aso_row, perfil_usuario) if aso_row else None

            cur.execute(
                f"""
                SELECT ab.*, bc.codigo AS beneficio_codigo, bc.nome AS beneficio_nome, bc.tipo AS beneficio_tipo
                FROM admissao_beneficios ab
                JOIN beneficios_catalogo bc ON bc.id = ab.beneficio_id
                WHERE ab.admissao_id = {p}
                ORDER BY ab.id ASC;
            """,
                (admissao_id,),
            )
            adm["beneficios"] = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"""
                SELECT * FROM esocial_eventos
                WHERE empresa_id = {p} AND (
                    identificador_origem = {p}
                    OR identificador_origem = {p}
                )
                ORDER BY id DESC;
            """,
                (
                    adm["empresa_id"],
                    f"ADM:{admissao_id}",
                    str(adm.get("colaborador_id") or "__NONE__"),
                ),
            )
            adm["esocial_eventos"] = fetchall_dict(cur, self.db_path)
            return adm
        finally:
            conn.close()

    def listar_admissoes(
        self,
        status: Optional[str] = None,
        empresa_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lista processos admissionais com isolamento multi-empresa e CPF mascarado para listagem."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            query = "SELECT * FROM admissoes WHERE 1=1"
            params: List[Any] = []
            if empresa_id:
                query += f" AND empresa_id = {p}"
                params.append(str(empresa_id).strip())
            if status:
                query += f" AND status = {p}"
                params.append(status.strip().lower())
            query += " ORDER BY id DESC"
            cur.execute(query, tuple(params))
            admissoes = fetchall_dict(cur, self.db_path)
            for a in admissoes:
                a["candidato_cpf_mascarado"] = _mascarar_cpf(a.get("candidato_cpf") or "")
                cur.execute(
                    f"""
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN status IN ('validado', 'dispensado') THEN 1 ELSE 0 END) as validados,
                           SUM(CASE WHEN obrigatorio = 1 THEN 1 ELSE 0 END) as obrigatorios
                    FROM checklist_admissional WHERE admissao_id = {p};
                """,
                    (a["id"],),
                )
                row = fetchone_dict(cur, self.db_path)
                if row:
                    tot = int(row.get("total") or 0)
                    val = int(row.get("validados") or 0)
                    a["checklist_resumo"] = f"{val}/{tot} validados"
                    a["total_documentos"] = tot
                    a["documentos_aprovados"] = val
            return admissoes
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-012: Checklist Admissional Configurável, Upload Seguro & Histórico
    # ─────────────────────────────────────────────────────────────────────────
    def configurar_item_checklist(
        self,
        admissao_id: int,
        dados: Dict[str, Any],
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Adiciona item customizado ou altera obrigatoriedade (obrigatório vs opcional) no checklist."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            item_id = (dados or {}).get("item_id")
            if item_id:
                cur.execute(
                    f"SELECT * FROM checklist_admissional WHERE id = {p} AND admissao_id = {p};",
                    (int(item_id), admissao_id),
                )
                it = fetchone_dict(cur, self.db_path)
                if not it:
                    raise PlataformaRecursoNaoEncontradoException("Item do checklist não encontrado.")
                obrig = 1 if dados.get("obrigatorio", 1) in (1, True, "1", "true") else 0
                cur.execute(
                    f"UPDATE checklist_admissional SET obrigatorio = {p}, atualizado_por = {p}, atualizado_em = {p} WHERE id = {p};",
                    (obrig, usuario, agora, int(item_id)),
                )
                self._sincronizar_status_processo(cur, admissao_id)
                conn.commit()
                return {"sucesso": True, "item_id": int(item_id), "obrigatorio": obrig}

            desc = str((dados or {}).get("item_descricao") or "").strip()
            if not desc:
                raise PlataformaValidacaoException("Descrição do item do checklist é obrigatória.")
            cod = str((dados or {}).get("codigo_documento") or re.sub(r"[^A-Z0-9]+", "_", desc.upper()).strip("_")[:30])
            obrig = 1 if (dados or {}).get("obrigatorio", 1) in (1, True, "1", "true") else 0
            sql_pg = f"""
                INSERT INTO checklist_admissional (
                    admissao_id, codigo_documento, item_descricao, obrigatorio, status, versao, atualizado_por, atualizado_em
                ) VALUES ({p},{p},{p},{p},'pendente',1,{p},{p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO checklist_admissional (
                    admissao_id, codigo_documento, item_descricao, obrigatorio, status, versao, atualizado_por, atualizado_em
                ) VALUES ({p},{p},{p},{p},'pendente',1,{p},{p});
            """
            novo_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, (admissao_id, cod, desc, obrig, usuario, agora), self.db_path)
            cur.execute(
                f"""
                INSERT INTO checklist_admissional_historico (
                    empresa_id, admissao_id, checklist_id, versao, acao, status_anterior, status_novo, usuario, criado_em
                ) VALUES ({p},{p},{p},1,'criacao_item',NULL,'pendente',{p},{p});
            """,
                (adm["empresa_id"], admissao_id, novo_id, usuario, agora),
            )
            self._sincronizar_status_processo(cur, admissao_id)
            conn.commit()
            return {"sucesso": True, "item_id": novo_id, "codigo_documento": cod, "obrigatorio": obrig}
        finally:
            conn.close()

    def upload_documento_checklist(
        self,
        admissao_id: int,
        item_id: int,
        nome_arquivo: str,
        conteudo_base64: str,
        mime_type: str = "application/octet-stream",
        usuario: str = "Operador",
        observacao: str = "",
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF-012: Anexa arquivo ao item do checklist em storage privado seguro com versionamento e SHA-256."""
        raw_bytes = self._decodificar_base64(conteudo_base64)
        if not raw_bytes:
            raise PlataformaValidacaoException("Conteúdo do documento ausente ou base64 inválido.")
        ok_arq, msg_arq, mime_validado = validar_arquivo_documento(nome_arquivo, mime_type, raw_bytes, tamanho_max_mb=10)
        if not ok_arq:
            raise PlataformaValidacaoException(msg_arq)

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            cur.execute(
                f"SELECT * FROM checklist_admissional WHERE id = {p} AND admissao_id = {p};",
                (int(item_id), admissao_id),
            )
            item = fetchone_dict(cur, self.db_path)
            if not item:
                raise PlataformaRecursoNaoEncontradoException("Item do checklist não encontrado para esta admissão.")

            _, ext = os.path.splitext(nome_arquivo.strip().lower())
            nome_interno = f"{uuid.uuid4().hex}{ext}"
            dir_dest = os.path.join(
                self._storage_dir("admissoes"),
                re.sub(r"[^a-zA-Z0-9_-]", "_", adm["empresa_id"]),
                str(admissao_id),
            )
            os.makedirs(dir_dest, exist_ok=True)
            caminho = os.path.join(dir_dest, nome_interno)
            with open(caminho, "wb") as f:
                f.write(raw_bytes)
            sha256 = hashlib.sha256(raw_bytes).hexdigest()

            nova_versao = int(item.get("versao") or 0) + 1 if item.get("nome_arquivo") else 1
            status_ant = str(item.get("status") or "pendente")
            # Nunca auto-valida um arquivo enviado (especialmente se previamente rejeitado)
            novo_status = "enviado"
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                f"""
                UPDATE checklist_admissional
                SET status = {p}, versao = {p}, nome_arquivo = {p}, caminho_privado = {p},
                    mime_type = {p}, tamanho_bytes = {p}, sha256_hash = {p},
                    motivo_rejeicao = NULL, atualizado_por = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (novo_status, nova_versao, nome_arquivo.strip(), caminho, mime_validado, len(raw_bytes), sha256, usuario, agora, item_id),
            )
            cur.execute(
                f"""
                INSERT INTO checklist_admissional_historico (
                    empresa_id, admissao_id, checklist_id, versao, acao, status_anterior, status_novo,
                    nome_arquivo, caminho_privado, sha256_hash, justificativa, usuario, criado_em
                ) VALUES ({p},{p},{p},{p},'upload',{p},{p},{p},{p},{p},{p},{p},{p});
            """,
                (adm["empresa_id"], admissao_id, item_id, nova_versao, status_ant, novo_status, nome_arquivo.strip(), caminho, sha256, observacao or "", usuario, agora),
            )
            self._sincronizar_status_processo(cur, admissao_id)
            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="upload_documento",
            registro_tipo="checklist_admissional",
            registro_id=item_id,
            usuario=usuario,
            valor_anterior=status_ant,
            valor_novo=f"{novo_status} (v{nova_versao})",
            detalhes=f"Documento '{nome_arquivo.strip()}' v{nova_versao} anexado ao item {item['item_descricao']}.",
            empresa_id=adm["empresa_id"],
        )
        return {
            "sucesso": True,
            "item_id": item_id,
            "versao": nova_versao,
            "status": novo_status,
            "nome_arquivo": nome_arquivo.strip(),
            "sha256_hash": sha256,
        }

    def atualizar_item_checklist(
        self,
        item_id: int,
        status: str,
        usuario: str,
        justificativa: Optional[str] = None,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF-012: Atualiza status do checklist (pendente/enviado/em_analise/validado/rejeitado/dispensado) com histórico."""
        st_norm = str(status or "").strip().lower()
        if st_norm in ("aprovado", "entregue"):
            st_norm = "validado"
        if st_norm not in STATUS_CHECKLIST_VALIDOS:
            raise PlataformaValidacaoException(f"Status inválido para item do checklist: '{status}'.")

        just = (justificativa or "").strip()
        if st_norm in ("rejeitado", "dispensado") and not just:
            raise PlataformaValidacaoException(
                f"Justificativa obrigatória ao marcar documento como '{st_norm}' (RF-012)."
            )

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM checklist_admissional WHERE id = {p};", (int(item_id),))
            item = fetchone_dict(cur, self.db_path)
            if not item:
                raise PlataformaRecursoNaoEncontradoException("Item do checklist não encontrado.")
            adm = self._buscar_admissao_cursor(cur, int(item["admissao_id"]), empresa_id=empresa_id)

            st_anterior = str(item.get("status") or "pendente").lower()
            # Regra explícita: um documento rejeitado não pode pular diretamente para validado sem novo envio ou justificativa de revisão
            if st_anterior == "rejeitado" and st_norm == "validado" and not just:
                raise PlataformaValidacaoException(
                    "Documento previamente rejeitado exige correção/re-envio ou justificativa formal de revisão."
                )

            mot_rej = just if st_norm == "rejeitado" else (None if st_norm == "validado" else item.get("motivo_rejeicao"))
            just_disp = just if st_norm == "dispensado" else item.get("justificativa_dispensa")
            val_por = usuario if st_norm in ("validado", "dispensado") else item.get("validado_por")
            val_em = agora if st_norm in ("validado", "dispensado") else item.get("validado_em")

            cur.execute(
                f"""
                UPDATE checklist_admissional
                SET status = {p}, motivo_rejeicao = {p}, justificativa_dispensa = {p},
                    validado_por = {p}, validado_em = {p}, atualizado_por = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (st_norm, mot_rej, just_disp, val_por, val_em, usuario, agora, int(item_id)),
            )
            cur.execute(
                f"""
                INSERT INTO checklist_admissional_historico (
                    empresa_id, admissao_id, checklist_id, versao, acao, status_anterior, status_novo,
                    nome_arquivo, sha256_hash, justificativa, usuario, criado_em
                ) VALUES ({p},{p},{p},{p},'atualizacao_status',{p},{p},{p},{p},{p},{p},{p});
            """,
                (
                    adm["empresa_id"],
                    adm["id"],
                    int(item_id),
                    int(item.get("versao") or 1),
                    st_anterior,
                    st_norm,
                    item.get("nome_arquivo"),
                    item.get("sha256_hash"),
                    just,
                    usuario,
                    agora,
                ),
            )
            self._sincronizar_status_processo(cur, int(adm["id"]))
            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="checklist_status",
            registro_tipo="checklist_admissional",
            registro_id=item_id,
            usuario=usuario,
            valor_anterior=st_anterior,
            valor_novo=st_norm,
            detalhes=f"Item '{item['item_descricao']}' atualizado de '{st_anterior}' para '{st_norm}'.",
            empresa_id=adm["empresa_id"],
        )
        return {"sucesso": True, "item_id": int(item_id), "status": st_norm, "mensagem": f"Item {item_id} atualizado para status '{st_norm}'."}

    def obter_documento_checklist_download(
        self,
        admissao_id: int,
        item_id: int,
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            cur.execute(
                f"SELECT * FROM checklist_admissional WHERE id = {p} AND admissao_id = {p};",
                (int(item_id), admissao_id),
            )
            item = fetchone_dict(cur, self.db_path)
            if not item or not item.get("caminho_privado") or not os.path.exists(item["caminho_privado"]):
                raise PlataformaRecursoNaoEncontradoException("Arquivo do item do checklist não encontrado.")
            with open(item["caminho_privado"], "rb") as f:
                conteudo = f.read()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="download_documento",
            registro_tipo="checklist_admissional",
            registro_id=item_id,
            usuario=usuario,
            detalhes=f"Download autorizado do documento '{item['nome_arquivo']}' (Admissão #{admissao_id}).",
            empresa_id=adm["empresa_id"],
        )
        return {
            "nome_arquivo": item["nome_arquivo"],
            "mime_type": item.get("mime_type") or "application/octet-stream",
            "conteudo_bytes": conteudo,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # RF-013: Validação Admissional Formal (RN-008 + RN-009)
    # ─────────────────────────────────────────────────────────────────────────
    def _avaliar_regras_admissao(
        self,
        cur,
        adm: Dict[str, Any],
        exigir_centro_custo: bool = False,
    ) -> Dict[str, Any]:
        p = self._p()
        aprovados: List[str] = []
        pendentes: List[str] = []
        invalidos: List[str] = []

        cpf_limpo = normalizar_cpf(adm.get("candidato_cpf") or "")
        if len(cpf_limpo) == 11 and validar_cpf(cpf_limpo):
            aprovados.append("CPF válido (RN-008)")
        else:
            invalidos.append("CPF do candidato ausente ou inválido (RN-008).")

        dt_adm_obj = converter_para_data(adm.get("data_prevista_admissao") or "")
        if dt_adm_obj:
            aprovados.append(f"Data prevista de admissão válida ({adm['data_prevista_admissao']}) (RN-008)")
        else:
            invalidos.append("Data de admissão ausente ou inválida (RN-008).")

        dt_nasc_raw = adm.get("candidato_data_nascimento")
        if not dt_nasc_raw:
            pendentes.append("Data de nascimento do candidato não preenchida (obrigatória antes da efetivação).")
        else:
            ok_n, msg_n = validar_data_nascimento(str(dt_nasc_raw))
            if ok_n:
                aprovados.append("Data de nascimento válida")
            else:
                invalidos.append(msg_n)

        if validar_email(adm.get("candidato_email") or ""):
            aprovados.append("E-mail do candidato válido")
        else:
            invalidos.append("E-mail do candidato ausente ou inválido.")

        sal = to_d(adm.get("salario_proposto") or 0)
        if sal >= SALARIO_MINIMO_2026:
            aprovados.append(f"Salário contratual conforme piso legal (R$ {sal:.2f}) (RN-008)")
        else:
            invalidos.append(f"Salário contratual (R$ {sal:.2f}) ausente ou inferior ao piso (R$ {SALARIO_MINIMO_2026:.2f}) (RN-008).")

        if adm.get("cargo") and str(adm["cargo"]).strip():
            aprovados.append(f"Cargo definido ({adm['cargo']}) (RN-008)")
        else:
            invalidos.append("Cargo obrigatório não informado (RN-008).")

        if adm.get("setor") and str(adm["setor"]).strip():
            aprovados.append(f"Setor definido ({adm['setor']})")
        else:
            pendentes.append("Setor não definido.")

        # Empresa e Filial
        cur.execute(f"SELECT * FROM empresas WHERE id = {p} AND ativo = 1;", (adm["empresa_id"],))
        emp = fetchone_dict(cur, self.db_path)
        if emp:
            aprovados.append(f"Empresa válida ({emp.get('nome_fantasia') or emp.get('razao_social')})")
        else:
            invalidos.append("Empresa inexistente ou inativa.")

        if adm.get("filial_id"):
            cur.execute(f"SELECT * FROM filiais WHERE id = {p} AND empresa_id = {p} AND ativo = 1;", (adm["filial_id"], adm["empresa_id"]))
            fil = fetchone_dict(cur, self.db_path)
            if fil:
                aprovados.append(f"Filial válida ({fil['nome']})")
            else:
                invalidos.append("Filial inválida ou incompatível com a empresa.")
        else:
            pendentes.append("Filial de lotação não informada.")

        # RF-017 / RN-008: Jornada cadastrada e ativa
        if adm.get("escala_id"):
            cur.execute(f"SELECT * FROM escalas_jornada WHERE id = {p} AND empresa_id = {p} AND ativo = 1;", (int(adm["escala_id"]), adm["empresa_id"]))
            esc = fetchone_dict(cur, self.db_path)
            if esc:
                aprovados.append(f"Jornada válida ({esc['codigo']} - {esc['descricao']}) (RF-017, RN-008)")
            else:
                invalidos.append("Jornada vinculada está inativa, inexistente ou pertence a outra empresa (RF-017, RN-008).")
        else:
            pendentes.append("Jornada inicial não definida (RF-017, RN-008).")

        # RF-018: Centro de Custo
        if adm.get("centro_custo_id"):
            cur.execute(
                f"SELECT * FROM centros_custo WHERE id = {p} AND empresa_id = {p} AND ativo = 1;",
                (adm["centro_custo_id"], adm["empresa_id"]),
            )
            cc = fetchone_dict(cur, self.db_path)
            if cc:
                aprovados.append(f"Centro de Custo válido ({cc['codigo']} - {cc['descricao']}) (RF-018)")
            else:
                invalidos.append("Centro de Custo vinculado inativo ou incompatível com a empresa (RF-018).")
        elif exigir_centro_custo:
            pendentes.append("Centro de Custo obrigatório não vinculado (RF-018).")

        # RF-012: Checklist documental
        cur.execute(f"SELECT * FROM checklist_admissional WHERE admissao_id = {p} ORDER BY id ASC;", (adm["id"],))
        itens_chk = fetchall_dict(cur, self.db_path)
        for it in itens_chk:
            st_it = str(it.get("status") or "pendente").lower()
            if it.get("obrigatorio"):
                if st_it in ("validado", "dispensado"):
                    continue
                if st_it == "rejeitado":
                    invalidos.append(f"Documento obrigatório rejeitado: {it['item_descricao']} ({it.get('motivo_rejeicao') or 'requer correção'}) (RF-012).")
                else:
                    pendentes.append(f"Documento obrigatório pendente/não validado: {it['item_descricao']} ({st_it}) (RF-012).")
        if not any(i["obrigatorio"] and i["status"] not in ("validado", "dispensado") for i in itens_chk):
            aprovados.append("Todos os documentos obrigatórios do checklist validados (RF-012)")

        # RF-016 / RN-009: ASO Admissional REAL em sst_asos
        cur.execute(
            f"SELECT * FROM sst_asos WHERE admissao_id = {p} ORDER BY id DESC LIMIT 1;",
            (adm["id"],),
        )
        aso = fetchone_dict(cur, self.db_path)
        hoje = date.today().strftime("%Y-%m-%d")
        if not aso:
            pendentes.append("ASO Admissional não registrado no módulo SST (RN-009, RF-016).")
        else:
            st_ex = str(aso.get("status_exame") or "realizado").lower()
            res_aso = str(aso.get("resultado") or "").lower()
            val_aso = str(aso.get("data_validade") or "")
            if res_aso == "inapto":
                invalidos.append("ASO Admissional com resultado INAPTO impede a contratação (RN-009, RF-016).")
            elif st_ex in ("pendente", "agendado", "pendente_analise"):
                pendentes.append(f"ASO Admissional em status '{st_ex}' aguardando conclusão e aptidão (RN-009).")
            elif res_aso != "apto":
                invalidos.append(f"ASO Admissional sem resultado 'apto' (resultado atual: '{res_aso}') (RN-009).")
            elif val_aso and val_aso < hoje:
                invalidos.append(f"ASO Admissional vencido em {val_aso} (RN-009).")
            else:
                aprovados.append(f"ASO Admissional APTO e válido até {val_aso} (CRM {aso.get('medico_crm')}/{aso.get('medico_uf')}) (RN-009, RF-016)")

        pendencias_impeditivas = invalidos + pendentes
        return {
            "apto_efetivacao": len(pendencias_impeditivas) == 0,
            "aprovados": aprovados,
            "pendentes": pendentes,
            "invalidos": invalidos,
            "pendencias_impeditivas": pendencias_impeditivas,
            "motivo_reprovacao": "; ".join(invalidos) if invalidos else None,
        }

    def validar_admissao(
        self,
        admissao_id: int,
        usuario: str,
        empresa_id: Optional[str] = None,
        exigir_centro_custo: bool = False,
    ) -> Dict[str, Any]:
        """RF-013: Executa etapa formal de validação admissional e grava snapshot em admissao_validacoes."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            res = self._avaliar_regras_admissao(cur, adm, exigir_centro_custo=exigir_centro_custo)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sql_pg = f"""
                INSERT INTO admissao_validacoes (
                    empresa_id, admissao_id, apto_efetivacao, aprovados_json, pendentes_json,
                    invalidos_json, motivo_reprovacao, validado_por, validado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO admissao_validacoes (
                    empresa_id, admissao_id, apto_efetivacao, aprovados_json, pendentes_json,
                    invalidos_json, motivo_reprovacao, validado_por, validado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p});
            """
            val_id = insert_returning_id(
                cur,
                conn,
                sql_pg,
                sql_sqlite,
                (
                    adm["empresa_id"],
                    admissao_id,
                    1 if res["apto_efetivacao"] else 0,
                    json.dumps(res["aprovados"], ensure_ascii=False),
                    json.dumps(res["pendentes"], ensure_ascii=False),
                    json.dumps(res["invalidos"], ensure_ascii=False),
                    res["motivo_reprovacao"],
                    usuario,
                    agora,
                ),
                self.db_path,
            )
            self._sincronizar_status_processo(cur, admissao_id)
            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="validacao",
            registro_tipo="admissao_validacoes",
            registro_id=val_id,
            usuario=usuario,
            valor_novo="APTO" if res["apto_efetivacao"] else "COM_PENDENCIAS",
            detalhes=f"Validação formal RF-013: {len(res['aprovados'])} aprovado(s), {len(res['pendentes'])} pendente(s), {len(res['invalidos'])} inválido(s).",
            empresa_id=adm["empresa_id"],
        )
        return {
            "id": val_id,
            "admissao_id": admissao_id,
            "validado_por": usuario,
            "validado_em": agora,
            **res,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # RF-016: Controle de Exame Admissional (ASO Real + Sigilo Médico)
    # ─────────────────────────────────────────────────────────────────────────
    def _filtrar_aso_sigilo(self, aso: Optional[Dict[str, Any]], perfil_usuario: str) -> Optional[Dict[str, Any]]:
        if not aso:
            return None
        perfil_low = str(perfil_usuario or "").strip().lower()
        if perfil_low in PERFIS_SIGILO_MEDICO_LIBERADO:
            return aso
        return {
            "id": aso.get("id"),
            "admissao_id": aso.get("admissao_id"),
            "tipo_aso": aso.get("tipo_aso"),
            "status_exame": aso.get("status_exame"),
            "resultado": aso.get("resultado"),
            "data_validade": aso.get("data_validade"),
            "restrito_sigilo_medico": True,
        }

    def registrar_aso_admissional(
        self,
        admissao_id: int,
        dados: Dict[str, Any],
        usuario: str = "SST",
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF-016 / RN-009: Registra ou atualiza exame ASO real vinculado ao processo admissional."""
        dados = dict(dados or {})
        st_exame = str(dados.get("status_exame") or "realizado").strip().lower()
        if st_exame not in STATUS_ASO_VALIDOS:
            raise PlataformaValidacaoException(f"Situação de ASO inválida: '{st_exame}'.")
        resultado = str(dados.get("resultado") or ("apto" if st_exame == "apto" else ("inapto" if st_exame == "inapto" else "pendente"))).strip().lower()
        if st_exame in ("apto", "inapto"):
            resultado = st_exame
            st_exame = "realizado"

        dt_real = (dados.get("data_realizacao") or dados.get("data_emissao") or date.today().strftime("%Y-%m-%d")).strip()[:10]
        dt_emissao = (dados.get("data_emissao") or dt_real).strip()[:10]
        dt_validade = (dados.get("data_validade") or "").strip()[:10]
        medico_nome = str(dados.get("medico_nome") or "").strip()
        medico_crm = str(dados.get("medico_crm") or "").strip()
        medico_uf = str(dados.get("medico_uf") or "SP").strip().upper()[:2]

        if st_exame == "realizado" and resultado in ("apto", "inapto"):
            if not medico_nome or not medico_crm:
                raise PlataformaValidacaoException("Médico responsável e CRM são obrigatórios para conclusão do ASO (RF-016).")
            if not converter_para_data(dt_emissao):
                raise PlataformaValidacaoException("Data de emissão do ASO inválida.")
            if not dt_validade or not converter_para_data(dt_validade):
                dt_validade = (datetime.strptime(dt_emissao, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")

        if not dt_validade:
            dt_validade = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            caminho_priv = None
            nome_arq = None
            mime_val = None
            sha_hex = None
            if dados.get("conteudo_base64") and dados.get("nome_arquivo"):
                raw_b = self._decodificar_base64(dados["conteudo_base64"])
                ok_a, msg_a, mime_val = validar_arquivo_documento(dados["nome_arquivo"], dados.get("mime_type") or "application/pdf", raw_b, 10)
                if not ok_a:
                    raise PlataformaValidacaoException(msg_a)
                _, ext = os.path.splitext(dados["nome_arquivo"].strip().lower())
                dir_aso = os.path.join(self._storage_dir("aso"), re.sub(r"[^a-zA-Z0-9_-]", "_", adm["empresa_id"]), str(admissao_id))
                os.makedirs(dir_aso, exist_ok=True)
                caminho_priv = os.path.join(dir_aso, f"{uuid.uuid4().hex}{ext}")
                with open(caminho_priv, "wb") as f:
                    f.write(raw_b)
                nome_arq = dados["nome_arquivo"].strip()
                sha_hex = hashlib.sha256(raw_b).hexdigest()

            colab_id = int(adm.get("colaborador_id") or 0)
            sql_pg = f"""
                INSERT INTO sst_asos (
                    empresa_id, colaborador_id, admissao_id, tipo_aso, status_exame, data_realizacao,
                    data_emissao, data_validade, resultado, medico_nome, medico_crm, medico_uf,
                    nome_arquivo, caminho_privado, mime_type, sha256_hash, observacoes_medicas, criado_por, criado_em
                ) VALUES ({','.join([p]*19)}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_asos (
                    empresa_id, colaborador_id, admissao_id, tipo_aso, status_exame, data_realizacao,
                    data_emissao, data_validade, resultado, medico_nome, medico_crm, medico_uf,
                    nome_arquivo, caminho_privado, mime_type, sha256_hash, observacoes_medicas, criado_por, criado_em
                ) VALUES ({','.join([p]*19)});
            """
            aso_id = insert_returning_id(
                cur,
                conn,
                sql_pg,
                sql_sqlite,
                (
                    adm["empresa_id"],
                    colab_id,
                    admissao_id,
                    "admissional",
                    st_exame,
                    dt_real,
                    dt_emissao,
                    dt_validade,
                    resultado,
                    medico_nome or "Aguardando médico examinador",
                    medico_crm or "PENDENTE",
                    medico_uf or "SP",
                    nome_arq,
                    caminho_priv,
                    mime_val,
                    sha_hex,
                    (dados.get("observacoes_medicas") or "").strip() or None,
                    usuario,
                    agora,
                ),
                self.db_path,
            )

            status_adm_aso = resultado if st_exame == "realizado" and resultado in ("apto", "inapto") else st_exame
            cur.execute(
                f"UPDATE admissoes SET aso_id = {p}, aso_admissional_status = {p}, atualizado_em = {p} WHERE id = {p};",
                (aso_id, status_adm_aso, agora, admissao_id),
            )

            # Sincroniza item do checklist correspondente quando concluído pelo exame médico real
            if resultado in ("apto", "inapto") and st_exame == "realizado":
                chk_st = "validado" if resultado == "apto" else "rejeitado"
                mot_chk = None if resultado == "apto" else "ASO Admissional registrado como INAPTO pelo SST."
                cur.execute(
                    f"""
                    UPDATE checklist_admissional
                    SET status = {p}, motivo_rejeicao = {p}, validado_por = {p}, validado_em = {p},
                        atualizado_por = {p}, atualizado_em = {p}
                    WHERE admissao_id = {p} AND (codigo_documento = 'ASO_ADMISSIONAL' OR UPPER(item_descricao) LIKE '%ASO%');
                """,
                    (chk_st, mot_chk, usuario, agora, usuario, agora, admissao_id),
                )

            self._sincronizar_status_processo(cur, admissao_id)
            conn.commit()
            cur.execute(f"SELECT * FROM sst_asos WHERE id = {p};", (aso_id,))
            aso_row = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="SST",
            operacao="inclusao_aso_admissional",
            registro_tipo="sst_asos",
            registro_id=aso_id,
            usuario=usuario,
            valor_novo=f"{st_exame}/{resultado}",
            detalhes=f"ASO Admissional #{aso_id} registrado para Admissão #{admissao_id} (Aptidão: {resultado}).",
            empresa_id=adm["empresa_id"],
        )
        return aso_row

    def consultar_aso_admissional(
        self,
        admissao_id: int,
        perfil_usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            cur.execute(f"SELECT * FROM sst_asos WHERE admissao_id = {p} ORDER BY id DESC LIMIT 1;", (admissao_id,))
            aso = fetchone_dict(cur, self.db_path)
            return self._filtrar_aso_sigilo(aso, perfil_usuario)
        finally:
            conn.close()

    def obter_documento_aso_download(
        self,
        admissao_id: int,
        usuario: str,
        perfil_usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if str(perfil_usuario or "").strip().lower() not in PERFIS_SIGILO_MEDICO_LIBERADO:
            raise PlataformaAcessoNegadoException("Acesso negado ao documento médico do ASO por regra de sigilo e LGPD (RF-016).")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            cur.execute(f"SELECT * FROM sst_asos WHERE admissao_id = {p} ORDER BY id DESC LIMIT 1;", (admissao_id,))
            aso = fetchone_dict(cur, self.db_path)
            if not aso or not aso.get("caminho_privado") or not os.path.exists(aso["caminho_privado"]):
                raise PlataformaRecursoNaoEncontradoException("Arquivo do ASO não anexado.")
            with open(aso["caminho_privado"], "rb") as f:
                conteudo = f.read()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="SST",
            operacao="download_aso",
            registro_tipo="sst_asos",
            registro_id=aso["id"],
            usuario=usuario,
            detalhes=f"Download autorizado de anexo do ASO Admissional #{aso['id']}.",
            empresa_id=adm["empresa_id"],
        )
        return {
            "nome_arquivo": aso.get("nome_arquivo") or f"aso_admissao_{admissao_id}.pdf",
            "mime_type": aso.get("mime_type") or "application/pdf",
            "conteudo_bytes": conteudo,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # RF-017: Cadastro de Jornada Inicial
    # ─────────────────────────────────────────────────────────────────────────
    def listar_escalas_jornada(self, empresa_id: Optional[str] = None, apenas_ativas: bool = True) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = "SELECT * FROM escalas_jornada WHERE 1=1"
            params: List[Any] = []
            if empresa_id:
                sql += f" AND empresa_id = {p}"
                params.append(str(empresa_id).strip())
            if apenas_ativas:
                sql += " AND ativo = 1"
            sql += " ORDER BY id ASC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def criar_escala_jornada(self, dados: Dict[str, Any], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        emp_id = str(empresa_id or (dados or {}).get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()
        cod = str((dados or {}).get("codigo") or "").strip().upper()
        desc = str((dados or {}).get("descricao") or "").strip()
        if not cod or not desc:
            raise PlataformaValidacaoException("Código e descrição da jornada são obrigatórios.")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO escalas_jornada (
                    empresa_id, codigo, descricao, carga_semanal_horas, divisor_mensal,
                    tipo_regime, entrada_padrao, saida_padrao, intervalo_minutos, ativo, criado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO escalas_jornada (
                    empresa_id, codigo, descricao, carga_semanal_horas, divisor_mensal,
                    tipo_regime, entrada_padrao, saida_padrao, intervalo_minutos, ativo, criado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p});
            """
            esc_id = insert_returning_id(
                cur,
                conn,
                sql_pg,
                sql_sqlite,
                (
                    emp_id,
                    cod,
                    desc,
                    float(dados.get("carga_semanal_horas") or 44.0),
                    float(dados.get("divisor_mensal") or 220.0),
                    str(dados.get("tipo_regime") or "5x2"),
                    str(dados.get("entrada_padrao") or "08:00"),
                    str(dados.get("saida_padrao") or "17:48"),
                    int(dados.get("intervalo_minutos") or 60),
                    1 if dados.get("ativo", 1) in (1, True, "1", "true") else 0,
                    agora,
                ),
                self.db_path,
            )
            conn.commit()
            cur.execute(f"SELECT * FROM escalas_jornada WHERE id = {p};", (esc_id,))
            row = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()
        self._registrar_auditoria("Jornada", "inclusao", "escalas_jornada", esc_id, usuario, detalhes=f"Escala {cod} criada.", empresa_id=emp_id)
        return row

    def definir_jornada_admissao(
        self,
        admissao_id: int,
        dados: Dict[str, Any],
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF-017: Vincula jornada/escala ativa e horários com vigência inicial e histórico."""
        if (dados or {}).get("escala_id") in (None, ""):
            raise PlataformaValidacaoException("Informe escala_id válida para definir a jornada (RF-017).")
        escala_id = int(dados["escala_id"])
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            refs = self._validar_referencias_vinculo(cur, adm["empresa_id"], None, escala_id, None)
            esc = refs["escala"]
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ent = str(dados.get("entrada") or esc["entrada_padrao"]).strip()
            sai = str(dados.get("saida") or esc["saida_padrao"]).strip()
            inter = int(dados.get("intervalo_minutos") if dados.get("intervalo_minutos") is not None else esc["intervalo_minutos"])
            dias_sem = str(dados.get("dias_semana") or esc["tipo_regime"]).strip()
            carga_m = float(dados.get("carga_mensal") or esc["divisor_mensal"])
            vig = str(dados.get("vigencia_inicio") or adm["data_prevista_admissao"]).strip()[:10]
            if not converter_para_data(vig):
                raise PlataformaValidacaoException("Data de vigência da jornada inválida.")

            cur.execute(
                f"""
                UPDATE admissoes
                SET escala_id={p}, jornada_descricao={p}, jornada_entrada={p}, jornada_saida={p},
                    jornada_intervalo_min={p}, jornada_dias_semana={p}, jornada_carga_mensal={p},
                    jornada_vigencia_inicio={p}, atualizado_em={p}
                WHERE id={p};
            """,
                (esc["id"], esc["descricao"], ent, sai, inter, dias_sem, carga_m, vig, agora, admissao_id),
            )
            cur.execute(
                f"""
                INSERT INTO admissao_jornadas_historico (
                    empresa_id, admissao_id, escala_id, descricao, entrada, saida,
                    intervalo_min, dias_semana, carga_mensal, vigencia_inicio, definido_por, definido_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p});
            """,
                (adm["empresa_id"], admissao_id, esc["id"], esc["descricao"], ent, sai, inter, dias_sem, carga_m, vig, usuario, agora),
            )
            self._sincronizar_status_processo(cur, admissao_id)
            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="jornada_definida",
            registro_tipo="admissoes",
            registro_id=admissao_id,
            usuario=usuario,
            valor_novo=f"{esc['codigo']} ({ent}-{sai}) vigência {vig}",
            detalhes=f"Jornada '{esc['descricao']}' vinculada à admissão #{admissao_id}.",
            empresa_id=adm["empresa_id"],
        )
        return self.obter_admissao(admissao_id, empresa_id=empresa_id)

    # ─────────────────────────────────────────────────────────────────────────
    # RF-018: Definição de Centro de Custo
    # ─────────────────────────────────────────────────────────────────────────
    def listar_centros_custo(self, empresa_id: Optional[str] = None, apenas_ativos: bool = True) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = "SELECT * FROM centros_custo WHERE 1=1"
            params: List[Any] = []
            if empresa_id:
                sql += f" AND empresa_id = {p}"
                params.append(str(empresa_id).strip())
            if apenas_ativas := apenas_ativos:
                sql += " AND ativo = 1"
            sql += " ORDER BY codigo ASC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def criar_centro_custo(self, dados: Dict[str, Any], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        emp_id = str(empresa_id or (dados or {}).get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()
        cod = str((dados or {}).get("codigo") or "").strip().upper()
        desc = str((dados or {}).get("descricao") or "").strip()
        if not cod or not desc:
            raise PlataformaValidacaoException("Código e descrição do centro de custo são obrigatórios.")
        cc_id = str((dados or {}).get("id") or f"cc-{uuid.uuid4().hex[:8]}").strip()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                INSERT INTO centros_custo (id, empresa_id, codigo, descricao, ativo, criado_em)
                VALUES ({p},{p},{p},{p},{p},{p});
            """,
                (cc_id, emp_id, cod, desc, 1 if dados.get("ativo", 1) in (1, True, "1", "true") else 0, agora),
            )
            conn.commit()
            cur.execute(f"SELECT * FROM centros_custo WHERE id = {p};", (cc_id,))
            row = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()
        self._registrar_auditoria("Financeiro", "inclusao", "centros_custo", cc_id, usuario, detalhes=f"Centro de custo {cod} criado.", empresa_id=emp_id)
        return row

    def definir_centro_custo_admissao(
        self,
        admissao_id: int,
        dados: Dict[str, Any],
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF-018: Vincula centro de custo ativo pertencente à mesma empresa e registra vigência."""
        cc_ref = str((dados or {}).get("centro_custo_id") or "").strip()
        if not cc_ref:
            raise PlataformaValidacaoException("Informe o centro_custo_id para vinculação (RF-018).")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            filial_req = str((dados or {}).get("filial_id") or adm.get("filial_id") or "").strip() or None
            refs = self._validar_referencias_vinculo(cur, adm["empresa_id"], filial_req, None, cc_ref)
            cc = refs["centro_custo"]
            vig = str((dados or {}).get("vigencia_inicio") or adm["data_prevista_admissao"]).strip()[:10]
            if not converter_para_data(vig):
                raise PlataformaValidacaoException("Data de vigência do centro de custo inválida.")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                f"""
                UPDATE admissoes
                SET centro_custo_id = {p}, centro_custo_vigencia = {p}, filial_id = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (cc["id"], vig, filial_req, agora, admissao_id),
            )
            cur.execute(
                f"""
                INSERT INTO admissao_centros_custo_historico (
                    empresa_id, admissao_id, centro_custo_id, filial_id, vigencia_inicio, definido_por, definido_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p});
            """,
                (adm["empresa_id"], admissao_id, cc["id"], filial_req, vig, usuario, agora),
            )
            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="centro_custo_definido",
            registro_tipo="admissoes",
            registro_id=admissao_id,
            usuario=usuario,
            valor_novo=f"{cc['codigo']} - {cc['descricao']} (vigência {vig})",
            detalhes=f"Centro de Custo '{cc['codigo']}' vinculado à admissão #{admissao_id}.",
            empresa_id=adm["empresa_id"],
        )
        return self.obter_admissao(admissao_id, empresa_id=empresa_id)

    # ─────────────────────────────────────────────────────────────────────────
    # RF-019: Definição de Benefícios Elegíveis na Admissão
    # ─────────────────────────────────────────────────────────────────────────
    def _avaliar_elegibilidade_candidato(self, adm: Dict[str, Any], benef: Dict[str, Any]) -> Dict[str, Any]:
        motivos: List[str] = []
        if int(benef.get("ativo", 1)) == 0:
            motivos.append(f"Benefício '{benef['nome']}' está inativo.")
        if str(benef.get("empresa_id") or "") != str(adm.get("empresa_id") or ""):
            motivos.append("Benefício pertence a outra empresa e não é compatível.")

        regras_raw = benef.get("regra_elegibilidade")
        try:
            regras = json.loads(regras_raw) if isinstance(regras_raw, str) and regras_raw else (regras_raw if isinstance(regras_raw, dict) else {})
        except Exception:
            regras = {}

        contratos_perm = [str(c).strip().lower() for c in (regras.get("tipos_contrato_permitidos") or []) if str(c).strip()]
        tipo_ctr = str(adm.get("tipo_contrato") or "CLT").strip().lower()
        # Contrato de experiência ou indeterminado é modalidade CLT no sistema
        tipo_ctr_norm = "clt" if tipo_ctr in ("experiencia", "indeterminado", "clt") else tipo_ctr
        if contratos_perm and tipo_ctr not in contratos_perm and tipo_ctr_norm not in contratos_perm:
            motivos.append(
                f"Contrato '{adm.get('tipo_contrato')}' inelegível (permitidos: {', '.join(regras['tipos_contrato_permitidos'])})."
            )

        tempo_min = int(regras.get("tempo_minimo_dias") or 0)
        if tempo_min > 0:
            motivos.append(f"Benefício exige {tempo_min} dias de casa (não elegível na admissão inicial).")

        setores_perm = [str(s).strip().lower() for s in (regras.get("setores_permitidos") or []) if str(s).strip()]
        if setores_perm and str(adm.get("setor") or "").strip().lower() not in setores_perm:
            motivos.append(f"Setor '{adm.get('setor')}' não contemplado pela regra de elegibilidade.")

        cargos_perm = [str(c).strip().lower() for c in (regras.get("cargos_permitidos") or []) if str(c).strip()]
        if cargos_perm and str(adm.get("cargo") or "").strip().lower() not in cargos_perm:
            motivos.append(f"Cargo '{adm.get('cargo')}' não contemplado pela regra de elegibilidade.")

        sal = float(adm.get("salario_proposto") or 0.0)
        sal_min = float(regras.get("salario_minimo") or 0.0)
        sal_max = float(regras.get("salario_maximo") or 0.0)
        if sal_min > 0 and sal < sal_min:
            motivos.append(f"Salário abaixo do piso de elegibilidade (R$ {sal_min:.2f}).")
        if sal_max > 0 and sal > sal_max:
            motivos.append(f"Salário acima do teto de elegibilidade (R$ {sal_max:.2f}).")

        return {"elegivel": len(motivos) == 0, "motivos": motivos}

    def listar_beneficios_elegiveis_admissao(
        self,
        admissao_id: int,
        empresa_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            cur.execute(
                f"SELECT * FROM beneficios_catalogo WHERE empresa_id = {p} AND ativo = 1 ORDER BY id ASC;",
                (adm["empresa_id"],),
            )
            catalogo = fetchall_dict(cur, self.db_path)
            resultado = []
            for b in catalogo:
                av = self._avaliar_elegibilidade_candidato(adm, b)
                resultado.append({**b, "elegivel": av["elegivel"], "motivos_inelegibilidade": av["motivos"]})
            return resultado
        finally:
            conn.close()

    def definir_beneficios_admissao(
        self,
        admissao_id: int,
        itens_beneficios: List[Dict[str, Any]],
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF-019: Associa benefícios elegíveis na admissão (validando existência, empresa e elegibilidade)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            if str(adm["status"]).lower() in ("efetivado", "aprovada", "cancelado"):
                raise PlataformaValidacaoException("Não é possível alterar benefícios pré-admissão após efetivação.")

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(f"DELETE FROM admissao_beneficios WHERE admissao_id = {p} AND status = 'pendente_efetivacao';", (admissao_id,))

            inseridos = []
            for item in (itens_beneficios or []):
                bid = item.get("beneficio_id")
                if not bid:
                    raise PlataformaValidacaoException("Cada item de benefício deve informar beneficio_id.")
                cur.execute(f"SELECT * FROM beneficios_catalogo WHERE id = {p};", (int(bid),))
                cat = fetchone_dict(cur, self.db_path)
                if not cat:
                    raise PlataformaValidacaoException(f"Benefício #{bid} não existe no catálogo (RF-019).")

                av = self._avaliar_elegibilidade_candidato(adm, cat)
                if not av["elegivel"]:
                    raise PlataformaValidacaoException(
                        f"Benefício '{cat['nome']}' inelegível/incompatível: {'; '.join(av['motivos'])} (RF-019)."
                    )

                vig_ini = str(item.get("vigencia_inicio") or adm["data_prevista_admissao"]).strip()[:10]
                if not converter_para_data(vig_ini):
                    raise PlataformaValidacaoException("Data de início de vigência do benefício inválida.")

                opt = 1 if item.get("optante", 1) in (1, True, "1", "true", "sim") else 0
                qtd_dep = int(item.get("qtd_dependentes") or 0)
                v_dia = float(item.get("valor_diario") if item.get("valor_diario") not in (None, "") else (cat.get("valor_diario_padrao") or 0.0))
                v_mens = float(item.get("valor_mensal_base") if item.get("valor_mensal_base") not in (None, "") else (cat.get("valor_mensal_padrao") or 0.0))
                cond = str(item.get("condicoes") or "").strip() or None

                sql_pg = f"""
                    INSERT INTO admissao_beneficios (
                        empresa_id, admissao_id, beneficio_id, elegivel, motivo_inelegibilidade,
                        optante, vigencia_inicio, qtd_dependentes, valor_diario, valor_mensal_base,
                        condicoes, status, definido_por, definido_em
                    ) VALUES ({p},{p},{p},1,NULL,{p},{p},{p},{p},{p},{p},'pendente_efetivacao',{p},{p}) RETURNING id;
                """
                sql_sqlite = f"""
                    INSERT INTO admissao_beneficios (
                        empresa_id, admissao_id, beneficio_id, elegivel, motivo_inelegibilidade,
                        optante, vigencia_inicio, qtd_dependentes, valor_diario, valor_mensal_base,
                        condicoes, status, definido_por, definido_em
                    ) VALUES ({p},{p},{p},1,NULL,{p},{p},{p},{p},{p},{p},'pendente_efetivacao',{p},{p});
                """
                ab_id = insert_returning_id(
                    cur,
                    conn,
                    sql_pg,
                    sql_sqlite,
                    (adm["empresa_id"], admissao_id, cat["id"], opt, vig_ini, qtd_dep, v_dia, v_mens, cond, usuario, agora),
                    self.db_path,
                )
                inseridos.append({"id": ab_id, "beneficio_id": cat["id"], "nome": cat["nome"], "vigencia_inicio": vig_ini})

            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="beneficios_definidos",
            registro_tipo="admissoes",
            registro_id=admissao_id,
            usuario=usuario,
            valor_novo=f"{len(inseridos)} benefício(s) associado(s)",
            detalhes=f"Benefícios vinculados à admissão #{admissao_id}: {[i['nome'] for i in inseridos]}",
            empresa_id=adm["empresa_id"],
        )
        return {"sucesso": True, "admissao_id": admissao_id, "total": len(inseridos), "dados": inseridos}

    # ─────────────────────────────────────────────────────────────────────────
    # RF-014: Modelos e Geração Real do Contrato de Trabalho em PDF
    # ─────────────────────────────────────────────────────────────────────────
    def listar_modelos_contrato(self, empresa_id: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = "SELECT * FROM admissao_contratos_modelos WHERE ativo = 1"
            params: List[Any] = []
            if empresa_id:
                sql += f" AND (empresa_id = {p} OR empresa_id = 'a0000000-0000-0000-0000-000000000001')"
                params.append(empresa_id)
            sql += " ORDER BY id ASC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def gerar_contrato_trabalho(
        self,
        admissao_id: int,
        usuario: str,
        modelo_id: Optional[int] = None,
        condicoes_adicionais: str = "",
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF-014: Gera PDF 1.4 real do contrato individual de trabalho, versiona e preserva formalizações anteriores."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)

            if modelo_id:
                cur.execute(f"SELECT * FROM admissao_contratos_modelos WHERE id = {p} AND ativo = 1;", (int(modelo_id),))
            else:
                tipo_c = str(adm.get("tipo_contrato") or "experiencia").strip().lower()
                cur.execute(
                    f"SELECT * FROM admissao_contratos_modelos WHERE LOWER(tipo_contrato) = {p} AND ativo = 1 LIMIT 1;",
                    (tipo_c,),
                )
            modelo = fetchone_dict(cur, self.db_path)
            if not modelo:
                cur.execute("SELECT * FROM admissao_contratos_modelos WHERE ativo = 1 ORDER BY id ASC LIMIT 1;")
                modelo = fetchone_dict(cur, self.db_path)
            if not modelo:
                raise PlataformaRecursoNaoEncontradoException("Nenhum modelo contratual ativo configurado.")

            cur.execute(f"SELECT * FROM empresas WHERE id = {p};", (adm["empresa_id"],))
            emp = fetchone_dict(cur, self.db_path)
            filial = None
            if adm.get("filial_id"):
                cur.execute(f"SELECT * FROM filiais WHERE id = {p};", (adm["filial_id"],))
                filial = fetchone_dict(cur, self.db_path)
            escala = None
            if adm.get("escala_id"):
                cur.execute(f"SELECT * FROM escalas_jornada WHERE id = {p};", (int(adm["escala_id"]),))
                escala = fetchone_dict(cur, self.db_path)
            cc = None
            if adm.get("centro_custo_id"):
                cur.execute(f"SELECT * FROM centros_custo WHERE id = {p};", (adm["centro_custo_id"],))
                cc = fetchone_dict(cur, self.db_path)

            cur.execute(
                f"""
                SELECT ab.*, bc.codigo AS beneficio_codigo, bc.nome AS beneficio_nome
                FROM admissao_beneficios ab
                JOIN beneficios_catalogo bc ON bc.id = ab.beneficio_id
                WHERE ab.admissao_id = {p};
            """,
                (admissao_id,),
            )
            beneficios = fetchall_dict(cur, self.db_path)

            cur.execute(f"SELECT COALESCE(MAX(versao), 0) FROM admissao_contratos WHERE admissao_id = {p};", (admissao_id,))
            nova_versao = int(cur.fetchone()[0] or 0) + 1

            try:
                pdf_bytes = gerar_pdf_contrato_trabalho(
                    modelo=modelo,
                    admissao=adm,
                    empresa=emp,
                    filial=filial,
                    escala=escala,
                    centro_custo=cc,
                    beneficios=beneficios,
                    versao=nova_versao,
                    condicoes_adicionais=condicoes_adicionais,
                )
            except ValueError as ve:
                raise PlataformaValidacaoException(str(ve))

            sha256_pdf = hashlib.sha256(pdf_bytes).hexdigest()
            nome_arq = f"CONTRATO_{adm.get('codigo_processo') or admissao_id}_v{nova_versao}.pdf"
            dir_ctr = os.path.join(self._storage_dir("contratos"), re.sub(r"[^a-zA-Z0-9_-]", "_", adm["empresa_id"]), str(admissao_id))
            os.makedirs(dir_ctr, exist_ok=True)
            caminho_priv = os.path.join(dir_ctr, f"{uuid.uuid4().hex}.pdf")
            with open(caminho_priv, "wb") as f:
                f.write(pdf_bytes)

            snapshot = {
                "modelo_codigo": modelo["codigo"],
                "cargo": adm["cargo"],
                "setor": adm["setor"],
                "salario": float(adm["salario_proposto"]),
                "data_admissao": adm["data_prevista_admissao"],
                "jornada": adm.get("jornada_descricao"),
                "versao": nova_versao,
            }
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO admissao_contratos (
                    empresa_id, admissao_id, modelo_id, versao, nome_arquivo, caminho_privado,
                    sha256_hash, formalizado, condicoes_adicionais, dados_snapshot_json, gerado_por, gerado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},0,{p},{p},{p},{p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO admissao_contratos (
                    empresa_id, admissao_id, modelo_id, versao, nome_arquivo, caminho_privado,
                    sha256_hash, formalizado, condicoes_adicionais, dados_snapshot_json, gerado_por, gerado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},0,{p},{p},{p},{p});
            """
            ctr_id = insert_returning_id(
                cur,
                conn,
                sql_pg,
                sql_sqlite,
                (
                    adm["empresa_id"],
                    admissao_id,
                    modelo["id"],
                    nova_versao,
                    nome_arq,
                    caminho_priv,
                    sha256_pdf,
                    condicoes_adicionais or "",
                    json.dumps(snapshot, ensure_ascii=False),
                    usuario,
                    agora,
                ),
                self.db_path,
            )
            cur.execute(
                f"UPDATE admissoes SET contrato_gerado = 1, contrato_id = {p}, atualizado_em = {p} WHERE id = {p};",
                (ctr_id, agora, admissao_id),
            )
            conn.commit()
            cur.execute(f"SELECT * FROM admissao_contratos WHERE id = {p};", (ctr_id,))
            ctr_row = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="geracao_contrato",
            registro_tipo="admissao_contratos",
            registro_id=ctr_id,
            usuario=usuario,
            valor_novo=f"{nome_arq} (SHA-256: {sha256_pdf[:12]})",
            detalhes=f"Contrato de Trabalho v{nova_versao} gerado para Admissão #{admissao_id}.",
            empresa_id=adm["empresa_id"],
        )
        return ctr_row

    def formalizar_contrato(
        self,
        admissao_id: int,
        contrato_id: int,
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            cur.execute(f"SELECT * FROM admissao_contratos WHERE id = {p} AND admissao_id = {p};", (int(contrato_id), admissao_id))
            ctr = fetchone_dict(cur, self.db_path)
            if not ctr:
                raise PlataformaRecursoNaoEncontradoException("Contrato não encontrado para esta admissão.")
            if int(ctr.get("formalizado") or 0) == 1:
                raise PlataformaValidacaoException("Esta versão do contrato já está formalizada e bloqueada contra edição.")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"UPDATE admissao_contratos SET formalizado = 1, formalizado_por = {p}, formalizado_em = {p} WHERE id = {p};",
                (usuario, agora, int(contrato_id)),
            )
            conn.commit()
            cur.execute(f"SELECT * FROM admissao_contratos WHERE id = {p};", (int(contrato_id),))
            row = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="formalizacao_contrato",
            registro_tipo="admissao_contratos",
            registro_id=contrato_id,
            usuario=usuario,
            valor_novo=f"Formalizado v{ctr['versao']}",
            detalhes=f"Versão v{ctr['versao']} do contrato preservada como formalizada.",
            empresa_id=adm["empresa_id"],
        )
        return row

    def obter_contrato_pdf_download(
        self,
        admissao_id: int,
        contrato_id: int,
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            cur.execute(f"SELECT * FROM admissao_contratos WHERE id = {p} AND admissao_id = {p};", (int(contrato_id), admissao_id))
            ctr = fetchone_dict(cur, self.db_path)
            if not ctr or not os.path.exists(ctr["caminho_privado"]):
                raise PlataformaRecursoNaoEncontradoException("Arquivo PDF do contrato não encontrado.")
            with open(ctr["caminho_privado"], "rb") as f:
                pdf_bytes = f.read()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="download_contrato",
            registro_tipo="admissao_contratos",
            registro_id=contrato_id,
            usuario=usuario,
            detalhes=f"Download autorizado do contrato '{ctr['nome_arquivo']}'.",
            empresa_id=adm["empresa_id"],
        )
        return {"nome_arquivo": ctr["nome_arquivo"], "mime_type": "application/pdf", "conteudo_bytes": pdf_bytes}

    # ─────────────────────────────────────────────────────────────────────────
    # RF-015: Integração eSocial Admissional (S-2190 & S-2200)
    # ─────────────────────────────────────────────────────────────────────────
    def gerar_evento_esocial_admissao(
        self,
        admissao_id: int,
        tipo_evento: Optional[str],
        usuario: str,
        ambiente: str = "homologacao",
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF-015 / RN-010: Avalia aplicabilidade e gera XML validado (S-2190 ou S-2200) sem recibos fictícios."""
        amb = str(ambiente or "homologacao").strip().lower()
        if amb not in ("homologacao", "producao_restrita", "producao"):
            raise PlataformaValidacaoException("Ambiente eSocial inválido.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            cur.execute(f"SELECT * FROM empresas WHERE id = {p};", (adm["empresa_id"],))
            emp = fetchone_dict(cur, self.db_path)
            filial = None
            if adm.get("filial_id"):
                cur.execute(f"SELECT * FROM filiais WHERE id = {p};", (adm["filial_id"],))
                filial = fetchone_dict(cur, self.db_path)
            escala = None
            if adm.get("escala_id"):
                cur.execute(f"SELECT * FROM escalas_jornada WHERE id = {p};", (int(adm["escala_id"]),))
                escala = fetchone_dict(cur, self.db_path)

            cur.execute(
                f"""
                SELECT * FROM esocial_eventos
                WHERE empresa_id = {p} AND (identificador_origem = {p} OR identificador_origem = {p})
                ORDER BY id DESC;
            """,
                (adm["empresa_id"], f"ADM:{admissao_id}", str(adm.get("colaborador_id") or "__NONE__")),
            )
            existentes = fetchall_dict(cur, self.db_path)

            aplic = avaliar_aplicabilidade_esocial(adm, existentes)
            tipo_alvo = str(tipo_evento or aplic["evento_recomendado"]).upper().strip()
            if tipo_alvo not in ("S-2190", "S-2200"):
                raise PlataformaValidacaoException("Evento admissional deve ser S-2190 ou S-2200.")

            ativos_mesmo_tipo = [e for e in existentes if e["tipo_evento"] == tipo_alvo and e["status"] not in ("rejeitado", "excluido")]
            if ativos_mesmo_tipo:
                raise PlataformaValidacaoException(
                    f"Já existe evento {tipo_alvo} ativo (#{ativos_mesmo_tipo[0]['id']}) para esta admissão (anti-duplicidade RF-015)."
                )

            if tipo_alvo == "S-2190":
                xml_str, erros_xml = gerar_xml_s2190(adm, emp, ambiente=amb)
            else:
                mat = None
                if adm.get("colaborador_id"):
                    cur.execute(f"SELECT matricula FROM colaboradores WHERE id = {p};", (int(adm["colaborador_id"]),))
                    r_m = cur.fetchone()
                    if r_m:
                        mat = r_m[0]
                mat = mat or adm.get("codigo_processo") or f"ADM-{admissao_id}"
                xml_str, erros_xml = gerar_xml_s2200(adm, emp, matricula=mat, filial=filial, escala=escala, ambiente=amb)

            if erros_xml:
                raise PlataformaValidacaoException("Falha na validação de dados para eSocial: " + "; ".join(erros_xml))

            ok_schema, erros_schema = validar_xml_esocial(tipo_alvo, xml_str)
            if not ok_schema:
                raise PlataformaValidacaoException("Falha na validação do schema XML eSocial: " + "; ".join(erros_schema))

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ident_orig = str(adm["colaborador_id"]) if adm.get("colaborador_id") else f"ADM:{admissao_id}"
            sql_pg = f"""
                INSERT INTO esocial_eventos (
                    empresa_id, tipo_evento, identificador_origem, ambiente, status,
                    xml_conteudo, numero_recibo, codigo_resposta, mensagem_resposta, criado_por, criado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},NULL,'VALIDADO_SCHEMA',{p},{p},{p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO esocial_eventos (
                    empresa_id, tipo_evento, identificador_origem, ambiente, status,
                    xml_conteudo, numero_recibo, codigo_resposta, mensagem_resposta, criado_por, criado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},NULL,'VALIDADO_SCHEMA',{p},{p},{p});
            """
            msg_resp = f"XML {tipo_alvo} validado no leiaute v_S_01_02_00 ({amb}). Aguardando transmissão com certificado ICP-Brasil (sem recibo fictício)."
            evt_id = insert_returning_id(
                cur,
                conn,
                sql_pg,
                sql_sqlite,
                (adm["empresa_id"], tipo_alvo, ident_orig, amb, "validado", xml_str, msg_resp, usuario, agora),
                self.db_path,
            )
            conn.commit()
            cur.execute(f"SELECT * FROM esocial_eventos WHERE id = {p};", (evt_id,))
            evt_row = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="eSocial",
            operacao=f"geracao_{tipo_alvo}",
            registro_tipo="esocial_eventos",
            registro_id=evt_id,
            usuario=usuario,
            valor_novo=f"{tipo_alvo} validado ({amb})",
            detalhes=f"Evento {tipo_alvo} gerado e validado no leiaute v_S_01_02_00 para Admissão #{admissao_id}.",
            empresa_id=adm["empresa_id"],
        )
        return {**evt_row, "aplicabilidade": aplic}

    def registrar_retorno_esocial(
        self,
        evento_id: int,
        status_retorno: str,
        codigo_resposta: str,
        mensagem_resposta: str,
        protocolo_envio: Optional[str] = None,
        numero_recibo: Optional[str] = None,
        usuario: str = "eSocial",
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Registra retorno real ou rejeição de evento eSocial sem fabricar recibos."""
        st_ret = str(status_retorno or "").strip().lower()
        if st_ret not in ("rejeitado", "aceito", "erro", "validado"):
            raise PlataformaValidacaoException("Status de retorno eSocial inválido.")
        if st_ret == "aceito" and (not numero_recibo or str(numero_recibo).startswith("SIM-")):
            raise PlataformaValidacaoException(
                "Não é permitido declarar evento como 'aceito' com recibo ausente ou simulado (RF-015)."
            )
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = f"SELECT * FROM esocial_eventos WHERE id = {p}"
            params: List[Any] = [int(evento_id)]
            if empresa_id:
                sql += f" AND empresa_id = {p}"
                params.append(empresa_id)
            cur.execute(sql + ";", tuple(params))
            evt = fetchone_dict(cur, self.db_path)
            if not evt:
                raise PlataformaRecursoNaoEncontradoException("Evento eSocial não encontrado.")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"""
                UPDATE esocial_eventos
                SET status = {p}, protocolo_envio = {p}, numero_recibo = {p},
                    codigo_resposta = {p}, mensagem_resposta = {p}, processado_em = {p}
                WHERE id = {p};
            """,
                (
                    "rejeitado" if st_ret == "erro" else st_ret,
                    protocolo_envio or evt.get("protocolo_envio"),
                    numero_recibo if st_ret == "aceito" else None,
                    codigo_resposta,
                    mensagem_resposta,
                    agora,
                    int(evento_id),
                ),
            )
            conn.commit()
            cur.execute(f"SELECT * FROM esocial_eventos WHERE id = {p};", (int(evento_id),))
            atual = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="eSocial",
            operacao="retorno_evento",
            registro_tipo="esocial_eventos",
            registro_id=evento_id,
            usuario=usuario,
            valor_novo=f"{atual['status']} ({codigo_resposta})",
            detalhes=mensagem_resposta,
            empresa_id=evt["empresa_id"],
        )
        return atual

    def reprocessar_evento_esocial(
        self,
        evento_id: int,
        usuario: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reprocessa um evento eSocial rejeitado gerando nova versão XML validada."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = f"SELECT * FROM esocial_eventos WHERE id = {p}"
            params: List[Any] = [int(evento_id)]
            if empresa_id:
                sql += f" AND empresa_id = {p}"
                params.append(empresa_id)
            cur.execute(sql + ";", tuple(params))
            evt = fetchone_dict(cur, self.db_path)
            if not evt:
                raise PlataformaRecursoNaoEncontradoException("Evento eSocial não encontrado.")
            if evt["status"] != "rejeitado":
                raise PlataformaValidacaoException("Somente eventos rejeitados podem ser reprocessados (RF-015).")
            ident = str(evt.get("identificador_origem") or "")
            if ident.startswith("ADM:"):
                adm_id = int(ident.split(":", 1)[1])
            else:
                cur.execute(f"SELECT id FROM admissoes WHERE colaborador_id = {p} LIMIT 1;", (int(ident),))
                row_a = cur.fetchone()
                if not row_a:
                    raise PlataformaValidacaoException("Evento não vinculado a uma admissão identificável.")
                adm_id = int(row_a[0])
        finally:
            conn.close()

        return self.gerar_evento_esocial_admissao(
            adm_id,
            tipo_evento=evt["tipo_evento"],
            usuario=usuario,
            ambiente=evt["ambiente"],
            empresa_id=evt["empresa_id"],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # RF-020: Fluxo de Aprovação, Segregação, Efetivação Atômica e Cartão Único
    # ─────────────────────────────────────────────────────────────────────────
    def solicitar_aprovacao_admissao(
        self,
        admissao_id: int,
        usuario: str,
        justificativa: str = "",
        empresa_id: Optional[str] = None,
        exigir_centro_custo: bool = False,
    ) -> Dict[str, Any]:
        """Valida prontidão (RF-013) e submete o processo admissional para fila de aprovação (RF-020)."""
        val = self.validar_admissao(admissao_id, usuario=usuario, empresa_id=empresa_id, exigir_centro_custo=exigir_centro_custo)
        if not val["apto_efetivacao"]:
            raise PlataformaValidacaoException(
                "Não é possível enviar para aprovação com pendências impeditivas: "
                + "; ".join(val["pendencias_impeditivas"])
            )
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"UPDATE admissoes SET status = 'aguardando_aprovacao', atualizado_em = {p} WHERE id = {p};",
                (agora, admissao_id),
            )
            cur.execute(
                f"""
                INSERT INTO aprovacoes_workflow (
                    empresa_id, modulo, processo_tipo, processo_id, solicitante,
                    status, justificativa, criado_em, atualizado_em
                ) VALUES ({p},'Admissao','admissao_solicitacao',{p},{p},'pendente',{p},{p},{p});
            """,
                (adm["empresa_id"], admissao_id, usuario, justificativa or "Submetido para aprovação final", agora, agora),
            )
            conn.commit()
        finally:
            conn.close()
        self._registrar_auditoria(
            modulo="Admissao",
            operacao="solicitacao_aprovacao",
            registro_tipo="admissoes",
            registro_id=admissao_id,
            usuario=usuario,
            valor_novo="aguardando_aprovacao",
            detalhes=f"Admissão #{admissao_id} submetida para aprovação.",
            empresa_id=adm["empresa_id"],
        )
        return {"sucesso": True, "admissao_id": admissao_id, "status": "aguardando_aprovacao"}

    def aprovar_admissao(
        self,
        admissao_id: int,
        aprovador: str,
        justificativa: str = "",
        empresa_id: Optional[str] = None,
        exigir_centro_custo: bool = False,
    ) -> Dict[str, Any]:
        """
        RF-020: Valida RN-080 (segregação de funções), RN-008, RN-009 e RF-012/RF-013,
        com suporte a dupla aprovação opcional e efetivação transacional atômica.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            st_adm = str(adm["status"]).lower()
            if st_adm in ("aprovada", "efetivado"):
                raise PlataformaValidacaoException("Esta admissão já foi aprovada e o colaborador já está ativo.")
            if st_adm in ("cancelado", "reprovado"):
                raise PlataformaValidacaoException(f"Admissão em situação '{st_adm}' não pode ser aprovada.")

            # Segregação de funções (RN-080)
            if str(adm["criado_por"]).strip().lower() == str(aprovador).strip().lower():
                raise PlataformaAcessoNegadoException(
                    "Violação de Segregação de Funções (RN-080): O usuário que registrou a admissão não pode aprovar a própria admissão."
                )

            # Dupla aprovação configurada
            dupla = int(adm.get("dupla_aprovacao_exigida") or 0) == 1
            if dupla and adm.get("primeira_aprovacao_por"):
                if str(adm["primeira_aprovacao_por"]).strip().lower() == str(aprovador).strip().lower():
                    raise PlataformaAcessoNegadoException(
                        "Violação de Segregação de Funções: A segunda aprovação deve ser feita por outro aprovador distinto."
                    )

            # Portão de validação estrito (checklist + RN-008 + RN-009)
            pendencias_docs = []
            cur.execute(f"SELECT * FROM checklist_admissional WHERE admissao_id = {p};", (admissao_id,))
            itens_chk = fetchall_dict(cur, self.db_path)
            pendencias_docs = [i["item_descricao"] for i in itens_chk if i["obrigatorio"] and i["status"] not in ("validado", "dispensado")]
            if pendencias_docs:
                raise PlataformaValidacaoException(
                    f"Admissão não pode ser aprovada com itens obrigatórios pendentes: {', '.join(pendencias_docs)} (RF-012, RF-020)."
                )

            av = self._avaliar_regras_admissao(cur, adm, exigir_centro_custo=exigir_centro_custo)
            if not av["apto_efetivacao"]:
                raise PlataformaValidacaoException(
                    "Bloqueio de Aprovação (RF-013/RF-020): " + "; ".join(av["pendencias_impeditivas"])
                )

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Caso seja dupla aprovação e ainda falte a segunda alçada:
            if dupla and not adm.get("primeira_aprovacao_por"):
                cur.execute(
                    f"""
                    UPDATE admissoes
                    SET status = 'aprovado', primeira_aprovacao_por = {p}, primeira_aprovacao_em = {p},
                        justificativa_aprovacao = {p}, atualizado_em = {p}
                    WHERE id = {p};
                """,
                    (aprovador, agora, (justificativa or "1ª aprovação concedida").strip(), agora, admissao_id),
                )
                cur.execute(
                    f"""
                    INSERT INTO aprovacoes_workflow (
                        empresa_id, modulo, processo_tipo, processo_id, solicitante,
                        aprovador, status, justificativa, criado_em, atualizado_em
                    ) VALUES ({p},'Admissao','admissao_1_alcada',{p},{p},{p},'aprovado',{p},{p},{p});
                """,
                    (adm["empresa_id"], admissao_id, adm["criado_por"], aprovador, justificativa or "1ª aprovação", agora, agora),
                )
                conn.commit()
                return {
                    "sucesso": True,
                    "admissao_id": admissao_id,
                    "aguardando_segunda_aprovacao": True,
                    "status": "aprovado",
                    "mensagem": "1ª aprovação registrada com sucesso! Aguardando 2ª alçada para efetivação.",
                }

            # Efetivação Transacional Atômica (tudo dentro de uma única transação SQL)
            # 1. Proteção de concorrência/idempotência contra duplicidade de CPF ativo
            cpf_limpo = normalizar_cpf(adm["candidato_cpf"])
            cpf_fmt = f"{cpf_limpo[:3]}.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-{cpf_limpo[9:11]}"
            cur.execute(
                f"""
                SELECT id FROM colaboradores
                WHERE (cpf = {p} OR cpf = {p}) AND COALESCE(situacao, 'ativo') = 'ativo'
                  AND COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p};
            """,
                (cpf_limpo, cpf_fmt, adm["empresa_id"]),
            )
            if cur.fetchone():
                raise PlataformaValidacaoException("Concorrência/Idempotência: Já existe colaborador ativo cadastrado com este CPF.")

            # 2. Gera matrícula única corporativa
            cur.execute("SELECT COUNT(*) FROM colaboradores;")
            count_colab = int(cur.fetchone()[0] or 0)
            seq_num = 1000 + count_colab + 1
            matricula_gerada = f"FV-{seq_num}"
            while True:
                cur.execute(f"SELECT 1 FROM colaboradores WHERE matricula = {p};", (matricula_gerada,))
                if not cur.fetchone():
                    break
                seq_num += 1
                matricula_gerada = f"FV-{seq_num}"

            # 3. Buscar metadados de jornada e centro de custo reais
            cur.execute(f"SELECT * FROM escalas_jornada WHERE id = {p};", (int(adm["escala_id"]),))
            escala = fetchone_dict(cur, self.db_path)
            cc_texto = None
            if adm.get("centro_custo_id"):
                cur.execute(f"SELECT codigo, descricao FROM centros_custo WHERE id = {p};", (adm["centro_custo_id"],))
                cc_r = fetchone_dict(cur, self.db_path)
                if cc_r:
                    cc_texto = f"{cc_r['codigo']} - {cc_r['descricao']}"

            # 4. Inserir colaborador ativo com data de nascimento, jornada, centro de custo, empresa e filial reais
            if self._pg():
                sql_colab = f"""
                    INSERT INTO colaboradores (
                        matricula, nome_completo, cpf, rg, pis_pasep, email, telefone, logradouro,
                        estado_civil, data_nascimento, data_admissao, cargo, setor, departamento,
                        centro_custo, tipo_contrato, jornada_trabalho, carga_horaria_mensal,
                        salario_base, situacao, empresa_id, filial_id, escala_id, criado_por, criado_em, atualizado_em
                    ) VALUES ({','.join([p]*19)}, 'ativo', {p},{p},{p},{p},{p},{p}) RETURNING id;
                """
                params_colab = (
                    matricula_gerada,
                    adm["candidato_nome"],
                    cpf_fmt,
                    adm.get("candidato_rg"),
                    adm.get("candidato_pis"),
                    adm["candidato_email"],
                    adm.get("candidato_telefone"),
                    adm.get("candidato_endereco"),
                    adm.get("candidato_estado_civil"),
                    adm["candidato_data_nascimento"],
                    adm["data_prevista_admissao"],
                    adm["cargo"],
                    adm["setor"],
                    adm["setor"],
                    cc_texto,
                    adm.get("tipo_contrato") or "CLT",
                    adm.get("jornada_descricao") or (escala["descricao"] if escala else "44h semanais"),
                    float(adm.get("jornada_carga_mensal") or (escala["divisor_mensal"] if escala else 220.0)),
                    float(adm["salario_proposto"]),
                    adm["empresa_id"],
                    adm.get("filial_id"),
                    int(adm["escala_id"]),
                    aprovador,
                    agora,
                    agora,
                )
            else:
                sql_colab = f"""
                    INSERT INTO colaboradores (
                        matricula, nome_completo, cpf, rg, pis_pasep, email, telefone, logradouro,
                        estado_civil, data_nascimento, data_admissao, cargo, setor, departamento,
                        centro_custo, tipo_contrato, jornada_trabalho, carga_horaria_mensal,
                        salario_base, situacao, empresa_id, filial_id, escala_id, criado_por, criado_em, atualizado_em
                    ) VALUES ({','.join([p]*19)}, 'ativo', {p},{p},{p},{p},{p},{p});
                """
                params_colab = (
                    matricula_gerada,
                    adm["candidato_nome"],
                    cpf_fmt,
                    adm.get("candidato_rg"),
                    adm.get("candidato_pis"),
                    adm["candidato_email"],
                    adm.get("candidato_telefone"),
                    adm.get("candidato_endereco"),
                    adm.get("candidato_estado_civil"),
                    adm["candidato_data_nascimento"],
                    adm["data_prevista_admissao"],
                    adm["cargo"],
                    adm["setor"],
                    adm["setor"],
                    cc_texto,
                    adm.get("tipo_contrato") or "CLT",
                    adm.get("jornada_descricao") or (escala["descricao"] if escala else "44h semanais"),
                    float(adm.get("jornada_carga_mensal") or (escala["divisor_mensal"] if escala else 220.0)),
                    float(adm["salario_proposto"]),
                    adm["empresa_id"],
                    adm.get("filial_id"),
                    int(adm["escala_id"]),
                    aprovador,
                    agora,
                    agora,
                )
            novo_colab_id = insert_returning_id(cur, conn, sql_colab, sql_colab, params_colab, self.db_path)

            # 5. Histórico funcional inicial (RF-006)
            cur.execute(
                f"""
                INSERT INTO historico_funcional (
                    colaborador_id, empresa_id, tipo_movimentacao, campo_afetado,
                    valor_anterior, valor_novo, data_alteracao, data_vigencia, retroativa,
                    justificativa, observacoes, usuario_responsavel, origem, criado_em
                ) VALUES ({p},{p},'admissao','Admissão Inicial',NULL,{p},{p},{p},0,{p},{p},{p},'Módulo Admissão',{p});
            """,
                (
                    novo_colab_id,
                    adm["empresa_id"],
                    f"{adm['cargo']} — {adm['setor']} — R$ {float(adm['salario_proposto']):.2f}",
                    agora[:10],
                    adm["data_prevista_admissao"],
                    justificativa or "Efetivação do processo admissional (RF-020)",
                    f"Processo {adm.get('codigo_processo') or admissao_id}",
                    aprovador,
                    agora,
                ),
            )

            # 6. Vincular ASO Admissional real ao novo colaborador (RF-016)
            cur.execute(
                f"UPDATE sst_asos SET colaborador_id = {p} WHERE admissao_id = {p};",
                (novo_colab_id, admissao_id),
            )

            # 7. Ativar benefícios selecionados no cadastro de benefícios do colaborador (RF-019 -> Folha)
            cur.execute(
                f"""
                SELECT ab.*, bc.*
                FROM admissao_beneficios ab
                JOIN beneficios_catalogo bc ON bc.id = ab.beneficio_id
                WHERE ab.admissao_id = {p} AND ab.status = 'pendente_efetivacao';
            """,
                (admissao_id,),
            )
            benefs_adm = fetchall_dict(cur, self.db_path)
            colab_dict = {
                "id": novo_colab_id,
                "salario_base": float(adm["salario_proposto"]),
                "tipo_contrato": adm.get("tipo_contrato") or "CLT",
            }
            for ba in benefs_adm:
                if self._calcular_beneficio_cb:
                    calc_b = self._calcular_beneficio_cb(colab_dict, ba, ba)
                else:
                    calc_b = {
                        "optante": int(ba.get("optante", 1)),
                        "valor_diario": float(ba.get("valor_diario") or 0.0),
                        "dias_uteis_mes": 22,
                        "valor_mensal_base": float(ba.get("valor_mensal_base") or 0.0),
                        "qtd_dependentes": int(ba.get("qtd_dependentes") or 0),
                        "valor_dependente": 0.0,
                        "coparticipacao_extra": 0.0,
                        "limite_mensal": float(ba.get("limite_padrao") or 0.0),
                        "valor_utilizado_mes": 0.0,
                        "saldo_flexivel": 0.0,
                        "alocacao_json": None,
                        "custo_total_mes": float(ba.get("valor_mensal_base") or 0.0),
                        "desconto_colaborador": 0.0,
                        "custo_empresa": float(ba.get("valor_mensal_base") or 0.0),
                    }
                sql_bc_pg = f"""
                    INSERT INTO beneficios_colaborador (
                        colaborador_id, beneficio_id, optante, valor_diario, dias_uteis_mes,
                        valor_mensal_base, qtd_dependentes, valor_dependente, coparticipacao_extra,
                        limite_mensal, valor_utilizado_mes, saldo_flexivel, alocacao_json,
                        custo_total_mes, desconto_colaborador, custo_empresa, vigencia_inicio,
                        observacoes, ativo, criado_em, atualizado_em
                    ) VALUES ({','.join([p]*18)}, 1, {p}, {p}) RETURNING id;
                """
                sql_bc_sq = f"""
                    INSERT INTO beneficios_colaborador (
                        colaborador_id, beneficio_id, optante, valor_diario, dias_uteis_mes,
                        valor_mensal_base, qtd_dependentes, valor_dependente, coparticipacao_extra,
                        limite_mensal, valor_utilizado_mes, saldo_flexivel, alocacao_json,
                        custo_total_mes, desconto_colaborador, custo_empresa, vigencia_inicio,
                        observacoes, ativo, criado_em, atualizado_em
                    ) VALUES ({','.join([p]*18)}, 1, {p}, {p});
                """
                bc_id = insert_returning_id(
                    cur,
                    conn,
                    sql_bc_pg,
                    sql_bc_sq,
                    (
                        novo_colab_id,
                        ba["beneficio_id"],
                        calc_b["optante"],
                        calc_b["valor_diario"],
                        calc_b["dias_uteis_mes"],
                        calc_b["valor_mensal_base"],
                        calc_b["qtd_dependentes"],
                        calc_b["valor_dependente"],
                        calc_b["coparticipacao_extra"],
                        calc_b["limite_mensal"],
                        calc_b["valor_utilizado_mes"],
                        calc_b["saldo_flexivel"],
                        calc_b["alocacao_json"],
                        calc_b["custo_total_mes"],
                        calc_b["desconto_colaborador"],
                        calc_b["custo_empresa"],
                        ba["vigencia_inicio"],
                        f"Ativado automaticamente na efetivação da admissão #{admissao_id}",
                        agora,
                        agora,
                    ),
                    self.db_path,
                )
                cur.execute(
                    f"UPDATE admissao_beneficios SET beneficio_colaborador_id = {p}, status = 'ativado' WHERE id = {p};",
                    (bc_id, ba["id"]),
                )

            # 8. Vincular contrato mais recente e documentos do checklist ao prontuário do colaborador (RF-007 + RF-012 + RF-014)
            for chk_doc in itens_chk:
                if chk_doc.get("caminho_privado") and chk_doc.get("nome_arquivo"):
                    cur.execute(
                        f"""
                        INSERT INTO colaborador_documentos (
                            colaborador_id, empresa_id, tipo_documento, categoria, nome_arquivo,
                            nome_interno_seguro, caminho_privado, mime_type, tamanho_bytes, sha256_hash,
                            observacao, data_emissao, situacao, versao, enviado_por, criado_em, atualizado_por, atualizado_em
                        ) VALUES ({','.join([p]*12)},'ativo',{','.join([p]*5)});
                    """,
                        (
                            novo_colab_id,
                            adm["empresa_id"],
                            chk_doc.get("item_descricao") or chk_doc.get("codigo_documento") or "Documento Admissional",
                            chk_doc.get("codigo_documento") or "ADMISSIONAL",
                            chk_doc["nome_arquivo"],
                            os.path.basename(chk_doc["caminho_privado"]),
                            chk_doc["caminho_privado"],
                            chk_doc.get("mime_type") or "application/pdf",
                            int(chk_doc.get("tamanho_bytes") or 0),
                            chk_doc.get("sha256_hash"),
                            f"Checklist admissional #{admissao_id} ({chk_doc.get('status')})",
                            agora[:10],
                            int(chk_doc.get("versao") or 1),
                            chk_doc.get("atualizado_por") or aprovador,
                            agora,
                            aprovador,
                            agora,
                        ),
                    )
            cur.execute(
                f"SELECT * FROM admissao_contratos WHERE admissao_id = {p} ORDER BY versao DESC, id DESC LIMIT 1;",
                (admissao_id,),
            )
            ctr_adm = fetchone_dict(cur, self.db_path)
            if ctr_adm:
                cur.execute(
                    f"""
                    INSERT INTO colaborador_documentos (
                        colaborador_id, empresa_id, tipo_documento, categoria, nome_arquivo,
                        nome_interno_seguro, caminho_privado, mime_type, tamanho_bytes, sha256_hash,
                        observacao, data_emissao, situacao, versao, enviado_por, criado_em, atualizado_por, atualizado_em
                    ) VALUES ({p},{p},'Contrato de Trabalho','CONTRATO_TRABALHO',{p},{p},{p},'application/pdf',0,{p},{p},{p},'ativo',{p},{p},{p},{p},{p});
                """,
                    (
                        novo_colab_id,
                        adm["empresa_id"],
                        ctr_adm["nome_arquivo"],
                        os.path.basename(ctr_adm["caminho_privado"]),
                        ctr_adm["caminho_privado"],
                        ctr_adm["sha256_hash"],
                        f"Contrato vinculado automaticamente na admissão #{admissao_id}",
                        agora[:10],
                        ctr_adm["versao"],
                        aprovador,
                        agora,
                        aprovador,
                        agora,
                    ),
                )

            # 9. Cria período aquisitivo de férias inicial automático (RF-051)
            dt_inicio_aq = adm["data_prevista_admissao"]
            dt_fim_aq = (datetime.strptime(dt_inicio_aq, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")
            dt_lim_conc = (datetime.strptime(dt_fim_aq, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")
            cur.execute(
                f"""
                INSERT INTO periodos_aquisitivos (
                    colaborador_id, inicio_aquisitivo, fim_aquisitivo, limite_concessivo,
                    faltas_injustificadas, dias_direito, dias_gozados, saldo_dias, situacao,
                    criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},0,30,0,30,'em_aquisicao',{p},{p});
            """,
                (novo_colab_id, dt_inicio_aq, dt_fim_aq, dt_lim_conc, agora, agora),
            )

            # 10. Gera evento eSocial S-2200 oficial (v_S_01_02_00) dentro da transação caso não exista ativo
            cur.execute(f"SELECT * FROM empresas WHERE id = {p};", (adm["empresa_id"],))
            emp = fetchone_dict(cur, self.db_path)
            filial = None
            if adm.get("filial_id"):
                cur.execute(f"SELECT * FROM filiais WHERE id = {p};", (adm["filial_id"],))
                filial = fetchone_dict(cur, self.db_path)
            cur.execute(
                f"""
                SELECT id FROM esocial_eventos
                WHERE empresa_id = {p} AND tipo_evento = 'S-2200'
                  AND status NOT IN ('rejeitado', 'excluido')
                  AND (identificador_origem = {p} OR identificador_origem = {p});
            """,
                (adm["empresa_id"], f"ADM:{admissao_id}", str(novo_colab_id)),
            )
            if not cur.fetchone():
                xml_s2200, erros_xml = gerar_xml_s2200(adm, emp, matricula=matricula_gerada, filial=filial, escala=escala, ambiente="homologacao")
                if erros_xml:
                    raise PlataformaValidacaoException("Falha ao gerar S-2200 na efetivação: " + "; ".join(erros_xml))
                ok_x, erros_x = validar_xml_esocial("S-2200", xml_s2200)
                if not ok_x:
                    raise PlataformaValidacaoException("XML S-2200 inválido no schema S-1.2: " + "; ".join(erros_x))
                cur.execute(
                    f"""
                    INSERT INTO esocial_eventos (
                        empresa_id, tipo_evento, identificador_origem, ambiente, status,
                        xml_conteudo, numero_recibo, codigo_resposta, mensagem_resposta, criado_por, criado_em
                    ) VALUES ({p},'S-2200',{p},'homologacao','validado',{p},NULL,'VALIDADO_SCHEMA',{p},{p},{p});
                """,
                    (
                        adm["empresa_id"],
                        str(novo_colab_id),
                        xml_s2200,
                        "XML S-2200 gerado na efetivação e validado no leiaute S-1.2 (aguardando transmissão com certificado ICP-Brasil).",
                        aprovador,
                        agora,
                    ),
                )

            # 11. Registra pendência de contrato de experiência na Central (RF-151, RN-079)
            if str(adm.get("tipo_contrato") or "").lower() == "experiencia":
                prazo_1 = int(adm.get("prazo_experiencia_dias") or 45)
                dt_venc_exp = (datetime.strptime(dt_inicio_aq, "%Y-%m-%d") + timedelta(days=prazo_1)).strftime("%Y-%m-%d")
                cur.execute(
                    f"""
                    INSERT INTO pendencias_operacionais (
                        empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                        colaborador_id, prazo_limite, responsavel, status, criado_em
                    ) VALUES ({p},'Admissão','experiencia_vencendo',{p},{p},'alta',{p},{p},'DP / Gestor','pendente',{p});
                """,
                    (
                        adm["empresa_id"],
                        f"Término do 1º Período de Experiência ({prazo_1} dias) — {adm['candidato_nome']}",
                        f"Colaborador {adm['candidato_nome']} ({matricula_gerada}) atinge o término em {dt_venc_exp}.",
                        novo_colab_id,
                        dt_venc_exp,
                        agora,
                    ),
                )

            # 12. Atualiza status final da admissão e grava workflow de aprovação
            cur.execute(
                f"""
                UPDATE admissoes
                SET status = 'efetivado', aprovado_por = {p}, aprovado_em = {p},
                    justificativa_aprovacao = {p}, efetivado_por = {p}, efetivado_em = {p},
                    colaborador_id = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (aprovador, agora, (justificativa or "Admissão aprovada e efetivada").strip(), aprovador, agora, novo_colab_id, agora, admissao_id),
            )
            cur.execute(
                f"""
                INSERT INTO aprovacoes_workflow (
                    empresa_id, modulo, processo_tipo, processo_id, solicitante,
                    aprovador, status, justificativa, criado_em, atualizado_em
                ) VALUES ({p},'Admissao','admissao_efetivacao',{p},{p},{p},'aprovado',{p},{p},{p});
            """,
                (adm["empresa_id"], admissao_id, adm["criado_por"], aprovador, justificativa or "Efetivação homologada", agora, agora),
            )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="aprovacao_efetivacao",
            registro_tipo="admissoes",
            registro_id=admissao_id,
            usuario=aprovador,
            valor_anterior=st_adm,
            valor_novo="efetivado",
            detalhes=f"Admissão #{admissao_id} aprovada e efetivada. Colaborador ID {novo_colab_id} ({matricula_gerada}).",
            empresa_id=adm["empresa_id"],
        )
        return {
            "sucesso": True,
            "admissao_id": admissao_id,
            "colaborador_id": novo_colab_id,
            "matricula": matricula_gerada,
            "status": "efetivado",
            "mensagem": f"Admissão aprovada e efetivada! Colaborador {adm['candidato_nome']} ativado sob matrícula {matricula_gerada}.",
        }

    def reprovar_admissao(
        self,
        admissao_id: int,
        aprovador: str,
        motivo: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not motivo or not str(motivo).strip():
            raise PlataformaValidacaoException("Justificativa/motivo é obrigatório para reprovar uma admissão (RF-020).")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            adm = self._buscar_admissao_cursor(cur, admissao_id, empresa_id=empresa_id)
            if str(adm["status"]).lower() in ("efetivado", "aprovada"):
                raise PlataformaValidacaoException("Admissão já efetivada não pode ser reprovada.")
            if str(adm["criado_por"]).strip().lower() == str(aprovador).strip().lower():
                raise PlataformaAcessoNegadoException("Violação de Segregação de Funções (RN-080): Solicitante e avaliador devem ser distintos.")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"""
                UPDATE admissoes
                SET status = 'reprovado', motivo_reprovacao = {p}, aprovado_por = {p}, aprovado_em = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (str(motivo).strip(), aprovador, agora, agora, admissao_id),
            )
            cur.execute(
                f"""
                INSERT INTO aprovacoes_workflow (
                    empresa_id, modulo, processo_tipo, processo_id, solicitante,
                    aprovador, status, justificativa, criado_em, atualizado_em
                ) VALUES ({p},'Admissao','admissao_reprovacao',{p},{p},{p},'reprovado',{p},{p},{p});
            """,
                (adm["empresa_id"], admissao_id, adm["criado_por"], aprovador, str(motivo).strip(), agora, agora),
            )
            conn.commit()
        finally:
            conn.close()

        self._registrar_auditoria(
            modulo="Admissao",
            operacao="reprovacao",
            registro_tipo="admissoes",
            registro_id=admissao_id,
            usuario=aprovador,
            valor_anterior=adm["status"],
            valor_novo="reprovado",
            detalhes=f"Admissão #{admissao_id} reprovada: {motivo}",
            empresa_id=adm["empresa_id"],
        )
        return self.obter_admissao(admissao_id, empresa_id=empresa_id)

    def obter_painel_admissao(
        self,
        admissao_id: int,
        empresa_id: Optional[str] = None,
        perfil_usuario: str = "gestor_rh",
    ) -> Dict[str, Any]:
        """
        Cartão Único de Acompanhamento Admissional (Seção 14):
        Consolida as 10 etapas (RF-011 a RF-020) com cálculo real de status, pendências e % de conclusão.
        """
        adm = self.obter_admissao(admissao_id, empresa_id=empresa_id, perfil_usuario=perfil_usuario)
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT nome_fantasia, razao_social FROM empresas WHERE id = {p};", (adm["empresa_id"],))
            emp = fetchone_dict(cur, self.db_path) or {}
            fil = {}
            if adm.get("filial_id"):
                cur.execute(f"SELECT nome FROM filiais WHERE id = {p};", (adm["filial_id"],))
                fil = fetchone_dict(cur, self.db_path) or {}
            av = self._avaliar_regras_admissao(cur, adm)
        finally:
            conn.close()

        chk = adm.get("checklist") or []
        obrig_chk = [c for c in chk if c.get("obrigatorio")]
        obrig_val = [c for c in obrig_chk if c.get("status") in ("validado", "dispensado")]
        obrig_rej = [c for c in obrig_chk if c.get("status") == "rejeitado"]
        contratos = adm.get("contratos") or []
        aso = adm.get("aso")
        benefs = adm.get("beneficios") or []
        ev_esocial = adm.get("esocial_eventos") or []
        val_snaps = adm.get("validacoes") or []
        aplic_esocial = avaliar_aplicabilidade_esocial(adm, ev_esocial)

        st_aso = "nao_iniciado"
        pend_aso = []
        if aso:
            res_a = str(aso.get("resultado") or "").lower()
            ex_a = str(aso.get("status_exame") or "").lower()
            if res_a == "inapto":
                st_aso = "reprovado"
                pend_aso.append("Resultado INAPTO registrado no ASO.")
            elif res_a == "apto" and ex_a == "realizado":
                st_aso = "concluido"
            else:
                st_aso = "em_analise" if ex_a in ("agendado", "pendente_analise") else "pendente"
                pend_aso.append(f"ASO em andamento ({ex_a}/{res_a}).")
        else:
            st_aso = "pendente"
            pend_aso.append("ASO Admissional ainda não cadastrado (RN-009).")

        st_chk = (
            "reprovado" if obrig_rej
            else ("concluido" if obrig_chk and len(obrig_val) == len(obrig_chk) else ("em_andamento" if any(c["status"] != "pendente" for c in chk) else "pendente"))
        )
        pend_chk = [c["item_descricao"] for c in obrig_chk if c["status"] not in ("validado", "dispensado")]

        st_val = "concluido" if av["apto_efetivacao"] and val_snaps else ("reprovado" if av["invalidos"] else ("pendente" if not val_snaps else "em_andamento"))
        st_ctr = "concluido" if contratos else "nao_iniciado"
        st_esoc = (
            "reprovado" if any(e["status"] == "rejeitado" for e in ev_esocial)
            else ("concluido" if any(e["tipo_evento"] == "S-2200" and e["status"] != "rejeitado" for e in ev_esocial)
                  else ("em_andamento" if ev_esocial else "nao_iniciado"))
        )
        st_jorn = "concluido" if adm.get("escala_id") else "pendente"
        st_cc = "concluido" if adm.get("centro_custo_id") else "nao_iniciado"
        st_ben = "concluido" if benefs else "nao_iniciado"

        st_proc = str(adm.get("status") or "").lower()
        if st_proc in ("efetivado", "aprovada"):
            st_aprov = "concluido"
        elif st_proc == "reprovado":
            st_aprov = "reprovado"
        elif st_proc == "cancelado":
            st_aprov = "bloqueado"
        elif not av["apto_efetivacao"]:
            st_aprov = "bloqueado"
        elif st_proc == "aprovado":
            st_aprov = "em_analise"
        else:
            st_aprov = "pendente"

        etapas = [
            {
                "ordem": "01",
                "rf": "RF-011",
                "nome": "Registrar Admissão",
                "status": "concluido",
                "responsavel": adm.get("criado_por"),
                "data_conclusao": adm.get("criado_em"),
                "pendencias": [],
                "evidencias": f"Processo {adm.get('codigo_processo') or adm['id']}",
            },
            {
                "ordem": "02",
                "rf": "RF-012",
                "nome": "Checklist Admissional",
                "status": st_chk,
                "responsavel": chk[0].get("atualizado_por") if chk else None,
                "data_conclusao": max((c.get("validado_em") or "" for c in obrig_val), default=None) if st_chk == "concluido" else None,
                "pendencias": pend_chk,
                "evidencias": f"{len(obrig_val)}/{len(obrig_chk)} obrigatórios validados",
            },
            {
                "ordem": "03",
                "rf": "RF-013",
                "nome": "Validação Admissional",
                "status": st_val,
                "responsavel": val_snaps[0].get("validado_por") if val_snaps else None,
                "data_conclusao": val_snaps[0].get("validado_em") if val_snaps else None,
                "pendencias": av["pendencias_impeditivas"],
                "evidencias": f"{len(av['aprovados'])} critérios aprovados",
            },
            {
                "ordem": "04",
                "rf": "RF-014",
                "nome": "Contrato de Trabalho",
                "status": st_ctr,
                "responsavel": contratos[0].get("gerado_por") if contratos else None,
                "data_conclusao": contratos[0].get("gerado_em") if contratos else None,
                "pendencias": [] if contratos else ["Contrato PDF ainda não gerado."],
                "evidencias": f"v{contratos[0]['versao']} ({'Formalizado' if contratos[0].get('formalizado') else 'Minuta'})" if contratos else "Sem contrato",
            },
            {
                "ordem": "05",
                "rf": "RF-015",
                "nome": "Integração eSocial",
                "status": st_esoc,
                "responsavel": ev_esocial[0].get("criado_por") if ev_esocial else None,
                "data_conclusao": ev_esocial[0].get("criado_em") if ev_esocial else None,
                "pendencias": [] if st_esoc == "concluido" else [aplic_esocial["motivo"]],
                "evidencias": f"{len(ev_esocial)} evento(s): {', '.join(e['tipo_evento'] + ' (' + e['status'] + ')' for e in ev_esocial[:3])}" if ev_esocial else "Aguardando geração",
            },
            {
                "ordem": "06",
                "rf": "RF-016",
                "nome": "Exame Admissional (ASO)",
                "status": st_aso,
                "responsavel": aso.get("criado_por") if aso else None,
                "data_conclusao": aso.get("data_emissao") if st_aso == "concluido" and aso else None,
                "pendencias": pend_aso,
                "evidencias": f"ASO {aso.get('resultado')} (validade {aso.get('data_validade')})" if aso else "Sem ASO",
            },
            {
                "ordem": "07",
                "rf": "RF-017",
                "nome": "Jornada Inicial",
                "status": st_jorn,
                "responsavel": adm.get("criado_por") if st_jorn == "concluido" else None,
                "data_conclusao": adm.get("jornada_vigencia_inicio") if st_jorn == "concluido" else None,
                "pendencias": [] if st_jorn == "concluido" else ["Selecionar escala ativa (RN-008)."],
                "evidencias": adm.get("jornada_descricao") or "Não vinculada",
            },
            {
                "ordem": "08",
                "rf": "RF-018",
                "nome": "Centro de Custo",
                "status": st_cc,
                "responsavel": adm.get("criado_por") if st_cc == "concluido" else None,
                "data_conclusao": adm.get("centro_custo_vigencia") if st_cc == "concluido" else None,
                "pendencias": [] if st_cc == "concluido" else ["Centro de custo opcional/não selecionado."],
                "evidencias": adm.get("centro_custo_id") or "Não vinculado",
            },
            {
                "ordem": "09",
                "rf": "RF-019",
                "nome": "Benefícios",
                "status": st_ben,
                "responsavel": benefs[0].get("definido_por") if benefs else None,
                "data_conclusao": benefs[0].get("definido_em") if benefs else None,
                "pendencias": [] if benefs else ["Nenhum benefício associado até o momento."],
                "evidencias": f"{len(benefs)} benefício(s) associado(s)",
            },
            {
                "ordem": "10",
                "rf": "RF-020",
                "nome": "Aprovação & Efetivação",
                "status": st_aprov,
                "responsavel": adm.get("aprovado_por"),
                "data_conclusao": adm.get("efetivado_em") or adm.get("aprovado_em"),
                "pendencias": av["pendencias_impeditivas"] if st_aprov in ("bloqueado", "pendente") else [],
                "evidencias": f"Colaborador #{adm['colaborador_id']}" if adm.get("colaborador_id") else adm.get("status"),
            },
        ]

        concluidas = sum(1 for e in etapas if e["status"] == "concluido")
        pendentes_et = sum(1 for e in etapas if e["status"] != "concluido")
        proxima = next((f"{e['rf']} — {e['nome']}" for e in etapas if e["status"] != "concluido"), "Processo Concluído")
        progresso_pct = round((concluidas / len(etapas)) * 100)

        return {
            "identificacao": {
                "admissao_id": adm["id"],
                "codigo_processo": adm.get("codigo_processo"),
                "candidato_nome": adm["candidato_nome"],
                "cpf_mascarado": adm["candidato_cpf_mascarado"],
                "cargo": adm["cargo"],
                "setor": adm["setor"],
                "empresa": emp.get("nome_fantasia") or emp.get("razao_social") or adm["empresa_id"],
                "filial": fil.get("nome") or adm.get("filial_id") or "--",
                "data_prevista_admissao": adm["data_prevista_admissao"],
                "responsavel": adm["criado_por"],
                "data_abertura": adm["criado_em"],
                "status": adm["status"],
                "colaborador_id": adm.get("colaborador_id"),
            },
            "resumo": {
                "progresso_percentual": progresso_pct,
                "etapas_concluidas": concluidas,
                "etapas_pendentes": pendentes_et,
                "total_etapas": len(etapas),
                "pendencias_impeditivas": av["pendencias_impeditivas"],
                "proxima_etapa": proxima,
                "responsavel_atual": adm.get("aprovado_por") or adm.get("criado_por"),
                "esocial_aplicabilidade": aplic_esocial,
            },
            "etapas": etapas,
            "admissao": adm,
        }
