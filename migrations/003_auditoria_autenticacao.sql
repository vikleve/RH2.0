-- ============================================================================
-- MIGRAÇÃO — AUDITORIA DE AUTENTICAÇÃO E SEGURANÇA (RF-LOGIN-006)
-- Arquivo: migrations/003_auditoria_autenticacao.sql
-- Registra eventos de autenticação sem armazenar senhas, tokens ou dados sensíveis.
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS auditoria_autenticacao (
    id             SERIAL PRIMARY KEY,
    evento         TEXT NOT NULL CHECK (evento IN ('LOGIN_SUCESSO', 'LOGIN_FALHA', 'LOGOUT', 'BLOQUEIO_RATE_LIMIT')),
    identificador  TEXT,
    ip_origem      TEXT,
    detalhes       TEXT,
    criado_em      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_auth_evento ON auditoria_autenticacao(evento);
CREATE INDEX IF NOT EXISTS idx_audit_auth_data   ON auditoria_autenticacao(criado_em);
CREATE INDEX IF NOT EXISTS idx_audit_auth_ip     ON auditoria_autenticacao(ip_origem);

ALTER TABLE auditoria_autenticacao ENABLE ROW LEVEL SECURITY;

COMMIT;

