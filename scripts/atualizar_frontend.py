# -*- coding: utf-8 -*-
"""
Script de atualização estruturada do frontend/index.html para a
Plataforma de Gestão do Ciclo Trabalhista (Módulos 01 a 20).
"""
import re

SIDEBAR_HTML = """
    <!-- Layout Unificado da Plataforma: Sidebar + Conteúdo -->
    <div class="platform-layout">
      <!-- Barra Lateral de Navegação da Plataforma (Módulos 01 a 20) -->
      <aside class="platform-sidebar" id="platform-sidebar">
        <div class="sidebar-nav">
          <div class="sidebar-section">
            <div class="sidebar-section-title">Estratégico & Indicadores</div>
            <div class="sidebar-menu">
              <button class="sidebar-btn active" data-view="dashboard" id="btn-menu-dashboard" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="3" width="7" height="9"></rect>
                  <rect x="14" y="3" width="7" height="5"></rect>
                  <rect x="14" y="12" width="7" height="9"></rect>
                  <rect x="3" y="16" width="7" height="5"></rect>
                </svg>
                <span>Dashboard &amp; BI</span>
              </button>
              <button class="sidebar-btn" data-view="pendencias" id="btn-menu-pendencias" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                  <line x1="12" y1="9" x2="12" y2="13"></line>
                  <line x1="12" y1="17" x2="12.01" y2="17"></line>
                </svg>
                <span>Central de Pendências</span>
                <span class="sidebar-badge" id="badge-pendencias-count">0</span>
              </button>
            </div>
          </div>

          <div class="sidebar-section">
            <div class="sidebar-section-title">Ciclo do Colaborador</div>
            <div class="sidebar-menu">
              <button class="sidebar-btn" data-view="colaboradores" id="btn-menu-colaboradores" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                  <circle cx="9" cy="7" r="4"></circle>
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                  <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                </svg>
                <span>Colaboradores (M01)</span>
              </button>
              <button class="sidebar-btn" data-view="admissoes" id="btn-menu-admissoes" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                  <circle cx="8.5" cy="7" r="4"></circle>
                  <line x1="20" y1="8" x2="20" y2="14"></line>
                  <line x1="23" y1="11" x2="17" y2="11"></line>
                </svg>
                <span>Admissões (M02)</span>
              </button>
              <button class="sidebar-btn" data-view="ponto" id="btn-menu-ponto" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <polyline points="12 6 12 12 16 14"></polyline>
                </svg>
                <span>Jornada &amp; Ponto (M03)</span>
              </button>
              <button class="sidebar-btn" data-view="ferias" id="btn-menu-ferias" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                  <line x1="16" y1="2" x2="16" y2="6"></line>
                  <line x1="8" y1="2" x2="8" y2="6"></line>
                  <line x1="3" y1="10" x2="21" y2="10"></line>
                </svg>
                <span>Férias &amp; Abono (M06)</span>
              </button>
              <button class="sidebar-btn" data-view="afastamentos" id="btn-menu-afastamentos" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
                </svg>
                <span>Afastamentos (M07)</span>
              </button>
              <button class="sidebar-btn" data-view="rescisoes" id="btn-menu-rescisoes" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                  <circle cx="8.5" cy="7" r="4"></circle>
                  <line x1="18" y1="8" x2="23" y2="13"></line>
                  <line x1="23" y1="8" x2="18" y2="13"></line>
                </svg>
                <span>Rescisões (M11)</span>
              </button>
            </div>
          </div>

          <div class="sidebar-section">
            <div class="sidebar-section-title">Folha &amp; Remuneração</div>
            <div class="sidebar-menu">
              <button class="sidebar-btn" data-view="folha" id="btn-menu-folha" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="2" y="4" width="20" height="16" rx="2"></rect>
                  <line x1="2" y1="10" x2="22" y2="10"></line>
                  <line x1="12" y1="14" x2="12" y2="18"></line>
                  <line x1="8" y1="18" x2="16" y2="18"></line>
                </svg>
                <span>Folha Mensal (M09/10)</span>
              </button>
              <button class="sidebar-btn" data-view="integracoes" id="btn-menu-integracoes" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="2" y="5" width="20" height="14" rx="2"></rect>
                  <line x1="2" y1="10" x2="22" y2="10"></line>
                </svg>
                <span>Bancos / CNAB 240 (M18)</span>
              </button>
            </div>
          </div>

          <div class="sidebar-section">
            <div class="sidebar-section-title">Compliance &amp; Segurança</div>
            <div class="sidebar-menu">
              <button class="sidebar-btn" data-view="sst" id="btn-menu-sst" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
                </svg>
                <span>SST &amp; Medicina (M13)</span>
              </button>
              <button class="sidebar-btn" data-view="esocial" id="btn-menu-esocial" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                  <polyline points="14 2 14 8 20 8"></polyline>
                  <line x1="16" y1="13" x2="8" y2="13"></line>
                  <line x1="16" y1="17" x2="8" y2="17"></line>
                  <polyline points="10 9 9 9 8 9"></polyline>
                </svg>
                <span>eSocial &amp; Obrigações (M12)</span>
              </button>
            </div>
          </div>

          <div class="sidebar-section">
            <div class="sidebar-section-title">Governança &amp; Sistema</div>
            <div class="sidebar-menu">
              <button class="sidebar-btn" data-view="auditoria" id="btn-menu-auditoria" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                </svg>
                <span>Auditoria &amp; Logs (M20)</span>
              </button>
              <button class="sidebar-btn" data-view="multiempresa" id="btn-menu-multiempresa" type="button">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                  <polyline points="9 22 9 12 15 12 15 22"></polyline>
                </svg>
                <span>Multiempresa (M17)</span>
              </button>
            </div>
          </div>
        </div>
      </aside>

      <!-- Conteúdo Principal da Plataforma -->
      <main class="main-content platform-main-content">
"""

