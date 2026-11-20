"""
Modulo de Banco de Dados — Dual-mode: PostgreSQL (producao) + SQLite (local/testes)
Camada de persistencia relacional com integridade referencial.
Atende a RF-01 a RF-09, CA-07, CA-08.

Em producao (Vercel): DATABASE_URL e OBRIGATORIA (PostgreSQL: Supabase, Neon, etc).
  Sem ela a aplicacao falha de forma explicita (DatabaseConfigError) — NAO ha fallback
  silencioso para SQLite, cujo arquivo em /tmp nao persiste entre execucoes serverless.
Em desenvolvimento local: usa SQLite se DATABASE_URL nao estiver definida.
Os testes passam db_path explicito => sempre SQLite isolado.
"""
import os
import sqlite3
import tempfile
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Configuracao de Ambiente e Drivers
# ─────────────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _env_file = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(_env_file):
        load_dotenv(_env_file)
except ImportError:
    pass

class DatabaseConfigError(RuntimeError):
    """Configuracao de banco ausente/invalida (ex.: DATABASE_URL ausente em producao)."""


class DatabaseUnavailableError(RuntimeError):
    """Banco indisponivel. A mensagem NUNCA contem a URL/credenciais de conexao."""


def em_producao() -> bool:
    """True quando rodando na Vercel ou com ambiente marcado como producao."""
    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        return True
    for nome in ("APP_ENV", "ENVIRONMENT", "NODE_ENV", "ENV"):
        if (os.environ.get(nome) or "").strip().lower() in ("production", "prod", "producao"):
            return True
    return False


def erro_http(exc: Exception):
    """
    Converte uma excecao em (status, corpo_json) para respostas da API.
    Falhas de banco => 503 com mensagem clara e sem detalhes sensiveis.
    """
    if isinstance(exc, (DatabaseConfigError, DatabaseUnavailableError)):
        return 503, {
            "sucesso": False,
            "codigo": "BANCO_INDISPONIVEL",
            "mensagem": str(exc),
        }
    try:
        import psycopg2
        if isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)):
            return 503, {
                "sucesso": False,
                "codigo": "BANCO_INDISPONIVEL",
                "mensagem": "Banco de dados indisponivel no momento. A operacao nao foi realizada.",
            }
    except ImportError:
        pass
    return 500, {"sucesso": False, "mensagem": f"Erro interno: {exc}"}


_SQLITE_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(tempfile.gettempdir(), "colaboradores.db") if os.environ.get("VERCEL")
    else os.path.join(os.path.dirname(__file__), "..", "colaboradores.db")
)


def get_database_url() -> str:
    """
    Retorna a URL do banco PostgreSQL a partir das variaveis de ambiente:
    - DATABASE_URL (Supabase, Railway, Neon, Render, Docker, etc.)
    - POSTGRES_URL / POSTGRES_PRISMA_URL (integracao nativa da Vercel)
    - Variaveis individuais PGHOST, PGDATABASE, PGUSER, PGPASSWORD
    """
    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("NEON_DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("POSTGRES_PRISMA_URL")
        or os.environ.get("POSTGRES_URL_NON_POOLING")
        or ""
    ).strip()

    if not url and os.environ.get("PGHOST") and os.environ.get("PGDATABASE"):
        user = os.environ.get("PGUSER", "postgres")
        pwd = os.environ.get("PGPASSWORD", "")
        host = os.environ.get("PGHOST", "localhost")
        port = os.environ.get("PGPORT", "5432")
        db = os.environ.get("PGDATABASE", "rh_db")
        url = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
    return url


# ─────────────────────────────────────────────────────────────────────────────
# Deteccao do modo
# ─────────────────────────────────────────────────────────────────────────────

def _usar_postgres(db_path: str = None) -> bool:
    """
    Retorna True se devemos usar PostgreSQL.
    Se db_path for fornecido explicitamente, usa SQLite com esse caminho (ex: testes).
    """
    if db_path:
        return False
    if get_database_url():
        return True
    if em_producao():
        raise DatabaseConfigError(
            "DATABASE_URL nao configurada: o PostgreSQL e obrigatorio em producao. "
            "Cadastre a variavel como segredo no ambiente Production da Vercel."
        )
    return False  # desenvolvimento local: SQLite


def _get_pg_conn():
    """Retorna conexao psycopg2 para PostgreSQL com tratamento de DSN e SSL."""
    try:
        import psycopg2
    except ImportError:
        raise ImportError(
            "psycopg2-binary nao encontrado. Execute: pip install psycopg2-binary"
        )
    url = get_database_url()
    if not url:
        raise DatabaseConfigError("DATABASE_URL nao configurada: o PostgreSQL e obrigatorio.")
    dsn = url.replace("postgres://", "postgresql://", 1)

    # Se for servico em nuvem (Neon, Supabase, Railway, Render) e nao especificar sslmode, garante sslmode=require
    if (
        "localhost" not in dsn
        and "127.0.0.1" not in dsn
        and "sslmode=" not in dsn
    ):
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"

    if "connect_timeout=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "connect_timeout=" + os.environ.get("DB_CONNECT_TIMEOUT", "15")

    try:
        return psycopg2.connect(dsn)
    except psycopg2.OperationalError:
        # Nao propaga a mensagem original: ela pode revelar host/usuario do banco.
        raise DatabaseUnavailableError(
            "Banco de dados indisponivel no momento. A operacao nao foi realizada e nenhum dado foi salvo."
        ) from None


def _get_sqlite_conn(db_path: str = None) -> sqlite3.Connection:
    """Retorna conexao SQLite para desenvolvimento local ou testes."""
    caminho = os.path.abspath(db_path if db_path else _SQLITE_PATH)
    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_connection(db_path: str = None):
    """
    Retorna conexao ao banco de dados correto:
      - SQLite no caminho db_path se fornecido (testes isolados / dev especifico)
      - PostgreSQL se DATABASE_URL estiver definida e db_path nao for fornecido
      - SQLite padrao caso contrario
    """
    if _usar_postgres(db_path):
        return _get_pg_conn()
    return _get_sqlite_conn(db_path)


# ─────────────────────────────────────────────────────────────────────────────
# DDL
# ─────────────────────────────────────────────────────────────────────────────

_DDL_COLABORADORES_PG = """
    CREATE TABLE IF NOT EXISTS colaboradores (
        id               SERIAL PRIMARY KEY,
        empresa_id       TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
        matricula        TEXT UNIQUE NOT NULL,
        nome_completo    TEXT NOT NULL,
        cpf              TEXT UNIQUE NOT NULL,
        rg               TEXT,
        data_nascimento  TEXT NOT NULL,
        telefone         TEXT,
        email            TEXT NOT NULL,
        logradouro       TEXT,
        numero           TEXT,
        bairro           TEXT,
        cidade           TEXT,
        uf               TEXT,
        cep              TEXT,
        data_admissao    TEXT NOT NULL,
        cargo            TEXT NOT NULL,
        setor            TEXT NOT NULL,
        departamento     TEXT,
        centro_custo     TEXT,
        tipo_contrato    TEXT DEFAULT 'CLT',
        jornada_trabalho TEXT DEFAULT '44h semanais',
        carga_horaria_mensal NUMERIC(6,2) DEFAULT 220.00,
        pis_pasep        TEXT,
        sexo             TEXT,
        estado_civil     TEXT,
        salario_base     NUMERIC(15,2) NOT NULL,
        situacao         TEXT NOT NULL DEFAULT 'ativo'
                         CHECK (situacao IN ('ativo', 'inativo', 'afastado', 'ferias', 'desligado')),
        criado_em        TEXT NOT NULL,
        atualizado_em    TEXT NOT NULL
    );
"""

_DDL_COLABORADORES_SQLITE = """
    CREATE TABLE IF NOT EXISTS colaboradores (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id       TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
        matricula        TEXT UNIQUE NOT NULL,
        nome_completo    TEXT NOT NULL,
        cpf              TEXT UNIQUE NOT NULL,
        rg               TEXT,
        data_nascimento  TEXT NOT NULL,
        telefone         TEXT,
        email            TEXT NOT NULL,
        logradouro       TEXT,
        numero           TEXT,
        bairro           TEXT,
        cidade           TEXT,
        uf               TEXT,
        cep              TEXT,
        data_admissao    TEXT NOT NULL,
        cargo            TEXT NOT NULL,
        setor            TEXT NOT NULL,
        departamento     TEXT,
        centro_custo     TEXT,
        tipo_contrato    TEXT DEFAULT 'CLT',
        jornada_trabalho TEXT DEFAULT '44h semanais',
        carga_horaria_mensal REAL DEFAULT 220.0,
        pis_pasep        TEXT,
        sexo             TEXT,
        estado_civil     TEXT,
        salario_base     REAL NOT NULL,
        situacao         TEXT NOT NULL DEFAULT 'ativo'
                         CHECK (situacao IN ('ativo', 'inativo', 'afastado', 'ferias', 'desligado')),
        criado_em        TEXT NOT NULL,
        atualizado_em    TEXT NOT NULL
    );
"""

