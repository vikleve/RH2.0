-- =============================================================================
-- Migração 006: Precisão Monetária (NUMERIC) e Parâmetros da Empresa Empregadora
-- Garante conformidade com o Neon PostgreSQL, eliminando truncamento de casas decimais
-- e permitindo customização dinâmica dos dados da empresa no contracheque / holerite.
-- =============================================================================

-- 1. Precisão monetária em folha_itens (NUMERIC(15,2))
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'folha_itens' AND column_name = 'referencia' AND data_type = 'real'
    ) THEN
        ALTER TABLE folha_itens ALTER COLUMN referencia TYPE NUMERIC(15,2);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'folha_itens' AND column_name = 'valor_unitario' AND data_type = 'real'
    ) THEN
        ALTER TABLE folha_itens ALTER COLUMN valor_unitario TYPE NUMERIC(15,2);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'folha_itens' AND column_name = 'valor_total' AND data_type = 'real'
    ) THEN
        ALTER TABLE folha_itens ALTER COLUMN valor_total TYPE NUMERIC(15,2);
    END IF;
END $$;

-- 2. Campos da empresa empregadora na tabela folha_parametros
ALTER TABLE folha_parametros ADD COLUMN IF NOT EXISTS razao_social TEXT DEFAULT 'PORTAL DP & RH LTDA';
ALTER TABLE folha_parametros ADD COLUMN IF NOT EXISTS cnpj TEXT DEFAULT '12.345.678/0001-90';
ALTER TABLE folha_parametros ADD COLUMN IF NOT EXISTS endereco_empresa TEXT DEFAULT 'Av. Paulista, 1000 - Bela Vista, São Paulo - SP';
ALTER TABLE folha_parametros ADD COLUMN IF NOT EXISTS telefone_empresa TEXT DEFAULT '(11) 3456-7890';
ALTER TABLE folha_parametros ADD COLUMN IF NOT EXISTS email_empresa TEXT DEFAULT 'contato@portaldprh.com.br';

-- 3. Atualizar registro padrão caso os campos estejam nulos
UPDATE folha_parametros
SET 
    razao_social = COALESCE(razao_social, 'PORTAL DP & RH LTDA'),
    cnpj = COALESCE(cnpj, '12.345.678/0001-90'),
    endereco_empresa = COALESCE(endereco_empresa, 'Av. Paulista, 1000 - Bela Vista, São Paulo - SP'),
    telefone_empresa = COALESCE(telefone_empresa, '(11) 3456-7890'),
    email_empresa = COALESCE(email_empresa, 'contato@portaldprh.com.br')
WHERE codigo = 'PADRAO_CLT_2026';
