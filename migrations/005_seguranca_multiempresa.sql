-- ============================================================================
-- MIGRAÇÃO POSTGRESQL — SEGURANÇA MULTIEMPRESA & IDOR (SPEC-03.1)
-- Arquivo: migrations/005_seguranca_multiempresa.sql
-- Descrição: Adiciona colunas de controle de escopo multi-tenant e abrangência
--            na tabela de usuários (empresa_id, filial_id, empresas_autorizadas).
-- ============================================================================

BEGIN;

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS filial_id TEXT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresas_autorizadas TEXT;

CREATE INDEX IF NOT EXISTS idx_usuarios_empresa_id ON usuarios(empresa_id);

COMMIT;
