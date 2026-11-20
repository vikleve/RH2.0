# ADR-004: Módulo de Folha de Pagamento e Regras de Cálculos Trabalhistas

## Status
Implementado com Motor Centralizado (SPEC-PATCH-FOLHA-001) / Aguardando Homologação de Negócio (DP-08, DP-14, DP-15)

## Data
Atualizado em 2026-11-18 (Versão 2.0 — Centralização de Motor e Deduplicação)

## Contexto
O cálculo de folha de pagamento no Brasil é regido pela Consolidação das Leis do Trabalho (CLT), legislação previdenciária e regulamentação da Receita Federal. Erros de arredondamento, faixas incorretas ou falta de rastreabilidade de memórias de cálculo podem gerar passivos trabalhistas e fiscais. Conforme identificado no documento oficial de requisitos (`Requisitos_Sistema_Folha.docx`), as decisões pendentes DP-08, DP-14 e DP-15 demandam homologação formal por parte do especialista de Departamento Pessoal e Contabilidade antes de serem declaradas definitivas.

Com a SPEC-PATCH-FOLHA-001, foi corrigida a divergência entre frontend e backend, centralizando 100% da inteligência de cálculo no backend NestJS (`folha-calculos.engine.ts`), eliminando fórmulas improvisadas no cliente e implementando simulação não-destrutiva e recálculo transacional.

## Decisão
Estruturar tecnicamente o módulo de Folha de Pagamento com as seguintes premissas arquiteturais preliminares, mantendo-as parametrizáveis e auditáveis:
1. **Precisão Numérica Estrita (NUMERIC no PostgreSQL):** Todos os cálculos utilizam `decimal.js` com arredondamento comercial `ROUND_HALF_UP`. Conforme Migration `006_ajuste_precisao_folha_itens.sql`, as colunas `referencia`, `valor_unitario` e `valor_total` em `folha_itens` foram convertidas de `REAL` para `NUMERIC(15,2)` e `NUMERIC(10,2)`, eliminando qualquer divergência de ponto flutuante IEEE 754.
2. **Tabela Progressiva de INSS:** Aplicação da alíquota progressiva oficial por faixas salariais (7,5%, 9%, 12%, 14%) com faixas nominais oficiais (R$ 1.518,00, R$ 2.793,88, R$ 4.190,83 e teto R$ 8.157,41 com desconto teto de R$ 951,63).
3. **Cálculo Progressivo de IRRF:** Dedução prévia da contribuição de INSS e dedução legal por dependente homologado (R$ 189,59/dependente), aplicando a tabela progressiva com parcela a deduzir.
4. **Catálogo Oficial e Deduplicação:**
   - Catálogo com 82 rubricas sincronizadas entre frontend e backend.
   - Cada rubrica possui situação formal (`HOMOLOGADO` vs `PENDENTE_VALIDACAO`).
   - Deduplicação automática: lançamentos avulsos de Salário Mensal (`0001`), INSS (`0501`) ou IRRF (`0505`) unificam com as rubricas oficiais calculadas pelo motor, impedindo dupla contagem.
5. **Endpoints Especializados de Simulação e Recálculo:**
   - `POST /api/folha/simular`: Executa o motor em memória, retorna totais, rubricas e memórias de cálculo sem tocar no banco de dados e sem efeitos colaterais.
   - `POST /api/folha/:id/recalcular`: Reprocessa folha aberta em transação atômica (`BEGIN ... COMMIT / ROLLBACK`), atualizando cabeçalho, itens e registrando evento `RECALCULO` em `folha_historico`.
6. **Encargos e Variáveis Trabalhistas:**
   - Horas extras com adicional técnico de 50% e 100% (parametrizável para percentuais acordados em CCT/ACT).
   - Adicional noturno urbano (20%) com cálculo técnico de redução ficta da hora noturna (fator ~1,142857), aguardando homologação do enquadramento rural/urbano da empresa (DP-02, DP-14).
   - DSR (Descanso Semanal Remunerado) sobre horas extras e variáveis.
   - Desconto proporcional de faltas integrais e horas de atraso.
   - FGTS com alíquota padrão de 8% calculado em caráter informativo (sem desconto do colaborador).
7. **Ciclo de Vida da Folha e Rastreabilidade:**
   - Estados formais: `Aberta`, `Calculada`, `Fechada` e `Cancelada`.
   - **Bloqueio de Duplicidade:** Chave de unicidade `(colaborador_id, competencia)`.
   - **Fechamento e Trilha de Auditoria:** Uma vez fechada, a folha bloqueia novas edições ordinárias (retorna HTTP 403 Forbidden); qualquer reabertura exige justificativa formal e identificação do responsável em `folha_historico`.

## Consequências e Ressalvas
- A implementação técnica provê memória de cálculo detalhada e transparente para conferência da equipe de DP/RH, contabilidade e professor orientador.
- **Ressalva de Governança:** O módulo está em estado `TESTADO — AGUARDANDO HOMOLOGAÇÃO`, aguardando a chancela formal das decisões de negócio DP-08 (tabelas e eventos CCT), DP-13 (critério de atraso), DP-14 (adicional noturno) e DP-15 (proporcionalidade de férias).
- 8 testes automatizados de integração fim-a-fim cobrindo 100% dos cenários de teste da SPEC-PATCH-FOLHA-001 foram executados e aprovados.
