# RH2.0 — Sistema Integrado de Departamento Pessoal & Folha de Pagamento

[![Testes Automatizados](https://img.shields.io/badge/Testes-77%20de%2077%20Aprovados%20(100%25)-success.svg)](tests/executar_todos_testes.py)
[![Segurança e Autenticação](https://img.shields.io/badge/Autentica%C3%A7%C3%A3o-AC--01%20a%20AC--16%20PASS-blue.svg)](docs/authentication/EVIDENCIAS.md)
[![Metodologia SDD](https://img.shields.io/badge/Metodologia-Spec--Driven%20Development-orange.svg)](docs/authentication/SPEC.md)

Módulo de **Login e Autenticação Segura** do RH2.0, desenvolvido seguindo a metodologia **Spec-Driven Development (SDD)**:
`SPEC → PLAN → TASKS → IMPLEMENTATION → TESTS → EVIDENCE`

---

## 1. Visão Geral da Arquitetura

O RH2.0 mantém a arquitetura oficial e as tecnologias homologadas pelos gestores de RH e GTI:
- **Backend:** Python 3.14 com servidor HTTP REST nativo (`backend/server.py`), extensível para execução autônoma local ou serverless (Vercel).
- **Persistência Relacional:** Dual-Mode (ADR-001) com SQLite em desenvolvimento local e testes efêmeros, e PostgreSQL em nuvem.
- **Criptografia e Senhas:** PBKDF2-HMAC-SHA256 com 100.000 iterações, salt criptográfico aleatório de 16 bytes e verificação em tempo constante (`hmac.compare_digest`).
- **Sessões e Cookies:** Tokens opacos de 32 bytes (64 caracteres hexadecimais), cookies com atributos `HttpOnly`, `SameSite=Lax` e `Secure` (em HTTPS), com regeneração de sessão no login e invalidação imediata no logout.
- **Proteções Avançadas:**
  - **Rate Limiting:** Bloqueio após 5 tentativas inválidas consecutivas em 15 minutos (HTTP 429 e `Retry-After`).
  - **Proteção CSRF / Origem:** Verificação estrita de cabeçalhos `Origin` e `Referer` em requisições mutáveis.
  - **Mensagens Neutras:** Mensagem genérica `"E-mail ou senha inválidos."` para evitar enumeração de contas.
  - **Auditoria:** Registro cronológico de logins, falhas, logouts e bloqueios na tabela `auditoria_autenticacao` sem armazenar segredos.
- **Frontend:** HTML5 semântico, CSS3 corporativo responsivo (mobile a desktop) e Vanilla JavaScript modular, garantindo leveza e ausência de dependências de compilação pesadas.

---

## 2. Como Configurar e Executar

### Pré-requisitos
- Python 3.10+ (recomendado Python 3.14)
- Terminal PowerShell (Windows) ou Bash (Linux/macOS)

### 2.1 Configuração de Variáveis de Ambiente
Copie o arquivo de exemplo para `.env`:
```bash
cp .env.example .env
```

Edite o arquivo `.env` para definir a senha da conta de administração:
```ini
ADMIN_INITIAL_PASSWORD=DefinaSuaSenhaForteAqui@2026!
GUEST_INITIAL_PASSWORD=OpcionalSenhaVisitante2026!
```

> **Atenção:** Em ambientes reais, o sistema interrompe a inicialização caso a variável `ADMIN_INITIAL_PASSWORD` não seja configurada, prevenindo senhas fracas.

### 2.2 Executar a Aplicação Localmente
Inicie o servidor HTTP nativo:
```powershell
python backend/server.py
```
Acesse a aplicação no navegador em: `http://127.0.0.1:8000`

---

## 3. Execução dos Testes Automatizados (Headless)

A suíte de testes do RH2.0 roda 100% em código de forma rápida e headless (sem necessidade de abrir navegadores gráficos ou instalar webdrivers externos):

```powershell
# Executar a suíte central consolidada (77 testes de integração e segurança)
python tests/executar_todos_testes.py

# Executar especificamente a suíte de Rate Limit, CSRF e AC-01 a AC-16
python tests/test_rate_limit_csrf.py
```

---

## 4. Estrutura Canônica de Diretórios

```text
RH2.0/
├── backend/
│   ├── auth.py              # Criptografia PBKDF2, gestão de sessão e login seguro
│   ├── audit.py             # Registro de auditoria sem segredos (RF-LOGIN-006)
│   ├── rate_limiter.py      # Rate limiting contra força bruta (RF-LOGIN-005)
│   ├── csrf.py              # Proteção CSRF e validação de origem (AC-13)
│   ├── database.py          # Gerenciador Dual-Mode SQLite/PostgreSQL
│   ├── server.py            # Servidor HTTP REST e roteamento de rotas protegidas
│   ├── service.py           # Regras de negócio de colaboradores
│   ├── folha_service.py     # Regras de negócio da folha de pagamento
│   └── folha_calculos.py    # Motor de cálculos trabalhistas
├── frontend/
│   ├── index.html           # Tela de Login RH2.0 e layout protegido
│   ├── styles.css           # Design system corporativo acessível e responsivo
│   └── app.js               # Gerenciador de sessão e formulários
├── migrations/
│   ├── 001_schema_inicial.sql
│   ├── 002_modulo_folha_pagamento.sql
│   └── 003_auditoria_autenticacao.sql   # Nova migração de auditoria
├── tests/
│   ├── executar_todos_testes.py         # Orquestrador consolidado (77 testes)
│   ├── test_rate_limit_csrf.py          # Testes específicos de AC-01 a AC-16
│   ├── test_autenticacao.py             # Testes de segurança e credenciais
│   ├── test_colaboradores.py            # Testes do Módulo 1 (Colaboradores)
│   ├── test_folha_calculos.py           # Testes de cálculos trabalhistas
│   └── test_folha_service.py            # Testes de ciclo de vida da folha
├── docs/
│   └── authentication/
│       ├── SPEC.md                      # Especificação funcional
│       ├── CRITERIOS_DE_ACEITE.md       # Matriz AC-01 a AC-16 (100% PASS)
│       └── EVIDENCIAS.md                # Relatório detalhado com logs reais
├── vercel.json                          # Configuração para deploy serverless
├── pyproject.toml                       # Configurações de qualidade e cobertura
└── .env.example                         # Modelo seguro sem credenciais reais
```

---

## 5. Matriz de Critérios de Aceite (AC-01 a AC-16)

Consulte o documento oficial com evidências e asserções comprovadas em:  
📘 **[Relatório de Evidências RH2.0](docs/authentication/EVIDENCIAS.md)** e **[Critérios de Aceite](docs/authentication/CRITERIOS_DE_ACEITE.md)**.

