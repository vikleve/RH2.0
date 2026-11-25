-- ============================================================================
-- Migração 015 — Otimização de Autenticação, Sessões e Desempenho (Neon/PG)
-- 100% compatível, não destrutiva e idempotente (IF NOT EXISTS).
-- ============================================================================

-- 1. Campos de controle de atividade e teto máximo absoluto na tabela sessoes
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS ultima_atividade TEXT;
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS expira_absoluto_em TEXT;

-- Preencher sessões já existentes de forma segura (sem apagar ou invalidar sessões válidas)
UPDATE sessoes
SET ultima_atividade = COALESCE(ultima_atividade, criado_em),
    expira_absoluto_em = COALESCE(expira_absoluto_em, expira_em)
WHERE ultima_atividade IS NULL OR expira_absoluto_em IS NULL;

-- 2. Garantir colunas de auditoria e empresa_id sem abortar transação
ALTER TABLE auditoria_operacoes ADD COLUMN IF NOT EXISTS hash_anterior TEXT;
ALTER TABLE auditoria_operacoes ADD COLUMN IF NOT EXISTS hash_atual TEXT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';

-- 3. Índices justificados pelo plano de execução das consultas críticas
-- Login usa WHERE LOWER(email) = %s OR LOWER(usuario) = %s
CREATE INDEX IF NOT EXISTS idx_usuario_email_lower ON usuarios (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_usuario_login_lower ON usuarios (LOWER(usuario));

-- Validação, renovação e controle de sessões simultâneas por usuário
CREATE INDEX IF NOT EXISTS idx_sessao_user_revogado ON sessoes (usuario_id, revogado);
CREATE INDEX IF NOT EXISTS idx_sessao_expira_em ON sessoes (expira_em);

-- Listagem de colaboradores por empresa e situação (tela principal e BI)
CREATE INDEX IF NOT EXISTS idx_colab_empresa_situacao ON colaboradores (empresa_id, situacao);
