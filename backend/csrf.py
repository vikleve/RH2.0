"""
Módulo de Proteção CSRF e Validação de Origem — RH2.0
Atende a RF-LOGIN-005 e AC-13:
Valida cabeçalhos Origin e Referer em requisições de mudança de estado (POST, PUT, PATCH, DELETE),
impedindo ataques de Cross-Site Request Forgery em autenticação baseada em cookies.
Compatível com proxies reversos e ambientes serverless (Vercel: Host, X-Forwarded-Host).
"""
import os
import urllib.parse

# Métodos HTTP seguros que não alteram estado
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def _get_header_ci(headers: dict, nome: str) -> str:
    """Lê cabeçalho HTTP de forma case-insensitive."""
    alvo = nome.lower()
    for k, v in (headers or {}).items():
        if str(k).lower() == alvo and v:
            return str(v).strip()
    return ""


def _extrair_hosts_esperados(headers: dict, host_esperado: str = None) -> set[str]:
    """
    Coleta todos os hosts legítimos da requisição considerando proxy reverso (Vercel/Cloudflare).
    Retorna conjunto normalizado (minúsculo, com e sem porta padrão).
    """
    candidatos = set()
    for bruto in (
        _get_header_ci(headers, "Host"),
        _get_header_ci(headers, "X-Forwarded-Host"),
        _get_header_ci(headers, "X-Vercel-Deployment-Url"),
        host_esperado or "",
    ):
        if not bruto:
            continue
        # X-Forwarded-Host pode conter lista separada por vírgula
        for parte in str(bruto).split(","):
            h = parte.strip().lower()
            if not h:
                continue
            # Remove esquema se vier como URL completa
            if "://" in h:
                h = urllib.parse.urlparse(h).netloc.lower()
            candidatos.add(h)
            if ":" in h:
                host_sem_porta, porta = h.rsplit(":", 1)
                if porta in ("80", "443"):
                    candidatos.add(host_sem_porta)
    return candidatos


class CsrfProtector:
    def __init__(self, origens_permitidas: list[str] = None):
        config_env = os.environ.get("ALLOWED_ORIGINS", "")
        if config_env:
            self.origens_permitidas = {o.strip().rstrip("/").lower() for o in config_env.split(",") if o.strip()}
        elif origens_permitidas:
            self.origens_permitidas = {o.strip().rstrip("/").lower() for o in origens_permitidas if o.strip()}
        else:
            self.origens_permitidas = set()

    def adicionar_origem(self, origem: str):
        if origem:
            self.origens_permitidas.add(origem.strip().rstrip("/").lower())

    def validar_requisicao(self, metodo: str, headers: dict, host_esperado: str = None) -> tuple[bool, str]:
        """
        Valida se a requisição mutável possui origem confiável.
        Retorna (valido: bool, motivo_erro: str).
        """
        metodo = (metodo or "").upper()
        if metodo in METODOS_SEGUROS:
            return True, ""

        origem = _get_header_ci(headers, "Origin")
        referer = _get_header_ci(headers, "Referer")
        sec_fetch_site = _get_header_ci(headers, "Sec-Fetch-Site").lower()
        hosts_esperados = _extrair_hosts_esperados(headers, host_esperado)

        # Bloqueio imediato se navegador indicar explicitamente origem cross-site não autorizada
        if sec_fetch_site == "cross-site":
            if origem and origem.rstrip("/").lower() in self.origens_permitidas:
                return True, ""
            return False, "Requisição cross-site bloqueada por Sec-Fetch-Site."

        # 1. Se informou cabeçalho Origin
        if origem:
            origem_normalizada = origem.rstrip("/")
            if origem_normalizada.lower() in self.origens_permitidas:
                return True, ""

            parsed_origem = urllib.parse.urlparse(origem_normalizada)
            origem_netloc = (parsed_origem.netloc or "").lower()
            origem_host = (parsed_origem.hostname or "").lower()

            # Compara com Host / X-Forwarded-Host / X-Vercel-Deployment-Url
            if origem_netloc and (origem_netloc in hosts_esperados or origem_host in hosts_esperados):
                return True, ""

            # Em ambiente Vercel com Sec-Fetch-Site=same-origin confirmado pelo navegador
            if sec_fetch_site == "same-origin" and parsed_origem.scheme in ("http", "https"):
                return True, ""

            # Permite origens locais padrão durante desenvolvimento e testes
            if origem_host in ("127.0.0.1", "localhost", "0.0.0.0"):
                if not hosts_esperados or any(h.split(":")[0] in ("127.0.0.1", "localhost", "0.0.0.0") for h in hosts_esperados):
                    return True, ""

            return False, f"Origem da requisição ('{origem}') não autorizada pela política CSRF/Origin."

        # 2. Se não informou Origin mas informou Referer
        if referer:
            parsed_ref = urllib.parse.urlparse(referer)
            ref_netloc = (parsed_ref.netloc or "").lower()
            ref_host = (parsed_ref.hostname or "").lower()
            if ref_netloc and (ref_netloc in hosts_esperados or ref_host in hosts_esperados):
                return True, ""
            if sec_fetch_site == "same-origin":
                return True, ""
            if ref_host in ("127.0.0.1", "localhost"):
                return True, ""
            return False, f"Referer da requisição ('{referer}') não autorizado pela política CSRF/Origin."

        # 3. Requisições sem Origin e sem Referer (clientes nativos, curl, testes de API)
        return True, ""


_global_csrf = CsrfProtector()


def get_csrf_protector() -> CsrfProtector:
    return _global_csrf
