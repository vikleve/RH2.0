# AUDITORIA E HOMOLOGAÇÃO TÉCNICA — REGRAS DE NEGÓCIO TRABALHISTAS E PREVIDENCIÁRIAS
## RH2.0 Enterprise — Regras de Negócio RN-001 a RN-035 (Volume 4 do SRS / Legislação Vigente 2026)
**Data de Execução:** 25/11/2026  
**Auditor Responsável:** Arquiteto de Software Enterprise & Especialista em Legislação Trabalhista  
**Status Consolidado:** **APROVADO (100% dos testes individuais e integrados em conformidade legal)**

---

## 1. MATRIZ DE REGRAS DE NEGÓCIO AUDITADAS E TESTADAS

Todas as 35 regras de negócio dos Volumes 3 e 4 do SRS foram implementadas, validadas e testadas com casos de testes formais:

### Seção 1: Admissão, Cadastro, Dependentes, Histórico e eSocial (RN-001 a RN-010)
| Regra | Descrição e Base Legal | Validação Realizada | Status |
| :--- | :--- | :--- | :--- |
| **RN-001** | Unicidade de CPF no âmbito da empresa | Bloqueio de duplicidade em banco com índice único e validação de serviço | **APROVADO** |
| **RN-002** | Unicidade de Matrícula Funcional | Validação de chave única por empresa/empregador | **APROVADO** |
| **RN-003** | Dependentes IRRF e Salário-Família (Portaria 2026) | Dedução IRRF R$ 189,59/mês; Salário-família R$ 67,54 por filho (teto R$ 1.819,26) | **APROVADO** |
| **RN-004** | Imutabilidade do Histórico Funcional | Tabela `auditoria_operacoes` registra alterações salariais/cargos sem exclusão | **APROVADO** |
| **RN-005** | Obrigatoriedade de Dados Cadastrais Mínimos | Bloqueio de admissão sem CPF, nome, cargo, salário e data de admissão | **APROVADO** |
| **RN-006** | Exigência de ASO Admissional Prévio (NR-7) | Efetivação condicionada a ASO válido com aptidão "Apto" | **APROVADO** |
| **RN-007** | Vínculo Obrigatório com Centro de Custo | Associação contábil do colaborador a centro de custo existente | **APROVADO** |
| **RN-008** | Restrições Temporais na Admissão | Vedação de admissão anterior à data de nascimento ou futura sem pré-admissão | **APROVADO** |
| **RN-009** | Integração eSocial Admissional (S-2190 e S-2200) | Geração do evento preliminar S-2190 e completo S-2200 | **APROVADO** |
| **RN-010** | Bloqueio de Duplicidade de Horários / Dedicação | Validação de choque de horários e contratos de dedicação exclusiva | **APROVADO** |

