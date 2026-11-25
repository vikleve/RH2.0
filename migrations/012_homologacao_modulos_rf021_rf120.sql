-- Migração 012: Consolidação e Homologação dos Módulos RF021 a RF120
-- Ponto, Ausências, Horas Extras/Adicionais, Férias, Afastamentos, Folha/13º, Rescisão,
-- Tabelas Legais Versionadas, Feriados, Rateio Contábil e Integração Financeira/CNAB.

-- 1. Tabelas Legais Versionadas com Vigência e Fonte Normativa
CREATE TABLE IF NOT EXISTS tabelas_legais_vigencia (
    id                          SERIAL PRIMARY KEY,
    identificador               TEXT UNIQUE NOT NULL,
    descricao                   TEXT NOT NULL,
    competencia_inicio          TEXT NOT NULL,
    competencia_fim             TEXT,
    vigencia_inicio             TEXT NOT NULL,
    fonte_normativa             TEXT NOT NULL,
    salario_minimo              NUMERIC(12,2) NOT NULL DEFAULT 1621.00,
    teto_inss                   NUMERIC(12,2) NOT NULL DEFAULT 8475.55,
    teto_contribuicao_inss      NUMERIC(12,2) NOT NULL DEFAULT 988.09,
    faixas_inss_json            TEXT NOT NULL,
    faixas_irrf_json            TEXT NOT NULL,
    deducao_dependente_irrf     NUMERIC(12,2) NOT NULL DEFAULT 189.59,
    desconto_simplificado_irrf  NUMERIC(12,2) NOT NULL DEFAULT 607.20,
    lei_15270_ativa             INTEGER NOT NULL DEFAULT 1,
    limite_salario_familia      NUMERIC(12,2) NOT NULL DEFAULT 1980.38,
    valor_cota_salario_familia  NUMERIC(12,2) NOT NULL DEFAULT 67.54,
    aliquota_fgts_padrao        NUMERIC(6,2) NOT NULL DEFAULT 8.00,
    aliquota_fgts_aprendiz      NUMERIC(6,2) NOT NULL DEFAULT 2.00,
    ativo                       INTEGER NOT NULL DEFAULT 1,
    criado_por                  TEXT NOT NULL,
    criado_em                   TEXT NOT NULL,
    atualizado_em               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tabelas_legais_historico (
    id                  SERIAL PRIMARY KEY,
    tabela_id           INTEGER NOT NULL,
    identificador       TEXT NOT NULL,
    acao                TEXT NOT NULL,
    snapshot_json       TEXT NOT NULL,
    motivo              TEXT,
    usuario             TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 2. Calendário Oficial de Feriados (Nacionais, Estaduais e Municipais)
CREATE TABLE IF NOT EXISTS feriados_calendario (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    filial_id           TEXT,
    data_feriado        TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    abrangencia         TEXT NOT NULL DEFAULT 'nacional',
    ativo               INTEGER NOT NULL DEFAULT 1,
    criado_em           TEXT NOT NULL
);

-- 3. Ponto Eletrônico: Importação de Lotes, Justificativas/Atestados, Banco de Horas e Histórico
CREATE TABLE IF NOT EXISTS ponto_lotes_importacao (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    origem              TEXT NOT NULL,
    nome_arquivo        TEXT,
    sha256_hash         TEXT,
    idempotency_key     TEXT,
    total_registros     INTEGER NOT NULL DEFAULT 0,
    total_importados    INTEGER NOT NULL DEFAULT 0,
    total_duplicados    INTEGER NOT NULL DEFAULT 0,
    total_erros         INTEGER NOT NULL DEFAULT 0,
    erros_json          TEXT,
    status              TEXT NOT NULL DEFAULT 'processado',
    importado_por       TEXT NOT NULL,
    importado_em        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ponto_justificativas (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    colaborador_id      INTEGER NOT NULL,
    data_referencia     TEXT NOT NULL,
    tipo                TEXT NOT NULL,
    motivo              TEXT NOT NULL,
    cid                 TEXT,
    dias_abono          INTEGER DEFAULT 1,
    artigo_clt          TEXT,
    nome_arquivo        TEXT,
    caminho_privado     TEXT,
    status              TEXT NOT NULL DEFAULT 'pendente',
    solicitado_por      TEXT NOT NULL,
    aprovado_por        TEXT,
    motivo_decisao      TEXT,
    criado_em           TEXT NOT NULL,
    atualizado_em       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ponto_banco_horas (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    colaborador_id      INTEGER NOT NULL,
    competencia         TEXT NOT NULL,
    data_referencia     TEXT NOT NULL,
    tipo_movimento      TEXT NOT NULL,
    minutos             INTEGER NOT NULL,
    saldo_acumulado_min INTEGER NOT NULL DEFAULT 0,
    prazo_compensacao   TEXT,
    observacao          TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ponto_historico_jornada (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    colaborador_id      INTEGER NOT NULL,
    competencia         TEXT NOT NULL,
    evento              TEXT NOT NULL,
    valor_anterior      TEXT,
    valor_novo          TEXT,
    justificativa       TEXT,
    usuario             TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 4. Afastamentos: Histórico de Prorrogações
CREATE TABLE IF NOT EXISTS afastamentos_prorrogacoes (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    afastamento_id      INTEGER NOT NULL,
    data_fim_anterior   TEXT NOT NULL,
    data_fim_nova       TEXT NOT NULL,
    motivo              TEXT NOT NULL,
    cid                 TEXT,
    documento_ref       TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 5. Folha: Rateio Contábil por Centro de Custo, Integração Financeira e Retorno CNAB
CREATE TABLE IF NOT EXISTS folha_rateio_centro_custo (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    folha_id            INTEGER NOT NULL,
    colaborador_id      INTEGER NOT NULL,
    competencia         TEXT NOT NULL,
    centro_custo_id     TEXT,
    centro_custo_codigo TEXT NOT NULL,
    percentual          NUMERIC(6,2) NOT NULL DEFAULT 100.00,
    valor_bruto         NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    valor_encargos      NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    valor_fgts          NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    custo_total         NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    criado_em           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folha_integracao_financeira (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    competencia         TEXT NOT NULL,
    tipo_titulo         TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    centro_custo        TEXT,
    valor_total         NUMERIC(12,2) NOT NULL DEFAULT 0.00,
    data_vencimento     TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'aberto',
    folha_ids_json      TEXT,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cnab_retornos (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    arquivo_cnab_id     INTEGER,
    nome_arquivo        TEXT NOT NULL,
    total_registros     INTEGER NOT NULL DEFAULT 0,
    total_liquidados    INTEGER NOT NULL DEFAULT 0,
    total_rejeitados    INTEGER NOT NULL DEFAULT 0,
    ocorrencias_json    TEXT NOT NULL,
    processado_por      TEXT NOT NULL,
    processado_em       TEXT NOT NULL
);

-- 6. Rescisões: Trilha de Homologação e Quitação
CREATE TABLE IF NOT EXISTS rescisoes_historico (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL,
    rescisao_id         INTEGER NOT NULL,
    acao                TEXT NOT NULL,
    status_anterior     TEXT,
    status_novo         TEXT,
    detalhes            TEXT,
    usuario             TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 7. Colunas Complementares Seguras em Tabelas Existentes
ALTER TABLE marcacoes_ponto ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE marcacoes_ponto ADD COLUMN IF NOT EXISTS tipo_marcacao TEXT;
ALTER TABLE marcacoes_ponto ADD COLUMN IF NOT EXISTS lote_importacao_id INTEGER;
ALTER TABLE marcacoes_ponto ADD COLUMN IF NOT EXISTS origem_detalhe TEXT;
ALTER TABLE marcacoes_ponto ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE marcacoes_ponto ADD COLUMN IF NOT EXISTS hash_marcacao TEXT;
ALTER TABLE marcacoes_ponto ADD COLUMN IF NOT EXISTS editada_por_ajuste_id INTEGER;

ALTER TABLE ocorrencias_ponto ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE ocorrencias_ponto ADD COLUMN IF NOT EXISTS minutos INTEGER DEFAULT 0;
ALTER TABLE ocorrencias_ponto ADD COLUMN IF NOT EXISTS cid TEXT;
ALTER TABLE ocorrencias_ponto ADD COLUMN IF NOT EXISTS justificativa_id INTEGER;
ALTER TABLE ocorrencias_ponto ADD COLUMN IF NOT EXISTS impacta_dsr INTEGER DEFAULT 0;
ALTER TABLE ocorrencias_ponto ADD COLUMN IF NOT EXISTS impacta_ferias INTEGER DEFAULT 0;
ALTER TABLE ocorrencias_ponto ADD COLUMN IF NOT EXISTS impacta_decimo INTEGER DEFAULT 0;
ALTER TABLE ocorrencias_ponto ADD COLUMN IF NOT EXISTS memoria_calculo TEXT;

ALTER TABLE ajustes_ponto ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE ajustes_ponto ADD COLUMN IF NOT EXISTS solicitante_usuario_id INTEGER;
ALTER TABLE ajustes_ponto ADD COLUMN IF NOT EXISTS aprovador_usuario_id INTEGER;
ALTER TABLE ajustes_ponto ADD COLUMN IF NOT EXISTS atualizado_em TEXT;

ALTER TABLE fechamentos_ponto ADD COLUMN IF NOT EXISTS resumo_json TEXT;

ALTER TABLE periodos_aquisitivos ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE periodos_aquisitivos ADD COLUMN IF NOT EXISTS dias_perdidos_faltas INTEGER DEFAULT 0;
ALTER TABLE periodos_aquisitivos ADD COLUMN IF NOT EXISTS memoria_calculo TEXT;

ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS numero_fracao INTEGER DEFAULT 1;
ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS media_variaveis NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS valor_adiantamento_13 NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS folha_id INTEGER;
ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS esocial_evento_id INTEGER;
ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT;
ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS memoria_calculo TEXT;
ALTER TABLE ferias_programadas ADD COLUMN IF NOT EXISTS pago_em TEXT;

ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS subtipo_licenca TEXT;
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS regime_efeito TEXT DEFAULT 'interrupcao';
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS cat_id INTEGER;
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS aso_retorno_id INTEGER;
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS esocial_inicio_id INTEGER;
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS esocial_termino_id INTEGER;
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS responsavel_registro TEXT;
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS observacoes TEXT;
ALTER TABLE afastamentos ADD COLUMN IF NOT EXISTS atualizado_em TEXT;

ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS tipo_aviso TEXT DEFAULT 'indenizado';
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS dias_aviso INTEGER DEFAULT 30;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS projecao_aviso_fim TEXT;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS saldo_fgts_informado NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS ferias_vencidas_dobro NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS terco_ferias_vencidas NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS terco_ferias_prop NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS media_variaveis NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS desconto_aviso_previo NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS desconto_faltas NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS aso_demissional_id INTEGER;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS homologado_por TEXT;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS homologado_em TEXT;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS esocial_evento_id INTEGER;
ALTER TABLE rescisoes ADD COLUMN IF NOT EXISTS memoria_calculo_json TEXT;

ALTER TABLE empresas ADD COLUMN IF NOT EXISTS aliquota_inss_patronal NUMERIC(6,2) DEFAULT 20.00;
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS aliquota_rat NUMERIC(6,2) DEFAULT 2.00;
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS fap NUMERIC(6,4) DEFAULT 1.0000;
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS aliquota_terceiros NUMERIC(6,2) DEFAULT 5.80;
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS banco_codigo TEXT DEFAULT '001';
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS banco_agencia TEXT DEFAULT '01234';
ALTER TABLE empresas ADD COLUMN IF NOT EXISTS banco_conta TEXT DEFAULT '000012345678';

ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS adicional_periculosidade INTEGER DEFAULT 0;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS adicional_insalubridade_grau TEXT DEFAULT 'nenhum';

CREATE INDEX IF NOT EXISTS idx_tab_legais_comp ON tabelas_legais_vigencia(competencia_inicio, ativo);
CREATE INDEX IF NOT EXISTS idx_feriados_data ON feriados_calendario(empresa_id, data_feriado);
CREATE INDEX IF NOT EXISTS idx_ponto_hash ON marcacoes_ponto(colaborador_id, hash_marcacao);
CREATE INDEX IF NOT EXISTS idx_ponto_idemp ON marcacoes_ponto(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_justif_colab ON ponto_justificativas(colaborador_id, status);
CREATE INDEX IF NOT EXISTS idx_bh_colab_comp ON ponto_banco_horas(colaborador_id, competencia);
CREATE INDEX IF NOT EXISTS idx_rateio_comp ON folha_rateio_centro_custo(empresa_id, competencia);
CREATE INDEX IF NOT EXISTS idx_fin_comp ON folha_integracao_financeira(empresa_id, competencia);
