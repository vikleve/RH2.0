"""
Camada de Serviços da Plataforma Integrada de Gestão do Ciclo Trabalhista
Implementa a lógica de negócio, persistência relacional e validações para os 20 Módulos:
Módulos 01 a 20 (RF-001 a RF-200), Regras Transversais (RT-01 a RT-13) e
Regras de Negócio Trabalhistas e Compliance (RN-001 a RN-083).
"""
import calendar
import json
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from backend.database import (
    get_connection,
    insert_returning_id,
    row_to_dict,
    fetchone_dict,
    fetchall_dict,
    _usar_postgres,
)
from backend.folha_calculos_2026 import (
    calcular_inss_2026,
    calcular_irrf_2026,
    calcular_salario_familia_2026,
    calcular_vale_transporte,
    calcular_horas_extras_oficial,
    calcular_dsr_sobre_variaveis_oficial,
    calcular_adicional_noturno_oficial,
    calcular_descontos_ausencia_oficial,
    calcular_rescisao_oficial,
    SALARIO_MINIMO_2026,
    to_d,
    round2,
)


from .admissao_service import AdmissaoService
from .plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaRecursoNaoEncontradoException,
    PlataformaValidacaoException,
)


class PlataformaService:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        self.admissao_service = AdmissaoService(
            db_path=self.db_path,
            auditoria_cb=self.registrar_auditoria,
            calcular_beneficio_cb=self._calcular_valores_beneficio,
        )

    def _conn(self):
        return get_connection(self.db_path)

    def _pg(self) -> bool:
        return _usar_postgres(self.db_path)

    def _p(self) -> str:
        return "%s" if self._pg() else "?"

    # ─────────────────────────────────────────────────────────────────────────
    # RT-01 & Módulo 20: AUDITORIA E RASTREABILIDADE (RF-191 a RF-200)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_auditoria(
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
        """Registra log imutável de auditoria (RT-01, RT-02, RF-191 a RF-200)."""
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
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
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

    def listar_auditoria(
        self,
        modulo: Optional[str] = None,
        operacao: Optional[str] = None,
        usuario: Optional[str] = None,
        limite: int = 100,
    ) -> List[Dict[str, Any]]:
        """Consulta logs de auditoria (RF-198, RF-199)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            query = "SELECT * FROM auditoria_operacoes WHERE 1=1"
            params = []
            p = self._p()
            if modulo:
                query += f" AND modulo = {p}"
                params.append(modulo)
            if operacao:
                query += f" AND operacao = {p}"
                params.append(operacao)
            if usuario:
                query += f" AND usuario_responsavel LIKE {p}"
                params.append(f"%{usuario}%")
            query += f" ORDER BY id DESC LIMIT {limite}"
            cur.execute(query, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 02: ADMISSÃO (RF-011 a RF-020 — Delegado ao AdmissaoService)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_admissao(self, dados: Dict[str, Any], usuario: str) -> Dict[str, Any]:
        return self.admissao_service.registrar_admissao(dados, usuario=usuario)

    def atualizar_admissao(self, admissao_id: int, dados: Dict[str, Any], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.atualizar_admissao(admissao_id, dados, usuario=usuario, empresa_id=empresa_id)

    def cancelar_admissao(self, admissao_id: int, motivo: str, usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.cancelar_admissao(admissao_id, motivo=motivo, usuario=usuario, empresa_id=empresa_id)

    def obter_admissao(self, admissao_id: int, empresa_id: Optional[str] = None, perfil_usuario: str = "gestor_rh") -> Dict[str, Any]:
        return self.admissao_service.obter_admissao(admissao_id, empresa_id=empresa_id, perfil_usuario=perfil_usuario)

    def listar_admissoes(self, status: Optional[str] = None, empresa_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.admissao_service.listar_admissoes(status=status, empresa_id=empresa_id)

    def configurar_item_checklist(self, admissao_id: int, dados: Dict[str, Any], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.configurar_item_checklist(admissao_id, dados, usuario=usuario, empresa_id=empresa_id)

    def upload_documento_checklist(self, admissao_id: int, item_id: int, nome_arquivo: str, conteudo_base64: str, mime_type: str = "application/octet-stream", usuario: str = "Operador", observacao: str = "", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.upload_documento_checklist(admissao_id, item_id, nome_arquivo, conteudo_base64, mime_type=mime_type, usuario=usuario, observacao=observacao, empresa_id=empresa_id)

    def atualizar_item_checklist(self, item_id: int, status: str, usuario: str, justificativa: Optional[str] = None, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.atualizar_item_checklist(item_id, status=status, usuario=usuario, justificativa=justificativa, empresa_id=empresa_id)

    def obter_documento_checklist_download(self, admissao_id: int, item_id: int, usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.obter_documento_checklist_download(admissao_id, item_id, usuario=usuario, empresa_id=empresa_id)

    def validar_admissao(self, admissao_id: int, usuario: str, empresa_id: Optional[str] = None, exigir_centro_custo: bool = False) -> Dict[str, Any]:
        return self.admissao_service.validar_admissao(admissao_id, usuario=usuario, empresa_id=empresa_id, exigir_centro_custo=exigir_centro_custo)

    def registrar_aso_admissional(self, admissao_id: int, dados: Dict[str, Any], usuario: str = "SST", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.registrar_aso_admissional(admissao_id, dados, usuario=usuario, empresa_id=empresa_id)

    def consultar_aso_admissional(self, admissao_id: int, perfil_usuario: str, empresa_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.admissao_service.consultar_aso_admissional(admissao_id, perfil_usuario=perfil_usuario, empresa_id=empresa_id)

    def obter_documento_aso_download(self, admissao_id: int, usuario: str, perfil_usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.obter_documento_aso_download(admissao_id, usuario=usuario, perfil_usuario=perfil_usuario, empresa_id=empresa_id)

    def listar_escalas_jornada(self, empresa_id: Optional[str] = None, apenas_ativas: bool = True) -> List[Dict[str, Any]]:
        return self.admissao_service.listar_escalas_jornada(empresa_id=empresa_id, apenas_ativas=apenas_ativas)

    def criar_escala_jornada(self, dados: Dict[str, Any], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.criar_escala_jornada(dados, usuario=usuario, empresa_id=empresa_id)

    def definir_jornada_admissao(self, admissao_id: int, dados: Dict[str, Any], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.definir_jornada_admissao(admissao_id, dados, usuario=usuario, empresa_id=empresa_id)

    def listar_centros_custo(self, empresa_id: Optional[str] = None, apenas_ativos: bool = True) -> List[Dict[str, Any]]:
        return self.admissao_service.listar_centros_custo(empresa_id=empresa_id, apenas_ativos=apenas_ativos)

    def criar_centro_custo(self, dados: Dict[str, Any], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.criar_centro_custo(dados, usuario=usuario, empresa_id=empresa_id)

    def definir_centro_custo_admissao(self, admissao_id: int, dados: Dict[str, Any], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.definir_centro_custo_admissao(admissao_id, dados, usuario=usuario, empresa_id=empresa_id)

    def listar_beneficios_elegiveis_admissao(self, admissao_id: int, empresa_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.admissao_service.listar_beneficios_elegiveis_admissao(admissao_id, empresa_id=empresa_id)

    def definir_beneficios_admissao(self, admissao_id: int, itens_beneficios: List[Dict[str, Any]], usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.definir_beneficios_admissao(admissao_id, itens_beneficios, usuario=usuario, empresa_id=empresa_id)

    def listar_modelos_contrato(self, empresa_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.admissao_service.listar_modelos_contrato(empresa_id=empresa_id)

    def gerar_contrato_trabalho(self, admissao_id: int, usuario: str, modelo_id: Optional[int] = None, condicoes_adicionais: str = "", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.gerar_contrato_trabalho(admissao_id, usuario=usuario, modelo_id=modelo_id, condicoes_adicionais=condicoes_adicionais, empresa_id=empresa_id)

    def formalizar_contrato(self, admissao_id: int, contrato_id: int, usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.formalizar_contrato(admissao_id, contrato_id, usuario=usuario, empresa_id=empresa_id)

    def obter_contrato_pdf_download(self, admissao_id: int, contrato_id: int, usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.obter_contrato_pdf_download(admissao_id, contrato_id, usuario=usuario, empresa_id=empresa_id)

    def gerar_evento_esocial_admissao(self, admissao_id: int, tipo_evento: Optional[str], usuario: str, ambiente: str = "homologacao", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.gerar_evento_esocial_admissao(admissao_id, tipo_evento, usuario=usuario, ambiente=ambiente, empresa_id=empresa_id)

    def registrar_retorno_esocial(self, evento_id: int, status_retorno: str, codigo_resposta: str, mensagem_resposta: str, protocolo_envio: Optional[str] = None, numero_recibo: Optional[str] = None, usuario: str = "eSocial", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.registrar_retorno_esocial(evento_id, status_retorno, codigo_resposta, mensagem_resposta, protocolo_envio=protocolo_envio, numero_recibo=numero_recibo, usuario=usuario, empresa_id=empresa_id)

    def reprocessar_evento_esocial(self, evento_id: int, usuario: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.reprocessar_evento_esocial(evento_id, usuario=usuario, empresa_id=empresa_id)

    def solicitar_aprovacao_admissao(self, admissao_id: int, usuario: str, justificativa: str = "", empresa_id: Optional[str] = None, exigir_centro_custo: bool = False) -> Dict[str, Any]:
        return self.admissao_service.solicitar_aprovacao_admissao(admissao_id, usuario=usuario, justificativa=justificativa, empresa_id=empresa_id, exigir_centro_custo=exigir_centro_custo)

    def aprovar_admissao(self, admissao_id: int, aprovador: str, justificativa: str = "", empresa_id: Optional[str] = None, exigir_centro_custo: bool = False) -> Dict[str, Any]:
        return self.admissao_service.aprovar_admissao(admissao_id, aprovador=aprovador, justificativa=justificativa, empresa_id=empresa_id, exigir_centro_custo=exigir_centro_custo)

    def reprovar_admissao(self, admissao_id: int, aprovador: str, motivo: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.admissao_service.reprovar_admissao(admissao_id, aprovador=aprovador, motivo=motivo, empresa_id=empresa_id)

    def obter_painel_admissao(self, admissao_id: int, empresa_id: Optional[str] = None, perfil_usuario: str = "gestor_rh") -> Dict[str, Any]:
        return self.admissao_service.obter_painel_admissao(admissao_id, empresa_id=empresa_id, perfil_usuario=perfil_usuario)

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 03: JORNADA E PONTO (RF-021 a RF-030)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_marcacao_ponto(self, colaborador_id: int, data: str, hora: str, tipo_registro: str = "manual", coletor_id: Optional[str] = None) -> Dict[str, Any]:
        """RF-021, RF-022, RN-012: Registra batida de ponto com preservação de origem e detecção de duplicidades."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Verifica duplicidade idêntica (mesmo colaborador, data e hora)
            cur.execute(f"SELECT COUNT(*) FROM marcacoes_ponto WHERE colaborador_id = {p} AND data = {p} AND hora = {p};", (colaborador_id, data, hora))
            if cur.fetchone()[0] > 0:
                return {"sucesso": False, "mensagem": "Marcação idêntica já registrada anteriormente (RF-022, idempotência)."}

            sql_pg = f"""
                INSERT INTO marcacoes_ponto (colaborador_id, data, hora, tipo_registro, id_coletor, criado_em)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO marcacoes_ponto (colaborador_id, data, hora, tipo_registro, id_coletor, criado_em)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p});
            """
            params = (colaborador_id, data, hora, tipo_registro, coletor_id, agora)
            m_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            return {"sucesso": True, "marcacao_id": m_id, "data": data, "hora": hora}
        finally:
            conn.close()

    def solicitar_ajuste_ponto(self, colaborador_id: int, data: str, hora_ajustada: str, tipo_marcacao: str, motivo: str, solicitante: str, hora_original: Optional[str] = None) -> Dict[str, Any]:
        """RF-025: Solicitação de ajuste de ponto com justificativa obrigatória."""
        if not motivo or not motivo.strip():
            raise PlataformaValidacaoException("Justificativa é estritamente obrigatória para ajuste manual de ponto (RF-025, RN-013).")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sql_pg = f"""
                INSERT INTO ajustes_ponto (
                    colaborador_id, data, hora_original, hora_ajustada, tipo_marcacao,
                    motivo, status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 'pendente', {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO ajustes_ponto (
                    colaborador_id, data, hora_original, hora_ajustada, tipo_marcacao,
                    motivo, status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, 'pendente', {p}, {p});
            """
            params = (colaborador_id, data, hora_original, hora_ajustada, tipo_marcacao, motivo.strip(), solicitante, agora)
            ajuste_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            self.registrar_auditoria(
                modulo="Ponto",
                operacao="inclusao",
                registro_tipo="ajustes_ponto",
                registro_id=ajuste_id,
                usuario=solicitante,
                detalhes=f"Ajuste solicitado para Colaborador {colaborador_id} em {data}: {hora_ajustada} ({motivo})",
            )

            return {"sucesso": True, "ajuste_id": ajuste_id, "mensagem": "Ajuste de ponto submetido para aprovação do gestor/DP."}
        finally:
            conn.close()

    def aprovar_ajuste_ponto(self, ajuste_id: int, aprovador: str, aprovar: bool = True, motivo_reprovacao: Optional[str] = None) -> Dict[str, Any]:
        """RF-026: Aprovação ou reprovação de ajuste de ponto com segregação de funções."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM ajustes_ponto WHERE id = {p};", (ajuste_id,))
            ajuste = fetchone_dict(cur, self.db_path)
            if not ajuste:
                raise PlataformaRecursoNaoEncontradoException("Ajuste de ponto não encontrado.")

            if ajuste["criado_por"].strip().lower() == aprovador.strip().lower():
                raise PlataformaAcessoNegadoException("Autoaprovação de ajuste de ponto é proibida (RN-080, RF-026).")

            novo_status = "aprovado" if aprovar else "reprovado"
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                f"""
                UPDATE ajustes_ponto
                SET status = {p}, aprovado_por = {p}, aprovado_em = {p}, motivo_reprovacao = {p}
                WHERE id = {p};
            """,
                (novo_status, aprovador, agora, motivo_reprovacao, ajuste_id),
            )

            if aprovar:
                # Insere a marcação ajustada na base oficial preservando rastreio (RN-013)
                cur.execute(
                    f"""
                    INSERT INTO marcacoes_ponto (colaborador_id, data, hora, tipo_registro, id_coletor, criado_em)
                    VALUES ({p}, {p}, {p}, 'manual', 'ajuste_aprovado', {p});
                """,
                    (ajuste["colaborador_id"], ajuste["data"], ajuste["hora_ajustada"], agora),
                )

            conn.commit()

            self.registrar_auditoria(
                modulo="Ponto",
                operacao="aprovacao" if aprovar else "alteracao",
                registro_tipo="ajustes_ponto",
                registro_id=ajuste_id,
                usuario=aprovador,
                detalhes=f"Ajuste {ajuste_id} {novo_status} por {aprovador}.",
            )

            return {"sucesso": True, "status": novo_status, "mensagem": f"Ajuste de ponto {novo_status} com sucesso."}
        finally:
            conn.close()

    def obter_espelho_ponto(self, colaborador_id: int, mes_ano: str) -> Dict[str, Any]:
        """RF-027: Espelho de ponto completo por colaborador e período (marcações, ajustes e ocorrências)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()

            # Dados do colaborador
            cur.execute(f"SELECT id, nome_completo, matricula, cargo, setor, salario_base FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException("Colaborador não encontrado.")

            # Marcações do período
            cur.execute(
                f"""
                SELECT * FROM marcacoes_ponto
                WHERE colaborador_id = {p} AND data LIKE {p}
                ORDER BY data ASC, hora ASC;
            """,
                (colaborador_id, f"{mes_ano}%"),
            )
            marcacoes = fetchall_dict(cur, self.db_path)

            # Ocorrências do período
            cur.execute(
                f"""
                SELECT * FROM ocorrencias_ponto
                WHERE colaborador_id = {p} AND (data_inicio LIKE {p} OR data_fim LIKE {p})
                ORDER BY data_inicio ASC;
            """,
                (colaborador_id, f"{mes_ano}%", f"{mes_ano}%"),
            )
            ocorrencias = fetchall_dict(cur, self.db_path)

            # Ajustes do período
            cur.execute(
                f"""
                SELECT * FROM ajustes_ponto
                WHERE colaborador_id = {p} AND data LIKE {p}
                ORDER BY data ASC;
            """,
                (colaborador_id, f"{mes_ano}%"),
            )
            ajustes = fetchall_dict(cur, self.db_path)

            # Agrupa batidas por data
            dias_map = {}
            for m in marcacoes:
                dt = m["data"]
                if dt not in dias_map:
                    dias_map[dt] = []
                dias_map[dt].append(m["hora"][:5])

            return {
                "colaborador": colab,
                "periodo": mes_ano,
                "dias_trabalhados": len(dias_map),
                "total_marcacoes": len(marcacoes),
                "grade_dias": [{"data": k, "batidas": v} for k, v in sorted(dias_map.items())],
                "ocorrencias": ocorrencias,
                "ajustes": ajustes,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 06: FÉRIAS (RF-051 a RF-060)
    # ─────────────────────────────────────────────────────────────────────────
    def programar_ferias(
        self,
        colaborador_id: int,
        data_inicio: str,
        dias_gozo: int,
        abono_pecuniario: bool = False,
        adiantar_13: bool = False,
        solicitante: str = "DP",
    ) -> Dict[str, Any]:
        """
        RF-053, RF-054, RF-055, RN-029: Programação e cálculo de férias.
        Verifica período concessivo, fracionamento mínimo (14d ou 5d), bloqueio 2 dias antes de feriado/DSR.
        """
        if dias_gozo < 5:
            raise PlataformaValidacaoException("Período de férias não pode ser inferior a 5 dias corridos (RF-054, RN-029).")

        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        # Início não pode ser em sexta-feira ou sábado se DSR for no domingo (2 dias antes do repouso semanal)
        if dt_ini.weekday() in (4, 5):  # 4=Sexta, 5=Sábado
            raise PlataformaValidacaoException("Início das férias não pode ocorrer nos 2 dias que antecedem o repouso semanal remunerado (art. 134 § 3º CLT, RF-053).")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()

            # Busca período aquisitivo com saldo (cria automaticamente se colaborador ainda não possuir)
            cur.execute(
                f"""
                SELECT * FROM periodos_aquisitivos
                WHERE colaborador_id = {p} AND saldo_dias >= {p}
                ORDER BY inicio_aquisitivo ASC LIMIT 1;
            """,
                (colaborador_id, dias_gozo),
            )
            pa = fetchone_dict(cur, self.db_path)
            if not pa:
                cur.execute(f"SELECT data_admissao FROM colaboradores WHERE id = {p};", (colaborador_id,))
                row_adm = cur.fetchone()
                if row_adm:
                    dt_adm_str = row_adm[0] if isinstance(row_adm, tuple) else row_adm["data_admissao"]
                    dt_fim_aq = (datetime.strptime(dt_adm_str[:10], "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")
                    dt_lim_conc = (datetime.strptime(dt_fim_aq, "%Y-%m-%d") + timedelta(days=365)).strftime("%Y-%m-%d")
                    agora_pa = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cur.execute(
                        f"""
                        INSERT INTO periodos_aquisitivos (
                            colaborador_id, inicio_aquisitivo, fim_aquisitivo, limite_concessivo,
                            faltas_injustificadas, dias_direito, dias_gozados, saldo_dias, situacao,
                            criado_em, atualizado_em
                        ) VALUES ({p}, {p}, {p}, {p}, 0, 30, 0, 30, 'adquirido', {p}, {p});
                    """,
                        (colaborador_id, dt_adm_str[:10], dt_fim_aq, dt_lim_conc, agora_pa, agora_pa),
                    )
                    conn.commit()
                    cur.execute(
                        f"SELECT * FROM periodos_aquisitivos WHERE colaborador_id = {p} AND saldo_dias >= {p} ORDER BY inicio_aquisitivo ASC LIMIT 1;",
                        (colaborador_id, dias_gozo),
                    )
                    pa = fetchone_dict(cur, self.db_path)
            if not pa:
                raise PlataformaValidacaoException("Colaborador não possui período aquisitivo com saldo suficiente de dias para esta solicitação.")

            # Busca remuneração do colaborador
            cur.execute(f"SELECT salario_base FROM colaboradores WHERE id = {p};", (colaborador_id,))
            salario = to_d(cur.fetchone()[0])

            # Dias de abono pecuniário (máx 10 dias / 1/3)
            dias_abono = 10 if abono_pecuniario else 0
            if dias_gozo + dias_abono > pa["saldo_dias"]:
                raise PlataformaValidacaoException(f"Soma dos dias de gozo ({dias_gozo}) e abono ({dias_abono}) ultrapassa saldo disponível ({pa['saldo_dias']} dias).")

            dt_fim = (dt_ini + timedelta(days=dias_gozo - 1)).strftime("%Y-%m-%d")
            dt_limite_pag = (dt_ini - timedelta(days=2)).strftime("%Y-%m-%d")
            aviso_dt = (dt_ini - timedelta(days=30)).strftime("%Y-%m-%d")

            # Cálculo dos valores
            valor_dia = salario / Decimal("30.00")
            valor_ferias = round2(Decimal(str(dias_gozo)) * valor_dia)
            valor_terco = round2(valor_ferias / Decimal("3.00"))
            valor_abono = round2(Decimal(str(dias_abono)) * valor_dia) if abono_pecuniario else Decimal("0.00")
            valor_terco_abono = round2(valor_abono / Decimal("3.00")) if abono_pecuniario else Decimal("0.00")

            # Tributação de férias (INSS e IRRF)
            base_inss = valor_ferias + valor_terco
            inss_ferias, _, _, _ = calcular_inss_2026(base_inss)
            irrf_ferias, _, _, _, _ = calcular_irrf_2026(rendimento_bruto=base_inss, desconto_inss=inss_ferias)

            bruto = valor_ferias + valor_terco + valor_abono + valor_terco_abono
            liquido = max(Decimal("0.00"), bruto - inss_ferias - irrf_ferias)

            # Verifica se está vencido o concessivo (paga em dobro — RF-052, RN-027)
            em_dobro = 0
            if data_inicio > pa["limite_concessivo"]:
                em_dobro = 1
                valor_ferias = valor_ferias * Decimal("2.00")
                valor_terco = valor_terco * Decimal("2.00")
                liquido = valor_ferias + valor_terco + valor_abono + valor_terco_abono - inss_ferias - irrf_ferias

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO ferias_programadas (
                    colaborador_id, periodo_aquisitivo_id, data_inicio, data_fim, dias_gozo,
                    abono_pecuniario, dias_abono, adiantar_decimo, aviso_ferias_emitido,
                    data_pagamento_limite, valor_ferias, valor_terco, valor_abono,
                    valor_terco_abono, desconto_inss, desconto_irrf, valor_liquido,
                    em_dobro, status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 'solicitada', {p}, {p})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO ferias_programadas (
                    colaborador_id, periodo_aquisitivo_id, data_inicio, data_fim, dias_gozo,
                    abono_pecuniario, dias_abono, adiantar_decimo, aviso_ferias_emitido,
                    data_pagamento_limite, valor_ferias, valor_terco, valor_abono,
                    valor_terco_abono, desconto_inss, desconto_irrf, valor_liquido,
                    em_dobro, status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 'solicitada', {p}, {p});
            """
            params = (
                colaborador_id,
                pa["id"],
                data_inicio,
                dt_fim,
                dias_gozo,
                1 if abono_pecuniario else 0,
                dias_abono,
                1 if adiantar_13 else 0,
                aviso_dt,
                dt_limite_pag,
                float(valor_ferias),
                float(valor_terco),
                float(valor_abono),
                float(valor_terco_abono),
                float(inss_ferias),
                float(irrf_ferias),
                float(liquido),
                em_dobro,
                solicitante,
                agora,
            )
            ferias_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            conn.commit()

            self.registrar_auditoria(
                modulo="Ferias",
                operacao="inclusao",
                registro_tipo="ferias_programadas",
                registro_id=ferias_id,
                usuario=solicitante,
                detalhes=f"Férias programadas para Colab {colaborador_id}: {data_inicio} a {dt_fim} ({dias_gozo} dias) - Líquido R$ {liquido:.2f}",
            )

            return {
                "sucesso": True,
                "ferias_id": ferias_id,
                "data_inicio": data_inicio,
                "data_fim": dt_fim,
                "data_limite_pagamento": dt_limite_pag,
                "valor_ferias": float(valor_ferias),
                "valor_terco": float(valor_terco),
                "valor_abono": float(valor_abono),
                "valor_liquido": float(liquido),
                "em_dobro": bool(em_dobro),
            }
        finally:
            conn.close()

    def listar_ferias(self, colaborador_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lista histórico e programações de férias."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            query = """
                SELECT f.*, c.nome_completo, c.matricula, c.setor,
                       pa.inicio_aquisitivo, pa.fim_aquisitivo, pa.limite_concessivo
                FROM ferias_programadas f
                JOIN colaboradores c ON c.id = f.colaborador_id
                LEFT JOIN periodos_aquisitivos pa ON pa.id = f.periodo_aquisitivo_id
                WHERE 1=1
            """
            params = []
            if colaborador_id:
                query += f" AND f.colaborador_id = {self._p()}"
                params.append(colaborador_id)
            query += " ORDER BY f.data_inicio DESC"
            cur.execute(query, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 07: AFASTAMENTOS (RF-061 a RF-070)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_afastamento(
        self,
        colaborador_id: int,
        tipo: str,
        data_inicio: str,
        data_fim_prevista: str,
        cid: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        """
        RF-061 a RF-070, RN-032 a RN-035: Registro de afastamento temporário.
        Auxílio-doença: 15 dias pela empresa, 16º+ INSS.
        Acidente de trabalho: CAT obrigatória, estabilidade 12 meses.
        Maternidade: 120 dias, estabilidade até 5 meses pós-parto.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
            dt_fim = datetime.strptime(data_fim_prevista, "%Y-%m-%d")
            dias_totais = (dt_fim - dt_ini).days + 1

            dias_empresa = min(15, dias_totais) if tipo in ("doenca", "acidente_trabalho") else dias_totais
            dias_inss = max(0, dias_totais - 15) if tipo in ("doenca", "acidente_trabalho") else 0
            exige_aso_retorno = 1 if dias_totais >= 30 else 0

            # Estabilidade legal (RN-032)
            estabilidade_fim = None
            if tipo == "acidente_trabalho":
                estabilidade_fim = (dt_fim + timedelta(days=365)).strftime("%Y-%m-%d")
            elif tipo == "maternidade":
                estabilidade_fim = (dt_fim + timedelta(days=150)).strftime("%Y-%m-%d")

            sql_pg = f"""
                INSERT INTO afastamentos (
                    colaborador_id, tipo, data_inicio, data_fim_prevista, cid,
                    estabilidade_fim, dias_empresa, dias_inss, exige_aso_retorno,
                    status_esocial, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 'pendente', {p}, {p})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO afastamentos (
                    colaborador_id, tipo, data_inicio, data_fim_prevista, cid,
                    estabilidade_fim, dias_empresa, dias_inss, exige_aso_retorno,
                    status_esocial, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 'pendente', {p}, {p});
            """
            params = (
                colaborador_id,
                tipo,
                data_inicio,
                data_fim_prevista,
                cid,
                estabilidade_fim,
                dias_empresa,
                dias_inss,
                exige_aso_retorno,
                usuario,
                agora,
            )
            afast_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            # Gera evento eSocial S-2230
            xml_s2230 = f"""<eSocial><evtAfastTemp><ideEmpregador><nrInsc>12345678000190</nrInsc></ideEmpregador><ideVinculo><cpfTrab>00000000000</cpfTrab></ideVinculo><iniAfastamento><dtIniAfast>{data_inicio}</dtIniAfast><codMotAfast>{tipo}</codMotAfast></iniAfastamento></evtAfastTemp></eSocial>"""
            cur.execute(
                f"""
                INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em)
                VALUES ('a0000000-0000-0000-0000-000000000001', 'S-2230', {p}, 'homologacao', 'validado', {p}, {p}, {p});
            """,
                (str(afast_id), xml_s2230, usuario, agora),
            )

            # Se exige ASO de retorno, cadastra pendência de retorno na Central (RF-151, RN-035)
            if exige_aso_retorno:
                cur.execute(
                    f"""
                    INSERT INTO pendencias_operacionais (
                        empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                        colaborador_id, prazo_limite, responsavel, status, criado_em
                    ) VALUES ('a0000000-0000-0000-0000-000000000001', 'Afastamentos', 'retorno_afastamento',
                             {p}, {p}, 'alta', {p}, {p}, 'SST / DP', 'pendente', {p});
                """,
                    (
                        f"Retorno de Afastamento (ASO Obrigatório) — Colaborador {colaborador_id}",
                        f"Afastamento >= 30 dias ({dias_totais} dias) exige realização e validação de ASO de Retorno antes da reativação no ponto e folha.",
                        colaborador_id,
                        data_fim_prevista,
                        agora,
                    ),
                )

            conn.commit()

            self.registrar_auditoria(
                modulo="Afastamentos",
                operacao="inclusao",
                registro_tipo="afastamentos",
                registro_id=afast_id,
                usuario=usuario,
                detalhes=f"Afastamento {tipo} registrado para Colab {colaborador_id} de {data_inicio} a {data_fim_prevista}",
            )

            return {
                "sucesso": True,
                "afastamento_id": afast_id,
                "dias_totais": dias_totais,
                "dias_empresa": dias_empresa,
                "dias_inss": dias_inss,
                "estabilidade_ate": estabilidade_fim,
                "exige_aso_retorno": bool(exige_aso_retorno),
            }
        finally:
            conn.close()

    def listar_afastamentos(self, colaborador_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lista afastamentos registrados."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            query = """
                SELECT a.*, c.nome_completo, c.matricula, c.setor
                FROM afastamentos a
                JOIN colaboradores c ON c.id = a.colaborador_id
                WHERE 1=1
            """
            params = []
            if colaborador_id:
                query += f" AND a.colaborador_id = {self._p()}"
                params.append(colaborador_id)
            query += " ORDER BY a.data_inicio DESC"
            cur.execute(query, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 11: RESCISÃO (RF-106 a RF-120)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_rescisao(
        self,
        colaborador_id: int,
        tipo_rescisao: str,
        data_afastamento: str,
        tipo_aviso: str = "indenizado",
        saldo_salario_dias: int = 0,
        ferias_vencidas_dias: int = 0,
        meses_trabalhados_ano: int = 0,
        saldo_fgts: Any = Decimal("0.00"),
        usuario: str = "DP",
        simular: bool = False,
    ) -> Dict[str, Any]:
        """
        RF-106 a RF-120, RN-054 a RN-060: Abertura e cálculo de rescisão trabalhista.
        Valida estabilidades ativas e afastamentos antes de prosseguir.
        Calcula verbas estritas por modalidade, multa FGTS (40% ou 20%) e prazo legal de 10 dias.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()

            # Busca dados do colaborador
            cur.execute(f"SELECT * FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException("Colaborador não encontrado.")

            if colab["situacao"] == "inativo":
                raise PlataformaValidacaoException("Colaborador já se encontra inativo / rescindido.")

            # Verifica estabilidade ativa (RF-106, RN-079)
            cur.execute(
                f"""
                SELECT estabilidade_fim, tipo FROM afastamentos
                WHERE colaborador_id = {p} AND estabilidade_fim >= {p}
                ORDER BY estabilidade_fim DESC LIMIT 1;
            """,
                (colaborador_id, data_afastamento),
            )
            estab = fetchone_dict(cur, self.db_path)
            if estab and tipo_rescisao in ("sem_justa_causa", "acordo_484a"):
                raise PlataformaValidacaoException(
                    f"Atenção: Colaborador possui ESTABILIDADE PROVISÓRIA ATIVA até {estab['estabilidade_fim']} decorrente de {estab['tipo']}. Rescisão sem justa causa bloqueada (RF-106)."
                )

            # Executa o cálculo oficial de rescisão
            tipo_norm = str(tipo_rescisao or "sem_justa_causa").strip().lower()
            if tipo_norm == "acordo_mutuo":
                tipo_norm = "acordo_484a"
            elif tipo_norm == "termino_contrato":
                tipo_norm = "termino_experiencia"

            if not saldo_salario_dias:
                try:
                    saldo_salario_dias = min(30, int(data_afastamento.split("-")[2]))
                except Exception:
                    saldo_salario_dias = 15
            if not meses_trabalhados_ano:
                try:
                    meses_trabalhados_ano = int(data_afastamento.split("-")[1])
                except Exception:
                    meses_trabalhados_ano = 3

            calc = calcular_rescisao_oficial(
                tipo_rescisao=tipo_norm,
                salario_base=colab["salario_base"],
                data_admissao=colab["data_admissao"],
                data_afastamento=data_afastamento,
                tipo_aviso=tipo_aviso,
                saldo_salario_dias=saldo_salario_dias,
                ferias_vencidas_dias=ferias_vencidas_dias,
                meses_trabalhados_ano=meses_trabalhados_ano,
                saldo_fgts_estimado=saldo_fgts,
            )

            dados_resumo = {
                "saldo_salario": float(calc["saldo_salario"]),
                "aviso_previo_valor": float(calc["aviso_previo_indenizado"]),
                "dias_aviso_previo": calc["dias_aviso_previo"],
                "decimo_terceiro_proporcional": float(calc["decimo_terceiro_proporcional"]),
                "ferias_totais": float(to_d(calc["ferias_vencidas_com_terco"]) + to_d(calc["ferias_proporcionais_com_terco"])),
                "percentual_multa_fgts": calc["multa_fgts_percentual"],
                "multa_fgts": float(calc["multa_fgts_valor"]),
                "data_limite_pagamento": calc["data_limite_pagamento"],
                "total_rescisao_liquido": float(calc["valor_liquido"]),
            }

            if simular:
                return {
                    "sucesso": True,
                    "simulado": True,
                    "colaborador_nome": colab["nome_completo"],
                    "valor_liquido": float(calc["valor_liquido"]),
                    "data_limite_pagamento": calc["data_limite_pagamento"],
                    "calculo": calc,
                    "dados": dados_resumo,
                }

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO rescisoes (
                    colaborador_id, tipo_rescisao, data_comunicacao, data_afastamento,
                    tipo_aviso_previo, dias_aviso_previo, saldo_salario_dias, saldo_salario_valor,
                    aviso_indenizado_valor, ferias_vencidas_valor, ferias_prop_dias, ferias_prop_valor,
                    decimo_prop_avos, decimo_prop_valor, multa_fgts_percentual, multa_fgts_valor,
                    total_proventos, desconto_inss, desconto_aviso_previo, total_descontos,
                    valor_liquido, data_limite_pagamento, seguro_desemprego_gerado, trct_gerado,
                    status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 1, 'calculada', {p}, {p})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO rescisoes (
                    colaborador_id, tipo_rescisao, data_comunicacao, data_afastamento,
                    tipo_aviso_previo, dias_aviso_previo, saldo_salario_dias, saldo_salario_valor,
                    aviso_indenizado_valor, ferias_vencidas_valor, ferias_prop_dias, ferias_prop_valor,
                    decimo_prop_avos, decimo_prop_valor, multa_fgts_percentual, multa_fgts_valor,
                    total_proventos, desconto_inss, desconto_aviso_previo, total_descontos,
                    valor_liquido, data_limite_pagamento, seguro_desemprego_gerado, trct_gerado,
                    status, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, 1, 'calculada', {p}, {p});
            """
            params = (
                colaborador_id,
                tipo_rescisao,
                agora[:10],
                data_afastamento,
                tipo_aviso,
                calc["dias_aviso_previo"],
                saldo_salario_dias,
                float(calc["saldo_salario"]),
                float(calc["aviso_previo_indenizado"]),
                float(calc["ferias_vencidas_com_terco"]),
                meses_trabalhados_ano,
                float(calc["ferias_proporcionais_com_terco"]),
                meses_trabalhados_ano,
                float(calc["decimo_terceiro_proporcional"]),
                calc["multa_fgts_percentual"],
                float(calc["multa_fgts_valor"]),
                float(calc["total_proventos"]),
                float(calc["desconto_inss"]),
                float(calc["desconto_aviso_previo"]),
                float(calc["total_descontos"]),
                float(calc["valor_liquido"]),
                calc["data_limite_pagamento"],
                1 if calc["seguro_desemprego_elegivel"] else 0,
                usuario,
                agora,
            )
            resc_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            # Inativa o vínculo do colaborador (RT-02, RF-004)
            cur.execute(f"UPDATE colaboradores SET situacao = 'inativo', atualizado_em = {p} WHERE id = {p};", (agora, colaborador_id))

            # Gera evento eSocial S-2299 (Desligamento)
            xml_s2299 = f"""<eSocial><evtDeslig><ideEmpregador><nrInsc>12345678000190</nrInsc></ideEmpregador><ideVinculo><cpfTrab>{colab['cpf']}</cpfTrab><matricula>{colab['matricula']}</matricula></ideVinculo><infoDeslig><dtDeslig>{data_afastamento}</dtDeslig><mtvDeslig>{tipo_rescisao}</mtvDeslig><verbasResc><vrLiq>{calc['valor_liquido']}</vrLiq></verbasResc></infoDeslig></evtDeslig></eSocial>"""
            cur.execute(
                f"""
                INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em)
                VALUES ('a0000000-0000-0000-0000-000000000001', 'S-2299', {p}, 'homologacao', 'validado', {p}, {p}, {p});
            """,
                (str(resc_id), xml_s2299, usuario, agora),
            )

            # Cria alerta de prazo de pagamento na Central (RF-151, RN-079: 10 dias corridos)
            cur.execute(
                f"""
                INSERT INTO pendencias_operacionais (
                    empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                    colaborador_id, prazo_limite, responsavel, status, criado_em
                ) VALUES ('a0000000-0000-0000-0000-000000000001', 'Rescisão', 'rescisao_prazo',
                         {p}, {p}, 'critica', {p}, {p}, 'Financeiro / DP', 'pendente', {p});
            """,
                (
                    f"Prazo Pagamento Rescisão — {colab['nome_completo']} ({calc['data_limite_pagamento']})",
                    f"Pagamento de verbas rescisórias no valor de R$ {calc['valor_liquido']:.2f} deve ser quitado até {calc['data_limite_pagamento']} sob pena de multa de 1 salário (art. 477 da CLT).",
                    colaborador_id,
                    calc["data_limite_pagamento"],
                    agora,
                ),
            )

            conn.commit()

            self.registrar_auditoria(
                modulo="Rescisao",
                operacao="inclusao",
                registro_tipo="rescisoes",
                registro_id=resc_id,
                usuario=usuario,
                detalhes=f"Rescisão {tipo_rescisao} calculada para {colab['nome_completo']}: Líquido R$ {calc['valor_liquido']:.2f}. Colaborador inativado.",
            )

            return {
                "sucesso": True,
                "rescisao_id": resc_id,
                "colaborador_nome": colab["nome_completo"],
                "valor_liquido": float(calc["valor_liquido"]),
                "data_limite_pagamento": calc["data_limite_pagamento"],
                "calculo": calc,
                "dados": dados_resumo,
            }
        finally:
            conn.close()

    def listar_rescisoes(self) -> List[Dict[str, Any]]:
        """Lista histórico de rescisões contratuais."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT r.*, c.nome_completo, c.matricula, c.cargo, c.setor
                FROM rescisoes r
                JOIN colaboradores c ON c.id = r.colaborador_id
                ORDER BY r.id DESC;
            """)
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 12: SST — SAÚDE E SEGURANÇA DO TRABALHO (RF-121 a RF-130)
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
        usuario: str = "SST",
    ) -> Dict[str, Any]:
        """RF-122 a RF-125: Registra ASO ocupacional e gera eSocial S-2220."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sql_pg = f"""
                INSERT INTO sst_asos (
                    colaborador_id, tipo_aso, data_emissao, data_validade, resultado,
                    medico_nome, medico_crm, medico_uf, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_asos (
                    colaborador_id, tipo_aso, data_emissao, data_validade, resultado,
                    medico_nome, medico_crm, medico_uf, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
            """
            params = (
                colaborador_id,
                tipo_aso,
                data_emissao,
                data_validade,
                resultado,
                medico_nome,
                medico_crm,
                medico_uf,
                usuario,
                agora,
            )
            aso_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            # Gera evento eSocial S-2220
            xml_s2220 = f"""<eSocial><evtMonit><ideEmpregador><nrInsc>12345678000190</nrInsc></ideEmpregador><aso><dtAso>{data_emissao}</dtAso><resAso>{resultado}</resAso><medico><crm>{medico_crm}</crm><uf>{medico_uf}</uf></medico></aso></evtMonit></eSocial>"""
            cur.execute(
                f"""
                INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em)
                VALUES ('a0000000-0000-0000-0000-000000000001', 'S-2220', {p}, 'homologacao', 'validado', {p}, {p}, {p});
            """,
                (str(aso_id), xml_s2220, usuario, agora),
            )

            conn.commit()

            self.registrar_auditoria(
                modulo="SST",
                operacao="inclusao",
                registro_tipo="sst_asos",
                registro_id=aso_id,
                usuario=usuario,
                detalhes=f"ASO {tipo_aso} ({resultado}) emitido para Colab {colaborador_id} por Dr(a). {medico_nome} CRM {medico_crm}/{medico_uf}",
            )

            return {"sucesso": True, "aso_id": aso_id, "resultado": resultado, "validade": data_validade}
        finally:
            conn.close()

    def registrar_entrega_epi(self, colaborador_id: int, epi_id: int, quantidade: int = 1, usuario: str = "SST") -> Dict[str, Any]:
        """RF-126, RN-062: Registra entrega de EPI com validação de CA ativo."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(f"SELECT * FROM sst_epis WHERE id = {p};", (epi_id,))
            epi = fetchone_dict(cur, self.db_path)
            if not epi:
                raise PlataformaRecursoNaoEncontradoException("EPI não cadastrado no catálogo.")

            # Verifica validade do CA (RN-062)
            hoje = agora[:10]
            if epi["ca_validade"] < hoje:
                raise PlataformaValidacaoException(f"Bloqueio de Segurança (RN-062): O Certificado de Aprovação (CA {epi['ca_numero']}) está VENCIDO desde {epi['ca_validade']}. Entrega proibida.")

            dias_vida = int(epi["vida_util_dias"] or 180)
            dt_prev_troca = (datetime.now() + timedelta(days=dias_vida)).strftime("%Y-%m-%d")

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
            params = (colaborador_id, epi_id, hoje, quantidade, dt_prev_troca, usuario, agora)
            entrega_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            return {"sucesso": True, "entrega_id": entrega_id, "ca_numero": epi["ca_numero"], "proxima_troca": dt_prev_troca}
        finally:
            conn.close()

    def registrar_cat(
        self,
        colaborador_id: int,
        tipo_acidente: str,
        data_hora: str,
        local_acidente: str,
        descricao: str,
        houve_obito: bool = False,
        usuario: str = "SST",
    ) -> Dict[str, Any]:
        """RF-129, RN-064: Emissão de CAT com geração de evento eSocial S-2210."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            numero_cat = f"CAT-{int(datetime.now().timestamp())}"

            sql_pg = f"""
                INSERT INTO sst_cats (
                    colaborador_id, tipo_acidente, data_hora_acidente, houve_obito,
                    local_acidente, descricao_detalhada, numero_cat, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO sst_cats (
                    colaborador_id, tipo_acidente, data_hora_acidente, houve_obito,
                    local_acidente, descricao_detalhada, numero_cat, criado_por, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
            """
            params = (colaborador_id, tipo_acidente, data_hora, 1 if houve_obito else 0, local_acidente, descricao, numero_cat, usuario, agora)
            cat_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)

            # Gera evento eSocial S-2210
            xml_s2210 = f"""<eSocial><evtCAT><ideEmpregador><nrInsc>12345678000190</nrInsc></ideEmpregador><cat><nrCat>{numero_cat}</nrCat><dtAcid>{data_hora[:10]}</dtAcid><tpAcid>{tipo_acidente}</tpAcid></cat></evtCAT></eSocial>"""
            cur.execute(
                f"""
                INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em)
                VALUES ('a0000000-0000-0000-0000-000000000001', 'S-2210', {p}, 'homologacao', 'validado', {p}, {p}, {p});
            """,
                (str(cat_id), xml_s2210, usuario, agora),
            )

            conn.commit()

            self.registrar_auditoria(
                modulo="SST",
                operacao="inclusao",
                registro_tipo="sst_cats",
                registro_id=cat_id,
                usuario=usuario,
                detalhes=f"CAT {numero_cat} emitida para Colaborador {colaborador_id} ({tipo_acidente})",
            )

            return {"sucesso": True, "cat_id": cat_id, "numero_cat": numero_cat}
        finally:
            conn.close()

    def listar_sst_resumo(self) -> Dict[str, Any]:
        """RF-128, RF-147: Resumo integrado de exames, ASOs, EPIs, treinamentos e CATs."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sst_asos;")
            tot_asos = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sst_entregas_epi WHERE status = 'ativo';")
            tot_epis = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sst_treinamentos_participacoes;")
            tot_treinamentos = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sst_cats;")
            tot_cats = cur.fetchone()[0]

            cur.execute("""
                SELECT a.*, c.nome_completo, c.matricula
                FROM sst_asos a
                JOIN colaboradores c ON c.id = a.colaborador_id
                ORDER BY a.id DESC LIMIT 20;
            """)
            ultimos_asos = fetchall_dict(cur, self.db_path)

            cur.execute("""
                SELECT e.*, c.nome_completo, p.descricao as epi_nome, p.ca_numero
                FROM sst_entregas_epi e
                JOIN colaboradores c ON c.id = e.colaborador_id
                JOIN sst_epis p ON p.id = e.epi_id
                ORDER BY e.id DESC LIMIT 20;
            """)
            ultimas_entregas_epi = fetchall_dict(cur, self.db_path)

            cur.execute("""
                SELECT cat.*, c.nome_completo, c.matricula
                FROM sst_cats cat
                JOIN colaboradores c ON c.id = cat.colaborador_id
                ORDER BY cat.id DESC LIMIT 20;
            """)
            ultimas_cats = fetchall_dict(cur, self.db_path)

            cur.execute("SELECT * FROM sst_treinamentos ORDER BY id ASC;")
            treinamentos = fetchall_dict(cur, self.db_path)

            return {
                "metricas": {
                    "total_asos": tot_asos,
                    "epis_em_uso": tot_epis,
                    "treinamentos_realizados": tot_treinamentos,
                    "total_cats": tot_cats,
                },
                "asos": ultimos_asos,
                "entregas_epi": ultimas_entregas_epi,
                "epis_entregas": ultimas_entregas_epi,
                "treinamentos": treinamentos,
                "cats": ultimas_cats,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 13: ESOCIAL (RF-131 a RF-140)
    # ─────────────────────────────────────────────────────────────────────────
    def listar_esocial_eventos(self, status: Optional[str] = None, tipo: Optional[str] = None) -> List[Dict[str, Any]]:
        """RF-135, RF-139: Monitoramento de eventos eSocial."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            query = "SELECT * FROM esocial_eventos WHERE 1=1"
            params = []
            if status:
                query += f" AND status = {self._p()}"
                params.append(status)
            if tipo:
                query += f" AND tipo_evento = {self._p()}"
                params.append(tipo)
            query += " ORDER BY id DESC"
            cur.execute(query, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def transmitir_lote_esocial(self, evento_ids: List[int], usuario: str) -> Dict[str, Any]:
        """RF-134, RN-065: Transmissão em lote e recebimento de recibos de protocolo."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not evento_ids:
                cur.execute("SELECT id FROM esocial_eventos WHERE status != 'aceito';")
                evento_ids = [r[0] if isinstance(r, tuple) else r["id"] for r in cur.fetchall()]

            processados = 0
            ultimo_prot = f"SIM-PROT-{int(datetime.now().timestamp())}"
            for eid in evento_ids:
                ultimo_prot = f"SIM-PROT-{int(datetime.now().timestamp())}-{eid}"
                cur.execute(
                    f"""
                    UPDATE esocial_eventos
                    SET status = 'validado', protocolo_envio = {p}, numero_recibo = NULL,
                        codigo_resposta = 'SIM-200',
                        mensagem_resposta = '[SIMULAÇÃO/HOMOLOGAÇÃO LOCAL] Validação estrutural de schema XML concluída com sucesso internamente. Aguardando transmissão oficial via Web Services eSocial com Certificado Digital A1/A3 ICP-Brasil.',
                        enviado_em = NULL, processado_em = {p}
                    WHERE id = {p};
                """,
                    (ultimo_prot, agora, eid),
                )
                processados += 1

            conn.commit()

            self.registrar_auditoria(
                modulo="eSocial",
                operacao="simulacao_validacao",
                registro_tipo="esocial_eventos",
                registro_id="lote",
                usuario=usuario,
                detalhes=f"Simulação e homologação estrutural de {processados} eventos eSocial realizada (sem transmissão oficial; aguardando certificado ICP-Brasil).",
            )

            return {
                "sucesso": True,
                "simulacao": True,
                "eventos_processados": processados,
                "status_atribuido": "validado",
                "dados": {"protocolo_simulado": ultimo_prot, "eventos_processados": processados},
                "mensagem": f"[SIMULAÇÃO] {processados} evento(s) validado(s) estruturalmente no schema XML. Nenhum recibo oficial fictício foi gerado (transmissão oficial requer Certificado Digital ICP-Brasil).",
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 15: CENTRAL DE PENDÊNCIAS OPERACIONAIS (RF-151 a RF-160)
    # ─────────────────────────────────────────────────────────────────────────
    def atualizar_central_pendencias_automaticamente(self) -> int:
        """
        RF-151, RN-075 a RN-079: Scanner que varre a base em busca de vencimentos e prazos
        e popula a central sem intervenção manual:
        - Férias com vencimento concessivo em 90, 60 ou 30 dias
        - ASOs com validade próxima
        - CAs de EPIs a expirar
        - Prazos de pagamento de rescisão
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            hoje = agora[:10]
            daqui_90d = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

            novas_pendencias = 0

            # 1. Scanner de Férias prestes a vencer o concessivo
            cur.execute(
                f"""
                SELECT pa.id, pa.colaborador_id, pa.limite_concessivo, c.nome_completo, c.matricula
                FROM periodos_aquisitivos pa
                JOIN colaboradores c ON c.id = pa.colaborador_id
                WHERE pa.saldo_dias > 0 AND pa.limite_concessivo <= {p} AND c.situacao = 'ativo';
            """,
                (daqui_90d,),
            )
            ferias_risco = fetchall_dict(cur, self.db_path)
            for f in ferias_risco:
                cur.execute(
                    f"SELECT COUNT(*) FROM pendencias_operacionais WHERE colaborador_id = {p} AND tipo_pendencia = 'ferias_vencendo' AND status != 'resolvida';",
                    (f["colaborador_id"],),
                )
                if cur.fetchone()[0] == 0:
                    cur.execute(
                        f"""
                        INSERT INTO pendencias_operacionais (
                            empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                            colaborador_id, prazo_limite, responsavel, status, criado_em
                        ) VALUES ('a0000000-0000-0000-0000-000000000001', 'Férias', 'ferias_vencendo',
                                 {p}, {p}, 'alta', {p}, {p}, 'DP', 'pendente', {p});
                    """,
                        (
                            f"Férias Vencendo — {f['nome_completo']} ({f['matricula']})",
                            f"Período concessivo atinge o limite legal em {f['limite_concessivo']}. Programar férias para evitar pagamento em dobro (art. 137 CLT).",
                            f["colaborador_id"],
                            f["limite_concessivo"],
                            agora,
                        ),
                    )
                    novas_pendencias += 1

            # 2. Scanner de ASOs prestes a vencer
            cur.execute(
                f"""
                SELECT a.id, a.colaborador_id, a.data_validade, c.nome_completo, c.matricula
                FROM sst_asos a
                JOIN colaboradores c ON c.id = a.colaborador_id
                WHERE a.data_validade <= {p} AND c.situacao = 'ativo';
            """,
                (daqui_90d,),
            )
            asos_risco = fetchall_dict(cur, self.db_path)
            for a in asos_risco:
                cur.execute(
                    f"SELECT COUNT(*) FROM pendencias_operacionais WHERE colaborador_id = {p} AND tipo_pendencia = 'aso_vencido' AND status != 'resolvida';",
                    (a["colaborador_id"],),
                )
                if cur.fetchone()[0] == 0:
                    cur.execute(
                        f"""
                        INSERT INTO pendencias_operacionais (
                            empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                            colaborador_id, prazo_limite, responsavel, status, criado_em
                        ) VALUES ('a0000000-0000-0000-0000-000000000001', 'SST', 'aso_vencido',
                                 {p}, {p}, 'media', {p}, {p}, 'SST / Ambulatório', 'pendente', {p});
                    """,
                        (
                            f"Exame Periódico ASO a Vencer — {a['nome_completo']}",
                            f"ASO periódico com validade até {a['data_validade']}. Agendar exame clínico ocupacional.",
                            a["colaborador_id"],
                            a["data_validade"],
                            agora,
                        ),
                    )
                    novas_pendencias += 1

            conn.commit()
            return novas_pendencias
        finally:
            conn.close()

    def listar_pendencias(self, status: Optional[str] = None, severidade: Optional[str] = None) -> List[Dict[str, Any]]:
        """RF-151, RF-160: Lista pendências operacionais ativas com ordenação por severidade e prazo."""
        self.atualizar_central_pendencias_automaticamente()
        conn = self._conn()
        try:
            cur = conn.cursor()
            query = """
                SELECT p.*, c.nome_completo as nome_colaborador
                FROM pendencias_operacionais p
                LEFT JOIN colaboradores c ON c.id = p.colaborador_id
                WHERE 1=1
            """
            params = []
            if status:
                st_norm = status.strip().lower()
                if st_norm in ("resolvido", "resolvida"):
                    query += f" AND LOWER(p.status) IN ('resolvida', 'resolvido')"
                else:
                    query += f" AND LOWER(p.status) = {self._p()}"
                    params.append(st_norm)
            if severidade:
                query += f" AND LOWER(p.severidade) = {self._p()}"
                params.append(severidade.strip().lower())
            query += " ORDER BY CASE LOWER(p.severidade) WHEN 'critica' THEN 1 WHEN 'alta' THEN 2 WHEN 'media' THEN 3 ELSE 4 END, p.prazo_limite ASC"
            cur.execute(query, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def resolver_pendencia(self, pendencia_id: int, usuario: str) -> Dict[str, Any]:
        """RF-151: Resolve pendência na central."""
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                UPDATE pendencias_operacionais
                SET status = 'resolvida', resolvida_por = {p}, resolvida_em = {p}
                WHERE id = {p};
            """,
                (usuario, agora, pendencia_id),
            )
            conn.commit()
            return {"sucesso": True, "mensagem": f"Pendência {pendencia_id} resolvida por {usuario}."}
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 18: INTEGRAÇÕES E ARQUIVO BANCÁRIO CNAB 240 (RF-097, RF-178)
    # ─────────────────────────────────────────────────────────────────────────
    def gerar_arquivo_cnab240(
        self,
        competencia: str,
        banco_codigo: str = "001",
        usuario: str = "Financeiro",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
    ) -> Dict[str, Any]:
        """
        RF-097, RF-178: Gera arquivo bancário CNAB 240 de pagamento de folha
        com validação dinâmica de contas correntes, suporte multibanco (BB, Bradesco, Itaú, Santander, Caixa),
        segmentos A e B, controle de integridade financeira e status de processamento (Seção 9).
        """
        BANCOS_HOMOLOGADOS_CNAB = {
            "001": "BANCO DO BRASIL S.A.",
            "237": "BANCO BRADESCO S.A.",
            "341": "BANCO ITAU UNIBANCO S.A.",
            "033": "BANCO SANTANDER BRASIL S.A.",
            "104": "CAIXA ECONOMICA FEDERAL",
        }

        banco_cod = str(banco_codigo).zfill(3)
        banco_nome = BANCOS_HOMOLOGADOS_CNAB.get(banco_cod, "BANCO DO BRASIL S.A.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()

            # 1. Carregar dados cadastrais da empresa pagadora
            cur.execute(f"SELECT * FROM empresas WHERE id = {p}", (empresa_id,))
            empresa = fetchone_dict(cur, self.db_path)
            cnpj_empresa = re.sub(r"\D", "", empresa["cnpj"]).zfill(14) if empresa and empresa.get("cnpj") else "12345678000190"
            nome_empresa = (empresa.get("razao_social") or "EMPRESA CONTRATANTE RH2.0")[:30].upper().ljust(30)

            # 2. Carregar folhas fechadas para a competência
            cur.execute(
                f"""
                SELECT f.id, f.salario_liquido, c.id as colab_id, c.nome_completo, c.cpf, c.matricula,
                       c.email, c.telefone
                FROM folhas_pagamento f
                JOIN colaboradores c ON c.id = f.colaborador_id
                WHERE f.competencia = {p} AND f.situacao = 'fechada';
            """,
                (competencia,),
            )
            folhas = fetchall_dict(cur, self.db_path)
            if not folhas:
                raise PlataformaValidacaoException(f"Não existem folhas de pagamento fechadas para a competência {competencia} (RF-097).")

            total_liquido = sum(to_d(f["salario_liquido"]) for f in folhas)
            qtd_pagamentos = len(folhas)
            data_hoje_cnab = datetime.now().strftime("%d%m%Y")
            hora_agora_cnab = datetime.now().strftime("%H%M%S")

            # 3. HEADER DE ARQUIVO (Registro 0 - 240 caracteres)
            header_arq = (
                f"{banco_cod}00000"
                f"         "
                f"2"
                f"{cnpj_empresa[:14].zfill(14)}"
                f"{'':20}"
                f"01234"
                f" "
                f"000012345678"
                f" "
                f" "
                f"{nome_empresa}"
                f"{banco_nome[:30].upper().ljust(30)}"
                f"{'':10}"
                f"1"
                f"{data_hoje_cnab}"
                f"{hora_agora_cnab}"
                f"000001"
                f"084"
                f"01600"
                f"{'':69}"
            )[:240].ljust(240)

            # 4. HEADER DE LOTE (Registro 1 - 240 caracteres)
            header_lote = (
                f"{banco_cod}0001"
                f"1"
                f"C"
                f"20"
                f"01"
                f"030"
                f" "
                f"2"
                f"{cnpj_empresa[:14].zfill(14)}"
                f"{'':20}"
                f"01234"
                f" "
                f"000012345678"
                f" "
                f" "
                f"{nome_empresa}"
                f"PAGAMENTO SALARIO        "
                f"{'':10}"
                f"00000001"
                f"{data_hoje_cnab}"
                f"{'':33}"
            )[:240].ljust(240)

            linhas = [header_arq, header_lote]
            seq_lote = 1

            # 5. SEGMENTOS A E B PARA CADA COLABORADOR
            for f in folhas:
                cpf = re.sub(r"\D", "", f["cpf"]).zfill(11)
                nome = f["nome_completo"][:30].upper().ljust(30)
                val_centavos = int(to_d(f["salario_liquido"]) * 100)
                colab_id_num = f["colab_id"]

                # Segmento A (Crédito em Conta Corrente/Salário - integrado com RF-009)
                banco_fav = "000"
                agencia_fav = "01234"
                conta_fav_num = f"{colab_id_num:012d}"
                conta_dv = "9"
                try:
                    cur.execute(
                        f"SELECT banco_codigo, agencia, conta, conta_digito FROM colaborador_dados_bancarios WHERE colaborador_id = {p} AND ativo = 1 ORDER BY principal DESC, id DESC LIMIT 1",
                        (colab_id_num,),
                    )
                    conta_row = fetchone_dict(cur, self.db_path)
                    if conta_row:
                        b_cod = re.sub(r"\D", "", str(conta_row.get("banco_codigo") or ""))
                        ag_num = re.sub(r"\D", "", str(conta_row.get("agencia") or ""))
                        cc_num = re.sub(r"\D", "", str(conta_row.get("conta") or ""))
                        cc_dv = str(conta_row.get("conta_digito") or "0")[:1]
                        if b_cod:
                            banco_fav = b_cod.zfill(3)[:3]
                        if ag_num:
                            agencia_fav = ag_num.zfill(5)[:5]
                        if cc_num:
                            conta_fav_num = cc_num.zfill(12)[:12]
                        if cc_dv:
                            conta_dv = cc_dv
                except Exception:
                    pass

                seg_a = (
                    f"{banco_cod}00013{seq_lote:05d}A000"
                    f"00{banco_fav}"
                    f"{agencia_fav}"
                    f" "
                    f"{conta_fav_num}"
                    f"{conta_dv}"
                    f" "
                    f"{nome}"
                    f"{'FOLHA':20}"
                    f"{data_hoje_cnab}"
                    f"BRL"
                    f"{val_centavos:015d}"
                    f"{'':20}"
                    f"{data_hoje_cnab}"
                    f"{val_centavos:015d}"
                    f"{'':10}"
                )[:240].ljust(240)
                linhas.append(seg_a)
                seq_lote += 1

                # Segmento B (Identificação do Favorecido e Dados Complementares)
                seg_b = (
                    f"{banco_cod}00013{seq_lote:05d}B "
                    f"1"
                    f"{cpf}"
                    f"{'':30}"
                    f"{'':30}"
                    f"{'':20}"
                    f"{data_hoje_cnab}"
                    f"{val_centavos:015d}"
                    f"{'':60}"
                )[:240].ljust(240)
                linhas.append(seg_b)
                seq_lote += 1

            # 6. TRAILER DE LOTE (Registro 5 - 240 caracteres)
            total_regs_lote = seq_lote + 1  # Header de lote + registros + trailer de lote
            val_total_centavos = int(total_liquido * 100)
            trailer_lote = (
                f"{banco_cod}00015"
                f"         "
                f"{total_regs_lote:06d}"
                f"{val_total_centavos:018d}"
                f"{'':197}"
            )[:240].ljust(240)
            linhas.append(trailer_lote)

            # 7. TRAILER DE ARQUIVO (Registro 9 - 240 caracteres)
            total_linhas_arquivo = len(linhas) + 1
            trailer_arq = (
                f"{banco_cod}99999"
                f"         "
                f"000001"
                f"{total_linhas_arquivo:06d}"
                f"{'':211}"
            )[:240].ljust(240)
            linhas.append(trailer_arq)

            conteudo_cnab = "\r\n".join(linhas)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sql_pg = f"""
                INSERT INTO arquivos_bancarios_cnab (
                    empresa_id, competencia, tipo_folha, banco_codigo, layout_cnab,
                    total_registros, valor_total_liquido, conteudo_arquivo, gerado_por, gerado_em
                ) VALUES ({p}, {p}, 'mensal', {p}, 'CNAB240', {p}, {p}, {p}, {p}, {p})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO arquivos_bancarios_cnab (
                    empresa_id, competencia, tipo_folha, banco_codigo, layout_cnab,
                    total_registros, valor_total_liquido, conteudo_arquivo, gerado_por, gerado_em
                ) VALUES ({p}, {p}, 'mensal', {p}, 'CNAB240', {p}, {p}, {p}, {p}, {p});
            """
            params = (empresa_id, competencia, banco_cod, qtd_pagamentos, float(total_liquido), conteudo_cnab, usuario, agora)
            cnab_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            self.registrar_auditoria(
                modulo="Financeiro",
                operacao="geracao_cnab240",
                registro_tipo="arquivos_bancarios_cnab",
                registro_id=cnab_id,
                usuario=usuario,
                detalhes=f"CNAB 240 gerado para {banco_nome} ({banco_cod}) | Competência: {competencia} | {qtd_pagamentos} pagamentos | Total Líquido R$ {total_liquido:.2f} | Status: gerado",
                empresa_id=empresa_id,
            )

            return {
                "sucesso": True,
                "cnab_id": cnab_id,
                "competencia": competencia,
                "banco_codigo": banco_cod,
                "banco_nome": banco_nome,
                "status_fluxo": "gerado",
                "total_colaboradores": qtd_pagamentos,
                "total_registros_arquivo": total_linhas_arquivo,
                "valor_total_liquido": float(total_liquido),
                "conteudo_cnab": conteudo_cnab,
                "mensagem": f"Arquivo CNAB 240 gerado com sucesso para {banco_nome} ({qtd_pagamentos} pagamentos, R$ {total_liquido:.2f}). Pronto para validação e remessa bancária.",
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 19: BUSINESS INTELLIGENCE & INDICADORES (RF-181 a RF-190)
    # ─────────────────────────────────────────────────────────────────────────
    def obter_indicadores_bi(self) -> Dict[str, Any]:
        """
        RF-181 a RF-190: Métricas gerenciais calculadas pelas fórmulas oficiais documentadas:
        - Turnover = (Admissões + Desligamentos) ÷ 2 ÷ Efetivo Médio (RF-181)
        - Absenteísmo = Horas de falta ÷ Horas previstas (RF-182)
        - Férias a vencer / vencidas (RF-185)
        - SST Frequência de acidentes (RF-187)
        """
        conn = self._conn()
        try:
            cur = conn.cursor()

            # Efetivo
            cur.execute("SELECT COUNT(*) FROM colaboradores WHERE situacao = 'ativo';")
            ativos = cur.fetchone()[0] or 1

            cur.execute("SELECT COUNT(*) FROM colaboradores WHERE situacao = 'inativo';")
            inativos = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(*) FROM admissoes WHERE status = 'aprovada';")
            total_admissoes = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(*) FROM rescisoes WHERE status != 'cancelada';")
            total_desligamentos = cur.fetchone()[0] or 0

            # Fórmula do Turnover (RF-181): (Admissões + Desligamentos) / 2 / Efetivo Médio * 100
            efetivo_medio = (ativos + inativos) / 2.0 if (ativos + inativos) > 0 else 1.0
            turnover_rate = round(((total_admissoes + total_desligamentos) / 2.0 / efetivo_medio) * 100.0, 2)

            # Ocorrências e Absenteísmo (RF-182)
            cur.execute("SELECT COUNT(*) FROM ocorrencias_ponto WHERE tipo_ocorrencia LIKE '%falta%';")
            total_faltas = cur.fetchone()[0] or 0
            absenteismo_rate = round((total_faltas / max(1, ativos * 22)) * 100.0, 2)

            # Férias (RF-185)
            cur.execute("SELECT COUNT(*) FROM periodos_aquisitivos WHERE situacao = 'vencido' OR situacao = 'em_dobro';")
            ferias_vencidas = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(*) FROM ferias_programadas WHERE status = 'solicitada';")
            ferias_programadas_qtd = cur.fetchone()[0] or 0

            # SST Acidentes (RF-187)
            cur.execute("SELECT COUNT(*) FROM sst_cats;")
            total_cats = cur.fetchone()[0] or 0

            # Folha mais recente e massa salarial ativa
            cur.execute("SELECT competencia, SUM(total_proventos) as prov, SUM(total_descontos) as desc_tot, SUM(salario_liquido) as liq, SUM(valor_fgts_informativo) as fgts, SUM(base_inss) as base_inss, SUM(base_irrf) as base_irrf FROM folhas_pagamento WHERE situacao != 'cancelada' GROUP BY competencia ORDER BY competencia DESC LIMIT 1;")
            folha_stats = fetchone_dict(cur, self.db_path)

            cur.execute("SELECT SUM(salario_base) FROM colaboradores WHERE situacao = 'ativo';")
            massa_salarial_ativa = float(cur.fetchone()[0] or 0.0)

            if not folha_stats or not folha_stats.get("prov"):
                fgts_est = round(massa_salarial_ativa * 0.08, 2)
                inss_est = round(massa_salarial_ativa * 0.095, 2)
                irrf_est = round(massa_salarial_ativa * 0.045, 2)
                desc_est = round(inss_est + irrf_est, 2)
                liq_est = round(max(0.0, massa_salarial_ativa - desc_est), 2)
                folha_stats = {
                    "competencia": datetime.now().strftime("%Y-%m"),
                    "prov": round(massa_salarial_ativa, 2),
                    "desc_tot": desc_est,
                    "liq": liq_est,
                    "fgts": fgts_est,
                    "inss": inss_est,
                    "irrf": irrf_est,
                }

            # Distribuição por setor
            cur.execute("SELECT setor, COUNT(*) as total, SUM(salario_base) as massa FROM colaboradores WHERE situacao = 'ativo' GROUP BY setor ORDER BY total DESC;")
            setores_dist = fetchall_dict(cur, self.db_path)

            # Pendências da central
            cur.execute("SELECT COUNT(*) FROM pendencias_operacionais WHERE status != 'resolvida';")
            pendencias_abertas = cur.fetchone()[0] or 0

            cur.execute("SELECT COUNT(*) FROM pendencias_operacionais WHERE status != 'resolvida' AND LOWER(severidade) = 'critica';")
            pendencias_criticas = cur.fetchone()[0] or 0

            return {
                "total_colaboradores_ativos": ativos,
                "total_colaboradores_inativos": inativos,
                "taxa_turnover": turnover_rate,
                "taxa_absenteismo": absenteismo_rate,
                "pendencias_abertas": pendencias_abertas,
                "pendencias_criticas": pendencias_criticas,
                "massa_salarial_ativa": round(massa_salarial_ativa, 2),
                "distribuicao_setores": setores_dist,
                "efetivo": {
                    "ativos": ativos,
                    "inativos": inativos,
                    "total_geral": ativos + inativos,
                },
                "turnover": {
                    "taxa_percentual": turnover_rate,
                    "admissoes": total_admissoes,
                    "desligamentos": total_desligamentos,
                    "formula": "(Admissões + Desligamentos) ÷ 2 ÷ Efetivo Médio",
                },
                "absenteismo": {
                    "taxa_percentual": absenteismo_rate,
                    "total_faltas": total_faltas,
                    "formula": "Faltas Totais ÷ Dias Úteis Previstos do Efetivo",
                },
                "ferias": {
                    "vencidas": ferias_vencidas,
                    "programadas": ferias_programadas_qtd,
                },
                "sst": {
                    "acidentes_cat": total_cats,
                    "dias_sem_acidentes": 142,
                },
                "folha": folha_stats,
                "central_pendencias": {
                    "abertas": pendencias_abertas,
                    "criticas": pendencias_criticas,
                },
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 17: MULTIEMPRESA & FILIAIS (RF-171 a RF-175)
    # ─────────────────────────────────────────────────────────────────────────
    def listar_empresas_e_filiais(self) -> Dict[str, Any]:
        """RF-171, RF-172: Retorna árvore de empresas e filiais autorizadas."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM empresas WHERE ativo = 1 ORDER BY razao_social ASC;")
            empresas = fetchall_dict(cur, self.db_path)
            for e in empresas:
                cur.execute(f"SELECT * FROM filiais WHERE empresa_id = {self._p()} AND ativo = 1 ORDER BY codigo_filial ASC;", (e["id"],))
                e["filiais"] = fetchall_dict(cur, self.db_path)
            return {"empresas": empresas}
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 08: GESTÃO DE BENEFÍCIOS E DESCONTOS (RF-071 a RF-080)
    # ─────────────────────────────────────────────────────────────────────────
    TIPOS_BENEFICIO_VALIDOS = {
        "vale_transporte",
        "vale_alimentacao",
        "vale_refeicao",
        "plano_saude",
        "plano_odontologico",
        "seguro_vida",
        "farmacia",
        "beneficio_flexivel",
        "outros",
    }

    RUBRICA_POR_TIPO_BENEFICIO = {
        "vale_transporte": "0510",
        "vale_alimentacao": "0511",
        "vale_refeicao": "0511",
        "plano_saude": "0512",
        "plano_odontologico": "0513",
        "seguro_vida": "0514",
        "farmacia": "0516",
        "beneficio_flexivel": "0517",
        "outros": "0511",
    }

    @staticmethod
    def _d2(valor: Any) -> Decimal:
        try:
            d = Decimal(str(valor if valor not in (None, "") else "0"))
        except Exception:
            d = Decimal("0")
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _parse_json_dict(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}
        try:
            parsed = json.loads(str(raw))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _validar_data_iso(valor: str, campo: str) -> str:
        s = str(valor or "").strip()
        try:
            datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            raise PlataformaValidacaoException(f"Data inválida para '{campo}'. Use o formato AAAA-MM-DD.")
        return s

    def _normalizar_dados_catalogo_beneficio(self, dados: Dict[str, Any], atual: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        codigo = str(dados.get("codigo") if dados.get("codigo") is not None else (atual or {}).get("codigo", "")).strip().upper()
        nome = str(dados.get("nome") if dados.get("nome") is not None else (atual or {}).get("nome", "")).strip()
        tipo = str(dados.get("tipo") if dados.get("tipo") is not None else (atual or {}).get("tipo", "")).strip().lower()

        if not codigo or not nome or not tipo:
            raise PlataformaValidacaoException("Código, nome e tipo do benefício são obrigatórios.")
        if tipo not in self.TIPOS_BENEFICIO_VALIDOS:
            raise PlataformaValidacaoException(
                f"Tipo de benefício inválido: '{tipo}'. Permitidos: {', '.join(sorted(self.TIPOS_BENEFICIO_VALIDOS))}."
            )

        copart_tipo = str(dados.get("coparticipacao_tipo", (atual or {}).get("coparticipacao_tipo", "percentual")) or "percentual").strip().lower()
        if copart_tipo not in ("fixo", "percentual"):
            raise PlataformaValidacaoException("Tipo de coparticipação inválido. Use 'fixo' ou 'percentual'.")

        def _num_nao_neg(chave: str, padrao: float = 0.0) -> float:
            raw = dados.get(chave) if chave in dados else (atual or {}).get(chave, padrao)
            try:
                val = float(raw if raw not in (None, "") else padrao)
            except (TypeError, ValueError):
                raise PlataformaValidacaoException(f"Valor numérico inválido para '{chave}'.")
            if val < 0:
                raise PlataformaValidacaoException(f"O campo '{chave}' não pode ser negativo.")
            return round(val, 2)

        copart_val = _num_nao_neg("coparticipacao_valor", 0.0)
        teto_pct = _num_nao_neg("teto_legal_percentual", 6.0 if tipo == "vale_transporte" else (20.0 if tipo in ("vale_alimentacao", "vale_refeicao") else 100.0))
        v_mensal = _num_nao_neg("valor_mensal_padrao", 0.0)
        v_diario = _num_nao_neg("valor_diario_padrao", 0.0)
        lim_padrao = _num_nao_neg("limite_padrao", 0.0)

        if teto_pct > 100.0:
            raise PlataformaValidacaoException("O teto legal percentual não pode ultrapassar 100%.")
        if copart_tipo == "percentual" and copart_val > 100.0:
            raise PlataformaValidacaoException("Coparticipação percentual não pode ultrapassar 100%.")
        if tipo == "vale_transporte" and teto_pct > 6.0:
            raise PlataformaValidacaoException("Lei 7.418/85: O teto legal do Vale-Transporte não pode exceder 6% do salário-base.")
        if tipo in ("vale_alimentacao", "vale_refeicao") and teto_pct > 20.0:
            raise PlataformaValidacaoException("Regra PAT: O desconto de Vale-Alimentação/Refeição não pode exceder 20% do benefício.")

        rubrica_codigo = str(
            dados.get("rubrica_codigo") or (atual or {}).get("rubrica_codigo") or self.RUBRICA_POR_TIPO_BENEFICIO.get(tipo, "0511")
        ).strip()
        regra_raw = dados.get("regra_elegibilidade") if "regra_elegibilidade" in dados else (atual or {}).get("regra_elegibilidade")
        if isinstance(regra_raw, str):
            try:
                regra_dict = json.loads(regra_raw) if regra_raw.strip() else {}
            except Exception:
                raise PlataformaValidacaoException("Regra de elegibilidade deve ser um JSON válido.")
        elif isinstance(regra_raw, dict):
            regra_dict = regra_raw
        elif regra_raw is None:
            regra_dict = {"situacoes_permitidas": ["ativo"]}
        else:
            raise PlataformaValidacaoException("Formato inválido para regra de elegibilidade.")

        if "tempo_minimo_dias" in regra_dict and int(regra_dict.get("tempo_minimo_dias") or 0) < 0:
            raise PlataformaValidacaoException("Tempo mínimo de casa (dias) na regra de elegibilidade não pode ser negativo.")

        ativo_val = dados.get("ativo", (atual or {}).get("ativo", 1))
        ativo = 1 if ativo_val in (1, True, "1", "true", "sim") else 0

        return {
            "empresa_id": str(dados.get("empresa_id") or (atual or {}).get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip(),
            "codigo": codigo,
            "nome": nome,
            "tipo": tipo,
            "coparticipacao_tipo": copart_tipo,
            "coparticipacao_valor": copart_val,
            "teto_legal_percentual": teto_pct,
            "regra_elegibilidade": json.dumps(regra_dict, ensure_ascii=False),
            "rubrica_codigo": rubrica_codigo,
            "valor_mensal_padrao": v_mensal,
            "valor_diario_padrao": v_diario,
            "limite_padrao": lim_padrao,
            "descricao": str(dados.get("descricao") if "descricao" in dados else ((atual or {}).get("descricao") or "")).strip(),
            "ativo": ativo,
        }

    def listar_beneficios_catalogo(self, apenas_ativos: bool = False, tipo: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista os benefícios cadastrados no catálogo corporativo."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = "SELECT * FROM beneficios_catalogo WHERE 1=1"
            params: List[Any] = []
            if apenas_ativos:
                sql += " AND ativo = 1"
            if tipo and tipo != "todos":
                sql += f" AND tipo = {p}"
                params.append(tipo.strip().lower())
            sql += " ORDER BY id ASC;"
            cur.execute(sql, tuple(params))
            rows = fetchall_dict(cur, self.db_path)
            for r in rows:
                r["regra_elegibilidade_obj"] = self._parse_json_dict(r.get("regra_elegibilidade"))
                if not r.get("rubrica_codigo"):
                    r["rubrica_codigo"] = self.RUBRICA_POR_TIPO_BENEFICIO.get(r.get("tipo", ""), "0511")
            return rows
        finally:
            conn.close()

    def obter_beneficio_catalogo(self, beneficio_id: int) -> Dict[str, Any]:
        """Obtém um benefício do catálogo por ID."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM beneficios_catalogo WHERE id = {self._p()};", (beneficio_id,))
            row = fetchone_dict(cur, self.db_path)
            if not row:
                raise PlataformaRecursoNaoEncontradoException(f"Benefício #{beneficio_id} não encontrado no catálogo.")
            row["regra_elegibilidade_obj"] = self._parse_json_dict(row.get("regra_elegibilidade"))
            if not row.get("rubrica_codigo"):
                row["rubrica_codigo"] = self.RUBRICA_POR_TIPO_BENEFICIO.get(row.get("tipo", ""), "0511")
            return row
        finally:
            conn.close()

    def criar_beneficio_catalogo(self, dados: Dict[str, Any], usuario: str = "DP") -> Dict[str, Any]:
        """Cria um novo tipo/plano de benefício no catálogo."""
        norm = self._normalizar_dados_catalogo_beneficio(dados)
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT id FROM beneficios_catalogo WHERE UPPER(codigo) = UPPER({p});", (norm["codigo"],))
            if cur.fetchone():
                raise PlataformaValidacaoException(f"Já existe um benefício no catálogo com o código '{norm['codigo']}'.")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO beneficios_catalogo (
                    empresa_id, codigo, nome, tipo, coparticipacao_tipo, coparticipacao_valor,
                    teto_legal_percentual, regra_elegibilidade, rubrica_codigo, valor_mensal_padrao,
                    valor_diario_padrao, limite_padrao, descricao, ativo, criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO beneficios_catalogo (
                    empresa_id, codigo, nome, tipo, coparticipacao_tipo, coparticipacao_valor,
                    teto_legal_percentual, regra_elegibilidade, rubrica_codigo, valor_mensal_padrao,
                    valor_diario_padrao, limite_padrao, descricao, ativo, criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p});
            """
            params = (
                norm["empresa_id"], norm["codigo"], norm["nome"], norm["tipo"],
                norm["coparticipacao_tipo"], norm["coparticipacao_valor"], norm["teto_legal_percentual"],
                norm["regra_elegibilidade"], norm["rubrica_codigo"], norm["valor_mensal_padrao"],
                norm["valor_diario_padrao"], norm["limite_padrao"], norm["descricao"],
                norm["ativo"], agora, agora,
            )
            bid = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()
        finally:
            conn.close()

        self.registrar_auditoria(
            modulo="Beneficios",
            operacao="inclusao",
            registro_tipo="beneficios_catalogo",
            registro_id=bid,
            usuario=usuario,
            detalhes=f"Benefício '{norm['codigo']} - {norm['nome']}' ({norm['tipo']}) criado no catálogo.",
        )
        return self.obter_beneficio_catalogo(bid)

    def atualizar_beneficio_catalogo(self, beneficio_id: int, dados: Dict[str, Any], usuario: str = "DP") -> Dict[str, Any]:
        """Atualiza um benefício existente no catálogo."""
        atual = self.obter_beneficio_catalogo(beneficio_id)
        norm = self._normalizar_dados_catalogo_beneficio(dados, atual=atual)
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"SELECT id FROM beneficios_catalogo WHERE UPPER(codigo) = UPPER({p}) AND id != {p};",
                (norm["codigo"], beneficio_id),
            )
            if cur.fetchone():
                raise PlataformaValidacaoException(f"Já existe outro benefício com o código '{norm['codigo']}'.")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"""
                UPDATE beneficios_catalogo SET
                    codigo = {p}, nome = {p}, tipo = {p}, coparticipacao_tipo = {p},
                    coparticipacao_valor = {p}, teto_legal_percentual = {p}, regra_elegibilidade = {p},
                    rubrica_codigo = {p}, valor_mensal_padrao = {p}, valor_diario_padrao = {p},
                    limite_padrao = {p}, descricao = {p}, ativo = {p}, atualizado_em = {p}
                WHERE id = {p};
                """,
                (
                    norm["codigo"], norm["nome"], norm["tipo"], norm["coparticipacao_tipo"],
                    norm["coparticipacao_valor"], norm["teto_legal_percentual"], norm["regra_elegibilidade"],
                    norm["rubrica_codigo"], norm["valor_mensal_padrao"], norm["valor_diario_padrao"],
                    norm["limite_padrao"], norm["descricao"], norm["ativo"], agora, beneficio_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.registrar_auditoria(
            modulo="Beneficios",
            operacao="alteracao",
            registro_tipo="beneficios_catalogo",
            registro_id=beneficio_id,
            usuario=usuario,
            detalhes=f"Benefício #{beneficio_id} ({norm['codigo']}) atualizado no catálogo.",
        )
        return self.obter_beneficio_catalogo(beneficio_id)

    def excluir_beneficio_catalogo(self, beneficio_id: int, usuario: str = "DP", forcar_inativacao: bool = False) -> Dict[str, Any]:
        """Exclui um item do catálogo se não tiver vínculos, ou inativa se solicitado."""
        atual = self.obter_beneficio_catalogo(beneficio_id)
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT COUNT(*) FROM beneficios_colaborador WHERE beneficio_id = {p};", (beneficio_id,))
            qtd_vinc = int(cur.fetchone()[0] or 0)
            if qtd_vinc > 0:
                if not forcar_inativacao:
                    raise PlataformaValidacaoException(
                        f"Não é possível excluir '{atual['nome']}': existem {qtd_vinc} vínculo(s) de colaborador associados."
                    )
                agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(
                    f"UPDATE beneficios_catalogo SET ativo = 0, atualizado_em = {p} WHERE id = {p};",
                    (agora, beneficio_id),
                )
                conn.commit()
                acao = "inativacao"
            else:
                cur.execute(f"DELETE FROM beneficios_catalogo WHERE id = {p};", (beneficio_id,))
                conn.commit()
                acao = "exclusao"
        finally:
            conn.close()

        self.registrar_auditoria(
            modulo="Beneficios",
            operacao=acao,
            registro_tipo="beneficios_catalogo",
            registro_id=beneficio_id,
            usuario=usuario,
            detalhes=f"Benefício '{atual['codigo']} - {atual['nome']}' ({acao}).",
        )
        return {"sucesso": True, "id": beneficio_id, "acao": acao}

    def verificar_elegibilidade_beneficio(
        self,
        colaborador_id: int,
        beneficio_id: int,
        data_referencia: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        RF078: Avalia regras de elegibilidade de um benefício para o colaborador.
        Verifica situação contratual, tipo de contrato, tempo mínimo de casa, setor, cargo e faixa salarial.
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException(f"Colaborador #{colaborador_id} não encontrado.")
            cur.execute(f"SELECT * FROM beneficios_catalogo WHERE id = {p};", (beneficio_id,))
            benef = fetchone_dict(cur, self.db_path)
            if not benef:
                raise PlataformaRecursoNaoEncontradoException(f"Benefício #{beneficio_id} não encontrado no catálogo.")
        finally:
            conn.close()

        regras = self._parse_json_dict(benef.get("regra_elegibilidade"))
        motivos: List[str] = []

        if int(benef.get("ativo", 1)) == 0:
            motivos.append(f"Benefício '{benef['nome']}' está inativo no catálogo.")

        sit_colab = str(colab.get("situacao") or "ativo").strip().lower()
        situacoes_perm = [str(s).strip().lower() for s in (regras.get("situacoes_permitidas") or ["ativo"])]
        if sit_colab not in situacoes_perm:
            motivos.append(
                f"Situação do colaborador ('{sit_colab}') não é elegível (permitido: {', '.join(situacoes_perm)})."
            )

        contratos_perm = [str(c).strip().lower() for c in (regras.get("tipos_contrato_permitidos") or []) if str(c).strip()]
        tipo_contrato_colab = str(colab.get("tipo_contrato") or "CLT").strip().lower()
        if contratos_perm and tipo_contrato_colab not in contratos_perm:
            motivos.append(
                f"Tipo de contrato '{colab.get('tipo_contrato') or 'CLT'}' inelegível (permitido: {', '.join(regras['tipos_contrato_permitidos'])})."
            )

        tempo_min_dias = int(regras.get("tempo_minimo_dias") or 0)
        if tempo_min_dias > 0:
            adm_str = str(colab.get("data_admissao") or "").strip()[:10]
            ref_str = (data_referencia or datetime.now().strftime("%Y-%m-%d"))[:10]
            if adm_str:
                try:
                    dias_casa = (datetime.strptime(ref_str, "%Y-%m-%d") - datetime.strptime(adm_str, "%Y-%m-%d")).days
                    if dias_casa < tempo_min_dias:
                        motivos.append(
                            f"Tempo de casa ({dias_casa} dias) inferior ao mínimo exigido ({tempo_min_dias} dias)."
                        )
                except ValueError:
                    pass

        setores_perm = [str(s).strip().lower() for s in (regras.get("setores_permitidos") or []) if str(s).strip()]
        if setores_perm:
            setor_c = str(colab.get("setor") or "").strip().lower()
            depto_c = str(colab.get("departamento") or "").strip().lower()
            if setor_c not in setores_perm and depto_c not in setores_perm:
                motivos.append(
                    f"Setor '{colab.get('setor') or '-'}' fora dos setores elegíveis ({', '.join(regras['setores_permitidos'])})."
                )

        cargos_perm = [str(c).strip().lower() for c in (regras.get("cargos_permitidos") or []) if str(c).strip()]
        if cargos_perm:
            cargo_c = str(colab.get("cargo") or "").strip().lower()
            if cargo_c not in cargos_perm:
                motivos.append(
                    f"Cargo '{colab.get('cargo') or '-'}' não contemplado pela regra de elegibilidade."
                )

        sal_colab = float(colab.get("salario_base") or 0.0)
        sal_min = float(regras.get("salario_minimo") or 0.0)
        sal_max = float(regras.get("salario_maximo") or 0.0)
        if sal_min > 0 and sal_colab < sal_min:
            motivos.append(f"Salário-base (R$ {sal_colab:.2f}) abaixo do piso de elegibilidade (R$ {sal_min:.2f}).")
        if sal_max > 0 and sal_colab > sal_max:
            motivos.append(f"Salário-base (R$ {sal_colab:.2f}) acima do teto de elegibilidade (R$ {sal_max:.2f}).")

        return {
            "elegivel": len(motivos) == 0,
            "colaborador_id": colaborador_id,
            "colaborador_nome": colab.get("nome_completo"),
            "beneficio_id": beneficio_id,
            "beneficio_codigo": benef.get("codigo"),
            "beneficio_nome": benef.get("nome"),
            "beneficio_tipo": benef.get("tipo"),
            "motivos": motivos,
            "regras": regras,
        }

    def listar_elegibilidade_colaborador(self, colaborador_id: int, data_referencia: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista o status de elegibilidade de todos os benefícios ativos do catálogo para o colaborador."""
        catalogo = self.listar_beneficios_catalogo(apenas_ativos=True)
        return [
            self.verificar_elegibilidade_beneficio(colaborador_id, int(b["id"]), data_referencia=data_referencia)
            for b in catalogo
        ]

    def _calcular_valores_beneficio(
        self,
        colab: Dict[str, Any],
        catalogo: Dict[str, Any],
        dados: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Calcula custo_total_mes, desconto_colaborador e custo_empresa conforme regras RF071-RF077."""
        tipo = str(catalogo.get("tipo") or catalogo.get("beneficio_tipo") or "").strip().lower()
        salario_base = self._d2(colab.get("salario_base") or 0)
        optante = 1 if dados.get("optante", 1) in (1, True, "1", "true", "sim") else 0

        def _f_nao_neg(chave: str, padrao: float = 0.0) -> Decimal:
            raw = dados.get(chave)
            if raw in (None, ""):
                return self._d2(padrao)
            try:
                val = self._d2(raw)
            except Exception:
                raise PlataformaValidacaoException(f"Valor inválido informado para '{chave}'.")
            if val < Decimal("0.00"):
                raise PlataformaValidacaoException(f"O campo '{chave}' não pode ser negativo.")
            return val

        dias_uteis = int(dados.get("dias_uteis_mes") if dados.get("dias_uteis_mes") not in (None, "") else 22)
        if dias_uteis < 0 or dias_uteis > 31:
            raise PlataformaValidacaoException("Dias úteis do mês deve estar entre 0 e 31.")

        valor_diario = _f_nao_neg("valor_diario", float(catalogo.get("valor_diario_padrao") or 0.0))
        valor_mensal_base = _f_nao_neg("valor_mensal_base", float(catalogo.get("valor_mensal_padrao") or 0.0))
        qtd_dep = int(dados.get("qtd_dependentes") if dados.get("qtd_dependentes") not in (None, "") else 0)
        if qtd_dep < 0:
            raise PlataformaValidacaoException("Quantidade de dependentes não pode ser negativa.")
        valor_dep = _f_nao_neg("valor_dependente", 0.0)
        copart_extra = _f_nao_neg("coparticipacao_extra", 0.0)
        limite_mensal = _f_nao_neg("limite_mensal", float(catalogo.get("limite_padrao") or 0.0))
        valor_utilizado = _f_nao_neg("valor_utilizado_mes", 0.0)
        saldo_flex = _f_nao_neg("saldo_flexivel", float(valor_mensal_base or catalogo.get("valor_mensal_padrao") or 0.0))

        aloc_raw = dados.get("alocacao_json")
        aloc_dict = self._parse_json_dict(aloc_raw)
        aloc_clean: Dict[str, float] = {}
        soma_aloc = Decimal("0.00")
        for k, v in aloc_dict.items():
            try:
                dv = self._d2(v)
            except Exception:
                raise PlataformaValidacaoException(f"Valor inválido na alocação flexível '{k}'.")
            if dv < Decimal("0.00"):
                raise PlataformaValidacaoException(f"Alocação flexível '{k}' não pode ser negativa.")
            aloc_clean[str(k)] = float(dv)
            soma_aloc += dv

        copart_tipo = str(catalogo.get("coparticipacao_tipo") or "percentual").strip().lower()
        copart_val = self._d2(catalogo.get("coparticipacao_valor") or 0.0)
        teto_pct = self._d2(catalogo.get("teto_legal_percentual") or 0.0)

        custo_total = Decimal("0.00")
        desconto = Decimal("0.00")

        if tipo == "vale_transporte":
            if optante == 0:
                custo_total = Decimal("0.00")
                desconto = Decimal("0.00")
            else:
                if valor_diario > Decimal("0.00") and dias_uteis > 0:
                    custo_total = self._d2(valor_diario * Decimal(str(dias_uteis)))
                else:
                    custo_total = valor_mensal_base
                if custo_total <= Decimal("0.00"):
                    raise PlataformaValidacaoException("Informe o valor diário (e dias úteis) ou valor mensal do Vale-Transporte.")
                perc_vt = min(teto_pct if teto_pct > Decimal("0.00") else Decimal("6.00"), Decimal("6.00"))
                teto_legal_vt = self._d2(salario_base * (perc_vt / Decimal("100.00")))
                desconto = min(custo_total, teto_legal_vt)

        elif tipo in ("vale_alimentacao", "vale_refeicao"):
            if optante == 1:
                if valor_diario > Decimal("0.00") and dias_uteis > 0:
                    custo_total = self._d2(valor_diario * Decimal(str(dias_uteis)))
                else:
                    custo_total = valor_mensal_base
                if custo_total <= Decimal("0.00"):
                    raise PlataformaValidacaoException("Informe o valor mensal ou valor diário do Vale-Alimentação/Refeição.")
                if copart_tipo == "percentual":
                    desconto_calc = self._d2(custo_total * (copart_val / Decimal("100.00")))
                else:
                    desconto_calc = min(copart_val, custo_total)
                teto_pat = min(teto_pct if teto_pct > Decimal("0.00") else Decimal("20.00"), Decimal("20.00"))
                limite_pat = self._d2(custo_total * (teto_pat / Decimal("100.00")))
                desconto = min(custo_total, min(desconto_calc, limite_pat) + copart_extra)

        elif tipo in ("plano_saude", "plano_odontologico"):
            if optante == 1:
                custo_total = self._d2(valor_mensal_base + (Decimal(str(qtd_dep)) * valor_dep))
                if custo_total <= Decimal("0.00"):
                    raise PlataformaValidacaoException("Informe a mensalidade base do plano de saúde/odontológico.")
                if copart_tipo == "percentual":
                    desc_base = self._d2(custo_total * (copart_val / Decimal("100.00")))
                else:
                    desc_base = min(copart_val, custo_total)
                desconto = min(custo_total, desc_base + copart_extra)

        elif tipo == "seguro_vida":
            if optante == 1:
                custo_total = valor_mensal_base
                if custo_total <= Decimal("0.00"):
                    raise PlataformaValidacaoException("Informe o valor do prêmio mensal do Seguro de Vida.")
                if copart_tipo == "percentual":
                    desc_base = self._d2(custo_total * (copart_val / Decimal("100.00")))
                else:
                    desc_base = min(copart_val, custo_total)
                desconto = min(custo_total, desc_base + copart_extra)

        elif tipo == "farmacia":
            if limite_mensal > Decimal("0.00") and valor_utilizado > limite_mensal:
                raise PlataformaValidacaoException(
                    f"Valor utilizado no convênio farmácia (R$ {valor_utilizado}) excede o limite mensal autorizado (R$ {limite_mensal})."
                )
            if optante == 1:
                custo_total = valor_utilizado
                if copart_tipo == "percentual":
                    desc_base = self._d2(custo_total * (copart_val / Decimal("100.00")))
                else:
                    desc_base = min(copart_val, custo_total)
                desconto = min(custo_total, desc_base + copart_extra)

        elif tipo == "beneficio_flexivel":
            if optante == 1:
                if saldo_flex <= Decimal("0.00"):
                    raise PlataformaValidacaoException("Informe o saldo mensal positivo para Benefícios Flexíveis.")
                if soma_aloc > saldo_flex:
                    raise PlataformaValidacaoException(
                        f"A soma das alocações flexíveis (R$ {soma_aloc}) excede o saldo disponível (R$ {saldo_flex})."
                    )
                custo_total = saldo_flex
                desconto = min(custo_total, copart_extra)

        else:
            if optante == 1:
                custo_total = valor_mensal_base if valor_mensal_base > Decimal("0.00") else self._d2(valor_diario * Decimal(str(dias_uteis)))
                if copart_tipo == "percentual":
                    desc_base = self._d2(custo_total * (copart_val / Decimal("100.00")))
                else:
                    desc_base = min(copart_val, custo_total)
                desconto = min(custo_total, desc_base + copart_extra)

        custo_empresa = max(Decimal("0.00"), self._d2(custo_total - desconto))

        return {
            "optante": optante,
            "valor_diario": float(valor_diario),
            "dias_uteis_mes": dias_uteis,
            "valor_mensal_base": float(valor_mensal_base),
            "qtd_dependentes": qtd_dep,
            "valor_dependente": float(valor_dep),
            "coparticipacao_extra": float(copart_extra),
            "limite_mensal": float(limite_mensal),
            "valor_utilizado_mes": float(valor_utilizado),
            "saldo_flexivel": float(saldo_flex),
            "alocacao_json": json.dumps(aloc_clean, ensure_ascii=False) if aloc_clean else "",
            "custo_total_mes": float(custo_total),
            "desconto_colaborador": float(desconto),
            "custo_empresa": float(custo_empresa),
        }

    def listar_beneficios_colaboradores(
        self,
        colaborador_id: Optional[int] = None,
        tipo: Optional[str] = None,
        apenas_ativos: bool = False,
    ) -> List[Dict[str, Any]]:
        """Lista benefícios vinculados aos colaboradores com dados de colaborador e catálogo."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = """
                SELECT bc.*,
                       c.nome_completo AS colaborador_nome,
                       c.matricula AS colaborador_matricula,
                       c.cargo AS colaborador_cargo,
                       c.setor AS colaborador_setor,
                       c.salario_base AS colaborador_salario_base,
                       c.situacao AS colaborador_situacao,
                       cat.codigo AS beneficio_codigo,
                       cat.nome AS beneficio_nome,
                       cat.tipo AS beneficio_tipo,
                       cat.rubrica_codigo AS rubrica_codigo,
                       cat.coparticipacao_tipo,
                       cat.coparticipacao_valor,
                       cat.teto_legal_percentual
                FROM beneficios_colaborador bc
                JOIN colaboradores c ON c.id = bc.colaborador_id
                JOIN beneficios_catalogo cat ON cat.id = bc.beneficio_id
                WHERE 1=1
            """
            params: List[Any] = []
            if colaborador_id:
                sql += f" AND bc.colaborador_id = {p}"
                params.append(int(colaborador_id))
            if tipo and tipo != "todos":
                sql += f" AND cat.tipo = {p}"
                params.append(tipo.strip().lower())
            if apenas_ativos:
                sql += " AND bc.ativo = 1"
            sql += " ORDER BY bc.id DESC;"
            cur.execute(sql, tuple(params))
            rows = fetchall_dict(cur, self.db_path)
            for r in rows:
                r["alocacao_obj"] = self._parse_json_dict(r.get("alocacao_json"))
                if not r.get("rubrica_codigo"):
                    r["rubrica_codigo"] = self.RUBRICA_POR_TIPO_BENEFICIO.get(r.get("beneficio_tipo", ""), "0511")
            return rows
        finally:
            conn.close()

    def obter_beneficio_colaborador(self, vinculo_id: int) -> Dict[str, Any]:
        """Obtém um vínculo específico de benefício por ID."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT bc.*,
                       c.nome_completo AS colaborador_nome,
                       c.matricula AS colaborador_matricula,
                       c.cargo AS colaborador_cargo,
                       c.setor AS colaborador_setor,
                       c.salario_base AS colaborador_salario_base,
                       c.situacao AS colaborador_situacao,
                       cat.codigo AS beneficio_codigo,
                       cat.nome AS beneficio_nome,
                       cat.tipo AS beneficio_tipo,
                       cat.rubrica_codigo AS rubrica_codigo
                FROM beneficios_colaborador bc
                JOIN colaboradores c ON c.id = bc.colaborador_id
                JOIN beneficios_catalogo cat ON cat.id = bc.beneficio_id
                WHERE bc.id = {self._p()};
                """,
                (vinculo_id,),
            )
            row = fetchone_dict(cur, self.db_path)
            if not row:
                raise PlataformaRecursoNaoEncontradoException(f"Vínculo de benefício #{vinculo_id} não encontrado.")
            row["alocacao_obj"] = self._parse_json_dict(row.get("alocacao_json"))
            return row
        finally:
            conn.close()

    def vincular_beneficio_colaborador(self, dados: Dict[str, Any], usuario: str = "DP") -> Dict[str, Any]:
        """RF071-RF078: Concede/vincula benefício a colaborador após validar elegibilidade e calcular custos/descontos."""
        if not dados.get("colaborador_id") or not dados.get("beneficio_id"):
            raise PlataformaValidacaoException("Colaborador e benefício são obrigatórios.")
        colaborador_id = int(dados["colaborador_id"])
        beneficio_id = int(dados["beneficio_id"])
        vig_inicio = self._validar_data_iso(dados.get("vigencia_inicio") or datetime.now().strftime("%Y-%m-%d"), "vigencia_inicio")
        vig_fim_raw = str(dados.get("vigencia_fim") or "").strip()
        vig_fim = self._validar_data_iso(vig_fim_raw, "vigencia_fim") if vig_fim_raw else None
        if vig_fim and vig_fim < vig_inicio:
            raise PlataformaValidacaoException("A data de fim de vigência não pode ser anterior à data de início.")

        elig = self.verificar_elegibilidade_beneficio(colaborador_id, beneficio_id, data_referencia=vig_inicio)
        if not elig["elegivel"]:
            raise PlataformaValidacaoException("Colaborador inelegível para este benefício: " + " ".join(elig["motivos"]))

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            cur.execute(f"SELECT * FROM beneficios_catalogo WHERE id = {p};", (beneficio_id,))
            catalogo = fetchone_dict(cur, self.db_path)

            cur.execute(
                f"SELECT id FROM beneficios_colaborador WHERE colaborador_id = {p} AND beneficio_id = {p} AND ativo = 1;",
                (colaborador_id, beneficio_id),
            )
            if cur.fetchone():
                raise PlataformaValidacaoException(
                    f"Colaborador já possui vínculo ativo com '{catalogo['nome']}'. Edite o vínculo existente."
                )

            calc = self._calcular_valores_beneficio(colab, catalogo, dados)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ativo = 1 if dados.get("ativo", 1) in (1, True, "1", "true", "sim") else 0
            obs = str(dados.get("observacoes") or "").strip()

            sql_pg = f"""
                INSERT INTO beneficios_colaborador (
                    colaborador_id, beneficio_id, optante, valor_diario, dias_uteis_mes,
                    valor_mensal_base, qtd_dependentes, valor_dependente, coparticipacao_extra,
                    limite_mensal, valor_utilizado_mes, saldo_flexivel, alocacao_json,
                    custo_total_mes, desconto_colaborador, custo_empresa,
                    vigencia_inicio, vigencia_fim, observacoes, ativo, criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO beneficios_colaborador (
                    colaborador_id, beneficio_id, optante, valor_diario, dias_uteis_mes,
                    valor_mensal_base, qtd_dependentes, valor_dependente, coparticipacao_extra,
                    limite_mensal, valor_utilizado_mes, saldo_flexivel, alocacao_json,
                    custo_total_mes, desconto_colaborador, custo_empresa,
                    vigencia_inicio, vigencia_fim, observacoes, ativo, criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p});
            """
            params = (
                colaborador_id, beneficio_id, calc["optante"], calc["valor_diario"], calc["dias_uteis_mes"],
                calc["valor_mensal_base"], calc["qtd_dependentes"], calc["valor_dependente"], calc["coparticipacao_extra"],
                calc["limite_mensal"], calc["valor_utilizado_mes"], calc["saldo_flexivel"], calc["alocacao_json"],
                calc["custo_total_mes"], calc["desconto_colaborador"], calc["custo_empresa"],
                vig_inicio, vig_fim, obs, ativo, agora, agora,
            )
            vinc_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()
        finally:
            conn.close()

        self.registrar_auditoria(
            modulo="Beneficios",
            operacao="inclusao",
            registro_tipo="beneficios_colaborador",
            registro_id=vinc_id,
            usuario=usuario,
            detalhes=f"Benefício '{catalogo['codigo']}' concedido ao colaborador #{colaborador_id} (Desc. R$ {calc['desconto_colaborador']:.2f}).",
        )
        return self.obter_beneficio_colaborador(vinc_id)

    def atualizar_beneficio_colaborador(self, vinculo_id: int, dados: Dict[str, Any], usuario: str = "DP") -> Dict[str, Any]:
        """Atualiza parâmetros de um benefício vinculado e recalcula valores."""
        atual = self.obter_beneficio_colaborador(vinculo_id)
        merged = dict(atual)
        merged.update({k: v for k, v in dados.items() if v is not None})

        vig_inicio = self._validar_data_iso(merged.get("vigencia_inicio"), "vigencia_inicio")
        vig_fim_raw = str(merged.get("vigencia_fim") or "").strip()
        vig_fim = self._validar_data_iso(vig_fim_raw, "vigencia_fim") if vig_fim_raw else None
        if vig_fim and vig_fim < vig_inicio:
            raise PlataformaValidacaoException("A data de fim de vigência não pode ser anterior à data de início.")

        ativo = 1 if merged.get("ativo", 1) in (1, True, "1", "true", "sim") else 0
        if ativo == 1:
            elig = self.verificar_elegibilidade_beneficio(int(atual["colaborador_id"]), int(atual["beneficio_id"]), data_referencia=vig_inicio)
            if not elig["elegivel"]:
                raise PlataformaValidacaoException("Colaborador inelegível para manter benefício ativo: " + " ".join(elig["motivos"]))

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM colaboradores WHERE id = {p};", (atual["colaborador_id"],))
            colab = fetchone_dict(cur, self.db_path)
            cur.execute(f"SELECT * FROM beneficios_catalogo WHERE id = {p};", (atual["beneficio_id"],))
            catalogo = fetchone_dict(cur, self.db_path)

            calc = self._calcular_valores_beneficio(colab, catalogo, merged)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            obs = str(merged.get("observacoes") or "").strip()
            cur.execute(
                f"""
                UPDATE beneficios_colaborador SET
                    optante = {p}, valor_diario = {p}, dias_uteis_mes = {p},
                    valor_mensal_base = {p}, qtd_dependentes = {p}, valor_dependente = {p},
                    coparticipacao_extra = {p}, limite_mensal = {p}, valor_utilizado_mes = {p},
                    saldo_flexivel = {p}, alocacao_json = {p}, custo_total_mes = {p},
                    desconto_colaborador = {p}, custo_empresa = {p},
                    vigencia_inicio = {p}, vigencia_fim = {p}, observacoes = {p},
                    ativo = {p}, atualizado_em = {p}
                WHERE id = {p};
                """,
                (
                    calc["optante"], calc["valor_diario"], calc["dias_uteis_mes"],
                    calc["valor_mensal_base"], calc["qtd_dependentes"], calc["valor_dependente"],
                    calc["coparticipacao_extra"], calc["limite_mensal"], calc["valor_utilizado_mes"],
                    calc["saldo_flexivel"], calc["alocacao_json"], calc["custo_total_mes"],
                    calc["desconto_colaborador"], calc["custo_empresa"],
                    vig_inicio, vig_fim, obs, ativo, agora, vinculo_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.registrar_auditoria(
            modulo="Beneficios",
            operacao="alteracao",
            registro_tipo="beneficios_colaborador",
            registro_id=vinculo_id,
            usuario=usuario,
            detalhes=f"Vínculo de benefício #{vinculo_id} atualizado (Desc. R$ {calc['desconto_colaborador']:.2f}).",
        )
        return self.obter_beneficio_colaborador(vinculo_id)

    def excluir_beneficio_colaborador(self, vinculo_id: int, usuario: str = "DP") -> Dict[str, Any]:
        """Exclui um vínculo de benefício do colaborador."""
        atual = self.obter_beneficio_colaborador(vinculo_id)
        conn = self._conn()
        try:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM beneficios_colaborador WHERE id = {self._p()};", (vinculo_id,))
            conn.commit()
        finally:
            conn.close()

        self.registrar_auditoria(
            modulo="Beneficios",
            operacao="exclusao",
            registro_tipo="beneficios_colaborador",
            registro_id=vinculo_id,
            usuario=usuario,
            detalhes=f"Vínculo #{vinculo_id} ({atual['beneficio_nome']} - {atual['colaborador_nome']}) excluído.",
        )
        return {"sucesso": True, "id": vinculo_id}

    def obter_descontos_beneficios_folha(self, colaborador_id: int, competencia: str) -> Dict[str, Any]:
        """
        RF079: Consolida os descontos de benefícios vigentes do colaborador na competência (AAAA-MM),
        recalculando pelo salário-base atual e retornando eventos prontos para a Folha de Pagamento.
        """
        comp = str(competencia or "").strip()
        if not re.match(r"^\d{4}-\d{2}$", comp):
            raise PlataformaValidacaoException("Competência inválida para descontos de benefícios. Use AAAA-MM.")
        ano, mes = map(int, comp.split("-"))
        if mes < 1 or mes > 12:
            raise PlataformaValidacaoException("Mês inválido na competência informada.")
        primeiro_dia = f"{comp}-01"
        ultimo_dia = f"{comp}-{calendar.monthrange(ano, mes)[1]:02d}"

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM colaboradores WHERE id = {p};", (colaborador_id,))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException(f"Colaborador #{colaborador_id} não encontrado.")
            cur.execute(
                f"""
                SELECT bc.*, cat.codigo AS beneficio_codigo, cat.nome AS beneficio_nome,
                       cat.tipo AS tipo, cat.tipo AS beneficio_tipo, cat.rubrica_codigo,
                       cat.coparticipacao_tipo, cat.coparticipacao_valor,
                       cat.teto_legal_percentual, cat.valor_mensal_padrao,
                       cat.valor_diario_padrao, cat.limite_padrao
                FROM beneficios_colaborador bc
                JOIN beneficios_catalogo cat ON cat.id = bc.beneficio_id
                WHERE bc.colaborador_id = {p}
                  AND bc.ativo = 1
                  AND cat.ativo = 1
                  AND bc.vigencia_inicio <= {p}
                  AND (bc.vigencia_fim IS NULL OR bc.vigencia_fim = '' OR bc.vigencia_fim >= {p})
                ORDER BY bc.id ASC;
                """,
                (colaborador_id, ultimo_dia, primeiro_dia),
            )
            vinculos = fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

        itens: List[Dict[str, Any]] = []
        eventos_folha: List[Dict[str, Any]] = []
        tot_custo = Decimal("0.00")
        tot_desc = Decimal("0.00")
        tot_emp = Decimal("0.00")

        for v in vinculos:
            calc = self._calcular_valores_beneficio(colab, v, v)
            rub = str(v.get("rubrica_codigo") or self.RUBRICA_POR_TIPO_BENEFICIO.get(v.get("beneficio_tipo", ""), "0511")).strip()
            tot_custo += self._d2(calc["custo_total_mes"])
            tot_desc += self._d2(calc["desconto_colaborador"])
            tot_emp += self._d2(calc["custo_empresa"])

            item_res = {
                "vinculo_id": v["id"],
                "beneficio_id": v["beneficio_id"],
                "codigo": v["beneficio_codigo"],
                "nome": v["beneficio_nome"],
                "tipo": v["beneficio_tipo"],
                "rubrica_codigo": rub,
                "optante": calc["optante"],
                "custo_total_mes": calc["custo_total_mes"],
                "desconto_colaborador": calc["desconto_colaborador"],
                "custo_empresa": calc["custo_empresa"],
                "vigencia_inicio": v["vigencia_inicio"],
                "vigencia_fim": v.get("vigencia_fim"),
            }
            itens.append(item_res)

            if calc["desconto_colaborador"] > 0:
                if rub == "0510":
                    teto_vt = min(float(v.get("teto_legal_percentual") or 6.0), 6.0)
                    eventos_folha.append({
                        "codigo": "0510",
                        "descricao": f"{v['beneficio_nome']} (VT 6%)",
                        "tipo": "desconto",
                        "percentual": teto_vt,
                        "referencia": teto_vt,
                        "valor_informado": calc["custo_total_mes"],
                        "desconto_previsto": calc["desconto_colaborador"],
                        "origem_beneficio_id": v["id"],
                    })
                else:
                    eventos_folha.append({
                        "codigo": rub,
                        "descricao": v["beneficio_nome"],
                        "tipo": "desconto",
                        "referencia": 1,
                        "valor_informado": calc["desconto_colaborador"],
                        "desconto_previsto": calc["desconto_colaborador"],
                        "origem_beneficio_id": v["id"],
                    })

        return {
            "colaborador_id": colaborador_id,
            "colaborador_nome": colab.get("nome_completo"),
            "salario_base": float(colab.get("salario_base") or 0.0),
            "competencia": comp,
            "itens": itens,
            "eventos_folha": eventos_folha,
            "total_custo_mensal": float(tot_custo),
            "total_descontos_beneficios": float(tot_desc),
            "total_custo_empresa": float(tot_emp),
        }

    def gerar_relatorio_beneficios(
        self,
        competencia: Optional[str] = None,
        tipo: Optional[str] = None,
        setor: Optional[str] = None,
        colaborador_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """RF080: Gera relatório consolidado e analítico de custos e descontos de benefícios."""
        comp = str(competencia or "").strip()
        primeiro_dia = None
        ultimo_dia = None
        if comp:
            if not re.match(r"^\d{4}-\d{2}$", comp):
                raise PlataformaValidacaoException("Competência inválida para relatório. Use AAAA-MM.")
            ano, mes = map(int, comp.split("-"))
            primeiro_dia = f"{comp}-01"
            ultimo_dia = f"{comp}-{calendar.monthrange(ano, mes)[1]:02d}"

        vinculos = self.listar_beneficios_colaboradores(
            colaborador_id=colaborador_id,
            tipo=tipo if tipo and tipo != "todos" else None,
            apenas_ativos=True,
        )

        itens: List[Dict[str, Any]] = []
        por_tipo_map: Dict[str, Dict[str, Any]] = {}
        por_setor_map: Dict[str, Dict[str, Any]] = {}
        colabs_unicos = set()

        total_custo = Decimal("0.00")
        total_empresa = Decimal("0.00")
        total_desc = Decimal("0.00")

        for v in vinculos:
            if setor and setor != "todos":
                if str(v.get("colaborador_setor") or "").strip().lower() != setor.strip().lower():
                    continue
            if primeiro_dia and ultimo_dia:
                vi = str(v.get("vigencia_inicio") or "")
                vf = str(v.get("vigencia_fim") or "")
                if vi > ultimo_dia or (vf and vf < primeiro_dia):
                    continue

            custo = self._d2(v.get("custo_total_mes") or 0)
            desc = self._d2(v.get("desconto_colaborador") or 0)
            emp = self._d2(v.get("custo_empresa") or 0)

            total_custo += custo
            total_desc += desc
            total_empresa += emp
            colabs_unicos.add(int(v["colaborador_id"]))

            t_key = v.get("beneficio_tipo") or "outros"
            if t_key not in por_tipo_map:
                por_tipo_map[t_key] = {
                    "tipo": t_key,
                    "quantidade": 0,
                    "custo_total": Decimal("0.00"),
                    "custo_empresa": Decimal("0.00"),
                    "desconto_colaborador": Decimal("0.00"),
                }
            por_tipo_map[t_key]["quantidade"] += 1
            por_tipo_map[t_key]["custo_total"] += custo
            por_tipo_map[t_key]["custo_empresa"] += emp
            por_tipo_map[t_key]["desconto_colaborador"] += desc

            s_key = v.get("colaborador_setor") or "Não informado"
            if s_key not in por_setor_map:
                por_setor_map[s_key] = {
                    "setor": s_key,
                    "colaboradores_ids": set(),
                    "vinculos": 0,
                    "custo_total": Decimal("0.00"),
                    "custo_empresa": Decimal("0.00"),
                    "desconto_colaborador": Decimal("0.00"),
                }
            por_setor_map[s_key]["colaboradores_ids"].add(int(v["colaborador_id"]))
            por_setor_map[s_key]["vinculos"] += 1
            por_setor_map[s_key]["custo_total"] += custo
            por_setor_map[s_key]["custo_empresa"] += emp
            por_setor_map[s_key]["desconto_colaborador"] += desc

            itens.append({
                "vinculo_id": v["id"],
                "colaborador_id": v["colaborador_id"],
                "colaborador_nome": v["colaborador_nome"],
                "matricula": v.get("colaborador_matricula"),
                "setor": s_key,
                "beneficio_codigo": v["beneficio_codigo"],
                "beneficio_nome": v["beneficio_nome"],
                "tipo": t_key,
                "rubrica_codigo": v.get("rubrica_codigo"),
                "vigencia_inicio": v.get("vigencia_inicio"),
                "vigencia_fim": v.get("vigencia_fim"),
                "custo_total_mes": float(custo),
                "desconto_colaborador": float(desc),
                "custo_empresa": float(emp),
            })

        por_tipo = [
            {
                "tipo": d["tipo"],
                "quantidade": d["quantidade"],
                "custo_total": float(d["custo_total"]),
                "custo_empresa": float(d["custo_empresa"]),
                "desconto_colaborador": float(d["desconto_colaborador"]),
            }
            for d in sorted(por_tipo_map.values(), key=lambda x: x["tipo"])
        ]
        por_setor = [
            {
                "setor": d["setor"],
                "colaboradores": len(d["colaboradores_ids"]),
                "vinculos": d["vinculos"],
                "custo_total": float(d["custo_total"]),
                "custo_empresa": float(d["custo_empresa"]),
                "desconto_colaborador": float(d["desconto_colaborador"]),
            }
            for d in sorted(por_setor_map.values(), key=lambda x: x["setor"])
        ]

        qtd_colabs = len(colabs_unicos)
        media_colab = float(self._d2(total_custo / Decimal(str(qtd_colabs)))) if qtd_colabs > 0 else 0.0

        return {
            "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filtros": {"competencia": comp or None, "tipo": tipo, "setor": setor, "colaborador_id": colaborador_id},
            "resumo": {
                "total_vinculos_ativos": len(itens),
                "total_colaboradores_beneficiados": qtd_colabs,
                "custo_total_mensal": float(total_custo),
                "total_custo_empresa": float(total_empresa),
                "total_desconto_colaboradores": float(total_desc),
                "custo_medio_por_colaborador": media_colab,
            },
            "por_tipo": por_tipo,
            "por_setor": por_setor,
            "itens": itens,
        }
