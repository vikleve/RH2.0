# RH2.0 — Critérios de Aceite do Módulo de Login & Autenticação Segura

**Projeto:** RH2.0 — Sistema Integrado de Departamento Pessoal & Folha de Pagamento  
**Data de Homologação:** 10 de Novembro de 2026  
**Status Consolidado:** 100% Aprovado em Ambas as Fases (Python Inicial + SPEC-02 NestJS/PostgreSQL)  

---

## 1. Critérios de Aceite de Segurança e Hardening (SPEC-02 — NestJS + PostgreSQL)

- [x] **SPEC02-RF-01 (CORS Seguro)**: `ALLOWED_ORIGINS` centralizado. Preflight OPTIONS e credenciais permitidos apenas para origens homologadas. Origens não autorizadas são bloqueadas sem cabeçalhos permissivos.
- [x] **SPEC02-RF-02 (PostgreSQL Fail-Fast)**: Em ambiente operacional, a ausência de `DATABASE_URL` impede imediatamente a inicialização. Conexão testada ativamente com `SELECT 1`. Falha em qualquer arquivo de migração interrompe a inicialização.
- [x] **SPEC02-RF-03 (Hashing de Token de Sessão)**: O token bruto trafega unicamente no cookie `HttpOnly; SameSite=Lax`. O banco de dados armazena exclusivamente o hash SHA-256 do token na tabela `sessoes`. Sessões anteriores do usuário são revogadas no login.
- [x] **SPEC02-RF-04 (Proteção CSRF Rigorosa)**: Validação estrita de cabeçalhos `Origin`, `Referer` e `Sec-Fetch-Site` para todas as requisições mutativas (`POST`, `PUT`, `PATCH`, `DELETE`). Requisições com origens não autorizadas retornam HTTP 403 Forbidden (`ORIGEM_PROIBIDA`).
- [x] **SPEC02-RF-05 (Rate Limiting Ativo)**: Bloqueio na 6ª tentativa consecutiva após 5 falhas no intervalo de 15 minutos (900s), retornando HTTP 429 Too Many Requests com cabeçalho `Retry-After`.
- [x] **SPEC02-RF-06 (Auditoria de Eventos)**: Registro em banco na tabela `auditoria_autenticacao` para eventos `LOGIN_SUCESSO`, `LOGIN_FALHA`, `LOGOUT` e `BLOQUEIO_RATE_LIMIT`, com higienização estrita de dados sensíveis.
- [x] **SPEC02-RF-07 (Validação Global de Entrada)**: `ValidationPipe` do NestJS com DTOs tipados (`LoginDto`, `CreateColaboradorDto`, `UpdateColaboradorDto`) rejeitando propriedades desconhecidas (`forbidNonWhitelisted: true`) com HTTP 400.
- [x] **SPEC02-RF-08 (Governança de Variáveis de Ambiente)**: `.env.example` completo e documentado na raiz e no backend NestJS.
- [x] **SPEC02-RF-09 (RBAC / Roles)**: `RolesGuard` e decorator `@Roles()` implementados para autorização por perfil (`administrador`, `analista_rh`, `operador_dp`).

---

## 2. Matriz Rastreabilidade: Critério → Teste E2E (NestJS) → Status

| ID Requisito | Método / Teste Executado no NestJS | Resultado Observado | Status |
|---|---|---|:---:|
| **RF-01** | `auth.e2e-spec.ts` (Preflight OPTIONS & Whitelist) | Preflight 204 com headers para localhost:3000; sem allow-origin para domínios maliciosos | **PASS** |
| **RF-02** | `auth.e2e-spec.ts` (DatabaseService Fail-Fast) | Exceção crítica lançada no bootstrap quando `DATABASE_URL` ausente fora de teste | **PASS** |
| **RF-03** | `auth.e2e-spec.ts` (Session Token Hashing SHA-256) | Token na tabela `sessoes` equivale a `sha256(rawToken)`; token em texto puro ausente do banco | **PASS** |
| **RF-04** | `auth.e2e-spec.ts` (CsrfGuard Cross-Origin Block) | HTTP 403 Forbidden com código `ORIGEM_PROIBIDA` para origens externas | **PASS** |
| **RF-05** | `auth.e2e-spec.ts` (Rate Limiter 5 Tentativas / 15 min) | 6ª tentativa retorna HTTP 429 com cabeçalho `Retry-After` numérico | **PASS** |
| **RF-06** | `auth.e2e-spec.ts` (Auditoria e Ausência de Senhas) | Eventos gravados em `auditoria_autenticacao` sem senhas, tokens ou segredos | **PASS** |
| **RF-07** | `auth.e2e-spec.ts` (ValidationPipe & DTOs) | HTTP 400 Bad Request ao enviar campos extras ou payload vazio | **PASS** |
| **AC-05** | `auth.e2e-spec.ts` (Login Válido) | HTTP 200 OK com cookie `session_token` (HttpOnly, SameSite=Lax) | **PASS** |
| **AC-06** | `auth.e2e-spec.ts` (Mensagem Genérica Uniforme) | HTTP 401 com `"E-mail ou senha inválidos."` para conta inexistente, inativa ou senha errada | **PASS** |
| **AC-10** | `auth.e2e-spec.ts` (Persistência `/api/auth/me`) | HTTP 200 OK mantendo sessão autenticada com cookie | **PASS** |
| **AC-11** | `auth.e2e-spec.ts` (Proteção de Rotas Privadas) | HTTP 401 Unauthorized para acessos anônimos em `/api/colaboradores` | **PASS** |
| **AC-12** | `auth.e2e-spec.ts` (Logout com Revogação) | HTTP 200 OK, cookie limpo; reuso do token rejeitado com HTTP 401 | **PASS** |
| **EPIC-C** | `colaboradores-folha.e2e-spec.ts` (10 testes) | CRUD, CPF, histórico, inativação, métricas, cálculo folha CLT, fechamento e reabertura | **PASS** |
