# 01 — Diagnóstico Atual do Sistema (Inventário Técnico e Funcional)

**Projeto:** RH2.0 — Portal de Departamento Pessoal & Folha de Pagamento  
**Data da Auditoria:** 18/11/2026  
**Fase:** Auditoria e Planejamento Inicial (Sem alteração de código funcional)

---

## 1. Resumo do Levantamento Técnico (Seção 7.1)

A inspeção completa do repositório revelou que o projeto possui uma implementação funcional e madura na stack principal **Python Serverless + Vanilla JS**, além de uma árvore paralela experimental em **NestJS + React**.

### 1.1. Stack Principal Operacional (Canônica para Vercel + Neon)
- **Linguagens:** Python 3.11+ (testado em Python 3.14), HTML5, CSS3, JavaScript (ES6+ Vanilla).
- **Backend Local e Serverless:**
  - Servidor HTTP REST nativo: `backend/server.py` (`ApiColaboradorHandler`).
  - Funções Serverless Vercel: `api/index.py`, `api/colaboradores.py`, `api/auth/login.py`, `api/auth/logout.py`, `api/auth/me.py`.
- **Camada de Persistência e Banco de Dados:**
  - Módulo Dual-Mode sem ORM (SQL parametrizado direto via driver nativo): `backend/database.py`.
  - Drivers: `psycopg2-binary>=2.9.0` (PostgreSQL/Neon em produção/nuvem) e `sqlite3` (desenvolvimento local isolado e testes automatizados).
- **Serviços e Regras de Negócio:**
  - `backend/auth.py`: Autenticação PBKDF2-HMAC-SHA256 (100.000 iterações), salt de 16 bytes, comparação em tempo constante (`hmac.compare_digest`), sessões de 12h com revogação no logout e regeneração no login.
  - `backend/audit.py`: Gravação de eventos de segurança (`LOGIN_SUCESSO`, `LOGIN_FALHA`, `LOGOUT`, `BLOQUEIO_RATE_LIMIT`) na tabela `auditoria_autenticacao`.
  - `backend/rate_limiter.py`: Limite de 5 tentativas inválidas em janela deslizante de 15 minutos (HTTP 429 + `Retry-After`).
  - `backend/csrf.py`: Proteção de origem (`Origin`, `Referer`, `Sec-Fetch-Site`) para métodos mutáveis (`POST`, `PUT`, `PATCH`, `DELETE`).
  - `backend/service.py` e `backend/validators.py`: CRUD completo de colaboradores e dependentes, validação matemática de CPF, idade mínima (14 anos), unicidade de CPF/matrícula, inativação/reativação lógica e trilha de auditoria em `historico_alteracoes`.
  - `backend/folha_service.py`: Ciclo de vida da folha de pagamento (`rascunho`, `calculada`, `fechada`, `cancelada`), parâmetros vigentes (`folha_parametros`), itens calculados (`folha_itens`) e trilha de auditoria (`folha_historico`).
  - `backend/folha_calculos.py` e `backend/catalogo_eventos.py`: Motor matemático com `Decimal` (`ROUND_HALF_UP`), cobrindo 82 rubricas trabalhistas (Grupos A a F), tabela progressiva de INSS (faixas 2026 até teto de R$ 8.157,41), tabela progressiva de IRRF com dedução por dependente (R$ 189,59), FGTS informativo (8%) e encargos patronais.
- **Frontend:**
  - `frontend/index.html` (1.378 linhas), `frontend/styles.css`, `frontend/app.js` (2.330 linhas).
  - Contém tela de login institucional, Módulo 01 (Gestão de Colaboradores com busca, filtros RF-002, modal de cadastro/edição, dependentes e histórico) e Módulo 02 (Folha de Pagamento com cards de resumo, filtros por competência/situação/setor, modal de lançamento com prévia, modal de parâmetros, holerite imprimível com memória de cálculo passo a passo e modais de fechamento/reabertura).
- **Migrações SQL:**
  - `migrations/001_schema_inicial.sql`
  - `migrations/002_modulo_folha_pagamento.sql`
  - `migrations/003_auditoria_autenticacao.sql`
  - `migrations/004_modulo_colaboradores_spec03.sql`
  - `migrations/005_seguranca_multiempresa.sql`
