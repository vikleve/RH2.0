# 06 — Escopo Funcional e Regras Trabalhistas da Folha (CLT Brasil)

**Projeto:** RH2.0 — Portal de Departamento Pessoal & Folha de Pagamento  
**Data:** 18/11/2026

---

## 1. Delimitação do Cenário Trabalhista (Seção 9)

O sistema **RH2.0** é projetado para um **cenário brasileiro delimitado de folha de pagamento mensal sob regime CLT (Consolidação das Leis do Trabalho — Decreto-Lei nº 5.452/1943)**, Previdência Social (EC nº 103/2019) e Receita Federal do Brasil (IRRF), com foco em transparência de memória de cálculo e parametrização por vigência.

### Princípios Obrigatórios de Implementação
1. **Separação Estrita da Interface:** Toda a lógica matemática reside exclusivamente em `backend/folha_calculos.py` e no catálogo `backend/catalogo_eventos.py`, operando com `decimal.Decimal` e arredondamento financeiro `ROUND_HALF_UP` (2 casas decimais para moeda, 4 casas decimais para valor-hora).
2. **Parametrização com Vigência Temporal:** As variáveis de cálculo (divisor padrão de 220h, dias comerciais de 30 dias, percentuais de HE 50%/100%, adicional noturno 20%, redução ficta 1,142857, alíquota de FGTS 8%, teto do INSS e dedução por dependente do IRRF) são lidas da tabela `folha_parametros` vinculada à folha (`folhas_pagamento.parametro_id`).
3. **Equação Fundamental Invariante:**
   $$\text{Salário Líquido} = \text{Total de Proventos} - \text{Total de Descontos}$$
   Eventos de natureza `informativo` (bases de cálculo e encargos patronais como FGTS 8%, INSS Patronal 20%, RAT/FAP e Terceiros) jamais somam aos proventos nem aos descontos do trabalhador.

---

## 2. Classificação das Regras Trabalhistas por Escopo (Seção 9)

