# Correção da persistência e integração com PostgreSQL

Estado geral: **IMPLEMENTADO** (código) — **TESTADO parcialmente** (ver seção 6). Não está HOMOLOGADO.

## 1. Diagnóstico da causa raiz
- `backend/database.py` escolhia PostgreSQL só se encontrasse `DATABASE_URL` (ou equivalentes). Sem ela, caía **silenciosamente** em SQLite; na Vercel o arquivo ficava em `/tmp/colaboradores.db`, que não persiste entre execuções serverless.
- `frontend/app.js` mantinha um fallback em `localStorage` (`DP_COLABORADORES`) e a listagem engolia erros da API devolvendo lista vazia (aparência de "dados perdidos").
- Marcadores de conflito de merge em vários arquivos (inclusive `app.js`, `server.py`, `api/colaboradores.py`) — resolvidos no PR #2.
- O backend NestJS (`backend-nest`) já falhava explicitamente sem `DATABASE_URL`; não foi alterado nesse ponto.
- Não foi possível consultar a configuração real da Vercel/Supabase nem verificar se existem dados no SQLite temporário (sem acesso). **Não presumir dados perdidos**: verificar no Supabase antes de qualquer ação.

## 2. Alterações
| Arquivo | Alteração |
|---|---|
| `backend/database.py` | `DatabaseConfigError`/`DatabaseUnavailableError`; `em_producao()` (VERCEL, VERCEL_ENV, APP_ENV/ENVIRONMENT/NODE_ENV/ENV=production); sem `DATABASE_URL` em produção → erro explícito (sem fallback SQLite); `connect_timeout` (padrão 10s, `DB_CONNECT_TIMEOUT`) e `sslmode=require` para hosts remotos; falha de conexão vira erro sem host/credenciais; `status_banco()`; `erro_http()` (503 para banco indisponível). |
| `backend/server.py`, `api/colaboradores.py`, `api/auth/login.py`, `api/auth/me.py` | Erros de banco respondem **503** com mensagem clara (`BANCO_INDISPONIVEL`); novo `GET /api/health` (público, sem credenciais) confirma o banco em uso. |
| `frontend/app.js` | Removido o armazenamento local de colaboradores; todas as operações usam a API; falha de rede/503 gera erro visível e nada é simulado como salvo; a listagem não devolve mais lista vazia em erro. Formulários permanecem abertos com os dados digitados. |
| `tests/test_persistencia_postgres.py` | Novos testes (9) de configuração/falha. |

## 3. Configuração necessária (Vercel)
- `DATABASE_URL` (segredo, ambiente **Production**; usar a string do Supabase, preferencialmente o pooler em modo transação para serverless).
- Opcional: `DB_CONNECT_TIMEOUT` (segundos).
- `requirements.txt` já inclui `psycopg2-binary`.
- Nunca versionar credenciais.

## 4. Migração / dados existentes
Nenhuma migração foi executada e nenhum banco foi apagado/recriado. Antes de publicar: conferir no Supabase se as tabelas existem e se há registros; se houver dados em SQLite fora da Vercel, fazer backup e planejar migração.

## 5. Decisões e limitações
- SQLite continua permitido em desenvolvimento local e testes (`db_path` explícito).
- Commit/rollback: as operações do `ColaboradorService` fazem `commit()` ao final e fecham a conexão sem commit em falhas (o PostgreSQL descarta a transação). Não foi feita refatoração para `try/finally`/context manager em todos os métodos (pendência).
- Sessões e auditoria de autenticação já são gravadas no banco (tabelas `sessoes`, `auditoria_autenticacao`).

## 6. Testes e evidências
| Teste | Resultado |
|---|---|
| Suíte Python (`python -m unittest discover -s tests`) | 86 testes OK (inclui os 9 novos) |
| Produção sem `DATABASE_URL` → erro explícito | OK (teste automatizado) |
| Falha de conexão: 503/erro sem vazar credenciais e sem fallback SQLite (Teste E, com driver simulado) | OK (teste automatizado) |
| DSN com `sslmode=require` e `connect_timeout` | OK (teste automatizado) |
| Esquema PostgreSQL (DDL de `database.py`) em servidor PostgreSQL local: criação, unicidade de CPF, unicidade (colaborador, competência), FK folha→itens, `ON DELETE RESTRICT` colaborador→folha, `CASCADE` folha→itens (Teste F, parcial) | OK (via `psql`) |
| Dados persistem após reinício do servidor PostgreSQL local | OK |
| Frontend: JS válido; fluxo de salvar folha | verificado em navegador com API simulada |
| **Testes A–D (cadastro, outro navegador, redeploy, atualização) contra o Supabase/Vercel reais** | **NÃO EXECUTADOS** (sem acesso) |
| **Escrita/leitura real via `psycopg2`** | **NÃO EXECUTADA** (driver indisponível no ambiente de teste) |

## 7. Critérios de aceite
- [ ] PostgreSQL configurado em produção — **pendente (ação no painel da Vercel)**
- [ ] Aplicação confirma uso do PostgreSQL — **IMPLEMENTADO** (`GET /api/health`), falta verificar em produção
- [x] SQLite não é fallback em produção — IMPLEMENTADO e testado
- [x] Conflitos de merge resolvidos — IMPLEMENTADO (PR #2)
- [~] Módulos usam persistência centralizada — IMPLEMENTADO (Python); folha via NestJS usa o próprio `DatabaseService` (também PostgreSQL obrigatório)
- [ ] Testes de persistência A–D — **pendentes em produção**
- [~] Testes de integridade — TESTADO parcialmente (esquema no PostgreSQL local)
- [x] Testes de falha de conexão — TESTADO com driver simulado
- [ ] Sem perda após reinício/deploy — pendente em produção
- [ ] Sem erros críticos nos logs — não verificado
- [x] Documentação técnica — este arquivo

## 8. Riscos remanescentes
- Se a Vercel já operou sem `DATABASE_URL`, dados podem ter ido para `/tmp` e não são recuperáveis.
- Pooler/conexões em serverless: validar limites de conexão do Supabase sob carga.
- Executar os Testes A–D e o Teste F completo em produção/staging antes de homologar.