- **Testes Automatizados:**
  - `tests/executar_todos_testes.py`: 94 testes automatizados (passando em 24,93s).
  - `tests/test_persistencia_postgres.py`: 12 testes específicos de configuração PostgreSQL/Neon e prevenção de fallback SQLite em produção (passando em 0,25s).
  - Total verificado na auditoria: **106 testes automatizados passando (100% PASS)**.
- **Configuração de Deploy:**
  - `vercel.json`, `requirements.txt`, `pyproject.toml`, `.env.example`.

### 1.2. Árvore Paralela Secundária (`backend-nest/` e `frontend-react/`)
- O repositório contém uma implementação paralela em NestJS (`backend-nest/`) e um esboço parcial em React (`frontend-react/`).
- O `frontend-react/` possui apenas a tela de colaboradores (`ColaboradoresPage.tsx`), não possui tela de login nem módulo de folha de pagamento, e não possui bundler configurado (`build: tsc --noEmit`).
- **Decisão de Preservação (Seções 3.1 e 7.3):** A stack Python (`backend/` + `api/`) + Vanilla JS (`frontend/`) é 100% compatível com o Vercel Serverless, já implementa toda a interface de Login, Colaboradores e Folha de Pagamento, e concentra os 106 testes automatizados. Portanto, ela é mantida como a arquitetura principal do projeto, preservando-se os diretórios `backend-nest/` e `frontend-react/` sem exclusão destrutiva.

---

## 2. Respostas Objetivas da Auditoria de Persistência (Seção 4.1)

1. **O sistema possui banco de dados?** Sim. Possui camada relacional implementada em `backend/database.py` e scripts em `migrations/001` a `005`.
2. **Qual tecnologia utiliza?** Arquitetura Dual-Mode: PostgreSQL (via `psycopg2-binary`) quando `DATABASE_URL` ou `NEON_DATABASE_URL` está configurada, e SQLite (`sqlite3`) exclusivamente para desenvolvimento local sem URL ou suíte de testes (`db_path` explícito).
3. **O Neon já está configurado?** Em nível de **código**, sim (`backend/database.py` reconhece `DATABASE_URL` e `NEON_DATABASE_URL`, força `sslmode=require`, `connect_timeout=15` e identifica `provedor: "neon"` e `pooled: true` em `/api/health`). Em nível de **ambiente**, não há arquivo `.env` local nem variável `DATABASE_URL` ativa na sessão atual, faltando injetar a connection string do banco Neon disponibilizado pelo responsável.
4. **Qual ORM ou biblioteca de acesso é utilizada?** Não utiliza ORM pesado; utiliza SQL parametrizado direto sobre `psycopg2` (PostgreSQL) e `sqlite3` (SQLite), abstraídos por helpers em `backend/database.py` (`get_connection`, `ph`, `fetchone_dict`, `fetchall_dict`, `insert_returning_id`).
5. **Existem modelos e migrações?** Sim. Existem 5 arquivos SQL versionados em `migrations/` (`001` a `005`) e o inicializador idempotente `init_db()` em `backend/database.py`.
6. **Quais tabelas existem?** Existem 10 tabelas modeladas:
   - `usuarios`
   - `sessoes`
   - `auditoria_autenticacao`
   - `colaboradores`
   - `dependentes`
   - `historico_alteracoes`
   - `folha_parametros`
   - `folhas_pagamento`
   - `folha_itens`
   - `folha_historico`
7. **Existem relacionamentos?** Sim, com chaves estrangeiras explícitas:
   - `dependentes.colaborador_id -> colaboradores.id (ON DELETE CASCADE)`
   - `historico_alteracoes.colaborador_id -> colaboradores.id (ON DELETE CASCADE)`
   - `sessoes.usuario_id -> usuarios.id (ON DELETE CASCADE)`
   - `folhas_pagamento.colaborador_id -> colaboradores.id (ON DELETE RESTRICT)`
   - `folhas_pagamento.parametro_id -> folha_parametros.id`
   - `folha_itens.folha_id -> folhas_pagamento.id (ON DELETE CASCADE)`
   - `folha_historico.folha_id -> folhas_pagamento.id (ON DELETE CASCADE)`
