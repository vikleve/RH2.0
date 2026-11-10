# Contratos de API REST — Módulo de Colaboradores (SPEC-03)

**Prefixo Global:** `/api`  
**Segurança:** Requer Cookie de Sessão `session_token` ou cabeçalho `Authorization: Bearer <token>`  

---

## 1. Cadastrar Colaborador
- **Rota:** `POST /api/colaboradores`
- **Código de Sucesso:** `201 Created`
- **Payload de Exemplo:**
```json
{
  "empresaId": "a0000000-0000-0000-0000-000000000001",
  "filialId": "b1111111-1111-1111-1111-111111111111",
  "matricula": "000123",
  "nomeCompleto": "João da Silva",
  "cpf": "52998224725",
  "dataNascimento": "1995-05-20",
  "sexo": "MASCULINO",
  "estadoCivil": "SOLTEIRO",
  "email": "joao@empresa.com.br",
  "telefone": "11999999999",
  "departamentoId": "d3333333-3333-3333-3333-333333333333",
  "cargoId": "cargo-analista-ti",
  "situacao": "ATIVO"
}
```

---

## 2. Listar Colaboradores (Paginado)
- **Rota:** `GET /api/colaboradores`
- **Query Parameters:** `page`, `limit`, `search`, `situacao`, `departamentoId`, `filialId`
- **Código de Sucesso:** `200 OK`
- **Resposta Padrão:**
```json
{
  "data": [
    {
      "id": 1,
      "matricula": "000123",
      "nome_completo": "João da Silva",
      "cpf_mascarado": "529.***.***-25",
      "setor": "Tecnologia",
      "cargo": "Analista",
      "situacao": "ativo"
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 1,
    "totalPages": 1
  }
}
```

---

## 3. Consultar Detalhes
- **Rota:** `GET /api/colaboradores/:id`
- **Código de Sucesso:** `200 OK`

---

## 4. Atualizar Colaborador
- **Rota:** `PATCH /api/colaboradores/:id`
- **Código de Sucesso:** `200 OK`

---

## 5. Inativar Colaborador
- **Rota:** `PATCH /api/colaboradores/:id/inativar`
- **Código de Sucesso:** `200 OK`
- **Payload:** `{ "motivo": "Justificativa opcional da inativação" }`
