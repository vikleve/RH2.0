# -*- coding: utf-8 -*-
"""
Testes Automatizados — RH 2.0 Versão Desktop & Mobile (Responsividade e UI Corporativa)
Valida:
1. Identidade visual corporativa (azul-escuro institucional, azul de destaque, fundo claro).
2. Breakpoints obrigatórios: 360px, 390px, 430px, 768px, 1024px, 1366px e 1920px.
3. Componentes Desktop: menu lateral fixo, cabeçalho com usuário e notificações, cards financeiros e gráficos do dashboard.
4. Componentes Mobile: menu hambúrguer retrátil, drawer com backdrop, barra de navegação inferior (Bottom Nav), botões >= 44px e prevenção de rolagem horizontal.
5. Integração ponta a ponta dos endpoints do Dashboard BI (cards financeiros e gráficos setoriais), Checklist e Simulação de Rescisão.
"""
import os
import unittest

from backend.database import init_db
from backend.plataforma_service import PlataformaService
from backend.service import ColaboradorService


class TestResponsividadeDesktopMobile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        cls.html_path = os.path.join(cls.raiz, "frontend", "index.html")
        cls.css_path = os.path.join(cls.raiz, "frontend", "styles.css")
        cls.js_path = os.path.join(cls.raiz, "frontend", "app.js")

        with open(cls.html_path, "r", encoding="utf-8") as f:
            cls.html = f.read()
        with open(cls.css_path, "r", encoding="utf-8") as f:
            cls.css = f.read()
        with open(cls.js_path, "r", encoding="utf-8") as f:
            cls.js = f.read()

    def test_01_breakpoints_obrigatorios_360_a_1920(self):
        """Verifica se todos os 7 tamanhos de tela exigidos possuem regras @media no CSS."""
        breakpoints = [
            "360px",   # celular pequeno
            "390px",   # celular moderno
            "430px",   # celular grande
            "768px",   # tablet
            "1024px",  # notebook pequeno
            "1366px",  # computador
            "1920px",  # monitor grande
        ]
        for bp in breakpoints:
            self.assertIn(bp, self.css, f"Breakpoint obrigatório {bp} deve estar implementado em styles.css")
        self.assertIn("overflow-x: hidden", self.css, "Prevenção de rolagem horizontal indesejada deve estar ativa")

    def test_02_identidade_visual_corporativa_azul(self):
        """Verifica paleta institucional azul-escuro, azul de destaque e fundo claro."""
        self.assertIn("--inst-navy: #0f172a", self.css)
        self.assertIn("--inst-dark-blue: #1e3a8a", self.css)
        self.assertIn("--primary: #1d4ed8", self.css)
        self.assertIn("--bg-app: #f8fafc", self.css)
        self.assertIn("RH 2.0", self.html)

    def test_03_componentes_versao_desktop(self):
        """Verifica menu lateral fixo, cabeçalho com notificações, cards financeiros e gráficos organizados."""
        # Cabeçalho e notificações
        self.assertIn('id="header-user-nome"', self.html)
        self.assertIn('id="btn-header-notificacoes"', self.html)
        self.assertIn('id="header-notif-badge"', self.html)
        self.assertIn('id="header-notif-dropdown"', self.html)

        # Menu lateral e módulos
        self.assertIn('id="platform-sidebar"', self.html)
        self.assertIn('position: sticky', self.css)

        # Cards financeiros no dashboard
        self.assertIn('id="dashboard-financial-cards"', self.html)
        self.assertIn('id="kpi-fin-proventos"', self.html)
        self.assertIn('id="kpi-fin-liquido"', self.html)
        self.assertIn('id="kpi-fin-fgts"', self.html)
        self.assertIn('id="kpi-fin-descontos"', self.html)

        # Gráficos organizados no dashboard
        self.assertIn('id="dashboard-charts-grid"', self.html)
        self.assertIn('id="chart-composicao-folha"', self.html)
        self.assertIn('id="chart-distribuicao-setores"', self.html)

    def test_04_componentes_versao_mobile(self):
        """Verifica menu hambúrguer, drawer lateral, barra de navegação inferior e controles mobile."""
        self.assertIn('id="btn-mobile-menu"', self.html)
        self.assertIn('id="btn-close-sidebar"', self.html)
        self.assertIn('id="sidebar-backdrop"', self.html)
        self.assertIn('id="mobile-bottom-nav"', self.html)
        self.assertIn('id="btn-bnav-dashboard"', self.html)
        self.assertIn('id="btn-bnav-colaboradores"', self.html)
        self.assertIn('id="btn-bnav-ponto"', self.html)
        self.assertIn('id="btn-bnav-folha"', self.html)
        self.assertIn('id="btn-bnav-menu"', self.html)

        # Funções JS de controle do menu mobile e notificações
        self.assertIn("abrirDrawerMobile()", self.js)
        self.assertIn("fecharDrawerMobile()", self.js)
        self.assertIn("configurarNotificacoesHeader()", self.js)
        self.assertIn("min-height: 44px", self.css)
        self.assertIn("font-size: 16px", self.css)

    def test_05_integracao_dados_reais_dashboard_e_simulacao(self):
        """Verifica se o backend fornece dados reais para os cards financeiros, gráficos setoriais e simulação."""
        db_file = "test_resp_ui.db"
        if os.path.exists(db_file):
            os.remove(db_file)
        try:
            init_db(db_file)
            colab_srv = ColaboradorService(db_path=db_file)
            plat_srv = PlataformaService(db_path=db_file)

            colab = colab_srv.cadastrar(
                {
                    "matricula": "FV-9010",
                    "nome_completo": " Mariana Costa",
                    "cpf": "52998224725",
                    "cargo": "Analista Financeiro",
                    "setor": "Financeiro",
                    "salario_base": 4800.00,
                    "data_admissao": "2025-02-01",
                    "data_nascimento": "1993-06-15",
                    "email": "mariana.costa@forcaverde.com.br",
                    "situacao": "ativo",
                },
                usuario="Teste UI",
            )

            bi = plat_srv.obter_indicadores_bi()
            self.assertGreaterEqual(bi["total_colaboradores_ativos"], 1)
            self.assertIn("folha", bi)
            self.assertGreater(bi["folha"]["prov"], 0)
            self.assertIn("distribuicao_setores", bi)
            self.assertTrue(any(s["setor"] == "Financeiro" for s in bi["distribuicao_setores"]))

            # Simulação de rescisão sem inativar o colaborador
            sim = plat_srv.registrar_rescisao(
                colaborador_id=colab["id"],
                tipo_rescisao="SEM_JUSTA_CAUSA",
                data_afastamento="2026-04-30",
                simular=True,
            )
            self.assertTrue(sim["sucesso"])
            self.assertTrue(sim["simulado"])
            self.assertIn("dados", sim)
            self.assertGreater(sim["dados"]["total_rescisao_liquido"], 0)

            # Colaborador continua ativo após simulação
            colab_atual = colab_srv.obter_por_id(colab["id"])
            self.assertEqual(colab_atual["situacao"], "ativo")
        finally:
            if os.path.exists(db_file):
                try:
                    os.remove(db_file)
                except OSError:
                    pass


if __name__ == "__main__":
    unittest.main()
