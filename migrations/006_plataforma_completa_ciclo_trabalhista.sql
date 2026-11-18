-- ============================================================================
-- MIGRAÇÃO POSTGRESQL / SUPABASE — PLATAFORMA INTEGRADA DO CICLO TRABALHISTA
-- Arquivo: migrations/006_plataforma_completa_ciclo_trabalhista.sql
-- Módulos 01 a 20: Cadastro, Admissão, Jornada/Ponto, Ausências, Férias,
-- Afastamentos, Benefícios, 13º, Rescisão, SST, eSocial, Central de Pendências,
-- Workflow de Aprovações, Multiempresa, Auditoria Rastreável e Indicadores.
-- ============================================================================

BEGIN;

-- 1. TABELA DE EMPRESAS (Módulo 17 Multiempresa)
CREATE TABLE IF NOT EXISTS empresas (
    id                  TEXT PRIMARY KEY,
    cnpj                TEXT UNIQUE NOT NULL,
    razao_social        TEXT NOT NULL,
    nome_fantasia       TEXT,
    regime_tributario   TEXT NOT NULL DEFAULT 'lucro_real'
                        CHECK (regime_tributario IN ('simples_nacional', 'lucro_presumido', 'lucro_real')),
    responsavel_nome    TEXT,
    responsavel_cpf     TEXT,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL,
    atualizado_em       TEXT NOT NULL
);

-- 2. TABELA DE FILIAIS (Módulo 17 Multiempresa)
CREATE TABLE IF NOT EXISTS filiais (
    id                  TEXT PRIMARY KEY,
    empresa_id          TEXT NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    codigo_filial       TEXT NOT NULL,
    nome                TEXT NOT NULL,
    cnpj                TEXT NOT NULL,
    cidade              TEXT NOT NULL,
    uf                  TEXT NOT NULL,
    feriados_locais     TEXT, -- JSON com lista de feriados específicos da filial
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL,
    CONSTRAINT unq_empresa_filial_cod UNIQUE (empresa_id, codigo_filial)
);

-- 3. TABELA DE CENTROS DE CUSTO (RF-018, RF-095)
CREATE TABLE IF NOT EXISTS centros_custo (
    id                  TEXT PRIMARY KEY,
    empresa_id          TEXT NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    codigo              TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL,
    CONSTRAINT unq_empresa_centro_custo UNIQUE (empresa_id, codigo)
);

-- 4. TABELA DE ADMISSÕES (Módulo 02 Admissão: RF-011 a RF-020)
CREATE TABLE IF NOT EXISTS admissoes (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    filial_id           TEXT,
    candidato_nome      TEXT NOT NULL,
    candidato_cpf       TEXT NOT NULL,
    candidato_email     TEXT NOT NULL,
    cargo               TEXT NOT NULL,
    setor               TEXT NOT NULL,
    salario_proposto    NUMERIC(15,2) NOT NULL,
    tipo_contrato       TEXT NOT NULL DEFAULT 'experiencia'
                        CHECK (tipo_contrato IN ('experiencia', 'indeterminado', 'temporario', 'aprendiz', 'estagio')),
    prazo_experiencia_dias INTEGER DEFAULT 45,
    prorrogacao_experiencia_dias INTEGER DEFAULT 45,
    data_prevista_admissao TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'em_andamento'
                        CHECK (status IN ('em_andamento', 'aprovada', 'reprovada')),
    motivo_reprovacao   TEXT,
    aprovado_por        TEXT,
    aprovado_em         TEXT,
    colaborador_id      INTEGER REFERENCES colaboradores(id) ON DELETE SET NULL,
    aso_admissional_status TEXT DEFAULT 'pendente'
                        CHECK (aso_admissional_status IN ('pendente', 'apto', 'inapto')),
    contrato_gerado     INTEGER DEFAULT 0,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL,
    atualizado_em       TEXT NOT NULL
);

