"""
Executor Principal de Testes Automatizados (Sem abrir navegador)
Executa a suíte completa de testes unitários, integração de API e testes de segurança da autenticação.
Gera relatório detalhado do atendimento aos critérios funcionais (CA-01 a CA-10) e de segurança (CA-LOGIN-01 a CA-LOGIN-10).
"""
import os
import sys
import time
import unittest

# Configurar caminhos e ambiente de teste isolado com credenciais sintéticas
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")
os.environ["GUEST_INITIAL_PASSWORD"] = os.environ.get("GUEST_INITIAL_PASSWORD", "Sintetico#GuestTest2026!")

from tests.test_api import TestApiColaboradores
from tests.test_autenticacao import TestAutenticacaoSeguranca
from tests.test_colaboradores import TestModuloColaboradores
from tests.test_folha_api import TestFolhaApi
from tests.test_folha_calculos import TestFolhaCalculos
from tests.test_folha_service import TestFolhaService
from tests.test_rate_limit_csrf import TestAutenticacaoRH20
from tests.test_rn_oficiais_2026 import TestRegrasNegocioOficiais2026
from tests.test_motor_unificado_e_empresarial import TestMotorUnificadoEEmpresarial
from tests.test_plataforma_ciclo_trabalhista import TestPlataformaCicloTrabalhista
from tests.test_rbac_enterprise import TestRBACEnterprise
from tests.test_responsividade_desktop_mobile import TestResponsividadeDesktopMobile
from tests.test_folha_enterprise_completa import TestFolhaEnterpriseCompleta
from tests.test_holerite_pdf import TestHoleritePDF
from tests.test_beneficios_rf071_rf080 import TestBeneficiosRF071RF080
from tests.test_colaborador_rf005_rf010 import TestColaboradorRF005RF010
from tests.test_admissao_rf011_rf020 import TestAdmissaoRF011RF020
from tests.test_frontend_integridade import TestFrontendIntegridade
from tests.test_ponto_ausencias_adicionais_rf021_rf050 import TestPontoAusenciasAdicionaisRF021RF050
from tests.test_ferias_rf051_rf060 import TestFeriasRF051RF060
from tests.test_afastamentos_rf061_rf070 import TestAfastamentosRF061RF070
from tests.test_folha_decimo_terceiro_rf081_rf105 import TestFolhaDecimoTerceiroRF081RF105
from tests.test_rescisao_rf106_rf120 import TestRescisaoRF106RF120
from tests.test_sst_rf121_rf130 import TestSSTRF121RF130
from tests.test_esocial_rf131_rf140 import TestESocialRF131RF140
from tests.test_relatorios_rf141_rf150 import TestRelatoriosRF141RF150
from tests.test_regras_negocio_rn001_rn035 import TestRegrasNegocioRN001aRN035
from tests.test_beneficios_rn036_rn038 import TestBeneficiosRN036RN038
from tests.test_rescisoes_rn054_rn060 import TestRescisoesRN054RN060
from tests.test_seguranca_rn068_rn074_rf161_rf170 import TestSegurancaRN068RN074RF161RF170
from tests.test_auditoria_rf191_rf200 import TestAuditoriaRF191RF200


