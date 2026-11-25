"""
Suíte Completa de Testes Automatizados e Integração — RF-005 a RF-010
Gestão Completa do Cadastro do Colaborador (Dependentes, Histórico Funcional Imutável,
Anexos Seguros e Versionados, Controle de Documentação/Alertas, Dados Bancários + CNAB 240,
e Auditoria Cadastral Unificada).
Utiliza exclusivamente dados fictícios e banco SQLite + diretório privado temporários.
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from io import BytesIO

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")
os.environ["GUEST_INITIAL_PASSWORD"] = os.environ.get("GUEST_INITIAL_PASSWORD", "Sintetico#GuestTest2026!")

from backend.auth import AuthService
from backend.folha_service import FolhaService
from backend.plataforma_service import PlataformaService
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


class TestColaboradorRF005RF010(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls._template_db = tempfile.mkstemp(prefix="rh20_rf005_010_tpl_", suffix=".db")
        os.close(fd)
        cls._template_docs = tempfile.mkdtemp(prefix="rh20_rf005_010_docs_")
        os.environ["PRIVATE_DOCS_DIR"] = cls._template_docs

        srv = _FakeServer(cls._template_db)
        _, cls._cached_token = srv.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        cls._cached_colab = srv.colab_service.cadastrar({
            "matricula": "RF-5001",
            "nome_completo": "Helena Prado Fictícia",
            "cpf": "52998224725",
            "rg": "12.345.678-9",
            "data_nascimento": "1992-05-18",
            "cargo": "Analista de RH Pleno",
            "setor": "Recursos Humanos",
            "departamento": "Gente e Gestão",
            "centro_custo": "CC-100",
            "tipo_contrato": "CLT",
            "jornada_trabalho": "44h semanais",
            "carga_horaria_mensal": 220,
            "data_admissao": "2024-02-01",
            "salario_base": 4500.00,
            "email": "helena.prado.teste@rh20.local",
            "telefone": "(16) 99999-5001",
        }, usuario="QA Homologação")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("PRIVATE_DOCS_DIR", None)
        for path_rm in (cls._template_db,):
            try:
                os.remove(path_rm)
            except OSError:
                pass
        shutil.rmtree(cls._template_docs, ignore_errors=True)

    def setUp(self):
        self.fd, self.db_path = tempfile.mkstemp(prefix="rh20_rf005_010_run_", suffix=".db")
        os.close(self.fd)
        shutil.copyfile(self._template_db, self.db_path)
        self.private_docs_dir = tempfile.mkdtemp(prefix="rh20_rf005_010_priv_")
        os.environ["PRIVATE_DOCS_DIR"] = self.private_docs_dir

        self.srv = _FakeServer(self.db_path)
        self.colab_svc = self.srv.colab_service
        self.folha_svc = self.srv.folha_service
        self.plat_svc = self.srv.plataforma_service
        self.auth_svc = self.srv.auth_service
        self.token = self._cached_token
        self.colab = dict(self._cached_colab)

    def tearDown(self):
        os.environ.pop("PRIVATE_DOCS_DIR", None)
        try:
            os.remove(self.db_path)
        except OSError:
            pass
        shutil.rmtree(self.private_docs_dir, ignore_errors=True)

    def _req(self, method: str, path: str, body=None, token=None, raw_response: bool = False):
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

        status_holder = {"code": None, "headers": {}}

        def send_resp(code, message=None):
            status_holder["code"] = code

        def send_hdr(k, v):
            status_holder["headers"][k.lower()] = v

        handler.send_response = send_resp
        handler.send_header = send_hdr
        handler.end_headers = lambda: None
        getattr(handler, f"do_{method}")()

        if raw_response:
            return status_holder["code"], bytes(handler.wfile.data), status_holder["headers"]
        resp_txt = handler.wfile.data.decode("utf-8") if handler.wfile.data else "{}"
        return status_holder["code"], json.loads(resp_txt)

    def test_rf005_dependentes_crud_validacoes_inativacao_e_folha(self):
        """RF-005: validações (CPF IRRF, nascimento, duplicidade), CRUD, inativação lógica e integração com folha."""
        cid = self.colab["id"]

        # 1. Rejeitar dependente IRRF sem CPF e com data futura
        st, _ = self._req("POST", f"/api/colaboradores/{cid}/dependentes", {
            "nome": "Sem CPF IRRF",
            "parentesco": "Filho(a)",
            "data_nascimento": "2018-03-10",
            "eh_dependente_irrf": True,
        })
        self.assertEqual(st, 400)

        amanha = (date.today() + timedelta(days=5)).isoformat()
        st, _ = self._req("POST", f"/api/colaboradores/{cid}/dependentes", {
            "nome": "Data Futura",
            "parentesco": "Filho(a)",
            "cpf": "39053344705",
            "data_nascimento": amanha,
            "eh_dependente_irrf": True,
        })
        self.assertEqual(st, 400)

        # 2. Cadastrar dependente válido com IRRF + Salário-Família
        st, res1 = self._req("POST", f"/api/colaboradores/{cid}/dependentes", {
            "nome": "Sofia Prado Fictícia",
            "parentesco": "Filho(a)",
            "cpf": "39053344705",
            "data_nascimento": "2018-07-15",
            "eh_dependente_irrf": True,
            "eh_elegivel_salario_familia": True,
            "eh_plano_saude": True,
        })
        self.assertEqual(st, 201)
        dep1 = res1["dados"]

        # 3. Bloquear duplicidade de CPF entre dependentes ativos do mesmo colaborador
        st, _ = self._req("POST", f"/api/colaboradores/{cid}/dependentes", {
            "nome": "Sofia Duplicada",
            "parentesco": "Filho(a)",
            "cpf": "39053344705",
            "data_nascimento": "2018-07-15",
            "eh_dependente_irrf": True,
        })
        self.assertEqual(st, 400)

        # 4. Cadastrar segundo dependente só para Plano de Saúde (sem IRRF)
        st, res2 = self._req("POST", f"/api/colaboradores/{cid}/dependentes", {
            "nome": "Carlos Prado Fictício",
            "parentesco": "Cônjuge",
            "data_nascimento": "1990-01-20",
            "eh_dependente_irrf": False,
            "eh_elegivel_salario_familia": False,
            "eh_plano_saude": True,
        })
        self.assertEqual(st, 201)
        dep2 = res2["dados"]

        # 5. Editar dependente 2
        st, res_ed = self._req("PUT", f"/api/colaboradores/{cid}/dependentes/{dep2['id']}", {
            "nome": "Carlos Eduardo Prado Fictício",
            "parentesco": "Cônjuge",
            "cpf": "71428793860",
            "data_nascimento": "1990-01-20",
            "eh_dependente_irrf": True,
            "eh_elegivel_salario_familia": False,
            "eh_plano_saude": True,
        })
        self.assertEqual(st, 200)
        self.assertEqual(res_ed["dados"]["nome"], "Carlos Eduardo Prado Fictício")

        # 6. Conferir integração com Folha antes da inativação (2 ativos, 2 IRRF, 1 SalFam, 2 Saúde)
        dados_folha = self.folha_svc.obter_dados_colaborador(cid)
        self.assertEqual(dados_folha["total_dependentes"], 2)
        self.assertEqual(dados_folha["total_dependentes_irrf"], 2)
        self.assertEqual(dados_folha["total_dependentes_salario_familia"], 1)
        self.assertEqual(dados_folha["total_dependentes_plano_saude"], 2)

        # 7. Inativação lógica do dependente 1
        st, res_del = self._req("DELETE", f"/api/colaboradores/{cid}/dependentes/{dep1['id']}", {
            "motivo": "Maioridade atingida"
        })
        self.assertEqual(st, 200)
        self.assertEqual(res_del["dados"]["situacao"], "inativo")
        self.assertTrue(res_del["dados"]["data_encerramento"])

        # Lista ativa retorna 1; incluir_inativos=1 retorna 2
        st, lst_atv = self._req("GET", f"/api/colaboradores/{cid}/dependentes")
        self.assertEqual(lst_atv["total"], 1)
        st, lst_all = self._req("GET", f"/api/colaboradores/{cid}/dependentes?incluir_inativos=1")
        self.assertEqual(lst_all["total"], 2)

        # Folha passa a considerar apenas dependentes ativos!
        dados_folha_pos = self.folha_svc.obter_dados_colaborador(cid)
        self.assertEqual(dados_folha_pos["total_dependentes"], 1)
        self.assertEqual(dados_folha_pos["total_dependentes_irrf"], 1)
        self.assertEqual(dados_folha_pos["total_dependentes_salario_familia"], 0)
        self.assertEqual(dados_folha_pos["total_dependentes_plano_saude"], 1)

    def test_rf006_historico_funcional_imutavel_retroativo_e_filtros(self):
        """RF-006: admissão automática, movimentação atômica, vigência retroativa, filtros e imutabilidade (403)."""
        cid = self.colab["id"]

        # 1. Histórico inicial contém admissão
        st, h0 = self._req("GET", f"/api/colaboradores/{cid}/historico-funcional")
        self.assertEqual(st, 200)
        self.assertGreaterEqual(h0["total"], 1)
        self.assertEqual(h0["dados"][0]["tipo_movimentacao"], "admissao")

        # 2. Registrar promoção com reajuste salarial atualizando colaborador em transação atômica
        st, res_prom = self._req("POST", f"/api/colaboradores/{cid}/historico-funcional", {
            "tipo_movimentacao": "promocao",
            "data_vigencia": "2026-03-01",
            "cargo_novo": "Analista de RH Sênior",
            "setor_novo": "Departamento Pessoal",
            "salario_novo": 6200.00,
            "justificativa": "Promoção anual por desempenho",
        })
        self.assertEqual(st, 201)
        mov_prom = res_prom["dados"]
        self.assertIn("Analista de RH Pleno", mov_prom["valor_anterior"])
        self.assertIn("Analista de RH Sênior", mov_prom["valor_novo"])
        self.assertEqual(mov_prom["justificativa"], "Promoção anual por desempenho")

        # Cadastro vigente atualizado automaticamente
        st, colab_atual = self._req("GET", f"/api/colaboradores/{cid}")
        self.assertEqual(st, 200)
        self.assertEqual(colab_atual["dados"]["cargo"], "Analista de RH Sênior")
        self.assertEqual(colab_atual["dados"]["setor"], "Departamento Pessoal")
        self.assertAlmostEqual(float(colab_atual["dados"]["salario_base"]), 6200.00, places=2)

        # 3. Registrar evento retroativo (data_vigencia anterior à promoção)
        st, res_retro = self._req("POST", f"/api/colaboradores/{cid}/historico-funcional", {
            "tipo_movimentacao": "transferencia",
            "data_vigencia": "2025-06-10",
            "centro_custo_novo": "CC-200",
            "justificativa": "Registro retroativo de transferência de centro de custo",
        })
        self.assertEqual(st, 201)
        mov_retro = res_retro["dados"]
        st, colab_pos_retro = self._req("GET", f"/api/colaboradores/{cid}")
        self.assertEqual(colab_pos_retro["dados"]["centro_custo"], "CC-200")

        # Ordenação cronológica descendente por data_vigencia (2026-03-01 antes de 2025-06-10 antes de 2024-02-01)
        st, h_ord = self._req("GET", f"/api/colaboradores/{cid}/historico-funcional")
        vigencias = [m["data_vigencia"] for m in h_ord["dados"]]
        self.assertEqual(vigencias, sorted(vigencias, reverse=True))

        # Filtro por tipo e período
        st, h_filt = self._req("GET", f"/api/colaboradores/{cid}/historico-funcional?tipo=promocao&data_inicio=2026-01-01")
        self.assertEqual(st, 200)
        self.assertEqual(h_filt["total"], 1)

        # 4. Bloqueio de imutabilidade (PUT e DELETE devem retornar 403)
        st_put, _ = self._req("PUT", f"/api/colaboradores/{cid}/historico-funcional/{mov_retro['id']}", {"motivo": "Adulterar"})
        st_del, _ = self._req("DELETE", f"/api/colaboradores/{cid}/historico-funcional/{mov_prom['id']}")
        self.assertEqual(st_put, 403)
        self.assertEqual(st_del, 403)

    def test_rf007_anexos_seguros_versionamento_download_e_inativacao(self):
        """RF-007: validação de MIME/assinatura/scripts, armazenamento privado, versionamento, download e inativação lógica."""
        cid = self.colab["id"]

        # 1. Bloquear arquivos executáveis, scripts e assinatura maliciosa disfarçada de PDF
        for nome_ruim, payload in [
            ("payload.exe", b"MZ\x90\x00executavel"),
            ("script.js", b"alert('xss')"),
            ("shell.php", b"<?php system($_GET['c']); ?>"),
            ("falso.pdf", b"<script>alert(1)</script>"),
            ("binario.pdf", b"MZ\x90\x00disfarcado"),
        ]:
            st, _ = self._req("POST", f"/api/colaboradores/{cid}/documentos", {
                "categoria": "CONTRATOS",
                "tipo_documento": "Contrato de Trabalho",
                "nome_arquivo": nome_ruim,
                "conteudo_base64": base64.b64encode(payload).decode(),
            })
            self.assertEqual(st, 400, f"Arquivo perigoso deveria ser bloqueado: {nome_ruim}")

        # 2. Bloquear path traversal no nome do arquivo (400) e depois fazer upload legítimo de PDF em storage privado
        pdf_v1 = b"%PDF-1.4\n%Conteudo contrato v1 teste QA\n%%EOF"
        st_trav, _ = self._req("POST", f"/api/colaboradores/{cid}/documentos", {
            "categoria": "CONTRATOS",
            "tipo_documento": "Contrato de Trabalho",
            "nome_arquivo": "../../contrato_trabalho_helena.pdf",
            "mime_type": "application/pdf",
            "conteudo_base64": base64.b64encode(pdf_v1).decode(),
        })
        self.assertEqual(st_trav, 400)

        st, res_v1 = self._req("POST", f"/api/colaboradores/{cid}/documentos", {
            "categoria": "CONTRATOS",
            "tipo_documento": "Contrato de Trabalho",
            "nome_arquivo": "contrato_trabalho_helena.pdf",
            "mime_type": "application/pdf",
            "data_emissao": "2026-01-10",
            "data_validade": "2027-01-10",
            "observacao": "Contrato assinado v1",
            "conteudo_base64": base64.b64encode(pdf_v1).decode(),
        })
        self.assertEqual(st, 201)
        doc_v1 = res_v1["dados"]
        self.assertEqual(doc_v1["nome_arquivo"], "contrato_trabalho_helena.pdf")
        self.assertEqual(doc_v1["versao"], 1)
        self.assertTrue(doc_v1["sha256_hash"])

        # Arquivo existe no storage privado (e não no frontend)
        priv_files = []
        for _, _, fs in os.walk(self.private_docs_dir):
            priv_files.extend(fs)
        self.assertEqual(len(priv_files), 1)

        # 3. Nova versão (v2) substitui logicamente v1
        pdf_v2 = b"%PDF-1.4\n%Conteudo contrato v2 aditivado\n%%EOF"
        st, res_v2 = self._req("POST", f"/api/colaboradores/{cid}/documentos/{doc_v1['id']}/versoes", {
            "categoria": "CONTRATOS",
            "tipo_documento": "Contrato de Trabalho",
            "nome_arquivo": "contrato_trabalho_helena_v2.pdf",
            "mime_type": "application/pdf",
            "data_emissao": "2026-06-01",
            "data_validade": "2028-06-01",
            "observacao": "Aditivo salarial v2",
            "conteudo_base64": base64.b64encode(pdf_v2).decode(),
        })
        self.assertEqual(st, 201)
        doc_v2 = res_v2["dados"]
        self.assertEqual(doc_v2["versao"], 2)
        self.assertEqual(doc_v2["documento_raiz_id"], doc_v1["id"])

        # Histórico de versões traz v2 e v1 (substituído)
        st, versoes = self._req("GET", f"/api/colaboradores/{cid}/documentos/{doc_v1['id']}/versoes")
        self.assertEqual(versoes["total"], 2)
        situacoes_v = {v["versao"]: v["situacao"] for v in versoes["dados"]}
        self.assertEqual(situacoes_v[1], "substituido")
        self.assertEqual(situacoes_v[2], "ativo")

        # Filtro por busca textual
        st, busca = self._req("GET", f"/api/colaboradores/{cid}/documentos?categoria=CONTRATOS&q=Aditivo")
        self.assertEqual(busca["total"], 1)
        self.assertEqual(busca["dados"][0]["id"], doc_v2["id"])

        # 4. Download autorizado retorna binário íntegro e gera auditoria de acesso
        st_dl, raw_dl, hdrs_dl = self._req("GET", f"/api/colaboradores/{cid}/documentos/{doc_v2['id']}/download?modo=download", raw_response=True)
        self.assertEqual(st_dl, 200)
        self.assertEqual(raw_dl, pdf_v2)
        self.assertIn("application/pdf", hdrs_dl.get("content-type", ""))
        self.assertIn("attachment", hdrs_dl.get("content-disposition", ""))

        # 5. Inativação lógica mantém arquivo e rastreabilidade
        st_in, _ = self._req("DELETE", f"/api/colaboradores/{cid}/documentos/{doc_v2['id']}", {"motivo": "Substituição contratual"})
        self.assertEqual(st_in, 200)
        st_list_atv, lst_atv = self._req("GET", f"/api/colaboradores/{cid}/documentos")
        self.assertEqual(lst_atv["total"], 0)
        st_list_all, lst_all = self._req("GET", f"/api/colaboradores/{cid}/documentos?incluir_inativos=1")
        self.assertGreaterEqual(lst_all["total"], 2)

    def test_rf008_controle_documentacao_vencimentos_alertas_e_pendencias(self):
        """RF-008: categorias, alertas configuráveis, vencidos/a vencer/regulares e sincronização de pendências."""
        cid = self.colab["id"]

        # 1. Listar 10 categorias padrão e criar uma nova categoria
        st, cats = self._req("GET", "/api/documentos/categorias")
        self.assertEqual(st, 200)
        self.assertGreaterEqual(cats["total"], 10)
        st, nova_cat = self._req("POST", "/api/documentos/categorias", {
            "codigo": "NR35_ALTURA",
            "nome": "Certificado NR-35",
            "obrigatorio": True,
            "exige_validade": True,
            "dias_alerta_padrao": 30,
        })
        self.assertEqual(st, 201)

        # 2. Configurar alertas [45, 20, 5] e tamanho máximo 12 MB
        st, cfg = self._req("PUT", "/api/documentos/config-alertas", {
            "dias_alertas": [45, 20, 5],
            "tamanho_max_mb": 12,
        })
        self.assertEqual(st, 200)
        self.assertEqual(cfg["dados"]["dias_alertas"], [45, 20, 5])
        self.assertEqual(cfg["dados"]["tamanho_max_mb"], 12)

        # 3. Anexar 3 documentos com vencido, próximo do vencimento e regular
        hoje = date.today()
        docs_spec = [
            ("DOC_VENCIDO.pdf", "ASO", (hoje - timedelta(days=10)).isoformat()),
            ("DOC_VENCENDO.pdf", "NR35_ALTURA", (hoje + timedelta(days=15)).isoformat()),
            ("DOC_REGULAR.pdf", "CONTRATOS", (hoje + timedelta(days=180)).isoformat()),
        ]
        for nome, cat, val in docs_spec:
            st_u, _ = self._req("POST", f"/api/colaboradores/{cid}/documentos", {
                "categoria": cat,
                "tipo_documento": cat,
                "nome_arquivo": nome,
                "data_validade": val,
                "conteudo_base64": base64.b64encode(b"%PDF-1.4\n%Teste RF008\n%%EOF").decode(),
            })
            self.assertEqual(st_u, 201)

        # 4. Consultar painel de controle sincronizando pendências
        st, ctrl = self._req("GET", "/api/documentos/controle?sincronizar=1")
        self.assertEqual(st, 200)
        resumo = ctrl["dados"]["resumo"]
        self.assertEqual(resumo["vencidos"], 1)
        self.assertEqual(resumo["proximos_vencimento"], 1)
        self.assertEqual(resumo["regulares"], 1)
        self.assertGreaterEqual(resumo["pendentes"], 1)

        # Filtrar só vencidos
        st, ctrl_v = self._req("GET", "/api/documentos/controle?situacao=vencido")
        self.assertEqual(len(ctrl_v["dados"]["itens"]), 1)
        self.assertEqual(ctrl_v["dados"]["itens"][0]["nome_arquivo"], "DOC_VENCIDO.pdf")

        # Sincronização idempotente não duplica pendências em pendencias_operacionais
        st, _ = self._req("GET", "/api/documentos/controle?sincronizar=1")
        self.assertEqual(st, 200)
        conn_p = self.colab_svc._conn()
        cur_p = conn_p.cursor()
        cur_p.execute("SELECT titulo FROM pendencias_operacionais WHERE modulo = 'Documentação'")
        titulos_p = [r[0] for r in cur_p.fetchall()]
        conn_p.close()
        self.assertGreaterEqual(len(titulos_p), 2)
        self.assertEqual(len(titulos_p), len(set(titulos_p)))

    def test_rf009_dados_bancarios_validacao_conta_principal_e_cnab240(self):
        """RF-009: validações bancárias/PIX, conta principal única, inativação e integração CNAB 240."""
        cid = self.colab["id"]

        # 1. Rejeitar CPF de titular inválido (menos de 11 dígitos) e PIX incompatível
        st, _ = self._req("POST", f"/api/colaboradores/{cid}/dados-bancarios", {
            "banco_codigo": "341",
            "banco_nome": "Itaú Unibanco",
            "agencia": "1234",
            "conta": "56789",
            "tipo_conta": "corrente",
            "titular_nome": "Helena Prado",
            "cpf_titular": "111.111.111-1",
        })
        self.assertEqual(st, 400)

        st, _ = self._req("POST", f"/api/colaboradores/{cid}/dados-bancarios", {
            "banco_codigo": "341",
            "banco_nome": "Itaú Unibanco",
            "agencia": "1234",
            "conta": "56789",
            "tipo_conta": "corrente",
            "titular_nome": "Helena Prado",
            "cpf_titular": "52998224725",
            "tipo_chave_pix": "email",
            "chave_pix": "email_invalido_sem_arroba",
        })
        self.assertEqual(st, 400)

        # 2. Cadastrar conta #1 como principal
        st, res_c1 = self._req("POST", f"/api/colaboradores/{cid}/dados-bancarios", {
            "banco_codigo": "001",
            "banco_nome": "Banco do Brasil",
            "agencia": "1111",
            "conta": "222222",
            "conta_digito": "3",
            "tipo_conta": "salario",
            "titular_nome": "Helena Prado Fictícia",
            "titular_cpf": "52998224725",
            "principal": True,
        })
        self.assertEqual(st, 201)
        c1 = res_c1["dados"]

        # 3. Cadastrar conta #2 como principal -> rebaixa conta #1 automaticamente
        st, res_c2 = self._req("POST", f"/api/colaboradores/{cid}/dados-bancarios", {
            "banco_codigo": "237",
            "banco_nome": "Bradesco",
            "agencia": "4321",
            "conta": "987654",
            "conta_digito": "8",
            "tipo_conta": "corrente",
            "titular_nome": "Helena Prado Fictícia",
            "titular_cpf": "52998224725",
            "chave_pix_tipo": "email",
            "chave_pix": "helena.pix@rh20.local",
            "principal": True,
        })
        self.assertEqual(st, 201)
        c2 = res_c2["dados"]

        st, lst_b = self._req("GET", f"/api/colaboradores/{cid}/dados-bancarios")
        principais = [x for x in lst_b["dados"] if int(x["principal"]) == 1]
        self.assertEqual(len(principais), 1)
        self.assertEqual(principais[0]["id"], c2["id"])

        # 4. Fechar folha e gerar CNAB 240 verificando conta principal no Segmento A
        folha = self.folha_svc.criar_ou_atualizar_folha(
            colaborador_id=cid,
            competencia="2026-08",
            periodo_inicio="2026-08-01",
            periodo_fim="2026-08-31",
            eventos=[],
            usuario="QA Folha",
        )
        self.folha_svc.aprovar_folha(folha["id"], usuario="QA Folha")
        self.folha_svc.fechar_folha(folha["id"], usuario="QA Folha")

        cnab = self.plat_svc.gerar_arquivo_cnab240("2026-08", banco_codigo="001", usuario="QA Financeiro")
        conteudo_cnab = cnab.get("conteudo_cnab") or ""
        seg_a_lines = [ln for ln in conteudo_cnab.splitlines() if len(ln) >= 14 and ln[13] == "A"]
        self.assertEqual(len(seg_a_lines), 1)
        self.assertIn("00237", seg_a_lines[0])          # Banco 237 da conta principal #2
        self.assertIn("04321", seg_a_lines[0])          # Agência 4321 da conta principal #2
        self.assertIn("0000009876548", seg_a_lines[0])  # Conta 987654 + DV 8

        # 5. Editar conta #1 e inativar conta #1
        st_put, _ = self._req("PUT", f"/api/colaboradores/{cid}/dados-bancarios/{c1['id']}", {
            "agencia": "1112",
            "principal": False,
        })
        self.assertEqual(st_put, 200)
        st_del, res_del = self._req("DELETE", f"/api/colaboradores/{cid}/dados-bancarios/{c1['id']}")
        self.assertEqual(st_del, 200)
        self.assertEqual(res_del["dados"]["ativo"], 0)

    def test_rf010_auditoria_cadastral_unificada_e_filtros(self):
        """RF-010: rastreabilidade completa de colaborador, dependentes, histórico funcional, documentos e dados bancários."""
        cid = self.colab["id"]

        # Executar ações em todos os submódulos
        self._req("PATCH", f"/api/colaboradores/{cid}", {"telefone": "(16) 98888-7777"})
        self._req("POST", f"/api/colaboradores/{cid}/dependentes", {
            "nome": "Lucas Auditoria",
            "parentesco": "Filho(a)",
            "cpf": "39053344705",
            "data_nascimento": "2020-02-02",
            "eh_dependente_irrf": True,
        })
        self._req("POST", f"/api/colaboradores/{cid}/historico-funcional", {
            "tipo_movimentacao": "reajuste_salarial",
            "data_vigencia": "2026-04-01",
            "salario_novo": 4900.00,
            "justificativa": "Dissídio coletivo",
        })
        st_doc, res_doc = self._req("POST", f"/api/colaboradores/{cid}/documentos", {
            "categoria": "COMPROVANTES",
            "tipo_documento": "Comprovante de Residência",
            "nome_arquivo": "comprovante.pdf",
            "conteudo_base64": base64.b64encode(b"%PDF-1.4\n%Comprovante\n%%EOF").decode(),
        })
        self.assertEqual(st_doc, 201)
        self._req("GET", f"/api/colaboradores/{cid}/documentos/{res_doc['dados']['id']}/download", raw_response=True)
        self._req("POST", f"/api/colaboradores/{cid}/dados-bancarios", {
            "banco_codigo": "341",
            "banco_nome": "Itaú",
            "agencia": "0500",
            "conta": "112233",
            "conta_digito": "4",
            "tipo_conta": "corrente",
            "titular_nome": "Helena Prado",
            "titular_cpf": "52998224725",
            "principal": True,
        })

        # Consultar auditoria unificada
        st, aud = self._req("GET", f"/api/colaboradores/{cid}/auditoria")
        self.assertEqual(st, 200)
        entidades = {a["entidade"] for a in aud["dados"]}
        self.assertTrue({"colaborador", "dependente", "historico_funcional", "documento", "dados_bancarios"}.issubset(entidades))

        # Validar metadados obrigatórios
        for item in aud["dados"]:
            self.assertTrue(item["data_hora"])
            self.assertTrue(item["usuario_responsavel"])
            self.assertTrue(item["origem"])

        # Filtros por entidade e campo
        st_f, aud_dep = self._req("GET", f"/api/colaboradores/{cid}/auditoria?entidade=dependente")
        self.assertEqual(st_f, 200)
        self.assertGreaterEqual(aud_dep["total"], 1)
        self.assertTrue(all(x["entidade"] == "dependente" for x in aud_dep["dados"]))

    def test_isolamento_multiempresa_rf005_rf010(self):
        """Isolamento multi-tenant: usuário da Empresa B não acessa submódulos de colaborador da Empresa A."""
        from backend.auth import hash_senha
        emp_b_id = "b0000000-0000-0000-0000-000000000002"
        conn = self.colab_svc._conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO empresas (id, cnpj, razao_social, nome_fantasia, regime_tributario, ativo, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, 'lucro_real', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00')""",
            (emp_b_id, "11222333000181", "Empresa Isolada B Ltda", "Empresa B"),
        )
        s_hash, s_salt = hash_senha("SenhaForte#EmpresaB2026!")
        cur.execute(
            """INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, empresa_id, criado_em)
               VALUES (?, ?, ?, ?, ?, 'gestor_rh', 'ativo', ?, '2026-01-01 00:00:00')""",
            ("gestor.empb@rh20.local", "gestor_empb", "Gestor Empresa B", s_hash, s_salt, emp_b_id),
        )
        conn.commit()
        conn.close()
        _, tok_b = self.auth_svc.autenticar("gestor.empb@rh20.local", "SenhaForte#EmpresaB2026!")

        cid_a = self.colab["id"]
        for rota in (
            f"/api/colaboradores/{cid_a}/dependentes",
            f"/api/colaboradores/{cid_a}/historico-funcional",
            f"/api/colaboradores/{cid_a}/documentos",
            f"/api/colaboradores/{cid_a}/dados-bancarios",
            f"/api/colaboradores/{cid_a}/auditoria",
        ):
            st, _ = self._req("GET", rota, token=tok_b)
            self.assertEqual(st, 404, f"Acesso cruzado não deveria retornar dados em {rota}")


if __name__ == "__main__":
    unittest.main()
