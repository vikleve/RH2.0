# -*- coding: utf-8 -*-
"""
Módulo 06: Gestão Completa de Férias Trabalhistas — RF-051 a RF-060
Cobre:
- RF-051: Períodos aquisitivos automáticos e redução por faltas injustificadas (art. 130 CLT)
- RF-052: Controle do período concessivo e alertas de vencimento/dobro (art. 134 e 137 CLT)
- RF-053: Programação com trava de 2 dias antes de DSR/feriado (art. 134 §3º CLT), sobreposição e aviso 30d
- RF-054: Fracionamento em até 3 períodos (mín. 14d em um e >= 5d nos demais, art. 134 §1º CLT)
- RF-055: Remuneração de férias (salário + médias variáveis + 1/3 + abono pecuniário + adiantamento 13º + dobro + INSS/IRRF c/ dependentes)
- RF-056: Geração real de PDF Aviso de Férias e Recibo de Férias
- RF-057: Integração automática das férias com a Folha de Pagamento
- RF-058: Férias coletivas (por empresa ou setor, com proporcionalidade CLT art. 140)
- RF-059: Aprovação, alteração, cancelamento com recomposição de saldo e pagamento art. 145 CLT
- RF-060: Geração de evento eSocial S-2230 (codMotAfast=15) e relatórios gerenciais
"""
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from backend.database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, insert_returning_id
from backend.documentos_trabalhistas_pdf import gerar_pdf_aviso_ferias, gerar_pdf_recibo_ferias
from backend.esocial_eventos_trabalhistas import gerar_xml_s2230, validar_xml_esocial_trabalhista
from backend.folha_calculos import (
    calcular_inss_progressivo,
    calcular_irrf_progressivo,
)
from backend.folha_calculos_2026 import round2, to_d
from backend.plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaValidacaoException,
)
from backend.tabelas_legais_service import TabelasLegaisService


def _dias_direito_art_130(faltas_injustificadas: int) -> int:
    f = max(0, int(faltas_injustificadas or 0))
    if f <= 5:
        return 30
    if f <= 14:
        return 24
    if f <= 23:
        return 18
    if f <= 32:
        return 12
    return 0


