"""
Suíte Completa de Testes Automatizados e Integração — RF-011 a RF-020
Processo Admissional Enterprise (SRS Volume 3 — Módulo 02)
Cobre: Registro sem defaults fictícios, Checklist configurável com anexos privados SHA-256,
Validação formal (RN-008/RN-009), Contrato PDF 1.4 real e formalização, eSocial S-2190/S-2200 (v_S_01_02_00),
ASO com sigilo médico, Jornada inicial, Centro de Custo, Benefícios elegíveis, Aprovação RN-080 / dupla alçada /
efetivação atômica com rollback, Cartão Único (painel), RBAC e Multi-tenant BOLA/IDOR.
Utiliza exclusivamente dados fictícios e banco SQLite + diretório privado temporários.
"""
import base64
import json
import os
import secrets
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")
os.environ["GUEST_INITIAL_PASSWORD"] = os.environ.get("GUEST_INITIAL_PASSWORD", "Sintetico#GuestTest2026!")

from backend.auth import AuthService, hash_senha
from backend.database import get_connection, ph
from backend.folha_service import FolhaService
from backend.plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaValidacaoException,
)
from backend.plataforma_service import PlataformaService
from backend.server import ApiColaboradorHandler
from backend.service import ColaboradorService

PDF_MINIMO_BYTES = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
)
PDF_MINIMO_B64 = base64.b64encode(PDF_MINIMO_BYTES).decode("ascii")


def _gerar_cpf_valido(seed9: str) -> str:
    nums = [int(c) for c in seed9]
    s1 = sum(nums[i] * (10 - i) for i in range(9))
    d1 = (s1 * 10) % 11
    d1 = 0 if d1 == 10 else d1
    nums.append(d1)
    s2 = sum(nums[i] * (11 - i) for i in range(10))
    d2 = (s2 * 10) % 11
    d2 = 0 if d2 == 10 else d2
    nums.append(d2)
    return "".join(str(x) for x in nums)


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


