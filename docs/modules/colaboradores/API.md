# Contratos de API REST — Módulo de Colaboradores (SPEC-03 & SPEC-03.1)

**Prefixo Global:** `/api`  
**Segurança:** Requer Cookie de Sessão `session_token` ou cabeçalho `Authorization: Bearer <token>`  
**Controle de Abrangência:** O backend infere a empresa autorizada a partir da sessão ativa. Usuários comuns não podem manipular a empresa alvo via parâmetros ou payloads.

---

## 1. Cadastrar Colaborador
- **Rota:** `POST /api/colaboradores`
- **Perfis Autorizados:** `administrador`, `analista_rh`
- **Código de Sucesso:** `201 Created`
- **Códigos de Erro:**
  * `400 Bad Request`: Dados inválidos (CPF inválido, campos obrigatórios ausentes, datas inconsistentes).
  * `403 Forbidden`: Usuário com escopo restrito tentando cadastrar para `empresaId` fora do seu escopo, ou perfil não autorizado (`operador_dp`).
  * `409 Conflict`: CPF ou Matrícula já existente dentro da mesma empresa.
- **Payload de Exemplo:**
```json
{
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
  "cargo": "Analista de TI",
  "setor": "Tecnologia",
  "salarioBase": 6500.0,
  "situacao": "ATIVO"
}
```

---

## 2. Listar Colaboradores (Paginado & Multiempresa)
- **Rota:** `GET /api/colaboradores`
- **Perfis Autorizados:** `administrador`, `analista_rh`, `operador_dp`
- **Query Parameters:** `page`, `limit`, `search`, `situacao`, `departamentoId`, `filialId`, `empresaId`
- **Regra de Segurança Multiempresa:**
  * Se o usuário possui escopo restrito a uma empresa, a consulta é **automaticamente restrita** àquela empresa.
  * Se o usuário tentar passar `?empresaId=` de uma organização que não lhe pertence, o backend retorna `HTTP 403 Forbidden` (`EMPRESA_NAO_AUTORIZADA`).
- **Código de Sucesso:** `200 OK`
- **Resposta Padrão:**
```json
{
  "sucesso": true,
  "total": 1,
  "dados": [
    {
      "id": 1,
      "empresa_id": "11111111-1111-1111-1111-111111111111",
      "matricula": "000123",
      "nome_completo": "João da Silva",
      "cpf_mascarado": "529.***.***-25",
      "setor": "Tecnologia",
      "cargo": "Analista de TI",
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

## 3. Visualizar Colaborador por ID (Proteção IDOR)
- **Rota:** `GET /api/colaboradores/:id`
- **Perfis Autorizados:** `administrador`, `analista_rh`, `operador_dp`
- **Regra de Segurança IDOR:** Se o colaborador existir mas pertencer a outra empresa para a qual o usuário não possui autorização, a API responde com **`HTTP 404 Not Found`** para evitar qualquer vazamento de informação inter-empresas.
- **Código de Sucesso:** `200 OK`

---

## 4. Atualizar Colaborador (PATCH)
- **Rota:** `PATCH /api/colaboradores/:id`
- **Perfis Autorizados:** `administrador`, `analista_rh`
- **Regras:**
  * Valida permissão sobre o ID (retorna 404 caso seja de outra organização).
  * Impede alteração ou transferência de `empresaId` para outra organização fora do escopo (retorna 403 Forbidden).
  * Preserva todos os campos omitidos na requisição.
  * Registra evento na tabela `historico_alteracoes`.
- **Código de Sucesso:** `200 OK`

---

## 5. Inativar Colaborador (Inativação Lógica)
- **Rota:** `PATCH /api/colaboradores/:id/inativar`
- **Perfis Autorizados:** `administrador`, `analista_rh`
- **Regras:**
  * Valida permissão sobre o ID (retorna 404 caso seja de outra organização).
  * Altera `situacao` para `inativo` sem apagar os dados físicos.
  * Preserva registros dependentes e históricos de auditoria.
- **Payload Opcional:** `{ "motivo": "string" }`
- **Código de Sucesso:** `200 OK`

---

## 6. Métricas Consolidadas
- **Rota:** `GET /api/colaboradores/metricas`
- **Perfis Autorizados:** `administrador`, `analista_rh`, `operador_dp`
- **Comportamento:** Retorna quantitativos de ativos, inativos, dependentes e distribuição por setor, filtrados pela abrangência do usuário.
- **Código de Sucesso:** `200 OK`
