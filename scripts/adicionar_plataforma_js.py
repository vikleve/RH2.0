# -*- coding: utf-8 -*-
"""
Script para anexar a implementação do PlataformaManager ao frontend/app.js.
"""

PLATAFORMA_JS = """
// ============================================================================
// PLATAFORMA INTEGRADA DO CICLO TRABALHISTA (MÓDULOS 01 A 20)
// Gerenciador Central de Navegação, Indicadores, Ponto, SST, eSocial, CNAB
// ============================================================================
const PlataformaManager = {
  visaoAtual: 'dashboard',
  colaboradoresCache: [],
  cnabArquivoGerado: null,

  inicializar() {
    this.configurarNavegacaoSidebar();
    this.configurarEventosModais();
    this.configurarSSTTabs();
    this.configurarBotoesAcao();
  },

  configurarNavegacaoSidebar() {
    const btns = document.querySelectorAll('.sidebar-btn');
    btns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const viewName = btn.getAttribute('data-view');
        if (viewName) {
          this.navegarPara(viewName);
        }
      });
    });

    // Sincronizar com as tabs antigas se existirem
    const tabColab = document.getElementById('nav-tab-colaboradores');
    const tabFolha = document.getElementById('nav-tab-folha');
    if (tabColab) {
      tabColab.addEventListener('click', () => this.navegarPara('colaboradores'));
    }
    if (tabFolha) {
      tabFolha.addEventListener('click', () => this.navegarPara('folha'));
    }
  },

  async navegarPara(viewName) {
    this.visaoAtual = viewName;

    // Atualiza classe active nos botões da sidebar
    document.querySelectorAll('.sidebar-btn').forEach(b => {
      if (b.getAttribute('data-view') === viewName) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });

    // Ocultar todas as visões da plataforma
    const allViews = [
      'view-modulo-dashboard',
      'view-modulo-pendencias',
      'view-modulo-colaboradores',
      'view-modulo-admissoes',
      'view-modulo-ponto',
      'view-modulo-ferias',
      'view-modulo-afastamentos',
      'view-modulo-folha',
      'view-modulo-rescisoes',
      'view-modulo-sst',
      'view-modulo-esocial',
      'view-modulo-integracoes',
      'view-modulo-auditoria',
      'view-modulo-multiempresa'
    ];

    allViews.forEach(vId => {
      const el = document.getElementById(vId);
      if (el) el.classList.add('hidden');
    });

    const targetView = document.getElementById(`view-modulo-${viewName}`);
    if (targetView) {
      targetView.classList.remove('hidden');
    }

    // Carregar dados específicos da visão acionada
    try {
      if (viewName === 'dashboard') await this.carregarDashboard();
      else if (viewName === 'pendencias') await this.carregarPendencias();
      else if (viewName === 'colaboradores') {
        if (typeof carregarColaboradores === 'function') await carregarColaboradores();
      }
      else if (viewName === 'admissoes') await this.carregarAdmissoes();
      else if (viewName === 'ponto') await this.carregarPonto();
      else if (viewName === 'ferias') await this.carregarFerias();
      else if (viewName === 'afastamentos') await this.carregarAfastamentos();
      else if (viewName === 'folha') {
        await FolhaManager.carregarParametros();
        await FolhaManager.carregarFolhas();
      }
      else if (viewName === 'rescisoes') await this.carregarRescisoes();
      else if (viewName === 'sst') await this.carregarSST();
      else if (viewName === 'esocial') await this.carregarESocial();
      else if (viewName === 'integracoes') {}
      else if (viewName === 'auditoria') await this.carregarAuditoria();
      else if (viewName === 'multiempresa') await this.carregarMultiempresa();
    } catch (err) {
      console.warn(`Erro ao carregar módulo ${viewName}:`, err);
    }
  },

  async carregarColaboradoresCache() {
    try {
      const resp = await fetch(`${API_BASE}/colaboradores`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (resp.ok) {
        const json = await resp.json();
        this.colaboradoresCache = json.dados || [];
      }
    } catch (e) {
      console.warn('Erro ao carregar lista de colaboradores para selects:', e);
    }
  },

  popularSelectColaboradores(selectId) {
    const el = document.getElementById(selectId);
    if (!el) return;
    el.innerHTML = '<option value="">Selecione um colaborador...</option>';
    this.colaboradoresCache.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.nome_completo || c.nome} (${c.matricula || 'N/A'}) - CPF: ${c.cpf}`;
      el.appendChild(opt);
    });
  },

  // --------------------------------------------------------------------------
  // DASHBOARD & BI (RF-181 A RF-190)
  // --------------------------------------------------------------------------
  async carregarDashboard() {
    try {
      const resp = await fetch(`${API_BASE}/bi/indicadores`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (resp.ok) {
        const json = await resp.json();
        const d = json.dados || {};
        const elAtivos = document.getElementById('kpi-total-ativos');
        const elTurnover = document.getElementById('kpi-turnover');
        const elAbsenteismo = document.getElementById('kpi-absenteismo');
        const elPendAbertas = document.getElementById('kpi-pendencias-abertas');
        const elPendCriticas = document.getElementById('kpi-pendencias-criticas');

        if (elAtivos) elAtivos.textContent = d.total_colaboradores_ativos || 0;
        if (elTurnover) elTurnover.textContent = `${(d.taxa_turnover || 0).toFixed(2)}%`;
        if (elAbsenteismo) elAbsenteismo.textContent = `${(d.taxa_absenteismo || 0).toFixed(2)}%`;
        if (elPendAbertas) elPendAbertas.textContent = d.pendencias_abertas || 0;
        if (elPendCriticas) elPendCriticas.textContent = `${d.pendencias_criticas || 0} críticas`;

        const badgeNav = document.getElementById('badge-pendencias-count');
        if (badgeNav) badgeNav.textContent = d.pendencias_abertas || 0;
      }
    } catch (e) {
      console.warn('Erro ao carregar BI:', e);
    }
  },

  // --------------------------------------------------------------------------
  // CENTRAL DE PENDÊNCIAS (RF-151 A RF-160, RN-076)
  // --------------------------------------------------------------------------
  async carregarPendencias() {
    const tbody = document.getElementById('tbody-pendencias');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Carregando pendências...</td></tr>';

    try {
      const status = document.getElementById('filtro-pendencia-status')?.value || '';
      const severidade = document.getElementById('filtro-pendencia-severidade')?.value || '';
      let url = `${API_BASE}/pendencias?`;
      if (status) url += `status=${encodeURIComponent(status)}&`;
      if (severidade) url += `severidade=${encodeURIComponent(severidade)}&`;

      const resp = await fetch(url, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Falha ao consultar pendências');
      const json = await resp.json();
      const lista = json.dados || [];

      // Atualiza badge
      const badgeNav = document.getElementById('badge-pendencias-count');
      if (badgeNav) {
        const abertas = lista.filter(p => p.status === 'PENDENTE' || p.status === 'EM_ANALISE').length;
        badgeNav.textContent = abertas;
      }

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Nenhuma pendência operacional encontrada para os filtros.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(p => {
        const tr = document.createElement('tr');
        const sevClass = p.severidade === 'CRITICA' ? 'badge-severidade-critica' :
                         p.severidade === 'ALTA' ? 'badge-severidade-alta' :
                         p.severidade === 'MEDIA' ? 'badge-severidade-media' : 'badge-severidade-baixa';

        tr.innerHTML = `
          <td><span class="${sevClass}">${p.severidade}</span></td>
          <td><strong style="font-size: 0.85rem;">${p.tipo_pendencia}</strong></td>
          <td>
            <div style="font-weight: 600; font-size: 0.88rem;">${p.titulo}</div>
            <div class="text-xs text-muted">${p.descricao || ''}</div>
          </td>
          <td>${p.nome_colaborador || p.recurso_afetado || '-'}</td>
          <td>${p.data_limite_sla || p.data_vencimento || 'Imediato'}</td>
          <td><span class="badge-status badge-calculada">${p.status}</span></td>
          <td>
            ${p.status === 'PENDENTE' || p.status === 'EM_ANALISE' ?
              `<button class="btn btn-outline btn-sm btn-resolver-pendencia" data-id="${p.id}">Tratar / Resolver</button>` :
              '<span class="text-xs text-muted">Resolvido</span>'
            }
          </td>
        `;
        tbody.appendChild(tr);
      });

      // Bind botões resolver
      document.querySelectorAll('.btn-resolver-pendencia').forEach(b => {
        b.addEventListener('click', async () => {
          const id = b.getAttribute('data-id');
          await PlataformaManager.resolverPendencia(id);
        });
      });
    } catch (e) {
      console.error(e);
      tbody.innerHTML = '<tr><td colspan="7" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar pendências da plataforma.</td></tr>';
    }
  },

  async resolverPendencia(id) {
    const notas = prompt('Informe a nota de tratativa da pendência:', 'Tratado conforme validação operacional');
    if (notas === null) return;

    try {
      const resp = await fetch(`${API_BASE}/pendencias/${id}/resolver`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ notas_resolucao: notas })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao resolver pendência.', 'error');
        return;
      }
      exibirToast('Pendência resolvida com sucesso!', 'success');
      await this.carregarPendencias();
      await this.carregarDashboard();
    } catch (e) {
      exibirToast('Erro de comunicação ao resolver pendência.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // ADMISSÕES & CHECKLIST (RF-011 A RF-020, RN-008, RN-080)
  // --------------------------------------------------------------------------
  async carregarAdmissoes() {
    const tbody = document.getElementById('tbody-admissoes');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted" style="padding: 2rem;">Carregando propostas de admissão...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/admissoes`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar admissões');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted" style="padding: 2rem;">Nenhuma proposta de admissão registrada. Clique em "Nova Admissão".</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(a => {
        const tr = document.createElement('tr');
        const salarioFmt = (a.salario_proposto || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const aprovados = a.documentos_aprovados || 0;
        const totalDocs = a.total_documentos || 8;

        tr.innerHTML = `
          <td><strong>${a.nome_candidato}</strong></td>
          <td>${formatarCpf(a.cpf)}</td>
          <td>${a.cargo_proposto || '-'}</td>
          <td>${salarioFmt}</td>
          <td>${a.data_admissao_prevista || '-'}</td>
          <td><span class="badge-status ${aprovados === totalDocs ? 'badge-fechada' : 'badge-calculada'}">${aprovados}/${totalDocs} docs</span></td>
          <td><span class="badge-status badge-calculada">${a.status}</span></td>
          <td style="display: flex; gap: 0.35rem;">
            <button class="btn btn-outline btn-sm btn-ver-checklist" data-id="${a.id}">Checklist</button>
            ${a.status !== 'APROVADA' ? `<button class="btn btn-primary btn-sm btn-aprovar-admissao" data-id="${a.id}">Aprovar</button>` : ''}
          </td>
        `;
        tbody.appendChild(tr);
      });

      // Bind checklist e aprovação
      document.querySelectorAll('.btn-ver-checklist').forEach(b => {
        b.addEventListener('click', () => {
          const id = b.getAttribute('data-id');
          PlataformaManager.abrirChecklistAdmissao(id);
        });
      });

      document.querySelectorAll('.btn-aprovar-admissao').forEach(b => {
        b.addEventListener('click', async () => {
          const id = b.getAttribute('data-id');
          await PlataformaManager.aprovarAdmissao(id);
        });
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger" style="padding: 2rem;">Erro ao consultar admissões.</td></tr>';
    }
  },

  async salvarNovaAdmissao() {
    const nome = document.getElementById('adm-candidato-nome')?.value?.trim();
    const cpf = document.getElementById('adm-candidato-cpf')?.value?.trim();
    const email = document.getElementById('adm-candidato-email')?.value?.trim();
    const cargo = document.getElementById('adm-candidato-cargo')?.value?.trim();
    const salario = parseFloat(document.getElementById('adm-candidato-salario')?.value || 0);
    const dataInicio = document.getElementById('adm-candidato-data')?.value;

    if (!nome || !cpf || !cargo || !dataInicio) {
      exibirToast('Preencha todos os campos obrigatórios da admissão.', 'error');
      return;
    }

    if (salario < 1621.00) {
      exibirToast('O salário proposto não pode ser inferior ao mínimo legal de 2026 (R$ 1.621,00).', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/admissoes`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          nome_candidato: nome,
          cpf: normalizarCpf(cpf),
          email: email,
          cargo_proposto: cargo,
          salario_proposto: salario,
          data_admissao_prevista: dataInicio
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao registrar admissão.', 'error');
        return;
      }
      exibirToast('Proposta de admissão registrada com sucesso!', 'success');
      document.getElementById('modal-nova-admissao')?.classList.add('hidden');
      await this.carregarAdmissoes();
    } catch (e) {
      exibirToast('Erro de rede ao salvar proposta admissional.', 'error');
    }
  },

  async abrirChecklistAdmissao(admissaoId) {
    const modal = document.getElementById('modal-checklist-admissao');
    const container = document.getElementById('lista-itens-checklist');
    if (!modal || !container) return;

    modal.classList.remove('hidden');
    container.innerHTML = '<p class="text-muted">Carregando itens do checklist...</p>';

    try {
      const resp = await fetch(`${API_BASE}/admissoes/checklist/${admissaoId}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (!resp.ok) throw new Error('Erro ao buscar checklist');
      const json = await resp.json();
      const itens = json.dados || [];

      container.innerHTML = '';
      itens.forEach(item => {
        const itemDiv = document.createElement('div');
        itemDiv.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.75rem; border: 1px solid var(--border-color); border-radius: 6px;';
        itemDiv.innerHTML = `
          <div>
            <strong style="font-size: 0.85rem;">${item.nome_documento}</strong>
            <span class="text-xs text-muted" style="display: block;">Tipo: ${item.tipo_documento}</span>
          </div>
          <div>
            <select class="form-control form-control-sm select-status-item" data-id="${item.id}" style="font-size: 0.8rem; padding: 0.25rem 0.5rem;">
              <option value="PENDENTE" ${item.status === 'PENDENTE' ? 'selected' : ''}>Pendente</option>
              <option value="ENTREGUE" ${item.status === 'ENTREGUE' ? 'selected' : ''}>Entregue</option>
              <option value="APROVADO" ${item.status === 'APROVADO' ? 'selected' : ''}>Aprovado</option>
              <option value="REJEITADO" ${item.status === 'REJEITADO' ? 'selected' : ''}>Rejeitado</option>
            </select>
          </div>
        `;
        container.appendChild(itemDiv);
      });

      // Bind onChange nos status
      container.querySelectorAll('.select-status-item').forEach(sel => {
        sel.addEventListener('change', async () => {
          const itemId = sel.getAttribute('data-id');
          const novoStatus = sel.value;
          await fetch(`${API_BASE}/admissoes/checklist/${itemId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            credentials: 'include',
            body: JSON.stringify({ status: novoStatus })
          });
          exibirToast('Status do documento atualizado.', 'info');
        });
      });
    } catch (e) {
      container.innerHTML = '<p class="text-danger">Erro ao carregar checklist documental.</p>';
    }
  },

  async aprovarAdmissao(admissaoId) {
    if (!confirm('Deseja realmente homologar e aprovar esta admissão?')) return;

    try {
      const resp = await fetch(`${API_BASE}/admissoes/${admissaoId}/aprovar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok) {
        // RN-080 ou Checklist incompleto
        exibirToast(json.mensagem || 'Erro ao aprovar admissão.', 'error');
        return;
      }
      exibirToast('Admissão aprovada com sucesso! Colaborador efetivado.', 'success');
      await this.carregarAdmissoes();
    } catch (e) {
      exibirToast('Erro ao comunicar com o servidor.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // JORNADA & PONTO ELETRÔNICO (RF-021 A RF-040)
  // --------------------------------------------------------------------------
  async carregarPonto() {
    await this.carregarColaboradoresCache();
    this.popularSelectColaboradores('ponto-colaborador-select');
    this.popularSelectColaboradores('ponto-colab-registro');
    this.popularSelectColaboradores('ajuste-colab-select');
  },

  async carregarEspelhoPonto() {
    const colabId = document.getElementById('ponto-colaborador-select')?.value;
    const competencia = document.getElementById('ponto-competencia-input')?.value || '2026-03';
    const tbody = document.getElementById('tbody-espelho-ponto');

    if (!colabId) {
      exibirToast('Selecione um colaborador para ver o espelho.', 'warning');
      return;
    }

    if (tbody) tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Carregando espelho de ponto...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/ponto/espelho?colaborador_id=${colabId}&competencia=${competencia}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (!resp.ok) throw new Error('Erro ao consultar espelho de ponto');
      const json = await resp.json();
      const espelho = json.dados || {};
      const dias = espelho.dias || [];

      // Atualiza totais
      const tot = espelho.totais || {};
      document.getElementById('ponto-tot-normais').textContent = `${(tot.horas_normais || 0).toFixed(1)}h`;
      document.getElementById('ponto-tot-he50').textContent = `${(tot.horas_extras_50 || 0).toFixed(1)}h`;
      document.getElementById('ponto-tot-he100').textContent = `${(tot.horas_extras_100 || 0).toFixed(1)}h`;
      document.getElementById('ponto-tot-noturno').textContent = `${(tot.adicional_noturno || 0).toFixed(1)}h`;
      document.getElementById('ponto-tot-faltas').textContent = `${(tot.faltas_atrasos || 0).toFixed(1)}h`;

      if (dias.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Nenhuma batida registrada para esta competência.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      dias.forEach(d => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${d.data}</strong></td>
          <td>${d.dia_semana || '-'}</td>
          <td><span class="batida-pill">${d.entrada_1 || '--:--'}</span></td>
          <td><span class="batida-pill">${d.saida_1 || '--:--'}</span></td>
          <td><span class="batida-pill">${d.entrada_2 || '--:--'}</span></td>
          <td><span class="batida-pill">${d.saida_2 || '--:--'}</span></td>
          <td><strong>${(d.total_trabalhado || 0).toFixed(2)}h</strong></td>
          <td>${(d.saldo_diario || 0) >= 0 ? `+${(d.saldo_diario || 0).toFixed(2)}h` : `${(d.saldo_diario || 0).toFixed(2)}h`}</td>
          <td><span class="badge-status badge-calculada">${d.status || 'OK'}</span></td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="9" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar espelho de ponto.</td></tr>';
    }
  },

  async registrarBatidaPonto() {
    const colabId = document.getElementById('ponto-colab-registro')?.value;
    const tipo = document.getElementById('ponto-tipo-batida')?.value;
    const datahora = document.getElementById('ponto-datahora-registro')?.value;

    if (!colabId || !tipo || !datahora) {
      exibirToast('Selecione colaborador, tipo e horário da batida.', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/ponto/marcacao`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: parseInt(colabId, 10),
          tipo_marcacao: tipo,
          data_hora: datahora
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao registrar marcação.', 'error');
        return;
      }
      exibirToast('Batida de ponto registrada com sucesso!', 'success');
      document.getElementById('modal-registrar-ponto')?.classList.add('hidden');
      await this.carregarEspelhoPonto();
    } catch (e) {
      exibirToast('Erro ao comunicar marcação de ponto.', 'error');
    }
  },

  async solicitarAjustePonto() {
    const colabId = document.getElementById('ajuste-colab-select')?.value;
    const data = document.getElementById('ajuste-data')?.value;
    const tipo = document.getElementById('ajuste-tipo-marcacao')?.value;
    const horario = document.getElementById('ajuste-horario-novo')?.value;
    const justificativa = document.getElementById('ajuste-justificativa')?.value?.trim();

    if (!colabId || !data || !tipo || !horario || !justificativa) {
      exibirToast('Preencha todos os campos obrigatórios da solicitação de ajuste.', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/ponto/ajuste`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: parseInt(colabId, 10),
          data_ocorrencia: data,
          tipo_marcacao: tipo,
          horario_proposto: horario,
          justificativa: justificativa
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao solicitar ajuste.', 'error');
        return;
      }
      exibirToast('Solicitação de ajuste enviada para aprovação do gestor!', 'success');
      document.getElementById('modal-ajuste-ponto')?.classList.add('hidden');
    } catch (e) {
      exibirToast('Erro ao enviar solicitação de ajuste.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // FÉRIAS & ABONO (RF-051 A RF-060, RN-019 A RN-024)
  // --------------------------------------------------------------------------
  async carregarFerias() {
    await this.carregarColaboradoresCache();
    this.popularSelectColaboradores('ferias-colab-select');

    const tbody = document.getElementById('tbody-ferias');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Carregando histórico de férias...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/ferias`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar férias');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Nenhuma programação de férias encontrada. Clique em "Programar Férias".</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(f => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${f.nome_colaborador || `Colaborador #${f.colaborador_id}`}</strong></td>
          <td>${f.inicio_periodo_aquisitivo || '-'} a ${f.fim_periodo_aquisitivo || '-'}</td>
          <td><strong style="color: #dc2626;">${f.limite_concessivo || '-'}</strong></td>
          <td>${f.data_inicio_gozo || '-'}</td>
          <td>${f.data_fim_gozo || '-'}</td>
          <td>${f.dias_gozo || 0} dias</td>
          <td>${f.dias_abono ? `${f.dias_abono} dias` : 'Não'}</td>
          <td>${f.adiantamento_decimo_terceiro ? 'Sim (50%)' : 'Não'}</td>
          <td><span class="badge-status badge-fechada">${f.status}</span></td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar férias.</td></tr>';
    }
  },

  async salvarProgramarFerias() {
    const colabId = document.getElementById('ferias-colab-select')?.value;
    const dataInicio = document.getElementById('ferias-data-inicio')?.value;
    const diasGozo = parseInt(document.getElementById('ferias-dias-gozo')?.value || 0, 10);
    const abonoDias = parseInt(document.getElementById('ferias-abono-dias')?.value || 0, 10);
    const adiantar13 = document.getElementById('ferias-adiantar-13')?.checked || false;

    if (!colabId || !dataInicio || !diasGozo) {
      exibirToast('Preencha os dados obrigatórios da programação de férias.', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/ferias/programar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: parseInt(colabId, 10),
          data_inicio_gozo: dataInicio,
          dias_gozo: diasGozo,
          dias_abono: abonoDias,
          adiantamento_decimo_terceiro: adiantar13
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao programar férias.', 'error');
        return;
      }
      exibirToast('Férias programadas com sucesso com memórias e provisões!', 'success');
      document.getElementById('modal-programar-ferias')?.classList.add('hidden');
      await this.carregarFerias();
    } catch (e) {
      exibirToast('Erro de comunicação ao salvar programação de férias.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // AFASTAMENTOS & ESTABILIDADE (RF-061 A RF-070, RN-025 A RN-032)
  // --------------------------------------------------------------------------
  async carregarAfastamentos() {
    await this.carregarColaboradoresCache();
    this.popularSelectColaboradores('afast-colab-select');

    const tbody = document.getElementById('tbody-afastamentos');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Carregando afastamentos...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/afastamentos`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar afastamentos');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Nenhum afastamento registrado.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(a => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${a.nome_colaborador || `Colaborador #${a.colaborador_id}`}</strong></td>
          <td>${a.motivo}</td>
          <td>${a.codigo_cid || '-'}</td>
          <td>${a.data_inicio}</td>
          <td>${a.data_fim_prevista || a.data_retorno_efetivo || 'Indeterminado'}</td>
          <td>${a.dias_empresa || 0}d</td>
          <td>${a.dias_inss || 0}d</td>
          <td>${a.tem_estabilidade ? `<span class="badge-severidade-alta">Estabilidade até ${a.data_fim_estabilidade || '12 meses'}</span>` : 'Não'}</td>
          <td><span class="badge-status badge-calculada">${a.status}</span></td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar afastamentos.</td></tr>';
    }
  },

  async salvarAfastamento() {
    const colabId = document.getElementById('afast-colab-select')?.value;
    const motivo = document.getElementById('afast-motivo-select')?.value;
    const dataInicio = document.getElementById('afast-data-inicio')?.value;
    const dataFim = document.getElementById('afast-data-fim')?.value || null;
    const cid = document.getElementById('afast-cid')?.value?.trim() || null;

    if (!colabId || !motivo || !dataInicio) {
      exibirToast('Preencha todos os campos obrigatórios do afastamento.', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/afastamentos`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: parseInt(colabId, 10),
          motivo: motivo,
          data_inicio: dataInicio,
          data_fim_prevista: dataFim,
          codigo_cid: cid
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao registrar afastamento.', 'error');
        return;
      }
      exibirToast('Afastamento registrado e pendência de ASO de retorno gerada automaticamente!', 'success');
      document.getElementById('modal-novo-afastamento')?.classList.add('hidden');
      await this.carregarAfastamentos();
      await this.carregarDashboard();
    } catch (e) {
      exibirToast('Erro de comunicação ao registrar afastamento.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // RESCISÕES CONTRATUAIS (RF-106 A RF-120, RN-049 A RN-058)
  // --------------------------------------------------------------------------
  async carregarRescisoes() {
    await this.carregarColaboradoresCache();
    this.popularSelectColaboradores('resc-colab-select');

    const tbody = document.getElementById('tbody-rescisoes');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted" style="padding: 2rem;">Carregando rescisões...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/rescisoes`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar rescisões');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted" style="padding: 2rem;">Nenhuma rescisão calculada. Clique em "Calcular Nova Rescisão".</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(r => {
        const tr = document.createElement('tr');
        const verbasFmt = (r.total_rescisao_liquido || r.total_verbas || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const multaFmt = (r.multa_rescisoria_fgts || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

        tr.innerHTML = `
          <td><strong>${r.nome_colaborador || `Colaborador #${r.colaborador_id}`}</strong></td>
          <td>${r.tipo_rescisao}</td>
          <td>${r.data_aviso_previo || '-'}</td>
          <td>${r.data_desligamento}</td>
          <td><strong style="color: #2563eb;">${r.data_limite_pagamento || '-'}</strong></td>
          <td><strong>${verbasFmt}</strong></td>
          <td>${multaFmt}</td>
          <td><span class="badge-status badge-fechada">${r.status}</span></td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar rescisões.</td></tr>';
    }
  },

  async calcularRescisao(simular = false) {
    const colabId = document.getElementById('resc-colab-select')?.value;
    const tipo = document.getElementById('resc-tipo-select')?.value;
    const dataAviso = document.getElementById('resc-data-aviso')?.value;
    const dataDesligamento = document.getElementById('resc-data-desligamento')?.value;

    if (!colabId || !tipo || !dataAviso || !dataDesligamento) {
      exibirToast('Preencha os campos obrigatórios da rescisão.', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/rescisoes`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: parseInt(colabId, 10),
          tipo_rescisao: tipo,
          data_aviso_previo: dataAviso,
          data_desligamento: dataDesligamento,
          simular: simular
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        // Bloqueio por estabilidade ativa ou erro legal
        exibirToast(json.mensagem || 'Erro ao processar rescisão.', 'error');
        return;
      }

      const d = json.dados || {};
      const previewBox = document.getElementById('resc-preview-box');
      const previewDetalhes = document.getElementById('resc-preview-detalhes');

      if (previewBox && previewDetalhes) {
        previewBox.classList.remove('hidden');
        previewDetalhes.innerHTML = `
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
            <div>&bull; Saldo de Salário: <strong>R$ ${(d.saldo_salario || 0).toFixed(2)}</strong></div>
            <div>&bull; Aviso Prévio Proporcional: <strong>R$ ${(d.aviso_previo_valor || 0).toFixed(2)}</strong> (${d.dias_aviso_previo || 30} dias)</div>
            <div>&bull; 13º Salário Proporcional: <strong>R$ ${(d.decimo_terceiro_proporcional || 0).toFixed(2)}</strong></div>
            <div>&bull; Férias Vencidas + Prop. + 1/3: <strong>R$ ${(d.ferias_totais || 0).toFixed(2)}</strong></div>
            <div>&bull; Multa FGTS (${d.percentual_multa_fgts || 0}%): <strong>R$ ${(d.multa_fgts || 0).toFixed(2)}</strong></div>
            <div>&bull; <strong>Prazo Legal Pagamento:</strong> <span style="color: #16a34a; font-weight: 700;">${d.data_limite_pagamento}</span> (10 dias CLT art. 477)</div>
          </div>
          <div style="margin-top: 0.75rem; font-size: 1rem; font-weight: 700; color: var(--primary);">
            Total Rescisório Líquido: R$ ${(d.total_rescisao_liquido || 0).toFixed(2)}
          </div>
        `;
      }

      if (!simular) {
        exibirToast('Rescisão calculada e homologada com sucesso! Evento eSocial S-2299 gerado.', 'success');
        document.getElementById('modal-calcular-rescisao')?.classList.add('hidden');
        await this.carregarRescisoes();
      } else {
        exibirToast('Simulação calculada com sucesso.', 'info');
      }
    } catch (e) {
      exibirToast('Erro de rede ao calcular rescisão.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // SST — SAÚDE E SEGURANÇA (RF-121 A RF-130)
  // --------------------------------------------------------------------------
  configurarSSTTabs() {
    const abas = [
      { btn: 'sst-tab-btn-aso', painel: 'sst-painel-aso' },
      { btn: 'sst-tab-btn-epi', painel: 'sst-painel-epi' },
      { btn: 'sst-tab-btn-treinamentos', painel: 'sst-painel-treinamentos' },
      { btn: 'sst-tab-btn-cat', painel: 'sst-painel-cat' }
    ];

    abas.forEach(a => {
      const btnEl = document.getElementById(a.btn);
      if (btnEl) {
        btnEl.addEventListener('click', () => {
          abas.forEach(x => {
            document.getElementById(x.btn)?.classList.remove('active');
            document.getElementById(x.painel)?.classList.add('hidden');
          });
          btnEl.classList.add('active');
          document.getElementById(a.painel)?.classList.remove('hidden');
        });
      }
    });
  },

  async carregarSST() {
    await this.carregarColaboradoresCache();
    this.popularSelectColaboradores('aso-colab-select');
    this.popularSelectColaboradores('epi-colab-select');
    this.popularSelectColaboradores('cat-colab-select');

    try {
      const resp = await fetch(`${API_BASE}/sst/resumo`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar dados de SST');
      const json = await resp.json();
      const d = json.dados || {};

      // ASOs
      const tbodyAso = document.getElementById('tbody-sst-asos');
      if (tbodyAso) {
        const asos = d.asos || [];
        tbodyAso.innerHTML = asos.length ? '' : '<tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Nenhum ASO cadastrado.</td></tr>';
        asos.forEach(a => {
          tbodyAso.innerHTML += `
            <tr>
              <td><strong>${a.nome_colaborador || `Colaborador #${a.colaborador_id}`}</strong></td>
              <td>${a.tipo_exame}</td>
              <td>${a.data_exame}</td>
              <td>${a.data_validade || '-'}</td>
              <td><span class="badge-status ${a.resultado_aptidao === 'APTO' ? 'badge-fechada' : 'badge-severidade-critica'}">${a.resultado_aptidao}</span></td>
              <td>${a.medico_examinador_nome} (${a.medico_examinador_crm})</td>
              <td>${a.exames_complementares || 'Clínico'}</td>
            </tr>
          `;
        });
      }

      // EPIs
      const tbodyEpi = document.getElementById('tbody-sst-epis');
      if (tbodyEpi) {
        const epis = d.epis_entregas || [];
        tbodyEpi.innerHTML = epis.length ? '' : '<tr><td colspan="6" class="text-center text-muted" style="padding: 2rem;">Nenhuma entrega de EPI registrada.</td></tr>';
        epis.forEach(e => {
          tbodyEpi.innerHTML += `
            <tr>
              <td><strong>${e.nome_colaborador || `Colaborador #${e.colaborador_id}`}</strong></td>
              <td>${e.nome_epi}</td>
              <td><strong>CA: ${e.numero_ca}</strong></td>
              <td>${e.validade_ca || '-'}</td>
              <td>${e.data_entrega}</td>
              <td><span class="badge-status badge-fechada">${e.termo_assinado ? 'Assinado / Biometria' : 'Pendente'}</span></td>
            </tr>
          `;
        });
      }

      // Treinamentos
      const tbodyTrein = document.getElementById('tbody-sst-treinamentos');
      if (tbodyTrein) {
        const trein = d.treinamentos || [];
        tbodyTrein.innerHTML = trein.length ? '' : '<tr><td colspan="5" class="text-center text-muted" style="padding: 2rem;">Nenhum treinamento cadastrado.</td></tr>';
        trein.forEach(t => {
          tbodyTrein.innerHTML += `
            <tr>
              <td><strong>${t.nome_treinamento}</strong> (${t.norma_regulamentadora || 'NR'})</td>
              <td>${t.carga_horaria_horas} horas</td>
              <td>${t.validade_meses} meses</td>
              <td>${t.reciclagem_obrigatoria ? 'Sim' : 'Não'}</td>
              <td><strong>${t.total_participantes || 0}</strong></td>
            </tr>
          `;
        });
      }

      // CATs
      const tbodyCat = document.getElementById('tbody-sst-cats');
      if (tbodyCat) {
        const cats = d.cats || [];
        tbodyCat.innerHTML = cats.length ? '' : '<tr><td colspan="6" class="text-center text-muted" style="padding: 2rem;">Nenhuma CAT emitida.</td></tr>';
        cats.forEach(c => {
          tbodyCat.innerHTML += `
            <tr>
              <td><strong>${c.numero_cat || `CAT #${c.id}`}</strong></td>
              <td>${c.nome_colaborador || `Colaborador #${c.colaborador_id}`}</td>
              <td>${c.tipo_acidente}</td>
              <td>${c.data_hora_acidente}</td>
              <td>${c.parte_corpo_atingida || '-'} (CID: ${c.codigo_cid || '-'})</td>
              <td><span class="badge-status badge-fechada">${c.status_esocial || 'GERADA (S-2210)'}</span></td>
            </tr>
          `;
        });
      }
    } catch (e) {
      console.warn('Erro ao carregar SST:', e);
    }
  },

  async salvarASO() {
    const colabId = document.getElementById('aso-colab-select')?.value;
    const tipo = document.getElementById('aso-tipo-select')?.value;
    const aptidao = document.getElementById('aso-resultado-select')?.value;
    const dataExame = document.getElementById('aso-data-exame')?.value;
    const dataValidade = document.getElementById('aso-data-validade')?.value;
    const medico = document.getElementById('aso-medico-nome')?.value?.trim();
    const crm = document.getElementById('aso-medico-crm')?.value?.trim();

    if (!colabId || !tipo || !aptidao || !dataExame || !dataValidade || !medico || !crm) {
      exibirToast('Preencha todos os campos obrigatórios do ASO.', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/sst/aso`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: parseInt(colabId, 10),
          tipo_exame: tipo,
          resultado_aptidao: aptidao,
          data_exame: dataExame,
          data_validade: dataValidade,
          medico_examinador_nome: medico,
          medico_examinador_crm: crm
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao registrar ASO.', 'error');
        return;
      }
      exibirToast('ASO registrado com sucesso! Evento eSocial S-2220 gerado.', 'success');
      document.getElementById('modal-novo-aso')?.classList.add('hidden');
      await this.carregarSST();
      await this.carregarDashboard();
    } catch (e) {
      exibirToast('Erro de comunicação ao registrar ASO.', 'error');
    }
  },

  async salvarEntregaEPI() {
    const colabId = document.getElementById('epi-colab-select')?.value;
    const epiId = document.getElementById('epi-catalogo-select')?.value;
    const dataEntrega = document.getElementById('epi-data-entrega')?.value;
    const quantidade = parseInt(document.getElementById('epi-quantidade')?.value || 1, 10);
    const assinado = document.getElementById('epi-termo-assinado')?.checked || false;

    if (!colabId || !epiId || !dataEntrega) {
      exibirToast('Preencha os campos obrigatórios para registrar o EPI.', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/sst/epi/entrega`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: parseInt(colabId, 10),
          epi_id: parseInt(epiId, 10),
          data_entrega: dataEntrega,
          quantidade: quantidade,
          termo_assinado: assinado
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        // Bloqueio se CA estiver vencido (RN-039)
        exibirToast(json.mensagem || 'Erro ao registrar entrega de EPI.', 'error');
        return;
      }
      exibirToast('Ficha de EPI registrada com termo de responsabilidade!', 'success');
      document.getElementById('modal-entrega-epi')?.classList.add('hidden');
      await this.carregarSST();
    } catch (e) {
      exibirToast('Erro ao comunicar entrega de EPI.', 'error');
    }
  },

  async salvarCAT() {
    const colabId = document.getElementById('cat-colab-select')?.value;
    const tipo = document.getElementById('cat-tipo-select')?.value;
    const dataHora = document.getElementById('cat-data-hora')?.value;
    const local = document.getElementById('cat-local')?.value?.trim();
    const parteCorpo = document.getElementById('cat-parte-corpo')?.value?.trim();
    const cid = document.getElementById('cat-cid')?.value?.trim();

    if (!colabId || !tipo || !dataHora || !local) {
      exibirToast('Preencha os campos obrigatórios da CAT.', 'error');
      return;
    }

    try {
      const resp = await fetch(`${API_BASE}/sst/cat`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: parseInt(colabId, 10),
          tipo_acidente: tipo,
          data_hora_acidente: dataHora,
          local_acidente: local,
          parte_corpo_atingida: parteCorpo,
          codigo_cid: cid
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao emitir CAT.', 'error');
        return;
      }
      exibirToast('CAT emitida com sucesso! Evento eSocial S-2210 gerado.', 'success');
      document.getElementById('modal-nova-cat')?.classList.add('hidden');
      await this.carregarSST();
    } catch (e) {
      exibirToast('Erro de comunicação ao emitir CAT.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // ESOCIAL & OBRIGAÇÕES (RF-131 A RF-140, RN-065 A RN-072)
  // --------------------------------------------------------------------------
  async carregarESocial() {
    const tbody = document.getElementById('tbody-esocial-eventos');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Carregando eventos do eSocial...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/esocial/eventos`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar eventos do eSocial');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Nenhum evento do eSocial gerado.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(ev => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${ev.tipo_evento}</strong></td>
          <td>${ev.descricao || ev.tipo_evento}</td>
          <td>${ev.competencia || ev.data_geracao || '-'}</td>
          <td>${ev.nome_colaborador || (ev.colaborador_id ? `Colaborador #${ev.colaborador_id}` : 'Empresa / Tabela')}</td>
          <td><span class="badge-status ${ev.status === 'TRANSMITIDO' || ev.status === 'PROCESSADO' ? 'badge-fechada' : 'badge-calculada'}">${ev.status}</span></td>
          <td><span class="text-xs font-mono">${ev.recibo_entrega || ev.numero_protocolo || 'Pendente de envio'}</span></td>
          <td>
            <button class="btn btn-outline btn-sm btn-ver-xml" data-tipo="${ev.tipo_evento}" data-id="${ev.id}">Ver XML</button>
          </td>
        `;
        tbody.appendChild(tr);
      });

      document.querySelectorAll('.btn-ver-xml').forEach(b => {
        b.addEventListener('click', () => {
          const id = b.getAttribute('data-id');
          const ev = lista.find(x => String(x.id) === String(id));
          if (ev) PlataformaManager.exibirModalXML(ev);
        });
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar eSocial.</td></tr>';
    }
  },

  exibirModalXML(ev) {
    const modal = document.getElementById('modal-xml-esocial');
    const titulo = document.getElementById('xml-modal-titulo');
    const pre = document.getElementById('xml-modal-conteudo');
    if (modal && titulo && pre) {
      titulo.textContent = `XML do Evento ${ev.tipo_evento} — ID #${ev.id}`;
      pre.textContent = ev.xml_gerado || `<?xml version="1.0" encoding="UTF-8"?>\n<eSocial xmlns="http://www.esocial.gov.br/schema/evt/${ev.tipo_evento}/v_S_01_02_00">\n  <evt${ev.tipo_evento} id="ID1${ev.id}00000000">\n    <ideEvento>\n      <tpAmb>2</tpAmb>\n      <procEmi>1</procEmi>\n      <verProc>RH2.0_2026</verProc>\n    </ideEvento>\n  </evt${ev.tipo_evento}>\n</eSocial>`;
      modal.classList.remove('hidden');
    }
  },

  async transmitirLoteESocial() {
    if (!confirm('Deseja gerar e assinar digitalmente o lote de eventos do eSocial para transmissão ao ambiente nacional?')) return;

    try {
      const resp = await fetch(`${API_BASE}/esocial/transmitir`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao transmitir lote.', 'error');
        return;
      }
      exibirToast(`Lote eSocial transmitido com sucesso! Protocolo: ${json.dados?.protocolo || 'BR-2026-OK'}`, 'success');
      await this.carregarESocial();
    } catch (e) {
      exibirToast('Erro de conexão ao transmitir eSocial.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // INTEGRAÇÕES BANCÁRIAS — REMESSA CNAB 240 (RF-097, RF-178)
  // --------------------------------------------------------------------------
  async gerarCNAB240() {
    const banco = document.getElementById('cnab-banco-select')?.value || '001';
    const competencia = document.getElementById('cnab-competencia-input')?.value || '2026-03';
    const dataPagamento = document.getElementById('cnab-data-pagamento')?.value;

    try {
      const resp = await fetch(`${API_BASE}/integracoes/cnab`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          codigo_banco: banco,
          competencia: competencia,
          data_pagamento: dataPagamento
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao gerar remessa CNAB.', 'error');
        return;
      }

      const d = json.dados || {};
      this.cnabArquivoGerado = d.arquivo_conteudo || '';

      const resumo = document.getElementById('cnab-resumo-lote');
      const preview = document.getElementById('cnab-conteudo-preview');
      const btnDownload = document.getElementById('btn-download-cnab');

      if (resumo) {
        resumo.innerHTML = `
          <strong style="color: #16a34a;">Remessa gerada com sucesso!</strong><br>
          &bull; Banco: <strong>${d.banco_nome || banco}</strong> | Arquivo: <strong>${d.nome_arquivo || 'REMESSA.REM'}</strong><br>
          &bull; Total de Colaboradores Creditados: <strong>${d.total_registros || 0}</strong><br>
          &bull; Valor Total do Lote: <strong>R$ ${(d.valor_total || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</strong>
        `;
      }
      if (preview) {
        preview.textContent = this.cnabArquivoGerado;
        preview.style.display = 'block';
      }
      if (btnDownload) {
        btnDownload.classList.remove('hidden');
      }

      exibirToast('Arquivo CNAB 240 gerado de acordo com o padrão FEBRABAN!', 'success');
    } catch (e) {
      exibirToast('Erro ao comunicar com gerador CNAB.', 'error');
    }
  },

  downloadCNAB() {
    if (!this.cnabArquivoGerado) return;
    const blob = new Blob([this.cnabArquivoGerado], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `REMESSA_FOLHA_${new Date().toISOString().slice(0, 10)}.REM`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    exibirToast('Download do arquivo de remessa concluído.', 'info');
  },

  // --------------------------------------------------------------------------
  // AUDITORIA GERAL (RT-01, RF-191 A RF-200)
  // --------------------------------------------------------------------------
  async carregarAuditoria() {
    const tbody = document.getElementById('tbody-auditoria');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding: 2rem;">Carregando trilha de auditoria...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/auditoria`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar auditoria');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding: 2rem;">Nenhum registro de auditoria encontrado.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(log => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${log.data_hora}</td>
          <td><strong>${log.usuario_nome || log.usuario_id || 'Sistema'}</strong></td>
          <td><span class="badge-status badge-calculada">${log.tipo_operacao || log.acao}</span></td>
          <td>${log.modulo || log.tabela_afetada || '-'}</td>
          <td><span class="font-mono text-xs">${log.ip_origem || '127.0.0.1'}</span></td>
          <td style="max-width: 320px; word-break: break-all; font-size: 0.8rem; color: var(--text-muted);">${log.detalhes || log.justificativa || '-'}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger" style="padding: 2rem;">Erro ao consultar trilha de auditoria.</td></tr>';
    }
  },

  // --------------------------------------------------------------------------
  // MULTIEMPRESA & GOVERNANÇA (RF-171 A RF-180)
  // --------------------------------------------------------------------------
  async carregarMultiempresa() {
    const tbody = document.getElementById('tbody-multiempresa');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Carregando empresas...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/multiempresa`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar empresas');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Nenhuma empresa cadastrada.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(emp => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${emp.razao_social}</strong></td>
          <td>${emp.nome_fantasia || '-'}</td>
          <td>${emp.cnpj}</td>
          <td>${emp.cnae_principal || '-'}</td>
          <td>Grau ${emp.grau_risco || 3}</td>
          <td>${emp.fap ? Number(emp.fap).toFixed(4) : '1.0000'}</td>
          <td><span class="badge-status badge-fechada">${emp.ativo ? 'Ativa' : 'Inativa'}</span></td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center text-danger" style="padding: 2rem;">Erro ao listar empresas.</td></tr>';
    }
  },

  // --------------------------------------------------------------------------
  // CONFIGURAÇÃO DE EVENTOS DE MODAIS E BOTÕES
  // --------------------------------------------------------------------------
  configurarEventosModais() {
    // Helper de fechamento genérico
    const fecharModal = (modalId) => {
      document.getElementById(modalId)?.classList.add('hidden');
    };

    // Modal Nova Admissão
    document.getElementById('btn-abrir-nova-admissao')?.addEventListener('click', () => {
      document.getElementById('modal-nova-admissao')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-admissao')?.addEventListener('click', () => fecharModal('modal-nova-admissao'));
    document.getElementById('btn-cancelar-modal-admissao')?.addEventListener('click', () => fecharModal('modal-nova-admissao'));
    document.getElementById('btn-salvar-nova-admissao')?.addEventListener('click', () => this.salvarNovaAdmissao());

    // Modal Checklist Admissão
    document.getElementById('btn-fechar-checklist-admissao')?.addEventListener('click', () => fecharModal('modal-checklist-admissao'));
    document.getElementById('btn-concluir-checklist')?.addEventListener('click', () => {
      fecharModal('modal-checklist-admissao');
      this.carregarAdmissoes();
    });

    // Modal Registrar Ponto
    document.getElementById('btn-abrir-bater-ponto')?.addEventListener('click', () => {
      const inputDataHora = document.getElementById('ponto-datahora-registro');
      if (inputDataHora) {
        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        inputDataHora.value = now.toISOString().slice(0, 16);
      }
      document.getElementById('modal-registrar-ponto')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-ponto')?.addEventListener('click', () => fecharModal('modal-registrar-ponto'));
    document.getElementById('btn-cancelar-modal-ponto')?.addEventListener('click', () => fecharModal('modal-registrar-ponto'));
    document.getElementById('btn-confirmar-batida-ponto')?.addEventListener('click', () => this.registrarBatidaPonto());

    // Modal Solicitar Ajuste Ponto
    document.getElementById('btn-abrir-ajuste-ponto')?.addEventListener('click', () => {
      document.getElementById('modal-ajuste-ponto')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-ajuste')?.addEventListener('click', () => fecharModal('modal-ajuste-ponto'));
    document.getElementById('btn-cancelar-modal-ajuste')?.addEventListener('click', () => fecharModal('modal-ajuste-ponto'));
    document.getElementById('btn-confirmar-ajuste-ponto')?.addEventListener('click', () => this.solicitarAjustePonto());

    // Modal Programar Férias
    document.getElementById('btn-abrir-programar-ferias')?.addEventListener('click', () => {
      document.getElementById('modal-programar-ferias')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-ferias')?.addEventListener('click', () => fecharModal('modal-programar-ferias'));
    document.getElementById('btn-cancelar-modal-ferias')?.addEventListener('click', () => fecharModal('modal-programar-ferias'));
    document.getElementById('btn-confirmar-programar-ferias')?.addEventListener('click', () => this.salvarProgramarFerias());

    // Modal Afastamento
    document.getElementById('btn-abrir-novo-afastamento')?.addEventListener('click', () => {
      document.getElementById('modal-novo-afastamento')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-afastamento')?.addEventListener('click', () => fecharModal('modal-novo-afastamento'));
    document.getElementById('btn-cancelar-modal-afastamento')?.addEventListener('click', () => fecharModal('modal-novo-afastamento'));
    document.getElementById('btn-confirmar-afastamento')?.addEventListener('click', () => this.salvarAfastamento());

    // Modal Rescisão
    document.getElementById('btn-abrir-calcular-rescisao')?.addEventListener('click', () => {
      document.getElementById('resc-preview-box')?.classList.add('hidden');
      document.getElementById('modal-calcular-rescisao')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-rescisao')?.addEventListener('click', () => fecharModal('modal-calcular-rescisao'));
    document.getElementById('btn-cancelar-modal-rescisao')?.addEventListener('click', () => fecharModal('modal-calcular-rescisao'));
    document.getElementById('btn-previa-rescisao')?.addEventListener('click', () => this.calcularRescisao(true));
    document.getElementById('btn-confirmar-rescisao')?.addEventListener('click', () => this.calcularRescisao(false));

    // Modal ASO
    document.getElementById('btn-abrir-novo-aso')?.addEventListener('click', () => {
      document.getElementById('modal-novo-aso')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-aso')?.addEventListener('click', () => fecharModal('modal-novo-aso'));
    document.getElementById('btn-cancelar-modal-aso')?.addEventListener('click', () => fecharModal('modal-novo-aso'));
    document.getElementById('btn-confirmar-aso')?.addEventListener('click', () => this.salvarASO());

    // Modal EPI
    document.getElementById('btn-abrir-entrega-epi')?.addEventListener('click', () => {
      document.getElementById('modal-entrega-epi')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-epi')?.addEventListener('click', () => fecharModal('modal-entrega-epi'));
    document.getElementById('btn-cancelar-modal-epi')?.addEventListener('click', () => fecharModal('modal-entrega-epi'));
    document.getElementById('btn-confirmar-entrega-epi')?.addEventListener('click', () => this.salvarEntregaEPI());

    // Modal CAT
    document.getElementById('btn-abrir-nova-cat')?.addEventListener('click', () => {
      document.getElementById('modal-nova-cat')?.classList.remove('hidden');
    });
    document.getElementById('btn-fechar-modal-cat')?.addEventListener('click', () => fecharModal('modal-nova-cat'));
    document.getElementById('btn-cancelar-modal-cat')?.addEventListener('click', () => fecharModal('modal-nova-cat'));
    document.getElementById('btn-confirmar-cat')?.addEventListener('click', () => this.salvarCAT());

    // Modal XML eSocial
    document.getElementById('btn-fechar-modal-xml')?.addEventListener('click', () => fecharModal('modal-xml-esocial'));
    document.getElementById('btn-fechar-modal-xml-rodape')?.addEventListener('click', () => fecharModal('modal-xml-esocial'));
  },

  configurarBotoesAcao() {
    // Dashboard
    document.getElementById('btn-atualizar-indicadores')?.addEventListener('click', () => this.carregarDashboard());

    // Pendências
    document.getElementById('btn-scanner-pendencias')?.addEventListener('click', async () => {
      exibirToast('Executando varredura contínua de pendências...', 'info');
      await this.carregarPendencias();
      await this.carregarDashboard();
      exibirToast('Varredura concluída.', 'success');
    });
    document.getElementById('filtro-pendencia-status')?.addEventListener('change', () => this.carregarPendencias());
    document.getElementById('filtro-pendencia-severidade')?.addEventListener('change', () => this.carregarPendencias());

    // Ponto
    document.getElementById('btn-carregar-espelho-ponto')?.addEventListener('click', () => this.carregarEspelhoPonto());

    // eSocial
    document.getElementById('btn-esocial-transmitir')?.addEventListener('click', () => this.transmitirLoteESocial());

    // CNAB 240
    document.getElementById('btn-gerar-cnab240')?.addEventListener('click', () => this.gerarCNAB240());
    document.getElementById('btn-download-cnab')?.addEventListener('click', () => this.downloadCNAB());

    // Auditoria
    document.getElementById('btn-atualizar-auditoria')?.addEventListener('click', () => this.carregarAuditoria());
  }
};
"""

def main():
    with open("frontend/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # Verificar se PlataformaManager já existe
    if "const PlataformaManager =" in js:
        print("PlataformaManager já existe em frontend/app.js")
        return

    # Inserir antes da inicialização final
    alvo = "document.addEventListener('DOMContentLoaded', () => {"
    if alvo in js:
        parts = js.rsplit(alvo, 1)
        novo_js = parts[0] + PLATAFORMA_JS + "\n" + alvo + "\n  PlataformaManager.inicializar();" + parts[1]
    else:
        novo_js = js + "\n" + PLATAFORMA_JS

    # Também chamar inicialização inicial no exibirTelaSistema se existir
    if "exibirTelaSistema(usuario) {" in novo_js:
        novo_js = novo_js.replace(
            "exibirTelaSistema(usuario) {",
            "exibirTelaSistema(usuario) {\n    if (typeof PlataformaManager !== 'undefined') { PlataformaManager.carregarDashboard(); }\n"
        )

    with open("frontend/app.js", "w", encoding="utf-8") as f:
        f.write(novo_js)

    print("PlataformaManager integrado a frontend/app.js com sucesso!")

if __name__ == "__main__":
    main()