VIEWS_DASHBOARD_AND_PENDENCIAS = """
        <!-- ============================================================ -->
        <!-- VISÃO DASHBOARD & BI (MÓDULOS 19 E 20)                        -->
        <!-- ============================================================ -->
        <div id="view-modulo-dashboard" class="platform-view">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Painel Executivo &amp; Indicadores BI</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Métricas consolidadas em tempo real com fórmulas oficiais (RF-181 a RF-190)</p>
            </div>
            <button id="btn-atualizar-indicadores" class="btn btn-outline" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
              </svg>
              Atualizar Indicadores
            </button>
          </div>

          <section class="metrics-grid">
            <div class="metric-card">
              <div class="metric-icon metric-icon-blue">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                  <circle cx="9" cy="7" r="4"></circle>
                </svg>
              </div>
              <div class="metric-info">
                <span class="metric-label">Colaboradores Ativos</span>
                <span class="metric-value" id="kpi-total-ativos">--</span>
                <span class="text-xs text-muted">Contratos CLT e Estágio</span>
              </div>
            </div>

            <div class="metric-card">
              <div class="metric-icon" style="background-color: #fef3c7; color: #d97706;">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"></polyline>
                  <polyline points="17 6 23 6 23 12"></polyline>
                </svg>
              </div>
              <div class="metric-info">
                <span class="metric-label">Taxa de Turnover</span>
                <span class="metric-value" id="kpi-turnover">0.00%</span>
                <span class="kpi-formula-tag">((Adm+Desl)/2/Ativos)*100</span>
              </div>
            </div>

            <div class="metric-card">
              <div class="metric-icon" style="background-color: #fee2e2; color: #dc2626;">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="8" x2="12" y2="12"></line>
                  <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
              </div>
              <div class="metric-info">
                <span class="metric-label">Taxa de Absenteísmo</span>
                <span class="metric-value" id="kpi-absenteismo">0.00%</span>
                <span class="kpi-formula-tag">(Horas Não Trab / Previstas)*100</span>
              </div>
            </div>

            <div class="metric-card">
              <div class="metric-icon" style="background-color: #ede9fe; color: #7c3aed;">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                </svg>
              </div>
              <div class="metric-info">
                <span class="metric-label">Pendências em Aberto</span>
                <span class="metric-value" id="kpi-pendencias-abertas">0</span>
                <span class="text-xs text-muted" id="kpi-pendencias-criticas">0 críticas</span>
              </div>
            </div>
          </section>

          <section class="table-card mt-3">
            <div class="table-card-header">
              <h3 style="font-size: 1.1rem; font-weight: 600;">Status Operacional da Plataforma — V1 &amp; Vigência 2026</h3>
            </div>
            <div class="p-3" style="padding: 1.25rem;">
              <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem;">
                <div style="border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; background: var(--bg-card);">
                  <strong style="color: var(--primary); display: block; margin-bottom: 0.25rem;">Parâmetros Legais 2026</strong>
                  <div style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5;">
                    &bull; Salário Mínimo: <strong>R$ 1.621,00</strong><br>
                    &bull; Teto INSS: <strong>R$ 8.475,55</strong><br>
                    &bull; Dedução Dependente IRRF: <strong>R$ 189,59</strong><br>
                    &bull; Desconto Simplificado IRRF: <strong>R$ 607,20</strong><br>
                    &bull; Redução Lei 15.270/2025: <strong>Ativa</strong>
                  </div>
                </div>
                <div style="border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; background: var(--bg-card);">
                  <strong style="color: #16a34a; display: block; margin-bottom: 0.25rem;">Compliance eSocial &amp; SST</strong>
                  <div style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5;">
                    &bull; Eventos Iniciais e Tabelas: <strong>S-1000 a S-1020</strong><br>
                    &bull; Eventos Não Periódicos: <strong>S-2190 a S-2299</strong><br>
                    &bull; Eventos SST: <strong>S-2210, S-2220, S-2240</strong><br>
                    &bull; Folha e Fechamento: <strong>S-1200, S-1210, S-1299</strong>
                  </div>
                </div>
                <div style="border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; background: var(--bg-card);">
                  <strong style="color: #ea580c; display: block; margin-bottom: 0.25rem;">Segurança &amp; Governança</strong>
                  <div style="font-size: 0.85rem; color: var(--text-muted); line-height: 1.5;">
                    &bull; Segregação de Funções: <strong>RN-080 Ativa</strong><br>
                    &bull; Trilha de Auditoria Geral: <strong>RT-01 Ativa</strong><br>
                    &bull; Exclusão Lógica e LGPD: <strong>RF-009 / RT-02</strong><br>
                    &bull; Dual-Mode: <strong>SQLite / PostgreSQL</strong>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO CENTRAL DE PENDÊNCIAS (RF-151 A RF-160, RN-076)        -->
        <!-- ============================================================ -->
        <div id="view-modulo-pendencias" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Central de Pendências &amp; Workflow Operacional</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Monitoramento contínuo, SLAs e tratativa de inconsistências operacionais</p>
            </div>
            <div style="display: flex; gap: 0.5rem;">
              <button id="btn-scanner-pendencias" class="btn btn-primary" type="button">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="23 4 23 10 17 10"></polyline>
                  <polyline points="1 20 1 14 7 14"></polyline>
                  <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                </svg>
                Executar Varredura Automática
              </button>
            </div>
          </div>

          <div class="filters-card">
            <div class="filters-row">
              <div class="form-group">
                <label for="filtro-pendencia-status">Status</label>
                <select id="filtro-pendencia-status" class="form-control">
                  <option value="">Todos</option>
                  <option value="PENDENTE" selected>Pendente</option>
                  <option value="EM_ANALISE">Em Análise</option>
                  <option value="RESOLVIDO">Resolvido</option>
                  <option value="DISPENSADO">Dispensado</option>
                </select>
              </div>
              <div class="form-group">
                <label for="filtro-pendencia-severidade">Severidade</label>
                <select id="filtro-pendencia-severidade" class="form-control">
                  <option value="">Todas</option>
                  <option value="CRITICA">Crítica</option>
                  <option value="ALTA">Alta</option>
                  <option value="MEDIA">Média</option>
                  <option value="BAIXA">Baixa</option>
                </select>
              </div>
            </div>
          </div>

          <section class="table-card mt-3">
            <div class="table-responsive">
              <table class="data-table" id="tabela-pendencias">
                <thead>
                  <tr>
                    <th>Severidade</th>
                    <th>Tipo</th>
                    <th>Título / Ocorrência</th>
                    <th>Colaborador / Alvo</th>
                    <th>Prazo / SLA</th>
                    <th>Status</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody id="tbody-pendencias">
                  <tr>
                    <td colspan="7" class="text-center text-muted" style="padding: 2rem;">Carregando pendências...</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
"""

