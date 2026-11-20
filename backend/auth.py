"""
Modulo de Autenticacao e Seguranca — Backend RH/DP
Implementa hashing seguro com salt (PBKDF2-HMAC-SHA256),
gerenciamento de sessoes criptograficas duraveis e controle de acesso por perfil.
Atende a RF-40, RF-41, RF-43 e RNF-01, RNF-02, RNF-03.
Funciona com PostgreSQL (producao) e SQLite (desenvolvimento local e testes).
"""
import hashlib
import hmac
import os
import secrets
import sys
from datetime import datetime, timedelta

from .database import _usar_postgres, get_connection, init_db, insert_returning_id, ph, row_to_dict
from .audit import AuditService

ITERATIONS = 100_000
SESSION_IDLE_TIMEOUT_HOURS = 12
SESSION_ABSOLUTE_TIMEOUT_HOURS = 8
MENSAGEM_GENERICA_ERRO = "E-mail ou senha inválidos."


class CredenciaisInvalidasException(Exception):
    pass


class SessaoInvalidaException(Exception):
    pass


def hash_senha(senha: str, salt: str = None) -> tuple:
    """
    Gera o hash PBKDF2-HMAC-SHA256 de uma senha com salt criptografico.
    Retorna (hash_hex, salt_hex).
    """
    if not salt:
        salt = secrets.token_hex(16)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        salt.encode("utf-8"),
        ITERATIONS,
    )
    return hash_bytes.hex(), salt


def verificar_senha(senha: str, senha_hash: str, salt: str) -> bool:
    """Verifica se a senha corresponde ao hash usando comparacao constante."""
    hash_calculado, _ = hash_senha(senha, salt)
    return hmac.compare_digest(hash_calculado, senha_hash)


