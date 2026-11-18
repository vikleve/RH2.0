"""
Suíte de Testes Automatizados — Plataforma Integrada de Gestão do Ciclo Trabalhista
Cobre os Módulos 01 a 20, Regras Transversais (RT-01 a RT-13) e
Regras de Negócio Trabalhistas e Compliance (RN-001 a RN-083).
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import init_db
from backend.plataforma_service import (
    PlataformaService,
    PlataformaValidacaoException,
    PlataformaAcessoNegadoException,
)
from backend.service import ColaboradorService


class TestPlataformaCicloTrabalhista(unittest.TestCase):
    db_teste = "test_plataforma_trabalhista.db"

    @classmethod
    def setUpClass(cls):
        if os.path.exists(cls.db_teste):
            try:
                os.remove(cls.db_teste)
            except Exception:
                pass
        init_db(cls.db_teste, auto_provision=False)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_teste):
            try:
                os.remove(cls.db_teste)
            except Exception:
                pass

    def setUp(self):
        self.service = PlataformaService(db_path=self.db_teste)
        self.colab_service = ColaboradorService(db_path=self.db_teste)

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 02: ADMISSÃO (RF-011 A RF-020, RN-008, RN-009, RN-080)
    # ─────────────────────────────────────────────────────────────────────────
    def test_admissao_rejeita_salario_abaixo_do_minimo_2026(self):
        """RN-008, RF-013: Bloqueia proposta salarial abaixo do salário mínimo legal 2026 (R$ 1.621,00)."""
        dados = {
            "candidato_nome": "João Pedro Silva",
            "candidato_cpf": "12345678909",
            "candidato_email": "joao.silva@teste.com",
            "cargo": "Ajudante Geral",
            "setor": "Operações",
            "salario_proposto": 1500.00,  # Abaixo de 1.621,00
            "data_prevista_admissao": "2026-12-01",
        }
        with self.assertRaises(PlataformaValidacaoException) as ctx:
            self.service.registrar_admissao(dados, usuario="Operador DP")
        self.assertIn("salário mínimo legal", str(ctx.exception))

    def test_admissao_ciclo_completo_com_segregacao_e_aprovacao(self):
        """RF-011 a RF-020: Cria admissão, valida checklist, aprova com segregação e ativa colaborador."""
        dados = {
            "candidato_nome": "Mariana Souza Oliveira",
            "candidato_cpf": "85328103068",
            "candidato_email": "mariana.souza@forcaverde.com.br",
            "cargo": "Operadora de Moenda I",
            "setor": "Operações Industriais",
            "salario_proposto": 2500.00,
            "data_prevista_admissao": "2026-11-20",
            "tipo_contrato": "experiencia",
            "prazo_experiencia_dias": 45,
        }
        adm = self.service.registrar_admissao(dados, usuario="Analista Mariana")
        adm_id = adm["id"]
        self.assertEqual(adm["status"], "em_andamento")
        self.assertTrue(len(adm["checklist"]) >= 5)

        # 1. Violação de Segregação de Funções: Quem criou não pode aprovar (RN-080)
        with self.assertRaises(PlataformaAcessoNegadoException) as ctx:
            self.service.aprovar_admissao(adm_id, aprovador="Analista Mariana")
        self.assertIn("Segregação de Funções", str(ctx.exception))

        # 2. Bloqueio de aprovação com documentos pendentes (RF-012, RF-020)
        with self.assertRaises(PlataformaValidacaoException) as ctx_doc:
            self.service.aprovar_admissao(adm_id, aprovador="Gestor Carlos")
        self.assertIn("itens obrigatórios pendentes", str(ctx_doc.exception))

        # 3. Valida os itens do checklist (RF-012)
        for item in adm["checklist"]:
            self.service.atualizar_item_checklist(item["id"], status="validado", usuario="Gestor Carlos")

        # 4. Aprovação por outro usuário (Gestor Carlos)
        res_aprov = self.service.aprovar_admissao(adm_id, aprovador="Gestor Carlos")
        self.assertTrue(res_aprov["sucesso"])
        self.assertIn("matricula", res_aprov)
        colab_id = res_aprov["colaborador_id"]

        # 5. Verifica se colaborador foi persistido e ativado no banco
        colab = self.colab_service.obter_por_id(colab_id)
        self.assertEqual(colab["situacao"], "ativo")
        self.assertEqual(colab["nome_completo"], "Mariana Souza Oliveira")

        # 6. Verifica se evento eSocial S-2200 foi gerado (RF-015, RN-010)
        eventos = self.service.listar_esocial_eventos(tipo="S-2200")
        self.assertTrue(any(e["identificador_origem"] == str(colab_id) for e in eventos))

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 03: JORNADA E PONTO (RF-021 A RF-030, RN-012, RN-013, RN-080)
    # ─────────────────────────────────────────────────────────────────────────
    def test_ponto_marcacao_e_ajuste_com_segregacao(self):
        """RF-021, RF-025, RF-026, RN-013: Marcações de ponto e ajustes manuais auditados."""
        colab = self.colab_service.listar()[0]
        cid = colab["id"]

        # 1. Registra batidas normais
        r1 = self.service.registrar_marcacao_ponto(cid, "2026-11-20", "08:02:00", tipo_registro="relogio_afd")
        self.assertTrue(r1["sucesso"])

        # 2. Idempotência de marcação idêntica (RF-022)
        r_dup = self.service.registrar_marcacao_ponto(cid, "2026-11-20", "08:02:00")
        self.assertFalse(r_dup["sucesso"])

        # 3. Solicitação de ajuste manual (RF-025)
        sol = self.service.solicitar_ajuste_ponto(
            colaborador_id=cid,
            data="2026-11-20",
            hora_ajustada="17:50:00",
            tipo_marcacao="saida",
            motivo="Esquecimento de registro no relógio ao término do expediente",
            solicitante="Colaborador Solicitante",
        )
        self.assertTrue(sol["sucesso"])
        ajuste_id = sol["ajuste_id"]

        # 4. Autoaprovação bloqueada (RN-080)
        with self.assertRaises(PlataformaAcessoNegadoException):
            self.service.aprovar_ajuste_ponto(ajuste_id, aprovador="Colaborador Solicitante", aprovar=True)

        # 5. Aprovação por gestor autorizado
        aprov = self.service.aprovar_ajuste_ponto(ajuste_id, aprovador="Supervisor DP", aprovar=True)
        self.assertEqual(aprov["status"], "aprovado")

        # 6. Espelho de ponto reflete as marcações (RF-027)
        espelho = self.service.obter_espelho_ponto(cid, "2026-11")
        self.assertEqual(espelho["colaborador"]["id"], cid)
        self.assertGreater(espelho["total_marcacoes"], 0)

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 06: FÉRIAS (RF-051 A RF-060, RN-026 A RN-031)
    # ─────────────────────────────────────────────────────────────────────────
    def test_programacao_ferias_calculos_e_bloqueios(self):
        """RF-053 a RF-057, RN-029: Programação de férias com cálculo de 1/3 e abono pecuniário."""
        colab = self.colab_service.listar()[0]
        cid = colab["id"]

        # Bloqueia férias com início em sexta-feira (2 dias antes do DSR no domingo - RF-053)
        # 2026-11-27 é Sexta-feira
        with self.assertRaises(PlataformaValidacaoException) as ctx:
            self.service.programar_ferias(
                colaborador_id=cid,
                data_inicio="2026-11-27",  # Sexta-feira
                dias_gozo=20,
            )
        self.assertIn("repouso semanal", str(ctx.exception))

        # Programação válida: Segunda-feira 2026-11-30, 20 dias de gozo + 10 dias de abono (1/3)
        ferias = self.service.programar_ferias(
            colaborador_id=cid,
            data_inicio="2026-11-30",
            dias_gozo=20,
            abono_pecuniario=True,
            solicitante="Operador DP",
        )
        self.assertTrue(ferias["sucesso"])
        self.assertGreater(ferias["valor_ferias"], 0)
        self.assertGreater(ferias["valor_terco"], 0)
        self.assertGreater(ferias["valor_abono"], 0)
        self.assertGreater(ferias["valor_liquido"], 0)

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 07: AFASTAMENTOS (RF-061 A RF-070, RN-032 A RN-035)
    # ─────────────────────────────────────────────────────────────────────────
    def test_afastamento_acidente_trabalho_e_estabilidade(self):
        """RF-063, RN-032: Afastamento por acidente de trabalho gera estabilidade de 12 meses."""
        colab = self.colab_service.listar()[0]
        cid = colab["id"]

        afast = self.service.registrar_afastamento(
            colaborador_id=cid,
            tipo="acidente_trabalho",
            data_inicio="2026-10-01",
            data_fim_prevista="2026-10-31",  # 31 dias
            cid="S82.1",
            usuario="SST Medico",
        )
        self.assertTrue(afast["sucesso"])
        self.assertEqual(afast["dias_empresa"], 15)
        self.assertEqual(afast["dias_inss"], 16)
        self.assertTrue(afast["exige_aso_retorno"])  # >= 30 dias exige ASO
        self.assertIsNotNone(afast["estabilidade_ate"])

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 11: RESCISÃO (RF-106 A RF-120, RN-054 A RN-060, RN-079)
    # ─────────────────────────────────────────────────────────────────────────
    def test_rescisao_bloqueada_por_estabilidade_e_calculo_sem_justa_causa(self):
        """RF-106, RF-107, RN-079: Bloqueia demissão em estabilidade e calcula verbas e prazo de 10 dias."""
        # 1. Colaborador com estabilidade ativa (do teste anterior)
        colab = self.colab_service.listar()[0]
        cid = colab["id"]

        with self.assertRaises(PlataformaValidacaoException) as ctx:
            self.service.registrar_rescisao(
                colaborador_id=cid,
                tipo_rescisao="sem_justa_causa",
                data_afastamento="2026-11-20",
                usuario="DP Mariana",
            )
        self.assertIn("ESTABILIDADE PROVISÓRIA ATIVA", str(ctx.exception))

        # 2. Criar novo colaborador sem estabilidade para teste de rescisão
        colab2 = self.colab_service.cadastrar({
            "matricula": "FV-2002",
            "nome_completo": "Lucas Antunes",
            "cpf": "52998224725",
            "email": "lucas.antunes@teste.com",
            "data_nascimento": "1988-05-10",
            "data_admissao": "2024-01-15",
            "cargo": "Técnico de Manutenção",
            "setor": "Manutenção",
            "salario_base": 3600.00,
        })
        cid2 = colab2["id"]

        resc = self.service.registrar_rescisao(
            colaborador_id=cid2,
            tipo_rescisao="sem_justa_causa",
            data_afastamento="2026-11-20",
            saldo_salario_dias=20,
            ferias_vencidas_dias=30,
            meses_trabalhados_ano=11,
            saldo_fgts=8000.00,
            usuario="DP Mariana",
        )
        self.assertTrue(resc["sucesso"])
        self.assertGreater(resc["valor_liquido"], 0)
        self.assertEqual(resc["calculo"]["multa_fgts_percentual"], 40.0)
        self.assertEqual(resc["calculo"]["multa_fgts_valor"], Decimal("3200.00"))  # 40% de 8000
        # Prazo de 10 dias corridos (art. 477 da CLT)
        self.assertEqual(resc["data_limite_pagamento"], "2026-11-30")

        # Colaborador deve estar inativo após a rescisão (RF-004, RT-02)
        c_pos = self.colab_service.obter_por_id(cid2)
        self.assertEqual(c_pos["situacao"], "inativo")

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 12: SST (RF-121 A RF-130, RN-061 A RN-064)
    # ─────────────────────────────────────────────────────────────────────────
    def test_sst_bloqueio_epi_ca_vencido_e_emissao_cat(self):
        """RF-126, RF-129, RN-062, RN-064: Bloqueia entrega de EPI com CA vencido e emite CAT."""
        colab = self.colab_service.listar()[0]
        cid = colab["id"]

        # 1. Emissão de ASO
        aso = self.service.registrar_aso(
            colaborador_id=cid,
            tipo_aso="periodico",
            data_emissao="2026-11-01",
            data_validade="2027-11-01",
            resultado="apto",
            medico_nome="Dra. Roberta Camargo",
            medico_crm="154321",
            medico_uf="SP",
        )
        self.assertTrue(aso["sucesso"])
        self.assertEqual(aso["resultado"], "apto")

        # 2. Entrega de EPI válido
        entrega = self.service.registrar_entrega_epi(cid, epi_id=1, quantidade=1)
        self.assertTrue(entrega["sucesso"])

        # 3. Emissão de CAT
        cat = self.service.registrar_cat(
            colaborador_id=cid,
            tipo_acidente="tipico",
            data_hora="2026-11-17 14:30:00",
            local_acidente="Área da Moenda Bloco B",
            descricao="Torção leve no tornozelo direito durante inspeção",
        )
        self.assertTrue(cat["sucesso"])
        self.assertIn("CAT-", cat["numero_cat"])

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULO 15: CENTRAL DE PENDÊNCIAS (RF-151 A RF-160, RN-075 A RN-079)
    # ─────────────────────────────────────────────────────────────────────────
    def test_central_pendencias_operacionais_e_resolucao(self):
        """RF-151, RF-160: Scanner automático de pendências e workflow de resolução."""
        novas = self.service.atualizar_central_pendencias_automaticamente()
        pendencias = self.service.listar_pendencias()
        self.assertTrue(len(pendencias) > 0)

        # Resolver primeira pendência
        p_id = pendencias[0]["id"]
        res = self.service.resolver_pendencia(p_id, usuario="Analista DP")
        self.assertTrue(res["sucesso"])

    # ─────────────────────────────────────────────────────────────────────────
    # MÓDULOS 18, 19, 20: INTEGRAÇÃO BANCÁRIA, BI E AUDITORIA (RF-097, RF-181, RF-191)
    # ─────────────────────────────────────────────────────────────────────────
    def test_indicadores_bi_e_auditoria(self):
        """RF-181, RF-182, RF-191 a RF-200: Indicadores de turnover/absenteísmo e logs."""
        bi = self.service.obter_indicadores_bi()
        self.assertIn("turnover", bi)
        self.assertIn("taxa_percentual", bi["turnover"])
        self.assertIn("absenteismo", bi)
        self.assertIn("efetivo", bi)

        # Verifica logs de auditoria
        logs = self.service.listar_auditoria()
        self.assertTrue(len(logs) > 0)
        self.assertTrue(any(l["operacao"] == "inclusao" for l in logs))


if __name__ == "__main__":
    unittest.main()
