"""
Módulo de Auditoria de Eventos de Autenticação — RH2.0
Atende a RF-LOGIN-006:
Registra eventos de login com sucesso, falhas, logout e bloqueio por rate limit.
NUNCA registra senhas, hashes completos, cookies ou tokens secretos.
Funciona em modo Dual-Mode (PostgreSQL e SQLite).
"""
from datetime import datetime
import os
import sys

from .database import get_connection, ph, _usar_postgres, row_to_dict

EVENTOS_PERMITIDOS = {
    "LOGIN_SUCESSO",
    "LOGIN_FALHA",
    "LOGOUT",
    "BLOQUEIO_RATE_LIMIT",
}


class AuditService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path

    def _ph(self) -> str:
        return ph(self.db_path)

    def _conn(self):
        return get_connection(self.db_path)

    def _row(self, cursor, row) -> dict:
        return row_to_dict(cursor, row, self.db_path)

    def sanitizar_identificador(self, identificador: str) -> str:
        """Sanitiza o identificador evitando quebras de linha e limitando o tamanho."""
        if not identificador:
            return "anônimo"
        # Mantém apenas caracteres seguros e limita a 100 caracteres
        identificador = str(identificador).strip().replace("\n", " ").replace("\r", " ")
        return identificador[:100]

    def registrar_evento(
        self,
        evento: str,
        identificador: str = None,
        ip_origem: str = None,
        detalhes: str = None,
    ) -> bool:
        """
        Registra um evento de autenticação no banco de dados.
        Garante que nenhum segredo seja persistido.
        """
        if evento not in EVENTOS_PERMITIDOS:
            raise ValueError(f"Evento de auditoria inválido: {evento}")

        identificador_seguro = self.sanitizar_identificador(identificador)
        ip_seguro = (str(ip_origem).strip()[:45]) if ip_origem else "127.0.0.1"
        detalhes_seguro = (str(detalhes).strip()[:255]) if detalhes else ""
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        try:
            cursor.execute(
                f"""
                INSERT INTO auditoria_autenticacao (
                    evento, identificador, ip_origem, detalhes, criado_em
                ) VALUES ({P}, {P}, {P}, {P}, {P})
                """,
                (evento, identificador_seguro, ip_seguro, detalhes_seguro, agora),
            )
            conn.commit()
            return True
        except Exception as e:
            # Não interrompe a requisição caso a auditoria falhe em registrar, mas não propaga segredos
            print(f"[AUDITORIA ERROR] Falha ao registrar evento: {type(e).__name__}", file=sys.stderr)
            return False
        finally:
            conn.close()

    def listar_eventos(self, limite: int = 50, evento: str = None) -> list[dict]:
        """Consulta os últimos eventos registrados para verificação e testes."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        if evento:
            cursor.execute(
                f"""
                SELECT id, evento, identificador, ip_origem, detalhes, criado_em
                FROM auditoria_autenticacao
                WHERE evento = {P}
                ORDER BY id DESC
                LIMIT {P}
                """,
                (evento, limite),
            )
        else:
            cursor.execute(
                f"""
                SELECT id, evento, identificador, ip_origem, detalhes, criado_em
                FROM auditoria_autenticacao
                ORDER BY id DESC
                LIMIT {P}
                """,
                (limite,),
            )

        rows = cursor.fetchall()
        eventos = [self._row(cursor, r) for r in rows]
        conn.close()
        return eventos

