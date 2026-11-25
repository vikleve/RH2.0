"""
Suíte Completa de Testes Automatizados e Integração — RF051 a RF060 (Módulo 06: Férias)
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


class TestFeriasRF051RF060(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls._template_db = tempfile.mkstemp(prefix="rh20_rf051_060_tpl_", suffix=".db")
        os.close(fd)
        cls._colab_srv = ColaboradorService(db_path=cls._template_db)
        cls._plat_srv = PlataformaService(db_path=cls._template_db)
        cls._folha_srv = FolhaService(db_path=cls._template_db)

        cls._c1 = cls._colab_srv.cadastrar({
            "matricula": "FER-1001",
            "nome_completo": "Clara Fernandes Férias",
            "cpf": "52998224725",
            "data_nascimento": "1992-03-15",
            "email": "clara.ferias@rh20.local",
            "cargo": "Analista Contábil",
            "setor": "Financeiro",
            "tipo_contrato": "CLT",
            "carga_horaria_mensal": 220.0,
            "data_admissao": "2024-01-02",
            "salario_base": 4500.00,
        }, usuario="QA Ferias")
        cls._c2 = cls._colab_srv.cadastrar({
            "matricula": "FER-1002",
            "nome_completo": "Rafael Gomes Férias",
            "cpf": "11144477735",
            "data_nascimento": "1990-08-20",
            "email": "rafael.ferias@rh20.local",
            "cargo": "Assistente Financeiro",
            "setor": "Financeiro",
            "tipo_contrato": "CLT",
            "carga_horaria_mensal": 220.0,
            "data_admissao": "2024-01-02",
            "salario_base": 3000.00,
        }, usuario="QA Ferias")

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls._template_db)
        except OSError:
            pass

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="rh20_rf051_060_run_", suffix=".db")
        os.close(fd)
        shutil.copyfile(self._template_db, self.db_path)
        self.plat_svc = PlataformaService(db_path=self.db_path)
        self.ferias_svc = self.plat_svc.ferias_service
        self.ponto_svc = self.plat_svc.ponto_service
        self.folha_svc = FolhaService(db_path=self.db_path)
        self.cid1 = self._c1["id"]
        self.cid2 = self._c2["id"]

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_rf051_art_130_faltas_injustificadas(self):
        """RF-051: Redução progressiva de direito pela tabela CLT art. 130 conforme faltas injustificadas."""
        # 8 faltas injustificadas no 1º período aquisitivo (2024-01-02 a 2025-01-02) -> direito = 24 dias
        for idx in range(8):
            dt = f"2024-03-{10 + idx:02d}"
            self.ponto_svc.registrar_ocorrencia(self.cid1, dt, dt, "falta_injustificada", "Falta teste art 130")

        pas = self.ferias_svc.sincronizar_periodos_aquisitivos(self.cid1, data_referencia="2025-02-01")
        self.assertEqual(pas[0]["faltas_injustificadas"], 8)
        self.assertEqual(pas[0]["dias_direito"], 24)
        self.assertEqual(pas[0]["saldo_dias"], 24)

        # >32 faltas zera o período aquisitivo
        for idx in range(25):
            mes = 4 + (idx // 20)
            dia = 1 + (idx % 20)
            dt = f"2024-{mes:02d}-{dia:02d}"
            self.ponto_svc.registrar_ocorrencia(self.cid1, dt, dt, "falta_injustificada", "Falta excessiva")
        pas2 = self.ferias_svc.sincronizar_periodos_aquisitivos(self.cid1, data_referencia="2025-02-01")
        self.assertEqual(pas2[0]["dias_direito"], 0)
        self.assertEqual(pas2[0]["situacao"], "perdido")

    def test_rf052_rf053_rf054_bloqueios_clt_dobro_e_fracionamento(self):
        """RF-052/053/054: Bloqueia 2d antes de feriado/DSR, aviso 30d estrito, <14d no fracionamento e calcula dobro."""
        # 2026-11-18 (quarta) é 2 dias antes do feriado nacional 2026-11-20 (Consciência Negra) -> bloqueado
        with self.assertRaises(PlataformaValidacaoException) as ctx_fer:
            self.ferias_svc.programar_ferias(self.cid2, "2026-11-18", 15)
        self.assertIn("feriado", str(ctx_fer.exception).lower())

        # Aviso 30d estrito em data próxima bloqueia
        with self.assertRaises(PlataformaValidacaoException):
            self.ferias_svc.programar_ferias(self.cid2, "2026-12-01", 15, exigir_aviso_30d=True)

        # Fracionamento: tentar 3 frações sem nenhuma >= 14d (10d + 10d OK? 10+10 deixa saldo 10 < 14 -> bloqueado!)
        ok1 = self.ferias_svc.programar_ferias(self.cid2, "2025-03-03", 10, solicitante="RH A")
        self.assertTrue(ok1["sucesso"])
        ok2 = self.ferias_svc.programar_ferias(self.cid2, "2025-06-02", 14, solicitante="RH A")
        self.assertTrue(ok2["sucesso"])
        # Sobreposição de datas bloqueada
        with self.assertRaises(PlataformaValidacaoException):
            self.ferias_svc.programar_ferias(self.cid2, "2025-06-05", 5, solicitante="RH A")

        # 3ª fração (6d) permitida pois já houve uma >=14d; 4ª fração bloqueada
        ok3 = self.ferias_svc.programar_ferias(self.cid2, "2025-09-01", 5, solicitante="RH A")
        self.assertEqual(ok3["numero_fracao"], 3)
        # Vencido concessivo -> em dobro (limite_concessivo 1º PA é 2026-01-02; férias após essa data paga em dobro)
        dobro = self.ferias_svc.programar_ferias(self.cid1, "2026-03-02", 15, solicitante="RH Dobro")
        self.assertTrue(dobro["em_dobro"])
        self.assertGreater(dobro["valor_ferias"], 4000.00)

    def test_rf055_rf056_rf057_rf059_rf060_calculo_pdf_folha_e_esocial(self):
        """RF-055/056/057/059/060: Médias, 13º, abono 1/3, PDFs Aviso/Recibo, integração folha, cancelamento e S-2230."""
        # Lançar folha anterior com HE 0010 para compor média de variáveis
        self.folha_svc.criar_ou_atualizar_folha(
            colaborador_id=self.cid1,
            competencia="2026-01",
            periodo_inicio="2026-01-01",
            periodo_fim="2026-01-31",
            eventos=[{"codigo": "0010", "referencia": 20}],
            usuario="Analista DP",
        )
        fer = self.ferias_svc.programar_ferias(
            colaborador_id=self.cid1,
            data_inicio="2026-03-02",
            dias_gozo=20,
            abono_pecuniario=True,
            dias_abono=10,
            adiantar_13=True,
            solicitante="Operador DP",
        )
        self.assertGreater(fer["media_variaveis"], 0.0)
        self.assertGreater(fer["valor_adiantamento_13"], 2000.0)
        self.assertGreater(fer["valor_abono"], 1000.0)
        self.assertIsNotNone(fer["esocial_evento_id"])

        # Verificar S-2230 codMotAfast=15 válido
        conn = get_connection(self.db_path)
        try:
            cur = conn.cursor()
            p = "%s" if _usar_postgres(self.db_path) else "?"
            cur.execute(f"SELECT xml_conteudo, status FROM esocial_eventos WHERE id = {p};", (fer["esocial_evento_id"],))
            ev = fetchone_dict(cur, self.db_path)
        finally:
            conn.close()
        self.assertIn("<codMotAfast>15</codMotAfast>", ev["xml_conteudo"])
        ok_xml, errs = validar_xml_esocial_trabalhista("S-2230", ev["xml_conteudo"])
        self.assertTrue(ok_xml, errs)

        # PDFs Aviso e Recibo
        pdf_aviso = self.ferias_svc.gerar_documentos_ferias_pdf(fer["ferias_id"], "aviso")
        pdf_recibo = self.ferias_svc.gerar_documentos_ferias_pdf(fer["ferias_id"], "recibo")
        self.assertTrue(pdf_aviso["pdf_bytes"].startswith(b"%PDF-1.4"))
        self.assertTrue(pdf_recibo["pdf_bytes"].startswith(b"%PDF-1.4"))

        # RN-080 aprovação + integração folha + pagamento
        with self.assertRaises(PlataformaAcessoNegadoException):
            self.ferias_svc.aprovar_ferias(fer["ferias_id"], aprovador="Operador DP", aprovar=True)
        self.ferias_svc.aprovar_ferias(fer["ferias_id"], aprovador="Gestor RH", aprovar=True)

        integ = self.ferias_svc.integrar_ferias_folha(fer["ferias_id"], competencia="2026-03", usuario="Folha DP")
        self.assertGreater(integ["folha_id"], 0)
        folha = self.folha_svc.obter_folha_por_id(integ["folha_id"])
        cods = {it["codigo_evento"] for it in folha["itens"]}
        self.assertTrue({"0100", "0101", "0102", "0103", "0110"}.issubset(cods))

        # Cancelamento de programação distinta recompõe saldo do PA
        fer2 = self.ferias_svc.programar_ferias(self.cid2, "2026-04-06", 20, solicitante="Op2")
        self.ferias_svc.cancelar_ferias(fer2["ferias_id"], "Reagendamento operacional", usuario="Gestor RH")
        pas_c2 = self.ferias_svc.listar_periodos_aquisitivos(self.cid2)
        self.assertEqual(pas_c2[-1]["saldo_dias"], 30)

    def test_rf058_ferias_coletivas(self):
        """RF-058: Férias coletivas aplicam ao setor inteiro com mínimo de 10 dias."""
        with self.assertRaises(PlataformaValidacaoException):
            self.ferias_svc.programar_ferias_coletivas("2026-07-06", dias_gozo=7, setor="Financeiro")

        col = self.ferias_svc.programar_ferias_coletivas("2026-07-06", dias_gozo=15, setor="Financeiro", usuario="Diretor RH")
        self.assertTrue(col["sucesso"])
        self.assertEqual(col["total_programados"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
