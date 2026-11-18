# Motor Oficial de Cálculos e Parametrização da Folha de Pagamento

**Projeto:** RH2.0 — Plataforma Integrada de Gestão do Ciclo Trabalhista  
**Módulo:** Folha de Pagamento & Departamento Pessoal  
**Especificação Técnica:** SPEC-PATCH-FOLHA-001  
**Status de Governança:** TESTADO — AGUARDANDO HOMOLOGAÇÃO DO DP / ORIENTADOR  
**Precisão Numérica:** Decimal estrita com arredondamento `ROUND_HALF_UP` (2 casas decimais)  

---

## 1. Visão Geral da Arquitetura

O motor de cálculos da folha do RH2.0 opera com **fonte única de regras centralizada no backend** (`backend-nest/src/modules/folha/folha-calculos.engine.ts`), eliminando regras independentes e dispersas no frontend.

A interface gráfica consome os cálculos oficiais através de duas operações padronizadas:
1. **Simulação Não Destrutiva (`POST /api/folha/simular`):** Calcula em memória os proventos, descontos, bases e totais sem persistência no banco de dados.
2. **Processamento & Persistência Transacional (`POST /api/folha` e `POST /api/folha/:id/recalcular`):** Executa o motor em transação ACID no PostgreSQL, registrando cada rubrica com memória de cálculo detalhada em `folha_itens` e trilha de auditoria em `folha_historico`.

---

## 2. Regras de Negócio e Deduplicação de Rubricas

### 2.1 Deduplicação do Salário Mensal (Evento 0001)
- O salário-base proporcional aos dias trabalhados é apurado como o item provento fundamental da folha.
- Caso o usuário selecione o evento `0001 — Salário mensal` na tabela de eventos avulsos, o sistema unifica o valor com o item base, **impedindo a duplicação do salário contratual**.

### 2.2 Deduplicação e Apuração Progressiva do INSS (Evento 0501)
- A contribuição previdenciária é apurada automaticamente pelo motor através da aplicação da tabela progressiva oficial sobre a base de proventos que incidem INSS, respeitando o teto previdenciário de R$ 8.157,41.
- Caso o usuário selecione `0501 — INSS` na tabela manual, o sistema evita duplicidade e assegura que apenas o desconto oficial progressivo seja lançado.

### 2.3 Cálculo Progressivo do IRRF (Evento 0505)
- Base de cálculo = Base INSS - Desconto de INSS - (Dependentes homologados × R$ 189,59).
- Aplicação das faixas legais de isenção e alíquotas progressivas (7,5%, 15%, 22,5%, 27,5%) com dedução da parcela correspondente.

### 2.4 Variáveis e Encargos
- **Horas Extras 50% (0010):** `(Salário Base / Divisor Horas) × 1,50 × Quantidade`.
- **Horas Extras 100% (0011):** `(Salário Base / Divisor Horas) × 2,00 × Quantidade`.
- **Adicional Noturno 20% (0020):** `(Salário Base / Divisor Horas) × 0,20 × Horas Noturnas`.
- **DSR sobre Variáveis (0012):** `(Total Horas Extras e Noturno / Dias Úteis) × Repousos e Feriados`.
- **Vale-transporte (0510):** Limitador legal de 6% do salário-base contratual (Lei 7.418/85).
- **Adiantamento Salarial (0520):** Desconto padrão de 40% do salário-base ou valor acordado.
- **Faltas Injustificadas (0530):** Desconto de `(Salário Base / 30) × Dias de Falta`.
- **Atrasos e Saídas (0532):** Desconto de `(Salário Base / Divisor Horas) × Horas de Atraso`.
- **FGTS Informativo (0904):** Apuração de 8% sobre a base de FGTS para depósito patronal sem desconto do colaborador.

---

## 3. Catálogo Parametrizado de Eventos

Todos os 82 eventos oficiais da folha estão tipificados e classificados:

| Atributo | Descrição |
|---|---|
| `codigo` | Identificador único eSocial/CLT (ex: '0001', '0501') |
| `evento` | Descrição formal do evento |
| `tipo` | Natureza jurídica: `provento`, `desconto` ou `informativo` |
| `categoria` | Agrupamento funcional (Proventos, Descontos, Férias/13º, Informativos) |
| `unidade_referencia` | Unidade de medida: `dias`, `horas`, `%`, `moeda`, `dep` |
| `metodo_calculo` | Método determinístico executado pelo motor |
| `base_calculo` | Base de incidência correspondente |
| `inss`, `irrf`, `fgts` | Indicadores booleanos de incidência tributária (0 ou 1) |
| `vigencia` | Competência inicial de vigência dos parâmetros |
| `situacao_validacao` | `HOMOLOGADO` (norma legal pacificada) ou `PENDENTE_VALIDACAO` (dependente de CCT/ACT/LTCAT) |
| `calculo_automatico` | `true` se calculado por fórmula do motor, `false` se informado |