| Rubrica / Regra Trabalhista | Classificação de Escopo | Estado no Código (`backend/folha_calculos.py`) | Fórmula e Regra Aplicada |
|---|---|---|---|
| **Salário-base e Salário Proporcional** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0001` / `001`) | $\text{Salário Proporcional} = (\text{Salário Base} / \text{Dias Mês}) \times \text{Dias Trabalhados}$. |
| **Valor da Hora Normal** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada | $\text{Valor Hora} = \text{Salário Base} / \text{Divisor Mensal (220h)}$. |
| **Horas Extras (50% e 100%)** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0010`/`101`, `0011`/`102`) | $\text{HE} = \text{Valor Hora} \times (1 + \text{Percentual}/100) \times \text{Qtd Horas}$ (CLT art. 59 § 1º). Incide INSS, IRRF e FGTS. |
| **Adicional Noturno e Redução Ficta** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0020`/`103`) | $\text{Adic. Noturno} = \text{Valor Hora} \times (\text{Percentual}/100) \times (\text{Qtd Horas} \times \text{Fator Redução})$ (CLT art. 73: 20% urbano; hora ficta $52\text{m}30\text{s} \Rightarrow \text{fator } 1{,}142857$ parametrizável). |
| **DSR sobre Variáveis** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0012`/`105`, `0021`, `0051`) | $\text{DSR} = (\text{Total Variáveis} / \text{Dias Úteis}) \times \text{Domingos e Feriados}$ (Lei nº 605/1949 e Súmula 172 TST). |
| **Adicionais Legais (Insalubridade, Periculosidade, Transferência, Função)** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0030` a `0042`) | Insalubridade: 10%/20%/40% sobre Salário Mínimo (CLT art. 192); Periculosidade: 30% sobre Salário-Base (CLT art. 193); Transferência: 25% (CLT art. 469); Gratificação de Função: 40% (CLT art. 62). |
| **Faltas Injustificadas e Atrasos** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0530`/`201`, `0531`, `0532`/`202`) | Faltas: $(\text{Salário Base} / \text{Dias Mês}) \times \text{Dias Falta}$; Atrasos: $\text{Valor Hora} \times \text{Horas Atraso}$. Reduzem a base de cálculo de INSS, FGTS e IRRF. |
| **Descontos Legais e Convencionais (VT, VR, Saúde, Adiantamento, Pensão, Consignado)** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0510` a `0552`) | Vale-Transporte (`0510`): limitado a 6% do salário-base ou custo real (Lei nº 7.418/1985); Pensão Alimentícia (`0540`) e Previdência Privada (`0515`) deduzem da base do IRRF. |
| **INSS Progressivo por Faixas** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0501`/`501`) | Apuração progressiva faixa a faixa (7,5%, 9%, 12%, 14%) sobre $\text{Base INSS} = \sum \text{Proventos}_{\text{inss}=1} - \text{Faltas/Atrasos}$, limitada ao teto previdenciário parametrizado (R$ 8.157,41). |
| **IRRF Progressivo na Fonte** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0505`/`502`) | $\text{Base Tributável} = \text{Base Bruta IRRF} - \text{INSS} - (\text{Nº Dependentes} \times \text{R\$ 189,59}) - \text{Pensão/Prev. Privada}$. $\text{IRRF} = (\text{Base Tributável} \times \text{Alíquota}) - \text{Parcela a Deduzir}$ (faixas de 0%, 7,5%, 15%, 22,5% e 27,5%). |
| **FGTS Mensal (8%) e Encargos Patronais** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada (`0901` a `0909` / `901`) | $\text{FGTS} = \text{Base FGTS} \times 8\%$ (Lei nº 8.036/1990), gravado como item informativo e no cabeçalho (`valor_fgts_informativo`), sem descontar do empregado. |
| **Admissões no Mês (Salário Proporcional)** | **Obrigatória no 1º Escopo (V1)** | Implementada e testada | Informando `dias_trabalhados < 30` no lançamento da folha da competência de admissão, o sistema calcula o salário proporcional automaticamente. |
| **Rubricas de Férias, 13º Salário, Afastamentos (15 dias / Salário-Família) e Verbas Rescisórias** | **Suportada via Catálogo no 1º Escopo / Fluxo Autônomo em Etapa Posterior** | Fórmulas implementadas e testadas no motor (`0100`–`0113`, `0200`–`0204`, `0300`–`0306`) | Podem ser lançadas como eventos na folha pelo catálogo; porém, a gestão autônoma de períodos aquisitivos de férias, cronograma de afastamentos INSS e termo de rescisão (TRCT separado) ficam para etapa posterior (V2). |
| **Integração com Relógio de Ponto Eletrônico (AFD/AFDT) e Banco de Horas Automático** | **Necessária em Etapa Posterior (V2)** | Fora da V1 (`RF-16`, `RF-25`, `DP-05`, `DP-07`) | Na V1, o operador informa o total de horas extras, noturnas, faltas e atrasos apurados no período. |
| **Transmissão ao eSocial, DCTFWeb, FGTS Digital e Pagamento Bancário (CNAB 240)** | **Explicitamente Fora do Escopo** | Fora do escopo (`RF-45`, `RF-54`) | O fechamento no RH2.0 é um **fechamento operacional e contábil interno**; não realiza transmissão eletrônica a órgãos governamentais nem liquidação bancária. |

---

## 3. Tabela de Parâmetros Padrão Vigentes no Sistema (`PADRAO_CLT_2026`)

| Parâmetro | Valor Padrão Configurado | Parametrizável no Banco (`folha_parametros`) |
|---|---|---|
| Divisor Mensal Padrão | `220,00 horas` | Sim (`horas_mensais_padrao`) |
| Dias do Mês Comercial | `30 dias` | Sim (`dias_mes_padrao`) |
| Hora Extra Padrão / Extraordinária | `50,00%` / `100,00%` | Sim (`percentual_he_padrao` / `percentual_he_extra`) |
| Adicional Noturno Urbano | `20,00%` | Sim (`percentual_adicional_noturno`) |
| Redução Ficta da Hora Noturna | `Opcional (Fator 1,142857)` | Sim (`aplicar_reducao_noturna` / `fator_reducao_noturna`) |
| Alíquota FGTS | `8,00%` | Sim (`aliquota_fgts`) |
| Teto Salário de Contribuição INSS | `R$ 8.157,41` | Sim (`teto_inss`) |
| Dedução Mensal por Dependente IRRF | `R$ 189,59` | Sim (`deducao_dependente_irrf`) |

---

## 4. Declaração de Limites de Conformidade Legal

1. **Fechamento Interno vs. Obrigações Acessórias:** O botão "Fechar Folha" / "Fechar Competência" bloqueia edições no banco de dados Neon e consolida os demonstrativos internos para conferência e pagamento, mas **não substitui** o envio dos eventos periódicos (`S-1200`, `S-1210`, `S-1299`) ao eSocial, nem a emissão de DARF Previdenciário/IRRF via DCTFWeb ou guia do FGTS Digital.
2. **Homologação Contábil/DP:** As faixas progressivas de INSS e IRRF, bem como regras específicas de Convenção Coletiva de Trabalho (CCT/ACT da categoria), devem ser conferidas pelo profissional responsável de Departamento Pessoal/Contabilidade na tela de **Parâmetros da Folha** antes do processamento produtivo de cada competência (conforme ressalvas `DP-08`, `DP-13`, `DP-14` e `DP-15`).
