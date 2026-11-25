# Relatório de Execução de Testes — Processo Admissional (RF-011 a RF-020)

**Projeto:** RH2.0 Enterprise — Módulo 02 (Processo Admissional)  
**Estratégia:** Execução 100% isolada com bancos SQLite temporários (`tempfile`), diretório privado temporário (`PRIVATE_DOCS_DIR`) e dados/usuários estritamente fictícios. O banco principal `colaboradores.db` não foi contaminado por dados de teste.

---

## 1. Evidências de Execução (Pós-última Edição)

| Comando Executado | Escopo | Total de Testes | Duração Observada | Resultado |
|---|---|---|---|---|
| `python -m unittest tests.test_admissao_rf011_rf020 -v` | Suíte dedicada RF-011 a RF-020 + RN-008/009/010/080 + RBAC + Multi-tenant + Rollback atômico | **10** | **65,906s** | **10 OK / 0 Falhas / 0 Erros** |
| `python tests\executar_todos_testes.py` | Regressão completa (Módulos Colaboradores, Folha 2026, Ciclo Trabalhista, RBAC, eSocial/CNAB, PDF Holerite, Benefícios RF071–080, Cadastro RF005–010, Admissão RF011–020, Sockets/Auth/CSRF) | **175** | **897,45s** | **175 OK / 0 Falhas / 0 Erros** |
| `python -m unittest tests.test_frontend_integridade tests.test_responsividade_desktop_mobile tests.test_rbac_enterprise -v` | Integridade HTML/JS após ajuste do `#cartao-processo-admissional` único no `frontend/index.html`, responsividade e matriz RBAC | **14** | **37,785s** | **14 OK / 0 Falhas / 0 Erros** |

> [!NOTE]
> A suíte `tests.test_plataforma_ciclo_trabalhista` (9 testes, 51,128s, 9 OK) também está integrada ao executor principal (`executar_todos_testes.py`), contabilizada dentro dos **175 testes** de regressão completa executados com 0 falhas e 0 erros.

---

## 2. Cobertura dos Cenários Testados em `tests/test_admissao_rf011_rf020.py`

1. **`test_rf011_abertura_validacoes_sem_defaults_e_cancelamento`**: bloqueia CPF inválido e ausência de campos obrigatórios (`candidato_email`, `cargo`, `setor`, `data_prevista_admissao`) e piso salarial < 2026; garante preservação de `candidato_data_nascimento = None` quando omitida (zero defaults fictícios), bloqueia duplicidade de admissão ativa por CPF, valida edição e cancelamento com liberação para novo processo.
2. **`test_rf012_checklist_configuravel_upload_privado_rejeicao_dispensa_e_historico`**: valida criação de 8 itens padrão, inclusão de item obrigatório customizado (`CERT_NR35`), rejeição de executável `.exe` (`400`), upload real em storage privado com SHA-256 e versionamento `v1 -> v2`, obrigatoriedade de justificativa em rejeição/dispensa (`400` sem justificativa), bloqueio de aprovação direta de item rejeitado, download autorizado do PDF e histórico imutável.
3. **`test_rf013_validacao_admissional_formal_e_bloqueios`**: executa `POST /api/admissoes/<id>/validar` detalhando listas `aprovados`, `pendentes` e `invalidos`, bloqueando ausência de jornada, centro de custo exigido e ASO, além de verificar persistência em `admissao_validacoes`.
4. **`test_rf014_contrato_trabalho_pdf_real_modelos_versionamento_e_formalizacao`**: lista os 5 modelos contratuais ativos, gera PDF 1.4 real contendo identificação de empregadora e empregado, realiza download autorizado (`application/pdf`), formaliza `v1` (`formalizado = 1`) e gera `v2` preservando `v1` imutável.
5. **`test_rf015_esocial_s2190_s2200_leiaute_schema_sequenciamento_e_sem_recibo_ficticio`**: valida `S-2190` e `S-2200` no leiaute `v_S_01_02_00`, impede duplicidade de eventos ativos, rejeita recibos fictícios (`SIM-`), processa retorno de rejeição com reprocessamento controlado e garante `numero_recibo = None` sem transmissão ICP-Brasil.
6. **`test_rf016_aso_admissional_rn009_e_sigilo_medico`**: comprova que marcar manualmente todos os itens do checklist não burla a ausência de ASO real nem um ASO `inapto` (`RN-009`), além de validar sigilo médico (`analista_rh` recebe resumo `restrito_sigilo_medico=True` sem observações clínicas/CRM e HTTP `403` no download do ASO, enquanto `medico_sst` acessa dados e PDF `200`).
7. **`test_rf017_jornada_inicial_escalas_empresa_e_vinculo_efetivacao`**: valida criação de escala e bloqueio de escalas inativas, inexistentes ou de outra empresa, propagando `escala_id` e jornada ao colaborador na efetivação.
8. **`test_rf018_centro_custo_ativo_empresa_e_integracao_folha`**: bloqueia centro de custo inativo, inexistente ou de outra empresa, registra vínculo na empresa correta e confirma integração do colaborador efetivado na criação de folha (`FolhaService.criar_ou_atualizar_folha`).
9. **`test_rf019_beneficios_elegibilidade_ativacao_e_integracao_folha`**: diferencia catálogo elegível de inelegível (`tempo_minimo_dias: 365`), bloqueia vinculação incompatível e ativa o benefício elegível em `beneficios_colaborador` na efetivação, com reflexo em `obter_descontos_beneficios_folha`.
10. **`test_rf020_segregacao_dupla_aprovacao_rollback_atomico_painel_rbac_e_multitenant`**: comprova `RN-080` (`403` na autoaprovação), dupla alçada com aprovadores distintos, rollback transacional atômico sem colaboradores órfãos após falha induzida em `gerar_xml_s2200`, idempotência, vinculação de prontuário (`colaborador_documentos`), férias, S-2200, pendência de experiência, Painel Único (10 etapas / 100% com CPF mascarado), bloqueio RBAC (`403` para `operador_dp` e `colaborador`) e isolamento multi-tenant BOLA/IDOR (`404` entre empresas).

---

## 3. Bugs Encontrados e Corrigidos Durante a Bateria de Testes

- **`backend/plataforma_service.py` (linha 214):** corrigido erro `NameError` (`condicoes_admissicionais` → `condicoes_adicionais`) no repasse para `AdmissaoService.gerar_contrato_trabalho`.
- **`backend/admissao_service.py` (efetivação `aprovar_admissao`, etapa 8):** estendida a transação atômica para vincular também todos os anexos privados entregues no `checklist_admissional` (além do contrato PDF gerado) na tabela `colaborador_documentos`.
- **`frontend/index.html`:** removidas 9 duplicações acidentais do bloco `#cartao-processo-admissional` fora de `#view-modulo-admissoes`, validando novamente 100% de unicidade de IDs e balanceamento HTML em `test_frontend_integridade`.