class AuthService:
    def __init__(self, db_path: str = None, auto_init: bool = True):
        self.db_path = db_path
        self.audit_service = AuditService(db_path=self.db_path)
        if auto_init:
            init_db(db_path=self.db_path, auto_provision=False)
            self.provisionar_usuario_inicial()

    # ──────────────────────────────────────────────────────────
    # Shortcuts que carregam db_path automaticamente
    # ──────────────────────────────────────────────────────────

    def _ph(self) -> str:
        return ph(self.db_path)

    def _pg(self) -> bool:
        return _usar_postgres(self.db_path)

    def _conn(self):
        return get_connection(self.db_path)

    def _row(self, cursor, row) -> dict:
        return row_to_dict(cursor, row, self.db_path)

    # ──────────────────────────────────────────────────────────
    # Provisionamento Seguro (GOV-002-02)
    # ──────────────────────────────────────────────────────────

    def provisionar_usuario_inicial(self) -> dict:
        """
        Provisiona as contas padrão de administrador e visitante/convidado
        caso ainda não existam no banco de dados.
        Exige ADMIN_INITIAL_PASSWORD explícita para prevenir senhas padrão em produção.
        """
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        # 1. Provisionar Administrador se não existir
        cursor.execute(f"SELECT id, email, usuario, nome_completo, perfil, status FROM usuarios WHERE email = {P} OR usuario = {P}", ("admin.dp@empresa.com.br", "admin.dp"))
        admin_existente = cursor.fetchone()

        # Determinar se a execução ocorre em contexto de testes automatizados
        em_ambiente_teste = os.environ.get("TESTING") == "1" or (
            "unittest" in sys.modules and os.environ.get("TESTING") != "0"
        )

        if not admin_existente:
            senha_inicial = os.environ.get("ADMIN_INITIAL_PASSWORD")
            if not senha_inicial:
                # Permitir credencial sintética apenas em ambiente explícito de testes automatizados
                if em_ambiente_teste:
                    senha_inicial = os.environ.get("TEST_ADMIN_PASSWORD", "Sintetico#AdminTest2026!")
                else:
                    conn.close()
                    raise RuntimeError(
                        "Falha de segurança operacional: A variável de ambiente ADMIN_INITIAL_PASSWORD "
                        "não foi configurada. É obrigatório definir uma senha inicial forte no arquivo .env "
                        "ou nas variáveis de ambiente antes da inicialização do Portal DP & RH em ambientes reais ou compartilhados."
                    )

            salt = secrets.token_hex(16)
            senha_hash, _ = hash_senha(senha_inicial, salt)
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            params = (
                "admin.dp@empresa.com.br",
                "admin.dp",
                "Administrador (RH/DP)",
                senha_hash,
                salt,
                "administrador",
                agora,
            )

            sql_pg = """
                INSERT INTO usuarios (
                    email, usuario, nome_completo,
                    senha_hash, salt, perfil, status, criado_em
                ) VALUES (%s,%s,%s,%s,%s,%s,'ativo',%s)
                RETURNING id, email, usuario, nome_completo, perfil, status
            """
            sql_sqlite = """
                INSERT INTO usuarios (
                    email, usuario, nome_completo,
                    senha_hash, salt, perfil, status, criado_em
                ) VALUES (?,?,?,?,?,?,'ativo',?)
            """

            insert_returning_id(cursor, conn, sql_pg, sql_sqlite, params, self.db_path)
            conn.commit()

        # 2. Provisionar Convidado / Visitante se não existir e se configurado
        cursor.execute(f"SELECT id, email, usuario, nome_completo, perfil, status FROM usuarios WHERE email = {P} OR usuario = {P}", ("visitante@empresa.com.br", "visitante"))
        convidado_existente = cursor.fetchone()

        if not convidado_existente:
            senha_convidado = os.environ.get("GUEST_INITIAL_PASSWORD")
            if not senha_convidado and em_ambiente_teste:
                senha_convidado = os.environ.get("TEST_GUEST_PASSWORD", "Sintetico#GuestTest2026!")

            if senha_convidado:
                salt = secrets.token_hex(16)
                senha_hash, _ = hash_senha(senha_convidado, salt)
                agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                params = (
                    "visitante@empresa.com.br",
                    "visitante",
                    "Convidado (Analista RH)",
                    senha_hash,
                    salt,
                    "analista_rh",
                    agora,
                )

                sql_pg = """
                    INSERT INTO usuarios (
                        email, usuario, nome_completo,
                        senha_hash, salt, perfil, status, criado_em
                    ) VALUES (%s,%s,%s,%s,%s,%s,'ativo',%s)
                    RETURNING id, email, usuario, nome_completo, perfil, status
                """
                sql_sqlite = """
                    INSERT INTO usuarios (
                        email, usuario, nome_completo,
                        senha_hash, salt, perfil, status, criado_em
                    ) VALUES (?,?,?,?,?,?,'ativo',?)
                """

                insert_returning_id(cursor, conn, sql_pg, sql_sqlite, params, self.db_path)
                conn.commit()

        cursor.execute(f"SELECT id, email, usuario, nome_completo, perfil, status FROM usuarios WHERE email = {P} OR usuario = {P}", ("admin.dp@empresa.com.br", "admin.dp"))
        row_admin = cursor.fetchone()
        user = self._row(cursor, row_admin) if row_admin else {}
        conn.close()
        return user

    # ──────────────────────────────────────────────────────────
    # Autenticacao
    # ──────────────────────────────────────────────────────────

    def autenticar(self, identificador: str, senha: str, ip_origem: str = None) -> tuple:
        """
        Valida as credenciais contra o banco de dados.
        Retorna (dados_usuario_sem_senha, token) se valido.
        Usa mensagem generica 'E-mail ou senha inválidos.' para evitar enumeracao de usuarios (RF-LOGIN-002, AC-06).
        Garante regeneracao de sessao anterior e auditoria do evento (RF-LOGIN-003, RF-LOGIN-006).
        """
        if not identificador or not senha:
            raise CredenciaisInvalidasException("E-mail e senha são obrigatórios.")

        identificador = identificador.strip().lower()
        P = self._ph()

        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT id, email, usuario, nome_completo,
                   senha_hash, salt, perfil, status
            FROM usuarios
            WHERE LOWER(email) = {P} OR LOWER(usuario) = {P}
        """, (identificador, identificador))

        row = cursor.fetchone()
        if not row:
            conn.close()
            self.audit_service.registrar_evento(
                "LOGIN_FALHA", identificador=identificador, ip_origem=ip_origem, detalhes="Usuário não encontrado"
            )
            raise CredenciaisInvalidasException(MENSAGEM_GENERICA_ERRO)

        usuario = self._row(cursor, row)

        # Conta inativa também retorna mensagem genérica para não revelar existência nem status
        if usuario["status"] != "ativo":
            conn.close()
            self.audit_service.registrar_evento(
                "LOGIN_FALHA", identificador=identificador, ip_origem=ip_origem, detalhes="Tentativa em conta inativa"
            )
            raise CredenciaisInvalidasException(MENSAGEM_GENERICA_ERRO)

        if not verificar_senha(senha, usuario["senha_hash"], usuario["salt"]):
            conn.close()
            self.audit_service.registrar_evento(
                "LOGIN_FALHA", identificador=identificador, ip_origem=ip_origem, detalhes="Senha incorreta"
            )
            raise CredenciaisInvalidasException(MENSAGEM_GENERICA_ERRO)

        # ── Regeneração de Sessão (RF-LOGIN-003) ──
        # Invalida quaisquer sessões anteriores abertas para o usuário
        cursor.execute(f"UPDATE sessoes SET revogado=1 WHERE usuario_id={P} AND revogado=0", (usuario["id"],))

        token = secrets.token_hex(32)
        agora_dt = datetime.now()
        expira_dt = agora_dt + timedelta(hours=SESSION_IDLE_TIMEOUT_HOURS)
        agora_str = agora_dt.strftime("%Y-%m-%d %H:%M:%S")
        expira_str = expira_dt.strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(f"""
            INSERT INTO sessoes (token, usuario_id, criado_em, expira_em, revogado)
            VALUES ({P},{P},{P},{P},0)
        """, (token, usuario["id"], agora_str, expira_str))

        cursor.execute(f"""
            UPDATE usuarios SET ultimo_login={P} WHERE id={P}
        """, (agora_str, usuario["id"]))

        conn.commit()
        conn.close()

        # Auditoria de sucesso
        self.audit_service.registrar_evento(
            "LOGIN_SUCESSO", identificador=usuario["email"], ip_origem=ip_origem, detalhes="Autenticação válida"
        )

        return {
            "id":            usuario["id"],
            "email":         usuario["email"],
            "usuario":       usuario["usuario"],
            "nome_completo": usuario["nome_completo"],
            "perfil":        usuario["perfil"],
            "empresa_id":    usuario.get("empresa_id") or "a0000000-0000-0000-0000-000000000001",
        }, token

    # ──────────────────────────────────────────────────────────
    # Sessoes
    # ──────────────────────────────────────────────────────────

    def validar_sessao(self, token: str):
        """
        Valida se o token existe, nao expirou e nao foi revogado.
        Retorna os dados do usuario autenticado ou None.
        """
        if not token:
            return None

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(f"""
            SELECT u.id, u.email, u.usuario, u.nome_completo, u.perfil, s.criado_em
            FROM sessoes s
            JOIN usuarios u ON u.id = s.usuario_id
            WHERE s.token = {P}
              AND s.revogado = 0
              AND s.expira_em > {P}
              AND u.status = 'ativo'
        """, (token, agora_str))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        usuario = self._row(cursor, row)
        criado_em = usuario.pop("criado_em", None)
        if isinstance(criado_em, datetime):
            criado_dt = criado_em
        else:
            criado_dt = datetime.strptime(str(criado_em), "%Y-%m-%d %H:%M:%S")
        agora_dt = datetime.now()
        limite_absoluto = criado_dt + timedelta(hours=SESSION_ABSOLUTE_TIMEOUT_HOURS)
        proxima_expiracao = min(
            agora_dt + timedelta(hours=SESSION_IDLE_TIMEOUT_HOURS),
            limite_absoluto,
        )
        if proxima_expiracao <= agora_dt:
            cursor.execute(f"UPDATE sessoes SET revogado=1 WHERE token={P}", (token,))
            conn.commit()
            conn.close()
            return None

        # Renova a janela de inatividade em toda requisição autenticada.
        # O limite absoluto de oito horas impede uma sessão sem fim.
        cursor.execute(
            f"UPDATE sessoes SET expira_em={P} WHERE token={P} AND revogado=0",
            (proxima_expiracao.strftime("%Y-%m-%d %H:%M:%S"), token),
        )
        conn.commit()
        conn.close()
        if usuario and "empresa_id" not in usuario:
            usuario["empresa_id"] = "a0000000-0000-0000-0000-000000000001"
        return usuario

    def encerrar_sessao(self, token: str, ip_origem: str = None) -> bool:
        """Invalida a sessao ativa no servidor (logout) e audita o evento (RF-LOGIN-003, RF-LOGIN-006)."""
        if not token:
            return False

        # Tenta descobrir o usuário associado antes de revogar para auditoria
        usuario = self.validar_sessao(token)
        identificador = usuario["email"] if usuario else "token-desconhecido"

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE sessoes SET revogado=1 WHERE token={P}", (token,))
        alterados = cursor.rowcount
        conn.commit()
        conn.close()

        if alterados > 0:
            self.audit_service.registrar_evento(
                "LOGOUT", identificador=identificador, ip_origem=ip_origem, detalhes="Sessão encerrada com sucesso"
            )

        return alterados > 0


# ──────────────────────────────────────────────────────────
# Matriz de Controle de Acesso RBAC Enterprise (8 Perfis)
# ──────────────────────────────────────────────────────────

PERFIS_ENTERPRISE = {
    "superadmin": "Superadministrador Global da Plataforma",
    "admin_empresa": "Administrador da Empresa / Organização",
    "gestor_rh": "Gestor de Recursos Humanos e Pessoas",
    "analista_dp": "Analista Especialista de Departamento Pessoal",
    "financeiro": "Gestor Financeiro e Custos de Pessoal",
    "contabilidade": "Contabilidade e Controladoria Fiscal",
    "gestor_departamento": "Gestor de Departamento / Liderança de Equipe",
    "colaborador": "Colaborador (Autoatendimento e Portal Próprio)",
    # Perfis adicionais / legados para compatibilidade total
    "administrador": "Administrador de Sistema (Legado)",
    "analista_rh": "Analista de RH (Legado)",
    "operador_dp": "Operador de DP (Legado)",
    "gestor": "Gestor Departamental (Legado)",
    "medico_sst": "Médico do Trabalho / SST (Legado)",
    "auditor": "Auditor Fiscal e de Compliance (Legado)",
}

PERMISSOES_RBAC = {
    # 1. Superadministrador e Administrador da Empresa
    "superadmin": ["*"],
    "administrador": ["*"],
    "admin_empresa": ["*"],

    # 2. Gestor de RH
    "gestor_rh": [
        "colaboradores:*", "admissoes:*", "ponto:*", "ferias:*", "afastamentos:*",
        "beneficios:*", "sst:*", "pendencias:*", "metricas:*", "folha:visualizar",
        "esocial:visualizar", "portal_gestor:*"
    ],
    "analista_rh": [
        "colaboradores:*", "admissoes:*", "ponto:*", "ferias:*", "afastamentos:*",
        "beneficios:*", "sst:*", "pendencias:*", "metricas:*", "folha:visualizar",
        "portal_gestor:*"
    ],

    # 3. Analista de Departamento Pessoal
    "analista_dp": [
        "folha:*", "colaboradores:*", "admissoes:*", "ponto:*", "ferias:*",
        "afastamentos:*", "rescisoes:*", "esocial:*", "cnab:*", "pendencias:*",
        "metricas:*", "portal_gestor:*"
    ],
    "operador_dp": [
        "folha:calcular", "folha:visualizar", "colaboradores:visualizar", "ponto:*",
        "ferias:*", "afastamentos:*", "rescisoes:calcular", "rescisoes:visualizar",
        "pendencias:*"
    ],

    # 4. Financeiro
    "financeiro": [
        "folha:visualizar", "rescisoes:visualizar", "metricas:*", "cnab:*",
        "pendencias:visualizar"
    ],

    # 5. Contabilidade
    "contabilidade": [
        "folha:visualizar", "rescisoes:visualizar", "metricas:visualizar",
        "esocial:visualizar", "relatorios:contabilidade"
    ],

    # 6. Gestor de Departamento
    "gestor_departamento": [
        "portal_gestor:*", "ponto:aprovar", "ponto:visualizar", "ferias:aprovar",
        "ferias:visualizar", "colaboradores:equipe", "pendencias:equipe"
    ],
    "gestor": [
        "portal_gestor:*", "ponto:aprovar", "ponto:visualizar", "ferias:aprovar",
        "ferias:visualizar", "colaboradores:equipe", "pendencias:equipe"
    ],

    # 7. Colaborador (Portal do Colaborador)
    "colaborador": [
        "portal_colaborador:*", "holerite:meu", "ponto:meu", "ferias:minhas",
        "informe:meu", "solicitacoes:minhas"
    ],

    # 8. Especialistas
    "medico_sst": [
        "sst:*", "afastamentos:*", "colaboradores:visualizar", "pendencias:visualizar"
    ],
    "auditor": [
        "auditoria:*", "folha:visualizar", "colaboradores:visualizar", "ponto:visualizar",
        "ferias:visualizar", "esocial:visualizar", "metricas:visualizar"
    ],
}


def checar_permissao(perfil: str, permissao_requerida: str) -> bool:
    """
    Verifica se o perfil possui a permissão requerida no modelo RBAC.
    Suporta wildcard '*' para acesso total ou prefixos como 'folha:*'.
    """
    if not perfil:
        return False
    permissoes = PERMISSOES_RBAC.get(perfil, [])
    if "*" in permissoes:
        return True
    if permissao_requerida in permissoes:
        return True

    # Checar prefixo curinga ex: "folha:*" cobre "folha:visualizar"
    if ":" in permissao_requerida:
        modulo = permissao_requerida.split(":")[0]
        if f"{modulo}:*" in permissoes:
            return True

    return False

