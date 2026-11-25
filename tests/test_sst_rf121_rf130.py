# -*- coding: utf-8 -*-
"""
Testes Automatizados para os Requisitos Funcionais de SST (RF-121 a RF-130)
- RF-121: Cadastro de Exames Ocupacionais (Catálogo, Periodicidade e CRUD)
- RF-122: Exame Admissional (Validação pré-admissão, ASO e Aptidão)
- RF-123: Exame Periódico (Agendamento e Periodicidade NR-07)
- RF-124: Exame Demissional (Prazos 10 dias e Regra de Dispensa NR-07)
- RF-125: Controle de ASO (Médico CRM/UF, Anexo com Hash SHA-256 e RBAC)
- RF-126: Controle de EPI (Catálogo, Bloqueio de CA Vencido, Devolução e Substituição)
- RF-127: Treinamentos Obrigatórios NRs (NR-05, NR-06, NR-10, NR-35 e Reciclagens)
- RF-128: Alertas de Vencimento Proativos (ASO, EPI e Treinamentos)
- RF-129: CAT (Comunicação de Acidente de Trabalho, CID-10 e Histórico)
- RF-130: Integração SST eSocial (Geração oficial S-2210, S-2220 e S-2240)
"""
import os
import sys
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.database import init_db
from backend.plataforma_exceptions import (
    PlataformaRecursoNaoEncontradoException,
    PlataformaValidacaoException,
)
from backend.sst_service import SSTService


