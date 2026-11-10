# Especificação Técnica — Módulo de Cadastro de Colaboradores (SPEC-03.1)

**Projeto:** RH2.0 — Plataforma Integrada de Gestão do Ciclo Trabalhista  
**Versão:** 3.1 — Correção de Conformidade, Segurança Multiempresa e Homologação  
**Stack Oficial:** React + TypeScript | NestJS (Node.js LTS v26) | PostgreSQL  
**Status:** IMPLEMENTADO — TESTADO — AGUARDANDO HOMOLOGAÇÃO  

---

## 1. Visão Geral e Contexto de Conformidade

O módulo de Cadastro de Colaboradores do **RH2.0** foi aprimorado para atender plenamente às diretrizes de conformidade e segurança da auditoria corporativa (SPEC-03.1). Esta especificação complementa a implementação inicial garantindo isolamento estrito multiempresa, proteção contra referências diretas a objetos inseguros (IDOR), controle de acesso baseado em papéis (RBAC) e rastreabilidade total de operações.

---

## 2. Governança e Regras de Segurança Multiempresa (Fase 1)

### 2.1 Contexto Empresarial Autenticado
- O escopo operacional do usuário não é determinado por parâmetros externos de requisição HTTP, mas estritamente pela **sessão autenticada** (`SessionGuard` e tabela `usuarios`).
- Usuários corporativos (perfis `analista_rh` e `operador_dp`) possuem seus escopos fixados em `empresa_id` e/ou lista explícita de `empresas_autorizadas`.
- Usuários com perfil `administrador` possuem gestão global por padrão, podendo ser parametrizados para escopos corporativos específicos.
- Tentativas de enviar `empresaId` diferente da empresa autorizada do usuário em requisições de criação (`POST`), edição (`PATCH`) ou consulta (`GET`) são sumariamente rejeitadas com `HTTP 403 Forbidden` (`EMPRESA_NAO_AUTORIZADA`).

### 2.2 Proteção Contra IDOR (Insecure Direct Object Reference)
- Em consultas e mutações por identificador primário (`GET /api/colaboradores/:id`, `PATCH /api/colaboradores/:id`, `PATCH /api/colaboradores/:id/inativar`, `GET /api/colaboradores/:id/historico`):
  * O backend valida o `empresa_id` do registro frente ao escopo do usuário autenticado.
  * Caso o colaborador pertença a outra organização, a API responde com **`HTTP 404 Not Found`**, impedindo a enumeração e vazamento da existência de recursos entre tenants.

---

## 3. Modelo de Dados Relacional e Migrações

### 3.1 Extensão do Schema (`migrations/005_seguranca_multiempresa.sql`)

```sql
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS filial_id TEXT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresas_autorizadas TEXT;

CREATE INDEX IF NOT EXISTS idx_usuarios_empresa_id ON usuarios(empresa_id);
```

### 3.2 Entidade Colaborador (PostgreSQL)

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL (PK) | Identificador numérico primário sequencial |
| `empresa_id` | TEXT / UUID | Identificador da organização para segregação multi-tenant |
| `filial_id` | TEXT / UUID | Identificador da filial vinculada |
| `matricula` | VARCHAR | Matrícula única por empresa |
| `nome_completo` | VARCHAR | Nome civil completo |
| `cpf` | VARCHAR | CPF normalizado (11 dígitos numéricos com validação matemática de módulo 11) |
| `data_nascimento`| DATE / TEXT | Data de nascimento (ISO AAAA-MM-DD) |
| `sexo` | VARCHAR | Identidade de gênero ou sexo declarado |
| `estado_civil` | VARCHAR | Estado civil |
| `email` | VARCHAR | Contato eletrônico institucional ou pessoal |
| `telefone` / `celular` | VARCHAR | Telefones de contato |
| `cep`, `logradouro`, `numero`, `complemento`, `bairro`, `cidade`, `uf` | VARCHAR | Endereço residencial completo |
| `departamento_id` / `cargo_id` | TEXT / UUID | Classificação hierárquica e alocação |
| `data_admissao` | DATE / TEXT | Data de admissão formal (posterior ao nascimento) |
| `cargo`, `setor`, `salario_base` | VARCHAR / NUMERIC | Dados contratuais básicos |
| `situacao` | VARCHAR | `ATIVO` ou `INATIVO` (inativação lógica sem expurgo físico) |
| `observacoes` | TEXT | Anotações gerenciais |
| `criado_em`, `atualizado_em` | TIMESTAMP / TEXT | Rastreabilidade cronológica |
| `criado_por`, `atualizado_por` | VARCHAR | Responsável pela ação |

---

## 4. Integração Frontend e Backend

- **Frontend React + TypeScript**: Componentes tipados, modais segregados em 4 seções (Dados Pessoais, Contato & Endereço, Vínculo Contratual, Dependentes), máscara de CPF na interface e nas listagens, confirmação explícita de inativação lógica.
- **Backend NestJS**: Camada controladora protegida por `SessionGuard`, `CsrfGuard` e `RolesGuard`, serviços de domínio com injeção de dependência e repositório parametrizado com proteção contra SQL Injection.
