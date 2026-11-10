"""
Módulo de Rate Limiting para Autenticação — RH2.0
Atende a RF-LOGIN-005 e AC-07:
Controla tentativas excessivas de login por IP e/ou identificador,
bloqueando ataques de força bruta com resposta HTTP 429 e cabeçalho Retry-After.
"""
from collections import defaultdict
import threading
import time

LIMITE_TENTATIVAS_PADRAO = 5
JANELA_SEGUNDOS_PADRAO = 900  # 15 minutos


class RateLimiter:
    """
    Controlador de taxa de requisições baseado em janela temporal deslizante.
    Thread-safe com lock nativo.
    """
    def __init__(self, max_tentativas: int = LIMITE_TENTATIVAS_PADRAO, janela_segundos: int = JANELA_SEGUNDOS_PADRAO):
        self.max_tentativas = max_tentativas
        self.janela_segundos = janela_segundos
        self._tentativas = defaultdict(list)
        self._lock = threading.Lock()

    def _limpar_antigas(self, chave: str, agora: float):
        """Remove registros fora da janela temporal."""
        corte = agora - self.janela_segundos
        self._tentativas[chave] = [t for t in self._tentativas[chave] if t > corte]

    def esta_bloqueado(self, chave: str) -> tuple[bool, int]:
        """
        Verifica se a chave atingiu o limite de tentativas.
        Retorna (bloqueado: bool, segundos_restantes: int).
        """
        if not chave:
            return False, 0

        agora = time.time()
        with self._lock:
            self._limpar_antigas(chave, agora)
            total = len(self._tentativas[chave])
            if total >= self.max_tentativas:
                mais_antiga = self._tentativas[chave][0]
                restante = max(1, int(self.janela_segundos - (agora - mais_antiga)))
                return True, restante
            return False, 0

    def registrar_falha(self, chave: str) -> tuple[bool, int]:
        """
        Registra uma falha de autenticação.
        Retorna (bloqueado: bool, segundos_restantes: int).
        """
        if not chave:
            return False, 0

        agora = time.time()
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
        with self._lock:
            if chave in self._tentativas:
                del self._tentativas[chave]

    def resetar(self):
        """Zera todos os contadores (útil em testes isolados)."""
        with self._lock:
            self._tentativas.clear()


# Instância global padrão do Rate Limiter
_global_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _global_rate_limiter