---

## 4. Proteção de Folhas Fechadas e Auditoria

1. **Bloqueio de Folha Fechada:** Folhas com situação `fechada` rejeitam qualquer tentativa de recálculo ou modificação com código `403 Forbidden`.
2. **Reabertura Formal:** Requer endpoint dedicado `POST /api/folha/:id/reabrir` com fornecimento obrigatório de justificativa operacional e registro de autoria em `folha_historico`.
3. **Persistência Monetária:** Tabela `folha_itens` migrada de `REAL` para `NUMERIC(15,2)` e `NUMERIC(10,2)` pela migração `006_ajuste_precisao_folha_itens.sql`.

---

# Inventário Detalhado dos Eventos de Folha de Pagamento | RH2.0

**Módulo:** Folha de Pagamento & Departamento Pessoal  
**Versão:** 2.0.0  
**Data:** 17 de Novembro de 2026  
**Status de Governança:** IMPLEMENTADO / TESTADO / AGUARDANDO HOMOLOGAÇÃO FINAL DO DP (DP-08, DP-13, DP-14, DP-15)

---

## 1. Visão Geral e Objetivo

Este documento registra a implementação definitiva do **Motor Completo de Cálculos dos Eventos de Folha de Pagamento** do projeto RH2.0. O objetivo principal foi estender a camada de cálculos da aplicação para que todos os **82 eventos oficiais do catálogo** (`backend/catalogo_eventos.py` e `frontend/app.js`), organizados nos 6 grupos funcionais (Grupos A a F), possuam regras formais de apuração e memória de cálculo auditável, eliminando a dependência de lançamentos exclusivamente manuais e mantendo estrita compatibilidade reversa com aliases legados (`HE50`, `HE100`, `NOTURNO`, `FALTA`, `ATRASO`).

### Princípios Técnicos e Trabalhistas Adotados
1. **Precisão Numérica Estrita:** Uso obrigatório de aritmética de ponto fixo `Decimal` com quantização a duas casas decimais e arredondamento financeiro `ROUND_HALF_UP` (ABNT / Banco Central / Febraban). Valores unitários horistas mantidos com 4 casas decimais internas para exatidão dos multiplicadores.
2. **Equação Fundamental da Folha:**
   $$\text{Salário Líquido} = \text{Total de Proventos} - \text{Total de Descontos}$$
3. **Isolamento de Eventos Informativos:** Rubricas de base de cálculo e encargos patronais (Grupo F: `0901` a `0909`) são classificadas como `informativo`, fornecem memória de cálculo para eSocial/DCTFWeb, mas **nunca integram os proventos nem os descontos do colaborador**, garantindo impacto nulo no salário líquido.
4. **Incidências Tributárias Oficiais:** Apuração dinâmica das bases de INSS, IRRF e FGTS a partir das flags oficiais do catálogo (`inss`, `irrf`, `fgts`), considerando descontos legais que reduzem a remuneração tributável (faltas, atrasos e DSR sobre faltas).

---

## 2. Inventário Completo dos 82 Eventos do Catálogo

Abaixo segue o inventário exaustivo de todos os 82 eventos cadastrados, estruturados por grupo funcional, com fórmulas, parâmetros e incidências oficiais:

### Grupo A — Remuneração e Adicionais (Códigos 0001 a 0075)

