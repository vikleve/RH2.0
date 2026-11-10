# Prompts prontos — uso mínimo de solicitações no Antigravity

## Preparação (custo zero de agente)
1. Crie uma pasta local chamada `folhafacil-demo` e abra-a no Antigravity.
2. Copie `SPEC.md`, `CRITERIOS_DE_ACEITE.md` e `AGENTS.md` para a raiz da pasta. Se quiser, copie também este arquivo.
3. Instale Node.js LTS, Git e dependências indicadas durante a implementação.
4. Se o Antigravity oferecer modo Planning/Planejamento, selecione-o. Faça commit inicial dos arquivos Markdown via terminal, opcionalmente.

## CHAMADA 1 — Planejamento: colar no Agent em Planning Mode

```text
/plan Leia integralmente os arquivos SPEC.md, CRITERIOS_DE_ACEITE.md e AGENTS.md da raiz deste workspace. Estamos construindo apenas o login didático do “FolhaFácil Demo”, com poucos créditos disponíveis.

Sua tarefa AGORA é elaborar um plano de implementação objetivo e uma lista ordenada de tarefas que cubram os critérios AC-01 a AC-16. Apresente:
(a) estrutura de pastas e scripts npm;
(b) escolhas e versões compatíveis da stack Node.js LTS + React/Vite/TS + Express/TS + SQLite;
(c) contratos das quatro rotas;
(d) decisão de armazenamento de sessão persistente, Argon2id, cookies, rate limit, CSRF/Origin, logs e seed;
(e) testes mínimos e comandos de verificação;
(f) riscos e como comprovar cada AC;
(g) etapas G0-G4 com definição de pronto.

Não implemente folha de pagamento, cadastro, recuperação de senha, OAuth ou infraestrutura externa. Não escreva código antes da minha aprovação. Não pergunte decisões já resolvidas na SPEC. Prefira a solução mais simples, local e reproduzível; não gaste uso com navegação/pesquisa ou subagentes desnecessários. Ao final, peça apenas que eu revise o plano e use o botão Proceed/Prosseguir.
```

### Aprovação sem nova conversa
- Revise o plano gerado, compare com AC-01..AC-16 e escopo fora do projeto.
- Corrija comentários diretamente no artefato, quando necessário.
- Clique **Proceed / Prosseguir** para autorizar a execução (o fluxo da interface pode variar conforme a versão do Antigravity).
- Durante a execução, o agente deve instalar dependências, gerar código, rodar testes e preencher `EVIDENCIAS.md` sem exigir um prompt separado para cada arquivo.

## CHAMADA 2 (somente se necessária) — Correção consolidada

```text
Corrija SOMENTE os problemas reais que restaram na implementação aprovada. Leia SPEC.md, CRITERIOS_DE_ACEITE.md, AGENTS.md e EVIDENCIAS.md. Considere esta saída literal dos testes e a lista de falhas que coletei abaixo:

[COLE AQUI EM UMA ÚNICA MENSAGEM: comandos executados, logs sem segredos, IDs AC com FAIL/BLOCKED, capturas/descrições dos problemas]

Para cada problema: identifique a causa raiz, proponha a menor correção necessária, aplique-a e execute novamente apenas os testes afetados mais o gate final (`typecheck`, `lint`, `test`, `build`, `test:e2e` se disponível). Não acrescente funcionalidades fora do escopo e não enfraqueça autenticação ou testes. Atualize EVIDENCIAS.md com os resultados efetivamente observados; relate problemas remanescentes de ambiente como BLOCKED. Termine com resumo de diffs, comandos e estado de AC-01..AC-16.
```

## Regras para poupar créditos
- Não gastar uma solicitação para cada cor, texto, componente ou erro isolado.
- Não mandar “está dando erro” sem logs: primeiro reproduza no terminal e agrupe os problemas.
- Use `npm run ...` e DevTools do navegador para testar antes de chamar o agente outra vez.
- Não pedir “refaça melhor”, “deixe mais moderno” ou features extras depois do escopo fechado.
- Duas solicitações são **meta pedagógica, não garantia de consumo/quota**: tarefas, modelos e aprovação podem consumir recursos de maneiras diferentes.
