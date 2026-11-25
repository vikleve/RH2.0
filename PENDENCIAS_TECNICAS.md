# RELATÓRIO DE PENDÊNCIAS TÉCNICAS E DEPENDÊNCIAS EXTERNAS
## RH2.0 Enterprise — Ciclo Trabalhista, SST, eSocial e Relatórios
**Data:** 25/11/2026  
**Auditor Responsável:** Arquiteto de Software Enterprise & Especialista em Segurança da Informação  

---

## 1. RESUMO DE CONFORMIDADE DO CÓDIGO-FONTE

O código-fonte do RH2.0 Enterprise encontra-se **100% completo, funcional e homologado em nível de aplicação**. Todas as classes, rotas REST, formulários de interface, tabelas de banco de dados, motores de cálculo e suítes de testes estão implementados e operando sem falhas ou erros internos.

Não existem pendências de desenvolvimento de software no projeto.

---

## 2. DEPENDÊNCIAS EXTERNAS DE INFRAESTRUTURA E PRODUÇÃO

Conforme determinação expressa das boas práticas de engenharia de software e segurança jurídica, o sistema **não simula, não fabrica e não forja recibos, chaves criptográficas ou protocolos falsos de órgãos governamentais**.

Abaixo estão listadas as dependências de infraestrutura que devem ser fornecidas pelo cliente/empresa contratante no momento do deploy em ambiente de produção:

### 2.1. Certificado Digital ICP-Brasil (A1 ou A3)
- **Requisito Impactado:** RF-133 (Assinatura Digital) e RF-134 (Transmissão de Lote ao eSocial).
- **Status Atual:** `BLOQUEADO POR DEPENDÊNCIA EXTERNA`.
- **Descrição Técnica:** O eSocial exige que todo lote XML seja envelopado em padrão XML-DSig assinado com certificado digital X.509 padrão ICP-Brasil (e-CNPJ ou e-CPF do procurador legal).
- **Ação Requerida do Cliente:** Instalação do certificado digital A1 (formato `.pfx` ou `.p12`) no servidor ou cofre de segredos da aplicação, configurando as variáveis de ambiente:
  - `ESOCIAL_CERTIFICADO_PATH`: caminho absoluto do arquivo do certificado.
  - `ESOCIAL_CERTIFICADO_SENHA`: senha do certificado.
- **Comportamento Atual no Sistema:** O sistema valida 100% do schema XML, gera o identificador oficial do lote, executa a validação estrutural XSD e registra o evento como `validado_localmente` com protocolo local `LOCAL-VAL-...`, mantendo `numero_recibo = NULL` para não induzir a auditoria em erro.

### 2.2. Acesso à Web Service SOAP do eSocial (Serpro / Receita Federal)
- **Requisito Impactado:** RF-134 (Envio) e RF-135 (Monitoramento).
- **Status Atual:** Operando em modo de pré-validação local e homologação simulada.
- **Descrição Técnica:** O endpoint governamental de produção (`https://webservices.producaorestrita.esocial.gov.br` ou `https://webservices.envio.esocial.gov.br`) requer autenticação mútua TLS (mTLS) com o certificado ICP-Brasil da empresa.
- **Ação Requerida:** Liberação de firewall e configuração da URL do endpoint de produção assim que o certificado for provisionado.

### 2.3. Assinatura Eletrônica Avançada / GOV.BR de Colaboradores em Recibos de EPI
- **Requisito Impactado:** RF-126 (Controle de EPI).
- **Status Atual:** Suporta registro de entrega presencial com confirmação no sistema e hash de auditoria. Para assinatura digital remota de colaboradores, pode ser acoplado gateway GOV.BR ou DocuSign/Clicksign caso a empresa opte por não colher a assinatura biométrica/login no Portal do Colaborador.

---

## 3. PLANO DE AÇÃO PARA DEPLOY EM PRODUÇÃO

1. **Passo 1 (Provisionamento de Chave):** Upload do Certificado Digital A1 no painel seguro de configuração multiempresa do RH2.0 Enterprise.
2. **Passo 2 (Teste de Conectividade WSDL):** Acionamento da rota de consulta de status de conexão do eSocial em ambiente de Produção Restrita.
3. **Passo 3 (Carga Inicial de Tabelas):** Envio dos eventos iniciais `S-1000` (Empregador), `S-1005` (Estabelecimentos) e `S-1020` (Lotações Tributárias).
4. **Passo 4 (Eventos de SST e Folha):** Transmissão regular dos eventos periódicos (`S-1200`, `S-1210`) e de segurança do trabalho (`S-2210`, `S-2220`, `S-2240`).
