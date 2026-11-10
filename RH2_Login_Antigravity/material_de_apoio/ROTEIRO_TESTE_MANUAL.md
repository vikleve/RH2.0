# Teste manual de 12 minutos — FolhaFácil Demo

> Nunca compartilhe capturas de cookie, senha ou variável secreta. Os resultados devem ser observados em máquina local e anotados em EVIDENCIAS.md.

## Antes de começar
- Execute `node -v`, `npm -v`, `npm ci`, configure `.env` com **senha de demonstração definida por você**, faça `npm run seed:demo` e `npm run dev` conforme README gerado.
- Abra a URL local exibida pelo Vite.

## Roteiro
1. **Visual (AC-01/02/03):** há rótulos, foco de teclado, contraste, mensagem anunciada e layout sem rolagem horizontal a 360 px?
2. **Validação (AC-04):** envie e-mail vazio, e-mail inválido e senha vazia. A API não é chamada em dados triviais inválidos?
3. **Falha de autenticação (AC-06):** senha errada e usuário inexistente retornam mensagem idêntica, sem informar qual caso ocorreu?
4. **Login válido (AC-05/10):** conta seed entra, abre painel, e refresh mantém a sessão?
5. **Proteção real (AC-11):** numa janela anônima, tente abrir URL privada e `GET /api/dashboard`; deve resultar em 401.
6. **Logout (AC-12):** saia e tente voltar para o painel, reusar uma chamada privada e fazer refresh; deve ser negado.
7. **Limite de tentativas (AC-07):** use o teste automatizado isolado para verificar 429 sem bloquear sua própria aula.
8. **Sessão e segurança (AC-08/09/13):** confira headers, cookie e banco sem copiar credenciais ou cookies; teste de origem indevida se previsto.
9. **Qualidade (AC-14/15/16):** execute typecheck, lint, unit/integração, build e e2e. Registre logs resumidos e passos reais do README.

## Perguntas de reflexão
- Por que uma tela bonita NÃO comprova autenticação segura?
- Onde o backend efetivamente rejeita acesso anônimo?
- Qual requisito teria sido esquecido sem a matriz AC?
- Quanto do trabalho foi testado fora do agente, sem gastar novas interações?
