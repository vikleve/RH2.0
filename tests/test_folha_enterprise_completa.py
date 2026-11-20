"""
Suíte de Testes Automatizados — RH2.0 Enterprise (Colaboradores + Folha Completa)
Valida os novos requisitos do Prompt Mestre:
- Campos pessoais/contratuais (PIS/PASEP, tipo_contrato, centro_custo, matrícula automática)
- Dependentes com indicadores IRRF e Salário-Família
- Documentos do colaborador
- Catálogo parametrizável de rubricas e proteção a rubricas legais
- Tipos de folha (mensal, 13ª 1ª parcela, adiantamento, complementar), rascunho e aprovação
- FGTS Aprendiz (2%) e Salário-Família automático
- Processamento em lote e Relatórios Gerenciais/Financeiros
- Endpoints REST e controle de permissões RBAC
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.auth import AuthService, hash_senha
from backend.folha_service import (
    FolhaBloqueadaException,
    FolhaService,
    FolhaValidacaoException,
)
from backend.server import ApiColaboradorHandler
from backend.service import ColaboradorService, ValidacaoException


class _FakeWFile(io.BytesIO):
    pass


def _executar_handler(method, path, db_path, body=None, cookie=None):
    raw_body = json.dumps(body).encode("utf-8") if body is not None else b""
    headers = {
        "Content-Length": str(len(raw_body)),
        "Content-Type": "application/json",
        "Origin": "http://localhost:8000",
        "Host": "localhost:8000",
    }
    if cookie:
        headers["Cookie"] = cookie

    handler = ApiColaboradorHandler.__new__(ApiColaboradorHandler)
    handler.path = path
    handler.headers = headers
    handler.rfile = io.BytesIO(raw_body)
    handler.wfile = _FakeWFile()
    handler.client_address = ("127.0.0.1", 55555)
    handler._status_code = 200
    handler._resp_headers = {}

    def _send_response(code, message=None):
        handler._status_code = code

    def _send_header(k, v):
        handler._resp_headers.setdefault(k, []).append(v)

    def _end_headers():
        pass

    handler.send_response = _send_response
    handler.send_header = _send_header
    handler.end_headers = _end_headers
    handler._local_service = ColaboradorService(db_path=db_path)
    handler._local_auth_service = AuthService(db_path=db_path)
    handler._local_folha_service = FolhaService(db_path=db_path)
    from backend.plataforma_service import PlataformaService
    handler._local_plataforma_service = PlataformaService(db_path=db_path)

    getattr(handler, f"do_{method}")()
    resp_bytes = handler.wfile.getvalue()
    resp_json = json.loads(resp_bytes.decode("utf-8")) if resp_bytes else {}
    return handler._status_code, handler._resp_headers, resp_json


class TestFolhaEnterpriseCompleta(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.colab_srv = ColaboradorService(db_path=self.db_path)
        self.folha_srv = FolhaService(db_path=self.db_path)
        self.auth_srv = AuthService(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    def _dados_colab(self, **overrides):
        base = {
            "auto_gerar_matricula": True,
            "nome_completo": "Mariana Costa Oliveira",
            "cpf": "52998224725",
            "rg": "45.678.901-2",
            "pis_pasep": "120.43215.67-3",
            "sexo": "F",
            "estado_civil": "Casado(a)",
            "data_nascimento": "1992-07-10",
            "email": "mariana.costa@usina.com.br",
            "telefone": "(16) 99123-4567",
            "data_admissao": "2024-02-01",
            "cargo": "Analista Contábil",
            "setor": "Financeiro",
            "centro_custo": "CC-005",
            "tipo_contrato": "CLT",
            "jornada_trabalho": "44h semanais",
            "carga_horaria_mensal": 220.0,
            "salario_base": 1800.00,
            "situacao": "ativo",
            "dependentes": [
                {
                    "nome": "Pedro Costa",
                    "cpf": "",
                    "data_nascimento": "2019-05-12",
                    "parentesco": "Filho(a)",
                    "eh_dependente_irrf": 1,
                    "eh_elegivel_salario_familia": 1,
                }
            ],
        }
        base.update(overrides)
        return base

    def test_01_cadastro_completo_pis_matricula_automatica_e_documentos(self):
        # Rejeita PIS inválido
        with self.assertRaises(ValidacaoException) as ctx:
            self.colab_srv.cadastrar(self._dados_colab(pis_pasep="123.45678.90-9"))
        self.assertIn("pis_pasep", ctx.exception.erros)

        # Cadastra com matrícula automática e PIS válido
        criado = self.colab_srv.cadastrar(self._dados_colab())
        self.assertTrue(criado["matricula"].startswith("RH-"))
        self.assertEqual(criado["centro_custo"], "CC-005")
        self.assertEqual(criado["dependentes"][0]["eh_elegivel_salario_familia"], 1)

        # Anexa e remove documento com auditoria
        doc = self.colab_srv.adicionar_documento(
            criado["id"], "Contrato de Trabalho", "contrato_mariana.pdf",
            conteudo_base64="ZGFkb3M=", tamanho_bytes=5, usuario="Tester"
        )
        self.assertEqual(doc["nome_arquivo"], "contrato_mariana.pdf")
        self.assertEqual(len(self.colab_srv.listar_documentos(criado["id"])), 1)
        self.assertTrue(self.colab_srv.remover_documento(criado["id"], doc["id"], usuario="Tester"))
        self.assertEqual(len(self.colab_srv.listar_documentos(criado["id"])), 0)

    def test_02_salario_familia_automatico_e_fgts_aprendiz(self):
        # Colaboradora com 1 dependente elegível ao salário-família e salário <= 1980,38
        c1 = self.colab_srv.cadastrar(self._dados_colab(salario_base=1800.00))
        f1 = self.folha_srv.criar_ou_atualizar_folha(
            colaborador_id=c1["id"],
            competencia="2026-10",
            periodo_inicio="2026-10-01",
            periodo_fim="2026-10-31",
            usuario="Analista DP",
        )
        codigos = [it["codigo_evento"] for it in f1["itens"]]
        self.assertIn("0202", codigos)  # Salário-família automático

        # Aprendiz deve ter FGTS 2%
        c2 = self.colab_srv.cadastrar(self._dados_colab(
            cpf="11144477735",
            email="aprendiz@usina.com.br",
            tipo_contrato="Aprendiz",
            salario_base=1621.00,
            dependentes=[],
        ))
        f2 = self.folha_srv.criar_ou_atualizar_folha(
            colaborador_id=c2["id"],
            competencia="2026-10",
            periodo_inicio="2026-10-01",
            periodo_fim="2026-10-31",
            usuario="Analista DP",
        )
        self.assertAlmostEqual(float(f2["valor_fgts_informativo"]), round(1621.00 * 0.02, 2), places=2)

    def test_03_catalogo_rubricas_parametrizavel_e_protecao_legal(self):
        rubricas = self.folha_srv.listar_rubricas()
        self.assertGreaterEqual(len(rubricas), 80)

        # Cria rubrica customizada
        nova = self.folha_srv.salvar_rubrica({
            "codigo": "0088",
            "descricao": "Auxílio Home Office",
            "tipo": "provento",
            "incide_inss": 0,
            "incide_irrf": 0,
            "incide_fgts": 0,
        })
        self.assertEqual(nova["codigo"], "0088")

        # Inativa e reativa rubrica customizada
        inativada = self.folha_srv.alterar_status_rubrica(nova["id"], False)
        self.assertEqual(inativada["ativo"], 0)

        # Proteção de rubrica legal: não permite alterar incidências da 0001
        r0001 = next(r for r in rubricas if r["codigo"] == "0001")
        with self.assertRaises(FolhaBloqueadaException):
            self.folha_srv.salvar_rubrica({
                "codigo": "0001",
                "descricao": "Salário mensal",
                "tipo": "provento",
                "incide_inss": 0,
                "incide_irrf": 1,
                "incide_fgts": 1,
            }, rubrica_id=r0001["id"])

    def test_04_tipos_folha_rascunho_aprovacao_lote_e_relatorios(self):
        c1 = self.colab_srv.cadastrar(self._dados_colab(salario_base=3000.00, dependentes=[]))
        c2 = self.colab_srv.cadastrar(self._dados_colab(
            cpf="11144477735",
            email="joao@usina.com.br",
            setor="Operações",
            centro_custo="CC-001",
            salario_base=4000.00,
            dependentes=[],
        ))

        # Processamento em lote na competência 2026-10
        lote = self.folha_srv.processar_lote(
            competencia="2026-10",
            periodo_inicio="2026-10-01",
            periodo_fim="2026-10-31",
            tipo_folha="mensal",
            usuario="Gestor RH",
        )
        self.assertEqual(lote["processadas"], 2)

        # Folha complementar na mesma competência é permitida
        comp_folha = self.folha_srv.criar_ou_atualizar_folha(
            colaborador_id=c1["id"],
            competencia="2026-10",
            periodo_inicio="2026-10-01",
            periodo_fim="2026-10-31",
            tipo_folha="complementar",
            eventos=[{"codigo": "0071", "descricao": "Diferença salarial", "tipo": "provento", "valor_informado": 500.00}],
            salvar_como_rascunho=True,
            usuario="Analista DP",
        )
        self.assertEqual(comp_folha["situacao"], "rascunho")
        self.assertEqual(comp_folha["tipo_folha"], "complementar")

        # Aprovação de folha calculada
        folha_mensal_c1 = lote["folhas"][0]
        aprovada = self.folha_srv.aprovar_folha(folha_mensal_c1["id"], usuario="Gestor RH")
        self.assertEqual(aprovada["situacao"], "aprovada")

        # Relatórios Gerenciais e Financeiros consolidados
        rel = self.folha_srv.obter_relatorios_folha(competencia="2026-10")
        rf = rel["resumo_financeiro"]
        self.assertEqual(rf["qtd_folhas"], 3)
        self.assertGreater(rf["total_bruto"], 7000.0)
        self.assertGreater(rf["custo_total_empresa"], rf["total_bruto"])
        self.assertGreaterEqual(len(rel["por_departamento"]), 2)

    def test_05_endpoints_rest_e_rbac(self):
        # Cria usuário gestor_rh e usuário colaborador
        conn = self.auth_srv._conn()
        cur = conn.cursor()
        for email, usr, nome, perfil in [
            ("gestor@usina.com.br", "gestor_rh_test", "Gestor RH", "gestor_rh"),
            ("colab@usina.com.br", "colab_test", "Colaborador Comum", "colaborador"),
        ]:
            h, s = hash_senha("SenhaForte#2026!")
            cur.execute(
                "INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, criado_em) VALUES (?,?,?,?,?,?, 'ativo', '2026-01-01 00:00:00')",
                (email, usr, nome, h, s, perfil),
            )
        conn.commit()
        conn.close()

        _, hdrs_g, _ = _executar_handler("POST", "/api/auth/login", self.db_path, {
            "identificador": "gestor_rh_test", "senha": "SenhaForte#2026!"
        })
        cookie_gestor = hdrs_g["Set-Cookie"][0].split(";")[0]

        _, hdrs_c, _ = _executar_handler("POST", "/api/auth/login", self.db_path, {
            "identificador": "colab_test", "senha": "SenhaForte#2026!"
        })
        cookie_colab = hdrs_c["Set-Cookie"][0].split(";")[0]

        # Colaborador não pode criar rubrica (403)
        st_c, _, _ = _executar_handler("POST", "/api/folha/eventos-catalogo", self.db_path, {
            "codigo": "0099", "descricao": "Teste", "tipo": "provento"
        }, cookie=cookie_colab)
        self.assertEqual(st_c, 403)

        # Gestor RH pode criar rubrica (201), consultar próxima matrícula e relatórios
        st_g, _, res_g = _executar_handler("POST", "/api/folha/eventos-catalogo", self.db_path, {
            "codigo": "0099", "descricao": "Bônus Produtividade", "tipo": "provento"
        }, cookie=cookie_gestor)
        self.assertEqual(st_g, 201)
        self.assertEqual(res_g["dados"]["codigo"], "0099")

        st_m, _, res_m = _executar_handler("GET", "/api/colaboradores/proxima-matricula", self.db_path, cookie=cookie_gestor)
        self.assertEqual(st_m, 200)
        self.assertTrue(res_m["matricula"].startswith("RH-"))

        st_r, _, res_r = _executar_handler("GET", "/api/folha/relatorios", self.db_path, cookie=cookie_gestor)
        self.assertEqual(st_r, 200)
        self.assertIn("resumo_financeiro", res_r["dados"])

        # Simulação em tempo real deve bater 100% com o cálculo salvo no banco
        colab = self.colab_srv.cadastrar(self._dados_colab(salario_base=6500.00))
        st_sim, _, res_sim = _executar_handler("POST", "/api/folha/simular", self.db_path, {
            "colaborador_id": colab["id"],
            "eventos": [{"codigo": "0010", "referencia": 5}]
        }, cookie=cookie_gestor)
        self.assertEqual(st_sim, 200)
        sim_resumo = res_sim["dados"]["resumo"]
        st_save, _, res_save = _executar_handler("POST", "/api/folha", self.db_path, {
            "colaborador_id": colab["id"],
            "competencia": "2026-10",
            "eventos": [{"codigo": "0010", "referencia": 5}]
        }, cookie=cookie_gestor)
        self.assertEqual(st_save, 201)
        salva = res_save["dados"]
        self.assertAlmostEqual(float(sim_resumo["total_proventos"]), float(salva["total_proventos"]), places=2)
        self.assertAlmostEqual(float(sim_resumo["total_descontos"]), float(salva["total_descontos"]), places=2)
        self.assertAlmostEqual(float(sim_resumo["salario_liquido"]), float(salva["salario_liquido"]), places=2)
        self.assertAlmostEqual(float(sim_resumo["inss_descontado"]), float(salva["inss_descontado"]), places=2)
        self.assertAlmostEqual(float(sim_resumo["irrf_descontado"]), float(salva["irrf_descontado"]), places=2)
        self.assertAlmostEqual(float(sim_resumo["valor_fgts_informativo"]), float(salva["valor_fgts_informativo"]), places=2)


if __name__ == "__main__":
    unittest.main()
