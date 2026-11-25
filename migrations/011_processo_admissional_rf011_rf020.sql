-- =============================================================================
-- Migration 011: Consolidação do Processo Admissional (SRS Vol. 3 — RF-011 a RF-020)
-- Banco alvo: PostgreSQL 14+ (execução estritamente idempotente e incremental)
-- Não realiza DROP TABLE nem apaga dados existentes.
-- =============================================================================

-- 1. Expansão incremental da tabela admissoes (RF-011 a RF-020)
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS codigo_processo TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS candidato_data_nascimento TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS candidato_telefone TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS candidato_endereco TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS candidato_estado_civil TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS candidato_rg TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS candidato_pis TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS escala_id INTEGER;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS jornada_descricao TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS jornada_entrada TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS jornada_saida TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS jornada_intervalo_min INTEGER DEFAULT 60;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS jornada_dias_semana TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS jornada_carga_mensal REAL DEFAULT 220.0;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS jornada_vigencia_inicio TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS centro_custo_id TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS centro_custo_vigencia TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS gestor_responsavel TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS local_trabalho TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS aso_id INTEGER;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS contrato_id INTEGER;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS esocial_modalidade TEXT DEFAULT 'auto';
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS dupla_aprovacao_exigida INTEGER NOT NULL DEFAULT 0;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS primeira_aprovacao_por TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS primeira_aprovacao_em TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS justificativa_aprovacao TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS efetivado_por TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS efetivado_em TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS cancelado_por TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS cancelado_em TEXT;
ALTER TABLE admissoes ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT;

-- 2. Expansão incremental da tabela checklist_admissional (RF-012)
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS codigo_documento TEXT;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS nome_arquivo TEXT;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS caminho_privado TEXT;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS mime_type TEXT;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS tamanho_bytes INTEGER DEFAULT 0;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS sha256_hash TEXT;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS motivo_rejeicao TEXT;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS atualizado_por TEXT;
ALTER TABLE checklist_admissional ADD COLUMN IF NOT EXISTS atualizado_em TEXT;

-- 3. Expansão incremental da tabela sst_asos (RF-016 + sigilo médico)
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS admissao_id INTEGER;
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS status_exame TEXT NOT NULL DEFAULT 'realizado';
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS data_realizacao TEXT;
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS nome_arquivo TEXT;
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS caminho_privado TEXT;
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS mime_type TEXT;
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS sha256_hash TEXT;
ALTER TABLE sst_asos ADD COLUMN IF NOT EXISTS observacoes_medicas TEXT;

-- 4. Expansão incremental de colaboradores para vínculo explícito de escala e filial
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS escala_id INTEGER;
ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS filial_id TEXT;

-- 5. Histórico imutável de versões e eventos do checklist admissional (RF-012)
CREATE TABLE IF NOT EXISTS checklist_admissional_historico (
    id              SERIAL PRIMARY KEY,
    empresa_id      TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    admissao_id     INTEGER NOT NULL REFERENCES admissoes(id) ON DELETE CASCADE,
    checklist_id    INTEGER NOT NULL REFERENCES checklist_admissional(id) ON DELETE CASCADE,
    versao          INTEGER NOT NULL DEFAULT 1,
    acao            TEXT NOT NULL,
    status_anterior TEXT,
    status_novo     TEXT NOT NULL,
    nome_arquivo    TEXT,
    caminho_privado TEXT,
    sha256_hash     TEXT,
    justificativa   TEXT,
    usuario         TEXT NOT NULL,
    criado_em       TEXT NOT NULL
);

-- 6. Snapshots formais de validação admissional (RF-013 / RN-008 / RN-009)
CREATE TABLE IF NOT EXISTS admissao_validacoes (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    admissao_id         INTEGER NOT NULL REFERENCES admissoes(id) ON DELETE CASCADE,
    apto_efetivacao     INTEGER NOT NULL DEFAULT 0,
    aprovados_json      TEXT NOT NULL DEFAULT '[]',
    pendentes_json      TEXT NOT NULL DEFAULT '[]',
    invalidos_json      TEXT NOT NULL DEFAULT '[]',
    motivo_reprovacao   TEXT,
    validado_por        TEXT NOT NULL,
    validado_em         TEXT NOT NULL
);

-- 7. Modelos configuráveis de Contrato de Trabalho (RF-014)
CREATE TABLE IF NOT EXISTS admissao_contratos_modelos (
    id              SERIAL PRIMARY KEY,
    empresa_id      TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    codigo          TEXT NOT NULL UNIQUE,
    nome            TEXT NOT NULL,
    tipo_contrato   TEXT NOT NULL,
    titulo_documento TEXT NOT NULL,
    clausulas_json  TEXT NOT NULL,
    ativo           INTEGER NOT NULL DEFAULT 1,
    criado_por      TEXT NOT NULL DEFAULT 'Sistema',
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL
);

