# RH2.0 — Especificação de Autenticação e Login
**Versão:** 1.0 — proposta para revisão  
**Status:** Planejamento; não autoriza implementação automática sem aprovação.

## 1. Objetivo
Implementar autenticação segura no RH2.0, permitindo que usuários autorizados entrem por e-mail e senha, mantenham uma sessão protegida, acessem rotas privadas e encerrem a sessão com invalidação no servidor.

## 2. Regra de compatibilidade arquitetural
- Esta especificação é uma adaptação do kit didático do professor ao RH2.0.
- Antes de implementar, inspecionar o workspace, documentação, dependências, banco e autenticação já existentes.
- Preservar a stack, arquitetura, banco e convenções definidos pelos gestores.
- Não introduzir SQLite, Express, outro banco ou um segundo mecanismo de autenticação apenas porque aparecem no exemplo didático.
- Se houver conflito ou decisão ausente, documentar e pedir aprovação; não assumir silenciosamente.
- O kit original está preservado em `material_de_apoio/`.

## 3. Escopo
Incluído:
- Tela de login responsiva e acessível;
- autenticação de credenciais no backend;
- sessão segura;
- proteção de rotas/endpoints privados;
- logout;
- limitação de tentativas;
- proteção CSRF/Origin apropriada;
- auditoria de eventos de autenticação;
- testes e documentação.

Fora do escopo inicial:
- recuperação/reset de senha;
- MFA/2FA;
- OAuth/SSO;
- cadastro público de usuários;
- permissões e RBAC completos (apenas respeitar mecanismos existentes e negar acesso quando não autorizado);
- funcionalidades de RH/folha.

## 4. Requisitos funcionais

### RF-LOGIN-001 — Interface
A tela deve conter:
- marca/identidade RH2.0, seguindo o design system existente;
- campo de e-mail;
- campo de senha;
- ação Entrar;
- controle mostrar/ocultar senha;
- estado de carregamento;
- mensagens de erro acessíveis;
- navegação por teclado e foco visível;
- layout responsivo para desktop e dispositivos móveis.

Não criar identidade visual ou componentes paralelos se já houver padrão no projeto.

### RF-LOGIN-002 — Autenticação
- Validar entradas no frontend e no backend.
- Autenticar pelo mecanismo de identidade já adotado no projeto.
- Rejeitar credenciais inválidas e contas inativas/bloqueadas conforme modelo existente.
- Usar resposta genérica para falhas: `E-mail ou senha inválidos.`
- Não revelar se um e-mail está cadastrado.
- Criar sessão somente após autenticação bem-sucedida.
- Não implementar autenticação simulada, hardcoded ou bypass para demonstração.

### RF-LOGIN-003 — Sessão
- Regenerar o identificador da sessão após autenticação, quando aplicável ao mecanismo adotado.
- Cookie de sessão com `HttpOnly`, `SameSite` adequado e `Secure` em HTTPS.
- Definir duração/expiração com base nas políticas do projeto; documentar a decisão.
- Não guardar senha, token secreto ou dados sensíveis em cookie/localStorage.
- Logout deve invalidar a sessão no servidor e limpar o cookie.
- Sessões expiradas ou revogadas não podem acessar endpoints privados.
- Não usar armazenamento em memória como persistência definitiva em produção.

### RF-LOGIN-004 — Proteção de recursos
- Todo endpoint privado deve validar autenticação no servidor.
- Não confiar apenas em redirecionamento ou ocultação de páginas no frontend.
- Requisição anônima a recurso privado deve receber `401`.
- Usuário autenticado sem permissão deve receber `403`, quando aplicável.
- Não retornar dados privados antes da validação de sessão/autorização.

### RF-LOGIN-005 — Proteções
- Rate limit no endpoint de login, com limites documentados e configuração compatível com infraestrutura/proxy.
- Proteção CSRF para operações mutáveis quando autenticação baseada em cookie for usada.
- Validar origem/`Origin` ou mecanismo equivalente quando apropriado.
- Validação de dados e consultas parametrizadas.
- Headers de segurança compatíveis com a aplicação.
- Não registrar senhas, cookies, tokens ou segredos.
- Não enfraquecer controles de segurança para fazer testes passarem.

