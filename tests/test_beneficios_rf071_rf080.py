"""
Suíte Completa de Testes Automatizados e Integração — Gestão de Benefícios e Descontos (RF071 a RF080)
Utiliza exclusivamente colaboradores e dados fictícios em banco SQLite temporário isolado.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from io import BytesIO

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")
os.environ["GUEST_INITIAL_PASSWORD"] = os.environ.get("GUEST_INITIAL_PASSWORD", "Sintetico#GuestTest2026!")

from backend.auth import AuthService
from backend.folha_service import FolhaService
from backend.plataforma_service import (
    PlataformaRecursoNaoEncontradoException,
    PlataformaService,
    PlataformaValidacaoException,
)
from backend.server import ApiColaboradorHandler
from backend.service import ColaboradorService


class _FakeServer:
    def __init__(self, db_path: str):
        self.colab_service = ColaboradorService(db_path=db_path)
        self.auth_service = AuthService(db_path=db_path)
        self.folha_service = FolhaService(db_path=db_path)
        self.plataforma_service = PlataformaService(db_path=db_path)


class _DummyWFile:
    def __init__(self):
        self.data = bytearray()

    def write(self, b):
        self.data.extend(b)


class _FakeSocket:
    def makefile(self, *args, **kwargs):
        return BytesIO()


class TestBeneficiosRF071RF080(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls._template_db = tempfile.mkstemp(prefix="rh20_benef_tpl_", suffix=".db")
        os.close(fd)
        srv = _FakeServer(cls._template_db)
        _, cls._cached_token = srv.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        cls._cached_clt = srv.colab_service.cadastrar({
            "matricula": "QA-9001",
            "nome_completo": "Mariana Teste Benefícios CLT",
            "cpf": "52998224725",
            "rg": "12.345.678-9",
            "data_nascimento": "1993-04-12",
            "cargo": "Analista Financeiro",
            "setor": "Financeiro",
            "departamento": "Financeiro",
            "tipo_contrato": "CLT",
            "data_admissao": "2024-01-10",
            "salario_base": 3000.00,
            "email": "mariana.qa.beneficios@teste.local",
            "telefone": "(16) 99999-1001",
            "dependentes": [
                {"nome": "Lucas Teste Filho", "parentesco": "filho", "data_nascimento": "2019-05-10"}
            ],
        }, usuario="QA")
        cls._cached_estag = srv.colab_service.cadastrar({
            "matricula": "QA-9002",
            "nome_completo": "Rafael Teste Estagiário",
            "cpf": "39053344705",
            "rg": "23.456.789-0",
            "data_nascimento": "2003-08-22",
            "cargo": "Estagiário de TI",
            "setor": "Tecnologia da Informação",
            "departamento": "TI",
            "tipo_contrato": "Estagiário",
            "data_admissao": "2026-10-01",
            "salario_base": 1800.00,
            "email": "rafael.qa.estag@teste.local",
            "telefone": "(16) 99999-1002",
        }, usuario="QA")
        cls._cached_inativo = srv.colab_service.cadastrar({
            "matricula": "QA-9003",
            "nome_completo": "Bruno Teste Inativo",
            "cpf": "71428793860",
            "rg": "34.567.890-1",
            "data_nascimento": "1989-11-05",
            "cargo": "Assistente Operacional",
            "setor": "Operações",
            "tipo_contrato": "CLT",
            "data_admissao": "2023-03-01",
            "salario_base": 2500.00,
            "email": "bruno.qa.inativo@teste.local",
            "telefone": "(16) 99999-1003",
        }, usuario="QA")
        srv.colab_service.inativar(cls._cached_inativo["id"], motivo="Desligamento QA", usuario="QA")

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls._template_db)
        except OSError:
            pass

    def setUp(self):
        self.fd, self.db_path = tempfile.mkstemp(prefix="rh20_benef_qa_", suffix=".db")
        os.close(self.fd)
        shutil.copyfile(self._template_db, self.db_path)
        self.srv = _FakeServer(self.db_path)
        self.colab_svc = self.srv.colab_service
        self.folha_svc = self.srv.folha_service
        self.plat_svc = self.srv.plataforma_service
        self.auth_svc = self.srv.auth_service
        self.token = self._cached_token
        self.colab_clt = self._cached_clt
        self.colab_estag = self._cached_estag
        self.colab_inativo = self._cached_inativo
        self.catalogo = {b["codigo"]: b for b in self.plat_svc.listar_beneficios_catalogo()}

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def _req(self, method: str, path: str, body=None, token=None):
        handler = ApiColaboradorHandler.__new__(ApiColaboradorHandler)
        handler.server = self.srv
        handler.path = path
        handler.command = method
        handler.request_version = "HTTP/1.1"
        handler.client_address = ("127.0.0.1", 50000)
        handler.connection = _FakeSocket()
        handler.wfile = _DummyWFile()
        raw_body = json.dumps(body).encode("utf-8") if body is not None else b""
        handler.rfile = BytesIO(raw_body)
        headers = {
            "Host": "localhost:8000",
            "Origin": "http://localhost:8000",
            "Content-Length": str(len(raw_body)),
            "Content-Type": "application/json",
        }
        tok = self.token if token is None else token
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        handler.headers = headers

        status_holder = {"code": None}

        def send_resp(code, message=None):
            status_holder["code"] = code

        handler.send_response = send_resp
        handler.send_header = lambda k, v: None
        handler.end_headers = lambda: None
        getattr(handler, f"do_{method}")()
        resp_txt = handler.wfile.data.decode("utf-8") if handler.wfile.data else "{}"
        return status_holder["code"], json.loads(resp_txt)

    def test_rf071_vale_transporte(self):
        """RF071: VT com teto legal de 6%, custo menor que teto, não-optante, edição, exclusão e validações."""
        vt = self.catalogo["VT01"]
        # Custo 12 * 22 = 264.00 > 6% de R$ 3.000 (180.00) -> desconto limitado a R$ 180.00
        st, res = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": vt["id"],
            "vigencia_inicio": "2026-10-01",
            "optante": 1,
            "valor_diario": 12.00,
            "dias_uteis_mes": 22,
        })
        self.assertEqual(st, 201, res)
        v = res["dados"]
        self.assertAlmostEqual(v["custo_total_mes"], 264.00, places=2)
        self.assertAlmostEqual(v["desconto_colaborador"], 180.00, places=2)
        self.assertAlmostEqual(v["custo_empresa"], 84.00, places=2)

        # Persistência em nova instância de serviço
        nova_plat = PlataformaService(db_path=self.db_path)
        lido = nova_plat.obter_beneficio_colaborador(v["id"])
        self.assertAlmostEqual(lido["desconto_colaborador"], 180.00, places=2)

        # Edição: custo menor que 6% (5 * 22 = 110.00 < 180.00) -> desconto = 110.00, empresa = 0
        st, res_ed = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {
            "valor_diario": 5.00,
            "dias_uteis_mes": 22,
        })
        self.assertEqual(st, 200, res_ed)
        self.assertAlmostEqual(res_ed["dados"]["desconto_colaborador"], 110.00, places=2)
        self.assertAlmostEqual(res_ed["dados"]["custo_empresa"], 0.00, places=2)

        # Edição para não-optante zera custos e descontos
        st, res_nao = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"optante": 0})
        self.assertEqual(st, 200)
        self.assertEqual(res_nao["dados"]["desconto_colaborador"], 0.00)

        # Dados inválidos: valor negativo e vigência fim anterior ao início
        st_neg, _ = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"valor_diario": -10, "optante": 1})
        self.assertEqual(st_neg, 400)
        st_dt, _ = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"vigencia_fim": "2026-09-01"})
        self.assertEqual(st_dt, 400)

        # Exclusão
        st_del, _ = self._req("DELETE", f"/api/beneficios/colaboradores/{v['id']}")
        self.assertEqual(st_del, 200)
        with self.assertRaises(PlataformaRecursoNaoEncontradoException):
            nova_plat.obter_beneficio_colaborador(v["id"])

    def test_rf072_vale_alimentacao(self):
        """RF072: Vale-Alimentação (PAT) cadastro, edição, teto 20%, persistência e exclusão."""
        va = self.catalogo["VA01"]
        st, res = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": va["id"],
            "vigencia_inicio": "2026-10-01",
            "valor_mensal_base": 700.00,
        })
        self.assertEqual(st, 201, res)
        v = res["dados"]
        self.assertAlmostEqual(v["custo_total_mes"], 700.00, places=2)
        self.assertAlmostEqual(v["desconto_colaborador"], 0.00, places=2)
        self.assertAlmostEqual(v["custo_empresa"], 700.00, places=2)

        # Teto PAT inválido (>20%) bloqueado no catálogo
        st_inv, _ = self._req("POST", "/api/beneficios/catalogo", {
            "codigo": "VA_INV",
            "nome": "VA Inválido",
            "tipo": "vale_alimentacao",
            "teto_legal_percentual": 25.0,
        })
        self.assertEqual(st_inv, 400)

        st_ed, res_ed = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"valor_mensal_base": 820.00})
        self.assertEqual(st_ed, 200)
        self.assertAlmostEqual(res_ed["dados"]["custo_total_mes"], 820.00, places=2)

        st_del, _ = self._req("DELETE", f"/api/beneficios/colaboradores/{v['id']}")
        self.assertEqual(st_del, 200)

    def test_rf073_vale_refeicao(self):
        """RF073: Vale-Refeição diário x dias úteis, coparticipação fixa PAT, edição e exclusão."""
        vr = self.catalogo["VR01"]  # coparticipação fixa = 5.00
        st, res = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": vr["id"],
            "vigencia_inicio": "2026-10-01",
            "valor_diario": 35.00,
            "dias_uteis_mes": 22,
        })
        self.assertEqual(st, 201, res)
        v = res["dados"]
        self.assertAlmostEqual(v["custo_total_mes"], 770.00, places=2)
        self.assertAlmostEqual(v["desconto_colaborador"], 5.00, places=2)
        self.assertAlmostEqual(v["custo_empresa"], 765.00, places=2)

        st_ed, res_ed = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"dias_uteis_mes": 20})
        self.assertEqual(st_ed, 200)
        self.assertAlmostEqual(res_ed["dados"]["custo_total_mes"], 700.00, places=2)

        st_del, _ = self._req("DELETE", f"/api/beneficios/colaboradores/{v['id']}")
        self.assertEqual(st_del, 200)

    def test_rf074_plano_saude(self):
        """RF074: Plano de saúde titular + dependentes + coparticipação extra, edição e exclusão."""
        ps = self.catalogo["PS01"]  # coparticipação 15%
        st, res = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": ps["id"],
            "vigencia_inicio": "2026-10-01",
            "valor_mensal_base": 500.00,
            "qtd_dependentes": len(self.colab_clt["dependentes"]),
            "valor_dependente": 200.00,
            "coparticipacao_extra": 45.00,
        })
        self.assertEqual(st, 201, res)
        v = res["dados"]
        # Custo = 500 + 1*200 = 700; 15% de 700 = 105 + 45 = 150
        self.assertAlmostEqual(v["custo_total_mes"], 700.00, places=2)
        self.assertAlmostEqual(v["desconto_colaborador"], 150.00, places=2)
        self.assertAlmostEqual(v["custo_empresa"], 550.00, places=2)

        st_inv, _ = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"qtd_dependentes": -1})
        self.assertEqual(st_inv, 400)

        st_ed, res_ed = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"coparticipacao_extra": 0.0})
        self.assertEqual(st_ed, 200)
        self.assertAlmostEqual(res_ed["dados"]["desconto_colaborador"], 105.00, places=2)

        st_del, _ = self._req("DELETE", f"/api/beneficios/colaboradores/{v['id']}")
        self.assertEqual(st_del, 200)

    def test_rf075_seguro_vida(self):
        """RF075: Seguro de vida em grupo (custeado pela empresa, edição e exclusão)."""
        sv = self.catalogo["SV01"]
        st, res = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": sv["id"],
            "vigencia_inicio": "2026-10-01",
            "valor_mensal_base": 45.00,
        })
        self.assertEqual(st, 201, res)
        v = res["dados"]
        self.assertAlmostEqual(v["custo_total_mes"], 45.00, places=2)
        self.assertAlmostEqual(v["desconto_colaborador"], 0.00, places=2)
        self.assertAlmostEqual(v["custo_empresa"], 45.00, places=2)

        st_ed, res_ed = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"valor_mensal_base": 60.00})
        self.assertEqual(st_ed, 200)
        self.assertAlmostEqual(res_ed["dados"]["custo_empresa"], 60.00, places=2)

        st_del, _ = self._req("DELETE", f"/api/beneficios/colaboradores/{v['id']}")
        self.assertEqual(st_del, 200)

    def test_rf076_convenio_farmacia(self):
        """RF076: Convênio farmácia com limite mensal, bloqueio por excesso, edição e exclusão."""
        far = self.catalogo["FAR01"]
        st_exc, _ = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": far["id"],
            "vigencia_inicio": "2026-10-01",
            "limite_mensal": 300.00,
            "valor_utilizado_mes": 350.00,
        })
        self.assertEqual(st_exc, 400)

        st, res = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": far["id"],
            "vigencia_inicio": "2026-10-01",
            "limite_mensal": 400.00,
            "valor_utilizado_mes": 125.50,
        })
        self.assertEqual(st, 201, res)
        v = res["dados"]
        self.assertAlmostEqual(v["desconto_colaborador"], 125.50, places=2)

        st_ed, res_ed = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {"valor_utilizado_mes": 190.00})
        self.assertEqual(st_ed, 200)
        self.assertAlmostEqual(res_ed["dados"]["desconto_colaborador"], 190.00, places=2)

        st_del, _ = self._req("DELETE", f"/api/beneficios/colaboradores/{v['id']}")
        self.assertEqual(st_del, 200)

    def test_rf077_beneficios_flexiveis(self):
        """RF077: Benefícios flexíveis com saldo e alocação por categorias, validação de excesso."""
        flex = self.catalogo["FLEX01"]
        # Alocação acima do saldo deve falhar
        st_exc, _ = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": flex["id"],
            "vigencia_inicio": "2026-10-01",
            "saldo_flexivel": 500.00,
            "alocacao_json": {"alimentacao": 300.00, "saude": 250.00},
        })
        self.assertEqual(st_exc, 400)

        st, res = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": flex["id"],
            "vigencia_inicio": "2026-10-01",
            "saldo_flexivel": 600.00,
            "alocacao_json": {"alimentacao": 250.00, "mobilidade": 150.00, "educacao": 200.00},
        })
        self.assertEqual(st, 201, res)
        v = res["dados"]
        self.assertAlmostEqual(v["saldo_flexivel"], 600.00, places=2)
        self.assertAlmostEqual(v["custo_empresa"], 600.00, places=2)
        self.assertEqual(v["alocacao_obj"]["educacao"], 200.00)

        st_ed, res_ed = self._req("PUT", f"/api/beneficios/colaboradores/{v['id']}", {
            "alocacao_json": {"alimentacao": 400.00, "saude": 200.00},
        })
        self.assertEqual(st_ed, 200)
        self.assertEqual(res_ed["dados"]["alocacao_obj"]["saude"], 200.00)

        st_del, _ = self._req("DELETE", f"/api/beneficios/colaboradores/{v['id']}")
        self.assertEqual(st_del, 200)

    def test_rf078_controle_elegibilidade(self):
        """RF078: Bloqueio por inatividade, tipo de contrato, tempo mínimo de casa e setor."""
        ps = self.catalogo["PS01"]  # exige CLT
        # Estagiário tentando Plano de Saúde (exige CLT)
        st_est, res_est = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_estag["id"],
            "beneficio_id": ps["id"],
            "vigencia_inicio": "2026-10-10",
            "valor_mensal_base": 480.00,
        })
        self.assertEqual(st_est, 400)
        self.assertIn("inelegível", res_est["mensagem"].lower())

        # Colaborador inativo bloqueado
        st_in, res_in = self._req("POST", "/api/beneficios/colaboradores", {
            "colaborador_id": self.colab_inativo["id"],
            "beneficio_id": self.catalogo["VT01"]["id"],
            "vigencia_inicio": "2026-10-01",
            "valor_diario": 10.0,
        })
        self.assertEqual(st_in, 400)
        self.assertIn("inelegível", res_in["mensagem"].lower())

        # Benefício customizado exigindo 90 dias de casa e setor Financeiro
        st_cat, res_cat = self._req("POST", "/api/beneficios/catalogo", {
            "codigo": "AUX90",
            "nome": "Auxílio Especial Finanças",
            "tipo": "outros",
            "regra_elegibilidade": {
                "situacoes_permitidas": ["ativo"],
                "tempo_minimo_dias": 90,
                "setores_permitidos": ["Financeiro"],
            },
        })
        self.assertEqual(st_cat, 201, res_cat)
        bid_custom = res_cat["dados"]["id"]

        # CLT (admitida em 2024-01-10, setor Financeiro) -> elegível
        st_el1, r_el1 = self._req("GET", f"/api/beneficios/elegibilidade?colaborador_id={self.colab_clt['id']}&beneficio_id={bid_custom}&data_referencia=2026-10-15")
        self.assertEqual(st_el1, 200)
        self.assertTrue(r_el1["dados"]["elegivel"])

        # Estagiário (admitido em 2026-10-01, TI) -> inelegível pelos dois critérios
        st_el2, r_el2 = self._req("GET", f"/api/beneficios/elegibilidade?colaborador_id={self.colab_estag['id']}&beneficio_id={bid_custom}&data_referencia=2026-10-15")
        self.assertEqual(st_el2, 200)
        self.assertFalse(r_el2["dados"]["elegivel"])
        self.assertGreaterEqual(len(r_el2["dados"]["motivos"]), 2)

        self._req("DELETE", f"/api/beneficios/catalogo/{bid_custom}")

    def test_rf079_integracao_descontos_folha(self):
        """RF079: Integração dos descontos ativos na folha de pagamento e atualização com reajuste salarial."""
        self.plat_svc.vincular_beneficio_colaborador({
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": self.catalogo["VT01"]["id"],
            "vigencia_inicio": "2026-10-01",
            "optante": 1,
            "valor_diario": 12.00,
            "dias_uteis_mes": 22,  # custo = 264.00; 6% de 3000 = 180.00
        }, usuario="QA")
        self.plat_svc.vincular_beneficio_colaborador({
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": self.catalogo["PS01"]["id"],
            "vigencia_inicio": "2026-10-01",
            "valor_mensal_base": 400.00,  # 15% = 60.00
        }, usuario="QA")
        self.plat_svc.vincular_beneficio_colaborador({
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": self.catalogo["FAR01"]["id"],
            "vigencia_inicio": "2026-10-01",
            "limite_mensal": 300.00,
            "valor_utilizado_mes": 50.00,  # 100% = 50.00
        }, usuario="QA")

        st_d, res_d = self._req("GET", f"/api/beneficios/descontos-folha?colaborador_id={self.colab_clt['id']}&competencia=2026-10")
        self.assertEqual(st_d, 200, res_d)
        self.assertAlmostEqual(res_d["dados"]["total_descontos_beneficios"], 290.00, places=2)  # 180 + 60 + 50

        # Folha gerada COM incluir_beneficios_ativos=True
        st_f, res_f = self._req("POST", "/api/folha", {
            "colaborador_id": self.colab_clt["id"],
            "competencia": "2026-10",
            "incluir_beneficios_ativos": True,
        })
        self.assertEqual(st_f, 201, res_f)
        folha = res_f["dados"]
        cods_itens = {it["codigo_evento"] for it in folha["itens"]}
        self.assertIn("0510", cods_itens)
        self.assertIn("0512", cods_itens)
        self.assertIn("0516", cods_itens)
        # Base INSS permanece sobre salário-base (R$ 3.000), sem incidência sobre benefícios
        self.assertAlmostEqual(float(folha["base_inss"]), 3000.00, places=2)
        self.assertGreater(float(folha["total_descontos"]), 290.00)

        # Integração dinâmica com alteração salarial (reajuste de 3000 -> 4000 aumenta teto VT 6% para 240.00)
        self.colab_svc.atualizar(self.colab_clt["id"], {"salario_base": 4000.00}, usuario="QA")
        st_d2, res_d2 = self._req("GET", f"/api/beneficios/descontos-folha?colaborador_id={self.colab_clt['id']}&competencia=2026-11")
        self.assertEqual(st_d2, 200)
        # VT agora 240 + PS 60 + FAR 50 = 350.00
        self.assertAlmostEqual(res_d2["dados"]["total_descontos_beneficios"], 350.00, places=2)

    def test_rf080_relatorio_beneficios(self):
        """RF080: Consistência dos totais, agrupamentos por tipo/setor e filtros do relatório."""
        self.plat_svc.vincular_beneficio_colaborador({
            "colaborador_id": self.colab_clt["id"],
            "beneficio_id": self.catalogo["VT01"]["id"],
            "vigencia_inicio": "2026-10-01",
            "valor_diario": 12.00,
            "dias_uteis_mes": 22,  # 264 total, 180 desc, 84 emp
        }, usuario="QA")
        self.plat_svc.vincular_beneficio_colaborador({
            "colaborador_id": self.colab_estag["id"],
            "beneficio_id": self.catalogo["VR01"]["id"],
            "vigencia_inicio": "2026-10-01",
            "valor_diario": 30.00,
            "dias_uteis_mes": 20,  # 600 total, 5 desc, 595 emp
        }, usuario="QA")

        st, res = self._req("GET", "/api/beneficios/relatorio?competencia=2026-10")
        self.assertEqual(st, 200, res)
        rel = res["dados"]
        r = rel["resumo"]
        self.assertEqual(r["total_vinculos_ativos"], 2)
        self.assertEqual(r["total_colaboradores_beneficiados"], 2)
        self.assertAlmostEqual(r["custo_total_mensal"], 864.00, places=2)
        self.assertAlmostEqual(r["total_desconto_colaboradores"], 185.00, places=2)
        self.assertAlmostEqual(r["total_custo_empresa"], 679.00, places=2)
        self.assertAlmostEqual(r["custo_total_mensal"], r["total_custo_empresa"] + r["total_desconto_colaboradores"], places=2)
        self.assertEqual(len(rel["por_tipo"]), 2)
        self.assertEqual(len(rel["por_setor"]), 2)

        st_f, res_f = self._req("GET", "/api/beneficios/relatorio?setor=Financeiro")
        self.assertEqual(st_f, 200)
        self.assertEqual(res_f["dados"]["resumo"]["total_vinculos_ativos"], 1)


if __name__ == "__main__":
    unittest.main()
