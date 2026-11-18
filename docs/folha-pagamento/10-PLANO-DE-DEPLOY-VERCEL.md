# 10 — Plano de Deploy na Vercel e Integração com Neon PostgreSQL

**Projeto:** RH2.0 — Portal de Departamento Pessoal & Folha de Pagamento  
**Data:** 18/11/2026

---

## 1. Viabilidade e Arquitetura de Hospedagem na Vercel (Seção 12.1)

A auditoria técnica confirmou que o projeto **RH2.0 é 100% compatível com execução integral na Vercel**:
- **Frontend Estático (`frontend/`):** Servido diretamente pela CDN global da Vercel (`index.html`, `styles.css`, `app.js`, `assets/*`), sem necessidade de etapa complexa de build JS.
- **Backend Serverless (`api/` + `backend/`):** Executado pelo runtime Python oficial da Vercel (`@vercel/python`), instalando automaticamente as dependências enxutas de `requirements.txt` (`psycopg2-binary>=2.9.0` e `python-dotenv>=1.0.0`).
- **Roteamento (`vercel.json`):**
  - Requisições para `/api/*` são encaminhadas para `api/index.py` (que expõe `handler(ApiColaboradorHandler)` de `backend/server.py`).
  - Requisições para `/(.*)` servem os arquivos estáticos de `/frontend/$1`.

---

## 2. Configuração de Variáveis de Ambiente na Vercel (Seção 5.2 e 12.1)

No painel do projeto na Vercel (**Settings → Environment Variables**), devem ser cadastradas as seguintes variáveis (com a opção **Sensitive** marcada para segredos):

| Variável | Ambiente `Production` | Ambiente `Preview` | Descrição |
|---|---|---|---|
| `DATABASE_URL` | Connection string **pooled** (`-pooler`) da branch `main` do Neon (`?sslmode=require`) | Connection string **pooled** (`-pooler`) de branch isolada (`preview`/`dev`) do Neon | Fonte de verdade PostgreSQL. **Nunca expor ao navegador.** |
| `ADMIN_INITIAL_PASSWORD` | Senha forte exclusiva de produção (mín. 12 caracteres) | Senha forte de homologação | Provisiona com segurança o usuário inicial `admin.dp@empresa.com.br`. |
| `GUEST_INITIAL_PASSWORD` | Opcional (senha forte) | Opcional | Provisiona o usuário `visitante@empresa.com.br` (`analista_rh`). |
| `DB_CONNECT_TIMEOUT` | `15` | `15` | Garante tempo hábil para wake-up (cold start) do compute do Neon. |

---

## 3. Garantias de Persistência Após o Deploy (Seção 12.2)

1. **Independência da Instância Serverless:** Nenhum dado operacional (colaboradores, folhas, itens, parâmetros ou sessões) é salvo em memória ou em `/tmp`.
2. **Sessões Persistidas no Banco (`sessoes`):** O token de sessão (`session_token` via Cookie `HttpOnly; SameSite=Lax; Secure` e header `Authorization: Bearer`) é validado diretamente na tabela `sessoes` do Neon PostgreSQL. Assim, mesmo que a próxima requisição HTTP caia em uma nova instância serverless recém-inicializada na Vercel, a sessão do usuário permanece válida e contínua.
3. **Auditoria e Rate Limit via Banco (`auditoria_autenticacao`):** Os eventos de login e falhas de autenticação ficam gravados no Neon, sobrevivendo a reinicializações e novos deploys.
4. **Proteção Fail-Fast contra Perda Silenciosa:** Se por erro operacional alguém remover `DATABASE_URL` na Vercel, o backend recusa qualquer gravação e responde HTTP 503 (`BANCO_INDISPONIVEL`), impedindo que o usuário acredite que salvou dados em um SQLite efêmero.

---

## 4. Checklist de Verificação Pós-Deploy (Quando Autorizado na Fase G)

1. **Verificação de Saúde e Conexão (`GET /api/health`):**
   - Acessar `https://<dominio-do-projeto>.vercel.app/api/health`.
   - Confirmar retorno HTTP 200:
     ```json
     {
       "sucesso": true,
       "banco": "postgresql",
       "conectado": true,
       "producao": true,
       "provedor": "neon",
       "pooled": true
     }
     ```
2. **Verificação de Segurança de Credenciais:**
   - Inspecionar o código-fonte da página e a aba Network do DevTools para confirmar que nenhuma credencial do PostgreSQL/Neon trafega para o cliente.
3. **Verificação de Persistência Entre Sessões e Após Redeploy:**
   - Realizar login, cadastrar colaborador e folha, fechar a folha, fazer logout, acionar **Redeploy** na Vercel, abrir nova sessão anônima e confirmar que todos os dados permanecem íntegros.
