"""
Módulo de Rate Limiting para Autenticação — RH2.0
Atende a RF-LOGIN-005, RF-161 e AC-07:
Controla tentativas excessivas de login por IP e/ou identificador,
bloqueando ataques de força bruta com resposta HTTP 429 e cabeçalho Retry-After.
Suporta persistência em banco de dados para compartilhamento seguro entre múltiplas instâncias/workers.
"""
from collections import defaultdict
import os
import threading
import time
from typing import Optional

LIMITE_TENTATIVAS_PADRAO = 5
JANELA_SEGUNDOS_PADRAO = 900  # 15 minutos


class RateLimiter:
    """
    Controlador de taxa de requisições baseado em janela temporal deslizante.
    Thread-safe com suporte a banco de dados compartilhado (multi-instância).
    """
    def __init__(
        self,
        max_tentativas: int = LIMITE_TENTATIVAS_PADRAO,
        janela_segundos: int = JANELA_SEGUNDOS_PADRAO,
        db_path: Optional[str] = None,
    ):
        self.max_tentativas = max_tentativas
        self.janela_segundos = janela_segundos
        self.db_path = db_path
        self._tentativas = defaultdict(list)
        self._lock = threading.Lock()

    def _get_db_conn(self):
        if not self.db_path:
            return None
        try:
            from .database import get_connection
            return get_connection(self.db_path)
        except Exception:
            return None

    def _limpar_antigas_db(self, conn, chave: str, agora: float):
        try:
            corte = agora - self.janela_segundos
            cur = conn.cursor()
            p = "%s" if getattr(self, "_usar_pg", False) else "?"
            cur.execute(f"DELETE FROM rate_limit_tentativas WHERE chave = {p} AND timestamp <= {p};", (chave, corte))
            conn.commit()
        except Exception:
            pass

    def _limpar_antigas(self, chave: str, agora: float):
        """Remove registros fora da janela temporal na memória."""
        corte = agora - self.janela_segundos
        self._tentativas[chave] = [t for t in self._tentativas[chave] if t > corte]

    def esta_bloqueado(self, chave: str) -> tuple[bool, int]:
        """
        Verifica se a chave atingiu o limite de tentativas.
        Consulta banco compartilhado e fallback em memória.
        Retorna (bloqueado: bool, segundos_restantes: int).
        """
        if not chave:
            return False, 0

        agora = time.time()
        conn = self._get_db_conn()
        if conn:
            try:
                self._limpar_antigas_db(conn, chave, agora)
                cur = conn.cursor()
                p = "?"
                cur.execute(f"SELECT timestamp FROM rate_limit_tentativas WHERE chave = {p} ORDER BY timestamp ASC;", (chave,))
                rows = cur.fetchall()
                total = len(rows)
                if total >= self.max_tentativas:
                    mais_antiga = float(rows[0][0])
                    restante = max(1, int(self.janela_segundos - (agora - mais_antiga)))
                    return True, restante
                return False, 0
            except Exception:
                pass
            finally:
                conn.close()

        with self._lock:
            self._limpar_antigas(chave, agora)
            total = len(self._tentativas[chave])
            if total >= self.max_tentativas:
                mais_antiga = self._tentativas[chave][0]
                restante = max(1, int(self.janela_segundos - (agora - mais_antiga)))
                return True, restante
            return False, 0

    def registrar_falha(self, chave: str, ip_origem: Optional[str] = None) -> tuple[bool, int]:
        """
        Registra uma falha de autenticação.
        Persiste no banco compartilhado para rate limiting distribuído.
        Retorna (bloqueado: bool, segundos_restantes: int).
        """
        if not chave:
            return False, 0

        agora = time.time()
        conn = self._get_db_conn()
        if conn:
            try:
                self._limpar_antigas_db(conn, chave, agora)
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO rate_limit_tentativas (chave, timestamp, ip_origem, recurso) VALUES (?, ?, ?, 'login');",
                    (chave, agora, ip_origem or "127.0.0.1"),
                )
                conn.commit()

                cur.execute("SELECT timestamp FROM rate_limit_tentativas WHERE chave = ? ORDER BY timestamp ASC;", (chave,))
                rows = cur.fetchall()
                total = len(rows)
                if total >= self.max_tentativas:
                    mais_antiga = float(rows[0][0])
                    restante = max(1, int(self.janela_segundos - (agora - mais_antiga)))
                    return True, restante
                return False, 0
            except Exception:
                pass
            finally:
                conn.close()

        with self._lock:
            self._limpar_antigas(chave, agora)
            self._tentativas[chave].append(agora)
            total = len(self._tentativas[chave])
            if total >= self.max_tentativas:
                mais_antiga = self._tentativas[chave][0]
                restante = max(1, int(self.janela_segundos - (agora - mais_antiga)))
                return True, restante
            return False, 0

    def registrar_sucesso(self, chave: str):
        """Limpa as tentativas acumuladas após um login bem-sucedido."""
        if not chave:
            return

        conn = self._get_db_conn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM rate_limit_tentativas WHERE chave = ?;", (chave,))
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

        with self._lock:
            if chave in self._tentativas:
                del self._tentativas[chave]

    def resetar(self):
        """Zera todos os contadores (útil em testes isolados)."""
        conn = self._get_db_conn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM rate_limit_tentativas;")
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

        with self._lock:
            self._tentativas.clear()


# Instância global padrão do Rate Limiter
_global_rate_limiter = RateLimiter()


def get_rate_limiter(db_path: Optional[str] = None) -> RateLimiter:
    if db_path and _global_rate_limiter.db_path != db_path:
        return RateLimiter(db_path=db_path)
    return _global_rate_limiter
