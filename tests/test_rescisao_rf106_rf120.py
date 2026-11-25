"""
Suíte Completa de Testes Automatizados e Integração — RF106 a RF120 (Módulo 11: Rescisão Contratual)
Utiliza banco SQLite temporário isolado (template DB em setUpClass) e dados exclusivamente fictícios.
"""
import os
import shutil
import sys
import tempfile
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")
os.environ["GUEST_INITIAL_PASSWORD"] = os.environ.get("GUEST_INITIAL_PASSWORD", "Sintetico#GuestTest2026!")

from backend.database import _usar_postgres, fetchone_dict, get_connection
from backend.esocial_eventos_trabalhistas import validar_xml_esocial_trabalhista
from backend.folha_service import FolhaService
from backend.plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaValidacaoException,
)
from backend.plataforma_service import PlataformaService
from backend.service import ColaboradorService


class TestRescisaoRF106RF120(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls._template_db = tempfile.mkstemp(prefix="rh20_rf106_120_tpl_", suffix=".db")
        os.close(fd)
        cls._colab_srv = ColaboradorService(db_path=cls._template_db)
        cls._plat_srv = PlataformaService(db_path=cls._template_db)
        cls._folha_srv = FolhaService(db_path=cls._template_db)

        cls._c1 = cls._colab_srv.cadastrar({
            "matricula": "RESC-101",
            "nome_completo": "Fernando Oliveira Rescisão",
            "cpf": "52998224725",
            "data_nascimento": "1986-02-14",
            "email": "fernando.resc@rh20.local",
            "cargo": "Supervisor Industrial",
            "setor": "Usina",
            "tipo_contrato": "CLT",
            "carga_horaria_mensal": 220.0,
            "data_admissao": "2023-01-10",  # > 3 anos -> 39d aviso prévio Lei 12.506
            "salario_base": 6000.00,
        }, usuario="QA Rescisao")
        cls._c2 = cls._colab_srv.cadastrar({
            "matricula": "RESC-102",
            "nome_completo": "Marina Santos Experiência",
            "cpf": "11144477735",
            "data_nascimento": "1995-09-01",
            "email": "marina.resc@rh20.local",
            "cargo": "Auxiliar Administrativo",
            "setor": "RH",
            "tipo_contrato": "experiencia",
            "carga_horaria_mensal": 220.0,
            "data_admissao": "2026-09-01",
            "salario_base": 2400.00,
        }, usuario="QA Rescisao")

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls._template_db)
        except OSError:
            pass

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="rh20_rf106_120_run_", suffix=".db")
        os.close(fd)
        shutil.copyfile(self._template_db, self.db_path)
        self.colab_srv = ColaboradorService(db_path=self.db_path)
        self.plat_svc = PlataformaService(db_path=self.db_path)
        self.resc_svc = self.plat_svc.rescisao_service
        self.folha_svc = FolhaService(db_path=self.db_path)
        self.cid1 = self._c1["id"]
        self.cid2 = self._c2["id"]

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_rf106_rf107_modalidades_estabilidade_e_justa_causa(self):
        """RF-106/RF-107: Bloqueia afastamento ativo, normaliza COM_JUSTA_CAUSA (zero prop), testa art. 479 e falecimento."""
        # Simulação prévia (RF-113)
        sim = self.resc_svc.registrar_rescisao(
            self.cid1, "SEM_JUSTA_CAUSA", "2026-10-15", saldo_fgts=15000.00, simular=True
        )
        self.assertTrue(sim["simulado"])
        self.assertGreaterEqual(sim["calculo"]["dias_aviso_previo"], 39)
        self.assertEqual(sim["calculo"]["multa_fgts_percentual"], 40.0)
        self.assertAlmostEqual(float(sim["calculo"]["multa_fgts_valor"]), 6000.00, places=2)
        # Multa FGTS GRRF NÃO deve inflar o líquido rescisório do TRCT
        self.assertLess(sim["valor_liquido"], float(sim["calculo"]["total_proventos"]) + 0.01)

        # COM_JUSTA_CAUSA normalizada: zera férias proporcionais, 13º proporcional e multa FGTS
        sim_jc = self.resc_svc.registrar_rescisao(
            self.cid1, "COM_JUSTA_CAUSA", "2026-10-15", saldo_salario_dias=15, ferias_vencidas_dias=0, simular=True
        )
        self.assertEqual(float(sim_jc["calculo"]["ferias_proporcionais_com_terco"]), 0.0)
        self.assertEqual(float(sim_jc["calculo"]["decimo_terceiro_proporcional"]), 0.0)
        self.assertEqual(float(sim_jc["calculo"]["multa_fgts_valor"]), 0.0)

        # Antecipada empregador art. 479 (20 dias restantes -> 50% = 10 dias = R$ 800,00 em R$ 2.400)
        sim_479 = self.resc_svc.registrar_rescisao(
            self.cid2, "rescisao_antecipada_empregador", "2026-09-25",
            dias_restantes_contrato_prazo=20, saldo_fgts=500.00, simular=True
        )
        self.assertAlmostEqual(float(sim_479["calculo"]["multa_art_479"]), 800.00, places=2)
        self.assertEqual(sim_479["calculo"]["multa_fgts_percentual"], 40.0)

        # Falecimento garante saque integral FGTS (cód 23) e 13º/férias proporcionais sem multa 40%
        sim_fal = self.resc_svc.registrar_rescisao(
            self.cid2, "falecimento", "2026-10-10", simular=True
        )
        self.assertEqual(sim_fal["calculo"]["codigo_saque_fgts"], "23")
        self.assertGreater(float(sim_fal["calculo"]["decimo_terceiro_proporcional"]), 0.0)

        # Afastamento ativo bloqueia dispensa sem justa causa
        self.plat_svc.registrar_afastamento(self.cid2, "doenca", "2026-10-01", "2026-10-20", cid="M54", usuario="SST")
        with self.assertRaises(PlataformaValidacaoException):
            self.resc_svc.registrar_rescisao(self.cid2, "sem_justa_causa", "2026-10-10")

    def test_rf108_a_rf120_aso_pdfs_homologacao_multa_477_e_esocial_s2299(self):
        """RF-108..RF-120: ASO demissional NR-07, busca PA férias vencidas, TRCT/FGTS PDFs, RN-080, multa art. 477 §8º e S-2299."""
        # Gerar saldo de férias vencido/em dobro em PA + folha variável para médias
        self.folha_svc.criar_ou_atualizar_folha(
            colaborador_id=self.cid1, competencia="2026-09",
            periodo_inicio="2026-09-01", periodo_fim="2026-09-30",
            eventos=[{"codigo": "0010", "referencia": 10}], usuario="DP",
        )
        self.plat_svc.sincronizar_periodos_aquisitivos(self.cid1, "2026-10-01")

        # Bloqueio sem ASO demissional quando exigir_aso_demissional=True
        with self.assertRaises(PlataformaValidacaoException):
            self.resc_svc.registrar_rescisao(
                self.cid1, "sem_justa_causa", "2026-10-15", exigir_aso_demissional=True
            )

        # Emitir ASO Demissional APTO
        aso = self.plat_svc.registrar_aso(
            self.cid1, "demissional", "2026-10-14", "2027-10-14", "apto",
            "Dr. Eduardo NR07", "654321", "SP", usuario="SST",
        )

        # Efetivar rescisão com ASO demissional + busca automática de férias vencidas e médias
        resc = self.resc_svc.registrar_rescisao(
            colaborador_id=self.cid1,
            tipo_rescisao="sem_justa_causa",
            data_afastamento="2026-10-15",
            saldo_fgts=12000.00,
            exigir_aso_demissional=True,
            usuario="Analista Rescisao",
        )
        rid = resc["rescisao_id"]
        self.assertEqual(resc["aso_demissional_id"], aso["aso_id"])
        self.assertGreater(float(resc["calculo"]["ferias_vencidas_com_terco"]), 0.0)
        self.assertGreater(float(resc["calculo"]["desconto_irrf"]), -0.01)

        # Verificar S-2299 v_S_01_02_00 válido
        conn = get_connection(self.db_path)
        try:
            cur = conn.cursor()
            p = "%s" if _usar_postgres(self.db_path) else "?"
            cur.execute(f"SELECT xml_conteudo FROM esocial_eventos WHERE id = {p};", (resc["esocial_evento_id"],))
            xml_2299 = cur.fetchone()[0]
        finally:
            conn.close()
        ok_xml, errs = validar_xml_esocial_trabalhista("S-2299", xml_2299)
        self.assertTrue(ok_xml, errs)

        # Gerar PDFs TRCT e Guia FGTS/SD
        pdf_trct = self.resc_svc.gerar_documentos_rescisao_pdf(rid, "trct")
        pdf_fgts = self.resc_svc.gerar_documentos_rescisao_pdf(rid, "fgts_sd")
        self.assertTrue(pdf_trct["pdf_bytes"].startswith(b"%PDF-1.4"))
        self.assertTrue(pdf_fgts["pdf_bytes"].startswith(b"%PDF-1.4"))

        # Homologação com segregação RN-080
        with self.assertRaises(PlataformaAcessoNegadoException):
            self.resc_svc.homologar_rescisao(rid, homologador="Analista Rescisao")
        hom = self.resc_svc.homologar_rescisao(rid, homologador="Gerente DP")
        self.assertEqual(hom["status"], "homologada")

        # Pagamento após 10 dias -> multa automática do art. 477 §8º CLT (= 1 salário = R$ 6.000,00)
        pg = self.resc_svc.registrar_pagamento_rescisao(rid, data_pagamento="2026-10-30", usuario="Financeiro")
        self.assertTrue(pg["multa_art_477_aplicada"])
        self.assertAlmostEqual(pg["valor_multa_art_477"], 6000.00, places=2)
        self.assertGreater(pg["valor_liquido_final"], resc["valor_liquido"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