8. **Os cadastros são efetivamente persistidos?** Sim. `frontend/app.js` envia todas as operações para a API REST (`/api/colaboradores` e `/api/folha`), que executa `INSERT`/`UPDATE` com `conn.commit()`. O antigo fallback em `localStorage` já foi removido.
9. **Os dados permanecem após reinicialização?** Quando conectado ao PostgreSQL/Neon (ou SQLite em disco local), sim. Em produção na Vercel sem `DATABASE_URL`, o sistema recusa operação com HTTP 503 (`BANCO_INDISPONIVEL`) para impedir gravação no filesystem efêmero `/tmp`.
10. **O sistema possui transações?** Parcialmente. `FolhaService.criar_ou_atualizar_folha` possui bloco `try / conn.commit() / except / conn.rollback()`. Já `ColaboradorService.cadastrar`, `ColaboradorService.atualizar`, `FolhaService.fechar_folha` e `FolhaService.reabrir_folha` executam múltiplos comandos SQL antes de `conn.commit()`, mas sem bloco `try/except/finally` explícito para garantir `rollback()` e fechamento determinístico da conexão em caso de exceção intermediária.
11. **Os dados são recuperados do banco ou de estruturas simuladas?** Recuperados diretamente do banco de dados via consultas SQL. Exceção parcial: os dados institucionais da empresa no cabeçalho do holerite (`PORTAL DP & RH LTDA`, CNPJ `12.345.678/0001-90`) estão fixos (hardcoded) em `frontend/index.html` (linhas 1130-1132).
12. **Existem operações de gravação que não chegam ao banco?** Sim, duas situações identificadas:
    - O modal de Parâmetros da Folha (`#modal-parametros-folha` em `frontend/index.html`, linhas 1273-1312) possui todos os campos marcados como `readonly` e não tem botão de salvar conectado ao endpoint `POST /api/folha/parametros` (que já existe em `backend/server.py`, linha 508).
    - O botão "Simular / Recalcular" (`#btn-simular-calculo` em `frontend/app.js`, linha 1678) executa apenas um cálculo aproximado no navegador (`atualizarPreviaCalculo`), que diverge do motor oficial em `backend/folha_calculos.py`.
13. **Há funcionalidades que funcionam somente no frontend?** A prévia rápida da folha (`atualizarPreviaCalculo` em `frontend/app.js`, linhas 1857-1925) roda apenas no cliente com fórmula simplificada (sem IRRF e com teto de INSS defasado de R$ 908,85), enquanto o cálculo real ocorre no backend ao salvar.
14. **O sistema utiliza credenciais seguras?** Sim. Não há senhas reais ou connection strings do Neon hardcoded no código. `AuthService` exige `ADMIN_INITIAL_PASSWORD` via variável de ambiente fora do modo de teste.
15. **É possível conectar ao Neon com as credenciais autorizadas disponíveis?** O driver `psycopg2` (v2.9.10) está instalado e pronto, mas a variável `DATABASE_URL` não está presente no ambiente atual. Assim que o responsável fornecer a `DATABASE_URL` do projeto Neon, a conexão imediata pode ser realizada e testada.

---

## 3. Inventário Funcional e Classificação (Seção 7.2)

