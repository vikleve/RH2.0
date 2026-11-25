# HISTÓRICO DE CORREÇÕES E IMPLEMENTAÇÕES (RF021 A RF120)

Registro cronológico das alterações aplicadas diretamente na arquitetura ativa do projeto RH2.0 Enterprise.

---

## Fase 1 — Banco de Dados e Tabelas Legais Versionadas
- **`migrations/012_homologacao_modulos_rf021_rf120.sql` (Novo):** Criação e adaptação das tabelas `tabelas_legais_vigencia`, `tabelas_legais_historico`, `feriados_calendario`, `ponto_espelhos_fechados`, `decimo_terceiro`, `folha_rateio_centro_custo`, `folha_integracao_financeira`, `cnab_retornos`, `rescisoes_historico` e novas colunas em `afastamentos`, `ferias_programadas`, `folhas_pagamento` e `rescisoes`.
- **`backend/database.py`:** Execução automática da migration `012` em SQLite e PostgreSQL.
- **`backend/tabelas_legais_service.py` (Novo):** Gestão versionada de faixas INSS/IRRF, salário mínimo, salário-família, FGTS, feriados nacionais/estaduais/municipais e contagem real de dias úteis vs DSR.

## Fase 2 — Motor Centralizado de Cálculos 2026
- **`backend/folha_calculos_2026.py`, `backend/motor_calculo_unificado.py`, `backend/folha_service.py`:** Integração da leitura dinâmica de parâmetros vigentes por competência através do `TabelasLegaisService`.

## Fases 3 e 4 — Ponto, Ausências e Adicionais (`RF021`–`RF050`)
- **`backend/ponto_service.py`:** Correção da ordenação cronológica em jornadas noturnas (`_ordenar_marcacoes_dia` + `ORDER BY data ASC, id ASC`), regras de tolerância 5/10 min, intrajornada, interjornada 11h, limite de 2h extras diárias, escalas `5x2`/`6x1`/`12x36`, hora ficta noturna (52m30s), prorrogação Súmula 60 TST, banco de horas, fechamento/reabertura com congelamento em `ponto_espelhos_fechados`, homologação médica de atestados, alertas de absenteísmo e relatório analítico.
- **`tests/test_ponto_ausencias_adicionais_rf021_rf050.py` (Novo):** 5 testes cobrindo todo o ciclo RF021–RF050 e integração com folha.

## Fase 5 — Férias, PDFs A4 e eSocial `v_S_01_02_00` (`RF051`–`RF060`)
- **`backend/ferias_service.py` (Novo):** Redução por faltas (CLT art. 130), fracionamento em até 3 períodos (art. 134), bloqueio 2 dias pré-DSR/feriado (RN-019), aviso 30 dias (art. 135), dobra (art. 137), abono 1/3, adiantamento de 50% do 13º, férias coletivas, aprovação RN-080, cancelamento, pagamento e integração com a folha (`0100`/`0101`/`0102`/`0103`/`0110`).
- **`backend/documentos_trabalhistas_pdf.py` (Novo):** Geradores de PDF A4 1.4 (`gerar_pdf_aviso_ferias`, `gerar_pdf_recibo_ferias`, `gerar_pdf_trct`, `gerar_pdf_guias_fgts_sd`).
- **`backend/esocial_eventos_trabalhistas.py` (Novo):** Geradores XML `v_S_01_02_00` e validador `ElementTree` (`validar_xml_esocial_trabalhista`) para `S-2230`, `S-1200`, `S-1210`, `S-1299` e `S-2299`.
- **`tests/test_ferias_rf051_rf060.py` (Novo):** 4 testes homologando `FeriasService`, PDFs e `S-2230`.

