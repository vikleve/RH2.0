# MATRIZ DE RASTREABILIDADE CONSOLIDADA — SST, ESOCIAL, RELATÓRIOS E REGRAS DE NEGÓCIO
## RH2.0 Enterprise — Requisitos RF-121 a RF-150 e Regras RN-001 a RN-035
**Data de Emissão:** 25/11/2026  
**Auditor Responsável:** Arquiteto de Software Enterprise & QA Lead  
**Critério de Homologação:** Código implementado, persistência verificada, regras de negócio aplicadas e testes automatizados executados com sucesso.

---

## 1. MÓDULO SST — SAÚDE E SEGURANÇA DO TRABALHO (RF-121 a RF-130)

| Requisito | Descrição Oficial | Arquivos de Código | Arquivos de Teste | Status Homologação | Evidência Técnica |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RF-121** | Cadastro de Exames Ocupacionais (PCMSO) | `backend/sst_service.py`, `migrations/013_...sql` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf121_cadastro_exames`: Catálogo de exames ativo com periodicidade e persistência |
| **RF-122** | Exame Admissional e Aptidão Prévia | `backend/sst_service.py`, `backend/admissao_service.py` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf122_exame_admissional`: Bloqueio admissional caso inapto; emissão de ASO |
| **RF-123** | Exame Periódico e Agendamentos | `backend/sst_service.py` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rn123_exame_periodico_agendamento`: Agendamento por clínica e status agendado |
| **RF-124** | Exame Demissional (Regra 135/90 dias) | `backend/sst_service.py`, `backend/rescisao_service.py` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf124_exame_demissional`: Dispensa por ASO recente (135d grau 1-2; 90d grau 3-4) |
| **RF-125** | Controle de ASO (Médico, CRM e Hash) | `backend/sst_service.py` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf125_controle_aso_aptidao_validade`: Registro com CRM, UF, data emissão e validade |
| **RF-126** | Controle de EPI (CA, Devolução, Substituição) | `backend/sst_service.py`, `migrations/013_...sql` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf126_controle_epi_entrega_devolucao_substituicao`: Rastreabilidade de entrega e troca |
| **RF-127** | Treinamentos Obrigatórios NRs e Reciclagem | `backend/sst_service.py` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf127_treinamentos_obrigatorios_nrs`: Participação em NR-10/35, carga horária e validade |
| **RF-128** | Alertas Proativos de Vencimento | `backend/sst_service.py` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf128_alertas_vencimento_proativos`: Detecção de ASOs, CAs e reciclagens a vencer |
| **RF-129** | Comunicação de Acidente de Trabalho (CAT) | `backend/sst_service.py`, `backend/esocial_eventos_trabalhistas.py` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf129_registro_cat_integracao_s2210`: Registro de acidente típico/trajeto e nro CAT |
| **RF-130** | Integração SST eSocial (S-2210, S-2220, S-2240) | `backend/esocial_eventos_trabalhistas.py`, `backend/sst_service.py` | `tests/test_sst_rf121_rf130.py` | **APROVADO** | `test_rf130_integracao_sst_esocial_s2220_s2240`: XMLs válidos contra XSD v_S_01_02_00 |

---

## 2. MÓDULO ESOCIAL (RF-131 a RF-140)

| Requisito | Descrição Oficial | Arquivos de Código | Arquivos de Teste | Status Homologação | Evidência Técnica |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RF-131** | Cadastro de Eventos Trabalhistas e Folha | `backend/esocial_service.py`, `backend/catalogo_eventos.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf131_cadastro_eventos_catalogo`: Catálogo oficial de eventos não-periódicos/periódicos |
| **RF-132** | Geração de XMLs Oficiais v_S_01_02_00 | `backend/esocial_eventos_trabalhistas.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf132_geracao_xml_eventos_completos`: XMLs estruturados com namespaces oficiais |
| **RF-133** | Assinatura Digital ICP-Brasil | `backend/esocial_service.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf133_assinatura_digital_com_ou_sem_certificado`: Sem forjar chave falsa; bloqueio ético |
| **RF-134** | Envio / Transmissão de Lote | `backend/esocial_service.py` | `tests/test_esocial_rf131_rf140.py` | **BLOQUEADO POR DEPENDÊNCIA EXTERNA** | `test_rf134_envio_transmissao_lote`: Simulação local com `LOCAL-VAL-...`; aguarda certificado A1/A3 |
| **RF-135** | Monitoramento de Protocolos e Lotes | `backend/esocial_service.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf135_monitoramento_status_eventos`: Filtros por status de processamento e retorno |
| **RF-136** | Tratamento de Rejeições e Ocorrências | `backend/esocial_service.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf136_tratamento_rejeicoes_criticas`: Parser de códigos de erro e mensagem explicativa |
| **RF-137** | Retificação de Eventos Anteriores | `backend/esocial_service.py`, `backend/database.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf137_retificacao_evento_com_recibo_anterior`: `indRetif=2` e vínculo `evento_retificador_de` |
| **RF-138** | Exclusão de Eventos via S-3000 | `backend/esocial_service.py`, `backend/esocial_eventos_trabalhistas.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf138_exclusao_evento_s3000`: Geração oficial de `<evtExclusao>` com recibo anterior |
| **RF-139** | Histórico e Rastreabilidade de Lotes | `backend/esocial_service.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf139_historico_completo_evento`: Trilha de auditoria por ID de evento |
| **RF-140** | Auditoria e Logs de Transmissão | `backend/esocial_service.py`, `backend/audit.py` | `tests/test_esocial_rf131_rf140.py` | **APROVADO** | `test_rf140_auditoria_operacoes_esocial`: Registro imutável de usuário, IP e timestamp |

---

## 3. MÓDULO DE RELATÓRIOS E EXPORTAÇÕES (RF-141 a RF-150)

| Requisito | Descrição Oficial | Arquivos de Código | Arquivos de Teste | Status Homologação | Evidência Técnica |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RF-141** | Relatório de Colaboradores e Headcount | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf141_relatorio_colaboradores`: Métricas por setor, massa salarial e média |
| **RF-142** | Relatório de Jornadas e Ponto | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf142_relatorio_jornadas_ponto`: Horas normais, HE 50/100%, noturnas e faltas |
| **RF-143** | Relatório de Férias e Dobra Legal | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf143_relatorio_ferias`: Detecção de férias a dobrar pelo Art. 137 da CLT |
| **RF-144** | Relatório de Afastamentos (15d Empresa x INSS) | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf144_relatorio_afastamentos`: Segregação de custos e casos de estabilidade provisória |
| **RF-145** | Relatório de Gestão de Benefícios | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf145_relatorio_beneficios`: Rateio de custos: subsídio empresa x desconto colaborador |
| **RF-146** | Relatório de Encargos Sociais (DCTFWeb) | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf146_relatorio_encargos_folha`: INSS Patronal (20%), RATxFAP, Terceiros (5,8%) e FGTS (8%) |
| **RF-147** | Relatório Consolidado de SST | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf147_relatorio_sst`: Indicadores de ASOs emitidos, EPIs em uso e CATs |
| **RF-148** | Relatório de Rescisões Contratuais | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf148_relatorio_rescisoes`: Verbas brutas, líquidos pagos e multas rescisórias de FGTS |
| **RF-149** | Relatório Financeiro e Contábil da Folha | `backend/relatorios_service.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf149_relatorio_financeiro_folha`: Provisões contábeis mensais de 13º e férias + terço |
| **RF-150** | Exportação Padronizada em PDF A4 Oficial | `backend/documentos_trabalhistas_pdf.py` | `tests/test_relatorios_rf141_rf150.py` | **APROVADO** | `test_rf150_exportacao_pdf_a4_oficial`: PDF A4 puro com cabeçalho, paginação "Página X de Y" e totalizadores |

---

## 4. REGRAS DE NEGÓCIO OFICIAIS (RN-001 a RN-035)

| Regra | Escopo Normativo | Arquivos de Código | Arquivos de Teste | Status Homologação | Evidência Técnica |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RN-001** a **RN-010** | Admissão, Cadastro, Dependentes, Histórico e eSocial | `backend/admissao_service.py`, `backend/folha_calculos_2026.py`, `backend/esocial_admissao.py` | `tests/test_regras_negocio_rn001_rn035.py` | **APROVADO** | Testes `test_rn_001` a `test_rn_010` (10/10 ok) |
| **RN-011** a **RN-025** | Jornadas, Tolerâncias, Intervalos, DSR, HE e Adicionais | `backend/folha_calculos_2026.py`, `backend/ponto_service.py` | `tests/test_regras_negocio_rn001_rn035.py` | **APROVADO** | Testes `test_rn_011` a `test_rn_025` (15/15 ok) |
| **RN-026** a **RN-035** | Férias, Afastamentos, Soma 60 Dias e Estabilidades | `backend/ferias_service.py`, `backend/afastamento_service.py`, `backend/sst_service.py` | `tests/test_regras_negocio_rn001_rn035.py` | **APROVADO** | Testes `test_rn_026` a `test_rn_035` (10/10 ok) |