-- 5. CHECKLIST ADMISSIONAL (RF-012)
CREATE TABLE IF NOT EXISTS checklist_admissional (
    id                  SERIAL PRIMARY KEY,
    admissao_id         INTEGER NOT NULL REFERENCES admissoes(id) ON DELETE CASCADE,
    item_descricao      TEXT NOT NULL,
    obrigatorio         INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente', 'recebido', 'validado', 'dispensado')),
    justificativa_dispensa TEXT,
    arquivo_url         TEXT,
    validado_por        TEXT,
    validado_em         TEXT
);

-- 6. ESCALAS DE JORNADA (RF-017, Módulo 03)
CREATE TABLE IF NOT EXISTS escalas_jornada (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    codigo              TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    carga_semanal_horas NUMERIC(5,2) NOT NULL DEFAULT 44.00,
    divisor_mensal      NUMERIC(6,2) NOT NULL DEFAULT 220.00,
    tipo_regime         TEXT NOT NULL DEFAULT '5x2'
                        CHECK (tipo_regime IN ('5x2', '6x1', '12x36', '4x3', 'especial')),
    entrada_padrao      TEXT NOT NULL DEFAULT '08:00',
    saida_padrao        TEXT NOT NULL DEFAULT '17:48',
    intervalo_minutos   INTEGER NOT NULL DEFAULT 60,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL
);

-- 7. MARCAÇÕES DE PONTO (RF-021 a RF-023)
CREATE TABLE IF NOT EXISTS marcacoes_ponto (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    data                TEXT NOT NULL, -- AAAA-MM-DD
    hora                TEXT NOT NULL, -- HH:MM:SS
    tipo_registro       TEXT NOT NULL DEFAULT 'automatico'
                        CHECK (tipo_registro IN ('automatico', 'relogio_afd', 'api', 'manual')),
    id_coletor          TEXT,
    arquivo_origem      TEXT,
    inconsistente       INTEGER DEFAULT 0,
    motivo_inconsistencia TEXT,
    criado_em           TEXT NOT NULL
);

