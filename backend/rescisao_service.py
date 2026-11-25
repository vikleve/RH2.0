# -*- coding: utf-8 -*-
"""
Módulo 11: Gestão Completa de Rescisão Contratual — RF-106 a RF-120
Cobre:
- RF-106: Trava legal de estabilidade provisória (CIPA, acidentária, gestante, sindical) e afastamento ativo
- RF-107: Cálculo rescisório das 9 modalidades legais (sem justa causa, com justa causa, pedido de demissão,
          acordo mútuo art. 484-A, término de experiência, antecipada empregador art. 479, antecipada empregado art. 480,
          rescisão indireta e falecimento)
- RF-108: Aviso prévio proporcional (Lei 12.506/2011: 30 + 3d/ano até 90d) com projeção em avos de 13º e férias
- RF-109: Busca automática de férias vencidas (+ dobro art. 137) em periodos_aquisitivos e médias variáveis
- RF-110: IRRF rescisório (com isenção de verbas indenizatórias), INSS rescisório e FGTS rescisório separado (GRRF)
- RF-111 / RF-112: Desconto de faltas e aviso prévio não cumprido; multa art. 479/480 em contrato a prazo
- RF-113 / RF-114: Simulação rescisória prévia e verificação de ASO demissional (NR-07)
- RF-115 / RF-116: Geração real de TRCT PDF e Guia FGTS/Seguro-Desemprego PDF
- RF-117: Homologação formal com segregação RN-080 e histórico auditável (rescisoes_historico)
- RF-118: Baixa de pagamento com aplicação automática da multa do art. 477 §8º CLT (1 salário) se atrasado
- RF-119 / RF-120: Geração de eSocial S-2299 (v_S_01_02_00) e relatórios gerenciais/listagem
"""
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from backend.database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, insert_returning_id
from backend.documentos_trabalhistas_pdf import gerar_pdf_guias_fgts_sd, gerar_pdf_trct
from backend.esocial_eventos_trabalhistas import gerar_xml_s2299, validar_xml_esocial_trabalhista
from backend.folha_calculos import (
    calcular_inss_progressivo,
    calcular_irrf_progressivo,
)
from backend.folha_calculos_2026 import round2, to_d
from backend.plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaRecursoNaoEncontradoException,
    PlataformaValidacaoException,
)
from backend.tabelas_legais_service import TabelasLegaisService

MODALIDADES_CANONICAS = {
    "sem_justa_causa": "sem_justa_causa",
    "com_justa_causa": "com_justa_causa",
    "justa_causa": "com_justa_causa",
    "pedido_demissao": "pedido_demissao",
    "acordo_mutuo": "acordo_484a",
    "acordo_484a": "acordo_484a",
    "termino_experiencia": "termino_experiencia",
    "termino_contrato": "termino_experiencia",
    "rescisao_antecipada_empregador": "rescisao_antecipada_empregador",
    "rescisao_antecipada_empregado": "rescisao_antecipada_empregado",
    "rescisao_indireta": "rescisao_indireta",
    "culpa_reciproca": "culpa_reciproca",
    "falecimento": "falecimento",
}


