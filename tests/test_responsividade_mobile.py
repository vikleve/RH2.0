"""
Teste Automatizado de Responsividade Mobile e Alta Fidelidade Visual
Valida regras CSS responsivas para smartphones (< 768px, < 440px),
tamanhos de touch targets, prevenção de zoom no iOS e integridade de modais/tabelas.
"""
import os
import re
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSS_PATH = os.path.join(BASE_DIR, "frontend", "styles.css")
HTML_PATH = os.path.join(BASE_DIR, "frontend", "index.html")


class TestResponsividadeMobile(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(CSS_PATH, "r", encoding="utf-8") as f:
            cls.css = f.read()
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            cls.html = f.read()

    def test_meta_viewport_presente_no_html(self):
        """O HTML deve conter a tag meta viewport correta para renderização mobile."""
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1.0">', self.html)

    def test_media_queries_mobile_presentes_no_css(self):
        """styles.css deve conter media queries para <= 768px e <= 440px."""
        self.assertIn("@media (max-width: 768px)", self.css)
        self.assertIn("@media (max-width: 440px)", self.css)

    def test_prevencao_zoom_ios_font_size_16px(self):
        """Inputs em telas mobile devem ter font-size: 16px para evitar auto-zoom em Safari/iOS."""
        match = re.search(r"@media \(max-width:\s*768px\)\s*\{([^}]+font-size:\s*16px[^}]+)\}", self.css, re.DOTALL)
        self.assertIsNotNone(match, "Regra de font-size: 16px para inputs em 768px não encontrada.")

    def test_nav_modules_scroll_touch_mobile(self):
        """Barra de navegação de módulos deve permitir rolagem horizontal suave no mobile."""
        self.assertIn("-webkit-overflow-scrolling: touch", self.css)
        self.assertIn("overflow-x: auto", self.css)

    def test_touch_targets_minimos(self):
        """Botões e abas no mobile devem garantir min-height de pelo menos 40px/44px."""
        self.assertIn("min-height: 44px", self.css)

    def test_tabela_responsiva_container(self):
        """Tabelas de colaboradores e folha devem estar contidas em containers com scroll horizontal."""
        self.assertIn(".table-responsive", self.css)
        self.assertIn('class="table-responsive"', self.html)

    def test_holerite_responsivo_mobile(self):
        """Demonstrativo de pagamento (holerite) deve ter regras específicas para telas móveis."""
        self.assertIn(".holerite-header", self.css)
        self.assertIn(".holerite-totais-box", self.css)
        self.assertIn(".holerite-colaborador-box", self.css)

    def test_botoes_lote_e_parametros_presentes_no_html(self):
        """Botoes de lote e parâmetros devem estar presentes no HTML com IDs corretos."""
        self.assertIn('id="btn-gerar-lote-folha"', self.html)
        self.assertIn('id="btn-fechar-lote-competencia"', self.html)
        self.assertIn('id="btn-parametros-folha"', self.html)
        self.assertIn('id="modal-parametros-folha"', self.html)
        self.assertIn('id="modal-lote-confirm"', self.html)


if __name__ == "__main__":
    unittest.main()
