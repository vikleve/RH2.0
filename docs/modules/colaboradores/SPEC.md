# Especificação Técnica — Módulo de Cadastro de Colaboradores (SPEC-03)

**Projeto:** RH2.0 — Plataforma de Gestão de Ciclo Trabalhista  
**Versão:** 1.0  
**Stack Oficial:** React + TypeScript | NestJS (Node.js LTS v26) | PostgreSQL  

---

## 1. Visão Geral

O módulo de Cadastro de Colaboradores do **RH2.0** viabiliza o registro, consulta, edição, inativação lógica e auditoria dos colaboradores corporativos, servindo como o alicerce relacional para os futuros módulos de Admissão, Jornada de Trabalho, Folha de Pagamento, Férias e eSocial.

---

## 2. Modelo de Dados

Entidade `colaboradores` persistida no PostgreSQL:

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL (PK) | Identificador numérico primário com suporte a chaves estrangeiras |
| `empresa_id` | UUID | Identificador da empresa para segregação multi-tenant |
| `filial_id` | UUID | Identificador da filial vinculada |
| `matricula` | VARCHAR | Matrícula única do colaborador dentro da empresa |
| `nome_completo` | VARCHAR | Nome civil completo |
| `cpf` | VARCHAR | CPF normalizado (11 dígitos numéricos com validação matemática) |
| `data_nascimento`| DATE / TEXT | Data de nascimento (formato ISO AAAA-MM-DD) |
| `sexo` | VARCHAR | Sexo / Identidade de gênero declarada |
| `estado_civil` | VARCHAR | Estado civil do colaborador |
| `email` | VARCHAR | Endereço eletrônico corporativo ou pessoal |
| `telefone` / `celular` | VARCHAR | Contato telefônico |
| `cep`, `logradouro`, `numero`, `complemento`, `bairro`, `cidade`, `uf` | VARCHAR | Endereço residencial completo |
| `departamento_id` / `cargo_id` | UUID | Vínculos organizacionais |
| `data_admissao` | DATE / TEXT | Data de admissão formal (opcional no cadastro inicial) |
| `cargo`, `setor`, `salario_base` | VARCHAR / NUMERIC | Dados contratuais básicos |
| `situacao` | VARCHAR | `ATIVO` ou `INATIVO` |
| `observacoes` | TEXT | Anotações administrativas |
| `criado_em`, `atualizado_em` | TIMESTAMP | Controle cronológico de auditoria |
| `criado_por`, `atualizado_por` | VARCHAR / UUID | Responsável pela ação |