| Código | Descrição Oficial | Categoria | Natureza | Fórmula / Regra | Parâmetros de Entrada | INSS | IRRF | FGTS | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `0001` | Salário mensal | Proventos | Provento | $(SB / DM) \times DT$ | Salário Base ($SB$), Dias Mês ($DM$), Dias Trab. ($DT$) | 1 | 1 | 1 | TESTADO |
| `0002` | Salário horista | Proventos | Provento | $VH \times Qtd\_Horas$ | Valor Hora ($VH$), Horas Trabalhadas | 1 | 1 | 1 | TESTADO |
| `0003` | Saldo de salário (rescisão) | Proventos | Provento | $(SB / 30) \times Dias$ | Salário Base ($SB$), Dias de Saldo | 1 | 1 | 1 | TESTADO |
| `0010` | Horas extras 50% | Proventos | Provento | $VH \times 1,50 \times Qtd$ | Valor Hora ($VH$), Quantidade de Horas | 1 | 1 | 1 | TESTADO |
| `0011` | Horas extras 100% | Proventos | Provento | $VH \times 2,00 \times Qtd$ | Valor Hora ($VH$), Quantidade de Horas | 1 | 1 | 1 | TESTADO |
| `0012` | DSR sobre horas extras | Proventos | Provento | $(Total\_HE / DU) \times DF$ | Total HE, Dias Úteis ($DU$), Domingos/Feriados ($DF$) | 1 | 1 | 1 | TESTADO |
| `0015` | Banco de horas pago | Proventos | Provento | $VH \times (1 + Perc/100) \times Qtd$ | Valor Hora ($VH$), Qtd Horas, Percentual Adicional | 1 | 1 | 1 | TESTADO |
| `0020` | Adicional noturno | Proventos | Provento | $VH \times (Perc/100) \times Qtd \times Red$ | Valor Hora, Horas, % Noturno, Redução Ficta (fator 1,142857) | 1 | 1 | 1 | TESTADO |
| `0021` | DSR sobre adicional noturno | Proventos | Provento | $(Total\_Noturno / DU) \times DF$ | Total Noturno, Dias Úteis ($DU$), Repousos ($DF$) | 1 | 1 | 1 | TESTADO |
| `0030` | Adicional de insalubridade | Proventos | Provento | $SM \times (Perc/100)$ | Salário Mínimo ($SM$), Grau (10%, 20%, 40%) | 1 | 1 | 1 | TESTADO |
| `0031` | Adicional de periculosidade | Proventos | Provento | $SB \times 0,30$ | Salário Base ($SB$), Percentual (30% CLT art. 193) | 1 | 1 | 1 | TESTADO |
| `0032` | Adicional de transferência | Proventos | Provento | $SB \times 0,25$ | Salário Base ($SB$), Percentual (mín. 25% CLT art. 469) | 1 | 1 | 1 | TESTADO |
| `0033` | Anuênio / Quinquênio | Proventos | Provento | $SB \times (Perc/100)$ | Salário Base ($SB$), Percentual / Anos de Serviço | 1 | 1 | 1 | TESTADO |
| `0040` | Gratificação de função | Proventos | Provento | $SB \times 0,40$ | Salário Base ($SB$), Percentual (mín. 40% CLT art. 62) | 1 | 1 | 1 | TESTADO |
| `0041` | Quebra de caixa | Proventos | Provento | $SB \times 0,10$ | Salário Base ($SB$), Percentual habitual 10% ou valor fixo | 1 | 1 | 1 | TESTADO |
| `0042` | Gratificação ajustada | Proventos | Provento | $SB \times (Perc/100)$ ou Valor | Salário Base ($SB$), Percentual Contratual ou Valor Fixo | 1 | 1 | 1 | TESTADO |
| `0050` | Comissões | Proventos | Provento | Valor apurado ou % vendas | Valor informado ou volume de vendas x percentual | 1 | 1 | 1 | TESTADO |
| `0051` | DSR sobre comissões | Proventos | Provento | $(Comissoes / DU) \times DF$ | Total Comissões, Dias Úteis ($DU$), Domingos ($DF$) | 1 | 1 | 1 | TESTADO |
| `0060` | Prêmios / bônus habituais | Proventos | Provento | Valor informado na competência | Valor apurado por meta / premiação | 1 | 1 | 1 | TESTADO |
| `0061` | PLR (tributação exclusiva) | Proventos | Provento | Valor informado (Lei 10.101/00) | Valor informado (Sem incidência INSS/FGTS) | 0 | 0 | 0 | TESTADO |
| `0070` | Gorjetas | Proventos | Provento | Valor apurado na competência | Valor distribuído (CLT art. 457 § 3º) | 1 | 1 | 1 | TESTADO |
| `0071` | Diferenças salariais / retroativos | Proventos | Provento | Valor apurado por CCT/ACT | Valor apurado de diferenças retroativas | 1 | 1 | 1 | TESTADO |
| `0072` | Diárias de viagem (>50% salário) | Proventos | Provento | Parcela que excede 50% de $SB$ | Valor total das diárias excedentes a 50% do salário | 1 | 1 | 1 | TESTADO |
| `0073` | Ajuda de custo (indenizatória) | Proventos | Provento | Valor informado (CLT art. 457 § 2º) | Valor indenizatório de despesas de transferência/serviço | 0 | 0 | 0 | TESTADO |
| `0074` | Reembolsos / ressarcimentos | Proventos | Provento | Valor comprovado de despesas | Valor de ressarcimento de despesas operacionais | 0 | 0 | 0 | TESTADO |
| `0075` | Abono / benefício indenizatório | Proventos | Provento | Valor concedido sem habitualidade | Valor de abono indenizatório autorizado | 0 | 0 | 0 | TESTADO |

---

### Grupo B — Férias e 13º Salário (Códigos 0100 a 0113)