class TestAdmissaoRF011RF020(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls._template_db = tempfile.mkstemp(prefix="rh20_rf011_020_tpl_", suffix=".db")
        os.close(fd)
        cls._template_docs = tempfile.mkdtemp(prefix="rh20_rf011_020_docs_")
        os.environ["PRIVATE_DOCS_DIR"] = cls._template_docs

        srv = _FakeServer(cls._template_db)
        _, cls._admin_token = srv.auth_service.autenticar("admin.dp@empresa.com.br", os.environ["ADMIN_INITIAL_PASSWORD"])
        _, cls._rh_token = srv.auth_service.autenticar("visitante@empresa.com.br", os.environ["GUEST_INITIAL_PASSWORD"])

        # Criar usuários adicionais para testar RBAC, sigilo médico e segregação multi-tenant
        cls._senha_teste = "Sintetico#Role2026!"
        cls._criar_usuario_teste(cls._template_db, "medico.sst@empresa.com.br", "medico.sst", "Dra. Helena SST", "medico_sst", "a0000000-0000-0000-0000-000000000001")
        cls._criar_usuario_teste(cls._template_db, "analista.dp2@empresa.com.br", "analista.dp2", "Bruno Analista DP", "analista_dp", "a0000000-0000-0000-0000-000000000001")
        cls._criar_usuario_teste(cls._template_db, "operador.dp@empresa.com.br", "operador.dp", "Paulo Operador DP", "operador_dp", "a0000000-0000-0000-0000-000000000001")
        cls._criar_usuario_teste(cls._template_db, "colab.portal@empresa.com.br", "colab.portal", "Lucas Colaborador", "colaborador", "a0000000-0000-0000-0000-000000000001")

        # Segunda empresa isolada para testes BOLA/IDOR e compatibilidade de escala/CC/benefício
        cls._empresa_b_id = "b0000000-0000-0000-0000-000000000002"
        conn = get_connection(cls._template_db)
        cur = conn.cursor()
        p = ph(cls._template_db)
        cur.execute(
            f"""
            INSERT OR IGNORE INTO empresas (id, cnpj, razao_social, nome_fantasia, regime_tributario, responsavel_nome, responsavel_cpf, ativo, criado_em, atualizado_em)
            VALUES ({p}, '11222333000181', 'Empresa B Filial Isolada Ltda', 'Empresa B Fictícia', 'lucro_real', 'Gestor B', '52998224725', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        """,
            (cls._empresa_b_id,),
        )
        cur.execute(
            f"""
            INSERT INTO escalas_jornada (empresa_id, codigo, descricao, carga_semanal_horas, divisor_mensal, tipo_regime, entrada_padrao, saida_padrao, intervalo_minutos, ativo, criado_em)
            VALUES ({p}, 'ESC-EMP-B', 'Escala Exclusiva Empresa B', 40.0, 200.0, '5x2', '09:00', '18:00', 60, 1, '2026-01-01 00:00:00');
        """,
            (cls._empresa_b_id,),
        )
        cls._escala_emp_b_id = cur.lastrowid
        cur.execute(
            f"""
            INSERT INTO escalas_jornada (empresa_id, codigo, descricao, carga_semanal_horas, divisor_mensal, tipo_regime, entrada_padrao, saida_padrao, intervalo_minutos, ativo, criado_em)
            VALUES ('a0000000-0000-0000-0000-000000000001', 'ESC-INATIVA', 'Escala Desativada', 40.0, 200.0, '5x2', '08:00', '17:00', 60, 0, '2026-01-01 00:00:00');
        """
        )
        cls._escala_inativa_id = cur.lastrowid
        cur.execute(
            f"""
            INSERT INTO centros_custo (id, empresa_id, codigo, descricao, ativo, criado_em)
            VALUES ('cc-emp-b-001', {p}, 'CC-B-01', 'Centro de Custo Empresa B', 1, '2026-01-01 00:00:00'),
                   ('cc-inativo-a', 'a0000000-0000-0000-0000-000000000001', 'CC-OFF', 'Centro de Custo Inativo A', 0, '2026-01-01 00:00:00');
        """,
            (cls._empresa_b_id,),
        )
        conn.commit()
        conn.close()

        cls._criar_usuario_teste(cls._template_db, "admin.empb@empresa.com.br", "admin.empb", "Gestor Empresa B", "admin_empresa", cls._empresa_b_id)

        _, cls._sst_token = srv.auth_service.autenticar("medico.sst@empresa.com.br", cls._senha_teste)
        _, cls._dp2_token = srv.auth_service.autenticar("analista.dp2@empresa.com.br", cls._senha_teste)
        _, cls._op_token = srv.auth_service.autenticar("operador.dp@empresa.com.br", cls._senha_teste)
        _, cls._colab_token = srv.auth_service.autenticar("colab.portal@empresa.com.br", cls._senha_teste)
        _, cls._empb_token = srv.auth_service.autenticar("admin.empb@empresa.com.br", cls._senha_teste)

    @classmethod
    def _criar_usuario_teste(cls, db_path: str, email: str, usuario: str, nome: str, perfil: str, empresa_id: str):
        salt = secrets.token_hex(16)
        senha_hash, _ = hash_senha(cls._senha_teste, salt)
        conn = get_connection(db_path)
        cur = conn.cursor()
        p = ph(db_path)
        cur.execute(
            f"""
            INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, empresa_id, criado_em)
            VALUES ({p},{p},{p},{p},{p},{p},'ativo',{p},'2026-01-01 00:00:00');
        """,
            (email, usuario, nome, senha_hash, salt, perfil, empresa_id),
        )
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("PRIVATE_DOCS_DIR", None)
        try:
            os.remove(cls._template_db)
        except OSError:
            pass
        shutil.rmtree(cls._template_docs, ignore_errors=True)

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="rh20_rf011_020_run_", suffix=".db")
        os.close(fd)
        shutil.copyfile(self._template_db, self.db_path)
        self.private_docs_dir = tempfile.mkdtemp(prefix="rh20_rf011_020_priv_")
        os.environ["PRIVATE_DOCS_DIR"] = self.private_docs_dir

        self.srv = _FakeServer(self.db_path)
        self.plat_svc = self.srv.plataforma_service
        self.folha_svc = self.srv.folha_service
        self.colab_svc = self.srv.colab_service

    def tearDown(self):
        os.environ.pop("PRIVATE_DOCS_DIR", None)
        try:
            os.remove(self.db_path)
        except OSError:
            pass
        shutil.rmtree(self.private_docs_dir, ignore_errors=True)

    def _req(self, method: str, path: str, body=None, token: str = None, raw_response: bool = False):
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
        tok = self._rh_token if token is None else token
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
        handler.headers = headers

        status_holder = {"code": None, "headers": {}}
        handler.send_response = lambda code, message=None: status_holder.__setitem__("code", code)
        handler.send_header = lambda k, v: status_holder["headers"].__setitem__(k.lower(), v)
        handler.end_headers = lambda: None
        getattr(handler, f"do_{method}")()

        if raw_response:
            return status_holder["code"], bytes(handler.wfile.data), status_holder["headers"]
        resp_txt = handler.wfile.data.decode("utf-8") if handler.wfile.data else "{}"
        return status_holder["code"], json.loads(resp_txt)

    def _payload_admissao_base(self, cpf: str, **overrides):
        base = {
            "candidato_nome": "Camila Ferreira Teste",
            "candidato_cpf": cpf,
            "candidato_data_nascimento": "1994-07-22",
            "candidato_email": "camila.ferreira.teste@rh20.local",
            "candidato_telefone": "(16) 99123-4567",
            "candidato_rg": "45.123.678-9",
            "candidato_pis": "12345678901",
            "cargo": "Analista Financeiro I",
            "setor": "Controladoria",
            "departamento": "Financeiro",
            "salario_proposto": 4200.00,
            "data_prevista_admissao": "2026-12-01",
            "tipo_contrato": "experiencia",
            "prazo_experiencia_dias": 45,
            "escala_id": 1,
        }
        base.update(overrides)
        return base

    def _preparar_admissao_completa_para_aprovacao(self, cpf: str, token_criador: str = None, **overrides):
        tok = token_criador or self._rh_token
        st, r = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf, **overrides), token=tok)
        self.assertEqual(st, 201, r)
        adm = r["dados"]
        adm_id = adm["id"]

        # Upload & validação de todos os itens obrigatórios
        for item in adm["checklist"]:
            if item["obrigatorio"]:
                st_u, ru = self._req(
                    "POST",
                    f"/api/admissoes/{adm_id}/checklist/{item['id']}/upload",
                    {"nome_arquivo": f"{item['codigo_documento']}.pdf", "mime_type": "application/pdf", "conteudo_base64": PDF_MINIMO_B64},
                    token=tok,
                )
                self.assertEqual(st_u, 201, ru)
                st_v, rv = self._req(
                    "PATCH",
                    f"/api/admissoes/checklist/{item['id']}",
                    {"status": "validado", "justificativa": "Conferido conforme original"},
                    token=tok,
                )
                self.assertEqual(st_v, 200, rv)

        # ASO admissional real apto (RF-016 / RN-009)
        st_a, ra = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/aso",
            {
                "status_exame": "realizado",
                "resultado": "apto",
                "data_emissao": "2026-11-20",
                "data_validade": "2027-11-20",
                "medico_nome": "Dra. Helena SST",
                "medico_crm": "998877",
                "medico_uf": "SP",
                "observacoes_medicas": "Apto sem restrições clínicas (dado sigiloso)",
                "nome_arquivo": "aso_admissional.pdf",
                "mime_type": "application/pdf",
                "conteudo_base64": PDF_MINIMO_B64,
            },
            token=self._sst_token,
        )
        self.assertEqual(st_a, 201, ra)
        return self.plat_svc.obter_admissao(adm_id)

    # ── RF-011 ────────────────────────────────────────────────────────────────
    def test_rf011_abertura_validacoes_sem_defaults_e_cancelamento(self):
        """RF-011: Registro completo sem preenchimento artificial, bloqueio de CPF inválido/duplicado, edição e cancelamento."""
        cpf1 = _gerar_cpf_valido("111222333")

        # Rejeitar CPF inválido, salário abaixo do piso, falta de nascimento, falta de setor/email
        st, _ = self._req("POST", "/api/admissoes", self._payload_admissao_base("11111111111"))
        self.assertEqual(st, 400)

        for campo in ("candidato_email", "cargo", "setor", "data_prevista_admissao"):
            inv = self._payload_admissao_base(cpf1)
            inv.pop(campo)
            st_c, rc = self._req("POST", "/api/admissoes", inv)
            self.assertEqual(st_c, 400, f"Deveria exigir campo {campo}: {rc}")

        # Sem data de nascimento na abertura inicial não inventa '1990-01-01', mantém None e barra na validação
        sem_nasc = self._payload_admissao_base(_gerar_cpf_valido("111222444"))
        sem_nasc.pop("candidato_data_nascimento")
        st_sn, r_sn = self._req("POST", "/api/admissoes", sem_nasc)
        self.assertEqual(st_sn, 201, r_sn)
        self.assertIsNone(r_sn["dados"]["candidato_data_nascimento"])
        self._req("POST", f"/api/admissoes/{r_sn['dados']['id']}/cancelar", {"motivo": "Teste sem nascimento encerrado"})

        st_sal, _ = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf1, salario_proposto=1200.00))
        self.assertEqual(st_sal, 400)

        # Registro válido preserva dados exatos (zero substituição por defaults fictícios)
        st_ok, r_ok = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf1))
        self.assertEqual(st_ok, 201, r_ok)
        adm = r_ok["dados"]
        self.assertTrue(adm["codigo_processo"].startswith("ADM-"))
        self.assertEqual(adm["candidato_email"], "camila.ferreira.teste@rh20.local")
        self.assertEqual(adm["setor"], "Controladoria")
        self.assertEqual(adm["candidato_data_nascimento"], "1994-07-22")

        # Bloquear outra admissão em andamento para o mesmo CPF
        st_dup, r_dup = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf1))
        self.assertEqual(st_dup, 400, r_dup)

        # Edição controlada e cancelamento justificável
        st_ed, r_ed = self._req("PUT", f"/api/admissoes/{adm['id']}", {"cargo": "Analista Financeiro II", "salario_proposto": 4600.00})
        self.assertEqual(st_ed, 200, r_ed)
        self.assertEqual(r_ed["dados"]["cargo"], "Analista Financeiro II")

        st_can, r_can = self._req("POST", f"/api/admissoes/{adm['id']}/cancelar", {"motivo": "Candidato desistiu antes da assinatura"})
        self.assertEqual(st_can, 200, r_can)
        self.assertEqual(r_can["dados"]["status"], "cancelado")

        # Após cancelamento o mesmo CPF pode iniciar novo processo
        st_novo, _ = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf1))
        self.assertEqual(st_novo, 201)

    # ── RF-012 ────────────────────────────────────────────────────────────────
    def test_rf012_checklist_configuravel_upload_privado_rejeicao_dispensa_e_historico(self):
        """RF-012: Itens configuráveis, upload seguro em storage privado, rejeição/dispensa justificadas, versionamento e download."""
        cpf = _gerar_cpf_valido("222333444")
        st, r = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf))
        self.assertEqual(st, 201)
        adm = r["dados"]
        adm_id = adm["id"]
        self.assertEqual(len(adm["checklist"]), 8)

        # Configurar novo item obrigatório específico da função
        st_cfg, r_cfg = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/checklist",
            {"codigo_documento": "CERT_NR35", "item_descricao": "Certificado NR-35 Trabalho em Altura", "obrigatorio": True},
        )
        self.assertEqual(st_cfg, 201, r_cfg)
        novo_item_id = r_cfg["item_id"]

        # Bloquear arquivo executável/extensão proibida
        st_bad, _ = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/checklist/{novo_item_id}/upload",
            {
                "nome_arquivo": "virus.exe",
                "mime_type": "application/octet-stream",
                "conteudo_base64": base64.b64encode(b"MZfakeexe").decode("ascii"),
            },
        )
        self.assertEqual(st_bad, 400)

        # Upload real v1 no diretório privado isolado
        st_up1, r_up1 = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/checklist/{novo_item_id}/upload",
            {
                "nome_arquivo": "cert_nr35_v1.pdf",
                "mime_type": "application/pdf",
                "conteudo_base64": PDF_MINIMO_B64,
                "observacao": "Frente e verso legíveis",
            },
        )
        self.assertEqual(st_up1, 201, r_up1)
        self.assertEqual(r_up1["versao"], 1)
        self.assertTrue(r_up1["sha256_hash"])

        # Rejeição exige justificativa; sem ela retorna 400
        st_rj0, _ = self._req("PATCH", f"/api/admissoes/checklist/{novo_item_id}", {"status": "rejeitado"})
        self.assertEqual(st_rj0, 400)

        st_rj1, _ = self._req(
            "PATCH",
            f"/api/admissoes/checklist/{novo_item_id}",
            {"status": "rejeitado", "justificativa": "Data de vencimento ilegível"},
        )
        self.assertEqual(st_rj1, 200)

        # Item rejeitado não pode pular direto para validado sem justificativa de revisão / reenvio
        st_pula, _ = self._req("PATCH", f"/api/admissoes/checklist/{novo_item_id}", {"status": "validado"})
        self.assertEqual(st_pula, 400)

        # Reenvio v2 + validação + histórico preservado
        st_up2, r_up2 = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/checklist/{novo_item_id}/upload",
            {"nome_arquivo": "cert_nr35_v2.pdf", "mime_type": "application/pdf", "conteudo_base64": PDF_MINIMO_B64},
        )
        self.assertEqual(st_up2, 201)
        self.assertEqual(r_up2["versao"], 2)

        st_val, _ = self._req("PATCH", f"/api/admissoes/checklist/{novo_item_id}", {"status": "validado"})
        self.assertEqual(st_val, 200)

        # Dispensa de item opcional com justificativa obrigatória
        item_opc = next(i for i in adm["checklist"] if not i["obrigatorio"])
        st_dp0, _ = self._req("PATCH", f"/api/admissoes/checklist/{item_opc['id']}", {"status": "dispensado"})
        self.assertEqual(st_dp0, 400)
        st_dp1, _ = self._req(
            "PATCH",
            f"/api/admissoes/checklist/{item_opc['id']}",
            {"status": "dispensado", "justificativa": "Candidato sem dependentes declarados"},
        )
        self.assertEqual(st_dp1, 200)

        # Download autorizado do arquivo privado + verificação do histórico completo
        st_dl, raw_pdf, hdrs = self._req("GET", f"/api/admissoes/{adm_id}/checklist/{novo_item_id}/download", raw_response=True)
        self.assertEqual(st_dl, 200)
        self.assertEqual(raw_pdf, PDF_MINIMO_BYTES)
        self.assertIn("application/pdf", hdrs.get("content-type", ""))

        adm_atual = self.plat_svc.obter_admissao(adm_id)
        self.assertTrue(len(adm_atual["checklist_historico"]) >= 5)

    # ── RF-013 ────────────────────────────────────────────────────────────────
    def test_rf013_validacao_admissional_formal_e_bloqueios(self):
        """RF-013: Validação admissional detalha aprovados/pendentes/inválidos e bloqueia sem ASO ou jornada."""
        cpf = _gerar_cpf_valido("333444555")
        st, r = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf, escala_id=None))
        self.assertEqual(st, 201)
        adm_id = r["dados"]["id"]

        st_v, rv = self._req("POST", f"/api/admissoes/{adm_id}/validar", {"exigir_centro_custo": True})
        self.assertEqual(st_v, 200, rv)
        dados_v = rv["dados"]
        self.assertFalse(dados_v["apto_efetivacao"])
        self.assertTrue(len(dados_v["aprovados"]) >= 4)
        self.assertTrue(any("Jornada" in m for m in dados_v["pendentes"]))
        self.assertTrue(any("Centro de Custo" in m for m in dados_v["pendentes"]))
        self.assertTrue(any("ASO" in m for m in dados_v["pendentes"]))

        # Snapshot persistido no banco
        adm_det = self.plat_svc.obter_admissao(adm_id)
        self.assertTrue(len(adm_det["validacoes"]) >= 1)

    # ── RF-014 ────────────────────────────────────────────────────────────────
    def test_rf014_contrato_trabalho_pdf_real_modelos_versionamento_e_formalizacao(self):
        """RF-014: Geração de PDF 1.4 real a partir de modelo configurável, bloqueio de dados incompletos, versionamento e formalização."""
        st_m, rm = self._req("GET", "/api/admissoes/contratos/modelos")
        self.assertEqual(st_m, 200)
        self.assertTrue(rm["total"] >= 5)

        cpf = _gerar_cpf_valido("444555666")
        st, r = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf))
        self.assertEqual(st, 201)
        adm_id = r["dados"]["id"]

        # Gerar contrato v1
        st_c1, rc1 = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/contratos/gerar",
            {"condicoes_adicionais": "Cláusula específica de confidencialidade e home office híbrido."},
        )
        self.assertEqual(st_c1, 201, rc1)
        ctr1 = rc1["dados"]
        self.assertEqual(ctr1["versao"], 1)

        # Download do PDF real
        st_dl, pdf_bytes, hdrs = self._req("GET", f"/api/admissoes/{adm_id}/contratos/{ctr1['id']}/download", raw_response=True)
        self.assertEqual(st_dl, 200)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        self.assertIn(b"Camila Ferreira Teste", pdf_bytes)
        self.assertIn("application/pdf", hdrs.get("content-type", ""))

        # Formalizar v1 (exige permissão admissoes:aprovar -> usar _admin_token)
        st_f, rf = self._req("POST", f"/api/admissoes/{adm_id}/contratos/{ctr1['id']}/formalizar", {}, token=self._admin_token)
        self.assertEqual(st_f, 200, rf)
        self.assertEqual(rf["dados"]["formalizado"], 1)

        # Nova versão v2 mantém v1 preservada e formalizada
        st_c2, rc2 = self._req("POST", f"/api/admissoes/{adm_id}/contratos/gerar", {"condicoes_adicionais": "Revisão v2"})
        self.assertEqual(st_c2, 201, rc2)
        self.assertEqual(rc2["dados"]["versao"], 2)

        adm_det = self.plat_svc.obter_admissao(adm_id)
        versoes = {c["versao"]: c for c in adm_det["contratos"]}
        self.assertEqual(versoes[1]["formalizado"], 1)
        self.assertTrue(bool(versoes[1]["formalizado_por"]))
        self.assertEqual(versoes[2]["formalizado"], 0)

    # ── RF-015 ────────────────────────────────────────────────────────────────
    def test_rf015_esocial_s2190_s2200_leiaute_schema_sequenciamento_e_sem_recibo_ficticio(self):
        """RF-015: Aplicabilidade S-2190/S-2200, validação XML schema v_S_01_02_00, anti-duplicidade, retorno/reprocessamento e zero recibo falso."""
        cpf = _gerar_cpf_valido("555666777")
        st, r = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf))
        self.assertEqual(st, 201)
        adm_id = r["dados"]["id"]

        # 1. Em admissão inicial ainda sem efetivação, gerar S-2190 preliminar válido
        st_e1, re1 = self._req("POST", f"/api/admissoes/{adm_id}/esocial/gerar", {"tipo_evento": "S-2190", "ambiente": "homologacao"})
        self.assertEqual(st_e1, 201, re1)
        evt1 = re1["dados"]
        self.assertEqual(evt1["tipo_evento"], "S-2190")
        self.assertEqual(evt1["status"], "validado")
        self.assertIsNone(evt1["numero_recibo"])
        self.assertIn("v_S_01_02_00", evt1["xml_conteudo"])

        # 2. Anti-duplicidade bloqueia segundo S-2190 ativo
        st_dup, _ = self._req("POST", f"/api/admissoes/{adm_id}/esocial/gerar", {"tipo_evento": "S-2190"})
        self.assertEqual(st_dup, 400)

        # 3. Bloqueia recibo fictício SIM- no registro de retorno
        st_sim, _ = self._req(
            "POST",
            f"/api/admissoes/esocial/{evt1['id']}/retorno",
            {"status_retorno": "aceito", "codigo_resposta": "201", "mensagem_resposta": "OK", "numero_recibo": "SIM-123456"},
        )
        self.assertEqual(st_sim, 400)

        # 4. Simular retorno real de rejeição e reprocessar de forma controlada
        st_rej, rrej = self._req(
            "POST",
            f"/api/admissoes/esocial/{evt1['id']}/retorno",
            {"status_retorno": "rejeitado", "codigo_resposta": "401", "mensagem_resposta": "Lotação incompatível no lote"},
        )
        self.assertEqual(st_rej, 200, rrej)
        self.assertEqual(rrej["dados"]["status"], "rejeitado")

        st_rep, rrep = self._req("POST", f"/api/admissoes/esocial/{evt1['id']}/reprocessar", {})
        self.assertEqual(st_rep, 201, rrep)
        self.assertEqual(rrep["dados"]["tipo_evento"], "S-2190")
        self.assertNotEqual(rrep["dados"]["id"], evt1["id"])

        # 5. Sequenciar para S-2200 completo em v_S_01_02_00 e impedir duplicidade de S-2200
        st_2200, r_2200 = self._req("POST", f"/api/admissoes/{adm_id}/esocial/gerar", {"tipo_evento": "S-2200"})
        self.assertEqual(st_2200, 201, r_2200)
        self.assertIn("evtAdmissao/v_S_01_02_00", r_2200["dados"]["xml_conteudo"])

        st_2200_dup, _ = self._req("POST", f"/api/admissoes/{adm_id}/esocial/gerar", {"tipo_evento": "S-2200"})
        self.assertEqual(st_2200_dup, 400)

    # ── RF-016 ────────────────────────────────────────────────────────────────
    def test_rf016_aso_admissional_rn009_e_sigilo_medico(self):
        """RF-016 / RN-009: Aprovação bloqueada sem ASO ou com ASO inapto mesmo se checklist ASO marcado validado; sigilo médico."""
        cpf = _gerar_cpf_valido("666777888")
        st, r = self._req("POST", "/api/admissoes", self._payload_admissao_base(cpf))
        self.assertEqual(st, 201)
        adm = r["dados"]
        adm_id = adm["id"]

        # Marcar TODOS os itens do checklist como validados manualmente (tentando burlar RN-009)
        for item in adm["checklist"]:
            if item["obrigatorio"]:
                self._req("PATCH", f"/api/admissoes/checklist/{item['id']}", {"status": "validado"})

        # Sem ASO real em sst_asos, aprovar deve ser BLOQUEADO!
        st_b1, rb1 = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {}, token=self._admin_token)
        self.assertEqual(st_b1, 400, rb1)
        self.assertIn("RN-009", rb1["mensagem"])

        # Registrar ASO INAPTO também bloqueia aprovação
        st_in, _ = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/aso",
            {
                "status_exame": "realizado",
                "resultado": "inapto",
                "data_emissao": "2026-11-20",
                "medico_nome": "Dra. Helena SST",
                "medico_crm": "998877",
                "medico_uf": "SP",
                "observacoes_medicas": "Restrição clínica confidencial para função.",
                "nome_arquivo": "aso_inapto.pdf",
                "mime_type": "application/pdf",
                "conteudo_base64": PDF_MINIMO_B64,
            },
            token=self._sst_token,
        )
        self.assertEqual(st_in, 201)

        # Mesmo que tentem forçar o item ASO_ADMISSIONAL no checklist para validado após o exame INAPTO,
        # o motor bloqueia pela regra RN-009 (ASO real != apto)
        item_aso = next(i for i in adm["checklist"] if i["codigo_documento"] == "ASO_ADMISSIONAL")
        self._req("PATCH", f"/api/admissoes/checklist/{item_aso['id']}", {"status": "validado", "justificativa": "Tentativa manual de burla"})

        st_b2, rb2 = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {}, token=self._admin_token)
        self.assertEqual(st_b2, 400, rb2)
        self.assertIn("inapto", rb2["mensagem"].lower())

        # Sigilo médico: analista_rh vê apenas resumo restrito e não baixa documento médico (403)
        st_sig, r_sig = self._req("GET", f"/api/admissoes/{adm_id}/aso", token=self._rh_token)
        self.assertEqual(st_sig, 200)
        self.assertTrue(r_sig["dados"]["restrito_sigilo_medico"])
        self.assertNotIn("observacoes_medicas", r_sig["dados"])
        self.assertNotIn("medico_crm", r_sig["dados"])

        st_dl_neg, _ = self._req("GET", f"/api/admissoes/{adm_id}/aso/download", token=self._rh_token)
        self.assertEqual(st_dl_neg, 403)

        # Perfil medico_sst vê dados clínicos e baixa PDF (200)
        st_lib, r_lib = self._req("GET", f"/api/admissoes/{adm_id}/aso", token=self._sst_token)
        self.assertEqual(st_lib, 200)
        self.assertEqual(r_lib["dados"]["medico_crm"], "998877")
        self.assertIn("confidencial", r_lib["dados"]["observacoes_medicas"])

        st_dl_ok, raw_aso, _ = self._req("GET", f"/api/admissoes/{adm_id}/aso/download", token=self._sst_token, raw_response=True)
        self.assertEqual(st_dl_ok, 200)
        self.assertEqual(raw_aso, PDF_MINIMO_BYTES)

    # ── RF-017 ────────────────────────────────────────────────────────────────
    def test_rf017_jornada_inicial_escalas_empresa_e_vinculo_efetivacao(self):
        """RF-017: Vincula escala ativa compatível com empresa, bloqueia inativa/outra empresa e propaga na efetivação."""
        cpf = _gerar_cpf_valido("777888999")
        adm = self._preparar_admissao_completa_para_aprovacao(cpf)
        adm_id = adm["id"]

        # Bloquear escala inexistente, inativa e de outra empresa
        for esc_bad in (999999, self._escala_inativa_id, self._escala_emp_b_id):
            st_bad, _ = self._req("POST", f"/api/admissoes/{adm_id}/jornada", {"escala_id": esc_bad})
            self.assertEqual(st_bad, 400)

        # Criar nova escala na empresa A e vincular à admissão com vigência
        st_ne, rne = self._req(
            "POST",
            "/api/admissoes/escalas",
            {
                "codigo": "ESC-12X36-LAB",
                "descricao": "Turno Especial 07:00 às 16:00",
                "tipo_regime": "5x2",
                "entrada_padrao": "07:00",
                "saida_padrao": "16:00",
                "intervalo_minutos": 60,
                "carga_semanal_horas": 40.0,
                "divisor_mensal": 200.0,
            },
        )
        self.assertEqual(st_ne, 201, rne)
        esc_id = rne["dados"]["id"]

        st_vj, rvj = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/jornada",
            {"escala_id": esc_id, "vigencia_inicio": "2026-12-01", "observacao": "Escala inicial acordada"},
        )
        self.assertEqual(st_vj, 200, rvj)

        st_ap, rap = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {}, token=self._admin_token)
        self.assertEqual(st_ap, 200, rap)
        colab = self.colab_svc.obter_por_id(rap["colaborador_id"])
        self.assertEqual(int(colab["escala_id"]), esc_id)
        self.assertIn("07:00", colab["jornada_trabalho"])

    # ── RF-018 ────────────────────────────────────────────────────────────────
    def test_rf018_centro_custo_ativo_empresa_e_integracao_folha(self):
        """RF-018: Vincula centro de custo ativo compatível com a empresa, grava histórico e integra colaborador/folha."""
        cpf = _gerar_cpf_valido("888999111")
        adm = self._preparar_admissao_completa_para_aprovacao(cpf)
        adm_id = adm["id"]

        # Bloquear centro de custo inexistente, inativo ou de outra empresa
        for cc_bad in ("cc-nao-existe", "cc-inativo-a", "cc-emp-b-001"):
            st_b, _ = self._req("POST", f"/api/admissoes/{adm_id}/centro-custo", {"centro_custo_id": cc_bad})
            self.assertEqual(st_b, 400)

        st_cc, rcc = self._req(
            "POST",
            "/api/admissoes/centros-custo",
            {"codigo": "CC-ADM-FIN", "descricao": "Controladoria Corporativa", "gestor_responsavel": "Diretor Financeiro", "orcamento_mensal": 85000.0},
        )
        self.assertEqual(st_cc, 201, rcc)
        cc_obj = rcc["dados"]

        st_vcc, rvcc = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/centro-custo",
            {"centro_custo_id": cc_obj["id"], "vigencia_inicio": "2026-12-01"},
        )
        self.assertEqual(st_vcc, 200, rvcc)

        st_ap, rap = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {"exigir_centro_custo": True}, token=self._admin_token)
        self.assertEqual(st_ap, 200, rap)
        colab = self.colab_svc.obter_por_id(rap["colaborador_id"])
        self.assertEqual(colab["centro_custo"], "CC-ADM-FIN - Controladoria Corporativa")
        adm_pos = self.plat_svc.obter_admissao(adm_id)
        self.assertEqual(adm_pos["centro_custo_id"], cc_obj["id"])

        # Integração real com criação da folha de pagamento
        folha = self.folha_svc.criar_ou_atualizar_folha(
            colaborador_id=colab["id"],
            competencia="2026-12",
            periodo_inicio="2026-12-01",
            periodo_fim="2026-12-31",
            eventos=[],
            usuario="QA Homologação",
        )
        self.assertEqual(folha["colaborador_id"], colab["id"])
        self.assertAlmostEqual(float(folha["salario_base_contratual"]), 4200.00, places=2)

    # ── RF-019 ────────────────────────────────────────────────────────────────
    def test_rf019_beneficios_elegibilidade_ativacao_e_integracao_folha(self):
        """RF-019: Avalia elegibilidade por tipo contrato/tempo/empresa, bloqueia incompatível e ativa benefícios na efetivação."""
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO beneficios_catalogo (
                empresa_id, codigo, nome, tipo, coparticipacao_tipo, coparticipacao_valor,
                teto_legal_percentual, regra_elegibilidade, rubrica_codigo,
                valor_mensal_padrao, valor_diario_padrao, limite_padrao, descricao, ativo, criado_em, atualizado_em
            ) VALUES (
                'a0000000-0000-0000-0000-000000000001', 'PLR_1ANO', 'Bônus Fidelidade 1 Ano', 'flexivel',
                'percentual', 0.0, 0.0, '{"tipos_contrato_permitidos": ["clt"], "tempo_minimo_dias": 365}', '0519',
                500.0, 0.0, 0.0, 'Elegível após 1 ano de empresa', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00'
            );
        """
        )
        benef_ineligivel_id = cur.lastrowid
        conn.commit()
        cur.execute("SELECT id, codigo FROM beneficios_catalogo WHERE empresa_id = 'a0000000-0000-0000-0000-000000000001' AND ativo = 1 ORDER BY id ASC;")
        cats = cur.fetchall()
        conn.close()

        benef_vt_id = next(row[0] for row in cats if "VT" in str(row[1]).upper() or "TRANSP" in str(row[1]).upper())

        cpf = _gerar_cpf_valido("999111222")
        adm = self._preparar_admissao_completa_para_aprovacao(cpf)
        adm_id = adm["id"]

        # Listagem de elegibilidade distingue elegível vs inelegível
        st_el, rel = self._req("GET", f"/api/admissoes/{adm_id}/beneficios-elegiveis")
        self.assertEqual(st_el, 200, rel)
        mapa = {b["id"]: b for b in rel["dados"]}
        self.assertFalse(mapa[benef_ineligivel_id]["elegivel"])
        self.assertTrue(mapa[benef_vt_id]["elegivel"])

        # Tentar associar benefício inelegível falha (400)
        st_b_bad, _ = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/beneficios",
            {"beneficios": [{"beneficio_id": benef_ineligivel_id}]},
        )
        self.assertEqual(st_b_bad, 400)

        # Associar Vale-Transporte elegível e aprovar
        st_b_ok, rb_ok = self._req(
            "POST",
            f"/api/admissoes/{adm_id}/beneficios",
            {"beneficios": [{"beneficio_id": benef_vt_id, "optante": 1, "valor_diario": 14.0, "vigencia_inicio": "2026-12-01"}]},
        )
        self.assertEqual(st_b_ok, 200, rb_ok)

        st_ap, rap = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {}, token=self._admin_token)
        self.assertEqual(st_ap, 200, rap)
        cid = rap["colaborador_id"]

        # Verificar benefício ativo no módulo de benefícios e refletido no motor da folha
        vinculos = self.plat_svc.listar_beneficios_colaboradores(colaborador_id=cid, apenas_ativos=True)
        self.assertEqual(len(vinculos), 1)
        self.assertEqual(int(vinculos[0]["beneficio_id"]), benef_vt_id)

        desc_folha = self.plat_svc.obter_descontos_beneficios_folha(colaborador_id=cid, competencia="2026-12")
        self.assertTrue(desc_folha["total_descontos_beneficios"] > 0)

    # ── RF-020 + RBAC + Multi-tenant + Painel ─────────────────────────────────
    def test_rf020_segregacao_dupla_aprovacao_rollback_atomico_painel_rbac_e_multitenant(self):
        """RF-020: RN-080, dupla aprovação, rollback atômico sem órfãos, painel único 10 etapas, RBAC 403 e BOLA/IDOR 404."""
        # 1. RBAC: operador_dp e colaborador não podem acessar nem criar admissão (403)
        st_op, _ = self._req("GET", "/api/admissoes", token=self._op_token)
        self.assertEqual(st_op, 403)
        st_col, _ = self._req("POST", "/api/admissoes", self._payload_admissao_base(_gerar_cpf_valido("123123123")), token=self._colab_token)
        self.assertEqual(st_col, 403)

        # 2. Preparar admissão com dupla aprovação exigida e todas as etapas configuradas
        cpf = _gerar_cpf_valido("102030405")
        adm = self._preparar_admissao_completa_para_aprovacao(cpf, token_criador=self._rh_token, dupla_aprovacao_exigida=1)
        adm_id = adm["id"]

        st_cc, rcc = self._req("POST", "/api/admissoes/centros-custo", {"codigo": "CC-PAINEL-10", "descricao": "Centro Painel"}, token=self._rh_token)
        self.assertEqual(st_cc, 201, rcc)
        self._req("POST", f"/api/admissoes/{adm_id}/centro-custo", {"centro_custo_id": rcc["dados"]["id"]}, token=self._rh_token)
        _, rel_b = self._req("GET", f"/api/admissoes/{adm_id}/beneficios-elegiveis", token=self._rh_token)
        vt = next(b for b in rel_b["dados"] if b["elegivel"])
        self._req("POST", f"/api/admissoes/{adm_id}/beneficios", {"beneficios": [{"beneficio_id": vt["id"], "optante": 1}]}, token=self._rh_token)
        self._req("POST", f"/api/admissoes/{adm_id}/contratos/gerar", {}, token=self._rh_token)
        self._req("POST", f"/api/admissoes/{adm_id}/validar", {"exigir_centro_custo": True}, token=self._rh_token)

        # Solicitar aprovação formal
        st_sol, rsol = self._req("POST", f"/api/admissoes/{adm_id}/solicitar-aprovacao", {"justificativa": "Pronto para alçada"}, token=self._rh_token)
        self.assertEqual(st_sol, 200, rsol)
        self.assertEqual(rsol["status"], "aguardando_aprovacao")

        # RN-080: criador tentando aprovar a própria admissão é bloqueado (403)
        st_seg, _ = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {}, token=self._rh_token)
        self.assertEqual(st_seg, 403)

        # Multi-tenant BOLA/IDOR: empresa B tentando acessar ou aprovar admissão da empresa A recebe 404
        st_idor, _ = self._req("GET", f"/api/admissoes/{adm_id}", token=self._empb_token)
        self.assertEqual(st_idor, 404)
        st_idor_ap, _ = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {}, token=self._empb_token)
        self.assertEqual(st_idor_ap, 404)

        # 1ª aprovação (Administrador) em dupla aprovação -> ainda não efetiva
        st_ap1, rap1 = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {"justificativa": "1ª alçada OK"}, token=self._admin_token)
        self.assertEqual(st_ap1, 200, rap1)
        self.assertTrue(rap1.get("aguardando_segunda_aprovacao"))

        # Mesmo aprovador tentando dar a 2ª aprovação é bloqueado (403)
        st_same, _ = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {"justificativa": "Tentativa 2ª"}, token=self._admin_token)
        self.assertEqual(st_same, 403)

        # 3. Teste real de rollback atômico: falha simulada na geração do S-2200 após inserir colaborador
        with patch("backend.admissao_service.gerar_xml_s2200", side_effect=RuntimeError("Falha simulada eSocial mid-transaction")):
            with self.assertRaises(RuntimeError):
                self.plat_svc.aprovar_admissao(adm_id, aprovador="Bruno Analista DP", justificativa="Teste Rollback")

        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM colaboradores WHERE cpf = ?;", (cpf,))
        self.assertEqual(cur.fetchone()[0], 0, "Rollback falhou: colaborador órfão persistido!")
        conn.close()

        # 4. 2ª aprovação válida (Bruno Analista DP) efetiva tudo atomicamente
        st_ap2, rap2 = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {"justificativa": "2ª alçada homologada"}, token=self._dp2_token)
        self.assertEqual(st_ap2, 200, rap2)
        self.assertEqual(rap2["status"], "efetivado")
        cid = rap2["colaborador_id"]
        self.assertTrue(rap2["matricula"].startswith("FV-"))

        # Idempotência: segunda chamada de aprovação é bloqueada (400) e não duplica colaborador
        st_idem, _ = self._req("POST", f"/api/admissoes/{adm_id}/aprovar", {}, token=self._dp2_token)
        self.assertEqual(st_idem, 400)

        # Verificar integrações atômicas pós-efetivação
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM historico_funcional WHERE colaborador_id = ?;", (cid,))
        self.assertGreaterEqual(cur.fetchone()[0], 1)
        cur.execute("SELECT COUNT(*) FROM periodos_aquisitivos WHERE colaborador_id = ?;", (cid,))
        self.assertEqual(cur.fetchone()[0], 1)
        cur.execute("SELECT COUNT(*) FROM colaborador_documentos WHERE colaborador_id = ?;", (cid,))
        self.assertGreaterEqual(cur.fetchone()[0], 6)
        cur.execute("SELECT COUNT(*) FROM esocial_eventos WHERE identificador_origem = ? AND tipo_evento = 'S-2200';", (str(cid),))
        self.assertGreaterEqual(cur.fetchone()[0], 1)
        cur.execute("SELECT COUNT(*) FROM pendencias_operacionais WHERE colaborador_id = ? AND tipo_pendencia = 'experiencia_vencendo';", (cid,))
        self.assertEqual(cur.fetchone()[0], 1)
        cur.execute("SELECT COUNT(*) FROM sst_asos WHERE admissao_id = ? AND colaborador_id = ?;", (adm_id, cid))
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

        # 5. Painel Unificado (Cartão Único de Acompanhamento Admissional)
        st_pan, rpan = self._req("GET", f"/api/admissoes/{adm_id}/painel", token=self._admin_token)
        self.assertEqual(st_pan, 200, rpan)
        painel = rpan["dados"]
        self.assertEqual(len(painel["etapas"]), 10)
        self.assertEqual(painel["resumo"]["progresso_percentual"], 100)
        self.assertIn("***", painel["identificacao"]["cpf_mascarado"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
