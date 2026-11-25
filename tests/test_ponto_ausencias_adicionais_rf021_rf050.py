"""
Suíte Completa de Testes Automatizados e Integração — RF021 a RF050
Módulos 03, 04 e 05: Jornada e Ponto Eletrônico, Faltas/Ausências, Horas Extras e Adicionais.
Utiliza banco SQLite temporário isolado (padrão template DB em setUpClass) e dados exclusivamente fictícios.
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

from backend.folha_calculos import processar_calculo_folha
from backend.folha_service import FolhaService, FolhaValidacaoException
from backend.plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaValidacaoException,
)
from backend.plataforma_service import PlataformaService
from backend.service import ColaboradorService


class TestPontoAusenciasAdicionaisRF021RF050(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls._template_db = tempfile.mkstemp(prefix="rh20_rf021_050_tpl_", suffix=".db")
        os.close(fd)
        cls._colab_srv = ColaboradorService(db_path=cls._template_db)
        cls._plat_srv = PlataformaService(db_path=cls._template_db)
        cls._folha_srv = FolhaService(db_path=cls._template_db)

        cls._colab1 = cls._colab_srv.cadastrar({
            "matricula": "PT-1001",
            "nome_completo": "Marcos Vinícius Ponto Teste",
            "cpf": "52998224725",
            "data_nascimento": "1991-04-12",
            "email": "marcos.ponto@rh20.local",
            "cargo": "Operador de Caldeira",
            "setor": "Caldeira",
            "tipo_contrato": "CLT",
            "carga_horaria_mensal": 220.0,
            "data_admissao": "2024-01-10",
            "salario_base": 2200.00,
        }, usuario="QA Ponto")

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls._template_db)
        except OSError:
            pass

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix="rh20_rf021_050_run_", suffix=".db")
        os.close(fd)
        shutil.copyfile(self._template_db, self.db_path)
        self.colab_srv = ColaboradorService(db_path=self.db_path)
        self.plat_svc = PlataformaService(db_path=self.db_path)
        self.ponto_svc = self.plat_svc.ponto_service
        self.folha_svc = FolhaService(db_path=self.db_path)
        self.cid = self._colab1["id"]

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_rf021_rf022_importacao_arquivo_e_api_idempotente(self):
        """RF021/RF022: Importação CSV/TXT com SHA-256, bloqueio duplicado e importação via API com idempotency_key."""
        # Extensão inválida bloqueada
        with self.assertRaises(PlataformaValidacaoException):
            self.ponto_svc.importar_arquivo_ponto("batidas.pdf", "PT-1001;2026-10-01;08:00")

        csv_txt = (
            "matricula;data;hora;tipo_marcacao;coletor\n"
            "PT-1001;2026-10-01;08:00;ENTRADA_1;REP-01\n"
            "PT-1001;2026-10-01;12:00;SAIDA_1;REP-01\n"
            "PT-1001;2026-10-01;13:00;ENTRADA_2;REP-01\n"
            "PT-1001;2026-10-01;17:48;SAIDA_2;REP-01\n"
            "INEXISTENTE;2026-10-01;08:00;ENTRADA_1;REP-01\n"
        )
        res_arq = self.ponto_svc.importar_arquivo_ponto("marcacoes_out.csv", csv_txt, usuario="Operador Ponto")
        self.assertTrue(res_arq["sucesso"])
        self.assertEqual(res_arq["total_importados"], 4)
        self.assertEqual(res_arq["total_erros"], 1)

        # Mesmo arquivo reenviado deve ser bloqueado por SHA-256
        with self.assertRaises(PlataformaValidacaoException):
            self.ponto_svc.importar_arquivo_ponto("marcacoes_out.csv", csv_txt)

        # Importação via API com idempotency_key
        lote_api = [
            {"colaborador_id": self.cid, "data": "2026-10-02", "hora": "08:03", "tipo_marcacao": "ENTRADA_1"},
            {"colaborador_id": self.cid, "data": "2026-10-02", "hora": "17:46", "tipo_marcacao": "SAIDA_2"},
        ]
        r_api1 = self.ponto_svc.importar_marcacoes_api(lote_api, idempotency_key="KEY-API-20261002", coletor_id="APP-MOBILE")
        self.assertFalse(r_api1["idempotente_reaproveitado"])
        self.assertEqual(r_api1["total_importados"], 2)

        r_api2 = self.ponto_svc.importar_marcacoes_api(lote_api, idempotency_key="KEY-API-20261002", coletor_id="APP-MOBILE")
        self.assertTrue(r_api2["idempotente_reaproveitado"])

    def test_rf023_tolerancia_intra_interjornada_limite_2h_e_rf050(self):
        """RF022/RF023/RF024/RF025/RF050: Tolerância 5m/10m, batida ímpar, intrajornada, interjornada <11h e >2h extras."""
        # Dia 05: dentro da tolerância (8h48min esperada -> trabalhou 8h53m = +5m -> saldo 0)
        for hr in ("08:04", "12:00", "13:00", "17:57"):
            self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-10-05", hr, tipo_registro="relogio_afd")

        # Dia 06: jornada >6h sem intervalo suficiente (08:00-12:00, 12:20-18:00 = 9h40 trab, 20m intervalo) + >2h extras + saída tardia às 22:00
        for hr in ("08:00", "12:00", "12:20", "22:00"):
            self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-10-06", hr, tipo_registro="relogio_afd")

        # Dia 07: entra às 06:00 (apenas 8h de descanso interjornada vs 22:00 do dia 06!) e batida ímpar
        self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-10-07", "06:00", tipo_registro="relogio_afd")

        val = self.ponto_svc.validar_marcacoes_periodo(self.cid, "2026-10")
        self.assertEqual(val["total_inconsistencias"], 2)

        esp = self.ponto_svc.obter_espelho_ponto(self.cid, "2026-10")
        d05 = next(d for d in esp["grade_dias"] if d["data"] == "2026-10-05")
        self.assertEqual(d05["he_50"], 0.0)  # Tolerância CLT art. 58 §1º absorveu +5 min
        self.assertEqual(d05["atraso_min"], 0)

        d06 = next(d for d in esp["grade_dias"] if d["data"] == "2026-10-06")
        self.assertTrue(d06["intrajornada_violada"])
        self.assertTrue(d06["limite_2h_extras_excedido"])

        d07 = next(d for d in esp["grade_dias"] if d["data"] == "2026-10-07")
        self.assertTrue(d07["interjornada_violada"])

    def test_rf025_rf026_rf028_rf029_ajustes_banco_horas_fechamento_e_reabertura(self):
        """RF025-RF030: Ajuste com segregação RN-080, banco de horas, fechamento com lock e reabertura justificada."""
        self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-10-08", "08:00")
        sol = self.ponto_svc.solicitar_ajuste_ponto(
            self.cid, "2026-10-08", "17:48", "SAIDA_2", "Esquecimento no coletor", solicitante="Marcos Colaborador"
        )
        aid = sol["ajuste_id"]

        # Segregação RN-080: bloqueia autoaprovação e reprovação sem motivo
        with self.assertRaises(PlataformaAcessoNegadoException):
            self.ponto_svc.aprovar_ajuste_ponto(aid, aprovador="Marcos Colaborador", aprovar=True)
        with self.assertRaises(PlataformaValidacaoException):
            self.ponto_svc.aprovar_ajuste_ponto(aid, aprovador="Gestor Ponto", aprovar=False, motivo_reprovacao="")

        ok_ap = self.ponto_svc.aprovar_ajuste_ponto(aid, aprovador="Gestor Ponto", aprovar=True)
        self.assertEqual(ok_ap["status"], "aprovado")

        # Reaprovar ajuste já aprovado deve falhar
        with self.assertRaises(PlataformaValidacaoException):
            self.ponto_svc.aprovar_ajuste_ponto(aid, aprovador="Gestor Ponto", aprovar=True)

        # Banco de horas
        bh1 = self.ponto_svc.movimentar_banco_horas(self.cid, "2026-10-08", "credito", 120, "Saldo positivo")
        self.assertEqual(bh1["saldo_atual_min"], 120)
        bh2 = self.ponto_svc.movimentar_banco_horas(self.cid, "2026-10-09", "compensacao", 45, "Saída compensada")
        self.assertEqual(bh2["saldo_atual_min"], 75)

        # Fechamento com lock (RF028)
        fech = self.ponto_svc.fechar_ponto_periodo("2026-10", usuario="Gestor DP")
        self.assertEqual(fech["situacao"], "fechado")

        # Após fechamento, nova marcação ou ajuste na competência é bloqueado
        with self.assertRaises(PlataformaValidacaoException):
            self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-10-12", "08:00")
        with self.assertRaises(PlataformaValidacaoException):
            self.ponto_svc.solicitar_ajuste_ponto(self.cid, "2026-10-12", "17:00", "SAIDA_2", "Teste lock", "Marcos")

        # Reabertura exige justificativa (RF029)
        with self.assertRaises(PlataformaValidacaoException):
            self.ponto_svc.reabrir_ponto_periodo("2026-10", "", usuario="Admin DP")
        reab = self.ponto_svc.reabrir_ponto_periodo("2026-10", "Inclusão de atestado tardio", usuario="Admin DP")
        self.assertEqual(reab["situacao"], "reaberto")

        # Desbloqueado após reabertura e histórico preservado (RF030)
        ok_after = self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-10-12", "08:00")
        self.assertTrue(ok_after["sucesso"])
        esp = self.ponto_svc.obter_espelho_ponto(self.cid, "2026-10")
        self.assertGreaterEqual(len(esp["historico_jornada"]), 3)

    def test_rf031_a_rf040_ocorrencias_dsr_justificativas_abonos_clt473_e_relatorios(self):
        """RF031-RF040: Faltas, abonos CLT art. 473, atrasos, saída antecipada, DSR, justificativas e absenteísmo."""
        # Limite art. 473 CLT (casamento máx 3d -> 4d deve bloquear)
        with self.assertRaises(PlataformaValidacaoException):
            self.ponto_svc.registrar_ocorrencia(
                self.cid, "2026-10-01", "2026-10-04", "falta_abonada",
                "Licença gala", artigo_clt="casamento", usuario="RH"
            )

        # Solicitar justificativa de abono válido (casamento 3d) e aprovar por outro usuário
        just = self.ponto_svc.registrar_justificativa(
            self.cid, "2026-10-01", "falta_abonada", "Certidão de casamento", solicitante="Marcos", dias_abono=3, artigo_clt="casamento"
        )
        with self.assertRaises(PlataformaAcessoNegadoException):
            self.ponto_svc.decidir_justificativa(just["justificativa_id"], aprovador="Marcos", aprovar=True)
        dec = self.ponto_svc.decidir_justificativa(just["justificativa_id"], aprovador="Gestor RH", aprovar=True)
        self.assertEqual(dec["tipo_ocorrencia_gerada"], "falta_abonada")

        # 3 faltas injustificadas em 3 semanas distintas geram alerta setorial e perda de DSR
        for dt_f in ("2026-10-05", "2026-10-14", "2026-10-21"):
            self.ponto_svc.registrar_ocorrencia(self.cid, dt_f, dt_f, "falta_injustificada", "Ausência sem justificativa")

        esp = self.ponto_svc.obter_espelho_ponto(self.cid, "2026-10")
        self.assertEqual(esp["totais"]["faltas_injustificadas_dias"], 3)
        self.assertEqual(esp["totais"]["dsr_perdidos_dias"], 3)

        rel = self.ponto_svc.relatorio_ausencias(competencia="2026-10", setor="Caldeira")
        self.assertGreaterEqual(rel["total_ocorrencias"], 4)
        self.assertEqual(len(rel["alertas_absenteismo_elevado"]), 1)
        self.assertIn("Caldeira", rel["csv"])

    def test_rf041_a_rf050_noturno_feriado_sobreaviso_acumulo_nr_e_medias_variaveis(self):
        """RF041-RF050: Feriado 100%, noturno com hora reduzida e prorrogação Súmula 60, sobreaviso 1/3, Súmula 132, CLT 193 §2º e médias."""
        # Jornada noturna atravessando as 05h em dia comum (2026-11-19 22:00 até 2026-11-20 06:00? Testar 22:00-06:00 em 2026-11-05)
        self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-11-05", "22:00")
        self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-11-05", "06:00")

        # Trabalho em feriado nacional 2026-11-20 (Consciência Negra): 4h de 08:00 às 12:00 -> 100%
        self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-11-20", "08:00")
        self.ponto_svc.registrar_marcacao_ponto(self.cid, "2026-11-20", "12:00")

        # Sobreaviso de 6 horas (360 min)
        self.ponto_svc.registrar_ocorrencia(self.cid, "2026-11-21", "2026-11-21", "sobreaviso", "Escala plantão", minutos_ausencia=360)

        esp = self.ponto_svc.obter_espelho_ponto(self.cid, "2026-11")
        t = esp["totais"]
        self.assertEqual(t["noturno_horas"], 7.0)  # 22h-05h
        self.assertAlmostEqual(t["noturno_horas_fictas"], 8.0, places=2)  # 7h * 60/52.5 = 8.0h
        self.assertEqual(t["prorrogacao_noturna_horas"], 1.0)  # 05h-06h Súmula 60 TST
        self.assertEqual(t["feriado_100_horas"], 4.0)
        self.assertEqual(t["sobreaviso_horas"], 6.0)
        # 6h * (10,00 / 3) = R$ 20,00
        self.assertAlmostEqual(t["valor_sobreaviso"], 20.00, places=2)
        self.assertTrue(len(esp["memoria_calculo"]["linhas"]) >= 6)

        # Integração automática dos eventos de ponto na FolhaService + bloqueio CLT art. 193 §2º (0030 + 0031)
        evs_ponto = self.ponto_svc.gerar_eventos_folha_do_ponto(self.cid, "2026-11")
        with self.assertRaises(FolhaValidacaoException):
            self.folha_svc.criar_ou_atualizar_folha(
                colaborador_id=self.cid,
                competencia="2026-11",
                periodo_inicio="2026-11-01",
                periodo_fim="2026-11-30",
                eventos=[{"codigo": "0030", "referencia": 20}, {"codigo": "0031"}],
                usuario="Analista DP",
            )

        # Súmula 132 TST: Periculosidade (30% s/ R$ 2.200 = 660 -> base 2.860 / 220 = R$ 13,00/h -> 10h HE 50% = R$ 195,00)
        res_sum132 = processar_calculo_folha(
            salario_base=2200.00,
            eventos_informados=[{"codigo": "0031"}, {"codigo": "0010", "referencia": 10}],
        )
        it_he = next(it for it in res_sum132["itens"] if it["codigo_catalogo"] == "0010")
        self.assertAlmostEqual(it_he["valor_total"], 195.00, places=2)

        # Salvar folha real de 2026-11 com eventos do ponto e validar apuração de médias variáveis (RF048/RF049)
        folha_11 = self.folha_svc.criar_ou_atualizar_folha(
            colaborador_id=self.cid,
            competencia="2026-11",
            periodo_inicio="2026-11-01",
            periodo_fim="2026-11-30",
            eventos=evs_ponto,
            usuario="Analista DP",
        )
        cods_11 = {it.get("codigo_evento") or it.get("codigo_catalogo") for it in folha_11["itens"]}
        self.assertIn("0013", cods_11)
        self.assertIn("0020", cods_11)
        self.assertIn("0022", cods_11)
        self.assertIn("0025", cods_11)

        medias = self.ponto_svc.calcular_medias_variaveis_colaborador(self.cid, ano=2026)
        self.assertGreater(medias["media_mensal"], 0.0)
        self.assertIn("Média de variáveis", medias["memoria_calculo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
