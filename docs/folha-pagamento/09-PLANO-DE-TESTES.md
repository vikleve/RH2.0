# 09 — Plano de Testes de Persistência (DB-01 a DB-15), Cálculos, Segurança e Ponta a Ponta

**Projeto:** RH2.0 — Portal de Departamento Pessoal & Folha de Pagamento  
**Data:** 18/11/2026

---

## 1. Matriz Obrigatória de Testes de Persistência no Neon (Seção 13: DB-01 a DB-15)

Todos os testes abaixo utilizam **dados exclusivamente fictícios** em ambiente controlado. Nenhuma execução é declarada concluída sem evidência real do banco.

| ID | Título | Pré-condições | Dados Utilizados (Fictícios) | Procedimento | Resultado Esperado | Evidência Requerida | Status Atual | Erros Encontrados na Auditoria |
|---|---|---|---|---|---|---|:---:|---|
| **DB-01** | **Conectividade Neon** | `DATABASE_URL` do Neon configurada. | Query `SELECT 1` e inspeção via `GET /api/health`. | Chamar `GET /api/health` e `status_banco()`. | HTTP 200 com `{"banco": "postgresql", "provedor": "neon", "pooled": true, "conectado": true}`. | JSON retornado por `/api/health`. | **Preparado (Aguardando `DATABASE_URL`)** | Sem `DATABASE_URL` no ambiente local atual. |
| **DB-02** | **Criação (INSERT)** | Sessão autenticada + Neon conectado. | Colaborador fictício: `Matrícula: E2E-001`, `Nome: Ana Clara Mendes`, `CPF: 529.982.247-25`, `Salário: R$ 3.500,00`, `1 dependente`. | Enviar `POST /api/colaboradores` pela interface/API e consultar tabela `colaboradores` e `dependentes` no Neon. | HTTP 201; registro gravado em `colaboradores`, `dependentes` e `historico_alteracoes`. | `id` retornado e `SELECT id, matricula, salario_base FROM colaboradores WHERE matricula='E2E-001'`. | **Validado em SQLite / Pendente no Neon** | Falta `try/except/finally` em `ColaboradorService.cadastrar` (GAP-06). |
| **DB-03** | **Leitura (SELECT)** | Registro `E2E-001` criado no `DB-02`. | `id` do colaborador `E2E-001`. | Consultar `GET /api/colaboradores` e `GET /api/colaboradores/<id>`. | Retorna os dados exatos do Neon, incluindo dependentes e histórico. | Payload JSON da resposta HTTP 200. | **Validado em SQLite / Pendente no Neon** | Nenhum em `ColaboradorService`. |
| **DB-04** | **Atualização (UPDATE)** | Registro `E2E-001` existente. | Alterar `salario_base` de `3500.00` para `4000.00` com justificativa `"Promoção anual"`. | Enviar `PUT /api/colaboradores/<id>` e consultar `colaboradores` e `historico_alteracoes`. | `salario_base = 4000.00` no Neon e novo registro em `historico_alteracoes` com valor anterior `R$ 3500.00` e novo `R$ 4000.00`. | Registro em `historico_alteracoes` lido do banco. | **Validado em SQLite / Pendente no Neon** | Nenhum. |
| **DB-05** | **Relacionamentos (FKs e Lançamentos)** | Colaborador `E2E-001` ativo no banco. | Competência `2026-10`, eventos `HE50` (10h) e `FALTA` (1 dia). | Enviar `POST /api/folha` vinculando `colaborador_id` à competência `2026-10`. | Cria cabeçalho em `folhas_pagamento` e itens vinculados em `folha_itens` (`folha_id`) e auditoria em `folha_historico`. | `SELECT COUNT(*) FROM folha_itens WHERE folha_id = <id>`. | **Bloqueado por D-01 no Postgres (Corrigir na M01)** | `Decimal` de `folhas_pagamento` causa `TypeError` no `json.dumps` (Defeito D-01). |
| **DB-06** | **Persistência após Reinicialização** | Dados criados nos testes `DB-02` a `DB-05`. | Colaborador `E2E-001` e Folha `2026-10`. | Encerrar o processo do servidor backend (`server.py`), iniciar novo processo e consultar `GET /api/colaboradores` e `GET /api/folha?competencia=2026-10`. | Todos os cadastros, itens e cálculos permanecem intactos. | Logs de parada/início do servidor e resposta HTTP 200 com os mesmos IDs. | **Validado em SQLite / Pendente no Neon** | Depende de `M01` e `DATABASE_URL`. |
| **DB-07** | **Persistência após Nova Sessão** | Dados persistidos no Neon. | Conta `admin.dp@empresa.com.br`. | Executar `POST /api/auth/logout`, limpar cookies/storage, realizar novo `POST /api/auth/login` e listar colaboradores e folhas. | Token anterior revogado (`revogado=1`); nova sessão recupera todos os dados do Neon. | Resposta `401` com token antigo e `200` com token novo trazendo os registros. | **Validado em SQLite / Pendente no Neon** | Nenhum. |
| **DB-08** | **Persistência após Redeploy** | Aplicação hospedada na Vercel conectada ao Neon. | Registros criados antes do redeploy. | Executar Redeploy na Vercel (sem cache) e consultar `/api/colaboradores` e `/api/folha`. | Zero perda de dados; registros anteriores continuam disponíveis após troca de instância serverless. | IDs e timestamps anteriores ao redeploy retornados pela API em produção. | **Pendente (Fase G — M09)** | Depende de deploy na Vercel com `DATABASE_URL`. |
| **DB-09** | **Integridade e Restrições (Constraints)** | Colaborador `E2E-001` e folha `2026-10` existentes. | Tentativa de CPF duplicado, matrícula duplicada, segunda folha `(colaborador_id, '2026-10')` e exclusão física de colaborador com folha (`ON DELETE RESTRICT`). | Tentar inserir duplicatas via API/banco. | Duplicidades bloqueadas com HTTP 400 (`ValidacaoException` / `FolhaValidacaoException`) e constraint `unq_colab_competencia` / `RESTRICT` no PostgreSQL. | Respostas HTTP 400 e teste de constraint no banco. | **Validado em código / Pendente no Neon** | Nenhum. |
| **DB-10** | **Transações (Atomicidade e Rollback)** | Conexão ativa com o banco. | Falha induzida durante a inserção do 2º item de folha ou dependente. | Simular exceção após o `INSERT` principal antes do `commit()` e verificar o banco. | `conn.rollback()` desfaz toda a operação; nenhum cabeçalho órfão permanece gravado e a conexão é fechada (`conn.close()`). | `SELECT COUNT(*)` confirmando 0 registros parciais. | **Parcial (Corrigir na M03)** | `ColaboradorService` precisa de `try/except/finally` explícito (GAP-06). |
| **DB-11** | **Isolamento Multi-empresa / Perfis** | Usuários de perfis/empresas distintas (`empresa_id`). | Usuário `operador_dp` vs `administrador`. | Tentar executar operação administrativa restrita (alterar parâmetros / reabrir folha) com perfil não autorizado. | Operação bloqueada com HTTP 403 Forbidden. | Resposta HTTP 403. | **Pendente (Implementar na M04)** | Falta validação RBAC por perfil em rotas críticas (GAP-11). |
| **DB-12** | **Fechamento Persistente** | Folha `2026-10` no estado `calculada`. | `POST /api/folha/<id>/fechar`. | Fechar a folha, tentar editá-la (`PUT /api/folha/<id>`) ou excluí-la (`DELETE /api/folha/<id>`). | Estado muda para `'fechada'` no Neon com `fechado_por` e `fechado_em`; tentativas de edição/exclusão retornam HTTP 403 (`FolhaBloqueadaException`). | Registro no banco com `situacao='fechada'` e HTTP 403 na tentativa de edição. | **Validado em SQLite / Pendente no Neon** | Nenhum. |
| **DB-13** | **Histórico de Competências** | Folhas fechadas em `2026-09` e `2026-10`. | Filtro `competencia=2026-09` em nova sessão. | Consultar `GET /api/folha?competencia=2026-09` e `GET /api/folha/<id>` após novo login. | Recupera exatamente os proventos, descontos, líquido, memória de cálculo e trilha `folha_historico` da competência fechada, mesmo que o salário do colaborador tenha mudado depois. | JSON do demonstrativo histórico intacto. | **Validado em SQLite / Pendente no Neon** | Depende de `M01`. |
| **DB-14** | **Segurança de Credenciais e Endpoints** | Aplicação em execução. | Inspeção de `frontend/app.js`, `index.html`, `/api/health` e respostas de erro 503. | Verificar todo o código estático servido ao navegador e forçar falha de conexão no `psycopg2`. | Nenhuma senha, token, hostname `neon.tech` ou `DATABASE_URL` aparece no frontend, em `/api/health` ou em mensagens HTTP 503. | Teste `test_neon_falha_de_conexao_nao_vaza_credenciais_nem_host` PASS. | **Validado por Teste Automatizado (PASS)** | Nenhum. |
| **DB-15** | **Recuperação após Erro de Conexão** | Simulação de indisponibilidade temporária do banco. | Falha `psycopg2.OperationalError` seguida de reconexão normal. | Disparar requisição com banco inacessível (recebendo HTTP 503 sem falso sucesso na UI) e repetir com banco ativo. | Na falha, UI exibe erro claro e mantém os dados digitados no formulário sem mostrar "Salvo com sucesso"; quando a conexão volta, a operação grava normalmente. | Teste automatizado + verificação em `frontend/app.js` (`requisitarApi`). | **Validado por Teste Automatizado (PASS)** | Nenhum. |