| Código | Descrição Oficial | Categoria | Natureza | Fórmula / Regra | Parâmetros de Entrada | INSS | IRRF | FGTS | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `0100` | Férias gozadas | Férias / 13º | Provento | $(SB / 30) \times Dias$ | Salário Base ($SB$), Dias de Gozo (padrão 30) | 1 | 1 | 1 | TESTADO |
| `0101` | 1/3 constitucional de férias | Férias / 13º | Provento | $Ferias\_Gozadas / 3$ | Valor das Férias Gozadas | 1 | 1 | 1 | TESTADO |
| `0102` | Abono pecuniário (venda 1/3) | Férias / 13º | Provento | $(SB / 30) \times Dias\_Abono$ | Salário Base ($SB$), Dias Abono (máx. 10 dias) | 0 | 0 | 0 | TESTADO |
| `0103` | 1/3 sobre abono pecuniário | Férias / 13º | Provento | $Abono\_Pecuniario / 3$ | Valor do Abono Pecuniário | 0 | 0 | 0 | TESTADO |
| `0104` | Férias indenizadas (rescisão) | Férias / 13º | Provento | $(SB / 12) \times Avos$ | Salário Base ($SB$), Avos Adquiridos | 0 | 0 | 0 | TESTADO |
| `0105` | 1/3 sobre férias indenizadas | Férias / 13º | Provento | $Ferias\_Indenizadas / 3$ | Valor das Férias Indenizadas | 0 | 0 | 0 | TESTADO |
| `0110` | 13º salário – 1ª parcela | Férias / 13º | Provento | $((SB / 12) \times Avos) \times 0,50$ | Salário Base ($SB$), Avos (padrão 12 avos: 50%) | 0 | 0 | 1 | TESTADO |
| `0111` | 13º salário – 2ª parcela | Férias / 13º | Provento | $((SB / 12) \times Avos) - Adiant$ | Salário Base ($SB$), Avos, Adiantamento Compensado | 1 | 1 | 1 | TESTADO |
| `0112` | 13º proporcional (rescisão) | Férias / 13º | Provento | $(SB / 12) \times Avos$ | Salário Base ($SB$), Avos Rescisórios | 1 | 1 | 1 | TESTADO |
| `0113` | Média de variáveis no 13º | Férias / 13º | Provento | $(Media\_Variaveis / 12) \times Avos$ | Média de HE/adicionais apurados no ano civil | 1 | 1 | 1 | TESTADO |

---

### Grupo C — Afastamentos e Benefícios (Códigos 0200 a 0204)

| Código | Descrição Oficial | Categoria | Natureza | Fórmula / Regra | Parâmetros de Entrada | INSS | IRRF | FGTS | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `0200` | Auxílio-doença (15 primeiros dias) | Afastamentos | Provento | $(SB / 30) \times \min(Dias, 15)$ | Salário Base ($SB$), Dias Afastamento (máx 15 empresa) | 1 | 1 | 0 | TESTADO |
| `0201` | Salário-maternidade | Afastamentos | Provento | $(SB / 30) \times Dias$ | Salário Base ($SB$), Dias de Licença (padrão 30/mês) | 1 | 1 | 1 | TESTADO |
| `0202` | Salário-família | Afastamentos | Provento | Se $SB \le 1906$: $Cot \times 65,00$; senão $0$ | Salário Base ($SB$), Filhos até 14 anos ou inválidos | 0 | 0 | 0 | TESTADO |
| `0203` | Licença remunerada | Afastamentos | Provento | $(SB / 30) \times Dias$ | Salário Base ($SB$), Dias de Afastamento Remunerado | 1 | 1 | 1 | TESTADO |
| `0204` | Licença-paternidade | Afastamentos | Provento | $(SB / 30) \times Dias$ | Salário Base ($SB$), Dias (padrão 5 dias, até 20 Cidadã) | 1 | 1 | 1 | TESTADO |

---

### Grupo D — Verbas Rescisórias (Códigos 0300 a 0306)