VIEWS_AFTER_COLABORADORES = """
        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 2: ADMISSÕES & CONTRATOS (RF-011 A RF-020)    -->
        <!-- ============================================================ -->
        <div id="view-modulo-admissoes" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Gestão de Admissões &amp; Checklist Documental</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Workflow admissional, validação documental e aprovação com segregação de funções (RN-080)</p>
            </div>
            <button id="btn-abrir-nova-admissao" class="btn btn-primary" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              Nova Admissão
            </button>
          </div>

          <section class="table-card">
            <div class="table-responsive">
              <table class="data-table" id="tabela-admissoes">
                <thead>
                  <tr>
                    <th>Candidato / Colaborador</th>
                    <th>CPF</th>
                    <th>Cargo Proposto</th>
                    <th>Salário Proposto</th>
                    <th>Data Admissão</th>
                    <th>Checklist (Itens)</th>
                    <th>Status</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody id="tbody-admissoes">
                  <tr>
                    <td colspan="8" class="text-center text-muted" style="padding: 2rem;">Carregando propostas de admissão...</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 3: JORNADA & PONTO ELETRÔNICO (RF-021 A RF-040)-->
        <!-- ============================================================ -->
        <div id="view-modulo-ponto" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Controle de Jornada, Ponto &amp; Banco de Horas</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Espelho de ponto mensal, marcações, horas extras 50%/100% e adicional noturno</p>
            </div>
            <div style="display: flex; gap: 0.5rem;">
              <button id="btn-abrir-bater-ponto" class="btn btn-primary" type="button">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <polyline points="12 6 12 12 16 14"></polyline>
                </svg>
                Registrar Batida de Ponto
              </button>
              <button id="btn-abrir-ajuste-ponto" class="btn btn-outline" type="button">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
                Solicitar Ajuste de Ponto
              </button>
            </div>
          </div>

          <div class="filters-card">
            <div class="filters-row">
              <div class="form-group">
                <label for="ponto-colaborador-select">Colaborador</label>
                <select id="ponto-colaborador-select" class="form-control">
                  <option value="">Selecione um colaborador...</option>
                </select>
              </div>
              <div class="form-group">
                <label for="ponto-competencia-input">Competência (Ano-Mês)</label>
                <input type="month" id="ponto-competencia-input" class="form-control" value="2026-03">
              </div>
              <div class="form-group" style="align-self: flex-end;">
                <button id="btn-carregar-espelho-ponto" class="btn btn-outline" type="button">Carregar Espelho</button>
              </div>
            </div>
          </div>

          <section class="metrics-grid mt-2">
            <div class="metric-card">
              <div class="metric-info">
                <span class="metric-label">Horas Trabalhadas</span>
                <span class="metric-value" id="ponto-tot-normais">0h 00m</span>
              </div>
            </div>
            <div class="metric-card">
              <div class="metric-info">
                <span class="metric-label">Horas Extras 50%</span>
                <span class="metric-value" id="ponto-tot-he50" style="color: #2563eb;">0h 00m</span>
              </div>
            </div>
            <div class="metric-card">
              <div class="metric-info">
                <span class="metric-label">Horas Extras 100%</span>
                <span class="metric-value" id="ponto-tot-he100" style="color: #d97706;">0h 00m</span>
              </div>
            </div>
            <div class="metric-card">
              <div class="metric-info">
                <span class="metric-label">Adicional Noturno</span>
                <span class="metric-value" id="ponto-tot-noturno" style="color: #7c3aed;">0h 00m</span>
              </div>
            </div>
            <div class="metric-card">
              <div class="metric-info">
                <span class="metric-label">Atrasos &amp; Faltas</span>
                <span class="metric-value" id="ponto-tot-faltas" style="color: #dc2626;">0h 00m</span>
              </div>
            </div>
          </section>

          <section class="table-card mt-3">
            <div class="table-card-header">
              <h3 style="font-size: 1.1rem; font-weight: 600;">Espelho de Ponto Oficial do Período</h3>
            </div>
            <div class="table-responsive">
              <table class="data-table" id="tabela-espelho-ponto">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Dia</th>
                    <th>Entrada 1</th>
                    <th>Saída 1 (Alm.)</th>
                    <th>Entrada 2 (Ret.)</th>
                    <th>Saída 2</th>
                    <th>Total Trab.</th>
                    <th>Saldo Diário</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody id="tbody-espelho-ponto">
                  <tr>
                    <td colspan="9" class="text-center text-muted" style="padding: 2rem;">Selecione um colaborador para ver o espelho de ponto.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 6: FÉRIAS & ABONO (RF-051 A RF-060)           -->
        <!-- ============================================================ -->
        <div id="view-modulo-ferias" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Gestão de Férias &amp; Abono Pecuniário</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Controle de períodos aquisitivos/concessivos, cálculo de 1/3 e regras de antecipação CLT</p>
            </div>
            <button id="btn-abrir-programar-ferias" class="btn btn-primary" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              Programar Férias
            </button>
          </div>

          <section class="table-card">
            <div class="table-responsive">
              <table class="data-table" id="tabela-ferias">
                <thead>
                  <tr>
                    <th>Colaborador</th>
                    <th>Período Aquisitivo</th>
                    <th>Limite Concessivo</th>
                    <th>Início Gozo</th>
                    <th>Fim Gozo</th>
                    <th>Dias Gozo</th>
                    <th>Abono (Dias)</th>
                    <th>Adiantamento 13º</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody id="tbody-ferias">
                  <tr>
                    <td colspan="9" class="text-center text-muted" style="padding: 2rem;">Carregando histórico e programação de férias...</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 7: AFASTAMENTOS & ESTABILIDADE (RF-061 A RF-070)-->
        <!-- ============================================================ -->
        <div id="view-modulo-afastamentos" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Afastamentos, Licenças &amp; Estabilidade Legal</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Controle de 15 dias empresa / INSS, CID-10, ASO de retorno e travas de estabilidade provisória</p>
            </div>
            <button id="btn-abrir-novo-afastamento" class="btn btn-primary" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              Registrar Afastamento
            </button>
          </div>

          <section class="table-card">
            <div class="table-responsive">
              <table class="data-table" id="tabela-afastamentos">
                <thead>
                  <tr>
                    <th>Colaborador</th>
                    <th>Tipo / Motivo</th>
                    <th>CID-10</th>
                    <th>Início</th>
                    <th>Término Previsto</th>
                    <th>Dias Empresa</th>
                    <th>Dias INSS</th>
                    <th>Estabilidade Pós-Retorno</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody id="tbody-afastamentos">
                  <tr>
                    <td colspan="9" class="text-center text-muted" style="padding: 2rem;">Carregando afastamentos cadastrados...</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
"""

