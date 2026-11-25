# Fluxo Oficial do Processo Admissional — Módulo 02 (SRS Volume 3)

**Requisitos Cobertos:** RF-011 a RF-020  
**Regras de Negócio:** RN-001, RN-003, RN-008, RN-009, RN-010, RN-080

---

## 1. Etapas Operacionais (13 Passos Integrados)

1. **Abertura da Admissão (`RF-011`)**: registro de candidato e vínculo previsto (`empresa_id`, `filial_id`, CPF válido, e-mail válido, salário >= piso legal, cargo, data prevista). Geração de identificador único (`ADM-YYYY-NNNNN`). Sem valores fictícios.
2. **Preenchimento Cadastral (`RF-011` / `RF-013`)**: coleta de nascimento, telefone, endereço, estado civil, gestor responsável e local de trabalho.
3. **Entrega Documental (`RF-012`)**: geração automática do checklist padrão (6 itens obrigatórios + 2 configuráveis/opcionais) e upload seguro em storage privado com SHA-256.
4. **Validação Documental (`RF-012`)**: conferência por operador autorizado (`validado`, `rejeitado` com motivo ou `dispensado` com justificativa), mantendo histórico imutável em `checklist_admissional_historico`.
5. **Definição de Jornada Inicial (`RF-017`)**: vinculação de escala ativa da empresa (`escalas_jornada`), horários, intervalo e vigência inicial (`admissao_jornadas_historico`).
6. **Definição de Centro de Custo (`RF-018`)**: vinculação de centro de custo ativo pertencente à mesma `empresa_id` (`admissao_centros_custo_historico`).
7. **Definição de Benefícios (`RF-019`)**: avaliação de elegibilidade contra `beneficios_catalogo` (Módulo 08), adesão e vigência inicial em `admissao_beneficios`.
8. **Registro e Validação do ASO (`RF-016` / `RN-009`)**: registro médico real em `sst_asos` (`agendado`, `realizado`, `apto`, `inapto`, `pendente_analise`) com anexo em storage privado e sigilo clínico para perfis não autorizados. O status manual do checklist nunca substitui um exame ASO válido e `apto`.
9. **Validação Formal Admissional (`RF-013` / `RN-008`)**: execução automática da conferência completa (CPF, data de admissão, salário, cargo, jornada ativa, ASO apto e válido, documentos obrigatórios validados/dispensados, empresa/filial/centro de custo) gravando snapshot em `admissao_validacoes`.
10. **Geração do Contrato de Trabalho (`RF-014`)**: seleção de modelo em `admissao_contratos_modelos`, geração real de PDF 1.4 (`backend/contrato_pdf.py`), visualização/download autorizado, formalização e controle de versões (`admissao_contratos`).
11. **Aprovação com Segregação de Funções (`RF-020` / `RN-080`)**: validação de alçada, segregação criador ≠ aprovador (e dupla aprovação quando habilitada), justificativa obrigatória e registro em `aprovacoes_workflow`.
12. **Efetivação Transacional Atômica (`RF-020`)**: em transação única SQL com idempotência e proteção contra duplicidade de CPF: cria colaborador ativo, gera matrícula, registra `historico_funcional` inicial, cria `periodos_aquisitivos`, vincula `sst_asos`, ativa `beneficios_colaborador`, vincula contrato em `colaborador_documentos` e cria alerta de experiência quando aplicável.
13. **Integração eSocial Admissional (`RF-015` / `RN-010`)**: determinação automática de aplicabilidade (**S-2190** preliminar quando aplicável vs **S-2200** admissional completo, ou sequência `S-2190 → S-2200`), geração XML conforme leiaute `v_S_01_02_00`, validação estrutural, controle de ambiente (`homologacao` / `producao_restrita` / `producao`), tratamento de rejeições e reprocessamento sem emissão de recibos fictícios.

---

## 2. Máquina de Estados do Processo Admissional

| Status do Processo (`admissoes.status`) | Significado Operacional |
|---|---|
| `rascunho` | Registro inicial ainda sem envio documental ou revisão completa. |
| `em_andamento` | Admissão ativa com preenchimento de dados, jornada, centro de custo e benefícios. |
| `aguardando_documentos` | Existem itens obrigatórios pendentes ou rejeitados no checklist ou ASO não concluído. |
| `aguardando_validacao` | Documentos obrigatórios e ASO preenchidos, aguardando validação formal (`RF-013`). |
| `aguardando_aprovacao` | Validação formal `RF-013` aprovada; aguardando deliberação de aprovador autorizado (`RN-080`). |
| `aprovado` | Primeira aprovação concluída (em dupla aprovação) ou aprovação registrada antes da efetivação. |
| `reprovado` | Processo formalmente reprovado por pendência impeditiva ou decisão do aprovador. |
| `cancelado` | Processo encerrado antes da efetivação sem criação de vínculo. |
| `efetivado` | Vínculo efetivado atomicamente (colaborador ativo, matrícula, benefícios, contrato, SST e eSocial). |

*(Nota de compatibilidade retroativa: processos legados encerrados com `'aprovada'` continuam reconhecidos como efetivados).*