class RescisaoService:
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

    def _empresa_colab(self, cur, emp_id: str) -> Dict[str, Any]:
        p = self._p()
        cur.execute(f"SELECT * FROM empresas WHERE id = {p};", (emp_id,))
        return fetchone_dict(cur, self.db_path) or {"id": emp_id, "razao_social": "RH2.0 Enterprise", "cnpj": "12345678000190"}

    def _contar_avos_data(self, dt_inicio, dt_fim) -> int:
        """Conta avos trabalhados (>= 15 dias) no ano civil até dt_fim."""
        ano = dt_fim.year
        inicio_ano = datetime(ano, 1, 1).date()
        eff_ini = max(inicio_ano, dt_inicio)
        if dt_fim < eff_ini:
            return 0
        avos = 0
        for m in range(1, dt_fim.month + 1):
            import calendar
            m_ini = datetime(ano, m, 1).date()
            m_fim = datetime(ano, m, calendar.monthrange(ano, m)[1]).date()
            if eff_ini > m_fim or dt_fim < m_ini:
                continue
            d_trab = (min(dt_fim, m_fim) - max(eff_ini, m_ini)).days + 1
            if d_trab >= 15:
                avos += 1
        return min(12, avos)

    def _calcular_rescisao_detalhada(
        self,
        cur,
        colab: Dict[str, Any],
        tipo_norm: str,
        data_afastamento: str,
        tipo_aviso: str,
        saldo_salario_dias: int,
        ferias_vencidas_dias: int,
        meses_trabalhados_ano: int,
        saldo_fgts: Any,
        dias_restantes_contrato_prazo: int = 0,
        desconto_faltas_valor: Any = Decimal("0.00"),
        incluir_medias_variaveis: bool = True,
    ) -> Dict[str, Any]:
        p = self._p()
        cid = int(colab["id"])
        sb = to_d(colab["salario_base"])
        dt_adm = datetime.strptime(str(colab["data_admissao"])[:10], "%Y-%m-%d").date()
        dt_afast = datetime.strptime(str(data_afastamento)[:10], "%Y-%m-%d").date()

        # Médias de variáveis dos últimos 12 meses na folha (RF-109)
        media_vars = Decimal("0.00")
        if incluir_medias_variaveis:
            cur.execute(
                f"""
                SELECT COALESCE(SUM(fi.valor_total), 0)
                FROM folhas_pagamento f
                JOIN folha_itens fi ON fi.folha_id = f.id
                WHERE f.colaborador_id = {p} AND fi.tipo = 'provento'
                  AND fi.codigo_evento NOT IN ('0001','0002','0100','0101','0102','0103','0110','0111');
            """,
                (cid,),
            )
            soma_var = to_d(cur.fetchone()[0] or 0.0)
            if soma_var > 0:
                media_vars = round2(soma_var / Decimal("12.00"))

        remuneracao = sb + media_vars
        valor_dia = remuneracao / Decimal("30.00")

        # Lei 12.506/2011: 30 + 3 dias por ano completo até 90 dias (para dispensa sem justa causa / indireta / acordo / culpa recíproca)
        anos_completos = max(0, (dt_afast - dt_adm).days // 365)
        dias_aviso = min(90, 30 + (anos_completos * 3)) if tipo_norm in ("sem_justa_causa", "rescisao_indireta", "acordo_484a", "culpa_reciproca") else 0

        tipo_aviso_norm = str(tipo_aviso or "indenizado").strip().lower()
        projecao_dt = dt_afast + timedelta(days=dias_aviso) if (tipo_aviso_norm == "indenizado" and dias_aviso > 0) else dt_afast

        # Avos 13º considerando projeção do aviso prévio indenizado (Súmula 182/OJ 82 SDI-1 TST)
        avos_13 = int(meses_trabalhados_ano) if meses_trabalhados_ano else self._contar_avos_data(dt_adm, projecao_dt)
        avos_13 = max(0, min(12, avos_13))

        # Avos férias proporcionais do ciclo aquisitivo corrente (com projeção do aviso)
        if meses_trabalhados_ano:
            avos_fer_prop = max(0, min(12, int(meses_trabalhados_ano)))
        else:
            dias_desde_adm = max(0, (projecao_dt - dt_adm).days)
            resto_dias = dias_desde_adm % 365
            avos_fer_prop = min(12, (resto_dias // 30) + (1 if (resto_dias % 30) >= 15 else 0))

        # Buscar saldo real de férias vencidas e em dobro em periodos_aquisitivos quando não informado manualmente
        fer_venc_val = Decimal("0.00")
        fer_venc_dobro = Decimal("0.00")
        terco_venc = Decimal("0.00")
        if ferias_vencidas_dias and int(ferias_vencidas_dias) > 0:
            fer_venc_val = round2(Decimal(str(int(ferias_vencidas_dias))) * valor_dia)
            terco_venc = round2(fer_venc_val / Decimal("3.00"))
        else:
            cur.execute(
                f"SELECT saldo_dias, limite_concessivo, fim_aquisitivo FROM periodos_aquisitivos WHERE colaborador_id = {p} AND saldo_dias > 0 AND fim_aquisitivo <= {p};",
                (cid, dt_afast.isoformat()),
            )
            for pa_row in fetchall_dict(cur, self.db_path):
                sd = int(pa_row.get("saldo_dias") or 0)
                if sd <= 0:
                    continue
                v_pa = round2(Decimal(str(sd)) * valor_dia)
                t_pa = round2(v_pa / Decimal("3.00"))
                if dt_afast.isoformat() > str(pa_row.get("limite_concessivo") or "9999-12-31")[:10]:
                    fer_venc_dobro += v_pa
                    terco_venc += round2(t_pa * Decimal("2.00"))
                else:
                    fer_venc_val += v_pa
                    terco_venc += t_pa

        saldo_dias = int(saldo_salario_dias) if saldo_salario_dias else min(30, dt_afast.day)
        saldo_salario = round2(Decimal(str(saldo_dias)) * valor_dia)

        aviso_ind_val = Decimal("0.00")
        desc_aviso_val = Decimal("0.00")
        fer_prop_base = round2((remuneracao / Decimal("12.00")) * Decimal(str(avos_fer_prop)))
        terco_prop = round2(fer_prop_base / Decimal("3.00"))
        decimo_prop_val = round2((remuneracao / Decimal("12.00")) * Decimal(str(avos_13)))

        multa_fgts_perc = Decimal("0.00")
        multa_fgts_val = Decimal("0.00")
        multa_art_479 = Decimal("0.00")
        desconto_art_480 = Decimal("0.00")
        seguro_desemprego = False
        codigo_saque_fgts = "NAO_AUTORIZADO"

        if tipo_norm in ("sem_justa_causa", "rescisao_indireta"):
            if tipo_aviso_norm == "indenizado":
                aviso_ind_val = round2(Decimal(str(dias_aviso)) * valor_dia)
            multa_fgts_perc = Decimal("40.00")
            multa_fgts_val = round2(to_d(saldo_fgts) * Decimal("0.40"))
            seguro_desemprego = True
            codigo_saque_fgts = "01"
        elif tipo_norm == "acordo_484a":
            if tipo_aviso_norm == "indenizado":
                aviso_ind_val = round2((Decimal(str(dias_aviso)) * valor_dia) * Decimal("0.50"))
            multa_fgts_perc = Decimal("20.00")
            multa_fgts_val = round2(to_d(saldo_fgts) * Decimal("0.20"))
            codigo_saque_fgts = "07"
        elif tipo_norm == "culpa_reciproca":
            # CLT art. 484, Súmula 14 do TST e Lei 8.036/90 art. 18 § 2º (RN-059):
            # - Aviso prévio indenizado: 50%
            # - 13º proporcional: 50%
            # - Férias proporcionais + 1/3: 50%
            # - Saldo de salário e férias vencidas: integrais (100%)
            # - Multa FGTS: 20%
            # - Saque FGTS: código 02 autorizado
            # - Seguro-desemprego: não tem direito (False)
            if tipo_aviso_norm == "indenizado":
                aviso_ind_val = round2((Decimal(str(dias_aviso)) * valor_dia) * Decimal("0.50"))
            fer_prop_base = round2(fer_prop_base * Decimal("0.50"))
            terco_prop = round2(terco_prop * Decimal("0.50"))
            decimo_prop_val = round2(decimo_prop_val * Decimal("0.50"))
            multa_fgts_perc = Decimal("20.00")
            multa_fgts_val = round2(to_d(saldo_fgts) * Decimal("0.20"))
            codigo_saque_fgts = "02"
            seguro_desemprego = False
        elif tipo_norm == "pedido_demissao":
            if tipo_aviso_norm == "indenizado":
                desc_aviso_val = round2(Decimal("30") * valor_dia)
        elif tipo_norm == "com_justa_causa":
            # Justa causa perde aviso prévio, férias proporcionais, 13º proporcional e multa FGTS (mantém apenas saldo + férias vencidas)
            fer_prop_base = Decimal("0.00")
            terco_prop = Decimal("0.00")
            decimo_prop_val = Decimal("0.00")
        elif tipo_norm == "termino_experiencia":
            codigo_saque_fgts = "04"
        elif tipo_norm == "rescisao_antecipada_empregador":
            # Art. 479 CLT: indenização de 50% dos dias faltantes do contrato a prazo
            multa_art_479 = round2((Decimal(str(max(0, int(dias_restantes_contrato_prazo)))) * valor_dia) * Decimal("0.50"))
            multa_fgts_perc = Decimal("40.00")
            multa_fgts_val = round2(to_d(saldo_fgts) * Decimal("0.40"))
            seguro_desemprego = True
            codigo_saque_fgts = "01"
        elif tipo_norm == "rescisao_antecipada_empregado":
            # Art. 480 CLT: desconto limitado a 50% dos dias faltantes
            desconto_art_480 = round2((Decimal(str(max(0, int(dias_restantes_contrato_prazo)))) * valor_dia) * Decimal("0.50"))
        elif tipo_norm == "falecimento":
            # Falecimento: dependentes recebem saldo, 13º prop, férias vencidas e proporcionais + 1/3 e saque integral FGTS (sem aviso e sem multa 40%)
            codigo_saque_fgts = "23"

        total_fer_venc = fer_venc_val + fer_venc_dobro + terco_venc
        total_fer_prop = fer_prop_base + terco_prop

        total_proventos = round2(
            saldo_salario + aviso_ind_val + total_fer_venc + total_fer_prop + decimo_prop_val + multa_art_479
        )

        # Tributação legal com tabela vigente da competência do desligamento
        tab_vig = TabelasLegaisService(db_path=self.db_path).obter_tabela_vigente(dt_afast.isoformat()[:7])
        cur.execute(f"SELECT COUNT(*) FROM dependentes WHERE colaborador_id = {p} AND COALESCE(eh_dependente_irrf, 1) = 1;", (cid,))
        dep_irrf = int(cur.fetchone()[0] or 0)

        inss_saldo, _, _, _ = calcular_inss_progressivo(
            saldo_salario,
            tabela_faixas=tab_vig["tabela_inss_tuples"],
            teto_maximo=Decimal(str(tab_vig["teto_inss"])),
            teto_contribuicao=Decimal(str(tab_vig["teto_contribuicao_inss"])),
        )
        inss_13, _, _, _ = calcular_inss_progressivo(
            decimo_prop_val,
            tabela_faixas=tab_vig["tabela_inss_tuples"],
            teto_maximo=Decimal(str(tab_vig["teto_inss"])),
            teto_contribuicao=Decimal(str(tab_vig["teto_contribuicao_inss"])),
        )
        total_inss = round2(inss_saldo + inss_13)

        irrf_saldo, _, _ = calcular_irrf_progressivo(
            base_bruta_irrf=saldo_salario,
            desconto_inss=inss_saldo,
            numero_dependentes=dep_irrf,
            deducao_por_dependente=Decimal(str(tab_vig["deducao_dependente_irrf"])),
            tabela_faixas=tab_vig["tabela_irrf_tuples"],
            desconto_simplificado=Decimal(str(tab_vig["desconto_simplificado_irrf"])),
            aplicar_reducao_lei_15270=bool(tab_vig.get("lei_15270_ativa", 1)),
        )
        irrf_13, _, _ = calcular_irrf_progressivo(
            base_bruta_irrf=decimo_prop_val,
            desconto_inss=inss_13,
            numero_dependentes=dep_irrf,
            deducao_por_dependente=Decimal(str(tab_vig["deducao_dependente_irrf"])),
            tabela_faixas=tab_vig["tabela_irrf_tuples"],
            desconto_simplificado=Decimal(str(tab_vig["desconto_simplificado_irrf"])),
            aplicar_reducao_lei_15270=bool(tab_vig.get("lei_15270_ativa", 1)),
        )
        total_irrf = round2(irrf_saldo + irrf_13)

        desc_faltas = round2(to_d(desconto_faltas_valor))
        total_descontos = round2(total_inss + total_irrf + desc_aviso_val + desconto_art_480 + desc_faltas)
        liquido = max(Decimal("0.00"), round2(total_proventos - total_descontos))
        dt_limite = (dt_afast + timedelta(days=10)).isoformat()

        return {
            "tipo_rescisao": tipo_norm,
            "tipo_aviso": tipo_aviso_norm,
            "dias_aviso_previo": dias_aviso,
            "projecao_aviso_fim": projecao_dt.isoformat(),
            "saldo_salario_dias": saldo_dias,
            "saldo_salario": saldo_salario,
            "aviso_previo_indenizado": aviso_ind_val,
            "desconto_aviso_previo": round2(desc_aviso_val + desconto_art_480),
            "desconto_art_480": desconto_art_480,
            "multa_art_479": multa_art_479,
            "media_variaveis": media_vars,
            "ferias_vencidas_base": fer_venc_val,
            "ferias_vencidas_dobro": fer_venc_dobro,
            "terco_ferias_vencidas": terco_venc,
            "ferias_vencidas_com_terco": round2(total_fer_venc),
            "ferias_prop_avos": avos_fer_prop,
            "ferias_prop_base": fer_prop_base,
            "terco_ferias_prop": terco_prop,
            "ferias_proporcionais_com_terco": round2(total_fer_prop),
            "decimo_prop_avos": avos_13,
            "decimo_terceiro_proporcional": decimo_prop_val,
            "multa_fgts_percentual": float(multa_fgts_perc),
            "multa_fgts_valor": multa_fgts_val,  # GRRF separada (não soma no líquido salarial)
            "desconto_inss": total_inss,
            "desconto_irrf": total_irrf,
            "desconto_faltas": desc_faltas,
            "total_proventos": total_proventos,
            "total_descontos": total_descontos,
            "valor_liquido": liquido,
            "seguro_desemprego_elegivel": seguro_desemprego,
            "codigo_saque_fgts": codigo_saque_fgts,
            "data_limite_pagamento": dt_limite,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # RF-106 a RF-114 / RF-119: Registrar / Simular Rescisão
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
        tipo_raw = str(tipo_rescisao or "sem_justa_causa").strip().lower()
        tipo_norm = MODALIDADES_CANONICAS.get(tipo_raw)
        if not tipo_norm:
            raise PlataformaValidacaoException(f"Modalidade rescisória inválida: '{tipo_rescisao}'.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM colaboradores WHERE id = {p};", (int(colaborador_id),))
            colab = fetchone_dict(cur, self.db_path)
            if not colab:
                raise PlataformaRecursoNaoEncontradoException("Colaborador não encontrado.")
            if colab["situacao"] in ("inativo", "desligado"):
                raise PlataformaValidacaoException("Colaborador já se encontra inativo / rescindido.")

            # RF-106: Trava de Estabilidade Provisória (antes da checagem de afastamento ativo!)
            cur.execute(
                f"""
                SELECT estabilidade_fim, tipo FROM afastamentos
                WHERE colaborador_id = {p} AND estabilidade_fim >= {p}
                ORDER BY estabilidade_fim DESC LIMIT 1;
            """,
                (int(colaborador_id), data_afastamento),
            )
            estab = fetchone_dict(cur, self.db_path)
            if estab and tipo_norm in ("sem_justa_causa", "acordo_484a", "rescisao_antecipada_empregador", "culpa_reciproca"):
                raise PlataformaValidacaoException(
                    f"Atenção: Colaborador possui ESTABILIDADE PROVISÓRIA ATIVA até {estab['estabilidade_fim']} decorrente de {estab['tipo']}. Rescisão bloqueada (RF-106)."
                )

            # Verificar afastamento em aberto (impede dispensa arbitrária durante licença previdenciária/maternidade)
            cur.execute(
                f"SELECT id, tipo FROM afastamentos WHERE colaborador_id = {p} AND data_retorno_efetivo IS NULL ORDER BY id DESC LIMIT 1;",
                (int(colaborador_id),),
            )
            af_aberto = fetchone_dict(cur, self.db_path)
            if af_aberto and tipo_norm in ("sem_justa_causa", "acordo_484a", "termino_experiencia", "rescisao_antecipada_empregador", "culpa_reciproca"):
                raise PlataformaValidacaoException(
                    f"Colaborador possui afastamento ativo ({af_aberto['tipo']}) sem retorno registrado. Registre o retorno antes do desligamento."
                )

            # RF-114: Verificação de ASO Demissional (NR-07) em sst_asos
            cur.execute(
                f"""
                SELECT * FROM sst_asos
                WHERE colaborador_id = {p} AND LOWER(tipo_aso) LIKE '%demissional%'
                  AND LOWER(resultado) = 'apto'
                ORDER BY id DESC LIMIT 1;
            """,
                (int(colaborador_id),),
            )
            aso_dem = fetchone_dict(cur, self.db_path)
            if exigir_aso_demissional and not aso_dem and tipo_norm != "falecimento":
                raise PlataformaValidacaoException(
                    "Bloqueio NR-07 / RF-114: ASO Demissional APTO é obrigatório para efetivar o desligamento."
                )

            calc = self._calcular_rescisao_detalhada(
                cur=cur,
                colab=colab,
                tipo_norm=tipo_norm,
                data_afastamento=data_afastamento,
                tipo_aviso=tipo_aviso,
                saldo_salario_dias=saldo_salario_dias,
                ferias_vencidas_dias=ferias_vencidas_dias,
                meses_trabalhados_ano=meses_trabalhados_ano,
                saldo_fgts=saldo_fgts,
                dias_restantes_contrato_prazo=dias_restantes_contrato_prazo,
                desconto_faltas_valor=desconto_faltas_valor,
                incluir_medias_variaveis=incluir_medias_variaveis,
            )

            dados_resumo = {
                "saldo_salario": float(calc["saldo_salario"]),
                "aviso_previo_valor": float(calc["aviso_previo_indenizado"]),
                "dias_aviso_previo": calc["dias_aviso_previo"],
                "projecao_aviso_fim": calc["projecao_aviso_fim"],
                "decimo_terceiro_proporcional": float(calc["decimo_terceiro_proporcional"]),
                "ferias_totais": float(to_d(calc["ferias_vencidas_com_terco"]) + to_d(calc["ferias_proporcionais_com_terco"])),
                "percentual_multa_fgts": calc["multa_fgts_percentual"],
                "multa_fgts": float(calc["multa_fgts_valor"]),
                "desconto_inss": float(calc["desconto_inss"]),
                "desconto_irrf": float(calc["desconto_irrf"]),
                "data_limite_pagamento": calc["data_limite_pagamento"],
                "total_rescisao_liquido": float(calc["valor_liquido"]),
                "aso_demissional_presente": bool(aso_dem),
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

            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            emp = self._empresa_colab(cur, emp_id)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            memoria_json = json.dumps({k: (float(v) if isinstance(v, Decimal) else v) for k, v in calc.items()}, ensure_ascii=False)

            sql_pg = f"""
                INSERT INTO rescisoes (
                    empresa_id, colaborador_id, tipo_rescisao, data_comunicacao, data_afastamento,
                    tipo_aviso_previo, tipo_aviso, dias_aviso_previo, dias_aviso, projecao_aviso_fim,
                    saldo_salario_dias, saldo_salario_valor, aviso_indenizado_valor,
                    ferias_vencidas_valor, ferias_vencidas_dobro, terco_ferias_vencidas,
                    ferias_prop_dias, ferias_prop_valor, terco_ferias_prop,
                    decimo_prop_avos, decimo_prop_valor, media_variaveis, outros_proventos,
                    saldo_fgts_informado, multa_fgts_percentual, multa_fgts_valor,
                    total_proventos, desconto_inss, desconto_irrf, desconto_aviso_previo, desconto_faltas,
                    total_descontos, valor_liquido, data_limite_pagamento, seguro_desemprego_gerado,
                    trct_gerado, aso_demissional_id, status, memoria_calculo_json, criado_por, criado_em
                ) VALUES ({','.join([p]*35)}, 1, {p}, 'calculada', {p}, {p}, {p}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO rescisoes (
                    empresa_id, colaborador_id, tipo_rescisao, data_comunicacao, data_afastamento,
                    tipo_aviso_previo, tipo_aviso, dias_aviso_previo, dias_aviso, projecao_aviso_fim,
                    saldo_salario_dias, saldo_salario_valor, aviso_indenizado_valor,
                    ferias_vencidas_valor, ferias_vencidas_dobro, terco_ferias_vencidas,
                    ferias_prop_dias, ferias_prop_valor, terco_ferias_prop,
                    decimo_prop_avos, decimo_prop_valor, media_variaveis, outros_proventos,
                    saldo_fgts_informado, multa_fgts_percentual, multa_fgts_valor,
                    total_proventos, desconto_inss, desconto_irrf, desconto_aviso_previo, desconto_faltas,
                    total_descontos, valor_liquido, data_limite_pagamento, seguro_desemprego_gerado,
                    trct_gerado, aso_demissional_id, status, memoria_calculo_json, criado_por, criado_em
                ) VALUES ({','.join([p]*35)}, 1, {p}, 'calculada', {p}, {p}, {p});
            """
            params = (
                emp_id, int(colaborador_id), tipo_norm, agora[:10], data_afastamento,
                calc["tipo_aviso"], calc["tipo_aviso"], calc["dias_aviso_previo"], calc["dias_aviso_previo"], calc["projecao_aviso_fim"],
                calc["saldo_salario_dias"], float(calc["saldo_salario"]), float(calc["aviso_previo_indenizado"]),
                float(calc["ferias_vencidas_base"]), float(calc["ferias_vencidas_dobro"]), float(calc["terco_ferias_vencidas"]),
                calc["ferias_prop_avos"], float(calc["ferias_prop_base"]), float(calc["terco_ferias_prop"]),
                calc["decimo_prop_avos"], float(calc["decimo_terceiro_proporcional"]), float(calc["media_variaveis"]), float(calc["multa_art_479"]),
                float(to_d(saldo_fgts)), calc["multa_fgts_percentual"], float(calc["multa_fgts_valor"]),
                float(calc["total_proventos"]), float(calc["desconto_inss"]), float(calc["desconto_irrf"]),
                float(calc["desconto_aviso_previo"]), float(calc["desconto_faltas"]),
                float(calc["total_descontos"]), float(calc["valor_liquido"]), calc["data_limite_pagamento"],
                1 if calc["seguro_desemprego_elegivel"] else 0,
                int(aso_dem["id"]) if aso_dem else None,
                memoria_json, usuario, agora,
            )
            resc_id = insert_returning_id(cur, conn, sql_pg, sql_sq, params, self.db_path)

            # Inativa o vínculo do colaborador (compatibilidade RF-004 / RT-02)
            cur.execute(
                f"UPDATE colaboradores SET situacao = 'inativo', atualizado_em = {p} WHERE id = {p};",
                (agora, int(colaborador_id)),
            )

            # Histórico inicial
            cur.execute(
                f"""
                INSERT INTO rescisoes_historico (empresa_id, rescisao_id, acao, status_anterior, status_novo, detalhes, usuario, criado_em)
                VALUES ({','.join([p]*8)});
            """,
                (emp_id, resc_id, "calculo_abertura", None, "calculada", f"Rescisão {tipo_norm} líquida R$ {calc['valor_liquido']:.2f} (GRRF FGTS R$ {calc['multa_fgts_valor']:.2f})", usuario, agora),
            )

            # RF-119: Evento eSocial S-2299 em v_S_01_02_00
            resc_payload = {
                "id": resc_id,
                "tipo_rescisao": tipo_norm,
                "data_afastamento": data_afastamento,
                "data_aviso_previo_projetada": calc["projecao_aviso_fim"],
                "data_limite_pagamento": calc["data_limite_pagamento"],
                "total_bruto": float(calc["total_proventos"]),
                "aviso_previo_indenizado": float(calc["aviso_previo_indenizado"]),
            }
            xml_s2299, _ = gerar_xml_s2299(colab, resc_payload, emp.get("cnpj") or "12345678000190")
            ok_xml, _ = validar_xml_esocial_trabalhista("S-2299", xml_s2299) if xml_s2299 else (False, [])
            esoc_id = insert_returning_id(
                cur,
                conn,
                f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({p},'S-2299',{p},'homologacao',{p},{p},{p},{p}) RETURNING id;",
                f"INSERT INTO esocial_eventos (empresa_id, tipo_evento, identificador_origem, ambiente, status, xml_conteudo, criado_por, criado_em) VALUES ({p},'S-2299',{p},'homologacao',{p},{p},{p},{p});",
                (emp_id, f"rescisao:{resc_id}", "validado" if ok_xml else "erro_schema", xml_s2299 or "<eSocial/>", usuario, agora),
                self.db_path,
            )
            cur.execute(f"UPDATE rescisoes SET esocial_evento_id = {p} WHERE id = {p};", (esoc_id, resc_id))

            # Pendência automática prazo art. 477 CLT
            cur.execute(
                f"""
                INSERT INTO pendencias_operacionais (
                    empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                    colaborador_id, prazo_limite, responsavel, status, criado_em
                ) VALUES ({','.join([p]*11)});
            """,
                (
                    emp_id, "Rescisao", "rescisao_prazo",
                    f"Prazo Pagamento Rescisão — {colab['nome_completo']} ({calc['data_limite_pagamento']})",
                    f"Verbas rescisórias líquidas R$ {calc['valor_liquido']:.2f} até {calc['data_limite_pagamento']} (art. 477 CLT).",
                    "critica", int(colaborador_id), calc["data_limite_pagamento"], "Financeiro / DP", "pendente", agora,
                ),
            )

            conn.commit()
            self._auditar(
                "Rescisao", "inclusao", "rescisoes", resc_id, usuario,
                f"Rescisão {tipo_norm} Colab {colaborador_id}: Líquido R$ {calc['valor_liquido']:.2f}, GRRF R$ {calc['multa_fgts_valor']:.2f}.",
            )
            return {
                "sucesso": True,
                "rescisao_id": resc_id,
                "colaborador_nome": colab["nome_completo"],
                "valor_liquido": float(calc["valor_liquido"]),
                "data_limite_pagamento": calc["data_limite_pagamento"],
                "esocial_evento_id": esoc_id,
                "aso_demissional_id": int(aso_dem["id"]) if aso_dem else None,
                "calculo": calc,
                "dados": dados_resumo,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-117 / RF-118: Homologação (RN-080) e Quitação (Multa Art. 477 §8º)
    # ─────────────────────────────────────────────────────────────────────────
    def homologar_rescisao(self, rescisao_id: int, homologador: str, usuario_dp_observacao: str = "") -> Dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM rescisoes WHERE id = {p};", (int(rescisao_id),))
            r = fetchone_dict(cur, self.db_path)
            if not r:
                raise PlataformaRecursoNaoEncontradoException(f"Rescisão #{rescisao_id} não encontrada.")
            if r["status"] in ("homologada", "paga"):
                raise PlataformaValidacaoException(f"Rescisão #{rescisao_id} já se encontra no status '{r['status']}'.")
            if str(r.get("criado_por") or "").strip().lower() == str(homologador or "").strip().lower():
                raise PlataformaAcessoNegadoException("RN-080: Quem abriu/calculou a rescisão não pode homologá-la.")

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            emp_id = r.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            cur.execute(
                f"UPDATE rescisoes SET status = 'homologada', homologado_por = {p}, homologado_em = {p} WHERE id = {p};",
                (homologador, agora, int(rescisao_id)),
            )
            cur.execute(
                f"INSERT INTO rescisoes_historico (empresa_id, rescisao_id, acao, status_anterior, status_novo, detalhes, usuario, criado_em) VALUES ({','.join([p]*8)});",
                (emp_id, int(rescisao_id), "homologacao", r["status"], "homologada", usuario_dp_observacao or "Homologação formal concluída", homologador, agora),
            )
            conn.commit()
            self._auditar("Rescisao", "homologacao", "rescisoes", rescisao_id, homologador, f"Rescisão #{rescisao_id} homologada.")
            return {"sucesso": True, "rescisao_id": int(rescisao_id), "status": "homologada", "homologado_por": homologador}
        finally:
            conn.close()

    def registrar_pagamento_rescisao(self, rescisao_id: int, data_pagamento: str, usuario: str = "Financeiro") -> Dict[str, Any]:
        """RF-118: Quita rescisão e aplica automaticamente multa do art. 477 §8º CLT (1 salário) se paga após prazo de 10 dias."""
        dt_pg = str(data_pagamento or datetime.now().strftime("%Y-%m-%d")).strip()[:10]
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM rescisoes WHERE id = {p};", (int(rescisao_id),))
            r = fetchone_dict(cur, self.db_path)
            if not r:
                raise PlataformaRecursoNaoEncontradoException(f"Rescisão #{rescisao_id} não encontrada.")
            if r["status"] == "paga":
                raise PlataformaValidacaoException("Rescisão já quitada.")

            cur.execute(f"SELECT salario_base FROM colaboradores WHERE id = {p};", (int(r["colaborador_id"]),))
            sal_colab = float(cur.fetchone()[0] or 0.0)
            fora_prazo = dt_pg > str(r["data_limite_pagamento"])[:10]
            multa_477_val = round(sal_colab, 2) if fora_prazo else 0.0
            novo_prov = round(float(r.get("total_proventos") or 0.0) + multa_477_val, 2)
            novo_liq = round(float(r.get("valor_liquido") or 0.0) + multa_477_val, 2)
            emp_id = r.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                f"""
                UPDATE rescisoes
                SET data_pagamento_realizada = {p}, multa_art_477_aplicada = {p},
                    outros_proventos = COALESCE(outros_proventos, 0) + {p},
                    total_proventos = {p}, valor_liquido = {p}, status = 'paga'
                WHERE id = {p};
            """,
                (dt_pg, 1 if fora_prazo else 0, multa_477_val, novo_prov, novo_liq, int(rescisao_id)),
            )
            cur.execute(
                f"INSERT INTO rescisoes_historico (empresa_id, rescisao_id, acao, status_anterior, status_novo, detalhes, usuario, criado_em) VALUES ({','.join([p]*8)});",
                (emp_id, int(rescisao_id), "quitacao", r["status"], "paga", f"Pago em {dt_pg} (multa_art_477={multa_477_val:.2f})", usuario, agora),
            )
            cur.execute(
                f"""
                UPDATE pendencias_operacionais
                SET status = 'resolvida', resolvida_por = {p}, resolvida_em = {p}
                WHERE colaborador_id = {p} AND tipo_pendencia = 'rescisao_prazo' AND status != 'resolvida';
            """,
                (usuario, agora, int(r["colaborador_id"])),
            )
            conn.commit()
            self._auditar("Rescisao", "pagamento", "rescisoes", rescisao_id, usuario, f"Quitação rescisão #{rescisao_id} em {dt_pg}, multa_477={multa_477_val:.2f}.")
            return {
                "sucesso": True,
                "rescisao_id": int(rescisao_id),
                "status": "paga",
                "data_pagamento": dt_pg,
                "multa_art_477_aplicada": fora_prazo,
                "valor_multa_art_477": multa_477_val,
                "valor_liquido_final": novo_liq,
            }
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF-115 / RF-116 / RF-120: PDFs Oficiais (TRCT / FGTS-SD) e Listagem
    # ─────────────────────────────────────────────────────────────────────────
    def gerar_documentos_rescisao_pdf(self, rescisao_id: int, tipo_documento: str = "trct") -> Dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM rescisoes WHERE id = {p};", (int(rescisao_id),))
            r = fetchone_dict(cur, self.db_path)
            if not r:
                raise PlataformaRecursoNaoEncontradoException(f"Rescisão #{rescisao_id} não encontrada.")
            cur.execute(f"SELECT * FROM colaboradores WHERE id = {p};", (int(r["colaborador_id"]),))
            colab = fetchone_dict(cur, self.db_path) or {}
            emp = self._empresa_colab(cur, r.get("empresa_id") or "a0000000-0000-0000-0000-000000000001")
        finally:
            conn.close()

        doc_payload = {
            "id": r["id"],
            "tipo_rescisao": r.get("tipo_rescisao"),
            "data_afastamento": r.get("data_afastamento"),
            "data_aviso_previo_projetada": r.get("projecao_aviso_fim") or r.get("data_afastamento"),
            "data_limite_pagamento": r.get("data_limite_pagamento"),
            "saldo_salario_dias": r.get("saldo_salario_dias"),
            "saldo_salario": r.get("saldo_salario_valor"),
            "decimo_terceiro_proporcional": r.get("decimo_prop_valor"),
            "ferias_proporcionais": r.get("ferias_prop_valor"),
            "terco_ferias_proporcionais": r.get("terco_ferias_prop"),
            "ferias_vencidas": float(r.get("ferias_vencidas_valor") or 0) + float(r.get("ferias_vencidas_dobro") or 0) + float(r.get("terco_ferias_vencidas") or 0),
            "dias_aviso_previo": r.get("dias_aviso_previo"),
            "aviso_previo_indenizado": r.get("aviso_indenizado_valor"),
            "medias_variaveis": r.get("media_variaveis"),
            "multa_art_479": r.get("outros_proventos"),
            "desconto_inss": r.get("desconto_inss"),
            "desconto_irrf": r.get("desconto_irrf"),
            "desconto_aviso_empregado": r.get("desconto_aviso_previo"),
            "total_bruto": r.get("total_proventos"),
            "total_descontos": r.get("total_descontos"),
            "valor_liquido": r.get("valor_liquido"),
            "saldo_fgts": r.get("saldo_fgts_informado"),
            "multa_fgts_percentual": r.get("multa_fgts_percentual"),
            "multa_fgts_valor": r.get("multa_fgts_valor"),
        }
        if str(tipo_documento).lower().strip() in ("fgts", "sd", "fgts_sd", "guias"):
            pdf_bytes = gerar_pdf_guias_fgts_sd(doc_payload, colab, emp)
            nome = f"GUIAS_FGTS_SD_{rescisao_id}.pdf"
        else:
            pdf_bytes = gerar_pdf_trct(doc_payload, colab, emp)
            nome = f"TRCT_{rescisao_id}.pdf"
        return {"sucesso": True, "filename": nome, "pdf_bytes": pdf_bytes}

    def listar_rescisoes(self, empresa_id: Optional[str] = None, colaborador_id: Optional[int] = None) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = """
                SELECT r.*, c.nome_completo, c.matricula, c.cargo, c.setor
                FROM rescisoes r
                JOIN colaboradores c ON c.id = r.colaborador_id
                WHERE 1=1
            """
            params: List[Any] = []
            if empresa_id:
                sql += f" AND COALESCE(r.empresa_id, c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p}"
                params.append(empresa_id.strip())
            if colaborador_id:
                sql += f" AND r.colaborador_id = {p}"
                params.append(int(colaborador_id))
            sql += " ORDER BY r.id DESC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()
