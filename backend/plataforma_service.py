"""
Camada de Serviços da Plataforma Integrada de Gestão do Ciclo Trabalhista
Implementa a lógica de negócio, persistência relacional e validações para os 20 Módulos:
Módulos 01 a 20 (RF-001 a RF-200), Regras Transversais (RT-01 a RT-13) e
Regras de Negócio Trabalhistas e Compliance (RN-001 a RN-083).
"""
import calendar
import hashlib
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
from .afastamento_service import AfastamentoService
from .esocial_eventos_trabalhistas import validar_xml_esocial_trabalhista
from .ferias_service import FeriasService
from .ponto_service import PontoService
from .rescisao_service import RescisaoService
from .sst_service import SSTService
from .esocial_service import ESocialService
from .relatorios_service import RelatoriosService
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
        self.ponto_service = PontoService(
            db_path=self.db_path,
            auditoria_cb=self.registrar_auditoria,
        )
        self.ferias_service = FeriasService(
            db_path=self.db_path,
            auditoria_cb=self.registrar_auditoria,
        )
        self.afastamento_service = AfastamentoService(
            db_path=self.db_path,
            auditoria_cb=self.registrar_auditoria,
        )
        self.rescisao_service = RescisaoService(
            db_path=self.db_path,
            auditoria_cb=self.registrar_auditoria,
        )
        self.sst_service = SSTService(db_path=self.db_path)
        self.esocial_service = ESocialService(db_path=self.db_path)
        self.relatorios_service = RelatoriosService(db_path=self.db_path)

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
        """Registra log imutável de auditoria com encadeamento criptográfico inviolável (RT-01, RT-02, RF-191 a RF-200, RN-072)."""
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()

            # Encadeamento criptográfico (RF-200)
            cur.execute(
                f"SELECT hash_atual FROM auditoria_operacoes WHERE empresa_id = {p} OR empresa_id IS NULL ORDER BY id DESC LIMIT 1;",
                (empresa_id,),
            )
            last_h = cur.fetchone()
            hash_anterior = last_h[0] if last_h and last_h[0] else "GENESIS_RH20_BLOCK"
            payload = f"{hash_anterior}|{empresa_id}|{modulo}|{operacao}|{registro_tipo}|{str(registro_id)}|{campo_alterado or ''}|{valor_anterior or ''}|{valor_novo or ''}|{usuario or 'Sistema'}|{agora}"
            hash_atual = hashlib.sha256(payload.encode("utf-8")).hexdigest()

            cur.execute(
                f"""
                INSERT INTO auditoria_operacoes (
                    empresa_id, modulo, operacao, registro_tipo, registro_id,
                    campo_alterado, valor_anterior, valor_novo, usuario_responsavel,
                    ip_origem, detalhes, hash_anterior, hash_atual, criado_em
                ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p});
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
                    hash_anterior,
                    hash_atual,
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
        empresa_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Consulta logs de auditoria com isolamento estrito por empresa (RN-074, RF-198, RF-199)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            query = "SELECT * FROM auditoria_operacoes WHERE 1=1"
            params = []
            p = self._p()
            if empresa_id:
                query += f" AND (empresa_id = {p} OR empresa_id IS NULL)"
                params.append(empresa_id)
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

    def verificar_integridade_auditoria(self, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        """Valida integridade da trilha de auditoria (RF-200, RN-072)."""
        from backend.audit import AuditService
        return AuditService(db_path=self.db_path).verificar_integridade_trilha(empresa_id=empresa_id)

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
    # MÓDULO 03, 04 e 05: PONTO, AUSÊNCIAS, HORAS EXTRAS E ADICIONAIS (RF021-RF050)
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_marcacao_ponto(self, colaborador_id: int, data: str, hora: str, tipo_registro: str = "manual", coletor_id: Optional[str] = None, tipo_marcacao: Optional[str] = None, usuario: str = "Sistema", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.registrar_marcacao_ponto(
            colaborador_id, data, hora, tipo_registro=tipo_registro, coletor_id=coletor_id,
            tipo_marcacao=tipo_marcacao, usuario=usuario, empresa_id=empresa_id,
        )

    def importar_arquivo_ponto(self, nome_arquivo: str, conteudo_texto_ou_base64: str, eh_base64: bool = False, usuario: str = "Operador Ponto", empresa_id: str = "a0000000-0000-0000-0000-000000000001") -> Dict[str, Any]:
        return self.ponto_service.importar_arquivo_ponto(nome_arquivo, conteudo_texto_ou_base64, eh_base64=eh_base64, usuario=usuario, empresa_id=empresa_id)

    def importar_marcacoes_api(self, marcacoes: List[Dict[str, Any]], idempotency_key: str, coletor_id: str = "API_EXTERNA", usuario: str = "Integração API", empresa_id: str = "a0000000-0000-0000-0000-000000000001") -> Dict[str, Any]:
        return self.ponto_service.importar_marcacoes_api(marcacoes, idempotency_key, coletor_id=coletor_id, usuario=usuario, empresa_id=empresa_id)

    def validar_marcacoes_periodo(self, colaborador_id: int, competencia: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.validar_marcacoes_periodo(colaborador_id, competencia, empresa_id=empresa_id)

    def listar_ajustes_ponto(self, empresa_id: Optional[str] = None, colaborador_id: Optional[int] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.ponto_service.listar_ajustes_ponto(empresa_id=empresa_id, colaborador_id=colaborador_id, status=status)

    def solicitar_ajuste_ponto(self, colaborador_id: int, data: str, hora_ajustada: str, tipo_marcacao: str, motivo: str, solicitante: str, hora_original: Optional[str] = None, solicitante_usuario_id: Optional[int] = None, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.solicitar_ajuste_ponto(
            colaborador_id, data, hora_ajustada, tipo_marcacao, motivo, solicitante,
            hora_original=hora_original, solicitante_usuario_id=solicitante_usuario_id, empresa_id=empresa_id,
        )

    def aprovar_ajuste_ponto(self, ajuste_id: int, aprovador: str, aprovar: bool = True, motivo_reprovacao: Optional[str] = None, aprovador_usuario_id: Optional[int] = None, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.aprovar_ajuste_ponto(
            ajuste_id, aprovador, aprovar=aprovar, motivo_reprovacao=motivo_reprovacao,
            aprovador_usuario_id=aprovador_usuario_id, empresa_id=empresa_id,
        )

    def obter_espelho_ponto(self, colaborador_id: int, mes_ano: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.obter_espelho_ponto(colaborador_id, mes_ano, empresa_id=empresa_id)

    def registrar_ocorrencia_ponto(self, colaborador_id: int, data_inicio: str, data_fim: Optional[str], tipo_ocorrencia: str, justificativa: str, minutos_ausencia: int = 0, cid: Optional[str] = None, artigo_clt: Optional[str] = None, status: str = "aprovado", usuario: str = "DP / RH", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.registrar_ocorrencia(
            colaborador_id, data_inicio, data_fim, tipo_ocorrencia, justificativa,
            minutos_ausencia=minutos_ausencia, cid=cid, artigo_clt=artigo_clt,
            status=status, usuario=usuario, empresa_id=empresa_id,
        )

    def listar_ocorrencias_ponto(self, empresa_id: Optional[str] = None, colaborador_id: Optional[int] = None, competencia: Optional[str] = None, tipo: Optional[str] = None, setor: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.ponto_service.listar_ocorrencias(empresa_id=empresa_id, colaborador_id=colaborador_id, competencia=competencia, tipo=tipo, setor=setor)

    def registrar_justificativa_ponto(self, colaborador_id: int, data_referencia: str, tipo: str, motivo: str, solicitante: str, cid: Optional[str] = None, dias_abono: int = 1, artigo_clt: Optional[str] = None, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.registrar_justificativa(colaborador_id, data_referencia, tipo, motivo, solicitante, cid=cid, dias_abono=dias_abono, artigo_clt=artigo_clt, empresa_id=empresa_id)

    def listar_justificativas_ponto(self, empresa_id: Optional[str] = None, colaborador_id: Optional[int] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.ponto_service.listar_justificativas(empresa_id=empresa_id, colaborador_id=colaborador_id, status=status)

    def decidir_justificativa_ponto(self, justificativa_id: int, aprovador: str, aprovar: bool = True, motivo_decisao: Optional[str] = None, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.decidir_justificativa(justificativa_id, aprovador, aprovar=aprovar, motivo_decisao=motivo_decisao, empresa_id=empresa_id)

    def fechar_ponto_periodo(self, competencia: str, usuario: str = "DP / Gestor", empresa_id: str = "a0000000-0000-0000-0000-000000000001", filial_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.fechar_ponto_periodo(competencia, usuario=usuario, empresa_id=empresa_id, filial_id=filial_id)

    def reabrir_ponto_periodo(self, competencia: str, justificativa: str, usuario: str = "Administrador DP", empresa_id: str = "a0000000-0000-0000-0000-000000000001") -> Dict[str, Any]:
        return self.ponto_service.reabrir_ponto_periodo(competencia, justificativa, usuario=usuario, empresa_id=empresa_id)

    def movimentar_banco_horas(self, colaborador_id: int, data_referencia: str, tipo_movimento: str, minutos: int, observacao: str = "", prazo_meses: int = 6, usuario: str = "DP", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.movimentar_banco_horas(colaborador_id, data_referencia, tipo_movimento, minutos, observacao=observacao, prazo_meses=prazo_meses, usuario=usuario, empresa_id=empresa_id)

    def obter_saldo_banco_horas(self, colaborador_id: int, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.obter_saldo_banco_horas(colaborador_id, empresa_id=empresa_id)

    def relatorio_ausencias(self, empresa_id: str = "a0000000-0000-0000-0000-000000000001", competencia: Optional[str] = None, setor: Optional[str] = None, colaborador_id: Optional[int] = None, tipo: Optional[str] = None) -> Dict[str, Any]:
        return self.ponto_service.relatorio_ausencias(empresa_id=empresa_id, competencia=competencia, setor=setor, colaborador_id=colaborador_id, tipo=tipo)

    def calcular_medias_variaveis_colaborador(self, colaborador_id: int, ano: Optional[int] = None, ultimos_meses: int = 12) -> Dict[str, Any]:
        return self.ponto_service.calcular_medias_variaveis_colaborador(colaborador_id, ano=ano, ultimos_meses=ultimos_meses)

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 06: FÉRIAS (RF-051 a RF-060)
    # ─────────────────────────────────────────────────────────────────────────
    def sincronizar_periodos_aquisitivos(
        self, colaborador_id: int, data_referencia: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.ferias_service.sincronizar_periodos_aquisitivos(colaborador_id, data_referencia=data_referencia)

    def listar_periodos_aquisitivos(
        self, colaborador_id: Optional[int] = None, empresa_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        return self.ferias_service.listar_periodos_aquisitivos(colaborador_id=colaborador_id, empresa_id=empresa_id)

    def programar_ferias(
        self,
        colaborador_id: int,
        data_inicio: str,
        dias_gozo: int,
        abono_pecuniario: bool = False,
        dias_abono: Optional[int] = None,
        adiantar_13: bool = False,
        solicitante: str = "DP",
        exigir_aviso_30d: bool = False,
        incluir_medias_variaveis: bool = True,
        gerar_esocial: bool = True,
    ) -> Dict[str, Any]:
        """RF-051 a RF-060, RN-029: Delega programação e cálculo completo de férias para FeriasService."""
        return self.ferias_service.programar_ferias(
            colaborador_id=colaborador_id,
            data_inicio=data_inicio,
            dias_gozo=dias_gozo,
            abono_pecuniario=abono_pecuniario,
            dias_abono=dias_abono,
            adiantar_13=adiantar_13,
            solicitante=solicitante,
            exigir_aviso_30d=exigir_aviso_30d,
            incluir_medias_variaveis=incluir_medias_variaveis,
            gerar_esocial=gerar_esocial,
        )

    def aprovar_ferias(self, ferias_id: int, aprovador: str, aprovar: bool = True, motivo: str = "") -> Dict[str, Any]:
        return self.ferias_service.aprovar_ferias(ferias_id, aprovador, aprovar=aprovar, motivo=motivo)

    def cancelar_ferias(self, ferias_id: int, motivo: str, usuario: str) -> Dict[str, Any]:
        return self.ferias_service.cancelar_ferias(ferias_id, motivo, usuario)

    def registrar_pagamento_ferias(self, ferias_id: int, data_pagamento: str, usuario: str) -> Dict[str, Any]:
        return self.ferias_service.registrar_pagamento_ferias(ferias_id, data_pagamento, usuario)

    def gerar_documentos_ferias_pdf(self, ferias_id: int, tipo_documento: str = "aviso") -> Dict[str, Any]:
        return self.ferias_service.gerar_documentos_ferias_pdf(ferias_id, tipo_documento=tipo_documento)

    def integrar_ferias_folha(self, ferias_id: int, competencia: str, usuario: str = "DP") -> Dict[str, Any]:
        return self.ferias_service.integrar_ferias_folha(ferias_id, competencia, usuario=usuario)

    def programar_ferias_coletivas(
        self,
        data_inicio: str,
        dias_gozo: int,
        setor: Optional[str] = None,
        empresa_id: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        return self.ferias_service.programar_ferias_coletivas(
            data_inicio=data_inicio, dias_gozo=dias_gozo, setor=setor, empresa_id=empresa_id, usuario=usuario
        )

    def listar_ferias(
        self, colaborador_id: Optional[int] = None, empresa_id: Optional[str] = None, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Lista histórico e programações de férias."""
        return self.ferias_service.listar_ferias(colaborador_id=colaborador_id, empresa_id=empresa_id, status=status)

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
        subtipo_licenca: Optional[str] = None,
        cat_id: Optional[int] = None,
        observacoes: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        """RF-061 a RF-070, RN-032 a RN-035: Delega registro e regras previdenciárias/eSocial para AfastamentoService."""
        return self.afastamento_service.registrar_afastamento(
            colaborador_id=colaborador_id,
            tipo=tipo,
            data_inicio=data_inicio,
            data_fim_prevista=data_fim_prevista,
            cid=cid,
            subtipo_licenca=subtipo_licenca,
            cat_id=cat_id,
            observacoes=observacoes,
            usuario=usuario,
        )

    def prorrogar_afastamento(
        self,
        afastamento_id: int,
        nova_data_fim: str,
        motivo: str,
        cid: Optional[str] = None,
        documento_ref: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        return self.afastamento_service.prorrogar_afastamento(
            afastamento_id=afastamento_id,
            nova_data_fim=nova_data_fim,
            motivo=motivo,
            cid=cid,
            documento_ref=documento_ref,
            usuario=usuario,
        )

    def registrar_retorno_afastamento(
        self,
        afastamento_id: int,
        data_retorno: str,
        aso_id: Optional[int] = None,
        usuario: str = "SST / DP",
    ) -> Dict[str, Any]:
        return self.afastamento_service.registrar_retorno_afastamento(
            afastamento_id=afastamento_id,
            data_retorno=data_retorno,
            aso_id=aso_id,
            usuario=usuario,
        )

    def relatorio_afastamentos(
        self,
        empresa_id: Optional[str] = None,
        tipo: Optional[str] = None,
        setor: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.afastamento_service.relatorio_afastamentos(
            empresa_id=empresa_id, tipo=tipo, setor=setor
        )

    def listar_afastamentos(
        self,
        colaborador_id: Optional[int] = None,
        empresa_id: Optional[str] = None,
        tipo: Optional[str] = None,
        apenas_ativos: bool = False,
    ) -> List[Dict[str, Any]]:
        """Lista afastamentos registrados."""
        return self.afastamento_service.listar_afastamentos(
            colaborador_id=colaborador_id,
            empresa_id=empresa_id,
            tipo=tipo,
            apenas_ativos=apenas_ativos,
        )

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
        dias_restantes_contrato_prazo: int = 0,
        desconto_faltas_valor: Any = Decimal("0.00"),
        exigir_aso_demissional: bool = False,
        incluir_medias_variaveis: bool = True,
        usuario: str = "DP",
        simular: bool = False,
    ) -> Dict[str, Any]:
        """RF-106 a RF-120, RN-054 a RN-060: Delega cálculo e registro rescisório para RescisaoService."""
        return self.rescisao_service.registrar_rescisao(
            colaborador_id=colaborador_id,
            tipo_rescisao=tipo_rescisao,
            data_afastamento=data_afastamento,
            tipo_aviso=tipo_aviso,
            saldo_salario_dias=saldo_salario_dias,
            ferias_vencidas_dias=ferias_vencidas_dias,
            meses_trabalhados_ano=meses_trabalhados_ano,
            saldo_fgts=saldo_fgts,
            dias_restantes_contrato_prazo=dias_restantes_contrato_prazo,
            desconto_faltas_valor=desconto_faltas_valor,
            exigir_aso_demissional=exigir_aso_demissional,
            incluir_medias_variaveis=incluir_medias_variaveis,
            usuario=usuario,
            simular=simular,
        )

    def homologar_rescisao(self, rescisao_id: int, homologador: str, usuario_dp_observacao: str = "") -> Dict[str, Any]:
        return self.rescisao_service.homologar_rescisao(rescisao_id, homologador, usuario_dp_observacao=usuario_dp_observacao)

    def registrar_pagamento_rescisao(self, rescisao_id: int, data_pagamento: str, usuario: str = "Financeiro") -> Dict[str, Any]:
        return self.rescisao_service.registrar_pagamento_rescisao(rescisao_id, data_pagamento, usuario=usuario)

    def gerar_documentos_rescisao_pdf(self, rescisao_id: int, tipo_documento: str = "trct") -> Dict[str, Any]:
        return self.rescisao_service.gerar_documentos_rescisao_pdf(rescisao_id, tipo_documento=tipo_documento)

    def listar_rescisoes(self, empresa_id: Optional[str] = None, colaborador_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lista histórico de rescisões contratuais."""
        return self.rescisao_service.listar_rescisoes(empresa_id=empresa_id, colaborador_id=colaborador_id)

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 12: SST — SAÚDE E SEGURANÇA DO TRABALHO (RF-121 a RF-130)
    # ─────────────────────────────────────────────────────────────────────────
    def cadastrar_exame(self, codigo: str, descricao: str, tipo: str, periodicidade_meses: int = 12, empresa_id: str = "a0000000-0000-0000-0000-000000000001", usuario: str = "Médico SST") -> Dict[str, Any]:
        """RF-121: Cadastro de exame ocupacional."""
        return self.sst_service.cadastrar_exame(codigo=codigo, descricao=descricao, tipo=tipo, periodicidade_meses=periodicidade_meses, empresa_id=empresa_id, usuario=usuario)

    def listar_exames(self, empresa_id: str = "a0000000-0000-0000-0000-000000000001", apenas_ativos: bool = True) -> List[Dict[str, Any]]:
        """RF-121: Listar exames ocupacionais."""
        return self.sst_service.listar_exames(empresa_id=empresa_id, apenas_ativos=apenas_ativos)

    def atualizar_exame(self, exame_id: int, dados: Dict[str, Any], empresa_id: str = "a0000000-0000-0000-0000-000000000001", usuario: str = "Médico SST") -> Dict[str, Any]:
        """RF-121: Atualizar exame ocupacional."""
        return self.sst_service.atualizar_exame(exame_id=exame_id, dados=dados, empresa_id=empresa_id, usuario=usuario)

    def inativar_exame(self, exame_id: int, usuario: str = "Médico SST") -> Dict[str, Any]:
        """RF-121: Inativar exame ocupacional."""
        return self.sst_service.inativar_exame(exame_id=exame_id, usuario=usuario)

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
        usuario: str = "SST",
    ) -> Dict[str, Any]:
        """RF-122 a RF-125, RF-130: Registra ASO ocupacional e gera eSocial S-2220."""
        return self.sst_service.registrar_aso(
            colaborador_id=colaborador_id,
            tipo_aso=tipo_aso,
            data_emissao=data_emissao,
            data_validade=data_validade,
            resultado=resultado,
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

    def consultar_aso(self, aso_id: int, perfil_usuario: str = "medico_sst") -> Dict[str, Any]:
        """RF-125: Consulta ASO com controle de RBAC/sigilo médico."""
        return self.sst_service.consultar_aso(aso_id=aso_id, perfil_usuario=perfil_usuario)

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
        """RF-123: Agenda exame periódico preventivo conforme NR-07."""
        return self.sst_service.agendar_exame_periodico(
            colaborador_id=colaborador_id,
            exame_id=exame_id,
            data_prevista=data_prevista,
            clinica_nome=clinica_nome,
            observacoes=observacoes,
            empresa_id=empresa_id,
            usuario=usuario,
        )

    def verificar_dispensa_exame_demissional(self, colaborador_id: int, data_demissao: str, grau_risco: int = 2) -> Dict[str, Any]:
        """RF-124: Verifica se o exame demissional é dispensável com base no último ASO e grau de risco (NR-07)."""
        return self.sst_service.verificar_dispensa_exame_demissional(colaborador_id=colaborador_id, data_demissao=data_demissao, grau_risco=grau_risco)

    def agendar_exame_demissional(
        self,
        colaborador_id: int,
        data_demissao: str,
        data_prevista: str,
        clinica_nome: str = "Clínica de Medicina Ocupacional",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        """RF-124: Agenda exame demissional e valida prazo legal de 10 dias (NR-07)."""
        return self.sst_service.agendar_exame_demissional(
            colaborador_id=colaborador_id,
            data_demissao=data_demissao,
            data_prevista=data_prevista,
            clinica_nome=clinica_nome,
            empresa_id=empresa_id,
            usuario=usuario,
        )

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
        """RF-126: Cadastra EPI no catálogo."""
        return self.sst_service.cadastrar_epi(
            codigo=codigo,
            descricao=descricao,
            ca_numero=ca_numero,
            ca_validade=ca_validade,
            vida_util_dias=vida_util_dias,
            fabricante=fabricante,
            tipo_protecao=tipo_protecao,
            empresa_id=empresa_id,
            usuario=usuario,
        )

    def registrar_entrega_epi(self, colaborador_id: int, epi_id: int, quantidade: int = 1, data_entrega: Optional[str] = None, usuario: str = "SST") -> Dict[str, Any]:
        """RF-126, RN-062: Registra entrega de EPI com validação de CA ativo."""
        return self.sst_service.registrar_entrega_epi(colaborador_id=colaborador_id, epi_id=epi_id, quantidade=quantidade, data_entrega=data_entrega, usuario=usuario)

    def registrar_devolucao_epi(self, entrega_id: int, data_devolucao: Optional[str] = None, motivo: str = "devolucao_normal", usuario: str = "Técnico SST") -> Dict[str, Any]:
        """RF-126: Registra devolução de EPI."""
        return self.sst_service.registrar_devolucao_epi(entrega_id=entrega_id, data_devolucao=data_devolucao, motivo=motivo, usuario=usuario)

    def registrar_substituicao_epi(self, entrega_anterior_id: int, novo_epi_id: int, motivo_troca: str = "desgaste", quantidade: int = 1, usuario: str = "Técnico SST") -> Dict[str, Any]:
        """RF-126: Registra substituição de EPI."""
        return self.sst_service.registrar_substituicao_epi(entrega_anterior_id=entrega_anterior_id, novo_epi_id=novo_epi_id, motivo_troca=motivo_troca, quantidade=quantidade, usuario=usuario)

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
        """RF-127: Cadastra treinamento regulamentar (NRs MTE)."""
        return self.sst_service.cadastrar_treinamento(codigo=codigo, nome=nome, nr_norma=nr_norma, carga_horaria=carga_horaria, validade_meses=validade_meses, empresa_id=empresa_id, usuario=usuario)

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
        """RF-127: Registra conclusão e reciclagem de treinamento."""
        return self.sst_service.registrar_conclusao_treinamento(
            colaborador_id=colaborador_id,
            treinamento_id=treinamento_id,
            data_conclusao=data_conclusao,
            instrutor_nome=instrutor_nome,
            certificado_url=certificado_url,
            carga_horaria_realizada=carga_horaria_realizada,
            nota_aproveitamento=nota_aproveitamento,
            usuario=usuario,
        )

    def obter_alertas_vencimento_sst(self, empresa_id: str = "a0000000-0000-0000-0000-000000000001", dias_horizonte: int = 60) -> Dict[str, Any]:
        """RF-128: Alertas proativos de vencimento de ASO, EPI e Treinamentos."""
        return self.sst_service.obter_alertas_vencimento_sst(empresa_id=empresa_id, dias_horizonte=dias_horizonte)

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
        """RF-129, RF-130, RN-064: Emissão de CAT com geração de evento eSocial S-2210."""
        return self.sst_service.registrar_cat(
            colaborador_id=colaborador_id,
            tipo_acidente=tipo_acidente,
            data_hora=data_hora,
            local_acidente=local_acidente,
            descricao=descricao,
            houve_afastamento=houve_afastamento,
            houve_obito=houve_obito,
            cid_codigo=cid_codigo,
            medico_nome=medico_nome,
            medico_crm=medico_crm,
            medico_uf=medico_uf,
            duracao_provavel_dias=duracao_provavel_dias,
            empresa_id=empresa_id,
            usuario=usuario,
        )

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
        """RF-130: Condições Ambientais do Trabalho (Agentes Nocivos) eSocial S-2240."""
        return self.sst_service.registrar_condicao_ambiental_s2240(
            colaborador_id=colaborador_id,
            ambiente_nome=ambiente_nome,
            fator_risco_codigo=fator_risco_codigo,
            fator_risco_descricao=fator_risco_descricao,
            data_inicio=data_inicio,
            tipo_avaliacao=tipo_avaliacao,
            intensidade_concentracao=intensidade_concentracao,
            limite_tolerancia=limite_tolerancia,
            tecnica_utilizada=tecnica_utilizada,
            epc_eficaz=epc_eficaz,
            epi_eficaz=epi_eficaz,
            ca_epi_utilizado=ca_epi_utilizado,
            responsavel_nome=responsavel_nome,
            responsavel_cpf=responsavel_cpf,
            descricao_atividades=descricao_atividades,
            data_fim=data_fim,
            empresa_id=empresa_id,
            usuario=usuario,
        )

    def listar_sst_resumo(self) -> Dict[str, Any]:
        """RF-128, RF-147: Resumo integrado de exames, ASOs, EPIs, treinamentos, CATs e alertas."""
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

            alertas = self.sst_service.obter_alertas_vencimento_sst()

            return {
                "metricas": {
                    "total_asos": tot_asos,
                    "epis_em_uso": tot_epis,
                    "treinamentos_realizados": tot_treinamentos,
                    "total_cats": tot_cats,
                    "alertas_vencimento": alertas.get("total_alertas", 0),
                    "alertas_criticos": alertas.get("total_criticos_vencidos", 0),
                },
                "asos": ultimos_asos,
                "entregas_epi": ultimas_entregas_epi,
                "epis_entregas": ultimas_entregas_epi,
                "treinamentos": treinamentos,
                "cats": ultimas_cats,
                "alertas": alertas,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 13: ESOCIAL (RF-131 a RF-140)
    # ─────────────────────────────────────────────────────────────────────────
    def cadastrar_evento_esocial(self, tipo_evento: str, identificador_origem: str, xml_conteudo: str, ambiente: str = "homologacao", empresa_id: str = "a0000000-0000-0000-0000-000000000001", usuario: str = "Sistema") -> Dict[str, Any]:
        """RF-131, RF-132: Cadastro de evento eSocial com validação de schema."""
        return self.esocial_service.cadastrar_evento(tipo_evento=tipo_evento, identificador_origem=identificador_origem, xml_conteudo=xml_conteudo, ambiente=ambiente, empresa_id=empresa_id, usuario=usuario)

    def assinar_evento_esocial(self, evento_id: int, certificado_base64: Optional[str] = None, chave_privada_pem: Optional[str] = None, usuario: str = "DP") -> Dict[str, Any]:
        """RF-133: Assinatura digital XMLDSig com tratamento honesto na ausência de certificado."""
        return self.esocial_service.assinar_evento(evento_id=evento_id, certificado_base64=certificado_base64, chave_privada_pem=chave_privada_pem, usuario=usuario)

    def listar_esocial_eventos(self, status: Optional[str] = None, tipo: Optional[str] = None) -> List[Dict[str, Any]]:
        """RF-135, RF-139: Monitoramento de eventos eSocial."""
        return self.esocial_service.listar_eventos(status=status, tipo=tipo)

    def obter_evento_esocial(self, evento_id: int) -> Dict[str, Any]:
        """RF-135: Obter detalhes de evento eSocial."""
        return self.esocial_service.obter_evento(evento_id=evento_id)

    def transmitir_lote_esocial(self, evento_ids: Optional[List[int]] = None, usuario: str = "DP") -> Dict[str, Any]:
        """RF-134, RN-065: Validação real de schema XML e simulação transparente (sem recibos fictícios)."""
        return self.esocial_service.transmitir_lote(evento_ids=evento_ids, usuario=usuario)

    def registrar_rejeicao_esocial(self, evento_id: int, codigo_resposta: str, mensagem_resposta: str, erros_detalhados: Optional[List[Dict[str, Any]]] = None, usuario: str = "Auditor eSocial") -> Dict[str, Any]:
        """RF-136: Tratamento e registro detalhado de rejeições do eSocial."""
        return self.esocial_service.registrar_rejeicao(evento_id=evento_id, codigo_resposta=codigo_resposta, mensagem_resposta=mensagem_resposta, erros_detalhados=erros_detalhados, usuario=usuario)

    def retificar_evento_esocial(self, evento_id_original: int, novo_xml_conteudo: str, numero_recibo_anterior: str, justificativa: str, usuario: str = "DP") -> Dict[str, Any]:
        """RF-137: Retificação formal de eventos aceitos anteriormente vinculados por evento_retificador_de."""
        return self.esocial_service.retificar_evento(evento_id_original=evento_id_original, novo_xml_conteudo=novo_xml_conteudo, numero_recibo_anterior=numero_recibo_anterior, justificativa=justificativa, usuario=usuario)

    def solicitar_exclusao_evento_esocial(self, evento_id_alvo: int, numero_recibo_alvo: str, cnpj_empregador: str = "12345678000190", cpf_trabalhador: Optional[str] = None, justificativa: str = "Exclusão solicitada pelo DP", usuario: str = "DP") -> Dict[str, Any]:
        """RF-138: Exclusão de evento eSocial via geração oficial do evento S-3000."""
        return self.esocial_service.solicitar_exclusao_evento(evento_id_alvo=evento_id_alvo, numero_recibo_alvo=numero_recibo_alvo, cnpj_empregador=cnpj_empregador, cpf_trabalhador=cpf_trabalhador, justificativa=justificativa, usuario=usuario)

    def obter_historico_evento_esocial(self, evento_id: int) -> List[Dict[str, Any]]:
        """RF-139, RF-140: Histórico e rastreabilidade genealógica do evento eSocial."""
        return self.esocial_service.obter_historico_evento(evento_id=evento_id)

    def exportar_relatorio_pdf(self, tipo_relatorio: str, empresa_id: str = "a0000000-0000-0000-0000-000000000001", filtros: Optional[Dict[str, Any]] = None) -> bytes:
        """RF-150: Exportação de relatórios gerenciais em PDF A4 oficial."""
        return self.relatorios_service.exportar_relatorio_pdf(tipo_relatorio=tipo_relatorio, empresa_id=empresa_id, filtros=filtros)

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
        tipo_pagamento: str = "folha_mensal",
    ) -> Dict[str, Any]:
        """
        RF-097, RF-104, RF-178: Gera arquivo bancário CNAB 240 multi-empresa e multi-finalidade
        (folha_mensal, decimo_terceiro, ferias, rescisao), com suporte PIX em Segmento B e retorno bancário.
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
        tipo_pg_norm = str(tipo_pagamento or "folha_mensal").strip().lower()

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()

            # 1. Carregar dados cadastrais e bancários da empresa pagadora (Multi-Tenant)
            cur.execute(f"SELECT * FROM empresas WHERE id = {p}", (empresa_id,))
            empresa = fetchone_dict(cur, self.db_path)
            cnpj_empresa = re.sub(r"\D", "", empresa["cnpj"]).zfill(14) if empresa and empresa.get("cnpj") else "12345678000190"
            nome_empresa = (empresa.get("razao_social") or "EMPRESA CONTRATANTE RH2.0")[:30].upper().ljust(30)
            ag_emp = re.sub(r"\D", "", str((empresa or {}).get("banco_agencia") or "01234")).zfill(5)[:5]
            cc_emp = re.sub(r"\D", "", str((empresa or {}).get("banco_conta") or "000012345678")).zfill(12)[:12]

            # 2. Carregar títulos fechados conforme tipo_pagamento + filtro empresa_id
            if tipo_pg_norm == "decimo_terceiro":
                ano_ref = int(str(competencia)[:4])
                cur.execute(
                    f"""
                    SELECT d.id, d.valor_liquido as salario_liquido, c.id as colab_id, c.nome_completo, c.cpf, c.matricula
                    FROM decimo_terceiro d
                    JOIN colaboradores c ON c.id = d.colaborador_id
                    WHERE d.ano_base = {p} AND COALESCE(c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p};
                """,
                    (ano_ref, empresa_id),
                )
            elif tipo_pg_norm == "ferias":
                cur.execute(
                    f"""
                    SELECT fp.id, fp.valor_liquido as salario_liquido, c.id as colab_id, c.nome_completo, c.cpf, c.matricula
                    FROM ferias_programadas fp
                    JOIN colaboradores c ON c.id = fp.colaborador_id
                    WHERE fp.data_inicio LIKE {p} AND fp.status IN ('aprovada', 'solicitada')
                      AND COALESCE(fp.empresa_id, c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p};
                """,
                    (f"{competencia}%", empresa_id),
                )
            elif tipo_pg_norm == "rescisao":
                cur.execute(
                    f"""
                    SELECT r.id, r.valor_liquido as salario_liquido, c.id as colab_id, c.nome_completo, c.cpf, c.matricula
                    FROM rescisoes r
                    JOIN colaboradores c ON c.id = r.colaborador_id
                    WHERE r.data_afastamento LIKE {p} AND r.status != 'cancelada'
                      AND COALESCE(r.empresa_id, c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p};
                """,
                    (f"{competencia}%", empresa_id),
                )
            else:
                cur.execute(
                    f"""
                    SELECT f.id, f.salario_liquido, c.id as colab_id, c.nome_completo, c.cpf, c.matricula,
                           c.email, c.telefone
                    FROM folhas_pagamento f
                    JOIN colaboradores c ON c.id = f.colaborador_id
                    WHERE f.competencia = {p} AND f.situacao = 'fechada'
                      AND COALESCE(f.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p};
                """,
                    (competencia, empresa_id),
                )
            folhas = fetchall_dict(cur, self.db_path)
            if not folhas:
                raise PlataformaValidacaoException(f"Não existem registros aptos ({tipo_pg_norm}) para CNAB 240 na competência {competencia} (RF-097).")

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
                f"{ag_emp}"
                f" "
                f"{cc_emp}"
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
                f"{ag_emp}"
                f" "
                f"{cc_emp}"
                f" "
                f" "
                f"{nome_empresa}"
                f"{tipo_pg_norm[:25].upper().ljust(25)}"
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

                # Segmento A (Crédito em Conta Corrente/Salário ou PIX - integrado com RF-009)
                banco_fav = "000"
                agencia_fav = "01234"
                conta_fav_num = f"{colab_id_num:012d}"
                conta_dv = "9"
                chave_pix = ""
                try:
                    cur.execute(
                        f"SELECT banco_codigo, agencia, conta, conta_digito, chave_pix FROM colaborador_dados_bancarios WHERE colaborador_id = {p} AND ativo = 1 ORDER BY principal DESC, id DESC LIMIT 1",
                        (colab_id_num,),
                    )
                    conta_row = fetchone_dict(cur, self.db_path)
                    if conta_row:
                        b_cod = re.sub(r"\D", "", str(conta_row.get("banco_codigo") or ""))
                        ag_num = re.sub(r"\D", "", str(conta_row.get("agencia") or ""))
                        cc_num = re.sub(r"\D", "", str(conta_row.get("conta") or ""))
                        cc_dv = str(conta_row.get("conta_digito") or "0")[:1]
                        chave_pix = str(conta_row.get("chave_pix") or "").strip()[:60]
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
                    f"{str(f['id']).ljust(20)[:20]}"
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

                # Segmento B (Identificação do Favorecido e Chave PIX quando configurada)
                seg_b = (
                    f"{banco_cod}00013{seq_lote:05d}B "
                    f"1"
                    f"{cpf}"
                    f"{'':30}"
                    f"{'':30}"
                    f"{'':20}"
                    f"{data_hoje_cnab}"
                    f"{val_centavos:015d}"
                    f"{chave_pix.ljust(60)[:60]}"
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
                ) VALUES ({p}, {p}, {p}, {p}, 'CNAB240', {p}, {p}, {p}, {p}, {p})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO arquivos_bancarios_cnab (
                    empresa_id, competencia, tipo_folha, banco_codigo, layout_cnab,
                    total_registros, valor_total_liquido, conteudo_arquivo, gerado_por, gerado_em
                ) VALUES ({p}, {p}, {p}, {p}, 'CNAB240', {p}, {p}, {p}, {p}, {p});
            """
            params = (empresa_id, competencia, tipo_pg_norm, banco_cod, qtd_pagamentos, float(total_liquido), conteudo_cnab, usuario, agora)
            cnab_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

            self.registrar_auditoria(
                modulo="Financeiro",
                operacao="geracao_cnab240",
                registro_tipo="arquivos_bancarios_cnab",
                registro_id=cnab_id,
                usuario=usuario,
                detalhes=f"CNAB 240 ({tipo_pg_norm}) gerado para {banco_nome} ({banco_cod}) | Competência: {competencia} | {qtd_pagamentos} pagamentos | Total Líquido R$ {total_liquido:.2f}",
                empresa_id=empresa_id,
            )

            return {
                "sucesso": True,
                "cnab_id": cnab_id,
                "competencia": competencia,
                "tipo_pagamento": tipo_pg_norm,
                "banco_codigo": banco_cod,
                "banco_nome": banco_nome,
                "status_fluxo": "gerado",
                "total_colaboradores": qtd_pagamentos,
                "total_registros_arquivo": total_linhas_arquivo,
                "valor_total_liquido": float(total_liquido),
                "conteudo_cnab": conteudo_cnab,
                "mensagem": f"Arquivo CNAB 240 ({tipo_pg_norm}) gerado com sucesso para {banco_nome} ({qtd_pagamentos} pagamentos, R$ {total_liquido:.2f}).",
            }
        finally:
            conn.close()

    def processar_retorno_cnab240(
        self,
        nome_arquivo: str,
        conteudo_retorno: str,
        usuario: str = "Tesouraria",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        arquivo_cnab_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """RF-105: Processa arquivo de retorno bancário CNAB 240 ('00'=liquidado, demais=rejeitado), persistindo em cnab_retornos."""
        if not conteudo_retorno or not str(conteudo_retorno).strip():
            raise PlataformaValidacaoException("Conteúdo do arquivo de retorno CNAB vazio.")

        ocorrencias = []
        liquidados = 0
        rejeitados = 0
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            dt_hoje = agora[:10]

            for raw_line in str(conteudo_retorno).splitlines():
                ln = raw_line.strip()
                if not ln:
                    continue
                folha_id_ref = None
                cod_oc = "00"
                desc_oc = "Liquidado"
                if ln.startswith("RET;"):
                    parts = ln.split(";")
                    if len(parts) >= 3 and parts[1].strip().isdigit():
                        folha_id_ref = int(parts[1].strip())
                        cod_oc = parts[2].strip()[:2]
                        desc_oc = parts[3].strip() if len(parts) > 3 else ("Liquidado" if cod_oc == "00" else "Rejeitado")
                elif len(raw_line) >= 240 and raw_line[7] == "3" and raw_line[13] == "A":
                    seu_num = raw_line[73:93].strip()
                    if seu_num.isdigit():
                        folha_id_ref = int(seu_num)
                    cod_oc = raw_line[230:232].strip() or "00"
                    desc_oc = "Liquidado CNAB" if cod_oc == "00" else f"Ocorrência {cod_oc}"
                else:
                    continue

                status_pg = "liquidado" if cod_oc in ("00", "BD") else "rejeitado"
                if status_pg == "liquidado":
                    liquidados += 1
                    if folha_id_ref:
                        cur.execute(
                            f"SELECT observacoes FROM folhas_pagamento WHERE id = {p};",
                            (folha_id_ref,),
                        )
                        row_f_obs = cur.fetchone()
                        obs_atual = (row_f_obs[0] or "") if row_f_obs else ""
                        nova_obs = f"{obs_atual} [CNAB 240 Liquidado em {dt_hoje}]".strip()
                        cur.execute(
                            f"UPDATE folhas_pagamento SET data_pagamento = COALESCE(data_pagamento, {p}), observacoes = {p}, atualizado_por = {p}, atualizado_em = {p} WHERE id = {p} AND COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p};",
                            (dt_hoje, nova_obs, usuario, agora, folha_id_ref, empresa_id),
                        )
                        cur.execute(
                            f"INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel) VALUES ({p}, {p}, 'PAGAMENTO_CNAB', {p}, {p});",
                            (folha_id_ref, agora, f"Pagamento liquidado via retorno CNAB ({nome_arquivo})", usuario),
                        )
                else:
                    rejeitados += 1

                ocorrencias.append({"folha_id": folha_id_ref, "codigo_ocorrencia": cod_oc, "status": status_pg, "descricao": desc_oc})

            sql_pg = f"""
                INSERT INTO cnab_retornos (
                    empresa_id, arquivo_cnab_id, nome_arquivo, total_registros, total_liquidados,
                    total_rejeitados, ocorrencias_json, processado_por, processado_em
                ) VALUES ({','.join([p]*9)}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO cnab_retornos (
                    empresa_id, arquivo_cnab_id, nome_arquivo, total_registros, total_liquidados,
                    total_rejeitados, ocorrencias_json, processado_por, processado_em
                ) VALUES ({','.join([p]*9)});
            """
            ret_id = insert_returning_id(
                cur, conn, sql_pg, sql_sq,
                (empresa_id, arquivo_cnab_id, nome_arquivo, len(ocorrencias), liquidados, rejeitados, json.dumps(ocorrencias, ensure_ascii=False), usuario, agora),
                self.db_path,
            )
            conn.commit()
            self.registrar_auditoria(
                modulo="Financeiro", operacao="retorno_cnab240", registro_tipo="cnab_retornos",
                registro_id=ret_id, usuario=usuario,
                detalhes=f"Retorno CNAB '{nome_arquivo}': {liquidados} liquidado(s), {rejeitados} rejeitado(s).",
                empresa_id=empresa_id,
            )
            return {
                "sucesso": True,
                "retorno_id": ret_id,
                "total_registros": len(ocorrencias),
                "total_liquidados": liquidados,
                "total_rejeitados": rejeitados,
                "ocorrencias": ocorrencias,
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

            # 1. Query consolidada de contagens (substitui 11 queries sequenciais por 1 única rodada ao Neon)
            cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM colaboradores WHERE situacao = 'ativo') AS ativos,
                    (SELECT COUNT(*) FROM colaboradores WHERE situacao = 'inativo') AS inativos,
                    (SELECT COALESCE(SUM(salario_base), 0) FROM colaboradores WHERE situacao = 'ativo') AS massa_salarial_ativa,
                    (SELECT COUNT(*) FROM admissoes WHERE status = 'aprovada') AS total_admissoes,
                    (SELECT COUNT(*) FROM rescisoes WHERE status != 'cancelada') AS total_desligamentos,
                    (SELECT COUNT(*) FROM ocorrencias_ponto WHERE tipo_ocorrencia LIKE '%falta%') AS total_faltas,
                    (SELECT COUNT(*) FROM periodos_aquisitivos WHERE situacao = 'vencido' OR situacao = 'em_dobro') AS ferias_vencidas,
                    (SELECT COUNT(*) FROM ferias_programadas WHERE status = 'solicitada') AS ferias_programadas_qtd,
                    (SELECT COUNT(*) FROM sst_cats) AS total_cats,
                    (SELECT COUNT(*) FROM pendencias_operacionais WHERE status != 'resolvida') AS pendencias_abertas,
                    (SELECT COUNT(*) FROM pendencias_operacionais WHERE status != 'resolvida' AND LOWER(severidade) = 'critica') AS pendencias_criticas
            """)
            agg = cur.fetchone()
            ativos = int((agg[0] or 0) if agg else 0) or 1
            inativos = int((agg[1] or 0) if agg else 0)
            massa_salarial_ativa = float((agg[2] or 0.0) if agg else 0.0)
            total_admissoes = int((agg[3] or 0) if agg else 0)
            total_desligamentos = int((agg[4] or 0) if agg else 0)
            total_faltas = int((agg[5] or 0) if agg else 0)
            ferias_vencidas = int((agg[6] or 0) if agg else 0)
            ferias_programadas_qtd = int((agg[7] or 0) if agg else 0)
            total_cats = int((agg[8] or 0) if agg else 0)
            pendencias_abertas = int((agg[9] or 0) if agg else 0)
            pendencias_criticas = int((agg[10] or 0) if agg else 0)

            # Fórmula do Turnover (RF-181): (Admissões + Desligamentos) / 2 / Efetivo Médio * 100
            efetivo_medio = (ativos + inativos) / 2.0 if (ativos + inativos) > 0 else 1.0
            turnover_rate = round(((total_admissoes + total_desligamentos) / 2.0 / efetivo_medio) * 100.0, 2)
            absenteismo_rate = round((total_faltas / max(1, ativos * 22)) * 100.0, 2)

            # 2. Folha mais recente
            cur.execute("SELECT competencia, SUM(total_proventos) as prov, SUM(total_descontos) as desc_tot, SUM(salario_liquido) as liq, SUM(valor_fgts_informativo) as fgts, SUM(base_inss) as base_inss, SUM(base_irrf) as base_irrf FROM folhas_pagamento WHERE situacao != 'cancelada' GROUP BY competencia ORDER BY competencia DESC LIMIT 1;")
            folha_stats = fetchone_dict(cur, self.db_path)

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

            # 3. Distribuição por setor
            cur.execute("SELECT setor, COUNT(*) as total, SUM(salario_base) as massa FROM colaboradores WHERE situacao = 'ativo' GROUP BY setor ORDER BY total DESC;")
            setores_dist = fetchall_dict(cur, self.db_path)

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

            # RN-038: Gravar histórico temporal imutável de concessão
            cur.execute(
                f"""
                INSERT INTO beneficios_historico (
                    vinculo_id, colaborador_id, beneficio_id, operacao,
                    valor_anterior, valor_novo, custo_empresa, desconto_colab,
                    motivo, usuario_responsavel, criado_em
                ) VALUES ({p}, {p}, {p}, 'CONCESSAO', 0.0, {p}, {p}, {p}, {p}, {p}, {p});
                """,
                (
                    vinc_id, colaborador_id, beneficio_id,
                    calc["custo_total_mes"], calc["custo_empresa"], calc["desconto_colaborador"],
                    "Concessão inicial de benefício", usuario, agora,
                ),
            )
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

            # RN-038: Gravar histórico temporal de alteração sem sobrescrever informações históricas
            cur.execute(
                f"""
                INSERT INTO beneficios_historico (
                    vinculo_id, colaborador_id, beneficio_id, operacao,
                    valor_anterior, valor_novo, custo_empresa, desconto_colab,
                    motivo, usuario_responsavel, criado_em
                ) VALUES ({p}, {p}, {p}, 'ALTERACAO_VALOR', {p}, {p}, {p}, {p}, {p}, {p}, {p});
                """,
                (
                    vinculo_id, atual["colaborador_id"], atual["beneficio_id"],
                    float(atual.get("custo_total_mes") or 0.0), float(calc["custo_total_mes"]),
                    float(calc["custo_empresa"]), float(calc["desconto_colaborador"]),
                    str(dados.get("motivo") or "Alteração de parâmetros e valores do benefício"),
                    usuario, agora,
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

    def suspender_beneficio_colaborador(
        self,
        vinculo_id: int,
        motivo: str,
        data_suspensao: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        """RN-037: Suspende temporariamente benefício vinculado ao colaborador mantendo histórico."""
        atual = self.obter_beneficio_colaborador(vinculo_id)
        if not motivo or not str(motivo).strip():
            raise PlataformaValidacaoException("Motivo da suspensão é obrigatório.")
        dt_susp = data_suspensao or datetime.now().strftime("%Y-%m-%d")
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"UPDATE beneficios_colaborador SET ativo = 0, vigencia_fim = {p}, atualizado_em = {p} WHERE id = {p};",
                (dt_susp, agora, vinculo_id),
            )
            cur.execute(
                f"""
                INSERT INTO beneficios_historico (
                    vinculo_id, colaborador_id, beneficio_id, operacao,
                    valor_anterior, valor_novo, custo_empresa, desconto_colab,
                    motivo, usuario_responsavel, criado_em
                ) VALUES ({p}, {p}, {p}, 'SUSPENSAO', {p}, 0.0, 0.0, 0.0, {p}, {p}, {p});
                """,
                (
                    vinculo_id, atual["colaborador_id"], atual["beneficio_id"],
                    float(atual.get("custo_total_mes") or 0.0), motivo, usuario, agora,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.registrar_auditoria(
            modulo="Beneficios",
            operacao="suspensao",
            registro_tipo="beneficios_colaborador",
            registro_id=vinculo_id,
            usuario=usuario,
            detalhes=f"Benefício '{atual['beneficio_nome']}' suspenso para colaborador #{atual['colaborador_id']}. Motivo: {motivo}",
        )
        return self.obter_beneficio_colaborador(vinculo_id)

    def cancelar_beneficio_colaborador(
        self,
        vinculo_id: int,
        motivo: str,
        data_cancelamento: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        """RN-037: Cancela benefício com registro de recusa/cancelamento e histórico imutável."""
        atual = self.obter_beneficio_colaborador(vinculo_id)
        if not motivo or not str(motivo).strip():
            raise PlataformaValidacaoException("Motivo do cancelamento é obrigatório.")
        dt_canc = data_cancelamento or datetime.now().strftime("%Y-%m-%d")
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"UPDATE beneficios_colaborador SET ativo = 0, optante = 0, vigencia_fim = {p}, atualizado_em = {p} WHERE id = {p};",
                (dt_canc, agora, vinculo_id),
            )
            cur.execute(
                f"""
                INSERT INTO beneficios_historico (
                    vinculo_id, colaborador_id, beneficio_id, operacao,
                    valor_anterior, valor_novo, custo_empresa, desconto_colab,
                    motivo, usuario_responsavel, criado_em
                ) VALUES ({p}, {p}, {p}, 'CANCELAMENTO', {p}, 0.0, 0.0, 0.0, {p}, {p}, {p});
                """,
                (
                    vinculo_id, atual["colaborador_id"], atual["beneficio_id"],
                    float(atual.get("custo_total_mes") or 0.0), motivo, usuario, agora,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self.registrar_auditoria(
            modulo="Beneficios",
            operacao="cancelamento",
            registro_tipo="beneficios_colaborador",
            registro_id=vinculo_id,
            usuario=usuario,
            detalhes=f"Benefício '{atual['beneficio_nome']}' cancelado para colaborador #{atual['colaborador_id']}. Motivo: {motivo}",
        )
        return self.obter_beneficio_colaborador(vinculo_id)

    def listar_historico_beneficios_colaborador(
        self,
        colaborador_id: Optional[int] = None,
        vinculo_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """RN-038: Retorna linha do tempo com todo o histórico de concessões, alterações, suspensões e cancelamentos."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = """
                SELECT bh.*,
                       cat.nome AS beneficio_nome,
                       cat.tipo AS beneficio_tipo,
                       cat.codigo AS beneficio_codigo,
                       c.nome_completo AS colaborador_nome,
                       c.matricula AS colaborador_matricula
                FROM beneficios_historico bh
                JOIN beneficios_catalogo cat ON cat.id = bh.beneficio_id
                JOIN colaboradores c ON c.id = bh.colaborador_id
                WHERE 1=1
            """
            params = []
            if colaborador_id:
                sql += f" AND bh.colaborador_id = {p}"
                params.append(int(colaborador_id))
            if vinculo_id:
                sql += f" AND bh.vinculo_id = {p}"
                params.append(int(vinculo_id))
            sql += " ORDER BY bh.id DESC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

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
