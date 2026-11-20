# Modo temporário de apresentação — RH2.0

## CPF sintético
Durante a fase de testes e apresentação, configure `RH2_ALLOW_FAKE_CPFS=1` no ambiente Production da Vercel.
- O CPF deve conter exatamente 11 dígitos após a normalização.
- A validação matemática dos dígitos verificadores fica temporariamente desativada.
- A verificação de unicidade no banco permanece ativa.
- O frontend também exige 11 dígitos.

## Sessão
Durante a apresentação, a expiração automática está temporariamente desativada:
- a sessão permanece válida até logout, revogação administrativa ou inativação da conta;
- o logout continua invalidando o token no servidor;
- o token continua armazenado em `sessionStorage`, portanto fechar a sessão/aba do navegador pode exigir novo login;
- a validade não depende mais do campo `expira_em`.

## Reversão obrigatória antes da versão final
Este modo é exclusivamente temporário para demonstração. Antes de liberar a versão final:
1. Remover `RH2_ALLOW_FAKE_CPFS` do ambiente Production da Vercel.
2. Restaurar a validação matemática oficial de CPF no backend.
3. Restaurar timeout deslizante e limite absoluto de sessão.
4. Executar a suíte de testes de autenticação e validar o deploy.
5. Registrar a aprovação dos responsáveis pela governança.

**Não utilizar CPFs sintéticos nem dados pessoais fictícios como se fossem registros reais em folha oficial, eSocial, relatórios legais ou operações empresariais.**