| Funcionalidade | Classificação | Estado Atual | Evidência Concreta |
|---|---|---|---|
| **Autenticação e Sessão (`POST /api/auth/login`, `logout`, `me`)** | **APROVEITAR** | Funcional e validada | `backend/auth.py`, `backend/server.py`, `tests/test_autenticacao.py` (17 testes PASS). |
| **Rate Limiting e Proteção CSRF** | **AJUSTAR** | Parcialmente funcional | Ativo em `backend/server.py`, mas ausente nos handlers isolados `api/auth/login.py` e `api/colaboradores.py`; contador do `RateLimiter` é apenas em memória. |
| **Auditoria de Autenticação (`auditoria_autenticacao`)** | **APROVEITAR** | Funcional e validada | `backend/audit.py`, `migrations/003_auditoria_autenticacao.sql`, `test_ac_16` PASS. |
| **Configuração da Empresa (Dados do Empregador)** | **COMPLEMENTAR** | Ausente (Hardcoded no HTML) | `frontend/index.html#L1130-L1132` exibe razão social e CNPJ fixos no holerite; não há persistência de dados da empresa em `folha_parametros` ou tabela dedicada. |
| **Cadastro, Listagem e Filtros de Colaboradores (`RF-002`)** | **APROVEITAR** | Funcional e validada | `backend/service.py`, `frontend/app.js`, `tests/test_colaboradores.py` (16 testes PASS). |
| **Edição Cadastral Auditada e Dependentes (`RF-003`)** | **APROVEITAR** | Funcional e validada | `backend/service.py#L308-L414`, grava antes/depois em `historico_alteracoes`. |
| **Inativação e Reativação Lógica de Colaboradores** | **APROVEITAR** | Funcional e validada | `backend/service.py#L416-L467`, preserva histórico e impede exclusão física. |
| **Parâmetros de Cálculo da Folha (`GET/POST /api/folha/parametros`)** | **CORRIGIR** | Parcialmente funcional | Backend tem `GET` e `POST` (`backend/server.py#L349,L508`), mas `frontend/index.html#L1273-L1316` deixa os campos `readonly` sem botão de salvar, e `Decimal` do Postgres falha no `json.dumps`. |
| **Catálogo de 82 Eventos Trabalhistas (`GET /api/folha/eventos-catalogo`)** | **APROVEITAR** | Funcional e validada | `backend/catalogo_eventos.py`, `backend/folha_calculos.py` (36 testes unitários PASS). |
| **Motor de Cálculo CLT (Proventos, Descontos, INSS, IRRF, FGTS)** | **APROVEITAR** | Funcional e validada | `backend/folha_calculos.py` (1.663 linhas com `Decimal` e memória de cálculo). |
| **Criação e Cálculo de Folha Individual (`POST /api/folha`)** | **CORRIGIR** | Parcialmente funcional | Funciona em SQLite (`test_folha_api.py` PASS), mas no PostgreSQL `psycopg2` retorna `Decimal` nas colunas `NUMERIC(15,2)` e `backend/server.py#L215` quebra por falta de `default` no `json.dumps`. |
| **Edição e Recálculo de Folha (`PUT /api/folha/<id>`)** | **CORRIGIR** | Defeituosa na interface | Em `frontend/app.js#L1599-L1615`, `abrirModalEdicaoFolha` mapeia `102` como Noturno (quando `102` é HE 100% e `103` é Noturno) e ignora rubricas do catálogo salvas com `origem='calculado'`. |
| **Prévia de Cálculo no Formulário (`atualizarPreviaCalculo`)** | **AJUSTAR** | Parcialmente funcional | `frontend/app.js#L1857-L1925` usa estimativa local sem IRRF e com teto INSS antigo (R$ 908,85), divergindo do valor calculado ao salvar. |
| **Geração / Processamento de Folha em Lote na Competência** | **COMPLEMENTAR** | Ausente | O sistema só permite criar folha escolhendo 1 colaborador por vez no modal; falta ação para processar/fechar a competência para todos os colaboradores ativos elegíveis. |
| **Fechamento e Reabertura Auditada (`POST /api/folha/<id>/fechar`, `reabrir`)** | **APROVEITAR** | Funcional e validada | `backend/folha_service.py#L528-L590`, bloqueia edição de folha fechada e exige justificativa na reabertura. |
| **Emissão de Demonstrativo / Holerite e Memória de Cálculo** | **AJUSTAR** | Parcialmente funcional | `frontend/index.html#L1113-L1253` e `frontend/app.js#L2020-L2131` geram holerite imprimível, mas com cabeçalho de empresa estático. |
| **Consulta de Histórico de Competências Anteriores** | **APROVEITAR** | Funcional e validada | `GET /api/folha?competencia=AAAA-MM` recupera folhas fechadas e calculadas diretamente do banco. |

---

## 4. Principais Defeitos e Bloqueadores Diagnosticados (Com Evidências)

### Defeito D-01 (P0 — Bloqueador de Execução no PostgreSQL/Neon): `TypeError: Object of type Decimal is not JSON serializable`
- **Onde ocorre:** `backend/server.py` (linha 215) em conjunto com `backend/folha_service.py` (linhas 68, 165, 425, 441, 520).
- **Evidência:** No PostgreSQL, as colunas `NUMERIC(15,2)` de `folhas_pagamento` e `folha_parametros` são retornadas pelo `psycopg2` como instâncias de `decimal.Decimal`. Enquanto `ColaboradorService` converte `salario_base` para `float` manualmente (`backend/service.py#L268,L300`), `FolhaService` retorna os dicionários brutos e `ApiColaboradorHandler._enviar_json` executa `json.dumps(dados, ensure_ascii=False, indent=2)` sem conversor `default`. Nos testes com SQLite o erro não aparece porque o SQLite devolve `float`. No Neon PostgreSQL, qualquer chamada a `/api/folha` ou `/api/folha/parametros` falhará com erro 500 se não for corrigida.

