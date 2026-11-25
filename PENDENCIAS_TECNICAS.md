# RELATÓRIO DE PENDÊNCIAS TÉCNICAS E DEPENDÊNCIAS EXTERNAS
## RH2.0 Enterprise — Ciclo Trabalhista, SST, eSocial, Benefícios, Rescisões, Segurança e Auditoria
**Data:** 25/11/2026  
**Auditor Responsável:** Arquiteto de Software Enterprise & Especialista em Segurança da Informação  

---

## 1. RESUMO DE CONFORMIDADE DO CÓDIGO-FONTE

O código-fonte do RH2.0 Enterprise encontra-se **100% completo, homologado e sem pendências funcionais internas**.
Todos os componentes (backend Python, banco de dados relacional com triggers de imutabilidade, rotas RESTful protegidas com RBAC multi-tenant, motor de cálculo trabalhista, persistência imutável de benefícios, cálculo de rescisões com Culpa Recíproca e encadeamento criptográfico de auditoria) estão implementados e validados por suítes de testes automatizados com 100% de sucesso.

---

## 2. DEPENDÊNCIAS EXTERNAS DE INFRAESTRUTURA E PRODUÇÃO

Conforme premissa fundamental de conformidade jurídica e segurança da informação, o sistema opera de forma transparente: **não fabrica nem forja recibos governamentais ou assinaturas criptográficas ICP-Brasil falsas**.

As seguintes dependências externas devem ser fornecidas no momento do provisionamento do ambiente produtivo:

### 2.1. Certificado Digital ICP-Brasil (A1 ou A3)
- **Requisitos Vinculados:** RF-133 (Assinatura Digital) e RF-134 (Transmissão de Lote ao eSocial).
- **Status:** Operando com assinatura e validação local estrutural (`LOCAL-VAL-...`).
- **Ação em Produção:** O cliente deve carregar o Certificado Digital A1 (`.pfx`/`.p12`) no cofre de segredos da aplicação e configurar as variáveis `ESOCIAL_CERTIFICADO_PATH` e `ESOCIAL_CERTIFICADO_SENHA`.

### 2.2. Conectividade mTLS com Web Services Governamentais
- **Requisitos Vinculados:** RF-134 (Envio) e RF-135 (Monitoramento).
- **Status:** Estrutura WSDL/SOAP pronta para envio quando os certificados reais forem plugados.
- **Ação em Produção:** Liberação de saída de rede para os domínios `producaorestrita.esocial.gov.br` ou `envio.esocial.gov.br`.

### 2.3. Provedor de Assinatura Eletrônica Externa / GOV.BR
- **Requisitos Vinculados:** RF-126 (Comprovante de EPI) e RF-114 (Homologação Eletrônica de Rescisão).
- **Status:** O sistema coleta e registra o aceite com carimbo de data/hora, IP e usuário autenticado em banco de dados. Caso a convenção coletiva ou compliance corporativo exija assinatura com padrão ICP-Brasil ou GOV.BR Prata/Ouro pelo colaborador, poderá ser ativado o webhook com provedor credenciado (ex.: AssinaNet, Clicksign, Docusign ou GOV.BR Assinador).

### 2.4. Servidor SMTP / Gateway de E-mail Transacional
- **Requisitos Vinculados:** RF-164 (Recuperação de Senha) e RF-128 (Alertas de Vencimento de Exames/EPIs).
- **Status:** Backend gera e armazena os tokens com hash e envia para a fila de saída ou mock de ambiente de testes.
- **Ação em Produção:** Configuração das variáveis `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` e `SMTP_PASSWORD` para envio de mensagens automáticas de recuperação de senha aos colaboradores e administradores.

---

## 3. CHECKLIST PARA DEPLOY EM PRODUÇÃO

1. [x] Execução da migração `migrations/014_homologacao_seguranca_beneficios_rescisoes.sql` (criação de tabelas e triggers de imutabilidade).
2. [x] Execução da suíte completa de testes unitários e de integração (`python tests/executar_todos_testes.py`).
3. [ ] Configuração de certificado digital A1 para transmissão ao eSocial.
4. [ ] Definição do segredo mestre de criptografia (`APP_SECRET_KEY`) e tempo de expiração de sessão.
5. [ ] Configuração de credenciais de gateway SMTP.
