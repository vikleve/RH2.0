"""
Camada de Serviços da Folha de Pagamento — RH / DP
Regras de negócio, persistência relacional, validação de unicidade,
auditoria histórica, ciclo de vida da folha (Rascunho -> Calculada -> Fechada)
e integração com a camada de cálculos.
Funciona em modo dual: PostgreSQL (produção/Supabase) e SQLite (local/testes).
"""
import calendar
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, init_db, insert_returning_id, ph
from .folha_calculos import (
    arredondar_moeda,
    calcular_inss_progressivo,
    calcular_irrf_progressivo,
    processar_calculo_folha,
)


class FolhaValidacaoException(Exception):
    def __init__(self, erros: dict):
        super().__init__("Inconsistência nos dados da folha de pagamento.")
        self.erros = erros


class FolhaNaoEncontradaException(Exception):
    pass


class FolhaBloqueadaException(Exception):
    pass


class FolhaService:
    def __init__(self, db_path: str = None, auto_init: bool = True):
        self.db_path = db_path
        # Em produção serverless, não execute migrações a cada requisição.
        # A inicialização continua habilitada por padrão para dev/testes.
        if auto_init:
            init_db(self.db_path)

    # ──────────────────────────────────────────────────────────
    # DB Helpers
    # ──────────────────────────────────────────────────────────

    def _ph(self) -> str:
        return ph(self.db_path)

    def _pg(self) -> bool:
        return _usar_postgres(self.db_path)

    def _conn(self):
        return get_connection(self.db_path)

    def _fetchone(self, cursor):
        return fetchone_dict(cursor, self.db_path)

    def _fetchall(self, cursor):
        return fetchall_dict(cursor, self.db_path)

    def _insert_id(self, cursor, conn, sql_pg, sql_sqlite, params):
        return insert_returning_id(cursor, conn, sql_pg, sql_sqlite, params, self.db_path)

    # ──────────────────────────────────────────────────────────
    # Parâmetros de Folha
    # ──────────────────────────────────────────────────────────

    def obter_parametro_vigente(self) -> Dict[str, Any]:
        """Retorna parâmetros ativos e vigentes; os defaults são oficiais para 2026."""
        self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM folha_parametros WHERE ativo = 1 ORDER BY id DESC LIMIT 1;"
        )
        param = self._fetchone(cursor)
        conn.close()
        padroes_2026 = {
            "id": 1,
            "codigo": "PADRAO_CLT_2026",
            "descricao": "Parâmetros Padrão CLT 2026",
            "horas_mensais_padrao": 220.0,
            "dias_mes_padrao": 30,
            "percentual_he_padrao": 50.0,
            "percentual_he_extra": 100.0,
            "percentual_adicional_noturno": 20.0,
            "aplicar_reducao_noturna": 0,
            "fator_reducao_noturna": 1.142857,
            "aplicar_inss": 1,
            "aplicar_irrf": 1,
            "aliquota_fgts": 8.0,
            "teto_inss": 8475.55,
            "deducao_dependente_irrf": 189.59,
            "desconto_simplificado_irrf": 607.20,
            "salario_minimo": 1621.00,
            "limite_salario_familia": 1980.38,
            "valor_cota_salario_familia": 67.54,
            "ativo": 1,
            "validado_por_profissional": 0,
        }
        if not param:
            return padroes_2026
        # Mantém configurações específicas já cadastradas, mas completa campos
        # recém-introduzidos sem sobrescrever percentuais aprovados pelo DP.
        for chave, valor in padroes_2026.items():
            param.setdefault(chave, valor)
        return param

    def salvar_parametros(self, dados: Dict[str, Any], usuario: str = "Sistema/Administrador") -> Dict[str, Any]:
        """Cria ou atualiza parâmetros de cálculo."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        codigo = dados.get("codigo", "CONFIG_CUSTOM").strip().upper()
        desc = dados.get("descricao", "Parâmetros Customizados").strip()
        vig_ini = dados.get("vigencia_inicio", "2026-01-01").strip()
        vig_fim = dados.get("vigencia_fim") or None
        padroes_2026 = {
            "teto_inss": 8475.55,
            "deducao_dependente_irrf": 189.59,
            "desconto_simplificado_irrf": 607.20,
            "salario_minimo": 1621.00,
            "limite_salario_familia": 1980.38,
            "valor_cota_salario_familia": 67.54,
        }

        cursor.execute(f"SELECT id FROM folha_parametros WHERE codigo = {P}", (codigo,))
        existente = cursor.fetchone()

        params_values = (
            desc, vig_ini, vig_fim,
            float(dados.get("horas_mensais_padrao", 220.0)),
            int(dados.get("dias_mes_padrao", 30)),
            float(dados.get("percentual_he_padrao", 50.0)),
            float(dados.get("percentual_he_extra", 100.0)),
            float(dados.get("percentual_adicional_noturno", 20.0)),
            int(dados.get("aplicar_reducao_noturna", 0)),
            float(dados.get("fator_reducao_noturna", 1.142857)),
            int(dados.get("aplicar_inss", 1)),
            int(dados.get("aplicar_irrf", 1)),
            float(dados.get("aliquota_fgts", 8.0)),
            float(dados.get("teto_inss", padroes_2026["teto_inss"])),
            float(dados.get("deducao_dependente_irrf", padroes_2026["deducao_dependente_irrf"])),
            int(dados.get("ativo", 1)),
            int(dados.get("validado_por_profissional", 0)),
            agora
        )

        if existente:
            param_id = existente[0]
            cursor.execute(f"""
                UPDATE folha_parametros SET
                    descricao = {P}, vigencia_inicio = {P}, vigencia_fim = {P},
                    horas_mensais_padrao = {P}, dias_mes_padrao = {P}, percentual_he_padrao = {P},
                    percentual_he_extra = {P}, percentual_adicional_noturno = {P}, aplicar_reducao_noturna = {P},
                    fator_reducao_noturna = {P}, aplicar_inss = {P}, aplicar_irrf = {P}, aliquota_fgts = {P},
                    teto_inss = {P}, deducao_dependente_irrf = {P}, ativo = {P}, validado_por_profissional = {P},
                    atualizado_em = {P}
                WHERE id = {param_id};
            """, params_values)
        else:
            sql_pg = f"""
                INSERT INTO folha_parametros (
                    descricao, vigencia_inicio, vigencia_fim,
                    horas_mensais_padrao, dias_mes_padrao, percentual_he_padrao,
                    percentual_he_extra, percentual_adicional_noturno, aplicar_reducao_noturna,
                    fator_reducao_noturna, aplicar_inss, aplicar_irrf, aliquota_fgts,
                    teto_inss, deducao_dependente_irrf, ativo, validado_por_profissional,
                    atualizado_em, codigo, criado_em
                ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO folha_parametros (
                    descricao, vigencia_inicio, vigencia_fim,
                    horas_mensais_padrao, dias_mes_padrao, percentual_he_padrao,
                    percentual_he_extra, percentual_adicional_noturno, aplicar_reducao_noturna,
                    fator_reducao_noturna, aplicar_inss, aplicar_irrf, aliquota_fgts,
                    teto_inss, deducao_dependente_irrf, ativo, validado_por_profissional,
                    atualizado_em, codigo, criado_em
                ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P});
            """
            param_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, params_values + (codigo, agora))

        conn.commit()
        cursor.execute(f"SELECT * FROM folha_parametros WHERE id = {P}", (param_id,))
        resultado = self._fetchone(cursor)
        conn.close()
        return resultado

    # ──────────────────────────────────────────────────────────
    # Dados Contratuais e Dependentes do Colaborador
    # ──────────────────────────────────────────────────────────

    def obter_dados_colaborador(self, colaborador_id: int) -> Dict[str, Any]:
        """Busca dados contratuais e dependentes para o cálculo da folha."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(f"SELECT * FROM colaboradores WHERE id = {P}", (colaborador_id,))
        colab = self._fetchone(cursor)
        if not colab:
            conn.close()
            raise FolhaNaoEncontradaException(f"Colaborador com ID {colaborador_id} não encontrado.")

        cursor.execute(f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo'", (colaborador_id,))
        total_dep = cursor.fetchone()[0]
        try:
            cursor.execute(
                f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo' AND COALESCE(eh_dependente_irrf, 1) = 1",
                (colaborador_id,)
            )
            total_dep_irrf = cursor.fetchone()[0]
            cursor.execute(
                f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo' AND COALESCE(eh_elegivel_salario_familia, 0) = 1",
                (colaborador_id,)
            )
            total_dep_sf = cursor.fetchone()[0]
            cursor.execute(
                f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo' AND COALESCE(eh_plano_saude, 0) = 1",
                (colaborador_id,)
            )
            total_dep_ps = cursor.fetchone()[0]
        except Exception:
            total_dep_irrf = total_dep
            total_dep_sf = 0
            total_dep_ps = 0

        colab["total_dependentes"] = total_dep
        colab["total_dependentes_irrf"] = total_dep_irrf
        colab["total_dependentes_salario_familia"] = total_dep_sf
        colab["total_dependentes_plano_saude"] = total_dep_ps

        conn.close()
        return colab

    # ──────────────────────────────────────────────────────────
    # Ciclo de Vida da Folha de Pagamento
    # ──────────────────────────────────────────────────────────

    def _validar_e_hidratar_eventos(
        self,
        eventos: Optional[List[Dict[str, Any]]],
        horas_divisor: float = 220.0,
        dias_mes: int = 30,
    ) -> List[Dict[str, Any]]:
        """Valida existência, status ativo, limites (horas/dias/percentual) e hidrata incidências do catálogo."""
        try:
            from .folha_calculos import MAPA_ALIAS_LEGADO
        except ImportError:
            from backend.folha_calculos import MAPA_ALIAS_LEGADO

        rubricas = self.listar_rubricas(apenas_ativas=False)
        rubricas_map = {str(r["codigo"]).strip().upper(): r for r in rubricas}
        max_horas = max(220.0, float(horas_divisor or 220.0))
        max_dias = max(31, int(dias_mes or 30))

        resultado: List[Dict[str, Any]] = []
        for raw_ev in (eventos or []):
            ev = dict(raw_ev)
            raw_cod = str(ev.get("codigo") or ev.get("codigo_evento") or "").strip().upper()
            cod_oficial = MAPA_ALIAS_LEGADO.get(raw_cod, raw_cod)
            is_livre = bool(ev.get("is_custom_livre")) or raw_cod in ("__OUTRO", "__OUTRO__")

            rub = None
            if cod_oficial and not is_livre:
                rub = rubricas_map.get(cod_oficial) or rubricas_map.get(raw_cod)
                if not rub:
                    raise FolhaValidacaoException({
                        "eventos": f"Evento '{raw_cod}' não está cadastrado no catálogo de rubricas."
                    })
                if int(rub.get("ativo", 1)) == 0:
                    raise FolhaValidacaoException({
                        "eventos": f"Evento '{cod_oficial} - {rub['descricao']}' está inativo e não pode ser lançado."
                    })
                ev.setdefault("tipo", rub.get("tipo", "provento"))
                ev.setdefault("forma_calculo", rub.get("forma_calculo", "valor_fixo"))
                ev.setdefault("incide_inss", int(rub.get("incide_inss", 0)))
                ev.setdefault("incide_irrf", int(rub.get("incide_irrf", 0)))
                ev.setdefault("incide_fgts", int(rub.get("incide_fgts", 0)))
                if not ev.get("descricao"):
                    ev["descricao"] = rub.get("descricao", "")
                has_val = ev.get("valor_total") not in (None, "") or ev.get("valor_informado") not in (None, "")
                if not has_val and ev.get("forma_calculo") == "valor_fixo" and float(rub.get("valor_padrao") or 0) > 0:
                    ev["valor_informado"] = float(rub["valor_padrao"])

            ref_raw = ev.get("quantidade") if ev.get("quantidade") not in (None, "") else ev.get("referencia")
            ref_val = float(ref_raw or 0)
            perc_val = float(ev.get("percentual") or 0)
            val_raw = ev.get("valor_total") if ev.get("valor_total") not in (None, "") else ev.get("valor_informado")
            val_num = float(val_raw or 0)

            if ref_val < 0 or perc_val < 0 or val_num < 0:
                raise FolhaValidacaoException({
                    "eventos": f"Valores ou referências negativos não são permitidos no evento '{raw_cod}'."
                })

            forma = str(ev.get("forma_calculo") or "").strip().lower()
            if cod_oficial in ("0010", "0011", "0015", "0020", "0532") or forma == "horas":
                if ref_val > max_horas:
                    raise FolhaValidacaoException({
                        "eventos": f"Quantidade de horas ({ref_val}) no evento '{raw_cod}' excede o limite mensal ({max_horas}h)."
                    })
            if cod_oficial in ("0530", "0531") or forma == "dias":
                if ref_val > max_dias:
                    raise FolhaValidacaoException({
                        "eventos": f"Quantidade de dias ({ref_val}) no evento '{raw_cod}' excede o limite do mês ({max_dias} dias)."
                    })
            if perc_val > 100.0 or (forma == "percentual" and ref_val > 100.0):
                raise FolhaValidacaoException({
                    "eventos": f"Percentual informado no evento '{raw_cod}' não pode exceder 100%."
                })

            resultado.append(ev)
        return resultado

    def criar_ou_atualizar_folha(
        self,
        colaborador_id: int,
        competencia: str,
        periodo_inicio: str,
        periodo_fim: str,
        data_pagamento: Optional[str] = None,
        dias_trabalhados: float = 30.0,
        dias_mes: int = 30,
        horas_divisor: float = 220.0,
        eventos: Optional[List[Dict[str, Any]]] = None,
        observacoes: str = "",
        usuario: str = "Sistema/Administrador",
        folha_id_existente: Optional[int] = None,
        tipo_folha: str = "mensal",
        empresa_id: Optional[str] = None,
        filial_id: Optional[str] = None,
        salvar_como_rascunho: bool = False,
        incluir_beneficios_ativos: bool = False,
        integrar_ponto: bool = False,
        integrar_afastamentos: bool = True,
    ) -> Dict[str, Any]:
        """
        Cria nova folha ou atualiza existente.
        Bloqueia duplicidade de (colaborador_id, competencia, tipo_folha), exceto folha complementar.
        Calcula os valores intermediários e finais, persistindo os itens discriminados.
        """
        colab = self.obter_dados_colaborador(colaborador_id)
        salario_base = float(colab.get("salario_base", 0.0))
        if salario_base <= 0:
            raise FolhaValidacaoException({"salario_base": "O colaborador selecionado não possui salário-base válido cadastrado."})

        num_dependentes = int(colab.get("total_dependentes_irrf", colab.get("total_dependentes", 0)))
        num_dep_sf = int(colab.get("total_dependentes_salario_familia", 0))
        tipo_folha_norm = (tipo_folha or "mensal").strip().lower()
        tipos_validos = ("mensal", "adiantamento", "13_primeira", "13_segunda", "complementar", "ferias", "rescisoria")
        if tipo_folha_norm not in tipos_validos:
            raise FolhaValidacaoException({"tipo_folha": f"Tipo de folha inválido: '{tipo_folha_norm}'."})

        if (colab.get("situacao") or "ativo").lower() != "ativo" and tipo_folha_norm != "rescisoria":
            raise FolhaValidacaoException({"colaborador_id": "Somente colaboradores ativos podem receber folha (exceto folha rescisória)."})

        emp_id = (empresa_id or colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()
        fil_id = (filial_id or colab.get("filial_id") or None)

        # Validação da competência (AAAA-MM) e confronto com data de admissão
        comp = competencia.strip()
        partes_comp = comp.split("-")
        if len(partes_comp) != 2 or not (len(partes_comp[0]) == 4 and len(partes_comp[1]) == 2):
            raise FolhaValidacaoException({"competencia": "A competência deve estar no formato AAAA-MM (ex: 2026-10)."})

        adm_str = str(colab.get("data_admissao") or "").strip()
        if len(adm_str) >= 7 and adm_str[4] == "-" and comp < adm_str[:7]:
            raise FolhaValidacaoException({
                "competencia": f"A competência {comp} não pode ser anterior à data de admissão ({adm_str})."
            })

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        # Checagem de duplicidade (folha complementar permite múltiplas versões na mesma competência)
        versao = 1
        if tipo_folha_norm != "complementar":
            if folha_id_existente:
                cursor.execute(
                    f"SELECT id, situacao FROM folhas_pagamento WHERE colaborador_id = {P} AND competencia = {P} AND COALESCE(tipo_folha, 'mensal') = {P} AND id != {P};",
                    (colaborador_id, comp, tipo_folha_norm, folha_id_existente)
                )
            else:
                cursor.execute(
                    f"SELECT id, situacao FROM folhas_pagamento WHERE colaborador_id = {P} AND competencia = {P} AND COALESCE(tipo_folha, 'mensal') = {P};",
                    (colaborador_id, comp, tipo_folha_norm)
                )
            dup = cursor.fetchone()
            if dup:
                conn.close()
                raise FolhaValidacaoException({
                    "competencia": f"Já existe uma folha cadastrada ({tipo_folha_norm}) para o colaborador {colab['nome_completo']} na competência {comp} (ID #{dup[0]})."
                })
        elif not folha_id_existente:
            cursor.execute(
                f"SELECT COALESCE(MAX(versao), 0) FROM folhas_pagamento WHERE colaborador_id = {P} AND competencia = {P} AND tipo_folha = 'complementar';",
                (colaborador_id, comp)
            )
            versao = int(cursor.fetchone()[0] or 0) + 1

        # Se estamos editando, checa se a folha existente está fechada
        if folha_id_existente:
            cursor.execute(f"SELECT situacao FROM folhas_pagamento WHERE id = {P};", (folha_id_existente,))
            folha_atual = cursor.fetchone()
            if folha_atual and folha_atual[0] == "fechada":
                conn.close()
                raise FolhaBloqueadaException("Esta folha de pagamento já está fechada e não pode ser alterada diretamente.")

        # Obter parâmetros vigentes + tabela legal da competência + calendário + alíquotas da empresa
        param = self.obter_parametro_vigente()
        param_id = param.get("id")
        try:
            from .tabelas_legais_service import TabelasLegaisService
        except ImportError:
            from backend.tabelas_legais_service import TabelasLegaisService
        tab_srv = TabelasLegaisService(db_path=self.db_path)
        tab_legal = tab_srv.obter_tabela_vigente(comp)
        cal_comp = tab_srv.contar_dias_uteis_dsr_competencia(comp, emp_id)

        cursor.execute(f"SELECT aliquota_inss_patronal, aliquota_rat, fap, aliquota_terceiros FROM empresas WHERE id = {P};", (emp_id,))
        emp_aliq = cursor.fetchone()
        aliq_pat = float(emp_aliq[0]) if emp_aliq and emp_aliq[0] is not None else 20.0
        aliq_rat = float(emp_aliq[1]) if emp_aliq and emp_aliq[1] is not None else 2.0
        fap_emp = float(emp_aliq[2]) if emp_aliq and emp_aliq[2] is not None else 1.0
        aliq_terc = float(emp_aliq[3]) if emp_aliq and emp_aliq[3] is not None else 5.8

        # Ajustes de regras conforme tipo de contrato e tipo de folha
        tipo_contrato = (colab.get("tipo_contrato") or "CLT").strip().lower()
        aliquota_fgts_efetiva = (
            float(tab_legal.get("aliquota_fgts_aprendiz", 2.0))
            if tipo_contrato == "aprendiz"
            else float(param.get("aliquota_fgts", tab_legal.get("aliquota_fgts_padrao", 8.0)))
        )

        eventos_proc = list(eventos or [])
        aplicar_inss_efetivo = bool(param.get("aplicar_inss", 1))
        aplicar_irrf_efetivo = bool(param.get("aplicar_irrf", 1))

        if tipo_folha_norm in ("13_primeira", "adiantamento"):
            aplicar_inss_efetivo = False
            aplicar_irrf_efetivo = False
            if tipo_folha_norm == "13_primeira" and not any(str(e.get("codigo", "")).strip() == "0110" for e in eventos_proc):
                eventos_proc.append({
                    "codigo": "0110",
                    "descricao": "13º salário – 1ª parcela (adiantamento)",
                    "tipo": "provento",
                    "referencia": 50.0,
                    "valor_informado": round(salario_base * 0.5, 2),
                })
                dias_trabalhados = 0.0
            elif tipo_folha_norm == "adiantamento" and not eventos_proc:
                eventos_proc.append({
                    "codigo": "0075",
                    "descricao": "Adiantamento salarial (40%)",
                    "tipo": "provento",
                    "referencia": 40.0,
                    "valor_informado": round(salario_base * 0.4, 2),
                })
                dias_trabalhados = 0.0

        # Salário-família automático se houver dependentes elegíveis e remuneração dentro do limite
        if num_dep_sf > 0 and tipo_folha_norm == "mensal":
            limite_sf = float(tab_legal.get("limite_salario_familia", 1980.38))
            cota_sf = float(tab_legal.get("valor_cota_salario_familia", 67.54))
            if salario_base <= limite_sf and not any(str(e.get("codigo", "")).strip() == "0202" for e in eventos_proc):
                eventos_proc.append({
                    "codigo": "0202",
                    "descricao": f"Salário-família ({num_dep_sf} cota(s))",
                    "tipo": "provento",
                    "referencia": num_dep_sf,
                    "valor_informado": round(num_dep_sf * cota_sf, 2),
                })

        # Integração com Afastamentos ativos na competência (reduz dias não remunerados pela empresa/suspensão)
        if integrar_afastamentos and tipo_folha_norm == "mensal" and float(dias_trabalhados) == 30.0:
            ano_c, mes_c = int(comp[:4]), int(comp[5:7])
            ult_dia = calendar.monthrange(ano_c, mes_c)[1]
            dt_comp_ini = date(ano_c, mes_c, 1)
            dt_comp_fim = date(ano_c, mes_c, ult_dia)
            cursor.execute(
                f"""
                SELECT tipo, dias_empresa, dias_inss, regime_efeito, data_inicio, data_fim_prevista, data_retorno_efetivo
                FROM afastamentos
                WHERE colaborador_id = {P}
                  AND (dias_inss > 0 OR regime_efeito = 'suspensao')
                  AND data_inicio <= {P}
                  AND COALESCE(data_retorno_efetivo, data_fim_prevista) >= {P};
            """,
                (colaborador_id, dt_comp_fim.isoformat(), dt_comp_ini.isoformat()),
            )
            dias_descontar_afast = 0
            for af_r in self._fetchall(cursor):
                af_ini = datetime.strptime(str(af_r["data_inicio"])[:10], "%Y-%m-%d").date()
                af_fim = datetime.strptime(str(af_r.get("data_retorno_efetivo") or af_r["data_fim_prevista"])[:10], "%Y-%m-%d").date()
                d_emp_af = int(af_r.get("dias_empresa") or 0)
                if str(af_r.get("regime_efeito") or "") == "suspensao" and d_emp_af == 0:
                    unpaid_ini = af_ini
                else:
                    unpaid_ini = af_ini + timedelta(days=d_emp_af)
                ov_ini = max(dt_comp_ini, unpaid_ini)
                ov_fim = min(dt_comp_fim, af_fim)
                if ov_fim >= ov_ini:
                    dias_descontar_afast += (ov_fim - ov_ini).days + 1
            if dias_descontar_afast > 0:
                dias_trabalhados = max(0.0, float(dias_trabalhados) - float(min(30, dias_descontar_afast)))

        # Integração com Ponto Eletrônico fechado ou solicitado (RF085/RF086)
        if integrar_ponto and tipo_folha_norm == "mensal":
            try:
                from .ponto_service import PontoService
            except ImportError:
                from backend.ponto_service import PontoService
            cods_man = {str(e.get("codigo") or e.get("codigo_evento") or "").strip() for e in eventos_proc}
            for ev_pt in PontoService(db_path=self.db_path).gerar_eventos_folha_do_ponto(colaborador_id, comp):
                if str(ev_pt.get("codigo") or "").strip() not in cods_man:
                    eventos_proc.append(ev_pt)

        # Recuperação automática do desconto de adiantamento salarial (rubrica 0520)
        if tipo_folha_norm == "mensal":
            cods_atuais = {str(e.get("codigo") or e.get("codigo_evento") or "").strip() for e in eventos_proc}
            if "0520" not in cods_atuais:
                cursor.execute(
                    f"""
                    SELECT salario_liquido FROM folhas_pagamento
                    WHERE colaborador_id = {P} AND competencia = {P} AND tipo_folha = 'adiantamento'
                      AND situacao IN ('calculada', 'aprovada', 'fechada', 'paga')
                    ORDER BY id DESC LIMIT 1;
                """,
                    (colaborador_id, comp),
                )
                row_adiant = cursor.fetchone()
                if row_adiant and float(row_adiant[0] or 0) > 0:
                    eventos_proc.append({
                        "codigo": "0520",
                        "descricao": "Adiantamento salarial (recuperação automática)",
                        "referencia": 1,
                        "valor_informado": round(float(row_adiant[0]), 2),
                    })

        # Integração opcional com Benefícios Ativos (RF079)
        if incluir_beneficios_ativos and tipo_folha_norm == "mensal":
            try:
                from .plataforma_service import PlataformaService
            except ImportError:
                from backend.plataforma_service import PlataformaService
            res_benef = PlataformaService(db_path=self.db_path).obter_descontos_beneficios_folha(colaborador_id, comp)
            codigos_ja_lancados = {str(e.get("codigo") or e.get("codigo_evento") or "").strip() for e in eventos_proc}
            for ev_ben in res_benef.get("eventos_folha", []):
                if str(ev_ben.get("codigo") or "").strip() not in codigos_ja_lancados:
                    eventos_proc.append(ev_ben)

        # Validar eventos no catálogo e hidratar incidências
        try:
            eventos_proc = self._validar_e_hidratar_eventos(
                eventos_proc, horas_divisor=horas_divisor, dias_mes=dias_mes
            )
            calc_result = processar_calculo_folha(
                salario_base=salario_base,
                dias_trabalhados=dias_trabalhados,
                dias_mes=dias_mes,
                divisor_horas=horas_divisor,
                eventos_informados=eventos_proc,
                numero_dependentes=num_dependentes,
                parametros_config={
                    "percentual_noturno": param.get("percentual_adicional_noturno", 20.0),
                    "aplicar_reducao_noturna": bool(param.get("aplicar_reducao_noturna", 0)),
                    "fator_reducao_noturna": param.get("fator_reducao_noturna", "1.142857"),
                    "aplicar_inss": aplicar_inss_efetivo,
                    "aplicar_irrf": aplicar_irrf_efetivo,
                    "aliquota_fgts": aliquota_fgts_efetiva,
                    "tabela_inss": tab_legal["tabela_inss_tuples"],
                    "teto_inss": tab_legal["teto_inss"],
                    "teto_contribuicao_inss": tab_legal["teto_contribuicao_inss"],
                    "tabela_irrf": tab_legal["tabela_irrf_tuples"],
                    "deducao_dependente_irrf": tab_legal["deducao_dependente_irrf"],
                    "desconto_simplificado_irrf": tab_legal["desconto_simplificado_irrf"],
                    "aplicar_reducao_lei_15270": bool(tab_legal.get("lei_15270_ativa", 1)),
                    "salario_minimo": tab_legal["salario_minimo"],
                    "limite_salario_familia": tab_legal["limite_salario_familia"],
                    "valor_cota_salario_familia": tab_legal["valor_cota_salario_familia"],
                    "dias_uteis": cal_comp["dias_uteis"],
                    "domingos_feriados": cal_comp["domingos_feriados"],
                    "aliquota_patronal": aliq_pat,
                    "aliquota_rat": aliq_rat,
                    "fap": fap_emp,
                    "aliquota_terceiros": aliq_terc,
                }
            )
        except FolhaValidacaoException:
            conn.close()
            raise
        except ValueError as ve:
            conn.close()
            raise FolhaValidacaoException({"eventos": str(ve)})
        except Exception:
            conn.close()
            raise

        # Ajuste diferencial verdadeiro para folha complementar quando houver folha mensal prévia
        if tipo_folha_norm == "complementar":
            cursor.execute(
                f"""
                SELECT * FROM folhas_pagamento
                WHERE colaborador_id = {P} AND competencia = {P} AND COALESCE(tipo_folha, 'mensal') = 'mensal'
                ORDER BY id DESC LIMIT 1;
            """,
                (colaborador_id, comp),
            )
            folha_mensal_ant = self._fetchone(cursor)
            if folha_mensal_ant:
                cursor.execute(
                    f"SELECT codigo_evento, descricao, tipo, referencia, valor_total, incide_inss, incide_irrf, incide_fgts FROM folha_itens WHERE folha_id = {P};",
                    (folha_mensal_ant["id"],),
                )
                itens_mensal_ant = self._fetchall(cursor)
                evs_recalc = [
                    {
                        "codigo": str(it["codigo_evento"]),
                        "referencia": float(it.get("referencia") or 1),
                        "valor_informado": float(it.get("valor_total") or 0),
                    }
                    for it in itens_mensal_ant
                    if str(it.get("codigo_evento")) not in ("0001", "0002", "0501", "0502", "0505", "0506", "0507")
                    and it.get("tipo") in ("provento", "desconto")
                ] + list(eventos_proc)
                evs_recalc_hid = self._validar_e_hidratar_eventos(evs_recalc, horas_divisor=horas_divisor, dias_mes=dias_mes)
                calc_comb = processar_calculo_folha(
                    salario_base=salario_base,
                    dias_trabalhados=float(folha_mensal_ant.get("dias_trabalhados") or 30.0),
                    dias_mes=dias_mes,
                    divisor_horas=horas_divisor,
                    eventos_informados=evs_recalc_hid,
                    numero_dependentes=num_dependentes,
                    parametros_config={
                        "percentual_noturno": param.get("percentual_adicional_noturno", 20.0),
                        "aplicar_reducao_noturna": bool(param.get("aplicar_reducao_noturna", 0)),
                        "fator_reducao_noturna": param.get("fator_reducao_noturna", "1.142857"),
                        "aplicar_inss": aplicar_inss_efetivo,
                        "aplicar_irrf": aplicar_irrf_efetivo,
                        "aliquota_fgts": aliquota_fgts_efetiva,
                        "tabela_inss": tab_legal["tabela_inss_tuples"],
                        "teto_inss": tab_legal["teto_inss"],
                        "teto_contribuicao_inss": tab_legal["teto_contribuicao_inss"],
                        "tabela_irrf": tab_legal["tabela_irrf_tuples"],
                        "deducao_dependente_irrf": tab_legal["deducao_dependente_irrf"],
                        "desconto_simplificado_irrf": tab_legal["desconto_simplificado_irrf"],
                        "aplicar_reducao_lei_15270": bool(tab_legal.get("lei_15270_ativa", 1)),
                        "salario_minimo": tab_legal["salario_minimo"],
                        "limite_salario_familia": tab_legal["limite_salario_familia"],
                        "valor_cota_salario_familia": tab_legal["valor_cota_salario_familia"],
                        "dias_uteis": cal_comp["dias_uteis"],
                        "domingos_feriados": cal_comp["domingos_feriados"],
                        "aliquota_patronal": aliq_pat,
                        "aliquota_rat": aliq_rat,
                        "fap": fap_emp,
                        "aliquota_terceiros": aliq_terc,
                    },
                )
                res_comb = calc_comb["resumo"]
                delta_prov = round(max(0.0, float(res_comb["total_proventos"]) - float(folha_mensal_ant["total_proventos"])), 2)
                inss_comb = sum(float(it["valor_total"]) for it in calc_comb["itens"] if it["tipo"] == "desconto" and it.get("codigo_catalogo") in ("0501", "0502"))
                irrf_comb = sum(float(it["valor_total"]) for it in calc_comb["itens"] if it["tipo"] == "desconto" and it.get("codigo_catalogo") in ("0505", "0506", "0507"))
                delta_inss = round(max(0.0, inss_comb - float(folha_mensal_ant.get("inss_descontado") or 0)), 2)
                delta_irrf = round(max(0.0, irrf_comb - float(folha_mensal_ant.get("irrf_descontado") or 0)), 2)
                delta_fgts = round(max(0.0, float(res_comb["valor_fgts_informativo"]) - float(folha_mensal_ant.get("valor_fgts_informativo") or 0)), 2)
                delta_base_fgts = round(max(0.0, float(res_comb["base_fgts"]) - float(folha_mensal_ant.get("base_fgts") or 0)), 2)
                delta_base_inss = round(max(0.0, float(res_comb["base_inss"]) - float(folha_mensal_ant.get("base_inss") or 0)), 2)
                delta_base_irrf = round(max(0.0, float(res_comb["base_irrf"]) - float(folha_mensal_ant.get("base_irrf") or 0)), 2)
                itens_delta = [it for it in calc_result["itens"] if str(it.get("codigo_catalogo") or it.get("codigo_evento")) not in ("0001", "0501", "0505", "0901", "0902", "0903", "0904", "0905", "0906", "0907") and it["tipo"] in ("provento", "desconto")]
                if delta_inss > 0:
                    itens_delta.append({"codigo_evento": "0501", "codigo_catalogo": "0501", "descricao": "INSS complementar (diferença)", "tipo": "desconto", "referencia": 1, "unidade_referencia": "valor", "valor_unitario": delta_inss, "valor_total": delta_inss, "origem": "calculado", "inss": 0, "irrf": 0, "fgts": 0, "memoria_calculo": f"Diferença INSS: {inss_comb:.2f} - {float(folha_mensal_ant.get('inss_descontado') or 0):.2f}"})
                if delta_irrf > 0:
                    itens_delta.append({"codigo_evento": "0505", "codigo_catalogo": "0505", "descricao": "IRRF complementar (diferença)", "tipo": "desconto", "referencia": 1, "unidade_referencia": "valor", "valor_unitario": delta_irrf, "valor_total": delta_irrf, "origem": "calculado", "inss": 0, "irrf": 0, "fgts": 0, "memoria_calculo": f"Diferença IRRF: {irrf_comb:.2f} - {float(folha_mensal_ant.get('irrf_descontado') or 0):.2f}"})
                if delta_fgts > 0:
                    itens_delta.append({"codigo_evento": "0904", "codigo_catalogo": "0904", "descricao": "FGTS complementar (diferença 8%)", "tipo": "informativo", "referencia": 8.0, "unidade_referencia": "%", "valor_unitario": delta_base_fgts, "valor_total": delta_fgts, "origem": "calculado", "inss": 0, "irrf": 0, "fgts": 0, "memoria_calculo": f"Diferença FGTS sobre base R$ {delta_base_fgts:.2f}"})
                delta_desc_tot = round(sum(float(x["valor_total"]) for x in itens_delta if x["tipo"] == "desconto"), 2)
                delta_liq = round(delta_prov - delta_desc_tot, 2)
                calc_result["resumo"].update({
                    "dias_trabalhados": 0.0,
                    "salario_base_proporcional": 0.0,
                    "total_proventos": delta_prov,
                    "total_descontos": delta_desc_tot,
                    "salario_liquido": delta_liq,
                    "base_inss": delta_base_inss,
                    "base_fgts": delta_base_fgts,
                    "valor_fgts_informativo": delta_fgts,
                    "base_irrf": delta_base_irrf,
                    "encargos_patronais": {"total_encargos_patronais": round(delta_base_inss * ((aliq_pat + (aliq_rat * fap_emp) + aliq_terc) / 100.0), 2)},
                })
                calc_result["itens"] = itens_delta
                observacoes = f"{observacoes} [Diferença apurada s/ Folha Mensal #{folha_mensal_ant['id']}]".strip()

        resumo = calc_result["resumo"]
        if float(resumo["salario_liquido"]) < 0:
            conn.close()
            raise FolhaValidacaoException({
                "salario_liquido": "O salário líquido não pode ser negativo. Revise os descontos lançados."
            })

        itens = calc_result["itens"]
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        situacao_destino = "rascunho" if salvar_como_rascunho else "calculada"

        inss_desc = sum(
            float(it["valor_total"]) for it in itens
            if it["tipo"] == "desconto" and (it.get("codigo_catalogo") in ("0501", "0502") or it["codigo_evento"] in ("501", "0501", "0502"))
        )
        irrf_desc = sum(
            float(it["valor_total"]) for it in itens
            if it["tipo"] == "desconto" and (it.get("codigo_catalogo") in ("0505", "0506", "0507") or it["codigo_evento"] in ("502", "0505", "0506", "0507"))
        )
        enc_pat = float((resumo.get("encargos_patronais") or {}).get("total_encargos_patronais") or round(float(resumo["base_inss"]) * 0.278, 2))

        # Transação segura
        try:
            if folha_id_existente:
                folha_id = folha_id_existente
                cursor.execute(f"""
                    UPDATE folhas_pagamento SET
                        empresa_id = {P},
                        filial_id = {P},
                        tipo_folha = {P},
                        periodo_inicio = {P},
                        periodo_fim = {P},
                        data_pagamento = {P},
                        dias_trabalhados = {P},
                        dias_mes = {P},
                        horas_mensais_divisor = {P},
                        salario_base_contratual = {P},
                        salario_base_proporcional = {P},
                        total_proventos = {P},
                        total_descontos = {P},
                        salario_liquido = {P},
                        base_inss = {P},
                        base_fgts = {P},
                        valor_fgts_informativo = {P},
                        base_irrf = {P},
                        inss_descontado = {P},
                        irrf_descontado = {P},
                        encargos_patronais = {P},
                        situacao = {P},
                        observacoes = {P},
                        parametro_id = {P},
                        atualizado_por = {P},
                        atualizado_em = {P}
                    WHERE id = {P};
                """, (
                    emp_id, fil_id, tipo_folha_norm,
                    periodo_inicio, periodo_fim, data_pagamento,
                    resumo["dias_trabalhados"], resumo["dias_mes"], resumo["divisor_horas"],
                    resumo["salario_base_contratual"], resumo["salario_base_proporcional"],
                    resumo["total_proventos"], resumo["total_descontos"], resumo["salario_liquido"],
                    resumo["base_inss"], resumo["base_fgts"], resumo["valor_fgts_informativo"],
                    resumo["base_irrf"], round(inss_desc, 2), round(irrf_desc, 2), enc_pat,
                    situacao_destino, observacoes, param_id, usuario, agora,
                    folha_id
                ))
                # Remove itens anteriores para recriar
                cursor.execute(f"DELETE FROM folha_itens WHERE folha_id = {P};", (folha_id,))

                # Auditoria
                cursor.execute(f"""
                    INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
                    VALUES ({P}, {P}, 'RECALCULO', 'Folha recalculada com novos lançamentos.', {P});
                """, (folha_id, agora, usuario))

            else:
                sql_pg = f"""
                    INSERT INTO folhas_pagamento (
                        empresa_id, filial_id, colaborador_id, competencia, tipo_folha, versao,
                        periodo_inicio, periodo_fim, data_pagamento,
                        dias_trabalhados, dias_mes, horas_mensais_divisor, salario_base_contratual,
                        salario_base_proporcional, total_proventos, total_descontos, salario_liquido,
                        base_inss, base_fgts, valor_fgts_informativo, base_irrf,
                        inss_descontado, irrf_descontado, encargos_patronais,
                        situacao, observacoes, parametro_id, criado_por, criado_em, atualizado_por, atualizado_em
                    ) VALUES (
                        {P},{P},{P},{P},{P},{P},
                        {P},{P},{P},
                        {P},{P},{P},{P},
                        {P},{P},{P},{P},
                        {P},{P},{P},{P},
                        {P},{P},{P},
                        {P},{P},{P},{P},{P},{P},{P}
                    ) RETURNING id;
                """
                sql_sqlite = f"""
                    INSERT INTO folhas_pagamento (
                        empresa_id, filial_id, colaborador_id, competencia, tipo_folha, versao,
                        periodo_inicio, periodo_fim, data_pagamento,
                        dias_trabalhados, dias_mes, horas_mensais_divisor, salario_base_contratual,
                        salario_base_proporcional, total_proventos, total_descontos, salario_liquido,
                        base_inss, base_fgts, valor_fgts_informativo, base_irrf,
                        inss_descontado, irrf_descontado, encargos_patronais,
                        situacao, observacoes, parametro_id, criado_por, criado_em, atualizado_por, atualizado_em
                    ) VALUES (
                        {P},{P},{P},{P},{P},{P},
                        {P},{P},{P},
                        {P},{P},{P},{P},
                        {P},{P},{P},{P},
                        {P},{P},{P},{P},
                        {P},{P},{P},
                        {P},{P},{P},{P},{P},{P},{P}
                    );
                """
                params_insert = (
                    emp_id, fil_id, colaborador_id, comp, tipo_folha_norm, versao,
                    periodo_inicio, periodo_fim, data_pagamento,
                    resumo["dias_trabalhados"], resumo["dias_mes"], resumo["divisor_horas"],
                    resumo["salario_base_contratual"], resumo["salario_base_proporcional"],
                    resumo["total_proventos"], resumo["total_descontos"], resumo["salario_liquido"],
                    resumo["base_inss"], resumo["base_fgts"], resumo["valor_fgts_informativo"],
                    resumo["base_irrf"], round(inss_desc, 2), round(irrf_desc, 2), enc_pat,
                    situacao_destino, observacoes, param_id, usuario, agora, usuario, agora
                )
                folha_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, params_insert)

                # Auditoria
                cursor.execute(f"""
                    INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
                    VALUES ({P}, {P}, 'CRIACAO', {P}, {P});
                """, (folha_id, agora, f"Folha ({tipo_folha_norm}) criada como '{situacao_destino}'.", usuario))

            # Inserir itens discriminados
            for it in itens:
                cursor.execute(f"""
                    INSERT INTO folha_itens (
                        folha_id, codigo_evento, descricao, tipo, referencia,
                        unidade_referencia, valor_unitario, valor_total, origem,
                        incide_inss, incide_irrf, incide_fgts,
                        memoria_calculo, criado_em
                    ) VALUES ({P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P});
                """, (
                    folha_id, it["codigo_evento"], it["descricao"], it["tipo"],
                    it["referencia"], it["unidade_referencia"], it["valor_unitario"],
                    it["valor_total"], it["origem"],
                    int(it.get("inss", 0)), int(it.get("irrf", 0)), int(it.get("fgts", 0)),
                    it["memoria_calculo"], agora
                ))

            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e

        conn.close()
        return self.obter_folha_por_id(folha_id)

    # ──────────────────────────────────────────────────────────
    # Consulta e Detalhamento da Folha
    # ──────────────────────────────────────────────────────────

    def obter_folha_por_id(self, folha_id: int) -> Dict[str, Any]:
        """Retorna a folha completa com colaborador, itens e histórico de auditoria."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT
                f.*,
                c.nome_completo as colaborador_nome,
                c.matricula as colaborador_matricula,
                c.cpf as colaborador_cpf,
                c.cargo as colaborador_cargo,
                c.setor as colaborador_setor,
                c.data_admissao as colaborador_data_admissao,
                c.situacao as colaborador_situacao,
                p.descricao as parametro_descricao
            FROM folhas_pagamento f
            JOIN colaboradores c ON c.id = f.colaborador_id
            LEFT JOIN folha_parametros p ON p.id = f.parametro_id
            WHERE f.id = {P};
        """, (folha_id,))
        folha = self._fetchone(cursor)
        if not folha:
            conn.close()
            raise FolhaNaoEncontradaException(f"Folha de pagamento #{folha_id} não encontrada.")

        # Buscar itens da folha ordenados por tipo (provento primeiro, depois desconto, depois informativo)
        cursor.execute(f"""
            SELECT * FROM folha_itens
            WHERE folha_id = {P}
            ORDER BY
                CASE tipo
                    WHEN 'provento' THEN 1
                    WHEN 'desconto' THEN 2
                    ELSE 3
                END, codigo_evento ASC;
        """, (folha_id,))
        folha["itens"] = self._fetchall(cursor)

        # Buscar histórico de auditoria
        cursor.execute(f"""
            SELECT * FROM folha_historico
            WHERE folha_id = {P}
            ORDER BY id ASC;
        """, (folha_id,))
        folha["historico"] = self._fetchall(cursor)

        # Buscar dependentes IRRF e dados da empresa/filial para o contracheque
        try:
            cursor.execute(
                f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(eh_dependente_irrf, 1) = 1;",
                (folha["colaborador_id"],)
            )
            folha["total_dependentes_irrf"] = int(cursor.fetchone()[0] or 0)
        except Exception:
            folha["total_dependentes_irrf"] = 0

        try:
            emp_id = folha.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            cursor.execute(f"SELECT razao_social, cnpj FROM empresas WHERE id = {P};", (emp_id,))
            emp = self._fetchone(cursor)
            if emp:
                folha["empresa_razao_social"] = emp.get("razao_social")
                folha["empresa_cnpj"] = emp.get("cnpj")
            cursor.execute(f"SELECT cidade, uf FROM filiais WHERE empresa_id = {P} LIMIT 1;", (emp_id,))
            fil = self._fetchone(cursor)
            if fil and fil.get("cidade"):
                folha["empresa_endereco"] = f"{fil.get('cidade')} / {fil.get('uf') or 'SP'}"
        except Exception:
            pass

        try:
            from .holerite_pdf import calcular_codigo_autenticidade, numero_recibo_folha
        except ImportError:
            from backend.holerite_pdf import calcular_codigo_autenticidade, numero_recibo_folha
        folha["numero_recibo"] = numero_recibo_folha(folha)
        folha["codigo_autenticidade"] = calcular_codigo_autenticidade(folha)

        conn.close()
        return folha

    def listar_folhas(
        self,
        competencia: Optional[str] = None,
        colaborador_id: Optional[int] = None,
        situacao: Optional[str] = None,
        setor: Optional[str] = None,
        termo: Optional[str] = None,
        tipo_folha: Optional[str] = None,
        empresa_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lista as folhas de pagamento com filtros de competência, funcionário, tipo e situação."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        sql = """
            SELECT
                f.id,
                f.empresa_id,
                f.filial_id,
                f.colaborador_id,
                f.competencia,
                COALESCE(f.tipo_folha, 'mensal') as tipo_folha,
                COALESCE(f.versao, 1) as versao,
                f.periodo_inicio,
                f.periodo_fim,
                f.data_pagamento,
                f.salario_base_contratual,
                f.salario_base_proporcional,
                f.total_proventos,
                f.total_descontos,
                f.salario_liquido,
                f.base_inss,
                f.base_fgts,
                f.valor_fgts_informativo,
                f.base_irrf,
                COALESCE(f.inss_descontado, 0.0) as inss_descontado,
                COALESCE(f.irrf_descontado, 0.0) as irrf_descontado,
                COALESCE(f.encargos_patronais, 0.0) as encargos_patronais,
                f.situacao,
                f.criado_por,
                f.criado_em,
                f.aprovado_por,
                f.aprovado_em,
                f.fechado_por,
                f.fechado_em,
                c.nome_completo as colaborador_nome,
                c.matricula as colaborador_matricula,
                c.cpf as colaborador_cpf,
                c.cargo as colaborador_cargo,
                c.setor as colaborador_setor,
                c.centro_custo as colaborador_centro_custo,
                c.tipo_contrato as colaborador_tipo_contrato
            FROM folhas_pagamento f
            JOIN colaboradores c ON c.id = f.colaborador_id
            WHERE 1=1
        """
        params = []

        if empresa_id:
            sql += f" AND (f.empresa_id = {P} OR f.empresa_id IS NULL)"
            params.append(empresa_id.strip())

        if competencia:
            sql += f" AND f.competencia = {P}"
            params.append(competencia.strip())

        if tipo_folha and tipo_folha != "todos":
            sql += f" AND COALESCE(f.tipo_folha, 'mensal') = {P}"
            params.append(tipo_folha.strip().lower())

        if colaborador_id:
            sql += f" AND f.colaborador_id = {P}"
            params.append(int(colaborador_id))

        if situacao and situacao != "todos":
            sql += f" AND f.situacao = {P}"
            params.append(situacao.strip())

        if setor:
            sql += f" AND c.setor = {P}"
            params.append(setor.strip())

        if termo:
            t = f"%{termo.strip()}%"
            sql += f" AND (c.nome_completo LIKE {P} OR c.cpf LIKE {P} OR c.matricula LIKE {P})"
            params.extend([t, t, t])

        sql += " ORDER BY f.competencia DESC, c.nome_completo ASC;"

        cursor.execute(sql, tuple(params))
        folhas = self._fetchall(cursor)
        conn.close()
        return folhas

    # ──────────────────────────────────────────────────────────
    # Fechamento e Reabertura de Folha (Auditoria e Controle)
    # ──────────────────────────────────────────────────────────

    def fechar_folha(self, folha_id: int, usuario: str = "Sistema/Administrador") -> Dict[str, Any]:
        """
        Fecha a folha de pagamento após validar vínculo, salário-base e eventos persistidos,
        impedindo modificações posteriores sem reabertura auditada.
        """
        folha = self.obter_folha_por_id(folha_id)
        if folha["situacao"] == "fechada":
            raise FolhaBloqueadaException("A folha de pagamento já se encontra fechada.")
        if float(folha.get("salario_base_contratual") or 0) <= 0:
            raise FolhaValidacaoException({"salario_base": "Não é possível fechar folha sem salário-base válido vinculado ao colaborador."})
        if not folha.get("itens"):
            raise FolhaValidacaoException({"itens": "Não é possível fechar uma folha sem eventos/itens calculados."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(f"""
            UPDATE folhas_pagamento SET
                situacao = 'fechada',
                fechado_por = {P},
                fechado_em = {P},
                atualizado_por = {P},
                atualizado_em = {P}
            WHERE id = {P};
        """, (usuario, agora, usuario, agora, folha_id))

        cursor.execute(f"""
            INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
            VALUES ({P}, {P}, 'FECHAMENTO', 'Folha fechada e homologada para pagamento.', {P});
        """, (folha_id, agora, usuario))

        conn.commit()
        conn.close()
        return self.obter_folha_por_id(folha_id)

    def reabrir_folha(
        self,
        folha_id: int,
        motivo: str,
        usuario: str = "Sistema/Administrador",
        apagar_para_relancar: bool = False,
    ) -> Dict[str, Any]:
        """
        Reabre uma folha fechada mediante registro obrigatório do motivo na auditoria.
        Se apagar_para_relancar=True, grava auditoria em auditoria_operacoes e apaga a folha
        para permitir novo lançamento do zero na mesma competência.
        """
        if not motivo or len(motivo.strip()) < 5:
            raise FolhaValidacaoException({"motivo": "Informe um motivo detalhado para reabertura da folha."})

        folha = self.obter_folha_por_id(folha_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if apagar_para_relancar:
            detalhes = (
                f"Folha #{folha_id} ({folha.get('colaborador_nome')} - {folha.get('competencia')}) "
                f"reaberta e apagada para relançamento. Motivo: {motivo.strip()}"
            )
            try:
                cursor.execute(f"""
                    INSERT INTO auditoria_operacoes (
                        empresa_id, modulo, operacao, registro_tipo, registro_id,
                        campo_alterado, valor_anterior, valor_novo, usuario_responsavel, detalhes, criado_em
                    ) VALUES ({P}, 'folha', 'REABERTURA_EXCLUSAO', 'folhas_pagamento', {P}, 'situacao', {P}, 'apagada', {P}, {P}, {P});
                """, (
                    folha.get("empresa_id") or "a0000000-0000-0000-0000-000000000001",
                    str(folha_id),
                    folha.get("situacao", "fechada"),
                    usuario,
                    detalhes,
                    agora,
                ))
            except Exception:
                pass
            cursor.execute(f"DELETE FROM folhas_pagamento WHERE id = {P};", (folha_id,))
            conn.commit()
            conn.close()
            return {
                "id": folha_id,
                "apagada": True,
                "colaborador_id": folha["colaborador_id"],
                "competencia": folha["competencia"],
                "motivo": motivo.strip(),
            }

        cursor.execute(f"""
            UPDATE folhas_pagamento SET
                situacao = 'calculada',
                atualizado_por = {P},
                atualizado_em = {P}
            WHERE id = {P};
        """, (usuario, agora, folha_id))

        desc = f"Folha reaberta pelo operador. Motivo informado: {motivo.strip()}"
        cursor.execute(f"""
            INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
            VALUES ({P}, {P}, 'REABERTURA', {P}, {P});
        """, (folha_id, agora, desc, usuario))

        conn.commit()
        conn.close()
        return self.obter_folha_por_id(folha_id)

    def cancelar_folha(self, folha_id: int, usuario: str = "Sistema/Administrador") -> bool:
        """Exclui ou cancela folha se não estiver fechada."""
        folha = self.obter_folha_por_id(folha_id)
        if folha["situacao"] == "fechada":
            raise FolhaBloqueadaException("Folhas já fechadas não podem ser canceladas sem reabertura prévia.")

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(f"DELETE FROM folhas_pagamento WHERE id = {P};", (folha_id,))
        conn.commit()
        conn.close()
        return True

    def aprovar_folha(self, folha_id: int, usuario: str = "Sistema/Administrador") -> Dict[str, Any]:
        """Aprova uma folha calculada antes do fechamento definitivo."""
        folha = self.obter_folha_por_id(folha_id)
        if folha["situacao"] == "fechada":
            raise FolhaBloqueadaException("A folha já está fechada.")
        if folha["situacao"] == "rascunho":
            raise FolhaValidacaoException({"situacao": "Calcule a folha antes de aprová-la."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(f"""
            UPDATE folhas_pagamento SET
                situacao = 'aprovada',
                aprovado_por = {P},
                aprovado_em = {P},
                atualizado_por = {P},
                atualizado_em = {P}
            WHERE id = {P};
        """, (usuario, agora, usuario, agora, folha_id))
        cursor.execute(f"""
            INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
            VALUES ({P}, {P}, 'APROVACAO', 'Folha conferida e aprovada para fechamento.', {P});
        """, (folha_id, agora, usuario))
        conn.commit()
        conn.close()
        return self.obter_folha_por_id(folha_id)

    def processar_lote(
        self,
        competencia: str,
        periodo_inicio: str,
        periodo_fim: str,
        data_pagamento: Optional[str] = None,
        tipo_folha: str = "mensal",
        empresa_id: Optional[str] = None,
        filial_id: Optional[str] = None,
        colaboradores_ids: Optional[List[int]] = None,
        dias_trabalhados: float = 30.0,
        dias_mes: int = 30,
        horas_divisor: float = 220.0,
        usuario: str = "Sistema/Administrador",
    ) -> Dict[str, Any]:
        """Processa a folha de pagamento em lote para todos os colaboradores ativos ou selecionados."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT situacao FROM fechamentos_ponto WHERE competencia = {P} ORDER BY id DESC LIMIT 1;", (competencia.strip(),))
        row_fp = cursor.fetchone()
        ponto_fechado = bool(row_fp and str(row_fp[0] or "").lower() == "fechado")

        sql = "SELECT id, nome_completo, matricula, carga_horaria_mensal FROM colaboradores WHERE situacao = 'ativo'"
        params = []
        if empresa_id:
            sql += f" AND (empresa_id = {P} OR empresa_id IS NULL)"
            params.append(empresa_id.strip())
        if filial_id:
            sql += f" AND (filial_id = {P} OR filial_id IS NULL)"
            params.append(filial_id.strip())
        cursor.execute(sql, tuple(params))
        alvos = self._fetchall(cursor)
        conn.close()

        if colaboradores_ids:
            ids_set = {int(x) for x in colaboradores_ids}
            alvos = [c for c in alvos if int(c["id"]) in ids_set]

        processadas = []
        ignoradas = []
        erros = []
        for colab in alvos:
            cid = int(colab["id"])
            divisor_colab = float(colab.get("carga_horaria_mensal") or horas_divisor or 220.0)
            try:
                f = self.criar_ou_atualizar_folha(
                    colaborador_id=cid,
                    competencia=competencia,
                    periodo_inicio=periodo_inicio,
                    periodo_fim=periodo_fim,
                    data_pagamento=data_pagamento,
                    dias_trabalhados=dias_trabalhados,
                    dias_mes=dias_mes,
                    horas_divisor=divisor_colab,
                    eventos=[],
                    observacoes=f"Processamento em lote ({tipo_folha})",
                    usuario=usuario,
                    tipo_folha=tipo_folha,
                    empresa_id=empresa_id,
                    filial_id=filial_id,
                    integrar_ponto=ponto_fechado,
                )
                processadas.append(f)
            except FolhaValidacaoException as exc:
                ignoradas.append({"colaborador_id": cid, "nome": colab["nome_completo"], "motivo": str(exc.erros)})
            except Exception as exc:
                erros.append({"colaborador_id": cid, "nome": colab["nome_completo"], "erro": str(exc)})

        return {
            "competencia": competencia,
            "tipo_folha": tipo_folha,
            "total_alvos": len(alvos),
            "processadas": len(processadas),
            "ignoradas": len(ignoradas),
            "erros": len(erros),
            "folhas": processadas,
            "detalhes_ignoradas": ignoradas,
            "detalhes_erros": erros,
        }

    # ──────────────────────────────────────────────────────────
    # Catálogo Parametrizável de Rubricas
    # ──────────────────────────────────────────────────────────

    def listar_rubricas(
        self,
        empresa_id: Optional[str] = None,
        tipo: Optional[str] = None,
        apenas_ativas: bool = False,
        termo: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lista rubricas parametrizadas do catálogo no banco."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = "SELECT * FROM folha_rubricas WHERE 1=1"
        params = []
        if empresa_id:
            sql += f" AND (empresa_id = {P} OR empresa_id = 'a0000000-0000-0000-0000-000000000001')"
            params.append(empresa_id.strip())
        if tipo and tipo != "todos":
            sql += f" AND tipo = {P}"
            params.append(tipo.strip().lower())
        if apenas_ativas:
            sql += " AND ativo = 1"
        if termo:
            t = f"%{termo.strip()}%"
            sql += f" AND (codigo LIKE {P} OR LOWER(descricao) LIKE LOWER({P}))"
            params.extend([t, t])
        sql += " ORDER BY codigo ASC;"
        cursor.execute(sql, tuple(params))
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def salvar_rubrica(self, dados: Dict[str, Any], usuario: str = "Sistema/Administrador", rubrica_id: Optional[int] = None) -> Dict[str, Any]:
        """Cria ou edita uma rubrica parametrizável, protegendo incidências de rubricas legais."""
        codigo = str(dados.get("codigo") or "").strip().upper()
        descricao = str(dados.get("descricao") or "").strip()
        tipo = str(dados.get("tipo") or "provento").strip().lower()
        if not codigo or not descricao:
            raise FolhaValidacaoException({"codigo": "Código e descrição da rubrica são obrigatórios."})
        if tipo not in ("provento", "desconto", "informativo"):
            raise FolhaValidacaoException({"tipo": "Tipo inválido. Use 'provento', 'desconto' ou 'informativo'."})

        empresa_id = str(dados.get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        inc_inss = 1 if dados.get("incide_inss") in (1, True, "1", "true") else 0
        inc_irrf = 1 if dados.get("incide_irrf") in (1, True, "1", "true") else 0
        inc_fgts = 1 if dados.get("incide_fgts") in (1, True, "1", "true") else 0
        inc_outras = 1 if dados.get("incide_outras_bases") in (1, True, "1", "true") else 0
        ref_ferias = 1 if dados.get("reflexo_ferias") in (1, True, "1", "true") else 0
        ref_13 = 1 if dados.get("reflexo_13") in (1, True, "1", "true") else 0
        ativo = 1 if dados.get("ativo", 1) in (1, True, "1", "true") else 0

        if rubrica_id:
            cursor.execute(f"SELECT * FROM folha_rubricas WHERE id = {P};", (rubrica_id,))
            atual = self._fetchone(cursor)
            if not atual:
                conn.close()
                raise FolhaNaoEncontradaException(f"Rubrica #{rubrica_id} não encontrada.")
            if int(atual.get("sistema_legal") or 0) == 1:
                if (
                    inc_inss != int(atual.get("incide_inss", 0))
                    or inc_irrf != int(atual.get("incide_irrf", 0))
                    or inc_fgts != int(atual.get("incide_fgts", 0))
                    or tipo != atual.get("tipo")
                ):
                    conn.close()
                    raise FolhaBloqueadaException(
                        f"Rubrica legal '{atual['codigo']} - {atual['descricao']}' protegida: incidências legais não podem ser alteradas."
                    )
            cursor.execute(f"""
                UPDATE folha_rubricas SET
                    descricao={P}, tipo={P}, categoria={P}, natureza={P}, forma_calculo={P},
                    valor_padrao={P}, referencia_padrao={P}, incide_inss={P}, incide_irrf={P},
                    incide_fgts={P}, incide_outras_bases={P}, reflexo_ferias={P}, reflexo_13={P},
                    vigencia_inicio={P}, vigencia_fim={P}, ativo={P}, observacao={P}, atualizado_em={P}
                WHERE id={P};
            """, (
                descricao, tipo, dados.get("categoria", atual.get("categoria", "Proventos")),
                dados.get("natureza", "salarial"), dados.get("forma_calculo", "valor_fixo"),
                float(dados.get("valor_padrao", 0.0) or 0.0), float(dados.get("referencia_padrao", 0.0) or 0.0),
                inc_inss, inc_irrf, inc_fgts, inc_outras, ref_ferias, ref_13,
                dados.get("vigencia_inicio", "2026-01-01"), dados.get("vigencia_fim") or None,
                ativo, dados.get("observacao", ""), agora, rubrica_id
            ))
            target_id = rubrica_id
        else:
            cursor.execute(f"SELECT id FROM folha_rubricas WHERE empresa_id = {P} AND codigo = {P};", (empresa_id, codigo))
            if cursor.fetchone():
                conn.close()
                raise FolhaValidacaoException({"codigo": f"Já existe uma rubrica com o código '{codigo}'."})
            sql_pg = f"""
                INSERT INTO folha_rubricas (
                    empresa_id, codigo, descricao, tipo, categoria, natureza, forma_calculo,
                    valor_padrao, referencia_padrao, incide_inss, incide_irrf, incide_fgts,
                    incide_outras_bases, reflexo_ferias, reflexo_13, vigencia_inicio, vigencia_fim,
                    ativo, sistema_legal, observacao, criado_em, atualizado_em
                ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},0,{P},{P},{P})
                RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO folha_rubricas (
                    empresa_id, codigo, descricao, tipo, categoria, natureza, forma_calculo,
                    valor_padrao, referencia_padrao, incide_inss, incide_irrf, incide_fgts,
                    incide_outras_bases, reflexo_ferias, reflexo_13, vigencia_inicio, vigencia_fim,
                    ativo, sistema_legal, observacao, criado_em, atualizado_em
                ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},0,{P},{P},{P});
            """
            target_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
                empresa_id, codigo, descricao, tipo, dados.get("categoria", "Proventos" if tipo == "provento" else "Descontos"),
                dados.get("natureza", "salarial"), dados.get("forma_calculo", "valor_fixo"),
                float(dados.get("valor_padrao", 0.0) or 0.0), float(dados.get("referencia_padrao", 0.0) or 0.0),
                inc_inss, inc_irrf, inc_fgts, inc_outras, ref_ferias, ref_13,
                dados.get("vigencia_inicio", "2026-01-01"), dados.get("vigencia_fim") or None,
                ativo, dados.get("observacao", ""), agora, agora
            ))

        conn.commit()
        cursor.execute(f"SELECT * FROM folha_rubricas WHERE id = {P};", (target_id,))
        salva = self._fetchone(cursor)
        conn.close()
        return salva

    def alterar_status_rubrica(self, rubrica_id: int, ativo: bool) -> Dict[str, Any]:
        """Ativa ou inativa uma rubrica (impede inativar rubricas legais essenciais)."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM folha_rubricas WHERE id = {P};", (rubrica_id,))
        atual = self._fetchone(cursor)
        if not atual:
            conn.close()
            raise FolhaNaoEncontradaException(f"Rubrica #{rubrica_id} não encontrada.")
        if not ativo and atual["codigo"] in ("0001", "0501", "0505", "0904"):
            conn.close()
            raise FolhaBloqueadaException(f"Rubrica legal essencial '{atual['codigo']}' não pode ser inativada.")
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(f"UPDATE folha_rubricas SET ativo = {P}, atualizado_em = {P} WHERE id = {P};", (1 if ativo else 0, agora, rubrica_id))
        conn.commit()
        cursor.execute(f"SELECT * FROM folha_rubricas WHERE id = {P};", (rubrica_id,))
        res = self._fetchone(cursor)
        conn.close()
        return res

    # ──────────────────────────────────────────────────────────
    # Relatórios Gerenciais, Financeiros e Dashboard da Folha
    # ──────────────────────────────────────────────────────────

    def obter_relatorios_folha(
        self,
        competencia: Optional[str] = None,
        empresa_id: Optional[str] = None,
        filial_id: Optional[str] = None,
        setor: Optional[str] = None,
        colaborador_id: Optional[int] = None,
        competencia_inicio: Optional[str] = None,
        competencia_fim: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Consolida indicadores reais da folha para Dashboard, Relatórios Gerenciais e Financeiros."""
        folhas = self.listar_folhas(
            competencia=competencia,
            colaborador_id=colaborador_id,
            setor=setor,
            empresa_id=empresa_id,
        )
        if filial_id:
            folhas = [f for f in folhas if (f.get("filial_id") or "") == filial_id]
        if competencia_inicio:
            ci = competencia_inicio.strip()
            folhas = [f for f in folhas if (f.get("competencia") or "") >= ci]
        if competencia_fim:
            cf = competencia_fim.strip()
            folhas = [f for f in folhas if (f.get("competencia") or "") <= cf]

        total_bruto = round(sum(float(f.get("total_proventos") or 0) for f in folhas), 2)
        total_descontos = round(sum(float(f.get("total_descontos") or 0) for f in folhas), 2)
        total_liquido = round(sum(float(f.get("salario_liquido") or 0) for f in folhas), 2)
        total_inss = round(sum(float(f.get("inss_descontado") or 0) for f in folhas), 2)
        total_irrf = round(sum(float(f.get("irrf_descontado") or 0) for f in folhas), 2)
        total_fgts = round(sum(float(f.get("valor_fgts_informativo") or 0) for f in folhas), 2)
        total_encargos = round(sum(float(f.get("encargos_patronais") or 0) for f in folhas), 2)
        total_base_inss = round(sum(float(f.get("base_inss") or 0) for f in folhas), 2)
        custo_total = round(total_bruto + total_fgts + total_encargos, 2)

        abertas = sum(1 for f in folhas if f.get("situacao") != "fechada")
        fechadas = sum(1 for f in folhas if f.get("situacao") == "fechada")
        colabs_unicos = len({f.get("colaborador_id") for f in folhas})

        def _agrupar(chave: str, padrao: str) -> List[Dict[str, Any]]:
            grupos: Dict[str, Dict[str, Any]] = {}
            for f in folhas:
                nome_g = (f.get(chave) or padrao).strip() or padrao
                g = grupos.setdefault(nome_g, {
                    "grupo": nome_g, "qtd_folhas": 0, "bruto": 0.0,
                    "descontos": 0.0, "liquido": 0.0, "fgts": 0.0, "encargos": 0.0, "custo_total": 0.0
                })
                bruto_f = float(f.get("total_proventos") or 0)
                fgts_f = float(f.get("valor_fgts_informativo") or 0)
                enc_f = float(f.get("encargos_patronais") or 0)
                g["qtd_folhas"] += 1
                g["bruto"] = round(g["bruto"] + bruto_f, 2)
                g["descontos"] = round(g["descontos"] + float(f.get("total_descontos") or 0), 2)
                g["liquido"] = round(g["liquido"] + float(f.get("salario_liquido") or 0), 2)
                g["fgts"] = round(g["fgts"] + fgts_f, 2)
                g["encargos"] = round(g["encargos"] + enc_f, 2)
                g["custo_total"] = round(g["custo_total"] + bruto_f + fgts_f + enc_f, 2)
            return sorted(grupos.values(), key=lambda x: x["custo_total"], reverse=True)

        # Colaboradores ativos e salário médio
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql_col = "SELECT COUNT(*), COALESCE(AVG(salario_base), 0) FROM colaboradores WHERE situacao = 'ativo'"
        p_col: List[Any] = []
        if empresa_id:
            sql_col += f" AND (empresa_id = {P} OR empresa_id IS NULL)"
            p_col.append(empresa_id.strip())
        if setor:
            sql_col += f" AND setor = {P}"
            p_col.append(setor.strip())
        cursor.execute(sql_col, tuple(p_col))
        row_col = cursor.fetchone()
        num_colabs_ativos = int(row_col[0] or 0)
        sal_medio_cadastro = round(float(row_col[1] or 0.0), 2)

        # Itens das folhas filtradas para eventos mais usados e horas extras
        eventos_map: Dict[tuple, Dict[str, Any]] = {}
        he_qtd = 0
        he_horas = 0.0
        he_valor = 0.0
        folha_ids = [int(f["id"]) for f in folhas]
        if folha_ids:
            placeholders = ",".join([P] * len(folha_ids))
            cursor.execute(
                f"SELECT codigo_evento, descricao, tipo, referencia, valor_total FROM folha_itens WHERE folha_id IN ({placeholders});",
                tuple(folha_ids),
            )
            for it in self._fetchall(cursor):
                cod = str(it.get("codigo_evento") or "")
                tipo_it = str(it.get("tipo") or "")
                val_it = float(it.get("valor_total") or 0.0)
                ref_it = float(it.get("referencia") or 0.0)
                if cod in ("0010", "0011", "101", "102"):
                    he_qtd += 1
                    he_horas = round(he_horas + ref_it, 2)
                    he_valor = round(he_valor + val_it, 2)
                if tipo_it != "informativo" and cod not in ("001", "0001"):
                    chave_ev = (cod, it.get("descricao") or cod, tipo_it)
                    agg = eventos_map.setdefault(chave_ev, {
                        "codigo": cod,
                        "descricao": it.get("descricao") or cod,
                        "tipo": tipo_it,
                        "qtd_lancamentos": 0,
                        "valor_total": 0.0,
                    })
                    agg["qtd_lancamentos"] += 1
                    agg["valor_total"] = round(agg["valor_total"] + val_it, 2)
        conn.close()

        eventos_mais_usados = sorted(
            eventos_map.values(),
            key=lambda x: (-x["qtd_lancamentos"], -x["valor_total"], x["codigo"]),
        )

        sal_medio = (
            round(sum(float(f.get("salario_base_contratual") or 0) for f in folhas) / len(folhas), 2)
            if folhas else sal_medio_cadastro
        )

        folhas_nao_fechadas = [
            {
                "id": f["id"],
                "colaborador_nome": f.get("colaborador_nome"),
                "matricula": f.get("colaborador_matricula"),
                "competencia": f.get("competencia"),
                "tipo_folha": f.get("tipo_folha", "mensal"),
                "situacao": f.get("situacao"),
                "salario_liquido": float(f.get("salario_liquido") or 0.0),
            }
            for f in folhas if f.get("situacao") != "fechada"
        ]

        # Totais por mês para o relatório financeiro (com filtros aplicados)
        totais_mes_map: Dict[str, Dict[str, Any]] = {}
        for f in folhas:
            c_mes = f.get("competencia") or "N/D"
            tm = totais_mes_map.setdefault(c_mes, {
                "competencia": c_mes, "qtd": 0, "bruto": 0.0, "descontos": 0.0, "liquido": 0.0,
                "inss_segurados": 0.0, "irrf": 0.0, "fgts": 0.0, "encargos_empresa": 0.0, "custo_total": 0.0,
            })
            br = float(f.get("total_proventos") or 0)
            fg = float(f.get("valor_fgts_informativo") or 0)
            en = float(f.get("encargos_patronais") or 0)
            tm["qtd"] += 1
            tm["bruto"] = round(tm["bruto"] + br, 2)
            tm["descontos"] = round(tm["descontos"] + float(f.get("total_descontos") or 0), 2)
            tm["liquido"] = round(tm["liquido"] + float(f.get("salario_liquido") or 0), 2)
            tm["inss_segurados"] = round(tm["inss_segurados"] + float(f.get("inss_descontado") or 0), 2)
            tm["irrf"] = round(tm["irrf"] + float(f.get("irrf_descontado") or 0), 2)
            tm["fgts"] = round(tm["fgts"] + fg, 2)
            tm["encargos_empresa"] = round(tm["encargos_empresa"] + en, 2)
            tm["custo_total"] = round(tm["custo_total"] + br + fg + en, 2)
        totais_por_mes = [totais_mes_map[k] for k in sorted(totais_mes_map.keys())]

        inss_pat_20 = round(total_base_inss * 0.20, 2)
        rat_fap_2 = round(total_base_inss * 0.02, 2)
        terceiros_5_8 = round(total_base_inss * 0.058, 2)
        inss_pat_e_terc = round(inss_pat_20 + rat_fap_2 + terceiros_5_8, 2)
        total_encargos_empresa = round(inss_pat_e_terc + total_fgts, 2)
        inss_total_recolher = round(total_inss + inss_pat_e_terc, 2)
        total_a_recolher = round(inss_total_recolher + total_irrf + total_fgts, 2)

        # Evolução mensal histórica (sem filtro de competência para visão comparativa)
        todas_folhas = self.listar_folhas(empresa_id=empresa_id, setor=setor, colaborador_id=colaborador_id)
        evolucao_map: Dict[str, Dict[str, Any]] = {}
        for f in todas_folhas:
            comp = f.get("competencia") or "N/D"
            ev = evolucao_map.setdefault(comp, {
                "competencia": comp, "qtd": 0, "bruto": 0.0, "descontos": 0.0, "liquido": 0.0, "custo_total": 0.0
            })
            br = float(f.get("total_proventos") or 0)
            fg = float(f.get("valor_fgts_informativo") or 0)
            en = float(f.get("encargos_patronais") or 0)
            ev["qtd"] += 1
            ev["bruto"] = round(ev["bruto"] + br, 2)
            ev["descontos"] = round(ev["descontos"] + float(f.get("total_descontos") or 0), 2)
            ev["liquido"] = round(ev["liquido"] + float(f.get("salario_liquido") or 0), 2)
            ev["custo_total"] = round(ev["custo_total"] + br + fg + en, 2)
        evolucao_mensal = [evolucao_map[k] for k in sorted(evolucao_map.keys())]

        por_dept = _agrupar("colaborador_setor", "Não informado")

        return {
            "filtros": {
                "competencia": competencia,
                "competencia_inicio": competencia_inicio,
                "competencia_fim": competencia_fim,
                "empresa_id": empresa_id,
                "filial_id": filial_id,
                "setor": setor,
                "colaborador_id": colaborador_id,
            },
            "resumo_financeiro": {
                "qtd_colaboradores": colabs_unicos,
                "qtd_folhas": len(folhas),
                "folhas_abertas": abertas,
                "folhas_fechadas": fechadas,
                "total_bruto": total_bruto,
                "total_descontos": total_descontos,
                "total_liquido": total_liquido,
                "total_inss": total_inss,
                "total_irrf": total_irrf,
                "total_fgts": total_fgts,
                "encargos_patronais": total_encargos,
                "custo_total_empresa": custo_total,
            },
            "gerencial": {
                "numero_colaboradores_ativos": num_colabs_ativos,
                "numero_colaboradores_folha": colabs_unicos,
                "salario_medio": sal_medio,
                "custo_por_departamento": por_dept,
                "eventos_mais_usados": eventos_mais_usados,
                "horas_extras": {
                    "qtd_lancamentos": he_qtd,
                    "total_horas": he_horas,
                    "valor_total": he_valor,
                },
                "folhas_nao_fechadas": {
                    "quantidade": len(folhas_nao_fechadas),
                    "lista": folhas_nao_fechadas,
                },
            },
            "financeiro": {
                "totais_por_mes": totais_por_mes,
                "encargos_empresa": {
                    "inss_patronal_20": inss_pat_20,
                    "rat_fap_2": rat_fap_2,
                    "terceiros_5_8": terceiros_5_8,
                    "fgts_deposito": total_fgts,
                    "total_encargos_empresa": total_encargos_empresa,
                },
                "valores_a_recolher": {
                    "inss_segurados": total_inss,
                    "inss_patronal_e_terceiros": inss_pat_e_terc,
                    "inss_total_recolher": inss_total_recolher,
                    "irrf_recolher": total_irrf,
                    "fgts_recolher": total_fgts,
                    "total_a_recolher": total_a_recolher,
                },
            },
            "por_departamento": por_dept,
            "por_centro_custo": _agrupar("colaborador_centro_custo", "Sem centro de custo"),
            "por_cargo": _agrupar("colaborador_cargo", "Não informado"),
            "evolucao_mensal": evolucao_mensal,
            "folhas": folhas,
        }

    # ──────────────────────────────────────────────────────────
    # MÓDULO 09B: 13º Salário Completo (RF-089 a RF-093)
    # ──────────────────────────────────────────────────────────

    def _contar_avos_decimo_terceiro(self, cursor, colab: Dict[str, Any], ano_base: int) -> int:
        """Apura avos (1..12) considerando admissão e afastamentos INSS/suspensão (>=15d trabalhados no mês)."""
        P = self._ph()
        cid = int(colab["id"])
        dt_adm_str = str(colab.get("data_admissao") or f"{ano_base}-01-01")[:10]
        dt_adm = datetime.strptime(dt_adm_str, "%Y-%m-%d").date()

        cursor.execute(
            f"""
            SELECT dias_empresa, dias_inss, regime_efeito, data_inicio, data_fim_prevista, data_retorno_efetivo
            FROM afastamentos
            WHERE colaborador_id = {P}
              AND (dias_inss > 0 OR regime_efeito = 'suspensao')
              AND data_inicio <= {P}
              AND COALESCE(data_retorno_efetivo, data_fim_prevista) >= {P};
        """,
            (cid, f"{ano_base}-12-31", f"{ano_base}-01-01"),
        )
        afasts = self._fetchall(cursor)

        avos = 0
        for mes in range(1, 13):
            ult = calendar.monthrange(ano_base, mes)[1]
            m_ini = date(ano_base, mes, 1)
            m_fim = date(ano_base, mes, ult)
            if dt_adm > m_fim:
                continue
            inicio_ef = max(m_ini, dt_adm)
            dias_no_mes = (m_fim - inicio_ef).days + 1
            dias_nao_trab = 0
            for af in afasts:
                af_i = datetime.strptime(str(af["data_inicio"])[:10], "%Y-%m-%d").date()
                af_f = datetime.strptime(str(af.get("data_retorno_efetivo") or af["data_fim_prevista"])[:10], "%Y-%m-%d").date()
                d_emp = int(af.get("dias_empresa") or 0)
                unpaid_i = af_i if (str(af.get("regime_efeito") or "") == "suspensao" and d_emp == 0) else (af_i + timedelta(days=d_emp))
                ov_i = max(inicio_ef, unpaid_i)
                ov_f = min(m_fim, af_f)
                if ov_f >= ov_i:
                    dias_nao_trab += (ov_f - ov_i).days + 1
            if max(0, dias_no_mes - dias_nao_trab) >= 15:
                avos += 1
        return avos

    def _media_variaveis_anual_13(self, cursor, colaborador_id: int, ano_base: int, avos: int) -> Decimal:
        """Apura média de verbas variáveis (HE, noturno, comissões, adicionais) do exercício."""
        P = self._ph()
        cursor.execute(
            f"""
            SELECT COALESCE(SUM(fi.valor_total), 0)
            FROM folhas_pagamento f
            JOIN folha_itens fi ON fi.folha_id = f.id
            WHERE f.colaborador_id = {P}
              AND f.competencia LIKE {P}
              AND fi.tipo = 'provento'
              AND COALESCE(f.tipo_folha, 'mensal') IN ('mensal', 'complementar')
              AND fi.codigo_evento NOT IN ('0001', '0002', '0100', '0101', '0102', '0103', '0110', '0111', '0112', '0113');
        """,
            (int(colaborador_id), f"{int(ano_base)}-%"),
        )
        soma = Decimal(str(cursor.fetchone()[0] or 0.0))
        divisor = Decimal(str(max(1, min(12, avos))))
        return arredondar_moeda(soma / divisor)

    def calcular_decimo_terceiro_colaborador(
        self,
        colaborador_id: int,
        ano_base: int,
        parcela: int = 1,
        data_pagamento: Optional[str] = None,
        usuario: str = "DP",
        salvar: bool = True,
    ) -> Dict[str, Any]:
        """RF-089..RF-093: Calcula e persiste 1ª ou 2ª parcela do 13º salário com avos, médias, férias e INSS/IRRF exclusivos."""
        parc = int(parcela or 1)
        if parc not in (1, 2):
            raise FolhaValidacaoException({"parcela": "Parcela de 13º deve ser 1 ou 2."})
        ano_i = int(ano_base)
        colab = self.obter_dados_colaborador(colaborador_id)
        sal = Decimal(str(colab.get("salario_base") or 0.0))
        if sal <= Decimal("0.00"):
            raise FolhaValidacaoException({"salario_base": "Colaborador sem salário-base válido."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        try:
            avos = self._contar_avos_decimo_terceiro(cursor, colab, ano_i)
            media_vars = self._media_variaveis_anual_13(cursor, int(colaborador_id), ano_i, avos)
            rem_total = arredondar_moeda(sal + media_vars)
            bruto_integral = arredondar_moeda((rem_total * Decimal(str(avos))) / Decimal("12"))
            dt_pg = str(data_pagamento or (f"{ano_i}-11-30" if parc == 1 else f"{ano_i}-12-20"))[:10]

            # Adiantamento de 13º eventualmente pago junto às férias
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(valor_adiantamento_13), 0) FROM ferias_programadas
                WHERE colaborador_id = {P} AND adiantar_decimo = 1
                  AND COALESCE(status, 'solicitada') != 'cancelada' AND data_inicio LIKE {P};
            """,
                (int(colaborador_id), f"{ano_i}-%"),
            )
            adiant_ferias = Decimal(str(cursor.fetchone()[0] or 0.0))

            aliq_fgts = Decimal("0.02") if str(colab.get("tipo_contrato") or "").lower() == "aprendiz" else Decimal("0.08")

            if parc == 1:
                valor_bruto = arredondar_moeda(bruto_integral * Decimal("0.50"))
                desc_1a = Decimal("0.00")
                inss_13 = Decimal("0.00")
                irrf_13 = Decimal("0.00")
                valor_liq = max(Decimal("0.00"), arredondar_moeda(valor_bruto - adiant_ferias))
                fgts_inf = arredondar_moeda(valor_liq * aliq_fgts)
            else:
                cursor.execute(
                    f"SELECT COALESCE(SUM(valor_liquido), 0) FROM decimo_terceiro WHERE colaborador_id = {P} AND ano_base = {P} AND parcela = 1;",
                    (int(colaborador_id), ano_i),
                )
                ja_pago_1a = Decimal(str(cursor.fetchone()[0] or 0.0))
                desc_1a = arredondar_moeda(ja_pago_1a + adiant_ferias)
                valor_bruto = bruto_integral

                try:
                    from .tabelas_legais_service import TabelasLegaisService
                except ImportError:
                    from backend.tabelas_legais_service import TabelasLegaisService
                tab_vig = TabelasLegaisService(db_path=self.db_path).obter_tabela_vigente(f"{ano_i}-12")
                dep_irrf = int(colab.get("total_dependentes_irrf", colab.get("total_dependentes", 0)))
                inss_13, _, _, _ = calcular_inss_progressivo(
                    bruto_integral,
                    tabela_faixas=tab_vig["tabela_inss_tuples"],
                    teto_maximo=Decimal(str(tab_vig["teto_inss"])),
                    teto_contribuicao=Decimal(str(tab_vig["teto_contribuicao_inss"])),
                )
                irrf_13, _, _ = calcular_irrf_progressivo(
                    base_bruta_irrf=bruto_integral,
                    desconto_inss=inss_13,
                    numero_dependentes=dep_irrf,
                    deducao_por_dependente=Decimal(str(tab_vig["deducao_dependente_irrf"])),
                    tabela_faixas=tab_vig["tabela_irrf_tuples"],
                    desconto_simplificado=Decimal(str(tab_vig["desconto_simplificado_irrf"])),
                    aplicar_reducao_lei_15270=bool(tab_vig.get("lei_15270_ativa", 1)),
                )
                valor_liq = max(Decimal("0.00"), arredondar_moeda(bruto_integral - desc_1a - inss_13 - irrf_13))
                fgts_inf = arredondar_moeda(max(Decimal("0.00"), bruto_integral - desc_1a) * aliq_fgts)

            rec_id = None
            if salvar:
                agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    f"DELETE FROM decimo_terceiro WHERE colaborador_id = {P} AND ano_base = {P} AND parcela = {P};",
                    (int(colaborador_id), ano_i, parc),
                )
                sql_pg = f"""
                    INSERT INTO decimo_terceiro (
                        colaborador_id, ano_base, parcela, meses_trabalhados, salario_base, media_variaveis,
                        remuneracao_total, valor_bruto, desconto_primeira_parcela, desconto_inss, desconto_irrf,
                        valor_liquido, fgts_informativo, data_pagamento, situacao, criado_por, criado_em
                    ) VALUES ({','.join([P]*17)}) RETURNING id;
                """
                sql_sq = f"""
                    INSERT INTO decimo_terceiro (
                        colaborador_id, ano_base, parcela, meses_trabalhados, salario_base, media_variaveis,
                        remuneracao_total, valor_bruto, desconto_primeira_parcela, desconto_inss, desconto_irrf,
                        valor_liquido, fgts_informativo, data_pagamento, situacao, criado_por, criado_em
                    ) VALUES ({','.join([P]*17)});
                """
                rec_id = self._insert_id(
                    cursor, conn, sql_pg, sql_sq,
                    (
                        int(colaborador_id), ano_i, parc, avos, float(sal), float(media_vars),
                        float(rem_total), float(valor_bruto), float(desc_1a), float(inss_13), float(irrf_13),
                        float(valor_liq), float(fgts_inf), dt_pg, "calculado", usuario, agora,
                    ),
                )
                conn.commit()

            return {
                "id": rec_id,
                "colaborador_id": int(colaborador_id),
                "colaborador_nome": colab["nome_completo"],
                "ano_base": ano_i,
                "parcela": parc,
                "avos": avos,
                "salario_base": float(sal),
                "media_variaveis": float(media_vars),
                "remuneracao_total": float(rem_total),
                "valor_bruto": float(valor_bruto),
                "desconto_primeira_parcela": float(desc_1a),
                "adiantamento_ferias_deduzido": float(adiant_ferias),
                "desconto_inss": float(inss_13),
                "desconto_irrf": float(irrf_13),
                "valor_liquido": float(valor_liq),
                "fgts_informativo": float(fgts_inf),
                "data_pagamento": dt_pg,
            }
        finally:
            conn.close()

    def calcular_decimo_terceiro_lote(
        self,
        ano_base: int,
        parcela: int = 1,
        empresa_id: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = "SELECT id FROM colaboradores WHERE situacao = 'ativo'"
        params: List[Any] = []
        if empresa_id:
            sql += f" AND COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {P}"
            params.append(empresa_id.strip())
        cursor.execute(sql, tuple(params))
        cids = [int(r[0]) for r in cursor.fetchall()]
        conn.close()

        itens = []
        erros = []
        for cid in cids:
            try:
                itens.append(self.calcular_decimo_terceiro_colaborador(cid, ano_base, parcela=parcela, usuario=usuario))
            except Exception as exc:
                erros.append({"colaborador_id": cid, "erro": str(exc)})
        return {
            "ano_base": int(ano_base),
            "parcela": int(parcela),
            "total_processados": len(itens),
            "total_liquido": round(sum(i["valor_liquido"] for i in itens), 2),
            "total_fgts": round(sum(i["fgts_informativo"] for i in itens), 2),
            "itens": itens,
            "erros": erros,
        }

    def listar_decimo_terceiro(
        self,
        ano_base: Optional[int] = None,
        colaborador_id: Optional[int] = None,
        empresa_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = """
            SELECT d.*, c.nome_completo, c.matricula, c.setor
            FROM decimo_terceiro d
            JOIN colaboradores c ON c.id = d.colaborador_id
            WHERE 1=1
        """
        params: List[Any] = []
        if ano_base:
            sql += f" AND d.ano_base = {P}"
            params.append(int(ano_base))
        if colaborador_id:
            sql += f" AND d.colaborador_id = {P}"
            params.append(int(colaborador_id))
        if empresa_id:
            sql += f" AND COALESCE(c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {P}"
            params.append(empresa_id.strip())
        sql += " ORDER BY d.ano_base DESC, d.parcela ASC, c.nome_completo ASC;"
        cursor.execute(sql, tuple(params))
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def calcular_provisao_decimo_terceiro(self, competencia: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        """RF-093: Provisão mensal contábil de 1/12 de 13º salário + FGTS + encargos patronais."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = "SELECT id, nome_completo, matricula, setor, centro_custo, salario_base FROM colaboradores WHERE situacao = 'ativo'"
        params: List[Any] = []
        if empresa_id:
            sql += f" AND COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {P}"
            params.append(empresa_id.strip())
        cursor.execute(sql, tuple(params))
        colabs = self._fetchall(cursor)
        conn.close()

        itens = []
        for c in colabs:
            sal = Decimal(str(c.get("salario_base") or 0.0))
            prov_13 = arredondar_moeda(sal / Decimal("12"))
            prov_fgts = arredondar_moeda(prov_13 * Decimal("0.08"))
            prov_enc = arredondar_moeda(prov_13 * Decimal("0.278"))
            itens.append({
                "colaborador_id": c["id"],
                "nome_completo": c["nome_completo"],
                "centro_custo": c.get("centro_custo") or c.get("setor") or "GERAL",
                "provisao_13": float(prov_13),
                "provisao_fgts": float(prov_fgts),
                "provisao_encargos": float(prov_enc),
                "custo_provisao_total": float(prov_13 + prov_fgts + prov_enc),
            })
        return {
            "competencia": competencia.strip()[:7],
            "qtd_colaboradores": len(itens),
            "total_provisao_13": round(sum(i["provisao_13"] for i in itens), 2),
            "total_provisao_fgts": round(sum(i["provisao_fgts"] for i in itens), 2),
            "total_provisao_encargos": round(sum(i["provisao_encargos"] for i in itens), 2),
            "custo_total_provisao": round(sum(i["custo_provisao_total"] for i in itens), 2),
            "itens": itens,
        }

    # ──────────────────────────────────────────────────────────
    # Conferência Analítica, Fechamento em Lote, Rateio, Integração & eSocial
    # ──────────────────────────────────────────────────────────

    def conferencia_analitica_folha(self, competencia: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        """RF-096: Auditoria pré-fechamento identificando divergências, variações >30%, líquidos zerados e ponto aberto."""
        comp = competencia.strip()[:7]
        folhas = self.listar_folhas(competencia=comp, empresa_id=empresa_id)
        ano, mes = int(comp[:4]), int(comp[5:7])
        prev_comp = f"{ano - 1}-12" if mes == 1 else f"{ano}-{mes - 1:02d}"
        folhas_prev = {int(f["colaborador_id"]): f for f in self.listar_folhas(competencia=prev_comp, empresa_id=empresa_id)}

        alertas = []
        for f in folhas:
            liq = float(f.get("salario_liquido") or 0)
            if liq <= 0:
                alertas.append({"colaborador_id": f["colaborador_id"], "colaborador": f.get("colaborador_nome"), "severidade": "critica", "mensagem": f"Líquido zerado ou negativo (R$ {liq:.2f})."})
            ant = folhas_prev.get(int(f["colaborador_id"]))
            if ant and float(ant.get("total_proventos") or 0) > 0:
                var = abs(float(f["total_proventos"]) - float(ant["total_proventos"])) / float(ant["total_proventos"])
                if var > 0.30:
                    alertas.append({"colaborador_id": f["colaborador_id"], "colaborador": f.get("colaborador_nome"), "severidade": "media", "mensagem": f"Variação de {var * 100:.1f}% nos proventos em relação a {prev_comp}."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT situacao FROM fechamentos_ponto WHERE competencia = {P} ORDER BY id DESC LIMIT 1;", (comp,))
        row_pt = cursor.fetchone()
        conn.close()
        ponto_fechado = bool(row_pt and str(row_pt[0] or "").lower() == "fechado")
        if not ponto_fechado:
            alertas.append({"colaborador_id": None, "colaborador": "Geral", "severidade": "media", "mensagem": f"Ponto da competência {comp} ainda não está fechado."})

        return {
            "competencia": comp,
            "total_folhas": len(folhas),
            "ponto_fechado": ponto_fechado,
            "total_alertas": len(alertas),
            "alertas": alertas,
            "apto_para_fechamento": not any(a["severidade"] == "critica" for a in alertas),
        }

    def gerar_rateio_centro_custo(self, competencia: str, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        """RF-101: Persiste rateio contábil da folha por centro de custo em folha_rateio_centro_custo."""
        comp = competencia.strip()[:7]
        emp_id = (empresa_id or "a0000000-0000-0000-0000-000000000001").strip()
        folhas = self.listar_folhas(competencia=comp, empresa_id=emp_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            f"DELETE FROM folha_rateio_centro_custo WHERE empresa_id = {P} AND competencia = {P};",
            (emp_id, comp),
        )
        resumo_cc: Dict[str, float] = {}
        for f in folhas:
            cc = str(f.get("colaborador_centro_custo") or f.get("colaborador_setor") or "GERAL").strip()
            bruto = float(f.get("total_proventos") or 0)
            enc = float(f.get("encargos_patronais") or 0)
            fgts = float(f.get("valor_fgts_informativo") or 0)
            tot = round(bruto + enc + fgts, 2)
            cursor.execute(
                f"""
                INSERT INTO folha_rateio_centro_custo (
                    empresa_id, folha_id, colaborador_id, competencia, centro_custo_id, centro_custo_codigo,
                    percentual, valor_bruto, valor_encargos, valor_fgts, custo_total, criado_em
                ) VALUES ({','.join([P]*12)});
            """,
                (emp_id, int(f["id"]), int(f["colaborador_id"]), comp, cc, cc, 100.0, bruto, enc, fgts, tot, agora),
            )
            resumo_cc[cc] = round(resumo_cc.get(cc, 0.0) + tot, 2)
        conn.commit()
        conn.close()
        return {"competencia": comp, "empresa_id": emp_id, "registros": len(folhas), "totais_por_centro_custo": resumo_cc}

    def listar_rateio_centro_custo(self, competencia: str, empresa_id: Optional[str] = None) -> List[Dict[str, Any]]:
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = "SELECT * FROM folha_rateio_centro_custo WHERE competencia = " + P
        params: List[Any] = [competencia.strip()[:7]]
        if empresa_id:
            sql += f" AND empresa_id = {P}"
            params.append(empresa_id.strip())
        sql += " ORDER BY centro_custo_codigo ASC, id ASC;"
        cursor.execute(sql, tuple(params))
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def gerar_integracao_financeira(self, competencia: str, empresa_id: Optional[str] = None, usuario: str = "Financeiro") -> Dict[str, Any]:
        """RF-102: Gera títulos financeiros consolidados a pagar (Salários, GPS/INSS, FGTS, DARF/IRRF)."""
        comp = competencia.strip()[:7]
        emp_id = (empresa_id or "a0000000-0000-0000-0000-000000000001").strip()
        rel = self.obter_relatorios_folha(competencia=comp, empresa_id=emp_id)
        res = rel["resumo_financeiro"]
        fin = rel["financeiro"]["valores_a_recolher"]
        folha_ids = json.dumps([int(f["id"]) for f in rel["folhas"]])

        ano, mes = int(comp[:4]), int(comp[5:7])
        prox_ano, prox_mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
        titulos_cfg = [
            ("salarios_liquidos", f"Folha Salários Líquidos {comp}", res["total_liquido"], f"{prox_ano}-{prox_mes:02d}-05"),
            ("inss_gps", f"Guia INSS / GPS / DCTFWeb {comp}", fin["inss_total_recolher"], f"{prox_ano}-{prox_mes:02d}-20"),
            ("fgts_guia", f"Guia FGTS Digital {comp}", fin["fgts_recolher"], f"{prox_ano}-{prox_mes:02d}-20"),
            ("irrf_darf", f"Guia DARF IRRF {comp}", fin["irrf_recolher"], f"{prox_ano}-{prox_mes:02d}-20"),
        ]

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            f"DELETE FROM folha_integracao_financeira WHERE empresa_id = {P} AND competencia = {P};",
            (emp_id, comp),
        )
        criados = []
        for tipo_t, desc_t, val_t, venc_t in titulos_cfg:
            if float(val_t or 0) <= 0:
                continue
            cursor.execute(
                f"""
                INSERT INTO folha_integracao_financeira (
                    empresa_id, competencia, tipo_titulo, descricao, centro_custo, valor_total,
                    data_vencimento, status, folha_ids_json, criado_por, criado_em
                ) VALUES ({','.join([P]*11)});
            """,
                (emp_id, comp, tipo_t, desc_t, "CONSOLIDADO", round(float(val_t), 2), venc_t, "aberto", folha_ids, usuario, agora),
            )
            criados.append({"tipo_titulo": tipo_t, "descricao": desc_t, "valor_total": round(float(val_t), 2), "data_vencimento": venc_t})
        conn.commit()
        conn.close()
        return {"competencia": comp, "empresa_id": emp_id, "titulos_gerados": len(criados), "titulos": criados}

    def listar_integracao_financeira(self, competencia: Optional[str] = None, empresa_id: Optional[str] = None) -> List[Dict[str, Any]]:
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = "SELECT * FROM folha_integracao_financeira WHERE 1=1"
        params: List[Any] = []
        if competencia:
            sql += f" AND competencia = {P}"
            params.append(competencia.strip()[:7])
        if empresa_id:
            sql += f" AND empresa_id = {P}"
            params.append(empresa_id.strip())
        sql += " ORDER BY competencia DESC, id ASC;"
        cursor.execute(sql, tuple(params))
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def fechar_competencia_lote(self, competencia: str, usuario: str = "Gestor DP", empresa_id: Optional[str] = None) -> Dict[str, Any]:
        """RF-096: Fecha todas as folhas abertas da competência, gera rateio contábil e títulos financeiros."""
        comp = competencia.strip()[:7]
        emp_id = (empresa_id or "a0000000-0000-0000-0000-000000000001").strip()
        folhas = self.listar_folhas(competencia=comp, empresa_id=emp_id)
        if not folhas:
            raise FolhaValidacaoException({"competencia": f"Não existem folhas lançadas para {comp}."})

        fechadas = 0
        for f in folhas:
            if f.get("situacao") != "fechada":
                self.fechar_folha(int(f["id"]), usuario=usuario)
                fechadas += 1

        rateio = self.gerar_rateio_centro_custo(comp, empresa_id=emp_id)
        fin = self.gerar_integracao_financeira(comp, empresa_id=emp_id, usuario=usuario)
        return {
            "sucesso": True,
            "competencia": comp,
            "folhas_fechadas_agora": fechadas,
            "total_folhas": len(folhas),
            "rateio": rateio,
            "integracao_financeira": fin,
        }

    def gerar_eventos_esocial_folha(self, competencia: str, empresa_id: Optional[str] = None, usuario: str = "DP") -> Dict[str, Any]:
        """RF-100: Gera e valida XMLs S-1200, S-1210 e S-1299 (v_S_01_02_00) para a competência."""
        try:
            from .esocial_eventos_trabalhistas import (
                gerar_xml_s1200,
                gerar_xml_s1210,
                gerar_xml_s1299,
                validar_xml_esocial_trabalhista,
            )
        except ImportError:
            from backend.esocial_eventos_trabalhistas import (
                gerar_xml_s1200,
                gerar_xml_s1210,
                gerar_xml_s1299,
                validar_xml_esocial_trabalhista,
            )

        comp = competencia.strip()[:7]
        emp_id = (empresa_id or "a0000000-0000-0000-0000-000000000001").strip()
        folhas = self.listar_folhas(competencia=comp, empresa_id=emp_id)
        if not folhas:
            raise FolhaValidacaoException({"competencia": f"Sem folhas na competência {comp} para geração eSocial."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT cnpj FROM empresas WHERE id = {P};", (emp_id,))
        row_emp = cursor.fetchone()
        cnpj_emp = row_emp[0] if row_emp and row_emp[0] else "12345678000190"
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        eventos_criados = []

        for f in folhas:
            f_full = self.obter_folha_por_id(int(f["id"]))
            colab_dict = {
                "cpf": f_full.get("colaborador_cpf"),
                "matricula": f_full.get("colaborador_matricula"),
                "setor": f_full.get("colaborador_setor"),
            }
            xml_1200, _ = gerar_xml_s1200(colab_dict, cnpj_emp, comp, f_full.get("itens") or [])
            if xml_1200:
                ok1, _ = validar_xml_esocial_trabalhista("S-1200", xml_1200)
                eid1 = self._insert_id(
                    cursor, conn,
                    f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({P},'S-1200',{P},'homologacao',{P},{P},{P},{P}) RETURNING id;",
                    f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({P},'S-1200',{P},'homologacao',{P},{P},{P},{P});",
                    (emp_id, f"folha_1200:{f_full['id']}", "validado" if ok1 else "erro_schema", xml_1200, usuario, agora),
                )
                eventos_criados.append({"id": eid1, "tipo": "S-1200", "folha_id": f_full["id"], "valido": ok1})

            dt_pg = f_full.get("data_pagamento") or f"{comp}-28"
            xml_1210, _ = gerar_xml_s1210(colab_dict, cnpj_emp, comp, dt_pg, float(f_full.get("salario_liquido") or 0))
            if xml_1210:
                ok2, _ = validar_xml_esocial_trabalhista("S-1210", xml_1210)
                eid2 = self._insert_id(
                    cursor, conn,
                    f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({P},'S-1210',{P},'homologacao',{P},{P},{P},{P}) RETURNING id;",
                    f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({P},'S-1210',{P},'homologacao',{P},{P},{P},{P});",
                    (emp_id, f"folha_1210:{f_full['id']}", "validado" if ok2 else "erro_schema", xml_1210, usuario, agora),
                )
                eventos_criados.append({"id": eid2, "tipo": "S-1210", "folha_id": f_full["id"], "valido": ok2})

        xml_1299, _ = gerar_xml_s1299(cnpj_emp, comp, possui_remuneracao=True, possui_pagamentos=True)
        if xml_1299:
            ok3, _ = validar_xml_esocial_trabalhista("S-1299", xml_1299)
            eid3 = self._insert_id(
                cursor, conn,
                f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({P},'S-1299',{P},'homologacao',{P},{P},{P},{P}) RETURNING id;",
                f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({P},'S-1299',{P},'homologacao',{P},{P},{P},{P});",
                (emp_id, f"fechamento:{comp}", "validado" if ok3 else "erro_schema", xml_1299, usuario, agora),
            )
            eventos_criados.append({"id": eid3, "tipo": "S-1299", "competencia": comp, "valido": ok3})

        conn.commit()
        conn.close()
        return {"competencia": comp, "total_eventos": len(eventos_criados), "eventos": eventos_criados}

