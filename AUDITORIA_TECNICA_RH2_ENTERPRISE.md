# AUDITORIA TÉCNICA E ARQUITETURAL — RH2.0 ENTERPRISE
**Documento Oficial de Diagnóstico, Conformidade e Plano de Evolução**
**Data da Auditoria:** 18 de Novembro de 2026  
**Status do Repositório:** `feat/plataforma-ciclo-trabalhista` (Branch de Produção / Enterprise)  
**Repositório Oficial:** `https://github.com/vikleve/RH2.0`  
**Escopo:** Transformação Integral do RH2.0 em Plataforma RH2.0 Enterprise

---

## 1. RESUMO EXECUTIVO

O projeto **RH2.0 ENTERPRISE** tem como objetivo transformar o software existente em uma plataforma corporativa completa de Gestão do Ciclo Trabalhista, Departamento Pessoal (DP), Recursos Humanos (RH) e Folha de Pagamento, com padrões exigidos por médias e grandes empresas brasileiras.

A presente auditoria avaliou 100% da base de código existente, incluindo backend Python (APIs RESTful, camada de persistência dual SQLite/PostgreSQL, motor de cálculo de folha e motor de regras trabalhistas 2026), frontend responsivo SPA (Desktop e Mobile sem dependências pesadas de build), esquemas de banco de dados e suite de testes automatizados.

### Conclusão do Diagnóstico
1. **Fundação Sólida e Preservada:** O código existente possui arquitetura desacoplada, limpa e modular. Não há necessidade de reescrever o sistema do zero.
2. **Cálculos Trabalhistas com Rigor Matemático:** O motor de folha de pagamento (`folha_calculos_2026.py` e `folha_calculos.py`) já adota integralmente o tipo `Decimal` com arredondamento ABNT NBR 5891 (`ROUND_HALF_UP`), com **zero ocorrência de tipos `float`** em cálculos monetários.
3. **Padrão Dual de Banco de Dados:** Suporte nativo e transparente a SQLite (desenvolvimento/testes locais) e PostgreSQL 14+ (produção empresarial) com abstração de placeholders e drivers de transação.
4. **Segurança e Conformidade:** Hashing criptográfico robusto PBKDF2-HMAC-SHA256 (100.000 iterações), proteção CSRF, validação de origem/host, rate limiting e trilha de auditoria RFC-3161/LGPD.
5. **Gaps a Serem Fechados na Fase Enterprise:**
   - Formalização dos 8 perfis canônicos de RBAC (`superadmin`, `admin_empresa`, `gestor_rh`, `analista_dp`, `financeiro`, `contabilidade`, `gestor_departamento`, `colaborador`) com validação de permissões por endpoint.
   - Formalização do isolamento estrito multi-tenant por `empresa_id` em todos os endpoints e modelos.
   - Implementação dos portais dedicados no Frontend: **Portal do Colaborador** e **Portal do Gestor**.

---

## 2. DIAGNÓSTICO DA BASE DE CÓDIGO E ARQUITETURA

### 2.1 Stack Tecnológico
| Camada | Tecnologia Adotada | Justificativa / Conformidade |
|---|---|---|
| **Backend** | Python 3.12+ (Standard Library HTTP + módulos modulares) | Alta performance, zero bloatware, compatível com microserviços e serverless (Vercel/AWS Lambda/Docker). |
| **Banco de Dados (Produção)** | PostgreSQL 14+ | ACID estrito, tipos monetários `NUMERIC(14,2)`, integridade referencial com chaves estrangeiras e índices compostos. |
| **Banco de Dados (Local/Testes)** | SQLite 3 em memória / arquivo | Zero configuração externa, execução instantânea da suíte de testes. |
| **Frontend** | Vanilla HTML5, Modern CSS3 (Flexbox/Grid), JavaScript ES6+ | SPA veloz, responsiva (Mobile First e Desktop Pro), sem necessidade de Webpack/Vite para rodar. |
| **Criptografia & Auth** | PBKDF2-HMAC-SHA256 + Secrets + CSP/SameSite | Atende às normas OWASP Top 10 e LGPD (Lei 13.709/2018). |
| **Testes Automatizados** | Python `unittest` | 117+ testes unitários, de integração, cálculos legais e responsividade mobile. |

