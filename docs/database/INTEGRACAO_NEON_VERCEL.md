# Integração Definitiva do RH2.0 com Neon PostgreSQL e Vercel

**Documento:** Guia de Arquitetura, Governança, Implantação e Homologação  
**Projeto:** RH2.0 (Sistema Integrado de Departamento Pessoal & Folha de Pagamento)  
**Repositório:** [https://github.com/vikleve/RH2.0](https://github.com/vikleve/RH2.0)  
**Ambiente de Nuvem:** Vercel (Serverless Functions Python + Frontend Estático)  
**Banco de Dados Operacional:** PostgreSQL gerenciado no Neon ([neon.tech](https://neon.tech))  
**Status Geral:** **IMPLEMENTADO** (Código e Configurações) | **TESTADO** (89 testes automatizados com sucesso) | **AGUARDANDO HOMOLOGAÇÃO** (Pendente configuração do segredo na Vercel pelo responsável)

---

## 1. Causa Raiz do Erro

### 1.1 Diagnóstico do Erro
A aplicação em produção na Vercel vinha apresentando o erro:
```text
HTTP 503 Service Unavailable
{
  "sucesso": false,
  "codigo": "BANCO_INDISPONIVEL",
  "mensagem": "DATABASE_URL nao configurada: o PostgreSQL e obrigatorio em producao. Cadastre a variavel como segredo no ambiente Production da Vercel."
}
```

### 1.2 Mecanismo Causal
1. Conforme a regra de governança e segurança (ADR-001 e `backend/database.py`), o RH2.0 detecta automaticamente o ambiente de execução através das variáveis `VERCEL`, `VERCEL_ENV`, `APP_ENV=production` ou `NODE_ENV=production`.
2. Em desenvolvimento local e testes sintéticos, o sistema opera em modo isolado com SQLite.
3. No entanto, em produção (Vercel), o sistema **proíbe estritamente** o fallback silencioso para SQLite, pois o sistema de arquivos serverless da Vercel é efêmero e não persiste entre invocações de funções lambda.
4. Como a variável `DATABASE_URL` não havia sido cadastrada como segredo no painel da Vercel para o ambiente **Production**, o backend disparou a exceção fail-fast `DatabaseConfigError`, protegendo a integridade do sistema contra perda de dados.

---

## 2. Arquitetura Homologada

```
+-----------------------------------------------------------------------------------+
|                                  VERCEL                                           |
|                                                                                   |
|   +-----------------------+                    +------------------------------+   |
|   |   Frontend Estático   |  HTTP REST (JSON)  |  Backend Serverless (Python) |   |
|   |   HTML5 / CSS3 / JS   | -----------------> |  api/index.py (routes)       |   |
|   |   (Sem localStorage)  |  Cookie HttpOnly   |  backend/database.py         |   |
|   +-----------------------+                    +---------------+--------------+   |
+----------------------------------------------------------------|------------------+
                                                                 |
                                                  TLS / SSL v1.3 | libpq / psycopg2
                                                  Porta 5432     | Pooling mode
                                                                 v
+-----------------------------------------------------------------------------------+
|                              NEON POSTGRESQL                                      |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   |  Neon PgBouncer Connection Pooler: ep-*-pooler.region.aws.neon.tech       |   |
|   +---------------------------------------------------------------------------+   |
|                                        |                                          |
|                                        v                                          |
|   +---------------------------------------------------------------------------+   |
|   |  Compute Endpoint Primário (Autoscaling / Auto-suspend)                   |   |
|   |  Banco de Dados: neondb                                                   |   |
|   |  Tabelas: colaboradores, dependentes, historico_alteracoes, usuarios,     |   |
|   |           sessoes, folha_parametros, folhas_pagamento, folha_itens,       |   |
|   |           folha_historico, auditoria_autenticacao                         |   |
|   +---------------------------------------------------------------------------+   |
+-----------------------------------------------------------------------------------+
```

- **Frontend:** Servido via CDN global da Vercel (arquivos estáticos em `frontend/`).
- **Backend:** Funções serverless Python (`api/*.py` e `backend/`).
- **Banco de Dados:** PostgreSQL hospedado no Neon, acessado via **endpoint com pooler** (`-pooler`).
- **Comunicação:** Conexão criptografada ponta a ponta (`sslmode=require`).
- **Segurança de Credenciais:** `DATABASE_URL` cadastrada exclusivamente como segredo de ambiente na Vercel, nunca no repositório.

---

## 3. Auditoria do Neon e Diretrizes de Conexão

### 3.1 Identificação do Projeto Neon Existente
1. Acesse o console do Neon: [https://console.neon.tech](https://console.neon.tech).
2. Selecione o projeto existente do RH2.0.
3. No menu **Dashboard**, localize o card **Connection Details**:
   - **Branch:** `main` (branch primária).
   - **Database:** `neondb` (ou o banco corporativo existente).
   - **Role / User:** `neondb_owner` (ou usuário administrador existente).
   - **Pooled connection:** Marque a opção **Connection pooling** (essencial para ambientes serverless Vercel).

### 3.2 Formato da Connection String
A connection string pooled do Neon segue o padrão:
```text
postgresql://[USER]:[SENHA]@[ENDPOINT]-pooler.[REGIAO].aws.neon.tech/[DATABASE]?sslmode=require
```

> [!IMPORTANT]
> **Por que usar o endpoint `-pooler`?**  
> Em plataformas serverless como a Vercel, dezenas de instâncias lambda podem ser criadas e destruídas simultaneamente. O endpoint pooled do Neon ativa o PgBouncer gerenciado, evitando esgotamento de conexões nativas do PostgreSQL e garantindo reuso eficiente de conexões.

### 3.3 Preservação e Verificação de Dados Existentes
Antes de qualquer deploy ou operação:
1. No console do Neon, acesse a aba **SQL Editor**.
2. Execute a consulta para inspecionar tabelas e dados existentes:
   ```sql
   SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
   SELECT COUNT(*) AS total_colaboradores FROM colaboradores;
   SELECT COUNT(*) AS total_usuarios FROM usuarios;
   ```
3. **Regra de Ouro:** É expressamente proibido executar `DROP TABLE`, `DROP DATABASE` ou `TRUNCATE`. As rotinas do RH2.0 operam exclusivamente com `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` e `CREATE INDEX IF NOT EXISTS`.

---

## 4. Configuração Passo a Passo na Vercel

### 4.1 Cadastro das Variáveis de Ambiente
1. Acesse o painel da Vercel: [https://vercel.com](https://vercel.com).
2. Selecione o projeto do **RH2.0**.
3. Navegue até **Settings** > **Environment Variables**.
4. Adicione as variáveis obrigatórias:

| Nome da Variável | Valor Recomendado | Ambientes Selecionados | Descrição |
|---|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@ep-*-pooler.*.aws.neon.tech/neondb?sslmode=require` | **Production**, Preview, Development | Connection string com pooler do Neon |
| `ADMIN_INITIAL_PASSWORD` | Senha forte (mín. 12 caracteres, letras, números e símbolos) | **Production**, Preview, Development | Senha inicial para criação da conta `admin.dp@empresa.com.br` |
| `DB_CONNECT_TIMEOUT` | `15` | **Production**, Preview, Development | Timeout em segundos para cobrir cold start do Neon compute |

> [!CAUTION]
> Marque a opção **Sensitive Environment Variable** (segredo protegido) para que o valor da `DATABASE_URL` não seja visível para membros não administradores e nunca apareça em logs de build.

### 4.2 Execução de Novo Deploy
Após cadastrar as variáveis:
1. No menu superior da Vercel, acesse a aba **Deployments**.
2. No deployment mais recente de Production, clique no menu de três pontos (`...`) e selecione **Redeploy**.
3. Desmarque "Use existing Build Cache" para garantir um deploy limpo.
4. Clique em **Redeploy**.

---

## 5. Auditoria de Código e Melhorias Implementadas

Durante a auditoria técnica de conformidade, foram identificadas e implementadas as seguintes melhorias:

1. **Reconhecimento Nativo do Neon (`backend/database.py`):**
   - Suporte transparente para `DATABASE_URL`, `NEON_DATABASE_URL`, `POSTGRES_URL` e `POSTGRES_PRISMA_URL`.
   - Ajuste do `connect_timeout` padrão para **15 segundos**, prevenindo timeouts durante o auto-wake de branches suspensas do Neon.
   - Enriquecimento do diagnóstico público `/api/health` para reportar se o banco ativo é Neon e se o pooling está ativo (`{"banco": "postgresql", "provedor": "neon", "pooled": true, "conectado": true}`), sem nunca expor senhas ou hostnames.

2. **Garantia de Fechamento de Conexões:**
   - Inspeção de todos os métodos em `backend/database.py`, `backend/service.py`, `backend/auth.py`, `backend/folha_service.py` e `backend/audit.py`.
   - Todas as conexões abertas (`conn = get_connection()`) realizam `conn.commit()` ou `conn.rollback()` e são finalizadas com `conn.close()`. Nenhuma conexão é mantida órfã no pooler.

3. **Padronização de Respostas de Erro HTTP 503:**
   - Atualização de `api/colaboradores.py` e `backend/server.py` para converter quaisquer exceções de banco via `erro_http(e)`.
   - Erros de indisponibilidade retornam HTTP 503 com código `BANCO_INDISPONIVEL` e supressão total de credenciais e hostnames.

4. **Captura de IP em Auditoria Serverless:**
   - Atualização de `api/auth/login.py` e `api/auth/logout.py` para extrair o cabeçalho `X-Forwarded-For` da Vercel, gravando o IP real do cliente na tabela `auditoria_autenticacao`.

5. **Evolução Segura e Idempotente do Schema:**
   - Inclusão em `init_db()` de validações não-destrutivas (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) para garantir que as colunas complementares da SPEC-03 (`empresa_id`, `filial_id`, etc.) existam sem requerer intervenção manual no banco.

---

## 6. Testes Automatizados e Evidências

A conformidade do sistema foi validada através de suíte de testes automatizados headless executada em Python:

```text
================================================================================
 SUÍTE DE TESTES AUTOMATIZADOS — PORTAL DP & RH
 Módulo 1 (Colaboradores), Segurança (Autenticação) & Módulo Folha de Pagamento
 Modo: Execução 100% em código (headless / sem abrir navegador)
================================================================================
Ran 89 tests in 46.85s

OK (Sucessos: 89, Falhas: 0, Erros: 0)
```

### 6.1 Detalhamento dos Testes de Persistência e Neon
- `test_producao_sem_database_url_falha_explicitamente`: Valida que o backend falha de imediato com HTTP 503 e código `BANCO_INDISPONIVEL` caso a variável falte, sem recorrer a SQLite.
- `test_neon_database_url_reconhecida_com_provedor_e_pooling`: Valida que o endpoint pooled do Neon é identificado e o provedor é setado como `"neon"`.
- `test_neon_falha_de_conexao_nao_vaza_credenciais_nem_host`: Valida que falhas de rede no Neon jamais expõem a senha ou o endpoint nos logs ou respostas.
- `test_dsn_recebe_sslmode_e_timeout`: Garante que `sslmode=require` e `connect_timeout` são injetados em qualquer URL de nuvem.
- `test_status_banco_identifica_neon_e_pooling`: Garante o correto funcionamento do `/api/health`.

---

## 7. Roteiro de Testes de Aceitação em Produção (Checklist)

Após o responsável configurar a `DATABASE_URL` na Vercel e realizar o redeploy:

1. **Teste de Diagnóstico de Conexão:**
   - Acesse via navegador ou curl: `https://<seu-app>.vercel.app/api/health`
   - Resposta esperada (HTTP 200):
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

2. **Teste de Autenticação Inicial:**
   - Acesse a aplicação no navegador: `https://<seu-app>.vercel.app`
   - Efetue login com `admin.dp@empresa.com.br` e a senha definida em `ADMIN_INITIAL_PASSWORD`.
   - Confirme acesso ao painel de colaboradores.

3. **Teste de Persistência Real (CRUD):**
   - Cadastre um novo colaborador com dados válidos.
   - Atualize um dado cadastral (ex: cargo ou salário).
   - Efetue logout e feche o navegador.
   - Abra um navegador diferente (ou aba anônima), realize login e confirme que o colaborador e seu histórico estão preservados.

4. **Teste de Persistência Após Novo Deploy:**
   - Realize um novo redeploy na Vercel.
   - Acesse o sistema e verifique que todos os dados cadastrados anteriormente permanecem intactos.

---

## 8. Governança e Matriz de Critérios de Aceite

| Critério de Aceite | Requisito | Estado | Evidência / Observação |
|---|---|---|---|---|
| **CA-NEON-01** | Proibição de SQLite em produção | **TESTADO** | Teste unitário e verificação em código garantem recusa imediata de fallback local. |
| **CA-NEON-02** | Suporte a endpoint pooled do Neon | **TESTADO** | Suporte a pooler testado com preservação de DSN e flag `pooled: true`. |
| **CA-NEON-03** | Conexão segura com SSL obrigatório | **TESTADO** | `sslmode=require` forçado em todas as conexões remotas. |
| **CA-NEON-04** | Proteção contra vazamento de credenciais | **TESTADO** | Teste de falha de conexão valida supressão de senhas e hostnames em exceções. |
| **CA-NEON-05** | Preservação de dados e DDL não-destrutivo | **IMPLEMENTADO** | Uso exclusivo de `IF NOT EXISTS` e sem comandos `DROP`/`TRUNCATE`. |
| **CA-NEON-06** | Encerramento correto de conexões | **TESTADO** | Todas as rotas fecham suas conexões no término ou em falha. |
| **CA-NEON-07** | Configuração do segredo na Vercel | **AGUARDANDO HOMOLOGAÇÃO** | Depende da inserção da string no painel da Vercel pelo responsável. |
| **CA-NEON-08** | Validação ponta a ponta publicada | **AGUARDANDO HOMOLOGAÇÃO** | Aguarda redeploy na Vercel com a variável ativa para teste final. |

---

## 9. Próximos Passos para o Responsável

1. Obter a connection string do banco Neon com **connection pooling habilitado**.
2. Cadastrar as variáveis `DATABASE_URL` e `ADMIN_INITIAL_PASSWORD` na Vercel (Ambiente **Production**).
3. Executar o **Redeploy** na Vercel.
4. Validar o endpoint `https://<app>.vercel.app/api/health`.
5. Confirmar a homologação final do sistema.