-- 8. Contratos de trabalho gerados e versionados por admissão (RF-014)
CREATE TABLE IF NOT EXISTS admissao_contratos (
    id                  SERIAL PRIMARY KEY,
    empresa_id          TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    admissao_id         INTEGER NOT NULL REFERENCES admissoes(id) ON DELETE CASCADE,
    modelo_id           INTEGER NOT NULL REFERENCES admissao_contratos_modelos(id),
    versao              INTEGER NOT NULL DEFAULT 1,
    nome_arquivo        TEXT NOT NULL,
    caminho_privado     TEXT NOT NULL,
    sha256_hash         TEXT NOT NULL,
    formalizado         INTEGER NOT NULL DEFAULT 0,
    formalizado_por     TEXT,
    formalizado_em      TEXT,
    condicoes_adicionais TEXT,
    dados_snapshot_json TEXT NOT NULL,
    gerado_por          TEXT NOT NULL,
    gerado_em           TEXT NOT NULL
);

-- 9. Histórico de atribuição de jornada na admissão (RF-017)
CREATE TABLE IF NOT EXISTS admissao_jornadas_historico (
    id              SERIAL PRIMARY KEY,
    empresa_id      TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    admissao_id     INTEGER NOT NULL REFERENCES admissoes(id) ON DELETE CASCADE,
    escala_id       INTEGER NOT NULL,
    descricao       TEXT NOT NULL,
    entrada         TEXT NOT NULL,
    saida           TEXT NOT NULL,
    intervalo_min   INTEGER NOT NULL DEFAULT 60,
    dias_semana     TEXT NOT NULL,
    carga_mensal    REAL NOT NULL DEFAULT 220.0,
    vigencia_inicio TEXT NOT NULL,
    definido_por    TEXT NOT NULL,
    definido_em     TEXT NOT NULL
);

-- 10. Histórico de vínculo de centro de custo na admissão (RF-018)
CREATE TABLE IF NOT EXISTS admissao_centros_custo_historico (
    id              SERIAL PRIMARY KEY,
    empresa_id      TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    admissao_id     INTEGER NOT NULL REFERENCES admissoes(id) ON DELETE CASCADE,
    centro_custo_id TEXT NOT NULL,
    filial_id       TEXT,
    vigencia_inicio TEXT NOT NULL,
    definido_por    TEXT NOT NULL,
    definido_em     TEXT NOT NULL
);

-- 11. Seleção de benefícios vinculados à admissão (RF-019)
CREATE TABLE IF NOT EXISTS admissao_beneficios (
    id                      SERIAL PRIMARY KEY,
    empresa_id              TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
    admissao_id             INTEGER NOT NULL REFERENCES admissoes(id) ON DELETE CASCADE,
    beneficio_id            INTEGER NOT NULL REFERENCES beneficios_catalogo(id),
    elegivel                INTEGER NOT NULL DEFAULT 1,
    motivo_inelegibilidade  TEXT,
    optante                 INTEGER NOT NULL DEFAULT 1,
    vigencia_inicio         TEXT NOT NULL,
    qtd_dependentes         INTEGER NOT NULL DEFAULT 0,
    valor_diario            REAL DEFAULT 0.0,
    valor_mensal_base       REAL DEFAULT 0.0,
    condicoes               TEXT,
    beneficio_colaborador_id INTEGER,
    status                  TEXT NOT NULL DEFAULT 'pendente_efetivacao',
    definido_por            TEXT NOT NULL,
    definido_em             TEXT NOT NULL
);

-- 12. Índices de performance e integridade
CREATE INDEX IF NOT EXISTS idx_admissoes_empresa_status ON admissoes(empresa_id, status);
CREATE INDEX IF NOT EXISTS idx_admissoes_cpf ON admissoes(candidato_cpf);
CREATE INDEX IF NOT EXISTS idx_chk_hist_admissao ON checklist_admissional_historico(admissao_id, checklist_id);
CREATE INDEX IF NOT EXISTS idx_adm_val_admissao ON admissao_validacoes(admissao_id);
CREATE INDEX IF NOT EXISTS idx_adm_contratos_admissao ON admissao_contratos(admissao_id, versao);
CREATE INDEX IF NOT EXISTS idx_adm_jornada_admissao ON admissao_jornadas_historico(admissao_id);
CREATE INDEX IF NOT EXISTS idx_adm_cc_admissao ON admissao_centros_custo_historico(admissao_id);
CREATE INDEX IF NOT EXISTS idx_adm_benef_admissao ON admissao_beneficios(admissao_id);
CREATE INDEX IF NOT EXISTS idx_sst_asos_admissao ON sst_asos(admissao_id);