_DDL_DEPENDENTES = """
    CREATE TABLE IF NOT EXISTS dependentes (
        id                          {serial} PRIMARY KEY,
        colaborador_id              INTEGER NOT NULL
                                    REFERENCES colaboradores(id) ON DELETE CASCADE,
        nome                        TEXT NOT NULL,
        cpf                         TEXT,
        parentesco                  TEXT NOT NULL,
        data_nascimento             TEXT,
        eh_dependente_irrf          INTEGER NOT NULL DEFAULT 1,
        eh_elegivel_salario_familia INTEGER NOT NULL DEFAULT 0
    );
"""

_DDL_HISTORICO = """
    CREATE TABLE IF NOT EXISTS historico_alteracoes (
        id                  {serial} PRIMARY KEY,
        colaborador_id      INTEGER NOT NULL
                            REFERENCES colaboradores(id) ON DELETE CASCADE,
        data_hora           TEXT NOT NULL,
        campo_alterado      TEXT NOT NULL,
        valor_anterior      TEXT,
        valor_novo          TEXT,
        usuario_responsavel TEXT NOT NULL DEFAULT 'Sistema/Administrador'
    );
"""

_DDL_USUARIOS_PG = """
    CREATE TABLE IF NOT EXISTS usuarios (
        id            SERIAL PRIMARY KEY,
        email         TEXT UNIQUE NOT NULL,
        usuario       TEXT UNIQUE NOT NULL,
        nome_completo TEXT NOT NULL,
        senha_hash    TEXT NOT NULL,
        salt          TEXT NOT NULL,
        perfil        TEXT NOT NULL
                      CHECK (perfil IN (
                          'superadmin', 'admin_empresa', 'gestor_rh', 'analista_dp',
                          'financeiro', 'contabilidade', 'gestor_departamento', 'colaborador',
                          'administrador', 'analista_rh', 'operador_dp', 'gestor', 'medico_sst', 'auditor'
                      )),
        status        TEXT NOT NULL DEFAULT 'ativo'
                      CHECK (status IN ('ativo', 'inativo')),
        criado_em     TEXT NOT NULL,
        ultimo_login  TEXT
    );
"""

_DDL_USUARIOS_SQLITE = """
    CREATE TABLE IF NOT EXISTS usuarios (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        email         TEXT UNIQUE NOT NULL,
        usuario       TEXT UNIQUE NOT NULL,
        nome_completo TEXT NOT NULL,
        senha_hash    TEXT NOT NULL,
        salt          TEXT NOT NULL,
        perfil        TEXT NOT NULL CHECK (perfil IN (
                          'superadmin', 'admin_empresa', 'gestor_rh', 'analista_dp',
                          'financeiro', 'contabilidade', 'gestor_departamento', 'colaborador',
                          'administrador', 'analista_rh', 'operador_dp', 'gestor', 'medico_sst', 'auditor'
                      )),
        status        TEXT NOT NULL DEFAULT 'ativo' CHECK (status IN ('ativo', 'inativo')),
        criado_em     TEXT NOT NULL,
        ultimo_login  TEXT
    );
"""

_DDL_SESSOES = """
    CREATE TABLE IF NOT EXISTS sessoes (
        token        TEXT PRIMARY KEY,
        usuario_id   INTEGER NOT NULL
                     REFERENCES usuarios(id) ON DELETE CASCADE,
        criado_em    TEXT NOT NULL,
        expira_em    TEXT NOT NULL,
        revogado     INTEGER NOT NULL DEFAULT 0
    );
"""

_DDL_FOLHA_PARAMETROS_PG = """
    CREATE TABLE IF NOT EXISTS folha_parametros (
        id                          SERIAL PRIMARY KEY,
        codigo                      TEXT UNIQUE NOT NULL,
        descricao                   TEXT NOT NULL,
        vigencia_inicio             TEXT NOT NULL,
        vigencia_fim                TEXT,
        horas_mensais_padrao        NUMERIC(6,2) NOT NULL DEFAULT 220.00,
        dias_mes_padrao             INTEGER NOT NULL DEFAULT 30,
        percentual_he_padrao        NUMERIC(5,2) NOT NULL DEFAULT 50.00,
        percentual_he_extra         NUMERIC(5,2) NOT NULL DEFAULT 100.00,
        percentual_adicional_noturno NUMERIC(5,2) NOT NULL DEFAULT 20.00,
        aplicar_reducao_noturna     INTEGER NOT NULL DEFAULT 0,
        fator_reducao_noturna       NUMERIC(8,6) NOT NULL DEFAULT 1.142857,
        aplicar_inss                INTEGER NOT NULL DEFAULT 1,
        aplicar_irrf                INTEGER NOT NULL DEFAULT 1,
        aliquota_fgts               NUMERIC(5,2) NOT NULL DEFAULT 8.00,
        teto_inss                   NUMERIC(15,2) NOT NULL DEFAULT 8157.41,
        deducao_dependente_irrf     NUMERIC(15,2) NOT NULL DEFAULT 189.59,
        ativo                       INTEGER NOT NULL DEFAULT 1,
        validado_por_profissional   INTEGER NOT NULL DEFAULT 0,
        criado_em                   TEXT NOT NULL,
        atualizado_em               TEXT NOT NULL
    );
"""

_DDL_FOLHA_PARAMETROS_SQLITE = """
    CREATE TABLE IF NOT EXISTS folha_parametros (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo                      TEXT UNIQUE NOT NULL,
        descricao                   TEXT NOT NULL,
        vigencia_inicio             TEXT NOT NULL,
        vigencia_fim                TEXT,
        horas_mensais_padrao        REAL NOT NULL DEFAULT 220.00,
        dias_mes_padrao             INTEGER NOT NULL DEFAULT 30,
        percentual_he_padrao        REAL NOT NULL DEFAULT 50.00,
        percentual_he_extra         REAL NOT NULL DEFAULT 100.00,
        percentual_adicional_noturno REAL NOT NULL DEFAULT 20.00,
        aplicar_reducao_noturna     INTEGER NOT NULL DEFAULT 0,
        fator_reducao_noturna       REAL NOT NULL DEFAULT 1.142857,
        aplicar_inss                INTEGER NOT NULL DEFAULT 1,
        aplicar_irrf                INTEGER NOT NULL DEFAULT 1,
        aliquota_fgts               REAL NOT NULL DEFAULT 8.00,
        teto_inss                   REAL NOT NULL DEFAULT 8157.41,
        deducao_dependente_irrf     REAL NOT NULL DEFAULT 189.59,
        ativo                       INTEGER NOT NULL DEFAULT 1,
        validado_por_profissional   INTEGER NOT NULL DEFAULT 0,
        criado_em                   TEXT NOT NULL,
        atualizado_em               TEXT NOT NULL
    );
"""

_DDL_FOLHAS_PAGAMENTO_PG = """
    CREATE TABLE IF NOT EXISTS folhas_pagamento (
        id                          SERIAL PRIMARY KEY,
        empresa_id                  TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
        filial_id                   TEXT,
        colaborador_id              INTEGER NOT NULL
                                    REFERENCES colaboradores(id) ON DELETE RESTRICT,
        competencia                 TEXT NOT NULL,
        tipo_folha                  TEXT NOT NULL DEFAULT 'mensal',
        versao                      INTEGER NOT NULL DEFAULT 1,
        periodo_inicio              TEXT NOT NULL,
        periodo_fim                 TEXT NOT NULL,
        data_pagamento              TEXT,
        dias_trabalhados            NUMERIC(4,1) NOT NULL DEFAULT 30.0,
        dias_mes                    INTEGER NOT NULL DEFAULT 30,
        horas_mensais_divisor       NUMERIC(6,2) NOT NULL DEFAULT 220.00,
        salario_base_contratual     NUMERIC(15,2) NOT NULL,
        salario_base_proporcional   NUMERIC(15,2) NOT NULL,
        total_proventos             NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        total_descontos             NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        salario_liquido             NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        base_inss                   NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        base_fgts                   NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        valor_fgts_informativo      NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        base_irrf                   NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        inss_descontado             NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        irrf_descontado             NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        encargos_patronais          NUMERIC(15,2) NOT NULL DEFAULT 0.00,
        situacao                    TEXT NOT NULL DEFAULT 'rascunho'
                                    CHECK (situacao IN ('rascunho', 'calculada', 'aprovada', 'fechada', 'cancelada')),
        observacoes                 TEXT,
        parametro_id                INTEGER REFERENCES folha_parametros(id),
        criado_por                  TEXT NOT NULL,
        criado_em                   TEXT NOT NULL,
        atualizado_por              TEXT,
        atualizado_em               TEXT,
        aprovado_por                TEXT,
        aprovado_em                 TEXT,
        fechado_por                 TEXT,
        fechado_em                  TEXT
    );
"""

