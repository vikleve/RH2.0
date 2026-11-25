"""
Suíte Completa de Testes Automatizados e Integração — RF061 a RF070 (Módulo 07: Afastamentos)
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
from backend.plataforma_exceptions import PlataformaValidacaoException
from backend.plataforma_service import PlataformaService
from backend.service import ColaboradorService


class TestAfastamentosRF061RF070(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls._template_db = tempfile.mkstemp(prefix="rh20_rf061_070_tpl_", suffix=".db")
        os.close(fd)
        cls._colab_srv = ColaboradorService(db_path=cls._template_db)
        cls._plat_srv = PlataformaService(db_path=cls._template_db)

        cls._c1 = cls._colab_srv.cadastrar({
            "matricula": "AFAST-101",
            "nome_completo": "Helena Moura Afastamento",
            "cpf": "52998224725",
            "data_nascimento": "1990-06-18",
            "email": "helena.afast@rh20.local",
            "cargo": "Analista Industrial",
            "setor": "Produção",
            "tipo_contrato": "CLT",
            "carga_horaria_mensal": 220.0,
            "data_admissao": "2024-02-01",
            "salario_base": 3800.00,
        }, usuario="QA Afast")

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls._template_db)
        except OSError:
            pass

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="rh20_rf061_070_run_", suffix=".db")
        os.close(fd)
        shutil.copyfile(self._template_db, self.db_path)
        self.colab_srv = ColaboradorService(db_path=self.db_path)
        self.plat_svc = PlataformaService(db_path=self.db_path)
        self.afast_svc = self.plat_svc.afastamento_service
        self.cid = self._c1["id"]

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_rf061_rf062_regra_15_dias_e_soma_60_dias_e_sobreposicao(self):
        """RF-061/RF-062/RF-067: Atestados em 60 dias somam na empresa (15d) e bloqueiam sobreposição."""
        # 1º atestado de 10 dias (2026-08-01 a 2026-08-10) -> 10d empresa, 0d INSS
        a1 = self.afast_svc.registrar_afastamento(
            self.cid, "doenca", "2026-08-01", "2026-08-10", cid="J11", usuario="RH"
        )
        self.assertEqual(a1["dias_empresa"], 10)
        self.assertEqual(a1["dias_inss"], 0)
        self.assertEqual(a1["regime_efeito"], "interrupcao")
        self.assertEqual(self.colab_srv.obter_por_id(self.cid)["situacao"], "afastado")

        # Sobreposição ativa bloqueada (RF-067)
        with self.assertRaises(PlataformaValidacaoException):
            self.afast_svc.registrar_afastamento(self.cid, "doenca", "2026-08-05", "2026-08-12", cid="J11")

        # Retorno do 1º atestado (<30d não exige ASO retorno)
        self.afast_svc.registrar_retorno_afastamento(a1["afastamento_id"], "2026-08-11", usuario="DP")
        self.assertEqual(self.colab_srv.obter_por_id(self.cid)["situacao"], "ativo")

        # 2º atestado do mesmo grupo dentro de 60 dias (2026-08-20 a 2026-08-31 = 12d)
        # Saldo empresa restante = 15 - 10 = 5d; INSS = 7d!
        a2 = self.afast_svc.registrar_afastamento(
            self.cid, "doenca", "2026-08-20", "2026-08-31", cid="J11", usuario="RH"
        )
        self.assertEqual(a2["dias_empresa"], 5)
        self.assertEqual(a2["dias_inss"], 7)
        self.assertEqual(a2["regime_efeito"], "suspensao")

    def test_rf063_rf064_estabilidades_e_suspensao_contratual(self):
        """RF-063/RF-064: Acidente <=15d não gera estabilidade; >15d gera 12m; maternidade gera estabilidade; licença s/ vencimento suspende."""
        # Acidente <= 15 dias (10d) -> sem benefício acidentário B91 -> estabilidade_ate is None
        ac_curto = self.afast_svc.registrar_afastamento(
            self.cid, "acidente_trabalho", "2026-09-01", "2026-09-10", cid="S61", usuario="SST"
        )
        self.assertIsNone(ac_curto["estabilidade_ate"])
        self.afast_svc.registrar_retorno_afastamento(ac_curto["afastamento_id"], "2026-09-11", usuario="DP")

        # Maternidade -> estabilidade 150 dias após fim
        mat = self.afast_svc.registrar_afastamento(
            self.cid, "maternidade", "2026-10-01", "2027-01-28", usuario="DP"
        )
        self.assertIsNotNone(mat["estabilidade_ate"])
        self.assertEqual(mat["dias_inss"], 0)
        self.assertEqual(mat["regime_efeito"], "interrupcao")

        # Licença não remunerada em outro colaborador -> regime suspensao, 0 dias empresa/INSS
        c2 = self.colab_srv.cadastrar({
            "matricula": "AFAST-102",
            "nome_completo": "Pedro Licença",
            "cpf": "11144477735",
            "data_nascimento": "1991-01-10",
            "email": "pedro.lic@rh20.local",
            "cargo": "Operador",
            "setor": "Produção",
            "data_admissao": "2024-03-01",
            "salario_base": 2500.00,
        })
        lic = self.afast_svc.registrar_afastamento(
            c2["id"], "licenca_nao_remunerada", "2026-11-01", "2026-11-20", usuario="DP"
        )
        self.assertEqual(lic["regime_efeito"], "suspensao")
        self.assertEqual(lic["dias_empresa"], 0)
        self.assertEqual(lic["dias_inss"], 0)

    def test_rf065_rf066_rf068_rf069_rf070_prorrogacao_aso_esocial_e_relatorio(self):
        """RF-065/066/068/069/070: Prorrogação, bloqueio sem ASO de Retorno >=30d, S-2230 início/fim v_S_01_02_00 e relatório CSV."""
        # Afastamento inicial 20d (<30d), depois prorrogado para 35d (>=30d passa a exigir ASO retorno)
        af = self.afast_svc.registrar_afastamento(
            self.cid, "acidente_trabalho", "2026-10-01", "2026-10-20", cid="S82.1", usuario="SST"
        )
        self.assertFalse(af["exige_aso_retorno"])

        prorr = self.afast_svc.prorrogar_afastamento(
            af["afastamento_id"], "2026-11-04", "Prorrogação por perícia médica INSS", cid="S82.1", usuario="SST"
        )
        self.assertEqual(prorr["dias_totais"], 35)
        self.assertEqual(prorr["dias_inss"], 20)
        self.assertTrue(prorr["exige_aso_retorno"])
        self.assertIsNotNone(prorr["estabilidade_ate"])

        # Retorno bloqueado sem ASO de Retorno APTO em sst_asos
        with self.assertRaises(PlataformaValidacaoException):
            self.afast_svc.registrar_retorno_afastamento(af["afastamento_id"], "2026-11-05", usuario="DP")

        # Emite ASO de retorno APTO e conclui retorno com S-2230 término válido
        aso = self.plat_svc.registrar_aso(
            colaborador_id=self.cid,
            tipo_aso="retorno_trabalho",
            data_emissao="2026-11-04",
            data_validade="2027-11-04",
            resultado="apto",
            medico_nome="Dra. Beatriz SST",
            medico_crm="123456",
            medico_uf="SP",
        )
        ret = self.afast_svc.registrar_retorno_afastamento(
            af["afastamento_id"], "2026-11-05", aso_id=aso["aso_id"], usuario="SST / DP"
        )
        self.assertTrue(ret["sucesso"])
        self.assertEqual(ret["aso_retorno_id"], aso["aso_id"])
        self.assertEqual(self.colab_srv.obter_por_id(self.cid)["situacao"], "ativo")

        # Validar ambos XMLs S-2230 (início e término)
        conn = get_connection(self.db_path)
        try:
            cur = conn.cursor()
            p = "%s" if _usar_postgres(self.db_path) else "?"
            cur.execute(f"SELECT xml_conteudo FROM esocial_eventos WHERE id IN ({p}, {p});", (af["esocial_inicio_id"], ret["esocial_termino_id"]))
            xmls = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
        self.assertEqual(len(xmls), 2)
        for x in xmls:
            ok, errs = validar_xml_esocial_trabalhista("S-2230", x)
            self.assertTrue(ok, errs)
        self.assertIn("<dtTermAfast>2026-11-05</dtTermAfast>", xmls[1])

        # Validar transmissão/validação lote eSocial sem recibo fictício
        res_lote = self.plat_svc.transmitir_lote_esocial([af["esocial_inicio_id"], ret["esocial_termino_id"]], usuario="Auditor")
        self.assertTrue(res_lote["simulacao"])
        self.assertEqual(res_lote["status_atribuido"], "validado")

        # Relatório gerencial + CSV (RF-070)
        rel = self.afast_svc.relatorio_afastamentos(setor="Produção")
        self.assertGreaterEqual(rel["total"], 1)
        self.assertGreaterEqual(rel["estabilidades_ativas"], 1)
        self.assertIn("Helena Moura", rel["csv"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