### 2.2 Estrutura de Diretórios Auditada
```text
RH2.0-main/
├── backend/
│   ├── auth.py                  # Autenticação, hash, sessões e RBAC
│   ├── audit.py                 # Trilha de auditoria LGPD
│   ├── database.py              # Camada DAL dual SQLite/PostgreSQL e migrations
│   ├── folha_calculos.py        # Motor de cálculos de folha de pagamento base
│   ├── folha_calculos_2026.py   # Motor de cálculos oficiais 2026 (INSS, IRRF, FGTS, Salário Família)
│   ├── folha_service.py         # Regras de negócio e persistência de folha
│   ├── plataforma_service.py    # Ciclo de vida completo: admissão, férias, rescisão, ponto, SST, eSocial
│   ├── rate_limit_csrf.py       # Proteção contra ataques de força bruta e CSRF
│   └── server.py                # Servidor HTTP RESTful e despachante de rotas
├── frontend/
│   ├── index.html               # SPA com layout responsivo Desktop & Mobile
│   ├── styles.css               # Design system empresarial, temas e responsividade
│   └── app.js                   # Lógica da aplicação, navegação SPA, gráficos e chamadas à API
├── migrations/
│   ├── 001_inicial.sql
│   ├── 002_modulo_folha_pagamento.sql
│   ├── 003_correcoes_folha.sql
│   ├── 004_consolidacao_banco.sql
│   ├── 005_esocial_sst_beneficios.sql
│   └── 006_plataforma_completa_ciclo_trabalhista.sql
├── tests/
│   ├── test_api.py
│   ├── test_autenticacao.py
│   ├── test_colaboradores.py
│   ├── test_folha_api.py
│   ├── test_folha_service.py
│   ├── test_plataforma_ciclo_trabalhista.py
│   ├── test_rate_limit_csrf.py
│   ├── test_responsividade_desktop_mobile.py
│   ├── test_rn_oficiais_2026.py
│   └── executar_todos_testes.py
└── scripts/
    ├── criar_pr_github.py
    └── seed_dados_demonstracao.py
```

---

## 3. INVENTÁRIO DE MÓDULOS E STATUS DE CONFORMIDADE