_DDL_FOLHAS_PAGAMENTO_SQLITE = """
    CREATE TABLE IF NOT EXISTS folhas_pagamento (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id                  TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
        filial_id                   TEXT,
        colaborador_id              INTEGER NOT NULL
                                    REFERENCES colaboradores(id) ON DELETE RESTRICT,
        competencia                 TEXT NOT NULL,
        tipo_folha                  TEXT NOT NULL DEFAULT 'mensal',
        versao                      INTEGER NOT NULL DEFAULT 1,
        periodo_inicio              TEXT NOT NULL,
        periodo_fim                 TEXT NOT NULL,
        data_pagamento              TEXT,
        dias_trabalhados            REAL NOT NULL DEFAULT 30.0,
        dias_mes                    INTEGER NOT NULL DEFAULT 30,
        horas_mensais_divisor       REAL NOT NULL DEFAULT 220.00,
        salario_base_contratual     REAL NOT NULL,
        salario_base_proporcional   REAL NOT NULL,
        total_proventos             REAL NOT NULL DEFAULT 0.00,
        total_descontos             REAL NOT NULL DEFAULT 0.00,
        salario_liquido             REAL NOT NULL DEFAULT 0.00,
        base_inss                   REAL NOT NULL DEFAULT 0.00,
        base_fgts                   REAL NOT NULL DEFAULT 0.00,
        valor_fgts_informativo      REAL NOT NULL DEFAULT 0.00,
        base_irrf                   REAL NOT NULL DEFAULT 0.00,
        inss_descontado             REAL NOT NULL DEFAULT 0.00,
        irrf_descontado             REAL NOT NULL DEFAULT 0.00,
        encargos_patronais          REAL NOT NULL DEFAULT 0.00,
        situacao                    TEXT NOT NULL DEFAULT 'rascunho'
                                    CHECK (situacao IN ('rascunho', 'calculada', 'aprovada', 'fechada', 'cancelada')),
        observacoes                 TEXT,
        parametro_id                INTEGER REFERENCES folha_parametros(id),
        criado_por                  TEXT NOT NULL,
        criado_em                   TEXT NOT NULL,
        atualizado_por              TEXT,
        atualizado_em               TEXT,
        aprovado_por                TEXT,
        aprovado_em                 TEXT,
        fechado_por                 TEXT,
        fechado_em                  TEXT
    );
"""

_DDL_FOLHA_ITENS = """
    CREATE TABLE IF NOT EXISTS folha_itens (
        id                  {serial} PRIMARY KEY,
        folha_id            INTEGER NOT NULL
                            REFERENCES folhas_pagamento(id) ON DELETE CASCADE,
        codigo_evento       TEXT NOT NULL,
        descricao           TEXT NOT NULL,
        tipo                TEXT NOT NULL CHECK (tipo IN ('provento', 'desconto', 'informativo')),
        referencia          REAL DEFAULT 0.0,
        unidade_referencia  TEXT,
        valor_unitario      REAL DEFAULT 0.0,
        valor_total         REAL NOT NULL DEFAULT 0.0,
        origem              TEXT NOT NULL DEFAULT 'calculado'
                            CHECK (origem IN ('sistema', 'calculado', 'manual', 'importado')),
        incide_inss         INTEGER NOT NULL DEFAULT 0,
        incide_irrf         INTEGER NOT NULL DEFAULT 0,
        incide_fgts         INTEGER NOT NULL DEFAULT 0,
        memoria_calculo     TEXT,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_FOLHA_RUBRICAS = """
    CREATE TABLE IF NOT EXISTS folha_rubricas (
        id                  {pk},
        empresa_id          TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001',
        codigo              TEXT NOT NULL,
        descricao           TEXT NOT NULL,
        tipo                TEXT NOT NULL CHECK (tipo IN ('provento', 'desconto', 'informativo')),
        categoria           TEXT DEFAULT 'Proventos',
        natureza            TEXT DEFAULT 'salarial',
        forma_calculo       TEXT DEFAULT 'valor_fixo',
        valor_padrao        REAL DEFAULT 0.0,
        referencia_padrao   REAL DEFAULT 0.0,
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
        UNIQUE (empresa_id, codigo)
    );
