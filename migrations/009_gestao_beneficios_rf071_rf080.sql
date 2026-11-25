-- ============================================================================
-- MIGRAÇÃO POSTGRESQL — MÓDULO DE GESTÃO DE BENEFÍCIOS E DESCONTOS (RF071–RF080)
-- Arquivo: migrations/009_gestao_beneficios_rf071_rf080.sql
-- Descrição: Expande beneficios_catalogo e beneficios_colaborador para suportar
--            Vale-Transporte, VA/VR, Plano de Saúde c/ dependentes, Seguro de Vida,
--            Convênio Farmácia c/ limite mensal, Benefícios Flexíveis, Elegibilidade
--            e Integração direta com a Folha de Pagamento.
-- ============================================================================

BEGIN;

-- 1. Expansão de beneficios_catalogo
ALTER TABLE beneficios_catalogo ADD COLUMN IF NOT EXISTS rubrica_codigo TEXT DEFAULT '0511';
ALTER TABLE beneficios_catalogo ADD COLUMN IF NOT EXISTS valor_mensal_padrao NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_catalogo ADD COLUMN IF NOT EXISTS valor_diario_padrao NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_catalogo ADD COLUMN IF NOT EXISTS limite_padrao NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_catalogo ADD COLUMN IF NOT EXISTS descricao TEXT;
ALTER TABLE beneficios_catalogo ADD COLUMN IF NOT EXISTS atualizado_em TEXT;

-- 2. Expansão de beneficios_colaborador
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS valor_mensal_base NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS qtd_dependentes INTEGER DEFAULT 0;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS valor_dependente NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS coparticipacao_extra NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS limite_mensal NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS valor_utilizado_mes NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS saldo_flexivel NUMERIC(12,2) DEFAULT 0.00;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS alocacao_json TEXT;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS observacoes TEXT;
ALTER TABLE beneficios_colaborador ADD COLUMN IF NOT EXISTS atualizado_em TEXT;

-- 3. Índices de performance
CREATE INDEX IF NOT EXISTS idx_benef_cat_tipo ON beneficios_catalogo(tipo);
CREATE INDEX IF NOT EXISTS idx_benef_colab_colab ON beneficios_colaborador(colaborador_id);
CREATE INDEX IF NOT EXISTS idx_benef_colab_benef ON beneficios_colaborador(beneficio_id);

-- 4. Atualização de rubricas e inclusão idempotente de Benefícios Flexíveis (RF077)
UPDATE beneficios_catalogo SET rubrica_codigo = '0510', valor_diario_padrao = COALESCE(NULLIF(valor_diario_padrao, 0), 12.00) WHERE codigo = 'VT01';
UPDATE beneficios_catalogo SET rubrica_codigo = '0511', valor_mensal_padrao = COALESCE(NULLIF(valor_mensal_padrao, 0), 650.00) WHERE codigo = 'VA01';
UPDATE beneficios_catalogo SET rubrica_codigo = '0511', valor_diario_padrao = COALESCE(NULLIF(valor_diario_padrao, 0), 35.00) WHERE codigo = 'VR01';
UPDATE beneficios_catalogo SET rubrica_codigo = '0512', valor_mensal_padrao = COALESCE(NULLIF(valor_mensal_padrao, 0), 480.00) WHERE codigo = 'PS01';
UPDATE beneficios_catalogo SET rubrica_codigo = '0514', valor_mensal_padrao = COALESCE(NULLIF(valor_mensal_padrao, 0), 45.00) WHERE codigo = 'SV01';
UPDATE beneficios_catalogo SET rubrica_codigo = '0516', limite_padrao = COALESCE(NULLIF(limite_padrao, 0), 400.00), coparticipacao_tipo = 'percentual', coparticipacao_valor = 100.00, teto_legal_percentual = 100.00 WHERE codigo = 'FAR01';

INSERT INTO beneficios_catalogo (
    empresa_id, codigo, nome, tipo, coparticipacao_tipo, coparticipacao_valor,
    teto_legal_percentual, regra_elegibilidade, rubrica_codigo, valor_mensal_padrao,
    valor_diario_padrao, limite_padrao, descricao, ativo, criado_em, atualizado_em
)
SELECT
    'a0000000-0000-0000-0000-000000000001',
    'FLEX01',
    'Carteira de Benefícios Flexíveis Caju / Swile',
    'beneficio_flexivel',
    'fixo',
    0.00,
    0.00,
    '{"situacoes_permitidas":["ativo"],"tipos_contrato_permitidos":["CLT"],"tempo_minimo_dias":0}',
    '0517',
    600.00,
    0.00,
    600.00,
    'Saldo mensal flexível distribuível entre alimentação, mobilidade, saúde, educação e cultura',
    1,
    TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS'),
    TO_CHAR(NOW(), 'YYYY-MM-DD HH24:MI:SS')
WHERE NOT EXISTS (
    SELECT 1 FROM beneficios_catalogo WHERE codigo = 'FLEX01'
);

COMMIT;