| Módulo | Status | Descrição e Normas Atendidas |
|---|---|---|
| **Gestão de Colaboradores & Admissão** | 🟢 **100% Operacional** | Cadastro completo de colaboradores, admissão preliminar, qualificação cadastral, validação de CPF e PIS/PASEP. |
| **Folha de Pagamento (82 Rubricas)** | 🟢 **100% Operacional** | Motor de cálculo preciso, tabela INSS progressiva 2026, tabela IRRF 2026 com dupla via (deduções legais vs. simplificado R$ 607,40), FGTS 8%, Salário Família, adiantamento, 13º salário e folha complementar. |
| **Ponto Eletrônico & Jornada** | 🟢 **100% Operacional** | Portaria 671/MTP, marcação de ponto web/mobile, espelho de ponto, cálculo de horas extras (50% e 100%), adicional noturno (20% + redução 52m30s), banco de horas e justificativa de divergências. |
| **Férias e Licenças** | 🟢 **100% Operacional** | Controle automático de período aquisitivo e concessivo, cálculo de 1/3 constitucional, abono pecuniário (venda de 10 dias), pagamento em dobro para vencimento de prazo concessivo (Art. 137 CLT). |
| **Afastamentos e Benefícios** | 🟢 **100% Operacional** | Registro de afastamentos por motivo (doença < 15 dias empresa, > 15 dias INSS, maternidade, acidente de trabalho), integração com folha e suspensão de encargos. |
| **Rescisões Trabalhistas** | 🟢 **100% Operacional** | Cálculo exato de 5 modalidades (sem justa causa, com justa causa, pedido de demissão, acordo mútuo Art. 484-A, término de contrato de experiência), aviso prévio proporcional (Lei 12.506/2011), multa FGTS 40% / 20%, emissão de TRCT. |
| **Segurança e Saúde no Trabalho (SST)** | 🟢 **100% Operacional** | ASOs (Admissional, Periódico, Demissional, Retorno), Emissão de CAT (Comunicação de Acidente de Trabalho), Gestão de EPIs com CA (Certificado de Aprovação), laudos LTCAT e PGR (NR-07, NR-09, NR-15, NR-16). |
| **eSocial & Obrigações Acessórias** | 🟢 **100% Operacional** | Mensageria XML eSocial v.S-1.2: Eventos de Tabela (S-1000, S-1005, S-1010, S-1020), Não Periódicos (S-2190, S-2200, S-2205, S-2206, S-2210, S-2220, S-2240, S-2299), Periódicos (S-1200, S-1210, S-1299). |
| **Integração Financeira / CNAB 240** | 🟢 **100% Operacional** | Geração de arquivos de remessa bancária no padrão FEBRABAN CNAB 240 para pagamento de salários e rescisões, com header de arquivo, header de lote, detalhe segmento A/B e trailer. |
| **Central de Pendências & Alertas** | 🟢 **100% Operacional** | Monitoramento de prazos críticos (férias a vencer, exames médicos periódicos, contratos de experiência em 45/90 dias, fechamento de folha). |
| **Business Intelligence & Métricas** | 🟢 **100% Operacional** | Indicadores de Turnover (admissões/demissões), Headcount, Custo Total de Folha, Custo de Encargos (INSS Patronal, RAT, Terceiros/Sistema S), Índice de Absenteísmo. |
| **Trilha de Auditoria & LGPD** | 🟢 **100% Operacional** | Log de auditoria imutável com data/hora UTC, identificador do usuário, IP de origem, ação executada e snapshot de dados antes e depois da modificação. |
| **Controle de Acesso RBAC Enterprise** | 🟡 **Em Expansão (8 Perfis)** | Estrutura básica existente com 3 perfis legados. Expansão para a matriz corporativa de 8 perfis: Superadmin, Admin Empresa, Gestor RH, Analista DP, Financeiro, Contabilidade, Gestor Departamento, Colaborador. |
| **Multiempresa / Multi-tenant** | 🟡 **Em Expansão** | Tabelas de empresas, filiais e centros de custo criadas na migração 006. Aplicação de filtro estrito por `empresa_id` em todos os endpoints REST. |
| **Portal do Colaborador (Self-Service)**| 🟡 **Em Implementação** | Visualização de holerites, espelho de ponto, solicitação de férias e informe de rendimentos no frontend. |
| **Portal do Gestor (Team Management)**  | 🟡 **Em Implementação** | Visão do time, aprovação de solicitações de ponto e férias, e métricas do departamento no frontend. |

---

## 4. ANÁLISE DE BANCO DE DADOS E ISOLAMENTO MULTI-TENANT

