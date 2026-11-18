-- ============================================================================
-- MIGRAÇÃO POSTGRESQL / RH2.0 — AJUSTE DE PRECISÃO NUMÉRICA EM FOLHA_ITENS
-- Arquivo: migrations/006_ajuste_precisao_folha_itens.sql
-- SPEC-PATCH-FOLHA-001 — Seção 9: Substituição segura dos tipos REAL por NUMERIC
-- ============================================================================

BEGIN;

DO $$
BEGIN
    -- Altera referencia para NUMERIC(10,2) preservando dados
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'folha_itens' AND column_name = 'referencia'
    ) THEN
        ALTER TABLE folha_itens ALTER COLUMN referencia TYPE NUMERIC(10,2) USING round(referencia::numeric, 2);
    END IF;

    -- Altera valor_unitario para NUMERIC(15,2) preservando dados
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'folha_itens' AND column_name = 'valor_unitario'
    ) THEN
        ALTER TABLE folha_itens ALTER COLUMN valor_unitario TYPE NUMERIC(15,2) USING round(valor_unitario::numeric, 2);
    END IF;

    -- Altera valor_total para NUMERIC(15,2) preservando dados
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'folha_itens' AND column_name = 'valor_total'
    ) THEN
        ALTER TABLE folha_itens ALTER COLUMN valor_total TYPE NUMERIC(15,2) USING round(valor_total::numeric, 2);
    END IF;
END $$;

COMMIT;
