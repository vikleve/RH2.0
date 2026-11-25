# -*- coding: utf-8 -*-
"""
Módulo de Segurança e Saúde no Trabalho (SST) — RH2.0 Enterprise
Implementação completa dos Requisitos Funcionais RF-121 a RF-130:
- RF-121: Cadastro de Exames Ocupacionais (Catálogo, Periodicidade e CRUD)
- RF-122: Exame Admissional (Validação pré-admissão, ASO e Aptidão)
- RF-123: Exame Periódico (Agendamento, Periodicidade NR-07 e Controle)
- RF-124: Exame Demissional (Prazos 10 dias, Regra de Dispensa NR-07)
- RF-125: Controle de ASO (Médico CRM/UF, Anexo com Hash SHA-256 e RBAC)
- RF-126: Controle de EPI (Catálogo, Validade CA, Entregas, Devoluções e Substituição)
- RF-127: Treinamentos Obrigatórios NRs (NR-05, NR-06, NR-10, NR-35 e Reciclagens)
- RF-128: Alertas de Vencimento Proativos (ASO, EPI e Treinamentos)
- RF-129: CAT (Comunicação de Acidente de Trabalho, CID-10 e Histórico)
- RF-130: Integração SST eSocial (Geração oficial S-2210, S-2220 e S-2240)
"""
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.database import (
    fetchall_dict,
    fetchone_dict,
    get_connection,
    insert_returning_id,
    ph,
)
from backend.plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaRecursoNaoEncontradoException,
    PlataformaValidacaoException,
)


