-- ============================================================================
-- MIGRAÇÃO POSTGRESQL — CONSOLIDAÇÃO CADASTRAL RF-005 A RF-010 (RH2.0 ENTERPRISE)
-- Arquivo: migrations/010_consolidacao_colaborador_rf005_rf010.sql
-- Descrição:
--   RF-005: Expansão de dependentes (tipo_dependencia, plano de saúde, situação lógica, datas)
--   RF-006: Tabela imutável historico_funcional
--   RF-007: Expansão de colaborador_documentos (storage privado, segurança, versões, inativação)
--   RF-008: Categorias configuráveis e configuração de alertas de vencimento (30/15/7 dias)
--   RF-009: Dados bancários por colaborador (integrados ao CNAB 240)
--   RF-010: Expansão da auditoria cadastral em historico_alteracoes
-- ============================================================================

BEGIN;

-- RF-005: Dependentes completos com inativação lógica e plano de saúde
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS tipo_dependencia TEXT DEFAULT 'legal';
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS eh_plano_saude INTEGER NOT NULL DEFAULT 0;
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS situacao TEXT NOT NULL DEFAULT 'ativo';
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS data_inclusao TEXT;
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS data_encerramento TEXT;
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS observacoes TEXT;
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS criado_em TEXT;
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS atualizado_em TEXT;

-- RF-006: Histórico Funcional imutável e cronológico
CREATE TABLE IF NOT EXISTS historico_funcional (
    id                  SERIAL PRIMARY KEY,
    colaborador_id      INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    empresa_id          TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    tipo_movimentacao   TEXT NOT NULL,
    campo_afetado       TEXT NOT NULL,
    valor_anterior      TEXT,
    valor_novo          TEXT NOT NULL,
    data_alteracao      TEXT NOT NULL,
    data_vigencia       TEXT NOT NULL,
    retroativa          INTEGER NOT NULL DEFAULT 0,
    justificativa       TEXT NOT NULL DEFAULT '',
    observacoes         TEXT,
    usuario_responsavel TEXT NOT NULL,
    origem              TEXT DEFAULT 'API',
    ip_origem           TEXT,
    criado_em           TEXT NOT NULL
);

-- RF-007: Anexos Cadastrais seguros, versionados e com inativação lógica
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS categoria TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS nome_interno_seguro TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS caminho_privado TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS sha256_hash TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS data_emissao TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS data_validade TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS situacao TEXT NOT NULL DEFAULT 'ativo';
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS documento_raiz_id INTEGER;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS atualizado_por TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS atualizado_em TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS inativado_por TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS inativado_em TEXT;
ALTER TABLE colaborador_documentos ADD COLUMN IF NOT EXISTS motivo_inativacao TEXT;

-- RF-008: Categorias configuráveis e alertas de documentação
CREATE TABLE IF NOT EXISTS documentos_categorias (
    id              SERIAL PRIMARY KEY,
    empresa_id      TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    codigo          TEXT NOT NULL,
    nome            TEXT NOT NULL,
    obrigatorio     INTEGER NOT NULL DEFAULT 0,
    exige_validade  INTEGER NOT NULL DEFAULT 0,
    ativo           INTEGER NOT NULL DEFAULT 1,
    criado_em       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documentos_config_alertas (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    dias_alertas_json   TEXT NOT NULL DEFAULT '[30, 15, 7]',
    tamanho_max_mb      INTEGER NOT NULL DEFAULT 10,
    atualizado_por      TEXT NOT NULL,
    atualizado_em       TEXT NOT NULL
);

-- RF-009: Dados Bancários por Colaborador
CREATE TABLE IF NOT EXISTS colaborador_dados_bancarios (
    id              SERIAL PRIMARY KEY,
    colaborador_id  INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    empresa_id      TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    banco_codigo    TEXT NOT NULL,
    banco_nome      TEXT NOT NULL,
    agencia         TEXT NOT NULL,
    agencia_digito  TEXT,
    conta           TEXT NOT NULL,
    conta_digito    TEXT,
    tipo_conta      TEXT NOT NULL DEFAULT 'corrente',
    chave_pix_tipo  TEXT,
    chave_pix       TEXT,
    titular_nome    TEXT NOT NULL,
    titular_cpf     TEXT NOT NULL,
    principal       INTEGER NOT NULL DEFAULT 1,
    ativo           INTEGER NOT NULL DEFAULT 1,
    criado_por      TEXT NOT NULL,
    criado_em       TEXT NOT NULL,
    atualizado_por  TEXT,
    atualizado_em   TEXT
);

-- RF-010: Expansão de Auditoria Cadastral
ALTER TABLE historico_alteracoes ADD COLUMN IF NOT EXISTS entidade TEXT DEFAULT 'colaborador';
ALTER TABLE historico_alteracoes ADD COLUMN IF NOT EXISTS operacao TEXT DEFAULT 'alteracao';
ALTER TABLE historico_alteracoes ADD COLUMN IF NOT EXISTS origem TEXT;
ALTER TABLE historico_alteracoes ADD COLUMN IF NOT EXISTS ip_origem TEXT;
ALTER TABLE historico_alteracoes ADD COLUMN IF NOT EXISTS justificativa TEXT;

-- Índices
CREATE INDEX IF NOT EXISTS idx_hist_func_colab   ON historico_funcional(colaborador_id);
CREATE INDEX IF NOT EXISTS idx_hist_func_tipo    ON historico_funcional(tipo_movimentacao);
CREATE INDEX IF NOT EXISTS idx_doc_validade      ON colaborador_documentos(data_validade);
CREATE INDEX IF NOT EXISTS idx_doc_situacao      ON colaborador_documentos(situacao);
CREATE INDEX IF NOT EXISTS idx_doc_raiz          ON colaborador_documentos(documento_raiz_id);
CREATE INDEX IF NOT EXISTS idx_banco_colab       ON colaborador_dados_bancarios(colaborador_id);

-- Seed idempotente das 10 categorias padrão e alertas [30, 15, 7]
INSERT INTO documentos_categorias (empresa_id, codigo, nome, obrigatorio, exige_validade, ativo, criado_em)
SELECT 'a0000000-0000-0000-0000-000000000001', v.codigo, v.nome, v.obrigatorio, v.exige_validade, 1, TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
FROM (VALUES
    ('RG', 'RG', 1, 0),
    ('CPF', 'CPF', 1, 0),
    ('COMPROVANTE_RESIDENCIA', 'Comprovante de Residência', 1, 1),
    ('CTPS', 'Carteira de Trabalho', 1, 0),
    ('CONTRATO_TRABALHO', 'Contrato de Trabalho', 1, 0),
    ('ADITIVOS_CONTRATUAIS', 'Aditivos Contratuais', 0, 0),
    ('CERTIFICADOS', 'Certificados', 0, 1),
    ('DIPLOMAS', 'Diplomas', 0, 0),
    ('ATESTADOS', 'Atestados', 0, 1),
    ('OUTROS', 'Documentos Diversos', 0, 0)
) AS v(codigo, nome, obrigatorio, exige_validade)
WHERE NOT EXISTS (
    SELECT 1 FROM documentos_categorias dc WHERE dc.codigo = v.codigo
);

INSERT INTO documentos_config_alertas (empresa_id, dias_alertas_json, tamanho_max_mb, atualizado_por, atualizado_em)
SELECT 'a0000000-0000-0000-0000-000000000001', '[30, 15, 7]', 10, 'Sistema', TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
WHERE NOT EXISTS (
    SELECT 1 FROM documentos_config_alertas WHERE empresa_id = 'a0000000-0000-0000-0000-000000000001'
);

COMMIT;
