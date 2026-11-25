"""
Módulo de Observabilidade, Métricas e Diagnóstico Seguro — RH2.0
Mede tempo de resposta de APIs, tempo de autenticação, contagem e duração de consultas SQL,
renovações/expirações de sessão e falhas de conexão com o banco.

Segurança:
- NUNCA registra senhas, tokens, cookies, cabeçalhos Authorization ou dados pessoais sensíveis.
"""
from collections import deque
from contextlib import contextmanager
import json
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

_TLS = threading.local()
_LOCK = threading.Lock()

SLOW_QUERY_MS = float(os.environ.get("OBSERVABILITY_SLOW_QUERY_MS", "200"))
LOG_ENABLED = os.environ.get("OBSERVABILITY_LOG_ENABLED", "1").strip().lower() not in ("0", "false", "no")

_METRICAS_GLOBAIS: Dict[str, Any] = {
    "requisicoes_total": 0,
    "auth_login_sucesso": 0,
    "auth_login_falha": 0,
    "auth_rate_limit": 0,
    "sessao_renovada": 0,
    "sessao_expirada": 0,
    "sessao_revogada": 0,
    "banco_erros": 0,
    "sql_total_queries": 0,
    "sql_slow_queries": 0,
    "rotas": {},
    "ultimos_eventos": deque(maxlen=100),
}


def _sanitizar_sql(sql: str) -> str:
    """Resume o comando SQL sem parâmetros/valores para diagnóstico seguro."""
    if not sql:
        return ""
    compacto = " ".join(str(sql).split())
    return compacto[:140]


def iniciar_contexto_requisicao(rota: str, metodo: str = "GET") -> Dict[str, Any]:
    ctx = {
        "rota": rota,
        "metodo": metodo,
        "inicio": time.perf_counter(),
        "sql_count": 0,
        "sql_ms": 0.0,
        "slow_queries": [],
        "auth_ms": None,
        "db_connect_ms": 0.0,
    }
    _TLS.ctx = ctx
    return ctx


def obter_contexto_requisicao() -> Optional[Dict[str, Any]]:
    return getattr(_TLS, "ctx", None)


def registrar_sql(duracao_ms: float, sql: str = ""):
    ctx = obter_contexto_requisicao()
    if ctx is not None:
        ctx["sql_count"] += 1
        ctx["sql_ms"] += duracao_ms
        if duracao_ms >= SLOW_QUERY_MS:
            ctx["slow_queries"].append({
                "ms": round(duracao_ms, 2),
                "sql": _sanitizar_sql(sql),
            })

    with _LOCK:
        _METRICAS_GLOBAIS["sql_total_queries"] += 1
        if duracao_ms >= SLOW_QUERY_MS:
            _METRICAS_GLOBAIS["sql_slow_queries"] += 1


def registrar_conexao_banco(duracao_ms: float):
    ctx = obter_contexto_requisicao()
    if ctx is not None:
        ctx["db_connect_ms"] += duracao_ms


def registrar_evento(tipo: str, detalhes: Optional[Dict[str, Any]] = None):
    """Registra contadores seguros de eventos de auth, sessão e banco."""
    with _LOCK:
        if tipo in _METRICAS_GLOBAIS and isinstance(_METRICAS_GLOBAIS[tipo], int):
            _METRICAS_GLOBAIS[tipo] += 1
        _METRICAS_GLOBAIS["ultimos_eventos"].append({
            "ts": round(time.time(), 3),
            "tipo": tipo,
            "detalhes": detalhes or {},
        })