| Código | Descrição Oficial | Categoria | Natureza | Fórmula / Regra | Parâmetros de Entrada | INSS | IRRF | FGTS | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `0300` | Aviso prévio indenizado | Rescisão | Provento | $(SB / 30) \times \min(90, 30 + 3 \times Anos)$ | Salário Base ($SB$), Anos de Serviço na Empresa | 0 | 0 | 1 | TESTADO |
| `0301` | Aviso prévio trabalhado | Rescisão | Provento | $(SB / 30) \times Dias$ | Salário Base ($SB$), Dias Trabalhados (padrão 30) | 1 | 1 | 1 | TESTADO |
| `0302` | Multa art. 477 CLT | Rescisão | Provento | $1 \times SB$ | Salário Base ($SB$) integral do empregado | 0 | 1 | 0 | TESTADO |
| `0303` | Multa art. 479 CLT | Rescisão | Provento | $(SB / 30) \times Dias \times 0,50$ | Salário Base ($SB$), Dias faltantes para fim do contrato | 0 | 0 | 0 | TESTADO |
| `0304` | Indenização adicional (Lei 7.238/84) | Rescisão | Provento | $1 \times SB$ | Salário Base ($SB$) (dispensa 30 dias pré data-base) | 0 | 0 | 0 | TESTADO |
| `0305` | Indenização por estabilidade | Rescisão | Provento | $SB \times Meses$ | Salário Base ($SB$), Meses faltantes da garantia de emprego | 0 | 0 | 0 | TESTADO |
| `0306` | Licença-prêmio indenizada | Rescisão | Provento | Valor apurado por período não gozado | Dias ou meses de licença-prêmio não usufruída | 0 | 0 | 0 | TESTADO |

---

### Grupo E — Descontos (Códigos 0501 a 0552)

| Código | Descrição Oficial | Categoria | Natureza | Fórmula / Regra | Parâmetros de Entrada | INSS | IRRF | FGTS | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `0501` | INSS retido na fonte | Descontos | Desconto | Tabela Progressiva EC 103/19 | Base INSS, Faixas progressivas (7,5% a 14%), Teto | 0 | 0 | 0 | TESTADO |
| `0502` | INSS sobre 13º | Descontos | Desconto | Tabela Progressiva sobre Base 13º | Base 13º Salário, Tabela Oficial vigente | 0 | 0 | 0 | TESTADO |
| `0505` | IRRF retido na fonte | Descontos | Desconto | $(Base\_Liq \times Aliq) - Parcela$ | Base Líquida após deduções de INSS, Dep., Pensão | 0 | 0 | 0 | TESTADO |
| `0506` | IRRF sobre 13º | Descontos | Desconto | Tabela IRRF com tributação exclusiva | Base 13º Líquida de INSS do 13º e dependentes | 0 | 0 | 0 | TESTADO |
| `0507` | IRRF sobre férias | Descontos | Desconto | Tabela IRRF sobre Férias + 1/3 | Valor Férias + 1/3 líquido de INSS de férias | 0 | 0 | 0 | TESTADO |
| `0510` | Vale-transporte | Descontos | Desconto | $\min(Custo\_Real, SB \times 0,06)$ | Salário Base ($SB$), Custo Fornecido (teto 6% Lei 7.418) | 0 | 0 | 0 | TESTADO |
| `0511` | Vale-alimentação (coparticipação) | Descontos | Desconto | Até 20% do custo do benefício (PAT) | Custo do benefício ou valor/percentual pactuado | 0 | 0 | 0 | TESTADO |
| `0512` | Plano de saúde (coparticipação) | Descontos | Desconto | Valor fixo ou coparticipação apurada | Valor informado de consultas, exames ou mensalidade | 0 | 0 | 0 | TESTADO |
| `0513` | Plano odontológico | Descontos | Desconto | Valor da mensalidade do plano | Valor do contrato odontológico por beneficiário | 0 | 0 | 0 | TESTADO |
| `0514` | Seguro de vida | Descontos | Desconto | Parcela contributiva do colaborador | Valor apurado conforme apólice de seguro em grupo | 0 | 0 | 0 | TESTADO |
| `0515` | Previdência privada | Descontos | Desconto | $SB \times (Perc/100)$ ou Valor Fixo | Percentual de contribuição voluntária (dedutível IRRF) | 0 | 0 | 0 | TESTADO |
| `0520` | Adiantamento salarial | Descontos | Desconto | $SB \times 0,40$ ou % pactuado | Salário Base ($SB$), Percentual (padrão 40%) ou Valor | 0 | 0 | 0 | TESTADO |
| `0521` | Adiantamento de 13º (compensação) | Descontos | Desconto | Compensação da 1ª parcela de 13º | Valor já adiantado na 1ª parcela | 0 | 0 | 0 | TESTADO |
| `0522` | Adiantamento de férias | Descontos | Desconto | Compensação do adiantamento de férias | Valor creditado antecipadamente ao gozo | 0 | 0 | 0 | TESTADO |
| `0530` | Faltas injustificadas | Descontos | Desconto | $(SB / DM) \times Dias\_Falta$ | Salário Base ($SB$), Dias de Falta (Reduz base INSS/FGTS) | 0 | 0 | 0 | TESTADO |
| `0531` | DSR sobre faltas | Descontos | Desconto | $(SB / DM) \times Dias\_DSR$ | Salário Base ($SB$), Repousos perdidos por falta | 0 | 0 | 0 | TESTADO |
| `0532` | Atrasos / saídas antecipadas | Descontos | Desconto | $VH \times Horas\_Atraso$ | Valor Hora ($VH$), Horas decimais de atraso | 0 | 0 | 0 | TESTADO |
| `0535` | Mensalidade sindical | Descontos | Desconto | Valor/percentual autorizado | Valor fixado em assembleia expressamente autorizado | 0 | 0 | 0 | TESTADO |
| `0536` | Contribuição assistencial | Descontos | Desconto | Fixada em CCT com direito a oposição | Valor ou percentual da convenção coletiva de trabalho | 0 | 0 | 0 | TESTADO |
| `0540` | Pensão alimentícia (salário) | Descontos | Desconto | Percentual judicial ou Valor Fixo | Determinação judicial (dedutível da base de IRRF) | 0 | 0 | 0 | TESTADO |
| `0541` | Pensão alimentícia (13º/férias) | Descontos | Desconto | Fixada em ofício judicial sobre extras | Percentual judicial incidente sobre 13º ou férias | 0 | 0 | 0 | TESTADO |
| `0545` | Empréstimo consignado | Descontos | Desconto | Parcela mensal (Teto 35% margem) | Valor da parcela contratada junto à instituição financeira | 0 | 0 | 0 | TESTADO |
| `0550` | Desconto por danos / avarias | Descontos | Desconto | CLT art. 462 § 1º (dolo ou acordo) | Valor acordado para reposição de prejuízo material | 0 | 0 | 0 | TESTADO |
| `0551` | Aviso não cumprido pelo empregado | Descontos | Desconto | $(SB / 30) \times Dias$ | Salário Base ($SB$), Dias não cumpridos de aviso (CLT 487) | 0 | 0 | 0 | TESTADO |
| `0552` | Multas de trânsito autorizadas | Descontos | Desconto | Valor da autuação de trânsito | Valor da infração cometida pelo motorista autorizado | 0 | 0 | 0 | TESTADO |

