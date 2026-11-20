# ARQUITETURA OFICIAL DO PROJETO — RH2.0 ENTERPRISE
**Documento de Consolidação de Arquitetura, Diagnóstico e Decisões Técnicas (ADR)**  
**Data:** 19 de Novembro de 2026  
**Status:** Oficial e Homologado  
**Versão:** 2.0.0-enterprise

---

## 1. DIAGNÓSTICO DA BASE DE CÓDIGO E COEXISTÊNCIA DE TECNOLOGIAS

Foi realizada uma auditoria profunda em toda a estrutura do repositório para mapear a duplicidade arquitetural identificada:

| Diretório | Linguagem / Framework | Escopo Implementado | Status na Arquitetura |
|---|---|---|---|
| `backend/` | Python 3.12+ (Standard Library HTTP + DAL SQLite/PostgreSQL) | **Completo:** 20 módulos funcionais, catálogo de 82 eventos, folha, ponto 671, férias, rescisões, SST, eSocial, CNAB 240, RBAC 8 perfis, LGPD, 122 testes automatizados. | **MOTOR OFICIAL DE PRODUÇÃO** |
| `backend-nest/` | TypeScript / NestJS | **Incompleto:** Apenas CRUD de colaboradores, autenticação básica e esboço inicial de cálculo de folha. Ausência de ponto, férias, rescisões, SST, eSocial e CNAB. | **PROTÓTIPO PRESERVADO (NÃO DEPLOYADO)** |
| `frontend/` | Vanilla HTML5 / Modern CSS3 / JavaScript ES6+ (SPA) | **Completo:** Interface 100% responsiva (Desktop & Mobile 360-1920px), todos os 20 módulos, Portal do Colaborador e Portal do Gestor. | **INTERFACE OFICIAL DE PRODUÇÃO** |
| `frontend-react/` | React 18 / TypeScript | **Incompleto:** Apenas visualização básica de colaboradores (`ColaboradoresPage.tsx`). Ausência de 19 módulos. | **PROTÓTIPO PRESERVADO (NÃO DEPLOYADO)** |
| `api/` | Python Serverless (Vercel) | Despachantes serverless delegando diretamente para `backend/server.py`. | **CAMADA DE DEPLOY SERVERLESS (VERCEL)** |

### Decisão Arquitetural Fundamental (ADR-001)
1. **Backend Oficial Unificado:** O backend corporativo oficial do RH2.0 Enterprise é a suite **Python 3.12+ (`backend/`)**. Essa decisão se fundamenta em:
   - Cobertura funcional total (100% dos requisitos RF-001 a RF-200 atendidos).
   - Motor de cálculo de alta precisão com `decimal.Decimal` e conformidade matemática ABNT NBR 5891.
   - Suporte dual maduro a SQLite (desenvolvimento/testes locais) e PostgreSQL 14+ (produção).
   - Configuração de deploy ativa em `vercel.json` roteando diretamente para Python.
2. **Frontend Oficial Unificado:** A interface oficial do sistema é a aplicação SPA contida em **`frontend/`**, garantindo:
   - Zero sobrecarga de build (sem vulnerabilidades de cadeias npm complexas em runtime).
   - Compatibilidade total com computadores, notebooks, tablets e smartphones (Android e iOS).
   - Renderização nativa dos 20 módulos de RH/DP e portais corporativos.
3. **Preservação de Código:** Nenhuma pasta legada (`backend-nest`, `frontend-react`) foi apagada, garantindo segurança patrimonial do código e evitando regressões.

---

## 2. UNIFICAÇÃO DOS MOTORES DE CÁLCULO E TABELAS LEGAIS

### 2.1 O Problema Identificado
Identificou-se a presença de arquivos de cálculo com tabelas e parâmetros divergentes:
- `backend/folha_calculos.py`: Utilizava parâmetros padrão de referência (Salário Mínimo R$ 1.518,00, Teto INSS R$ 8.157,41).
- `backend/folha_calculos_2026.py`: Utilizava parâmetros da Portaria MPS/MF 13/2026 e RN-001 a RN-083 (Salário Mínimo R$ 1.621,00, Teto INSS R$ 8.475,55).
- Funções `_to_decimal()` e `to_d()` realizavam conversão silenciosa de textos inválidos para `0.00`.

### 2.2 Arquitetura Centralizada Unificada
Criação do módulo `backend/tabelas_legais.py` e `backend/motor_calculo_unificado.py`:
- **Centralização:** Um único repositório de parâmetros legais indexados por competência e vigência normativa.
- **Memória de Cálculo Completa:** Toda rubrica calculada gera um objeto detalhado com: base de cálculo, alíquotas aplicadas, deduções legais, fórmulas, vigência normativa e resultado final.
- **Validação Estrita de Dados:** A função `converter_decimal_estrito()` valida tipos e rejeita strings não numéricas com erro explícito (`ValueError`), eliminando distorções financeiras silenciosas.
- **Retrocompatibilidade Garantida:** `folha_calculos.py` e `folha_calculos_2026.py` passam a orquestrar suas operações através da engine centralizada.

---

## 3. MULTIEMPRESA E ISOLAMENTO DE DADOS

- **Contexto Seguro de Tenant:** O `empresa_id` é extraído exclusivamente da sessão criptográfica autenticada do usuário (`token`). Parâmetros soltos enviados no corpo ou na URL são validados contra a autorização do usuário.
- **Prevenção de Vulnerabilidades BOLA / IDOR:** Consultas a colaboradores, folhas, férias, ponto e rescisões aplicam cláusula mandatória `AND empresa_id = :empresa_id`.
- **Perfis de Acesso (RBAC):** Os 8 perfis canônicos operam sob o princípio do menor privilégio (`superadmin`, `admin_empresa`, `gestor_rh`, `analista_dp`, `financeiro`, `contabilidade`, `gestor_departamento`, `colaborador`).

---

## 4. CONFORMIDADE COM ESOCIAL E CNAB 240

- **eSocial:** As transmissões de eventos em ambiente de desenvolvimento/homologação sem certificado digital ICP-Brasil instalado são explicitamente registradas com status `SIMULADO_HOMOLOGACAO`, sem emissão de recibos oficiais falsos da Receita Federal.
- **CNAB 240:** A geração de remessa bancária utiliza dados dinâmicos da empresa pagadora e contas bancárias cadastradas dos colaboradores, contemplando layouts de múltiplos bancos (Banco do Brasil 001, Bradesco 237, Itaú 341, Santander 033 e Caixa 104).

---
*Aprovado pelo Arquiteto de Software e Engenheiro Chefe do Projeto RH2.0 Enterprise.*