### Seção 2: Jornada de Trabalho, Ponto, Tolerâncias e Horas Extras (RN-011 a RN-025)
| Regra | Descrição e Base Legal | Validação Realizada | Status |
| :--- | :--- | :--- | :--- |
| **RN-011** | Limite Constitucional de Jornada (8h/dia e 44h/sem) | Segregação de horas normais e apuração de excessos como horas extras | **APROVADO** |
| **RN-012** | Tolerância de Marcação de Ponto (CLT Art. 58 § 1º) | Variações até 5 minutos por batida e limite de 10 min diários não descontadas nem pagas | **APROVADO** |
| **RN-013** | Intervalo Intrajornada (CLT Art. 71) | Mínimo de 1h para jornadas > 6h; 15 min para jornadas entre 4h e 6h | **APROVADO** |
| **RN-014** | Intervalo Interjornada (CLT Art. 66) | Descanso obrigatório de 11 horas consecutivas entre duas jornadas | **APROVADO** |
| **RN-015** | Descanso Semanal Remunerado (CLT Art. 67 / CF Art. 7º) | DSR de 24 horas consecutivas preferencialmente aos domingos | **APROVADO** |
| **RN-016** | Banco de Horas (CLT Art. 59 § 5º) | Limite legal de compensação individual de até 6 meses | **APROVADO** |
| **RN-017** | Perda do DSR por Faltas Injustificadas (Lei 605/49) | Desconto de 1 DSR na folha por semana com falta injustificada | **APROVADO** |
| **RN-018** | Reflexo de Faltas nas Férias (CLT Art. 130) | Aplicação estrita da tabela do Art. 130 (até 5 faltas: 30d; 6-14: 24d; etc.) | **APROVADO** |
| **RN-019** | Desconto de Atrasos e Saídas Antecipadas | Cálculo do desconto proporcional com base no salário-hora real | **APROVADO** |
| **RN-020** | Adicional de Horas Extras (CF Art. 7º XVI) | Acréscimo mínimo de 50% em dias úteis e 100% em domingos e feriados | **APROVADO** |
| **RN-021** | Adicional Noturno Urbano e Hora Ficta (CLT Art. 73) | 20% sobre hora normal e cômputo da hora ficta noturna de 52m30s (7h relógio = 8h) | **APROVADO** |
| **RN-022** | Prorrogação de Jornada Noturna (Súmula 60 TST) | Extensão do adicional noturno de 20% para horas prorrogadas além das 05h | **APROVADO** |
| **RN-023** | Bloqueio de Edição após Fechamento do Ponto | Bloqueio de inclusões/alterações em competências fechadas sem reabertura | **APROVADO** |
| **RN-024** | Justificativas Legais de Abono (CLT Art. 473) | Abono de casamento (3d), luto (2d), nascimento filho (5d), doação sangue, etc. | **APROVADO** |
| **RN-025** | Periculosidade (30%) e Insalubridade (10%, 20%, 40%) | Periculosidade sobre salário base; insalubridade sobre mínimo; não cumulação | **APROVADO** |

### Seção 3: Férias, Afastamentos, Soma 60 Dias e Estabilidades (RN-026 a RN-035)
| Regra | Descrição e Base Legal | Validação Realizada | Status |
| :--- | :--- | :--- | :--- |
| **RN-026** | Período Aquisitivo de Férias (CLT Art. 130) | Aquisição de 30 dias de direito a cada 12 meses de vigência contratual | **APROVADO** |
| **RN-027** | Período Concessivo de Férias (CLT Art. 134) | Concessão obrigatória nos 12 meses subsequentes ao período aquisitivo | **APROVADO** |
| **RN-028** | Dobra de Férias (CLT Art. 137) | Pagamento em dobro da remuneração de férias quando gozadas após o concessivo | **APROVADO** |
| **RN-029** | Fracionamento em até 3 Períodos (CLT Art. 134 § 1º) | Exigência de um período não menor que 14 dias e nenhum menor que 5 dias | **APROVADO** |
| **RN-030** | Vedação de Início de Férias Pré-DSR (CLT Art. 134 § 3º) | Bloqueio de início nos 2 dias que antecedem DSR ou feriados (sextas/sábados) | **APROVADO** |
| **RN-031** | Abono Pecuniário de Férias (CLT Art. 143) | Conversão de até 1/3 das férias em abono em dinheiro (10 dias de 30) | **APROVADO** |
| **RN-032** | Prazo de Pagamento das Férias (CLT Art. 145) | Quitação e depósito do terço constitucional até 2 dias antes do início do gozo | **APROVADO** |
| **RN-033** | Afastamentos: 15 Dias Empresa x INSS (Lei 8.213) | Empresa remunera os primeiros 15 dias; a partir do 16º dia encaminhado à Previdência | **APROVADO** |
| **RN-034** | Soma de Afastamentos pela Mesma CID (Dec. 3.048 Art. 75) | Soma de atestados da mesma doença dentro de 60 dias para perfazer os 15 dias | **APROVADO** |
| **RN-035** | Estabilidades Provisórias e ASO de Retorno (NR-7) | Estabilidade acidentária B91 (12 meses); gestante (5 meses pós-parto); ASO >= 30 dias | **APROVADO** |

---

## 2. RESULTADO DOS TESTES DE HOMOLOGAÇÃO DAS REGRAS

Arquivo de testes: `tests/test_regras_negocio_rn001_rn035.py`
Execução: 35 testes unitários e de integração, abrangendo cada regra individualmente.

```text
Ran 35 tests in 92.221s
OK
```

**Resultado:** 100% de aprovação técnica e normativa. Nenhuma inconsistência legal detectada.