-- 8. OCORRÊNCIAS DE PONTO E AUSÊNCIAS (RF-024, Módulo 04: RF-031 a RF-040)
CREATE TABLE IF NOT EXISTS ocorrencias_ponto (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    data_inicio         TEXT NOT NULL,
    data_fim            TEXT NOT NULL,
    tipo_ocorrencia     TEXT NOT NULL
                        CHECK (tipo_ocorrencia IN ('falta_justificada', 'falta_injustificada', 'falta_abonada', 'atraso', 'saida_antecipada', 'folga_compensatoria', 'trabalho_externo', 'declaracao', 'suspensao')),
    minutos_ausencia    INTEGER DEFAULT 0,
    justificativa       TEXT NOT NULL,
    comprovante_anexo   TEXT,
    desconta_dsr        INTEGER DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente', 'aprovada', 'reprovada')),
    aprovado_por        TEXT,
    aprovado_em         TEXT,
    motivo_reprovacao   TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 9. AJUSTES MANUAIS DE PONTO (RF-025, RF-026, RF-153)
CREATE TABLE IF NOT EXISTS ajustes_ponto (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    data                TEXT NOT NULL,
    hora_original       TEXT,
    hora_ajustada       TEXT NOT NULL,
    tipo_marcacao       TEXT NOT NULL, -- entrada, saida_intervalo, volta_intervalo, saida
    motivo              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente', 'aprovado', 'reprovado')),
    aprovado_por        TEXT,
    aprovado_em         TEXT,
    motivo_reprovacao   TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 10. FECHAMENTOS DE PONTO (RF-028, RF-029)
CREATE TABLE IF NOT EXISTS fechamentos_ponto (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    filial_id           TEXT,
    competencia         TEXT NOT NULL, -- AAAA-MM
    fechado_em          TEXT NOT NULL,
    fechado_por         TEXT NOT NULL,
    situacao            TEXT NOT NULL DEFAULT 'fechado'
                        CHECK (situacao IN ('fechado', 'reaberto')),
    justificativa_reabertura TEXT,
    reaberto_por        TEXT,
    reaberto_em         TEXT,
    CONSTRAINT unq_fechamento_ponto UNIQUE (empresa_id, filial_id, competencia)
);

-- 11. PERÍODOS AQUISITIVOS DE FÉRIAS (Módulo 06: RF-051 a RF-060)
CREATE TABLE IF NOT EXISTS periodos_aquisitivos (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    inicio_aquisitivo   TEXT NOT NULL,
    fim_aquisitivo      TEXT NOT NULL,
    limite_concessivo   TEXT NOT NULL,
    faltas_injustificadas INTEGER NOT NULL DEFAULT 0,
    dias_direito        INTEGER NOT NULL DEFAULT 30,
    dias_gozados        INTEGER NOT NULL DEFAULT 0,
    saldo_dias          INTEGER NOT NULL DEFAULT 30,
    situacao            TEXT NOT NULL DEFAULT 'adquirido'
                        CHECK (situacao IN ('em_aquisicao', 'adquirido', 'gozo_parcial', 'quitado', 'vencido', 'em_dobro')),
    criado_em           TEXT NOT NULL,
    atualizado_em       TEXT NOT NULL
);

-- 12. PROGRAMAÇÃO E CÁLCULO DE FÉRIAS (RF-053 a RF-059, RF-154)
CREATE TABLE IF NOT EXISTS ferias_programadas (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    periodo_aquisitivo_id INTEGER NOT NULL REFERENCES periodos_aquisitivos(id) ON DELETE RESTRICT,
    data_inicio         TEXT NOT NULL,
    data_fim            TEXT NOT NULL,
    dias_gozo           INTEGER NOT NULL,
    abono_pecuniario    INTEGER NOT NULL DEFAULT 0, -- 1/3 vendido
    dias_abono          INTEGER NOT NULL DEFAULT 0,
    adiantar_decimo     INTEGER NOT NULL DEFAULT 0,
    aviso_ferias_emitido TEXT,
    data_pagamento_limite TEXT,
    valor_ferias        NUMERIC(15,2) DEFAULT 0.00,
    valor_terco         NUMERIC(15,2) DEFAULT 0.00,
    valor_abono         NUMERIC(15,2) DEFAULT 0.00,
    valor_terco_abono   NUMERIC(15,2) DEFAULT 0.00,
    desconto_inss       NUMERIC(15,2) DEFAULT 0.00,
    desconto_irrf       NUMERIC(15,2) DEFAULT 0.00,
    valor_liquido       NUMERIC(15,2) DEFAULT 0.00,
    em_dobro            INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'solicitada'
                        CHECK (status IN ('solicitada', 'aprovada', 'calculada', 'paga', 'cancelada')),
    aprovado_por        TEXT,
    aprovado_em         TEXT,
    motivo_reprovacao   TEXT,
    competencia_folha   TEXT, -- competência em que o evento entra na folha
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 13. AFASTAMENTOS (Módulo 07: RF-061 a RF-070, eSocial S-2230)
CREATE TABLE IF NOT EXISTS afastamentos (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    tipo                TEXT NOT NULL
                        CHECK (tipo IN ('doenca', 'acidente_trabalho', 'maternidade', 'paternidade', 'servico_militar', 'licenca_sem_remuneracao', 'outro')),
    motivo_esocial      TEXT NOT NULL DEFAULT '01',
    data_inicio         TEXT NOT NULL,
    data_fim_prevista   TEXT NOT NULL,
    data_retorno_efetivo TEXT,
    cid                 TEXT, -- Acesso restrito LGPD
    estabilidade_fim    TEXT,
    dias_empresa        INTEGER DEFAULT 15,
    dias_inss           INTEGER DEFAULT 0,
    exige_aso_retorno   INTEGER DEFAULT 0,
    aso_retorno_realizado INTEGER DEFAULT 0,
    status_esocial      TEXT DEFAULT 'pendente',
    recibo_esocial      TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 14. BENEFÍCIOS (Módulo 08: RF-071 a RF-080)
CREATE TABLE IF NOT EXISTS beneficios_catalogo (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    codigo              TEXT NOT NULL,
    nome                TEXT NOT NULL,
    tipo                TEXT NOT NULL
                        CHECK (tipo IN ('vale_transporte', 'vale_alimentacao', 'vale_refeicao', 'plano_saude', 'seguro_vida', 'farmacia', 'flexivel')),
    coparticipacao_tipo TEXT NOT NULL DEFAULT 'percentual'
                        CHECK (coparticipacao_tipo IN ('percentual', 'fixo', 'nenhuma')),
    coparticipacao_valor NUMERIC(10,2) DEFAULT 0.00,
    teto_legal_percentual NUMERIC(5,2) DEFAULT 6.00,
    regra_elegibilidade TEXT,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS beneficios_colaborador (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    beneficio_id        INTEGER NOT NULL REFERENCES beneficios_catalogo(id) ON DELETE RESTRICT,
    optante             INTEGER NOT NULL DEFAULT 1,
    valor_diario        NUMERIC(10,2) DEFAULT 0.00,
    dias_uteis_mes      INTEGER DEFAULT 22,
    custo_total_mes     NUMERIC(15,2) DEFAULT 0.00,
    desconto_colaborador NUMERIC(15,2) DEFAULT 0.00,
    custo_empresa       NUMERIC(15,2) DEFAULT 0.00,
    vigencia_inicio     TEXT NOT NULL,
    vigencia_fim        TEXT,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL
);

-- 15. DÉCIMO TERCEIRO SALÁRIO (Módulo 10: RF-101 a RF-105)
CREATE TABLE IF NOT EXISTS decimo_terceiro (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    ano_base            INTEGER NOT NULL,
    parcela             INTEGER NOT NULL CHECK (parcela IN (1, 2, 3)), -- 1=adiantamento, 2=segunda, 3=complemento
    meses_trabalhados   INTEGER NOT NULL DEFAULT 12,
    salario_base        NUMERIC(15,2) NOT NULL,
    media_variaveis     NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    remuneracao_total   NUMERIC(15,2) NOT NULL,
    valor_bruto         NUMERIC(15,2) NOT NULL,
    desconto_primeira_parcela NUMERIC(15,2) DEFAULT 0.00,
    desconto_inss       NUMERIC(15,2) DEFAULT 0.00,
    desconto_irrf       NUMERIC(15,2) DEFAULT 0.00,
    valor_liquido       NUMERIC(15,2) NOT NULL,
    fgts_informativo    NUMERIC(15,2) DEFAULT 0.00,
    data_pagamento      TEXT NOT NULL,
    situacao            TEXT NOT NULL DEFAULT 'calculado'
                        CHECK (situacao IN ('calculado', 'pago', 'cancelado')),
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL,
    CONSTRAINT unq_13_colab_ano_parcela UNIQUE (colaborador_id, ano_base, parcela)
);

-- 16. RESCISÃO CONTRATUAL (Módulo 11: RF-106 a RF-120, RN-054 a RN-060)
CREATE TABLE IF NOT EXISTS rescisoes (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE RESTRICT,
    tipo_rescisao       TEXT NOT NULL
                        CHECK (tipo_rescisao IN ('sem_justa_causa', 'pedido_demissao', 'justa_causa', 'acordo_484a', 'rescisao_indireta', 'culpa_reciproca', 'termino_contrato', 'falecimento')),
    data_comunicacao    TEXT NOT NULL,
    data_afastamento    TEXT NOT NULL,
    tipo_aviso_previo   TEXT NOT NULL DEFAULT 'indenizado'
                        CHECK (tipo_aviso_previo IN ('trabalhado', 'indenizado', 'dispensado')),
    dias_aviso_previo   INTEGER NOT NULL DEFAULT 30,
    saldo_salario_dias  INTEGER NOT NULL DEFAULT 0,
    saldo_salario_valor NUMERIC(15,2) DEFAULT 0.00,
    aviso_indenizado_valor NUMERIC(15,2) DEFAULT 0.00,
    ferias_vencidas_valor NUMERIC(15,2) DEFAULT 0.00,
    terco_ferias_vencidas NUMERIC(15,2) DEFAULT 0.00,
    ferias_prop_dias    INTEGER DEFAULT 0,
    ferias_prop_valor   NUMERIC(15,2) DEFAULT 0.00,
    terco_ferias_prop   NUMERIC(15,2) DEFAULT 0.00,
    decimo_prop_avos    INTEGER DEFAULT 0,
    decimo_prop_valor   NUMERIC(15,2) DEFAULT 0.00,
    multa_fgts_percentual NUMERIC(5,2) DEFAULT 40.00,
    multa_fgts_valor    NUMERIC(15,2) DEFAULT 0.00,
    outros_proventos    NUMERIC(15,2) DEFAULT 0.00,
    total_proventos     NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    desconto_inss       NUMERIC(15,2) DEFAULT 0.00,
    desconto_irrf       NUMERIC(15,2) DEFAULT 0.00,
    desconto_aviso_previo NUMERIC(15,2) DEFAULT 0.00,
    outros_descontos    NUMERIC(15,2) DEFAULT 0.00,
    total_descontos     NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    valor_liquido       NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    data_limite_pagamento TEXT NOT NULL, -- 10 dias corridos
    data_pagamento_realizada TEXT,
    multa_art_477_aplicada INTEGER DEFAULT 0,
    seguro_desemprego_gerado INTEGER DEFAULT 0,
    trct_gerado         INTEGER DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'aberta'
                        CHECK (status IN ('aberta', 'calculada', 'homologada', 'paga', 'cancelada')),
    recibo_esocial_s2299 TEXT,
    motivo_legal        TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 17. SST: EXAMES E ASO (Módulo 12: RF-121 a RF-125, RF-130)
CREATE TABLE IF NOT EXISTS sst_exames (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    codigo              TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    tipo                TEXT NOT NULL DEFAULT 'periodico'
                        CHECK (tipo IN ('admissional', 'periodico', 'demissional', 'retorno_trabalho', 'mudanca_risco')),
    periodicidade_meses INTEGER NOT NULL DEFAULT 12,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sst_asos (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    exame_id            INTEGER REFERENCES sst_exames(id),
    tipo_aso            TEXT NOT NULL CHECK (tipo_aso IN ('admissional', 'periodico', 'demissional', 'retorno_trabalho', 'mudanca_risco')),
    data_emissao        TEXT NOT NULL,
    data_validade       TEXT NOT NULL,
    resultado           TEXT NOT NULL CHECK (resultado IN ('apto', 'inapto')),
    medico_nome         TEXT NOT NULL,
    medico_crm          TEXT NOT NULL,
    medico_uf           TEXT NOT NULL,
    arquivo_url         TEXT,
    recibo_esocial_s2220 TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 18. SST: EPIS (RF-126)
CREATE TABLE IF NOT EXISTS sst_epis (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    codigo              TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    ca_numero           TEXT NOT NULL,
    ca_validade         TEXT NOT NULL,
    vida_util_dias      INTEGER NOT NULL DEFAULT 180,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sst_entregas_epi (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    epi_id              INTEGER NOT NULL REFERENCES sst_epis(id) ON DELETE RESTRICT,
    data_entrega        TEXT NOT NULL,
    quantidade          INTEGER NOT NULL DEFAULT 1,
    data_prevista_troca TEXT,
    ciencia_colaborador INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL DEFAULT 'ativo'
                        CHECK (status IN ('ativo', 'trocado', 'devolvido', 'perdido')),
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 19. SST: TREINAMENTOS OBRIGATÓRIOS (RF-127)
CREATE TABLE IF NOT EXISTS sst_treinamentos (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    codigo              TEXT NOT NULL,
    nome                TEXT NOT NULL,
    nr_norma            TEXT NOT NULL, -- Ex: 'NR-06', 'NR-10', 'NR-35'
    carga_horaria       INTEGER NOT NULL,
    validade_meses      INTEGER NOT NULL DEFAULT 24,
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sst_treinamentos_participacoes (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    treinamento_id      INTEGER NOT NULL REFERENCES sst_treinamentos(id) ON DELETE RESTRICT,
    data_conclusao      TEXT NOT NULL,
    data_expiracao      TEXT NOT NULL,
    certificado_url     TEXT,
    instrutor_nome      TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 20. SST: CAT (RF-129, eSocial S-2210)
CREATE TABLE IF NOT EXISTS sst_cats (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    tipo_acidente       TEXT NOT NULL CHECK (tipo_acidente IN ('tipico', 'doenca_ocupacional', 'trajeto')),
    data_hora_acidente  TEXT NOT NULL,
    houve_afastamento   INTEGER NOT NULL DEFAULT 1,
    houve_obito         INTEGER NOT NULL DEFAULT 0,
    local_acidente      TEXT NOT NULL,
    descricao_detalhada TEXT NOT NULL,
    numero_cat          TEXT,
    recibo_esocial_s2210 TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 21. ESOCIAL (Módulo 13: RF-131 a RF-140)
CREATE TABLE IF NOT EXISTS esocial_eventos (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    tipo_evento         TEXT NOT NULL, -- S-1000, S-2190, S-2200, S-2210, S-2220, S-2230, S-2240, S-2299, S-1200, S-1210, S-1299, S-3000
    identificador_origem TEXT, -- ex: id do colaborador ou admissao
    ambiente            TEXT NOT NULL DEFAULT 'homologacao'
                        CHECK (ambiente IN ('producao', 'homologacao')),
    status              TEXT NOT NULL DEFAULT 'gerado'
                        CHECK (status IN ('gerado', 'validado', 'enviado', 'aceito', 'rejeitado')),
    xml_conteudo        TEXT NOT NULL,
    xml_assinado        TEXT,
    protocolo_envio     TEXT,
    numero_recibo       TEXT,
    codigo_resposta     TEXT,
    mensagem_resposta   TEXT,
    evento_retificador_de TEXT, -- aponta para recibo anterior em caso de retificação
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL,
    enviado_em          TEXT,
    processado_em       TEXT
);

-- 22. CENTRAL DE PENDÊNCIAS OPERACIONAIS (Módulo 15: RF-151 a RF-160)
CREATE TABLE IF NOT EXISTS pendencias_operacionais (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    modulo              TEXT NOT NULL,
    tipo_pendencia      TEXT NOT NULL
                        CHECK (tipo_pendencia IN ('experiencia_vencendo', 'ferias_vencendo', 'estabilidade_ativa', 'retorno_afastamento', 'aso_vencido', 'epi_vencido', 'treinamento_vencido', 'esocial_rejeitado', 'rescisao_prazo', 'ponto_inconsistente')),
    titulo              TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    severidade          TEXT NOT NULL DEFAULT 'media'
                        CHECK (severidade IN ('baixa', 'media', 'alta', 'critica')),
    colaborador_id      INTEGER REFERENCES colaboradores(id) ON DELETE CASCADE,
    prazo_limite        TEXT NOT NULL,
    responsavel         TEXT NOT NULL DEFAULT 'Departamento Pessoal',
    status              TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente', 'em_tratamento', 'resolvida')),
    resolvida_por       TEXT,
    resolvida_em        TEXT,
    criado_em           TEXT NOT NULL
);

-- 23. WORKFLOW DE APROVAÇÕES (RF-020, RF-026, RF-039, RF-153 a RF-156)
CREATE TABLE IF NOT EXISTS aprovacoes_workflow (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    modulo              TEXT NOT NULL,
    processo_tipo       TEXT NOT NULL
                        CHECK (processo_tipo IN ('admissao', 'ajuste_ponto', 'justificativa_falta', 'ferias', 'rescisao', 'esocial')),
    processo_id         INTEGER NOT NULL,
    solicitante         TEXT NOT NULL,
    aprovador           TEXT,
    status              TEXT NOT NULL DEFAULT 'pendente'
                        CHECK (status IN ('pendente', 'aprovado', 'reprovado')),
    justificativa       TEXT,
    criado_em           TEXT NOT NULL,
    atualizado_em       TEXT NOT NULL
);

-- 24. AUDITORIA GERAL DE OPERAÇÕES (Módulo 20: RF-191 a RF-200, RT-01)
CREATE TABLE IF NOT EXISTS auditoria_operacoes (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT,
    modulo              TEXT NOT NULL,
    operacao            TEXT NOT NULL
                        CHECK (operacao IN ('inclusao', 'alteracao', 'exclusao_logica', 'fechamento', 'reabertura', 'calculo', 'aprovacao', 'exportacao', 'acesso_negado', 'integracao')),
    registro_tipo       TEXT NOT NULL,
    registro_id         TEXT NOT NULL,
    campo_alterado      TEXT,
    valor_anterior      TEXT,
    valor_novo          TEXT,
    usuario_responsavel TEXT NOT NULL,
    ip_origem           TEXT,
    detalhes            TEXT,
    criado_em           TEXT NOT NULL
);

-- 25. INTEGRAÇÕES CORPORATIVAS E ARQUIVOS BANCÁRIOS (Módulo 18: RF-176 a RF-180, RF-096, RF-097)
CREATE TABLE IF NOT EXISTS arquivos_bancarios_cnab (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    competencia         TEXT NOT NULL,
    tipo_folha          TEXT NOT NULL DEFAULT 'mensal',
    banco_codigo        TEXT NOT NULL DEFAULT '001', -- Banco do Brasil / Itaú / Caixa / Bradesco / Santander
    layout_cnab         TEXT NOT NULL DEFAULT 'CNAB240',
    total_registros     INTEGER NOT NULL,
    valor_total_liquido NUMERIC(15,2) NOT NULL,
    conteudo_arquivo    TEXT NOT NULL,
    gerado_por          TEXT NOT NULL,
    gerado_em           TEXT NOT NULL
);

-- 26. ÍNDICES DE PERFORMANCE E INTEGRIDADE
CREATE INDEX IF NOT EXISTS idx_adm_status        ON admissoes(status);
CREATE INDEX IF NOT EXISTS idx_adm_cpf           ON admissoes(candidato_cpf);
CREATE INDEX IF NOT EXISTS idx_ponto_colab_data  ON marcacoes_ponto(colaborador_id, data);
CREATE INDEX IF NOT EXISTS idx_ocorrencia_colab  ON ocorrencias_ponto(colaborador_id, data_inicio);
CREATE INDEX IF NOT EXISTS idx_ferias_colab      ON ferias_programadas(colaborador_id);
CREATE INDEX IF NOT EXISTS idx_afast_colab       ON afastamentos(colaborador_id);
CREATE INDEX IF NOT EXISTS idx_rescisao_colab    ON rescisoes(colaborador_id);
CREATE INDEX IF NOT EXISTS idx_pendencias_status ON pendencias_operacionais(status, prazo_limite);
CREATE INDEX IF NOT EXISTS idx_audit_modulo_data ON auditoria_operacoes(modulo, criado_em);

COMMIT;