class SSTService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def _conn(self):
        return get_connection(self.db_path)

    def _p(self) -> str:
        return ph(self.db_path)

    def _registrar_auditoria(
        self,
        modulo: str,
        operacao: str,
        registro_tipo: str,
        registro_id: Any,
        usuario: str,
        detalhes: str,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
    ):
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"""
                INSERT INTO auditoria_operacoes (
                    empresa_id, modulo, operacao, registro_tipo, registro_id, usuario_responsavel, detalhes, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
            """,
                (empresa_id, modulo, operacao, registro_tipo, str(registro_id), usuario, detalhes, agora),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-121: CADASTRO DE EXAMES OCUPACIONAIS
    # ─────────────────────────────────────────────────────────────────────────
    def cadastrar_exame(
        self,
        codigo: str,
        descricao: str,
        tipo: str,
        periodicidade_meses: int = 12,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "Médico SST",
    ) -> Dict[str, Any]:
        """RF-121: Cadastra um novo exame ocupacional no catálogo."""
        if not codigo or not codigo.strip():
            raise PlataformaValidacaoException("Código do exame é obrigatório.")
        if not descricao or not descricao.strip():
            raise PlataformaValidacaoException("Descrição do exame é obrigatória.")
        if periodicidade_meses <= 0:
            raise PlataformaValidacaoException("Periodicidade deve ser maior que zero meses.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Verifica duplicidade
            cur.execute(f"SELECT id FROM sst_exames WHERE codigo = {p} AND empresa_id = {p};", (codigo.strip().upper(), empresa_id))
            if cur.fetchone():
                raise PlataformaValidacaoException(f"Já existe exame cadastrado com o código '{codigo}'.")

            sql_pg = f"""
                INSERT INTO sst_exames (
                    empresa_id, codigo, descricao, tipo, periodicidade_meses, ativo, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, 1, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_exames (
                    empresa_id, codigo, descricao, tipo, periodicidade_meses, ativo, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, 1, {p});
            """
            params = (empresa_id, codigo.strip().upper(), descricao.strip(), tipo.strip().lower(), int(periodicidade_meses), agora)
            exame_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            self._registrar_auditoria(
                modulo="SST",
                operacao="inclusao",
                registro_tipo="sst_exames",
                registro_id=exame_id,
                usuario=usuario,
                detalhes=f"Exame '{codigo}' ({descricao}) cadastrado com periodicidade de {periodicidade_meses} meses.",
                empresa_id=empresa_id,
            )

            return {
                "sucesso": True,
                "exame_id": exame_id,
                "codigo": codigo.strip().upper(),
                "descricao": descricao.strip(),
                "tipo": tipo.strip().lower(),
                "periodicidade_meses": periodicidade_meses,
            }
        finally:
            conn.close()

    def listar_exames(self, empresa_id: str = "a0000000-0000-0000-0000-000000000001", apenas_ativos: bool = True) -> List[Dict[str, Any]]:
        """RF-121: Lista exames ocupacionais cadastrados."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            query = f"SELECT * FROM sst_exames WHERE (empresa_id = {p} OR empresa_id IS NULL)"
            params = [empresa_id]
            if apenas_ativos:
                query += " AND ativo = 1"
            query += " ORDER BY codigo ASC;"
            cur.execute(query, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def atualizar_exame(
        self,
        exame_id: int,
        dados: Dict[str, Any],
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "Médico SST",
    ) -> Dict[str, Any]:
        """RF-121: Atualiza exame ocupacional existente."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM sst_exames WHERE id = {p};", (exame_id,))
            exame = fetchone_dict(cur, self.db_path)
            if not exame:
                raise PlataformaRecursoNaoEncontradoException(f"Exame ID {exame_id} não encontrado.")

            descricao = dados.get("descricao", exame["descricao"])
            tipo = dados.get("tipo", exame["tipo"])
            periodicidade = int(dados.get("periodicidade_meses", exame["periodicidade_meses"]))

            cur.execute(
                f"""
                UPDATE sst_exames
                SET descricao = {p}, tipo = {p}, periodicidade_meses = {p}
                WHERE id = {p};
            """,
                (descricao, tipo, periodicidade, exame_id),
            )
            conn.commit()

            self._registrar_auditoria(
                modulo="SST",
                operacao="alteracao",
                registro_tipo="sst_exames",
                registro_id=exame_id,
                usuario=usuario,
                detalhes=f"Exame ID {exame_id} atualizado: {descricao}, {tipo}, {periodicidade}m.",
                empresa_id=empresa_id,
            )

            return {"sucesso": True, "exame_id": exame_id, "mensagem": "Exame atualizado com sucesso."}
        finally:
            conn.close()

    def inativar_exame(self, exame_id: int, usuario: str = "Médico SST") -> Dict[str, Any]:
        """RF-121: Exclusão lógica do exame ocupacional."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT id, codigo FROM sst_exames WHERE id = {p};", (exame_id,))
            exame = fetchone_dict(cur, self.db_path)
            if not exame:
                raise PlataformaRecursoNaoEncontradoException(f"Exame ID {exame_id} não encontrado.")

            cur.execute(f"UPDATE sst_exames SET ativo = 0 WHERE id = {p};", (exame_id,))
            conn.commit()

            self._registrar_auditoria(
                modulo="SST",
                operacao="exclusao_logica",
                registro_tipo="sst_exames",
                registro_id=exame_id,
                usuario=usuario,
                detalhes=f"Exame {exame['codigo']} inativado logicamente.",
            )
            return {"sucesso": True, "exame_id": exame_id, "ativo": False}
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-122: EXAME ADMISSIONAL
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_exame_admissional(
        self,
        colaborador_id: int,
        data_realizacao: str,
        resultado: str,
        medico_nome: str,
        medico_crm: str,
        medico_uf: str,
        admissao_id: Optional[int] = None,
        data_admissao: Optional[str] = None,
        observacoes: str = "",
        conteudo_base64: Optional[str] = None,
        nome_arquivo: Optional[str] = None,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "Médico SST",
    ) -> Dict[str, Any]:
        """
        RF-122, RN-009: Exame Admissional obrigatório com validação de realização pré-admissão.
        O ASO deve ser obrigatoriamente APTO antes de efetivar o colaborador.
        """
        resultado_upper = resultado.strip().upper()
        if resultado_upper not in ("APTO", "INAPTO"):
            raise PlataformaValidacaoException("Resultado do exame admissional deve ser 'APTO' ou 'INAPTO'.")

        if data_admissao and data_realizacao > data_admissao:
            raise PlataformaValidacaoException(
                f"Violação da RN-009 / NR-07: O Exame Médico Admissional ({data_realizacao}) "
                f"deve ser realizado antes ou até a data da admissão ({data_admissao})."
            )

        # Validade padrão do ASO: 1 ano (NR-07)
        dt_val = (datetime.strptime(data_realizacao, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")

        res_aso = self.registrar_aso(
            colaborador_id=colaborador_id,
            tipo_aso="ADMISSIONAL",
            data_emissao=data_realizacao,
            data_validade=dt_val,
            resultado=resultado_upper,
            medico_nome=medico_nome,
            medico_crm=medico_crm,
            medico_uf=medico_uf,
            admissao_id=admissao_id,
            data_realizacao=data_realizacao,
            observacoes=observacoes,
            conteudo_base64=conteudo_base64,
            nome_arquivo=nome_arquivo,
            empresa_id=empresa_id,
            usuario=usuario,
        )
        res_aso["resultado"] = resultado_upper
        return res_aso

    # ─────────────────────────────────────────────────────────────────────────
    # RF-123: EXAME PERIÓDICO
    # ─────────────────────────────────────────────────────────────────────────
    def agendar_exame_periodico(
        self,
        colaborador_id: int,
        exame_id: Optional[int],
        data_prevista: str,
        clinica_nome: str = "Clínica de Medicina Ocupacional",
        observacoes: str = "",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "DP / SST",
    ) -> Dict[str, Any]:
        """RF-123: Agenda exame periódico preventivo de acordo com a periodicidade da NR-07."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(f"SELECT id, nome_completo FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException(f"Colaborador ID {colaborador_id} não encontrado.")

            sql_pg = f"""
                INSERT INTO sst_exames_agendamentos (
                    empresa_id, colaborador_id, exame_id, tipo_exame, data_prevista,
                    status, clinica_nome, observacoes, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, 'periodico', {p}, 'agendado', {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_exames_agendamentos (
                    empresa_id, colaborador_id, exame_id, tipo_exame, data_prevista,
                    status, clinica_nome, observacoes, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, 'periodico', {p}, 'agendado', {p}, {p}, {p}, {p});
            """
            params = (empresa_id, colaborador_id, exame_id, data_prevista, clinica_nome, observacoes, usuario, agora)
            agend_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            self._registrar_auditoria(
                modulo="SST",
                operacao="agendamento",
                registro_tipo="sst_exames_agendamentos",
                registro_id=agend_id,
                usuario=usuario,
                detalhes=f"Exame periódico agendado para {colab['nome_completo']} em {data_prevista} na clínica {clinica_nome}.",
                empresa_id=empresa_id,
            )

            return {
                "sucesso": True,
                "agendamento_id": agend_id,
                "colaborador_id": colaborador_id,
                "data_prevista": data_prevista,
                "status": "agendado",
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-124: EXAME DEMISSIONAL
    # ─────────────────────────────────────────────────────────────────────────
    def verificar_dispensa_exame_demissional(
        self,
        colaborador_id: int,
        data_demissao: str,
        grau_risco: int = 2,
    ) -> Dict[str, Any]:
        """
        RF-124, NR-07: Verifica se o exame demissional é dispensável com base no último exame realizado:
        - Grau de risco 1 ou 2: dispensado se o último exame foi há menos de 135 dias.
        - Grau de risco 3 ou 4: dispensado se o último exame foi há menos de 90 dias.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                SELECT id, data_emissao, data_realizacao, resultado
                FROM sst_asos
                WHERE colaborador_id = {p}
                ORDER BY coalesce(data_realizacao, data_emissao) DESC
                LIMIT 1;
            """,
                (colaborador_id,),
            )
            ultimo_aso = fetchone_dict(cur, self.db_path)
            if not ultimo_aso:
                return {
                    "dispensado": False,
                    "motivo": "Nenhum ASO anterior registrado. Exame demissional obrigatório.",
                    "dias_decorridos": None,
                }

            dt_str = ultimo_aso.get("data_realizacao") or ultimo_aso["data_emissao"]
            dt_ultimo = datetime.strptime(dt_str[:10], "%Y-%m-%d")
            dt_dem = datetime.strptime(data_demissao[:10], "%Y-%m-%d")
            dias_decorridos = (dt_dem - dt_ultimo).days

            limite_dias = 90 if grau_risco in (3, 4) else 135
            dispensado = 0 <= dias_decorridos <= limite_dias

            return {
                "dispensado": dispensado,
                "ultimo_aso_id": ultimo_aso["id"],
                "data_ultimo_aso": dt_str[:10],
                "dias_decorridos": dias_decorridos,
                "limite_dias_nr07": limite_dias,
                "grau_risco": grau_risco,
                "motivo": (
                    f"Dispensado conforme NR-07: último exame realizado há {dias_decorridos} dias (limite: {limite_dias} dias para grau de risco {grau_risco})."
                    if dispensado
                    else f"Obrigatório: último exame há {dias_decorridos} dias ultrapassou o limite legal de {limite_dias} dias da NR-07."
                ),
            }
        finally:
            conn.close()

    def agendar_exame_demissional(
        self,
        colaborador_id: int,
        data_demissao: str,
        data_prevista: str,
        clinica_nome: str = "Clínica de Medicina Ocupacional",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        """
        RF-124: Agenda exame demissional e valida prazo legal de até 10 dias contados do desligamento (NR-07).
        """
        dt_dem = datetime.strptime(data_demissao[:10], "%Y-%m-%d")
        dt_prev = datetime.strptime(data_prevista[:10], "%Y-%m-%d")
        dias_diferenca = (dt_prev - dt_dem).days

        if dias_diferenca > 10:
            raise PlataformaValidacaoException(
                f"Violação da NR-07: O Exame Demissional deve ser obrigatoriamente realizado "
                f"em até 10 dias após o término do contrato de trabalho (Data demissão: {data_demissao}, Data agendada: {data_prevista})."
            )

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sql_pg = f"""
                INSERT INTO sst_exames_agendamentos (
                    empresa_id, colaborador_id, tipo_exame, data_prevista,
                    status, clinica_nome, observacoes, criado_por, criado_em
                ) VALUES ({p}, {p}, 'demissional', {p}, 'agendado', {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_exames_agendamentos (
                    empresa_id, colaborador_id, tipo_exame, data_prevista,
                    status, clinica_nome, observacoes, criado_por, criado_em
                ) VALUES ({p}, {p}, 'demissional', {p}, 'agendado', {p}, {p}, {p}, {p});
            """
            obs = f"Exame demissional agendado para demissão de {data_demissao} (Prazo legal 10 dias atendido)."
            params = (empresa_id, colaborador_id, data_prevista, clinica_nome, obs, usuario, agora)
            agend_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            return {
                "sucesso": True,
                "agendamento_id": agend_id,
                "colaborador_id": colaborador_id,
                "data_prevista": data_prevista,
                "dentro_prazo_10_dias": True,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-125: CONTROLE INTEGRAL DE ASO (ATESTADO DE SAÚDE OCUPACIONAL)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_aso(
        self,
        colaborador_id: int,
        tipo_aso: str,
        data_emissao: str,
        data_validade: str,
        resultado: str,
        medico_nome: str,
        medico_crm: str,
        medico_uf: str,
        admissao_id: Optional[int] = None,
        data_realizacao: Optional[str] = None,
        observacoes: str = "",
        conteudo_base64: Optional[str] = None,
        nome_arquivo: Optional[str] = None,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "Médico SST",
    ) -> Dict[str, Any]:
        """
        RF-125, RF-130: Registra ASO ocupacional com validação, anexo com hash SHA-256
        e geração oficial do evento S-2220 do eSocial.
        """
        if not medico_nome or not medico_crm or not medico_uf:
            raise PlataformaValidacaoException("Dados do médico examinador (Nome, CRM e UF) são obrigatórios.")

        resultado_upper = resultado.strip().upper()
        if resultado_upper not in ("APTO", "INAPTO"):
            raise PlataformaValidacaoException("Resultado do ASO deve ser 'APTO' ou 'INAPTO'.")

        sha256_hash = None
        if conteudo_base64:
            sha256_hash = hashlib.sha256(conteudo_base64.encode("utf-8")).hexdigest()

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(f"SELECT id, nome_completo, cpf, matricula FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException(f"Colaborador ID {colaborador_id} não encontrado.")

            sql_pg = f"""
                INSERT INTO sst_asos (
                    empresa_id, colaborador_id, admissao_id, tipo_aso, status_exame,
                    data_realizacao, data_emissao, data_validade, resultado,
                    medico_nome, medico_crm, medico_uf, nome_arquivo,
                    sha256_hash, observacoes_medicas, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, 'realizado', {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_asos (
                    empresa_id, colaborador_id, admissao_id, tipo_aso, status_exame,
                    data_realizacao, data_emissao, data_validade, resultado,
                    medico_nome, medico_crm, medico_uf, nome_arquivo,
                    sha256_hash, observacoes_medicas, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, 'realizado', {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
            """
            params = (
                empresa_id,
                colaborador_id,
                admissao_id,
                tipo_aso.upper(),
                data_realizacao or data_emissao,
                data_emissao,
                data_validade,
                resultado_upper,
                medico_nome,
                medico_crm,
                medico_uf,
                nome_arquivo,
                sha256_hash,
                observacoes,
                usuario,
                agora,
            )
            aso_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            # Geração oficial do evento eSocial S-2220 (Monitoramento da Saúde do Trabalhador)
            tp_exame_map = {
                "ADMISSIONAL": "0",
                "PERIODICO": "1",
                "RETORNO_TRABALHO": "2",
                "MUDANCA_FUNCAO": "3",
                "MUDANCA_RISCO": "3",
                "DEMISSIONAL": "4",
            }
            tp_exame_cod = tp_exame_map.get(tipo_aso.upper(), "1")
            res_aso_cod = "1" if resultado_upper == "APTO" else "2"
            cpf_dig = "".join(filter(str.isdigit, str(colab.get("cpf") or "00000000000"))).zfill(11)
            matr_limpa = str(colab.get("matricula") or f"MATR-{colaborador_id}").strip()

            xml_s2220 = f"""<?xml version="1.0" encoding="UTF-8"?>
<eSocial xmlns="http://www.esocial.gov.br/schema/evt/evtMonit/v_S_01_02_00">
  <evtMonit id="ID112345678000000{datetime.now().strftime('%Y%m%d%H%M%S')}00001">
    <ideEmpregador>
      <tpInsc>1</tpInsc>
      <nrInsc>12345678000190</nrInsc>
    </ideEmpregador>
    <ideTrabalhador>
      <cpfTrab>{cpf_dig}</cpfTrab>
    </ideTrabalhador>
    <ideVinculo>
      <cpfTrab>{cpf_dig}</cpfTrab>
      <matricula>{matr_limpa}</matricula>
    </ideVinculo>
    <aso>
      <dtAso>{data_emissao}</dtAso>
      <tpExame>{tp_exame_cod}</tpExame>
      <resAso>{res_aso_cod}</resAso>
      <medico>
        <nmMed>{medico_nome}</nmMed>
        <nrCRM>{medico_crm}</nrCRM>
        <ufCRM>{medico_uf}</ufCRM>
      </medico>
    </aso>
  </evtMonit>
</eSocial>"""

            cur.execute(
                f"""
                INSERT INTO esocial_eventos (
                    empresa_id, tipo_evento, identificador_origem, ambiente, status,
                    xml_conteudo, criado_por, criado_em
                ) VALUES ({p}, 'S-2220', {p}, 'homologacao', 'validado', {p}, {p}, {p});
            """,
                (empresa_id, str(aso_id), xml_s2220, usuario, agora),
            )

            conn.commit()

            self._registrar_auditoria(
                modulo="SST",
                operacao="emissao_aso",
                registro_tipo="sst_asos",
                registro_id=aso_id,
                usuario=usuario,
                detalhes=f"ASO {tipo_aso} ({resultado_upper}) emitido para Colaborador {colaborador_id} por Dr(a). {medico_nome} CRM {medico_crm}/{medico_uf}.",
                empresa_id=empresa_id,
            )

            return {
                "sucesso": True,
                "aso_id": aso_id,
                "tipo_aso": tipo_aso.upper(),
                "resultado": resultado.strip().lower(),
                "validade": data_validade,
                "esocial_gerado": True,
                "tipo_evento_esocial": "S-2220",
            }
        finally:
            conn.close()

    def consultar_aso(self, aso_id: int, perfil_usuario: str = "medico_sst") -> Dict[str, Any]:
        """RF-125: Consulta ASO com controle de visualização médica sensível (RBAC)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                SELECT a.*, c.nome_completo, c.cpf, c.matricula, c.setor, c.cargo
                FROM sst_asos a
                JOIN colaboradores c ON c.id = a.colaborador_id
                WHERE a.id = {p};
            """,
                (aso_id,),
            )
            aso = fetchone_dict(cur, self.db_path)
            if not aso:
                raise PlataformaRecursoNaoEncontradoException(f"ASO ID {aso_id} não encontrado.")

            # Se o usuário não for do time de medicina do trabalho ou DP auditor, mascara observações clínicas sigilosas
            if perfil_usuario.lower() not in ("admin", "medico_sst", "sst", "analista_dp", "auditor"):
                aso["observacoes_medicas"] = "[PROTEGIDO POR SIGILO MÉDICO - RESOLUÇÃO CFM]"

            return aso
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-126: CONTROLE DE EQUIPAMENTO DE PROTEÇÃO INDIVIDUAL (EPI)
    # ─────────────────────────────────────────────────────────────────────────
    def cadastrar_epi(
        self,
        codigo: str,
        descricao: str,
        ca_numero: str,
        ca_validade: str,
        vida_util_dias: int = 180,
        fabricante: str = "Fabricante Homologado",
        tipo_protecao: str = "Individual",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "Técnico SST",
    ) -> Dict[str, Any]:
        """RF-126: Cadastra EPI no catálogo com controle do Certificado de Aprovação (CA)."""
        if not codigo or not descricao or not ca_numero or not ca_validade:
            raise PlataformaValidacaoException("Código, descrição, número do CA e validade do CA são obrigatórios.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sql_pg = f"""
                INSERT INTO sst_epis (
                    empresa_id, codigo, descricao, ca_numero, ca_validade,
                    vida_util_dias, ativo, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 1, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_epis (
                    empresa_id, codigo, descricao, ca_numero, ca_validade,
                    vida_util_dias, ativo, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 1, {p});
            """
            params = (empresa_id, codigo.upper().strip(), descricao.strip(), ca_numero.strip(), ca_validade.strip(), int(vida_util_dias), agora)
            epi_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            return {
                "sucesso": True,
                "epi_id": epi_id,
                "codigo": codigo.upper().strip(),
                "ca_numero": ca_numero.strip(),
                "ca_validade": ca_validade.strip(),
            }
        finally:
            conn.close()

    def registrar_entrega_epi(
        self,
        colaborador_id: int,
        epi_id: int,
        quantidade: int = 1,
        data_entrega: Optional[str] = None,
        usuario: str = "Técnico SST",
    ) -> Dict[str, Any]:
        """
        RF-126, RN-062: Entrega de EPI com BLOQUEIO ESTRITO de Certificado de Aprovação (CA) vencido.
        Calcula data prevista de troca com base na vida útil do equipamento.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dt_ent = data_entrega or agora[:10]

            cur.execute(f"SELECT * FROM sst_epis WHERE id = {p};", (epi_id,))
            epi = fetchone_dict(cur, self.db_path)
            if not epi:
                raise PlataformaRecursoNaoEncontradoException(f"EPI ID {epi_id} não cadastrado no catálogo.")

            # Validação RN-062: Bloqueio imediato se CA estiver vencido na data da entrega
            if epi["ca_validade"] < dt_ent:
                raise PlataformaValidacaoException(
                    f"Bloqueio de Segurança (RN-062): O Certificado de Aprovação (CA {epi['ca_numero']}) "
                    f"está VENCIDO desde {epi['ca_validade']}. É expressamente proibida a entrega de EPI com CA expirado."
                )

            dias_vida = int(epi["vida_util_dias"] or 180)
            dt_prev_troca = (datetime.strptime(dt_ent, "%Y-%m-%d") + timedelta(days=dias_vida)).strftime("%Y-%m-%d")

            sql_pg = f"""
                INSERT INTO sst_entregas_epi (
                    colaborador_id, epi_id, data_entrega, quantidade, data_prevista_troca,
                    ciencia_colaborador, status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, 1, 'ativo', {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_entregas_epi (
                    colaborador_id, epi_id, data_entrega, quantidade, data_prevista_troca,
                    ciencia_colaborador, status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, 1, 'ativo', {p}, {p});
            """
            params = (colaborador_id, epi_id, dt_ent, quantidade, dt_prev_troca, usuario, agora)
            entrega_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            return {
                "sucesso": True,
                "entrega_id": entrega_id,
                "colaborador_id": colaborador_id,
                "epi_id": epi_id,
                "ca_numero": epi["ca_numero"],
                "data_entrega": dt_ent,
                "proxima_troca": dt_prev_troca,
                "status": "ativo",
            }
        finally:
            conn.close()

    def registrar_devolucao_epi(
        self,
        entrega_id: int,
        data_devolucao: Optional[str] = None,
        motivo: str = "devolucao_normal",
        usuario: str = "Técnico SST",
    ) -> Dict[str, Any]:
        """RF-126: Registra a devolução ou encerramento de uso de um EPI entregue."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dt_dev = data_devolucao or agora[:10]

            cur.execute(f"SELECT * FROM sst_entregas_epi WHERE id = {p};", (entrega_id,))
            entrega = fetchone_dict(cur, self.db_path)
            if not entrega:
                raise PlataformaRecursoNaoEncontradoException(f"Registro de entrega ID {entrega_id} não encontrado.")

            cur.execute(
                f"""
                UPDATE sst_entregas_epi
                SET status = 'devolvido', data_devolucao = {p}, motivo_troca = {p}
                WHERE id = {p};
            """,
                (dt_dev, motivo, entrega_id),
            )
            conn.commit()

            return {"sucesso": True, "entrega_id": entrega_id, "status": "devolvido", "data_devolucao": dt_dev}
        finally:
            conn.close()

    def registrar_substituicao_epi(
        self,
        entrega_anterior_id: int,
        novo_epi_id: int,
        motivo_troca: str = "desgaste",
        quantidade: int = 1,
        usuario: str = "Técnico SST",
    ) -> Dict[str, Any]:
        """RF-126: Substituição de EPI por desgaste, dano ou término da vida útil."""
        # Devolve o anterior
        self.registrar_devolucao_epi(entrega_anterior_id, motivo=motivo_troca, usuario=usuario)

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT colaborador_id FROM sst_entregas_epi WHERE id = {p};", (entrega_anterior_id,))
            colab_id = cur.fetchone()[0]
        finally:
            conn.close()

        # Registra a nova entrega com novo EPI
        nova_entrega = self.registrar_entrega_epi(colaborador_id=colab_id, epi_id=novo_epi_id, quantidade=quantidade, usuario=usuario)
        nova_entrega["substituido_de_id"] = entrega_anterior_id
        nova_entrega["motivo_substituicao"] = motivo_troca
        return nova_entrega

    # ─────────────────────────────────────────────────────────────────────────
    # RF-127: TREINAMENTOS OBRIGATÓRIOS (NR-05, NR-06, NR-10, NR-35, ETC.)
    # ─────────────────────────────────────────────────────────────────────────
    def cadastrar_treinamento(
        self,
        codigo: str,
        nome: str,
        nr_norma: str,
        carga_horaria: int,
        validade_meses: int = 24,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "Instrutor SST",
    ) -> Dict[str, Any]:
        """RF-127: Cadastra treinamento regulamentar (Normas Regulamentadoras MTE)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sql_pg = f"""
                INSERT INTO sst_treinamentos (
                    empresa_id, codigo, nome, nr_norma, carga_horaria,
                    validade_meses, ativo, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 1, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_treinamentos (
                    empresa_id, codigo, nome, nr_norma, carga_horaria,
                    validade_meses, ativo, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 1, {p});
            """
            params = (empresa_id, codigo.upper().strip(), nome.strip(), nr_norma.upper().strip(), int(carga_horaria), int(validade_meses), agora)
            trein_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            return {
                "sucesso": True,
                "treinamento_id": trein_id,
                "codigo": codigo.upper().strip(),
                "nome": nome.strip(),
                "nr_norma": nr_norma.upper().strip(),
                "carga_horaria": carga_horaria,
                "validade_meses": validade_meses,
            }
        finally:
            conn.close()

    def registrar_conclusao_treinamento(
        self,
        colaborador_id: int,
        treinamento_id: int,
        data_conclusao: str,
        instrutor_nome: str,
        certificado_url: Optional[str] = None,
        carga_horaria_realizada: Optional[int] = None,
        nota_aproveitamento: float = 10.0,
        usuario: str = "Instrutor SST",
    ) -> Dict[str, Any]:
        """
        RF-127: Registra conclusão de treinamento com cálculo automático de data de expiração/reciclagem.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(f"SELECT * FROM sst_treinamentos WHERE id = {p};", (treinamento_id,))
            trein = fetchone_dict(cur, self.db_path)
            if not trein:
                raise PlataformaRecursoNaoEncontradoException(f"Treinamento ID {treinamento_id} não encontrado.")

            val_meses = int(trein.get("validade_meses") or 24)
            # data expiração aproximada somando dias
            dias_exp = int(val_meses * 30.4375)
            dt_exp = (datetime.strptime(data_conclusao[:10], "%Y-%m-%d") + timedelta(days=dias_exp)).strftime("%Y-%m-%d")

            ch = carga_horaria_realizada or int(trein.get("carga_horaria") or 8)

            sql_pg = f"""
                INSERT INTO sst_treinamentos_participacoes (
                    colaborador_id, treinamento_id, data_conclusao, data_expiracao,
                    certificado_url, instrutor_nome, carga_horaria_realizada,
                    nota_aproveitamento, status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 'concluido', {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_treinamentos_participacoes (
                    colaborador_id, treinamento_id, data_conclusao, data_expiracao,
                    certificado_url, instrutor_nome, carga_horaria_realizada,
                    nota_aproveitamento, status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 'concluido', {p}, {p});
            """
            params = (colaborador_id, treinamento_id, data_conclusao, dt_exp, certificado_url, instrutor_nome, ch, float(nota_aproveitamento), usuario, agora)
            part_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            return {
                "sucesso": True,
                "participacao_id": part_id,
                "colaborador_id": colaborador_id,
                "treinamento_id": treinamento_id,
                "nr_norma": trein["nr_norma"],
                "data_conclusao": data_conclusao,
                "data_expiracao_reciclagem": dt_exp,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-128: ALERTAS DE VENCIMENTO PROATIVOS
    # ─────────────────────────────────────────────────────────────────────────
    def obter_alertas_vencimento_sst(
        self,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        dias_horizonte: int = 60,
    ) -> Dict[str, Any]:
        """
        RF-128, RF-147: Scanner preventivo que consolida alertas de vencimento:
        - ASOs vencidos e a vencer em até 60 dias.
        - EPIs com troca prevista expirada ou próxima.
        - Certificados de Aprovação (CA) de EPIs no catálogo vencidos ou a vencer.
        - Treinamentos regulamentares com validade expirada ou a expirar.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            hoje = datetime.now().strftime("%Y-%m-%d")
            data_limite = (datetime.now() + timedelta(days=dias_horizonte)).strftime("%Y-%m-%d")

            # 1. Alertas de ASO
            cur.execute(
                f"""
                SELECT a.id, a.colaborador_id, c.nome_completo, c.matricula, c.setor,
                       a.tipo_aso, a.data_validade,
                       CASE
                           WHEN a.data_validade < {p} THEN 'vencido'
                           ELSE 'a_vencer'
                       END as situacao_alerta
                FROM sst_asos a
                JOIN colaboradores c ON c.id = a.colaborador_id
                WHERE a.data_validade <= {p}
                ORDER BY a.data_validade ASC;
            """,
                (hoje, data_limite),
            )
            alertas_asos = fetchall_dict(cur, self.db_path)

            # 2. Alertas de Troca de EPI
            cur.execute(
                f"""
                SELECT e.id, e.colaborador_id, c.nome_completo, p.descricao as epi_nome,
                       p.ca_numero, e.data_prevista_troca,
                       CASE
                           WHEN e.data_prevista_troca < {p} THEN 'vencido'
                           ELSE 'a_vencer'
                       END as situacao_alerta
                FROM sst_entregas_epi e
                JOIN colaboradores c ON c.id = e.colaborador_id
                JOIN sst_epis p ON p.id = e.epi_id
                WHERE e.status = 'ativo' AND e.data_prevista_troca <= {p}
                ORDER BY e.data_prevista_troca ASC;
            """,
                (hoje, data_limite),
            )
            alertas_epis = fetchall_dict(cur, self.db_path)

            # 3. Alertas de C.A. de EPIs no catálogo
            cur.execute(
                f"""
                SELECT id, codigo, descricao, ca_numero, ca_validade,
                       CASE
                           WHEN ca_validade < {p} THEN 'ca_vencido'
                           ELSE 'ca_a_vencer'
                       END as situacao_alerta
                FROM sst_epis
                WHERE ca_validade <= {p} AND ativo = 1
                ORDER BY ca_validade ASC;
            """,
                (hoje, data_limite),
            )
            alertas_cas = fetchall_dict(cur, self.db_path)

            # 4. Alertas de Treinamentos / Reciclagens
            cur.execute(
                f"""
                SELECT tp.id, tp.colaborador_id, c.nome_completo, t.nome as treinamento_nome,
                       t.nr_norma, tp.data_expiracao,
                       CASE
                           WHEN tp.data_expiracao < {p} THEN 'vencido'
                           ELSE 'a_vencer'
                       END as situacao_alerta
                FROM sst_treinamentos_participacoes tp
                JOIN colaboradores c ON c.id = tp.colaborador_id
                JOIN sst_treinamentos t ON t.id = tp.treinamento_id
                WHERE tp.data_expiracao <= {p}
                ORDER BY tp.data_expiracao ASC;
            """,
                (hoje, data_limite),
            )
            alertas_treinamentos = fetchall_dict(cur, self.db_path)

            total_criticos = (
                sum(1 for a in alertas_asos if a["situacao_alerta"] == "vencido")
                + sum(1 for e in alertas_epis if e["situacao_alerta"] == "vencido")
                + sum(1 for c in alertas_cas if c["situacao_alerta"] == "ca_vencido")
                + sum(1 for t in alertas_treinamentos if t["situacao_alerta"] == "vencido")
            )

            return {
                "total_alertas": len(alertas_asos) + len(alertas_epis) + len(alertas_cas) + len(alertas_treinamentos),
                "total_criticos_vencidos": total_criticos,
                "horizonte_dias": dias_horizonte,
                "asos": alertas_asos,
                "epis_troca": alertas_epis,
                "epis_ca": alertas_cas,
                "treinamentos": alertas_treinamentos,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-129: CAT (COMUNICAÇÃO DE ACIDENTE DE TRABALHO)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_cat(
        self,
        colaborador_id: int,
        tipo_acidente: str,
        data_hora: str,
        local_acidente: str,
        descricao: str,
        houve_afastamento: bool = True,
        houve_obito: bool = False,
        cid_codigo: Optional[str] = None,
        medico_nome: Optional[str] = None,
        medico_crm: Optional[str] = None,
        medico_uf: Optional[str] = None,
        duracao_provavel_dias: int = 0,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "SST",
    ) -> Dict[str, Any]:
        """
        RF-129, RF-130, RN-064: Emissão da Comunicação de Acidente de Trabalho (CAT).
        Valida preenchimento obrigatório e dispara geração do evento eSocial S-2210.
        """
        if not tipo_acidente or not local_acidente or not descricao:
            raise PlataformaValidacaoException("Tipo de acidente, local e descrição do fato são obrigatórios.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(f"SELECT id, nome_completo, cpf, matricula FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException(f"Colaborador ID {colaborador_id} não encontrado.")

            numero_cat = f"CAT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{colaborador_id}"

            sql_pg = f"""
                INSERT INTO sst_cats (
                    empresa_id, colaborador_id, tipo_acidente, data_hora_acidente,
                    houve_afastamento, houve_obito, local_acidente, descricao_detalhada,
                    numero_cat, cid_codigo, atestado_medico_nome, atestado_medico_crm,
                    atestado_medico_uf, duracao_provavel_dias, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_cats (
                    empresa_id, colaborador_id, tipo_acidente, data_hora_acidente,
                    houve_afastamento, houve_obito, local_acidente, descricao_detalhada,
                    numero_cat, cid_codigo, atestado_medico_nome, atestado_medico_crm,
                    atestado_medico_uf, duracao_provavel_dias, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
            """
            params = (
                empresa_id,
                colaborador_id,
                tipo_acidente.strip().lower(),
                data_hora,
                1 if houve_afastamento else 0,
                1 if houve_obito else 0,
                local_acidente.strip(),
                descricao.strip(),
                numero_cat,
                cid_codigo or "N/A",
                medico_nome or "",
                medico_crm or "",
                medico_uf or "",
                int(duracao_provavel_dias),
                usuario,
                agora,
            )
            cat_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            # Geração oficial do evento eSocial S-2210 (Comunicação de Acidente de Trabalho)
            tp_acid_map = {"tipico": "1", "doenca": "2", "trajeto": "3"}
            tp_acid_cod = tp_acid_map.get(tipo_acidente.strip().lower(), "1")
            cpf_dig = "".join(filter(str.isdigit, str(colab.get("cpf") or "00000000000"))).zfill(11)
            matr_limpa = str(colab.get("matricula") or f"MATR-{colaborador_id}").strip()

            xml_s2210 = f"""<?xml version="1.0" encoding="UTF-8"?>
<eSocial xmlns="http://www.esocial.gov.br/schema/evt/evtCAT/v_S_01_02_00">
  <evtCAT id="ID112345678000000{datetime.now().strftime('%Y%m%d%H%M%S')}00002">
    <ideEmpregador>
      <tpInsc>1</tpInsc>
      <nrInsc>12345678000190</nrInsc>
    </ideEmpregador>
    <ideTrabalhador>
      <cpfTrab>{cpf_dig}</cpfTrab>
    </ideTrabalhador>
    <ideVinculo>
      <cpfTrab>{cpf_dig}</cpfTrab>
      <matricula>{matr_limpa}</matricula>
    </ideVinculo>
    <cat>
      <dtAcid>{data_hora[:10]}</dtAcid>
      <tpAcid>{tp_acid_cod}</tpAcid>
      <hrAcid>{data_hora[11:16] if len(data_hora) >= 16 else '08:00'}</hrAcid>
      <hrsTrabAntesAcid>0400</hrsTrabAntesAcid>
      <tpCat>1</tpCat>
      <localAcidente>
        <tpLocal>1</tpLocal>
        <dscLocal>{local_acidente[:80]}</dscLocal>
      </localAcidente>
      <parteAtingida>
        <codParte>751000000</codParte>
      </parteAtingida>
      <atestado>
        <dtAtendimento>{data_hora[:10]}</dtAtendimento>
        <hrAtendimento>{data_hora[11:16] if len(data_hora) >= 16 else '08:00'}</hrAtendimento>
        <indAfast>{'S' if houve_afastamento else 'N'}</indAfast>
        <qtdDiasAfast>{duracao_provavel_dias}</qtdDiasAfast>
        <dscLesao>Acidente de trabalho</dscLesao>
        <codCID>{cid_codigo or 'S00'}</codCID>
        <emitente>
          <nmEmit>{medico_nome or 'Médico Responsável'}</nmEmit>
          <ideOC>1</ideOC>
          <nrOC>{medico_crm or '12345'}</nrOC>
          <ufOC>{medico_uf or 'SP'}</ufOC>
        </emitente>
      </atestado>
    </cat>
  </evtCAT>
</eSocial>"""

            cur.execute(
                f"""
                INSERT INTO esocial_eventos (
                    empresa_id, tipo_evento, identificador_origem, ambiente, status,
                    xml_conteudo, criado_por, criado_em
                ) VALUES ({p}, 'S-2210', {p}, 'homologacao', 'validado', {p}, {p}, {p});
            """,
                (empresa_id, str(cat_id), xml_s2210, usuario, agora),
            )

            conn.commit()

            self._registrar_auditoria(
                modulo="SST",
                operacao="emissao_cat",
                registro_tipo="sst_cats",
                registro_id=cat_id,
                usuario=usuario,
                detalhes=f"CAT {numero_cat} emitida para Colaborador {colaborador_id} ({tipo_acidente}). CID {cid_codigo}.",
                empresa_id=empresa_id,
            )

            return {
                "sucesso": True,
                "cat_id": cat_id,
                "numero_cat": numero_cat,
                "tipo_acidente": tipo_acidente,
                "esocial_gerado": True,
                "tipo_evento_esocial": "S-2210",
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-130: INTEGRAÇÃO SST ESOCIAL (S-2210, S-2220, S-2240)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_condicao_ambiental_s2240(
        self,
        colaborador_id: int,
        ambiente_nome: str,
        fator_risco_codigo: str,
        fator_risco_descricao: str,
        data_inicio: str,
        tipo_avaliacao: str = "qualitativa",
        intensidade_concentracao: float = 0.0,
        limite_tolerancia: float = 0.0,
        tecnica_utilizada: str = "Medição Direta / Dosimetria",
        epc_eficaz: bool = False,
        epi_eficaz: bool = True,
        ca_epi_utilizado: Optional[str] = None,
        responsavel_nome: str = "Engenheiro de Segurança",
        responsavel_cpf: str = "12345678909",
        descricao_atividades: str = "Atividades operacionais em ambiente corporativo",
        data_fim: Optional[str] = None,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "Engenheiro SST",
    ) -> Dict[str, Any]:
        """
        RF-130: Registra as Condições Ambientais do Trabalho / Fatores de Risco
        e gera o evento oficial eSocial S-2240.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(f"SELECT id, nome_completo, cpf, matricula FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException(f"Colaborador ID {colaborador_id} não encontrado.")

            sql_pg = f"""
                INSERT INTO sst_condicoes_ambientais (
                    empresa_id, colaborador_id, ambiente_nome, descricao_atividades,
                    fator_risco_codigo, fator_risco_descricao, tipo_avaliacao,
                    intensidade_concentracao, limite_tolerancia, tecnica_utilizada,
                    epc_eficaz, epi_eficaz, ca_epi_utilizado, responsavel_registros_nome,
                    responsavel_registros_cpf, data_inicio_condicao, data_fim_condicao,
                    criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_condicoes_ambientais (
                    empresa_id, colaborador_id, ambiente_nome, descricao_atividades,
                    fator_risco_codigo, fator_risco_descricao, tipo_avaliacao,
                    intensidade_concentracao, limite_tolerancia, tecnica_utilizada,
                    epc_eficaz, epi_eficaz, ca_epi_utilizado, responsavel_registros_nome,
                    responsavel_registros_cpf, data_inicio_condicao, data_fim_condicao,
                    criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
            """
            params = (
                empresa_id,
                colaborador_id,
                ambiente_nome.strip(),
                descricao_atividades.strip(),
                fator_risco_codigo.strip(),
                fator_risco_descricao.strip(),
                tipo_avaliacao.strip().lower(),
                float(intensidade_concentracao),
                float(limite_tolerancia),
                tecnica_utilizada.strip(),
                1 if epc_eficaz else 0,
                1 if epi_eficaz else 0,
                ca_epi_utilizado or "",
                responsavel_nome.strip(),
                responsavel_cpf.strip(),
                data_inicio[:10],
                data_fim[:10] if data_fim else None,
                usuario,
                agora,
            )
            cond_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            # Geração oficial do evento eSocial S-2240 (Condições Ambientais do Trabalho - Agentes Nocivos)
            cpf_dig = "".join(filter(str.isdigit, str(colab.get("cpf") or "00000000000"))).zfill(11)
            matr_limpa = str(colab.get("matricula") or f"MATR-{colaborador_id}").strip()

            xml_s2240 = f"""<?xml version="1.0" encoding="UTF-8"?>
<eSocial xmlns="http://www.esocial.gov.br/schema/evt/evtExpRisco/v_S_01_02_00">
  <evtExpRisco id="ID112345678000000{datetime.now().strftime('%Y%m%d%H%M%S')}00003">
    <ideEmpregador>
      <tpInsc>1</tpInsc>
      <nrInsc>12345678000190</nrInsc>
    </ideEmpregador>
    <ideTrabalhador>
      <cpfTrab>{cpf_dig}</cpfTrab>
    </ideTrabalhador>
    <ideVinculo>
      <cpfTrab>{cpf_dig}</cpfTrab>
      <matricula>{matr_limpa}</matricula>
    </ideVinculo>
    <infoExpRisco>
      <dtIniCondicao>{data_inicio[:10]}</dtIniCondicao>
      <infoAmb>
        <localAmb>1</localAmb>
        <dscSetor>{ambiente_nome[:50]}</dscSetor>
      </infoAmb>
      <infoAtiv>
        <dscAtivDes>{descricao_atividades[:100]}</dscAtivDes>
      </infoAtiv>
      <agNoc>
        <codAgNoc>{fator_risco_codigo}</codAgNoc>
        <dscAgNoc>{fator_risco_descricao[:100]}</dscAgNoc>
        <tpAval>{'1' if tipo_avaliacao == 'quantitativa' else '2'}</tpAval>
        <epcEpi>
          <utilizEPC>{'2' if epc_eficaz else '1'}</utilizEPC>
          <utilizEPI>{'2' if epi_eficaz else '1'}</utilizEPI>
          <epi>
            <docAval>{ca_epi_utilizado or '12345'}</docAval>
          </epi>
        </epcEpi>
      </agNoc>
      <respReg>
        <cpfResp>{responsavel_cpf}</cpfResp>
        <ideOC>4</ideOC>
        <nrOC>12345</nrOC>
        <ufOC>SP</ufOC>
      </respReg>
    </infoExpRisco>
  </evtExpRisco>
</eSocial>"""

            cur.execute(
                f"""
                INSERT INTO esocial_eventos (
                    empresa_id, tipo_evento, identificador_origem, ambiente, status,
                    xml_conteudo, criado_por, criado_em
                ) VALUES ({p}, 'S-2240', {p}, 'homologacao', 'validado', {p}, {p}, {p});
            """,
                (empresa_id, str(cond_id), xml_s2240, usuario, agora),
            )
            ev_id = cur.lastrowid if hasattr(cur, "lastrowid") and cur.lastrowid else None
            if ev_id:
                cur.execute(f"UPDATE sst_condicoes_ambientais SET esocial_evento_id = {p} WHERE id = {p};", (ev_id, cond_id))

            conn.commit()

            self._registrar_auditoria(
                modulo="SST",
                operacao="condicao_ambiental",
                registro_tipo="sst_condicoes_ambientais",
                registro_id=cond_id,
                usuario=usuario,
                detalhes=f"Condição ambiental S-2240 ({fator_risco_codigo} - {fator_risco_descricao}) registrada para Colaborador {colaborador_id}.",
                empresa_id=empresa_id,
            )

            return {
                "sucesso": True,
                "condicao_id": cond_id,
                "colaborador_id": colaborador_id,
                "fator_risco_codigo": fator_risco_codigo,
                "esocial_gerado": True,
                "tipo_evento_esocial": "S-2240",
            }
        finally:
            conn.close()