"""

_DDL_COLABORADOR_DOCUMENTOS = """
    CREATE TABLE IF NOT EXISTS colaborador_documentos (
        id              {pk},
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
"""

_DDL_FOLHA_HISTORICO = """
    CREATE TABLE IF NOT EXISTS folha_historico (
        id                  {serial} PRIMARY KEY,
        folha_id            INTEGER NOT NULL
                            REFERENCES folhas_pagamento(id) ON DELETE CASCADE,
        data_hora           TEXT NOT NULL,
        acao                TEXT NOT NULL,
        descricao           TEXT NOT NULL,
        dados_anteriores    TEXT,
        dados_novos         TEXT,
        usuario_responsavel TEXT NOT NULL
    );
"""

_DDL_AUDITORIA_AUTENTICACAO_PG = """
    CREATE TABLE IF NOT EXISTS auditoria_autenticacao (
        id             SERIAL PRIMARY KEY,
        evento         TEXT NOT NULL CHECK (evento IN ('LOGIN_SUCESSO', 'LOGIN_FALHA', 'LOGOUT', 'BLOQUEIO_RATE_LIMIT')),
        identificador  TEXT,
        ip_origem      TEXT,
        detalhes       TEXT,
        criado_em      TEXT NOT NULL
    );
"""

_DDL_AUDITORIA_AUTENTICACAO_SQLITE = """
    CREATE TABLE IF NOT EXISTS auditoria_autenticacao (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        evento         TEXT NOT NULL CHECK (evento IN ('LOGIN_SUCESSO', 'LOGIN_FALHA', 'LOGOUT', 'BLOQUEIO_RATE_LIMIT')),
        identificador  TEXT,
        ip_origem      TEXT,
        detalhes       TEXT,
        criado_em      TEXT NOT NULL
    );
"""

# ─────────────────────────────────────────────────────────────────────────────
# DDL — Plataforma de Gestão do Ciclo Trabalhista (Módulos 01 a 20)
# ─────────────────────────────────────────────────────────────────────────────

_DDL_EMPRESAS = """
    CREATE TABLE IF NOT EXISTS empresas (
        id                  TEXT PRIMARY KEY,
        cnpj                TEXT UNIQUE NOT NULL,
        razao_social        TEXT NOT NULL,
        nome_fantasia       TEXT,
        regime_tributario   TEXT NOT NULL DEFAULT 'lucro_real',
        responsavel_nome    TEXT,
        responsavel_cpf     TEXT,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL,
        atualizado_em       TEXT NOT NULL
    );
"""

_DDL_FILIAIS = """
    CREATE TABLE IF NOT EXISTS filiais (
        id                  TEXT PRIMARY KEY,
        empresa_id          TEXT NOT NULL,
        codigo_filial       TEXT NOT NULL,
        nome                TEXT NOT NULL,
        cnpj                TEXT NOT NULL,
        cidade              TEXT NOT NULL,
        uf                  TEXT NOT NULL,
        feriados_locais     TEXT,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_CENTROS_CUSTO = """
    CREATE TABLE IF NOT EXISTS centros_custo (
        id                  TEXT PRIMARY KEY,
        empresa_id          TEXT NOT NULL,
        codigo              TEXT NOT NULL,
        descricao           TEXT NOT NULL,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_ADMISSOES = """
    CREATE TABLE IF NOT EXISTS admissoes (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        filial_id           TEXT,
        candidato_nome      TEXT NOT NULL,
        candidato_cpf       TEXT NOT NULL,
        candidato_email     TEXT NOT NULL,
        cargo               TEXT NOT NULL,
        setor               TEXT NOT NULL,
        salario_proposto    REAL NOT NULL,
        tipo_contrato       TEXT NOT NULL DEFAULT 'experiencia',
        prazo_experiencia_dias INTEGER DEFAULT 45,
        prorrogacao_experiencia_dias INTEGER DEFAULT 45,
        data_prevista_admissao TEXT NOT NULL,
        status              TEXT NOT NULL DEFAULT 'em_andamento',
        motivo_reprovacao   TEXT,
        aprovado_por        TEXT,
        aprovado_em         TEXT,
        colaborador_id      INTEGER,
        aso_admissional_status TEXT DEFAULT 'pendente',
        contrato_gerado     INTEGER DEFAULT 0,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL,
        atualizado_em       TEXT NOT NULL
    );
"""

_DDL_CHECKLIST_ADMISSONAL = """
    CREATE TABLE IF NOT EXISTS checklist_admissional (
        id                  {pk},
        admissao_id         INTEGER NOT NULL,
        item_descricao      TEXT NOT NULL,
        obrigatorio         INTEGER NOT NULL DEFAULT 1,
        status              TEXT NOT NULL DEFAULT 'pendente',
        justificativa_dispensa TEXT,
        arquivo_url         TEXT,
        validado_por        TEXT,
        validado_em         TEXT
    );
"""

_DDL_ESCALAS_JORNADA = """
    CREATE TABLE IF NOT EXISTS escalas_jornada (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        codigo              TEXT NOT NULL,
        descricao           TEXT NOT NULL,
        carga_semanal_horas REAL NOT NULL DEFAULT 44.00,
        divisor_mensal      REAL NOT NULL DEFAULT 220.00,
        tipo_regime         TEXT NOT NULL DEFAULT '5x2',
        entrada_padrao      TEXT NOT NULL DEFAULT '08:00',
        saida_padrao        TEXT NOT NULL DEFAULT '17:48',
        intervalo_minutos   INTEGER NOT NULL DEFAULT 60,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_MARCACOES_PONTO = """
    CREATE TABLE IF NOT EXISTS marcacoes_ponto (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        data                TEXT NOT NULL,
        hora                TEXT NOT NULL,
        tipo_registro       TEXT NOT NULL DEFAULT 'automatico',
        id_coletor          TEXT,
        arquivo_origem      TEXT,
        inconsistente       INTEGER DEFAULT 0,
        motivo_inconsistencia TEXT,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_OCORRENCIAS_PONTO = """
    CREATE TABLE IF NOT EXISTS ocorrencias_ponto (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        data_inicio         TEXT NOT NULL,
        data_fim            TEXT NOT NULL,
        tipo_ocorrencia     TEXT NOT NULL,
        minutos_ausencia    INTEGER DEFAULT 0,
        justificativa       TEXT NOT NULL,
        comprovante_anexo   TEXT,
        desconta_dsr        INTEGER DEFAULT 0,
        status              TEXT NOT NULL DEFAULT 'pendente',
        aprovado_por        TEXT,
        aprovado_em         TEXT,
        motivo_reprovacao   TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_AJUSTES_PONTO = """
    CREATE TABLE IF NOT EXISTS ajustes_ponto (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        data                TEXT NOT NULL,
        hora_original       TEXT,
        hora_ajustada       TEXT NOT NULL,
        tipo_marcacao       TEXT NOT NULL,
        motivo              TEXT NOT NULL,
        status              TEXT NOT NULL DEFAULT 'pendente',
        aprovado_por        TEXT,
        aprovado_em         TEXT,
        motivo_reprovacao   TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_FECHAMENTOS_PONTO = """
    CREATE TABLE IF NOT EXISTS fechamentos_ponto (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        filial_id           TEXT,
        competencia         TEXT NOT NULL,
        fechado_em          TEXT NOT NULL,
        fechado_por         TEXT NOT NULL,
        situacao            TEXT NOT NULL DEFAULT 'fechado',
        justificativa_reabertura TEXT,
        reaberto_por        TEXT,
        reaberto_em         TEXT
    );
"""

_DDL_PERIODOS_AQUISITIVOS = """
    CREATE TABLE IF NOT EXISTS periodos_aquisitivos (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        inicio_aquisitivo   TEXT NOT NULL,
        fim_aquisitivo      TEXT NOT NULL,
        limite_concessivo   TEXT NOT NULL,
        faltas_injustificadas INTEGER NOT NULL DEFAULT 0,
        dias_direito        INTEGER NOT NULL DEFAULT 30,
        dias_gozados        INTEGER NOT NULL DEFAULT 0,
        saldo_dias          INTEGER NOT NULL DEFAULT 30,
        situacao            TEXT NOT NULL DEFAULT 'adquirido',
        criado_em           TEXT NOT NULL,
        atualizado_em       TEXT NOT NULL
    );
"""

_DDL_FERIAS_PROGRAMADAS = """
    CREATE TABLE IF NOT EXISTS ferias_programadas (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        periodo_aquisitivo_id INTEGER,
        data_inicio         TEXT NOT NULL,
        data_fim            TEXT NOT NULL,
        dias_gozo           INTEGER NOT NULL,
        abono_pecuniario    INTEGER NOT NULL DEFAULT 0,
        dias_abono          INTEGER NOT NULL DEFAULT 0,
        adiantar_decimo     INTEGER NOT NULL DEFAULT 0,
        aviso_ferias_emitido TEXT,
        data_pagamento_limite TEXT,
        valor_ferias        REAL DEFAULT 0.00,
        valor_terco         REAL DEFAULT 0.00,
        valor_abono         REAL DEFAULT 0.00,
        valor_terco_abono   REAL DEFAULT 0.00,
        desconto_inss       REAL DEFAULT 0.00,
        desconto_irrf       REAL DEFAULT 0.00,
        valor_liquido       REAL DEFAULT 0.00,
        em_dobro            INTEGER NOT NULL DEFAULT 0,
        status              TEXT NOT NULL DEFAULT 'solicitada',
        aprovado_por        TEXT,
        aprovado_em         TEXT,
        motivo_reprovacao   TEXT,
        competencia_folha   TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_AFASTAMENTOS = """
    CREATE TABLE IF NOT EXISTS afastamentos (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        tipo                TEXT NOT NULL,
        motivo_esocial      TEXT NOT NULL DEFAULT '01',
        data_inicio         TEXT NOT NULL,
        data_fim_prevista   TEXT NOT NULL,
        data_retorno_efetivo TEXT,
        cid                 TEXT,
        estabilidade_fim    TEXT,
        dias_empresa        INTEGER DEFAULT 15,
        dias_inss           INTEGER DEFAULT 0,
        exige_aso_retorno   INTEGER DEFAULT 0,
        aso_retorno_realizado INTEGER DEFAULT 0,
        status_esocial      TEXT DEFAULT 'pendente',
        recibo_esocial      TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_BENEFICIOS_CATALOGO = """
    CREATE TABLE IF NOT EXISTS beneficios_catalogo (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        codigo              TEXT NOT NULL,
        nome                TEXT NOT NULL,
        tipo                TEXT NOT NULL,
        coparticipacao_tipo TEXT NOT NULL DEFAULT 'percentual',
        coparticipacao_valor REAL DEFAULT 0.00,
        teto_legal_percentual REAL DEFAULT 6.00,
        regra_elegibilidade TEXT,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_BENEFICIOS_COLABORADOR = """
    CREATE TABLE IF NOT EXISTS beneficios_colaborador (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        beneficio_id        INTEGER NOT NULL,
        optante             INTEGER NOT NULL DEFAULT 1,
        valor_diario        REAL DEFAULT 0.00,
        dias_uteis_mes      INTEGER DEFAULT 22,
        custo_total_mes     REAL DEFAULT 0.00,
        desconto_colaborador REAL DEFAULT 0.00,
        custo_empresa       REAL DEFAULT 0.00,
        vigencia_inicio     TEXT NOT NULL,
        vigencia_fim        TEXT,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_DECIMO_TERCEIRO = """
    CREATE TABLE IF NOT EXISTS decimo_terceiro (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        ano_base            INTEGER NOT NULL,
        parcela             INTEGER NOT NULL,
        meses_trabalhados   INTEGER NOT NULL DEFAULT 12,
        salario_base        REAL NOT NULL,
        media_variaveis     REAL NOT NULL DEFAULT 0.00,
        remuneracao_total   REAL NOT NULL,
        valor_bruto         REAL NOT NULL,
        desconto_primeira_parcela REAL DEFAULT 0.00,
        desconto_inss       REAL DEFAULT 0.00,
        desconto_irrf       REAL DEFAULT 0.00,
        valor_liquido       REAL NOT NULL,
        fgts_informativo    REAL DEFAULT 0.00,
        data_pagamento      TEXT NOT NULL,
        situacao            TEXT NOT NULL DEFAULT 'calculado',
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_RESCISOES = """
    CREATE TABLE IF NOT EXISTS rescisoes (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        tipo_rescisao       TEXT NOT NULL,
        data_comunicacao    TEXT NOT NULL,
        data_afastamento    TEXT NOT NULL,
        tipo_aviso_previo   TEXT NOT NULL DEFAULT 'indenizado',
        dias_aviso_previo   INTEGER NOT NULL DEFAULT 30,
        saldo_salario_dias  INTEGER NOT NULL DEFAULT 0,
        saldo_salario_valor REAL DEFAULT 0.00,
        aviso_indenizado_valor REAL DEFAULT 0.00,
        ferias_vencidas_valor REAL DEFAULT 0.00,
        terco_ferias_vencidas REAL DEFAULT 0.00,
        ferias_prop_dias    INTEGER DEFAULT 0,
        ferias_prop_valor   REAL DEFAULT 0.00,
        terco_ferias_prop   REAL DEFAULT 0.00,
        decimo_prop_avos    INTEGER DEFAULT 0,
        decimo_prop_valor   REAL DEFAULT 0.00,
        multa_fgts_percentual REAL DEFAULT 40.00,
        multa_fgts_valor    REAL DEFAULT 0.00,
        outros_proventos    REAL DEFAULT 0.00,
        total_proventos     REAL NOT NULL DEFAULT 0.00,
        desconto_inss       REAL DEFAULT 0.00,
        desconto_irrf       REAL DEFAULT 0.00,
        desconto_aviso_previo REAL DEFAULT 0.00,
        outros_descontos    REAL DEFAULT 0.00,
        total_descontos     REAL NOT NULL DEFAULT 0.00,
        valor_liquido       REAL NOT NULL DEFAULT 0.00,
        data_limite_pagamento TEXT NOT NULL,
        data_pagamento_realizada TEXT,
        multa_art_477_aplicada INTEGER DEFAULT 0,
        seguro_desemprego_gerado INTEGER DEFAULT 0,
        trct_gerado         INTEGER DEFAULT 0,
        status              TEXT NOT NULL DEFAULT 'aberta',
        recibo_esocial_s2299 TEXT,
        motivo_legal        TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_SST_EXAMES = """
    CREATE TABLE IF NOT EXISTS sst_exames (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        codigo              TEXT NOT NULL,
        descricao           TEXT NOT NULL,
        tipo                TEXT NOT NULL DEFAULT 'periodico',
        periodicidade_meses INTEGER NOT NULL DEFAULT 12,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_SST_ASOS = """
    CREATE TABLE IF NOT EXISTS sst_asos (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        exame_id            INTEGER,
        tipo_aso            TEXT NOT NULL,
        data_emissao        TEXT NOT NULL,
        data_validade       TEXT NOT NULL,
        resultado           TEXT NOT NULL,
        medico_nome         TEXT NOT NULL,
        medico_crm          TEXT NOT NULL,
        medico_uf           TEXT NOT NULL,
        arquivo_url         TEXT,
        recibo_esocial_s2220 TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_SST_EPIS = """
    CREATE TABLE IF NOT EXISTS sst_epis (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        codigo              TEXT NOT NULL,
        descricao           TEXT NOT NULL,
        ca_numero           TEXT NOT NULL,
        ca_validade         TEXT NOT NULL,
        vida_util_dias      INTEGER NOT NULL DEFAULT 180,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_SST_ENTREGAS_EPI = """
    CREATE TABLE IF NOT EXISTS sst_entregas_epi (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        epi_id              INTEGER NOT NULL,
        data_entrega        TEXT NOT NULL,
        quantidade          INTEGER NOT NULL DEFAULT 1,
        data_prevista_troca TEXT,
        ciencia_colaborador INTEGER NOT NULL DEFAULT 1,
        status              TEXT NOT NULL DEFAULT 'ativo',
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_SST_TREINAMENTOS = """
    CREATE TABLE IF NOT EXISTS sst_treinamentos (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        codigo              TEXT NOT NULL,
        nome                TEXT NOT NULL,
        nr_norma            TEXT NOT NULL,
        carga_horaria       INTEGER NOT NULL,
        validade_meses      INTEGER NOT NULL DEFAULT 24,
        ativo               INTEGER NOT NULL DEFAULT 1,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_SST_TREINAMENTOS_PARTICIPACOES = """
    CREATE TABLE IF NOT EXISTS sst_treinamentos_participacoes (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        treinamento_id      INTEGER NOT NULL,
        data_conclusao      TEXT NOT NULL,
        data_expiracao      TEXT NOT NULL,
        certificado_url     TEXT,
        instrutor_nome      TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_SST_CATS = """
    CREATE TABLE IF NOT EXISTS sst_cats (
        id                  {pk},
        colaborador_id      INTEGER NOT NULL,
        tipo_acidente       TEXT NOT NULL,
        data_hora_acidente  TEXT NOT NULL,
        houve_afastamento   INTEGER NOT NULL DEFAULT 1,
        houve_obito         INTEGER NOT NULL DEFAULT 0,
        local_acidente      TEXT NOT NULL,
        descricao_detalhada TEXT NOT NULL,
        numero_cat          TEXT,
        recibo_esocial_s2210 TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_ESOCIAL_EVENTOS = """
    CREATE TABLE IF NOT EXISTS esocial_eventos (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        tipo_evento         TEXT NOT NULL,
        identificador_origem TEXT,
        ambiente            TEXT NOT NULL DEFAULT 'homologacao',
        status              TEXT NOT NULL DEFAULT 'gerado',
        xml_conteudo        TEXT NOT NULL,
        xml_assinado        TEXT,
        protocolo_envio     TEXT,
        numero_recibo       TEXT,
        codigo_resposta     TEXT,
        mensagem_resposta   TEXT,
        evento_retificador_de TEXT,
        criado_por          TEXT NOT NULL,
        criado_em           TEXT NOT NULL,
        enviado_em          TEXT,
        processado_em       TEXT
    );
"""

_DDL_PENDENCIAS_OPERACIONAIS = """
    CREATE TABLE IF NOT EXISTS pendencias_operacionais (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        modulo              TEXT NOT NULL,
        tipo_pendencia      TEXT NOT NULL,
        titulo              TEXT NOT NULL,
        descricao           TEXT NOT NULL,
        severidade          TEXT NOT NULL DEFAULT 'media',
        colaborador_id      INTEGER,
        prazo_limite        TEXT NOT NULL,
        responsavel         TEXT NOT NULL DEFAULT 'Departamento Pessoal',
        status              TEXT NOT NULL DEFAULT 'pendente',
        resolvida_por       TEXT,
        resolvida_em        TEXT,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_APROVACOES_WORKFLOW = """
    CREATE TABLE IF NOT EXISTS aprovacoes_workflow (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        modulo              TEXT NOT NULL,
        processo_tipo       TEXT NOT NULL,
        processo_id         INTEGER NOT NULL,
        solicitante         TEXT NOT NULL,
        aprovador           TEXT,
        status              TEXT NOT NULL DEFAULT 'pendente',
        justificativa       TEXT,
        criado_em           TEXT NOT NULL,
        atualizado_em       TEXT NOT NULL
    );
"""

_DDL_AUDITORIA_OPERACOES = """
    CREATE TABLE IF NOT EXISTS auditoria_operacoes (
        id                  {pk},
        empresa_id          TEXT,
        modulo              TEXT NOT NULL,
        operacao            TEXT NOT NULL,
        registro_tipo       TEXT NOT NULL,
        registro_id         TEXT NOT NULL,
        campo_alterado      TEXT,
        valor_anterior      TEXT,
        valor_novo          TEXT,
        usuario_responsavel TEXT NOT NULL,
        ip_origem           TEXT,
        detalhes            TEXT,
        criado_em           TEXT NOT NULL
    );
"""

_DDL_ARQUIVOS_BANCARIOS_CNAB = """
    CREATE TABLE IF NOT EXISTS arquivos_bancarios_cnab (
        id                  {pk},
        empresa_id          TEXT NOT NULL,
        competencia         TEXT NOT NULL,
        tipo_folha          TEXT NOT NULL DEFAULT 'mensal',
        banco_codigo        TEXT NOT NULL DEFAULT '001',
        layout_cnab         TEXT NOT NULL DEFAULT 'CNAB240',
        total_registros     INTEGER NOT NULL,
        valor_total_liquido REAL NOT NULL,
        conteudo_arquivo    TEXT NOT NULL,
        gerado_por          TEXT NOT NULL,
        gerado_em           TEXT NOT NULL
    );
"""

# ─────────────────────────────────────────────────────────────────────────────
# Inicializacao
# ─────────────────────────────────────────────────────────────────────────────

def init_db(db_path: str = None, auto_provision: bool = True):
    """
    Cria as tabelas e indices necessarios se nao existirem.
    Funciona tanto com PostgreSQL quanto com SQLite.
    """
    pg = _usar_postgres(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    serial = "SERIAL" if pg else "INTEGER"
    pk = "SERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    cursor.execute(_DDL_COLABORADORES_PG if pg else _DDL_COLABORADORES_SQLITE)
    cursor.execute(_DDL_DEPENDENTES.format(serial=serial))
    cursor.execute(_DDL_HISTORICO.format(serial=serial))
    cursor.execute(_DDL_USUARIOS_PG if pg else _DDL_USUARIOS_SQLITE)
    cursor.execute(_DDL_SESSOES)
    cursor.execute(_DDL_FOLHA_PARAMETROS_PG if pg else _DDL_FOLHA_PARAMETROS_SQLITE)
    cursor.execute(_DDL_FOLHAS_PAGAMENTO_PG if pg else _DDL_FOLHAS_PAGAMENTO_SQLITE)
    cursor.execute(_DDL_FOLHA_ITENS.format(serial=serial))
    cursor.execute(_DDL_FOLHA_HISTORICO.format(serial=serial))
    cursor.execute(_DDL_AUDITORIA_AUTENTICACAO_PG if pg else _DDL_AUDITORIA_AUTENTICACAO_SQLITE)

    # Execução das tabelas dos Módulos 01 a 20 da Plataforma
    tabelas_plataforma = [
        _DDL_EMPRESAS,
        _DDL_FILIAIS,
        _DDL_CENTROS_CUSTO,
        _DDL_ADMISSOES.format(pk=pk),
        _DDL_CHECKLIST_ADMISSONAL.format(pk=pk),
        _DDL_ESCALAS_JORNADA.format(pk=pk),
        _DDL_MARCACOES_PONTO.format(pk=pk),
        _DDL_OCORRENCIAS_PONTO.format(pk=pk),
        _DDL_AJUSTES_PONTO.format(pk=pk),
        _DDL_FECHAMENTOS_PONTO.format(pk=pk),
        _DDL_PERIODOS_AQUISITIVOS.format(pk=pk),
        _DDL_FERIAS_PROGRAMADAS.format(pk=pk),
        _DDL_AFASTAMENTOS.format(pk=pk),
        _DDL_BENEFICIOS_CATALOGO.format(pk=pk),
        _DDL_BENEFICIOS_COLABORADOR.format(pk=pk),
        _DDL_DECIMO_TERCEIRO.format(pk=pk),
        _DDL_RESCISOES.format(pk=pk),
        _DDL_SST_EXAMES.format(pk=pk),
        _DDL_SST_ASOS.format(pk=pk),
        _DDL_SST_EPIS.format(pk=pk),
        _DDL_SST_ENTREGAS_EPI.format(pk=pk),
        _DDL_SST_TREINAMENTOS.format(pk=pk),
        _DDL_SST_TREINAMENTOS_PARTICIPACOES.format(pk=pk),
        _DDL_SST_CATS.format(pk=pk),
        _DDL_ESOCIAL_EVENTOS.format(pk=pk),
        _DDL_PENDENCIAS_OPERACIONAIS.format(pk=pk),
        _DDL_APROVACOES_WORKFLOW.format(pk=pk),
        _DDL_AUDITORIA_OPERACOES.format(pk=pk),
        _DDL_ARQUIVOS_BANCARIOS_CNAB.format(pk=pk),
        _DDL_FOLHA_RUBRICAS.format(pk=pk),
        _DDL_COLABORADOR_DOCUMENTOS.format(pk=pk),
    ]
    for ddl_sql in tabelas_plataforma:
        try:
            cursor.execute(ddl_sql)
        except Exception:
            pass

    indices = [
        "CREATE INDEX IF NOT EXISTS idx_colab_matricula ON colaboradores(matricula);",
        "CREATE INDEX IF NOT EXISTS idx_colab_cpf       ON colaboradores(cpf);",
        "CREATE INDEX IF NOT EXISTS idx_colab_nome      ON colaboradores(nome_completo);",
        "CREATE INDEX IF NOT EXISTS idx_colab_situacao  ON colaboradores(situacao);",
        "CREATE INDEX IF NOT EXISTS idx_colab_setor     ON colaboradores(setor);",
        "CREATE INDEX IF NOT EXISTS idx_hist_colab      ON historico_alteracoes(colaborador_id);",
        "CREATE INDEX IF NOT EXISTS idx_dep_colab       ON dependentes(colaborador_id);",
        "CREATE INDEX IF NOT EXISTS idx_usuario_email   ON usuarios(email);",
        "CREATE INDEX IF NOT EXISTS idx_usuario_login   ON usuarios(usuario);",
        "CREATE INDEX IF NOT EXISTS idx_sessao_token    ON sessoes(token);",
        "CREATE INDEX IF NOT EXISTS idx_sessao_user     ON sessoes(usuario_id);",
        "CREATE INDEX IF NOT EXISTS idx_folha_colab     ON folhas_pagamento(colaborador_id);",
        "CREATE INDEX IF NOT EXISTS idx_folha_comp      ON folhas_pagamento(competencia);",
        "CREATE INDEX IF NOT EXISTS idx_folha_situacao  ON folhas_pagamento(situacao);",
        "CREATE INDEX IF NOT EXISTS idx_folha_itens_folha ON folha_itens(folha_id);",
        "CREATE INDEX IF NOT EXISTS idx_folha_hist_folha  ON folha_historico(folha_id);",
        "CREATE INDEX IF NOT EXISTS idx_audit_auth_evento ON auditoria_autenticacao(evento);",
        "CREATE INDEX IF NOT EXISTS idx_audit_auth_data   ON auditoria_autenticacao(criado_em);",
        "CREATE INDEX IF NOT EXISTS idx_audit_auth_ip     ON auditoria_autenticacao(ip_origem);",
        "CREATE INDEX IF NOT EXISTS idx_adm_status        ON admissoes(status);",
        "CREATE INDEX IF NOT EXISTS idx_ponto_colab_data  ON marcacoes_ponto(colaborador_id, data);",
        "CREATE INDEX IF NOT EXISTS idx_ocorrencia_colab  ON ocorrencias_ponto(colaborador_id, data_inicio);",
        "CREATE INDEX IF NOT EXISTS idx_ferias_colab      ON ferias_programadas(colaborador_id);",
        "CREATE INDEX IF NOT EXISTS idx_afast_colab       ON afastamentos(colaborador_id);",
        "CREATE INDEX IF NOT EXISTS idx_rescisao_colab    ON rescisoes(colaborador_id);",
        "CREATE INDEX IF NOT EXISTS idx_pendencias_status ON pendencias_operacionais(status, prazo_limite);",
        "CREATE INDEX IF NOT EXISTS idx_audit_modulo_data ON auditoria_operacoes(modulo, criado_em);",
    ]
    for idx_sql in indices:
        try:
            cursor.execute(idx_sql)
        except Exception:
            pass

    # Colunas complementares idempotentes de schema para PostgreSQL (SPEC-03 e SPEC-03.1)
    if pg:
        colunas_extras = [
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS empresa_id TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS filial_id TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS departamento_id TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS cargo_id TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS sexo TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS estado_civil TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS celular TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS complemento TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS observacoes TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS criado_por TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS atualizado_por TEXT;",
            "ALTER TABLE colaboradores ALTER COLUMN data_admissao DROP NOT NULL;",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS filial_id TEXT;",
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS empresas_autorizadas TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS pis_pasep TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS departamento TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS centro_custo TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS tipo_contrato TEXT DEFAULT 'CLT';",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS jornada_trabalho TEXT DEFAULT '44h semanais';",
            "ALTER TABLE colaboradores ADD COLUMN IF NOT EXISTS carga_horaria_mensal NUMERIC(6,2) DEFAULT 220.00;",
            "ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS data_nascimento TEXT;",
            "ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS eh_dependente_irrf INTEGER NOT NULL DEFAULT 1;",
            "ALTER TABLE dependentes ADD COLUMN IF NOT EXISTS eh_elegivel_salario_familia INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS empresa_id TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS filial_id TEXT;",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS tipo_folha TEXT NOT NULL DEFAULT 'mensal';",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS versao INTEGER NOT NULL DEFAULT 1;",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS aprovado_por TEXT;",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS aprovado_em TEXT;",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS inss_descontado NUMERIC(15,2) NOT NULL DEFAULT 0.00;",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS irrf_descontado NUMERIC(15,2) NOT NULL DEFAULT 0.00;",
            "ALTER TABLE folhas_pagamento ADD COLUMN IF NOT EXISTS encargos_patronais NUMERIC(15,2) NOT NULL DEFAULT 0.00;",
            "ALTER TABLE folha_itens ADD COLUMN IF NOT EXISTS incide_inss INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE folha_itens ADD COLUMN IF NOT EXISTS incide_irrf INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE folha_itens ADD COLUMN IF NOT EXISTS incide_fgts INTEGER NOT NULL DEFAULT 0;",
        ]
        for col_sql in colunas_extras:
            try:
                cursor.execute(col_sql)
            except Exception:
                pass
    else:
        colunas_extras_sqlite = [
            "ALTER TABLE colaboradores ADD COLUMN empresa_id TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';",
            "ALTER TABLE colaboradores ADD COLUMN filial_id TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN departamento_id TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN cargo_id TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN sexo TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN estado_civil TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN celular TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN complemento TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN observacoes TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN criado_por TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';",
            "ALTER TABLE colaboradores ADD COLUMN atualizado_por TEXT;",
            "ALTER TABLE usuarios ADD COLUMN empresa_id TEXT DEFAULT 'a0000000-0000-0000-0000-000000000001';",
            "ALTER TABLE usuarios ADD COLUMN filial_id TEXT;",
            "ALTER TABLE usuarios ADD COLUMN empresas_autorizadas TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN pis_pasep TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN departamento TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN centro_custo TEXT;",
            "ALTER TABLE colaboradores ADD COLUMN tipo_contrato TEXT DEFAULT 'CLT';",
            "ALTER TABLE colaboradores ADD COLUMN jornada_trabalho TEXT DEFAULT '44h semanais';",
            "ALTER TABLE colaboradores ADD COLUMN carga_horaria_mensal REAL DEFAULT 220.0;",
            "ALTER TABLE dependentes ADD COLUMN data_nascimento TEXT;",
            "ALTER TABLE dependentes ADD COLUMN eh_dependente_irrf INTEGER NOT NULL DEFAULT 1;",
            "ALTER TABLE dependentes ADD COLUMN eh_elegivel_salario_familia INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE folhas_pagamento ADD COLUMN empresa_id TEXT NOT NULL DEFAULT 'a0000000-0000-0000-0000-000000000001';",
            "ALTER TABLE folhas_pagamento ADD COLUMN filial_id TEXT;",
            "ALTER TABLE folhas_pagamento ADD COLUMN tipo_folha TEXT NOT NULL DEFAULT 'mensal';",
            "ALTER TABLE folhas_pagamento ADD COLUMN versao INTEGER NOT NULL DEFAULT 1;",
            "ALTER TABLE folhas_pagamento ADD COLUMN aprovado_por TEXT;",
            "ALTER TABLE folhas_pagamento ADD COLUMN aprovado_em TEXT;",
            "ALTER TABLE folhas_pagamento ADD COLUMN inss_descontado REAL NOT NULL DEFAULT 0.0;",
            "ALTER TABLE folhas_pagamento ADD COLUMN irrf_descontado REAL NOT NULL DEFAULT 0.0;",
            "ALTER TABLE folhas_pagamento ADD COLUMN encargos_patronais REAL NOT NULL DEFAULT 0.0;",
            "ALTER TABLE folha_itens ADD COLUMN incide_inss INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE folha_itens ADD COLUMN incide_irrf INTEGER NOT NULL DEFAULT 0;",
            "ALTER TABLE folha_itens ADD COLUMN incide_fgts INTEGER NOT NULL DEFAULT 0;",
        ]
        for col_sql in colunas_extras_sqlite:
            try:
                cursor.execute(col_sql)
            except Exception:
                pass

    # Provisiona catálogo inicial de rubricas caso esteja vazio
    try:
        p_mark = "%s" if pg else "?"
        cursor.execute("SELECT COUNT(*) FROM folha_rubricas;")
        if cursor.fetchone()[0] == 0:
            try:
                from .catalogo_eventos import CATALOGO_EVENTOS_FOLHA
            except ImportError:
                from backend.catalogo_eventos import CATALOGO_EVENTOS_FOLHA
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            codigos_legais = {
                "0001", "0002", "0003", "0100", "0101", "0102", "0103", "0104", "0105",
                "0110", "0111", "0112", "0200", "0201", "0202", "0300", "0301", "0302",
                "0501", "0502", "0505", "0506", "0507", "0510",
                "0901", "0902", "0903", "0904", "0905", "0906", "0907", "0908", "0909",
            }
            for ev in CATALOGO_EVENTOS_FOLHA:
                cod = str(ev["codigo"]).strip()
                tipo = ev.get("tipo", "provento")
                natureza = "informativa" if tipo == "informativo" else ("indenizatoria" if ev.get("inss", 0) == 0 and tipo == "provento" and cod not in ("0110", "0300") else "salarial")
                forma = "calculado" if cod in ("0001", "0002", "0501", "0502", "0505", "0506", "0507", "0901", "0902", "0903", "0904", "0905", "0906", "0907", "0908", "0909") else "valor_fixo"
                sistema_legal = 1 if cod in codigos_legais else 0
                reflexo_ferias = 1 if tipo == "provento" and ev.get("inss", 0) == 1 and cod not in ("0100", "0101", "0111", "0112") else 0
                reflexo_13 = reflexo_ferias
                cursor.execute(f"""
                    INSERT INTO folha_rubricas (
                        empresa_id, codigo, descricao, tipo, categoria, natureza, forma_calculo,
                        valor_padrao, referencia_padrao, incide_inss, incide_irrf, incide_fgts,
                        incide_outras_bases, reflexo_ferias, reflexo_13, vigencia_inicio, vigencia_fim,
                        ativo, sistema_legal, observacao, criado_em, atualizado_em
                    ) VALUES (
                        {p_mark},{p_mark},{p_mark},{p_mark},{p_mark},{p_mark},{p_mark},
                        0.0,0.0,{p_mark},{p_mark},{p_mark},
                        {p_mark},{p_mark},{p_mark},'2026-01-01',NULL,
                        1,{p_mark},{p_mark},{p_mark},{p_mark}
                    );
                """, (
                    "a0000000-0000-0000-0000-000000000001",
                    cod, ev["evento"], tipo, ev.get("categoria", "Proventos"),
                    natureza, forma,
                    int(ev.get("inss", 0)), int(ev.get("irrf", 0)), int(ev.get("fgts", 0)),
                    int(ev.get("fgts", 0)), reflexo_ferias, reflexo_13,
                    sistema_legal, ev.get("observacao", ""), agora, agora
                ))
    except Exception:
        pass

    # Provisiona parâmetro padrão de cálculo caso não exista
    try:
        p_mark = "%s" if pg else "?"
        cursor.execute(f"SELECT COUNT(*) FROM folha_parametros WHERE codigo = {p_mark};", ("PADRAO_CLT_2026",))
        qtd = cursor.fetchone()[0]
        if qtd == 0:
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(f"""
                INSERT INTO folha_parametros (
                    codigo, descricao, vigencia_inicio, vigencia_fim,
                    horas_mensais_padrao, dias_mes_padrao, percentual_he_padrao,
                    percentual_he_extra, percentual_adicional_noturno, aplicar_reducao_noturna,
                    fator_reducao_noturna, aplicar_inss, aplicar_irrf, aliquota_fgts,
                    teto_inss, deducao_dependente_irrf, ativo, validado_por_profissional,
                    criado_em, atualizado_em
                ) VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark});
            """, (
                "PADRAO_CLT_2026", "Parâmetros Gerais CLT 220h / Vigência 2026 (Padrão)",
                "2026-01-01", None,
                220.0, 30, 50.0, 100.0, 20.0, 0, 1.142857,
                1, 1, 8.0, 8475.55, 189.59, 1, 1,
                agora, agora
            ))
    except Exception:
        pass

    # Provisiona empresa e filiais padrão caso não existam
    try:
        p_mark = "%s" if pg else "?"
        cursor.execute(f"SELECT COUNT(*) FROM empresas WHERE id = {p_mark};", ("a0000000-0000-0000-0000-000000000001",))
        if cursor.fetchone()[0] == 0:
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(f"""
                INSERT INTO empresas (id, cnpj, razao_social, nome_fantasia, regime_tributario, responsavel_nome, responsavel_cpf, ativo, criado_em, atualizado_em)
                VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark}, {p_mark});
            """, (
                "a0000000-0000-0000-0000-000000000001", "12.345.678/0001-90",
                "ForçaVerde Usina de Energia e Biocombustíveis S.A.", "ForçaVerde Usina",
                "lucro_real", "Carlos Eduardo Mendes", "123.456.789-00", agora, agora
            ))
            cursor.execute(f"""
                INSERT INTO filiais (id, empresa_id, codigo_filial, nome, cnpj, cidade, uf, feriados_locais, ativo, criado_em)
                VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark});
            """, (
                "b0000000-0000-0000-0000-000000000001", "a0000000-0000-0000-0000-000000000001",
                "0001", "Matriz — Usina Central", "12.345.678/0001-90",
                "Ribeirão Preto", "SP", "[]", agora
            ))
            cursor.execute(f"""
                INSERT INTO filiais (id, empresa_id, codigo_filial, nome, cnpj, cidade, uf, feriados_locais, ativo, criado_em)
                VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark});
            """, (
                "b0000000-0000-0000-0000-000000000002", "a0000000-0000-0000-0000-000000000001",
                "0002", "Filial 02 — Destilaria Norte", "12.345.678/0002-71",
                "Sertãozinho", "SP", "[]", agora
            ))

            # Centros de Custo
            ccs = [
                ("CC-001", "Operações Agrícolas & Colheita"),
                ("CC-002", "Manutenção Industrial & Moenda"),
                ("CC-003", "Departamento Pessoal & RH"),
                ("CC-004", "Saúde e Segurança do Trabalho (SST)"),
                ("CC-005", "Administrativo & Financeiro"),
            ]
            for cod, desc in ccs:
                cursor.execute(f"""
                    INSERT INTO centros_custo (id, empresa_id, codigo, descricao, ativo, criado_em)
                    VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark});
                """, (f"cc-{cod.lower()}", "a0000000-0000-0000-0000-000000000001", cod, desc, agora))

            # Escalas de Jornada
            escalas = [
                ("ESC-5X2", "Escala 5x2 Comercial (44h)", 44.0, 220.0, "5x2", "08:00", "17:48", 60),
                ("ESC-6X1", "Escala 6x1 Operacional (44h)", 44.0, 220.0, "6x1", "07:00", "15:20", 60),
                ("ESC-12X36", "Escala 12x36 Turno Revezamento", 36.0, 180.0, "12x36", "06:00", "18:00", 60),
            ]
            for cod, desc, ch, div, reg, ent, sai, inter in escalas:
                cursor.execute(f"""
                    INSERT INTO escalas_jornada (empresa_id, codigo, descricao, carga_semanal_horas, divisor_mensal, tipo_regime, entrada_padrao, saida_padrao, intervalo_minutos, ativo, criado_em)
                    VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark});
                """, ("a0000000-0000-0000-0000-000000000001", cod, desc, ch, div, reg, ent, sai, inter, agora))

            # Catálogo de Benefícios
            benefs = [
                ("VT01", "Vale-Transporte Urbano / Intermunicipal", "vale_transporte", "percentual", 6.0, 6.0),
                ("VA01", "Vale-Alimentação Cesta Mensal", "vale_alimentacao", "fixo", 0.0, 0.0),
                ("VR01", "Vale-Refeição Restaurante Usina", "vale_refeicao", "fixo", 5.0, 20.0),
                ("PS01", "Plano de Saúde Unimed Integral", "plano_saude", "percentual", 15.0, 30.0),
                ("SV01", "Seguro de Vida em Grupo MetLife", "seguro_vida", "fixo", 0.0, 0.0),
                ("FAR01", "Convênio Farmácia DrogaVitta", "farmacia", "fixo", 0.0, 0.0),
            ]
            for cod, nome, tipo, c_tipo, c_val, teto in benefs:
                cursor.execute(f"""
                    INSERT INTO beneficios_catalogo (empresa_id, codigo, nome, tipo, coparticipacao_tipo, coparticipacao_valor, teto_legal_percentual, ativo, criado_em)
                    VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark});
                """, ("a0000000-0000-0000-0000-000000000001", cod, nome, tipo, c_tipo, c_val, teto, agora))

            # Catálogo de Exames SST
            exames = [
                ("EX-ADM", "Exame Médico Clínico Admissional", "admissional", 12),
                ("EX-PER", "Exame Médico Periódico NR-7", "periodico", 12),
                ("EX-DEM", "Exame Médico Demissional", "demissional", 12),
                ("EX-RET", "Exame de Retorno ao Trabalho (>= 30d)", "retorno_trabalho", 12),
                ("EX-RISCO", "Exame de Mudança de Riscos Ocupacionais", "mudanca_risco", 12),
            ]
            for cod, desc, tipo, period in exames:
                cursor.execute(f"""
                    INSERT INTO sst_exames (empresa_id, codigo, descricao, tipo, periodicidade_meses, ativo, criado_em)
                    VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark});
                """, ("a0000000-0000-0000-0000-000000000001", cod, desc, tipo, period, agora))

            # Catálogo de EPIs
            epis = [
                ("EPI-CAP", "Capacete de Segurança Classe B com Jugular", "31469", "2028-12-31", 365),
                ("EPI-BOT", "Botina de Couro com Bico de Composite e Palmilha de Aço", "43290", "2027-10-15", 180),
                ("EPI-LUV", "Luva de Vaqueta Mista para Manutenção Pesada", "27814", "2027-06-30", 90),
                ("EPI-OCU", "Óculos de Proteção Antirrisco e Antiembaçante", "18828", "2028-05-20", 180),
                ("EPI-AUR", "Protetor Auditivo Tipo Concha 24dB NRRsf", "14235", "2028-08-10", 365),
            ]
            for cod, desc, ca, val, vida in epis:
                cursor.execute(f"""
                    INSERT INTO sst_epis (empresa_id, codigo, descricao, ca_numero, ca_validade, vida_util_dias, ativo, criado_em)
                    VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark});
                """, ("a0000000-0000-0000-0000-000000000001", cod, desc, ca, val, vida, agora))

            # Catálogo de Treinamentos
            treinamentos = [
                ("TR-NR06", "Treinamento de Uso e Conservação de EPIs", "NR-06", 4, 24),
                ("TR-NR10", "Segurança em Instalações e Serviços em Eletricidade", "NR-10", 40, 24),
                ("TR-NR12", "Segurança no Trabalho em Máquinas e Equipamentos", "NR-12", 16, 24),
                ("TR-NR33", "Trabalho e Resgate em Espaços Confinados", "NR-33", 16, 12),
                ("TR-NR35", "Trabalho em Altura e Prevenção de Quedas", "NR-35", 8, 24),
            ]
            for cod, nome, nr, ch, val in treinamentos:
                cursor.execute(f"""
                    INSERT INTO sst_treinamentos (empresa_id, codigo, nome, nr_norma, carga_horaria, validade_meses, ativo, criado_em)
                    VALUES ({p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, {p_mark}, 1, {p_mark});
                """, ("a0000000-0000-0000-0000-000000000001", cod, nome, nr, ch, val, agora))
    except Exception:
        pass

    conn.commit()
    conn.close()

    if auto_provision:
        try:
            from .auth import AuthService
        except ImportError:
            import sys
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
            from backend.auth import AuthService
        auth_service = AuthService(db_path=db_path, auto_init=False)
        auth_service.provisionar_usuario_inicial()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de cursor — abstraem as diferencas entre psycopg2 e sqlite3
# ─────────────────────────────────────────────────────────────────────────────

def row_to_dict(cursor, row, db_path: str = None) -> dict:
    """Converte uma linha em dicionario independente do driver."""
    if _usar_postgres(db_path):
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))
    return dict(row)  # SQLite row_factory=sqlite3.Row


def fetchone_dict(cursor, db_path: str = None):
    row = cursor.fetchone()
    if row is None:
        return None
    return row_to_dict(cursor, row, db_path)


def fetchall_dict(cursor, db_path: str = None) -> list:
    return [row_to_dict(cursor, r, db_path) for r in cursor.fetchall()]


def insert_returning_id(
    cursor, conn, sql_pg: str, sql_sqlite: str,
    params: tuple, db_path: str = None
) -> int:
    """
    Executa um INSERT e retorna o id gerado.
    PostgreSQL: usa RETURNING id. SQLite: usa lastrowid.
    """
    if _usar_postgres(db_path):
        cursor.execute(sql_pg, params)
        return cursor.fetchone()[0]
    cursor.execute(sql_sqlite, params)
    return cursor.lastrowid


def status_banco(db_path: str = None) -> dict:
    """
    Verifica de fato o banco ativo (SELECT 1). Nao expoe URL nem credenciais.
    Usado pelo endpoint /api/health para confirmar que o PostgreSQL esta em uso.
    """
    pg = _usar_postgres(db_path)
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
    finally:
        conn.close()

    info = {
        "banco": "postgresql" if pg else "sqlite",
        "conectado": True,
        "producao": em_producao(),
    }
    if pg:
        url = get_database_url().lower()
        if "neon.tech" in url:
            info["provedor"] = "neon"
        elif "supabase" in url:
            info["provedor"] = "supabase"
        else:
            info["provedor"] = "postgresql"
        info["pooled"] = "-pooler" in url or "pooler" in url or "6543" in url
    return info


def ph(db_path: str = None) -> str:
    """Retorna o placeholder correto para o banco ativo: %s (PG) ou ? (SQLite)."""
    return "%s" if _usar_postgres(db_path) else "?"


if __name__ == "__main__":
    init_db()
    modo = "PostgreSQL" if _usar_postgres() else "SQLite"
    print(f"Banco de dados ({modo}) inicializado com sucesso!")
