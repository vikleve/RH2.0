-- ============================================================================
-- MIGRATION 014: Homologação de Benefícios, Rescisões, Segurança e Auditoria
-- Atende a:
-- RN-036 a RN-038 (Benefícios: elegibilidade, coparticipação e histórico)
-- RN-054 a RN-060 (Rescisões: modalidades legais incluindo Culpa Recíproca)
-- RN-068 a RN-074 (Segurança: RBAC, sigilo salarial, dados sensíveis, imutabilidade)
-- RF-161 a RF-170 (Autenticação, sessões em hash, recuperação de senha, rate limit compartilhado)
-- RF-191 a RF-200 (Auditoria empresarial, hash chaining, trilha de integridade)
-- ============================================================================

-- 1. Histórico de Benefícios (RN-038)
CREATE TABLE IF NOT EXISTS beneficios_historico (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    vinculo_id          INTEGER NOT NULL,
    colaborador_id      INTEGER NOT NULL,
    beneficio_id        INTEGER NOT NULL,
    operacao            TEXT NOT NULL, -- CONCESSAO, ALTERACAO_VALOR, SUSPENSAO, CANCELAMENTO, REATIVACAO
    valor_anterior      REAL DEFAULT 0.00,
    valor_novo          REAL DEFAULT 0.00,
    custo_empresa       REAL DEFAULT 0.00,
    desconto_colab      REAL DEFAULT 0.00,
    motivo              TEXT,
    usuario_responsavel TEXT NOT NULL,
    criado_em           TEXT NOT NULL,
    FOREIGN KEY (beneficio_id) REFERENCES beneficios_catalogo(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_benef_hist_colab ON beneficios_historico(colaborador_id);
CREATE INDEX IF NOT EXISTS idx_benef_hist_vinculo ON beneficios_historico(vinculo_id);

-- 2. Recuperação Segura de Senha (RF-162)
CREATE TABLE IF NOT EXISTS recuperacao_senha (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id     INTEGER NOT NULL,
    token_hash     TEXT NOT NULL UNIQUE,
    criado_em      TEXT NOT NULL,
    expira_em      TEXT NOT NULL,
    usado          INTEGER NOT NULL DEFAULT 0,
    ip_solicitacao TEXT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recup_senha_hash ON recuperacao_senha(token_hash);

-- 3. Rate Limiting Compartilhado no Banco de Dados (RF-161, AC-07)
CREATE TABLE IF NOT EXISTS rate_limit_tentativas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chave      TEXT NOT NULL,
    timestamp  REAL NOT NULL,
    ip_origem  TEXT,
    recurso    TEXT DEFAULT 'login'
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_chave_time ON rate_limit_tentativas(chave, timestamp);

-- 4. Triggers de Imutabilidade dos Registros de Auditoria (RN-073)
CREATE TRIGGER IF NOT EXISTS trg_auditoria_operacoes_no_update
BEFORE UPDATE ON auditoria_operacoes
BEGIN
    SELECT RAISE(ABORT, 'Operação proibida: logs de auditoria operacional são estritamente imutáveis (RN-073).');
END;

CREATE TRIGGER IF NOT EXISTS trg_auditoria_operacoes_no_delete
BEFORE DELETE ON auditoria_operacoes
BEGIN
    SELECT RAISE(ABORT, 'Operação proibida: logs de auditoria operacional não podem ser excluídos (RN-073).');
END;

CREATE TRIGGER IF NOT EXISTS trg_auditoria_autenticacao_no_update
BEFORE UPDATE ON auditoria_autenticacao
BEGIN
    SELECT RAISE(ABORT, 'Operação proibida: logs de autenticação são estritamente imutáveis (RN-073).');
END;

CREATE TRIGGER IF NOT EXISTS trg_auditoria_autenticacao_no_delete
BEFORE DELETE ON auditoria_autenticacao
BEGIN
    SELECT RAISE(ABORT, 'Operação proibida: logs de autenticação não podem ser excluídos (RN-073).');
END;
