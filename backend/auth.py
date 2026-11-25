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
import threading
from datetime import datetime, timedelta

from .database import _usar_postgres, get_connection, init_db, insert_returning_id, ph, row_to_dict
from .audit import AuditService
from .observabilidade import medir_operacao, registrar_evento as obs_registrar_evento

ITERATIONS = 100_000
MENSAGEM_GENERICA_ERRO = "E-mail ou senha inválidos."

_PROVISIONED_DBS = set()
_PROVISION_LOCK = threading.Lock()


def get_session_idle_seconds() -> int:
    """Tempo de expiração por inatividade (padrão: 120 minutos = 2 horas)."""
    if os.environ.get("SESSION_IDLE_MINUTES"):
        minutos = max(1, int(os.environ.get("SESSION_IDLE_MINUTES", "120")))
        return minutos * 60
    if os.environ.get("SESSION_EXPIRATION_HOURS"):
        horas = max(1, int(os.environ.get("SESSION_EXPIRATION_HOURS", "8")))
        return horas * 3600
    return 120 * 60


def get_session_max_seconds() -> int:
    """Tempo máximo absoluto de duração da sessão (padrão: 12 horas — nunca infinita)."""
    horas = max(1, int(os.environ.get("SESSION_MAX_HOURS", "12")))
    return max(get_session_idle_seconds(), horas * 3600)


def get_session_renew_threshold_seconds() -> int:
    """Intervalo mínimo entre gravações de renovação deslizante no banco (padrão: 15 min)."""
    minutos = max(0, int(os.environ.get("SESSION_RENEW_THRESHOLD_MINUTES", "15")))
    return minutos * 60


def get_session_max_concurrent() -> int:
    """Quantidade máxima de sessões simultâneas permitidas por usuário (padrão: 5)."""
    if os.environ.get("SESSION_SINGLE_CONCURRENT", "").strip().lower() in ("1", "true", "yes"):
        return 1
    return max(1, int(os.environ.get("SESSION_MAX_CONCURRENT", "5")))


def resetar_cache_provisionamento():
    with _PROVISION_LOCK:
        _PROVISIONED_DBS.clear()


class CredenciaisInvalidasException(Exception):
    pass


class SessaoInvalidaException(Exception):
    pass