VIEWS_AFTER_FOLHA = """
        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 11: RESCISÕES CONTRATUAIS (RF-106 A RF-120)  -->
        <!-- ============================================================ -->
        <div id="view-modulo-rescisoes" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Rescisão Contratual &amp; Verbas Rescisórias 2026</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Cálculo do TRCT oficial, multa FGTS (40%/20%), aviso prévio proporcional e prazo legal de 10 dias (CLT art. 477)</p>
            </div>
            <button id="btn-abrir-calcular-rescisao" class="btn btn-primary" type="button">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              Calcular Nova Rescisão
            </button>
          </div>

          <section class="table-card">
            <div class="table-responsive">
              <table class="data-table" id="tabela-rescisoes">
                <thead>
                  <tr>
                    <th>Colaborador</th>
                    <th>Tipo de Rescisão</th>
                    <th>Data Aviso</th>
                    <th>Data Desligamento</th>
                    <th>Prazo Pagamento (10d)</th>
                    <th>Total Verbas</th>
                    <th>Multa FGTS</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody id="tbody-rescisoes">
                  <tr>
                    <td colspan="8" class="text-center text-muted" style="padding: 2rem;">Carregando rescisões processadas...</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 13: SST — SAÚDE E SEGURANÇA (RF-121 A RF-130)-->
        <!-- ============================================================ -->
        <div id="view-modulo-sst" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">SST — Saúde &amp; Segurança do Trabalho</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Gestão de ASO, Fichas de EPIs com verificação de CA vencido (RN-039), Treinamentos e Emissão de CAT</p>
            </div>
            <div style="display: flex; gap: 0.5rem;">
              <button id="btn-abrir-novo-aso" class="btn btn-outline" type="button">Novo ASO</button>
              <button id="btn-abrir-entrega-epi" class="btn btn-outline" type="button">Entregar EPI</button>
              <button id="btn-abrir-nova-cat" class="btn btn-primary" type="button">Emitir CAT</button>
            </div>
          </div>

          <!-- SST Sub-abas -->
          <div style="display: flex; gap: 0.5rem; margin-bottom: 1.25rem; border-bottom: 2px solid var(--border-color);">
            <button id="sst-tab-btn-aso" class="nav-module-tab active" type="button">ASO &amp; Exames</button>
            <button id="sst-tab-btn-epi" class="nav-module-tab" type="button">EPIs &amp; Fichas</button>
            <button id="sst-tab-btn-treinamentos" class="nav-module-tab" type="button">Treinamentos NRs</button>
            <button id="sst-tab-btn-cat" class="nav-module-tab" type="button">CATs Emitidas</button>
          </div>

          <div id="sst-painel-aso" class="sst-painel">
            <section class="table-card">
              <div class="table-responsive">
                <table class="data-table" id="tabela-sst-asos">
                  <thead>
                    <tr>
                      <th>Colaborador</th>
                      <th>Tipo ASO</th>
                      <th>Data Realização</th>
                      <th>Validade</th>
                      <th>Aptidão</th>
                      <th>Médico / CRM</th>
                      <th>Exames Complementares</th>
                    </tr>
                  </thead>
                  <tbody id="tbody-sst-asos">
                    <tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Carregando ASOs...</td></tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <div id="sst-painel-epi" class="sst-painel hidden">
            <section class="table-card">
              <div class="table-responsive">
                <table class="data-table" id="tabela-sst-epis">
                  <thead>
                    <tr>
                      <th>Colaborador</th>
                      <th>EPI / Descrição</th>
                      <th>Número CA</th>
                      <th>Validade do CA</th>
                      <th>Data Entrega</th>
                      <th>Status Assinatura</th>
                    </tr>
                  </thead>
                  <tbody id="tbody-sst-epis">
                    <tr><td colspan="6" class="text-center text-muted" style="padding: 2rem;">Carregando entregas de EPIs...</td></tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <div id="sst-painel-treinamentos" class="sst-painel hidden">
            <section class="table-card">
              <div class="table-responsive">
                <table class="data-table" id="tabela-sst-treinamentos">
                  <thead>
                    <tr>
                      <th>Nome do Treinamento / NR</th>
                      <th>Carga Horária</th>
                      <th>Validade (Meses)</th>
                      <th>Reciclagem Obrigatória</th>
                      <th>Total Participantes</th>
                    </tr>
                  </thead>
                  <tbody id="tbody-sst-treinamentos">
                    <tr><td colspan="5" class="text-center text-muted" style="padding: 2rem;">Carregando treinamentos...</td></tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <div id="sst-painel-cat" class="sst-painel hidden">
            <section class="table-card">
              <div class="table-responsive">
                <table class="data-table" id="tabela-sst-cats">
                  <thead>
                    <tr>
                      <th>Número CAT</th>
                      <th>Colaborador</th>
                      <th>Tipo Acidente</th>
                      <th>Data / Hora</th>
                      <th>Parte do Corpo / CID</th>
                      <th>Status eSocial</th>
                    </tr>
                  </thead>
                  <tbody id="tbody-sst-cats">
                    <tr><td colspan="6" class="text-center text-muted" style="padding: 2rem;">Carregando CATs...</td></tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 12: ESOCIAL & OBRIGAÇÕES (RF-131 A RF-140)   -->
        <!-- ============================================================ -->
        <div id="view-modulo-esocial" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Obrigações Legais &amp; Central eSocial</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Geração e mensageria de lotes XML (Eventos Iniciais, Tabelas, Não Periódicos, SST e Folha)</p>
            </div>
            <div style="display: flex; gap: 0.5rem;">
              <button id="btn-esocial-transmitir" class="btn btn-primary" type="button">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="22" y1="2" x2="11" y2="13"></line>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                </svg>
                Transmitir Lote ao eSocial
              </button>
            </div>
          </div>

          <section class="table-card">
            <div class="table-responsive">
              <table class="data-table" id="tabela-esocial-eventos">
                <thead>
                  <tr>
                    <th>Evento</th>
                    <th>Tipo</th>
                    <th>Competência / Data</th>
                    <th>Colaborador / Alvo</th>
                    <th>Status Mensageria</th>
                    <th>Protocolo / Recibo</th>
                    <th>Ações</th>
                  </tr>
                </thead>
                <tbody id="tbody-esocial-eventos">
                  <tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Carregando eventos do eSocial...</td></tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 18: INTEGRAÇÕES & BANCOS (RF-097, RF-178)    -->
        <!-- ============================================================ -->
        <div id="view-modulo-integracoes" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Integrações Bancárias — Remessa CNAB 240</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Geração oficial de arquivo bancário padrão FEBRABAN para pagamento de salários em conta</p>
            </div>
          </div>

          <div class="filters-card">
            <h3 style="font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem;">Gerador de Remessa de Salários</h3>
            <div class="filters-row">
              <div class="form-group">
                <label for="cnab-banco-select">Banco do Convênio</label>
                <select id="cnab-banco-select" class="form-control">
                  <option value="001">001 — Banco do Brasil</option>
                  <option value="341">341 — Banco Itaú</option>
                  <option value="237">237 — Banco Bradesco</option>
                  <option value="033">033 — Santander Brasil</option>
                  <option value="104">104 — Caixa Econômica Federal</option>
                </select>
              </div>
              <div class="form-group">
                <label for="cnab-competencia-input">Competência da Folha</label>
                <input type="month" id="cnab-competencia-input" class="form-control" value="2026-03">
              </div>
              <div class="form-group">
                <label for="cnab-data-pagamento">Data de Pagamento</label>
                <input type="date" id="cnab-data-pagamento" class="form-control" value="2026-04-05">
              </div>
              <div class="form-group" style="align-self: flex-end;">
                <button id="btn-gerar-cnab240" class="btn btn-primary" type="button">Gerar Remessa CNAB 240</button>
              </div>
            </div>
          </div>

          <section class="table-card mt-3">
            <div class="table-card-header" style="display: flex; justify-content: space-between; align-items: center;">
              <h3 style="font-size: 1.1rem; font-weight: 600;">Prévia do Lote de Pagamento Gerado</h3>
              <button id="btn-download-cnab" class="btn btn-outline btn-sm hidden" type="button">Download Arquivo .REM</button>
            </div>
            <div class="p-3" style="padding: 1.25rem;">
              <div id="cnab-resumo-lote" style="margin-bottom: 1rem; color: var(--text-muted); font-size: 0.9rem;">
                Selecione os parâmetros e clique em "Gerar Remessa CNAB 240" para consolidar as contas bancárias dos colaboradores.
              </div>
              <pre id="cnab-conteudo-preview" style="background: #0f172a; color: #38bdf8; padding: 1rem; border-radius: 6px; font-size: 0.75rem; overflow-x: auto; max-height: 280px; display: none;"></pre>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 20: AUDITORIA & RASTREABILIDADE (RT-01, RF-191)-->
        <!-- ============================================================ -->
        <div id="view-modulo-auditoria" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Trilha de Auditoria &amp; Rastreabilidade Geral</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Registro imutável de todas as operações, alterações, cálculos e acessos ao sistema (RT-01)</p>
            </div>
            <button id="btn-atualizar-auditoria" class="btn btn-outline" type="button">Atualizar Trilha</button>
          </div>

          <section class="table-card">
            <div class="table-responsive">
              <table class="data-table" id="tabela-auditoria">
                <thead>
                  <tr>
                    <th>Data / Hora</th>
                    <th>Usuário Operador</th>
                    <th>Ação</th>
                    <th>Recurso</th>
                    <th>IP Origem</th>
                    <th>Detalhes da Operação</th>
                  </tr>
                </thead>
                <tbody id="tbody-auditoria">
                  <tr><td colspan="6" class="text-center text-muted" style="padding: 2rem;">Carregando registros de auditoria...</td></tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <!-- ============================================================ -->
        <!-- VISÃO DO MÓDULO 17: MULTIEMPRESA & GOVERNANÇA (RF-171 A RF-180)-->
        <!-- ============================================================ -->
        <div id="view-modulo-multiempresa" class="platform-view hidden">
          <div class="view-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
            <div>
              <h2 style="font-size: 1.5rem; font-weight: 700; color: var(--text-main); margin-bottom: 0.25rem;">Gestão Multiempresa, Filiais &amp; Centros de Custo</h2>
              <p style="color: var(--text-muted); font-size: 0.88rem;">Estrutura corporativa, isolamento tenant e governança descentralizada</p>
            </div>
          </div>

          <section class="table-card">
            <div class="table-card-header">
              <h3 style="font-size: 1.1rem; font-weight: 600;">Empresas do Grupo Econômico</h3>
            </div>
            <div class="table-responsive">
              <table class="data-table" id="tabela-multiempresa">
                <thead>
                  <tr>
                    <th>Razão Social</th>
                    <th>Nome Fantasia</th>
                    <th>CNPJ</th>
                    <th>CNAE</th>
                    <th>Grau de Risco</th>
                    <th>FAP</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody id="tbody-multiempresa">
                  <tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Carregando empresas...</td></tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
"""