def finalizar_contexto_requisicao(status_code: int = 200) -> Dict[str, Any]:
    ctx = obter_contexto_requisicao()
    _TLS.ctx = None
    if not ctx:
        return {}

    total_ms = (time.perf_counter() - ctx["inicio"]) * 1000.0
    resumo = {
        "rota": ctx["rota"],
        "metodo": ctx["metodo"],
        "status": status_code,
        "total_ms": round(total_ms, 2),
        "sql_count": ctx["sql_count"],
        "sql_ms": round(ctx["sql_ms"], 2),
        "db_connect_ms": round(ctx["db_connect_ms"], 2),
        "slow_queries_count": len(ctx["slow_queries"]),
    }
    if ctx.get("auth_ms") is not None:
        resumo["auth_ms"] = round(ctx["auth_ms"], 2)

    chave_rota = f"{ctx['metodo']} {ctx['rota']}"
    with _LOCK:
        _METRICAS_GLOBAIS["requisicoes_total"] += 1
        r = _METRICAS_GLOBAIS["rotas"].setdefault(chave_rota, {
            "count": 0,
            "total_ms": 0.0,
            "max_ms": 0.0,
            "sql_total": 0,
        })
        r["count"] += 1
        r["total_ms"] += total_ms
        if total_ms > r["max_ms"]:
            r["max_ms"] = total_ms
        r["sql_total"] += ctx["sql_count"]

    if LOG_ENABLED and (total_ms >= 300.0 or status_code >= 500 or ctx["slow_queries"]):
        try:
            print(f"[RH20-PERF] {json.dumps(resumo, ensure_ascii=False)}", file=sys.stderr)
        except Exception:
            pass

    return resumo


def formatar_server_timing(resumo: Dict[str, Any]) -> str:
    """Gera valor para o cabeçalho HTTP Server-Timing (sem dados sensíveis)."""
    if not resumo:
        return ""
    partes = [
        f"total;dur={resumo.get('total_ms', 0)}",
        f"db;dur={resumo.get('sql_ms', 0)};desc=\"queries={resumo.get('sql_count', 0)}\"",
    ]
    if resumo.get("auth_ms") is not None:
        partes.append(f"auth;dur={resumo['auth_ms']}")
    return ", ".join(partes)


@contextmanager
def medir_operacao(campo_ctx: str = None):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        if campo_ctx:
            ctx = obter_contexto_requisicao()
            if ctx is not None:
                ctx[campo_ctx] = ms


def obter_metricas_snapshot() -> Dict[str, Any]:
    """Retorna snapshot seguro das métricas de desempenho e sessões."""
    with _LOCK:
        rotas_ordenadas = []
        for rota, dados in _METRICAS_GLOBAIS["rotas"].items():
            cnt = max(1, dados["count"])
            rotas_ordenadas.append({
                "rota": rota,
                "requisicoes": dados["count"],
                "media_ms": round(dados["total_ms"] / cnt, 2),
                "max_ms": round(dados["max_ms"], 2),
                "media_queries": round(dados["sql_total"] / cnt, 2),
            })
        rotas_ordenadas.sort(key=lambda x: x["media_ms"], reverse=True)

        return {
            "requisicoes_total": _METRICAS_GLOBAIS["requisicoes_total"],
            "auth_login_sucesso": _METRICAS_GLOBAIS["auth_login_sucesso"],
            "auth_login_falha": _METRICAS_GLOBAIS["auth_login_falha"],
            "auth_rate_limit": _METRICAS_GLOBAIS["auth_rate_limit"],
            "sessao_renovada": _METRICAS_GLOBAIS["sessao_renovada"],
            "sessao_expirada": _METRICAS_GLOBAIS["sessao_expirada"],
            "sessao_revogada": _METRICAS_GLOBAIS["sessao_revogada"],
            "banco_erros": _METRICAS_GLOBAIS["banco_erros"],
            "sql_total_queries": _METRICAS_GLOBAIS["sql_total_queries"],
            "sql_slow_queries": _METRICAS_GLOBAIS["sql_slow_queries"],
            "rotas_mais_lentas": rotas_ordenadas[:15],
        }


def resetar_metricas():
    with _LOCK:
        for k, v in _METRICAS_GLOBAIS.items():
            if isinstance(v, int):
                _METRICAS_GLOBAIS[k] = 0
            elif isinstance(v, dict):
                v.clear()
            elif isinstance(v, deque):
                v.clear()
