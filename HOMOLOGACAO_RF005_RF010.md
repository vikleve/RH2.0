# Documento de Homologação Técnica — Consolidação do Cadastro do Colaborador (RF-005 a RF-010)

**Sistema:** RH2.0 Enterprise — Departamento Pessoal & GTI  
**Escopo:** Requisitos Funcionais **RF-005 a RF-010**  
**Arquitetura Oficial:** Backend Python (`backend/`) + Banco Dual SQLite/PostgreSQL (`backend/database.py`, `migrations/`) + Frontend SPA Vanilla JS (`frontend/`)

---

## 1. Resumo da Auditoria Técnica e Arquitetural

1. **Preservação da arquitetura oficial (`ADR-001`)**:
   - Confirmado em `docs/ARQUITETURA_OFICIAL_RH2_ENTERPRISE.md` e `vercel.json` que a aplicação oficial em produção executa sobre o backend Python (`backend/server.py`, `api/index.py`, `api/colaboradores.py`) e o frontend SPA em `frontend/index.html`, `frontend/app.js` e `frontend/styles.css`.
   - As pastas `backend-nest/` e `frontend-react/` são protótipos legados não implantados e foram integralmente preservadas sem remoção nem duplicação paralela.
2. **Saneamento e Correções Estruturais Identificadas**:
   - Remoção de **3 cópias duplicadas** dos métodos de anexos (`adicionar_documento`, `listar_documentos`, `remover_documento`) em `backend/service.py`.
   - Correção multi-tenant em `AuthService.validar_sessao` (`backend/auth.py`) para retornar `u.empresa_id` do usuário autenticado (com fallback seguro quando a coluna não existir).
   - Correção da contagem de dependentes ativos em `ColaboradorService.listar` (`backend/service.py`) adicionando `d.id IS NOT NULL AND COALESCE(d.situacao, 'ativo') = 'ativo'` no `LEFT JOIN`.
   - Namespacing de registros de auditoria de colaboradores espelhados em `auditoria_operacoes` (`registro_id = f"colaborador:{colaborador_id}"` em `_registrar_auditoria_cadastral`) para evitar colisão de IDs numéricos com outros módulos como `folhas_pagamento`.
   - Prevenção de sobrescrita silenciosa de `cpf_titular` por `titular_cpf` no cadastro de dados bancários (`cadastrar_dados_bancarios`).

---

## 2. Matriz de Rastreabilidade (RF-005 a RF-010)

