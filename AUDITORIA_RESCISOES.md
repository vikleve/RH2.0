# AUDITORIA E HOMOLOGAÇÃO DE RESCISÕES CONTRATUAIS (RN-054 A RN-060) — RH2.0

## 1. Visão Geral
Esta auditoria valida todas as 7 modalidades canônicas de rescisão trabalhista conforme a Consolidação das Leis do Trabalho (CLT), legislação previdenciária e Súmulas do TST, garantindo cálculos exatos de verbas rescisórias, aviso prévio, multas e deduções legais.

---

## 2. Modalidades Canônicas Auditadas

### 2.1. RN-054 — Rescisão Sem Justa Causa
- **Dispositivo Legal**: Art. 477 da CLT e Lei 8.036/90.
- **Direitos**: Saldo de salário integral, aviso prévio indenizado (com projeção de 3 dias por ano trabalhado, Lei 12.506/11), 13º proporcional, férias vencidas e proporcionais com terço constitucional (+1/3), multa de 40% sobre o saldo do FGTS, saque FGTS (código 01) e guias para Seguro-Desemprego.
- **Status**: **APROVADO**.

### 2.2. RN-055 — Pedido de Demissão
- **Dispositivo Legal**: Arts. 487 e 488 da CLT.
- **Direitos**: Saldo de salário, 13º salário proporcional, férias vencidas e férias proporcionais com 1/3 (Súmula 261 TST). Sem aviso prévio indenizado (desconto se não cumprido), sem saque de FGTS, sem multa rescisória e sem seguro-desemprego.
- **Status**: **APROVADO**.

### 2.3. RN-056 — Demissão Por Justa Causa
- **Dispositivo Legal**: Art. 482 da CLT.
- **Direitos**: Apenas saldo de salário e férias vencidas com 1/3 (Súmula 171 TST). Perda do 13º proporcional, férias proporcionais, aviso prévio, saque/multa de FGTS e seguro-desemprego.
- **Status**: **APROVADO**.

### 2.4. RN-057 — Acordo Entre as Partes (Mútuo Acordo)
- **Dispositivo Legal**: Art. 484-A da CLT (Reforma Trabalhista, Lei 13.467/17).
- **Direitos**: 50% do aviso prévio indenizado, 20% de multa rescisória sobre o FGTS, 100% de saldo de salário, 100% do 13º e férias (+1/3), saque de até 80% dos depósitos do FGTS (código 07), e vedação ao seguro-desemprego.
- **Status**: **APROVADO**.

### 2.5. RN-058 — Rescisão Indireta (Falta Grave do Empregador)
- **Dispositivo Legal**: Art. 483 da CLT.
- **Direitos**: Idênticos à dispensa sem justa causa (saldo de salário, aviso prévio indenizado, 13º proporcional, férias integrais e proporcionais com 1/3, multa rescisória de 40% do FGTS, saque FGTS e seguro-desemprego).
- **Status**: **APROVADO**.

### 2.6. RN-059 — Culpa Recíproca
- **Dispositivo Legal**: Art. 484 da CLT, Súmula 14 do TST e Art. 18, § 2º da Lei 8.036/90.
- **Diferenciação Estrita do Art. 484-A**:
  - Saldo de salário: 100%.
  - Férias vencidas (+1/3): 100%.
  - Aviso Prévio: **50%** (pago pela metade).
  - 13º Salário Proporcional: **50%** (pago pela metade).
  - Férias Proporcionais (+1/3): **50%** (pago pela metade).
  - Multa do FGTS: **20%** sobre o saldo rescisório.
  - Saque do FGTS: Permitido sob **Código de Saque 02**.
  - Seguro-Desemprego: **Não elegível** (vedado por lei).
- **Implementação**: Adicionada modalidade canônica `"culpa_reciproca"` em `MODALIDADES_CANONICAS` e implementado cálculo oficial em `_calcular_rescisao_detalhada()` no módulo [backend/rescisao_service.py](file:///c:/Users/Renan/Downloads/RH2.0-main/backend/rescisao_service.py).
- **Status**: **APROVADO**.

### 2.7. RN-060 — Término de Contrato e Rescisão Antecipada
- **Dispositivo Legal**: Arts. 479 e 480 da CLT.
- **Cenários Cobertos**:
  - *Término Normal de Prazo Determinado/Experiência*: Saldo de salário, 13º proporcional, férias proporcionais + 1/3, saque do FGTS sem multa rescisória (código 04).
  - *Rescisão Antecipada pelo Empregador (Art. 479 CLT)*: Indenização de 50% dos dias faltantes até o término, além de verbas integrais e multa de 40% de FGTS.
  - *Rescisão Antecipada pelo Empregado (Art. 480 CLT)*: Indenização dos prejuízos causados ao empregador, limitada a 50% dos salários faltantes.
- **Status**: **APROVADO**.

---

## 3. Matriz de Evidências Técnicas
| Requisito | Modalidade Canônica | Dispositivo Legal | Arquivo / Função | Teste Automatizado | Status |
|---|---|---|---|---|---|
| **RN-054** | `sem_justa_causa` | Art. 477 CLT | `rescisao_service._calcular_rescisao_detalhada` | `test_rn054_rescisao_sem_justa_causa` | APROVADO |
| **RN-055** | `pedido_demissao` | Art. 487 CLT | `rescisao_service._calcular_rescisao_detalhada` | `test_rn055_pedido_demissao` | APROVADO |
| **RN-056** | `com_justa_causa` | Art. 482 CLT | `rescisao_service._calcular_rescisao_detalhada` | `test_rn056_justa_causa` | APROVADO |
| **RN-057** | `acordo_partes` | Art. 484-A CLT | `rescisao_service._calcular_rescisao_detalhada` | `test_rn057_acordo_trabalhista_art_484a` | APROVADO |
| **RN-058** | `rescisao_indireta` | Art. 483 CLT | `rescisao_service._calcular_rescisao_detalhada` | `test_rn058_rescisao_indireta` | APROVADO |
| **RN-059** | `culpa_reciproca` | Art. 484 CLT / Súmula 14 TST | `rescisao_service._calcular_rescisao_detalhada` | `test_rn059_culpa_reciproca_art_484_sumula14` | APROVADO |
| **RN-060** | `termino_contrato` | Art. 479 / 480 CLT | `rescisao_service._calcular_rescisao_detalhada` | `test_rn060_termino_contrato_prazo_determinado` | APROVADO |