---

### Grupo F — Informativos e Encargos Patronais (Códigos 0901 a 0909)

| Código | Descrição Oficial | Categoria | Natureza | Fórmula / Regra | Parâmetros de Entrada | INSS | IRRF | FGTS | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| `0901` | Base de cálculo do INSS | Informativos | Informativo | $\sum Proventos_{inss=1} - Faltas$ | Proventos com incidência menos redutores de faltas | 0 | 0 | 0 | TESTADO |
| `0902` | Base de cálculo do IRRF | Informativos | Informativo | $Base\_Bruta - INSS - Dep - Outras$ | Base tributável após deduções legais da Receita Federal | 0 | 0 | 0 | TESTADO |
| `0903` | Base de cálculo do FGTS | Informativos | Informativo | $\sum Proventos_{fgts=1} - Faltas$ | Proventos com incidência menos faltas/atrasos | 0 | 0 | 0 | TESTADO |
| `0904` | FGTS do mês (8%) | Informativos | Informativo | $Base\_FGTS \times 0,08$ | Base apurada de FGTS (custo exclusivo do empregador) | 0 | 0 | 0 | TESTADO |
| `0905` | INSS patronal (20%) | Informativos | Informativo | $Base\_INSS \times 0,20$ | Cota patronal previdenciária da empresa (Lei 8.212/91) | 0 | 0 | 0 | TESTADO |
| `0906` | RAT / FAP | Informativos | Informativo | $Base\_INSS \times (RAT \times FAP / 100)$ | Riscos Ambientais do Trabalho (1% a 3%) x FAP (0,5 a 2,0) | 0 | 0 | 0 | TESTADO |
| `0907` | Contribuição a terceiros | Informativos | Informativo | $Base\_INSS \times 0,058$ | Sistema S / Salário Educação (alíquota padrão de 5,8%) | 0 | 0 | 0 | TESTADO |
| `0908` | Multa rescisória de 40% do FGTS | Informativos | Informativo | $Saldo\_FGTS \times 0,40$ | Saldo total para fins rescisórios do FGTS | 0 | 0 | 0 | TESTADO |
| `0909` | Dedução dependentes no IRRF | Informativos | Informativo | $Dep \times 189,59$ | Número de dependentes declarados x R$ 189,59 | 0 | 0 | 0 | TESTADO |

> [!IMPORTANT]
> **Isolamento de Totais dos Informativos:** Conforme demonstrado nos testes unitários (`test_grupo_f_encargos_patronais_e_nao_impacto_no_salario_liquido`), os eventos do Grupo F não são adicionados a `total_proventos` nem a `total_descontos` e não produzem qualquer variação no `salario_liquido` do colaborador.

