# Plano e Execução de Testes — Módulo de Colaboradores (SPEC-03 & SPEC-03.1)

## 1. Estratégia de Testes

A validação de qualidade do SPEC-03.1 consolida a pirâmide de testes corporativa:
- **Testes Unitários de Regras e Validadores**: Validação matemática de CPF (módulo 11), validação de formatos ISO de data, normalização, mascaramento e controle de escopo.
- **Testes de Integração e Repositório**: Consultas parametrizadas com filtros combinados, métricas por empresa e prevenção de SQL Injection.
- **Testes E2E Multiempresa (SPEC-03.1)**: Suíte dedicada `backend-nest/test/colaboradores-multiempresa-spec03-1.e2e-spec.ts` validando cenários de segurança e IDOR.
- **Testes E2E de Regressão**: Validação completa dos módulos de Autenticação (`auth.e2e-spec.ts`), Folha de Pagamento (`colaboradores-folha.e2e-spec.ts`) e Colaboradores Base (`colaboradores-spec03.e2e-spec.ts`).

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
| **CT-12** | Consulta isolada da própria empresa | `GET /api/colaboradores` | HTTP 200 (somente empresa 1) | **PASS** |
| **CT-13** | Bloqueio de consulta a outra empresa via filtro | `GET /api/colaboradores?empresaId=...` | HTTP 403 Forbidden | **PASS** |
| **CT-14** | Proteção IDOR em consulta por ID de outra empresa | `GET /api/colaboradores/:idEmpresa2` | HTTP 404 Not Found | **PASS** |
| **CT-15** | Proteção IDOR em edição de colaborador alheio | `PATCH /api/colaboradores/:idEmpresa2` | HTTP 404 Not Found | **PASS** |
| **CT-16** | Proteção IDOR em inativação de colaborador alheio | `PATCH /api/colaboradores/:idEmpresa2/inativar` | HTTP 404 Not Found | **PASS** |
| **CT-17** | Bloqueio de injeção de empresaId no cadastro | `POST /api/colaboradores` | HTTP 403 Forbidden | **PASS** |
| **CT-18** | Bloqueio de transferência indevida de empresa | `PATCH /api/colaboradores/:id` | HTTP 403 Forbidden | **PASS** |
| **CT-19** | Bloqueio de ampliação de escopo por filtros | `GET /api/colaboradores?empresaId=...&situacao=...` | HTTP 403 Forbidden | **PASS** |
| **CT-20** | RBAC: Bloqueio de cadastro por operador_dp | `POST /api/colaboradores` | HTTP 403 Forbidden | **PASS** |
| **CT-21** | RBAC: Bloqueio de inativação por operador_dp | `PATCH /api/colaboradores/:id/inativar` | HTTP 403 Forbidden | **PASS** |

---

## 3. Comandos de Reprodução dos Testes

```bash
# Executar todos os testes unitários (20 testes)
npm test

# Executar todas as 4 suítes de testes E2E e regressão (47 testes)
npm run test:e2e
```