def hash_token(token: str) -> str:
    """Gera hash SHA-256 do token de sessão para armazenamento protegido no banco (RF-168, RF-169)."""
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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

    def provisionar_usuario_inicial(self, force: bool = False) -> dict:
        """
        Provisiona as contas padrão de administrador e visitante/convidado
        caso ainda não existam no banco de dados.
        Exige ADMIN_INITIAL_PASSWORD explícita para prevenir senhas padrão em produção.
        """
        chave_cache = f"pg:{os.environ.get('DATABASE_URL', '')}" if self._pg() else f"sqlite:{os.path.abspath(self.db_path or 'colaboradores.db')}"
        if not force and chave_cache in _PROVISIONED_DBS:
            return {}

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

        if admin_existente:
            user = self._row(cursor, admin_existente)
        else:
            cursor.execute(f"SELECT id, email, usuario, nome_completo, perfil, status FROM usuarios WHERE email = {P} OR usuario = {P}", ("admin.dp@empresa.com.br", "admin.dp"))
            row_admin = cursor.fetchone()
            user = self._row(cursor, row_admin) if row_admin else {}
        conn.close()
        with _PROVISION_LOCK:
            _PROVISIONED_DBS.add(chave_cache)
        return user

    # ──────────────────────────────────────────────────────────
    # Autenticacao
    # ──────────────────────────────────────────────────────────

    def autenticar(self, identificador: str, senha: str, ip_origem: str = None) -> tuple:
        """
        Valida as credenciais contra o banco de dados.
        Retorna (dados_usuario_sem_senha, token) se valido.
        Usa mensagem generica 'E-mail ou senha inválidos.' para evitar enumeracao de usuarios (RF-LOGIN-002, AC-06).
        Gerencia política segura de sessões simultâneas, inatividade deslizante e teto absoluto.
        """
        if not identificador or not senha:
            raise CredenciaisInvalidasException("E-mail e senha são obrigatórios.")

        identificador = identificador.strip().lower()
        P = self._ph()

        with medir_operacao("auth_ms"):
            conn = self._conn()
            try:
                cursor = conn.cursor()

                try:
                    cursor.execute(f"""
                        SELECT id, email, usuario, nome_completo,
                               senha_hash, salt, perfil, status, empresa_id
                        FROM usuarios
                        WHERE LOWER(email) = {P} OR LOWER(usuario) = {P}
                    """, (identificador, identificador))
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    cursor.execute(f"""
                        SELECT id, email, usuario, nome_completo,
                               senha_hash, salt, perfil, status
                        FROM usuarios
                        WHERE LOWER(email) = {P} OR LOWER(usuario) = {P}
                    """, (identificador, identificador))

                row = cursor.fetchone()
                if not row:
                    conn.close()
                    obs_registrar_evento("auth_login_falha", {"motivo": "nao_encontrado"})
                    self.audit_service.registrar_evento(
                        "LOGIN_FALHA", identificador=identificador, ip_origem=ip_origem, detalhes="Usuário não encontrado"
                    )
                    raise CredenciaisInvalidasException(MENSAGEM_GENERICA_ERRO)

                usuario = self._row(cursor, row)

                # Conta inativa também retorna mensagem genérica para não revelar existência nem status
                if usuario["status"] != "ativo":
                    conn.close()
                    obs_registrar_evento("auth_login_falha", {"motivo": "inativo"})
                    self.audit_service.registrar_evento(
                        "LOGIN_FALHA", identificador=identificador, ip_origem=ip_origem, detalhes="Tentativa em conta inativa"
                    )
                    raise CredenciaisInvalidasException(MENSAGEM_GENERICA_ERRO)

                if not verificar_senha(senha, usuario["senha_hash"], usuario["salt"]):
                    conn.close()
                    obs_registrar_evento("auth_login_falha", {"motivo": "senha_incorreta"})
                    self.audit_service.registrar_evento(
                        "LOGIN_FALHA", identificador=identificador, ip_origem=ip_origem, detalhes="Senha incorreta"
                    )
                    raise CredenciaisInvalidasException(MENSAGEM_GENERICA_ERRO)

                # ── Controle seguro de sessões simultâneas ──
                max_concorrentes = get_session_max_concurrent()
                if max_concorrentes <= 1:
                    cursor.execute(f"UPDATE sessoes SET revogado=1 WHERE usuario_id={P} AND revogado=0", (usuario["id"],))
                else:
                    # Mantém até (max_concorrentes - 1) sessões mais recentes, revogando apenas o excedente
                    cursor.execute(
                        f"SELECT token FROM sessoes WHERE usuario_id={P} AND revogado=0 ORDER BY criado_em DESC",
                        (usuario["id"],),
                    )
                    ativas = cursor.fetchall()
                    if len(ativas) >= max_concorrentes:
                        excedentes = [r[0] for r in ativas[max_concorrentes - 1:]]
                        for tok_ant in excedentes:
                            cursor.execute(f"UPDATE sessoes SET revogado=1 WHERE token={P}", (tok_ant,))

                token = secrets.token_hex(32)
                token_armazenado = hash_token(token)
                agora_dt = datetime.now()
                idle_seg = get_session_idle_seconds()
                max_seg = get_session_max_seconds()
                expira_dt = agora_dt + timedelta(seconds=idle_seg)
                expira_abs_dt = agora_dt + timedelta(seconds=max_seg)
                agora_str = agora_dt.strftime("%Y-%m-%d %H:%M:%S")
                expira_str = expira_dt.strftime("%Y-%m-%d %H:%M:%S")
                expira_abs_str = expira_abs_dt.strftime("%Y-%m-%d %H:%M:%S")

                try:
                    cursor.execute(f"""
                        INSERT INTO sessoes (token, usuario_id, criado_em, expira_em, ultima_atividade, expira_absoluto_em, revogado)
                        VALUES ({P},{P},{P},{P},{P},{P},0)
                    """, (token_armazenado, usuario["id"], agora_str, expira_str, agora_str, expira_abs_str))
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    cursor.execute(f"""
                        INSERT INTO sessoes (token, usuario_id, criado_em, expira_em, revogado)
                        VALUES ({P},{P},{P},{P},0)
                    """, (token_armazenado, usuario["id"], agora_str, expira_str))

                cursor.execute(f"""
                    UPDATE usuarios SET ultimo_login={P} WHERE id={P}
                """, (agora_str, usuario["id"]))

                # Grava auditoria de sucesso na MESMA transação (elimina 1 conexão + round-trip extra ao Neon)
                try:
                    ip_seguro = (str(ip_origem).strip()[:45]) if ip_origem else "127.0.0.1"
                    ident_seguro = self.audit_service.sanitizar_identificador(usuario["email"])
                    cursor.execute(
                        f"""
                        INSERT INTO auditoria_autenticacao (
                            evento, identificador, ip_origem, detalhes, criado_em
                        ) VALUES ({P}, {P}, {P}, {P}, {P})
                        """,
                        ("LOGIN_SUCESSO", ident_seguro, ip_seguro, "Autenticação válida", agora_str),
                    )
                except Exception:
                    pass

                conn.commit()
            finally:
                conn.close()

        obs_registrar_evento("auth_login_sucesso")

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

    def validar_sessao(self, token: str, renovar: bool = True):
        """
        Valida se o token existe, não expirou (inatividade e teto máximo absoluto) e não foi revogado.
        Aplica renovação deslizante controlada (throttled) durante a atividade do usuário,
        nunca ultrapassando o limite máximo absoluto (expira_absoluto_em).
        Retorna os dados do usuario autenticado ou None.
        """
        if not token:
            return None

        token_hash = hash_token(token)
        P = self._ph()
        conn = self._conn()
        try:
            cursor = conn.cursor()
            agora_dt = datetime.now()
            agora_str = agora_dt.strftime("%Y-%m-%d %H:%M:%S")
            tem_colunas_estendidas = True

            try:
                cursor.execute(f"""
                    SELECT u.id, u.email, u.usuario, u.nome_completo, u.perfil, u.empresa_id,
                           s.token AS sessao_token_armazenado, s.criado_em, s.expira_em,
                           s.ultima_atividade, s.expira_absoluto_em, s.revogado
                    FROM sessoes s
                    JOIN usuarios u ON u.id = s.usuario_id
                    WHERE (s.token = {P} OR s.token = {P})
                      AND s.revogado = 0
                      AND u.status = 'ativo'
                """, (token_hash, token))
            except Exception:
                tem_colunas_estendidas = False
                try:
                    conn.rollback()
                except Exception:
                    pass
                cursor.execute(f"""
                    SELECT u.id, u.email, u.usuario, u.nome_completo, u.perfil,
                           s.token AS sessao_token_armazenado, s.criado_em, s.expira_em, s.revogado
                    FROM sessoes s
                    JOIN usuarios u ON u.id = s.usuario_id
                    WHERE (s.token = {P} OR s.token = {P})
                      AND s.revogado = 0
                      AND u.status = 'ativo'
                """, (token_hash, token))

            row = cursor.fetchone()
            if not row:
                return None

            usuario = self._row(cursor, row)
            expira_em_str = usuario.get("expira_em") or ""
            criado_em_str = usuario.get("criado_em") or agora_str
            ultima_ativ_str = usuario.get("ultima_atividade") or criado_em_str
            expira_abs_str = usuario.get("expira_absoluto_em")

            # Verifica expiração por inatividade
            if expira_em_str and expira_em_str < agora_str:
                obs_registrar_evento("sessao_expirada", {"motivo": "inatividade"})
                return None

            # Verifica limite máximo absoluto (nunca permite sessão infinita)
            try:
                criado_dt = datetime.strptime(criado_em_str[:19], "%Y-%m-%d %H:%M:%S")
                if expira_abs_str:
                    expira_abs_dt = datetime.strptime(expira_abs_str[:19], "%Y-%m-%d %H:%M:%S")
                else:
                    expira_abs_dt = criado_dt + timedelta(seconds=get_session_max_seconds())
            except Exception:
                expira_abs_dt = agora_dt + timedelta(seconds=get_session_max_seconds())

            if agora_dt > expira_abs_dt:
                obs_registrar_evento("sessao_expirada", {"motivo": "expiracao_maxima"})
                return None

            # ── Renovação deslizante controlada (throttled) ──
            sessao_renovada = False
            if renovar:
                try:
                    ultima_dt = datetime.strptime(ultima_ativ_str[:19], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    ultima_dt = agora_dt - timedelta(seconds=get_session_renew_threshold_seconds() + 1)

                threshold = get_session_renew_threshold_seconds()
                elapsed = (agora_dt - ultima_dt).total_seconds()
                if elapsed >= threshold:
                    idle_seg = get_session_idle_seconds()
                    novo_expira_dt = min(agora_dt + timedelta(seconds=idle_seg), expira_abs_dt)
                    novo_expira_str = novo_expira_dt.strftime("%Y-%m-%d %H:%M:%S")
                    tok_db = usuario.get("sessao_token_armazenado") or token_hash
                    try:
                        if tem_colunas_estendidas:
                            cursor.execute(
                                f"UPDATE sessoes SET expira_em={P}, ultima_atividade={P} WHERE token={P}",
                                (novo_expira_str, agora_str, tok_db),
                            )
                        else:
                            cursor.execute(
                                f"UPDATE sessoes SET expira_em={P} WHERE token={P}",
                                (novo_expira_str, tok_db),
                            )
                        conn.commit()
                        usuario["expira_em"] = novo_expira_str
                        usuario["ultima_atividade"] = agora_str
                        sessao_renovada = True
                        obs_registrar_evento("sessao_renovada")
                    except Exception:
                        try:
                            conn.rollback()
                        except Exception:
                            pass

            usuario.pop("sessao_token_armazenado", None)
            usuario["_sessao_renovada"] = sessao_renovada
            if not usuario.get("empresa_id"):
                usuario["empresa_id"] = "a0000000-0000-0000-0000-000000000001"
            return usuario
        finally:
            conn.close()

    def encerrar_sessao(self, token: str, ip_origem: str = None) -> bool:
        """Invalida a sessao ativa no servidor (logout) e audita o evento (RF-LOGIN-003, RF-LOGIN-006)."""
        if not token:
            return False


        # Tenta descobrir o usuário associado antes de revogar para auditoria
        usuario = self.validar_sessao(token)
        identificador = usuario["email"] if usuario else "token-desconhecido"

        token_hash = hash_token(token)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE sessoes SET revogado=1 WHERE token={P} OR token={P}", (token_hash, token))
        alterados = cursor.rowcount
        conn.commit()
        conn.close()

        if alterados > 0:
            self.audit_service.registrar_evento(
                "LOGOUT", identificador=identificador, ip_origem=ip_origem, detalhes="Sessão encerrada com sucesso"
            )

        return alterados > 0

    def revogar_todas_sessoes_usuario(self, usuario_id: int) -> int:
        """Revoga todas as sessões ativas de um usuário (RF-169, RF-170)."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE sessoes SET revogado=1 WHERE usuario_id={P} AND revogado=0", (usuario_id,))
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return count

    def solicitar_recuperacao_senha(self, identificador: str, ip_origem: str = None) -> dict:
        """
        Gera token aleatório seguro para recuperação de senha com validade de 1 hora.
        Armazena hash SHA-256 no banco (RF-162).
        Retorna sucesso sem enumeração de usuário caso não exista.
        """
        if not identificador:
            raise ValueError("E-mail ou nome de usuário é obrigatório.")

        identificador = identificador.strip().lower()
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT id, email, usuario, nome_completo, status FROM usuarios WHERE LOWER(email) = {P} OR LOWER(usuario) = {P};",
            (identificador, identificador),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            self.audit_service.registrar_evento(
                "RECUPERACAO_SENHA_SOLICITADA",
                identificador=identificador,
                ip_origem=ip_origem,
                detalhes="Identificador não encontrado (sem enumeração)",
            )
            return {
                "sucesso": True,
                "mensagem": "Se o e-mail ou usuário estiver cadastrado, as instruções de recuperação serão enviadas.",
                "token_gerado": False,
            }

        usr = self._row(cursor, row)
        if usr.get("status") != "ativo":
            conn.close()
            return {
                "sucesso": True,
                "mensagem": "Se o e-mail ou usuário estiver cadastrado, as instruções de recuperação serão enviadas.",
                "token_gerado": False,
            }

        token_raw = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token_raw.encode("utf-8")).hexdigest()
        agora = datetime.now()
        expira_dt = agora + timedelta(hours=1)
        agora_str = agora.strftime("%Y-%m-%d %H:%M:%S")
        expira_str = expira_dt.strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            f"""
            INSERT INTO recuperacao_senha (usuario_id, token_hash, criado_em, expira_em, usado, ip_solicitacao)
            VALUES ({P}, {P}, {P}, {P}, 0, {P});
            """,
            (usr["id"], token_hash, agora_str, expira_str, ip_origem or "127.0.0.1"),
        )
        conn.commit()
        conn.close()

        self.audit_service.registrar_evento(
            "RECUPERACAO_SENHA_SOLICITADA",
            identificador=usr["email"],
            ip_origem=ip_origem,
            detalhes="Token de recuperação emitido com sucesso",
        )

        return {
            "sucesso": True,
            "mensagem": "Instruções e código de recuperação de senha gerados com sucesso.",
            "token_gerado": True,
            "token_recuperacao": token_raw,
            "expira_em": expira_str,
        }

    def redefinir_senha_com_token(self, token_recuperacao: str, nova_senha: str, ip_origem: str = None) -> dict:
        """
        Valida o token de uso único, checa expiração, altera a senha e invalida sessões antigas (RF-162).
        """
        if not token_recuperacao or not nova_senha:
            raise ValueError("Token e nova senha são obrigatórios.")

        if len(nova_senha) < 8:
            raise ValueError("A nova senha deve ter no mínimo 8 caracteres.")

        token_hash = hashlib.sha256(token_recuperacao.strip().encode("utf-8")).hexdigest()
        agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(
            f"""
            SELECT id, usuario_id, expira_em, usado
            FROM recuperacao_senha
            WHERE token_hash = {P};
            """,
            (token_hash,),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            self.audit_service.registrar_evento(
                "RECUPERACAO_SENHA_FALHA",
                identificador="desconhecido",
                ip_origem=ip_origem,
                detalhes="Token de recuperação inválido ou inexistente",
            )
            raise ValueError("Token de recuperação inválido ou expirado.")

        rec = self._row(cursor, row)
        if int(rec.get("usado", 0)) == 1:
            conn.close()
            raise ValueError("Token de recuperação já foi utilizado. Solicite um novo.")

        if str(rec.get("expira_em")) < agora_str:
            conn.close()
            raise ValueError("Token de recuperação expirado. Solicite um novo token.")

        uid = int(rec["usuario_id"])
        salt = secrets.token_hex(16)
        senha_hash, _ = hash_senha(nova_senha, salt)

        cursor.execute(
            f"UPDATE usuarios SET senha_hash = {P}, salt = {P} WHERE id = {P};",
            (senha_hash, salt, uid),
        )
        cursor.execute(
            f"UPDATE recuperacao_senha SET usado = 1 WHERE id = {P};",
            (rec["id"],),
        )
        # Revoga todas as sessões anteriores para garantir segurança total
        cursor.execute(
            f"UPDATE sessoes SET revogado = 1 WHERE usuario_id = {P} AND revogado = 0;",
            (uid,),
        )
        conn.commit()

        cursor.execute(f"SELECT email FROM usuarios WHERE id = {P};", (uid,))
        usr_row = cursor.fetchone()
        email_usr = usr_row[0] if usr_row else f"user-{uid}"
        conn.close()

        self.audit_service.registrar_evento(
            "RECUPERACAO_SENHA_SUCESSO",
            identificador=email_usr,
            ip_origem=ip_origem,
            detalhes="Senha redefinida e sessões ativas revogadas",
        )

        return {
            "sucesso": True,
            "mensagem": "Senha redefinida com sucesso! Faça login com a nova credencial.",
        }


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


def filtrar_dados_sensiveis(dados: dict, perfil: str) -> dict:
    """
    Aplica regras de sigilo salarial (RN-069) e proteção de dados sensíveis LGPD (RN-070).
    Mascara remuneração e dados médicos para perfis sem privilégios correspondentes.
    """
    if not isinstance(dados, dict):
        return dados

    d = dict(dados)
    # 1. Sigilo Salarial (RN-069)
    perfis_com_acesso_salarial = {
        "superadmin", "administrador", "admin_empresa", "analista_dp",
        "operador_dp", "financeiro", "contabilidade"
    }
    if perfil not in perfis_com_acesso_salarial:
        for campo_salario in [
            "salario_base", "salario", "remuneracao", "custo_total_mes",
            "desconto_colaborador", "total_liquido", "total_proventos"
        ]:
            if campo_salario in d and d[campo_salario] is not None:
                d[campo_salario] = "***"
        if "dados_bancarios" in d:
            d["dados_bancarios"] = "***"

    # 2. Dados Médicos e ASOs (RN-070)
    perfis_medicos = {"superadmin", "administrador", "medico_sst"}
    if perfil not in perfis_medicos:
        for campo_medico in ["cid", "cid_codigo", "diagnostico", "observacoes_medicas", "laudo_medico"]:
            if campo_medico in d and d[campo_medico]:
                d[campo_medico] = "[DADO MÉDICO RESTRITO — NR-07 / LGPD]"

    # 3. Mascaramento LGPD de CPF se não for gestor DP / RH
    perfis_dp = {
        "superadmin", "administrador", "admin_empresa", "gestor_rh",
        "analista_rh", "analista_dp", "operador_dp"
    }
    if perfil not in perfis_dp and "cpf" in d and d["cpf"]:
        cpf_limpo = str(d["cpf"]).replace(".", "").replace("-", "")
        if len(cpf_limpo) == 11:
            d["cpf"] = f"***.{cpf_limpo[3:6]}.{cpf_limpo[6:9]}-**"

    return d


