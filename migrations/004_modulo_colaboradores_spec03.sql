-- ============================================================================
-- MIGRAÇÃO POSTGRESQL — MÓDULO DE CADASTRO DE COLABORADORES (SPEC-03)
-- Arquivo: migrations/004_modulo_colaboradores_spec03.sql
-- Descrição: Extensão da tabela colaboradores para suportar segregação
--            multi-empresa, dados complementares e índices de busca.
-- ============================================================================

BEGIN;

-- Permite que data_admissao seja nula conforme SPEC-03 Seção 4.1
ALTER TABLE colaboradores ALTER COLUMN data_admissao DROP NOT NULL;

-- Adiciona empresa_id com UUID padrão corporativo para registros legados
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS empresa_id TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS filial_id TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS departamento_id TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS cargo_id TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS sexo TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS estado_civil TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS celular TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS complemento TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS observacoes TEXT;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS criado_por TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS atualizado_por TEXT;

-- Índices de performance para busca textual e filtros organizacionais
CREATE INDEX IF NOT EXISTS idx_colab_empresa_id       ON colaboradores(empresa_id);
CREATE INDEX IF NOT EXISTS idx_colab_filial_id        ON colaboradores(filial_id);
CREATE INDEX IF NOT EXISTS idx_colab_departamento_id  ON colaboradores(departamento_id);
CREATE INDEX IF NOT EXISTS idx_colab_cargo_id         ON colaboradores(cargo_id);
CREATE INDEX IF NOT EXISTS idx_colab_empresa_cpf      ON colaboradores(empresa_id, cpf);
CREATE INDEX IF NOT EXISTS idx_colab_empresa_mat      ON colaboradores(empresa_id, matricula);

COMMIT;
