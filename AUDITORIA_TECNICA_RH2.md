# AUDITORIA TÉCNICA — MÓDULOS RH2.0 ENTERPRISE (RF021 A RF120)

**Data de Consolidação:** 25/11/2026  
**Escopo Auditado:** Módulos 03 a 11 (`RF021` a `RF120`) na arquitetura produtiva do RH2.0 (`backend/`, `migrations/`, `frontend/`, `tests/`).

---

## 1. Arquitetura Ativa vs. Protótipos Legados

- **Stack Produtiva Auditada e Alterada:** Backend Python (`backend/server.py`, serviços em `backend/*.py`), banco dual-mode SQLite/PostgreSQL via `backend/database.py` e `migrations/001..012`, e SPA consolidada em `frontend/index.html` + `frontend/app.js`.
- **Protótipos Fora de Escopo:** Os diretórios `backend-nest/` e `frontend-react/` foram identificados como protótipos incompletos não servidos pelo runtime principal e mantidos intocados.

---

## 2. Achados Críticos da Auditoria Inicial e Correções Realizadas

1. **Tabelas Legais Versionadas e Feriados (`RF042`, `RF081`–`RF085`):**
   - *Achado:* Ausência de versionamento histórico de tabelas legais e contagem simplificada de dias úteis/DSR.
   - *Correção:* Criada migration `migrations/012_homologacao_modulos_rf021_rf120.sql` com `tabelas_legais_vigencia`, `tabelas_legais_historico` e `feriados_calendario`, além do serviço `backend/tabelas_legais_service.py` (`TabelasLegaisService`), integrado a `FolhaService` e `FeriasService`.

2. **Ponto, Ausências e Adicionais (`RF021`–`RF050`):**
   - *Achado:* `PontoService` possuía ordenação insuficiente de batidas noturnas virando a meia-noite (`_ordenar_marcacoes_dia`) e faltavam bloqueios/integrações completas de escalas 12x36, interjornada 11h, banco de horas e fechamento/reabertura em lote.
   - *Correção:* Refatorado `backend/ponto_service.py` com ordenação cronológica em turnos noturnos, validação de tolerância 5/10 min (CLT art. 58 §1º), intrajornada, interjornada 11h, limite de 2h extras diárias, redução ficta noturna (52m30s), prorrogação noturna (Súmula 60 TST), atestados com homologação médica e integração real de fechamento com a folha (`integrar_ponto`).

3. **Férias & Abono (`RF051`–`RF060`):**
   - *Achado:* Regras de férias concentradas parcialmente sem serviço dedicado, faltando PDFs oficiais (Aviso e Recibo A4) e XML `S-2230` real.
   - *Correção:* Criado `backend/ferias_service.py` (`FeriasService`), `backend/documentos_trabalhistas_pdf.py` (`gerar_pdf_aviso_ferias`, `gerar_pdf_recibo_ferias`) e `backend/esocial_eventos_trabalhistas.py` (`S-2230` leiaute `v_S_01_02_00`), aplicando redução por faltas (CLT art. 130), fracionamento em até 3 períodos (art. 134), trava de 2 dias pré-DSR/feriado (RN-019), antecedência de 30 dias (art. 135), dobra (art. 137), abono 1/3, adiantamento de 13º e integração automática com `FolhaService` (rubricas `0100`, `0101`, `0102`, `0103`, `0110`).

4. **Afastamentos & Estabilidade (`RF061`–`RF070`) e Honestidade no eSocial:**
   - *Achado:* Regras de afastamentos e estabilidade sem service dedicado; `transmitir_lote_esocial` gerava recibos simulados prefixados com `SIM-` e `frontend/app.js` exibia protocolo fictício `BR-2026-OK` e XML fallback inventado.
   - *Correção:* Criado `backend/afastamento_service.py` (`AfastamentoService`) com rateio de 15 dias empresa vs INSS (inclusive soma de 60 dias Decreto 3.048/99), prorrogação, exigência de ASO de retorno em afastamentos >= 30 dias (`sst_asos`), bloqueio de sobreposição, estabilidades B91 (12 meses) e maternidade (150 dias), e XML `S-2230` de início e término. Removida fabricação de recibo `SIM-`, mantido `numero_recibo = NULL` e validação XML via `ElementTree` (`validar_xml_esocial_trabalhista`), além de remoção do texto `BR-2026-OK` e fallback XML no frontend.

5. **Folha de Pagamento, 13º Salário, Rateio, Integração Financeira e CNAB 240 (`RF081`–`RF105`):**
   - *Achado:* `FolhaService` sem persistência dedicada de 13º salário/provisão mensal `1/12`, sem cálculo diferencial completo de folha complementar, sem rateio contábil por centro de custo e sem processamento de retorno bancário CNAB 240.
   - *Correção:* Ampliado `backend/folha_service.py` (`calcular_decimo_terceiro_colaborador`, `calcular_decimo_terceiro_lote`, `listar_decimo_terceiro`, `calcular_provisao_decimo_terceiro`, `conferencia_analitica_folha`, `fechar_competencia_lote`, `gerar_rateio_centro_custo`, `gerar_integracao_financeira`, `gerar_eventos_esocial_folha`, `integrar_afastamentos`) e `PlataformaService` (`gerar_arquivo_cnab240` multi-empresa/PIX + `processar_retorno_cnab240`).

6. **Rescisão Contratual (`RF106`–`RF120`):**
   - *Achado:* Fluxo rescisório sem cobertura completa das 9 modalidades legais, sem geração dedicada de TRCT/Guias FGTS-SD em PDF A4 e sem baixa completa de obrigações e S-2299 estruturado.
   - *Correção:* Criado `backend/rescisao_service.py` (`RescisaoService`) cobrindo 9 modalidades rescisórias, bloqueio de estabilidade/afastamento, aviso prévio proporcional (Lei 12.506/2011) com projeção em avos, férias vencidas simples/dobro, 12 meses de médias, GRRF separada, validação NR-07 de ASO demissional em `sst_asos`, multa do art. 477 §8º por atraso na quitação, PDFs A4 (`gerar_pdf_trct`, `gerar_pdf_guias_fgts_sd`), homologação RN-080 e XML `S-2299`.

7. **Rotas HTTP, RBAC, Multi-Tenant e UI Consolidada:**
   - *Correção:* Adicionadas novas rotas GET e POST em `backend/server.py` protegidas por `_exigir_permissao` e `_resolver_empresa_escopo`. Em `frontend/index.html` e `frontend/app.js`, as ações foram incorporadas exclusivamente dentro dos cartões consolidados existentes, corrigindo `carregarEspelhoPonto()` para ler os campos reais de `PontoService` e conectando os portais (`carregarPortalColaborador` e `carregarPortalGestor`) às APIs reais.