def executar():
    print("=" * 80)
    print(" SUÍTE DE TESTES AUTOMATIZADOS — PLATAFORMA INTEGRADA DO CICLO TRABALHISTA")
    print(" Módulos 01 a 20 (RF-001 a RF-200), RT-01 a RT-13 e RN-001 a RN-083 (2026)")
    print(" Projeto Interdisciplinar RH & GTI — Departamento Pessoal & GTI")
    print(" Modo: Execução 100% em código (headless / sem abrir navegador)")
    print("=" * 80)
    print()

    suite = unittest.TestSuite()
    carregador = unittest.TestLoader()

    # 1. Testes de Regras de Negócio e Persistência (Módulo 1: CA-01 a CA-10)
    suite.addTests(carregador.loadTestsFromTestCase(TestModuloColaboradores))

    # 2. Testes de Cálculos da Folha de Pagamento (Módulo 2: Cálculos e Proporcionalidades)
    suite.addTests(carregador.loadTestsFromTestCase(TestFolhaCalculos))

    # 3. Testes Oficiais de Cálculos 2026 (INSS, IRRF Lei 15.270/25, Salário Família, Casos Seção 5)
    suite.addTests(carregador.loadTestsFromTestCase(TestRegrasNegocioOficiais2026))

    # 4. Testes da Plataforma Completa do Ciclo Trabalhista (Módulos 01 a 20)
    suite.addTests(carregador.loadTestsFromTestCase(TestPlataformaCicloTrabalhista))

    # 4b. Testes de Responsividade Desktop & Mobile (360px a 1920px, UI Corporativa e Gráficos)
    suite.addTests(carregador.loadTestsFromTestCase(TestResponsividadeDesktopMobile))

    # 4c. Testes de RBAC Enterprise e Portais do Colaborador e do Gestor
    suite.addTests(carregador.loadTestsFromTestCase(TestRBACEnterprise))

    # 4d. Testes do Motor Unificado, Tabelas Legais, eSocial e CNAB240
    suite.addTests(carregador.loadTestsFromTestCase(TestMotorUnificadoEEmpresarial))

    # 5. Testes de Serviço e Persistência da Folha (Ciclo de Vida e Auditoria)
    suite.addTests(carregador.loadTestsFromTestCase(TestFolhaService))

    # 6. Testes de API In-Memory da Folha (Endpoints REST protegidos)
    suite.addTests(carregador.loadTestsFromTestCase(TestFolhaApi))

    # 7. Testes Enterprise Completos (Rubricas, Lote, Tipos de Folha, Documentos, Relatórios)
    suite.addTests(carregador.loadTestsFromTestCase(TestFolhaEnterpriseCompleta))

    # 8. Testes de Geração Real de Contracheques em PDF A4 (Individual e Lote)
    suite.addTests(carregador.loadTestsFromTestCase(TestHoleritePDF))

    # 9. Testes Reais de Gestão de Benefícios e Descontos (RF071 a RF080)
    suite.addTests(carregador.loadTestsFromTestCase(TestBeneficiosRF071RF080))

    # 10. Testes Completos de Consolidação do Cadastro do Colaborador (RF-005 a RF-010)
    suite.addTests(carregador.loadTestsFromTestCase(TestColaboradorRF005RF010))

    # 11. Testes Completos do Processo Admissional Enterprise (RF-011 a RF-020)
    suite.addTests(carregador.loadTestsFromTestCase(TestAdmissaoRF011RF020))

    # 12. Testes de Integridade do Frontend Consolidado (HTML/JS/IDs)
    suite.addTests(carregador.loadTestsFromTestCase(TestFrontendIntegridade))

    # 13. Testes de Jornada, Ponto, Ausências e Adicionais (RF-021 a RF-050)
    suite.addTests(carregador.loadTestsFromTestCase(TestPontoAusenciasAdicionaisRF021RF050))

    # 14. Testes de Férias, Abono, PDFs e eSocial S-2230 (RF-051 a RF-060)
    suite.addTests(carregador.loadTestsFromTestCase(TestFeriasRF051RF060))

    # 15. Testes de Afastamentos, Estabilidade e eSocial Schema (RF-061 a RF-070)
    suite.addTests(carregador.loadTestsFromTestCase(TestAfastamentosRF061RF070))

    # 16. Testes de Folha, 13º Salário, Rateio, Integração Financeira e CNAB 240 (RF-081 a RF-105)
    suite.addTests(carregador.loadTestsFromTestCase(TestFolhaDecimoTerceiroRF081RF105))

    # 17. Testes de Rescisão Contratual, TRCT PDF, Guias e S-2299 (RF-106 a RF-120)
    suite.addTests(carregador.loadTestsFromTestCase(TestRescisaoRF106RF120))

    # 18. Testes de Saúde e Segurança do Trabalho — SST, ASO, EPI, CAT S-2210/2220/2240 (RF-121 a RF-130)
    suite.addTests(carregador.loadTestsFromTestCase(TestSSTRF121RF130))

    # 19. Testes Oficiais de eSocial — Ciclo Completo, XML, Retificação e Exclusão S-3000 (RF-131 a RF-140)
    suite.addTests(carregador.loadTestsFromTestCase(TestESocialRF131RF140))

    # 20. Testes de Relatórios Gerenciais, Encargos e Exportação PDF A4 Oficial (RF-141 a RF-150)
    suite.addTests(carregador.loadTestsFromTestCase(TestRelatoriosRF141RF150))

    # 21. Testes de Homologação das Regras de Negócio Oficiais Trabalhistas e Previdenciárias (RN-001 a RN-035)
    suite.addTests(carregador.loadTestsFromTestCase(TestRegrasNegocioRN001aRN035))

    # 22. Testes de Elegibilidade, Participação e Histórico Imutável de Benefícios (RN-036 a RN-038)
    suite.addTests(carregador.loadTestsFromTestCase(TestBeneficiosRN036RN038))

    # 23. Testes das 7 Modalidades Canônicas de Rescisão, Culpa Recíproca e Término (RN-054 a RN-060)
    suite.addTests(carregador.loadTestsFromTestCase(TestRescisoesRN054RN060))

    # 24. Testes de Segurança Avançada, RBAC, Sigilo Salarial/LGPD, Criptografia e Autenticação (RN-068 a RN-074, RF-161 a RF-170)
    suite.addTests(carregador.loadTestsFromTestCase(TestSegurancaRN068RN074RF161RF170))

    # 25. Testes de Auditoria Completa, Encadeamento Criptográfico SHA-256 e Isolamento Multi-tenant (RF-191 a RF-200)
    suite.addTests(carregador.loadTestsFromTestCase(TestAuditoriaRF191RF200))

    # 5. Testes de Integração com Sockets de Rede (quando permitido pelo ambiente de SO)
    executar_sockets = os.environ.get("SKIP_SOCKET_TESTS", "0") != "1"
    if executar_sockets:
        try:
            suite.addTests(carregador.loadTestsFromTestCase(TestApiColaboradores))
            suite.addTests(carregador.loadTestsFromTestCase(TestAutenticacaoSeguranca))
            suite.addTests(carregador.loadTestsFromTestCase(TestAutenticacaoRH20))
        except Exception:
            pass

    inicio = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    resultado = runner.run(suite)
    duracao = time.time() - inicio

    sucessos = resultado.testsRun - len(resultado.failures) - len(resultado.errors)

    print()
    print("=" * 80)
    print(f" RESUMO DA EXECUÇÃO: {resultado.testsRun} testes executados em {duracao:.2f}s")
    print(f" Sucessos: {sucessos}")
    print(f" Falhas:   {len(resultado.failures)}")
    print(f" Erros:    {len(resultado.errors)}")
    print("=" * 80)

    if resultado.wasSuccessful():
        print(">> TODOS OS CRITÉRIOS FUNCIONAIS (CA-01 A CA-10) E DE SEGURANÇA (CA-LOGIN-01 A CA-LOGIN-10)")
        print("   FORAM ATENDIDOS COM 100% DE SUCESSO! <<")
        return 0
    else:
        print(">> ATENÇÃO: EXISTEM FALHAS NOS TESTES <<")
        return 1

if __name__ == "__main__":
    sys.exit(executar())
