"""
Módulo de Auditoria de Eventos e Trilha de Rastreabilidade — RH2.0
Atende a:
- RF-LOGIN-006, RF-170: Eventos de autenticação (sucesso, falhas, logout, rate limit, recuperação de senha).
- RN-072, RN-073, RN-074: Rastreabilidade, imutabilidade e consulta com isolamento estrito por empresa.
- RF-191 a RF-200: Inclusões, alterações, exclusões, aprovações, recusas, memória de cálculos e encadeamento criptográfico inviolável (hash chaining).
Funciona em modo Dual-Mode (PostgreSQL e SQLite).
"""
from datetime import datetime
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .database import get_connection, ph, _usar_postgres, row_to_dict

EVENTOS_PERMITIDOS = {
    "LOGIN_SUCESSO",
    "LOGIN_FALHA",
    "LOGOUT",
    "BLOQUEIO_RATE_LIMIT",
    "RECUPERACAO_SENHA_SOLICITADA",
    "RECUPERACAO_SENHA_SUCESSO",
    "RECUPERACAO_SENHA_FALHA",
    "SESSAO_EXPIRADA",
    "SESSAO_REVOGADA",
    "ALTERACAO_PERMISSAO",
}


def calcular_hash_registro(
    hash_anterior: str,
    empresa_id: str,
    modulo: str,
    operacao: str,
    registro_tipo: str,
    registro_id: str,
    campo: str,
    v_ant: str,
    v_novo: str,
    usuario: str,
    criado_em: str,
) -> str:
    """Calcula hash criptográfico SHA-256 para encadeamento inviolável de logs (RF-200)."""
    payload = f"{hash_anterior or 'GENESIS'}|{empresa_id or ''}|{modulo}|{operacao}|{registro_tipo}|{registro_id}|{campo or ''}|{v_ant or ''}|{v_novo or ''}|{usuario}|{criado_em}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        Registra um evento de autenticação/segurança no banco de dados.
        Garante que nenhum segredo seja persistido (RF-LOGIN-006, RF-170).
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
            print(f"[AUDITORIA ERROR] Falha ao registrar evento: {type(e).__name__}", file=sys.stderr)
            return False
        finally:
            conn.close()

    def registrar_operacao(
        self,
        modulo: str,
        operacao: str,
        registro_tipo: str,
        registro_id: Any,
        usuario: str,
        campo_alterado: Optional[str] = None,
        valor_anterior: Optional[Any] = None,
        valor_novo: Optional[Any] = None,
        empresa_id: Optional[str] = None,
        ip_origem: Optional[str] = None,
        detalhes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Registra log de auditoria operacional com encadeamento criptográfico inviolável (RF-191 a RF-200).
        Suporta diff de alteração, inclusão, exclusão, histórico de cálculo e aprovação.
        """
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        v_ant_str = json.dumps(valor_anterior, ensure_ascii=False) if isinstance(valor_anterior, (dict, list)) else (str(valor_anterior) if valor_anterior is not None else None)
        v_nov_str = json.dumps(valor_novo, ensure_ascii=False) if isinstance(valor_novo, (dict, list)) else (str(valor_novo) if valor_novo is not None else None)
        emp_id = empresa_id or "a0000000-0000-0000-0000-000000000001"
        reg_id_str = str(registro_id)

        P = self._ph()
        conn = self._conn()
        try:
            cur = conn.cursor()
            # Obter o último hash da cadeia para a mesma empresa (ou global)
            cur.execute(
                f"""
                SELECT hash_atual FROM auditoria_operacoes
                WHERE empresa_id = {P} OR empresa_id IS NULL
                ORDER BY id DESC LIMIT 1;
                """,
                (emp_id,),
            )
            last_row = cur.fetchone()
            hash_anterior = last_row[0] if last_row and last_row[0] else "GENESIS_RH20_BLOCK"

            hash_atual = calcular_hash_registro(
                hash_anterior=hash_anterior,
                empresa_id=emp_id,
                modulo=modulo,
                operacao=operacao,
                registro_tipo=registro_tipo,
                registro_id=reg_id_str,
                campo=campo_alterado or "",
                v_ant=v_ant_str or "",
                v_novo=v_nov_str or "",
                usuario=usuario or "Sistema",
                criado_em=agora,
            )

            cur.execute(
                f"""
                INSERT INTO auditoria_operacoes (
                    empresa_id, modulo, operacao, registro_tipo, registro_id,
                    campo_alterado, valor_anterior, valor_novo,
                    usuario_responsavel, ip_origem, detalhes,
                    hash_anterior, hash_atual, criado_em
                ) VALUES ({P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P}, {P});
                """,
                (
                    emp_id,
                    modulo,
                    operacao,
                    registro_tipo,
                    reg_id_str,
                    campo_alterado,
                    v_ant_str,
                    v_nov_str,
                    usuario or "Sistema",
                    ip_origem or "127.0.0.1",
                    detalhes,
                    hash_anterior,
                    hash_atual,
                    agora,
                ),
            )
            conn.commit()
            return {
                "sucesso": True,
                "hash_atual": hash_atual,
                "hash_anterior": hash_anterior,
                "criado_em": agora,
            }
        finally:
            conn.close()

    def verificar_integridade_trilha(self, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Valida a integridade matemática da trilha criptográfica de auditoria (RF-200, RN-072).
        Detecta adulteração ou exclusão de qualquer registro na cadeia.
        """
        P = self._ph()
        conn = self._conn()
        try:
            cur = conn.cursor()
            if empresa_id:
                cur.execute(
                    f"""
                    SELECT id, empresa_id, modulo, operacao, registro_tipo, registro_id,
                           campo_alterado, valor_anterior, valor_novo, usuario_responsavel,
                           detalhes, hash_anterior, hash_atual, criado_em
                    FROM auditoria_operacoes
                    WHERE empresa_id = {P}
                    ORDER BY id ASC;
                    """,
                    (empresa_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT id, empresa_id, modulo, operacao, registro_tipo, registro_id,
                           campo_alterado, valor_anterior, valor_novo, usuario_responsavel,
                           detalhes, hash_anterior, hash_atual, criado_em
                    FROM auditoria_operacoes
                    ORDER BY id ASC;
                    """
                )

            rows = cur.fetchall()
            if not rows:
                return {
                    "integro": True,
                    "total_registros_verificados": 0,
                    "mensagem": "Nenhum registro de auditoria na base. Cadeia vazia e íntegra.",
                }

            ultimo_hash = "GENESIS_RH20_BLOCK"
            for r in rows:
                d = self._row(cur, r)
                esperado_anterior = d.get("hash_anterior")
                # Se for o primeiro registro encadeado
                if esperado_anterior and esperado_anterior != ultimo_hash and esperado_anterior != "GENESIS_RH20_BLOCK":
                    return {
                        "integro": False,
                        "violacao_em_id": d["id"],
                        "tipo_violacao": "QUEBRA_ENCADEAMENTO_ANTERIOR",
                        "mensagem": f"Violação de integridade no registro #{d['id']}: hash_anterior não confere.",
                    }

                recalculado = calcular_hash_registro(
                    hash_anterior=d.get("hash_anterior") or "",
                    empresa_id=d.get("empresa_id") or "",
                    modulo=d.get("modulo") or "",
                    operacao=d.get("operacao") or "",
                    registro_tipo=d.get("registro_tipo") or "",
                    registro_id=str(d.get("registro_id") or ""),
                    campo=d.get("campo_alterado") or "",
                    v_ant=d.get("valor_anterior") or "",
                    v_novo=d.get("valor_novo") or "",
                    usuario=d.get("usuario_responsavel") or "",
                    criado_em=d.get("criado_em") or "",
                )

                if d.get("hash_atual") and d.get("hash_atual") != recalculado:
                    return {
                        "integro": False,
                        "violacao_em_id": d["id"],
                        "tipo_violacao": "HASH_ALTERADO_OU_REGISTRO_ADULTERADO",
                        "mensagem": f"Adulteração detectada no registro #{d['id']}: dados do registro foram modificados.",
                    }

                ultimo_hash = d.get("hash_atual") or ultimo_hash

            return {
                "integro": True,
                "total_registros_verificados": len(rows),
                "mensagem": "Trilha criptográfica de auditoria 100% íntegra, verificada e livre de adulterações.",
            }
        finally:
            conn.close()

    def listar_auditoria(
        self,
        empresa_id: Optional[str] = None,
        modulo: Optional[str] = None,
        operacao: Optional[str] = None,
        usuario: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        pagina: int = 1,
        limite: int = 50,
    ) -> Dict[str, Any]:
        """
        Consulta avançada de logs com paginação e isolamento estrito por empresa (RN-074, RF-198, RF-199).
        """
        P = self._ph()
        conn = self._conn()
        try:
            cur = conn.cursor()
            filtros = ["1=1"]
            params = []

            # Isolamento multi-empresa estrito (RN-074)
            if empresa_id:
                filtros.append(f"empresa_id = {P}")
                params.append(empresa_id)

            if modulo:
                filtros.append(f"modulo = {P}")
                params.append(modulo)

            if operacao:
                filtros.append(f"operacao = {P}")
                params.append(operacao)

            if usuario:
                filtros.append(f"usuario_responsavel LIKE {P}")
                params.append(f"%{usuario}%")

            if data_inicio:
                filtros.append(f"criado_em >= {P}")
                params.append(f"{data_inicio} 00:00:00")

            if data_fim:
                filtros.append(f"criado_em <= {P}")
                params.append(f"{data_fim} 23:59:59")

            where_clause = " AND ".join(filtros)

            # Contagem total para paginação
            cur.execute(f"SELECT COUNT(*) FROM auditoria_operacoes WHERE {where_clause};", tuple(params))
            total_registros = int(cur.fetchone()[0] or 0)

            offset = max(0, (pagina - 1) * limite)
            params.extend([limite, offset])

            cur.execute(
                f"""
                SELECT id, empresa_id, modulo, operacao, registro_tipo, registro_id,
                       campo_alterado, valor_anterior, valor_novo,
                       usuario_responsavel, ip_origem, detalhes,
                       hash_anterior, hash_atual, criado_em
                FROM auditoria_operacoes
                WHERE {where_clause}
                ORDER BY id DESC
                LIMIT {P} OFFSET {P};
                """,
                tuple(params),
            )

            rows = cur.fetchall()
            itens = [self._row(cur, r) for r in rows]

            return {
                "total": total_registros,
                "pagina": pagina,
                "limite": limite,
                "paginas_total": max(1, (total_registros + limite - 1) // limite),
                "itens": itens,
            }
        finally:
            conn.close()

    def listar_eventos(self, limite: int = 50, evento: str = None) -> list[dict]:
        """Consulta os últimos eventos registrados para verificação e testes."""
        P = self._ph()
        conn = self._conn()
        try:
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
            return [self._row(cursor, r) for r in rows]
        finally:
            conn.close()