---

## 2. Roteiro do Teste Final de Ponta a Ponta — 16 Passos (Seção 14)

O teste integrado final (`tests/test_jornada_ponta_a_ponta.py` + validação na UI) executará exatamente os 16 passos obrigatórios usando os fluxos reais da aplicação:

1. **Acessar o sistema:** Autenticar com `POST /api/auth/login` (`admin.dp@empresa.com.br`) e validar sessão em `GET /api/auth/me`.
2. **Cadastrar/Configurar a empresa:** Configurar em `POST /api/folha/parametros` a empresa fictícia `"Usina ForçaVerde Agroindustrial S.A."`, CNPJ `"12.345.678/0001-90"`, divisor `220h`, dias mês `30`.
3. **Cadastrar três funcionários fictícios (`POST /api/colaboradores`):**
   - **Funcionário 1:** `Matrícula: FV-0101`, `Nome: Marcos Vinícius Rocha`, `CPF: 529.982.247-25`, `Cargo: Operador de Caldeira`, `Setor: Operações`, `Dependentes: 1 (Filho)`.
   - **Funcionário 2:** `Matrícula: FV-0102`, `Nome: Beatriz Helena Costa`, `CPF: 111.444.777-35`, `Cargo: Analista Financeiro Pleno`, `Setor: Financeiro`, `Dependentes: 2 (Filhos)`.
   - **Funcionário 3:** `Matrícula: FV-0103`, `Nome: Rafael Almeida Prado`, `CPF: 123.456.789-09`, `Cargo: Coordenador de TI`, `Setor: Tecnologia da Informação`, `Dependentes: 0`.
