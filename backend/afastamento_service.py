# -*- coding: utf-8 -*-
"""
Módulo 07: Gestão Completa de Afastamentos e Licenças — RF-061 a RF-070
Cobre:
- RF-061: Registro de afastamento (doença, acidente, maternidade, paternidade, licença não remunerada, serviço militar, suspensão)
- RF-062: Regra dos 15 dias empresa + 16º dia INSS com soma de atestados em 60 dias (Decreto 3.048/99 art. 75 §4º)
- RF-063: Estabilidade acidentária 12 meses (somente se >15d / benefício B91) e maternidade (ADCT art. 10 II 'b')
- RF-064: Suspensão vs interrupção contratual e impacto em férias/13º
- RF-065: Prorrogações auditáveis de afastamento (afastamentos_prorrogacoes)
- RF-066: Retorno ao trabalho exigindo ASO de Retorno APTO em sst_asos para afastamentos >= 30 dias
- RF-067: Bloqueio de sobreposição de afastamentos e atualização de colaboradores.situacao = 'afastado'
- RF-068: Geração eSocial S-2230 (início e término) em leiaute oficial v_S_01_02_00
- RF-069: Integração automática com Central de Pendências Operacionais
- RF-070: Consulta filtrada e relatório gerencial CSV de afastamentos e estabilidades
"""
import csv
import io
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from backend.database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, insert_returning_id
from backend.esocial_eventos_trabalhistas import (
    MAPA_MOTIVO_AFAST_ESOCIAL,
    gerar_xml_s2230,
    validar_xml_esocial_trabalhista,
)
from backend.plataforma_exceptions import (
    PlataformaRecursoNaoEncontradoException,
    PlataformaValidacaoException,
)

TIPOS_SUSPENSAO = {"licenca_nao_remunerada", "servico_militar", "suspensao_disciplinar"}