-- 13. Seed idempotente dos modelos contratuais padrão (RF-014)
INSERT INTO admissao_contratos_modelos (empresa_id, codigo, nome, tipo_contrato, titulo_documento, clausulas_json, ativo, criado_por, criado_em, atualizado_em)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'CLT_INDETERMINADO', 'Contrato Individual de Trabalho — Prazo Indeterminado', 'CLT', 'CONTRATO INDIVIDUAL DE TRABALHO POR PRAZO INDETERMINADO', '["Cláusula 1ª — Objeto e Função: O EMPREGADO é admitido para exercer o cargo indicado neste instrumento, subordinando-se às normas internas da EMPREGADORA.","Cláusula 2ª — Remuneração: O EMPREGADO perceberá o salário contratual ajustado, com descontos legais previstos na CLT e legislação previdenciária/tributária vigente.","Cláusula 3ª — Jornada de Trabalho: O cumprimento da jornada observará a escala e os intervalos intrajornada formalmente registrados no sistema de ponto.","Cláusula 4ª — Prazo e Vigência: O presente contrato vigora por prazo indeterminado a partir da data de admissão.","Cláusula 5ª — Confidencialidade e Proteção de Dados: As partes comprometem-se ao sigilo profissional e à observância da Lei Geral de Proteção de Dados (Lei nº 13.709/2018)."]', 1, 'Sistema', CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('a0000000-0000-0000-0000-000000000001', 'EXPERIENCIA', 'Contrato Individual de Trabalho a Título de Experiência', 'experiencia', 'CONTRATO INDIVIDUAL DE TRABALHO DE EXPERIÊNCIA (ART. 443 §2º ALÍNEA C CLT)', '["Cláusula 1ª — Objeto: Contratação em caráter experimental para avaliação mútua de adaptação às atividades do cargo proposto.","Cláusula 2ª — Prazo de Experiência: Vigência inicial e eventual prorrogação única respeitando o limite legal máximo de 90 (noventa) dias (art. 445 parágrafo único da CLT).","Cláusula 3ª — Remuneração e Jornada: A remuneração mensal e a escala inicial constam do quadro contratual deste instrumento.","Cláusula 4ª — Conversão Automática: Findo o prazo experimental sem manifestação contrária de qualquer das partes, o contrato passa a vigorar por prazo indeterminado."]', 1, 'Sistema', CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('a0000000-0000-0000-0000-000000000001', 'APRENDIZ', 'Contrato de Aprendizagem Profissional (Lei nº 10.097/2000)', 'aprendiz', 'CONTRATO ESPECIAL DE APRENDIZAGEM PROFISSIONAL', '["Cláusula 1ª — Objeto: Formação técnico-profissional metódica compatível com o desenvolvimento físico, moral e psicológico do aprendiz (art. 428 da CLT).","Cláusula 2ª — Jornada e Remuneração: Jornada respeitando os limites legais aplicáveis ao contrato de aprendizagem e remuneração proporcional assegurada.","Cláusula 3ª — Alíquota FGTS: Recolhimento mensal de FGTS nos termos do art. 15 §7º da Lei nº 8.036/1990 (2%)."]', 1, 'Sistema', CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('a0000000-0000-0000-0000-000000000001', 'ESTAGIO', 'Termo de Compromisso de Estágio (Lei nº 11.788/2008)', 'estagio', 'TERMO DE COMPROMISSO DE ESTÁGIO SUPERVISIONADO', '["Cláusula 1ª — Natureza: Estágio supervisionado sem vínculo empregatício, regido pela Lei nº 11.788/2008.","Cláusula 2ª — Bolsa-Auxílio e Carga Horária: Concessão de bolsa-auxílio e jornada compatível com o horário escolar.","Cláusula 3ª — Recesso e Seguro: Assegurado recesso remunerado proporcional e cobertura de seguro contra acidentes pessoais."]', 1, 'Sistema', CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT),
    ('a0000000-0000-0000-0000-000000000001', 'TEMPORARIO', 'Contrato de Trabalho Temporário (Lei nº 6.019/1974)', 'temporario', 'CONTRATO DE TRABALHO TEMPORÁRIO', '["Cláusula 1ª — Objeto e Motivo: Prestação de serviços temporários para substituição transitória de pessoal ou demanda complementar de serviços.","Cláusula 2ª — Remuneração e Direitos: Assegurada remuneração equivalente à dos empregados da mesma categoria e cumprimento da escala designada."]', 1, 'Sistema', CURRENT_TIMESTAMP::TEXT, CURRENT_TIMESTAMP::TEXT)
ON CONFLICT (codigo) DO NOTHING;