4. **Informar salários:**
   - Funcionário 1: `R$ 2.640,00`
   - Funcionário 2: `R$ 4.800,00`
   - Funcionário 3: `R$ 7.500,00`
5. **Criar/Selecionar uma competência:** Selecionar competência `2026-11` (`01/11/2026` a `30/11/2026`, pagamento `05/12/2026`).
6. **Registrar eventos:**
   - Funcionário 1: `10 horas extras 50%` (`HE50`) e `20 horas de adicional noturno 20%` (`NOTURNO`).
   - Funcionário 2: `1 falta injustificada` (`FALTA`) e `Vale-transporte 6%` (`0510`).
   - Funcionário 3: `Gratificação de função 40%` (`0040`).
7. **Processar a folha:** Calcular as 3 folhas via API/UI (`POST /api/folha`), gravando cabeçalhos e itens no banco.
8. **Conferir os valores:** Verificar para os 3 funcionários que `total_proventos`, `base_inss`, `INSS (501)`, `base_irrf`, `IRRF (502)`, `FGTS (901)` e `salario_liquido` batem centavo a centavo com os casos de teste validados.
9. **Corrigir um lançamento:** Abrir a folha da Funcionária 2 (`Beatriz Helena Costa`), remover a `1 falta injustificada` (justificada por atestado entregue) e adicionar `4 horas extras 50%`.
10. **Recalcular:** Submeter `PUT /api/folha/<id>` e verificar que o `salario_liquido`, `base_inss` e `folha_historico` (`acao = 'RECALCULO'`) foram atualizados.
11. **Fechar a folha:** Executar o fechamento da competência `2026-11` (`POST /api/folha/fechar-competencia` / `POST /api/folha/<id>/fechar`) e confirmar que tentativas posteriores de edição retornam HTTP 403.
12. **Gerar demonstrativos:** Consultar `GET /api/folha/<id>` para os 3 funcionários e verificar que o holerite traz o nome/CNPJ da empresa, todos os itens discriminados, as bases legais e a memória de cálculo.
13. **Encerrar a sessão:** Executar `POST /api/auth/logout` e confirmar invalidação do token (`GET /api/auth/me` -> HTTP 401).
14. **Acessar novamente:** Realizar novo login (`POST /api/auth/login`) em nova sessão.
15. **Consultar a folha fechada:** Consultar `GET /api/folha?competencia=2026-11&situacao=fechada` e abrir os 3 holerites.
16. **Confirmar a persistência dos dados no Neon:** Verificar diretamente no banco que a empresa/parâmetros, os 3 colaboradores, as 3 folhas com `situacao='fechada'`, todos os `folha_itens` e os registros em `folha_historico` estão persistidos e íntegros.
