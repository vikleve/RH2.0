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
