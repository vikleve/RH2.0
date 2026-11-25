# -*- coding: utf-8 -*-
"""
Serviço de Tabelas Legais Versionadas e Calendário Oficial de Competência — RH2.0 Enterprise
Centraliza vigência, fonte normativa, histórico de atualizações e contagem real de dias úteis/DSR.
"""
import calendar
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from .database import fetchall_dict, fetchone_dict, get_connection, init_db, insert_returning_id, ph
from .plataforma_exceptions import PlataformaRecursoNaoEncontradoException, PlataformaValidacaoException


class TabelasLegaisService:
    def __init__(self, db_path: Optional[str] = None, auto_init: bool = True):
        self.db_path = db_path
        # Evita executar migrações repetidas no caminho das requisições serverless.
        if auto_init:
            init_db(db_path=self.db_path)

    def _conn(self):
        return get_connection(self.db_path)

    def _p(self) -> str:
        return ph(self.db_path)

    def listar_tabelas_legais(self, apenas_ativas: bool = False) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            sql = "SELECT * FROM tabelas_legais_vigencia"
            if apenas_ativas:
                sql += " WHERE ativo = 1"
            sql += " ORDER BY vigencia_inicio DESC, id DESC;"
            cur.execute(sql)
            linhas = fetchall_dict(cur, self.db_path)
            for row in linhas:
                row["faixas_inss"] = json.loads(row.get("faixas_inss_json") or "[]")
                row["faixas_irrf"] = json.loads(row.get("faixas_irrf_json") or "[]")
            return linhas
        finally:
            conn.close()

    def listar_historico_tabelas(self, tabela_id: Optional[int] = None) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            if tabela_id:
                cur.execute(f"SELECT * FROM tabelas_legais_historico WHERE tabela_id = {p} ORDER BY id DESC;", (int(tabela_id),))
            else:
                cur.execute("SELECT * FROM tabelas_legais_historico ORDER BY id DESC LIMIT 100;")
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def obter_tabela_vigente(self, competencia: Optional[str] = None) -> Dict[str, Any]:
        """Resolve a tabela legal vigente para a competência AAAA-MM sem hardcode cego."""
        comp = (competencia or datetime.now().strftime("%Y-%m")).strip()[:7]
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                SELECT * FROM tabelas_legais_vigencia
                WHERE ativo = 1
                  AND competencia_inicio <= {p}
                  AND (competencia_fim IS NULL OR competencia_fim = '' OR competencia_fim >= {p})
                ORDER BY competencia_inicio DESC, id DESC
                LIMIT 1;
            """,
                (comp, comp),
            )
            row = fetchone_dict(cur, self.db_path)
            if not row:
                cur.execute("SELECT * FROM tabelas_legais_vigencia WHERE ativo = 1 ORDER BY competencia_inicio DESC, id DESC LIMIT 1;")
                row = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()

        if not row:
            raise PlataformaRecursoNaoEncontradoException("Nenhuma tabela legal vigente cadastrada no banco.")

        row["faixas_inss"] = json.loads(row.get("faixas_inss_json") or "[]")
        row["faixas_irrf"] = json.loads(row.get("faixas_irrf_json") or "[]")
        row["tabela_inss_tuples"] = [
            (Decimal(str(fx[0])), Decimal(str(fx[1])), Decimal(str(fx[2])))
            for fx in row["faixas_inss"]
        ]
        row["tabela_irrf_tuples"] = [
            (Decimal(str(fx[0])) if fx[0] is not None else None, Decimal(str(fx[1])), Decimal(str(fx[2])))
            for fx in row["faixas_irrf"]
        ]
        return row

    def salvar_tabela_legal(self, dados: Dict[str, Any], usuario: str = "Administrador DP") -> Dict[str, Any]:
        """Cria ou atualiza tabela legal versionada registrando histórico normativo imutável."""
        d = dict(dados or {})
        identificador = str(d.get("identificador") or "").strip().upper()
        comp_ini = str(d.get("competencia_inicio") or "").strip()[:7]
        fonte = str(d.get("fonte_normativa") or "").strip()
        if not identificador or not comp_ini or not fonte:
            raise PlataformaValidacaoException("Identificador, competência de início (AAAA-MM) e fonte normativa são obrigatórios.")

        faixas_inss = d.get("faixas_inss")
        faixas_irrf = d.get("faixas_irrf")
        if not isinstance(faixas_inss, list) or not faixas_inss:
            raise PlataformaValidacaoException("As faixas de INSS devem ser informadas em lista não vazia.")
        if not isinstance(faixas_irrf, list) or not faixas_irrf:
            raise PlataformaValidacaoException("As faixas de IRRF devem ser informadas em lista não vazia.")

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        comp_fim = str(d.get("competencia_fim") or "").strip()[:7] or None
        vig_ini = str(d.get("vigencia_inicio") or f"{comp_ini}-01").strip()[:10]
        desc = str(d.get("descricao") or f"Tabela Legal {identificador}").strip()
        sm = float(d.get("salario_minimo") or 1621.00)
        teto_inss = float(d.get("teto_inss") or 8475.55)
        teto_contrib = float(d.get("teto_contribuicao_inss") or 988.09)
        ded_dep = float(d.get("deducao_dependente_irrf") or 189.59)
        desc_simp = float(d.get("desconto_simplificado_irrf") or 607.20)
        lei_15270 = 1 if d.get("lei_15270_ativa", 1) in (1, True, "1", "true") else 0
        lim_sf = float(d.get("limite_salario_familia") or 1980.38)
        cota_sf = float(d.get("valor_cota_salario_familia") or 67.54)
        fgts_pad = float(d.get("aliquota_fgts_padrao") or 8.00)
        fgts_apr = float(d.get("aliquota_fgts_aprendiz") or 2.00)
        ativo = 1 if d.get("ativo", 1) in (1, True, "1", "true") else 0
        inss_json = json.dumps(faixas_inss, ensure_ascii=False)
        irrf_json = json.dumps(faixas_irrf, ensure_ascii=False)

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT id FROM tabelas_legais_vigencia WHERE identificador = {p};", (identificador,))
            existente = cur.fetchone()
            if existente:
                tab_id = int(existente[0])
                cur.execute(
                    f"""
                    UPDATE tabelas_legais_vigencia
                    SET descricao = {p}, competencia_inicio = {p}, competencia_fim = {p},
                        vigencia_inicio = {p}, fonte_normativa = {p}, salario_minimo = {p},
                        teto_inss = {p}, teto_contribuicao_inss = {p}, faixas_inss_json = {p},
                        faixas_irrf_json = {p}, deducao_dependente_irrf = {p},
                        desconto_simplificado_irrf = {p}, lei_15270_ativa = {p},
                        limite_salario_familia = {p}, valor_cota_salario_familia = {p},
                        aliquota_fgts_padrao = {p}, aliquota_fgts_aprendiz = {p},
                        ativo = {p}, atualizado_em = {p}
                    WHERE id = {p};
                """,
                    (
                        desc, comp_ini, comp_fim, vig_ini, fonte, sm,
                        teto_inss, teto_contrib, inss_json, irrf_json, ded_dep,
                        desc_simp, lei_15270, lim_sf, cota_sf, fgts_pad, fgts_apr,
                        ativo, agora, tab_id,
                    ),
                )
                acao = "atualizacao"
            else:
                sql_pg = f"""
                    INSERT INTO tabelas_legais_vigencia (
                        identificador, descricao, competencia_inicio, competencia_fim,
                        vigencia_inicio, fonte_normativa, salario_minimo, teto_inss,
                        teto_contribuicao_inss, faixas_inss_json, faixas_irrf_json,
                        deducao_dependente_irrf, desconto_simplificado_irrf, lei_15270_ativa,
                        limite_salario_familia, valor_cota_salario_familia,
                        aliquota_fgts_padrao, aliquota_fgts_aprendiz, ativo,
                        criado_por, criado_em, atualizado_em
                    ) VALUES ({','.join([p]*22)}) RETURNING id;
                """
                sql_sq = f"""
                    INSERT INTO tabelas_legais_vigencia (
                        identificador, descricao, competencia_inicio, competencia_fim,
                        vigencia_inicio, fonte_normativa, salario_minimo, teto_inss,
                        teto_contribuicao_inss, faixas_inss_json, faixas_irrf_json,
                        deducao_dependente_irrf, desconto_simplificado_irrf, lei_15270_ativa,
                        limite_salario_familia, valor_cota_salario_familia,
                        aliquota_fgts_padrao, aliquota_fgts_aprendiz, ativo,
                        criado_por, criado_em, atualizado_em
                    ) VALUES ({','.join([p]*22)});
                """
                tab_id = insert_returning_id(
                    cur,
                    conn,
                    sql_pg,
                    sql_sq,
                    (
                        identificador, desc, comp_ini, comp_fim, vig_ini, fonte, sm,
                        teto_inss, teto_contrib, inss_json, irrf_json, ded_dep,
                        desc_simp, lei_15270, lim_sf, cota_sf, fgts_pad, fgts_apr,
                        ativo, usuario, agora, agora,
                    ),
                    self.db_path,
                )
                acao = "criacao"

            cur.execute(
                f"""
                INSERT INTO tabelas_legais_historico (
                    tabela_id, identificador, acao, snapshot_json, motivo, usuario, criado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p});
            """,
                (
                    tab_id,
                    identificador,
                    acao,
                    json.dumps(d, ensure_ascii=False),
                    str(d.get("motivo") or f"Registro normativo ({fonte})"),
                    usuario,
                    agora,
                ),
            )
            conn.commit()
            cur.execute(f"SELECT * FROM tabelas_legais_vigencia WHERE id = {p};", (tab_id,))
            row = fetchone_dict(cur, self.db_path)
            row["faixas_inss"] = json.loads(row["faixas_inss_json"])
            row["faixas_irrf"] = json.loads(row["faixas_irrf_json"])
            return row
        finally:
            conn.close()

    def listar_feriados(
        self,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        ano: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = f"SELECT * FROM feriados_calendario WHERE ativo = 1 AND (empresa_id = {p} OR abrangencia = 'nacional')"
            params: List[Any] = [empresa_id]
            if ano:
                sql += f" AND data_feriado LIKE {p}"
                params.append(f"{int(ano)}-%%" if self._p() == "%s" else f"{int(ano)}-%")
            sql += " ORDER BY data_feriado ASC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def cadastrar_feriado(
        self,
        data_feriado: str,
        descricao: str,
        abrangencia: str = "municipal",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        filial_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        dt_str = str(data_feriado or "").strip()[:10]
        try:
            datetime.strptime(dt_str, "%Y-%m-%d")
        except ValueError:
            raise PlataformaValidacaoException("Data do feriado inválida (use AAAA-MM-DD).")
        desc = str(descricao or "").strip()
        if not desc:
            raise PlataformaValidacaoException("Descrição do feriado é obrigatória.")
        abr = str(abrangencia or "municipal").strip().lower()
        if abr not in ("nacional", "estadual", "municipal"):
            raise PlataformaValidacaoException("Abrangência deve ser nacional, estadual ou municipal.")
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql_pg = f"""
                INSERT INTO feriados_calendario (empresa_id, filial_id, data_feriado, descricao, abrangencia, ativo, criado_em)
                VALUES ({p},{p},{p},{p},{p},1,{p}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO feriados_calendario (empresa_id, filial_id, data_feriado, descricao, abrangencia, ativo, criado_em)
                VALUES ({p},{p},{p},{p},{p},1,{p});
            """
            fid = insert_returning_id(cur, conn, sql_pg, sql_sq, (empresa_id, filial_id, dt_str, desc, abr, agora), self.db_path)
            conn.commit()
            cur.execute(f"SELECT * FROM feriados_calendario WHERE id = {p};", (fid,))
            return fetchone_dict(cur, self.db_path)
        finally:
            conn.close()

    def contar_dias_uteis_dsr_competencia(
        self,
        competencia: str,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        tipo_regime: str = "5x2",
    ) -> Dict[str, int]:
        """Calcula dias úteis e domingos/feriados reais da competência AAAA-MM com base no calendário oficial."""
        try:
            ano, mes = map(int, competencia.strip()[:7].split("-"))
        except Exception:
            return {"dias_uteis": 25, "domingos_feriados": 5, "total_dias_mes": 30}

        _, total_dias = calendar.monthrange(ano, mes)
        feriados = {
            f["data_feriado"][:10]
            for f in self.listar_feriados(empresa_id=empresa_id, ano=ano)
            if f["data_feriado"].startswith(f"{ano:04d}-{mes:02d}")
        }
        dias_uteis = 0
        dom_fer = 0
        for d in range(1, total_dias + 1):
            dt_obj = date(ano, mes, d)
            dt_iso = dt_obj.isoformat()
            # Para fins de DSR sobre variáveis CLT (Lei 605/49), consideram-se úteis seg-sáb não feriados
            if dt_obj.weekday() == 6 or dt_iso in feriados:
                dom_fer += 1
            else:
                dias_uteis += 1
        return {
            "dias_uteis": max(1, dias_uteis),
            "domingos_feriados": max(1, dom_fer),
            "total_dias_mes": total_dias,
            "feriados_no_mes": len(feriados),
        }