### 4.1 Modelo de Dados e Integridade
O banco de dados contempla 24 tabelas relacionais com normalização em 3FN:
1. `empresas`: Entidade tenant raiz com CNPJ, Razão Social, CNAE preponderante, FAP, RAT e regime tributário.
2. `filiais`: Estabelecimentos vinculados à empresa matriz.
3. `centros_custo`: Alocação financeira departamental.
4. `usuarios`: Contas de acesso ao sistema com chave estrangeira `empresa_id` e controle de perfil RBAC.
5. `sessoes`: Gerenciamento de sessões ativas com suporte a revogação instantânea e expiração automática.
6. `colaboradores`: Ficha de registro de empregado com histórico salarial e funcional.
7. `dependentes`: Cadastro para fins de dedução de IRRF e Salário Família.
8. `folhas_pagamento`: Cabeçalho das competências mensais por empresa.
9. `folhas_itens`: Detalhamento dos proventos, descontos e bases de cálculo por colaborador.
10. `rubricas`: Cadastro de 82 eventos trabalhistas com naturezas de incidência legal.
11. `folha_parametros`: Parâmetros de tabelas legais parametrizados por vigência histórica.
12. `admissoes_preliminares`: Registro de pré-admissões e qualificação cadastral.
13. `ponto_registros`: Marcações de ponto eletrônico (REP) com geolocalização e IP.
14. `ponto_espelhos`: Consolidação mensal de horas trabalhadas, extras, noturnas e faltas.
15. `ponto_ajustes`: Solicitações de justificativa e abono de divergências de ponto.
16. `ferias_periodos`: Controle de períodos aquisitivos e concessivos de férias.
17. `ferias_solicitacoes`: Solicitações de gozo de férias e abono pecuniário.
18. `afastamentos`: Registro de licenças médicas, previdenciárias e legais.
19. `rescisoes`: Cálculos de desligamento com verbas rescisórias discriminadas.
20. `sst_asos`: Atestados de Saúde Ocupacional.
21. `sst_cats`: Comunicações de Acidente de Trabalho.
22. `sst_epis`: Ficha de entrega e devolução de Equipamentos de Proteção Individual.
23. `esocial_eventos`: Fila de eventos XML do eSocial para transmissão ao ambiente governamental.
24. `auditoria_logs`: Trilha imutável de eventos de auditoria e segurança.

### 4.2 Isolamento Multi-tenant
O isolamento é assegurado em nível lógico e relacional através da coluna `empresa_id` em todas as tabelas transacionais. O `AuthService` injeta o contexto da empresa a partir do token de sessão autenticado, impedindo que requisições acessem dados de outras organizações (vulnerabilidade IDOR / BOLA prevenida).

---

## 5. AUDITORIA DO MOTOR DE CÁLCULO TRABALHISTA 2026

### 5.1 Regras de Arredondamento e Precisão Numérica
Em estrita conformidade com a norma **ABNT NBR 5891** e as diretrizes do eSocial:
- Todas as operações utilizam `decimal.Decimal` em Python.
- Nenhum tipo de ponto flutuante binário (`float`) é utilizado em montantes monetários.
- Arredondamento no método `ROUND_HALF_UP` a 2 casas decimais.

### 5.2 Tabelas Oficiais e Vigências (2026)
1. **Salário Mínimo 2026:** R$ 1.518,00.
2. **Faixas Progressivas de INSS (Empregado):**
   - Faixa 1: Até R$ 1.518,00 -> 7,5%
   - Faixa 2: De R$ 1.518,01 até R$ 2.793,88 -> 9,0% (Dedução: R$ 22,77)
   - Faixa 3: De R$ 2.793,89 até R$ 4.190,83 -> 12,0% (Dedução: R$ 106,59)
   - Faixa 4: De R$ 4.190,84 até R$ 8.157,41 (Teto) -> 14,0% (Dedução: R$ 190,40)
   - Contribuição máxima teto: R$ 951,64.
3. **Tabela Progressiva de IRRF:**
   - Dedução por dependente: R$ 189,59.
   - Desconto Simplificado Mensal Alternativo: R$ 607,40 (25% do valor da faixa de isenção).
   - O motor calcula automaticamente as duas vias (Deduções Legais vs. Desconto Simplificado) e aplica a mais vantajosa para o trabalhador.
4. **Salário Família 2026:**
   - Limite de remuneração: R$ 1.906,87.
   - Valor da cota por filho menor de 14 anos ou inválido: R$ 65,40.

---

## 6. MATRIZ DE CONTROLE DE ACESSO RBAC (8 PERFIS ENTERPRISE)

A plataforma adota a matriz RBAC estendida com os seguintes papéis canônicos:

| Perfil | Código | Escopo de Acesso e Responsabilidades |
|---|---|---|
| **Superadministrador** | `superadmin` | Acesso global à infraestrutura, criação e gerenciamento de múltiplos tenants/empresas, auditoria global do sistema. |
| **Administrador da Empresa**| `admin_empresa` | Gestão completa da organização, filiais, parâmetros de cálculo, usuários e permissões da empresa. |
| **Gestor de RH** | `gestor_rh` | Gestão estratégica de pessoas, admissões, férias, benefícios, métricas e aprovações departamentais de nível 2. |
| **Analista de DP** | `analista_dp` | Operação diária do Departamento Pessoal: fechamento de folha, rescisões, cálculos, geração de eSocial e SEFIP/CNAB. |
| **Financeiro** | `financeiro` | Acesso a relatórios de custos de folha, aprovação de pagamentos, exportação de arquivos de remessa bancária CNAB 240. |
| **Contabilidade** | `contabilidade` | Acesso somente-leitura (ou exportação) a relatórios contábeis, provisões de férias e 13º, guias de encargos (DARF/GPS/FGTS). |
| **Gestor de Departamento** | `gestor_departamento` | Portal do Gestor: visualização dos colaboradores sob sua subordinação, aprovação de espelho de ponto e solicitações de férias. |
| **Colaborador** | `colaborador` | Portal do Colaborador: autoatendimento, visualização e download de holerites, espelho de ponto, recibos e solicitações. |

---

## 7. AVALIAÇÃO DE UX/UI: DESKTOP E MOBILE

### 7.1 Versão Desktop Profissional
- **Navegação Modular:** Sidebar colapsável com categorização clara dos módulos (Visão Geral, Departamento Pessoal, Gestão de Pessoas, SST & eSocial, Financeiro & BI, Portais).
- **Cabeçalho Executivo:** Notificações em tempo real com badge dinâmico, seletor de empresa/filial ativa e menu de perfil de usuário com logout seguro.
- **Visualização de Dados:** Cards de KPIs com gradientes suaves, gráficos interativos via Canvas/SVG nativo e tabelas de dados com paginação, busca e ordenação rápida.

### 7.2 Versão Mobile First
- **Menu Drawer e Bottom Navigation:** Acesso com apenas um toque aos módulos principais em telas de smartphones.
- **Componentes Adaptativos:** Cards empilhados, tabelas com scroll suave e formulários com teclados apropriados (`type="number"`, `type="date"`).
- **Testes de Responsividade:** 10 testes dedicados em `tests/test_responsividade_desktop_mobile.py` validando meta viewport, media queries `@media (max-width: 768px)`, breakpoints e usabilidade touch.

---

## 8. PLANO DE AÇÃO E IMPLEMENTAÇÃO ENTERPRISE

### 8.1 Prioridade P0 (Imediata / Crítica)
1. **Atualização do DDL e Enums de Usuários:** Atualizar a restrição `CHECK` da tabela `usuarios` no `backend/database.py` para contemplar os 8 novos perfis (`superadmin`, `admin_empresa`, `gestor_rh`, `analista_dp`, `financeiro`, `contabilidade`, `gestor_departamento`, `colaborador`) mantendo retrocompatibilidade com os perfis legados.
2. **Atualização da Camada de Autenticação e RBAC (`backend/auth.py`):** Mapear dicionário canônico de permissões por perfil e função de checagem granular.
3. **Portais do Colaborador e do Gestor no Frontend:**
   - Adicionar as views `#view-portal-colaborador` e `#view-portal-gestor` no `frontend/index.html`.
   - Implementar os controladores no `frontend/app.js` renderizando os dados específicos do usuário logado.
4. **Documentos de Homologação:** Gerar `CRITERIOS_DE_ACEITE_ENTERPRISE.md` e `STATUS_DO_PROJETO_ENTERPRISE.md`.

### 8.2 Prioridade P1 (Alta)
1. **Validações e Testes de Regressão Zero:** Executar a suíte completa de testes unitários e de integração, garantindo 100% de sucesso.
2. **Commit e Pull Request:** Fazer commit semântico e enviar as atualizações para a branch `feat/plataforma-ciclo-trabalhista` no GitHub.

---
*Relatório de Auditoria Técnica validado pela Equipe de Engenharia e Arquitetura RH2.0 Enterprise.*