| Requisito | Entidades / Banco | Camada de Negócio & Validação | API REST (`backend/server.py`) | Interface (`frontend/`) | Integrações & Segurança |
|---|---|---|---|---|---|
| **RF-005 — Gestão de Dependentes** | `dependentes` (campos de IRRF, Salário-Família, Plano de Saúde, `situacao`, `data_encerramento`) | `validar_dependente(..., exigir_campos_completos=True)` em `backend/validators.py`; `listar_dependentes`, `cadastrar_dependente`, `editar_dependente`, `inativar_dependente` em `backend/service.py` | `GET /api/colaboradores/<id>/dependentes`<br>`POST /api/colaboradores/<id>/dependentes`<br>`PUT /api/colaboradores/<id>/dependentes/<dep_id>`<br>`DELETE /api/colaboradores/<id>/dependentes/<dep_id>` | Aba `#tab-dependentes` no `#modal-detalhes` com CRUD, flags legais e filtro de inativos | Exclusão lógica preservando histórico; bloqueio de CPF duplicado entre ativos; `FolhaService.obter_dados_colaborador` e `/api/folha/colaboradores` filtram apenas dependentes ativos por finalidade (`IRRF`, `Salário-Família`, `Plano de Saúde`). |
| **RF-006 — Histórico Funcional** | `historico_funcional` (tipos de movimentação, `data_alteracao`, `data_vigencia`, `retroativa`, `justificativa`, metadados de auditoria) | `listar_historico_funcional`, `registrar_movimentacao_funcional`, `_inserir_movimentacao_funcional_cursor` em `backend/service.py` (atualização atômica em `colaboradores` na mesma transação) | `GET /api/colaboradores/<id>/historico-funcional` (filtros `tipo`, `data_inicio`, `data_fim`)<br>`POST /api/colaboradores/<id>/historico-funcional`<br>`PUT/DELETE .../historico-funcional/<mov_id>` → **HTTP 403** | Aba `#tab-hist-funcional` no `#modal-detalhes` com filtros por tipo/período e registro imutável | Imutabilidade garantida (PUT/DELETE retornam HTTP 403); ordenação cronológica por `data_vigencia DESC`; suporte a lançamentos retroativos e atualização conjunta (promoção, reajuste, transferência, jornada, centro de custo). |
| **RF-007 — Anexos Cadastrais** | `colaborador_documentos` (`categoria`, `nome_interno_seguro`, `caminho_privado`, `sha256_hash`, `versao`, `documento_raiz_id`, `situacao`, `data_emissao`, `data_validade`, campos de inativação) | `validar_arquivo_documento` em `backend/validators.py`; `adicionar_documento`, `listar_documentos`, `listar_versoes_documento`, `obter_documento_para_download`, `remover_documento` em `backend/service.py` | `GET /api/colaboradores/<id>/documentos`<br>`POST /api/colaboradores/<id>/documentos`<br>`POST .../documentos/<doc_id>/versoes`<br>`GET .../documentos/<doc_id>/versoes`<br>`GET .../documentos/<doc_id>/download`<br>`DELETE .../documentos/<doc_id>` | Aba `#tab-documentos` com categoria, emissão, validade, pesquisa textual, histórico de versões, download via `Blob` autenticado e inativação lógica | Storage privado em `storage/private_docs` (ou `PRIVATE_DOCS_DIR`, fora de `frontend/` e ignorado no `.gitignore`); bloqueio de extensões/assinaturas maliciosas (`MZ`, `\x7fELF`, `#!`, `<script`, `<?php`, `<html`, `<svg`) e path traversal; trilha de download/visualização. |
| **RF-008 — Controle de Documentação** | `documentos_categorias` (10 categorias seed), `documentos_config_alertas` (`[30, 15, 7]`, `10 MB`), `pendencias_operacionais` | `listar_categorias_documentos`, `criar_categoria_documento`, `obter_config_alertas_documentos`, `atualizar_config_alertas_documentos`, `obter_controle_documentacao` em `backend/service.py` | `GET /api/documentos/controle`<br>`GET /api/documentos/categorias`<br>`POST /api/documentos/categorias`<br>`GET /api/documentos/config-alertas`<br>`PUT /api/documentos/config-alertas` | Painel RF-008 em `#view-modulo-documentos` com KPIs (`Regulares`, `Próximos do Vencimento`, `Vencidos`, `Pendências Obrigatórias`), filtros, configuração de alertas e sincronização | Classificação automática (`regular`, `proximo_vencimento`, `vencido`, `pendente`, `sem_validade`, `inativo`) e sincronização idempotente de alertas em `pendencias_operacionais`. |
| **RF-009 — Dados Bancários** | `colaborador_dados_bancarios` (banco, agência, conta, dígito, tipo, PIX, titular, CPF, `principal`, `ativo`) | `validar_dados_bancarios` em `backend/validators.py`; `listar_dados_bancarios`, `cadastrar_dados_bancarios`, `atualizar_dados_bancarios`, `inativar_dados_bancarios` em `backend/service.py` | `GET /api/colaboradores/<id>/dados-bancarios`<br>`POST /api/colaboradores/<id>/dados-bancarios`<br>`PUT /api/colaboradores/<id>/dados-bancarios/<conta_id>`<br>`DELETE /api/colaboradores/<id>/dados-bancarios/<conta_id>` | Aba `#tab-bancarios` no `#modal-detalhes` | Validação de banco, agência, conta, CPF do titular e chave PIX; garantia de conta `principal` única ativa por colaborador; integração com `PlataformaService.gerar_arquivo_cnab240` (Segmento A). |
| **RF-010 — Auditoria Cadastral** | `historico_alteracoes` (`entidade`, `operacao`, `origem`, `ip_origem`, `justificativa`) e espelho em `auditoria_operacoes` | `_registrar_auditoria_cadastral` e `listar_auditoria_cadastral` em `backend/service.py` | `GET /api/colaboradores/<id>/auditoria` (filtros `entidade`, `usuario`, `campo`, `data_inicio`, `data_fim`) | Aba `#tab-historico` atualizada com filtros por entidade, usuário e campo | Rastreabilidade completa de `valor_anterior`, `valor_novo`, `usuario_responsavel`, `data_hora`, `origem` e `ip_origem` em todas as mutações de RF-001 a RF-009 e visualização/download de documentos. |

