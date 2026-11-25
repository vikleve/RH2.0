# PENDÊNCIAS TÉCNICAS — RH2.0 ENTERPRISE

Itens identificados que dependem de infraestrutura externa ou execução em ambiente específico fora do escopo deste sandbox:

1. **Integração Produtiva eSocial com Certificado ICP-Brasil A1/A3 (`RF-060`, `RF-069`, `RF-092`, `RF-093`, `RF-103`, `RF-119`):**
   - **Estado atual:** Os arquivos XML no leiaute `v_S_01_02_00` (`S-2230`, `S-1200`, `S-1210`, `S-1299`, `S-2299`) e a validação estrutural `ElementTree` em `backend/esocial_eventos_trabalhistas.py` + `PlataformaService.transmitir_lote_esocial` estão implementados e testados; recibos fictícios `SIM-` e protocolo fictício `BR-2026-OK` foram removidos (`numero_recibo = NULL`, `simulacao: True`).
   - **Pendência:** Conectar assinatura digital XMLDSig com certificado ICP-Brasil A1/A3 da empresa e envio SOAP/mTLS ao ambiente de Produção Restrita / Produção Nacional do eSocial.

2. **Execução e Homologação em Instância PostgreSQL Ativa (`migrations/012_homologacao_modulos_rf021_rf120.sql`):**
   - **Estado atual:** Toda a suíte automatizada de 196 testes foi executada contra SQLite isolado com placeholders/helpers dual-mode (`_usar_postgres`, `ph`, `insert_returning_id`).
   - **Pendência:** Executar a migration `migrations/012_homologacao_modulos_rf021_rf120.sql` e rodar `tests/test_persistencia_postgres.py` contra um servidor PostgreSQL ativo no ambiente de homologação/produção.

3. **Testes End-to-End Interativos em Navegador Real (Chrome / Playwright):**
   - **Estado atual:** A integridade estrutural de `frontend/index.html`, a sintaxe JavaScript (`node --check frontend/app.js`), a responsividade CSS (`360px` a `1920px`), a presença de todos os IDs e os contratos REST foram validados via `TestFrontendIntegridade`, `TestResponsividadeDesktopMobile`, `TestRBACEnterprise` e `TestApiColaboradores`/`TestFolhaApi`.
   - **Pendência:** Executar bateria E2E visual em navegador Chrome real (cliques, preenchimento de modais, download visual de PDFs/CSVs e fluxos completos em `localhost`).

4. **Protótipos Legados (`backend-nest/` e `frontend-react/`):**
   - Mantidos intocados fora da arquitetura produtiva ativa (Python + Vanilla SPA).
