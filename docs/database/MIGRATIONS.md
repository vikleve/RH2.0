# Guia de Migrações do Banco de Dados PostgreSQL — RH2.0

## 1. Visão Geral

As migrações do banco de dados do RH2.0 residem no diretório `/migrations` e são gerenciadas de forma idempotente e segura durante o ciclo de inicialização do backend NestJS.

```
migrations/
├── 001_schema_inicial.sql            # Tabelas base: colaboradores, dependentes, histórico, usuários, sessões
├── 002_modulo_folha_pagamento.sql    # Parâmetros de cálculo, folhas, folha_itens, folha_historico
└── 003_auditoria_autenticacao.sql    # Tabela auditoria_autenticacao para eventos de segurança
```

---

## 2. Ordem de Execução e Dependências

1. **`001_schema_inicial.sql`**:
   - Criação das tabelas centrais: `colaboradores`, `dependentes`, `historico_alteracoes`, `usuarios`, `sessoes`.
   - Índices de unicidade para `matricula` e `cpf`.
   - Habilitação de Row-Level Security (RLS).
   - Definição da tabela `sessoes` com `token TEXT PRIMARY KEY` (armazenando o hash SHA-256 do token).

2. **`002_modulo_folha_pagamento.sql`**:
   - Criação das tabelas de negócio da folha: `folha_parametros`, `folhas_pagamento`, `folha_itens`, `folha_historico`.
   - Regra de integridade: unicidade `(colaborador_id, competencia)` para evitar duplicidade de folhas no mesmo período.
   - Parâmetro inicial de cálculo CLT padrão 2026.

3. **`003_auditoria_autenticacao.sql`**:
   - Criação da tabela `auditoria_autenticacao`:
     - `id SERIAL PRIMARY KEY`
     - `evento TEXT NOT NULL` (`LOGIN_SUCESSO`, `LOGIN_FALHA`, `LOGOUT`, `BLOQUEIO_RATE_LIMIT`)
     - `identificador TEXT NOT NULL`
     - `ip_origem TEXT NOT NULL`
     - `detalhes TEXT`
     - `criado_em TEXT NOT NULL`
   - Índices em `evento`, `identificador` e `criado_em`.

---

## 3. Diretrizes de Governança de Migrações

- **Transacionalidade**: Migrações devem ser executadas com suporte transacional (`BEGIN` / `COMMIT`).
- **Fail-Fast**: Se qualquer arquivo de migração falhar na execução, a aplicação interrompe imediatamente o bootstrap, garantindo que o sistema não inicie em estado de schema incompleto ou corrompido.
- **Ambiente de Testes (`pg-mem`)**: Durante a execução da suíte de testes sintéticos isolados, comandos específicos de infraestrutura de nuvem (como RLS policies ativas do PostgreSQL) são sanados dinamicamente para preservar total fidelidade lógica dos testes unitários e de integração sem necessitar de banco externo ligado.
