# SPEC — Login do Sistema de Folha de Pagamento (v1.0)

> Objetivo: construir um LOGIN funcional, verificável e didático. Não construir folha de pagamento real.
> Método: Spec-Driven Development (SDD): especificação → plano → tarefas → implementação → testes → evidências.

## 1. Contexto e objetivo
Uma pessoa do RH precisa acessar a área privada de um sistema chamado **FolhaFácil Demo** por meio de e-mail e senha. A interface deve ser genérica, acessível e responsiva. O sistema autentica no backend Node.js, mantém uma sessão segura e abre um painel demonstrativo sem dados salariais ou pessoais reais.

## 2. Histórias de usuário
- HU-01: Como analista de RH, quero informar e-mail e senha para entrar no sistema.
- HU-02: Como usuário, quero mensagens claras e não reveladoras ao errar credenciais.
- HU-03: Como usuário autenticado, quero acessar um painel privado e ver minha identificação mínima.
- HU-04: Como usuário, quero sair e impedir que minha sessão anterior continue válida.
- HU-05: Como usuário de celular ou teclado, quero usar o formulário sem barreiras de interação.

## 3. Escopo funcional
- Tela com logomarca textual “FolhaFácil Demo”, campo e-mail, campo senha, botão “Entrar”, alternância mostrar/ocultar senha, indicadores de carregamento, mensagem de erro acessível e layout responsivo.
- Validação cliente e servidor: e-mail com formato válido; senha obrigatória; limites de tamanho de entrada.
- Endpoint para autenticar credenciais, endpoint para consultar sessão, endpoint para encerrar sessão e endpoint protegido do painel.
- Uma conta de demonstração criada por script de seed; o e-mail e a senha são informados pelo aluno por variáveis de ambiente locais, nunca versionados.
- Painel privado mínimo: “Você está autenticado”, nome de exibição e botão “Sair”. Não há folha, remuneração, cadastro real ou qualquer PII sensível.
- Testes automatizados de integração e testes básicos de interface/e2e, documentação e instruções reproduzíveis.

## 4. Fora de escopo
- Cadastro público, recuperação de senha por e-mail, OAuth/SSO, MFA, permissões de RH completas, folha de pagamento, holerites, CPF, dados salariais, envio de e-mails, hospedagem pública e infraestrutura de produção.
- Não simular integração com APIs reais, não usar serviços pagos e não inventar usuários ou credenciais reais.

## 5. Stack e execução
- Node.js **26 LTS** preferencialmente (se dependência impedir, usar Node 24 LTS e registrar a justificativa).
- Frontend: React + Vite + TypeScript, CSS simples e sem biblioteca pesada de UI.
- Backend: Express + TypeScript.
- Persistência local: SQLite para `users` e sessão persistente via store compatível com `express-session` (não usar `MemoryStore` como solução final).
- Segurança: hash de senha Argon2id, `express-session`, `helmet`, `express-rate-limit`, validação com Zod, consultas parametrizadas; considerar middleware de proteção de origem/CSRF para ações de mudança de estado.
- Qualidade: Vitest e Supertest para integração; Playwright para ao menos 1 fluxo e2e essencial (quando instalação de browser estiver disponível), ESLint e verificação de tipos.
- Raiz de projeto com scripts consistentes: `npm run dev`, `npm run seed:demo`, `npm test`, `npm run test:e2e`, `npm run lint`, `npm run typecheck`, `npm run build`, `npm start`. Documentar comandos reais e, se necessário, instalar browser para e2e uma única vez.
- Servir frontend e API sob mesma origem em produção; durante desenvolvimento usar proxy do Vite para `/api` (sem CORS irrestrito).
- O código deve funcionar no Windows com terminal PowerShell e também em ambientes Unix; não exigir WSL, Docker, Redis ou serviços externos.
- Dependências devem ser mantidas em versões compatíveis e registrar `package-lock.json`.

## 6. Modelo de dados mínimo
Tabela `users`: `id` (identificador), `email` (único e normalizado), `display_name`, `password_hash`, `is_active`, `created_at`.
Store persistente de sessões: identificador de sessão aleatório, conteúdo mínimo (somente `userId`) e expiração; nunca armazenar senha na sessão.