MODALS_PLATAFORMA_HTML = """
    <!-- ============================================================ -->
    <!-- MODAL: NOVA ADMISSÃO / PROPOSTA ADMISSIONAL                   -->
    <!-- ============================================================ -->
    <div id="modal-nova-admissao" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-lg">
        <div class="modal-header">
          <h2 class="modal-title">Nova Proposta de Admissão (Módulo 02)</h2>
          <button class="btn-close" id="btn-fechar-modal-admissao">&times;</button>
        </div>
        <form id="form-nova-admissao" class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label for="adm-candidato-nome">Nome do Candidato <span class="required">*</span></label>
              <input type="text" id="adm-candidato-nome" class="form-control" required placeholder="Nome completo">
            </div>
            <div class="form-group">
              <label for="adm-candidato-cpf">CPF <span class="required">*</span></label>
              <input type="text" id="adm-candidato-cpf" class="form-control" required placeholder="000.000.000-00">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label for="adm-candidato-email">E-mail</label>
              <input type="email" id="adm-candidato-email" class="form-control" placeholder="candidato@email.com">
            </div>
            <div class="form-group">
              <label for="adm-candidato-cargo">Cargo Proposto <span class="required">*</span></label>
              <input type="text" id="adm-candidato-cargo" class="form-control" required placeholder="Ex: Operador de Caldeira">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label for="adm-candidato-salario">Salário Proposto (R$) <span class="required">*</span></label>
              <input type="number" step="0.01" min="1621.00" id="adm-candidato-salario" class="form-control" required value="1621.00">
              <span class="text-xs text-muted">Piso mínimo legal 2026: R$ 1.621,00</span>
            </div>
            <div class="form-group">
              <label for="adm-candidato-data">Data de Início Prevista <span class="required">*</span></label>
              <input type="date" id="adm-candidato-data" class="form-control" required value="2026-04-01">
            </div>
          </div>
        </form>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-admissao">Cancelar</button>
          <button class="btn btn-primary" id="btn-salvar-nova-admissao">Registrar Admissão</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: CHECKLIST ADMISSIONAL                                  -->
    <!-- ============================================================ -->
    <div id="modal-checklist-admissao" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-md">
        <div class="modal-header">
          <h2 class="modal-title">Checklist de Documentos Admissionais</h2>
          <button class="btn-close" id="btn-fechar-checklist-admissao">&times;</button>
        </div>
        <div class="modal-body" id="corpo-checklist-admissao">
          <p class="text-muted text-sm mb-2">Validação e conferência documental obrigatória (8 itens):</p>
          <div id="lista-itens-checklist" style="display: flex; flex-direction: column; gap: 0.5rem;">
            <!-- Itens preenchidos via JS -->
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" id="btn-concluir-checklist">Fechar</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: REGISTRAR MARCAÇÃO DE PONTO                           -->
    <!-- ============================================================ -->
    <div id="modal-registrar-ponto" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-sm">
        <div class="modal-header">
          <h2 class="modal-title">Registrar Batida de Ponto</h2>
          <button class="btn-close" id="btn-fechar-modal-ponto">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label for="ponto-colab-registro">Colaborador <span class="required">*</span></label>
            <select id="ponto-colab-registro" class="form-control"></select>
          </div>
          <div class="form-group mt-2">
            <label for="ponto-tipo-batida">Tipo de Marcação <span class="required">*</span></label>
            <select id="ponto-tipo-batida" class="form-control">
              <option value="ENTRADA_1">Entrada 1 (Início do Turno)</option>
              <option value="SAIDA_1">Saída 1 (Início do Intervalo)</option>
              <option value="ENTRADA_2">Entrada 2 (Fim do Intervalo)</option>
              <option value="SAIDA_2">Saída 2 (Fim do Turno)</option>
            </select>
          </div>
          <div class="form-group mt-2">
            <label for="ponto-datahora-registro">Data e Hora <span class="required">*</span></label>
            <input type="datetime-local" id="ponto-datahora-registro" class="form-control">
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-ponto">Cancelar</button>
          <button class="btn btn-primary" id="btn-confirmar-batida-ponto">Confirmar Marcação</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: SOLICITAR AJUSTE DE PONTO                             -->
    <!-- ============================================================ -->
    <div id="modal-ajuste-ponto" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-md">
        <div class="modal-header">
          <h2 class="modal-title">Solicitar Ajuste de Ponto</h2>
          <button class="btn-close" id="btn-fechar-modal-ajuste">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label for="ajuste-colab-select">Colaborador <span class="required">*</span></label>
            <select id="ajuste-colab-select" class="form-control"></select>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="ajuste-data">Data da Marcação <span class="required">*</span></label>
              <input type="date" id="ajuste-data" class="form-control" required>
            </div>
            <div class="form-group">
              <label for="ajuste-tipo-marcacao">Tipo <span class="required">*</span></label>
              <select id="ajuste-tipo-marcacao" class="form-control">
                <option value="ENTRADA_1">Entrada 1</option>
                <option value="SAIDA_1">Saída 1</option>
                <option value="ENTRADA_2">Entrada 2</option>
                <option value="SAIDA_2">Saída 2</option>
              </select>
            </div>
          </div>
          <div class="form-group mt-2">
            <label for="ajuste-horario-novo">Horário Proposto <span class="required">*</span></label>
            <input type="time" id="ajuste-horario-novo" class="form-control" required value="08:00">
          </div>
          <div class="form-group mt-2">
            <label for="ajuste-justificativa">Justificativa Legal Obrigatória <span class="required">*</span></label>
            <textarea id="ajuste-justificativa" class="form-control" rows="3" required placeholder="Ex: Esquecimento de registro, falha no leitor biométrico, consulta médica..."></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-ajuste">Cancelar</button>
          <button class="btn btn-primary" id="btn-confirmar-ajuste-ponto">Enviar Solicitação</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: PROGRAMAR FÉRIAS                                      -->
    <!-- ============================================================ -->
    <div id="modal-programar-ferias" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-md">
        <div class="modal-header">
          <h2 class="modal-title">Programar Gozo de Férias (Módulo 06)</h2>
          <button class="btn-close" id="btn-fechar-modal-ferias">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label for="ferias-colab-select">Colaborador <span class="required">*</span></label>
            <select id="ferias-colab-select" class="form-control"></select>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="ferias-data-inicio">Data Início Gozo <span class="required">*</span></label>
              <input type="date" id="ferias-data-inicio" class="form-control" required>
              <span class="text-xs text-muted">Proibido início 2 dias antes do repouso semanal (RN-019).</span>
            </div>
            <div class="form-group">
              <label for="ferias-dias-gozo">Dias de Férias <span class="required">*</span></label>
              <input type="number" id="ferias-dias-gozo" class="form-control" min="5" max="30" value="20" required>
            </div>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="ferias-abono-dias">Abono Pecuniário (Dias)</label>
              <input type="number" id="ferias-abono-dias" class="form-control" min="0" max="10" value="10">
              <span class="text-xs text-muted">Venda de no máximo 1/3 das férias (10 dias).</span>
            </div>
            <div class="form-group" style="display: flex; align-items: center; gap: 0.5rem; margin-top: 1.5rem;">
              <input type="checkbox" id="ferias-adiantar-13" style="width: 18px; height: 18px;">
              <label for="ferias-adiantar-13" style="margin: 0; font-size: 0.88rem;">Adiantar 50% do 13º Salário</label>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-ferias">Cancelar</button>
          <button class="btn btn-primary" id="btn-confirmar-programar-ferias">Programar Férias</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: REGISTRAR AFASTAMENTO PREVIDENCIÁRIO                  -->
    <!-- ============================================================ -->
    <div id="modal-novo-afastamento" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-md">
        <div class="modal-header">
          <h2 class="modal-title">Registrar Afastamento &amp; Licença (Módulo 07)</h2>
          <button class="btn-close" id="btn-fechar-modal-afastamento">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label for="afast-colab-select">Colaborador <span class="required">*</span></label>
            <select id="afast-colab-select" class="form-control"></select>
          </div>
          <div class="form-group mt-2">
            <label for="afast-motivo-select">Motivo do Afastamento <span class="required">*</span></label>
            <select id="afast-motivo-select" class="form-control">
              <option value="DOENCA_COMUM_15D">Auxílio por Incapacidade Temporária Comum (B31)</option>
              <option value="ACIDENTE_TRABALHO_B91">Acidente do Trabalho ou Doença Ocupacional (B91 — Gera Estabilidade)</option>
              <option value="LICENCA_MATERNIDADE">Licença-Maternidade (120 dias — Estabilidade 5 meses pós-parto)</option>
              <option value="LICENCA_PATERNIDADE">Licença-Paternidade (5 a 20 dias)</option>
              <option value="OUTROS">Outras Licenças Remuneradas / Não Remuneradas</option>
            </select>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="afast-data-inicio">Data Início <span class="required">*</span></label>
              <input type="date" id="afast-data-inicio" class="form-control" required>
            </div>
            <div class="form-group">
              <label for="afast-data-fim">Data Término Prevista</label>
              <input type="date" id="afast-data-fim" class="form-control">
            </div>
          </div>
          <div class="form-group mt-2">
            <label for="afast-cid">Código CID-10</label>
            <input type="text" id="afast-cid" class="form-control" placeholder="Ex: M54.5, S82.1">
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-afastamento">Cancelar</button>
          <button class="btn btn-primary" id="btn-confirmar-afastamento">Salvar Afastamento</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: CALCULAR RESCISÃO CONTRATUAL                          -->
    <!-- ============================================================ -->
    <div id="modal-calcular-rescisao" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-lg">
        <div class="modal-header">
          <h2 class="modal-title">Cálculo de Rescisão de Contrato (Módulo 11)</h2>
          <button class="btn-close" id="btn-fechar-modal-rescisao">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label for="resc-colab-select">Colaborador <span class="required">*</span></label>
              <select id="resc-colab-select" class="form-control"></select>
            </div>
            <div class="form-group">
              <label for="resc-tipo-select">Tipo de Desligamento <span class="required">*</span></label>
              <select id="resc-tipo-select" class="form-control">
                <option value="SEM_JUSTA_CAUSA">Dispensa sem Justa Causa (Empregador — Multa FGTS 40%)</option>
                <option value="COM_JUSTA_CAUSA">Dispensa com Justa Causa (Falta Grave CLT art. 482)</option>
                <option value="PEDIDO_DEMISSAO">Pedido de Demissão (Empregado)</option>
                <option value="ACORDO_MUTUO">Acordo Mútuo (CLT art. 484-A — Multa FGTS 20%)</option>
                <option value="TERMINO_CONTRATO">Término Normal de Contrato de Experiência</option>
              </select>
            </div>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="resc-data-aviso">Data do Aviso Prévio <span class="required">*</span></label>
              <input type="date" id="resc-data-aviso" class="form-control" required value="2026-03-01">
            </div>
            <div class="form-group">
              <label for="resc-data-desligamento">Data do Desligamento (Último Dia) <span class="required">*</span></label>
              <input type="date" id="resc-data-desligamento" class="form-control" required value="2026-03-31">
            </div>
          </div>

          <!-- Memória de Cálculo Rescisória -->
          <div id="resc-preview-box" class="memoria-box mt-3 hidden">
            <h4 style="font-size: 0.95rem; font-weight: 700; margin-bottom: 0.5rem; color: var(--primary);">Memória de Cálculo de Verbas Rescisórias (Oficial 2026)</h4>
            <div id="resc-preview-detalhes" style="font-size: 0.85rem; line-height: 1.6;"></div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-rescisao">Cancelar</button>
          <button class="btn btn-outline" id="btn-previa-rescisao">Simular Cálculo</button>
          <button class="btn btn-primary" id="btn-confirmar-rescisao">Homologar Rescisão</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: REGISTRAR ASO (SST)                                   -->
    <!-- ============================================================ -->
    <div id="modal-novo-aso" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-md">
        <div class="modal-header">
          <h2 class="modal-title">Registrar Atestado de Saúde Ocupacional (ASO)</h2>
          <button class="btn-close" id="btn-fechar-modal-aso">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label for="aso-colab-select">Colaborador <span class="required">*</span></label>
            <select id="aso-colab-select" class="form-control"></select>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="aso-tipo-select">Tipo de Exame <span class="required">*</span></label>
              <select id="aso-tipo-select" class="form-control">
                <option value="ADMISSIONAL">Admissional</option>
                <option value="PERIODICO">Periódico</option>
                <option value="RETORNO_TRABALHO">Retorno ao Trabalho</option>
                <option value="MUDANCA_RISCO">Mudança de Riscos Ocupacionais</option>
                <option value="DEMISSIONAL">Demissional</option>
              </select>
            </div>
            <div class="form-group">
              <label for="aso-resultado-select">Conclusão / Aptidão <span class="required">*</span></label>
              <select id="aso-resultado-select" class="form-control">
                <option value="APTO">Apto para a Função</option>
                <option value="INAPTO">Inapto</option>
                <option value="APTO_COM_RESTRICAO">Apto com Restrições</option>
              </select>
            </div>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="aso-data-exame">Data do Exame <span class="required">*</span></label>
              <input type="date" id="aso-data-exame" class="form-control" required>
            </div>
            <div class="form-group">
              <label for="aso-data-validade">Data de Validade <span class="required">*</span></label>
              <input type="date" id="aso-data-validade" class="form-control" required>
            </div>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="aso-medico-nome">Médico Examinador <span class="required">*</span></label>
              <input type="text" id="aso-medico-nome" class="form-control" required value="Dr. Marcelo Santos">
            </div>
            <div class="form-group">
              <label for="aso-medico-crm">CRM / UF <span class="required">*</span></label>
              <input type="text" id="aso-medico-crm" class="form-control" required value="CRM-SP 98765">
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-aso">Cancelar</button>
          <button class="btn btn-primary" id="btn-confirmar-aso">Registrar ASO</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: REGISTRAR ENTREGA DE EPI                              -->
    <!-- ============================================================ -->
    <div id="modal-entrega-epi" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-md">
        <div class="modal-header">
          <h2 class="modal-title">Ficha de Entrega de EPI (NR-06)</h2>
          <button class="btn-close" id="btn-fechar-modal-epi">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label for="epi-colab-select">Colaborador <span class="required">*</span></label>
            <select id="epi-colab-select" class="form-control"></select>
          </div>
          <div class="form-group mt-2">
            <label for="epi-catalogo-select">Equipamento de Proteção (EPI) <span class="required">*</span></label>
            <select id="epi-catalogo-select" class="form-control">
              <option value="1">Capacete de Segurança com Jugular (CA: 31469)</option>
              <option value="2">Óculos de Proteção Antirrisco (CA: 25714)</option>
              <option value="3">Protetor Auditivo tipo Concha (CA: 12188)</option>
              <option value="4">Luvas de Vaqueta para Eletricista (CA: 41250)</option>
              <option value="5">Botina de Segurança com Bico de Composite (CA: 28511)</option>
            </select>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="epi-data-entrega">Data de Entrega <span class="required">*</span></label>
              <input type="date" id="epi-data-entrega" class="form-control" required>
            </div>
            <div class="form-group">
              <label for="epi-quantidade">Quantidade</label>
              <input type="number" id="epi-quantidade" class="form-control" min="1" value="1">
            </div>
          </div>
          <div class="form-group mt-2">
            <label style="display: flex; align-items: center; gap: 0.5rem;">
              <input type="checkbox" id="epi-termo-assinado" checked style="width: 18px; height: 18px;">
              <span>Termo de responsabilidade e biometria/assinatura colhida</span>
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-epi">Cancelar</button>
          <button class="btn btn-primary" id="btn-confirmar-entrega-epi">Registrar Entrega</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: EMISSÃO DE CAT (SST / ESOCIAL S-2210)                  -->
    <!-- ============================================================ -->
    <div id="modal-nova-cat" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-lg">
        <div class="modal-header">
          <h2 class="modal-title">Emissão de Comunicação de Acidente de Trabalho (CAT)</h2>
          <button class="btn-close" id="btn-fechar-modal-cat">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <div class="form-group">
              <label for="cat-colab-select">Colaborador Acidentado <span class="required">*</span></label>
              <select id="cat-colab-select" class="form-control"></select>
            </div>
            <div class="form-group">
              <label for="cat-tipo-select">Tipo de Acidente <span class="required">*</span></label>
              <select id="cat-tipo-select" class="form-control">
                <option value="TIPICO">Típico (No local de trabalho em operação)</option>
                <option value="TRAJETO">Trajeto (Deslocamento residência / empresa)</option>
                <option value="DOENCA_OCUPACIONAL">Doença Profissional ou Ocupacional</option>
              </select>
            </div>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="cat-data-hora">Data e Hora do Acidente <span class="required">*</span></label>
              <input type="datetime-local" id="cat-data-hora" class="form-control" required>
            </div>
            <div class="form-group">
              <label for="cat-local">Local / Setor do Acidente <span class="required">*</span></label>
              <input type="text" id="cat-local" class="form-control" required value="Usina - Moenda Setor B">
            </div>
          </div>
          <div class="form-row mt-2">
            <div class="form-group">
              <label for="cat-parte-corpo">Parte do Corpo Atingida</label>
              <input type="text" id="cat-parte-corpo" class="form-control" placeholder="Ex: Mão direita, Antebraço esquerdo">
            </div>
            <div class="form-group">
              <label for="cat-cid">CID-10 do Diagnóstico Médico</label>
              <input type="text" id="cat-cid" class="form-control" placeholder="Ex: S61.0 - Ferimento no dedo">
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" id="btn-cancelar-modal-cat">Cancelar</button>
          <button class="btn btn-primary" id="btn-confirmar-cat">Emitir CAT &amp; Gerar S-2210</button>
        </div>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- MODAL: VISUALIZADOR DE XML ESOCIAL                           -->
    <!-- ============================================================ -->
    <div id="modal-xml-esocial" class="modal-overlay hidden" role="dialog" aria-modal="true">
      <div class="modal-card modal-lg">
        <div class="modal-header">
          <h2 class="modal-title" id="xml-modal-titulo">XML do Evento eSocial</h2>
          <button class="btn-close" id="btn-fechar-modal-xml">&times;</button>
        </div>
        <div class="modal-body">
          <pre id="xml-modal-conteudo" style="background: #0f172a; color: #38bdf8; padding: 1.25rem; border-radius: 6px; font-size: 0.8rem; overflow: auto; max-height: 400px; white-space: pre-wrap; word-break: break-all;"></pre>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" id="btn-fechar-modal-xml-rodape">Fechar</button>
        </div>
      </div>
    </div>
"""

