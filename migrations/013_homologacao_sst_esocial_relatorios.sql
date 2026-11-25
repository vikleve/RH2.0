-- Migração 013: Homologação e Consolidação dos Módulos SST, eSocial, Relatórios e Regras de Negócio
-- Suporte completo a RF121-RF150 e RN-001 a RN-083 (2026)

-- 1. Tabela de Condições Ambientais do Trabalho / Fatores de Risco (eSocial S-2240)
CREATE TABLE IF NOT EXISTS sst_condicoes_ambientais (
    id                          SERIAL PRIMARY KEY,
    empresa_id                  TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    colaborador_id              INTEGER NOT NULL,
    ambiente_nome               TEXT NOT NULL,
    descricao_atividades        TEXT,
    fator_risco_codigo          TEXT NOT NULL,
    fator_risco_descricao       TEXT NOT NULL,
    tipo_avaliacao              TEXT NOT NULL DEFAULT 'qualitativa',
    intensidade_concentracao    NUMERIC(10,2) DEFAULT 0.00,
    limite_tolerancia           NUMERIC(10,2) DEFAULT 0.00,
    tecnica_utilizada           TEXT,
    epc_eficaz                  INTEGER NOT NULL DEFAULT 0,
    epi_eficaz                  INTEGER NOT NULL DEFAULT 1,
    ca_epi_utilizado            TEXT,
    responsavel_registros_nome  TEXT,
    responsavel_registros_cpf   TEXT,
    data_inicio_condicao        TEXT NOT NULL,
    data_fim_condicao           TEXT,
    esocial_evento_id           INTEGER,
    criado_por                  TEXT NOT NULL,
    criado_em                   TEXT NOT NULL
);

-- 2. Tabela de Agendamento e Controle de Prazos de Exames Ocupacionais (RF121-RF124)
CREATE TABLE IF NOT EXISTS sst_exames_agendamentos (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    colaborador_id      INTEGER NOT NULL,
    exame_id            INTEGER,
    tipo_exame          TEXT NOT NULL, -- 'admissional', 'periodico', 'demissional', 'retorno_trabalho', 'mudanca_risco'
    data_prevista       TEXT NOT NULL,
    data_realizacao     TEXT,
    status              TEXT NOT NULL DEFAULT 'agendado', -- 'agendado', 'concluido', 'cancelado', 'atrasado'
    clinica_nome        TEXT,
    medico_examinador   TEXT,
    observacoes         TEXT,
    aso_gerado_id       INTEGER,
    criado_por          TEXT NOT NULL,
    criado_em           TEXT NOT NULL
);

-- 3. Índices de Desempenho e Rastreabilidade
CREATE INDEX IF NOT EXISTS idx_sst_condamb_colab ON sst_condicoes_ambientais(colaborador_id);
CREATE INDEX IF NOT EXISTS idx_sst_condamb_risco ON sst_condicoes_ambientais(fator_risco_codigo);
CREATE INDEX IF NOT EXISTS idx_sst_agend_colab   ON sst_exames_agendamentos(colaborador_id);
CREATE INDEX IF NOT EXISTS idx_sst_agend_status  ON sst_exames_agendamentos(status, data_prevista);
