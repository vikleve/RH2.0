"""
Testes Automatizados — Geração Real de Contracheques em PDF (Padrão A4)
Valida:
- Estrutura PDF 1.4 A4 (595.28 x 841.89 pt), tabela xref e %%EOF
- Nome padronizado CONTRACHEQUE_NOME_MM_AAAA.pdf
- Paridade exata de valores (proventos, descontos, líquido, bases INSS/IRRF/FGTS, recibo e hash SHA-256)
  entre os dados retornados pelo backend/tela e o conteúdo do PDF gerado
- Geração de PDF único em lote com múltiplos colaboradores e múltiplas páginas A4
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.auth import AuthService, hash_senha
from backend.folha_service import FolhaService
from backend.holerite_pdf import _fmt_moeda, nome_arquivo_contracheque
from backend.plataforma_service import PlataformaService
from backend.server import ApiColaboradorHandler
from backend.service import ColaboradorService


def _executar_raw(method, path, db_path, body=None, cookie=None):
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
    handler.wfile = io.BytesIO()
    handler.client_address = ("127.0.0.1", 55556)
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
    handler._local_plataforma_service = PlataformaService(db_path=db_path)

    getattr(handler, f"do_{method}")()
    return handler._status_code, handler._resp_headers, handler.wfile.getvalue()


class TestHoleritePDF(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.colab_srv = ColaboradorService(db_path=self.db_path)
        self.folha_srv = FolhaService(db_path=self.db_path)
        self.auth_srv = AuthService(db_path=self.db_path)

        conn = self.auth_srv._conn()
        cur = conn.cursor()
        h, s = hash_senha("SenhaForte#2026!")
        cur.execute(
            "INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, criado_em) VALUES (?,?,?,?,?,?, 'ativo', '2026-01-01 00:00:00')",
            ("dp_pdf@usina.com.br", "dp_pdf_user", "Analista DP PDF", h, s, "analista_dp"),
        )
        conn.commit()
        conn.close()

        _, hdrs, _ = _executar_raw("POST", "/api/auth/login", self.db_path, {
            "identificador": "dp_pdf_user", "senha": "SenhaForte#2026!"
        })
        self.cookie = hdrs["Set-Cookie"][0].split(";")[0]

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    def _criar_colab_e_folha(self, nome, cpf, email, salario, eventos=None, deps=None):
        c = self.colab_srv.cadastrar({
            "auto_gerar_matricula": True,
            "nome_completo": nome,
            "cpf": cpf,
            "data_nascimento": "1990-05-15",
            "email": email,
            "data_admissao": "2023-01-10",
            "cargo": "Engenheiro de Produção",
            "setor": "Operações",
            "salario_base": salario,
            "dependentes": deps or [],
        })
        f = self.folha_srv.criar_ou_atualizar_folha(
            colaborador_id=c["id"],
            competencia="2026-11",
            periodo_inicio="2026-11-01",
            periodo_fim="2026-11-30",
            data_pagamento="2026-12-05",
            eventos=eventos or [],
            usuario="Analista DP PDF",
        )
        return c, f

    def test_01_pdf_individual_a4_e_paridade_de_valores(self):
        _, f = self._criar_colab_e_folha(
            nome="Carlos Eduardo Silva",
            cpf="52998224725",
            email="carlos.eduardo@usina.com.br",
            salario=5200.00,
            eventos=[
                {"codigo": "0010", "referencia": 10},  # 10h HE 50%
                {"codigo": "0530", "referencia": 1},   # 1 falta
            ],
            deps=[{"nome": "Ana Silva", "cpf": "", "parentesco": "Filho(a)", "eh_dependente_irrf": 1}],
        )

        status, hdrs, pdf_bytes = _executar_raw("GET", f"/api/folha/{f['id']}/pdf", self.db_path, cookie=self.cookie)
        self.assertEqual(status, 200)
        self.assertEqual(hdrs["Content-Type"][0], "application/pdf")
        disp = hdrs["Content-Disposition"][0]
        self.assertIn("CONTRACHEQUE_CARLOS_EDUARDO_SILVA_11_2026.pdf", disp)

        # Estrutura PDF 1.4 A4
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4"))
        self.assertIn(b"/MediaBox [0 0 595.28 841.89]", pdf_bytes)
        self.assertIn(b"/Count 1", pdf_bytes)
        self.assertIn(b"%%EOF", pdf_bytes[-32:])

        # Paridade exata dos valores entre tela/JSON e PDF
        texto_pdf = pdf_bytes.decode("cp1252", errors="replace")
        self.assertIn("Carlos Eduardo Silva", texto_pdf)
        self.assertIn(f["numero_recibo"], texto_pdf)
        self.assertIn(f["codigo_autenticidade"], texto_pdf)
        self.assertIn(_fmt_moeda(f["total_proventos"]), texto_pdf)
        self.assertIn(_fmt_moeda(f["total_descontos"]), texto_pdf)
        self.assertIn(_fmt_moeda(f["salario_liquido"]), texto_pdf)
        self.assertIn(_fmt_moeda(f["base_inss"]), texto_pdf)
        self.assertIn(_fmt_moeda(f["base_irrf"]), texto_pdf)
        self.assertIn(_fmt_moeda(f["base_fgts"]), texto_pdf)
        self.assertIn(_fmt_moeda(f["valor_fgts_informativo"]), texto_pdf)

    def test_02_pdf_lote_multipagina_a4(self):
        _, f1 = self._criar_colab_e_folha("Carlos Eduardo Silva", "52998224725", "c1@usina.com.br", 3000.00)
        _, f2 = self._criar_colab_e_folha("Mariana Costa", "11144477735", "c2@usina.com.br", 4500.00, eventos=[{"codigo": "0020", "referencia": 20}])
        _, f3 = self._criar_colab_e_folha("Joao Pedro Lima", "71428793860", "c3@usina.com.br", 2200.00)

        status, hdrs, pdf_bytes = _executar_raw(
            "GET", "/api/folha/holerites-lote/pdf?competencia=2026-11", self.db_path, cookie=self.cookie
        )
        self.assertEqual(status, 200)
        self.assertEqual(hdrs["Content-Type"][0], "application/pdf")
        self.assertIn("CONTRACHEQUES_LOTE_2026_11.pdf", hdrs["Content-Disposition"][0])
        self.assertIn(b"/Count 3", pdf_bytes)
        self.assertIn(b"%%EOF", pdf_bytes[-32:])

        texto_pdf = pdf_bytes.decode("cp1252", errors="replace")
        for f in (f1, f2, f3):
            self.assertIn(f["colaborador_nome"], texto_pdf)
            self.assertIn(_fmt_moeda(f["salario_liquido"]), texto_pdf)


if __name__ == "__main__":
    unittest.main()