### Defeito D-02 (P0 — Integridade de Tipos Monetários): Colunas `REAL` na tabela `folha_itens`
- **Onde ocorre:** `migrations/002_modulo_folha_pagamento.sql` (linhas 78–81) e `backend/database.py` (linhas 434–436).
- **Evidência:** As colunas `referencia`, `valor_unitario` e `valor_total` da tabela `folha_itens` foram definidas como `REAL` (ponto flutuante binário de 32 bits / precisão simples) no PostgreSQL, contrariando o requisito de precisão decimal exata (`NUMERIC(15,2)` / `NUMERIC(15,4)`) usado em `folhas_pagamento`.

### Defeito D-03 (P0 — Performance e Concorrência Serverless no Neon): DDL e `ALTER TABLE` executados a cada instanciação de serviço
- **Onde ocorre:** `backend/database.py` (`init_db`, linhas 484–596), chamado no `__init__` de `ColaboradorService`, `FolhaService` e `AuthService`.
- **Evidência:** A cada cold start serverless (ou instanciação sem cache), `init_db()` executa 10 `CREATE TABLE`, 19 `CREATE INDEX`, 15 `ALTER TABLE` e 3 consultas de provisionamento de parâmetros e usuários. Em conexões pooled (`-pooler` / PgBouncer em modo transaction), executar `ALTER TABLE` repetidamente no boot das funções serverless gera contenção de locks de catálogo no Neon.

### Defeito D-04 (P1 — Defeito Funcional na Edição de Folha): Perda de eventos do catálogo e troca de códigos `102`/`103` ao editar folha
- **Onde ocorre:** `frontend/app.js` (`abrirModalEdicaoFolha`, linhas 1598–1615) vs. `backend/folha_calculos.py` (linhas 998–1010).
- **Evidência:** O motor `folha_calculos.py` grava Horas Extras 50% com código `'101'`, Horas Extras 100% com código `'102'` e Adicional Noturno com código `'103'`, e grava todos os eventos do catálogo oficial (`0010` a `0552`) com `origem = 'calculado'`. Porém, ao abrir o modal de edição (`abrirModalEdicaoFolha`), o `frontend/app.js` lê `codigo_evento === '102'` como se fosse `noturno` (misturando HE 100% com adicional noturno), ignora o código `'103'` e descarta todos os eventos avulsos do catálogo porque filtra apenas `it.origem === 'manual'`. Se o usuário editar uma folha para corrigir uma inconsistência (Passo 7 da jornada), os eventos anteriores são perdidos no recálculo.

### Defeito D-05 (P1 — Divergência entre Handler Unificado e Handlers Serverless Isolados): `vercel.json` e `api/*.py`
- **Onde ocorre:** `vercel.json`, `api/auth/login.py`, `api/auth/logout.py`, `api/auth/me.py` e `api/colaboradores.py`.
- **Evidência:** Os arquivos `api/auth/login.py` e `api/colaboradores.py` reimplementam handlers HTTP separados de `backend/server.py`, omitindo a validação de CSRF (`CsrfProtector`) e o bloqueio de força bruta (`RateLimiter`), além de manter código duplicado. Já `api/index.py` herda diretamente de `ApiColaboradorHandler` (`backend/server.py`), que contém todas as rotas (`/api/health`, `/api/auth/*`, `/api/colaboradores*`, `/api/folha*`) com todas as proteções ativas.

### Defeito D-06 (P1 — Lacuna Funcional no Fluxo Ponta a Ponta): Dados da empresa estáticos e Parâmetros bloqueados na UI
- **Onde ocorre:** `frontend/index.html` (linhas 1130–1132 e 1273–1316) e `frontend/app.js` (`abrirModalParametros`, linhas 2303–2322).
- **Evidência:** O usuário não consegue configurar razão social, CNPJ e endereço da empresa (Passo 1 do fluxo de folha) nem editar os parâmetros de cálculo pela interface, pois os inputs do modal `#modal-parametros-folha` estão com atributo `readonly` e sem botão de submissão.
