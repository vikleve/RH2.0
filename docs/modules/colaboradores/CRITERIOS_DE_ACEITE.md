# Critérios de Aceite — Módulo de Colaboradores (SPEC-03 & SPEC-03.1)

**Projeto:** RH2.0  
**Data:** 10 de Novembro de 2026  
**Status Oficial:** IMPLEMENTADO — TESTADO — AGUARDANDO HOMOLOGAÇÃO  

---

## 1. Critérios de Aceite Fundamentais (SPEC-03)

- [x] **CA-01 (Backend NestJS)**: Arquitetura oficial modular implementada com `ColaboradoresController`, `ColaboradoresService` e `ColaboradoresRepository`.
- [x] **CA-02 (Frontend React + TypeScript)**: Interface completa em `frontend-react` com listagem, busca, filtros, paginação e modais estruturados em 4 seções.
- [x] **CA-03 (PostgreSQL Operacional)**: Migração `004_modulo_colaboradores_spec03.sql` aplicada com colunas de segregação multi-empresa e índices de busca.
- [x] **CA-04 (Cadastro Funcional)**: `POST /api/colaboradores` retorna HTTP 201 com dados criados e validação rigorosa.
- [x] **CA-05 (Listagem Paginada)**: `GET /api/colaboradores` retorna estrutura oficial `{ data: [], meta: { page, limit, total, totalPages } }`.
- [x] **CA-06 (Pesquisa Textual)**: Suporte a busca no backend por nome, CPF e matrícula.
- [x] **CA-07 (Filtros Combináveis)**: Filtros por situação (`ATIVO`/`INATIVO`), departamento e filial operando simultaneamente.
- [x] **CA-08 (Visualização Completa)**: `GET /api/colaboradores/:id` retorna dados cadastrais e dependentes com HTTP 200.
- [x] **CA-09 (Edição com Preservação)**: `PATCH /api/colaboradores/:id` atualiza dados cadastrais, preserva campos não enviados e registra histórico.
- [x] **CA-10 (Inativação Lógica)**: `PATCH /api/colaboradores/:id/inativar` altera a situação para `INATIVO` sem apagar registros ou violar integridade referencial.
- [x] **CA-11 (Validação de CPF)**: Algoritmo dos dígitos verificadores ativo; rejeição de CPF inválido com HTTP 400.
- [x] **CA-12 (Bloqueio de Duplicidade)**: Rejeição de CPF e matrícula duplicados dentro da mesma empresa com HTTP 409 Conflict.
- [x] **CA-13 (Privacidade de Dados)**: CPF mascarado (`123.***.***-09`) nas listagens públicas.
- [x] **CA-14 (Segurança & RBAC)**: Proteção por autenticação centralizada (`SessionGuard`) e autorização por perfil (`RolesGuard`).
- [x] **CA-15 (Auditoria Integral)**: Eventos de `CADASTRO`, `ALTERACAO` e `INATIVACAO` registrados na tabela `historico_alteracoes`.
- [x] **CA-16 (Suíte de Testes Base)**: Testes E2E dedicados ao SPEC-03 aprovados.

---

## 2. Critérios de Aceite de Segurança Multiempresa & Homologação (SPEC-03.1)

- [x] **CA-17 (Contexto de Sessão Multiempresa)**: A abrangência do usuário é derivada com base nos atributos autenticados (`empresa_id` e `empresas_autorizadas`) providos pelo `SessionGuard`.
- [x] **CA-18 (Proteção de Escopo na Listagem)**: Usuário comum não pode ampliar seu escopo informando `?empresaId=` de outra empresa (retorno HTTP 403 Forbidden). A listagem sem parâmetro filtra estritamente pela sua própria empresa.
- [x] **CA-19 (Proteção contra IDOR em Leitura)**: `GET /api/colaboradores/:id` retorna HTTP 404 Not Found para colaboradores pertencentes a empresas fora da abrangência do usuário, impedindo reconhecimento e enumeração.
- [x] **CA-20 (Proteção contra IDOR em Mutação)**: `PATCH /api/colaboradores/:id` e `PATCH /api/colaboradores/:id/inativar` retornam HTTP 404 Not Found para requisições direcionadas a registros fora da abrangência.
- [x] **CA-21 (Bloqueio de Injeção de Empresa no Payload)**: Tentativa de injetar `empresaId` não autorizada no corpo de `POST /api/colaboradores` ou tentar transferir organização no `PATCH` resulta em HTTP 403 Forbidden.
- [x] **CA-22 (Migração Segura 005)**: Migração `005_seguranca_multiempresa.sql` versionada e integrada sem quebra de dados nem estruturas legadas.
- [x] **CA-23 (Cobertura de Testes de Regressão)**: 20 testes unitários + 47 testes E2E executados com 100% de sucesso nas 4 suítes (`auth`, `folha`, `spec03`, `multiempresa-spec03-1`).
- [x] **CA-24 (Compilação Frontend & Backend)**: TypeScript sem erros de tipos no frontend (`tsc --noEmit`) e no backend NestJS.
