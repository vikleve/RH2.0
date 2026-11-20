# Sessão ativa e CPFs sintéticos — RH2.0

## Sessão durante o uso

O backend Vercel/Python usa timeout deslizante:
- 12 horas sem requisição autenticada: a sessão expira;
- cada requisição autenticada renova a janela de 12 horas;
- limite absoluto de 7 dias desde o login, mesmo com atividade;
- logout continua revogando a sessão imediatamente.

O frontend envia uma validação leve para `/api/auth/me` no máximo a cada 5 minutos quando há interação (clique, teclado, toque ou rolagem) e a aba está visível. Falhas transitórias de rede não encerram a sessão local.

## CPFs sintéticos para testes

A validação matemática pode ser relaxada exclusivamente em ambiente não produtivo.

Na Vercel, configure a variável:
- Nome: `RH2_ALLOW_FAKE_CPFS`
- Valor: `1`
- Ambiente: **Preview** (não Production)

O código também verifica `VERCEL_ENV`, `APP_ENV` e `ENVIRONMENT`: se qualquer um indicar `production`, CPFs fictícios continuam bloqueados mesmo que a variável esteja configurada.

Nesse modo, o CPF ainda precisa conter exatamente 11 dígitos. A unicidade por empresa continua ativa, inclusive para dados sintéticos. A validação matemática normal permanece ativa em produção.

Para desativar o modo de teste, remova `RH2_ALLOW_FAKE_CPFS` do ambiente Preview e faça um novo deploy.

**Importante:** não configure essa variável no ambiente Production. Os dados criados com CPFs sintéticos são exclusivamente para testes e não devem ser usados em cadastros reais, folha oficial ou obrigações legais.
