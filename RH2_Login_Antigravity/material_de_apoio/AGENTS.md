# Regras de execução para agentes — FolhaFácil Demo

Leia primeiro `SPEC.md` e `CRITERIOS_DE_ACEITE.md` antes de editar.

1. Trabalhe estritamente no escopo do LOGIN de demonstração. Não implemente folha, holerite, API externa ou registro de usuários.
2. Use React + Vite + TypeScript, Express + TypeScript, SQLite local, sessões no servidor, Argon2id, Zod, Helmet e rate limit conforme SPEC. Prefira compatibilidade com Node 26 LTS e registre eventual fallback para Node 24 LTS.
3. Inicie em modo planejamento: produza plano concreto, lista de tarefas, desenho de rotas, segurança e testes. Aguarde aprovação do plano antes de editar arquivos.
4. Após aprovação, implemente as tarefas em ordem e execute as verificações localmente; corrija falhas determinísticas do próprio código durante a execução sem pedir nova orientação para cada detalhe.
5. Nunca invente evidências. Teste não executado = BLOCKED. Não afirme “pronto para produção”.
6. Nunca exponha senhas, hashes completos, cookies de sessão ou segredos em logs ou relatórios. `.env` e `*.sqlite*` devem ficar fora do Git; commitar apenas `.env.example`.
7. Não adicione serviços externos, IA, Docker, novas features ou dependências pesadas sem necessidade. Não gerar imagens por IA. Não fazer pesquisas abertas/longas no navegador quando documentação local resolve.
8. Mantenha README curto com pré-requisitos, instalação, variáveis de ambiente, seed, comandos de execução, testes e troubleshooting.
9. Escreva um relatório final em `EVIDENCIAS.md`: AC-01..AC-16 com PASS/FAIL/BLOCKED e indicação de comando/arquivo de teste observado; seja explícito quanto a limitações do ambiente.
10. Se aparecer problema de ambiente, isole-o e reporte o comando exato para reprodução; não degrade segurança só para deixar o build verde.
