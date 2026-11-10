# Relatório de Evidências — Módulo de Colaboradores (SPEC-03)

**Projeto:** RH2.0 — Sistema Integrado de Departamento Pessoal & Folha de Pagamento  
**Data:** 10 de Novembro de 2026  
**Quality Gate:** SPEC-03 Homologado  

---

## 1. Evidências da Execução de Testes Automatizados E2E

Execução consolidada via `npm run test:e2e`:

```text
PASS test/colaboradores-spec03.e2e-spec.ts (6.642 s)
  Módulo de Cadastro de Colaboradores — SPEC-03 (NestJS E2E)
    √ RF-10: Bloqueia acesso a endpoints de colaboradores sem autenticação (401) (7 ms)
    √ RF-04 & Seção 6.1: Cadastra novo colaborador com payload oficial SPEC-03 (201) (36 ms)
    √ RF-07: Rejeita cadastro com CPF inválido (400 Bad Request) (9 ms)
    √ RF-07: Bloqueia cadastro com CPF duplicado dentro da mesma empresa (409 Conflict) (9 ms)
    √ RF-08: Bloqueia cadastro com Matrícula duplicada dentro da mesma empresa (409 Conflict) (8 ms)
    √ RF-01 & Seção 6.2: Retorna listagem paginada com metadados e CPF mascarado (53 ms)
    √ RF-02: Pesquisa colaboradores por termo no backend (search) (43 ms)
    √ RF-03: Filtra colaboradores por departamento e filial (16 ms)
    √ RF-05 & Seção 6.3: Consulta detalhes completos de um colaborador (200 OK) (8 ms)
    √ RF-06 & Seção 6.4: Atualiza dados cadastrais e preserva campos não enviados (PATCH 200) (22 ms)
    √ RF-09 & Seção 6.5: Inativa colaborador logicamente com histórico e confirmação (PATCH 200) (20 ms)

PASS test/colaboradores-folha.e2e-spec.ts (6.697 s)
  Colaboradores e Folha de Pagamento RH2.0 (NestJS E2E)
    √ 1. Deve cadastrar um colaborador com sucesso (POST /api/colaboradores) (43 ms)
    √ 2. Deve rejeitar colaborador com CPF duplicado (409 Conflict) (7 ms)
    √ 3. Deve listar colaboradores com busca e filtros (GET /api/colaboradores) (13 ms)
    √ 4. Deve atualizar dados e registrar histórico de auditoria (PUT /api/colaboradores/:id) (33 ms)
    √ 5. Deve inativar e reativar logicamente colaborador (PATCH) (22 ms)
    √ 6. Deve consultar métricas agregadas (GET /api/colaboradores/metricas) (13 ms)
    √ 7. Deve calcular folha com horas extras e encargos CLT (POST /api/folha) (44 ms)
    √ 8. Deve fechar a folha e bloquear recálculos indevidos (POST /api/folha/:id/fechar) (18 ms)
    √ 9. Deve reabrir a folha mediante justificativa obrigatória (POST /api/folha/:id/reabrir) (22 ms)
    √ 10. Deve cancelar a folha com sucesso (DELETE /api/folha/:id) (20 ms)

PASS test/auth.e2e-spec.ts (6.837 s)
  Auth & Segurança RH2.0 — SPEC-02 (NestJS E2E)
    √ RF-07 / AC-04: Rejeita login com campos vazios ou inválidos com HTTP 400 (42 ms)
    √ RF-07: Rejeita login com propriedades não autorizadas (forbidNonWhitelisted) (5 ms)
    √ RF-01: Permite requisições preflight OPTIONS e cabeçalhos CORS para origens autorizadas (3 ms)
    √ RF-01: Bloqueia cabeçalhos CORS para origens não autorizadas (3 ms)
    √ RF-03 / AC-05: Login válido cria sessão, emite cookie HttpOnly e retorna dados (66 ms)
    √ RF-03: Token de sessão é persistido no banco como Hash SHA-256 e não em texto puro (57 ms)
    √ AC-06: Rejeita usuário inexistente e senha incorreta com a mesma mensagem genérica (60 ms)
    √ RF-03: Usuário inativo é rejeitado com a mesma mensagem genérica sem vazar status (17 ms)
    √ RF-05 / AC-07: Bloqueia na 6ª tentativa consecutiva com HTTP 429 e Retry-After (39 ms)
    √ AC-08: Senhas armazenadas como PBKDF2 com salt de 16 bytes e sem texto puro (3 ms)
    √ AC-10: /api/auth/me mantém autenticação usando o cookie de sessão (66 ms)
    √ AC-11: Endpoints privados bloqueiam requisições anônimas com HTTP 401 (3 ms)
    √ AC-12: Logout revoga sessão e limpa cookie; reuso retorna 401 (78 ms)
    √ RF-04 / AC-13: Rejeita POST com Origin não autorizado com HTTP 403 Forbidden (3 ms)
    √ RF-06 / AC-16: Tabela auditoria_autenticacao registra eventos sem senhas ou segredos (5 ms)
    √ RF-02: DatabaseService rejeita inicialização sem DATABASE_URL fora do ambiente de testes (19 ms)

Test Suites: 3 passed, 3 total
Tests:       37 passed, 37 total
Snapshots:   0 total
Time:        7.932 s
```

---

## 2. Evidência de Compilação do Backend (Build TypeScript)

- **Comando:** `npm run build`
- **Resultado:** Código de saída 0, sem erros ou advertências.