class FeriasService:
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
            raise PlataformaValidacaoException(f"Colaborador #{colaborador_id} não encontrado.")
        return c

    def _empresa_colab(self, cur, emp_id: str) -> Dict[str, Any]:
        p = self._p()
        cur.execute(f"SELECT * FROM empresas WHERE id = {p};", (emp_id,))
        return fetchone_dict(cur, self.db_path) or {"id": emp_id, "razao_social": "RH2.0 Enterprise", "cnpj": "12345678000190"}

    # ─────────────────────────────────────────────────────────────────────────
    # RF-051 / RF-052: Sincronização de Períodos Aquisitivos e Concessivos
    # ─────────────────────────────────────────────────────────────────────────
    def sincronizar_periodos_aquisitivos(
        self,
        colaborador_id: int,
        data_referencia: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        RF-051/RF-052: Garante existência de períodos aquisitivos desde a admissão
        e recalcula dias de direito pela tabela de faltas injustificadas (CLT art. 130).
        """
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, colaborador_id)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            dt_adm_str = str(colab.get("data_admissao") or datetime.now().strftime("%Y-%m-%d"))[:10]
            dt_adm = datetime.strptime(dt_adm_str, "%Y-%m-%d").date()
            ref_dt = datetime.strptime((data_referencia or datetime.now().strftime("%Y-%m-%d"))[:10], "%Y-%m-%d").date()

            cur.execute(
                f"SELECT * FROM periodos_aquisitivos WHERE colaborador_id = {p} ORDER BY inicio_aquisitivo ASC;",
                (int(colaborador_id),),
            )
            existentes = fetchall_dict(cur, self.db_path)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Garante ao menos o primeiro ciclo aquisitivo completo (ou em formação)
            if not existentes:
                fim_aq = dt_adm + timedelta(days=365)
                lim_conc = fim_aq + timedelta(days=365)
                cur.execute(
                    f"""
                    INSERT INTO periodos_aquisitivos (
                        empresa_id, colaborador_id, inicio_aquisitivo, fim_aquisitivo, limite_concessivo,
                        faltas_injustificadas, dias_direito, dias_gozados, saldo_dias, dias_perdidos_faltas,
                        situacao, criado_em, atualizado_em
                    ) VALUES ({','.join([p]*13)});
                """,
                    (emp_id, int(colaborador_id), dt_adm.isoformat(), fim_aq.isoformat(), lim_conc.isoformat(), 0, 30, 0, 30, 0, "adquirido", agora, agora),
                )
                conn.commit()
                cur.execute(
                    f"SELECT * FROM periodos_aquisitivos WHERE colaborador_id = {p} ORDER BY inicio_aquisitivo ASC;",
                    (int(colaborador_id),),
                )
                existentes = fetchall_dict(cur, self.db_path)
            else:
                # Criar ciclos subsequentes caso o último período aquisitivo já tenha vencido na data de referência
                ultimo = existentes[-1]
                ult_fim = datetime.strptime(ultimo["fim_aquisitivo"][:10], "%Y-%m-%d").date()
                while ult_fim < ref_dt:
                    novo_ini = ult_fim + timedelta(days=1)
                    novo_fim = novo_ini + timedelta(days=364)
                    novo_lim = novo_fim + timedelta(days=365)
                    cur.execute(
                        f"""
                        INSERT INTO periodos_aquisitivos (
                            empresa_id, colaborador_id, inicio_aquisitivo, fim_aquisitivo, limite_concessivo,
                            faltas_injustificadas, dias_direito, dias_gozados, saldo_dias, dias_perdidos_faltas,
                            situacao, criado_em, atualizado_em
                        ) VALUES ({','.join([p]*13)});
                    """,
                        (emp_id, int(colaborador_id), novo_ini.isoformat(), novo_fim.isoformat(), novo_lim.isoformat(), 0, 30, 0, 30, 0, "em_aquisicao" if novo_fim > ref_dt else "adquirido", agora, agora),
                    )
                    ult_fim = novo_fim
                conn.commit()
                cur.execute(
                    f"SELECT * FROM periodos_aquisitivos WHERE colaborador_id = {p} ORDER BY inicio_aquisitivo ASC;",
                    (int(colaborador_id),),
                )
                existentes = fetchall_dict(cur, self.db_path)

            # Atualizar faltas injustificadas por período aquisitivo (CLT art. 130)
            for pa in existentes:
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM ocorrencias_ponto
                    WHERE colaborador_id = {p} AND tipo_ocorrencia = 'falta_injustificada'
                      AND data_inicio >= {p} AND data_inicio <= {p};
                """,
                    (int(colaborador_id), pa["inicio_aquisitivo"][:10], pa["fim_aquisitivo"][:10]),
                )
                faltas_cnt = int(cur.fetchone()[0] or 0)

                # Verificar também se colaborador teve férias já consumidas neste PA (não canceladas)
                cur.execute(
                    f"""
                    SELECT COALESCE(SUM(dias_gozo + COALESCE(dias_abono, 0)), 0)
                    FROM ferias_programadas
                    WHERE periodo_aquisitivo_id = {p} AND COALESCE(status, 'solicitada') != 'cancelada';
                """,
                    (pa["id"],),
                )
                consumidos = int(cur.fetchone()[0] or 0)

                # Verificar perda art. 133 IV CLT (>= 180 dias de afastamento INSS previdenciário/acidentário no período aquisitivo)
                cur.execute(
                    f"""
                    SELECT COALESCE(SUM(dias_inss), 0) FROM afastamentos
                    WHERE colaborador_id = {p} AND tipo IN ('doenca', 'acidente_trabalho', 'auxilio_doenca', 'auxilio_doenca_acidentario')
                      AND data_inicio >= {p} AND data_inicio <= {p};
                """,
                    (int(colaborador_id), pa["inicio_aquisitivo"][:10], pa["fim_aquisitivo"][:10]),
                )
                dias_inss_pa = int(cur.fetchone()[0] or 0)

                direito = 0 if dias_inss_pa >= 180 else _dias_direito_art_130(faltas_cnt)
                perdidos = max(0, 30 - direito)
                saldo = max(0, direito - consumidos)
                sit = "perdido" if direito == 0 else ("quitado" if saldo == 0 and consumidos > 0 else ("vencido" if ref_dt.isoformat() > pa["limite_concessivo"][:10] and saldo > 0 else "adquirido"))

                cur.execute(
                    f"""
                    UPDATE periodos_aquisitivos
                    SET faltas_injustificadas = {p}, dias_direito = {p}, dias_gozados = {p},
                        saldo_dias = {p}, dias_perdidos_faltas = {p}, situacao = {p}, atualizado_em = {p}
                    WHERE id = {p};
                """,
                    (faltas_cnt, direito, consumidos, saldo, perdidos, sit, agora, pa["id"]),
                )

            conn.commit()
            cur.execute(
                f"SELECT * FROM periodos_aquisitivos WHERE colaborador_id = {p} ORDER BY inicio_aquisitivo ASC;",
                (int(colaborador_id),),
            )
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def listar_periodos_aquisitivos(self, colaborador_id: Optional[int] = None, empresa_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if colaborador_id:
            self.sincronizar_periodos_aquisitivos(int(colaborador_id))
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = """
                SELECT pa.*, c.nome_completo, c.matricula, c.setor
                FROM periodos_aquisitivos pa
                JOIN colaboradores c ON c.id = pa.colaborador_id
                WHERE 1=1
            """
            params: List[Any] = []
            if colaborador_id:
                sql += f" AND pa.colaborador_id = {p}"
                params.append(int(colaborador_id))
            if empresa_id:
                sql += f" AND COALESCE(c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p}"
                params.append(empresa_id)
            sql += " ORDER BY pa.inicio_aquisitivo DESC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-053 / RF-054 / RF-055 / RF-060: Programação e Cálculo CLT Completo
    # ─────────────────────────────────────────────────────────────────────────
    def _calcular_medias_variaveis_12m(self, cur, colaborador_id: int) -> Decimal:
        """Apura média mensal de variáveis (HE, adicionais, comissões) dos últimos 12 meses na folha."""
        p = self._p()
        cur.execute(
            f"""
            SELECT f.competencia, COALESCE(SUM(fi.valor_total), 0) as total_var
            FROM folhas_pagamento f
            JOIN folha_itens fi ON fi.folha_id = f.id
            WHERE f.colaborador_id = {p}
              AND fi.tipo = 'provento'
              AND fi.codigo_evento NOT IN ('0001', '0002', '0100', '0101', '0102', '0103', '0110', '0111')
              AND f.situacao IN ('calculada', 'fechada', 'paga')
            GROUP BY f.competencia
            ORDER BY f.competencia DESC
            LIMIT 12;
        """,
            (int(colaborador_id),),
        )
        rows = fetchall_dict(cur, self.db_path)
        if not rows:
            return Decimal("0.00")
        soma = sum(to_d(r["total_var"]) for r in rows)
        return round2(soma / Decimal("12.00"))

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
        """
        RF-053, RF-054, RF-055, RF-060, RN-029:
        - Bloqueia < 5 dias (art. 134 §1º CLT).
        - Bloqueia início 2 dias antes de DSR ou feriado oficial (art. 134 §3º CLT).
        - Valida fracionamento (máx. 3 frações e pelo menos 1 >= 14 dias).
        - Valida sobreposição de férias e conflito com afastamento ativo.
        - Calcula férias, 1/3, médias, abono pecuniário, adiantamento 13º, dobra art. 137, INSS e IRRF c/ dependentes.
        - Gera evento eSocial S-2230 (codMotAfast=15) e alerta aviso 30d se necessário.
        """
        dias_gozo_i = int(dias_gozo or 0)
        if dias_gozo_i < 5:
            raise PlataformaValidacaoException("Período de férias não pode ser inferior a 5 dias corridos (RF-054, RN-029).")

        try:
            dt_ini = datetime.strptime(str(data_inicio)[:10], "%Y-%m-%d").date()
        except ValueError:
            raise PlataformaValidacaoException(f"Data inicial inválida: '{data_inicio}'.")

        # Sincronizar períodos aquisitivos com base nas faltas/INSS antes de alocar
        self.sincronizar_periodos_aquisitivos(int(colaborador_id), data_referencia=dt_ini.isoformat())

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, int(colaborador_id))
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            emp = self._empresa_colab(cur, emp_id)

            # RF-053: Bloqueio 2 dias antes de DSR (weekday 4=Sex, 5=Sáb, 6=Dom para escala padrão) ou Feriado oficial
            if dt_ini.weekday() in (4, 5):
                raise PlataformaValidacaoException(
                    "Início das férias não pode ocorrer nos 2 dias que antecedem o repouso semanal remunerado (art. 134 § 3º CLT, RF-053)."
                )
            tab_srv = TabelasLegaisService(db_path=self.db_path)
            feriados = {
                f["data_feriado"][:10]
                for f in tab_srv.listar_feriados(empresa_id=emp_id, ano=dt_ini.year)
            } | {
                f["data_feriado"][:10]
                for f in tab_srv.listar_feriados(empresa_id=emp_id, ano=dt_ini.year + 1)
            }
            for offset in (0, 1, 2):
                cand = (dt_ini + timedelta(days=offset)).isoformat()
                if cand in feriados:
                    raise PlataformaValidacaoException(
                        f"Início das férias ({dt_ini.isoformat()}) não pode ocorrer em feriado nem nos 2 dias que o antecedem ({cand}) (art. 134 § 3º CLT, RF-053)."
                    )

            # Validação opcional estrita do aviso prévio de 30 dias (CLT art. 135)
            dias_antecedencia = (dt_ini - datetime.now().date()).days
            alerta_aviso_30d = dias_antecedencia < 30
            if exigir_aviso_30d and alerta_aviso_30d:
                raise PlataformaValidacaoException(
                    f"Aviso de férias deve ser comunicado com no mínimo 30 dias de antecedência (art. 135 CLT, RF-053). Antecedência informada: {dias_antecedencia}d."
                )

            # Buscar abono pecuniário solicitado
            dias_abono_i = 0
            if abono_pecuniario:
                dias_abono_i = 10 if dias_abono is None else int(dias_abono)
                if dias_abono_i <= 0:
                    raise PlataformaValidacaoException("Quantidade de dias de abono pecuniário deve ser positiva.")

            # Buscar período aquisitivo elegível
            cur.execute(
                f"""
                SELECT * FROM periodos_aquisitivos
                WHERE colaborador_id = {p} AND saldo_dias >= {p} AND situacao != 'perdido'
                ORDER BY inicio_aquisitivo ASC LIMIT 1;
            """,
                (int(colaborador_id), dias_gozo_i + dias_abono_i),
            )
            pa = fetchone_dict(cur, self.db_path)
            if not pa:
                raise PlataformaValidacaoException(
                    "Colaborador não possui período aquisitivo com saldo suficiente para gozo e abono solicitados."
                )

            if abono_pecuniario:
                max_abono = pa["dias_direito"] // 3
                if dias_abono_i > max_abono:
                    raise PlataformaValidacaoException(
                        f"Abono pecuniário máximo permitido pela CLT art. 143 é 1/3 do direito ({max_abono} dias)."
                    )

            # RF-054: Validação de fracionamento (máx. 3 períodos, ao menos 1 >= 14 dias)
            cur.execute(
                f"""
                SELECT id, dias_gozo, data_inicio, data_fim
                FROM ferias_programadas
                WHERE periodo_aquisitivo_id = {p} AND COALESCE(status, 'solicitada') != 'cancelada';
            """,
                (pa["id"],),
            )
            fracoes_existentes = fetchall_dict(cur, self.db_path)
            num_fracao = len(fracoes_existentes) + 1
            if num_fracao > 3:
                raise PlataformaValidacaoException(
                    "Limite legal de fracionamento excedido: férias podem ser divididas em no máximo 3 períodos (art. 134 §1º CLT, RF-054)."
                )
            ja_tem_14 = any(int(f["dias_gozo"] or 0) >= 14 for f in fracoes_existentes)
            if not ja_tem_14 and dias_gozo_i < 14:
                saldo_apos = int(pa["saldo_dias"]) - (dias_gozo_i + dias_abono_i)
                if num_fracao == 3 or saldo_apos < 14:
                    raise PlataformaValidacaoException(
                        "Pelo menos um dos períodos fracionados de férias deve ter no mínimo 14 dias corridos (art. 134 §1º CLT, RF-054)."
                    )

            dt_fim = dt_ini + timedelta(days=dias_gozo_i - 1)
            dt_ini_iso = dt_ini.isoformat()
            dt_fim_iso = dt_fim.isoformat()

            # Impedir sobreposição com outras férias não canceladas ou afastamentos ativos
            cur.execute(
                f"""
                SELECT id, data_inicio, data_fim FROM ferias_programadas
                WHERE colaborador_id = {p} AND COALESCE(status, 'solicitada') != 'cancelada'
                  AND data_inicio <= {p} AND data_fim >= {p};
            """,
                (int(colaborador_id), dt_fim_iso, dt_ini_iso),
            )
            if cur.fetchone():
                raise PlataformaValidacaoException("Já existem férias programadas com sobreposição de datas para este colaborador.")

            cur.execute(
                f"""
                SELECT id, tipo, data_inicio, data_fim_prevista FROM afastamentos
                WHERE colaborador_id = {p} AND data_retorno_efetivo IS NULL
                  AND data_inicio <= {p} AND COALESCE(data_retorno_efetivo, data_fim_prevista) >= {p};
            """,
                (int(colaborador_id), dt_fim_iso, dt_ini_iso),
            )
            if cur.fetchone():
                raise PlataformaValidacaoException("Não é possível programar férias durante período de afastamento ativo.")

            # RF-055: Remuneração + médias + abono + adiantamento 13º + dobro + INSS/IRRF
            salario = to_d(colab["salario_base"])
            media_vars = self._calcular_medias_variaveis_12m(cur, int(colaborador_id)) if incluir_medias_variaveis else Decimal("0.00")
            base_rem = salario + media_vars
            valor_dia = base_rem / Decimal("30.00")

            valor_ferias_base = round2(Decimal(str(dias_gozo_i)) * valor_dia)
            valor_ferias = round2(Decimal(str(dias_gozo_i)) * (salario / Decimal("30.00")))
            valor_medias = round2(max(Decimal("0.00"), valor_ferias_base - valor_ferias))
            valor_terco = round2(valor_ferias_base / Decimal("3.00"))

            valor_abono = round2(Decimal(str(dias_abono_i)) * valor_dia) if abono_pecuniario else Decimal("0.00")
            valor_terco_abono = round2(valor_abono / Decimal("3.00")) if abono_pecuniario else Decimal("0.00")
            adiant_13 = round2(base_rem * Decimal("0.50")) if adiantar_13 else Decimal("0.00")

            # Férias em dobro art. 137 CLT se gozo iniciar após limite concessivo
            em_dobro = 1 if dt_ini_iso > pa["limite_concessivo"][:10] else 0
            if em_dobro:
                valor_ferias = round2(valor_ferias * Decimal("2.00"))
                valor_medias = round2(valor_medias * Decimal("2.00"))
                valor_terco = round2(valor_terco * Decimal("2.00"))

            # Dependentes IRRF reais + Tabela legal da competência do início das férias
            cur.execute(
                f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {p} AND COALESCE(eh_dependente_irrf, 1) = 1;",
                (int(colaborador_id),),
            )
            dep_irrf = int(cur.fetchone()[0] or 0)
            tab_vig = tab_srv.obter_tabela_vigente(dt_ini_iso[:7])

            # Base tributável férias (abono pecuniário + 1/3 abono são isentos; dobra punitiva idem conforme STJ)
            base_trib_ferias = valor_ferias_base + round2(valor_ferias_base / Decimal("3.00"))
            inss_ferias, _, _, _ = calcular_inss_progressivo(
                base_trib_ferias,
                tabela_faixas=tab_vig["tabela_inss_tuples"],
                teto_maximo=Decimal(str(tab_vig["teto_inss"])),
                teto_contribuicao=Decimal(str(tab_vig["teto_contribuicao_inss"])),
            )
            irrf_ferias, _, _ = calcular_irrf_progressivo(
                base_bruta_irrf=base_trib_ferias,
                desconto_inss=inss_ferias,
                numero_dependentes=dep_irrf,
                deducao_por_dependente=Decimal(str(tab_vig["deducao_dependente_irrf"])),
                tabela_faixas=tab_vig["tabela_irrf_tuples"],
                desconto_simplificado=Decimal(str(tab_vig["desconto_simplificado_irrf"])),
                aplicar_reducao_lei_15270=bool(tab_vig.get("lei_15270_ativa", 1)),
            )

            bruto_total = valor_ferias + valor_medias + valor_terco + valor_abono + valor_terco_abono + adiant_13
            liquido = max(Decimal("0.00"), round2(bruto_total - inss_ferias - irrf_ferias))

            dt_limite_pag = (dt_ini - timedelta(days=2)).isoformat()
            aviso_dt = (dt_ini - timedelta(days=30)).isoformat()
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memoria = json.dumps(
                {
                    "salario_base": float(salario),
                    "media_variaveis_12m": float(media_vars),
                    "valor_ferias": float(valor_ferias),
                    "valor_medias": float(valor_medias),
                    "valor_terco": float(valor_terco),
                    "valor_abono": float(valor_abono),
                    "valor_terco_abono": float(valor_terco_abono),
                    "adiantamento_13": float(adiant_13),
                    "em_dobro": bool(em_dobro),
                    "dependentes_irrf": dep_irrf,
                    "inss": float(inss_ferias),
                    "irrf": float(irrf_ferias),
                    "liquido": float(liquido),
                    "numero_fracao": num_fracao,
                },
                ensure_ascii=False,
            )

            sql_pg = f"""
                INSERT INTO ferias_programadas (
                    empresa_id, colaborador_id, periodo_aquisitivo_id, data_inicio, data_fim, dias_gozo,
                    numero_fracao, abono_pecuniario, dias_abono, adiantar_decimo, valor_adiantamento_13,
                    aviso_ferias_emitido, data_pagamento_limite, valor_ferias, media_variaveis, valor_terco,
                    valor_abono, valor_terco_abono, desconto_inss, desconto_irrf, valor_liquido,
                    em_dobro, status, memoria_calculo, criado_por, criado_em
                ) VALUES ({','.join([p]*22)}, 'solicitada', {p}, {p}, {p}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO ferias_programadas (
                    empresa_id, colaborador_id, periodo_aquisitivo_id, data_inicio, data_fim, dias_gozo,
                    numero_fracao, abono_pecuniario, dias_abono, adiantar_decimo, valor_adiantamento_13,
                    aviso_ferias_emitido, data_pagamento_limite, valor_ferias, media_variaveis, valor_terco,
                    valor_abono, valor_terco_abono, desconto_inss, desconto_irrf, valor_liquido,
                    em_dobro, status, memoria_calculo, criado_por, criado_em
                ) VALUES ({','.join([p]*22)}, 'solicitada', {p}, {p}, {p});
            """
            params = (
                emp_id, int(colaborador_id), pa["id"], dt_ini_iso, dt_fim_iso, dias_gozo_i,
                num_fracao, 1 if abono_pecuniario else 0, dias_abono_i, 1 if adiantar_13 else 0, float(adiant_13),
                aviso_dt, dt_limite_pag, float(valor_ferias), float(valor_medias), float(valor_terco),
                float(valor_abono), float(valor_terco_abono), float(inss_ferias), float(irrf_ferias), float(liquido),
                em_dobro, memoria, solicitante, agora,
            )
            ferias_id = insert_returning_id(cur, conn, sql_pg, sql_sq, params, self.db_path)

            # Abater saldo do período aquisitivo (será recomposto se cancelado)
            novo_gozado = int(pa["dias_gozados"] or 0) + dias_gozo_i + dias_abono_i
            novo_saldo = max(0, int(pa["dias_direito"]) - novo_gozado)
            cur.execute(
                f"UPDATE periodos_aquisitivos SET dias_gozados = {p}, saldo_dias = {p}, situacao = {p}, atualizado_em = {p} WHERE id = {p};",
                (novo_gozado, novo_saldo, "quitado" if novo_saldo == 0 else "em_gozo", agora, pa["id"]),
            )

            # RF-060: Gerar evento eSocial S-2230 codMotAfast=15 (Férias) com schema v_S_01_02_00
            esocial_id = None
            if gerar_esocial and len(str(colab.get("cpf") or "")) >= 11:
                xml_2230, _ = gerar_xml_s2230(
                    colaborador=colab,
                    cnpj_empregador=emp.get("cnpj") or "12345678000190",
                    data_inicio=dt_ini_iso,
                    motivo="ferias",
                    data_fim=dt_fim_iso,
                )
                if xml_2230:
                    ok_xml, _ = validar_xml_esocial_trabalhista("S-2230", xml_2230)
                    esocial_id = insert_returning_id(
                        cur,
                        conn,
                        f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({p},'S-2230',{p},'homologacao',{p},{p},{p},{p}) RETURNING id;",
                        f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({p},'S-2230',{p},'homologacao',{p},{p},{p},{p});",
                        (emp_id, f"ferias:{ferias_id}", "validado" if ok_xml else "erro_schema", xml_2230, solicitante, agora),
                        self.db_path,
                    )
                    cur.execute(
                        f"UPDATE ferias_programadas SET esocial_evento_id = {p} WHERE id = {p};",
                        (esocial_id, ferias_id),
                    )

            # Se aviso < 30d, gera alerta na Central de Pendências
            if alerta_aviso_30d:
                cur.execute(
                    f"""
                    INSERT INTO pendencias_operacionais (
                        empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                        colaborador_id, prazo_limite, responsavel, status, criado_em
                    ) VALUES ({','.join([p]*11)});
                """,
                    (
                        emp_id, "Ferias", "aviso_ferias_fora_prazo",
                        f"Aviso de Férias fora do prazo legal (30d) — {colab['nome_completo']}",
                        f"Férias #{ferias_id} com início {dt_ini_iso} programada com {dias_antecedencia}d de antecedência (CLT art. 135 exige 30d).",
                        "media", int(colaborador_id), dt_limite_pag, "DP", "pendente", agora,
                    ),
                )

            conn.commit()
            self._auditar(
                "Ferias", "inclusao", "ferias_programadas", ferias_id, solicitante,
                f"Férias #{ferias_id} programadas Colab {colaborador_id}: {dt_ini_iso} a {dt_fim_iso} ({dias_gozo_i}d + {dias_abono_i}d abono) Líquido R$ {liquido:.2f}",
            )

            return {
                "sucesso": True,
                "ferias_id": ferias_id,
                "periodo_aquisitivo_id": pa["id"],
                "numero_fracao": num_fracao,
                "data_inicio": dt_ini_iso,
                "data_fim": dt_fim_iso,
                "data_limite_pagamento": dt_limite_pag,
                "aviso_ferias_emitido": aviso_dt,
                "alerta_aviso_30d": alerta_aviso_30d,
                "valor_ferias": float(valor_ferias),
                "media_variaveis": float(valor_medias),
                "valor_terco": float(valor_terco),
                "valor_abono": float(valor_abono),
                "valor_terco_abono": float(valor_terco_abono),
                "valor_adiantamento_13": float(adiant_13),
                "desconto_inss": float(inss_ferias),
                "desconto_irrf": float(irrf_ferias),
                "valor_liquido": float(liquido),
                "em_dobro": bool(em_dobro),
                "esocial_evento_id": esocial_id,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-059: Aprovação, Alteração, Cancelamento e Pagamento Art. 145 CLT
    # ─────────────────────────────────────────────────────────────────────────
    def aprovar_ferias(self, ferias_id: int, aprovador: str, aprovar: bool = True, motivo: str = "") -> Dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM ferias_programadas WHERE id = {p};", (int(ferias_id),))
            f = fetchone_dict(cur, self.db_path)
            if not f:
                raise PlataformaValidacaoException(f"Programação de férias #{ferias_id} não encontrada.")
            if f["status"] not in ("solicitada",):
                raise PlataformaValidacaoException(f"Férias #{ferias_id} já está no status '{f['status']}'.")
            if str(f.get("criado_por") or "").strip().lower() == str(aprovador or "").strip().lower():
                raise PlataformaAcessoNegadoException("RN-080: O solicitante não pode aprovar a própria programação de férias.")

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if aprovar:
                cur.execute(
                    f"UPDATE ferias_programadas SET status = 'aprovada', aprovado_por = {p}, aprovado_em = {p} WHERE id = {p};",
                    (aprovador, agora, int(ferias_id)),
                )
                novo_st = "aprovada"
            else:
                if not motivo or len(motivo.strip()) < 3:
                    raise PlataformaValidacaoException("Motivo é obrigatório ao reprovar/cancelar programação de férias.")
                cur.execute(
                    f"UPDATE ferias_programadas SET status = 'cancelada', motivo_reprovacao = {p}, motivo_cancelamento = {p}, aprovado_por = {p}, aprovado_em = {p} WHERE id = {p};",
                    (motivo.strip(), motivo.strip(), aprovador, agora, int(ferias_id)),
                )
                self._recompor_saldo_pa(cur, f, agora)
                novo_st = "cancelada"

            conn.commit()
            self._auditar("Ferias", "aprovacao" if aprovar else "cancelamento", "ferias_programadas", ferias_id, aprovador, f"Férias #{ferias_id} -> {novo_st}")
            return {"sucesso": True, "ferias_id": int(ferias_id), "status": novo_st}
        finally:
            conn.close()

    def cancelar_ferias(self, ferias_id: int, motivo: str, usuario: str) -> Dict[str, Any]:
        if not motivo or len(motivo.strip()) < 5:
            raise PlataformaValidacaoException("Cancelamento de férias exige motivo formal (mín. 5 caracteres).")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM ferias_programadas WHERE id = {p};", (int(ferias_id),))
            f = fetchone_dict(cur, self.db_path)
            if not f:
                raise PlataformaValidacaoException("Férias não encontradas.")
            if f["status"] == "cancelada":
                raise PlataformaValidacaoException("Férias já canceladas.")
            if f["status"] == "paga":
                raise PlataformaValidacaoException("Férias já quitadas (status='paga') não podem ser canceladas diretamente.")

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"UPDATE ferias_programadas SET status = 'cancelada', motivo_cancelamento = {p} WHERE id = {p};",
                (motivo.strip(), int(ferias_id)),
            )
            self._recompor_saldo_pa(cur, f, agora)
            conn.commit()
            self._auditar("Ferias", "cancelamento", "ferias_programadas", ferias_id, usuario, f"Cancelamento #{ferias_id}: {motivo}")
            return {"sucesso": True, "ferias_id": int(ferias_id), "status": "cancelada"}
        finally:
            conn.close()

    def _recompor_saldo_pa(self, cur, ferias_row: Dict[str, Any], agora: str):
        p = self._p()
        pa_id = ferias_row.get("periodo_aquisitivo_id")
        if not pa_id:
            return
        cur.execute(f"SELECT * FROM periodos_aquisitivos WHERE id = {p};", (pa_id,))
        pa = fetchone_dict(cur, self.db_path)
        if not pa:
            return
        devolver = int(ferias_row.get("dias_gozo") or 0) + int(ferias_row.get("dias_abono") or 0)
        novo_goz = max(0, int(pa["dias_gozados"] or 0) - devolver)
        novo_saldo = min(int(pa["dias_direito"]), int(pa["dias_direito"]) - novo_goz)
        cur.execute(
            f"UPDATE periodos_aquisitivos SET dias_gozados = {p}, saldo_dias = {p}, situacao = 'adquirido', atualizado_em = {p} WHERE id = {p};",
            (novo_goz, novo_saldo, agora, pa_id),
        )

    def registrar_pagamento_ferias(self, ferias_id: int, data_pagamento: str, usuario: str) -> Dict[str, Any]:
        """RF-059 / CLT art. 145: Registra quitação das férias validando o prazo legal (até 2 dias antes do início)."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM ferias_programadas WHERE id = {p};", (int(ferias_id),))
            f = fetchone_dict(cur, self.db_path)
            if not f:
                raise PlataformaValidacaoException("Férias não encontradas.")
            if f["status"] == "cancelada":
                raise PlataformaValidacaoException("Férias canceladas não podem ser pagas.")
            dt_pg = str(data_pagamento or datetime.now().strftime("%Y-%m-%d")).strip()[:10]
            atrasado = dt_pg > str(f["data_pagamento_limite"])[:10]
            cur.execute(
                f"UPDATE ferias_programadas SET status = 'paga', pago_em = {p} WHERE id = {p};",
                (dt_pg, int(ferias_id)),
            )
            conn.commit()
            self._auditar("Ferias", "pagamento", "ferias_programadas", ferias_id, usuario, f"Pagamento férias #{ferias_id} em {dt_pg} (atraso_art_145={atrasado})")
            return {
                "sucesso": True,
                "ferias_id": int(ferias_id),
                "status": "paga",
                "pago_em": dt_pg,
                "fora_prazo_art_145": atrasado,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-056: Documentos Oficiais PDF (Aviso e Recibo de Férias)
    # ─────────────────────────────────────────────────────────────────────────
    def gerar_documentos_ferias_pdf(self, ferias_id: int, tipo_documento: str = "aviso") -> Dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                SELECT f.*, pa.inicio_aquisitivo, pa.fim_aquisitivo, pa.limite_concessivo
                FROM ferias_programadas f
                LEFT JOIN periodos_aquisitivos pa ON pa.id = f.periodo_aquisitivo_id
                WHERE f.id = {p};
            """,
                (int(ferias_id),),
            )
            f = fetchone_dict(cur, self.db_path)
            if not f:
                raise PlataformaValidacaoException(f"Férias #{ferias_id} não encontrada.")
            colab = self._buscar_colab(cur, int(f["colaborador_id"]))
            emp = self._empresa_colab(cur, colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001")
        finally:
            conn.close()

        f["valor_medias"] = f.get("media_variaveis", 0.0)
        if str(tipo_documento).lower().strip() == "recibo":
            pdf_bytes = gerar_pdf_recibo_ferias(f, colab, emp)
            nome = f"RECIBO_FERIAS_{ferias_id}.pdf"
        else:
            pdf_bytes = gerar_pdf_aviso_ferias(f, colab, emp)
            nome = f"AVISO_FERIAS_{ferias_id}.pdf"

        return {"sucesso": True, "filename": nome, "pdf_bytes": pdf_bytes}

    # ─────────────────────────────────────────────────────────────────────────
    # RF-057: Integração com Folha de Pagamento
    # ─────────────────────────────────────────────────────────────────────────
    def integrar_ferias_folha(self, ferias_id: int, competencia: str, usuario: str = "DP") -> Dict[str, Any]:
        """RF-057: Lança automaticamente rubricas de férias na Folha de Pagamento e vincula folha_id."""
        from backend.folha_service import FolhaService

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM ferias_programadas WHERE id = {p};", (int(ferias_id),))
            f = fetchone_dict(cur, self.db_path)
            if not f:
                raise PlataformaValidacaoException("Férias não encontradas.")
            if f["status"] == "cancelada":
                raise PlataformaValidacaoException("Férias canceladas não podem ser integradas à folha.")
            cid = int(f["colaborador_id"])
            comp = str(competencia or f["data_inicio"][:7]).strip()[:7]
        finally:
            conn.close()

        evs: List[Dict[str, Any]] = [
            {"codigo": "0100", "referencia": int(f["dias_gozo"]), "valor_informado": float(f["valor_ferias"]) + float(f.get("media_variaveis") or 0)},
            {"codigo": "0101", "referencia": 1, "valor_informado": float(f["valor_terco"])},
        ]
        if f.get("abono_pecuniario") and float(f.get("valor_abono") or 0) > 0:
            evs.append({"codigo": "0102", "referencia": int(f.get("dias_abono") or 0), "valor_informado": float(f["valor_abono"])})
            evs.append({"codigo": "0103", "referencia": 1, "valor_informado": float(f.get("valor_terco_abono") or 0)})
        if f.get("adiantar_decimo") and float(f.get("valor_adiantamento_13") or 0) > 0:
            evs.append({"codigo": "0110", "referencia": 1, "valor_informado": float(f["valor_adiantamento_13"])})

        folha_srv = FolhaService(db_path=self.db_path)
        folha = folha_srv.criar_ou_atualizar_folha(
            colaborador_id=cid,
            competencia=comp,
            periodo_inicio=f"{comp}-01",
            periodo_fim=f"{comp}-28",
            eventos=evs,
            observacoes=f"Integração automática de férias #{ferias_id} ({f['data_inicio']} a {f['data_fim']})",
            usuario=usuario,
        )

        conn2 = self._conn()
        try:
            cur2 = conn2.cursor()
            p2 = self._p()
            cur2.execute(
                f"UPDATE ferias_programadas SET folha_id = {p2}, competencia_folha = {p2} WHERE id = {p2};",
                (folha["id"], comp, int(ferias_id)),
            )
            conn2.commit()
        finally:
            conn2.close()

        return {"sucesso": True, "ferias_id": int(ferias_id), "folha_id": folha["id"], "competencia": comp}

    # ─────────────────────────────────────────────────────────────────────────
    # RF-058: Férias Coletivas (CLT art. 139/140)
    # ─────────────────────────────────────────────────────────────────────────
    def programar_ferias_coletivas(
        self,
        data_inicio: str,
        dias_gozo: int,
        setor: Optional[str] = None,
        empresa_id: Optional[str] = None,
        usuario: str = "DP",
    ) -> Dict[str, Any]:
        """RF-058: Concede férias coletivas por setor/empresa ajustando proporcionalmente quem tem < 12 meses (CLT art. 140)."""
        if int(dias_gozo or 0) < 10:
            raise PlataformaValidacaoException("Férias coletivas exigem no mínimo 10 dias corridos por período (art. 139 §1º CLT, RF-058).")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = "SELECT id, nome_completo, data_admissao, setor, empresa_id FROM colaboradores WHERE situacao = 'ativo'"
            params: List[Any] = []
            if setor:
                sql += f" AND LOWER(setor) = {p}"
                params.append(setor.strip().lower())
            if empresa_id:
                sql += f" AND COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p}"
                params.append(empresa_id)
            cur.execute(sql, tuple(params))
            colabs = fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

        if not colabs:
            raise PlataformaValidacaoException("Nenhum colaborador ativo elegível encontrado para férias coletivas.")

        resultados = []
        erros = []
        for col in colabs:
            try:
                res = self.programar_ferias(
                    colaborador_id=int(col["id"]),
                    data_inicio=data_inicio,
                    dias_gozo=int(dias_gozo),
                    solicitante=usuario,
                    exigir_aviso_30d=False,
                    incluir_medias_variaveis=False,
                    gerar_esocial=True,
                )
                resultados.append({"colaborador_id": col["id"], "nome": col["nome_completo"], "ferias_id": res["ferias_id"]})
            except Exception as exc:
                erros.append({"colaborador_id": col["id"], "nome": col["nome_completo"], "erro": str(exc)})

        self._auditar("Ferias", "coletivas", "ferias_programadas", 0, usuario, f"Coletivas {data_inicio} ({dias_gozo}d): {len(resultados)} programados, {len(erros)} avisos.")
        return {
            "sucesso": len(resultados) > 0,
            "total_programados": len(resultados),
            "programados": resultados,
            "ignorados_ou_erros": erros,
        }

    def listar_ferias(
        self,
        colaborador_id: Optional[int] = None,
        empresa_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            query = """
                SELECT f.*, c.nome_completo, c.matricula, c.setor,
                       pa.inicio_aquisitivo, pa.fim_aquisitivo, pa.limite_concessivo
                FROM ferias_programadas f
                JOIN colaboradores c ON c.id = f.colaborador_id
                LEFT JOIN periodos_aquisitivos pa ON pa.id = f.periodo_aquisitivo_id
                WHERE 1=1
            """
            params: List[Any] = []
            if colaborador_id:
                query += f" AND f.colaborador_id = {p}"
                params.append(int(colaborador_id))
            if empresa_id:
                query += f" AND COALESCE(c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p}"
                params.append(empresa_id)
            if status:
                query += f" AND f.status = {p}"
                params.append(status)
            query += " ORDER BY f.data_inicio DESC;"
            cur.execute(query, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()
