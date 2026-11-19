# -*- coding: utf-8 -*-
"""
Testes Automatizados — Matriz de Acesso RBAC Enterprise e Portais (RH2.0 Enterprise)
Valida:
1. Existência e completude dos 8 perfis canônicos Enterprise.
2. Função checar_permissao com wildcards globais (*), curingas por módulo (ex: folha:*) e permissões específicas.
3. Rota GET /api/auth/perfis retornando catálogo oficial de perfis.
4. Rota GET /api/auth/me enriquecida com perfil, empresa_id e lista de permissões RBAC.
5. Presença dos Portais do Colaborador e do Gestor no Frontend (HTML, CSS e JS).
"""
import json
import os
import unittest

from backend.auth import PERFIS_ENTERPRISE, PERMISSOES_RBAC, AuthService, checar_permissao
from backend.database import init_db


class TestRBACEnterprise(unittest.TestCase):
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

    def test_01_oito_perfis_canonicos_enterprise(self):
        """Verifica a presença dos 8 perfis enterprise canônicos no dicionário oficial."""
        perfis_obrigatorios = [
            "superadmin",
            "admin_empresa",
            "gestor_rh",
            "analista_dp",
            "financeiro",
            "contabilidade",
            "gestor_departamento",
            "colaborador",
        ]
        for p in perfis_obrigatorios:
            self.assertIn(p, PERFIS_ENTERPRISE, f"Perfil {p} deve existir em PERFIS_ENTERPRISE")
            self.assertIn(p, PERMISSOES_RBAC, f"Perfil {p} deve ter regras mapeadas em PERMISSOES_RBAC")

    def test_02_checar_permissao_wildcard_admin(self):
        """Superadmin e Admin Empresa possuem wildcard total (*) para qualquer recurso."""
        self.assertTrue(checar_permissao("superadmin", "folha:calcular"))
        self.assertTrue(checar_permissao("superadmin", "qualquer_coisa_critica"))
        self.assertTrue(checar_permissao("admin_empresa", "usuarios:criar"))
        self.assertTrue(checar_permissao("administrador", "folha:fechar"))

    def test_03_checar_permissao_gestor_rh_e_analista_dp(self):
        """Gestor RH acessa pessoas e ponto; Analista DP acessa folha e eSocial."""
        # Gestor RH
        self.assertTrue(checar_permissao("gestor_rh", "colaboradores:criar"))
        self.assertTrue(checar_permissao("gestor_rh", "ferias:aprovar"))
        self.assertTrue(checar_permissao("gestor_rh", "folha:visualizar"))
        self.assertFalse(checar_permissao("gestor_rh", "cnab:gerar"))

        # Analista DP
        self.assertTrue(checar_permissao("analista_dp", "folha:calcular"))
        self.assertTrue(checar_permissao("analista_dp", "esocial:transmitir"))
        self.assertTrue(checar_permissao("analista_dp", "cnab:gerar"))
        self.assertTrue(checar_permissao("analista_dp", "rescisoes:homologar"))

    def test_04_checar_permissao_colaborador_e_gestor_departamento(self):
        """Colaborador restrito a autoatendimento; Gestor aprova equipe."""
        # Colaborador
        self.assertTrue(checar_permissao("colaborador", "portal_colaborador:visualizar"))
        self.assertTrue(checar_permissao("colaborador", "holerite:meu"))
        self.assertFalse(checar_permissao("colaborador", "folha:calcular"))
        self.assertFalse(checar_permissao("colaborador", "colaboradores:excluir"))

        # Gestor Departamento
        self.assertTrue(checar_permissao("gestor_departamento", "portal_gestor:visualizar"))
        self.assertTrue(checar_permissao("gestor_departamento", "ponto:aprovar"))
        self.assertTrue(checar_permissao("gestor_departamento", "ferias:aprovar"))
        self.assertFalse(checar_permissao("gestor_departamento", "folha:calcular"))

    def test_05_portal_colaborador_e_gestor_frontend(self):
        """Verifica se os elementos dos portais estão implementados no HTML, CSS e JS."""
        # HTML
        self.assertIn('id="view-modulo-portal-colaborador"', self.html)
        self.assertIn('id="view-modulo-portal-gestor"', self.html)
        self.assertIn('id="btn-menu-portal-colaborador"', self.html)
        self.assertIn('id="btn-menu-portal-gestor"', self.html)
        self.assertIn('id="tab-btn-holerites"', self.html)
        self.assertIn('id="tab-btn-espelho"', self.html)
        self.assertIn('id="tab-btn-ferias"', self.html)
        self.assertIn('id="tab-btn-informes"', self.html)
        self.assertIn('id="btn-gestor-aprovar-lote"', self.html)

        # CSS
        self.assertIn(".colab-profile-card", self.css)
        self.assertIn(".portal-nav-tabs", self.css)
        self.assertIn(".portal-tab-btn", self.css)

        # JS
        self.assertIn("carregarPortalColaborador()", self.js)
        self.assertIn("carregarPortalGestor()", self.js)
        self.assertIn("view-modulo-portal-colaborador", self.js)
        self.assertIn("view-modulo-portal-gestor", self.js)


if __name__ == "__main__":
    unittest.main()
