# INC-LOGIN-001 — Falha de login (tela de login sem reação e sem mensagem)

Estado: **IMPLEMENTADO e TESTADO localmente** · **AGUARDANDO HOMOLOGAÇÃO** (falta validar na Vercel após o deploy).

## 1. Sintoma
Credenciais corretas → "Autenticando..." → continua na tela de login, sem mensagem.

## 2. Causa raiz (reproduzida no navegador com o backend real)
O merge `c1082ec` ("sincronizar main com implementações da plataforma e SPEC-PATCH-FOLHA-001") quebrou o frontend de duas formas:

1. **`frontend/app.js` com erro de sintaxe** — faltava `},` ao fim de `calcularValorAutomaticoEvento` (`Unexpected token '{'` em `montarOpcoesEventos`). Com isso, **nenhum** trecho do script executa.
2. **`frontend/index.html` perdeu 410 linhas** — os modais de cadastro/detalhes de colaboradores (`modal-form`, `modal-detalhes`) e as telas Integrações/Auditoria/Multiempresa (≈85 IDs). Mesmo com a sintaxe corrigida, `configurarEventos()` fazia `getElementById('btn-fechar-form-modal').addEventListener(...)` em elemento inexistente (`TypeError`), abortando o `DOMContentLoaded` **antes** de `AuthManager.inicializar()`: o formulário de login nunca recebia o handler.

Resultado: nenhuma chamada de API era feita; o submit não tinha tratamento e nenhuma mensagem era exibida.

Evidências: `PAGEERR Unexpected token '{'` → (após corrigir) `TypeError ... addEventListener at configurarEventos (app.js:1023)` → rede vazia (nenhum `/api/*`). Bisect: `9534838`…`089f965` OK; `c1082ec` em diante quebrados.

O backend (`api/auth/*`, `backend/auth.py`) **não** apresentou defeito: login 200, `/me` 200 com cookie e com Bearer, sessão persistida no banco.

## 3. Correção
- `frontend/app.js`: adicionado o `},` ausente; 401 em Folha agora exibe "Sessão expirada. Faça login novamente." (antes voltava ao login em silêncio).
- `frontend/index.html`: restaurado o bloco removido (linhas 1349–1758 da versão `4236101`), sem alterar o restante.
- Nenhuma alteração em autenticação, rate limiting, auditoria, perfis ou multiempresa.

## 4. Prevenção
- `tests/test_frontend_integridade.py` (roda no `unittest`): sintaxe do `app.js`, HTML balanceado/sem IDs duplicados, todo `getElementById('x')` do JS existe no HTML. Os 3 primeiros **falham** na `main` anterior e passam agora.
- `tests/e2e/run_login_e2e.sh`: E2E de login com backend real (Playwright).

## 5. Testes executados
| Verificação | Resultado |
|---|---|
| Suíte Python (`python -m unittest discover -s tests`) | 128/128 OK |
| E2E: login válido, token armazenado, `/me` por cookie e Bearer, carga de colaboradores, recarga, 2 usuários independentes (admin × analista_rh), logout (token antigo → 401), login inválido (mensagem), sessão revogada (volta ao login com mensagem), endpoints sem auth → 401 | 16/16 OK |
| Na Vercel (produção) | **NÃO EXECUTADO** — sem acesso autorizado ao site |

## 6. Pendências e riscos
- Validar na Vercel após o deploy do PR (login real, recarga, logout). Se persistir, verificar `GET /api/health` (banco) e variáveis `DATABASE_URL`/`ADMIN_INITIAL_PASSWORD`.
- Por requisito (RF-LOGIN-003), um novo login **do mesmo usuário** revoga as sessões anteriores dele: dois gestores usando a mesma conta (ex.: `admin.dp`) derrubam-se mutuamente. Recomenda-se uma conta por pessoa. Não foi alterado.
- Tokens de sessão são gravados em texto no banco (a documentação cita hash SHA-256). Fora do escopo deste incidente; recomenda-se tratar à parte.
- Não houve deploy, mudança de variáveis/segredos, redefinição de senhas ou migração.
