# 03 — Modelo de Dados e Integridade no Neon PostgreSQL

**Projeto:** RH2.0 — Portal de Departamento Pessoal & Folha de Pagamento  
**Data:** 18/11/2026

---

## 1. Diagrama Entidade-Relacionamento (ERD) do Modelo Atual + Evolução Mínima

```mermaid
erDiagram
    USUARIOS ||--o{ SESSOES : "possui (ON DELETE CASCADE)"
    COLABORADORES ||--o{ DEPENDENTES : "possui (ON DELETE CASCADE)"
    COLABORADORES ||--o{ HISTORICO_ALTERACOES : "audita (ON DELETE CASCADE)"
    COLABORADORES ||--o{ FOLHAS_PAGAMENTO : "recebe (ON DELETE RESTRICT)"
    FOLHA_PARAMETROS ||--o{ FOLHAS_PAGAMENTO : "parametriza"
    FOLHAS_PAGAMENTO ||--o{ FOLHA_ITENS : "discrimina (ON DELETE CASCADE)"
    FOLHAS_PAGAMENTO ||--o{ FOLHA_HISTORICO : "audita (ON DELETE CASCADE)"

    USUARIOS {
        serial id PK
        text email UK
        text usuario UK
        text nome_completo
        text senha_hash
        text salt
        text perfil "administrador | analista_rh | operador_dp"
        text status "ativo | inativo"
        text empresa_id
        text criado_em
        text ultimo_login
    }

    SESSOES {
        text token PK
        integer usuario_id FK
        text criado_em
        text expira_em
        integer revogado "0 | 1"
    }

    AUDITORIA_AUTENTICACAO {
        serial id PK
        text evento "LOGIN_SUCESSO | LOGIN_FALHA | LOGOUT | BLOQUEIO_RATE_LIMIT"
        text identificador
        text ip_origem
        text detalhes
        text criado_em
    }

    COLABORADORES {
        serial id PK
        text matricula UK
        text nome_completo
        text cpf UK
        text rg
        text data_nascimento
        text telefone
        text email
        text logradouro
        text numero
        text bairro
        text cidade
        text uf
        text cep
        text data_admissao
        text cargo
        text setor
        numeric_15_2 salario_base
        text situacao "ativo | inativo"
        text empresa_id
        text criado_em
        text atualizado_em
    }

    DEPENDENTES {
        serial id PK
        integer colaborador_id FK
        text nome
        text cpf
        text parentesco
    }

    HISTORICO_ALTERACOES {
        serial id PK
        integer colaborador_id FK
        text data_hora
        text campo_alterado
        text valor_anterior
        text valor_novo
        text usuario_responsavel
    }

    FOLHA_PARAMETROS {
        serial id PK
        text codigo UK
        text descricao
        text razao_social "Novo (M06) - Dados da Empresa"
        text cnpj "Novo (M06) - Dados da Empresa"
        text endereco_empresa "Novo (M06) - Dados da Empresa"
        text vigencia_inicio
        text vigencia_fim
        numeric_6_2 horas_mensais_padrao
        integer dias_mes_padrao
        numeric_5_2 percentual_he_padrao
        numeric_5_2 percentual_he_extra
        numeric_5_2 percentual_adicional_noturno
        integer aplicar_reducao_noturna
        numeric_8_6 fator_reducao_noturna
        integer aplicar_inss
        integer aplicar_irrf
        numeric_5_2 aliquota_fgts
        numeric_15_2 teto_inss
        numeric_15_2 deducao_dependente_irrf
        integer ativo
        integer validado_por_profissional
        text criado_em
        text atualizado_em
    }

    FOLHAS_PAGAMENTO {
        serial id PK
        integer colaborador_id FK "UNIQUE(colaborador_id, competencia)"
        text competencia "Formato AAAA-MM"
        text periodo_inicio
        text periodo_fim
        text data_pagamento
        numeric_4_1 dias_trabalhados
        integer dias_mes
        numeric_6_2 horas_mensais_divisor
        numeric_15_2 salario_base_contratual
        numeric_15_2 salario_base_proporcional
        numeric_15_2 total_proventos
        numeric_15_2 total_descontos
        numeric_15_2 salario_liquido
        numeric_15_2 base_inss
        numeric_15_2 base_fgts
        numeric_15_2 valor_fgts_informativo
        numeric_15_2 base_irrf
        text situacao "rascunho | calculada | fechada | cancelada"
        text observacoes
        integer parametro_id FK
        text criado_por
        text criado_em
        text atualizado_por
        text atualizado_em
        text fechado_por
        text fechado_em
    }

    FOLHA_ITENS {
        serial id PK
        integer folha_id FK
        text codigo_evento
        text descricao
        text tipo "provento | desconto | informativo"
        numeric_12_4 referencia "Corrigido de REAL para NUMERIC(12,4)"
        text unidade_referencia
        numeric_15_4 valor_unitario "Corrigido de REAL para NUMERIC(15,4)"
        numeric_15_2 valor_total "Corrigido de REAL para NUMERIC(15,2)"
        text origem "sistema | calculado | manual | importado"
        text memoria_calculo
        text criado_em
    }

    FOLHA_HISTORICO {
        serial id PK
        integer folha_id FK
        text data_hora
        text acao
        text descricao
        text dados_anteriores
        text dados_novos
        text usuario_responsavel
    }
```

