# Matriz de critérios de aceite — Login FolhaFácil Demo

> Preencher Estado (PASS / FAIL / BLOCKED) somente após executar o teste. Anexar evidência: nome do teste/log, comando, ou captura manual sem expor segredos.

| ID | Requisito verificável | Como testar | Resultado esperado | Estado/Evidência |
|---|---|---|---|---|
| AC-01 | Tela apresenta e-mail, senha, Entrar | Abrir `/login` | Campos rotulados e botão visível | PENDENTE |
| AC-02 | Formulário acessível | Teclado + foco + leitor de tela quando possível | Ordem coerente; rótulos; erro `role=alert` | PENDENTE |
| AC-03 | Layout responsivo | Inspecionar viewport 360 px e desktop | Sem overflow horizontal; controles utilizáveis | PENDENTE |
| AC-04 | Validação de entradas | Enviar vazio/e-mail malformado | Erro de validação sem login | PENDENTE |
| AC-05 | Credenciais válidas | Criar conta demo por seed e autenticar | HTTP 200; sessão criada; redirecionamento ao painel | PENDENTE |
| AC-06 | Credenciais inválidas e usuário inexistente | Testar dois casos | HTTP 401; mesma mensagem genérica | PENDENTE |
| AC-07 | Proteção contra tentativa repetida | Repetir requisições com dados de teste isolados | HTTP 429 no limite documentado | PENDENTE |
| AC-08 | Senha protegida | Inspecionar base e logs | Hash Argon2id; sem senha em claro/log | PENDENTE |
| AC-09 | Cookie e sessão | Inspecionar Set-Cookie e backend | HttpOnly, SameSite, Secure em HTTPS; sessão persistente | PENDENTE |
| AC-10 | Sessão continua após refresh | Login e recarregar a página | `/api/auth/me` mantém autenticação | PENDENTE |
| AC-11 | Rota privada bloqueada | Abrir `/api/dashboard` sem cookie | HTTP 401 sem conteúdo privado | PENDENTE |
| AC-12 | Logout realmente invalida | Fazer login, sair e reutilizar cookie anterior | Sessão destruída; API privada volta 401 | PENDENTE |
| AC-13 | Proteção de requisições mutáveis | Enviar POST de origem indevida / sem defesa exigida | Bloqueio por política CSRF/Origin documentada | PENDENTE |
| AC-14 | Build e verificações | `npm run typecheck`, `npm run lint`, `npm run build` | Todos exit code 0 | PENDENTE |
| AC-15 | Testes automatizados | `npm test` e `npm run test:e2e` | Fluxos centrais aprovados ou bloqueio registrado | PENDENTE |
| AC-16 | Reproduzibilidade e documentação | Clonar/copiar, `npm ci`, configurar `.env`, seed, dev | Aluno consegue rodar com README sem segredos no Git | PENDENTE |

## Política de fechamento
- Critério PASS somente com execução observada e evidência registrada.
- Se AC-01..AC-16 estão PASS, o exercício didático termina. Se algum estiver FAIL ou BLOCKED, registrar limitação sem alegar sucesso completo.
- Produção real não faz parte do aceite: exige revisão de segurança, arquitetura operacional, controles de compliance e dados reais sob autorização.