def main():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Esconder nav-modules antiga para dar lugar ao sidebar unificado, mantendo os botões intactos
    nav_old = '<nav class="nav-modules" aria-label="Navegação entre módulos">'
    nav_new = '<nav class="nav-modules" aria-label="Navegação entre módulos" style="display: none;">'
    html = html.replace(nav_old, nav_new)

    # 2. Localizar onde <main class="main-content"> começa
    main_start = '<main class="main-content">'
    if main_start in html:
        # Substituir por SIDEBAR + <main class="main-content platform-main-content"> + VIEWS_DASHBOARD_AND_PENDENCIAS
        html = html.replace(main_start, SIDEBAR_HTML + VIEWS_DASHBOARD_AND_PENDENCIAS)
    else:
        print("Aviso: main_start não encontrado!")

    # 3. Inserir VIEWS_AFTER_COLABORADORES logo após </div> <!-- /#view-modulo-colaboradores -->
    colab_end = '</div> <!-- /#view-modulo-colaboradores -->'
    if colab_end in html:
        html = html.replace(colab_end, colab_end + "\n" + VIEWS_AFTER_COLABORADORES)
    else:
        # Tentar procurar apenas </div> fechando colaboradores
        pass

    # 4. Inserir VIEWS_AFTER_FOLHA logo após </div> <!-- /#view-modulo-folha -->
    folha_end = '</div> <!-- /#view-modulo-folha -->'
    if folha_end in html:
        html = html.replace(folha_end, folha_end + "\n" + VIEWS_AFTER_FOLHA)

    # 5. Fechar </main> e fechar <div class="platform-layout">
    # Procurar </main>
    # Deve virar </main>\n    </div> <!-- /.platform-layout -->
    html = html.replace('</main>', '</main>\n    </div> <!-- /.platform-layout -->', 1)

    # 6. Inserir MODALS_PLATAFORMA_HTML antes de </div> <!-- /#tela-sistema -->
    tela_end = '</div> <!-- /#tela-sistema -->'
    if tela_end in html:
        html = html.replace(tela_end, MODALS_PLATAFORMA_HTML + "\n  " + tela_end)

    with open("frontend/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("frontend/index.html atualizado com sucesso!")

if __name__ == "__main__":
    main()