### RF-LOGIN-006 — Auditoria
Registrar eventos necessários:
- login bem-sucedido;
- falha de login;
- logout;
- limitação/bloqueio por excesso de tentativas.

Registrar somente dados mínimos (data/hora, resultado e identificador disponível); nunca registrar senha, hash completo, cookie ou token secreto. Seguir mecanismo de auditoria já existente.

## 5. Contratos e fluxo
O agente deve primeiro descobrir os contratos existentes. Se não existirem, propor para aprovação antes de implementar. O mínimo esperado é:
- operação de login;
- operação para consultar sessão/usuário autenticado;
- operação de logout.

Não fixar paths, payloads ou nomes de tabelas sem verificar padrões existentes. Documentar respostas de sucesso e erro, códigos HTTP e validações.

Fluxo esperado:
1. Usuário envia e-mail/senha.
2. Backend valida entradas e aplica rate limit.
3. Mecanismo de autenticação valida credenciais/estado da conta.
4. Em sucesso, sessão é criada/regenerada e evento é auditado.
5. Frontend obtém estado autenticado e navega para destino autorizado.
6. Em falha, apresenta mensagem genérica.
7. Logout invalida sessão no servidor e remove cookie.

## 6. Critérios de aceite
- AC-01: tela de login funcional e coerente com identidade visual existente.
- AC-02: navegação por teclado, foco visível e mensagens acessíveis.
- AC-03: layout responsivo.
- AC-04: validação de entrada no frontend e backend.
- AC-05: credenciais válidas autenticam e criam sessão.
- AC-06: falhas usam mensagem genérica, sem revelar existência da conta.
- AC-07: rate limit funciona e é testado.
- AC-08: credenciais são tratadas pelo mecanismo seguro existente; não há senha em texto puro.
- AC-09: cookie/sessão configurados conforme ambiente e política documentada.
- AC-10: sessão permanece válida após refresh dentro do prazo.
- AC-11: endpoints privados rejeitam usuários anônimos.
- AC-12: logout invalida sessão no servidor.
- AC-13: proteção CSRF/Origin testada conforme arquitetura.
- AC-14: build, lint e typecheck (se existentes) passam.
- AC-15: testes automatizados executados; resultados reais documentados.
- AC-16: documentação de configuração e execução reproduzível.

## 7. Testes mínimos
- login válido;
- senha incorreta;
- usuário inexistente (mesma resposta externa);
- conta inativa/bloqueada;
- entradas inválidas;
- excesso de tentativas;
- acesso anônimo a endpoint privado (`401`);
- usuário sem autorização (`403`, se aplicável);
- sessão após refresh;
- logout e tentativa de reutilizar sessão;
- CSRF/Origin inválido;
- ausência de segredos em logs;
- testes de UI para estados de loading, erro e acessibilidade básica.

## 8. Segurança e qualidade
- Hash de senha: usar mecanismo existente e configuração recomendada; se o projeto gerenciar hashes diretamente, avaliar Argon2id (ou solução já aprovada) e parâmetros apropriados.
- Não implementar algoritmo criptográfico próprio.
- Segredos somente em variáveis de ambiente/secret manager; nunca commitados.
- Cookies seguros em produção HTTPS.
- Considerar proxy confiável antes de configurar IP/rate limit.
- Testes devem validar comportamento real, não apenas mocks isolados.
- Não declarar testes, build ou deploy como aprovados sem execução e evidência.

## 9. Definition of Done
- Requisitos e decisões arquiteturais revisados.
- Implementação integrada ao projeto (sem subsistema paralelo).
- Critérios de aceite verificados.
- Testes executados e resultados registrados.
- Build/lint/typecheck executados, quando disponíveis.
- Nenhum segredo no código ou logs.
- Documentação atualizada.
- Evidências e limitações conhecidas apresentadas.

## 10. Decisões pendentes
O agente deve apontar para aprovação humana:
- mecanismo de identidade/sessão já existente ou a adotar;
- duração e política de sessão;
- rate limit e comportamento de bloqueio;
- modelo de usuário/estado ativo;
- destino pós-login;
- endpoints finais, caso ainda não existam.