class AfastamentoService:
    def __init__(
        self,
        db_path: Optional[str] = None,
        auditoria_cb: Optional[Callable[..., None]] = None,
    ):
        self.db_path = db_path
        self._auditoria_cb = auditoria_cb

    def _conn(self):
        return get_connection(self.db_path)

    def _p(self) -> str:
        return "%s" if _usar_postgres(self.db_path) else "?"

    def _auditar(self, modulo: str, operacao: str, registro_tipo: str, registro_id: Any, usuario: str, detalhes: str):
        if self._auditoria_cb:
            self._auditoria_cb(
                modulo=modulo,
                operacao=operacao,
                registro_tipo=registro_tipo,
                registro_id=registro_id,
                usuario=usuario,
                detalhes=detalhes,
            )

    def _buscar_colab(self, cur, colaborador_id: int) -> Dict[str, Any]:
        p = self._p()
        cur.execute(f"SELECT * FROM colaboradores WHERE id = {p};", (int(colaborador_id),))
        c = fetchone_dict(cur, self.db_path)
        if not c:
            raise PlataformaRecursoNaoEncontradoException(f"Colaborador #{colaborador_id} não encontrado.")
        return c

    def _empresa_colab(self, cur, emp_id: str) -> Dict[str, Any]:
        p = self._p()
        cur.execute(f"SELECT * FROM empresas WHERE id = {p};", (emp_id,))
        return fetchone_dict(cur, self.db_path) or {"id": emp_id, "razao_social": "RH2.0 Enterprise", "cnpj": "12345678000190"}

    def _calcular_regras_afastamento(
        self,
        cur,
        colaborador_id: int,
        tipo: str,
        dt_ini_iso: str,
        dt_fim_iso: str,
        excluir_afastamento_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        p = self._p()
        dt_ini = datetime.strptime(dt_ini_iso, "%Y-%m-%d").date()
        dt_fim = datetime.strptime(dt_fim_iso, "%Y-%m-%d").date()
        if dt_fim < dt_ini:
            raise PlataformaValidacaoException("Data fim prevista não pode ser anterior à data de início do afastamento.")

        dias_totais = (dt_fim - dt_ini).days + 1
        tipo_norm = str(tipo or "doenca").strip().lower()

        if tipo_norm in ("doenca", "auxilio_doenca", "doenca_nao_relacionada"):
            # Decreto 3.048/99 art. 75 §4º: soma dias pagos pela empresa nos 60 dias anteriores
            jan_60 = (dt_ini - timedelta(days=60)).isoformat()
            sql_prev = f"""
                SELECT COALESCE(SUM(dias_empresa), 0) FROM afastamentos
                WHERE colaborador_id = {p}
                  AND tipo IN ('doenca', 'auxilio_doenca', 'doenca_nao_relacionada')
                  AND data_fim_prevista >= {p} AND data_inicio < {p}
            """
            params_prev: List[Any] = [int(colaborador_id), jan_60, dt_ini_iso]
            if excluir_afastamento_id:
                sql_prev += f" AND id != {p}"
                params_prev.append(int(excluir_afastamento_id))
            cur.execute(sql_prev, tuple(params_prev))
            ja_pagos = int(cur.fetchone()[0] or 0)
            saldo_empresa = max(0, 15 - ja_pagos)
            dias_empresa = min(saldo_empresa, dias_totais)
            dias_inss = max(0, dias_totais - dias_empresa)
            regime = "suspensao" if dias_inss > 0 else "interrupcao"
        elif tipo_norm in ("acidente_trabalho", "auxilio_doenca_acidentario"):
            dias_empresa = min(15, dias_totais)
            dias_inss = max(0, dias_totais - 15)
            regime = "suspensao" if dias_inss > 0 else "interrupcao"
        elif tipo_norm in ("maternidade", "licenca_maternidade", "paternidade"):
            dias_empresa = dias_totais
            dias_inss = 0
            regime = "interrupcao"
        elif tipo_norm in TIPOS_SUSPENSAO:
            dias_empresa = 0
            dias_inss = 0
            regime = "suspensao"
        else:
            dias_empresa = dias_totais
            dias_inss = 0
            regime = "interrupcao"

        exige_aso = 1 if (dias_totais >= 30 and tipo_norm not in ("paternidade",)) else 0

        estabilidade_fim = None
        if tipo_norm in ("acidente_trabalho", "auxilio_doenca_acidentario") and dias_totais > 15:
            # Lei 8.213/91 art. 118: estabilidade de 12 meses somente após cessação do auxílio-doença acidentário (>15d)
            estabilidade_fim = (dt_fim + timedelta(days=365)).isoformat()
        elif tipo_norm in ("maternidade", "licenca_maternidade"):
            estabilidade_fim = (dt_fim + timedelta(days=150)).isoformat()

        motivo_esocial = MAPA_MOTIVO_AFAST_ESOCIAL.get(tipo_norm, "03")
        return {
            "tipo": tipo_norm,
            "motivo_esocial": motivo_esocial,
            "dias_totais": dias_totais,
            "dias_empresa": dias_empresa,
            "dias_inss": dias_inss,
            "exige_aso_retorno": exige_aso,
            "estabilidade_fim": estabilidade_fim,
            "regime_efeito": regime,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # RF-061..RF-064 / RF-067..RF-069: Registrar Afastamento
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
        dt_ini_iso = str(data_inicio or "").strip()[:10]
        dt_fim_iso = str(data_fim_prevista or "").strip()[:10]

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, int(colaborador_id))
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            emp = self._empresa_colab(cur, emp_id)

            # Verificar sobreposição com afastamentos ativos (RF-067)
            cur.execute(
                f"""
                SELECT id, tipo, data_inicio, data_fim_prevista FROM afastamentos
                WHERE colaborador_id = {p} AND data_retorno_efetivo IS NULL
                  AND data_inicio <= {p} AND data_fim_prevista >= {p};
            """,
                (int(colaborador_id), dt_fim_iso, dt_ini_iso),
            )
            if cur.fetchone():
                raise PlataformaValidacaoException(
                    "Colaborador já possui afastamento ativo com sobreposição neste período (RF-067)."
                )

            regras = self._calcular_regras_afastamento(cur, int(colaborador_id), tipo, dt_ini_iso, dt_fim_iso)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sql_pg = f"""
                INSERT INTO afastamentos (
                    empresa_id, colaborador_id, tipo, motivo_esocial, subtipo_licenca, regime_efeito,
                    data_inicio, data_fim_prevista, cid, cat_id, estabilidade_fim,
                    dias_empresa, dias_inss, exige_aso_retorno, aso_retorno_realizado,
                    status_esocial, responsavel_registro, observacoes, criado_por, criado_em, atualizado_em
                ) VALUES ({','.join([p]*15)}, 'validado', {p}, {p}, {p}, {p}, {p}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO afastamentos (
                    empresa_id, colaborador_id, tipo, motivo_esocial, subtipo_licenca, regime_efeito,
                    data_inicio, data_fim_prevista, cid, cat_id, estabilidade_fim,
                    dias_empresa, dias_inss, exige_aso_retorno, aso_retorno_realizado,
                    status_esocial, responsavel_registro, observacoes, criado_por, criado_em, atualizado_em
                ) VALUES ({','.join([p]*15)}, 'validado', {p}, {p}, {p}, {p}, {p});
            """
            params = (
                emp_id, int(colaborador_id), regras["tipo"], regras["motivo_esocial"], subtipo_licenca,
                regras["regime_efeito"], dt_ini_iso, dt_fim_iso, cid, cat_id, regras["estabilidade_fim"],
                regras["dias_empresa"], regras["dias_inss"], regras["exige_aso_retorno"], 0,
                usuario, observacoes, usuario, agora, agora,
            )
            afast_id = insert_returning_id(cur, conn, sql_pg, sql_sq, params, self.db_path)

            # Atualiza status do colaborador para 'afastado'
            cur.execute(
                f"UPDATE colaboradores SET situacao = 'afastado', atualizado_em = {p} WHERE id = {p};",
                (agora, int(colaborador_id)),
            )

            # RF-068: Gera evento eSocial S-2230 v_S_01_02_00
            xml_s2230, _ = gerar_xml_s2230(
                colaborador=colab,
                cnpj_empregador=emp.get("cnpj") or "12345678000190",
                data_inicio=dt_ini_iso,
                motivo=regras["tipo"],
                cid=cid,
            )
            ok_xml, _ = validar_xml_esocial_trabalhista("S-2230", xml_s2230) if xml_s2230 else (False, ["XML vazio"])
            esoc_id = insert_returning_id(
                cur,
                conn,
                f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({p},'S-2230',{p},'homologacao',{p},{p},{p},{p}) RETURNING id;",
                f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({p},'S-2230',{p},'homologacao',{p},{p},{p},{p});",
                (emp_id, f"afastamento:{afast_id}", "validado" if ok_xml else "erro_schema", xml_s2230 or "<eSocial/>", usuario, agora),
                self.db_path,
            )
            cur.execute(
                f"UPDATE afastamentos SET esocial_inicio_id = {p}, status_esocial = {p} WHERE id = {p};",
                (esoc_id, "validado" if ok_xml else "erro_schema", afast_id),
            )

            # RF-069: Se exige ASO retorno (>=30d), cadastra pendência operacional
            if regras["exige_aso_retorno"]:
                cur.execute(
                    f"""
                    INSERT INTO pendencias_operacionais (
                        empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                        colaborador_id, prazo_limite, responsavel, status, criado_em
                    ) VALUES ({','.join([p]*11)});
                """,
                    (
                        emp_id, "Afastamentos", "retorno_afastamento",
                        f"Retorno de Afastamento (ASO Obrigatório) — {colab['nome_completo']}",
                        f"Afastamento #{afast_id} ({regras['dias_totais']} dias) exige ASO de Retorno APTO antes da reativação.",
                        "alta", int(colaborador_id), dt_fim_iso, "SST / DP", "pendente", agora,
                    ),
                )

            conn.commit()
            self._auditar(
                "Afastamentos", "inclusao", "afastamentos", afast_id, usuario,
                f"Afastamento {regras['tipo']} ({regras['regime_efeito']}) Colab {colaborador_id}: {dt_ini_iso} a {dt_fim_iso} ({regras['dias_totais']}d).",
            )

            return {
                "sucesso": True,
                "afastamento_id": afast_id,
                "tipo": regras["tipo"],
                "motivo_esocial": regras["motivo_esocial"],
                "regime_efeito": regras["regime_efeito"],
                "dias_totais": regras["dias_totais"],
                "dias_empresa": regras["dias_empresa"],
                "dias_inss": regras["dias_inss"],
                "estabilidade_ate": regras["estabilidade_fim"],
                "exige_aso_retorno": bool(regras["exige_aso_retorno"]),
                "esocial_inicio_id": esoc_id,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-065: Prorrogação de Afastamento
    # ─────────────────────────────────────────────────────────────────────────
    def prorrogar_afastamento(
        self,
        afastamento_id: int,
        nova_data_fim: str,
        motivo: str,
        cid: Optional[str] = None,
        documento_ref: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        if not motivo or len(motivo.strip()) < 3:
            raise PlataformaValidacaoException("Motivo da prorrogação é obrigatório.")
        nova_fim_iso = str(nova_data_fim or "").strip()[:10]

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM afastamentos WHERE id = {p};", (int(afastamento_id),))
            af = fetchone_dict(cur, self.db_path)
            if not af:
                raise PlataformaRecursoNaoEncontradoException(f"Afastamento #{afastamento_id} não encontrado.")
            if af.get("data_retorno_efetivo"):
                raise PlataformaValidacaoException("Afastamento já encerrado não pode ser prorrogado.")
            if nova_fim_iso <= str(af["data_fim_prevista"])[:10]:
                raise PlataformaValidacaoException("Nova data de término deve ser posterior à previsão atual.")

            regras = self._calcular_regras_afastamento(
                cur,
                int(af["colaborador_id"]),
                af["tipo"],
                str(af["data_inicio"])[:10],
                nova_fim_iso,
                excluir_afastamento_id=int(afastamento_id),
            )
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            emp_id = af.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

            cur.execute(
                f"""
                INSERT INTO afastamentos_prorrogacoes (
                    empresa_id, afastamento_id, data_fim_anterior, data_fim_nova, motivo, cid, documento_ref, criado_por, criado_em
                ) VALUES ({','.join([p]*9)});
            """,
                (emp_id, int(afastamento_id), str(af["data_fim_prevista"])[:10], nova_fim_iso, motivo.strip(), cid or af.get("cid"), documento_ref, usuario, agora),
            )
            cur.execute(
                f"""
                UPDATE afastamentos
                SET data_fim_prevista = {p}, dias_empresa = {p}, dias_inss = {p}, exige_aso_retorno = {p},
                    estabilidade_fim = {p}, regime_efeito = {p}, cid = COALESCE({p}, cid), atualizado_em = {p}
                WHERE id = {p};
            """,
                (
                    nova_fim_iso, regras["dias_empresa"], regras["dias_inss"], regras["exige_aso_retorno"],
                    regras["estabilidade_fim"], regras["regime_efeito"], cid, agora, int(afastamento_id),
                ),
            )
            conn.commit()
            self._auditar("Afastamentos", "prorrogacao", "afastamentos", afastamento_id, usuario, f"Prorrogado até {nova_fim_iso}: {motivo}")
            return {
                "sucesso": True,
                "afastamento_id": int(afastamento_id),
                "data_fim_anterior": str(af["data_fim_prevista"])[:10],
                "data_fim_nova": nova_fim_iso,
                "dias_totais": regras["dias_totais"],
                "dias_empresa": regras["dias_empresa"],
                "dias_inss": regras["dias_inss"],
                "exige_aso_retorno": bool(regras["exige_aso_retorno"]),
                "estabilidade_ate": regras["estabilidade_fim"],
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-066 / RF-068: Retorno ao Trabalho com Validação de ASO de Retorno
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_retorno_afastamento(
        self,
        afastamento_id: int,
        data_retorno: str,
        aso_id: Optional[int] = None,
        usuario: str = "SST / DP",
    ) -> Dict[str, Any]:
        dt_ret_iso = str(data_retorno or "").strip()[:10]
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM afastamentos WHERE id = {p};", (int(afastamento_id),))
            af = fetchone_dict(cur, self.db_path)
            if not af:
                raise PlataformaRecursoNaoEncontradoException(f"Afastamento #{afastamento_id} não encontrado.")
            if af.get("data_retorno_efetivo"):
                raise PlataformaValidacaoException("Retorno deste afastamento já foi registrado anteriormente.")

            cid = int(af["colaborador_id"])
            colab = self._buscar_colab(cur, cid)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            emp = self._empresa_colab(cur, emp_id)

            aso_validado = None
            if int(af.get("exige_aso_retorno") or 0) == 1:
                if aso_id:
                    cur.execute(
                        f"SELECT * FROM sst_asos WHERE id = {p} AND colaborador_id = {p};",
                        (int(aso_id), cid),
                    )
                    aso_validado = fetchone_dict(cur, self.db_path)
                else:
                    cur.execute(
                        f"""
                        SELECT * FROM sst_asos
                        WHERE colaborador_id = {p}
                          AND LOWER(tipo_aso) LIKE '%retorno%'
                          AND LOWER(resultado) = 'apto'
                          AND data_emissao >= {p}
                        ORDER BY id DESC LIMIT 1;
                    """,
                        (cid, str(af["data_inicio"])[:10]),
                    )
                    aso_validado = fetchone_dict(cur, self.db_path)

                if not aso_validado or str(aso_validado.get("resultado") or "").lower() != "apto":
                    raise PlataformaValidacaoException(
                        "Bloqueio NR-07 / RF-066: Afastamento >= 30 dias exige ASO de Retorno ao Trabalho com resultado 'apto' registrado em SST."
                    )
                aso_id = int(aso_validado["id"])

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Recomputar estabilidade a partir do retorno efetivo quando acidentário >15d
            nova_estab = af.get("estabilidade_fim")
            if str(af["tipo"]).lower() in ("acidente_trabalho", "auxilio_doenca_acidentario"):
                dias_reais = (datetime.strptime(dt_ret_iso, "%Y-%m-%d").date() - datetime.strptime(str(af["data_inicio"])[:10], "%Y-%m-%d").date()).days + 1
                if dias_reais > 15:
                    nova_estab = (datetime.strptime(dt_ret_iso, "%Y-%m-%d").date() + timedelta(days=365)).isoformat()

            # Gera S-2230 de término do afastamento
            xml_fim, _ = gerar_xml_s2230(
                colaborador=colab,
                cnpj_empregador=emp.get("cnpj") or "12345678000190",
                data_inicio=str(af["data_inicio"])[:10],
                motivo=af["tipo"],
                data_fim=dt_ret_iso,
            )
            ok_xml, _ = validar_xml_esocial_trabalhista("S-2230", xml_fim) if xml_fim else (False, [])
            esoc_termino_id = insert_returning_id(
                cur,
                conn,
                f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({p},'S-2230',{p},'homologacao',{p},{p},{p},{p}) RETURNING id;",
                f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({p},'S-2230',{p},'homologacao',{p},{p},{p},{p});",
                (emp_id, f"afastamento_retorno:{afastamento_id}", "validado" if ok_xml else "erro_schema", xml_fim or "<eSocial/>", usuario, agora),
                self.db_path,
            )

            cur.execute(
                f"""
                UPDATE afastamentos
                SET data_retorno_efetivo = {p}, aso_retorno_realizado = {p}, aso_retorno_id = {p},
                    esocial_termino_id = {p}, estabilidade_fim = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (dt_ret_iso, 1 if aso_id else 0, aso_id, esoc_termino_id, nova_estab, agora, int(afastamento_id)),
            )

            # Reativa colaborador se não houver outro afastamento aberto
            cur.execute(
                f"SELECT COUNT(*) FROM afastamentos WHERE colaborador_id = {p} AND data_retorno_efetivo IS NULL AND id != {p};",
                (cid, int(afastamento_id)),
            )
            if int(cur.fetchone()[0] or 0) == 0:
                cur.execute(
                    f"UPDATE colaboradores SET situacao = 'ativo', atualizado_em = {p} WHERE id = {p} AND situacao = 'afastado';",
                    (agora, cid),
                )

            # Resolve pendência operacional de retorno
            cur.execute(
                f"""
                UPDATE pendencias_operacionais
                SET status = 'resolvida', resolvida_por = {p}, resolvida_em = {p}
                WHERE colaborador_id = {p} AND tipo_pendencia = 'retorno_afastamento' AND status != 'resolvida';
            """,
                (usuario, agora, cid),
            )

            conn.commit()
            self._auditar("Afastamentos", "retorno", "afastamentos", afastamento_id, usuario, f"Retorno registrado em {dt_ret_iso} (ASO #{aso_id}).")
            return {
                "sucesso": True,
                "afastamento_id": int(afastamento_id),
                "data_retorno_efetivo": dt_ret_iso,
                "aso_retorno_id": aso_id,
                "estabilidade_ate": nova_estab,
                "esocial_termino_id": esoc_termino_id,
                "colaborador_reativado": True,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-070: Consulta Filtrada e Relatório Gerencial CSV
    # ─────────────────────────────────────────────────────────────────────────
    def listar_afastamentos(
        self,
        colaborador_id: Optional[int] = None,
        empresa_id: Optional[str] = None,
        tipo: Optional[str] = None,
        apenas_ativos: bool = False,
    ) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            query = """
                SELECT a.*, c.nome_completo, c.matricula, c.setor, c.cargo
                FROM afastamentos a
                JOIN colaboradores c ON c.id = a.colaborador_id
                WHERE 1=1
            """
            params: List[Any] = []
            if colaborador_id:
                query += f" AND a.colaborador_id = {p}"
                params.append(int(colaborador_id))
            if empresa_id:
                query += f" AND COALESCE(c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p}"
                params.append(empresa_id)
            if tipo:
                query += f" AND LOWER(a.tipo) = {p}"
                params.append(tipo.strip().lower())
            if apenas_ativos:
                query += " AND a.data_retorno_efetivo IS NULL"
            query += " ORDER BY a.data_inicio DESC, a.id DESC;"
            cur.execute(query, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def relatorio_afastamentos(
        self,
        empresa_id: Optional[str] = None,
        tipo: Optional[str] = None,
        setor: Optional[str] = None,
    ) -> Dict[str, Any]:
        itens = self.listar_afastamentos(empresa_id=empresa_id, tipo=tipo)
        if setor:
            itens = [i for i in itens if str(i.get("setor") or "").strip().lower() == setor.strip().lower()]

        hoje = datetime.now().strftime("%Y-%m-%d")
        por_tipo: Dict[str, int] = {}
        ativos = 0
        estabilidades_ativas = 0
        pendentes_aso = 0
        for a in itens:
            t = a.get("tipo") or "outro"
            por_tipo[t] = por_tipo.get(t, 0) + 1
            if not a.get("data_retorno_efetivo"):
                ativos += 1
                if int(a.get("exige_aso_retorno") or 0) == 1 and not int(a.get("aso_retorno_realizado") or 0):
                    pendentes_aso += 1
            if a.get("estabilidade_fim") and str(a["estabilidade_fim"])[:10] >= hoje:
                estabilidades_ativas += 1

        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["ID", "Matricula", "Colaborador", "Setor", "Tipo", "Regime", "Inicio", "Fim Previsto", "Retorno Efetivo", "Dias Empresa", "Dias INSS", "Estabilidade Ate", "ASO Retorno"])
        for a in itens:
            w.writerow([
                a["id"], a.get("matricula") or "", a.get("nome_completo") or "", a.get("setor") or "",
                a.get("tipo") or "", a.get("regime_efeito") or "", a.get("data_inicio") or "",
                a.get("data_fim_prevista") or "", a.get("data_retorno_efetivo") or "",
                a.get("dias_empresa") or 0, a.get("dias_inss") or 0,
                a.get("estabilidade_fim") or "", "OK" if a.get("aso_retorno_realizado") else ("PENDENTE" if a.get("exige_aso_retorno") else "N/A"),
            ])

        return {
            "total": len(itens),
            "ativos": ativos,
            "estabilidades_ativas": estabilidades_ativas,
            "pendentes_aso_retorno": pendentes_aso,
            "por_tipo": por_tipo,
            "itens": itens,
            "csv": buf.getvalue(),
        }