---

## 2. Mapeamento dos Dados Obrigatórios (Seção 2.3)

Seguindo a diretriz de **não criar tabelas desnecessárias** e aproveitar os modelos já criados pelos alunos:

| Item Exigido (Seção 2.3) | Tabela Existente no Projeto | Situação e Ajuste Planejado |
|---|---|---|
| 1. Empresas e suas configurações | `folha_parametros` ( + `empresa_id` em `colaboradores`/`usuarios`) | **Complementar** com 3 colunas idempotentes em `folha_parametros` (`razao_social`, `cnpj`, `endereco_empresa`) para persistir os dados da empresa exibidos no holerite sem criar tabela extra desnecessária. |
| 2. Usuários e permissões | `usuarios` e `sessoes` | **Aproveitar** (`perfil IN ('administrador', 'analista_rh', 'operador_dp')`). |
| 3. Funcionários | `colaboradores` e `dependentes` | **Aproveitar** integralmente. |
| 4. Vínculos empregatícios | `colaboradores` (`matricula`, `data_admissao`, `situacao`) | **Aproveitar** integralmente. |
| 5. Dados contratuais | `colaboradores` (`cargo`, `setor`, `salario_base`) | **Aproveitar** integralmente. |
| 6. Histórico salarial | `historico_alteracoes` (`campo_alterado = 'Salário-base'`) | **Aproveitar** integralmente (já grava `valor_anterior` e `valor_novo` a cada alteração salarial). |
| 7. Competências | `folhas_pagamento.competencia` (`AAAA-MM`) | **Aproveitar** com constraint `UNIQUE (colaborador_id, competencia)`. |
| 8. Eventos e lançamentos | `folha_itens` + `catalogo_eventos.py` | **Corrigir** precisão de `REAL` para `NUMERIC` no PostgreSQL. |
| 9. Parâmetros de cálculo | `folha_parametros` | **Aproveitar** e liberar edição persistida pela interface. |
| 10. Resultados das folhas | `folhas_pagamento` | **Aproveitar** e corrigir serialização JSON de `Decimal` para `float`. |
| 11. Proventos | `folha_itens` (`tipo = 'provento'`) + `folhas_pagamento.total_proventos` | **Aproveitar** integralmente. |
| 12. Descontos | `folha_itens` (`tipo = 'desconto'`) + `folhas_pagamento.total_descontos` | **Aproveitar** integralmente. |
| 13. Bases de cálculo e incidências | `folhas_pagamento` (`base_inss`, `base_fgts`, `base_irrf`, `valor_fgts_informativo`) + `folha_itens` (`tipo = 'informativo'`) | **Aproveitar** integralmente. |
| 14. Estados de processamento | `folhas_pagamento.situacao` (`rascunho`, `calculada`, `fechada`, `cancelada`) | **Aproveitar** integralmente. |
| 15. Fechamentos | `folhas_pagamento` (`fechado_por`, `fechado_em`) + `folha_historico` (`acao = 'FECHAMENTO'`) | **Aproveitar** e adicionar endpoint de fechamento consolidado da competência. |
| 16. Demonstrativos e referências | `folhas_pagamento` + `folha_itens` (`memoria_calculo`) | **Aproveitar** e alimentar cabeçalho do holerite com os dados da empresa persistidos. |
| 17. Histórico de alterações | `historico_alteracoes` e `folha_historico` | **Aproveitar** integralmente. |
| 18. Informações de auditoria | `auditoria_autenticacao`, `historico_alteracoes`, `folha_historico` | **Aproveitar** integralmente. |

