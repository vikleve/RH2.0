"""
Suíte Completa de Testes Automatizados e Integração — RF081 a RF105
Módulos 09 e 10: Folha de Pagamento, 13º Salário, Provisões, Rateio Contábil, Integração Financeira,
eSocial Periódico (S-1200, S-1210, S-1299) e CNAB 240 Multibanco / PIX / Retorno.
Utiliza banco SQLite temporário isolado (template DB em setUpClass) e dados exclusivamente fictícios.
"""
import os
import shutil
import sys
import tempfile
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

os.environ["TESTING"] = "1"
os.environ["ADMIN_INITIAL_PASSWORD"] = os.environ.get("ADMIN_INITIAL_PASSWORD", "Sintetico#AdminTest2026!")
os.environ["GUEST_INITIAL_PASSWORD"] = os.environ.get("GUEST_INITIAL_PASSWORD", "Sintetico#GuestTest2026!")

from backend.database import _usar_postgres, fetchall_dict, get_connection
from backend.esocial_eventos_trabalhistas import validar_xml_esocial_trabalhista
from backend.folha_service import FolhaService, FolhaValidacaoException
from backend.plataforma_service import PlataformaService
from backend.service import ColaboradorService


class TestFolhaDecimoTerceiroRF081RF105(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls._template_db = tempfile.mkstemp(prefix="rh20_rf081_105_tpl_", suffix=".db")
        os.close(fd)
        cls._colab_srv = ColaboradorService(db_path=cls._template_db)
        cls._plat_srv = PlataformaService(db_path=cls._template_db)
        cls._folha_srv = FolhaService(db_path=cls._template_db)

        cls._c1 = cls._colab_srv.cadastrar({
            "matricula": "FOL-1001",
            "nome_completo": "Beatriz Martins Folha",
            "cpf": "52998224725",
            "data_nascimento": "1989-07-22",
            "email": "beatriz.folha@rh20.local",
            "cargo": "Engenheira de Processos",
            "setor": "Engenharia",
            "centro_custo": "CC-ENG-01",
            "tipo_contrato": "CLT",
            "carga_horaria_mensal": 220.0,
            "data_admissao": "2024-01-10",
            "salario_base": 5500.00,
        }, usuario="QA Folha")
        cls._c2 = cls._colab_srv.cadastrar({
            "matricula": "FOL-1002",
            "nome_completo": "Lucas Almeida Folha",
            "cpf": "11144477735",
            "data_nascimento": "1994-11-03",
            "email": "lucas.folha@rh20.local",
            "cargo": "Técnico de Campo",
            "setor": "Operações",
            "centro_custo": "CC-OPR-02",
            "tipo_contrato": "CLT",
            "carga_horaria_mensal": 220.0,
            "data_admissao": "2026-04-05",
            "salario_base": 3000.00,
        }, usuario="QA Folha")

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls._template_db)
        except OSError:
            pass

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="rh20_rf081_105_run_", suffix=".db")
        os.close(fd)
        shutil.copyfile(self._template_db, self.db_path)
        self.colab_srv = ColaboradorService(db_path=self.db_path)
        self.plat_svc = PlataformaService(db_path=self.db_path)
        self.ponto_svc = self.plat_svc.ponto_service
        self.folha_svc = FolhaService(db_path=self.db_path)
        self.cid1 = self._c1["id"]
        self.cid2 = self._c2["id"]

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_rf081_a_rf088_ponto_afastamento_adiantamento_0520_e_complementar_diferencial(self):
        """RF-081..RF-088: Ponto fechado no lote, redução por INSS/suspensão, recuperação 0520 e complementar diferencial."""
        # 1. Ponto em 2026-09 com HE 50% (2h no sábado 2026-09-05 = HE 100%? No regime 5x2 sábado tem meta 0 -> HE 50% / 100%)
        self.ponto_svc.registrar_marcacao_ponto(self.cid1, "2026-09-01", "08:00")
        self.ponto_svc.registrar_marcacao_ponto(self.cid1, "2026-09-01", "12:00")
        self.ponto_svc.registrar_marcacao_ponto(self.cid1, "2026-09-01", "13:00")
        self.ponto_svc.registrar_marcacao_ponto(self.cid1, "2026-09-01", "19:48")  # +2h extra
        self.ponto_svc.fechar_ponto_periodo("2026-09", usuario="Gestor Ponto")

        # 2. Adiantamento salarial em 2026-09 -> deve gerar desconto automático 0520 na mensal!
        adiant = self.folha_svc.criar_ou_atualizar_folha(
            colaborador_id=self.cid1,
            competencia="2026-09",
            periodo_inicio="2026-09-01",
            periodo_fim="2026-09-15",
            tipo_folha="adiantamento",
            usuario="Analista DP",
        )
        self.assertAlmostEqual(adiant["salario_liquido"], 2200.00, places=2)  # 40% de 5500

        # 3. Afastamento não remunerado de 10 dias para cid2 em setembro (2026-09-10 a 2026-09-19) -> reduz 10 dias trabalhados
        self.plat_svc.registrar_afastamento(
            self.cid2, "licenca_nao_remunerada", "2026-09-10", "2026-09-19", usuario="DP"
        )
        # Reativa manualmente apenas para simular retorno no mês mantendo registro do afastamento parcial,
        # ou calcula direto via criar_ou_atualizar_folha após retorno em 2026-09-20
        af_c2 = self.plat_svc.listar_afastamentos(self.cid2)[0]
        self.plat_svc.registrar_retorno_afastamento(af_c2["id"], "2026-09-19", usuario="DP")

        # 4. Lote mensal 2026-09 integra ponto fechado e recupera 0520 + proporcionaliza cid2 (20 dias)
        lote = self.folha_svc.processar_lote(
            competencia="2026-09", periodo_inicio="2026-09-01", periodo_fim="2026-09-30", usuario="DP Lote"
        )
        self.assertEqual(lote["processadas"], 2)
        f1 = next(f for f in lote["folhas"] if f["colaborador_id"] == self.cid1)
        f2 = next(f for f in lote["folhas"] if f["colaborador_id"] == self.cid2)

        cods1 = {it["codigo_evento"] for it in f1["itens"]}
        self.assertIn("0520", cods1)  # Recuperou adiantamento automaticamente!
        self.assertIn("0010", cods1)  # Integrou HE 50% do ponto fechado!
        self.assertEqual(f2["dias_trabalhados"], 20.0)
        self.assertAlmostEqual(f2["salario_base_proporcional"], 2000.00, places=2)

        # 5. Folha complementar diferencial (retroativo 0071 = R$ 500,00) calcula apenas a diferença!
        comp = self.folha_svc.criar_ou_atualizar_folha(
            colaborador_id=self.cid1,
            competencia="2026-09",
            periodo_inicio="2026-09-01",
            periodo_fim="2026-09-30",
            eventos=[{"codigo": "0071", "valor_informado": 500.00}],
            tipo_folha="complementar",
            usuario="Analista DP",
        )
        self.assertAlmostEqual(comp["total_proventos"], 500.00, places=2)
        self.assertLess(comp["salario_liquido"], 500.01)

    def test_rf089_a_rf093_decimo_terceiro_avos_variaveis_ferias_e_provisao(self):
        """RF-089..RF-093: 13º avos (>=15d), médias variáveis, dedução adiantamento férias, INSS/IRRF 2ª parcela e provisão 1/12."""
        # Lançar folha mensal com HE para compor média de variáveis em 2026
        self.folha_svc.criar_ou_atualizar_folha(
            colaborador_id=self.cid1,
            competencia="2026-08",
            periodo_inicio="2026-08-01",
            periodo_fim="2026-08-31",
            eventos=[{"codigo": "0010", "referencia": 12}],
            usuario="DP",
        )
        # Programar férias com adiantamento de 13º para Beatriz (cid1)
        self.plat_svc.programar_ferias(self.cid1, "2026-06-01", 15, adiantar_13=True, solicitante="DP Ferias")

        # cid2 foi admitido em 2026-04-05 (abril teve 26d >= 15d -> abr..dez = 9 avos)
        p1_c2 = self.folha_svc.calcular_decimo_terceiro_colaborador(self.cid2, 2026, parcela=1, usuario="DP")
        self.assertEqual(p1_c2["avos"], 9)
        # 3000 * 9/12 = 2250 -> 50% = 1125.00
        self.assertAlmostEqual(p1_c2["valor_liquido"], 1125.00, places=2)
        self.assertEqual(p1_c2["desconto_inss"], 0.0)

        # 2ª parcela de cid2 calcula INSS/IRRF sobre os 9/12 integrais e desconta 1ª parcela
        p2_c2 = self.folha_svc.calcular_decimo_terceiro_colaborador(self.cid2, 2026, parcela=2, usuario="DP")
        self.assertGreater(p2_c2["desconto_inss"], 0.0)
        self.assertAlmostEqual(p2_c2["desconto_primeira_parcela"], 1125.00, places=2)

        # 1ª parcela de cid1 (12 avos) deduz adiantamento de 13º recebido nas férias
        p1_c1 = self.folha_svc.calcular_decimo_terceiro_colaborador(self.cid1, 2026, parcela=1, usuario="DP")
        self.assertEqual(p1_c1["avos"], 12)
        self.assertGreater(p1_c1["media_variaveis"], 0.0)
        self.assertGreater(p1_c1["adiantamento_ferias_deduzido"], 2000.0)

        # Persistência listável + provisão 1/12 (RF-093)
        lista_13 = self.folha_svc.listar_decimo_terceiro(ano_base=2026)
        self.assertEqual(len(lista_13), 3)
        prov = self.folha_svc.calcular_provisao_decimo_terceiro("2026-10")
        self.assertEqual(prov["qtd_colaboradores"], 2)
        self.assertGreater(prov["total_provisao_13"], 700.0)

    def test_rf096_a_rf105_fechamento_lote_rateio_financeiro_esocial_e_cnab_retorno(self):
        """RF-096..RF-105: Conferência, fechamento lote, rateio CC, títulos financeiros, S-1200/1210/1299 e CNAB PIX/retorno."""
        # Cadastrar chave PIX bancária para cid1
        conn = get_connection(self.db_path)
        try:
            cur = conn.cursor()
            p = "%s" if _usar_postgres(self.db_path) else "?"
            cur.execute(
                f"""
                INSERT INTO colaborador_dados_bancarios (
                    colaborador_id, banco_codigo, banco_nome, agencia, conta, conta_digito,
                    chave_pix_tipo, chave_pix, titular_nome, titular_cpf, principal, ativo, criado_por, criado_em
                ) VALUES ({p}, '341', 'Itau', '1234', '56789', '0', 'cpf', '52998224725', 'Beatriz Martins', '52998224725', 1, 1, 'RH', '2026-01-01');
            """,
                (self.cid1,),
            )
            conn.commit()
        finally:
            conn.close()

        self.folha_svc.processar_lote("2026-10", "2026-10-01", "2026-10-31", usuario="DP")
        conf = self.folha_svc.conferencia_analitica_folha("2026-10")
        self.assertTrue(conf["apto_para_fechamento"])

        fech = self.folha_svc.fechar_competencia_lote("2026-10", usuario="Gestor DP")
        self.assertEqual(fech["folhas_fechadas_agora"], 2)
        self.assertIn("CC-ENG-01", fech["rateio"]["totais_por_centro_custo"])
        self.assertIn("CC-OPR-02", fech["rateio"]["totais_por_centro_custo"])
        self.assertGreaterEqual(fech["integracao_financeira"]["titulos_gerados"], 3)

        # Conferir persistência de rateio e títulos
        self.assertEqual(len(self.folha_svc.listar_rateio_centro_custo("2026-10")), 2)
        self.assertGreaterEqual(len(self.folha_svc.listar_integracao_financeira("2026-10")), 3)

        # eSocial periódico S-1200, S-1210 e S-1299 válidos
        esoc = self.folha_svc.gerar_eventos_esocial_folha("2026-10", usuario="DP eSocial")
        self.assertEqual(esoc["total_eventos"], 5)  # 2x S-1200 + 2x S-1210 + 1x S-1299
        self.assertTrue(all(ev["valido"] for ev in esoc["eventos"]))

        # CNAB 240 com todas as linhas == 240 chars e processamento de retorno
        cnab = self.plat_svc.gerar_arquivo_cnab240("2026-10", banco_codigo="341", usuario="Tesouraria")
        self.assertTrue(cnab["sucesso"])
        linhas_cnab = cnab["conteudo_cnab"].split("\r\n")
        self.assertTrue(all(len(ln) == 240 for ln in linhas_cnab))

        folhas_out = self.folha_svc.listar_folhas(competencia="2026-10")
        ret_txt = "\n".join([f"RET;{f['id']};00;LIQUIDADO_PIX" for f in folhas_out])
        ret = self.plat_svc.processar_retorno_cnab240(
            "RET_341_202610.RET", ret_txt, usuario="Tesouraria", arquivo_cnab_id=cnab["cnab_id"]
        )
        self.assertEqual(ret["total_liquidados"], 2)
        for f_out in self.folha_svc.listar_folhas(competencia="2026-10"):
            f_det = self.folha_svc.obter_folha_por_id(f_out["id"])
            self.assertIsNotNone(f_det["data_pagamento"])
            self.assertIn("CNAB 240 Liquidado", f_det.get("observacoes") or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