---

## 3. Artefatos Criados e Atualizados

- `migrations/010_consolidacao_colaborador_rf005_rf010.sql` (migração idempotente PostgreSQL com DDL, índices e seeds iniciais)
- `backend/database.py` (DDLs SQLite/PostgreSQL, colunas incrementais, índices e seeds de categorias/alertas em `init_db`)
- `backend/auth.py` (`AuthService.validar_sessao` com suporte a `empresa_id`)
- `backend/validators.py` (validações completas de RF-005, RF-007 e RF-009)
- `backend/service.py` (serviços completos RF-001 a RF-010, sem duplicações)
- `backend/folha_service.py` (contagem exclusiva de dependentes ativos por benefício/tributo)
- `backend/plataforma_service.py` (integração da conta principal ativa no CNAB 240)
- `backend/server.py` (endpoints REST e resolução segura de escopo multi-empresa)
- `frontend/index.html` e `frontend/app.js` (abas do `#modal-detalhes` e painel RF-008 em `#view-modulo-documentos`)
- `.gitignore` (exclusão do diretório privado `storage/`)
- `tests/test_colaborador_rf005_rf010.py` e `tests/executar_todos_testes.py`

---

## 4. Evidências de Execução dos Testes (Pós-Edição Final)

1. **Compilação Python & Sintaxe JavaScript**:
   - `python -m py_compile backend\auth.py backend\database.py backend\validators.py backend\service.py backend\folha_service.py backend\plataforma_service.py backend\server.py` → **exit code 0**
   - `node --check frontend\app.js` → **exit code 0**
2. **Integridade Estrutural do Frontend (`tests/test_frontend_integridade.py`)**:
   - `python -m unittest tests.test_frontend_integridade -v` → **4 testes executados, 4 aprovados (`OK` em 0.924s)**.
3. **Suíte Completa de Regressão (`tests/executar_todos_testes.py`)**:
   - Inclui `TestModuloColaboradores`, `TestFolhaCalculos`, `TestRegrasNegocioOficiais2026`, `TestPlataformaCicloTrabalhista`, `TestResponsividadeDesktopMobile`, `TestRBACEnterprise`, `TestMotorUnificadoEEmpresarial`, `TestFolhaService`, `TestFolhaApi`, `TestFolhaEnterpriseCompleta`, `TestHoleritePDF`, `TestBeneficiosRF071RF080`, `TestColaboradorRF005RF010` (RF-005 a RF-010 + isolamento multiempresa), `TestApiColaboradores`, `TestAutenticacaoSeguranca` e `TestAutenticacaoRH20`.
   - Resultado observado: **165 testes executados em 1046.54s — Sucessos: 165 | Falhas: 0 | Erros: 0 (`OK`)**.
4. **Limitações de Ambiente Observadas**:
   - A execução E2E via navegador Chrome/Edge headless CDP não está disponível neste ambiente de sandbox; todos os fluxos de API, regras de negócio, integridade HTML/JS, geração binária de arquivos, CNAB 240, folha e isolamento multi-tenant foram validados por testes automatizados reais contra servidores/handlers e banco SQLite isolado.
   - A migração PostgreSQL `migrations/010_consolidacao_colaborador_rf005_rf010.sql` foi estruturada de forma idempotente para execução em produção PostgreSQL (não há instância PostgreSQL em execução no sandbox local para execução direta da migração).
