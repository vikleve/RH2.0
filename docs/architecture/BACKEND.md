# Arquitetura do Backend RH2.0 — NestJS + PostgreSQL

## 1. Visão Geral

O backend oficial do **RH2.0** é construído sobre a plataforma **Node.js (LTS v26)** utilizando o framework corporativo modular **NestJS**, persistência primária e relacional em **PostgreSQL** (com suporte a conexões seguras SSL para provedores de nuvem como Supabase) e comunicação estrita via **API REST** sob o prefixo `/api`.

```
                  ┌────────────────────────────────────────┐
                  │          Frontend React (SPA)          │
                  └──────────────────┬─────────────────────┘
                                     │ HTTPS / Cookies HttpOnly / Bearer
                                     ▼
       ┌──────────────────────────────────────────────────────────────┐
       │                 API Gateway / NestJS Server                  │
       │  ┌────────────────────────────────────────────────────────┐  │
       │  │ CORS Guard (ALLOWED_ORIGINS Whitelist)                  │  │
       │  │ CSRF Guard (Origin / Referer / Sec-Fetch-Site Check)   │  │
       │  │ Global ValidationPipe (class-validator & DTOs)         │  │
       │  │ RateLimiterService (5 tentativas / 15 min / 429)       │  │
       │  └────────────────────────────────────────────────────────┘  │
       │  ┌───────────────┬─────────────────┬──────────────────────┐  │
       │  │ AuthModule    │ Colaboradores   │ Folha Pagamento      │  │
       │  │ (SessionGuard,│ (CRUD, History, │ (CLT Engine, DSR,    │  │
       │  │  RolesGuard)  │  Validações CPF)│  INSS/IRRF, Fech.)   │  │
       │  └───────┬───────┴────────┬────────┴──────────┬───────────┘  │
       │          │                │                   │              │
       │          ▼                ▼                   ▼              │
       │  ┌────────────────────────────────────────────────────────┐  │
       │  │ DatabaseService (PostgreSQL Pool / Fail-fast Startup)  │  │
       │  └────────────────────────────────────────────────────────┘  │
       └─────────────────────────────┬────────────────────────────────┘
                                     │ Connection Pool (pg)
                                     ▼
                  ┌────────────────────────────────────────┐
                  │         PostgreSQL Operacional         │
                  │ (sessoes, usuarios, auditoria,         │
                  │  colaboradores, folhas, itens)         │
                  └────────────────────────────────────────┘
```

---

## 2. Padrões de Segurança e Hardening (SPEC-02)

### RF-01: CORS Restritivo
- **Lista de Origens Permitidas**: O backend lê a variável de ambiente `ALLOWED_ORIGINS` (ex: `http://localhost:3000,http://localhost:5173`).
- **Bloqueio de Origens Desconhecidas**: Origens não cadastradas são rejeitadas sem emissão do cabeçalho `Access-Control-Allow-Origin`.
- **Credenciais**: `credentials: true` opera exclusivamente com origens explicitamente autorizadas.

### RF-02: Inicialização Segura do PostgreSQL (Fail-Fast)
- **Obrigatoriedade Operacional**: Fora do ambiente de testes (`NODE_ENV !== 'test'` e `TESTING !== '1'`), a ausência de `DATABASE_URL` interrompe imediatamente o bootstrap da aplicação.
- **Validação de Conectividade**: Um teste ativo `SELECT 1` é executado na inicialização. Em caso de indisponibilidade do banco, a aplicação aborta com erro explícito.
- **Execução Controlada de Migrações**: Migrações obrigatórias (`001_schema_inicial.sql`, `002_modulo_folha_pagamento.sql`, `003_auditoria_autenticacao.sql`) são aplicadas no boot; qualquer erro sintático ou de execução aborta a inicialização, impedindo operação com banco inconsistente.
- **Mascaramento em Logs**: A connection string tem sua credencial mascarada nos logs (`replace(/:([^:@]+)@/, ':****@')`).

### RF-03: Sessões Criptográficas com Hashing de Token
- **Tokens**: 32 bytes (256 bits) gerados com `crypto.randomBytes(32).toString('hex')`.
- **Armazenamento no Banco**: O banco de dados armazena **estritamente o Hash SHA-256** do token (`crypto.createHash('sha256').update(token).digest('hex')`). Em eventual vazamento da tabela `sessoes`, os tokens de sessão ativos não são comprometidos.
- **Cookies**: Transmitidos com `HttpOnly`, `SameSite=Lax` e `Secure` (quando HTTPS ativo).
- **Regeneração de Sessão**: A cada login válido, sessões anteriores do mesmo usuário são marcadas como `revogado = 1`.

### RF-04: Proteção CSRF
- **Métodos Mutativos**: Requisições `POST`, `PUT`, `PATCH`, `DELETE` têm seus cabeçalhos `Origin`, `Referer` e `Sec-Fetch-Site` avaliados pelo `CsrfGuard`.
- **Bloqueio**: Requisições cross-site de origens não autorizadas são bloqueadas com HTTP 403 Forbidden (`ORIGEM_PROIBIDA`).

### RF-05: Rate Limiting
- **Janela**: 5 tentativas incorretas por IP em 15 minutos (900 segundos).
- **Bloqueio**: Retorna HTTP 429 Too Many Requests com cabeçalho `Retry-After`.
- **Limpeza**: Autenticação com sucesso limpa as falhas registradas para o IP.

### RF-06: Auditoria Contínua
- **Tabela**: `auditoria_autenticacao`.
- **Eventos Registrados**: `LOGIN_SUCESSO`, `LOGIN_FALHA`, `LOGOUT`, `BLOQUEIO_RATE_LIMIT`.
- **Sanitização**: Senhas, hashes e dados sensíveis são rigorosamente expurgados dos registros de auditoria.

### RF-07: Validação Estrita de Entrada
- **Pipes Globais**: `ValidationPipe` com `{ whitelist: true, forbidNonWhitelisted: true, transform: true }`.
- **DTOs**: `LoginDto`, `CreateColaboradorDto`, `UpdateColaboradorDto`. Payloads com campos extras ou maliciosos são rejeitados com HTTP 400 Bad Request.

---

## 3. Estrutura Modular

```
backend-nest/src/
├── app.module.ts              # Módulo raiz importando todos os submódulos
├── main.ts                    # Bootstrap com CORS, Pipes globais e Security Headers
├── cors.config.ts             # Configuração e validação de origens CORS
├── database/
│   ├── database.module.ts     # Módulo de banco exportando DatabaseService
│   └── database.service.ts    # Conexão Pool pg, migrações e fail-fast
└── modules/
    ├── audit/                 # Auditoria de eventos de autenticação
    ├── auth/                  # Autenticação, Hashing, Sessões, Guards e RBAC
    │   ├── dto/login.dto.ts
    │   ├── roles/             # Decorator e Guard de perfis
    │   ├── auth.controller.ts
    │   ├── auth.service.ts
    │   └── session.guard.ts
    ├── colaboradores/         # Gestão de colaboradores, validação de CPF e histórico
    ├── csrf/                  # CsrfGuard
    ├── folha/                 # Motor de cálculo CLT, INSS, IRRF, fechamento e reabertura
    └── rate-limiter/          # RateLimiterService em memória com expiração
```

