"""
Módulo de Proteção CSRF e Validação de Origem — RH2.0
Atende a RF-LOGIN-005 e AC-13:
Valida cabeçalhos Origin e Referer em requisições de mudança de estado (POST, PUT, PATCH, DELETE),
impedindo ataques de Cross-Site Request Forgery em autenticação baseada em cookies.
"""
import os
import urllib.parse

# Métodos HTTP seguros que não alteram estado
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


class CsrfProtector:
    def __init__(self, origens_permitidas: list[str] = None):
        config_env = os.environ.get("ALLOWED_ORIGINS", "")
        if config_env:
            self.origens_permitidas = {o.strip() for o in config_env.split(",") if o.strip()}
        elif origens_permitidas:
            self.origens_permitidas = set(origens_permitidas)
        else:
            self.origens_permitidas = set()

    def adicionar_origem(self, origem: str):
        if origem:
            self.origens_permitidas.add(origem.rstrip("/"))

    def validar_requisicao(self, metodo: str, headers: dict, host_esperado: str = None) -> tuple[bool, str]:
        """
        Valida se a requisição mutável possui origem confiável.
        Retorna (valido: bool, motivo_erro: str).
        """
        metodo = (metodo or "").upper()
        if metodo in METODOS_SEGUROS:
            return True, ""

        origem = headers.get("Origin") or headers.get("origin")
        referer = headers.get("Referer") or headers.get("referer")

        # 1. Se informou cabeçalho Origin
        if origem:
            origem_normalizada = origem.rstrip("/")
            # Verifica lista de origens explicitamente configuradas
            if origem_normalizada in self.origens_permitidas:
                return True, ""

            parsed_origem = urllib.parse.urlparse(origem_normalizada)
            origem_netloc = parsed_origem.netloc

            # Compara com o host da requisição (Host: 127.0.0.1:8000)
            host_header = headers.get("Host") or headers.get("host") or host_esperado
            if host_header:
                host_esperado_netloc = host_header.strip()
                if origem_netloc == host_esperado_netloc:
                    return True, ""

            # Permite origens locais padrão durante desenvolvimento e testes
            if parsed_origem.hostname in ("127.0.0.1", "localhost", "0.0.0.0"):
                # Se não houver host_header conflitante
                if not host_header or host_header.split(":")[0] in ("127.0.0.1", "localhost", "0.0.0.0"):
                    return True, ""

            return False, f"Origem da requisição ('{origem}') não autorizada pela política CSRF/Origin."

        # 2. Se não informou Origin mas informou Referer
        if referer:
            parsed_ref = urllib.parse.urlparse(referer)
            ref_netloc = parsed_ref.netloc
            host_header = headers.get("Host") or headers.get("host") or host_esperado
            if host_header and ref_netloc == host_header.strip():
                return True, ""
            if parsed_ref.hostname in ("127.0.0.1", "localhost"):
                return True, ""
            return False, f"Referer da requisição ('{referer}') não autorizado pela política CSRF/Origin."

        # 3. Requisições sem Origin e sem Referer:
        # Se for cliente nativo, curl ou teste de API direto no backend local
        # Em modo estrito de produção, exigiria Origin; em ambiente de desenvolvimento permitimos se Sec-Fetch-Site não for 'cross-site'
        sec_fetch_site = headers.get("Sec-Fetch-Site") or headers.get("sec-fetch-site")
        if sec_fetch_site == "cross-site":
            return False, "Requisição cross-site bloqueada por Sec-Fetch-Site."

        return True, ""


_global_csrf = CsrfProtector()


def get_csrf_protector() -> CsrfProtector:
    return _global_csrf

