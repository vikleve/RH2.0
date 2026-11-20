"""
Camada de Serviços da Folha de Pagamento — RH / DP
Regras de negócio, persistência relacional, validação de unicidade,
auditoria histórica, ciclo de vida da folha (Rascunho -> Calculada -> Fechada)
e integração com a camada de cálculos.
Funciona em modo dual: PostgreSQL (produção/Supabase) e SQLite (local/testes).
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from .database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, init_db, insert_returning_id, ph
from .folha_calculos import processar_calculo_folha


class FolhaValidacaoException(Exception):
    def __init__(self, erros: dict):
        super().__init__("Inconsistência nos dados da folha de pagamento.")
        self.erros = erros


class FolhaNaoEncontradaException(Exception):
    pass


class FolhaBloqueadaException(Exception):
    pass


class FolhaService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path
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

        cursor.execute(f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P}", (colaborador_id,))
        total_dep = cursor.fetchone()[0]
        try:
            cursor.execute(
                f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(eh_dependente_irrf, 1) = 1",
                (colaborador_id,)
            )
            total_dep_irrf = cursor.fetchone()[0]
            cursor.execute(
                f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {P} AND COALESCE(eh_elegivel_salario_familia, 0) = 1",
                (colaborador_id,)
            )
            total_dep_sf = cursor.fetchone()[0]
        except Exception:
            total_dep_irrf = total_dep
            total_dep_sf = 0

        colab["total_dependentes"] = total_dep
        colab["total_dependentes_irrf"] = total_dep_irrf
        colab["total_dependentes_salario_familia"] = total_dep_sf

        conn.close()
        return colab

    # ──────────────────────────────────────────────────────────
    # Ciclo de Vida da Folha de Pagamento
    # ──────────────────────────────────────────────────────────

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

        if (colab.get("situacao") or "ativo").lower() in ("inativo", "desligado") and tipo_folha_norm != "rescisoria":
            raise FolhaValidacaoException({"colaborador_id": "Colaborador inativo/desligado só pode receber folha rescisória."})

        for ev in (eventos or []):
            ref_ev = ev.get("referencia")
            val_ev = ev.get("valor_informado")
            if ref_ev is not None and float(ref_ev) < 0:
                raise FolhaValidacaoException({"eventos": f"Referência negativa não permitida no evento {ev.get('codigo', '')}."})
            if val_ev is not None and float(val_ev) < 0:
                raise FolhaValidacaoException({"eventos": f"Valor negativo não permitido no evento {ev.get('codigo', '')}."})

        emp_id = (empresa_id or colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()
        fil_id = (filial_id or colab.get("filial_id") or None)

        # Validação da competência (AAAA-MM)
        comp = competencia.strip()
        partes_comp = comp.split("-")
        if len(partes_comp) != 2 or not (len(partes_comp[0]) == 4 and len(partes_comp[1]) == 2):
            raise FolhaValidacaoException({"competencia": "A competência deve estar no formato AAAA-MM (ex: 2026-10)."})

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

        # Obter parâmetros vigentes
        param = self.obter_parametro_vigente()
        param_id = param.get("id")

        # Ajustes de regras conforme tipo de contrato e tipo de folha
        tipo_contrato = (colab.get("tipo_contrato") or "CLT").strip().lower()
        aliquota_fgts_efetiva = 2.0 if tipo_contrato == "aprendiz" else param.get("aliquota_fgts", 8.0)

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
            limite_sf = float(param.get("limite_salario_familia", 1980.38))
            cota_sf = float(param.get("valor_cota_salario_familia", 67.54))
            if salario_base <= limite_sf and not any(str(e.get("codigo", "")).strip() == "0202" for e in eventos_proc):
                eventos_proc.append({
                    "codigo": "0202",
                    "descricao": f"Salário-família ({num_dep_sf} cota(s))",
                    "tipo": "provento",
                    "referencia": num_dep_sf,
                    "valor_informado": round(num_dep_sf * cota_sf, 2),
                })

        # Processar cálculos detalhados
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
                "teto_inss": param.get("teto_inss", "8475.55"),
                "deducao_dependente_irrf": param.get("deducao_dependente_irrf", "189.59"),
                "desconto_simplificado_irrf": param.get("desconto_simplificado_irrf", "607.20"),
                "salario_minimo": param.get("salario_minimo", "1621.00"),
                "limite_salario_familia": param.get("limite_salario_familia", "1980.38"),
                "valor_cota_salario_familia": param.get("valor_cota_salario_familia", "67.54")
            }
        )

        resumo = calc_result["resumo"]
        itens = calc_result["itens"]
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        situacao_destino = "rascunho" if salvar_como_rascunho else "calculada"

        inss_desc = sum(float(it["valor_total"]) for it in itens if it["tipo"] == "desconto" and it["codigo_evento"] in ("0501", "0502"))
        irrf_desc = sum(float(it["valor_total"]) for it in itens if it["tipo"] == "desconto" and it["codigo_evento"] in ("0505", "0506", "0507"))
        enc_pat = round(float(resumo["base_inss"]) * 0.278, 2)  # 20% Patronal + 2% RAT + 5.8% Terceiros

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
                        memoria_calculo, criado_em
                    ) VALUES ({P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P});
                """, (
                    folha_id, it["codigo_evento"], it["descricao"], it["tipo"],
                    it["referencia"], it["unidade_referencia"], it["valor_unitario"],
                    it["valor_total"], it["origem"], it["memoria_calculo"], agora
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

    def reabrir_folha(self, folha_id: int, motivo: str, usuario: str = "Sistema/Administrador") -> Dict[str, Any]:
        """
        Reabre uma folha fechada mediante registro obrigatório do motivo na auditoria.
        """
        if not motivo or len(motivo.strip()) < 5:
            raise FolhaValidacaoException({"motivo": "Informe um motivo detalhado para reabertura da folha."})

        self.obter_folha_por_id(folha_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

        total_bruto = round(sum(float(f.get("total_proventos") or 0) for f in folhas), 2)
        total_descontos = round(sum(float(f.get("total_descontos") or 0) for f in folhas), 2)
        total_liquido = round(sum(float(f.get("salario_liquido") or 0) for f in folhas), 2)
        total_inss = round(sum(float(f.get("inss_descontado") or 0) for f in folhas), 2)
        total_irrf = round(sum(float(f.get("irrf_descontado") or 0) for f in folhas), 2)
        total_fgts = round(sum(float(f.get("valor_fgts_informativo") or 0) for f in folhas), 2)
        total_encargos = round(sum(float(f.get("encargos_patronais") or 0) for f in folhas), 2)
        custo_total = round(total_bruto + total_fgts + total_encargos, 2)

        abertas = sum(1 for f in folhas if f.get("situacao") in ("rascunho", "calculada", "aprovada"))
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

        # Evolução mensal (sem filtro de competência para mostrar histórico comparativo)
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

        return {
            "filtros": {"competencia": competencia, "empresa_id": empresa_id, "filial_id": filial_id, "setor": setor, "colaborador_id": colaborador_id},
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
            "por_departamento": _agrupar("colaborador_setor", "Não informado"),
            "por_centro_custo": _agrupar("colaborador_centro_custo", "Sem centro de custo"),
            "por_cargo": _agrupar("colaborador_cargo", "Não informado"),
            "evolucao_mensal": evolucao_mensal,
            "folhas": folhas,
        }