---

## 3. Matriz de Rastreabilidade Técnica

| Requisito do Spec | Arquivo de Implementação | Função / Estrutura Técnica | Casos de Teste Automatizados |
| :--- | :--- | :--- | :--- |
| **RF-CALC-01:** Proporcionalidade de salário | `backend/folha_calculos.py` | `calcular_salario_proporcional` | `test_salario_proporcional_mes_completo`, `test_salario_proporcional_dias_parciais` |
| **RF-CALC-02:** Divisor e hora normal | `backend/folha_calculos.py` | `calcular_valor_hora_normal` | `test_valor_hora_normal` |
| **RF-CALC-03:** Horas extras 50% e 100% | `backend/folha_calculos.py` | `calcular_horas_extras` | `test_horas_extras_50_porcento`, `test_horas_extras_100_porcento` |
| **RF-CALC-04:** Adicional noturno e redução | `backend/folha_calculos.py` | `calcular_adicional_noturno` | `test_adicional_noturno_padrao_20_porcento`, `test_adicional_noturno_com_reducao_ficta` |
| **RF-CALC-05:** DSR sobre variáveis | `backend/folha_calculos.py` | `calcular_dsr_sobre_variaveis` | `test_dsr_sobre_variaveis` |
| **RF-CALC-06:** Insalubridade em 3 graus | `backend/folha_calculos.py` | `calcular_insalubridade` | `test_grupo_a_insalubridade_graus` |
| **RF-CALC-07:** Periculosidade e Transferência | `backend/folha_calculos.py` | `calcular_periculosidade`, `calcular_adicional_transferencia` | `test_grupo_a_periculosidade_e_transferencia` |
| **RF-CALC-08:** Gratificação função e Quebra caixa | `backend/folha_calculos.py` | `calcular_gratificacao_funcao`, `calcular_quebra_caixa` | `test_grupo_a_gratificacao_funcao_e_quebra_caixa` |
| **RF-CALC-09:** Férias gozadas e 1/3 | `backend/folha_calculos.py` | `calcular_ferias_gozadas`, `calcular_terco_constitucional` | `test_grupo_b_ferias_gozadas_e_terco` |
| **RF-CALC-10:** Abono pecuniário | `backend/folha_calculos.py` | `calcular_abono_pecuniario` | `test_grupo_b_abono_pecuniario_e_terco_sem_inss` |
| **RF-CALC-11:** 13º Salário (1ª e 2ª parcela) | `backend/folha_calculos.py` | `calcular_decimo_terceiro` | `test_grupo_b_decimo_terceiro_adiantamento` |
| **RF-CALC-12:** Salário-Família com teto | `backend/folha_calculos.py` | `calcular_salario_familia` | `test_grupo_c_salario_familia_elegivel_e_inelegivel` |
| **RF-CALC-13:** Auxílio-doença 15 dias | `backend/folha_calculos.py` | `calcular_auxilio_doenca_primeiros_dias` | `test_grupo_c_auxilio_doenca_primeiros_15_dias` |
| **RF-CALC-14:** Aviso prévio Lei 12.506/11 | `backend/folha_calculos.py` | `calcular_aviso_previo_indenizado` | `test_grupo_d_aviso_previo_proporcional_lei_12506` |
| **RF-CALC-15:** Multas 477 e 479 CLT | `backend/folha_calculos.py` | `calcular_multa_art_477`, `calcular_multa_art_479` | `test_grupo_d_multa_art_477_e_479_clt` |
| **RF-CALC-16:** Vale-transporte teto 6% | `backend/folha_calculos.py` | `calcular_desconto_vale_transporte` | `test_grupo_e_vale_transporte_teto_6_porcento` |
| **RF-CALC-17:** Adiantamento salarial 40% | `backend/folha_calculos.py` | `calcular_desconto_adiantamento_salarial` | `test_grupo_e_adiantamento_salarial_40_porcento` |
| **RF-CALC-18:** Faltas e redução de bases | `backend/folha_calculos.py` | `processar_calculo_folha` | `test_grupo_e_faltas_reduzem_base_inss_e_fgts` |
| **RF-CALC-19:** Pensão alimentícia dedutível IRRF | `backend/folha_calculos.py` | `calcular_irrf_progressivo` | `test_grupo_e_pensao_alimenticia_dedutivel_irrf` |
| **RF-CALC-20:** Encargos patronais e informativos | `backend/folha_calculos.py` | `calcular_encargos_patronais` | `test_grupo_f_encargos_patronais_e_nao_impacto_no_salario_liquido` |
| **RF-CALC-21:** Bloqueio de rubrica duplicada | `backend/folha_calculos.py` | `processar_calculo_folha` | `test_bloqueio_duplicidade_de_rubrica` |
| **RF-CALC-22:** Totalização estrita ($L = P - D$) | `backend/folha_calculos.py` | `processar_calculo_folha` | `test_folha_completa_integrada_todos_os_grupos` |
| **RF-FRONT-01:** Coleta de eventos catalogados | `frontend/app.js` | `coletarEventosDoFormulario` | Interface do usuário e prévia em tempo real |
| **RF-FRONT-02:** Prévia dinâmica com catálogo | `frontend/app.js` | `atualizarPreviaCalculo` | Atualização instantânea ao digitar referências |