## Fase 6 — Afastamentos, Estabilidades e Honestidade no eSocial (`RF061`–`RF070`)
- **`backend/afastamento_service.py` (Novo):** Regra 15 dias empresa vs INSS (incluindo soma de 60 dias Decreto 3.048/99), bloqueio de sobreposição, `interrupcao`/`suspensao`, estabilidades B91 (12 meses) e maternidade (150 dias), prorrogação, exigência de ASO de retorno (`sst_asos`) para >= 30 dias, baixa automática de pendências (`resolvida_por`/`resolvida_em`), `S-2230` de início/término e relatório.
- **`backend/plataforma_service.py`:** `transmitir_lote_esocial` atualizado para validar XMLs via `ElementTree`, rejeitar XMLs inválidos (`erro_schema`) e eliminar a fabricação de recibos falsos (`SIM-`).
- **`tests/test_afastamentos_rf061_rf070.py` (Novo):** 3 testes de afastamentos, estabilidades, ASO de retorno e validação XML eSocial.

## Fase 7 — Folha, 13º Salário, Rateio, Financeiro e CNAB 240 (`RF081`–`RF105`)
- **`backend/folha_service.py`:** Integração automática de ponto fechado (`integrar_ponto`) e afastamentos (`integrar_afastamentos`), recuperação automática do adiantamento `0520`, folha complementar diferencial incremental, motor completo persistido de 13º salário (1ª/2ª parcelas, avos >= 15d, médias anuais, dedução de adiantamento das férias, INSS/IRRF exclusivos, provisão 1/12), `conferencia_analitica_folha`, `fechar_competencia_lote`, `gerar_rateio_centro_custo`, `gerar_integracao_financeira` e `gerar_eventos_esocial_folha`.
- **`backend/plataforma_service.py`:** `gerar_arquivo_cnab240` atualizado com isolamento multi-empresa, finalidade (`folha_mensal`, `decimo_terceiro`, `ferias`, `rescisao`) e chave PIX em Segmento B; criado `processar_retorno_cnab240`.
- **`tests/test_folha_decimo_terceiro_rf081_rf105.py` (Novo):** 3 testes cobrindo 13º, folha complementar, rateio, integração financeira, periódicos eSocial e CNAB remessa/retorno.

## Fase 8 — Rescisão Contratual (`RF106`–`RF120`)
- **`backend/rescisao_service.py` (Novo):** 9 modalidades rescisórias normalizadas, bloqueios de estabilidade e afastamento ativo, aviso prévio proporcional Lei 12.506/2011 com projeção, férias vencidas simples/dobro, 12 meses de médias, GRRF separada, validação NR-07 de ASO demissional, multa art. 477 §8º, TRCT e guias em PDF A4, homologação RN-080 e XML `S-2299`.
- **`tests/test_rescisao_rf106_rf120.py` (Novo):** 2 testes cobrindo modalidades, bloqueios, atraso, homologação e PDFs.

## Fase 9 — Servidor HTTP, RBAC e Interface Consolidada
- **`backend/server.py`:** Inclusão das novas rotas GET e POST para ponto, férias, afastamentos, tabelas legais, feriados, 13º salário, fechamento em lote, rateio CC, integração financeira, eSocial periódicos, retorno CNAB 240 e PDFs de férias/rescisão com proteção RBAC (`_exigir_permissao`) e escopo multi-tenant (`_resolver_empresa_escopo`).
- **`frontend/index.html` e `frontend/app.js`:** Inclusão dos novos controles diretamente nos módulos consolidados (sem criar cartões por RF individual), correção de `carregarEspelhoPonto()` para ler chaves reais da API, remoção de `BR-2026-OK` e XML fallback fictício, inclusão de download autenticado de PDFs/CSVs e conexão real de `carregarPortalColaborador()` e `carregarPortalGestor()`.

## Fase 10 — Suíte de Regressão e Documentação Final
- **`tests/executar_todos_testes.py`:** Registro das 5 novas suítes RF021–RF120 e `TestFrontendIntegridade`, totalizando **196 testes executados com 0 falhas e 0 erros**.
- **`docs/CHECKLIST_REQUISITOS_PLATAFORMA.md` e documentos raiz:** Checklist atualizado e criação de `AUDITORIA_TECNICA_RH2.md`, `MATRIZ_RASTREABILIDADE_RF.md`, `RELATORIO_TESTES_HOMOLOGACAO.md`, `PENDENCIAS_TECNICAS.md` e `HISTORICO_CORRECOES.md`.