## 7. Contrato REST (mesma origem)
- `POST /api/auth/login`: `{ "email": "...", "password": "..." }`; sucesso `200` com `{ "user": { "id", "displayName" } }`; inválido `401` com mensagem genérica; entrada inválida `400`; excesso de tentativas `429`.
- `GET /api/auth/me`: autenticado `200` com usuário mínimo; sem sessão `401`.
- `POST /api/auth/logout`: encerrar sessão e limpar cookie; retornar `204` se sessão foi encerrada; documentar comportamento de ausência de sessão.
- `GET /api/dashboard`: autenticado `200` com dados demonstrativos não sensíveis; sem sessão `401`.
- Respostas que dependem de autenticação devem usar `Cache-Control: no-store`.

## 8. Política de autenticação e sessão
- Hash Argon2id com sal gerenciado pela biblioteca; nunca texto simples, SHA-256 direto ou log de senha.
- Identificadores desconhecidos e senhas inválidas produzem a mesma mensagem: **“E-mail ou senha inválidos.”** Sem revelar se conta existe ou está desativada.
- Rate limit no endpoint de login; propor política explicada nos testes (ex.: 5 tentativas/15 min em chave adequada, com reset após janela, considerando limitações do projeto local).
- Regenerar ID de sessão depois do login bem-sucedido; destruir sessão no logout; impedir reutilização de sessão encerrada.
- Cookie de sessão: `HttpOnly`, `SameSite=Lax` ou mais restritivo, `Secure` quando HTTPS/produção, limite de duração configurado e sem dados pessoais no valor.
- Proteger chamadas mutáveis contra CSRF usando verificação de origem e/ou token apropriado; não confiar exclusivamente no atributo SameSite como defesa universal.
- Não manter token em localStorage; evitar rotas privadas somente protegidas visualmente no React — backend deve recusar.
- Não imprimir segredos, corpo integral de login ou cookies nos logs. `.env` e base local no `.gitignore`.
- Para produção real: análise de ameaças, gestão de segredos, HTTPS obrigatório, auditoria, sessões compartilhadas em escala, MFA/SSO conforme requisitos e avaliação de privacidade/LGPD.

## 9. Estados de interface
1. Inicial: formulário com rótulos e botão ativo.
2. Validação: campos ausentes/formato inválido; sem chamar API desnecessariamente.
3. Enviando: indicador visual, botão temporariamente desabilitado; não duplicar submissão.
4. Erro de credenciais: mensagem neutra e acessível (`role="alert"`); senha não revelada.
5. Muitas tentativas: mensagem amigável e status do backend respeitado.
6. Sucesso: navega para o painel; refresh mantém sessão válida enquanto não expirada.
7. Logout: redireciona ao login; rota protegida não é acessível após sair.

## 10. Gates de qualidade
- G0 — Especificação aprovada: escopo, critérios AC e riscos claros.
- G1 — Plano aprovado: arquivos, rotas, dependências, sequência de tarefas, testes, sem extras.
- G2 — Implementação funcional: formulário, API, sessão, banco e seed.
- G3 — Testes e segurança básica: typecheck, lint, build, integração, e2e, revisão manual.
- G4 — Evidência e entrega: logs de testes, README e checklist AC preenchido com PASS/FAIL/BLOCKED. Não afirmar PASS sem executar.

## 11. Critérios de aceite
Referência canônica: `CRITERIOS_DE_ACEITE.md`. Cada AC deve ter teste, expectativa e evidência. Marcar `BLOCKED` quando ambiente ou navegador não permitir executar teste; jamais marcar como aprovado por suposição.

## 12. Restrições para economizar chamadas no Antigravity
- Não perguntar sobre decisões já fixadas nesta SPEC.
- Não instalar ferramentas pagas nem criar recursos em nuvem.
- Evitar frameworks, bibliotecas e abstrações desnecessárias.
- Planejar a entrega integral em uma implementação focada; executar comandos e corrigir problemas observados dentro da mesma execução sempre que possível.
- Não chamar outros agentes, pesquisar web extensivamente nem gerar visuais por IA sem necessidade.
- Ao final, resumir os artefatos criados, comandos reais, testes executados e falhas remanescentes em tabela curta.
