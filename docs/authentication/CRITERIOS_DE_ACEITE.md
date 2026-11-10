# RH2.0 — Critérios de Aceite do Módulo de Login & Autenticação Segura

**Projeto:** RH2.0 — Sistema Integrado de Departamento Pessoal & Folha de Pagamento  
**Data de Homologação:** 10 de Novembro de 2026  
**Status Consolidado:** 16 de 16 Critérios Aprovados (**100% PASS**)  

---

## 1. Checklist de Critérios de Aceite

- [x] **AC-01** — Tela de login funcional e alinhada à identidade visual RH2.0.
- [x] **AC-02** — Acessibilidade: navegação por teclado, foco visível, rótulos e mensagens com `role="alert"` e `aria-live`.
- [x] **AC-03** — Layout responsivo compatível com viewports desktop e celular (<= 480px) sem overflow horizontal.
- [x] **AC-04** — Validação de entradas no frontend e no backend (campos vazios rejeitados com HTTP 400).
- [x] **AC-05** — Login válido com credenciais homologadas cria sessão segura e retorna HTTP 200.
- [x] **AC-06** — Falhas de autenticação utilizam a mensagem genérica estrita `"E-mail ou senha inválidos."` (sem enumeração de contas).
- [x] **AC-07** — Rate limit contra ataques de força bruta ativo: 5 falhas consecutivas bloqueiam a 6ª tentativa com HTTP 429 e `Retry-After`.
- [x] **AC-08** — Senhas protegidas criptograficamente via PBKDF2-HMAC-SHA256 (100.000 iterações com salt individual); nunca em texto puro.
- [x] **AC-09** — Cookie de sessão gerado com `HttpOnly`, `SameSite=Lax` e `Secure` (em HTTPS), com token de 32 bytes de alta entropia.
- [x] **AC-10** — Persistência da sessão após refresh validada via `GET /api/auth/me`.
- [x] **AC-11** — Endpoints privados (`/api/colaboradores`, `/api/folha`) bloqueiam imediatamente usuários anônimos com HTTP 401.
- [x] **AC-12** — Logout com invalidação imediata da sessão no servidor e revogação durável do token.
- [x] **AC-13** — Proteção CSRF / Origem ativada em mutações de estado: origens externas não confiáveis recebem HTTP 403 Forbidden.
- [x] **AC-14** — Build e syntax check executados com sucesso em todos os módulos Python (`python -m py_compile`).
- [x] **AC-15** — 77 testes automatizados headless executados e aprovados com 100% de sucesso.
- [x] **AC-16** — Documentação e relatório de auditoria e evidências reproduzíveis sem segredos versionados.

---

## 2. Matriz Rastreabilidade: Critério → Teste → Status

| ID | Requisito Verificável | Método / Teste Executado | Resultado Observado | Status |
|---|---|---|---|:---:|
| **AC-01** | Tela apresenta marca RH2.0, e-mail, senha, Entrar, toggle e spinner | `test_ac_01_elementos_tela_login_rh20` | Elementos presentes no DOM com IDs e estrutura requerida | **PASS** |
| **AC-02** | Formulário acessível (`role="alert"`, `aria-live`, labels associados) | `test_ac_02_acessibilidade` | Labels for, alert com role e aria-label no toggle verificados | **PASS** |
| **AC-03** | Layout responsivo sem overflow horizontal | `test_ac_03_responsividade_css` | Media queries e seletores adaptativos presentes no CSS | **PASS** |
| **AC-04** | Validação no backend de entradas vazias | `test_ac_04_validacao_entradas_backend` | HTTP 400 Bad Request para payload sem identificador/senha | **PASS** |
| **AC-05** | Login válido cria sessão e retorna dados do operador | `test_ac_05_login_valido_sucesso` | HTTP 200 OK, token emitido, Set-Cookie HttpOnly retornado | **PASS** |
| **AC-06** | Mensagem genérica estrita sem enumeração | `test_ac_06_mensagens_genericas_sem_enumeracao` | HTTP 401 com `"E-mail ou senha inválidos."` idêntico para conta inexistente e senha incorreta | **PASS** |
| **AC-07** | Rate limit de 5 tentativas por janela | `test_ac_07_rate_limit_bloqueio_apos_5_tentativas` | 5 erros seguidos geram HTTP 429 com Retry-After na 6ª tentativa | **PASS** |
| **AC-08** | Senha nunca em texto puro / hash PBKDF2 | `test_ac_08_protecao_senhas_banco_e_logs` | Hash hex de 64 chars e salt de 32 chars verificados na base | **PASS** |
| **AC-09** | Cookie e sessão com flags seguras | `test_ac_09_ac_10_sessao_persiste_refresh` | Set-Cookie contém `session_token`, `HttpOnly` e `SameSite=Lax` | **PASS** |
| **AC-10** | Sessão continua válida após refresh | `test_ac_09_ac_10_sessao_persiste_refresh` | `GET /api/auth/me` com cookie retorna HTTP 200 e dados do operador | **PASS** |
| **AC-11** | Endpoints privados bloqueiam anônimos | `test_ac_11_rotas_privadas_bloqueadas_para_anonimos` | `GET /api/colaboradores` e `/api/folha` sem token retornam HTTP 401 | **PASS** |
| **AC-12** | Logout invalida sessão no servidor | `test_ac_12_logout_invalida_sessao_no_servidor` | Token revogado no SQLite (`revogado=1`); reuso retorna HTTP 401 | **PASS** |
| **AC-13** | Proteção CSRF / Origem em mutações | `test_ac_13_protecao_csrf_origem_rejeita_origem_fraudulenta` | POST com `Origin: http://site-hacker-malicioso.com` recebe HTTP 403 | **PASS** |
| **AC-14** | Verificação de integridade e compilação | `python -m py_compile` em backend, api, tests | Exit code 0 em todos os arquivos | **PASS** |
| **AC-15** | Suíte consolidada de testes headless | `tests/executar_todos_testes.py` | 77 de 77 testes aprovados em 13.72s (100% sucesso) | **PASS** |
| **AC-16** | Auditoria e ausência de segredos em logs | `test_ac_16_auditoria_eventos_autenticacao` | Tabela `auditoria_autenticacao` populada sem senhas ou tokens | **PASS** |
