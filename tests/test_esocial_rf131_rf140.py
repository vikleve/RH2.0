# -*- coding: utf-8 -*-
"""
Testes Automatizados para o Módulo de eSocial (RF-131 a RF-140)
- RF-131: Cadastro de Eventos (Gerenciamento e ciclo de vida)
- RF-132: Geração XML (Validação estrita v_S_01_02_00)
- RF-133: Assinatura Digital (Suporte a XMLDSig e tratamento honesto sem certificado)
- RF-134: Envio / Transmissão (Sem geração de recibos falsos/fictícios)
- RF-135: Monitoramento (Consultas avançadas e filtros)
- RF-136: Tratamento de Rejeições (Detalhes estruturados e reprocessamento)
- RF-137: Retificação (Evento retificador com vínculo indRetif=2 e recibo anterior)
- RF-138: Exclusão (Geração de evento oficial S-3000)
- RF-139: Histórico e Rastreabilidade de Versões
- RF-140: Auditoria Imutável de Transmissões e Alterações
"""
import os
import sys
import sqlite3
import tempfile
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.database import init_db
from backend.esocial_service import ESocialService
from backend.esocial_eventos_trabalhistas import gerar_xml_s2230, gerar_xml_s3000


class TestESocialRF131RF140(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        init_db(self.db_path, auto_provision=False)
        self.service = ESocialService(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def _gerar_s2230(self, cpf="11122233344", matr="MAT-001", dt="2026-03-01", motivo="ferias", ind_retif=1):
        return gerar_xml_s2230(
            colaborador={"cpf": cpf, "matricula": matr},
            cnpj_empregador="12345678000190",
            data_inicio=dt,
            motivo=motivo,
            ind_retif=ind_retif,
        )

    def test_rf131_cadastro_eventos_ciclo_vida(self):
        """RF-131: Cadastro de evento com persistência e status inicial."""
        xml_s2230, _ = self._gerar_s2230(matr="MAT-001")
        res = self.service.cadastrar_evento(
            tipo_evento="S-2230",
            identificador_origem="afast-101",
            xml_conteudo=xml_s2230,
            ambiente="homologacao",
            usuario="Analista DP",
        )
        self.assertTrue(res["sucesso"])
        self.assertEqual(res["tipo_evento"], "S-2230")
        self.assertEqual(res["status"], "validado")
        self.assertTrue(res["schema_valido"])

    def test_rf132_geracao_xml_xsd_validacao(self):
        """RF-132: Validação estrita de schema XML contra leiaute oficial v_S_01_02_00."""
        # XML válido
        xml_s2230, errs = self._gerar_s2230(matr="MAT-002", motivo="doenca")
        self.assertEqual(len(errs), 0)
        self.assertIn("v_S_01_02_00", xml_s2230)

        # XML inválido (tags faltando)
        xml_invalido = "<eSocial><evtInvalido/></eSocial>"
        cad_inv = self.service.cadastrar_evento(
            tipo_evento="S-2230",
            identificador_origem="afast-999",
            xml_conteudo=xml_invalido,
        )
        self.assertFalse(cad_inv["schema_valido"])
        self.assertEqual(cad_inv["status"], "erro_schema")

    def test_rf133_assinatura_digital_com_e_sem_certificado(self):
        """RF-133: Assinatura digital sem forjar assinatura na ausência de certificado."""
        xml_s2230, _ = self._gerar_s2230(matr="MAT-003")
        cad = self.service.cadastrar_evento(tipo_evento="S-2230", identificador_origem="1", xml_conteudo=xml_s2230)
        ev_id = cad["evento_id"]

        # Sem certificado: NÃO deve forjar assinatura falsa, deve ir para aguardando_assinatura
        res_sem_cert = self.service.assinar_evento(evento_id=ev_id)
        self.assertTrue(res_sem_cert["sucesso"])
        self.assertEqual(res_sem_cert["status"], "aguardando_assinatura")
        self.assertFalse(res_sem_cert["assinado"])
        self.assertIn("aguardando Certificado Digital", res_sem_cert["mensagem"])

        # Com certificado fornecido: assina o XML
        res_com_cert = self.service.assinar_evento(
            evento_id=ev_id,
            certificado_base64="MIIE...FAKE...CERT",
            chave_privada_pem="-----BEGIN RSA PRIVATE KEY-----...",
        )
        self.assertTrue(res_com_cert["sucesso"])
        self.assertEqual(res_com_cert["status"], "assinado")
        self.assertTrue(res_com_cert["assinado"])

    def test_rf134_envio_transmissao_sem_recibos_falsos(self):
        """RF-134, RN-065: Transmissão em homologação sem fabricação de recibos falsos."""
        xml_s2230, _ = self._gerar_s2230(matr="MAT-004")
        cad = self.service.cadastrar_evento(tipo_evento="S-2230", identificador_origem="2", xml_conteudo=xml_s2230)
        ev_id = cad["evento_id"]

        transm = self.service.transmitir_lote(evento_ids=[ev_id], ambiente="homologacao")
        self.assertTrue(transm["sucesso"])
        self.assertTrue(transm["simulacao"])
        self.assertEqual(transm["eventos_processados"], 1)

        # Verifica no banco que numero_recibo é estritamente NULL (sem falsificação)
        ev = self.service.obter_evento(ev_id)
        self.assertIsNone(ev["numero_recibo"])
        self.assertTrue(ev["protocolo_envio"].startswith("LOCAL-VAL-"))
        self.assertEqual(ev["codigo_resposta"], "XML-OK-LOCAL")

    def test_rf135_monitoramento_e_filtros(self):
        """RF-135: Monitoramento com filtros por status e tipo de evento."""
        xml_s2230, _ = self._gerar_s2230(matr="MAT-005")
        self.service.cadastrar_evento(tipo_evento="S-2230", identificador_origem="3", xml_conteudo=xml_s2230)

        lista_todos = self.service.listar_eventos()
        self.assertGreaterEqual(len(lista_todos), 1)

        lista_s2230 = self.service.listar_eventos(tipo="S-2230")
        self.assertTrue(all(e["tipo_evento"] == "S-2230" for e in lista_s2230))

    def test_rf136_tratamento_rejeicoes_estruturado(self):
        """RF-136: Registro estruturado de rejeições governamentais com detalhes."""
        xml_s2230, _ = self._gerar_s2230(matr="MAT-006")
        cad = self.service.cadastrar_evento(tipo_evento="S-2230", identificador_origem="4", xml_conteudo=xml_s2230)
        ev_id = cad["evento_id"]

        erros_detalhe = [
            {"codigo": "401", "campo": "matricula", "mensagem": "Matrícula informada não cadastrada no RET."},
        ]
        rej = self.service.registrar_rejeicao(
            evento_id=ev_id,
            codigo_resposta="MS0401",
            mensagem_resposta="Lote rejeitado pelo eSocial: Matrícula inexistente.",
            erros_detalhados=erros_detalhe,
        )
        self.assertTrue(rej["sucesso"])
        self.assertEqual(rej["status"], "rejeitado")

        ev = self.service.obter_evento(ev_id)
        self.assertEqual(ev["status"], "rejeitado")
        self.assertIn("MS0401", ev["codigo_resposta"])

    def test_rf137_retificacao_com_vinculo_recibo_anterior(self):
        """RF-137: Retificação formal de evento com indRetif=2 e vínculo ao original."""
        xml_orig, _ = self._gerar_s2230(matr="MAT-007", dt="2026-06-01")
        cad = self.service.cadastrar_evento(tipo_evento="S-2230", identificador_origem="5", xml_conteudo=xml_orig)
        ev_id_orig = cad["evento_id"]

        # Novo XML retificado
        xml_retif, _ = self._gerar_s2230(matr="MAT-007", dt="2026-06-05", ind_retif=2)

        retif = self.service.retificar_evento(
            evento_id_original=ev_id_orig,
            novo_xml_conteudo=xml_retif,
            numero_recibo_anterior="1.2.0000000000000000001",
            justificativa="Correção da data de início do gozo de férias",
        )
        self.assertTrue(retif["sucesso"])
        novo_id = retif["evento_retificador_id"]

        # Verifica status do original (marcado como retificado)
        ev_orig = self.service.obter_evento(ev_id_orig)
        self.assertEqual(ev_orig["status"], "retificado")

        # Verifica vínculo do novo evento
        ev_novo = self.service.obter_evento(novo_id)
        self.assertEqual(ev_novo["evento_retificador_de"], str(ev_id_orig))

    def test_rf138_exclusao_evento_s3000(self):
        """RF-138: Solicitação de exclusão de evento via S-3000."""
        xml_orig, _ = self._gerar_s2230(matr="MAT-008")
        cad = self.service.cadastrar_evento(tipo_evento="S-2230", identificador_origem="6", xml_conteudo=xml_orig)
        ev_id_alvo = cad["evento_id"]

        excl = self.service.solicitar_exclusao_evento(
            evento_id_alvo=ev_id_alvo,
            numero_recibo_alvo="1.2.9999999999999999999",
            cpf_trabalhador="11122233344",
            justificativa="Afastamento lançado indevidamente por duplicidade.",
        )
        self.assertTrue(excl["sucesso"])
        s3000_id = excl["evento_s3000_id"]

        # Alvo marcado como excluído
        alvo = self.service.obter_evento(ev_id_alvo)
        self.assertEqual(alvo["status"], "excluido")

        # S-3000 criado e validado
        s3000 = self.service.obter_evento(s3000_id)
        self.assertEqual(s3000["tipo_evento"], "S-3000")
        self.assertIn("evtExclusao", s3000["xml_conteudo"])
        self.assertIn("1.2.9999999999999999999", s3000["xml_conteudo"])

    def test_rf139_historico_genealogico_versoes(self):
        """RF-139: Rastreamento do histórico completo de versões do evento."""
        xml_orig, _ = self._gerar_s2230(matr="MAT-009", dt="2026-08-01")
        cad = self.service.cadastrar_evento(tipo_evento="S-2230", identificador_origem="7", xml_conteudo=xml_orig)
        ev_orig_id = cad["evento_id"]

        # Retifica
        xml_ret, _ = self._gerar_s2230(matr="MAT-009", dt="2026-08-05", ind_retif=2)
        ret = self.service.retificar_evento(
            evento_id_original=ev_orig_id,
            novo_xml_conteudo=xml_ret,
            numero_recibo_anterior="1.2.8888888888888888888",
            justificativa="Ajuste de datas",
        )
        ev_ret_id = ret["evento_retificador_id"]

        historico = self.service.obter_historico_evento(ev_ret_id)
        self.assertGreaterEqual(len(historico), 2)
        ids_hist = [h["id"] for h in historico]
        self.assertIn(ev_orig_id, ids_hist)
        self.assertIn(ev_ret_id, ids_hist)

    def test_rf140_auditoria_imutavel_esocial(self):
        """RF-140: Auditoria de operações do eSocial registrada imutavelmente."""
        xml_s2230, _ = self._gerar_s2230(matr="MAT-010")
        self.service.cadastrar_evento(
            tipo_evento="S-2230",
            identificador_origem="8",
            xml_conteudo=xml_s2230,
            usuario="Auditor Master",
        )

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT modulo, operacao, usuario_responsavel, detalhes FROM auditoria_operacoes WHERE modulo = 'eSocial';")
        auditorias = cur.fetchall()
        self.assertGreaterEqual(len(auditorias), 1)
        self.assertEqual(auditorias[0][0], "eSocial")
        self.assertEqual(auditorias[0][2], "Auditor Master")
        conn.close()


if __name__ == "__main__":
    unittest.main()
