# RH2.0 — Planning: Login e Autenticação Segura

/plan

Leia `docs/authentication/SPEC.md`, os documentos do projeto e os arquivos em `material_de_apoio/`. Leia também as instruções do workspace (AGENTS.md, se existir).

## Prioridade
A especificação `docs/authentication/SPEC.md` é a adaptação proposta para RH2.0. O kit do professor é referência didática original e deve ser preservado. A arquitetura e tecnologias oficiais dos gestores prevalecem.

## Antes de planejar
1. Inspecione a estrutura e estado atual do repositório.
2. Identifique stack, banco, mecanismo de autenticação, sessão, padrões de API, UI e testes.
3. Localize autenticação existente ou parcial.
4. Compare a arquitetura real com o kit didático.
5. Liste conflitos, lacunas e decisões que precisam de aprovação.

## Entrega do planejamento
Produza:
- diagnóstico arquitetural;
- proposta de fluxo de login;
- contratos de login, sessão e logout (sem inventar endpoints se já houver padrões);
- componentes frontend e responsabilidades backend;
- tarefas ordenadas e pequenas;
- plano de testes mapeado para AC-01…AC-16;
- análise de ameaças/riscos;
- configuração necessária por ambiente;
- Definition of Done;
- decisões pendentes.

## Restrições
- NÃO implemente código neste momento.
- NÃO altere dependências, banco, schema ou arquitetura sem aprovação.
- NÃO introduza SQLite/Express ou uma segunda autenticação por copiar o exemplo.
- NÃO crie credenciais hardcoded, login fictício ou bypass.
- NÃO declare testes/build aprovados sem executá-los.
- Evite escopo adicional (MFA, OAuth, recuperação de senha etc.).
- Se algo estiver ambíguo, pergunte em vez de adivinhar.

Ao terminar, apresente o plano para revisão humana e aguarde aprovação explícita antes de implementar.