class TestSSTRF121RF130(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        init_db(self.db_path, auto_provision=False)
        self.service = SSTService(db_path=self.db_path)

        # Insere colaborador de teste
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO colaboradores (
                empresa_id, matricula, nome_completo, cpf, email, data_nascimento, cargo, setor,
                salario_base, data_admissao, situacao, criado_em, atualizado_em
            ) VALUES (
                'a0000000-0000-0000-0000-000000000001', 'SST-001', 'Carlos Silva SST',
                '11122233344', 'carlos.sst@empresa.com', '1990-05-15', 'Operador de Máquinas', 'Operações',
                3500.00, '2026-02-01', 'ativo', '2026-02-01 08:00:00', '2026-02-01 08:00:00'
            );
        """
        )
        self.colaborador_id = cur.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_rf121_catalogo_exames_crud(self):
        """RF-121: Cadastro, listagem, atualização e exclusão lógica de exames ocupacionais."""
        # 1. Cadastro
        res = self.service.cadastrar_exame(
            codigo="AUD-01",
            descricao="Audiometria Tonal e Vocal",
            tipo="audiometria",
            periodicidade_meses=6,
        )
        self.assertTrue(res["sucesso"])
        exame_id = res["exame_id"]

        # 2. Listagem
        exames = self.service.listar_exames()
        codigos = [e["codigo"] for e in exames]
        self.assertIn("AUD-01", codigos)

        # 3. Atualização
        upd = self.service.atualizar_exame(
            exame_id=exame_id,
            dados={"descricao": "Audiometria Ocupacional Completa", "periodicidade_meses": 12},
        )
        self.assertTrue(upd["sucesso"])

        # 4. Inativação lógica
        inativ = self.service.inativar_exame(exame_id=exame_id)
        self.assertTrue(inativ["sucesso"])
        self.assertFalse(inativ["ativo"])

        # Não deve aparecer em apenas_ativos=True
        exames_ativos = self.service.listar_exames(apenas_ativos=True)
        self.assertNotIn("AUD-01", [e["codigo"] for e in exames_ativos])

    def test_rf122_exame_admissional_validacoes(self):
        """RF-122, RN-009: Exame Admissional com validação de realização prévia à admissão."""
        # Sucesso: Realizado antes da admissão
        res_ok = self.service.registrar_exame_admissional(
            colaborador_id=self.colaborador_id,
            data_realizacao="2026-01-28",
            resultado="APTO",
            medico_nome="Dr. Roberto Médico",
            medico_crm="123456",
            medico_uf="SP",
            data_admissao="2026-02-01",
        )
        self.assertTrue(res_ok["sucesso"])
        self.assertEqual(res_ok["resultado"], "APTO")

        # Violação RN-009 / NR-07: Realizado APÓS a data de admissão
        with self.assertRaises(PlataformaValidacaoException) as ctx:
            self.service.registrar_exame_admissional(
                colaborador_id=self.colaborador_id,
                data_realizacao="2026-02-05",
                resultado="APTO",
                medico_nome="Dr. Roberto Médico",
                medico_crm="123456",
                medico_uf="SP",
                data_admissao="2026-02-01",
            )
        self.assertIn("RN-009", str(ctx.exception))

    def test_rf123_exame_periodico_agendamento(self):
        """RF-123: Agendamento preventivo de exames periódicos com base na NR-07."""
        agend = self.service.agendar_exame_periodico(
            colaborador_id=self.colaborador_id,
            exame_id=None,
            data_prevista="2027-01-28",
            clinica_nome="Medicina do Trabalho Alpha",
            observacoes="Periódico anual NR-07",
        )
        self.assertTrue(agend["sucesso"])
        self.assertEqual(agend["status"], "agendado")
        self.assertEqual(agend["data_prevista"], "2027-01-28")

    def test_rf124_exame_demissional_dispensa_e_prazos(self):
        """RF-124, NR-07: Verificação de dispensa por exame recente e prazo de 10 dias."""
        # 1. Registra ASO realizado há 40 dias
        dt_aso = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
        self.service.registrar_aso(
            colaborador_id=self.colaborador_id,
            tipo_aso="PERIODICO",
            data_emissao=dt_aso,
            data_validade="2027-01-01",
            resultado="APTO",
            medico_nome="Dr. Examinador",
            medico_crm="99988",
            medico_uf="SP",
        )

        # Para grau de risco 2 (limite 135 dias), deve ser dispensado
        hoje = datetime.now().strftime("%Y-%m-%d")
        disp = self.service.verificar_dispensa_exame_demissional(
            colaborador_id=self.colaborador_id,
            data_demissao=hoje,
            grau_risco=2,
        )
        self.assertTrue(disp["dispensado"])
        self.assertIn("Dispensado conforme NR-07", disp["motivo"])

        # 2. Agendamento com validação do prazo de até 10 dias da demissão
        # Sucesso: agendado para 5 dias após demissão
        dt_agend_ok = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        agend_ok = self.service.agendar_exame_demissional(
            colaborador_id=self.colaborador_id,
            data_demissao=hoje,
            data_prevista=dt_agend_ok,
        )
        self.assertTrue(agend_ok["sucesso"])

        # Falha: agendado para 15 dias após demissão (ultrapassa prazo legal de 10 dias)
        dt_agend_tarde = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        with self.assertRaises(PlataformaValidacaoException) as ctx:
            self.service.agendar_exame_demissional(
                colaborador_id=self.colaborador_id,
                data_demissao=hoje,
                data_prevista=dt_agend_tarde,
            )
        self.assertIn("10 dias", str(ctx.exception))

    def test_rf125_controle_aso_rbac_e_anexos(self):
        """RF-125: Controle de ASO com anexo hash SHA-256 e RBAC médico."""
        res = self.service.registrar_aso(
            colaborador_id=self.colaborador_id,
            tipo_aso="PERIODICO",
            data_emissao="2026-03-01",
            data_validade="2027-03-01",
            resultado="APTO",
            medico_nome="Dra. Mariana Sanitarista",
            medico_crm="77665",
            medico_uf="MG",
            observacoes="Apto sem restrições ocupacionais.",
            conteudo_base64="RG9jdW1lbnRvIEFTTyBTaW50ZXRpY28=",
            nome_arquivo="aso_carlos.pdf",
        )
        self.assertTrue(res["sucesso"])
        aso_id = res["aso_id"]

        # Consulta com perfil médico: vê observações completas
        aso_medico = self.service.consultar_aso(aso_id=aso_id, perfil_usuario="medico_sst")
        self.assertEqual(aso_medico["observacoes_medicas"], "Apto sem restrições ocupacionais.")
        self.assertIsNotNone(aso_medico["sha256_hash"])

        # Consulta com perfil não-médico (ex: gestor comum): observações sensíveis são mascaradas
        aso_gestor = self.service.consultar_aso(aso_id=aso_id, perfil_usuario="gestor")
        self.assertIn("SIGILO MÉDICO", aso_gestor["observacoes_medicas"])

    def test_rf126_epi_entrega_bloqueio_ca_vencido_devolucao_e_troca(self):
        """RF-126, RN-062: Gestão de EPI, bloqueio de CA expirado, devolução e substituição."""
        # 1. Cadastro de EPI com CA válido
        epi_valido = self.service.cadastrar_epi(
            codigo="LUVA-01",
            descricao="Luva Nitrílica Anticorte",
            ca_numero="44550",
            ca_validade="2028-12-31",
            vida_util_dias=90,
        )
        self.assertTrue(epi_valido["sucesso"])
        epi_valido_id = epi_valido["epi_id"]

        # 2. Cadastro de EPI com CA já VENCIDO
        epi_vencido = self.service.cadastrar_epi(
            codigo="PROT-01",
            descricao="Protetor Auricular Tipo Concha",
            ca_numero="11220",
            ca_validade="2025-01-01",  # Vencido
            vida_util_dias=180,
        )
        epi_vencido_id = epi_vencido["epi_id"]

        # 3. Entrega de EPI válido: Sucesso e cálculo de próxima troca (+90 dias)
        entrega = self.service.registrar_entrega_epi(
            colaborador_id=self.colaborador_id,
            epi_id=epi_valido_id,
            quantidade=2,
            data_entrega="2026-02-01",
        )
        self.assertTrue(entrega["sucesso"])
        self.assertEqual(entrega["proxima_troca"], "2026-05-02")
        entrega_id = entrega["entrega_id"]

        # 4. Entrega de EPI com CA vencido: DEVE SER BLOQUEADA com RN-062
        with self.assertRaises(PlataformaValidacaoException) as ctx:
            self.service.registrar_entrega_epi(
                colaborador_id=self.colaborador_id,
                epi_id=epi_vencido_id,
                quantidade=1,
                data_entrega="2026-02-01",
            )
        self.assertIn("RN-062", str(ctx.exception))
        self.assertIn("VENCIDO", str(ctx.exception))

        # 5. Devolução de EPI
        dev = self.service.registrar_devolucao_epi(
            entrega_id=entrega_id,
            data_devolucao="2026-05-01",
            motivo="desgaste_natural",
        )
        self.assertTrue(dev["sucesso"])
        self.assertEqual(dev["status"], "devolvido")

        # 6. Substituição de EPI
        subst = self.service.registrar_substituicao_epi(
            entrega_anterior_id=entrega_id,
            novo_epi_id=epi_valido_id,
            motivo_troca="troca_preventiva",
        )
        self.assertTrue(subst["sucesso"])
        self.assertEqual(subst["status"], "ativo")

    def test_rf127_treinamentos_obrigatorios_reciclagem(self):
        """RF-127: Catálogo de NRs e registro de participação com cálculo de reciclagem."""
        trein = self.service.cadastrar_treinamento(
            codigo="NR-35-ALT",
            nome="Trabalho em Altura NR-35",
            nr_norma="NR-35",
            carga_horaria=8,
            validade_meses=24,
        )
        self.assertTrue(trein["sucesso"])
        trein_id = trein["treinamento_id"]

        concl = self.service.registrar_conclusao_treinamento(
            colaborador_id=self.colaborador_id,
            treinamento_id=trein_id,
            data_conclusao="2026-02-10",
            instrutor_nome="Eng. Sérgio Treinador",
            nota_aproveitamento=9.5,
        )
        self.assertTrue(concl["sucesso"])
        # Validade 24 meses => ~2028-02-10
        self.assertTrue(concl["data_expiracao_reciclagem"].startswith("2028-02"))

    def test_rf128_alertas_vencimento_proativos(self):
        """RF-128: Alertas preventivos consolidados de ASO, EPI e Treinamentos."""
        # Insere ASO já vencido
        self.service.registrar_aso(
            colaborador_id=self.colaborador_id,
            tipo_aso="PERIODICO",
            data_emissao="2025-01-01",
            data_validade="2026-01-01",  # Vencido
            resultado="APTO",
            medico_nome="Dr. Teste",
            medico_crm="1122",
            medico_uf="SP",
        )

        alertas = self.service.obter_alertas_vencimento_sst(dias_horizonte=60)
        self.assertGreater(alertas["total_alertas"], 0)
        self.assertGreater(alertas["total_criticos_vencidos"], 0)
        self.assertTrue(any(a["situacao_alerta"] == "vencido" for a in alertas["asos"]))

    def test_rf129_cat_emissao_e_validacoes(self):
        """RF-129, RN-064: Emissão de CAT com detalhamento, CID e histórico."""
        cat = self.service.registrar_cat(
            colaborador_id=self.colaborador_id,
            tipo_acidente="tipico",
            data_hora="2026-02-15 09:30",
            local_acidente="Galpão Principal - Setor de Usinagem",
            descricao="Queda de mesmo nível com contusão leve no punho esquerdo.",
            houve_afastamento=True,
            houve_obito=False,
            cid_codigo="S60.0",
            medico_nome="Dr. Pronto Atendimento",
            medico_crm="44332",
            medico_uf="SP",
            duracao_provavel_dias=3,
        )
        self.assertTrue(cat["sucesso"])
        self.assertTrue(cat["numero_cat"].startswith("CAT-"))
        self.assertTrue(cat["esocial_gerado"])

    def test_rf130_integracao_sst_esocial_s2210_s2220_s2240(self):
        """RF-130: Geração de eventos oficiais SST: S-2210, S-2220 e S-2240."""
        # 1. Evento S-2220 gerado via ASO
        aso = self.service.registrar_aso(
            colaborador_id=self.colaborador_id,
            tipo_aso="PERIODICO",
            data_emissao="2026-02-20",
            data_validade="2027-02-20",
            resultado="APTO",
            medico_nome="Dr. Cláudio do Trabalho",
            medico_crm="55443",
            medico_uf="SP",
        )
        self.assertTrue(aso["esocial_gerado"])

        # 2. Evento S-2210 gerado via CAT
        cat = self.service.registrar_cat(
            colaborador_id=self.colaborador_id,
            tipo_acidente="trajeto",
            data_hora="2026-02-21 07:45",
            local_acidente="Av. Principal, altura do nº 1000",
            descricao="Colisão leve de trânsito em trajeto para a empresa.",
            houve_afastamento=False,
            houve_obito=False,
            cid_codigo="T14.0",
        )
        self.assertTrue(cat["esocial_gerado"])

        # 3. Evento S-2240 gerado via Condições Ambientais / Agentes Nocivos
        cond = self.service.registrar_condicao_ambiental_s2240(
            colaborador_id=self.colaborador_id,
            ambiente_nome="Oficina Mecânica",
            fator_risco_codigo="01.01.001",
            fator_risco_descricao="Ruído contínuo ou intermitente acima de 85 dB(A)",
            data_inicio="2026-02-01",
            tipo_avaliacao="quantitativa",
            intensidade_concentracao=88.5,
            limite_tolerancia=85.0,
            epi_eficaz=True,
            ca_epi_utilizado="44550",
            responsavel_nome="Eng. João Segurança",
            responsavel_cpf="11122233344",
        )
        self.assertTrue(cond["sucesso"])
        self.assertTrue(cond["esocial_gerado"])
        self.assertEqual(cond["tipo_evento_esocial"], "S-2240")

        # Verifica eventos na tabela esocial_eventos
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT tipo_evento, status, xml_conteudo FROM esocial_eventos ORDER BY id ASC;")
        eventos = cur.fetchall()
        tipos = [e[0] for e in eventos]
        self.assertIn("S-2220", tipos)
        self.assertIn("S-2210", tipos)
        self.assertIn("S-2240", tipos)

        # Valida que XMLs contêm a estrutura oficial v_S_01_02_00
        for ev in eventos:
            xml = ev[2]
            self.assertIn("<eSocial", xml)
            self.assertIn("12345678000190", xml)
        conn.close()


if __name__ == "__main__":
    unittest.main()
