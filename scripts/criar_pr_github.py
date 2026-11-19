# -*- coding: utf-8 -*-
"""
Script para criação automatizada de Pull Request no repositório GitHub via REST API.
Uso: python scripts/criar_pr_github.py <TOKEN_GITHUB>
"""
import sys
import json
import urllib.request
import urllib.error

REPO = "vikleve/RH2.0"
BASE = "main"
HEAD = "feat/plataforma-ciclo-trabalhista"
TITLE = "feat: implementacao completa da plataforma de gestao do ciclo trabalhista (modulos 01 a 20)"

BODY = """## Plataforma de Gestão do Ciclo Trabalhista (Módulos 01 a 20) — Versão 1.0 Oficial

### 1. Resumo das Entregas
Implementação integral dos 20 módulos funcionais descritos na especificação oficial do projeto, preservando todos os requisitos (RF-001 a RF-200), regras transversais (RT-01 a RT-13) e regras de negócio (RN-001 a RN-083), com motor de cálculo parametrizado por vigência legal para 2026.

### 2. Módulos Implementados
1. **Gestão de Colaboradores** (RF-001 a RF-010) — Cadastro completo, histórico, dependentes e inativação lógica LGPD.
2. **Admissão & Contratos** (RF-011 a RF-020) — Propostas, checklist de 8 documentos, validação salarial e aprovação com segregação RN-080.
3. **Jornada & Ponto Eletrônico** (RF-021 a RF-030) — Espelho mensal, tolerâncias CLT, solicitações de ajuste e fechamento de período.
4. **Faltas, Atrasos & Ausências** (RF-031 a RF-040) — Desconto de DSR, atestados com CID e impactos automáticos em férias e 13º.
5. **Horas Extras & Adicionais** (RF-041 a RF-050) — HE 50%/100%, adicional noturno com redução ficta (52m30s) e reflexos no DSR.
6. **Férias & Abono Pecuniário** (RF-051 a RF-060) — Períodos aquisitivos/concessivos, abono de até 10 dias e bloqueio pré-repouso RN-019.
7. **Afastamentos Previdenciários** (RF-061 a RF-070) — Cômputo 15 dias empresa / INSS, estabilidade 12 meses pós-B91 e exigência de ASO de retorno.
8. **Benefícios Corporativos** (RF-071 a RF-080) — VT limitado a 6% do salário base ou custo real, plano de saúde e integração com a folha.
9. **Folha de Pagamento Oficial 2026** (RF-081 a RF-095) — Progressividade INSS (teto R$ 8.475,55), IRRF com Deduções vs Simplificado (R$ 607,20), Redução Especial Lei nº 15.270/2025, Salário Família (teto R$ 1.980,38 e cota R$ 67,54) e holerite oficial.
10. **Décimo Terceiro Salário** (RF-096 a RF-105) — 1ª parcela (sem descontos) e 2ª parcela (com encargos e IRRF exclusivo).
11. **Rescisão Contratual CLT** (RF-106 a RF-120) — Aviso prévio proporcional Lei 12.506, multa FGTS 40%/20%, bloqueio de dispensa em estabilidade ativa e prazo de pagamento de até 10 dias corridos (art. 477 § 6º).
12. **Obrigações Legais & Central eSocial** (RF-131 a RF-140) — Geração de lotes XML para eventos S-1000 a S-1299 e mensageria.
13. **SST — Saúde e Segurança do Trabalho** (RF-121 a RF-130) — ASO com CRM e validade, entrega de EPI com bloqueio de CA vencido (RN-039) e emissão imediata de CAT (S-2210).
14. **Gestão Documental** (RF-141 a RF-150) — Armazenamento seguro, minutas contratuais e temporalidade LGPD.
15. **Workflow Operacional & Central de Pendências** (RF-151 a RF-160) — Scanner automático de inconformidades com severidades e princípio de segregação de funções (RN-080).
16. **Segurança & Governança** (RF-161 a RF-170) — Autenticação PBKDF2 com salt, rate limiting, proteção anti-CSRF e controle RBAC.
17. **Gestão Multiempresa** (RF-171 a RF-180) — Multi-tenant por empresa_id, Matriz, Filiais e Centros de Custo.
18. **Integrações Bancárias CNAB 240** (RF-097, RF-178) — Remessa FEBRABAN de crédito de salários em conta corrente/poupança.
19. **BI & Indicadores** (RF-181 a RF-190) — Turnover oficial `((Admitidos+Desligados)/2/Ativos)*100` e taxa de absenteísmo.
20. **Auditoria Geral & Rastreabilidade** (RF-191 a RF-200, RT-01) — Trilha imutável de operações com registro antes/depois.

### 3. Validação e Qualidade
- **112 testes automatizados** executados e aprovados com **100% de sucesso** (`tests/executar_todos_testes.py`).
- **Zero regressões** nos módulos legados.
- Suporte Dual-Mode: SQLite para desenvolvimento ágil e PostgreSQL para produção.
- Checklist de rastreabilidade completo disponível em `docs/CHECKLIST_REQUISITOS_PLATAFORMA.md`."""

def criar_pull_request(token):
    url = f"https://api.github.com/repos/{REPO}/pulls"
    payload = {
        "title": TITLE,
        "head": HEAD,
        "base": BASE,
        "body": BODY
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "RH20-PR-Creator",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            print(f"SUCESSO: Pull Request #{data.get('number')} criado com sucesso!")
            print(f"URL: {data.get('html_url')}")
            return True, data.get('html_url')
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        print(f"ERRO HTTP {e.code}: {err_body}")
        return False, err_body
    except Exception as e:
        print(f"ERRO: {e}")
        return False, str(e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/criar_pr_github.py <TOKEN_GITHUB>")
        sys.exit(1)
    criar_pull_request(sys.argv[1].strip())
