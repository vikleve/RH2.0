# Plano e Execução de Testes — Módulo de Colaboradores (SPEC-03)

## 1. Estratégia de Testes

A validação de qualidade do SPEC-03 seguiu a pirâmide de testes corporativa:
- **Testes de Regras e Validadores**: Validação matemática de CPF (módulo 11) e checagem de formatos ISO de data.
- **Testes de Repositório e Consultas Parametrizadas**: Validação de cláusulas `LIMIT`, `OFFSET`, `ILIKE` e índices de busca.
- **Testes E2E (Supertest + Jest)**: Cobertura completa do ciclo de vida do colaborador em `backend-nest/test/colaboradores-spec03.e2e-spec.ts`.

---

## 2. Matriz de Cenários E2E Executados

| ID | Cenário de Teste | Método & Endpoint | Resposta Esperada | Status |
|---|---|---|---|:---:|
| **CT-01** | Bloqueio de acesso anônimo | `GET /api/colaboradores` | HTTP 401 Unauthorized | **PASS** |
| **CT-02** | Cadastro com payload completo SPEC-03 | `POST /api/colaboradores` | HTTP 201 Created | **PASS** |
| **CT-03** | Rejeição de CPF com dígitos inválidos | `POST /api/colaboradores` | HTTP 400 Bad Request | **PASS** |
| **CT-04** | Bloqueio de CPF duplicado na mesma empresa | `POST /api/colaboradores` | HTTP 409 Conflict | **PASS** |
| **CT-05** | Bloqueio de matrícula duplicada na empresa | `POST /api/colaboradores` | HTTP 409 Conflict | **PASS** |
| **CT-06** | Listagem paginada com CPF mascarado | `GET /api/colaboradores?page=1&limit=10` | HTTP 200 `{ data, meta }` | **PASS** |
| **CT-07** | Pesquisa textual por nome e matrícula | `GET /api/colaboradores?search=...` | HTTP 200 dados filtrados | **PASS** |
| **CT-08** | Filtro combinado de departamento e filial | `GET /api/colaboradores?dept=...&filial=...` | HTTP 200 dados filtrados | **PASS** |
| **CT-09** | Visualização completa de colaborador | `GET /api/colaboradores/:id` | HTTP 200 dados cadastrais | **PASS** |
| **CT-10** | Atualização parcial preservando campos | `PATCH /api/colaboradores/:id` | HTTP 200 dados atualizados | **PASS** |
| **CT-11** | Inativação lógica com confirmação | `PATCH /api/colaboradores/:id/inativar` | HTTP 200 situacao='inativo' | **PASS** |
