-- ============================================================================
-- MIGRAÇÃO POSTGRESQL — MÓDULO DE COLABORADORES E FOLHA ENTERPRISE COMPLETA
-- Arquivo: migrations/008_folha_enterprise_completa.sql
-- Descrição: Adiciona campos pessoais/contratuais de colaboradores,
--            atributos fiscais de dependentes (IRRF e Salário-Família),
--            catálogo parametrizável de rubricas (folha_rubricas),
--            tipos de folha, aprovação e documentos de colaboradores.
-- ============================================================================

BEGIN;

-- 1. Expansão cadastral de colaboradores
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS pis_pasep TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS departamento TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS centro_custo TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS tipo_contrato TEXT DEFAULT 'CLT';
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS jornada_trabalho TEXT DEFAULT '44h semanais';
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS carga_horaria_mensal NUMERIC(6,2) DEFAULT 220.00;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'colaboradores' AND constraint_name = 'colaboradores_situacao_check'
    ) THEN
        ALTER TABLE colaboradores DROP CONSTRAINT colaboradores_situacao_check;
    END IF;
    ALTER TABLE colaboradores ADD CONSTRAINT colaboradores_situacao_check
        CHECK (situacao IN ('ativo', 'inativo', 'afastado', 'ferias', 'desligado'));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

-- 2. Dependentes: data de nascimento e indicadores fiscais/previdenciários
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS data_nascimento TEXT;
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS eh_dependente_irrf INTEGER NOT NULL DEFAULT 1;
ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS eh_elegivel_salario_familia INTEGER NOT NULL DEFAULT 0;

-- 3. Documentos do colaborador (anexos cadastrais)
CREATE TABLE IF NOT EXISTS colaborador_documentos (
    id              SERIAL PRIMARY KEY,
    colaborador_id  INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
    empresa_id      TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    tipo_documento  TEXT NOT NULL,
    nome_arquivo    TEXT NOT NULL,
    mime_type       TEXT,
    tamanho_bytes   INTEGER DEFAULT 0,
    conteudo_base64 TEXT,
    observacao      TEXT,
    enviado_por     TEXT NOT NULL,
    criado_em       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_colab_docs_colab ON colaborador_documentos(colaborador_id);

-- 4. Catálogo parametrizável de rubricas da folha
CREATE TABLE IF NOT EXISTS folha_rubricas (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    codigo              TEXT NOT NULL,
    descricao           TEXT NOT NULL,
    tipo                TEXT NOT NULL CHECK (tipo IN ('provento', 'desconto', 'informativo')),
    categoria           TEXT DEFAULT 'Proventos',
    natureza            TEXT DEFAULT 'salarial',
    forma_calculo       TEXT DEFAULT 'valor_fixo',
    valor_padrao        NUMERIC(15,4) DEFAULT 0.0000,
    referencia_padrao   NUMERIC(10,2) DEFAULT 0.00,
    incide_inss         INTEGER NOT NULL DEFAULT 0,
    incide_irrf         INTEGER NOT NULL DEFAULT 0,
    incide_fgts         INTEGER NOT NULL DEFAULT 0,
    incide_outras_bases INTEGER NOT NULL DEFAULT 0,
    reflexo_ferias      INTEGER NOT NULL DEFAULT 0,
    reflexo_13          INTEGER NOT NULL DEFAULT 0,
    vigencia_inicio     TEXT NOT NULL DEFAULT '2026-01-01',
    vigencia_fim        TEXT,
    ativo               INTEGER NOT NULL DEFAULT 1,
    sistema_legal       INTEGER NOT NULL DEFAULT 0,
    observacao          TEXT,
    criado_em           TEXT NOT NULL,
    atualizado_em       TEXT NOT NULL,
    CONSTRAINT unq_rubrica_empresa_codigo UNIQUE (empresa_id, codigo)
);
CREATE INDEX IF NOT EXISTS idx_rubricas_codigo ON folha_rubricas(codigo);
CREATE INDEX IF NOT EXISTS idx_rubricas_tipo   ON folha_rubricas(tipo);

-- 5. Expansão de folhas_pagamento para multi-empresa, filial, tipo de folha, aprovação e encargos
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS empresa_id TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS filial_id TEXT;
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS tipo_folha TEXT NOT NULL DEFAULT 'mensal';
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1;
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS aprovado_por TEXT;
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS aprovado_em TEXT;
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS inss_descontado NUMERIC(15,2) NOT NULL DEFAULT 0.00;
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS irrf_descontado NUMERIC(15,2) NOT NULL DEFAULT 0.00;
ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS encargos_patronais NUMERIC(15,2) NOT NULL DEFAULT 0.00;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'folhas_pagamento' AND constraint_name = 'unq_colab_competencia'
    ) THEN
        ALTER TABLE folhas_pagamento DROP CONSTRAINT unq_colab_competencia;
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'folhas_pagamento' AND constraint_name = 'folhas_pagamento_situacao_check'
    ) THEN
        ALTER TABLE folhas_pagamento DROP CONSTRAINT folhas_pagamento_situacao_check;
    END IF;
    ALTER TABLE folhas_pagamento ADD CONSTRAINT folhas_pagamento_situacao_check
        CHECK (situacao IN ('rascunho', 'calculada', 'aprovada', 'fechada', 'cancelada'));
EXCEPTION WHEN OTHERS THEN
    NULL;
END $$;

ALTER TABLE folha_itens ADD COLUMN IF NOT EXISTS incide_inss INTEGER NOT NULL DEFAULT 0;
ALTER TABLE folha_itens ADD COLUMN IF NOT EXISTS incide_irrf INTEGER NOT NULL DEFAULT 0;
ALTER TABLE folha_itens ADD COLUMN IF NOT EXISTS incide_fgts INTEGER NOT NULL DEFAULT 0;

COMMIT;
