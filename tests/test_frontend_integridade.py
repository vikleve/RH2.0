"""
Guarda de regressao do frontend (falha de login por merge quebrado).

Causa original: um merge deixou app.js com erro de sintaxe e removeu do index.html os
modais usados por configurarEventos(); o JS abortava antes de ligar o formulario de login
(tela de login sem reacao e sem mensagem). Estes testes impedem a recorrencia.
"""
import os
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS = os.path.join(RAIZ, "frontend", "app.js")
INDEX_HTML = os.path.join(RAIZ, "frontend", "index.html")


def _ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


class _Balanceamento(HTMLParser):
    VOID = {"meta", "link", "input", "br", "img", "hr", "col", "source", "area", "base", "wbr"}

    def __init__(self):
        super().__init__()
        self.pilha, self.erros, self.ids = [], [], []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id" and v:
                self.ids.append(v)
        if tag not in self.VOID:
            self.pilha.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.pilha or self.pilha[-1][0] != tag:
            self.erros.append((tag, self.getpos()[0]))
        else:
            self.pilha.pop()


class TestFrontendIntegridade(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node nao instalado")
    def test_app_js_tem_sintaxe_valida(self):
        r = subprocess.run(["node", "--check", APP_JS], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"Erro de sintaxe em app.js:\n{r.stderr[:600]}")

    def test_index_html_balanceado_e_sem_ids_duplicados(self):
        p = _Balanceamento()
        p.feed(_ler(INDEX_HTML))
        self.assertEqual(p.erros, [], f"Tags desbalanceadas: {p.erros[:3]}")
        self.assertEqual(p.pilha, [], f"Tags nao fechadas: {p.pilha[:3]}")
        duplicados = sorted({i for i in p.ids if p.ids.count(i) > 1})
        self.assertEqual(duplicados, [], f"IDs duplicados: {duplicados}")

    def test_todo_id_usado_pelo_js_existe_no_html(self):
        """configurarEventos() usa getElementById(...).addEventListener sem checagem de null."""
        js = _ler(APP_JS)
        html = _ler(INDEX_HTML)
        usados = set(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", js))
        no_html = set(re.findall(r'id="([^"]+)"', html))
        dinamicos = set(re.findall(r"""id=\\?["']([A-Za-z0-9_-]+)\\?["']""", js))
        dinamicos |= set(re.findall(r"""\.id\s*=\s*['"]([A-Za-z0-9_-]+)['"]""", js))
        ausentes = sorted(usados - no_html - dinamicos)
        self.assertEqual(ausentes, [], f"IDs usados no app.js e ausentes no index.html: {ausentes}")

    def test_elementos_do_login_existem(self):
        html = _ler(INDEX_HTML)
        for i in ("tela-login", "tela-sistema", "form-login", "login-identificador",
                  "login-senha", "login-alerta", "login-alerta-mensagem", "btn-logout"):
            self.assertIn(f'id="{i}"', html, f"Elemento de login ausente: {i}")


if __name__ == "__main__":
    unittest.main()