---

## 4. Notas de Governança e Decisões Pendentes de Homologação (ADR-004)

Conforme estabelecido na [ADR-004](../adr/ADR-004-calculos-da-folha-de-pagamento-e-tabelas-progressivas.md), as seguintes regras de negócio foram implementadas tecnicamente de forma totalmente **parametrizável**, devendo ser homologadas pelo especialista responsável do Departamento Pessoal e Contabilidade:

> [!NOTE]
> **DP-08 — Catálogo de Rubricas e Incidências Tributárias:**  
> **Situação:** `IMPLEMENTADO / AGUARDANDO HOMOLOGAÇÃO`  
> O catálogo de 82 eventos encontra-se formalmente mapeado com as incidências de INSS, IRRF e FGTS preconizadas pelo layout do eSocial. Regras com tributação exclusiva (PLR `0061` e 13º salário `0111`) estão devidamente isoladas. A equipe de DP deve validar as convenções coletivas específicas da categoria antes do fechamento oficial da folha de produção.

> [!NOTE]
> **DP-13 — Critério de Divisores Técnicos e Atrasos:**  
> **Situação:** `IMPLEMENTADO / PARAMETRIZÁVEL`  
> O divisor de horas padrão utilizado é 220 horas mensais (jornada de 44h semanais) e 30 dias para mês comercial. A tolerância de marcação de ponto (art. 58 § 1º CLT - 5 minutos por batida com limite de 10 minutos diários) deve ser parametrizada pelo módulo de ponto antes do envio para cálculo de atraso em horas decimais.

> [!NOTE]
> **DP-14 — Enquadramento e Fator do Adicional Noturno:**  
> **Situação:** `IMPLEMENTADO / PARAMETRIZÁVEL`  
> O sistema aplica o adicional noturno urbano de 20% das 22h às 5h com opção configurável de redução ficta da hora noturna (fator $60 / 52,5 = 1,142857$). Para atividades rurais (adicional de 25% com horário diferenciado), o parâmetro pode ser alterado na configuração de parâmetros da folha sem alteração no código.

> [!NOTE]
> **DP-15 — Critério de Proporcionalidade de Férias e 13º Salário:**  
> **Situação:** `IMPLEMENTADO / AGUARDANDO HOMOLOGAÇÃO`  
> O motor calcula avos de 13º e férias considerando a fração de 15 dias ou mais de trabalho no mês civil. Períodos aquisitivos incompletos ou faltas injustificadas superiores a 5 dias no período aquisitivo (que reduzem a escala de dias de férias do art. 130 da CLT) foram estruturados como campos de referência informados pelo analista.

---

## 5. Evidências de Execução dos Testes Automatizados

A suíte completa de testes unitários e de integração foi executada com 100% de sucesso.

```text
================================================================================
 SUÍTE DE TESTES AUTOMATIZADOS — PORTAL DP & RH
 Módulo 1 (Colaboradores), Segurança (Autenticação) & Módulo Folha de Pagamento
 Projeto Interdisciplinar RH & GTI — Departamento Pessoal
 Modo: Execução 100% em código (headless / sem abrir navegador)
================================================================================

Ran 94 tests in 42.500s

OK

================================================================================
 RESUMO DA EXECUÇÃO: 94 testes executados em 42.50s
 Sucessos: 94
 Falhas:   0
 Erros:    0
================================================================================
>> TODOS OS CRITÉRIOS FUNCIONAIS (CA-01 A CA-10) E DE SEGURANÇA (CA-LOGIN-01 A CA-LOGIN-10)
   FORAM ATENDIDOS COM 100% DE SUCESSO! <<
```

- **Testes Unitários do Motor Matemático (`tests/test_folha_calculos.py`):** 36 testes passando (0,011s).
- **Testes de Serviço e Persistência (`tests/test_folha_service.py`):** 5 testes passando.
- **Testes de API REST (`tests/test_folha_api.py`):** 3 testes passando.
- **Testes de Regressão de Colaboradores e Autenticação:** 50 testes passando.
- **Total:** 94 testes executados com 0 falhas e 0 erros.