---

## 3. Precisão Monetária e Máquina de Estados do Fechamento (Seções 6.1 e 6.2)

### 3.1. Valores Monetários (`Decimal` e `NUMERIC`)
- No código Python (`backend/folha_calculos.py`), todos os cálculos já utilizam `decimal.Decimal` com quantização `Decimal("0.01")` e arredondamento `ROUND_HALF_UP`.
- No banco PostgreSQL (Neon), `colaboradores.salario_base`, `folha_parametros.*` e `folhas_pagamento.*` já utilizam `NUMERIC(15,2)`.
- **Correção obrigatória (`migrations/006_precisao_monetaria_e_empresa.sql`):**
  - Alterar `folha_itens.referencia` para `NUMERIC(12,4)`, `folha_itens.valor_unitario` para `NUMERIC(15,4)` e `folha_itens.valor_total` para `NUMERIC(15,2)` no PostgreSQL.
  - Garantir conversão determinística de `Decimal` para `float` (ou serializador JSON seguro) na saída de `FolhaService` e `ApiColaboradorHandler._enviar_json`.

### 3.2. Máquina de Estados da Folha e da Competência
```mermaid
stateDiagram-v2
    [*] --> rascunho : Criação preliminar
    [*] --> calculada : POST /api/folha (Cálculo inicial)
    rascunho --> calculada : Recálculo (PUT /api/folha/:id)
    calculada --> calculada : Ajuste de eventos e recálculo
    calculada --> fechada : Fechamento (POST /api/folha/:id/fechar)
    fechada --> calculada : Reabertura justificada (POST /api/folha/:id/reabrir)
    rascunho --> cancelada : Cancelamento (DELETE /api/folha/:id)
    calculada --> cancelada : Cancelamento (DELETE /api/folha/:id)
```

**Regras de Integridade do Fechamento:**
1. **Prevenção de Duplicidade:** Constraint no banco `CONSTRAINT unq_colab_competencia UNIQUE (colaborador_id, competencia)`.
2. **Imutabilidade de Folha Fechada:** Qualquer tentativa de `PUT /api/folha/<id>`, `POST /api/folha/<id>/calcular`, `POST /api/folha/<id>/fechar` ou `DELETE /api/folha/<id>` quando `situacao == 'fechada'` levanta `FolhaBloqueadaException` (HTTP 403).
3. **Preservação de Histórico Salarial na Folha:** Quando uma folha é calculada, `salario_base_contratual` e `salario_base_proporcional` são gravados em `folhas_pagamento`. Uma alteração posterior no cadastro do colaborador (`colaboradores.salario_base`) **não altera nem invalida** folhas já calculadas ou fechadas.
4. **Reabertura Controlada:** Só é permitida mediante `motivo` com no mínimo 5 caracteres, gravando registro imutável em `folha_historico` com `data_hora`, `acao='REABERTURA'`, `descricao` e `usuario_responsavel`.

---

## 4. Estratégia de Migrações Versionadas (Seção 6.3)

- As migrações existentes (`001` a `005`) serão preservadas intactas.
- Será adicionada a migração **`migrations/006_precisao_monetaria_e_empresa.sql`**, 100% não-destrutiva e idempotente:
  - Adiciona `razao_social`, `cnpj` e `endereco_empresa` em `folha_parametros` (`ADD COLUMN IF NOT EXISTS`).
  - Converte as colunas `referencia`, `valor_unitario` e `valor_total` de `folha_itens` de `REAL` para `NUMERIC` (`ALTER COLUMN ... TYPE NUMERIC(...) USING ...`).
  - Cria tabela de controle `schema_migrations (versao TEXT PRIMARY KEY, aplicado_em TEXT NOT NULL)` para rastrear quais migrações já foram aplicadas no Neon e evitar reexecução desnecessária de DDL a cada requisição serverless.
- **Ressalva sobre Backups no Neon:** O recurso de restauração ponto no tempo (Point-in-Time Restore / History retention) no Neon depende do plano contratado da conta (Free Tier possui janela limitada de histórico, tipicamente 24h a 7 dias conforme a versão da conta). Não se deve presumir backup externo automático sem verificação no painel do Neon; por isso, todas as migrações são estritamente aditivas (sem `DROP` ou `TRUNCATE`).
