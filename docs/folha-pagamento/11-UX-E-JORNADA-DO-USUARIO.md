# 11 — UX/UI e Jornada Simplificada para Usuário Não Técnico

**Projeto:** RH2.0 — Portal de Departamento Pessoal & Folha de Pagamento  
**Data:** 18/11/2026

---

## 1. Diagnóstico da Interface Atual (`frontend/index.html`, `styles.css`, `app.js`)

A interface web desenvolvida pelos alunos já apresenta um excelente padrão visual corporativo (identidade visual *ForçaVerde Usina • RH2.0*), responsiva, limpa e dividida em duas abas claras:
1. **Módulo 01 — Gestão de Colaboradores:** Cards de indicadores no topo (`Total`, `Ativos`, `Inativos`, `Departamentos`), busca unificada + filtros específicos (`Nome`, `Matrícula`, `CPF`, `Cargo`, `Setor`, `Situação`), tabela com ações claras (`Ver Detalhes e Auditoria`, `Editar`, `Inativar/Reativar`) e modal organizado em seções (`A. Dados Pessoais`, `B. Contato/Endereço`, `C. Vínculo e Salário`, `D. Dependentes`, `E. Justificativa de Alteração`).
2. **Módulo 02 — Folha de Pagamento:** Cards de resumo financeiro da competência (`Folhas na Competência`, `Total de Proventos`, `Total de Descontos`, `Total Líquido a Pagar`), seletor de competência (`AAAA-MM`), modal de lançamento com prévia financeira em tempo real, modal de parâmetros e modal de **Demonstrativo de Pagamento (Holerite)** pronto para impressão com memória de cálculo passo a passo.

---

## 2. Melhorias de Usabilidade Planejadas (Seção 10 — Simplicidade Extrema)

Para tornar a operação 100% intuitiva e guiada para um usuário comum (sem nenhum jargão técnico de banco de dados, API ou migrações):

### 2.1. Faixa de Status e Passo a Passo da Competência (Módulo 2)
Adicionar no topo do Módulo 2 um **Indicador Guiado da Competência Selecionada**, comunicando em linguagem simples:
- **Estado da Competência:**
  - `EM ABERTO (Pendente de Geração)`: Quando existem colaboradores ativos sem folha calculada no mês. Exibe botão direto **"Gerar Folhas do Mês (Todos os Ativos)"**.
  - `EM CONFERÊNCIA (Pronta para Fechamento)`: Quando as folhas do mês já foram calculadas e estão abertas para conferência ou ajustes de eventos. Exibe botão **"Fechar Competência"**.
  - `COMPETÊNCIA FECHADA E HOMOLOGADA`: Quando todas as folhas da competência estão fechadas, indicando data e responsável pelo fechamento.

### 2.2. Configuração Simples da Empresa e Parâmetros (`#modal-parametros-folha`)
- Transformar o modal de Parâmetros (atualmente bloqueado como somente leitura) em uma tela clara dividida em duas partes simples:
  1. **Dados da Empresa (Exibidos no Holerite):** Razão Social, CNPJ (com máscara automática) e Endereço.
  2. **Regras Trabalhistas da Folha:** Divisor mensal (220h), Dias comerciais (30), Percentuais de Horas Extras (50% e 100%), Adicional Noturno (20%), Teto do INSS e Dedução por Dependente IRRF.
- Adicionar botão **"Salvar Configurações"** que só exibe a notificação verde `"Configurações salvas com sucesso!"` após confirmação HTTP 200 do Neon PostgreSQL.

### 2.3. Fidelidade da Barra de Prévia e Edição Sem Perda de Dados
- Ao digitar horas extras, faltas ou adicionar um evento do catálogo no modal da folha, a **Barra de Prévia em Tempo Real** mostrará os valores exatos de Proventos, Descontos (incluindo INSS e IRRF 2026) e Salário Líquido.
- Ao clicar em **Editar** em uma folha calculada para corrigir um lançamento, todos os eventos anteriormente registrados (horas extras 50%/100%, adicional noturno, faltas, atrasos e rubricas adicionais) serão preenchidos fielmente na tela, evitando que o usuário precise redigitá-los.

### 2.4. Honestidade Visual sobre Persistência (Prevenção de Falso Sucesso)
- Manter e reforçar a regra já implementada em `requisitarApi()` (`frontend/app.js#L387`): **nenhum toast de sucesso é exibido e nenhum modal é fechado antes da confirmação HTTP 200/201 do backend/Neon**. Se houver falha de validação ou indisponibilidade do banco (HTTP 400/503), o formulário permanece aberto com os dados digitados preservados e destaca exatamente o campo ou motivo do erro em português claro.
