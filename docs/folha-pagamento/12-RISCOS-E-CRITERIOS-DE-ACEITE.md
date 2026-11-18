# 12 — Riscos, Governança e Critérios Globais de Aceite

**Projeto:** RH2.0 — Portal de Departamento Pessoal & Folha de Pagamento  
**Data:** 18/11/2026

---

## 1. Matriz de Riscos e Mitigações

| ID | Risco Identificado | Severidade | Mitigação Técnica Planejada |
|---|---|:---:|---|
| **R-01** | Falha de serialização JSON (`Decimal`) ao trocar de SQLite (testes) para PostgreSQL/Neon (produção). | **Alta** | Microetapa `M01` converte `Decimal` de forma determinística em `row_to_dict` e `_enviar_json`, validada com teste automatizado simulando retorno `Decimal` do `psycopg2`. |
| **R-02** | Contenção de conexões ou lentidão em cold start serverless no Neon devido a `init_db()` repetitivo. | **Alta** | Microetapa `M02` introduz controle `_INITIALIZED_TARGETS` em memória por instância e tabela `schema_migrations`, além de usar a connection string `-pooler` com `DB_CONNECT_TIMEOUT=15`. |
| **R-03** | Perda silenciosa de eventos ao editar uma folha existente na interface. | **Alta** | Microetapa `M07` corrige o mapeamento de códigos `101`, `102`, `103`, `201`, `202` e recarrega todas as rubricas lançadas pelo usuário em `abrirModalEdicaoFolha`. |
| **R-04** | Divergência entre os handlers isolados `api/*.py` e o servidor principal `backend/server.py`. | **Média** | Microetapa `M04` unifica todos os entrypoints de `api/` para herdarem diretamente de `ApiColaboradorHandler`. |
| **R-05** | Exposição acidental de credenciais do Neon ou senhas em logs, respostas de erro ou commits. | **Alta** | `.gitignore` bloqueia `.env`; `DatabaseUnavailableError` suprime DSN/host/senha em falhas de conexão (`CA-NEON-04` testado); variáveis cadastradas como *Sensitive* na Vercel. |
| **R-06** | Interpretação equivocada do fechamento interno como transmissão oficial ao eSocial/bancos. | **Média** | Documentação explícita (`06-ESCOPO-E-REGRAS-DE-FOLHA.md`) e avisos claros na interface de fechamento e parâmetros. |

---

## 2. Checklist dos Critérios Globais de Conclusão (Seção 19: A a M)

O sistema somente receberá o aceite operacional final após a execução das microetapas `M01` a `M10` quando todos os 13 critérios objetivos abaixo estiverem comprovados com evidências:

- [ ] **A. Reaproveitamento:** Código Python (`backend/`, `api/`) e Vanilla JS (`frontend/`) dos alunos integralmente preservado e evoluído com intervenção mínima.
- [ ] **B. Funcionalidades:** Jornada completa de 10 passos da folha (empresa/parâmetros, colaboradores, competência, eventos, cálculo, conferência, correção/recálculo, fechamento, demonstrativos e histórico) funcional.
- [ ] **C. Banco de Dados:** Neon PostgreSQL configurado e confirmado via `GET /api/health` (`"banco": "postgresql", "provedor": "neon", "conectado": true`).
- [ ] **D. Persistência:** Cadastros, dependentes, parâmetros, folhas, itens, fechamentos e auditorias gravados e recuperados do Neon (Testes `DB-01` a `DB-05`, `DB-12`, `DB-13`).
- [ ] **E. Integridade:** Transações com `commit`/`rollback` atômicos, chaves estrangeiras (`CASCADE`/`RESTRICT`) e unicidade `(colaborador_id, competencia)` verificadas (Testes `DB-09`, `DB-10`).
- [ ] **F. Cálculos:** Motor matemático de 82 eventos com `Decimal` (`ROUND_HALF_UP`), INSS e IRRF progressivos e memória de cálculo auditável com 100% dos testes passando.
- [ ] **G. Interface:** Fluxo guiado compreensível para usuário não técnico, com prévia fiel, geração/fechamento de competência e mensagens honestas.
- [ ] **H. Hospedagem:** Aplicação funcional na Vercel (Frontend Estático + Serverless Functions Python).
- [ ] **I. Integração:** Fluxo `INTERFACE → API → VALIDAÇÃO → NEON POSTGRESQL → RESPOSTA → UI` operando ponta a ponta sem simulações locais.
- [ ] **J. Segurança:** Senhas com PBKDF2-HMAC-SHA256, cookies `HttpOnly`, proteção CSRF, Rate Limiting, RBAC por perfil e zero exposição de credenciais no navegador (Teste `DB-14`).
- [ ] **K. Histórico e Durabilidade:** Dados permanecem disponíveis após reinicialização do processo, logout/login e redeploy na Vercel (Testes `DB-06`, `DB-07`, `DB-08`).
- [ ] **L. Documentação:** Todos os 12 documentos canônicos mantidos e atualizados em `docs/folha-pagamento/`.
- [ ] **M. Conformidade e Limites:** Regras CLT/INSS/IRRF/FGTS do escopo verificadas e exclusões (eSocial, ponto eletrônico, pagamento bancário) claramente declaradas.
