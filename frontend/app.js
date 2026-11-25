/**
 * Sistema de Departamento Pessoal — Módulo 1: Cadastro de Colaboradores
 * Lógica do Frontend (Vanilla JavaScript)
 * Integração com API REST (persistência exclusiva no banco PostgreSQL)
 */

// Estado global da aplicação
const Estado = {
  usuarioAutenticado: null,
  token: sessionStorage.getItem('AUTH_TOKEN') || null,
  colaboradores: [],
  colaboradorEmEdicao: null,
  colaboradorParaInativar: null,
  filtros: {
    termo: '',
    nome: '',
    matricula: '',
    cpf: '',
    situacao: 'ativo',
    setor: '',
    cargo: ''
  },
  usaApi: window.location.protocol.startsWith('http')
};

function getApiBase() {
  if (typeof window !== 'undefined' && window.location) {
    const { protocol, hostname, port } = window.location;
    // Se acessado via file://
    if (protocol === 'file:') {
      return 'http://127.0.0.1:8000/api';
    }
    // Se acessado localmente em outra porta dev (ex: Live Server 5500, Vite 5173, etc.)
    if ((hostname === 'localhost' || hostname === '127.0.0.1') && port && port !== '8000') {
      return 'http://127.0.0.1:8000/api';
    }
  }
  return '/api';
}

const API_BASE = getApiBase();

function getAuthHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  const token = Estado.token || sessionStorage.getItem('AUTH_TOKEN');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

// ============================================================================
// Utilitários de Máscara e Validação
// ============================================================================
function normalizarCpf(cpf) {
  return String(cpf || '').replace(/\D/g, '');
}

function formatarCpf(cpf) {
  const d = normalizarCpf(cpf);
  if (d.length === 11) {
    return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9, 11)}`;
  }
  return cpf;
}

function mascaraCpf(valor) {
  let v = normalizarCpf(valor).slice(0, 11);
  if (v.length > 9) return `${v.slice(0, 3)}.${v.slice(3, 6)}.${v.slice(6, 9)}-${v.slice(9)}`;
  if (v.length > 6) return `${v.slice(0, 3)}.${v.slice(3, 6)}.${v.slice(6)}`;
  if (v.length > 3) return `${v.slice(0, 3)}.${v.slice(3)}`;
  return v;
}

function mascaraTelefone(valor) {
  let v = String(valor || '').replace(/\D/g, '').slice(0, 11);
  if (v.length > 10) return `(${v.slice(0, 2)}) ${v.slice(2, 7)}-${v.slice(7)}`;
  if (v.length > 6) return `(${v.slice(0, 2)}) ${v.slice(2, 6)}-${v.slice(6)}`;
  if (v.length > 2) return `(${v.slice(0, 2)}) ${v.slice(2)}`;
  return v;
}

function mascaraCep(valor) {
  let v = String(valor || '').replace(/\D/g, '').slice(0, 8);
  if (v.length > 5) return `${v.slice(0, 5)}-${v.slice(5)}`;
  return v;
}

function formatarMoeda(valor) {
  const num = typeof valor === 'number' ? valor : parseFloat(String(valor).replace(/[^\d,-]/g, '').replace(',', '.')) || 0;
  return num.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatarDataBR(dataIso) {
  if (!dataIso) return '--';
  const partes = String(dataIso).split('T')[0].split('-');
  if (partes.length === 3) {
    return `${partes[2]}/${partes[1]}/${partes[0]}`;
  }
  return dataIso;
}

function validarCpf(cpf) {
  // O navegador valida apenas o formato. A validação matemática é autoritativa no backend,
  // onde pode ser relaxada somente com RH2_ALLOW_FAKE_CPFS em ambiente não produtivo.
  return normalizarCpf(cpf).length === 11;
}

function validarEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(email).trim());
}

// ============================================================================
// Notificações Toast
// ============================================================================
function exibirToast(mensagem, tipo = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${tipo}`;

  let icone = '✓';
  if (tipo === 'error') icone = '✕';
  if (tipo === 'warning') icone = '⚠';

  toast.innerHTML = `<strong>${icone}</strong> <span>${mensagem}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ============================================================================
// Paginação Reutilizável Enterprise para Tabelas DOM
// ============================================================================
function aplicarPaginacaoTabela(tbodyId, pagerId, pageSize = 12) {
  const tbody = document.getElementById(tbodyId);
  const pager = document.getElementById(pagerId);
  if (!tbody || !pager) return;

  const rows = Array.from(tbody.querySelectorAll('tr'));
  const total = rows.length;
  if (total <= pageSize) {
    rows.forEach(r => { r.style.display = ''; });
    if (total === 0) {
      pager.classList.add('hidden');
      pager.innerHTML = '';
    } else {
      pager.classList.remove('hidden');
      pager.innerHTML = `<span class="pagination-info">Exibindo ${total} registro(s)</span><div class="pagination-controls"></div>`;
    }
    return;
  }

  const totalPages = Math.ceil(total / pageSize);
  let currentPage = Number(pager.dataset.page || 1);
  if (currentPage > totalPages) currentPage = 1;

  const renderPage = (page) => {
    currentPage = page;
    pager.dataset.page = String(page);
    const start = (page - 1) * pageSize;
    const end = start + pageSize;

    rows.forEach((row, idx) => {
      row.style.display = (idx >= start && idx < end) ? '' : 'none';
    });

    const showingEnd = Math.min(end, total);
    let buttonsHtml = `
      <button type="button" class="page-btn" data-p="${page - 1}" ${page <= 1 ? 'disabled' : ''}>Anterior</button>
    `;
    for (let p = 1; p <= totalPages; p++) {
      if (totalPages > 7 && Math.abs(p - page) > 2 && p !== 1 && p !== totalPages) {
        if (p === 2 || p === totalPages - 1) buttonsHtml += `<span class="text-muted" style="padding:0 0.25rem;">...</span>`;
        continue;
      }
      buttonsHtml += `<button type="button" class="page-btn ${p === page ? 'active' : ''}" data-p="${p}">${p}</button>`;
    }
    buttonsHtml += `
      <button type="button" class="page-btn" data-p="${page + 1}" ${page >= totalPages ? 'disabled' : ''}>Próxima</button>
    `;

    pager.classList.remove('hidden');
    pager.innerHTML = `
      <span class="pagination-info">Mostrando ${start + 1}–${showingEnd} de ${total} registros</span>
      <div class="pagination-controls">${buttonsHtml}</div>
    `;

    pager.querySelectorAll('.page-btn[data-p]').forEach(btn => {
      btn.addEventListener('click', () => {
        const targetPage = Number(btn.getAttribute('data-p'));
        if (targetPage >= 1 && targetPage <= totalPages) renderPage(targetPage);
      });
    });
  };

  renderPage(currentPage);
}

// ============================================================================
// ============================================================================
// Gerenciador de Autenticação e Sessão (RF-40, RF-41, RF-43)
// ============================================================================
const AuthManager = {
  token: sessionStorage.getItem('AUTH_TOKEN') || null,
  usuario: null,

  async inicializar() {
    this.configurarEventosLogin();

    // Tenta validar a sessão atual com o backend
    try {
      const resp = await fetch(`${API_BASE}/auth/me`, {
        method: 'GET',
        headers: getAuthHeaders(),
        credentials: 'include'
      });

      if (resp.ok) {
        const data = await resp.json();
        if (data.sucesso && data.usuario) {
          this.usuario = data.usuario;
          Estado.usuarioAutenticado = data.usuario;
          this.exibirTelaSistema(data.usuario);
          await carregarColaboradores();
          return;
        }
      }
    } catch (e) {
      console.warn('Sessão não autenticada no servidor.');
    }

    // Não autenticado: exibe tela de login
    this.exibirTelaLogin();
  },

  pararMonitoramentoSessao() {
    if (!this._monitoramentoSessao) return;
    ['pointerdown', 'keydown', 'touchstart', 'scroll'].forEach(evento =>
      document.removeEventListener(evento, this._monitoramentoSessao.atividade, true)
    );
    document.removeEventListener('visibilitychange', this._monitoramentoSessao.visibilidade);
    this._monitoramentoSessao = null;
  },

  iniciarMonitoramentoSessao() {
    if (this._monitoramentoSessao) return;
    const intervaloMinimo = 5 * 60 * 1000;
    let ultimaRenovacao = 0;
    const renovar = async () => {
      if (!this.usuario || document.hidden || Date.now() - ultimaRenovacao < intervaloMinimo) return;
      ultimaRenovacao = Date.now();
      try {
        const resp = await fetch(`${API_BASE}/auth/me`, {
          method: 'GET',
          headers: getAuthHeaders(),
          credentials: 'include'
        });
        if (resp.status === 401) {
          this.exibirTelaLogin('Sua sessão expirou. Entre novamente para continuar.');
          exibirToast('Sua sessão expirou. Entre novamente para continuar.', 'warning');
        }
      } catch (e) {
        console.warn('Falha transitória ao renovar sessão; a sessão local foi mantida.');
      }
    };
    const atividade = () => { renovar(); };
    const visibilidade = () => { if (!document.hidden) renovar(); };
    this._monitoramentoSessao = { atividade, visibilidade };
    ['pointerdown', 'keydown', 'touchstart', 'scroll'].forEach(evento =>
      document.addEventListener(evento, atividade, { passive: true, capture: true })
    );
    document.addEventListener('visibilitychange', visibilidade);
  },

  exibirTelaLogin(mensagemErro = null) {
    this.pararMonitoramentoSessao();
    const telaLogin = document.getElementById('tela-login');
    const telaSistema = document.getElementById('tela-sistema');
    if (telaLogin) telaLogin.classList.remove('hidden');
    if (telaSistema) telaSistema.classList.add('hidden');

    this.token = null;
    this.usuario = null;
    Estado.token = null;
    Estado.usuarioAutenticado = null;
    Estado.colaboradores = [];
    sessionStorage.removeItem('AUTH_TOKEN');

    renderizarTabela([]);
    if (typeof atualizarMetricas === 'function') {
      atualizarMetricas();
    }

    const alerta = document.getElementById('login-alerta');
    const alertaMsg = document.getElementById('login-alerta-mensagem');
    if (alerta && alertaMsg) {
      if (mensagemErro) {
        alertaMsg.textContent = mensagemErro;
        alerta.classList.remove('hidden');
      } else {
        alerta.classList.add('hidden');
      }
    }
  },

  exibirTelaSistema(usuario) {
    this.iniciarMonitoramentoSessao();
    if (typeof PlataformaManager !== 'undefined') { PlataformaManager.carregarDashboard(); }

    const telaLogin = document.getElementById('tela-login');
    const telaSistema = document.getElementById('tela-sistema');
    if (telaLogin) telaLogin.classList.add('hidden');
    if (telaSistema) telaSistema.classList.remove('hidden');

    const elNome = document.getElementById('header-user-nome');
    const elPerfil = document.getElementById('header-user-perfil');
    if (elNome) elNome.textContent = usuario.nome_completo || usuario.usuario;
    if (elPerfil) elPerfil.textContent = usuario.perfil || 'administrador';

    // Roteamento contextual por perfil de acesso (RBAC Enterprise)
    const perfil = (usuario.perfil || '').toLowerCase();
    if (perfil === 'colaborador') {
      this.navegarPara('portal-colaborador');
    } else if (perfil === 'gestor' || perfil === 'gestor_departamento') {
      this.navegarPara('portal-gestor');
    }
  },

  configurarEventosLogin() {
    const formLogin = document.getElementById('form-login');
    const btnToggleSenha = document.getElementById('btn-toggle-senha');
    const inputSenha = document.getElementById('login-senha');
    const inputIdentificador = document.getElementById('login-identificador');
    const btnLogout = document.getElementById('btn-logout');

    if (btnToggleSenha && inputSenha) {
      btnToggleSenha.addEventListener('click', () => {
        const isPassword = inputSenha.getAttribute('type') === 'password';
        inputSenha.setAttribute('type', isPassword ? 'text' : 'password');
        const iconClosed = document.getElementById('icon-eye-closed');
        const iconOpen = document.getElementById('icon-eye-open');
        if (iconClosed) iconClosed.classList.toggle('hidden', isPassword);
        if (iconOpen) iconOpen.classList.toggle('hidden', !isPassword);
      });
    }

    if (inputIdentificador) {
      inputIdentificador.addEventListener('input', () => {
        const err = document.getElementById('erro-login-identificador');
        const alertBox = document.getElementById('login-alerta');
        if (err) err.classList.add('hidden');
        if (alertBox) alertBox.classList.add('hidden');
      });
    }

    if (inputSenha) {
      inputSenha.addEventListener('input', () => {
        const err = document.getElementById('erro-login-senha');
        const alertBox = document.getElementById('login-alerta');
        if (err) err.classList.add('hidden');
        if (alertBox) alertBox.classList.add('hidden');
      });
    }

    if (formLogin) {
      formLogin.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.executarLogin();
      });
    }

    if (btnLogout) {
      btnLogout.addEventListener('click', async () => {
        await this.executarLogout();
      });
    }
  },

  async executarLogin() {
    const inputIdentificador = document.getElementById('login-identificador');
    const inputSenha = document.getElementById('login-senha');
    const erroIdentificador = document.getElementById('erro-login-identificador');
    const erroSenha = document.getElementById('erro-login-senha');
    const alerta = document.getElementById('login-alerta');
    const alertaMsg = document.getElementById('login-alerta-mensagem');
    const btnEntrar = document.getElementById('btn-entrar');
    const spinner = document.getElementById('login-spinner');
    const btnTexto = document.getElementById('btn-entrar-texto');

    const identificador = (inputIdentificador.value || '').trim();
    const senha = inputSenha.value || '';

    let valido = true;
    if (!identificador) {
      if (erroIdentificador) erroIdentificador.classList.remove('hidden');
      valido = false;
    } else {
      if (erroIdentificador) erroIdentificador.classList.add('hidden');
    }

    if (!senha) {
      if (erroSenha) erroSenha.classList.remove('hidden');
      valido = false;
    } else {
      if (erroSenha) erroSenha.classList.add('hidden');
    }

    if (!valido) return;

    // Indicador visual de processamento
    if (btnEntrar) btnEntrar.disabled = true;
    if (spinner) spinner.classList.remove('hidden');
    if (btnTexto) btnTexto.textContent = 'Autenticando...';
    if (alerta) alerta.classList.add('hidden');

    try {
      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ identificador, senha })
      });

      let data = null;
      try {
        data = await resp.json();
      } catch (parseError) {
        console.warn('A resposta do servidor não é um JSON válido:', resp.status, parseError);
      }

      if (resp.ok && data && data.sucesso) {
        this.token = data.token;
        this.usuario = data.usuario;
        Estado.token = data.token;
        Estado.usuarioAutenticado = data.usuario;
        sessionStorage.setItem('AUTH_TOKEN', data.token);

        inputSenha.value = '';
        this.exibirTelaSistema(data.usuario);
        exibirToast(`Autenticado como ${data.usuario.nome_completo}`, 'success');
        await carregarColaboradores();
      } else if (data && data.mensagem) {
        if (alertaMsg) alertaMsg.textContent = data.mensagem;
        if (alerta) alerta.classList.remove('hidden');
      } else if (resp.status === 404) {
        if (alertaMsg) alertaMsg.textContent = 'Serviço de autenticação não encontrado (HTTP 404). Verifique se o backend está ativo.';
        if (alerta) alerta.classList.remove('hidden');
      } else if (resp.status >= 500) {
        if (alertaMsg) alertaMsg.textContent = `Erro interno no servidor de autenticação (HTTP ${resp.status}). Tente novamente mais tarde.`;
        if (alerta) alerta.classList.remove('hidden');
      } else {
        if (alertaMsg) alertaMsg.textContent = 'Falha na autenticação. Verifique os dados informados.';
        if (alerta) alerta.classList.remove('hidden');
      }
    } catch (e) {
      console.error('Falha de conexão com o serviço de autenticação:', e);
      if (alertaMsg) alertaMsg.textContent = 'Serviço de autenticação temporariamente indisponível. Verifique se o servidor backend está rodando.';
      if (alerta) alerta.classList.remove('hidden');
    } finally {
      if (btnEntrar) btnEntrar.disabled = false;
      if (spinner) spinner.classList.add('hidden');
      if (btnTexto) btnTexto.textContent = 'Entrar no Sistema';
    }
  },

  async executarLogout() {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include'
      });
    } catch (e) {
      console.warn('Erro ao notificar logout no servidor:', e);
    } finally {
      this.exibirTelaLogin();
      exibirToast('Sessão encerrada com sucesso.', 'info');
    }
  }
};

// ============================================================================
// Camada de Dados (somente API / banco de dados — sem persistência local)
// ============================================================================
const MSG_API_INDISPONIVEL = 'Não foi possível comunicar com o servidor. Abra o sistema pelo endereço do servidor (http/https); os dados não são salvos no navegador.';

// Executa fetch e converte falhas de rede em erro claro (sem salvamento alternativo)
async function requisitarApi(url, opcoes) {
  let resp;
  try {
    resp = await fetch(url, opcoes);
  } catch (e) {
    throw new Error('Servidor indisponível: a operação não foi realizada e nada foi salvo. Tente novamente em instantes.');
  }
  if (resp.status === 503) {
    let msg = 'Banco de dados indisponível: a operação não foi realizada.';
    try { const j = await resp.json(); if (j && j.mensagem) msg = j.mensagem; } catch (_) { }
    throw new Error(msg);
  }
  return resp;
}

const DadosService = {
  async listar(filtros = {}) {
    // Visitante não autenticado não deve receber lista de colaboradores
    if (!Estado.usuarioAutenticado && !sessionStorage.getItem('AUTH_TOKEN')) {
      return [];
    }

    if (Estado.usaApi) {
      try {
        const params = new URLSearchParams();
        if (filtros.termo) params.set('q', filtros.termo);
        if (filtros.nome) params.set('nome', filtros.nome);
        if (filtros.matricula) params.set('matricula', filtros.matricula);
        if (filtros.cpf) params.set('cpf', filtros.cpf);
        if (filtros.situacao && filtros.situacao !== 'todos') params.set('situacao', filtros.situacao);
        if (filtros.setor) params.set('setor', filtros.setor);
        if (filtros.cargo) params.set('cargo', filtros.cargo);

        const resp = await requisitarApi(`${API_BASE}/colaboradores?${params.toString()}`, {
          headers: getAuthHeaders(),
          credentials: 'include'
        });

        if (resp.status === 401) {
          AuthManager.exibirTelaLogin('Sessão expirada. Faça login novamente.');
          return [];
        }

        const data = await resp.json();
        if (data.sucesso) return data.dados;
        throw new Error(data.mensagem || 'Erro ao carregar colaboradores.');
      } catch (e) {
        console.error('Erro ao consultar API:', e.message);
        throw e;
      }
    }
    throw new Error(MSG_API_INDISPONIVEL);
  },

  async obter(id) {
    if (Estado.usaApi) {
      const resp = await requisitarApi(`${API_BASE}/colaboradores/${id}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (resp.status === 401) {
        AuthManager.exibirTelaLogin('Sessão expirada. Faça login novamente.');
        throw new Error('Não autenticado.');
      }
      const data = await resp.json();
      if (data.sucesso) return data.dados;
      throw new Error(data.mensagem || 'Colaborador não encontrado.');
    }
    throw new Error(MSG_API_INDISPONIVEL);
  },

  async cadastrar(dados) {
    if (Estado.usaApi) {
      const resp = await requisitarApi(`${API_BASE}/colaboradores`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify(dados)
      });
      if (resp.status === 401) {
        AuthManager.exibirTelaLogin('Sessão expirada. Faça login novamente.');
        throw new Error('Não autenticado.');
      }
      const data = await resp.json();
      if (!resp.ok) {
        const err = new Error(data.mensagem || 'Erro de validação');
        err.erros = data.erros;
        throw err;
      }
      return data.dados;
    }
    throw new Error(MSG_API_INDISPONIVEL);
  },

  async atualizar(id, dados) {
    if (Estado.usaApi) {
      const resp = await requisitarApi(`${API_BASE}/colaboradores/${id}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify(dados)
      });
      if (resp.status === 401) {
        AuthManager.exibirTelaLogin('Sessão expirada. Faça login novamente.');
        throw new Error('Não autenticado.');
      }
      const data = await resp.json();
      if (!resp.ok) {
        const err = new Error(data.mensagem || 'Erro ao atualizar');
        err.erros = data.erros;
        throw err;
      }
      return data.dados;
    }
    throw new Error(MSG_API_INDISPONIVEL);
  },

  async inativar(id, motivo) {
    if (Estado.usaApi) {
      const resp = await requisitarApi(`${API_BASE}/colaboradores/${id}/inativar`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ motivo })
      });
      if (resp.status === 401) {
        AuthManager.exibirTelaLogin('Sessão expirada. Faça login novamente.');
        throw new Error('Não autenticado.');
      }
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.mensagem || 'Erro ao inativar colaborador');
      return data.dados;
    }
    throw new Error(MSG_API_INDISPONIVEL);
  },

  async reativar(id) {
    if (Estado.usaApi) {
      const resp = await requisitarApi(`${API_BASE}/colaboradores/${id}/reativar`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({})
      });
      if (resp.status === 401) {
        AuthManager.exibirTelaLogin('Sessão expirada. Faça login novamente.');
        throw new Error('Não autenticado.');
      }
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.mensagem || 'Erro ao reativar colaborador');
      return data.dados;
    }
    throw new Error(MSG_API_INDISPONIVEL);
  }
};

// ============================================================================
// Renderização e Controle da Interface
// ============================================================================
async function carregarColaboradores() {
  try {
    const lista = await DadosService.listar(Estado.filtros);
    Estado.colaboradores = lista;
    renderizarTabela(lista);
    atualizarMetricas();
  } catch (e) {
    exibirToast(e.message || 'Falha ao carregar colaboradores.', 'error');
  }
}

function renderizarTabela(lista) {
  const tbody = document.getElementById('corpo-tabela');
  const emptyState = document.getElementById('estado-vazio');
  tbody.innerHTML = '';

  if (!lista || lista.length === 0) {
    emptyState.classList.remove('hidden');
    aplicarPaginacaoTabela('corpo-tabela', 'paginacao-colaboradores', 12);
    return;
  }
  emptyState.classList.add('hidden');

  lista.forEach(colab => {
    const tr = document.createElement('tr');
    if (colab.situacao === 'inativo') tr.classList.add('row-inativo');

    const totalDep = colab.total_dependentes !== undefined ? colab.total_dependentes : (colab.dependentes ? colab.dependentes.length : 0);
    const badgeSituacao = colab.situacao === 'ativo'
      ? '<span class="badge badge-ativo">Ativo</span>'
      : '<span class="badge badge-inativo">Inativo</span>';

    const botaoStatus = colab.situacao === 'ativo'
      ? `<button class="btn-icon text-danger" title="Inativar Colaborador" onclick="abrirModalInativar(${colab.id})">
           <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></svg>
         </button>`
      : `<button class="btn-icon text-success" title="Reativar Colaborador" onclick="reativarColaborador(${colab.id})">
           <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
         </button>`;

    tr.innerHTML = `
      <td><strong>${colab.matricula}</strong></td>
      <td>
        <div class="colab-cell-main">
          <span class="colab-name">${colab.nome_completo}</span>
          <span class="colab-sub">CPF: ${colab.cpf}</span>
        </div>
      </td>
      <td>
        <div class="colab-cell-main">
          <span>${colab.cargo}</span>
          <span class="colab-sub">${colab.setor}</span>
        </div>
      </td>
      <td><span class="text-money">${formatarMoeda(colab.salario_base)}</span></td>
      <td>
        <span class="badge badge-dep">${totalDep} dep.</span>
      </td>
      <td>${badgeSituacao}</td>
      <td class="text-right">
        <div class="table-actions">
          <button class="btn-icon" title="Ver Detalhes e Auditoria" onclick="abrirModalDetalhes(${colab.id})">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
          </button>
          <button class="btn-icon" title="Editar Cadastro" onclick="abrirModalEditar(${colab.id})">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
          </button>
          ${botaoStatus}
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
  aplicarPaginacaoTabela('corpo-tabela', 'paginacao-colaboradores', 12);
}

async function atualizarMetricas() {
  try {
    // Busca todos sem filtro para computar totais gerais
    const todos = await DadosService.listar({ situacao: 'todos' });
    const ativos = todos.filter(c => c.situacao === 'ativo').length;
    const inativos = todos.filter(c => c.situacao === 'inativo').length;
    const setores = new Set(todos.map(c => c.setor).filter(Boolean)).size;

    document.getElementById('stat-total').textContent = todos.length;
    document.getElementById('stat-ativos').textContent = ativos;
    document.getElementById('stat-inativos').textContent = inativos;
    document.getElementById('stat-setores').textContent = setores;
  } catch (e) {
    console.error('Erro ao atualizar métricas:', e);
  }
}

// ============================================================================
// Gerenciamento de Dependentes Dinâmicos no Formulário
// ============================================================================
function adicionarLinhaDependente(dados = {}) {
  const container = document.getElementById('container-dependentes');
  const emptyHint = document.getElementById('dependentes-vazio');
  emptyHint.classList.add('hidden');

  const ehIrrf = dados.eh_dependente_irrf === undefined ? true : Boolean(Number(dados.eh_dependente_irrf));
  const ehSf = Boolean(Number(dados.eh_elegivel_salario_familia || 0));

  const row = document.createElement('div');
  row.className = 'dependente-row';
  row.style.flexWrap = 'wrap';
  row.innerHTML = `
    <div>
      <input type="text" class="form-control dep-nome" placeholder="Nome do Dependente *" value="${dados.nome || ''}" required>
    </div>
    <div>
      <input type="text" class="form-control dep-cpf" placeholder="CPF (Opcional)" maxlength="14" value="${dados.cpf || ''}">
    </div>
    <div>
      <input type="date" class="form-control dep-data-nasc" title="Data de Nascimento" value="${dados.data_nascimento || ''}">
    </div>
    <div>
      <select class="form-control select-control dep-parentesco" required>
        <option value="">Parentesco *</option>
        <option value="Filho(a)" ${dados.parentesco === 'Filho(a)' ? 'selected' : ''}>Filho(a)</option>
        <option value="Cônjuge/Companheiro(a)" ${dados.parentesco === 'Cônjuge/Companheiro(a)' ? 'selected' : ''}>Cônjuge/Companheiro(a)</option>
        <option value="Pai/Mãe" ${dados.parentesco === 'Pai/Mãe' ? 'selected' : ''}>Pai/Mãe</option>
        <option value="Enteado(a)" ${dados.parentesco === 'Enteado(a)' ? 'selected' : ''}>Enteado(a)</option>
        <option value="Irmão(ã)" ${dados.parentesco === 'Irmão(ã)' ? 'selected' : ''}>Irmão(ã)</option>
        <option value="Outro" ${dados.parentesco === 'Outro' ? 'selected' : ''}>Outro</option>
      </select>
    </div>
    <div style="display:flex; gap:0.6rem; align-items:center; font-size:0.78rem;">
      <label title="Dependente para dedução de IRRF"><input type="checkbox" class="dep-irrf" ${ehIrrf ? 'checked' : ''}> IRRF</label>
      <label title="Elegível ao Salário-Família"><input type="checkbox" class="dep-sf" ${ehSf ? 'checked' : ''}> Sal. Família</label>
    </div>
    <div>
      <button type="button" class="btn-icon text-danger btn-remover-dep" title="Remover Dependente">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
      </button>
    </div>
  `;

  // Máscara no CPF do dependente
  const cpfInput = row.querySelector('.dep-cpf');
  cpfInput.addEventListener('input', (e) => e.target.value = mascaraCpf(e.target.value));

  // Remoção
  row.querySelector('.btn-remover-dep').addEventListener('click', () => {
    row.remove();
    if (container.children.length === 0) emptyHint.classList.remove('hidden');
  });

  container.appendChild(row);
}

function coletarDependentesDoFormulario() {
  const rows = document.querySelectorAll('.dependente-row');
  const deps = [];
  rows.forEach(r => {
    const nome = r.querySelector('.dep-nome').value.trim();
    const cpf = r.querySelector('.dep-cpf').value.trim();
    const data_nascimento = r.querySelector('.dep-data-nasc')?.value || '';
    const parentesco = r.querySelector('.dep-parentesco').value;
    const eh_dependente_irrf = r.querySelector('.dep-irrf')?.checked ? 1 : 0;
    const eh_elegivel_salario_familia = r.querySelector('.dep-sf')?.checked ? 1 : 0;
    if (nome || parentesco) {
      deps.push({ nome, cpf, data_nascimento, parentesco, eh_dependente_irrf, eh_elegivel_salario_familia });
    }
  });
  return deps;
}

// ============================================================================
// Modais: Formulário de Cadastro / Edição
// ============================================================================
function limparErrosFormulario() {
  document.querySelectorAll('.field-error').forEach(el => el.textContent = '');
  document.querySelectorAll('.form-control').forEach(el => el.classList.remove('is-invalid'));
  const alerta = document.getElementById('form-alerta-erro');
  alerta.classList.add('hidden');
  alerta.textContent = '';
}

function abrirModalNovo() {
  Estado.colaboradorEmEdicao = null;
  document.getElementById('form-modal-title').textContent = 'Cadastrar Novo Colaborador';
  document.getElementById('colaborador-id').value = '';
  document.getElementById('colaborador-form').reset();
  document.getElementById('campo-situacao').value = 'ativo';
  document.getElementById('container-dependentes').innerHTML = '';
  document.getElementById('dependentes-vazio').classList.remove('hidden');
  const secAlt = document.getElementById('secao-controle-alteracoes');
  if (secAlt) secAlt.classList.add('hidden');
  const inputJust = document.getElementById('campo-justificativa-alteracao');
  if (inputJust) inputJust.value = '';
  limparErrosFormulario();
  document.getElementById('modal-form').classList.remove('hidden');
}

async function abrirModalEditar(id) {
  try {
    const colab = await DadosService.obter(id);
    Estado.colaboradorEmEdicao = colab;
    document.getElementById('form-modal-title').textContent = `Editar Colaborador: ${colab.nome_completo}`;
    document.getElementById('colaborador-id').value = colab.id;
    const secAlt = document.getElementById('secao-controle-alteracoes');
    if (secAlt) secAlt.classList.remove('hidden');
    const inputJust = document.getElementById('campo-justificativa-alteracao');
    if (inputJust) inputJust.value = '';

    // Preenchimento dos campos
    document.getElementById('campo-nome').value = colab.nome_completo || '';
    document.getElementById('campo-cpf').value = colab.cpf || '';
    document.getElementById('campo-rg').value = colab.rg || '';
    if (document.getElementById('campo-pis')) document.getElementById('campo-pis').value = colab.pis_pasep || '';
    if (document.getElementById('campo-sexo')) document.getElementById('campo-sexo').value = colab.sexo || '';
    if (document.getElementById('campo-estado-civil')) document.getElementById('campo-estado-civil').value = colab.estado_civil || '';
    document.getElementById('campo-data-nasc').value = colab.data_nascimento || '';
    document.getElementById('campo-email').value = colab.email || '';
    document.getElementById('campo-telefone').value = colab.telefone || '';
    document.getElementById('campo-logradouro').value = colab.logradouro || '';
    document.getElementById('campo-numero').value = colab.numero || '';
    document.getElementById('campo-bairro').value = colab.bairro || '';
    document.getElementById('campo-cidade').value = colab.cidade || '';
    document.getElementById('campo-uf').value = colab.uf || '';
    document.getElementById('campo-cep').value = colab.cep || '';
    document.getElementById('campo-matricula').value = colab.matricula || '';
    document.getElementById('campo-data-adm').value = colab.data_admissao || '';
    document.getElementById('campo-situacao').value = colab.situacao || 'ativo';
    document.getElementById('campo-cargo').value = colab.cargo || '';
    document.getElementById('campo-setor').value = colab.setor || '';
    if (document.getElementById('campo-centro-custo')) document.getElementById('campo-centro-custo').value = colab.centro_custo || '';
    if (document.getElementById('campo-tipo-contrato')) document.getElementById('campo-tipo-contrato').value = colab.tipo_contrato || 'CLT';
    if (document.getElementById('campo-jornada-trabalho')) document.getElementById('campo-jornada-trabalho').value = colab.jornada_trabalho || '44h semanais';
    if (document.getElementById('campo-carga-horaria')) document.getElementById('campo-carga-horaria').value = colab.carga_horaria_mensal || 220;
    document.getElementById('campo-salario').value = formatarMoeda(colab.salario_base);

    // Dependentes
    const container = document.getElementById('container-dependentes');
    container.innerHTML = '';
    const deps = colab.dependentes || [];
    if (deps.length > 0) {
      document.getElementById('dependentes-vazio').classList.add('hidden');
      deps.forEach(d => adicionarLinhaDependente(d));
    } else {
      document.getElementById('dependentes-vazio').classList.remove('hidden');
    }

    limparErrosFormulario();
    document.getElementById('modal-form').classList.remove('hidden');
  } catch (e) {
    exibirToast(e.message || 'Erro ao carregar dados para edição.', 'error');
  }
}

function fecharModalForm() {
  document.getElementById('modal-form').classList.add('hidden');
  Estado.colaboradorEmEdicao = null;
}

// Submissão do Formulário
async function salvarColaborador(e) {
  e.preventDefault();
  limparErrosFormulario();

  const id = document.getElementById('colaborador-id').value;
  const isEdicao = Boolean(id);

  const dados = {
    nome_completo: document.getElementById('campo-nome').value.trim(),
    cpf: document.getElementById('campo-cpf').value.trim(),
    rg: document.getElementById('campo-rg').value.trim(),
    pis_pasep: (document.getElementById('campo-pis')?.value || '').trim(),
    sexo: document.getElementById('campo-sexo')?.value || '',
    estado_civil: document.getElementById('campo-estado-civil')?.value || '',
    data_nascimento: document.getElementById('campo-data-nasc').value,
    email: document.getElementById('campo-email').value.trim(),
    telefone: document.getElementById('campo-telefone').value.trim(),
    logradouro: document.getElementById('campo-logradouro').value.trim(),
    numero: document.getElementById('campo-numero').value.trim(),
    bairro: document.getElementById('campo-bairro').value.trim(),
    cidade: document.getElementById('campo-cidade').value.trim(),
    uf: document.getElementById('campo-uf').value.trim().toUpperCase(),
    cep: document.getElementById('campo-cep').value.trim(),
    matricula: document.getElementById('campo-matricula').value.trim(),
    data_admissao: document.getElementById('campo-data-adm').value,
    situacao: document.getElementById('campo-situacao').value,
    cargo: document.getElementById('campo-cargo').value.trim(),
    setor: document.getElementById('campo-setor').value,
    departamento: document.getElementById('campo-setor').value,
    centro_custo: (document.getElementById('campo-centro-custo')?.value || '').trim(),
    tipo_contrato: document.getElementById('campo-tipo-contrato')?.value || 'CLT',
    jornada_trabalho: (document.getElementById('campo-jornada-trabalho')?.value || '44h semanais').trim(),
    carga_horaria_mensal: Number(document.getElementById('campo-carga-horaria')?.value || 220),
    salario_base: document.getElementById('campo-salario').value,
    justificativa: (document.getElementById('campo-justificativa-alteracao')?.value || '').trim(),
    dependentes: coletarDependentesDoFormulario()
  };

  // Pré-validação rápida no cliente
  const erros = {};
  if (!dados.nome_completo) erros.nome_completo = 'Nome completo é obrigatório.';
  if (!dados.cpf) erros.cpf = 'CPF é obrigatório.';
  else if (!validarCpf(dados.cpf)) erros.cpf = 'CPF inválido. Verifique os dígitos.';
  if (!dados.data_nascimento) erros.data_nascimento = 'Data de nascimento é obrigatória.';
  if (!dados.email) erros.email = 'E-mail é obrigatório.';
  else if (!validarEmail(dados.email)) erros.email = 'Formato de e-mail inválido.';
  if (!dados.matricula) erros.matricula = 'Matrícula é obrigatória.';
  if (!dados.data_admissao) erros.data_admissao = 'Data de admissão é obrigatória.';
  if (!dados.cargo) erros.cargo = 'Cargo é obrigatório.';
  if (!dados.setor) erros.setor = 'Setor é obrigatório.';
  if (!dados.salario_base) erros.salario_base = 'Salário-base é obrigatório.';

  if (Object.keys(erros).length > 0) {
    aplicarErrosNosCampos(erros);
    return;
  }

  try {
    if (isEdicao) {
      await DadosService.atualizar(id, dados);
      exibirToast('Colaborador atualizado com sucesso e alterações auditadas!', 'success');
    } else {
      await DadosService.cadastrar(dados);
      exibirToast('Novo colaborador cadastrado com sucesso!', 'success');
    }
    fecharModalForm();
    await carregarColaboradores();
  } catch (err) {
    if (err.erros) {
      aplicarErrosNosCampos(err.erros);
    } else {
      const alerta = document.getElementById('form-alerta-erro');
      alerta.textContent = err.message || 'Erro ao processar solicitação.';
      alerta.classList.remove('hidden');
    }
  }
}

function aplicarErrosNosCampos(erros) {
  let primeiroInvalido = null;
  for (const [campo, msg] of Object.entries(erros)) {
    const span = document.getElementById(`erro-${campo}`);
    if (span) span.textContent = Array.isArray(msg) ? msg.join(', ') : msg;

    const input = document.getElementById(`campo-${campo.replace('_', '-')}`) ||
      document.querySelector(`[name="${campo}"]`);
    if (input) {
      input.classList.add('is-invalid');
      if (!primeiroInvalido) primeiroInvalido = input;
    }
  }
  if (primeiroInvalido) primeiroInvalido.focus();
}

// ============================================================================
// Modal: Visualização Completa de Detalhes e Histórico
// ============================================================================
async function abrirModalDetalhes(id) {
  try {
    const colab = await DadosService.obter(id);
    document.getElementById('detalhes-nome').textContent = colab.nome_completo;
    document.getElementById('detalhes-matricula-sub').textContent = `Matrícula: ${colab.matricula} • Situação: ${colab.situacao.toUpperCase()}`;

    // Ficha Cadastral
    Estado.colaboradorEmDetalhesId = colab.id;
    document.getElementById('view-nome').textContent = colab.nome_completo;
    document.getElementById('view-cpf').textContent = colab.cpf;
    document.getElementById('view-rg').textContent = colab.rg || 'Não informado';
    if (document.getElementById('view-pis')) document.getElementById('view-pis').textContent = colab.pis_pasep || 'Não informado';
    if (document.getElementById('view-sexo-civil')) document.getElementById('view-sexo-civil').textContent = [colab.sexo, colab.estado_civil].filter(Boolean).join(' / ') || 'Não informado';
    document.getElementById('view-nasc').textContent = formatarDataBR(colab.data_nascimento);

    document.getElementById('view-email').textContent = colab.email;
    document.getElementById('view-telefone').textContent = colab.telefone || 'Não informado';
    const end = [colab.logradouro, colab.numero, colab.bairro, colab.cidade, colab.uf, colab.cep].filter(Boolean).join(', ');
    document.getElementById('view-endereco').textContent = end || 'Não informado';

    document.getElementById('view-matricula').textContent = colab.matricula;
    document.getElementById('view-admissao').textContent = formatarDataBR(colab.data_admissao);
    document.getElementById('view-cargo').textContent = colab.cargo;
    document.getElementById('view-setor').textContent = colab.setor;
    if (document.getElementById('view-centro-custo')) document.getElementById('view-centro-custo').textContent = colab.centro_custo || 'Não informado';
    if (document.getElementById('view-contrato-jornada')) document.getElementById('view-contrato-jornada').textContent = `${colab.tipo_contrato || 'CLT'} • ${colab.jornada_trabalho || '44h semanais'} (${colab.carga_horaria_mensal || 220}h)`;
    document.getElementById('view-salario').textContent = formatarMoeda(colab.salario_base);
    document.getElementById('view-situacao').innerHTML = colab.situacao === 'ativo'
      ? '<span class="badge badge-ativo">Ativo</span>'
      : `<span class="badge badge-inativo">${(colab.situacao || 'inativo').toUpperCase()}</span>`;

    const escHtml = (v) => String(v ?? '').replace(/[&<>"']/g, s => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[s]));

    // Carregar sub-recursos RF-005 a RF-010 em paralelo com fallback seguro
    Estado.dependentesModal = colab.dependentes || [];
    Estado.documentosModal = colab.documentos || [];
    Estado.histFuncModal = colab.historico_funcional || [];
    Estado.bancariosModal = colab.dados_bancarios || [];

    limparFormDependenteModal();
    limparFormBancarioModal();
    cancelarNovaVersaoDocumento();
    if (document.getElementById('det-bank-titular')) document.getElementById('det-bank-titular').value = colab.nome_completo || '';
    if (document.getElementById('det-bank-cpf')) document.getElementById('det-bank-cpf').value = colab.cpf || '';

    renderizarDependentesColaborador(colab.id, Estado.dependentesModal);
    renderizarDocumentosColaborador(colab.id, Estado.documentosModal);
    renderizarHistoricoFuncionalColaborador(Estado.histFuncModal);
    renderizarDadosBancariosColaborador(colab.id, Estado.bancariosModal);
    renderizarAuditoriaColaborador(colab.historico || []);

    await Promise.allSettled([
      carregarCategoriasDocumentosSelect(),
      carregarDependentesDetalhes(colab.id),
      carregarHistoricoFuncionalDetalhes(colab.id),
      carregarDocumentosDetalhes(colab.id),
      carregarDadosBancariosDetalhes(colab.id),
      carregarAuditoriaDetalhes(colab.id),
    ]);

    // Botão de editar a partir do modal de detalhes
    document.getElementById('btn-editar-a-partir-detalhes').onclick = () => {
      fecharModalDetalhes();
      abrirModalEditar(colab.id);
    };

    document.getElementById('modal-detalhes').classList.remove('hidden');
  } catch (e) {
    exibirToast(e.message || 'Erro ao carregar detalhes.', 'error');
  }
}

function _escHtml(v) {
  return String(v ?? '').replace(/[&<>"']/g, s => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[s]));
}

async function carregarCategoriasDocumentosSelect() {
  try {
    const res = await requisitarApi(`${getApiBase()}/documentos/categorias`);
    const cats = res.dados || [];
    const selUpload = document.getElementById('doc-categoria-input');
    const selFiltro = document.getElementById('det-doc-filtro-cat');
    const selCtrl = document.getElementById('doc-ctrl-filtro-categoria');
    if (selUpload && cats.length) {
      selUpload.innerHTML = cats.map(c => `<option value="${_escHtml(c.codigo)}">${_escHtml(c.nome)}</option>`).join('');
    }
    if (selFiltro && cats.length) {
      const atual = selFiltro.value || 'todas';
      selFiltro.innerHTML = '<option value="todas">Todas as categorias</option>' +
        cats.map(c => `<option value="${_escHtml(c.codigo)}">${_escHtml(c.nome)}</option>`).join('');
      selFiltro.value = atual;
    }
    if (selCtrl && cats.length) {
      const atual = selCtrl.value || 'todas';
      selCtrl.innerHTML = '<option value="todas">Todas as categorias</option>' +
        cats.map(c => `<option value="${_escHtml(c.codigo)}">${_escHtml(c.nome)}</option>`).join('');
      selCtrl.value = atual;
    }
  } catch (_) { }
}

// ---------- RF-005: Dependentes ----------
async function carregarDependentesDetalhes(colabId) {
  const incluirInativos = document.getElementById('det-dep-incluir-inativos')?.checked ? '1' : '0';
  const res = await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/dependentes?incluir_inativos=${incluirInativos}`);
  Estado.dependentesModal = res.dados || [];
  renderizarDependentesColaborador(colabId, Estado.dependentesModal);
}

function renderizarDependentesColaborador(colabId, listaDep) {
  const elQtd = document.getElementById('detalhes-qtd-dep');
  if (elQtd) elQtd.textContent = (listaDep || []).filter(d => (d.situacao || 'ativo') === 'ativo').length;
  const container = document.getElementById('detalhes-lista-dependentes');
  if (!container) return;
  if (!listaDep || !listaDep.length) {
    container.innerHTML = '<p class="text-muted" style="padding:1rem;">Nenhum dependente cadastrado para este colaborador.</p>';
    return;
  }
  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr><th>Nome</th><th>CPF</th><th>Nasc.</th><th>Parentesco</th><th>Vínculos Legais</th><th>Situação</th><th class="text-right">Ações</th></tr>
      </thead>
      <tbody>
        ${listaDep.map(d => {
    const ativo = (d.situacao || 'ativo') === 'ativo';
    const vinculos = [
      Number(d.eh_dependente_irrf ?? 1) ? 'IRRF' : '',
      Number(d.eh_elegivel_salario_familia || 0) ? 'Sal.Fam' : '',
      Number(d.eh_plano_saude || 0) ? 'Plano Saúde' : '',
    ].filter(Boolean).join(' • ') || 'Nenhum';
    return `
            <tr>
              <td><strong>${_escHtml(d.nome)}</strong></td>
              <td>${_escHtml(d.cpf || 'Não informado')}</td>
              <td>${d.data_nascimento ? formatarDataBR(d.data_nascimento) : '--'}</td>
              <td><span class="badge badge-dep">${_escHtml(d.parentesco)}</span></td>
              <td>${_escHtml(vinculos)}</td>
              <td><span class="badge ${ativo ? 'badge-ativo' : 'badge-inativo'}">${ativo ? 'Ativo' : 'Inativo'}</span></td>
              <td class="text-right">
                ${ativo ? `<button type="button" class="btn btn-outline btn-sm" onclick="editarDependenteModal(${d.id})">Editar</button>
                <button type="button" class="btn btn-outline btn-sm text-danger" onclick="inativarDependenteModal(${colabId}, ${d.id})">Inativar</button>` : '<span class="text-muted">Encerrado</span>'}
              </td>
            </tr>
          `;
  }).join('')}
      </tbody>
    </table>
  `;
}

function limparFormDependenteModal() {
  const ids = ['det-dep-id', 'det-dep-nome', 'det-dep-cpf', 'det-dep-nasc'];
  ids.forEach(i => { const el = document.getElementById(i); if (el) el.value = ''; });
  if (document.getElementById('det-dep-parentesco')) document.getElementById('det-dep-parentesco').value = 'Filho(a)';
  if (document.getElementById('det-dep-irrf')) document.getElementById('det-dep-irrf').checked = true;
  if (document.getElementById('det-dep-sf')) document.getElementById('det-dep-sf').checked = false;
  if (document.getElementById('det-dep-saude')) document.getElementById('det-dep-saude').checked = false;
  if (document.getElementById('det-dep-titulo-form')) document.getElementById('det-dep-titulo-form').textContent = 'Gerenciar Dependente (RF-005)';
}

function editarDependenteModal(depId) {
  const dep = (Estado.dependentesModal || []).find(d => Number(d.id) === Number(depId));
  if (!dep) return;
  document.getElementById('det-dep-id').value = dep.id;
  document.getElementById('det-dep-nome').value = dep.nome || '';
  document.getElementById('det-dep-parentesco').value = dep.parentesco || 'Filho(a)';
  document.getElementById('det-dep-cpf').value = dep.cpf || '';
  document.getElementById('det-dep-nasc').value = (dep.data_nascimento || '').slice(0, 10);
  document.getElementById('det-dep-irrf').checked = Boolean(Number(dep.eh_dependente_irrf ?? 1));
  document.getElementById('det-dep-sf').checked = Boolean(Number(dep.eh_elegivel_salario_familia || 0));
  document.getElementById('det-dep-saude').checked = Boolean(Number(dep.eh_plano_saude || 0));
  if (document.getElementById('det-dep-titulo-form')) document.getElementById('det-dep-titulo-form').textContent = `Editando Dependente #${dep.id}`;
}

async function salvarDependenteModal() {
  const colabId = Estado.colaboradorEmDetalhesId;
  if (!colabId) return;
  const depId = document.getElementById('det-dep-id')?.value;
  const payload = {
    nome: document.getElementById('det-dep-nome')?.value?.trim(),
    parentesco: document.getElementById('det-dep-parentesco')?.value,
    cpf: document.getElementById('det-dep-cpf')?.value?.trim(),
    data_nascimento: document.getElementById('det-dep-nasc')?.value,
    eh_dependente_irrf: Boolean(document.getElementById('det-dep-irrf')?.checked),
    eh_elegivel_salario_familia: Boolean(document.getElementById('det-dep-sf')?.checked),
    eh_plano_saude: Boolean(document.getElementById('det-dep-saude')?.checked),
  };
  try {
    const url = depId
      ? `${getApiBase()}/colaboradores/${colabId}/dependentes/${depId}`
      : `${getApiBase()}/colaboradores/${colabId}/dependentes`;
    await requisitarApi(url, { method: depId ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    exibirToast(depId ? 'Dependente atualizado com sucesso!' : 'Dependente cadastrado com sucesso!', 'success');
    limparFormDependenteModal();
    await Promise.all([carregarDependentesDetalhes(colabId), carregarAuditoriaDetalhes(colabId)]);
  } catch (e) {
    exibirToast(e.message || 'Erro ao salvar dependente.', 'error');
  }
}

async function inativarDependenteModal(colabId, depId) {
  try {
    await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/dependentes/${depId}`, {
      method: 'DELETE',
      body: JSON.stringify({ motivo: 'Inativado via ficha do colaborador' })
    });
    exibirToast('Dependente inativado com preservação de histórico.', 'success');
    await Promise.all([carregarDependentesDetalhes(colabId), carregarAuditoriaDetalhes(colabId)]);
  } catch (e) {
    exibirToast(e.message || 'Erro ao inativar dependente.', 'error');
  }
}

// ---------- RF-006: Histórico Funcional ----------
async function carregarHistoricoFuncionalDetalhes(colabId) {
  const tipo = document.getElementById('det-hf-filtro-tipo')?.value || '';
  const dtIni = document.getElementById('det-hf-filtro-inicio')?.value || '';
  const dtFim = document.getElementById('det-hf-filtro-fim')?.value || '';
  const params = new URLSearchParams();
  if (tipo) params.set('tipo', tipo);
  if (dtIni) params.set('data_inicio', dtIni);
  if (dtFim) params.set('data_fim', dtFim);
  const qs = params.toString() ? `?${params.toString()}` : '';
  const res = await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/historico-funcional${qs}`);
  Estado.histFuncModal = res.dados || [];
  renderizarHistoricoFuncionalColaborador(Estado.histFuncModal);
}

function renderizarHistoricoFuncionalColaborador(movs) {
  const elQtd = document.getElementById('detalhes-qtd-hist-func');
  if (elQtd) elQtd.textContent = (movs || []).length;
  const container = document.getElementById('detalhes-lista-hist-funcional');
  if (!container) return;
  if (!movs || !movs.length) {
    container.innerHTML = '<p class="text-muted" style="padding:1rem;">Nenhuma movimentação funcional registrada.</p>';
    return;
  }
  container.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Vigência</th><th>Tipo</th><th>Cargo (Ant. → Novo)</th><th>Setor (Ant. → Novo)</th><th>Salário (Ant. → Novo)</th><th>Motivo</th></tr></thead>
      <tbody>
        ${movs.map(m => `
          <tr>
            <td>${m.data_vigencia ? formatarDataBR(m.data_vigencia) : '--'}</td>
            <td><span class="badge badge-dep">${_escHtml(m.tipo_movimentacao)}</span></td>
            <td>${_escHtml(m.cargo_anterior || '--')} &rarr; <strong>${_escHtml(m.cargo_novo || '--')}</strong></td>
            <td>${_escHtml(m.setor_anterior || '--')} &rarr; <strong>${_escHtml(m.setor_novo || '--')}</strong></td>
            <td>${m.salario_anterior != null ? formatarMoeda(m.salario_anterior) : '--'} &rarr; <strong>${m.salario_novo != null ? formatarMoeda(m.salario_novo) : '--'}</strong></td>
            <td>${_escHtml(m.motivo || '--')}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

async function registrarMovimentacaoFuncionalModal() {
  const colabId = Estado.colaboradorEmDetalhesId;
  if (!colabId) return;
  const salRaw = document.getElementById('det-hf-salario')?.value;
  const payload = {
    tipo_movimentacao: document.getElementById('det-hf-tipo')?.value,
    data_vigencia: document.getElementById('det-hf-data-vigencia')?.value,
    cargo_novo: document.getElementById('det-hf-cargo')?.value?.trim() || undefined,
    setor_novo: document.getElementById('det-hf-setor')?.value?.trim() || undefined,
    centro_custo_novo: document.getElementById('det-hf-cc')?.value?.trim() || undefined,
    salario_novo: salRaw ? Number(salRaw) : undefined,
    jornada_nova: document.getElementById('det-hf-jornada')?.value?.trim() || undefined,
    motivo: document.getElementById('det-hf-motivo')?.value?.trim(),
  };
  try {
    await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/historico-funcional`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    exibirToast('Movimentação funcional registrada e aplicada ao cadastro!', 'success');
    ['det-hf-cargo', 'det-hf-setor', 'det-hf-cc', 'det-hf-salario', 'det-hf-jornada', 'det-hf-motivo'].forEach(i => {
      const el = document.getElementById(i);
      if (el) el.value = '';
    });
    await abrirModalDetalhes(colabId);
    if (typeof carregarColaboradores === 'function') carregarColaboradores();
  } catch (e) {
    exibirToast(e.message || 'Erro ao registrar movimentação funcional.', 'error');
  }
}

// ---------- RF-007: Documentos ----------
async function carregarDocumentosDetalhes(colabId) {
  const cat = document.getElementById('det-doc-filtro-cat')?.value || 'todas';
  const termo = document.getElementById('det-doc-filtro-busca')?.value?.trim() || '';
  const incluirInativos = document.getElementById('det-doc-incluir-inativos')?.checked ? '1' : '0';
  const params = new URLSearchParams({ incluir_inativos: incluirInativos });
  if (cat && cat !== 'todas') params.set('categoria', cat);
  if (termo) params.set('q', termo);
  const res = await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/documentos?${params.toString()}`);
  Estado.documentosModal = res.dados || [];
  renderizarDocumentosColaborador(colabId, Estado.documentosModal);
}

function prepararNovaVersaoDocumento(docId, nomeArquivo, categoria) {
  if (document.getElementById('doc-raiz-id-input')) document.getElementById('doc-raiz-id-input').value = docId;
  if (categoria && document.getElementById('doc-categoria-input')) document.getElementById('doc-categoria-input').value = categoria;
  const banner = document.getElementById('doc-versao-banner');
  const texto = document.getElementById('doc-versao-banner-texto');
  if (texto) texto.textContent = `Enviando nova versão de: ${nomeArquivo} (Doc #${docId})`;
  if (banner) banner.classList.remove('hidden');
}

function cancelarNovaVersaoDocumento() {
  if (document.getElementById('doc-raiz-id-input')) document.getElementById('doc-raiz-id-input').value = '';
  const banner = document.getElementById('doc-versao-banner');
  if (banner) banner.classList.add('hidden');
}

async function visualizarOuBaixarDocumento(colabId, docId, modo, nomeArquivo) {
  try {
    const headers = getAuthHeaders();
    delete headers['Content-Type'];
    const resp = await fetch(`${getApiBase()}/colaboradores/${colabId}/documentos/${docId}/download?modo=${modo}`, {
      headers,
      credentials: 'include'
    });
    if (!resp.ok) throw new Error('Falha ao acessar documento autorizado.');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    if (modo === 'visualizar') {
      window.open(url, '_blank', 'noopener');
    } else {
      const a = document.createElement('a');
      a.href = url;
      a.download = nomeArquivo || `documento_${docId}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (e) {
    exibirToast(e.message || 'Erro no download do documento.', 'error');
  }
}

async function verVersoesDocumento(colabId, docId) {
  try {
    const res = await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/documentos/${docId}/versoes`);
    const versoes = res.dados || [];
    const resumo = versoes.map(v => `v${v.versao} — ${v.nome_arquivo} (${v.situacao}) [${v.criado_em}]`).join(' | ');
    exibirToast(`Versões do documento #${docId}: ${resumo}`, 'info');
  } catch (e) {
    exibirToast(e.message || 'Erro ao consultar versões.', 'error');
  }
}

function renderizarDocumentosColaborador(colabId, docs) {
  const elQtd = document.getElementById('detalhes-qtd-docs');
  if (elQtd) elQtd.textContent = (docs || []).filter(d => (d.situacao || 'ativo') === 'ativo').length;
  const container = document.getElementById('detalhes-lista-documentos');
  if (!container) return;
  if (!docs.length) {
    container.innerHTML = '<p class="text-muted" style="padding:0.75rem;">Nenhum documento encontrado para este filtro.</p>';
    return;
  }
  container.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Categoria / Tipo</th><th>Arquivo</th><th>Versão / Status</th><th>Validade</th><th>Tamanho</th><th class="text-right">Ações</th></tr></thead>
      <tbody>
        ${docs.map(d => {
    const st = d.situacao || 'ativo';
    const badgeCls = st === 'ativo' ? 'badge-ativo' : 'badge-inativo';
    return `
            <tr>
              <td><span class="badge badge-dep">${_escHtml(d.categoria || d.tipo_documento)}</span><br><small class="text-muted">${_escHtml(d.tipo_documento)}</small></td>
              <td><strong>${_escHtml(d.nome_arquivo)}</strong>${d.observacao ? `<br><small class="text-muted">${_escHtml(d.observacao)}</small>` : ''}</td>
              <td>v${d.versao || 1} <span class="badge ${badgeCls}">${_escHtml(st)}</span></td>
              <td>${d.data_validade ? formatarDataBR(d.data_validade) : 'Sem validade'}</td>
              <td>${d.tamanho_bytes ? Math.max(1, Math.round(d.tamanho_bytes / 1024)) + ' KB' : '--'}</td>
              <td class="text-right" style="white-space:nowrap;">
                <button type="button" class="btn btn-outline btn-sm" onclick="visualizarOuBaixarDocumento(${colabId}, ${d.id}, 'visualizar', '${_escHtml(d.nome_arquivo)}')">Ver</button>
                <button type="button" class="btn btn-outline btn-sm" onclick="visualizarOuBaixarDocumento(${colabId}, ${d.id}, 'download', '${_escHtml(d.nome_arquivo)}')">Baixar</button>
                <button type="button" class="btn btn-outline btn-sm" onclick="prepararNovaVersaoDocumento(${d.id}, '${_escHtml(d.nome_arquivo)}', '${_escHtml(d.categoria || '')}')">Nova Versão</button>
                <button type="button" class="btn btn-outline btn-sm" onclick="verVersoesDocumento(${colabId}, ${d.id})">Versões</button>
                ${st === 'ativo' ? `<button type="button" class="btn btn-outline btn-sm text-danger" onclick="removerDocumentoColaborador(${colabId}, ${d.id})">Inativar</button>` : ''}
              </td>
            </tr>
          `;
  }).join('')}
      </tbody>
    </table>
  `;
}

async function enviarDocumentoColaborador() {
  const colabId = Estado.colaboradorEmDetalhesId;
  const categoria = document.getElementById('doc-categoria-input')?.value || 'OUTROS';
  const tipo = document.getElementById('doc-tipo-input')?.value || 'Outros';
  const dataEmissao = document.getElementById('doc-emissao-input')?.value || null;
  const dataValidade = document.getElementById('doc-validade-input')?.value || null;
  const observacao = document.getElementById('doc-obs-input')?.value?.trim() || '';
  const raizId = document.getElementById('doc-raiz-id-input')?.value || null;
  const inputArq = document.getElementById('doc-arquivo-input');
  const file = inputArq?.files?.[0];
  if (!colabId || !file) {
    exibirToast('Selecione um arquivo para anexar.', 'error');
    return;
  }
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      const endpoint = raizId
        ? `${getApiBase()}/colaboradores/${colabId}/documentos/${raizId}/versoes`
        : `${getApiBase()}/colaboradores/${colabId}/documentos`;
      await requisitarApi(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          categoria,
          tipo_documento: tipo,
          nome_arquivo: file.name,
          mime_type: file.type,
          tamanho_bytes: file.size,
          data_emissao: dataEmissao,
          data_validade: dataValidade,
          observacao,
          documento_raiz_id: raizId ? Number(raizId) : null,
          conteudo_base64: String(reader.result || '')
        })
      });
      exibirToast(raizId ? 'Nova versão anexada com sucesso!' : 'Documento anexado com segurança!', 'success');
      if (inputArq) inputArq.value = '';
      if (document.getElementById('doc-obs-input')) document.getElementById('doc-obs-input').value = '';
      cancelarNovaVersaoDocumento();
      await Promise.all([carregarDocumentosDetalhes(colabId), carregarAuditoriaDetalhes(colabId)]);
    } catch (e) {
      exibirToast(e.message || 'Erro ao enviar documento.', 'error');
    }
  };
  reader.readAsDataURL(file);
}

async function removerDocumentoColaborador(colabId, docId) {
  try {
    await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/documentos/${docId}`, {
      method: 'DELETE',
      body: JSON.stringify({ motivo: 'Inativado via painel de documentos' })
    });
    exibirToast('Documento inativado com rastreabilidade preservada.', 'success');
    await Promise.all([carregarDocumentosDetalhes(colabId), carregarAuditoriaDetalhes(colabId)]);
  } catch (e) {
    exibirToast(e.message || 'Erro ao inativar documento.', 'error');
  }
}

// ---------- RF-009: Dados Bancários ----------
async function carregarDadosBancariosDetalhes(colabId) {
  const res = await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/dados-bancarios`);
  Estado.bancariosModal = res.dados || [];
  renderizarDadosBancariosColaborador(colabId, Estado.bancariosModal);
}

function renderizarDadosBancariosColaborador(colabId, contas) {
  const elQtd = document.getElementById('detalhes-qtd-banc');
  if (elQtd) elQtd.textContent = (contas || []).filter(c => Number(c.ativo ?? 1) === 1).length;
  const container = document.getElementById('detalhes-lista-bancarios');
  if (!container) return;
  if (!contas || !contas.length) {
    container.innerHTML = '<p class="text-muted" style="padding:1rem;">Nenhuma conta bancária cadastrada.</p>';
    return;
  }
  container.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Banco</th><th>Agência / Conta</th><th>Tipo</th><th>Titular / CPF</th><th>PIX</th><th>Principal</th><th class="text-right">Ações</th></tr></thead>
      <tbody>
        ${contas.map(c => `
          <tr>
            <td><strong>${_escHtml(c.banco_codigo)}</strong> — ${_escHtml(c.banco_nome)}</td>
            <td>Ag ${_escHtml(c.agencia)} / CC ${_escHtml(c.conta)}${c.digito_conta ? '-' + _escHtml(c.digito_conta) : ''}</td>
            <td><span class="badge badge-dep">${_escHtml(c.tipo_conta)}</span></td>
            <td>${_escHtml(c.titular_nome)}<br><small class="text-muted">${_escHtml(c.cpf_titular)}</small></td>
            <td>${c.chave_pix ? `${_escHtml(c.tipo_chave_pix)}: ${_escHtml(c.chave_pix)}` : '--'}</td>
            <td>${Number(c.principal) === 1 ? '<span class="badge badge-ativo">Principal</span>' : 'Secundária'}</td>
            <td class="text-right">
              <button type="button" class="btn btn-outline btn-sm" onclick="editarDadosBancariosModal(${c.id})">Editar</button>
              <button type="button" class="btn btn-outline btn-sm text-danger" onclick="inativarDadosBancariosModal(${colabId}, ${c.id})">Inativar</button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function limparFormBancarioModal() {
  ['det-bank-id', 'det-bank-codigo', 'det-bank-nome', 'det-bank-agencia', 'det-bank-conta', 'det-bank-digito', 'det-bank-pix-chave'].forEach(i => {
    const el = document.getElementById(i);
    if (el) el.value = '';
  });
  if (document.getElementById('det-bank-tipo')) document.getElementById('det-bank-tipo').value = 'corrente';
  if (document.getElementById('det-bank-pix-tipo')) document.getElementById('det-bank-pix-tipo').value = '';
  if (document.getElementById('det-bank-principal')) document.getElementById('det-bank-principal').checked = true;
}

function editarDadosBancariosModal(contaId) {
  const c = (Estado.bancariosModal || []).find(x => Number(x.id) === Number(contaId));
  if (!c) return;
  document.getElementById('det-bank-id').value = c.id;
  document.getElementById('det-bank-codigo').value = c.banco_codigo || '';
  document.getElementById('det-bank-nome').value = c.banco_nome || '';
  document.getElementById('det-bank-agencia').value = c.agencia || '';
  document.getElementById('det-bank-conta').value = c.conta || '';
  document.getElementById('det-bank-digito').value = c.digito_conta || '';
  document.getElementById('det-bank-tipo').value = c.tipo_conta || 'corrente';
  document.getElementById('det-bank-titular').value = c.titular_nome || '';
  document.getElementById('det-bank-cpf').value = c.cpf_titular || '';
  document.getElementById('det-bank-pix-tipo').value = c.tipo_chave_pix || '';
  document.getElementById('det-bank-pix-chave').value = c.chave_pix || '';
  document.getElementById('det-bank-principal').checked = Boolean(Number(c.principal));
}

async function salvarDadosBancariosModal() {
  const colabId = Estado.colaboradorEmDetalhesId;
  if (!colabId) return;
  const contaId = document.getElementById('det-bank-id')?.value;
  const payload = {
    banco_codigo: document.getElementById('det-bank-codigo')?.value?.trim(),
    banco_nome: document.getElementById('det-bank-nome')?.value?.trim(),
    agencia: document.getElementById('det-bank-agencia')?.value?.trim(),
    conta: document.getElementById('det-bank-conta')?.value?.trim(),
    digito_conta: document.getElementById('det-bank-digito')?.value?.trim(),
    tipo_conta: document.getElementById('det-bank-tipo')?.value,
    titular_nome: document.getElementById('det-bank-titular')?.value?.trim(),
    cpf_titular: document.getElementById('det-bank-cpf')?.value?.trim(),
    tipo_chave_pix: document.getElementById('det-bank-pix-tipo')?.value,
    chave_pix: document.getElementById('det-bank-pix-chave')?.value?.trim(),
    principal: Boolean(document.getElementById('det-bank-principal')?.checked),
  };
  try {
    const url = contaId
      ? `${getApiBase()}/colaboradores/${colabId}/dados-bancarios/${contaId}`
      : `${getApiBase()}/colaboradores/${colabId}/dados-bancarios`;
    await requisitarApi(url, { method: contaId ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    exibirToast(contaId ? 'Conta bancária atualizada!' : 'Conta bancária cadastrada!', 'success');
    limparFormBancarioModal();
    await Promise.all([carregarDadosBancariosDetalhes(colabId), carregarAuditoriaDetalhes(colabId)]);
  } catch (e) {
    exibirToast(e.message || 'Erro ao salvar dados bancários.', 'error');
  }
}

async function inativarDadosBancariosModal(colabId, contaId) {
  try {
    await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/dados-bancarios/${contaId}`, { method: 'DELETE' });
    exibirToast('Conta bancária inativada.', 'success');
    await Promise.all([carregarDadosBancariosDetalhes(colabId), carregarAuditoriaDetalhes(colabId)]);
  } catch (e) {
    exibirToast(e.message || 'Erro ao inativar conta bancária.', 'error');
  }
}

// ---------- RF-010: Auditoria Cadastral Unificada ----------
async function carregarAuditoriaDetalhes(colabId) {
  const ent = document.getElementById('det-aud-filtro-entidade')?.value || 'todas';
  const usr = document.getElementById('det-aud-filtro-usuario')?.value?.trim() || '';
  const campo = document.getElementById('det-aud-filtro-campo')?.value?.trim() || '';
  const params = new URLSearchParams();
  if (ent && ent !== 'todas') params.set('entidade', ent);
  if (usr) params.set('usuario', usr);
  if (campo) params.set('campo', campo);
  const qs = params.toString() ? `?${params.toString()}` : '';
  const res = await requisitarApi(`${getApiBase()}/colaboradores/${colabId}/auditoria${qs}`);
  renderizarAuditoriaColaborador(res.dados || []);
}

function renderizarAuditoriaColaborador(historico) {
  const timeline = document.getElementById('detalhes-timeline');
  const elQtdHist = document.getElementById('detalhes-qtd-hist');
  if (elQtdHist) elQtdHist.textContent = historico.length;
  if (!timeline) return;
  if (historico.length === 0) {
    timeline.innerHTML = '<p class="text-muted">Nenhuma alteração registrada até o momento.</p>';
    return;
  }
  timeline.innerHTML = historico.map(h => {
    const detalheAlteracao = (h.valor_anterior !== null && h.valor_anterior !== undefined && h.valor_anterior !== '')
      ? `De: <s>${_escHtml(h.valor_anterior)}</s> &rarr; Para: <strong>${_escHtml(h.valor_novo)}</strong>`
      : `<strong>${_escHtml(h.valor_novo)}</strong>`;
    const tagEnt = h.entidade ? `<span class="badge badge-dep" style="margin-right:0.4rem;">${_escHtml(h.entidade)}</span>` : '';
    const extraOrigem = h.origem ? ` • Origem: ${_escHtml(h.origem)}` : '';
    return `
      <div class="timeline-item">
        <div class="timeline-header">
          <span class="timeline-action">${tagEnt}${_escHtml(h.campo_alterado)}</span>
          <span class="timeline-date">${_escHtml(h.data_hora)}</span>
        </div>
        <div class="timeline-body">
          ${detalheAlteracao}
          <div class="timeline-user">Registrado por: ${_escHtml(h.usuario_responsavel || 'Sistema')}${extraOrigem}</div>
        </div>
      </div>
    `;
  }).join('');
}

function fecharModalDetalhes() {
  document.getElementById('modal-detalhes').classList.add('hidden');
}

// ============================================================================
// Modal: Inativação e Reativação Lógica
// ============================================================================
function abrirModalInativar(id) {
  const colab = Estado.colaboradores.find(c => c.id === id);
  if (!colab) return;

  Estado.colaboradorParaInativar = colab;
  document.getElementById('inativar-info-colaborador').innerHTML = `
    <strong>${colab.nome_completo}</strong> (Matrícula: ${colab.matricula})<br>
    Cargo: ${colab.cargo} • Setor: ${colab.setor}
  `;
  document.getElementById('inativar-motivo').value = '';
  document.getElementById('modal-inativar').classList.remove('hidden');
}

function fecharModalInativar() {
  document.getElementById('modal-inativar').classList.add('hidden');
  Estado.colaboradorParaInativar = null;
}

async function confirmarInativacao() {
  if (!Estado.colaboradorParaInativar) return;
  const id = Estado.colaboradorParaInativar.id;
  const motivo = document.getElementById('inativar-motivo').value.trim();

  try {
    await DadosService.inativar(id, motivo);
    exibirToast('Colaborador inativado com sucesso. Histórico preservado!', 'warning');
    fecharModalInativar();
    await carregarColaboradores();
  } catch (e) {
    exibirToast(e.message || 'Erro ao inativar colaborador.', 'error');
  }
}

async function reativarColaborador(id) {
  if (!confirm('Deseja reativar o vínculo deste colaborador?')) return;
  try {
    await DadosService.reativar(id);
    exibirToast('Colaborador reativado com sucesso!', 'success');
    await carregarColaboradores();
  } catch (e) {
    exibirToast(e.message || 'Erro ao reativar colaborador.', 'error');
  }
}

// ============================================================================
// Configuração de Eventos
// ============================================================================
function configurarEventos() {
  // Novo Colaborador
  document.getElementById('btn-novo-colaborador').addEventListener('click', abrirModalNovo);
  document.getElementById('btn-fechar-form-modal').addEventListener('click', fecharModalForm);
  document.getElementById('btn-cancelar-form').addEventListener('click', fecharModalForm);
  document.getElementById('colaborador-form').addEventListener('submit', salvarColaborador);
  document.getElementById('btn-gerar-matricula')?.addEventListener('click', async () => {
    try {
      const res = await requisitarApi(`${getApiBase()}/colaboradores/proxima-matricula`);
      if (res && res.matricula) {
        document.getElementById('campo-matricula').value = res.matricula;
      }
    } catch (e) {
      exibirToast('Não foi possível gerar matrícula automática.', 'error');
    }
  });

  // Dependentes
  document.getElementById('btn-adicionar-dependente').addEventListener('click', () => adicionarLinhaDependente());

  // Modal Detalhes
  document.getElementById('btn-fechar-detalhes').addEventListener('click', fecharModalDetalhes);
  document.getElementById('btn-fechar-detalhes-footer').addEventListener('click', fecharModalDetalhes);

  // Abas do Modal Detalhes
  document.querySelectorAll('.modal-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      e.currentTarget.classList.add('active');
      const targetId = e.currentTarget.getAttribute('data-tab');
      document.getElementById(targetId).classList.add('active');
    });
  });

  // Eventos RF-005 a RF-010 no Modal de Detalhes
  document.getElementById('btn-salvar-dep-detalhes')?.addEventListener('click', salvarDependenteModal);
  document.getElementById('btn-limpar-dep-detalhes')?.addEventListener('click', limparFormDependenteModal);
  document.getElementById('det-dep-incluir-inativos')?.addEventListener('change', () => {
    if (Estado.colaboradorEmDetalhesId) carregarDependentesDetalhes(Estado.colaboradorEmDetalhesId);
  });
  document.getElementById('det-dep-cpf')?.addEventListener('input', (e) => { e.target.value = mascaraCpf(e.target.value); });
  document.getElementById('det-bank-cpf')?.addEventListener('input', (e) => { e.target.value = mascaraCpf(e.target.value); });

  document.getElementById('btn-registrar-hf')?.addEventListener('click', registrarMovimentacaoFuncionalModal);
  document.getElementById('btn-filtrar-hf')?.addEventListener('click', () => {
    if (Estado.colaboradorEmDetalhesId) carregarHistoricoFuncionalDetalhes(Estado.colaboradorEmDetalhesId);
  });

  document.getElementById('btn-cancelar-nova-versao')?.addEventListener('click', cancelarNovaVersaoDocumento);
  document.getElementById('det-doc-filtro-cat')?.addEventListener('change', () => {
    if (Estado.colaboradorEmDetalhesId) carregarDocumentosDetalhes(Estado.colaboradorEmDetalhesId);
  });
  document.getElementById('det-doc-incluir-inativos')?.addEventListener('change', () => {
    if (Estado.colaboradorEmDetalhesId) carregarDocumentosDetalhes(Estado.colaboradorEmDetalhesId);
  });
  document.getElementById('det-doc-filtro-busca')?.addEventListener('input', () => {
    if (Estado.colaboradorEmDetalhesId) carregarDocumentosDetalhes(Estado.colaboradorEmDetalhesId);
  });

  document.getElementById('btn-salvar-bank-detalhes')?.addEventListener('click', salvarDadosBancariosModal);
  document.getElementById('btn-limpar-bank-detalhes')?.addEventListener('click', limparFormBancarioModal);
  document.getElementById('btn-filtrar-auditoria')?.addEventListener('click', () => {
    if (Estado.colaboradorEmDetalhesId) carregarAuditoriaDetalhes(Estado.colaboradorEmDetalhesId);
  });

  // Modal Inativar
  document.getElementById('btn-fechar-inativar').addEventListener('click', fecharModalInativar);
  document.getElementById('btn-cancelar-inativar').addEventListener('click', fecharModalInativar);
  document.getElementById('btn-confirmar-inativacao').addEventListener('click', confirmarInativacao);

  // Filtros e Pesquisa com Debounce
  let timerBusca = null;
  const inputPesquisa = document.getElementById('filtro-pesquisa');
  const btnLimpar = document.getElementById('btn-limpar-pesquisa');

  inputPesquisa.addEventListener('input', (e) => {
    const val = e.target.value;
    btnLimpar.classList.toggle('hidden', !val);
    clearTimeout(timerBusca);
    timerBusca = setTimeout(() => {
      Estado.filtros.termo = val;
      carregarColaboradores();
    }, 280);
  });

  btnLimpar.addEventListener('click', () => {
    inputPesquisa.value = '';
    btnLimpar.classList.add('hidden');
    Estado.filtros.termo = '';
    carregarColaboradores();
  });

  document.getElementById('filtro-situacao').addEventListener('change', (e) => {
    Estado.filtros.situacao = e.target.value;
    carregarColaboradores();
  });

  document.getElementById('filtro-setor').addEventListener('change', (e) => {
    Estado.filtros.setor = e.target.value;
    carregarColaboradores();
  });

  const bindDebouncedFilter = (inputId, filterKey, applyCpfMask = false) => {
    let timer = null;
    const el = document.getElementById(inputId);
    if (!el) return null;
    el.addEventListener('input', (e) => {
      if (applyCpfMask) {
        e.target.value = mascaraCpf(e.target.value);
      }
      const val = e.target.value;
      clearTimeout(timer);
      timer = setTimeout(() => {
        Estado.filtros[filterKey] = val;
        carregarColaboradores();
      }, 260);
    });
    return el;
  };

  const inputNome = bindDebouncedFilter('filtro-nome', 'nome');
  const inputMatricula = bindDebouncedFilter('filtro-matricula', 'matricula');
  const inputCpf = bindDebouncedFilter('filtro-cpf', 'cpf', true);
  const inputCargo = bindDebouncedFilter('filtro-cargo', 'cargo');

  const limparTodosFiltrosColaboradores = () => {
    inputPesquisa.value = '';
    btnLimpar.classList.add('hidden');
    document.getElementById('filtro-situacao').value = 'todos';
    document.getElementById('filtro-setor').value = '';
    if (inputNome) inputNome.value = '';
    if (inputMatricula) inputMatricula.value = '';
    if (inputCpf) inputCpf.value = '';
    if (inputCargo) inputCargo.value = '';
    Estado.filtros = { termo: '', nome: '', matricula: '', cpf: '', situacao: 'todos', setor: '', cargo: '' };
    carregarColaboradores();
  };

  document.getElementById('btn-recarregar').addEventListener('click', carregarColaboradores);
  document.getElementById('btn-limpar-filtros').addEventListener('click', limparTodosFiltrosColaboradores);
  const btnLimparTopo = document.getElementById('btn-limpar-filtros-topo');
  if (btnLimparTopo) {
    btnLimparTopo.addEventListener('click', limparTodosFiltrosColaboradores);
  }

  // Máscaras de Entrada no Formulário
  document.getElementById('campo-cpf').addEventListener('input', (e) => {
    e.target.value = mascaraCpf(e.target.value);
  });

  document.getElementById('campo-telefone').addEventListener('input', (e) => {
    e.target.value = mascaraTelefone(e.target.value);
  });

  document.getElementById('campo-cep').addEventListener('input', (e) => {
    e.target.value = mascaraCep(e.target.value);
  });

  document.getElementById('campo-salario').addEventListener('blur', (e) => {
    if (e.target.value) e.target.value = formatarMoeda(e.target.value);
  });
}

// ============================================================================
// ============================================================================
// CATÁLOGO OFICIAL DE RUBRICAS E EVENTOS DA FOLHA (CLT / eSocial)
// ============================================================================
const CATALOGO_EVENTOS_FOLHA = [
  { codigo: '0001', evento: 'Salário mensal', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'salario_proporcional', situacao: 'HOMOLOGADO', observacao: 'Salário contratual integral ou proporcional aos dias trabalhados (art. 457 CLT). Unifica com o item base.' },
  { codigo: '0002', evento: 'Salário horista', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'hora_normal', situacao: 'HOMOLOGADO', observacao: 'Horas trabalhadas multiplicadas pelo valor da hora.' },
  { codigo: '0003', evento: 'Saldo de salário (rescisão)', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'salario_proporcional', situacao: 'HOMOLOGADO', observacao: 'Verba rescisória no mês de desligamento.' },
  { codigo: '0010', evento: 'Horas extras 50%', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'hora_extra_50', situacao: 'HOMOLOGADO', observacao: 'Hora normal acrescida de no mínimo 50% (art. 59 § 1º CLT).' },
  { codigo: '0011', evento: 'Horas extras 100%', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'hora_extra_100', situacao: 'HOMOLOGADO', observacao: 'Hora normal acrescida de 100% para domingos e feriados (Lei 605/49).' },
  { codigo: '0012', evento: 'DSR sobre horas extras', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'dsr', situacao: 'HOMOLOGADO', observacao: 'Reflexo no descanso semanal remunerado.' },
  { codigo: '0015', evento: 'Banco de horas pago', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'hora_extra_50', situacao: 'PENDENTE_VALIDACAO', observacao: 'Pagamento de saldo não compensado. Requer previsão em CCT/ACT.' },
  { codigo: '0020', evento: 'Adicional noturno', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'adicional_noturno', situacao: 'HOMOLOGADO', observacao: 'Adicional legal de 20% sobre a hora diurna no perímetro urbano (art. 73 CLT).' },
  { codigo: '0021', evento: 'DSR sobre adicional noturno', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'dsr', situacao: 'HOMOLOGADO', observacao: 'Reflexo no DSR.' },
  { codigo: '0030', evento: 'Adicional de insalubridade', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: '10%, 20% ou 40% sobre o salário mínimo. Requer laudo LTCAT.' },
  { codigo: '0031', evento: 'Adicional de periculosidade', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'periculosidade_sb', situacao: 'PENDENTE_VALIDACAO', observacao: '30% sobre o salário-base sem acréscimos (art. 193 § 1º CLT).' },
  { codigo: '0032', evento: 'Adicional de transferência', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Mínimo de 25% do salário enquanto durar a transferência.' },
  { codigo: '0033', evento: 'Adicional por tempo de serviço (anuênio/quinquênio)', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Conforme previsão em CCT.' },
  { codigo: '0040', evento: 'Gratificação de função / cargo de confiança', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Art. 62, II e art. 224 § 2º CLT.' },
  { codigo: '0041', evento: 'Quebra de caixa', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Súmula 247 TST.' },
  { codigo: '0042', evento: 'Gratificação ajustada', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: '' },
  { codigo: '0050', evento: 'Comissões', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Integra a remuneração para todos os efeitos (art. 457 § 1º CLT).' },
  { codigo: '0051', evento: 'DSR sobre comissões', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'dsr', situacao: 'HOMOLOGADO', observacao: 'Súmula 27 TST.' },
  { codigo: '0060', evento: 'Prêmios / bônus habituais', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: '' },
  { codigo: '0061', evento: 'PLR (tributação exclusiva)', tipo: 'provento', categoria: 'Proventos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Lei 10.101/2000. Isento de encargos; IRRF exclusivo.' },
  { codigo: '0070', evento: 'Gorjetas', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Art. 457 § 3º CLT.' },
  { codigo: '0071', evento: 'Diferenças salariais / retroativos', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: '' },
  { codigo: '0072', evento: 'Diárias de viagem (acima de 50% do salário)', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Integra apenas no valor que exceder 50%.' },
  { codigo: '0073', evento: 'Ajuda de custo (indenizatória)', tipo: 'provento', categoria: 'Proventos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Natureza indenizatória (art. 457 § 2º CLT).' },
  { codigo: '0074', evento: 'Reembolsos / ressarcimentos', tipo: 'provento', categoria: 'Proventos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Reembolso mediante comprovação.' },
  { codigo: '0075', evento: 'Abono / benefício indenizatório', tipo: 'provento', categoria: 'Proventos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Não integra remuneração nem encargos.' },
  { codigo: '0100', evento: 'Férias gozadas', tipo: 'provento', categoria: 'Férias e 13º salário', inss: 1, irrf: 1, fgts: 1, metodo: 'ferias_dias', situacao: 'HOMOLOGADO', observacao: 'Proporcional aos dias de gozo no mês.' },
  { codigo: '0101', evento: '1/3 constitucional de férias', tipo: 'provento', categoria: 'Férias e 13º salário', inss: 1, irrf: 1, fgts: 1, metodo: 'terco_ferias', situacao: 'HOMOLOGADO', observacao: 'Art. 7º, XVII da Constituição Federal.' },
  { codigo: '0102', evento: 'Abono pecuniário (venda de 1/3)', tipo: 'provento', categoria: 'Férias e 13º salário', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Art. 143 da CLT. Sem encargos.' },
  { codigo: '0110', evento: '13º salário – 1ª parcela (adiantamento)', tipo: 'provento', categoria: 'Férias e 13º salário', inss: 0, irrf: 0, fgts: 1, metodo: 'adiantamento_13', situacao: 'HOMOLOGADO', observacao: '50% do salário sem descontos de INSS/IRRF (apenas FGTS devido).' },
  { codigo: '0111', evento: '13º salário – 2ª parcela', tipo: 'provento', categoria: 'Férias e 13º salário', inss: 1, irrf: 1, fgts: 1, metodo: 'segunda_parcela_13', situacao: 'HOMOLOGADO', observacao: 'Competência de dezembro com apuração integral.' },
  { codigo: '0501', evento: 'INSS', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'inss_progressivo', situacao: 'HOMOLOGADO', observacao: 'Tabela progressiva com faixas de 7,5%, 9%, 12% e 14% e teto R$ 8.157,41. Unifica com item de sistema.' },
  { codigo: '0505', evento: 'IRRF', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'irrf_progressivo', situacao: 'HOMOLOGADO', observacao: 'Tabela progressiva da Receita Federal com dedução por dependente de R$ 189,59.' },
  { codigo: '0510', evento: 'Vale-transporte (até 6% do salário base)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'vale_transporte', situacao: 'HOMOLOGADO', observacao: 'Limitado a 6% do salário-base conforme art. 4º da Lei 7.418/1985.' },
  { codigo: '0511', evento: 'Vale-alimentação / refeição (coparticipação)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Conforme política de benefícios da empresa / PAT.' },
  { codigo: '0512', evento: 'Plano de saúde (coparticipação / mensalidade)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Mediante autorização prévia e expressa do empregado (Súmula 342 TST).' },
  { codigo: '0513', evento: 'Plano odontológico', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: '' },
  { codigo: '0514', evento: 'Seguro de vida', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: '' },
  { codigo: '0515', evento: 'Previdência privada', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: '' },
  { codigo: '0520', evento: 'Adiantamento salarial', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'adiantamento_salarial', situacao: 'HOMOLOGADO', observacao: 'Compensação de adiantamento (padrão 40% do salário-base).' },
  { codigo: '0521', evento: 'Adiantamento de 13º (compensação)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Compensado na 2ª parcela.' },
  { codigo: '0530', evento: 'Faltas injustificadas', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'faltas_dias', situacao: 'HOMOLOGADO', observacao: 'Desconto à razão de 1/30 do salário por dia de falta integral injustificada.' },
  { codigo: '0531', evento: 'DSR sobre faltas', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'dsr_faltas', situacao: 'HOMOLOGADO', observacao: 'Perda do repouso semanal na semana da falta (art. 6º Lei 605/49).' },
  { codigo: '0532', evento: 'Atrasos / saídas antecipadas', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'atrasos_horas', situacao: 'HOMOLOGADO', observacao: 'Desconto apurado com base no valor da hora normal.' },
  { codigo: '0535', evento: 'Mensalidade sindical', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Somente com autorização prévia e expressa do empregado.' },
  { codigo: '0540', evento: 'Pensão alimentícia (salário)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Conforme ofício judicial.' },
  { codigo: '0545', evento: 'Empréstimo consignado', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'HOMOLOGADO', observacao: 'Respeitada margem consignável (Lei 10.820/2003).' },
  { codigo: '0550', evento: 'Desconto por danos / avarias', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'manual_valor', situacao: 'PENDENTE_VALIDACAO', observacao: 'Somente se acordado em contrato ou em dolo (art. 462 § 1º CLT).' },
  { codigo: '0551', evento: 'Aviso prévio não cumprido pelo empregado', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0, metodo: 'salario_proporcional', situacao: 'HOMOLOGADO', observacao: 'Desconto rescisório correspondente a um mês de salário.' },
  { codigo: '0901', evento: 'Base de cálculo do INSS', tipo: 'informativo', categoria: 'Eventos informativos (bases e encargos)', inss: 0, irrf: 0, fgts: 0, metodo: 'base', situacao: 'HOMOLOGADO', observacao: 'Soma dos proventos com incidência de INSS menos faltas.' },
  { codigo: '0902', evento: 'Base de cálculo do IRRF', tipo: 'informativo', categoria: 'Eventos informativos (bases e encargos)', inss: 0, irrf: 0, fgts: 0, metodo: 'base', situacao: 'HOMOLOGADO', observacao: 'Base do INSS deduzida do próprio INSS retido e dependentes.' },
  { codigo: '0903', evento: 'Base de cálculo do FGTS', tipo: 'informativo', categoria: 'Eventos informativos (bases e encargos)', inss: 0, irrf: 0, fgts: 0, metodo: 'base', situacao: 'HOMOLOGADO', observacao: 'Soma dos proventos que compõem remuneração do FGTS.' },
  { codigo: '0904', evento: 'FGTS do mês (8%)', tipo: 'informativo', categoria: 'Eventos informativos (bases e encargos)', inss: 0, irrf: 0, fgts: 0, metodo: 'fgts_8', situacao: 'HOMOLOGADO', observacao: 'Depósito patronal de 8% (sem desconto do colaborador).' }
];

function gerarOpcoesEventos(codigoSelecionado, tipoAtual, isCustom) {
  const categoriasOrdem = tipoAtual === 'desconto'
    ? ['Descontos', 'Proventos', 'Férias e 13º salário', 'Eventos informativos (bases e encargos)']
    : (tipoAtual === 'informativo'
      ? ['Eventos informativos (bases e encargos)', 'Proventos', 'Descontos', 'Férias e 13º salário']
      : ['Proventos', 'Descontos', 'Férias e 13º salário', 'Eventos informativos (bases e encargos)']);

  let html = '<option value="" disabled ' + (!codigoSelecionado && !isCustom ? 'selected' : '') + '>-- Selecione um evento da lista --</option>';

  categoriasOrdem.forEach(cat => {
    const eventosCat = CATALOGO_EVENTOS_FOLHA.filter(e => e.categoria === cat);
    if (eventosCat.length > 0) {
      html += '<optgroup label="' + cat + '">';
      eventosCat.forEach(ev => {
        const sel = (!isCustom && ev.codigo === codigoSelecionado) ? 'selected' : '';
        const badgeValidacao = ev.situacao === 'PENDENTE_VALIDACAO' ? ' [⚠️ Pendente CCT]' : '';
        html += '<option value="' + ev.codigo + '" data-tipo="' + ev.tipo + '" ' + sel + '>' + ev.codigo + ' — ' + ev.evento + badgeValidacao + '</option>';
      });
      html += '</optgroup>';
    }
  });

  html += '<optgroup label="Personalizado">';
  html += '<option value="__OUTRO__" ' + (isCustom ? 'selected' : '') + '>✏️ Outro evento personalizado (digitar descrição)...</option>';
  html += '</optgroup>';

  return html;
}


const FolhaManager = {
  folhas: [],
  colaboradoresElegiveis: [],
  parametrosVigentes: null,
  rubricasManuais: [],
  folhaEmEdicao: null,
  folhaParaFecharOuReabrir: null,
  filtros: {
    competencia: '2026-10',
    situacao: 'todos',
    setor: '',
    termo: ''
  },

  inicializar() {
    this.configurarNavegacaoAbas();
    this.configurarFiltros();
    this.configurarEventosModal();
    this.configurarEventosHolerite();
  },

  configurarNavegacaoAbas() {
    const tabColab = document.getElementById('nav-tab-colaboradores');
    const tabFolha = document.getElementById('nav-tab-folha');
    const viewColab = document.getElementById('view-modulo-colaboradores');
    const viewFolha = document.getElementById('view-modulo-folha');

    if (tabColab && tabFolha && viewColab && viewFolha) {
      tabColab.addEventListener('click', () => {
        tabColab.classList.add('active');
        tabFolha.classList.remove('active');
        viewColab.classList.remove('hidden');
        viewFolha.classList.add('hidden');
      });

      tabFolha.addEventListener('click', async () => {
        tabFolha.classList.add('active');
        tabColab.classList.remove('active');
        viewFolha.classList.remove('hidden');
        viewColab.classList.add('hidden');
        await this.carregarParametros();
        await this.carregarFolhas();
      });
    }
  },

  catalogoEventos: [],

  async carregarCatalogoEventos() {
    if (this.catalogoEventos.length > 0) return;
    try {
      const resp = await fetch(`${API_BASE}/folha/eventos-catalogo`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      const json = await resp.json();
      if (resp.ok && json.sucesso && Array.isArray(json.dados) && json.dados.length > 0) {
        this.catalogoEventos = json.dados;
        return;
      }
    } catch (e) {
      console.warn('Erro ao carregar catálogo de eventos do backend:', e);
    }

    if (this.catalogoEventos.length === 0) {
      this.catalogoEventos = [
        { codigo: '0010', evento: 'Horas extras 50%', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0011', evento: 'Horas extras 100%', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0012', evento: 'DSR sobre horas extras', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0020', evento: 'Adicional noturno', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0030', evento: 'Adicional de insalubridade', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0031', evento: 'Adicional de periculosidade', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0040', evento: 'Gratificação de função / cargo de confiança', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0050', evento: 'Comissões', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0060', evento: 'Prêmios / bônus habituais', tipo: 'provento', categoria: 'Proventos', inss: 1, irrf: 1, fgts: 1 },
        { codigo: '0075', evento: 'Abono / benefício indenizatório', tipo: 'provento', categoria: 'Proventos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0510', evento: 'Vale-transporte (até 6% do salário base)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0511', evento: 'Vale-alimentação / refeição (coparticipação)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0512', evento: 'Plano de saúde (coparticipação / mensalidade)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0514', evento: 'Seguro de vida', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0520', evento: 'Adiantamento salarial', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0530', evento: 'Faltas injustificadas', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0532', evento: 'Atrasos / saídas antecipadas', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0540', evento: 'Pensão alimentícia (salário)', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 },
        { codigo: '0545', evento: 'Empréstimo consignado', tipo: 'desconto', categoria: 'Descontos', inss: 0, irrf: 0, fgts: 0 }
      ];
    }
  },

  escaparHtml(v) {
    return String(v ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  },

  async carregarParametros() {
    try {
      const resp = await fetch(`${API_BASE}/folha/parametros`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (resp.ok) {
        const json = await resp.json();
        if (json.sucesso && json.dados) {
          this.parametrosVigentes = json.dados;
        }
      }
    } catch (e) {
      console.warn('Não foi possível obter os parâmetros da folha:', e);
    }
  },

  async carregarColaboradoresElegiveis() {
    try {
      const resp = await fetch(`${API_BASE}/folha/colaboradores`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (resp.ok) {
        const json = await resp.json();
        if (json.sucesso && Array.isArray(json.dados) && json.dados.length > 0) {
          this.colaboradoresElegiveis = json.dados;
        }
      }
    } catch (e) {
      console.error('Erro ao carregar colaboradores elegíveis:', e);
    }

    if (!this.colaboradoresElegiveis || this.colaboradoresElegiveis.length === 0) {
      const ativos = (Estado.colaboradores || []).filter(c => c.situacao === 'ativo');
      if (ativos.length > 0) {
        this.colaboradoresElegiveis = ativos;
      }
    }

    const select = document.getElementById('folha-campo-colaborador');
    if (select) {
      select.innerHTML = '<option value="">Selecione um colaborador ativo...</option>';
      (this.colaboradoresElegiveis || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.matricula} — ${c.nome_completo} (${c.cargo || 'Geral'})`;
        select.appendChild(opt);
      });
    }
  },

  configurarFiltros() {
    const inputCompetencia = document.getElementById('filtro-folha-competencia');
    const selectSituacao = document.getElementById('filtro-folha-situacao');
    const selectSetor = document.getElementById('filtro-folha-setor');
    const inputPesquisa = document.getElementById('filtro-folha-pesquisa');
    const btnLimparPesquisa = document.getElementById('btn-limpar-pesquisa-folha');
    const btnLimparFiltros = document.getElementById('btn-limpar-filtros-folha');
    const btnNovaFolha = document.getElementById('btn-nova-folha');
    const btnParametros = document.getElementById('btn-parametros-folha');

    if (inputCompetencia) {
      inputCompetencia.addEventListener('change', (e) => {
        this.filtros.competencia = e.target.value;
        this.carregarFolhas();
      });
    }

    if (selectSituacao) {
      selectSituacao.addEventListener('change', (e) => {
        this.filtros.situacao = e.target.value;
        this.carregarFolhas();
      });
    }

    const selectTipo = document.getElementById('filtro-folha-tipo');
    if (selectTipo) {
      selectTipo.addEventListener('change', (e) => {
        this.filtros.tipo_folha = e.target.value;
        this.carregarFolhas();
      });
    }

    if (selectSetor) {
      selectSetor.addEventListener('change', (e) => {
        this.filtros.setor = e.target.value;
        this.carregarFolhas();
      });
    }

    let timerFiltro = null;
    if (inputPesquisa) {
      inputPesquisa.addEventListener('input', (e) => {
        const val = e.target.value;
        if (btnLimparPesquisa) btnLimparPesquisa.classList.toggle('hidden', !val);
        clearTimeout(timerFiltro);
        timerFiltro = setTimeout(() => {
          this.filtros.termo = val;
          this.carregarFolhas();
        }, 280);
      });
    }

    if (btnLimparPesquisa) {
      btnLimparPesquisa.addEventListener('click', () => {
        inputPesquisa.value = '';
        btnLimparPesquisa.classList.add('hidden');
        this.filtros.termo = '';
        this.carregarFolhas();
      });
    }

    if (btnLimparFiltros) {
      btnLimparFiltros.addEventListener('click', () => {
        if (inputPesquisa) inputPesquisa.value = '';
        if (btnLimparPesquisa) btnLimparPesquisa.classList.add('hidden');
        if (selectSituacao) selectSituacao.value = 'todos';
        if (selectSetor) selectSetor.value = '';
        this.filtros = {
          competencia: inputCompetencia ? inputCompetencia.value : '2026-10',
          situacao: 'todos',
          setor: '',
          termo: ''
        };
        this.carregarFolhas();
      });
    }

    if (btnNovaFolha) {
      btnNovaFolha.addEventListener('click', () => this.abrirModalNovaFolha());
    }

    if (btnParametros) {
      btnParametros.addEventListener('click', () => this.abrirModalParametros());
    }
  },

  async carregarFolhas() {
    const params = new URLSearchParams();
    if (this.filtros.competencia) params.append('competencia', this.filtros.competencia);
    if (this.filtros.situacao && this.filtros.situacao !== 'todos') params.append('situacao', this.filtros.situacao);
    if (this.filtros.tipo_folha && this.filtros.tipo_folha !== 'todos') params.append('tipo_folha', this.filtros.tipo_folha);
    if (this.filtros.setor) params.append('setor', this.filtros.setor);
    if (this.filtros.termo) params.append('q', this.filtros.termo);

    try {
      const resp = await fetch(`${API_BASE}/folha?${params.toString()}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });

      if (resp.status === 401) {
        AuthManager.exibirTelaLogin('Sessão expirada. Faça login novamente.');
        return;
      }

      if (resp.ok) {
        const json = await resp.json();
        this.folhas = json.dados || [];
        this.renderizarTabelaFolhas();
        this.atualizarCardsMetricas();
      }
    } catch (e) {
      console.error('Erro ao consultar folhas de pagamento:', e);
      exibirToast('Não foi possível carregar as folhas de pagamento.', 'error');
    }
  },

  atualizarCardsMetricas() {
    const elTotal = document.getElementById('stat-folha-total');
    const elProventos = document.getElementById('stat-folha-proventos');
    const elDescontos = document.getElementById('stat-folha-descontos');
    const elLiquido = document.getElementById('stat-folha-liquido');

    let totalBruto = 0;
    let totalDesc = 0;
    let totalLiq = 0;

    this.folhas.forEach(f => {
      totalBruto += Number(f.total_proventos || 0);
      totalDesc += Number(f.total_descontos || 0);
      totalLiq += Number(f.salario_liquido || 0);
    });

    if (elTotal) elTotal.textContent = String(this.folhas.length);
    if (elProventos) elProventos.textContent = formatarMoeda(totalBruto);
    if (elDescontos) elDescontos.textContent = formatarMoeda(totalDesc);
    if (elLiquido) elLiquido.textContent = formatarMoeda(totalLiq);

    // Atualiza Banner Executivo da Competência da Folha
    const compInput = document.getElementById('filtro-folha-competencia')?.value;
    const elBannerComp = document.getElementById('folha-banner-competencia');
    const elBannerQtd = document.getElementById('folha-banner-qtd-func');
    const elBannerEncargos = document.getElementById('folha-banner-encargos');
    const elBannerStatus = document.getElementById('folha-banner-status');

    if (elBannerComp) elBannerComp.textContent = compInput || 'Todas as Competências';
    if (elBannerQtd) elBannerQtd.textContent = String(this.folhas.length);
    if (elBannerEncargos) elBannerEncargos.textContent = formatarMoeda(totalBruto * 0.08);
    if (elBannerStatus) {
      if (this.folhas.length === 0) {
        elBannerStatus.textContent = 'Sem Lançamentos';
      } else if (this.folhas.every(f => f.situacao === 'fechada')) {
        elBannerStatus.textContent = 'Competência Fechada';
      } else if (this.folhas.some(f => f.situacao === 'rascunho')) {
        elBannerStatus.textContent = 'Com Rascunhos Pendentes';
      } else {
        elBannerStatus.textContent = 'Calculada / Em Conferência';
      }
    }
  },

  renderizarTabelaFolhas() {
    const corpo = document.getElementById('corpo-tabela-folha');
    const estadoVazio = document.getElementById('estado-vazio-folha');
    if (!corpo) return;

    corpo.innerHTML = '';

    if (this.folhas.length === 0) {
      if (estadoVazio) estadoVazio.classList.remove('hidden');
      aplicarPaginacaoTabela('corpo-tabela-folha', 'paginacao-folha', 12);
      return;
    }

    if (estadoVazio) estadoVazio.classList.add('hidden');

    this.folhas.forEach(f => {
      const tr = document.createElement('tr');

      let badgeClass = 'badge-calculada';
      if (f.situacao === 'fechada') badgeClass = 'badge-fechada';
      if (f.situacao === 'rascunho') badgeClass = 'badge-rascunho';
      if (f.situacao === 'cancelada') badgeClass = 'badge-cancelada';

      const isFechada = f.situacao === 'fechada';

      tr.innerHTML = `
        <td>
          <div class="user-cell">
            <span class="user-name">${f.colaborador_nome || '--'}</span>
            <span class="user-matricula">Matrícula: ${f.colaborador_matricula || '--'} &bull; CPF: ${formatarCpf(f.colaborador_cpf || '')}</span>
            <span class="text-xs text-muted">${f.colaborador_cargo || ''} (${f.colaborador_setor || ''})</span>
          </div>
        </td>
        <td>
          <strong>${f.competencia}</strong>
        </td>
        <td>
          <div style="font-size: 0.8rem;">
            <span>${formatarDataBR(f.periodo_inicio)} a ${formatarDataBR(f.periodo_fim)}</span>
            ${f.data_pagamento ? `<div class="text-muted text-xs">Pagto: ${formatarDataBR(f.data_pagamento)}</div>` : ''}
          </div>
        </td>
        <td class="text-money">${formatarMoeda(f.salario_base_contratual)}</td>
        <td class="text-money text-green">+ ${formatarMoeda(f.total_proventos)}</td>
        <td class="text-money text-gray">- ${formatarMoeda(f.total_descontos)}</td>
        <td class="text-money" style="font-weight: 700; color: #1e3a8a;">${formatarMoeda(f.salario_liquido)}</td>
        <td>
          <span class="badge-status ${badgeClass}">${f.situacao}</span>
        </td>
        <td class="text-right">
          <div class="action-buttons">
            <button class="btn-action btn-action-view" data-folha-id="${f.id}" title="Visualizar Demonstrativo / Imprimir Holerite">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
              </svg>
              Holerite
            </button>
            ${!isFechada ? `
              <button class="btn-action btn-action-edit" data-folha-id="${f.id}" title="Editar eventos e recalcular">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 20h9"></path>
                  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
                </svg>
              </button>
              <button class="btn-action btn-action-close" data-folha-id="${f.id}" title="Fechar e homologar folha" style="color: #166534;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
              </button>
              <button class="btn-action btn-action-delete" data-folha-id="${f.id}" title="Cancelar folha" style="color: #b91c1c;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            ` : `
              <button class="btn-action btn-action-reopen" data-folha-id="${f.id}" title="Reabrir folha fechada" style="color: #d97706;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                  <path d="M7 11V7a5 5 0 0 1 9.9-1"></path>
                </svg>
              </button>
            `}
          </div>
        </td>
      `;

      corpo.appendChild(tr);
    });

    // Delegar eventos de botões da tabela
    corpo.querySelectorAll('.btn-action-view').forEach(btn => {
      btn.addEventListener('click', () => this.abrirModalHolerite(btn.dataset.folhaId));
    });

    corpo.querySelectorAll('.btn-action-edit').forEach(btn => {
      btn.addEventListener('click', () => this.abrirModalEdicaoFolha(btn.dataset.folhaId));
    });

    corpo.querySelectorAll('.btn-action-close').forEach(btn => {
      btn.addEventListener('click', () => this.solicitarFechamento(btn.dataset.folhaId));
    });

    corpo.querySelectorAll('.btn-action-delete').forEach(btn => {
      btn.addEventListener('click', () => this.excluirFolha(btn.dataset.folhaId));
    });

    corpo.querySelectorAll('.btn-action-reopen').forEach(btn => {
      btn.addEventListener('click', () => this.solicitarReabertura(btn.dataset.folhaId));
    });

    aplicarPaginacaoTabela('corpo-tabela-folha', 'paginacao-folha', 12);
  },

  async abrirModalNovaFolha() {
    this.folhaEmEdicao = null;
    this.rubricasManuais = [];
    document.getElementById('modal-folha-title').textContent = 'Lançar & Calcular Nova Folha de Pagamento';
    document.getElementById('folha-id-edicao').value = '';
    document.getElementById('form-folha-pagamento').reset();
    document.getElementById('folha-form-alerta').classList.add('hidden');
    document.getElementById('folha-info-colaborador-box').style.display = 'none';

    // Competência padrão conforme filtro
    const comp = this.filtros.competencia || '2026-10';
    document.getElementById('folha-campo-competencia').value = comp;
    document.getElementById('folha-campo-inicio').value = `${comp}-01`;
    document.getElementById('folha-campo-fim').value = `${comp}-30`;
    document.getElementById('folha-campo-dias').value = '30';
    document.getElementById('folha-campo-divisor').value = '220';

    await this.carregarColaboradoresElegiveis();
    await this.carregarCatalogoEventos();
    this.renderizarRubricasManuais();
    this.atualizarPreviaCalculo();

    document.getElementById('modal-folha-form').classList.remove('hidden');
  },

  async abrirModalEdicaoFolha(folhaId) {
    try {
      const resp = await fetch(`${API_BASE}/folha/${folhaId}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (!resp.ok) {
        exibirToast('Não foi possível obter dados da folha para edição.', 'error');
        return;
      }
      const json = await resp.json();
      const folha = json.dados;
      this.folhaEmEdicao = folha;

      await this.carregarColaboradoresElegiveis();
      await this.carregarCatalogoEventos();

      document.getElementById('modal-folha-title').textContent = `Editar & Recalcular Folha #${folha.id}`;
      document.getElementById('folha-id-edicao').value = folha.id;
      document.getElementById('folha-campo-colaborador').value = folha.colaborador_id;
      document.getElementById('folha-campo-competencia').value = folha.competencia;
      document.getElementById('folha-campo-inicio').value = folha.periodo_inicio;
      document.getElementById('folha-campo-fim').value = folha.periodo_fim;
      document.getElementById('folha-campo-pagamento').value = folha.data_pagamento || '';
      document.getElementById('folha-campo-dias').value = folha.dias_trabalhados;
      document.getElementById('folha-campo-divisor').value = folha.horas_mensais_divisor;
      document.getElementById('folha-campo-observacoes').value = folha.observacoes || '';

      // Preencher eventos conhecidos
      let he50 = '';
      let he100 = '';
      let noturno = '';
      let faltas = '';
      let atrasos = '';
      this.rubricasManuais = [];

      const refNumerica = (it) => parseFloat(String(it.unidade_referencia || '').replace(',', '.')) || Number(it.referencia) || '';
      (folha.itens || []).forEach(it => {
        if (it.origem !== 'manual' && it.codigo_evento === '101') {
          if (String(it.descricao).includes('100%')) he100 = refNumerica(it);
          else he50 = refNumerica(it);
        }
        else if (it.origem !== 'manual' && it.codigo_evento === '102') noturno = refNumerica(it);
        else if (it.origem !== 'manual' && it.codigo_evento === '201') faltas = refNumerica(it);
        else if (it.origem !== 'manual' && it.codigo_evento === '202') atrasos = refNumerica(it);
        else if (it.origem === 'manual') {
          this.rubricasManuais.push({
            tipo: it.tipo,
            codigo: this.catalogoEventos.some(c => c.codigo === it.codigo_evento) ? it.codigo_evento : '__outro',
            descricao: it.descricao,
            referencia: parseFloat(String(it.unidade_referencia || '').replace(',', '.')) || 1,
            valor_total: it.valor_total
          });
        }
      });

      document.getElementById('folha-campo-he50').value = he50;
      document.getElementById('folha-campo-he100').value = he100;
      document.getElementById('folha-campo-noturno').value = noturno;
      document.getElementById('folha-campo-faltas').value = faltas;
      document.getElementById('folha-campo-atrasos').value = atrasos;

      this.atualizarCardColaboradorSelecionado(folha.colaborador_id);
      this.renderizarRubricasManuais();
      this.atualizarPreviaCalculo();

      document.getElementById('modal-folha-form').classList.remove('hidden');
    } catch (e) {
      console.error('Erro ao abrir folha para edição:', e);
      exibirToast('Erro ao carregar dados da folha.', 'error');
    }
  },

  configurarEventosModal() {
    const btnFechar = document.getElementById('btn-fechar-folha-form');
    const btnCancelar = document.getElementById('btn-cancelar-folha-form');
    const selectColab = document.getElementById('folha-campo-colaborador');
    const btnAddRubrica = document.getElementById('btn-add-rubrica');
    const btnSimular = document.getElementById('btn-simular-calculo');
    const formFolha = document.getElementById('form-folha-pagamento');

    if (btnFechar) btnFechar.addEventListener('click', () => {
      document.getElementById('modal-folha-form').classList.add('hidden');
    });

    if (btnCancelar) btnCancelar.addEventListener('click', () => {
      document.getElementById('modal-folha-form').classList.add('hidden');
    });

    if (selectColab) {
      selectColab.addEventListener('change', (e) => {
        if (!this.folhaEmEdicao) {
          this.rubricasManuais = [];
          ['folha-campo-he50', 'folha-campo-he100', 'folha-campo-noturno', 'folha-campo-faltas', 'folha-campo-atrasos', 'folha-campo-observacoes'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
          });
          this.renderizarRubricasManuais();
        }
        this.atualizarCardColaboradorSelecionado(e.target.value);
        this.atualizarPreviaCalculo();
      });
    }

    if (btnAddRubrica) {
      btnAddRubrica.addEventListener('click', () => {
        this.rubricasManuais.push({
          tipo: 'provento',
          codigo: '0075',
          descricao: 'Abono / benefício indenizatório',
          referencia: 1,
          valor_total: 100,
          isCustom: false
        });
        this.renderizarRubricasManuais();
        this.atualizarPreviaCalculo();
      });
    }

    // Recalcula prévia ao alterar qualquer número
    ['folha-campo-dias', 'folha-campo-divisor', 'folha-campo-he50', 'folha-campo-he100', 'folha-campo-noturno', 'folha-campo-faltas', 'folha-campo-atrasos'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('input', () => this.atualizarPreviaCalculo());
    });

    if (btnSimular) {
      btnSimular.addEventListener('click', () => {
        const folhaId = document.getElementById('folha-id-edicao').value;
        if (folhaId) {
          this.recalcularFolhaNoBackend(folhaId);
        } else {
          this.simularFolhaNoBackend(true);
        }
      });
    }

    if (formFolha) {
      formFolha.addEventListener('submit', (e) => {
        e.preventDefault();
        this.salvarFolha();
      });
    }
  },

  atualizarCardColaboradorSelecionado(colabId) {
    const box = document.getElementById('folha-info-colaborador-box');
    if (!colabId) {
      if (box) box.style.display = 'none';
      return;
    }

    const c = this.colaboradoresElegiveis.find(item => String(item.id) === String(colabId));
    if (c && box) {
      document.getElementById('folha-info-matricula').textContent = c.matricula;
      document.getElementById('folha-info-cargo').textContent = c.cargo;
      document.getElementById('folha-info-setor').textContent = c.setor;
      document.getElementById('folha-info-salario').textContent = formatarMoeda(c.salario_base);
      document.getElementById('folha-info-dependentes').textContent = String(c.total_dependentes || 0);
      box.style.display = 'block';
    }
  },

  calcularValorAutomaticoEvento(cod, ref, tipo) {
    const colabId = document.getElementById('folha-campo-colaborador').value;
    const dias = Number(document.getElementById('folha-campo-dias').value || 30);
    const divisor = Number(document.getElementById('folha-campo-divisor').value || 220);
    const c = this.colaboradoresElegiveis.find(item => String(item.id) === String(colabId));
    const sb = c ? Number(c.salario_base || 0) : 0;
    const vh = divisor > 0 ? (sb / divisor) : 0;
    const r = Number(ref || 1);

    if (cod === '0001') {
      return Number(((sb / 30) * Math.min(30, dias)).toFixed(2));
    } else if (cod === '0002') {
      return Number((vh * r).toFixed(2));
    } else if (cod === '0010') {
      return Number((vh * 1.5 * r).toFixed(2));
    } else if (cod === '0011') {
      return Number((vh * 2.0 * r).toFixed(2));
    } else if (cod === '0020') {
      return Number((vh * 0.20 * r).toFixed(2));
    } else if (cod === '0031') {
      return Number((sb * 0.30).toFixed(2)); // Periculosidade 30%
    } else if (cod === '0100') {
      return Number(((sb / 30) * r).toFixed(2));
    } else if (cod === '0101') {
      return Number((((sb / 30) * r) / 3).toFixed(2));
    } else if (cod === '0110') {
      return Number((sb * 0.5).toFixed(2)); // 1ª parcela 13º
    } else if (cod === '0501') {
      // INSS progressivo sobre salário
      if (sb <= 1518.00) return Number((sb * 0.075).toFixed(2));
      if (sb <= 2793.88) return Number((113.85 + (sb - 1518.00) * 0.09).toFixed(2));
      if (sb <= 4190.83) return Number((113.85 + 114.83 + (sb - 2793.88) * 0.12).toFixed(2));
      return Number(Math.min(908.85, 113.85 + 114.83 + 167.63 + (sb - 4190.83) * 0.14).toFixed(2));
    } else if (cod === '0510') {
      return Number((sb * 0.06).toFixed(2)); // Vale-transporte limite 6%
    } else if (cod === '0520') {
      return Number((sb * 0.40).toFixed(2)); // Adiantamento salarial padrão 40%
    } else if (cod === '0530') {
      return Number(((sb / 30) * r).toFixed(2)); // Faltas
    } else if (cod === '0532') {
      return Number((vh * r).toFixed(2)); // Atrasos
    }
    return 0;
  },

  montarOpcoesEventos(rub) {
    const eventos = this.catalogoEventos.filter(c => c.tipo === rub.tipo);
    const porCategoria = {};
    eventos.forEach(ev => {
      (porCategoria[ev.categoria] = porCategoria[ev.categoria] || []).push(ev);
    });

    let html = `<option value="">Selecione o evento...</option>`;
    Object.keys(porCategoria).forEach(cat => {
      html += `<optgroup label="${this.escaparHtml(cat)}">`;
      porCategoria[cat].forEach(ev => {
        const sel = rub.codigo === ev.codigo ? 'selected' : '';
        const dica = ev.observacao ? ` title="${this.escaparHtml(ev.observacao)}"` : '';
        html += `<option value="${this.escaparHtml(ev.codigo)}" ${sel}${dica}>${this.escaparHtml(ev.codigo)} — ${this.escaparHtml(ev.evento)}</option>`;
      });
      html += `</optgroup>`;
    });
    html += `<option value="__outro" ${rub.codigo === '__outro' ? 'selected' : ''}>Outro (descrição livre)</option>`;
    return html;
  },

  renderizarRubricasManuais() {
    const wrapper = document.getElementById('wrapper-rubricas-manuais');
    const corpo = document.getElementById('corpo-rubricas-manuais');
    if (!wrapper || !corpo) return;

    if (this.rubricasManuais.length === 0) {
      wrapper.style.display = 'none';
      corpo.innerHTML = '';
      return;
    }

    wrapper.style.display = 'block';
    corpo.innerHTML = '';

    this.rubricasManuais.forEach((rub, idx) => {
      const tr = document.createElement('tr');
      const evCat = CATALOGO_EVENTOS_FOLHA.find(item => item.codigo === rub.codigo);
      const isPendente = evCat && evCat.situacao === 'PENDENTE_VALIDACAO';

      tr.innerHTML = `
        <td style="font-size: 0.78rem; font-weight: 700; color: #1e3a8a; text-align: center; vertical-align: middle;">
          ${rub.codigo ? `<span style="background:#e0e7ff;padding:2px 6px;border-radius:4px;">${rub.codigo}</span>` : '<span style="color:#94a3b8;">—</span>'}
        </td>
        <td>
          <div style="display: flex; flex-direction: column; gap: 0.35rem;">
            <select class="form-control select-control rub-evento" data-idx="${idx}" style="font-size: 0.82rem; padding: 0.35rem 0.5rem;">
              ${gerarOpcoesEventos(rub.codigo, rub.tipo, rub.isCustom)}
            </select>
            ${isPendente ? `
              <span style="font-size: 0.72rem; color: #b45309; background: #fef3c7; border: 1px solid #fde68a; padding: 2px 6px; border-radius: 4px; display: inline-block;">
                ⚠️ Regra pendente de homologação formal CCT/DP
              </span>
            ` : ''}
            ${rub.isCustom ? `
              <input type="text" class="form-control rub-desc" data-idx="${idx}" value="${rub.descricao || ''}" placeholder="Digite o nome do evento avulso..." style="font-size: 0.8rem; padding: 0.3rem 0.5rem;">
            ` : ''}
          </div>
        </td>
        <td>
          <input type="number" class="form-control rub-ref" data-idx="${idx}" value="${rub.referencia ?? 1}" min="0" step="0.5" style="font-size: 0.82rem; padding: 0.35rem; text-align: center;">
        </td>
        <td>
          ${rub.tipo !== 'desconto' ? `<input type="number" class="form-control rub-val" data-idx="${idx}" value="${rub.valor_total ?? 0}" min="0" step="0.01" style="font-size: 0.82rem; padding: 0.35rem; font-weight: 600; color: #15803d;">` : `<span style="color:#94a3b8;font-size:0.82rem;display:block;text-align:center;">—</span>`}
        </td>
        <td>
          ${rub.tipo === 'desconto' ? `<input type="number" class="form-control rub-val" data-idx="${idx}" value="${rub.valor_total ?? 0}" min="0" step="0.01" style="font-size: 0.82rem; padding: 0.35rem; font-weight: 600; color: #dc2626;">` : `<span style="color:#94a3b8;font-size:0.82rem;display:block;text-align:center;">—</span>`}
        </td>
        <td style="text-align: center;">
          <button type="button" class="btn-remover-rubrica rub-remover" data-idx="${idx}" title="Excluir este evento">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="pointer-events: none;">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
            <span style="pointer-events: none;">Excluir</span>
          </button>
        </td>
      `;
      corpo.appendChild(tr);
    });

    // O tipo do evento é derivado automaticamente do catálogo ao selecionar o evento
    // (o select de "Tipo" foi removido da UI — o tipo é inferido do catálogo)

    corpo.querySelectorAll('.rub-evento').forEach(el => {
      el.addEventListener('change', (e) => {
        const idx = Number(e.target.dataset.idx);
        const val = e.target.value;
        if (val === '__OUTRO__') {
          this.rubricasManuais[idx].isCustom = true;
          this.rubricasManuais[idx].codigo = '';
          this.renderizarRubricasManuais();
        } else {
          this.rubricasManuais[idx].isCustom = false;
          const ev = CATALOGO_EVENTOS_FOLHA.find(item => item.codigo === val);
          if (ev) {
            this.rubricasManuais[idx].codigo = ev.codigo;
            this.rubricasManuais[idx].descricao = ev.evento;
            if (ev.tipo === 'provento' || ev.tipo === 'desconto') {
              this.rubricasManuais[idx].tipo = ev.tipo;
            }
            // Auto-preenche o valor do evento conforme sua regra e parametrização
            const vAuto = this.calcularValorAutomaticoEvento(ev.codigo, this.rubricasManuais[idx].referencia, ev.tipo);
            if (vAuto > 0 || (this.rubricasManuais[idx].valor_total === 0 || this.rubricasManuais[idx].valor_total === 100)) {
              this.rubricasManuais[idx].valor_total = vAuto;
            }
          }
          this.renderizarRubricasManuais();
        }
        this.atualizarPreviaCalculo();
      });
    });

    corpo.querySelectorAll('.rub-desc').forEach(el => {
      el.addEventListener('input', (e) => {
        const idx = Number(e.target.dataset.idx);
        this.rubricasManuais[idx].descricao = e.target.value;
      });
    });

    corpo.querySelectorAll('.rub-ref').forEach(el => {
      el.addEventListener('input', (e) => {
        const idx = Number(e.target.dataset.idx);
        const novaRef = Number(e.target.value || 0);
        this.rubricasManuais[idx].referencia = novaRef;
        const cod = this.rubricasManuais[idx].codigo;
        if (cod) {
          const vAuto = this.calcularValorAutomaticoEvento(cod, novaRef, this.rubricasManuais[idx].tipo);
          if (vAuto > 0) {
            this.rubricasManuais[idx].valor_total = vAuto;
            const inputVal = corpo.querySelector(`.rub-val[data-idx="${idx}"]`);
            if (inputVal) inputVal.value = vAuto;
          }
        }
        this.atualizarPreviaCalculo();
      });
    });

    corpo.querySelectorAll('.rub-val').forEach(el => {
      el.addEventListener('input', (e) => {
        const idx = Number(e.target.dataset.idx);
        this.rubricasManuais[idx].valor_total = Number(e.target.value || 0);
        this.atualizarPreviaCalculo();
      });
    });

    corpo.querySelectorAll('.rub-remover').forEach(el => {
      el.addEventListener('click', (e) => {
        const idx = Number(e.target.dataset.idx);
        this.rubricasManuais.splice(idx, 1);
        this.renderizarRubricasManuais();
        this.atualizarPreviaCalculo();
      });
    });
  },

  coletarEventosDoFormulario() {
    const eventos = [];
    const he50 = Number(document.getElementById('folha-campo-he50').value || 0);
    const he100 = Number(document.getElementById('folha-campo-he100').value || 0);
    const noturno = Number(document.getElementById('folha-campo-noturno').value || 0);
    const faltas = Number(document.getElementById('folha-campo-faltas').value || 0);
    const atrasos = Number(document.getElementById('folha-campo-atrasos').value || 0);

    if (he50 > 0) eventos.push({ codigo: '0010', quantidade: he50, percentual: 50.0 });
    if (he100 > 0) eventos.push({ codigo: '0011', quantidade: he100, percentual: 100.0 });
    if (noturno > 0) eventos.push({ codigo: '0020', quantidade: noturno, percentual: 20.0 });
    if (faltas > 0) eventos.push({ codigo: '0530', quantidade: faltas });
    if (atrasos > 0) eventos.push({ codigo: '0532', quantidade: atrasos });

    this.rubricasManuais.forEach((r, i) => {
      if (r.valor_total > 0 && (r.descricao || r.codigo)) {
        eventos.push({
          codigo: r.codigo || `MANUAL_${i + 1}`,
          descricao: r.descricao,
          tipo: r.tipo,
          referencia: r.referencia,
          valor_total: r.valor_total,
          is_custom_livre: Boolean(r.isCustom)
        });
      }
    });

    return eventos;
  },

  async simularFolhaNoBackend(exibirAviso = false) {
    const colabId = document.getElementById('folha-campo-colaborador').value;
    const competencia = document.getElementById('folha-campo-competencia').value;
    const dias = Number(document.getElementById('folha-campo-dias').value || 30);
    const divisor = Number(document.getElementById('folha-campo-divisor').value || 220);

    if (!colabId) {
      this.atualizarPreviaCalculoLocal();
      return;
    }

    const payload = {
      colaborador_id: Number(colabId),
      competencia: (competencia || '2026-10').trim(),
      dias_trabalhados: dias,
      dias_mes: 30,
      horas_divisor: divisor,
      eventos: this.coletarEventosDoFormulario()
    };

    try {
      const resp = await fetch(`${API_BASE}/folha/simular`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify(payload)
      });
      if (resp.ok) {
        const json = await resp.json();
        const d = json.dados;
        document.getElementById('preview-salario-prop').textContent = formatarMoeda(d.salario_base_contratual || d.salario_base_proporcional);
        document.getElementById('preview-base-inss').textContent = formatarMoeda(d.base_inss);
        document.getElementById('preview-base-fgts').textContent = formatarMoeda(d.base_fgts);
        document.getElementById('preview-fgts-mes').textContent = formatarMoeda(d.valor_fgts_informativo);
        document.getElementById('preview-base-irrf').textContent = formatarMoeda(d.base_irrf);
        if (exibirAviso) {
          exibirToast('Simulação executada com sucesso pelo motor oficial do backend!', 'success');
        }
        return;
      }
    } catch (e) {
      console.warn('Simulação backend indisponível, usando estimativa local:', e);
    }

    this.atualizarPreviaCalculoLocal();
  },

  async recalcularFolhaNoBackend(folhaId) {
    const alerta = document.getElementById('folha-form-alerta');
    alerta.classList.add('hidden');
    const colabId = document.getElementById('folha-campo-colaborador').value;
    const competencia = document.getElementById('folha-campo-competencia').value;
    const inicio = document.getElementById('folha-campo-inicio').value;
    const fim = document.getElementById('folha-campo-fim').value;
    const pagto = document.getElementById('folha-campo-pagamento').value;
    const dias = Number(document.getElementById('folha-campo-dias').value || 30);
    const divisor = Number(document.getElementById('folha-campo-divisor').value || 220);
    const observacoes = document.getElementById('folha-campo-observacoes').value;

    const payload = {
      colaborador_id: Number(colabId),
      competencia: competencia.trim(),
      tipo_folha: tipoFolha,
      salvar_como_rascunho: Boolean(salvarComoRascunho),
      periodo_inicio: inicio,
      periodo_fim: fim,
      data_pagamento: pagto || null,
      dias_trabalhados: dias,
      dias_mes: 30,
      horas_divisor: divisor,
      eventos: this.coletarEventosDoFormulario(),
      observacoes: observacoes
    };

    try {
      const resp = await fetch(`${API_BASE}/folha/${folhaId}/recalcular`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify(payload)
      });
      const resJson = await resp.json();
      if (!resp.ok) {
        alerta.textContent = resJson.mensagem || 'Falha ao recalcular folha.';
        alerta.classList.remove('hidden');
        return;
      }

      exibirToast(`Folha #${folhaId} recalculada e persistida com sucesso no banco de dados!`, 'success');
      const d = resJson.dados;
      document.getElementById('preview-salario-prop').textContent = formatarMoeda(d.salario_base_contratual || d.salario_base_proporcional);
      document.getElementById('preview-base-inss').textContent = formatarMoeda(d.base_inss);
      document.getElementById('preview-base-fgts').textContent = formatarMoeda(d.base_fgts);
      document.getElementById('preview-fgts-mes').textContent = formatarMoeda(d.valor_fgts_informativo);
      document.getElementById('preview-base-irrf').textContent = formatarMoeda(d.base_irrf);
      await this.carregarFolhas();
    } catch (e) {
      console.error('Erro ao recalcular folha:', e);
      alerta.textContent = 'Erro de comunicação ao recalcular.';
      alerta.classList.remove('hidden');
    }
  },

  atualizarPreviaCalculoLocal() {
    const colabId = document.getElementById('folha-campo-colaborador').value;
    const dias = Number(document.getElementById('folha-campo-dias').value || 30);
    const divisor = Number(document.getElementById('folha-campo-divisor').value || 220);

    const c = this.colaboradoresElegiveis.find(item => String(item.id) === String(colabId));
    const sb = c ? Number(c.salario_base || 0) : 0;

    const sbProp = (sb / 30) * Math.min(30, dias);
    const vh = divisor > 0 ? (sb / divisor) : 0;

    const he50 = Number(document.getElementById('folha-campo-he50').value || 0);
    const he100 = Number(document.getElementById('folha-campo-he100').value || 0);
    const noturno = Number(document.getElementById('folha-campo-noturno').value || 0);
    const faltas = Number(document.getElementById('folha-campo-faltas').value || 0);
    const atrasos = Number(document.getElementById('folha-campo-atrasos').value || 0);

    let totProventos = sbProp;
    totProventos += he50 * (vh * 1.5);
    totProventos += he100 * (vh * 2.0);
    totProventos += noturno * (vh * 0.2);

    let totDescontos = 0;
    totDescontos += faltas * (sb / 30);
    totDescontos += atrasos * vh;

    this.rubricasManuais.forEach(r => {
      let v = Number(r.valor_total || 0);
      if (v <= 0 && sb > 0) {
        // Prévia estimada instantânea com base nas fórmulas do catálogo de eventos
        const ref = Number(r.referencia || 0);
        if (r.codigo === '0010') v = ref * (vh * 1.5);
        else if (r.codigo === '0011') v = ref * (vh * 2.0);
        else if (r.codigo === '0020') v = ref * (vh * 0.2);
        else if (r.codigo === '0030') v = 1518.00 * ((ref === 10 || ref === 20 || ref === 40 ? ref : 20) / 100);
        else if (r.codigo === '0031') v = sb * 0.30;
        else if (r.codigo === '0032') v = sb * 0.25;
        else if (r.codigo === '0040') v = sb * ((ref || 40) / 100);
        else if (r.codigo === '0041') v = sb * 0.10;
        else if (r.codigo === '0100') v = (sb / 30) * (ref || 30);
        else if (r.codigo === '0101') v = (sb / 30) * (ref || 30) * (1 / 3);
        else if (r.codigo === '0110') v = ((sb / 12) * (ref || 12)) * 0.50;
        else if (r.codigo === '0510') v = sb * ((ref || 6) / 100);
        else if (r.codigo === '0520') v = sb * ((ref || 40) / 100);
        else if (r.codigo === '0530') v = (sb / 30) * (ref || 1);
        else if (r.codigo === '0532') v = vh * (ref || 1);
      }
      if (r.tipo === 'provento') totProventos += v;
      else if (r.tipo === 'desconto') totDescontos += v;
      // informativo: apenas registro (bases/encargos), não entra nos totais
    });

    let estInss = 0;
    if (totProventos > 0) {
      if (totProventos <= 1518.00) estInss = totProventos * 0.075;
      else if (totProventos <= 2793.88) estInss = 113.85 + (totProventos - 1518.00) * 0.09;
      else if (totProventos <= 4190.83) estInss = 113.85 + 114.83 + (totProventos - 2793.88) * 0.12;
      else estInss = Math.min(908.85, 113.85 + 114.83 + 167.63 + (totProventos - 4190.83) * 0.14);
    }
    totDescontos += estInss;

    const liquido = Math.max(0, totProventos - totDescontos);
    // Estimativa local das bases (usada apenas quando o backend está indisponível)
    const baseInssEst = totProventos;
    const baseFgtsEst = totProventos;
    const fgtsMesEst = baseFgtsEst * 0.08;
    const baseIrrfEst = Math.max(0, baseInssEst - estInss);

    document.getElementById('preview-salario-prop').textContent = formatarMoeda(sb);
    document.getElementById('preview-base-inss').textContent = formatarMoeda(baseInssEst);
    document.getElementById('preview-base-fgts').textContent = formatarMoeda(baseFgtsEst);
    document.getElementById('preview-fgts-mes').textContent = formatarMoeda(fgtsMesEst);
    document.getElementById('preview-base-irrf').textContent = formatarMoeda(baseIrrfEst);
  },

  atualizarPreviaCalculo() {
    this.simularFolhaNoBackend(false);
  },

  async salvarFolha(salvarComoRascunho = false) {
    const colabId = document.getElementById('folha-campo-colaborador').value;
    const competencia = document.getElementById('folha-campo-competencia').value;
    const tipoFolha = document.getElementById('folha-campo-tipo')?.value || 'mensal';
    const inicio = document.getElementById('folha-campo-inicio').value;
    const fim = document.getElementById('folha-campo-fim').value;
    const pagto = document.getElementById('folha-campo-pagamento').value;
    const dias = Number(document.getElementById('folha-campo-dias').value || 30);
    const divisor = Number(document.getElementById('folha-campo-divisor').value || 220);
    const observacoes = document.getElementById('folha-campo-observacoes').value;
    const folhaId = document.getElementById('folha-id-edicao').value;

    const alerta = document.getElementById('folha-form-alerta');
    alerta.classList.add('hidden');
    const mostrarErro = (msg) => {
      alerta.textContent = msg;
      alerta.classList.remove('hidden');
      alerta.scrollIntoView({ behavior: 'smooth', block: 'center' });
      exibirToast(msg, 'error');
    };

    const incompletas = this.rubricasManuais.filter(r => Number(r.valor_total) > 0 && (!r.codigo || !r.descricao));
    if (incompletas.length > 0) {
      mostrarErro('Selecione o evento (ou informe a descrição em "Outro") em todas as linhas com valor.');
      return;
    }

    if (!colabId) {
      mostrarErro('Selecione um colaborador ativo para a folha.');
      return;
    }

    if (!competencia) {
      mostrarErro('Informe a competência no formato AAAA-MM.');
      return;
    }

    const payload = {
      colaborador_id: Number(colabId),
      competencia: competencia.trim(),
      tipo_folha: tipoFolha,
      salvar_como_rascunho: Boolean(salvarComoRascunho),
      periodo_inicio: inicio,
      periodo_fim: fim,
      data_pagamento: pagto || null,
      dias_trabalhados: dias,
      dias_mes: 30,
      horas_divisor: divisor,
      eventos: this.coletarEventosDoFormulario(),
      observacoes: observacoes
    };

    const metodo = folhaId ? 'PUT' : 'POST';
    const url = folhaId ? `${API_BASE}/folha/${folhaId}` : `${API_BASE}/folha`;

    const btnSalvar = document.querySelector('#form-folha-pagamento button[type="submit"]') || document.getElementById('btn-salvar-folha');
    if (btnSalvar) btnSalvar.disabled = true;

    try {
      const resp = await fetch(url, {
        method: metodo,
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify(payload)
      });

      const resJson = await resp.json();

      if (!resp.ok) {
        mostrarErro((resJson.erros && resJson.erros.competencia) || resJson.mensagem || 'Ocorreu um erro ao processar a folha.');
        return;
      }

      const msgSucesso = folhaId ? 'Folha recalculada e salva com sucesso!' : 'Folha de pagamento gerada e salva com sucesso no banco de dados!';
      exibirToast(msgSucesso, 'success');
      document.getElementById('modal-folha-form').classList.add('hidden');

      // Sincroniza o filtro com a competência da folha salva para que ela apareça na tabela imediatamente
      if (payload.competencia) {
        this.filtros.competencia = payload.competencia;
        const inputComp = document.getElementById('filtro-folha-competencia');
        if (inputComp) inputComp.value = payload.competencia;
      }

      await this.carregarFolhas();
      if (resJson.dados && resJson.dados.id) {
        this.abrirModalHolerite(resJson.dados.id, true);
      }
    } catch (e) {
      console.error('Falha ao salvar folha:', e);
      mostrarErro('Erro de comunicação com o servidor backend.');
    } finally {
      if (btnSalvar) btnSalvar.disabled = false;
    }
  },

  async abrirModalHolerite(folhaId, acabouDeSalvar = false) {
    try {
      const resp = await fetch(`${API_BASE}/folha/${folhaId}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (!resp.ok) {
        exibirToast('Não foi possível obter os dados do holerite.', 'error');
        return;
      }

      const json = await resp.json();
      const f = json.dados;
      this.folhaParaFecharOuReabrir = f;

      const bannerSucesso = document.getElementById('holerite-alerta-sucesso');
      if (bannerSucesso) {
        if (acabouDeSalvar) {
          bannerSucesso.classList.remove('hidden');
        } else {
          bannerSucesso.classList.add('hidden');
        }
      }

      // Preencher Cabeçalho da Empresa
      const elRazao = document.getElementById('h-empresa-razao');
      const elCnpjCidade = document.getElementById('h-empresa-cnpj-cidade');
      if (elRazao) {
        elRazao.textContent = f.empresa_razao_social || f.empresa_nome || 'FORÇAVERDE USINA DE ENERGIA E BIOCOMBUSTÍVEIS S.A.';
      }
      if (elCnpjCidade) {
        elCnpjCidade.textContent = f.empresa_cnpj ? `CNPJ: ${f.empresa_cnpj} • ${f.empresa_endereco || 'Sertãozinho / SP'}` : 'CNPJ: 12.345.678/0001-90 • Fazenda Boa Esperança, s/n - Sertãozinho / SP';
      }

      // Preencher Contracheque
      document.getElementById('h-competencia').textContent = f.competencia;
      if (document.getElementById('h-numero-recibo')) document.getElementById('h-numero-recibo').textContent = f.numero_recibo || `REC-${String(f.competencia || '').replace('-', '')}-${String(f.id || 0).padStart(6, '0')}`;
      document.getElementById('h-matricula').textContent = f.colaborador_matricula || '--';
      document.getElementById('h-nome').textContent = f.colaborador_nome || '--';
      const cpfBruto = formatarCpf(f.colaborador_cpf || '');
      const cpfMascarado = cpfBruto.length === 14 ? `***.${cpfBruto.slice(4, 11)}-**` : cpfBruto;
      document.getElementById('h-cpf').textContent = cpfMascarado;
      document.getElementById('h-cpf').title = cpfBruto;
      document.getElementById('h-cargo').textContent = f.colaborador_cargo || '--';
      document.getElementById('h-setor').textContent = f.colaborador_setor || '--';
      document.getElementById('h-admissao').textContent = formatarDataBR(f.colaborador_data_admissao);
      document.getElementById('h-data-pagto').textContent = formatarDataBR(f.data_pagamento) || '05 do mês subsequente';
      if (document.getElementById('h-colab-salario-base')) document.getElementById('h-colab-salario-base').textContent = formatarMoeda(f.salario_base_contratual);
      if (document.getElementById('h-dep-irrf')) document.getElementById('h-dep-irrf').textContent = String(f.total_dependentes_irrf ?? 0);
      if (document.getElementById('h-data-emissao')) document.getElementById('h-data-emissao').textContent = new Date().toLocaleString('pt-BR');
      if (document.getElementById('h-autenticidade')) document.getElementById('h-autenticidade').textContent = f.codigo_autenticidade || '--';

      // Itens discriminados
      const corpoItens = document.getElementById('h-corpo-itens');
      corpoItens.innerHTML = '';

      (f.itens || []).forEach(it => {
        const tr = document.createElement('tr');
        const isProvento = it.tipo === 'provento';
        const isDesconto = it.tipo === 'desconto';

        let refStr = '--';
        if (it.referencia > 0) {
          refStr = `${it.referencia} ${it.unidade_referencia || ''}`;
        }

        tr.innerHTML = `
          <td><strong>${it.codigo_evento}</strong></td>
          <td>${it.descricao} ${it.tipo === 'informativo' ? '<span class="text-xs text-muted">(Informativo)</span>' : ''}</td>
          <td style="text-align: center;">${refStr}</td>
          <td style="text-align: right; font-weight: ${isProvento ? '600' : 'normal'}; color: ${isProvento ? '#166534' : 'inherit'};">
            ${isProvento ? formatarMoeda(it.valor_total) : ''}
          </td>
          <td style="text-align: right; font-weight: ${isDesconto ? '600' : 'normal'}; color: ${isDesconto ? '#991b1b' : 'inherit'};">
            ${isDesconto ? formatarMoeda(it.valor_total) : ''}
          </td>
        `;
        corpoItens.appendChild(tr);
      });

      // Totais e bases
      document.getElementById('h-total-proventos').textContent = formatarMoeda(f.total_proventos);
      document.getElementById('h-total-descontos').textContent = formatarMoeda(f.total_descontos);
      document.getElementById('h-salario-liquido').textContent = formatarMoeda(f.salario_liquido);

      document.getElementById('h-base-contratual').textContent = formatarMoeda(f.salario_base_contratual);
      document.getElementById('h-base-inss').textContent = formatarMoeda(f.base_inss);
      document.getElementById('h-base-fgts').textContent = formatarMoeda(f.base_fgts);
      document.getElementById('h-valor-fgts').textContent = formatarMoeda(f.valor_fgts_informativo);
      document.getElementById('h-base-irrf').textContent = formatarMoeda(f.base_irrf);

      // Memória de cálculo detalhada
      const containerMem = document.getElementById('h-memoria-linhas');
      containerMem.innerHTML = '';
      (f.itens || []).forEach(it => {
        if (it.memoria_calculo) {
          const div = document.createElement('div');
          div.className = 'memoria-linha';
          div.innerHTML = `<strong>[${it.codigo_evento}] ${it.descricao}:</strong> ${it.memoria_calculo}`;
          containerMem.appendChild(div);
        }
      });

      // Auditoria
      const timeline = document.getElementById('h-auditoria-timeline');
      timeline.innerHTML = '';
      const divCriador = document.createElement('div');
      divCriador.innerHTML = `&bull; <strong>Criada por:</strong> ${f.criado_por} em ${f.criado_em}`;
      timeline.appendChild(divCriador);

      if (f.fechado_por) {
        const divFechador = document.createElement('div');
        divFechador.innerHTML = `&bull; <strong>Fechada por:</strong> ${f.fechado_por} em ${f.fechado_em}`;
        timeline.appendChild(divFechador);
      }

      (f.historico || []).forEach(h => {
        const divH = document.createElement('div');
        divH.innerHTML = `&bull; [${h.data_hora}] <strong>${h.acao}:</strong> ${h.descricao} (${h.usuario_responsavel})`;
        timeline.appendChild(divH);
      });

      // Visibilidade de botões contextuais
      const btnAprovarAcao = document.getElementById('btn-aprovar-folha-acao');
      const btnFecharAcao = document.getElementById('btn-fechar-folha-acao');
      const btnReabrirAcao = document.getElementById('btn-reabrir-folha-acao');
      if (f.situacao === 'fechada') {
        if (btnAprovarAcao) btnAprovarAcao.style.display = 'none';
        if (btnFecharAcao) btnFecharAcao.style.display = 'none';
        if (btnReabrirAcao) btnReabrirAcao.style.display = 'inline-flex';
      } else {
        if (btnAprovarAcao) btnAprovarAcao.style.display = f.situacao === 'calculada' ? 'inline-flex' : 'none';
        if (btnFecharAcao) btnFecharAcao.style.display = 'inline-flex';
        if (btnReabrirAcao) btnReabrirAcao.style.display = 'none';
      }

      document.getElementById('modal-holerite').classList.remove('hidden');
    } catch (e) {
      console.error('Erro ao abrir demonstrativo da folha:', e);
      exibirToast('Erro ao carregar demonstrativo.', 'error');
    }
  },

  async aprovarFolhaAtual() {
    if (!this.folhaParaFecharOuReabrir) return;
    try {
      const resp = await fetch(`${API_BASE}/folha/${this.folhaParaFecharOuReabrir.id}/aprovar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({})
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao aprovar folha.', 'error');
        return;
      }
      exibirToast(json.mensagem || 'Folha aprovada!', 'success');
      await this.carregarFolhas();
      await this.abrirModalHolerite(this.folhaParaFecharOuReabrir.id, false);
    } catch (e) {
      exibirToast('Erro de comunicação ao aprovar folha.', 'error');
    }
  },

  // ── Catálogo Parametrizável de Rubricas ─────────────────────────────────
  rubricasCatalogo: [],

  async abrirCatalogoRubricas() {
    try {
      const resp = await fetch(`${API_BASE}/folha/eventos-catalogo`, { headers: getAuthHeaders(), credentials: 'include' });
      const json = await resp.json();
      this.rubricasCatalogo = json.dados || [];
      this.renderizarRubricas();
      document.getElementById('modal-catalogo-rubricas').classList.remove('hidden');
    } catch (e) {
      exibirToast('Erro ao carregar catálogo de rubricas.', 'error');
    }
  },

  renderizarRubricas() {
    const tbody = document.getElementById('corpo-tabela-rubricas');
    if (!tbody) return;
    const q = (document.getElementById('rub-filtro-q')?.value || '').trim().toLowerCase();
    const tipo = document.getElementById('rub-filtro-tipo')?.value || 'todos';
    const filtradas = (this.rubricasCatalogo || []).filter(r => {
      if (tipo !== 'todos' && r.tipo !== tipo) return false;
      if (q && !String(r.codigo).toLowerCase().includes(q) && !String(r.descricao || r.evento).toLowerCase().includes(q)) return false;
      return true;
    });
    tbody.innerHTML = filtradas.map(r => `
      <tr>
        <td><strong>${r.codigo}</strong>${Number(r.sistema_legal) ? ' <span title="Rubrica Legal Protegida">🔒</span>' : ''}</td>
        <td>${r.descricao || r.evento}</td>
        <td><span class="badge badge-dep">${r.tipo}</span></td>
        <td>${Number(r.incide_inss) ? '✓' : '—'}</td>
        <td>${Number(r.incide_irrf) ? '✓' : '—'}</td>
        <td>${Number(r.incide_fgts) ? '✓' : '—'}</td>
        <td>${Number(r.ativo ?? 1) ? '<span class="badge badge-ativo">Ativa</span>' : '<span class="badge badge-inativo">Inativa</span>'}</td>
        <td class="text-right">
          <button type="button" class="btn btn-outline btn-sm" onclick="FolhaManager.editarRubrica(${r.id})">Editar</button>
          <button type="button" class="btn btn-outline btn-sm" onclick="FolhaManager.alternarStatusRubrica(${r.id}, ${Number(r.ativo ?? 1) ? 'false' : 'true'})">${Number(r.ativo ?? 1) ? 'Inativar' : 'Ativar'}</button>
        </td>
      </tr>
    `).join('');
  },

  limparFormRubrica() {
    document.getElementById('rubrica-id').value = '';
    document.getElementById('rub-codigo').value = '';
    document.getElementById('rub-codigo').disabled = false;
    document.getElementById('rub-descricao').value = '';
    document.getElementById('rub-tipo').value = 'provento';
    document.getElementById('rub-forma').value = 'valor_fixo';
    ['rub-inss', 'rub-irrf', 'rub-fgts', 'rub-ref-ferias', 'rub-ref-13'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.checked = false;
    });
  },

  editarRubrica(id) {
    const r = (this.rubricasCatalogo || []).find(x => x.id === id);
    if (!r) return;
    document.getElementById('rubrica-id').value = r.id;
    document.getElementById('rub-codigo').value = r.codigo;
    document.getElementById('rub-codigo').disabled = true;
    document.getElementById('rub-descricao').value = r.descricao || r.evento;
    document.getElementById('rub-tipo').value = r.tipo;
    document.getElementById('rub-forma').value = r.forma_calculo || 'valor_fixo';
    document.getElementById('rub-inss').checked = Boolean(Number(r.incide_inss));
    document.getElementById('rub-irrf').checked = Boolean(Number(r.incide_irrf));
    document.getElementById('rub-fgts').checked = Boolean(Number(r.incide_fgts));
    document.getElementById('rub-ref-ferias').checked = Boolean(Number(r.reflexo_ferias));
    document.getElementById('rub-ref-13').checked = Boolean(Number(r.reflexo_13));
  },

  async salvarRubrica() {
    const id = document.getElementById('rubrica-id').value;
    const payload = {
      codigo: document.getElementById('rub-codigo').value.trim(),
      descricao: document.getElementById('rub-descricao').value.trim(),
      tipo: document.getElementById('rub-tipo').value,
      forma_calculo: document.getElementById('rub-forma').value,
      incide_inss: document.getElementById('rub-inss').checked ? 1 : 0,
      incide_irrf: document.getElementById('rub-irrf').checked ? 1 : 0,
      incide_fgts: document.getElementById('rub-fgts').checked ? 1 : 0,
      reflexo_ferias: document.getElementById('rub-ref-ferias').checked ? 1 : 0,
      reflexo_13: document.getElementById('rub-ref-13').checked ? 1 : 0,
    };
    const url = id ? `${API_BASE}/folha/eventos-catalogo/${id}` : `${API_BASE}/folha/eventos-catalogo`;
    const method = id ? 'PUT' : 'POST';
    try {
      const resp = await fetch(url, { method, headers: getAuthHeaders(), credentials: 'include', body: JSON.stringify(payload) });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao salvar rubrica.', 'error');
        return;
      }
      exibirToast(json.mensagem || 'Rubrica salva!', 'success');
      this.limparFormRubrica();
      await this.abrirCatalogoRubricas();
    } catch (e) {
      exibirToast('Erro de comunicação ao salvar rubrica.', 'error');
    }
  },

  async alternarStatusRubrica(id, ativo) {
    try {
      const resp = await fetch(`${API_BASE}/folha/eventos-catalogo/${id}/status`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ ativo })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao alterar status da rubrica.', 'error');
        return;
      }
      exibirToast(json.mensagem || 'Status atualizado!', 'success');
      await this.abrirCatalogoRubricas();
    } catch (e) {
      exibirToast('Erro ao atualizar status da rubrica.', 'error');
    }
  },

  // ── Processamento de Folha em Lote ──────────────────────────────────────
  async abrirModalLote() {
    try {
      const resp = await fetch(`${API_BASE}/folha/colaboradores`, { headers: getAuthHeaders(), credentials: 'include' });
      const json = await resp.json();
      const colabs = json.dados || [];
      const container = document.getElementById('lote-lista-colaboradores');
      container.innerHTML = colabs.map(c => `
        <label style="display:flex; align-items:center; gap:0.4rem; font-size:0.84rem; padding:0.3rem; border:1px solid #e2e8f0; border-radius:6px;">
          <input type="checkbox" class="lote-colab-cb" value="${c.id}" checked onchange="FolhaManager.atualizarContadorLote()">
          <span><strong>${c.matricula}</strong> — ${c.nome_completo}</span>
        </label>
      `).join('');
      const comp = document.getElementById('filtro-folha-competencia')?.value;
      if (comp) document.getElementById('lote-competencia').value = comp;
      this.atualizarContadorLote();
      document.getElementById('modal-processar-lote').classList.remove('hidden');
    } catch (e) {
      exibirToast('Erro ao carregar colaboradores para lote.', 'error');
    }
  },

  toggleTodosLote(checked) {
    document.querySelectorAll('.lote-colab-cb').forEach(cb => { cb.checked = checked; });
    this.atualizarContadorLote();
  },

  atualizarContadorLote() {
    const qtd = document.querySelectorAll('.lote-colab-cb:checked').length;
    const el = document.getElementById('lote-qtd-selecionados');
    if (el) el.textContent = String(qtd);
  },

  async executarProcessamentoLote() {
    const competencia = document.getElementById('lote-competencia').value;
    const tipo_folha = document.getElementById('lote-tipo-folha').value;
    const data_pagamento = document.getElementById('lote-data-pagto').value;
    const colaboradores_ids = Array.from(document.querySelectorAll('.lote-colab-cb:checked')).map(cb => Number(cb.value));
    if (!competencia || colaboradores_ids.length === 0) {
      exibirToast('Informe a competência e selecione ao menos um colaborador.', 'error');
      return;
    }
    const [ano, mes] = competencia.split('-').map(Number);
    const ultimoDia = new Date(ano, mes, 0).getDate();
    try {
      const resp = await fetch(`${API_BASE}/folha/processar-lote`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          competencia,
          tipo_folha,
          periodo_inicio: `${competencia}-01`,
          periodo_fim: `${competencia}-${String(ultimoDia).padStart(2, '0')}`,
          data_pagamento: data_pagamento || null,
          colaboradores_ids
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro no processamento em lote.', 'error');
        return;
      }
      exibirToast(json.mensagem, 'success');
      document.getElementById('modal-processar-lote').classList.add('hidden');
      this.filtros.competencia = competencia;
      const inputComp = document.getElementById('filtro-folha-competencia');
      if (inputComp) inputComp.value = competencia;
      await this.carregarFolhas();
    } catch (e) {
      exibirToast('Erro de comunicação no processamento em lote.', 'error');
    }
  },

  // ── Painel Detalhado da Folha Individual (Layout 2 Colunas) ──────────────
  painelInd: {
    colaboradorId: null,
    folhaId: null,
    situacao: 'aberta',
    eventosLancados: [],
    ultimoCalculo: null,
  },

  async abrirPainelIndividual(folhaId = null, colabId = null) {
    const wrapper = document.getElementById('painel-folha-individual');
    if (!wrapper) return;
    wrapper.classList.remove('hidden');

    // Carregar colaboradores ativos e rubricas se ainda não carregados
    if (!this.colaboradoresAtivos || !this.colaboradoresAtivos.length) {
      await this.carregarColaboradoresAtivos();
    }
    if (!this.rubricasCatalogo || !this.rubricasCatalogo.length) {
      try {
        const rResp = await fetch(`${API_BASE}/folha/eventos-catalogo?apenas_ativas=1`, { headers: getAuthHeaders(), credentials: 'include' });
        const rJson = await rResp.json();
        this.rubricasCatalogo = rJson.dados || [];
      } catch (e) { /* ignore */ }
    }

    const selColab = document.getElementById('ind-select-colaborador');
    if (selColab) {
      selColab.innerHTML = '<option value="">Selecione um colaborador...</option>' +
        (this.colaboradoresAtivos || []).map(c => `<option value="${c.id}">${c.matricula} — ${c.nome_completo}</option>`).join('');
    }
    const selRub = document.getElementById('ind-ev-rubrica');
    if (selRub) {
      const editaveis = (this.rubricasCatalogo || []).filter(r => r.tipo !== 'informativo' && !['0001', '0501', '0502', '0505', '0506', '0507'].includes(r.codigo));
      selRub.innerHTML = '<option value="">Selecione...</option>' +
        editaveis.map(r => `<option value="${r.codigo}" data-tipo="${r.tipo}" data-desc="${r.descricao || r.evento}">[${r.codigo}] ${r.descricao || r.evento} (${r.tipo})</option>`).join('');
    }

    if (folhaId) {
      try {
        const resp = await fetch(`${API_BASE}/folha/${folhaId}`, { headers: getAuthHeaders(), credentials: 'include' });
        const json = await resp.json();
        const f = json.dados;
        if (f) {
          document.getElementById('ind-competencia').value = f.competencia;
          document.getElementById('ind-tipo-folha').value = f.tipo_folha || 'mensal';
          if (selColab) selColab.value = String(f.colaborador_id);
          await this._carregarDadosPainel(f.colaborador_id, f);
          return;
        }
      } catch (e) { /* fallback */ }
    }

    const alvoColab = colabId || (this.colaboradoresAtivos && this.colaboradoresAtivos[0] && this.colaboradoresAtivos[0].id);
    if (alvoColab) {
      if (selColab) selColab.value = String(alvoColab);
      await this.selecionarColaboradorPainel(alvoColab);
    }
  },

  fecharPainelIndividual() {
    document.getElementById('painel-folha-individual')?.classList.add('hidden');
  },

  async selecionarColaboradorPainel(colabId) {
    if (!colabId) return;
    const comp = document.getElementById('ind-competencia')?.value || '2026-10';
    const tipo = document.getElementById('ind-tipo-folha')?.value || 'mensal';
    try {
      const resp = await fetch(`${API_BASE}/folha?colaborador_id=${colabId}&competencia=${encodeURIComponent(comp)}&tipo_folha=${encodeURIComponent(tipo)}`, {
        headers: getAuthHeaders(), credentials: 'include'
      });
      const json = await resp.json();
      const lista = json.dados || [];
      if (lista.length > 0) {
        const detResp = await fetch(`${API_BASE}/folha/${lista[0].id}`, { headers: getAuthHeaders(), credentials: 'include' });
        const detJson = await detResp.json();
        await this._carregarDadosPainel(Number(colabId), detJson.dados);
      } else {
        await this._carregarDadosPainel(Number(colabId), null);
      }
    } catch (e) {
      await this._carregarDadosPainel(Number(colabId), null);
    }
  },

  async recarregarPainelIndividual() {
    const colabId = document.getElementById('ind-select-colaborador')?.value;
    if (colabId) await this.selecionarColaboradorPainel(colabId);
  },

  async _carregarDadosPainel(colabId, folhaExistente) {
    const colab = (this.colaboradoresAtivos || []).find(c => Number(c.id) === Number(colabId)) || {};
    this.painelInd.colaboradorId = Number(colabId);
    this.painelInd.folhaId = folhaExistente ? folhaExistente.id : null;
    this.painelInd.situacao = folhaExistente ? folhaExistente.situacao : 'aberta';

    const nome = folhaExistente?.colaborador_nome || colab.nome_completo || '--';
    const iniciais = nome.split(' ').filter(Boolean).slice(0, 2).map(p => p[0].toUpperCase()).join('') || 'RH';
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    set('ind-avatar', iniciais);
    set('ind-nome', nome);
    set('ind-cargo-mat', `${folhaExistente?.colaborador_cargo || colab.cargo || '--'} • Mat. ${folhaExistente?.colaborador_matricula || colab.matricula || '--'}`);
    set('ind-salario-base', formatarMoeda(folhaExistente?.salario_base_contratual ?? colab.salario_base ?? 0));
    set('ind-admissao', formatarDataBR(folhaExistente?.colaborador_data_admissao || colab.data_admissao));
    set('ind-dependentes', String(folhaExistente?.total_dependentes_irrf ?? colab.total_dependentes_irrf ?? colab.total_dependentes ?? 0));
    set('ind-cpf', formatarCpf(folhaExistente?.colaborador_cpf || colab.cpf || ''));

    // Limpar mini-formulário ao trocar colaborador/mês
    const elRub = document.getElementById('ind-ev-rubrica');
    const elRef = document.getElementById('ind-ev-ref');
    const elVal = document.getElementById('ind-ev-valor');
    if (elRub) elRub.value = '';
    if (elRef) elRef.value = '0';
    if (elVal) elVal.value = '';
    document.getElementById('ind-form-novo-evento')?.classList.add('hidden');

    // Eventos lançados manuais/variáveis (excluindo salário-base e tributos automáticos INSS/IRRF)
    const codigosAutomaticos = ['001', '0001', '501', '0501', '0502', '502', '0505', '0506', '0507'];
    const eventos = [];
    if (folhaExistente && Array.isArray(folhaExistente.itens)) {
      folhaExistente.itens.forEach(it => {
        if (it.tipo === 'informativo') return;
        if (codigosAutomaticos.includes(String(it.codigo_evento))) return;
        eventos.push({
          codigo: it.codigo_evento,
          descricao: it.descricao,
          tipo: it.tipo,
          referencia: Number(it.referencia || 0),
          valor_informado: it.origem === 'manual' ? Number(it.valor_total || 0) : null,
        });
      });
    }
    this.painelInd.eventosLancados = eventos;
    this._atualizarBotoesStatusPainel();
    await this.simularPainelIndividual();
  },

  _atualizarBotoesStatusPainel() {
    const sit = this.painelInd.situacao;
    const fechada = sit === 'fechada';
    const txtMap = {
      aberta: 'Competência aberta — adicione eventos e clique em Salvar & Calcular.',
      rascunho: 'Rascunho salvo — adicione ou edite eventos antes de calcular.',
      calculada: 'Folha calculada — aguardando conferência e aprovação.',
      aprovada: 'Folha aprovada — pronta para fechamento definitivo.',
      fechada: 'Competência fechada — os lançamentos não podem ser alterados.'
    };
    const elTxt = document.getElementById('ind-status-texto');
    if (elTxt) elTxt.textContent = (fechada ? '🔒 ' : '') + (txtMap[sit] || sit);

    const show = (id, cond) => { const el = document.getElementById(id); if (el) el.style.display = cond ? 'inline-flex' : 'none'; };
    show('ind-btn-importar-beneficios', !fechada);
    show('ind-btn-add-evento', !fechada);
    show('ind-btn-salvar', !fechada);
    show('ind-btn-aprovar', sit === 'calculada');
    show('ind-btn-fechar', Boolean(this.painelInd.folhaId) && !fechada);
    show('ind-btn-reabrir', fechada);
    show('ind-btn-holerite', Boolean(this.painelInd.folhaId));
    show('ind-btn-pdf', Boolean(this.painelInd.folhaId));
  },

  toggleFormEventoPainel() {
    document.getElementById('ind-form-novo-evento')?.classList.toggle('hidden');
  },

  async adicionarEventoPainel() {
    const sel = document.getElementById('ind-ev-rubrica');
    const opt = sel?.options[sel.selectedIndex];
    const codigo = sel?.value;
    if (!codigo) {
      exibirToast('Selecione uma rubrica.', 'error');
      return;
    }
    const tipo = opt.getAttribute('data-tipo') || 'provento';
    const descricao = opt.getAttribute('data-desc') || opt.textContent;
    const ref = Number(document.getElementById('ind-ev-ref')?.value || 0);
    const valRaw = document.getElementById('ind-ev-valor')?.value;
    const valor_informado = valRaw !== '' && valRaw !== null ? Number(valRaw) : null;

    this.painelInd.eventosLancados.push({ codigo, descricao, tipo, referencia: ref, valor_informado });
    document.getElementById('ind-ev-ref').value = '0';
    document.getElementById('ind-ev-valor').value = '';
    await this.simularPainelIndividual();
  },

  async removerEventoPainel(idx) {
    if (this.painelInd.situacao === 'fechada') return;
    this.painelInd.eventosLancados.splice(idx, 1);
    await this.simularPainelIndividual();
  },

  async importarBeneficiosAtivosPainel() {
    if (!this.painelInd.colaboradorId) {
      exibirToast('Selecione um colaborador primeiro.', 'warning');
      return;
    }
    const comp = document.getElementById('ind-competencia')?.value || '2026-10';
    try {
      const resp = await fetch(
        `${API_BASE}/beneficios/descontos-folha?colaborador_id=${this.painelInd.colaboradorId}&competencia=${encodeURIComponent(comp)}`,
        { headers: getAuthHeaders(), credentials: 'include' }
      );
      const json = await resp.json();
      if (!resp.ok || !json.dados) {
        exibirToast(json.mensagem || 'Erro ao consultar descontos de benefícios.', 'error');
        return;
      }
      const eventosBen = json.dados.eventos_folha || [];
      if (!eventosBen.length) {
        exibirToast('Nenhum desconto de benefício ativo encontrado para esta competência.', 'info');
        return;
      }
      let adicionados = 0;
      eventosBen.forEach(ev => {
        const jaExiste = this.painelInd.eventosLancados.some(x => x.codigo === ev.codigo && x.descricao === ev.descricao);
        if (!jaExiste) {
          this.painelInd.eventosLancados.push({
            codigo: ev.codigo,
            descricao: ev.descricao,
            tipo: 'desconto',
            referencia: Number(ev.referencia || 1),
            percentual: ev.percentual || 0,
            valor_informado: Number(ev.valor_informado || 0)
          });
          adicionados++;
        }
      });
      await this.simularPainelIndividual();
      exibirToast(`${adicionados} desconto(s) de benefício importado(s) para a folha.`, 'success');
    } catch (e) {
      exibirToast('Erro de comunicação ao importar benefícios na folha.', 'error');
    }
  },

  async simularPainelIndividual() {
    if (!this.painelInd.colaboradorId) return;
    try {
      const resp = await fetch(`${API_BASE}/folha/simular`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          colaborador_id: this.painelInd.colaboradorId,
          competencia: this.painelInd.competencia || document.getElementById('ind-competencia')?.value,
          eventos: this.painelInd.eventosLancados
        })
      });
      const json = await resp.json();
      if (!resp.ok || !json.dados) {
        if (json.erros && json.erros.eventos) exibirToast(json.erros.eventos, 'error');
        else if (json.mensagem) exibirToast(json.mensagem, 'error');
        return;
      }
      const calc = json.dados;
      this.painelInd.ultimoCalculo = calc;
      const r = calc.resumo || {};
      const itens = calc.itens || [];

      const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
      set('ind-calc-proventos', formatarMoeda(r.total_proventos));
      set('ind-calc-base-inss', formatarMoeda(r.base_inss));
      set('ind-calc-inss', `- ${formatarMoeda(r.inss_descontado)}`);
      set('ind-calc-base-irrf', formatarMoeda(r.base_irrf));
      set('ind-calc-irrf', `- ${formatarMoeda(r.irrf_descontado)}`);
      set('ind-calc-desc-lanc', `- ${formatarMoeda(r.descontos_lancados)}`);
      set('ind-calc-total-desc', `- ${formatarMoeda(r.total_descontos)}`);
      set('ind-calc-fgts', formatarMoeda(r.valor_fgts_informativo));
      set('ind-calc-liquido', formatarMoeda(r.salario_liquido));

      const codigosTributosAuto = ['501', '0501', '0502', '502', '0505', '0506', '0507'];
      const proventos = itens.filter(it => it.tipo === 'provento');
      const descontosAvulsos = itens.filter(it => it.tipo === 'desconto' && !codigosTributosAuto.includes(String(it.codigo_evento)) && !codigosTributosAuto.includes(String(it.codigo_catalogo || '')));
      set('ind-qtd-eventos', `${proventos.length + descontosAvulsos.length} evento(s)`);

      const fechada = this.painelInd.situacao === 'fechada';
      const elProv = document.getElementById('ind-lista-proventos');
      if (elProv) {
        elProv.innerHTML = proventos.map(it => {
          const idxManual = this.painelInd.eventosLancados.findIndex(e => e.codigo === it.codigo_evento && e.tipo === 'provento');
          const btnRem = (!fechada && idxManual >= 0) ? `<button type="button" class="btn-icon text-danger" title="Remover" onclick="FolhaManager.removerEventoPainel(${idxManual})">&times;</button>` : '';
          return `
            <div class="folha-evento-linha">
              <div><span style="color:#64748b; margin-right:0.5rem;">${it.codigo_evento}</span><strong>${it.descricao}</strong> <span class="text-xs text-muted">${it.referencia > 0 ? `(${it.referencia} ${it.unidade_referencia || ''})` : ''}</span></div>
              <div style="display:flex; align-items:center; gap:0.5rem;"><strong>${formatarMoeda(it.valor_total)}</strong>${btnRem}</div>
            </div>
          `;
        }).join('');
      }

      const elDesc = document.getElementById('ind-lista-descontos');
      if (elDesc) {
        elDesc.innerHTML = descontosAvulsos.length ? descontosAvulsos.map(it => {
          const idxManual = this.painelInd.eventosLancados.findIndex(e => e.codigo === it.codigo_evento && e.tipo === 'desconto');
          const btnRem = (!fechada && idxManual >= 0) ? `<button type="button" class="btn-icon text-danger" title="Remover" onclick="FolhaManager.removerEventoPainel(${idxManual})">&times;</button>` : '';
          return `
            <div class="folha-evento-linha">
              <div><span style="color:#64748b; margin-right:0.5rem;">${it.codigo_evento}</span><strong>${it.descricao}</strong> <span class="text-xs text-muted">${it.referencia > 0 ? `(${it.referencia} ${it.unidade_referencia || ''})` : ''}</span></div>
              <div style="display:flex; align-items:center; gap:0.5rem;"><strong style="color:#b91c1c;">- ${formatarMoeda(it.valor_total)}</strong>${btnRem}</div>
            </div>
          `;
        }).join('') : '<p class="text-muted" style="font-size:0.84rem; margin:0.25rem 0;">Nenhum desconto avulso — INSS e IRRF são calculados automaticamente.</p>';
      }
    } catch (e) {
      console.error('Erro ao simular painel:', e);
    }
  },

  async salvarPainelIndividual(rascunho = false) {
    if (!this.painelInd.colaboradorId) return;
    const comp = document.getElementById('ind-competencia')?.value || '2026-10';
    const tipo = document.getElementById('ind-tipo-folha')?.value || 'mensal';
    const [ano, mes] = comp.split('-').map(Number);
    const ultDia = new Date(ano, mes, 0).getDate();
    const payload = {
      colaborador_id: this.painelInd.colaboradorId,
      competencia: comp,
      tipo_folha: tipo,
      salvar_como_rascunho: rascunho,
      periodo_inicio: `${comp}-01`,
      periodo_fim: `${comp}-${String(ultDia).padStart(2, '0')}`,
      eventos: this.painelInd.eventosLancados
    };
    const url = this.painelInd.folhaId ? `${API_BASE}/folha/${this.painelInd.folhaId}` : `${API_BASE}/folha`;
    const method = this.painelInd.folhaId ? 'PUT' : 'POST';
    try {
      const resp = await fetch(url, { method, headers: getAuthHeaders(), credentials: 'include', body: JSON.stringify(payload) });
      const json = await resp.json();
      if (!resp.ok) {
        const errDet = json.erros ? Object.values(json.erros).join(' ') : '';
        exibirToast(errDet || json.mensagem || 'Erro ao salvar folha.', 'error');
        return;
      }
      exibirToast(json.mensagem || 'Folha salva e calculada!', 'success');
      await this.carregarFolhas();
      await this._carregarDadosPainel(this.painelInd.colaboradorId, json.dados);
    } catch (e) {
      exibirToast('Erro de comunicação ao salvar folha.', 'error');
    }
  },

  async aprovarDoPainel() {
    if (!this.painelInd.folhaId) return;
    const resp = await fetch(`${API_BASE}/folha/${this.painelInd.folhaId}/aprovar`, { method: 'POST', headers: getAuthHeaders(), credentials: 'include', body: JSON.stringify({}) });
    const json = await resp.json();
    if (!resp.ok) { exibirToast(json.mensagem || 'Erro ao aprovar.', 'error'); return; }
    exibirToast(json.mensagem, 'success');
    await this.carregarFolhas();
    await this._carregarDadosPainel(this.painelInd.colaboradorId, json.dados);
  },

  async fecharDoPainel() {
    if (!this.painelInd.colaboradorId) return;
    if (this.painelInd.situacao !== 'fechada') {
      await this.salvarPainelIndividual(false);
    }
    if (this.painelInd.folhaId) {
      this.solicitarFechamento(this.painelInd.folhaId);
    }
  },

  async reabrirDoPainel() {
    if (!this.painelInd.folhaId) return;
    this.solicitarReabertura(this.painelInd.folhaId);
  },

  abrirHoleriteDoPainel() {
    if (this.painelInd.folhaId) this.abrirModalHolerite(this.painelInd.folhaId, false);
  },

  baixarPdfDoPainel() {
    if (this.painelInd.folhaId) this.baixarHoleritePDF(this.painelInd.folhaId);
  },

  _baixarBlobArquivo(blob, nomeArq) {
    if (window.navigator && typeof window.navigator.msSaveOrOpenBlob === 'function') {
      window.navigator.msSaveOrOpenBlob(blob, nomeArq);
      return;
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = nomeArq;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      if (a.parentNode) a.parentNode.removeChild(a);
      URL.revokeObjectURL(url);
    }, 1500);
  },

  async baixarHoleritePDF(folhaId = null) {
    const id = folhaId || (this.folhaParaFecharOuReabrir && this.folhaParaFecharOuReabrir.id);
    if (!id) {
      exibirToast('Abra um contracheque antes de baixar o PDF A4.', 'error');
      return;
    }
    try {
      const resp = await fetch(`${API_BASE}/folha/${id}/pdf`, { headers: getAuthHeaders(), credentials: 'include' });
      const contentType = (resp.headers.get('Content-Type') || '').toLowerCase();
      if (!resp.ok || !contentType.includes('application/pdf')) {
        const err = await resp.json().catch(() => ({}));
        exibirToast(err.mensagem || `Erro ao gerar PDF do contracheque (HTTP ${resp.status}).`, 'error');
        return;
      }
      const blob = await resp.blob();
      const disp = resp.headers.get('Content-Disposition') || '';
      const match = disp.match(/filename="?([^";]+)"?/i);
      const nomeArq = match ? match[1] : `CONTRACHEQUE_${id}.pdf`;
      this._baixarBlobArquivo(blob, nomeArq);
      exibirToast('PDF A4 do contracheque baixado com sucesso!', 'success');
    } catch (e) {
      console.error('Erro ao baixar PDF A4:', e);
      exibirToast('Falha ao baixar PDF do contracheque.', 'error');
    }
  },

  async baixarHoleritesLotePDF() {
    const comp = document.getElementById('filtro-folha-competencia')?.value || '';
    const setor = document.getElementById('filtro-folha-setor')?.value || '';
    const situacao = document.getElementById('filtro-folha-situacao')?.value || '';
    const params = new URLSearchParams();
    if (comp) params.set('competencia', comp);
    if (setor) params.set('setor', setor);
    if (situacao && situacao !== 'todos') params.set('situacao', situacao);
    try {
      const resp = await fetch(`${API_BASE}/folha/holerites-lote/pdf?${params.toString()}`, { headers: getAuthHeaders(), credentials: 'include' });
      const contentType = (resp.headers.get('Content-Type') || '').toLowerCase();
      if (!resp.ok || !contentType.includes('application/pdf')) {
        const err = await resp.json().catch(() => ({}));
        exibirToast(err.mensagem || `Nenhum contracheque encontrado para o lote (HTTP ${resp.status}).`, 'error');
        return;
      }
      const blob = await resp.blob();
      const disp = resp.headers.get('Content-Disposition') || '';
      const match = disp.match(/filename="?([^";]+)"?/i);
      const nomeArq = match ? match[1] : `CONTRACHEQUES_LOTE_${comp || 'GERAL'}.pdf`;
      this._baixarBlobArquivo(blob, nomeArq);
      exibirToast('PDF A4 em lote baixado com sucesso!', 'success');
    } catch (e) {
      console.error('Erro ao baixar PDF A4 em lote:', e);
      exibirToast('Falha ao gerar PDF em lote.', 'error');
    }
  },

  // ── Emissão de Holerites em Lote (PDF / Impressão) ──────────────────────
  async emitirHoleritesLote() {
    const comp = document.getElementById('filtro-folha-competencia')?.value || '';
    try {
      const params = new URLSearchParams();
      if (comp) params.set('competencia', comp);
      const resp = await fetch(`${API_BASE}/folha/holerites-lote?${params.toString()}`, { headers: getAuthHeaders(), credentials: 'include' });
      const json = await resp.json();
      const lista = json.dados || [];
      if (!lista.length) {
        exibirToast('Nenhum holerite encontrado para os filtros atuais.', 'error');
        return;
      }
      const win = window.open('', '_blank');
      if (!win) {
        exibirToast('Permita pop-ups para visualizar o lote de holerites.', 'error');
        return;
      }
      const paginas = lista.map(f => {
        const cpfStr = formatarCpf(f.colaborador_cpf || '');
        const cpfMask = cpfStr.length === 14 ? `***.${cpfStr.slice(4, 11)}-**` : cpfStr;
        const linhas = (f.itens || []).map(it => `
          <tr>
            <td>${it.codigo_evento}</td>
            <td>${it.descricao}</td>
            <td style="text-align:center;">${it.referencia > 0 ? it.referencia + ' ' + (it.unidade_referencia || '') : '--'}</td>
            <td style="text-align:right;">${it.tipo === 'provento' ? formatarMoeda(it.valor_total) : ''}</td>
            <td style="text-align:right;">${it.tipo === 'desconto' ? formatarMoeda(it.valor_total) : ''}</td>
          </tr>
        `).join('');
        return `
          <div style="page-break-after: always; border:1px solid #334155; padding:18px; margin-bottom:24px; font-family:Arial,sans-serif; font-size:12px;">
            <div style="display:flex; justify-content:space-between; border-bottom:2px solid #0f172a; padding-bottom:8px; margin-bottom:10px;">
              <div><strong>USINA CENTRAL DE BIOENERGIA S.A.</strong><br>CNPJ: 54.321.987/0001-00</div>
              <div style="text-align:right;"><strong>RECIBO DE PAGAMENTO (${(f.tipo_folha || 'mensal').toUpperCase()})</strong><br>Competência: ${f.competencia}</div>
            </div>
            <div style="display:grid; grid-template-columns:1fr 2fr 1fr; gap:6px; margin-bottom:10px; background:#f8fafc; padding:8px;">
              <div><strong>Matrícula:</strong> ${f.colaborador_matricula}</div>
              <div><strong>Nome:</strong> ${f.colaborador_nome}</div>
              <div><strong>CPF:</strong> ${cpfMask}</div>
              <div><strong>Cargo:</strong> ${f.colaborador_cargo}</div>
              <div><strong>Setor:</strong> ${f.colaborador_setor}</div>
              <div><strong>Admissão:</strong> ${formatarDataBR(f.colaborador_data_admissao)}</div>
            </div>
            <table style="width:100%; border-collapse:collapse; margin-bottom:10px;" border="1" cellpadding="4">
              <thead><tr><th>Cód</th><th>Descrição</th><th>Ref.</th><th>Proventos</th><th>Descontos</th></tr></thead>
              <tbody>${linhas}</tbody>
            </table>
            <div style="display:flex; justify-content:space-between; font-weight:bold; background:#f1f5f9; padding:8px;">
              <span>Proventos: ${formatarMoeda(f.total_proventos)}</span>
              <span>Descontos: ${formatarMoeda(f.total_descontos)}</span>
              <span>Líquido: ${formatarMoeda(f.salario_liquido)}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:11px; margin-top:8px;">
              <span>Base INSS: ${formatarMoeda(f.base_inss)}</span>
              <span>Base FGTS: ${formatarMoeda(f.base_fgts)}</span>
              <span>FGTS Mês: ${formatarMoeda(f.valor_fgts_informativo)}</span>
              <span>Base IRRF: ${formatarMoeda(f.base_irrf)}</span>
            </div>
          </div>
        `;
      }).join('');
      win.document.write(`<html><head><title>Holerites em Lote - ${comp || 'Todos'}</title></head><body>${paginas}<script>window.print();<\/script></body></html>`);
      win.document.close();
    } catch (e) {
      exibirToast('Erro ao gerar holerites em lote.', 'error');
    }
  },

  // ── Relatórios Gerenciais & Financeiros ─────────────────────────────────
  ultimoRelatorio: null,

  async carregarRelatorios() {
    const compInicio = document.getElementById('rel-folha-inicio')?.value || '';
    const compFim = document.getElementById('rel-folha-fim')?.value || '';
    const comp = document.getElementById('rel-folha-competencia')?.value || '';
    const setor = document.getElementById('rel-folha-setor')?.value || '';
    const params = new URLSearchParams();
    if (compInicio) params.set('competencia_inicio', compInicio);
    if (compFim) params.set('competencia_fim', compFim);
    if (comp) params.set('competencia', comp);
    if (setor) params.set('setor', setor);
    try {
      const resp = await fetch(`${API_BASE}/folha/relatorios?${params.toString()}`, { headers: getAuthHeaders(), credentials: 'include' });
      const json = await resp.json();
      const rel = json.dados || {};
      this.ultimoRelatorio = rel;
      const rf = rel.resumo_financeiro || {};
      const ger = rel.gerencial || {};
      const fin = rel.financeiro || {};
      const he = ger.horas_extras || {};
      const naoFech = ger.folhas_nao_fechadas || {};
      const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

      set('rel-kpi-colabs', String(ger.numero_colaboradores_ativos ?? rf.qtd_colaboradores ?? 0));
      set('rel-kpi-sal-medio', formatarMoeda(ger.salario_medio || 0));
      set('rel-kpi-he', `${Number(he.total_horas || 0)}h (${formatarMoeda(he.valor_total || 0)})`);
      set('rel-kpi-nao-fechadas', String(naoFech.quantidade ?? rf.folhas_abertas ?? 0));
      set('rel-kpi-bruto', formatarMoeda(rf.total_bruto || 0));
      set('rel-kpi-descontos', formatarMoeda(rf.total_descontos || 0));
      set('rel-kpi-liquido', formatarMoeda(rf.total_liquido || 0));
      set('rel-kpi-tributos', `${formatarMoeda(rf.total_inss || 0)} / ${formatarMoeda(rf.total_irrf || 0)} / ${formatarMoeda(rf.total_fgts || 0)}`);
      set('rel-kpi-encargos', formatarMoeda(rf.encargos_patronais || 0));
      set('rel-kpi-custo', formatarMoeda(rf.custo_total_empresa || 0));

      const depts = rel.por_departamento || [];
      const maxCusto = Math.max(...depts.map(d => d.custo_total), 1);
      const chartDept = document.getElementById('rel-chart-departamentos');
      if (chartDept) {
        chartDept.innerHTML = depts.length ? depts.map(d => `
          <div>
            <div style="display:flex; justify-content:space-between; font-size:0.8rem;"><span>${d.grupo}</span><strong>${formatarMoeda(d.custo_total)}</strong></div>
            <div style="background:#e2e8f0; border-radius:4px; height:8px; overflow:hidden;"><div style="background:#16a34a; height:100%; width:${Math.round((d.custo_total / maxCusto) * 100)}%;"></div></div>
          </div>
        `).join('') : '<span class="text-muted">Sem dados para os filtros informados.</span>';
      }

      const evs = rel.evolucao_mensal || [];
      const maxEv = Math.max(...evs.map(e => e.bruto), 1);
      const chartEv = document.getElementById('rel-chart-evolucao');
      if (chartEv) {
        chartEv.innerHTML = evs.length ? evs.map(e => `
          <div>
            <div style="display:flex; justify-content:space-between; font-size:0.8rem;"><span>${e.competencia} (${e.qtd})</span><strong>Bruto: ${formatarMoeda(e.bruto)} | Líq: ${formatarMoeda(e.liquido)}</strong></div>
            <div style="background:#e2e8f0; border-radius:4px; height:8px; overflow:hidden;"><div style="background:#2563eb; height:100%; width:${Math.round((e.bruto / maxEv) * 100)}%;"></div></div>
          </div>
        `).join('') : '<span class="text-muted">Sem competências processadas.</span>';
      }

      const tbody = document.getElementById('rel-tabela-departamentos');
      if (tbody) {
        tbody.innerHTML = depts.map(d => `
          <tr>
            <td><strong>${d.grupo}</strong></td>
            <td>${d.qtd_folhas}</td>
            <td>${formatarMoeda(d.bruto)}</td>
            <td>${formatarMoeda(d.descontos)}</td>
            <td>${formatarMoeda(d.liquido)}</td>
            <td>${formatarMoeda(d.fgts)}</td>
            <td>${formatarMoeda(d.encargos)}</td>
            <td><strong>${formatarMoeda(d.custo_total)}</strong></td>
          </tr>
        `).join('') || '<tr><td colspan="8" class="text-center text-muted">Nenhum registro encontrado.</td></tr>';
      }

      const tbodyEv = document.getElementById('rel-tabela-eventos');
      if (tbodyEv) {
        const evMais = ger.eventos_mais_usados || [];
        tbodyEv.innerHTML = evMais.slice(0, 10).map(e => `
          <tr>
            <td><strong>${e.codigo}</strong></td>
            <td>${e.descricao}</td>
            <td>${e.tipo}</td>
            <td>${e.qtd_lancamentos}</td>
            <td>${formatarMoeda(e.valor_total)}</td>
          </tr>
        `).join('') || '<tr><td colspan="5" class="text-center text-muted">Sem eventos no período.</td></tr>';
      }

      const tbodyNF = document.getElementById('rel-tabela-nao-fechadas');
      if (tbodyNF) {
        const nfLista = naoFech.lista || [];
        tbodyNF.innerHTML = nfLista.map(f => `
          <tr>
            <td>${f.colaborador_nome}</td>
            <td>${f.competencia}</td>
            <td><span class="badge badge-dep">${f.situacao}</span></td>
            <td>${formatarMoeda(f.salario_liquido)}</td>
          </tr>
        `).join('') || '<tr><td colspan="4" class="text-center text-muted">Todas as folhas do período estão fechadas.</td></tr>';
      }

      const tbodyFinMes = document.getElementById('rel-tabela-financeiro-mes');
      if (tbodyFinMes) {
        const tMes = fin.totais_por_mes || [];
        tbodyFinMes.innerHTML = tMes.map(m => `
          <tr>
            <td><strong>${m.competencia}</strong></td>
            <td>${m.qtd}</td>
            <td>${formatarMoeda(m.bruto)}</td>
            <td>${formatarMoeda(m.liquido)}</td>
            <td>${formatarMoeda(m.encargos_empresa)}</td>
            <td><strong>${formatarMoeda(m.custo_total)}</strong></td>
          </tr>
        `).join('') || '<tr><td colspan="6" class="text-center text-muted">Sem dados financeiros no período.</td></tr>';
      }

      const boxRec = document.getElementById('rel-valores-recolher');
      if (boxRec) {
        const enc = fin.encargos_empresa || {};
        const rec = fin.valores_a_recolher || {};
        boxRec.innerHTML = `
          <div style="display:flex; justify-content:space-between;"><span>INSS Segurados (retido):</span><strong>${formatarMoeda(rec.inss_segurados || 0)}</strong></div>
          <div style="display:flex; justify-content:space-between;"><span>INSS Patronal (20%) + RAT (2%) + Terceiros (5,8%):</span><strong>${formatarMoeda(rec.inss_patronal_e_terceiros || 0)}</strong></div>
          <div style="display:flex; justify-content:space-between;"><span>Total Guia INSS (GPS/DARF):</span><strong>${formatarMoeda(rec.inss_total_recolher || 0)}</strong></div>
          <div style="display:flex; justify-content:space-between;"><span>IRRF a Recolher (DARF):</span><strong>${formatarMoeda(rec.irrf_recolher || 0)}</strong></div>
          <div style="display:flex; justify-content:space-between;"><span>FGTS a Recolher (GFIP/FGTS Digital):</span><strong>${formatarMoeda(rec.fgts_recolher || 0)}</strong></div>
          <div style="display:flex; justify-content:space-between; border-top:1px solid #cbd5e1; padding-top:0.4rem;"><span><strong>Total Encargos da Empresa (Patr. + FGTS):</strong></span><strong>${formatarMoeda(enc.total_encargos_empresa || 0)}</strong></div>
          <div style="display:flex; justify-content:space-between;"><span><strong>Total Geral de Tributos a Recolher:</strong></span><strong style="color:#166534;">${formatarMoeda(rec.total_a_recolher || 0)}</strong></div>
        `;
      }
    } catch (e) {
      exibirToast('Erro ao carregar relatórios da folha.', 'error');
    }
  },

  exportarRelatorioGerencialCSV() {
    if (!this.ultimoRelatorio) {
      exibirToast('Gere o relatório antes de exportar.', 'error');
      return;
    }
    const ger = this.ultimoRelatorio.gerencial || {};
    const depts = ger.custo_por_departamento || this.ultimoRelatorio.por_departamento || [];
    const evs = ger.eventos_mais_usados || [];
    const linhas = [
      ['RELATORIO GERENCIAL DA FOLHA'],
      ['Colaboradores Ativos', ger.numero_colaboradores_ativos || 0],
      ['Salario Medio', ger.salario_medio || 0],
      ['Horas Extras (Qtd / Horas / Valor)', ger.horas_extras?.qtd_lancamentos || 0, ger.horas_extras?.total_horas || 0, ger.horas_extras?.valor_total || 0],
      ['Folhas Nao Fechadas', ger.folhas_nao_fechadas?.quantidade || 0],
      [],
      ['CUSTO POR DEPARTAMENTO', 'Folhas', 'Bruto', 'Descontos', 'Liquido', 'FGTS', 'Encargos', 'Custo Total'],
      ...depts.map(d => [d.grupo, d.qtd_folhas, d.bruto, d.descontos, d.liquido, d.fgts, d.encargos, d.custo_total]),
      [],
      ['EVENTOS MAIS USADOS (Codigo)', 'Descricao', 'Tipo', 'Qtd Lancamentos', 'Valor Total'],
      ...evs.map(e => [e.codigo, e.descricao, e.tipo, e.qtd_lancamentos, e.valor_total])
    ];
    const csv = '\uFEFF' + linhas.map(l => l.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(';')).join('\n');
    this._baixarBlobArquivo(new Blob([csv], { type: 'text/csv;charset=utf-8;' }), `relatorio_gerencial_${new Date().toISOString().slice(0, 10)}.csv`);
    exibirToast('Relatório Gerencial CSV exportado!', 'success');
  },

  exportarRelatorioFinanceiroCSV() {
    if (!this.ultimoRelatorio) {
      exibirToast('Gere o relatório antes de exportar.', 'error');
      return;
    }
    const fin = this.ultimoRelatorio.financeiro || {};
    const tMes = fin.totais_por_mes || [];
    const rec = fin.valores_a_recolher || {};
    const enc = fin.encargos_empresa || {};
    const linhas = [
      ['RELATORIO FINANCEIRO DA FOLHA'],
      ['Competencia', 'Qtd Folhas', 'Bruto', 'Descontos', 'Liquido', 'INSS Segurados', 'IRRF', 'FGTS', 'Encargos Empresa', 'Custo Total'],
      ...tMes.map(m => [m.competencia, m.qtd, m.bruto, m.descontos, m.liquido, m.inss_segurados, m.irrf, m.fgts, m.encargos_empresa, m.custo_total]),
      [],
      ['ENCARGOS E VALORES A RECOLHER', 'Valor (R$)'],
      ['INSS Segurados', rec.inss_segurados || 0],
      ['INSS Patronal + RAT + Terceiros', rec.inss_patronal_e_terceiros || 0],
      ['INSS Total a Recolher', rec.inss_total_recolher || 0],
      ['IRRF a Recolher', rec.irrf_recolher || 0],
      ['FGTS a Recolher', rec.fgts_recolher || 0],
      ['Total Encargos da Empresa', enc.total_encargos_empresa || 0],
      ['Total Geral a Recolher', rec.total_a_recolher || 0],
    ];
    const csv = '\uFEFF' + linhas.map(l => l.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(';')).join('\n');
    this._baixarBlobArquivo(new Blob([csv], { type: 'text/csv;charset=utf-8;' }), `relatorio_financeiro_${new Date().toISOString().slice(0, 10)}.csv`);
    exibirToast('Relatório Financeiro CSV exportado!', 'success');
  },

  exportarRelatorioExcel() {
    const depts = (this.ultimoRelatorio && this.ultimoRelatorio.por_departamento) || [];
    if (!depts.length) {
      exibirToast('Gere o relatório antes de exportar para Excel.', 'error');
      return;
    }
    const linhas = [
      ['Departamento', 'Folhas', 'Bruto', 'Descontos', 'Liquido', 'FGTS', 'Encargos Patronais', 'Custo Total'],
      ...depts.map(d => [d.grupo, d.qtd_folhas, d.bruto, d.descontos, d.liquido, d.fgts, d.encargos, d.custo_total])
    ];
    const csv = '\uFEFF' + linhas.map(l => l.map(v => `"${String(v).replace(/"/g, '""')}"`).join(';')).join('\n');
    const blob = new Blob([csv], { type: 'application/vnd.ms-excel;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `relatorio_folha_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    exibirToast('Relatório exportado para Excel/CSV com sucesso!', 'success');
  },

  configurarEventosHolerite() {
    const btnFecharX = document.getElementById('btn-fechar-holerite');
    const btnFecharFooter = document.getElementById('btn-fechar-holerite-footer');
    const btnImprimir = document.getElementById('btn-imprimir-holerite');
    const btnFecharAcao = document.getElementById('btn-fechar-folha-acao');
    const btnReabrirAcao = document.getElementById('btn-reabrir-folha-acao');

    const fecharModal = () => document.getElementById('modal-holerite').classList.add('hidden');

    if (btnFecharX) btnFecharX.addEventListener('click', fecharModal);
    if (btnFecharFooter) btnFecharFooter.addEventListener('click', fecharModal);

    if (btnImprimir) {
      btnImprimir.addEventListener('click', () => {
        window.print();
      });
    }

    if (btnFecharAcao) {
      btnFecharAcao.addEventListener('click', () => {
        if (this.folhaParaFecharOuReabrir) {
          this.solicitarFechamento(this.folhaParaFecharOuReabrir.id);
        }
      });
    }

    if (btnReabrirAcao) {
      btnReabrirAcao.addEventListener('click', () => {
        if (this.folhaParaFecharOuReabrir) {
          this.solicitarReabertura(this.folhaParaFecharOuReabrir.id);
        }
      });
    }

    // Modal de fechamento
    document.getElementById('btn-cancelar-fechamento').addEventListener('click', () => {
      document.getElementById('modal-fechar-folha-confirm').classList.add('hidden');
    });
    document.getElementById('btn-cancelar-fechamento-topo').addEventListener('click', () => {
      document.getElementById('modal-fechar-folha-confirm').classList.add('hidden');
    });
    document.getElementById('btn-confirmar-fechamento').addEventListener('click', () => {
      this.executarFechamento();
    });

    // Modal de reabertura
    document.getElementById('btn-cancelar-reabertura').addEventListener('click', () => {
      document.getElementById('modal-reabrir-folha-confirm').classList.add('hidden');
    });
    document.getElementById('btn-cancelar-reabertura-topo').addEventListener('click', () => {
      document.getElementById('modal-reabrir-folha-confirm').classList.add('hidden');
    });
    document.getElementById('btn-confirmar-reabertura').addEventListener('click', () => {
      this.executarReabertura();
    });

    // Modal de parâmetros
    document.getElementById('btn-fechar-parametros').addEventListener('click', () => {
      document.getElementById('modal-parametros-folha').classList.add('hidden');
    });
    document.getElementById('btn-fechar-parametros-footer').addEventListener('click', () => {
      document.getElementById('modal-parametros-folha').classList.add('hidden');
    });
  },

  solicitarFechamento(folhaId) {
    const f = this.folhas.find(item => String(item.id) === String(folhaId)) || this.folhaParaFecharOuReabrir;
    if (!f) return;
    this.folhaParaFecharOuReabrir = f;

    const elInfo = document.getElementById('fechar-folha-info');
    if (elInfo) {
      elInfo.innerHTML = `
        <strong>Colaborador:</strong> ${f.colaborador_nome || ''} (Matrícula: ${f.colaborador_matricula || ''})<br>
        <strong>Competência:</strong> ${f.competencia} &bull; <strong>Líquido:</strong> ${formatarMoeda(f.salario_liquido)}
      `;
    }
    document.getElementById('modal-fechar-folha-confirm').classList.remove('hidden');
  },

  async executarFechamento() {
    if (!this.folhaParaFecharOuReabrir) return;
    const folhaId = this.folhaParaFecharOuReabrir.id;
    try {
      const resp = await fetch(`${API_BASE}/folha/${folhaId}/fechar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Falha ao fechar folha.', 'error');
        return;
      }
      exibirToast(`Folha #${folhaId} homologada e fechada com sucesso!`, 'success');
      document.getElementById('modal-fechar-folha-confirm').classList.add('hidden');
      document.getElementById('modal-holerite').classList.add('hidden');
      await this.carregarFolhas();
      if (this.painelInd && Number(this.painelInd.folhaId) === Number(folhaId) && json.dados) {
        await this._carregarDadosPainel(this.painelInd.colaboradorId, json.dados);
      }
    } catch (e) {
      console.error('Erro ao fechar folha:', e);
      exibirToast('Erro de comunicação ao fechar folha.', 'error');
    }
  },

  solicitarReabertura(folhaId) {
    const f = this.folhas.find(item => String(item.id) === String(folhaId)) || this.folhaParaFecharOuReabrir;
    if (!f) return;
    this.folhaParaFecharOuReabrir = f;
    document.getElementById('reabrir-folha-motivo').value = '';
    document.getElementById('erro-reabrir-folha-motivo').classList.add('hidden');
    document.getElementById('modal-reabrir-folha-confirm').classList.remove('hidden');
  },

  async executarReabertura() {
    if (!this.folhaParaFecharOuReabrir) return;
    const folhaId = this.folhaParaFecharOuReabrir.id;
    const motivo = document.getElementById('reabrir-folha-motivo').value.trim();
    const erroEl = document.getElementById('erro-reabrir-folha-motivo');

    if (!motivo || motivo.length < 5) {
      erroEl.textContent = 'Informe uma justificativa válida com no mínimo 5 caracteres.';
      erroEl.classList.remove('hidden');
      return;
    }

    const apagar = Boolean(document.getElementById('reabrir-apagar-folha')?.checked);

    try {
      const resp = await fetch(`${API_BASE}/folha/${folhaId}/reabrir`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ motivo, apagar_para_relancar: apagar })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Falha ao reabrir folha.', 'error');
        return;
      }
      exibirToast(json.mensagem || `Folha #${folhaId} reaberta!`, 'success');
      document.getElementById('modal-reabrir-folha-confirm').classList.add('hidden');
      document.getElementById('modal-holerite').classList.add('hidden');
      await this.carregarFolhas();
      if (this.painelInd && Number(this.painelInd.folhaId) === Number(folhaId)) {
        if (apagar) {
          await this.selecionarColaboradorPainel(this.painelInd.colaboradorId);
        } else if (json.dados) {
          await this._carregarDadosPainel(this.painelInd.colaboradorId, json.dados);
        }
      }
    } catch (e) {
      console.error('Erro ao reabrir folha:', e);
      exibirToast('Erro de comunicação ao reabrir folha.', 'error');
    }
  },

  async excluirFolha(folhaId) {
    if (!confirm(`Deseja realmente cancelar e excluir a folha #${folhaId}? Esta ação não pode ser desfeita.`)) {
      return;
    }
    try {
      const resp = await fetch(`${API_BASE}/folha/${folhaId}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Não foi possível cancelar a folha.', 'error');
        return;
      }
      exibirToast(`Folha #${folhaId} cancelada com sucesso.`, 'success');
      await this.carregarFolhas();
    } catch (e) {
      console.error('Erro ao cancelar folha:', e);
      exibirToast('Erro ao cancelar folha.', 'error');
    }
  },

  async abrirModalParametros() {
    await this.carregarParametros();
    const p = this.parametrosVigentes;
    if (!p) {
      exibirToast('Parâmetros indisponíveis no momento.', 'warning');
      return;
    }

    document.getElementById('param-codigo').value = p.codigo || '';
    document.getElementById('param-descricao').value = p.descricao || '';
    document.getElementById('param-divisor').value = p.horas_mensais_padrao || 220;
    document.getElementById('param-dias').value = p.dias_mes_padrao || 30;
    document.getElementById('param-he50').value = p.percentual_he_padrao || 50;
    document.getElementById('param-he100').value = p.percentual_he_extra || 100;
    document.getElementById('param-noturno').value = p.percentual_adicional_noturno || 20;
    document.getElementById('param-teto-inss').value = p.teto_inss || 8157.41;
    document.getElementById('param-deducao-dep').value = p.deducao_dependente_irrf || 189.59;

    document.getElementById('modal-parametros-folha').classList.remove('hidden');
  }
};

// Inicialização

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
    this.configurarCollapseSidebar();
    this.configurarMenuMobile();
    this.configurarNotificacoesHeader();
    this.configurarEventosModais();
    this.configurarSSTTabs();
    this.configurarBotoesAcao();
  },

  configurarCollapseSidebar() {
    const sidebar = document.getElementById('platform-sidebar');
    const btnCollapse = document.getElementById('btn-collapse-sidebar');
    if (!sidebar || !btnCollapse) return;

    if (localStorage.getItem('rh2_sidebar_collapsed') === '1') {
      sidebar.classList.add('collapsed');
    }

    btnCollapse.addEventListener('click', () => {
      sidebar.classList.toggle('collapsed');
      const collapsed = sidebar.classList.contains('collapsed');
      localStorage.setItem('rh2_sidebar_collapsed', collapsed ? '1' : '0');
    });
  },

  atualizarBreadcrumb(viewName) {
    const map = {
      'dashboard': ['Estratégico', 'Dashboard & BI'],
      'pendencias': ['Estratégico', 'Central de Pendências'],
      'colaboradores': ['Pessoas & Admissão', 'Funcionários'],
      'admissoes': ['Pessoas & Admissão', 'Admissões & Contratos'],
      'beneficios': ['Pessoas & Admissão', 'Benefícios & Descontos'],
      'ponto': ['Jornada & Desligamento', 'Controle de Ponto'],
      'ferias': ['Jornada & Desligamento', 'Férias & Abono'],
      'afastamentos': ['Jornada & Desligamento', 'Afastamentos'],
      'rescisoes': ['Jornada & Desligamento', 'Rescisões'],
      'folha': ['Folha & Remuneração', 'Folha de Pagamento'],
      'integracoes': ['Folha & Remuneração', 'Bancos / CNAB 240'],
      'relatorios': ['Compliance & Relatórios', 'Relatórios Gerenciais'],
      'documentos': ['Compliance & Relatórios', 'Documentos Trabalhistas'],
      'sst': ['Compliance & Relatórios', 'SST & Medicina'],
      'esocial': ['Compliance & Relatórios', 'eSocial & Obrigações'],
      'auditoria': ['Governança & Sistema', 'Auditoria & Logs'],
      'multiempresa': ['Governança & Sistema', 'Multiempresa'],
      'configuracoes': ['Governança & Sistema', 'Configurações & Parâmetros'],
      'portal-colaborador': ['Portais Enterprise', 'Portal do Colaborador'],
      'portal-gestor': ['Portais Enterprise', 'Portal do Gestor']
    };
    const [cat, pag] = map[viewName] || ['Módulo', viewName];
    const elCat = document.getElementById('breadcrumb-categoria');
    const elPag = document.getElementById('breadcrumb-pagina');
    if (elCat) elCat.textContent = cat;
    if (elPag) elPag.textContent = pag;
  },

  abrirDrawerMobile() {
    const sidebar = document.getElementById('platform-sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const btnHamb = document.getElementById('btn-mobile-menu');
    if (sidebar) sidebar.classList.add('sidebar-open');
    if (backdrop) backdrop.classList.remove('hidden');
    if (btnHamb) btnHamb.setAttribute('aria-expanded', 'true');
  },

  fecharDrawerMobile() {
    const sidebar = document.getElementById('platform-sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const btnHamb = document.getElementById('btn-mobile-menu');
    if (sidebar) sidebar.classList.remove('sidebar-open');
    if (backdrop) backdrop.classList.add('hidden');
    if (btnHamb) btnHamb.setAttribute('aria-expanded', 'false');
  },

  configurarMenuMobile() {
    const btnHamb = document.getElementById('btn-mobile-menu');
    const btnClose = document.getElementById('btn-close-sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const btnBnavMenu = document.getElementById('btn-bnav-menu');

    if (btnHamb) {
      btnHamb.addEventListener('click', () => {
        const sidebar = document.getElementById('platform-sidebar');
        if (sidebar && sidebar.classList.contains('sidebar-open')) {
          this.fecharDrawerMobile();
        } else {
          this.abrirDrawerMobile();
        }
      });
    }
    if (btnClose) {
      btnClose.addEventListener('click', () => this.fecharDrawerMobile());
    }
    if (backdrop) {
      backdrop.addEventListener('click', () => this.fecharDrawerMobile());
    }
    if (btnBnavMenu) {
      btnBnavMenu.addEventListener('click', () => this.abrirDrawerMobile());
    }

    // Botões de navegação inferior mobile
    document.querySelectorAll('.bottom-nav-item[data-view]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const viewName = btn.getAttribute('data-view');
        if (viewName) {
          this.navegarPara(viewName);
        }
      });
    });
  },

  configurarNotificacoesHeader() {
    const btnBell = document.getElementById('btn-header-notificacoes');
    const dropdown = document.getElementById('header-notif-dropdown');
    const btnIrCentral = document.getElementById('btn-ir-central-pendencias');

    if (btnBell && dropdown) {
      btnBell.addEventListener('click', async (e) => {
        e.stopPropagation();
        const isHidden = dropdown.classList.contains('hidden');
        if (isHidden) {
          dropdown.classList.remove('hidden');
          await this.carregarPreviewNotificacoes();
        } else {
          dropdown.classList.add('hidden');
        }
      });

      document.addEventListener('click', (e) => {
        const wrapper = document.getElementById('header-notif-wrapper');
        if (wrapper && !wrapper.contains(e.target)) {
          dropdown.classList.add('hidden');
        }
      });
    }

    if (btnIrCentral) {
      btnIrCentral.addEventListener('click', () => {
        if (dropdown) dropdown.classList.add('hidden');
        this.navegarPara('pendencias');
      });
    }
  },

  async carregarPreviewNotificacoes() {
    const listEl = document.getElementById('notif-dropdown-list');
    const countLabel = document.getElementById('notif-dropdown-count-label');
    if (!listEl) return;

    try {
      const resp = await fetch(`${API_BASE}/pendencias?status=pendente`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (!resp.ok) return;
      const json = await resp.json();
      const pendencias = json.dados || [];
      this.atualizarBadgesPendencias(pendencias.length);
      if (countLabel) countLabel.textContent = `${pendencias.length} abertas`;

      if (pendencias.length === 0) {
        listEl.innerHTML = '<div class="notif-empty">Nenhuma pendência operacional em aberto.</div>';
        return;
      }

      listEl.innerHTML = '';
      pendencias.slice(0, 5).forEach(p => {
        const sev = String(p.severidade || 'media').toUpperCase();
        const item = document.createElement('div');
        item.className = 'notif-item';
        item.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong style="color:var(--inst-navy);">${p.titulo}</strong>
            <span class="badge-severidade-${sev.toLowerCase()}">${sev}</span>
          </div>
          <span class="text-xs text-muted">${p.modulo || p.tipo_pendencia} &bull; Prazo: ${p.prazo_limite || 'Imediato'}</span>
        `;
        item.addEventListener('click', () => {
          document.getElementById('header-notif-dropdown')?.classList.add('hidden');
          this.navegarPara('pendencias');
        });
        listEl.appendChild(item);
      });
    } catch (e) {
      console.warn('Erro ao carregar preview de notificações:', e);
    }
  },

  atualizarBadgesPendencias(qtd) {
    const n = Number(qtd || 0);
    ['badge-pendencias-count', 'header-notif-badge', 'bnav-badge-pendencias'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = n;
    });
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
    this.fecharDrawerMobile();
    this.atualizarBreadcrumb(viewName);

    // Atualiza classe active nos botões da sidebar
    document.querySelectorAll('.sidebar-btn').forEach(b => {
      if (b.getAttribute('data-view') === viewName) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });

    // Atualiza classe active na barra inferior mobile
    document.querySelectorAll('.bottom-nav-item[data-view]').forEach(b => {
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
      'view-modulo-beneficios',
      'view-modulo-ponto',
      'view-modulo-ferias',
      'view-modulo-afastamentos',
      'view-modulo-folha',
      'view-modulo-rescisoes',
      'view-modulo-relatorios',
      'view-modulo-documentos',
      'view-modulo-sst',
      'view-modulo-esocial',
      'view-modulo-integracoes',
      'view-modulo-auditoria',
      'view-modulo-multiempresa',
      'view-modulo-configuracoes',
      'view-modulo-portal-colaborador',
      'view-modulo-portal-gestor'
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
      else if (viewName === 'beneficios') await this.carregarBeneficiosCatalogo();
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
      else if (viewName === 'documentos') await this.carregarControleDocumentacao();
      else if (viewName === 'integracoes') { }
      else if (viewName === 'auditoria') await this.carregarAuditoria();
      else if (viewName === 'multiempresa') await this.carregarMultiempresa();
      else if (viewName === 'portal-colaborador') await this.carregarPortalColaborador();
      else if (viewName === 'portal-gestor') await this.carregarPortalGestor();
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
  // DASHBOARD & BI (RF-181 A RF-190) — CARDS FINANCEIROS E GRÁFICOS
  // --------------------------------------------------------------------------
  formatarMoedaBRL(val) {
    return Number(val || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  },

  async carregarDashboard() {
    try {
      const resp = await fetch(`${API_BASE}/bi/indicadores`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      if (resp.ok) {
        const json = await resp.json();
        const d = json.dados || {};
        const ativos = d.total_colaboradores_ativos ?? d.efetivo?.ativos ?? 0;
        const turnover = d.taxa_turnover ?? d.turnover?.taxa_percentual ?? 0;
        const absenteismo = d.taxa_absenteismo ?? d.absenteismo?.taxa_percentual ?? 0;
        const pendAbertas = d.pendencias_abertas ?? d.central_pendencias?.abertas ?? 0;
        const pendCriticas = d.pendencias_criticas ?? d.central_pendencias?.criticas ?? 0;

        const elAtivos = document.getElementById('kpi-total-ativos');
        const elTurnover = document.getElementById('kpi-turnover');
        const elAbsenteismo = document.getElementById('kpi-absenteismo');
        const elPendAbertas = document.getElementById('kpi-pendencias-abertas');
        const elPendCriticas = document.getElementById('kpi-pendencias-criticas');

        if (elAtivos) elAtivos.textContent = ativos;
        if (elTurnover) elTurnover.textContent = `${Number(turnover).toFixed(2)}%`;
        if (elAbsenteismo) elAbsenteismo.textContent = `${Number(absenteismo).toFixed(2)}%`;
        if (elPendAbertas) elPendAbertas.textContent = pendAbertas;
        if (elPendCriticas) elPendCriticas.textContent = `${pendCriticas} críticas`;

        this.atualizarBadgesPendencias(pendAbertas);

        // Cards Financeiros
        const folha = d.folha || {};
        const prov = Number(folha.prov || d.massa_salarial_ativa || 0);
        const liq = Number(folha.liq || prov * 0.84);
        const fgts = Number(folha.fgts || prov * 0.08);
        const inss = Number(folha.inss || prov * 0.095);
        const irrf = Number(folha.irrf || Math.max(0, prov - liq - inss));
        const descTot = Number(folha.desc_tot || (inss + irrf));

        const elFinComp = document.getElementById('kpi-fin-competencia');
        const elFinProv = document.getElementById('kpi-fin-proventos');
        const elFinLiq = document.getElementById('kpi-fin-liquido');
        const elFinFgts = document.getElementById('kpi-fin-fgts');
        const elFinDesc = document.getElementById('kpi-fin-descontos');

        if (elFinComp) elFinComp.textContent = `Comp. ${folha.competencia || '2026'}`;
        if (elFinProv) elFinProv.textContent = this.formatarMoedaBRL(prov);
        if (elFinLiq) elFinLiq.textContent = this.formatarMoedaBRL(liq);
        if (elFinFgts) elFinFgts.textContent = this.formatarMoedaBRL(fgts);
        if (elFinDesc) elFinDesc.textContent = this.formatarMoedaBRL(descTot);

        // Gráfico 1: Composição Financeira da Folha
        const baseTotal = Math.max(1, liq + inss + irrf + fgts);
        const pLiq = Math.round((liq / baseTotal) * 100);
        const pInss = Math.round((inss / baseTotal) * 100);
        const pIrrf = Math.round((irrf / baseTotal) * 100);
        const pFgts = Math.max(1, 100 - pLiq - pInss - pIrrf);

        const setBar = (segId, fillId, valId, valor, pct) => {
          const seg = document.getElementById(segId);
          const fill = document.getElementById(fillId);
          const val = document.getElementById(valId);
          if (seg) seg.style.width = `${Math.max(2, pct)}%`;
          if (fill) fill.style.width = `${Math.min(100, Math.max(4, pct))}%`;
          if (val) val.textContent = `${this.formatarMoedaBRL(valor)} (${pct}%)`;
        };

        setBar('seg-bar-liquido', 'chart-fill-liquido', 'chart-val-liquido', liq, pLiq);
        setBar('seg-bar-inss', 'chart-fill-inss', 'chart-val-inss', inss, pInss);
        setBar('seg-bar-irrf', 'chart-fill-irrf', 'chart-val-irrf', irrf, pIrrf);
        setBar('seg-bar-fgts', 'chart-fill-fgts', 'chart-val-fgts', fgts, pFgts);

        // Gráfico 2: Distribuição do Efetivo por Departamento
        const chartSetores = document.getElementById('chart-distribuicao-setores');
        if (chartSetores) {
          const setores = d.distribuicao_setores || [];
          if (setores.length === 0) {
            chartSetores.innerHTML = '<div class="text-sm text-muted">Nenhum setor ativo cadastrado.</div>';
          } else {
            const totalColabs = Math.max(1, setores.reduce((acc, s) => acc + Number(s.total || 0), 0));
            const cores = ['seg-liquido', 'seg-inss', 'seg-fgts', 'seg-irrf'];
            chartSetores.innerHTML = '';
            setores.forEach((s, idx) => {
              const qtd = Number(s.total || 0);
              const pct = Math.round((qtd / totalColabs) * 100);
              const corClass = cores[idx % cores.length];
              const item = document.createElement('div');
              item.className = 'chart-bar-item';
              item.innerHTML = `
                <div class="chart-bar-meta">
                  <span class="chart-bar-name"><span class="legend-dot ${corClass}"></span>${s.setor || 'Geral'}</span>
                  <strong class="chart-bar-val">${qtd} colab. (${pct}%) &bull; ${this.formatarMoedaBRL(s.massa || 0)}</strong>
                </div>
                <div class="chart-bar-track">
                  <div class="chart-bar-fill ${corClass}" style="width: ${Math.max(6, pct)}%;"></div>
                </div>
              `;
              chartSetores.appendChild(item);
            });
          }
        }
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

      // Atualiza badges de pendências
      const abertas = lista.filter(p => {
        const st = String(p.status || '').toUpperCase();
        return st === 'PENDENTE' || st === 'EM_ANALISE';
      }).length;
      this.atualizarBadgesPendencias(abertas);

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding: 2rem;">Nenhuma pendência operacional encontrada para os filtros.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(p => {
        const tr = document.createElement('tr');
        const sevUp = String(p.severidade || 'MEDIA').toUpperCase();
        const stUp = String(p.status || 'PENDENTE').toUpperCase();
        const sevClass = sevUp === 'CRITICA' ? 'badge-severidade-critica' :
          sevUp === 'ALTA' ? 'badge-severidade-alta' :
            sevUp === 'MEDIA' ? 'badge-severidade-media' : 'badge-severidade-baixa';

        tr.innerHTML = `
          <td><span class="${sevClass}">${sevUp}</span></td>
          <td><strong style="font-size: 0.85rem;">${p.tipo_pendencia || p.modulo || '-'}</strong></td>
          <td>
            <div style="font-weight: 600; font-size: 0.88rem;">${p.titulo}</div>
            <div class="text-xs text-muted">${p.descricao || ''}</div>
          </td>
          <td>${p.nome_colaborador || p.responsavel || p.recurso_afetado || '-'}</td>
          <td>${p.prazo_limite || p.data_limite_sla || p.data_vencimento || 'Imediato'}</td>
          <td><span class="badge-status ${stUp.startsWith('RESOLVID') ? 'badge-fechada' : 'badge-calculada'}">${stUp}</span></td>
          <td>
            ${stUp === 'PENDENTE' || stUp === 'EM_ANALISE' ?
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
  // ADMISSÕES & CHECKLIST + CARTÃO ÚNICO (RF-011 A RF-020, RN-008, RN-009, RN-010, RN-080)
  // --------------------------------------------------------------------------
  admissaoEmPainelId: null,
  escalasCache: [],
  centrosCustoCache: [],
  modelosContratoCache: [],

  async carregarCatalogosAdmissao() {
    try {
      const [rEsc, rCc, rMod] = await Promise.all([
        fetch(`${API_BASE}/admissoes/escalas`, { headers: getAuthHeaders(), credentials: 'include' }),
        fetch(`${API_BASE}/admissoes/centros-custo`, { headers: getAuthHeaders(), credentials: 'include' }),
        fetch(`${API_BASE}/admissoes/contratos/modelos`, { headers: getAuthHeaders(), credentials: 'include' }),
      ]);
      if (rEsc.ok) this.escalasCache = (await rEsc.json()).dados || [];
      if (rCc.ok) this.centrosCustoCache = (await rCc.json()).dados || [];
      if (rMod.ok) this.modelosContratoCache = (await rMod.json()).dados || [];

      const popSel = (selId, optsHtml, keepFirst) => {
        const el = document.getElementById(selId);
        if (!el) return;
        const firstOpt = keepFirst ? (el.options[0]?.outerHTML || '') : '';
        el.innerHTML = firstOpt + optsHtml;
      };
      const escOpts = this.escalasCache.map(e => `<option value="${e.id}">${_escHtml(e.codigo)} — ${_escHtml(e.descricao)} (${_escHtml(e.entrada_padrao)}-${_escHtml(e.saida_padrao)})</option>`).join('');
      const ccOpts = this.centrosCustoCache.map(c => `<option value="${_escHtml(c.id)}">${_escHtml(c.codigo)} — ${_escHtml(c.descricao)}</option>`).join('');
      const modOpts = this.modelosContratoCache.map(m => `<option value="${m.id}">${_escHtml(m.nome)}</option>`).join('');

      popSel('adm-candidato-escala', escOpts, true);
      popSel('adm-jornada-escala-select', escOpts, false);
      popSel('adm-candidato-cc', ccOpts, true);
      popSel('adm-cc-select', ccOpts, false);
      popSel('adm-ctr-modelo-select', modOpts, false);
    } catch (_) {}
  },

  async carregarAdmissoes() {
    await this.carregarCatalogosAdmissao();
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
        const salarioFmt = Number(a.salario_proposto || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const nomeCand = _escHtml(a.candidato_nome || a.nome_candidato || '-');
        const cpfExibir = _escHtml(a.candidato_cpf_mascarado || formatarCpf(a.candidato_cpf || ''));
        const cargoCand = _escHtml(a.cargo || a.cargo_proposto || '-');
        const dtAdm = _escHtml(a.data_prevista_admissao || a.data_admissao_prevista || '-');
        const stUp = String(a.status || 'em_andamento').toUpperCase();
        const resumoChk = _escHtml(a.checklist_resumo || `${a.documentos_aprovados || 0}/${a.total_documentos || 8} docs`);
        const concluido = stUp === 'EFETIVADO' || stUp === 'APROVADA';

        tr.innerHTML = `
          <td><strong>${nomeCand}</strong><br><small class="text-muted">${_escHtml(a.codigo_processo || '')}</small></td>
          <td>${cpfExibir}</td>
          <td>${cargoCand}</td>
          <td>${salarioFmt}</td>
          <td>${dtAdm}</td>
          <td><span class="badge-status badge-calculada">${resumoChk}</span></td>
          <td><span class="badge-status ${concluido ? 'badge-fechada' : 'badge-calculada'}">${_escHtml(stUp)}</span></td>
          <td style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
            <button class="btn btn-primary btn-sm btn-painel-admissao" data-id="${a.id}">Cartão (RF-011..020)</button>
            <button class="btn btn-outline btn-sm btn-ver-checklist" data-id="${a.id}">Checklist</button>
          </td>
        `;
        tbody.appendChild(tr);
      });

      document.querySelectorAll('.btn-painel-admissao').forEach(b => {
        b.addEventListener('click', () => {
          PlataformaManager.abrirCartaoAdmissao(Number(b.getAttribute('data-id')));
        });
      });
      document.querySelectorAll('.btn-ver-checklist').forEach(b => {
        b.addEventListener('click', () => {
          PlataformaManager.abrirChecklistAdmissao(b.getAttribute('data-id'));
        });
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger" style="padding: 2rem;">Erro ao consultar admissões.</td></tr>';
    }
  },

  async abrirCartaoAdmissao(admissaoId) {
    this.admissaoEmPainelId = admissaoId;
    const card = document.getElementById('cartao-processo-admissional');
    if (card) card.classList.remove('hidden');

    try {
      await this.carregarCatalogosAdmissao();
      const [rPainel, rBenef] = await Promise.all([
        fetch(`${API_BASE}/admissoes/${admissaoId}/painel`, { headers: getAuthHeaders(), credentials: 'include' }),
        fetch(`${API_BASE}/admissoes/${admissaoId}/beneficios-elegiveis`, { headers: getAuthHeaders(), credentials: 'include' }),
      ]);
      if (!rPainel.ok) throw new Error('Erro ao carregar Cartão Admissional.');
      const painel = (await rPainel.json()).dados;
      const benefEleg = rBenef.ok ? ((await rBenef.json()).dados || []) : [];

      const idf = painel.identificacao || {};
      const res = painel.resumo || {};
      const adm = painel.admissao || {};

      document.getElementById('adm-card-titulo').textContent = `CARTÃO: PROCESSO ADMISSIONAL — ${idf.codigo_processo || '#' + admissaoId}`;
      document.getElementById('adm-card-subtitulo').textContent = `Status atual: ${String(idf.status || '').toUpperCase()} • ${res.etapas_concluidas}/10 etapas concluídas`;
      document.getElementById('adm-id-cand-nome').textContent = idf.candidato_nome || '--';
      document.getElementById('adm-id-cpf').textContent = idf.cpf_mascarado || '--';
      document.getElementById('adm-id-cargo').textContent = `${idf.cargo || '--'} / ${idf.setor || '--'}`;
      document.getElementById('adm-id-empresa').textContent = idf.empresa || '--';
      document.getElementById('adm-id-filial').textContent = idf.filial || '--';
      document.getElementById('adm-id-data-adm').textContent = idf.data_prevista_admissao || '--';
      document.getElementById('adm-id-responsavel').textContent = idf.responsavel || '--';
      document.getElementById('adm-id-data-abertura').textContent = idf.data_abertura || '--';

      document.getElementById('adm-resumo-progresso-pct').textContent = `${res.progresso_percentual || 0}%`;
      document.getElementById('adm-resumo-barra-progresso').style.width = `${res.progresso_percentual || 0}%`;
      document.getElementById('adm-resumo-concluidas').textContent = `${res.etapas_concluidas || 0}/10`;
      document.getElementById('adm-resumo-pendentes').textContent = String(res.etapas_pendentes ?? 10);
      document.getElementById('adm-resumo-proxima').textContent = res.proxima_etapa || '--';
      document.getElementById('adm-resumo-responsavel-atual').textContent = res.responsavel_atual || '--';
      const impEl = document.getElementById('adm-resumo-impeditivas');
      if (impEl) {
        const imps = res.pendencias_impeditivas || [];
        impEl.textContent = imps.length ? `Pendências impeditivas (${imps.length}): ${imps.join(' | ')}` : 'Sem pendências impeditivas para aprovação.';
      }

      // Renderiza as 10 etapas individuais rastreáveis
      const mapSecao = {
        'RF-011': 'cartao-processo-admissional',
        'RF-012': 'adm-secao-rf012',
        'RF-013': 'adm-secao-rf013',
        'RF-014': 'adm-secao-rf014',
        'RF-015': 'adm-secao-rf015',
        'RF-016': 'adm-secao-rf016',
        'RF-017': 'adm-secao-rf017',
        'RF-018': 'adm-secao-rf018',
        'RF-019': 'adm-secao-rf019',
        'RF-020': 'adm-secao-rf020',
      };
      const tbodyEt = document.getElementById('adm-etapas-lista');
      if (tbodyEt) {
        tbodyEt.innerHTML = (painel.etapas || []).map(et => {
          const badge = et.status === 'concluido' ? 'badge-ativo' : (et.status === 'reprovado' || et.status === 'bloqueado' ? 'badge-inativo' : 'badge-dep');
          const pendTxt = (et.pendencias || []).length ? `<div class="text-xs text-danger">${_escHtml(et.pendencias.join('; '))}</div>` : '';
          return `
            <tr>
              <td><strong>${_escHtml(et.ordem)} — ${_escHtml(et.rf)}</strong> | ${_escHtml(et.nome)}</td>
              <td><span class="badge ${badge}">${_escHtml(et.status.toUpperCase())}</span></td>
              <td>${_escHtml(et.responsavel || '--')}</td>
              <td>${_escHtml(et.data_conclusao || '--')}</td>
              <td><div>${_escHtml(et.evidencias || '--')}</div>${pendTxt}</td>
              <td class="text-right"><button type="button" class="btn btn-outline btn-sm" onclick="document.getElementById('${mapSecao[et.rf] || 'cartao-processo-admissional'}')?.scrollIntoView({behavior:'smooth'})">Acessar</button></td>
            </tr>
          `;
        }).join('');
      }

      // Preenche Checklist RF-012
      const chk = adm.checklist || [];
      const selChk = document.getElementById('adm-chk-item-select');
      if (selChk) selChk.innerHTML = chk.map(c => `<option value="${c.id}">${_escHtml(c.item_descricao)}</option>`).join('');
      const chkBox = document.getElementById('adm-chk-tbody');
      if (chkBox) {
        chkBox.innerHTML = `
          <table class="data-table">
            <thead><tr><th>Documento</th><th>Obrig.</th><th>Arquivo / Versão</th><th>Status</th><th class="text-right">Ações</th></tr></thead>
            <tbody>
              ${chk.map(c => `
                <tr>
                  <td>${_escHtml(c.item_descricao)}${c.motivo_rejeicao ? `<br><small class="text-danger">Motivo: ${_escHtml(c.motivo_rejeicao)}</small>` : ''}</td>
                  <td>${c.obrigatorio ? 'Sim' : 'Opcional'}</td>
                  <td>${c.nome_arquivo ? `${_escHtml(c.nome_arquivo)} (v${c.versao || 1})` : '--'}</td>
                  <td><span class="badge badge-dep">${_escHtml(c.status)}</span></td>
                  <td class="text-right" style="white-space:nowrap;">
                    ${c.nome_arquivo ? `<button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.baixarAnexoChecklist(${admissaoId}, ${c.id}, '${_escHtml(c.nome_arquivo)}')">Baixar</button>` : ''}
                    <button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.alterarStatusChecklistDireto(${c.id}, 'validado')">Validar</button>
                    <button type="button" class="btn btn-outline btn-sm text-danger" onclick="PlataformaManager.alterarStatusChecklistDireto(${c.id}, 'rejeitado')">Rejeitar</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }

      // Preenche Jornada RF-017 e Centro de Custo RF-018
      if (adm.escala_id && document.getElementById('adm-jornada-escala-select')) document.getElementById('adm-jornada-escala-select').value = String(adm.escala_id);
      if (adm.jornada_entrada && document.getElementById('adm-jornada-entrada')) document.getElementById('adm-jornada-entrada').value = adm.jornada_entrada;
      if (adm.jornada_saida && document.getElementById('adm-jornada-saida')) document.getElementById('adm-jornada-saida').value = adm.jornada_saida;
      if (document.getElementById('adm-jornada-vigencia')) document.getElementById('adm-jornada-vigencia').value = adm.jornada_vigencia_inicio || adm.data_prevista_admissao || '';
      if (adm.centro_custo_id && document.getElementById('adm-cc-select')) document.getElementById('adm-cc-select').value = adm.centro_custo_id;
      if (document.getElementById('adm-cc-vigencia')) document.getElementById('adm-cc-vigencia').value = adm.centro_custo_vigencia || adm.data_prevista_admissao || '';
      if (document.getElementById('adm-benef-vigencia')) document.getElementById('adm-benef-vigencia').value = adm.data_prevista_admissao || '';

      // Preenche ASO RF-016
      const asoResEl = document.getElementById('adm-aso-resumo');
      if (asoResEl) {
        if (adm.aso) {
          asoResEl.textContent = adm.aso.restrito_sigilo_medico
            ? `Aptidão: ${adm.aso.resultado} (Detalhes clínicos protegidos por sigilo)`
            : `ASO #${adm.aso.id}: ${adm.aso.resultado} (${adm.aso.status_exame}) • CRM ${adm.aso.medico_crm}/${adm.aso.medico_uf} • Validade: ${adm.aso.data_validade}`;
        } else {
          asoResEl.textContent = 'Nenhum ASO Admissional registrado no SST (RN-009).';
        }
      }

      // Preenche Benefícios RF-019
      const benDiv = document.getElementById('adm-beneficios-disponiveis');
      const benSelIds = new Set((adm.beneficios || []).map(b => Number(b.beneficio_id)));
      if (benDiv) {
        benDiv.innerHTML = benefEleg.map(b => `
          <label style="display:flex; align-items:center; gap:0.45rem; padding:0.25rem 0; opacity:${b.elegivel ? '1' : '0.55'};">
            <input type="checkbox" class="adm-benef-chk" value="${b.id}" ${benSelIds.has(Number(b.id)) ? 'checked' : ''} ${b.elegivel ? '' : 'disabled'}>
            <span><strong>${_escHtml(b.nome)}</strong> (${_escHtml(b.tipo)})${b.elegivel ? '' : ` — <small class="text-danger">${_escHtml((b.motivos_inelegibilidade || []).join('; '))}</small>`}</span>
          </label>
        `).join('') || '<p class="text-muted">Nenhum benefício ativo no catálogo.</p>';
      }

      // Preenche Contratos RF-014
      const ctrLista = document.getElementById('adm-ctr-lista');
      if (ctrLista) {
        const ctrs = adm.contratos || [];
        ctrLista.innerHTML = ctrs.length ? ctrs.map(c => `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:0.35rem 0; border-bottom:1px solid #e5e7eb;">
            <span><strong>${_escHtml(c.nome_arquivo)}</strong> (v${c.versao}) — ${c.formalizado ? '<span class="badge badge-ativo">Formalizado</span>' : 'Minuta'}</span>
            <span style="display:flex; gap:0.35rem;">
              <button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.baixarContratoAdmissao(${admissaoId}, ${c.id}, '${_escHtml(c.nome_arquivo)}')">PDF</button>
              ${!c.formalizado ? `<button type="button" class="btn btn-primary btn-sm" onclick="PlataformaManager.formalizarContratoAdmissao(${admissaoId}, ${c.id})">Formalizar</button>` : ''}
            </span>
          </div>
        `).join('') : 'Nenhum contrato gerado.';
      }

      // Preenche eSocial RF-015
      const aplicEl = document.getElementById('adm-esoc-aplicabilidade');
      if (aplicEl && res.esocial_aplicabilidade) {
        aplicEl.textContent = `Recomendado: ${res.esocial_aplicabilidade.evento_recomendado} — ${res.esocial_aplicabilidade.motivo}`;
      }
      const esocLista = document.getElementById('adm-esoc-lista');
      if (esocLista) {
        const evs = adm.esocial_eventos || [];
        esocLista.innerHTML = evs.length ? evs.map(ev => `
          <div style="padding:0.35rem 0; border-bottom:1px solid #e5e7eb;">
            <strong>${_escHtml(ev.tipo_evento)} #${ev.id}</strong> (${_escHtml(ev.ambiente)}) — <span class="badge badge-dep">${_escHtml(ev.status)}</span>
            ${ev.numero_recibo ? `• Recibo: ${_escHtml(ev.numero_recibo)}` : '• Sem recibo oficial (simulado/local)'}
          </div>
        `).join('') : 'Nenhum evento eSocial gerado para esta admissão.';
      }
    } catch (e) {
      exibirToast(e.message || 'Erro ao carregar cartão da admissão.', 'error');
    }
  },

  async salvarNovaAdmissao() {
    const nome = document.getElementById('adm-candidato-nome')?.value?.trim();
    const cpf = document.getElementById('adm-candidato-cpf')?.value?.trim();
    const nasc = document.getElementById('adm-candidato-nasc')?.value;
    const email = document.getElementById('adm-candidato-email')?.value?.trim();
    const tel = document.getElementById('adm-candidato-telefone')?.value?.trim();
    const estCiv = document.getElementById('adm-candidato-estado-civil')?.value;
    const end = document.getElementById('adm-candidato-endereco')?.value?.trim();
    const cargo = document.getElementById('adm-candidato-cargo')?.value?.trim();
    const setor = document.getElementById('adm-candidato-setor')?.value?.trim();
    const salario = parseFloat(document.getElementById('adm-candidato-salario')?.value || 0);
    const dataInicio = document.getElementById('adm-candidato-data')?.value;
    const tipoCtr = document.getElementById('adm-candidato-tipo-contrato')?.value || 'experiencia';
    const filialId = document.getElementById('adm-candidato-filial')?.value || 'b0000000-0000-0000-0000-000000000001';
    const escalaId = document.getElementById('adm-candidato-escala')?.value || null;
    const ccId = document.getElementById('adm-candidato-cc')?.value || null;
    const gestor = document.getElementById('adm-candidato-gestor')?.value?.trim();
    const localTrab = document.getElementById('adm-candidato-local')?.value?.trim();

    if (!nome || !cpf || !nasc || !email || !cargo || !setor || !dataInicio) {
      exibirToast('Preencha todos os campos obrigatórios (nome, CPF, nascimento, e-mail, cargo, setor, data e salário).', 'error');
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
          candidato_nome: nome,
          candidato_cpf: normalizarCpf(cpf),
          candidato_data_nascimento: nasc,
          candidato_email: email,
          candidato_telefone: tel,
          candidato_estado_civil: estCiv,
          candidato_endereco: end,
          cargo,
          setor,
          salario_proposto: salario,
          data_prevista_admissao: dataInicio,
          tipo_contrato: tipoCtr,
          filial_id: filialId,
          escala_id: escalaId ? Number(escalaId) : null,
          centro_custo_id: ccId || null,
          gestor_responsavel: gestor,
          local_trabalho: localTrab,
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao registrar admissão.', 'error');
        return;
      }
      exibirToast('Processo admissional aberto com sucesso!', 'success');
      document.getElementById('modal-nova-admissao')?.classList.add('hidden');
      await this.carregarAdmissoes();
      if (json.dados?.id) await this.abrirCartaoAdmissao(json.dados.id);
    } catch (e) {
      exibirToast('Erro de rede ao salvar processo admissional.', 'error');
    }
  },

  async uploadChecklistAdmissao() {
    const admId = this.admissaoEmPainelId;
    const itemId = document.getElementById('adm-chk-item-select')?.value;
    const input = document.getElementById('adm-chk-arquivo');
    const file = input?.files?.[0];
    const obs = document.getElementById('adm-chk-obs')?.value?.trim() || '';
    if (!admId || !itemId || !file) {
      exibirToast('Selecione o documento e o arquivo para upload.', 'error');
      return;
    }
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        await requisitarApi(`${API_BASE}/admissoes/${admId}/checklist/${itemId}/upload`, {
          method: 'POST',
          body: JSON.stringify({ nome_arquivo: file.name, mime_type: file.type, conteudo_base64: String(reader.result || ''), observacao: obs }),
        });
        exibirToast('Documento enviado com sucesso!', 'success');
        if (input) input.value = '';
        await Promise.all([this.abrirCartaoAdmissao(admId), this.carregarAdmissoes()]);
      } catch (e) {
        exibirToast(e.message || 'Erro no upload.', 'error');
      }
    };
    reader.readAsDataURL(file);
  },

  async alterarStatusChecklistDireto(itemId, novoStatus) {
    const admId = this.admissaoEmPainelId;
    const just = document.getElementById('adm-chk-obs')?.value?.trim() || (novoStatus === 'rejeitado' ? 'Documento ilegível ou divergente' : '');
    try {
      await requisitarApi(`${API_BASE}/admissoes/checklist/${itemId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: novoStatus, justificativa: just }),
      });
      exibirToast(`Item atualizado para ${novoStatus}.`, 'success');
      if (admId) await Promise.all([this.abrirCartaoAdmissao(admId), this.carregarAdmissoes()]);
    } catch (e) {
      exibirToast(e.message || 'Erro ao atualizar item.', 'error');
    }
  },

  async baixarAnexoChecklist(admId, itemId, nomeArq) {
    try {
      const headers = getAuthHeaders();
      delete headers['Content-Type'];
      const r = await fetch(`${API_BASE}/admissoes/${admId}/checklist/${itemId}/download`, { headers, credentials: 'include' });
      if (!r.ok) throw new Error('Falha ao baixar documento.');
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = nomeArq || `doc_${itemId}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      exibirToast(e.message || 'Erro no download.', 'error');
    }
  },

  async salvarJornadaAdmissao() {
    const admId = this.admissaoEmPainelId;
    if (!admId) return;
    try {
      await requisitarApi(`${API_BASE}/admissoes/${admId}/jornada`, {
        method: 'POST',
        body: JSON.stringify({
          escala_id: Number(document.getElementById('adm-jornada-escala-select')?.value),
          entrada: document.getElementById('adm-jornada-entrada')?.value,
          saida: document.getElementById('adm-jornada-saida')?.value,
          intervalo_minutos: Number(document.getElementById('adm-jornada-intervalo')?.value || 60),
          vigencia_inicio: document.getElementById('adm-jornada-vigencia')?.value,
        }),
      });
      exibirToast('Jornada inicial vinculada!', 'success');
      await this.abrirCartaoAdmissao(admId);
    } catch (e) {
      exibirToast(e.message || 'Erro ao vincular jornada.', 'error');
    }
  },

  async salvarCentroCustoAdmissao() {
    const admId = this.admissaoEmPainelId;
    if (!admId) return;
    try {
      await requisitarApi(`${API_BASE}/admissoes/${admId}/centro-custo`, {
        method: 'POST',
        body: JSON.stringify({
          centro_custo_id: document.getElementById('adm-cc-select')?.value,
          vigencia_inicio: document.getElementById('adm-cc-vigencia')?.value,
        }),
      });
      exibirToast('Centro de Custo vinculado!', 'success');
      await this.abrirCartaoAdmissao(admId);
    } catch (e) {
      exibirToast(e.message || 'Erro ao vincular centro de custo.', 'error');
    }
  },

  async salvarAsoAdmissional() {
    const admId = this.admissaoEmPainelId;
    if (!admId) return;
    const inputFile = document.getElementById('adm-aso-arquivo');
    const file = inputFile?.files?.[0];
    const enviar = async (b64 = null) => {
      try {
        await requisitarApi(`${API_BASE}/admissoes/${admId}/aso`, {
          method: 'POST',
          body: JSON.stringify({
            status_exame: document.getElementById('adm-aso-status')?.value,
            resultado: document.getElementById('adm-aso-resultado')?.value,
            data_emissao: document.getElementById('adm-aso-data-real')?.value,
            data_validade: document.getElementById('adm-aso-data-val')?.value,
            medico_nome: document.getElementById('adm-aso-medico')?.value?.trim(),
            medico_crm: document.getElementById('adm-aso-crm')?.value?.trim(),
            medico_uf: document.getElementById('adm-aso-uf')?.value?.trim(),
            nome_arquivo: file ? file.name : null,
            mime_type: file ? file.type : null,
            conteudo_base64: b64,
          }),
        });
        exibirToast('ASO Admissional registrado no SST!', 'success');
        if (inputFile) inputFile.value = '';
        await Promise.all([this.abrirCartaoAdmissao(admId), this.carregarAdmissoes()]);
      } catch (e) {
        exibirToast(e.message || 'Erro ao registrar ASO.', 'error');
      }
    };
    if (file) {
      const r = new FileReader();
      r.onload = () => enviar(String(r.result || ''));
      r.readAsDataURL(file);
    } else {
      await enviar(null);
    }
  },

  async salvarBeneficiosAdmissao() {
    const admId = this.admissaoEmPainelId;
    if (!admId) return;
    const vig = document.getElementById('adm-benef-vigencia')?.value;
    const itens = Array.from(document.querySelectorAll('.adm-benef-chk:checked')).map(c => ({
      beneficio_id: Number(c.value),
      vigencia_inicio: vig,
      optante: true,
    }));
    try {
      await requisitarApi(`${API_BASE}/admissoes/${admId}/beneficios`, {
        method: 'POST',
        body: JSON.stringify({ beneficios: itens }),
      });
      exibirToast('Benefícios elegíveis associados à admissão!', 'success');
      await this.abrirCartaoAdmissao(admId);
    } catch (e) {
      exibirToast(e.message || 'Erro ao associar benefícios.', 'error');
    }
  },

  async executarValidacaoAdmissional() {
    const admId = this.admissaoEmPainelId;
    if (!admId) return;
    try {
      const res = await requisitarApi(`${API_BASE}/admissoes/${admId}/validar`, { method: 'POST', body: '{}' });
      const d = res.dados || {};
      const box = document.getElementById('adm-val-resultado');
      if (box) {
        box.innerHTML = `
          <div><strong>Situação:</strong> ${d.apto_efetivacao ? '<span class="badge badge-ativo">APTO PARA APROVAÇÃO</span>' : '<span class="badge badge-inativo">PENDÊNCIAS IMPEDITIVAS</span>'}</div>
          <div class="text-xs" style="margin-top:0.35rem;"><strong>Aprovados:</strong> ${_escHtml((d.aprovados || []).join(' • ') || '--')}</div>
          ${(d.pendentes || []).length ? `<div class="text-xs text-danger"><strong>Pendentes:</strong> ${_escHtml(d.pendentes.join(' • '))}</div>` : ''}
          ${(d.invalidos || []).length ? `<div class="text-xs text-danger"><strong>Inválidos:</strong> ${_escHtml(d.invalidos.join(' • '))}</div>` : ''}
        `;
      }
      await this.abrirCartaoAdmissao(admId);
    } catch (e) {
      exibirToast(e.message || 'Erro ao executar validação.', 'error');
    }
  },

  async gerarContratoAdmissao() {
    const admId = this.admissaoEmPainelId;
    if (!admId) return;
    try {
      await requisitarApi(`${API_BASE}/admissoes/${admId}/contratos/gerar`, {
        method: 'POST',
        body: JSON.stringify({
          modelo_id: Number(document.getElementById('adm-ctr-modelo-select')?.value || 0) || null,
          condicoes_adicionais: document.getElementById('adm-ctr-condicoes')?.value?.trim() || '',
        }),
      });
      exibirToast('Contrato de Trabalho PDF gerado com sucesso!', 'success');
      await this.abrirCartaoAdmissao(admId);
    } catch (e) {
      exibirToast(e.message || 'Erro ao gerar contrato.', 'error');
    }
  },

  async baixarContratoAdmissao(admId, ctrId, nomeArq) {
    try {
      const headers = getAuthHeaders();
      delete headers['Content-Type'];
      const r = await fetch(`${API_BASE}/admissoes/${admId}/contratos/${ctrId}/download`, { headers, credentials: 'include' });
      if (!r.ok) throw new Error('Falha ao baixar PDF do contrato.');
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = nomeArq || `contrato_${ctrId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e) {
      exibirToast(e.message || 'Erro ao baixar contrato.', 'error');
    }
  },

  async formalizarContratoAdmissao(admId, ctrId) {
    try {
      await requisitarApi(`${API_BASE}/admissoes/${admId}/contratos/${ctrId}/formalizar`, { method: 'POST', body: '{}' });
      exibirToast('Contrato formalizado! Versão original preservada.', 'success');
      await this.abrirCartaoAdmissao(admId);
    } catch (e) {
      exibirToast(e.message || 'Erro ao formalizar contrato.', 'error');
    }
  },

  async gerarESocialAdmissao() {
    const admId = this.admissaoEmPainelId;
    if (!admId) return;
    try {
      await requisitarApi(`${API_BASE}/admissoes/${admId}/esocial/gerar`, {
        method: 'POST',
        body: JSON.stringify({
          tipo_evento: document.getElementById('adm-esoc-tipo-select')?.value || null,
          ambiente: document.getElementById('adm-esoc-ambiente-select')?.value || 'homologacao',
        }),
      });
      exibirToast('Evento eSocial gerado e validado no schema S-1.2!', 'success');
      await this.abrirCartaoAdmissao(admId);
    } catch (e) {
      exibirToast(e.message || 'Erro ao gerar evento eSocial.', 'error');
    }
  },

  async aprovarAdmissaoPainel() {
    const admId = this.admissaoEmPainelId;
    if (!admId) return;
    const just = document.getElementById('adm-aprov-justificativa')?.value?.trim() || '';
    try {
      const json = await requisitarApi(`${API_BASE}/admissoes/${admId}/aprovar`, {
        method: 'POST',
        body: JSON.stringify({ justificativa: just }),
      });
      exibirToast(json.mensagem || 'Admissão aprovada e efetivada!', 'success');
      await Promise.all([this.carregarAdmissoes(), this.abrirCartaoAdmissao(admId)]);
    } catch (e) {
      exibirToast(e.message || 'Erro ao aprovar admissão.', 'error');
    }
  },

  async reprovarAdmissaoPainel() {
    const admId = this.admissaoEmPainelId;
    const just = document.getElementById('adm-aprov-justificativa')?.value?.trim() || '';
    if (!admId || !just) {
      exibirToast('Informe a justificativa para reprovar.', 'error');
      return;
    }
    try {
      await requisitarApi(`${API_BASE}/admissoes/${admId}/reprovar`, { method: 'POST', body: JSON.stringify({ motivo: just }) });
      exibirToast('Processo admissional reprovado.', 'success');
      await Promise.all([this.carregarAdmissoes(), this.abrirCartaoAdmissao(admId)]);
    } catch (e) {
      exibirToast(e.message || 'Erro ao reprovar admissão.', 'error');
    }
  },

  async cancelarAdmissaoPainel() {
    const admId = this.admissaoEmPainelId;
    const just = document.getElementById('adm-aprov-justificativa')?.value?.trim() || '';
    if (!admId || !just) {
      exibirToast('Informe o motivo do cancelamento no campo Justificativa.', 'error');
      return;
    }
    try {
      await requisitarApi(`${API_BASE}/admissoes/${admId}/cancelar`, { method: 'POST', body: JSON.stringify({ motivo: just }) });
      exibirToast('Processo admissional cancelado.', 'success');
      await Promise.all([this.carregarAdmissoes(), this.abrirCartaoAdmissao(admId)]);
    } catch (e) {
      exibirToast(e.message || 'Erro ao cancelar admissão.', 'error');
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
        const stItem = String(item.status || 'pendente').toLowerCase();
        const nomeDoc = item.item_descricao || item.nome_documento || 'Documento Obrigatório';
        const itemDiv = document.createElement('div');
        itemDiv.style.cssText = 'display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; padding: 0.6rem 0.85rem; border: 1px solid var(--border-color); border-radius: 8px; background: #fff;';
        itemDiv.innerHTML = `
          <div>
            <strong style="font-size: 0.85rem;">${nomeDoc}</strong>
            <span class="text-xs text-muted" style="display: block;">${item.obrigatorio ? 'Obrigatório (RF-012)' : 'Complementar'}</span>
          </div>
          <div>
            <select class="form-control form-control-sm select-status-item" data-id="${item.id}" style="font-size: 0.8rem; padding: 0.25rem 0.5rem; min-width: 120px;">
              <option value="pendente" ${stItem === 'pendente' ? 'selected' : ''}>Pendente</option>
              <option value="validado" ${stItem === 'validado' || stItem === 'aprovado' || stItem === 'entregue' ? 'selected' : ''}>Validado</option>
              <option value="dispensado" ${stItem === 'dispensado' ? 'selected' : ''}>Dispensado</option>
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

  async baixarArquivoAutenticado(url, nomeArquivoFallback = 'documento.pdf') {
    try {
      const resp = await fetch(url, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) {
        let msg = 'Erro ao baixar arquivo.';
        try {
          const j = await resp.json();
          msg = j.mensagem || msg;
        } catch (_) {}
        exibirToast(msg, 'error');
        return;
      }
      const blob = await resp.blob();
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = nomeArquivoFallback;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objUrl);
    } catch (e) {
      exibirToast('Erro de comunicação ao baixar documento.', 'error');
    }
  },

  exportarCSVGenerico(cabecalho, linhas, nomeArquivo) {
    if (!linhas || linhas.length === 0) {
      exibirToast('Nenhum dado disponível para exportar em CSV.', 'warning');
      return;
    }
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const conteudo = '\uFEFF' + [
      cabecalho.map(esc).join(';'),
      ...linhas.map(row => row.map(esc).join(';'))
    ].join('\n');
    const blob = new Blob([conteudo], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = nomeArquivo;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    exibirToast(`Relatório ${nomeArquivo} exportado em CSV.`, 'success');
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
      let dias = espelho.dias || [];
      if (dias.length === 0 && Array.isArray(espelho.grade_dias)) {
        dias = espelho.grade_dias.map(g => {
          const b = g.batidas || [];
          const trab = Number(g.horas_trab ?? g.horas_trabalhadas ?? 0);
          const saldoHoras = Number(g.saldo ?? g.saldo_horas ?? 0);
          const temIncons = Boolean(g.incons_msg);
          return {
            data: g.data,
            dia_semana: g.dia_semana || 'Dia',
            entrada_1: b[0] || '--:--',
            saida_1: b[1] || '--:--',
            entrada_2: b[2] || '--:--',
            saida_2: b[3] || '--:--',
            total_trabalhado: trab,
            saldo_diario: saldoHoras,
            status: temIncons ? g.incons_msg : ((g.ocorrencias && g.ocorrencias.length > 0) ? g.ocorrencias[0] : (b.length % 2 === 0 ? 'COMPLETO' : 'INCOMPLETO'))
          };
        });
      }

      // Atualiza totais reais do motor PontoService
      const tot = espelho.totais || {};
      const totNormais = tot.normais_horas ?? tot.horas_normais ?? 0;
      const totHe50 = tot.he_50_horas ?? tot.horas_extras_50 ?? 0;
      const totHe100 = (Number(tot.he_100_horas ?? tot.horas_extras_100 ?? 0) + Number(tot.feriado_100_horas ?? 0));
      const totNoturno = tot.noturno_horas ?? tot.adicional_noturno ?? 0;
      const totAtrasos = Number(tot.atraso_horas ?? 0) + (Number(tot.faltas_injustificadas_dias ?? 0) * 8);

      document.getElementById('ponto-tot-normais').textContent = `${Number(totNormais).toFixed(2)}h`;
      document.getElementById('ponto-tot-he50').textContent = `${Number(totHe50).toFixed(2)}h`;
      document.getElementById('ponto-tot-he100').textContent = `${Number(totHe100).toFixed(2)}h`;
      document.getElementById('ponto-tot-noturno').textContent = `${Number(totNoturno).toFixed(2)}h`;
      document.getElementById('ponto-tot-faltas').textContent = `${Number(totAtrasos).toFixed(2)}h`;

      if (dias.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Nenhuma batida registrada para esta competência.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      dias.forEach(d => {
        const tr = document.createElement('tr');
        const trabNum = Number(d.total_trabalhado || 0);
        const saldoNum = Number(d.saldo_diario || 0);
        tr.innerHTML = `
          <td><strong>${d.data}</strong></td>
          <td>${d.dia_semana || '-'}</td>
          <td><span class="batida-pill">${d.entrada_1 || '--:--'}</span></td>
          <td><span class="batida-pill">${d.saida_1 || '--:--'}</span></td>
          <td><span class="batida-pill">${d.entrada_2 || '--:--'}</span></td>
          <td><span class="batida-pill">${d.saida_2 || '--:--'}</span></td>
          <td><strong>${trabNum.toFixed(2)}h</strong></td>
          <td>${saldoNum >= 0 ? `+${saldoNum.toFixed(2)}h` : `${saldoNum.toFixed(2)}h`}</td>
          <td><span class="badge-status badge-calculada">${d.status || 'OK'}</span></td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="9" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar espelho de ponto.</td></tr>';
    }
  },

  async fecharCompetenciaPonto() {
    const competencia = document.getElementById('ponto-competencia-input')?.value || '2026-03';
    if (!confirm(`Confirmar o fechamento da competência de ponto ${competencia}?`)) return;
    try {
      const resp = await fetch(`${API_BASE}/ponto/fechar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ competencia })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao fechar competência de ponto.', 'error');
        return;
      }
      exibirToast(`Competência de ponto ${competencia} fechada e congelada para folha!`, 'success');
    } catch (e) {
      exibirToast('Erro ao comunicar fechamento de ponto.', 'error');
    }
  },

  async exportarRelatorioAusenciasPonto() {
    const competencia = document.getElementById('ponto-competencia-input')?.value || '2026-03';
    try {
      const resp = await fetch(`${API_BASE}/ponto/relatorio-ausencias?competencia=${encodeURIComponent(competencia)}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao consultar relatório de ausências.', 'error');
        return;
      }
      const dados = json.dados || {};
      const itens = Array.isArray(dados) ? dados : (dados.ocorrencias || dados.itens || dados.detalhes || []);
      const linhas = itens.map(it => [
        it.colaborador_nome || it.nome_completo || `#${it.colaborador_id || ''}`,
        it.setor || '-',
        it.data_ocorrencia || it.data_inicio || '-',
        it.tipo || '-',
        it.horas ?? it.dias ?? 0,
        it.justificada ? 'Sim' : 'Não'
      ]);
      this.exportarCSVGenerico(
        ['Colaborador', 'Setor', 'Data', 'Tipo', 'Quantidade', 'Justificada'],
        linhas,
        `ausencias_ponto_${competencia}.csv`
      );
    } catch (e) {
      exibirToast('Erro ao exportar relatório de ausências.', 'error');
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
    tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted" style="padding: 2rem;">Carregando histórico de férias...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/ferias`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar férias');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted" style="padding: 2rem;">Nenhuma programação de férias encontrada. Clique em "Programar Férias".</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(f => {
        const tr = document.createElement('tr');
        const nomeColab = f.nome_completo || f.nome_colaborador || `Colaborador #${f.colaborador_id}`;
        const iniAq = f.inicio_aquisitivo || f.inicio_periodo_aquisitivo || '-';
        const fimAq = f.fim_aquisitivo || f.fim_periodo_aquisitivo || '-';
        const iniGozo = f.data_inicio || f.data_inicio_gozo || '-';
        const fimGozo = f.data_fim || f.data_fim_gozo || '-';
        const adianta = f.adiantar_decimo || f.adiantamento_decimo_terceiro;
        const statusStr = String(f.status || 'solicitada').toLowerCase();
        tr.innerHTML = `
          <td><strong>${nomeColab}</strong></td>
          <td>${iniAq} a ${fimAq}</td>
          <td><strong style="color: #dc2626;">${f.limite_concessivo || f.data_pagamento_limite || '-'}</strong></td>
          <td>${iniGozo}</td>
          <td>${fimGozo}</td>
          <td>${f.dias_gozo || 0} dias</td>
          <td>${f.dias_abono ? `${f.dias_abono} dias` : 'Não'}</td>
          <td>${adianta ? 'Sim (50%)' : 'Não'}</td>
          <td><span class="badge-status badge-fechada">${statusStr.toUpperCase()}</span></td>
          <td class="text-right">
            <div style="display:flex; gap:0.25rem; justify-content:flex-end; flex-wrap:wrap;">
              ${statusStr === 'solicitada' ? `<button type="button" class="btn btn-primary btn-sm" onclick="PlataformaManager.aprovarFerias(${f.id}, true)">Aprovar</button>` : ''}
              ${statusStr !== 'cancelada' ? `<button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.baixarArquivoAutenticado('${API_BASE}/ferias/${f.id}/pdf?tipo=aviso', 'aviso_ferias_${f.id}.pdf')">Aviso PDF</button>` : ''}
              ${statusStr !== 'cancelada' ? `<button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.baixarArquivoAutenticado('${API_BASE}/ferias/${f.id}/pdf?tipo=recibo', 'recibo_ferias_${f.id}.pdf')">Recibo PDF</button>` : ''}
              ${statusStr === 'aprovada' ? `<button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.integrarFeriasFolha(${f.id}, '${iniGozo}')">Integrar Folha</button>` : ''}
              ${statusStr !== 'cancelada' && statusStr !== 'paga' ? `<button type="button" class="btn btn-outline btn-sm text-danger" onclick="PlataformaManager.cancelarFerias(${f.id})">Cancelar</button>` : ''}
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="10" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar férias.</td></tr>';
    }
  },

  async aprovarFerias(feriasId, aprovar = true) {
    try {
      const resp = await fetch(`${API_BASE}/ferias/${feriasId}/aprovar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ aprovar })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao aprovar férias.', 'error');
        return;
      }
      exibirToast('Férias aprovadas com segregação RN-080!', 'success');
      await this.carregarFerias();
    } catch (e) {
      exibirToast('Erro de comunicação ao aprovar férias.', 'error');
    }
  },

  async cancelarFerias(feriasId) {
    const motivo = prompt('Informe o motivo do cancelamento das férias:');
    if (motivo === null) return;
    try {
      const resp = await fetch(`${API_BASE}/ferias/${feriasId}/cancelar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ motivo: motivo || 'Cancelamento operacional' })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao cancelar férias.', 'error');
        return;
      }
      exibirToast('Programação de férias cancelada e saldo restaurado.', 'success');
      await this.carregarFerias();
    } catch (e) {
      exibirToast('Erro ao cancelar férias.', 'error');
    }
  },

  async integrarFeriasFolha(feriasId, dataInicio) {
    const competencia = (dataInicio && String(dataInicio).length >= 7) ? String(dataInicio).slice(0, 7) : '2026-10';
    try {
      const resp = await fetch(`${API_BASE}/ferias/${feriasId}/integrar-folha`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ competencia })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao integrar férias na folha.', 'error');
        return;
      }
      exibirToast(`Férias integradas à folha da competência ${competencia}!`, 'success');
      await this.carregarFerias();
    } catch (e) {
      exibirToast('Erro ao integrar férias à folha.', 'error');
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
    tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted" style="padding: 2rem;">Carregando afastamentos...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/afastamentos`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar afastamentos');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted" style="padding: 2rem;">Nenhum afastamento registrado.</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(a => {
        const tr = document.createElement('tr');
        const nomeColab = a.nome_completo || a.nome_colaborador || `Colaborador #${a.colaborador_id}`;
        const estabFim = a.estabilidade_fim || a.data_fim_estabilidade;
        const encerrado = Boolean(a.data_retorno_efetivo);
        tr.innerHTML = `
          <td><strong>${nomeColab}</strong></td>
          <td>${a.tipo || a.motivo || '-'}</td>
          <td>${a.cid || a.codigo_cid || '-'}</td>
          <td>${a.data_inicio}</td>
          <td>${a.data_fim_prevista || a.data_retorno_efetivo || 'Indeterminado'}</td>
          <td>${a.dias_empresa || 0}d</td>
          <td>${a.dias_inss || 0}d</td>
          <td>${estabFim || a.tem_estabilidade ? `<span class="badge-severidade-alta">Estabilidade até ${estabFim || '12 meses'}</span>` : 'Não'}</td>
          <td><span class="badge-status badge-calculada">${encerrado ? 'ENCERRADO' : String(a.status_esocial || 'ATIVO').toUpperCase()}</span></td>
          <td class="text-right">
            <div style="display:flex; gap:0.25rem; justify-content:flex-end; flex-wrap:wrap;">
              ${!encerrado ? `<button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.prorrogarAfastamento(${a.id}, '${a.data_fim_prevista || a.data_inicio}')">Prorrogar</button>` : ''}
              ${!encerrado ? `<button type="button" class="btn btn-primary btn-sm" onclick="PlataformaManager.registrarRetornoAfastamento(${a.id})">Retorno</button>` : ''}
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="10" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar afastamentos.</td></tr>';
    }
  },

  async prorrogarAfastamento(afastId, dataFimAtual) {
    const novaData = prompt('Informe a nova data de término previsto (AAAA-MM-DD):', dataFimAtual || '');
    if (!novaData) return;
    const motivo = prompt('Motivo da prorrogação (ex.: perícia INSS / atestado médico):') || 'Prorrogação médica';
    try {
      const resp = await fetch(`${API_BASE}/afastamentos/${afastId}/prorrogar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ nova_data_fim: novaData.trim(), motivo })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao prorrogar afastamento.', 'error');
        return;
      }
      exibirToast('Afastamento prorrogado com recálculo Empresa/INSS!', 'success');
      await this.carregarAfastamentos();
    } catch (e) {
      exibirToast('Erro de rede ao prorrogar afastamento.', 'error');
    }
  },

  async registrarRetornoAfastamento(afastId) {
    const hoje = new Date().toISOString().slice(0, 10);
    const dataRet = prompt('Data efetiva do retorno (AAAA-MM-DD):', hoje);
    if (!dataRet) return;
    try {
      const resp = await fetch(`${API_BASE}/afastamentos/${afastId}/retorno`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ data_retorno: dataRet.trim() })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao registrar retorno (verifique ASO de retorno se >= 30 dias).', 'error');
        return;
      }
      exibirToast('Retorno registrado, colaborador reativado e S-2230 de término gerado!', 'success');
      await this.carregarAfastamentos();
    } catch (e) {
      exibirToast('Erro ao registrar retorno de afastamento.', 'error');
    }
  },

  async exportarRelatorioAfastamentosCSV() {
    try {
      const resp = await fetch(`${API_BASE}/afastamentos/relatorio`, { headers: getAuthHeaders(), credentials: 'include' });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao gerar relatório de afastamentos.', 'error');
        return;
      }
      const dados = json.dados || {};
      const lista = Array.isArray(dados) ? dados : (dados.registros || dados.afastamentos || []);
      const linhas = lista.map(a => [
        a.nome_completo || `#${a.colaborador_id}`,
        a.tipo || '-',
        a.cid || '-',
        a.data_inicio || '-',
        a.data_fim_prevista || '-',
        a.dias_empresa || 0,
        a.dias_inss || 0,
        a.estabilidade_fim || 'Não'
      ]);
      this.exportarCSVGenerico(
        ['Colaborador', 'Tipo', 'CID-10', 'Início', 'Término Previsto', 'Dias Empresa', 'Dias INSS', 'Estabilidade Até'],
        linhas,
        `afastamentos_${new Date().toISOString().slice(0, 10)}.csv`
      );
    } catch (e) {
      exibirToast('Erro ao exportar relatório de afastamentos.', 'error');
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
    tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Carregando rescisões...</td></tr>';

    try {
      const resp = await fetch(`${API_BASE}/rescisoes`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro ao listar rescisões');
      const json = await resp.json();
      const lista = json.dados || [];

      if (lista.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted" style="padding: 2rem;">Nenhuma rescisão calculada. Clique em "Calcular Nova Rescisão".</td></tr>';
        return;
      }

      tbody.innerHTML = '';
      lista.forEach(r => {
        const tr = document.createElement('tr');
        const verbasFmt = Number(r.valor_liquido || r.total_rescisao_liquido || r.total_verbas || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const multaFmt = Number(r.multa_fgts_valor || r.multa_rescisoria_fgts || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        const nomeColab = r.nome_completo || r.nome_colaborador || `Colaborador #${r.colaborador_id}`;
        const statusStr = String(r.status || 'calculada').toLowerCase();

        tr.innerHTML = `
          <td><strong>${nomeColab}</strong></td>
          <td>${r.tipo_rescisao}</td>
          <td>${r.data_comunicacao || r.data_aviso_previo || '-'}</td>
          <td>${r.data_afastamento || r.data_desligamento || '-'}</td>
          <td><strong style="color: #2563eb;">${r.data_limite_pagamento || '-'}</strong></td>
          <td><strong>${verbasFmt}</strong></td>
          <td>${multaFmt}</td>
          <td><span class="badge-status badge-fechada">${statusStr.toUpperCase()}</span></td>
          <td class="text-right">
            <div style="display:flex; gap:0.25rem; justify-content:flex-end; flex-wrap:wrap;">
              <button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.baixarArquivoAutenticado('${API_BASE}/rescisoes/${r.id}/pdf?tipo=trct', 'TRCT_${r.id}.pdf')">TRCT PDF</button>
              <button type="button" class="btn btn-outline btn-sm" onclick="PlataformaManager.baixarArquivoAutenticado('${API_BASE}/rescisoes/${r.id}/pdf?tipo=guias', 'Guias_FGTS_SD_${r.id}.pdf')">Guias PDF</button>
              ${statusStr === 'calculada' ? `<button type="button" class="btn btn-primary btn-sm" onclick="PlataformaManager.homologarRescisao(${r.id})">Homologar</button>` : ''}
              ${statusStr === 'homologada' ? `<button type="button" class="btn btn-primary btn-sm" onclick="PlataformaManager.pagarRescisao(${r.id})">Quitar</button>` : ''}
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center text-danger" style="padding: 2rem;">Erro ao carregar rescisões.</td></tr>';
    }
  },

  async homologarRescisao(rescisaoId) {
    try {
      const resp = await fetch(`${API_BASE}/rescisoes/${rescisaoId}/homologar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ observacao: 'Homologado via interface DP' })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao homologar rescisão.', 'error');
        return;
      }
      exibirToast('Rescisão homologada com evento S-2299 pronto na fila!', 'success');
      await this.carregarRescisoes();
    } catch (e) {
      exibirToast('Erro ao homologar rescisão.', 'error');
    }
  },

  async pagarRescisao(rescisaoId) {
    const hoje = new Date().toISOString().slice(0, 10);
    const dataPg = prompt('Data de quitação das verbas rescisórias (AAAA-MM-DD):', hoje);
    if (!dataPg) return;
    try {
      const resp = await fetch(`${API_BASE}/rescisoes/${rescisaoId}/pagar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ data_pagamento: dataPg.trim() })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao registrar pagamento da rescisão.', 'error');
        return;
      }
      exibirToast(json.mensagem || 'Quitação rescisória registrada com sucesso!', 'success');
      await this.carregarRescisoes();
    } catch (e) {
      exibirToast('Erro ao registrar pagamento da rescisão.', 'error');
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
          const resUp = String(a.resultado || a.resultado_aptidao || 'APTO').toUpperCase();
          tbodyAso.innerHTML += `
            <tr>
              <td><strong>${a.nome_completo || a.nome_colaborador || `Colaborador #${a.colaborador_id}`}</strong></td>
              <td>${a.tipo_aso || a.tipo_exame || '-'}</td>
              <td>${a.data_emissao || a.data_exame || '-'}</td>
              <td>${a.data_validade || '-'}</td>
              <td><span class="badge-status ${resUp === 'APTO' ? 'badge-fechada' : 'badge-severidade-critica'}">${resUp}</span></td>
              <td>${a.medico_nome || a.medico_examinador_nome || '-'} (${a.medico_crm || a.medico_examinador_crm || '-'})</td>
              <td>${a.exames_complementares || 'Clínico Ocupacional'}</td>
            </tr>
          `;
        });
      }

      // EPIs
      const tbodyEpi = document.getElementById('tbody-sst-epis');
      if (tbodyEpi) {
        const epis = d.entregas_epi || d.epis_entregas || [];
        tbodyEpi.innerHTML = epis.length ? '' : '<tr><td colspan="6" class="text-center text-muted" style="padding: 2rem;">Nenhuma entrega de EPI registrada.</td></tr>';
        epis.forEach(e => {
          tbodyEpi.innerHTML += `
            <tr>
              <td><strong>${e.nome_completo || e.nome_colaborador || `Colaborador #${e.colaborador_id}`}</strong></td>
              <td>${e.epi_nome || e.nome_epi || '-'}</td>
              <td><strong>CA: ${e.ca_numero || e.numero_ca || '-'}</strong></td>
              <td>${e.data_prevista_troca || e.validade_ca || '-'}</td>
              <td>${e.data_entrega}</td>
              <td><span class="badge-status badge-fechada">${e.ciencia_colaborador || e.termo_assinado ? 'Assinado / Biometria' : 'Pendente'}</span></td>
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
              <td><strong>${t.titulo || t.nome_treinamento}</strong> (${t.nr_referencia || t.norma_regulamentadora || 'NR'})</td>
              <td>${t.carga_horaria_horas} horas</td>
              <td>${t.validade_meses} meses</td>
              <td>${t.obrigatorio || t.reciclagem_obrigatoria ? 'Sim' : 'Não'}</td>
              <td><strong>${t.total_participantes || 1}</strong></td>
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
              <td>${c.nome_completo || c.nome_colaborador || `Colaborador #${c.colaborador_id}`}</td>
              <td>${c.tipo_acidente}</td>
              <td>${c.data_hora_acidente}</td>
              <td>${c.descricao_detalhada || c.parte_corpo_atingida || c.local_acidente || '-'}</td>
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
        const stUp = String(ev.status || 'validado').toUpperCase();
        tr.innerHTML = `
          <td><strong>${ev.tipo_evento}</strong></td>
          <td>${ev.ambiente || ev.descricao || ev.tipo_evento}</td>
          <td>${ev.criado_em || ev.competencia || ev.data_geracao || '-'}</td>
          <td>${ev.nome_colaborador || (ev.identificador_origem ? `Origem #${ev.identificador_origem}` : 'Empresa / Tabela')}</td>
          <td><span class="badge-status ${stUp === 'ACEITO' || stUp === 'TRANSMITIDO' || stUp === 'PROCESSADO' ? 'badge-fechada' : 'badge-calculada'}">${stUp}</span></td>
          <td><span class="text-xs font-mono">${ev.numero_recibo || ev.protocolo_envio || ev.recibo_entrega || 'Pendente de envio'}</span></td>
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
      pre.textContent = ev.xml_conteudo || ev.xml_gerado || 'XML ainda não gerado para este evento no servidor.';
      modal.classList.remove('hidden');
    }
  },

  async transmitirLoteESocial() {
    if (!confirm('Deseja validar o schema XML e enfileirar/simular a transmissão do lote eSocial? (Transmissão produtiva requer Certificado ICP-Brasil A1/A3.)')) return;

    try {
      const resp = await fetch(`${API_BASE}/esocial/transmitir`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({})
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao validar/processar lote eSocial.', 'error');
        return;
      }
      exibirToast(json.mensagem || 'Lote eSocial validado localmente em modo simulação.', json.erros_schema > 0 ? 'warning' : 'success');
      await this.carregarESocial();
    } catch (e) {
      exibirToast('Erro de conexão ao processar lote eSocial.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // INTEGRAÇÕES BANCÁRIAS — REMESSA CNAB 240 (RF-097, RF-178)
  // --------------------------------------------------------------------------
  async gerarCNAB240() {
    const banco = document.getElementById('cnab-banco-select')?.value || '001';
    const competencia = document.getElementById('cnab-competencia-input')?.value || '2026-03';
    const dataPagamento = document.getElementById('cnab-data-pagamento')?.value;
    const tipoPagamento = document.getElementById('cnab-tipo-pagamento')?.value || 'folha_mensal';

    try {
      const resp = await fetch(`${API_BASE}/integracoes/cnab`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          codigo_banco: banco,
          competencia: competencia,
          data_pagamento: dataPagamento,
          tipo_pagamento: tipoPagamento
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao gerar remessa CNAB.', 'error');
        return;
      }

      const d = json.dados || json || {};
      this.cnabArquivoGerado = d.conteudo_cnab || d.arquivo_conteudo || '';
      const totReg = d.total_colaboradores ?? d.total_registros ?? 0;
      const valTot = d.valor_total_liquido ?? d.valor_total ?? 0;

      const resumo = document.getElementById('cnab-resumo-lote');
      const preview = document.getElementById('cnab-conteudo-preview');
      const btnDownload = document.getElementById('btn-download-cnab');

      if (resumo) {
        resumo.innerHTML = `
          <strong style="color: #16a34a;">Remessa gerada com sucesso (${tipoPagamento})!</strong><br>
          &bull; Banco: <strong>${d.banco_nome || banco}</strong> | Arquivo: <strong>${d.nome_arquivo || 'REMESSA.REM'}</strong><br>
          &bull; Total de Colaboradores Creditados: <strong>${totReg}</strong><br>
          &bull; Valor Total do Lote: <strong>R$ ${Number(valTot).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</strong>
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

  async processarRetornoCNAB240() {
    const conteudo = document.getElementById('cnab-retorno-conteudo')?.value || '';
    const resumo = document.getElementById('cnab-retorno-resumo');
    if (!conteudo.trim()) {
      exibirToast('Cole o conteúdo do arquivo de retorno CNAB 240 antes de processar.', 'warning');
      return;
    }
    try {
      const resp = await fetch(`${API_BASE}/integracoes/cnab/retorno`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          nome_arquivo: `retorno_${new Date().toISOString().slice(0, 10)}.ret`,
          conteudo_retorno: conteudo
        })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao processar retorno bancário.', 'error');
        return;
      }
      const d = json.dados || json || {};
      if (resumo) {
        resumo.innerHTML = `<strong style="color:#16a34a;">Retorno processado:</strong> Liquidados: <strong>${d.liquidados ?? 0}</strong> | Rejeitados: <strong>${d.rejeitados ?? 0}</strong>`;
      }
      exibirToast('Retorno bancário CNAB 240 processado com sucesso!', 'success');
    } catch (e) {
      exibirToast('Erro de comunicação ao processar retorno CNAB.', 'error');
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
          <td>${log.criado_em || log.data_hora || '-'}</td>
          <td><strong>${log.usuario_responsavel || log.usuario_nome || log.usuario_id || 'Sistema'}</strong></td>
          <td><span class="badge-status badge-calculada">${String(log.operacao || log.tipo_operacao || log.acao || 'ACAO').toUpperCase()}</span></td>
          <td>${log.modulo || log.registro_tipo || log.tabela_afetada || '-'}</td>
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
      const raw = json.dados || {};
      const lista = Array.isArray(raw) ? raw : (raw.empresas || []);

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
          <td>${emp.cnae_principal || '1071-6/00'}</td>
          <td>Grau ${emp.grau_risco_rat || emp.grau_risco || 3}</td>
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
  // ROTINAS ENTERPRISE DA FOLHA (RF-081 A RF-105: 13º, LOTE, RATEIO, FINANCEIRO)
  // --------------------------------------------------------------------------
  exibirPainelFolhaEnterprise(titulo, html) {
    const sec = document.getElementById('folha-painel-resultado-enterprise');
    const elT = document.getElementById('folha-resultado-enterprise-titulo');
    const elC = document.getElementById('folha-resultado-enterprise-corpo');
    if (elT) elT.textContent = titulo;
    if (elC) elC.innerHTML = html;
    if (sec) sec.classList.remove('hidden');
  },

  async executarDecimoTerceiroLote() {
    const comp = document.getElementById('filtro-folha-competencia')?.value || '2026-11';
    const anoBase = parseInt(comp.slice(0, 4), 10) || 2026;
    const parcStr = prompt('Parcela do 13º salário a calcular em lote (1 ou 2):', comp.endsWith('-12') ? '2' : '1');
    if (!parcStr) return;
    const parcela = parseInt(parcStr, 10) === 2 ? 2 : 1;
    try {
      const resp = await fetch(`${API_BASE}/folha/decimo-terceiro`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ ano_base: anoBase, parcela })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao calcular 13º em lote.', 'error');
        return;
      }
      const d = json.dados || {};
      const itens = d.itens || [];
      this.exibirPainelFolhaEnterprise(
        `13º Salário — ${parcela}ª Parcela / ${anoBase} (${itens.length} colaboradores)`,
        `<p>Processados: <strong>${itens.length}</strong> | Erros: <strong>${(d.erros || []).length}</strong></p>
         <table class="data-table"><thead><tr><th>Colaborador</th><th>Avos</th><th>Bruto</th><th>INSS</th><th>IRRF</th><th>Líquido</th></tr></thead><tbody>
         ${itens.map(i => `<tr><td>${i.colaborador_nome || i.colaborador_id}</td><td>${i.avos}/12</td><td>R$ ${Number(i.valor_bruto || 0).toFixed(2)}</td><td>R$ ${Number(i.desconto_inss || 0).toFixed(2)}</td><td>R$ ${Number(i.desconto_irrf || 0).toFixed(2)}</td><td><strong>R$ ${Number(i.valor_liquido || 0).toFixed(2)}</strong></td></tr>`).join('')}
         </tbody></table>`
      );
      exibirToast(json.mensagem || '13º salário calculado com sucesso!', 'success');
    } catch (e) {
      exibirToast('Erro de rede ao calcular 13º salário.', 'error');
    }
  },

  async carregarConferenciaAnalitica() {
    const comp = document.getElementById('filtro-folha-competencia')?.value || '2026-10';
    try {
      const resp = await fetch(`${API_BASE}/folha/conferencia-analitica?competencia=${encodeURIComponent(comp)}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro na conferência analítica.', 'error');
        return;
      }
      const d = json.dados || {};
      const divg = d.divergencias || [];
      this.exibirPainelFolhaEnterprise(
        `Conferência Analítica — Competência ${comp}`,
        `<p>Folhas avaliadas: <strong>${d.total_folhas || 0}</strong> | Divergências detectadas: <strong>${divg.length}</strong> | Líquido total: <strong>R$ ${Number(d.total_liquido || 0).toFixed(2)}</strong></p>
         ${divg.length ? `<ul>${divg.map(x => `<li>${x.colaborador || x.colaborador_id}: ${x.motivo || JSON.stringify(x)}</li>`).join('')}</ul>` : '<p class="text-success">Nenhuma inconsistência encontrada.</p>'}`
      );
    } catch (e) {
      exibirToast('Erro ao consultar conferência analítica.', 'error');
    }
  },

  async fecharCompetenciaFolhaLote() {
    const comp = document.getElementById('filtro-folha-competencia')?.value || '2026-10';
    if (!confirm(`Deseja fechar em lote todas as folhas calculadas/aprovadas de ${comp}?`)) return;
    try {
      const resp = await fetch(`${API_BASE}/folha/fechar-lote`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ competencia: comp })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao fechar competência em lote.', 'error');
        return;
      }
      const d = json.dados || {};
      exibirToast(`Lote ${comp}: ${d.fechadas ?? 0} folha(s) fechada(s)!`, 'success');
      if (typeof FolhaManager !== 'undefined' && FolhaManager.carregarFolhas) await FolhaManager.carregarFolhas();
    } catch (e) {
      exibirToast('Erro de comunicação ao fechar competência em lote.', 'error');
    }
  },

  async gerarRateioCentroCusto() {
    const comp = document.getElementById('filtro-folha-competencia')?.value || '2026-10';
    try {
      const resp = await fetch(`${API_BASE}/folha/rateio-centro-custo`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ competencia: comp })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao gerar rateio.', 'error');
        return;
      }
      const d = json.dados || {};
      const linhas = d.centros_custo || d.itens || [];
      this.exibirPainelFolhaEnterprise(
        `Rateio por Centro de Custo — ${comp}`,
        `<table class="data-table"><thead><tr><th>Centro de Custo / Setor</th><th>Colaboradores</th><th>Bruto</th><th>FGTS</th><th>Custo Total</th></tr></thead><tbody>
        ${linhas.length ? linhas.map(c => `<tr><td>${c.centro_custo || c.setor || '-'}</td><td>${c.qtd_colaboradores ?? 0}</td><td>R$ ${Number(c.total_proventos || 0).toFixed(2)}</td><td>R$ ${Number(c.total_fgts || 0).toFixed(2)}</td><td><strong>R$ ${Number(c.custo_total_empresa || c.total_liquido || 0).toFixed(2)}</strong></td></tr>`).join('') : '<tr><td colspan="5" class="text-center text-muted">Nenhum rateio gerado para a competência.</td></tr>'}
        </tbody></table>`
      );
      exibirToast(json.mensagem || 'Rateio consolidado!', 'success');
    } catch (e) {
      exibirToast('Erro ao gerar rateio por centro de custo.', 'error');
    }
  },

  async gerarIntegracaoFinanceira() {
    const comp = document.getElementById('filtro-folha-competencia')?.value || '2026-10';
    try {
      const resp = await fetch(`${API_BASE}/folha/integracao-financeira`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ competencia: comp })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao gerar integração financeira.', 'error');
        return;
      }
      const d = json.dados || {};
      const lancs = d.lancamentos || [];
      this.exibirPainelFolhaEnterprise(
        `Integração Financeira e Contábil — ${comp}`,
        `<table class="data-table"><thead><tr><th>Categoria / Guia</th><th>Valor</th><th>Vencimento</th><th>Status</th></tr></thead><tbody>
        ${lancs.length ? lancs.map(l => `<tr><td>${l.categoria || l.descricao || '-'}</td><td><strong>R$ ${Number(l.valor || 0).toFixed(2)}</strong></td><td>${l.data_vencimento || '-'}</td><td>${l.status || 'gerado'}</td></tr>`).join('') : '<tr><td colspan="4" class="text-center text-muted">Nenhum lançamento gerado.</td></tr>'}
        </tbody></table>`
      );
      exibirToast(json.mensagem || 'Lançamentos financeiros gerados!', 'success');
    } catch (e) {
      exibirToast('Erro ao gerar integração financeira.', 'error');
    }
  },

  async gerarEsocialPeriodicosFolha() {
    const comp = document.getElementById('filtro-folha-competencia')?.value || '2026-10';
    try {
      const resp = await fetch(`${API_BASE}/folha/esocial-periodicos`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ competencia: comp })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Erro ao gerar eventos periódicos eSocial.', 'error');
        return;
      }
      const d = json.dados || {};
      exibirToast(`Eventos periódicos S-1200/S-1210/S-1299 gerados para ${comp}: ${(d.eventos_gerados || []).length} evento(s).`, 'success');
    } catch (e) {
      exibirToast('Erro ao gerar eventos periódicos eSocial.', 'error');
    }
  },

  // --------------------------------------------------------------------------
  // PORTAIS ENTERPRISE: PORTAL DO COLABORADOR E PORTAL DO GESTOR
  // --------------------------------------------------------------------------
  async carregarPortalColaborador() {
    await this.carregarColaboradoresCache();
    const colab = (this.colaboradoresCache && this.colaboradoresCache.length > 0) ? this.colaboradoresCache[0] : null;

    const elNome = document.getElementById('colab-nome-display');
    const elCargo = document.getElementById('colab-cargo-display');
    const elBadge = document.getElementById('colab-situacao-badge');
    const elAdmissao = document.getElementById('colab-admissao-display');
    const elDepto = document.getElementById('colab-departamento-display');

    if (colab) {
      if (elNome) elNome.textContent = colab.nome_completo || 'Colaborador';
      if (elCargo) elCargo.innerHTML = `${colab.cargo || '-'} &bull; Matrícula: <strong id="colab-matricula-display">${colab.matricula || '-'}</strong>`;
      if (elBadge) elBadge.textContent = `${String(colab.situacao || 'ativo').toUpperCase()} (${colab.tipo_contrato || 'CLT'})`;
      if (elAdmissao) elAdmissao.textContent = `Admissão: ${formatarDataBR(colab.data_admissao) || '-'}`;
      if (elDepto) elDepto.textContent = `Departamento: ${colab.setor || '-'}`;

      // Carregar holerites reais
      try {
        const respF = await fetch(`${API_BASE}/folha?colaborador_id=${colab.id}`, { headers: getAuthHeaders(), credentials: 'include' });
        const jsonF = await respF.json();
        const folhas = jsonF.dados || [];
        const tbH = document.getElementById('tbody-meus-holerites');
        const elUlt = document.getElementById('colab-ultimo-holerite');
        if (elUlt) elUlt.textContent = folhas.length ? `Competência ${folhas[0].competencia}` : 'Sem folhas';
        if (tbH) {
          tbH.innerHTML = folhas.length ? folhas.map(fl => `
            <tr>
              <td><strong>${fl.competencia}</strong></td>
              <td>${fl.tipo_folha || 'mensal'}</td>
              <td>R$ ${Number(fl.salario_base || 0).toFixed(2)}</td>
              <td class="text-success">R$ ${Number(fl.total_proventos || 0).toFixed(2)}</td>
              <td class="text-danger">R$ ${Number(fl.total_descontos || 0).toFixed(2)}</td>
              <td><strong class="text-primary">R$ ${Number(fl.salario_liquido || 0).toFixed(2)}</strong></td>
              <td><button class="btn btn-outline btn-sm" onclick="PlataformaManager.baixarArquivoAutenticado('${API_BASE}/folha/${fl.id}/pdf', 'holerite_${fl.competencia}.pdf')">Baixar PDF</button></td>
            </tr>`).join('') : '<tr><td colspan="7" class="text-center text-muted" style="padding:1.5rem;">Nenhum holerite processado para este colaborador.</td></tr>';
        }
      } catch (_) {}

      // Carregar espelho de ponto real
      try {
        const compAtual = new Date().toISOString().slice(0, 7);
        const respP = await fetch(`${API_BASE}/ponto/espelho?colaborador_id=${colab.id}&competencia=${compAtual}`, { headers: getAuthHeaders(), credentials: 'include' });
        const jsonP = await respP.json();
        const esp = jsonP.dados || {};
        const tbP = document.getElementById('tbody-meu-espelho-ponto');
        const elBanco = document.getElementById('colab-saldo-banco');
        const bancoMin = Number(esp.totais?.banco_horas_saldo_min ?? 0);
        if (elBanco) elBanco.textContent = `${(bancoMin / 60).toFixed(1)}h`;
        const grade = esp.grade_dias || [];
        if (tbP) {
          tbP.innerHTML = grade.length ? grade.slice(0, 15).map(g => {
            const b = g.batidas || [];
            return `<tr><td>${g.data}</td><td>${b[0] || '--:--'}</td><td>${b[1] || '--:--'}</td><td>${b[2] || '--:--'}</td><td>${b[3] || '--:--'}</td><td><strong>${Number(g.horas_trab || 0).toFixed(2)}h</strong></td><td>${Number((g.he_50 || 0) + (g.he_100 || 0)).toFixed(2)}h</td><td><span class="badge-status badge-calculada">${g.incons_msg ? 'Ajuste' : 'Regular'}</span></td></tr>`;
          }).join('') : '<tr><td colspan="8" class="text-center text-muted" style="padding:1.5rem;">Sem registros de ponto nesta competência.</td></tr>';
        }
      } catch (_) {}

      // Carregar períodos aquisitivos reais
      try {
        const respPA = await fetch(`${API_BASE}/ferias/periodos-aquisitivos?colaborador_id=${colab.id}`, { headers: getAuthHeaders(), credentials: 'include' });
        const jsonPA = await respPA.json();
        const pas = jsonPA.dados || [];
        const saldoTot = pas.reduce((acc, p) => acc + Number(p.dias_saldo ?? 0), 0);
        const elFerias = document.getElementById('colab-ferias-saldo');
        if (elFerias) elFerias.textContent = `${saldoTot} dias`;
        const tbFer = document.getElementById('tbody-minhas-ferias');
        if (tbFer) {
          tbFer.innerHTML = pas.length ? pas.map(p => `
            <tr><td>${p.data_inicio} a ${p.data_fim}</td><td>${p.data_limite_concessivo || '-'}</td><td>${p.dias_direito ?? 30} dias</td><td>${p.dias_gozados ?? 0} dias</td><td><strong>${p.dias_saldo ?? 0} dias</strong></td><td><span class="badge-status badge-calculada">${p.status || 'ativo'}</span></td></tr>`).join('') : '<tr><td colspan="6" class="text-center text-muted" style="padding:1.5rem;">Nenhum período aquisitivo encontrado.</td></tr>';
        }
      } catch (_) {}
    } else {
      if (elNome) elNome.textContent = 'Nenhum colaborador ativo encontrado';
    }

    // Alternância de abas do portal
    const tabs = ['holerites', 'espelho', 'ferias', 'informes'];
    tabs.forEach(tabKey => {
      const btn = document.getElementById(`tab-btn-${tabKey}`);
      if (btn && !btn.dataset.bound) {
        btn.dataset.bound = 'true';
        btn.addEventListener('click', () => {
          tabs.forEach(k => {
            document.getElementById(`tab-btn-${k}`)?.classList.remove('active');
            document.getElementById(`pane-${k}`)?.classList.add('hidden');
          });
          btn.classList.add('active');
          document.getElementById(`pane-${tabKey}`)?.classList.remove('hidden');
        });
      }
    });

    const btnBater = document.getElementById('btn-colab-bater-ponto');
    if (btnBater && !btnBater.dataset.bound) {
      btnBater.dataset.bound = 'true';
      btnBater.addEventListener('click', () => {
        const modalPonto = document.getElementById('modal-registrar-ponto');
        if (modalPonto) {
          const inputDataHora = document.getElementById('ponto-datahora-registro');
          if (inputDataHora) inputDataHora.value = new Date().toISOString().slice(0, 16);
          modalPonto.classList.remove('hidden');
        }
      });
    }

    const btnSolicitarFerias = document.getElementById('btn-colab-solicitar-ferias');
    if (btnSolicitarFerias && !btnSolicitarFerias.dataset.bound) {
      btnSolicitarFerias.dataset.bound = 'true';
      btnSolicitarFerias.addEventListener('click', () => {
        document.getElementById('modal-programar-ferias')?.classList.remove('hidden');
      });
    }

    const btnAjustePonto = document.getElementById('btn-solicitar-ajuste-ponto');
    if (btnAjustePonto && !btnAjustePonto.dataset.bound) {
      btnAjustePonto.dataset.bound = 'true';
      btnAjustePonto.addEventListener('click', () => {
        document.getElementById('modal-ajuste-ponto')?.classList.remove('hidden');
      });
    }
  },

  async carregarPortalGestor() {
    await this.carregarColaboradoresCache();
    const equipe = this.colaboradoresCache || [];

    const totalEl = document.getElementById('kpi-gestor-equipe-total');
    const presentesEl = document.getElementById('kpi-gestor-presentes');
    const feriasEl = document.getElementById('kpi-gestor-ferias');
    const pendEl = document.getElementById('kpi-gestor-aprovacoes-pendentes');

    const ativos = equipe.filter(c => String(c.situacao || '').toLowerCase() === 'ativo');
    if (totalEl) totalEl.textContent = equipe.length;
    if (presentesEl) presentesEl.textContent = ativos.length;

    const tbEq = document.getElementById('tbody-equipe-gestor');
    if (tbEq) {
      tbEq.innerHTML = equipe.length ? equipe.slice(0, 20).map(c => `
        <tr>
          <td><strong>${c.nome_completo}</strong></td>
          <td>${c.matricula || '-'}</td>
          <td>${c.cargo || '-'}</td>
          <td>${c.carga_horaria_mensal || 220}h</td>
          <td><span class="badge-status badge-calculada">${String(c.situacao || 'ativo').toUpperCase()}</span></td>
          <td>--</td>
        </tr>`).join('') : '<tr><td colspan="6" class="text-center text-muted" style="padding:1.5rem;">Nenhum colaborador encontrado.</td></tr>';
    }

    try {
      const [respPend, respFer] = await Promise.all([
        fetch(`${API_BASE}/pendencias`, { headers: getAuthHeaders(), credentials: 'include' }),
        fetch(`${API_BASE}/ferias`, { headers: getAuthHeaders(), credentials: 'include' })
      ]);
      const pJson = respPend.ok ? await respPend.json() : { dados: [] };
      const fJson = respFer.ok ? await respFer.json() : { dados: [] };
      const pendencias = (pJson.dados || []).filter(p => String(p.status || 'aberta') === 'aberta');
      const feriasPend = (fJson.dados || []).filter(f => String(f.status || '').toLowerCase() === 'solicitada');
      const emFeriasHoje = (fJson.dados || []).filter(f => String(f.status || '').toLowerCase() === 'em_gozo');

      if (feriasEl) feriasEl.textContent = emFeriasHoje.length;
      if (pendEl) pendEl.textContent = pendencias.length + feriasPend.length;

      const tbApr = document.getElementById('tbody-aprovacoes-gestor');
      if (tbApr) {
        const linhas = [
          ...feriasPend.map(f => `
            <tr data-kind="ferias" data-id="${f.id}">
              <td><input type="checkbox" class="chk-gestor-item"></td>
              <td><strong>${f.nome_completo || f.colaborador_id}</strong></td>
              <td><span class="badge-status badge-calculada">Programação Férias</span></td>
              <td>${f.data_inicio || '-'} a ${f.data_fim || '-'}</td>
              <td>${f.dias_gozo || 0}d gozo</td>
              <td><span class="badge-status badge-aberta">Pendente Gestor</span></td>
              <td><div class="btn-group-actions">
                <button class="btn btn-primary btn-sm" onclick="PlataformaManager.processarAcaoGestor(this, 'ferias', ${f.id}, true)">Aprovar</button>
                <button class="btn btn-outline btn-sm text-danger" onclick="PlataformaManager.processarAcaoGestor(this, 'ferias', ${f.id}, false)">Rejeitar</button>
              </div></td>
            </tr>`),
          ...pendencias.slice(0, 15).map(p => `
            <tr data-kind="pendencia" data-id="${p.id}">
              <td><input type="checkbox" class="chk-gestor-item"></td>
              <td><strong>${p.colaborador_nome || p.modulo || 'Operação DP'}</strong></td>
              <td><span class="badge-status badge-aberta">${p.modulo || 'Pendência'}</span></td>
              <td>${p.prazo_limite || '-'}</td>
              <td>${p.descricao || p.titulo || '-'}</td>
              <td><span class="badge-status badge-aberta">${p.severidade || 'Aberta'}</span></td>
              <td><div class="btn-group-actions">
                <button class="btn btn-primary btn-sm" onclick="PlataformaManager.processarAcaoGestor(this, 'pendencia', ${p.id}, true)">Resolver</button>
              </div></td>
            </tr>`)
        ];
        tbApr.innerHTML = linhas.length ? linhas.join('') : '<tr><td colspan="7" class="text-center text-muted" style="padding:1.5rem;">Nenhuma aprovação pendente no momento.</td></tr>';
      }
    } catch (_) {}

    const chkAll = document.getElementById('chk-gestor-select-all');
    if (chkAll && !chkAll.dataset.bound) {
      chkAll.dataset.bound = 'true';
      chkAll.addEventListener('change', (e) => {
        document.querySelectorAll('.chk-gestor-item').forEach(chk => { chk.checked = e.target.checked; });
      });
    }

    const btnLote = document.getElementById('btn-gestor-aprovar-lote');
    if (btnLote && !btnLote.dataset.bound) {
      btnLote.dataset.bound = 'true';
      btnLote.addEventListener('click', async () => {
        const selecionados = Array.from(document.querySelectorAll('.chk-gestor-item:checked'));
        if (selecionados.length === 0) {
          exibirToast('Selecione ao menos uma pendência para aprovar.', 'warning');
          return;
        }
        for (const chk of selecionados) {
          const tr = chk.closest('tr');
          if (tr?.dataset.kind && tr?.dataset.id) {
            await this.processarAcaoGestor(tr.querySelector('button'), tr.dataset.kind, parseInt(tr.dataset.id, 10), true);
          }
        }
      });
    }
  },

  async processarAcaoGestor(btn, kind, itemId, aprovado) {
    try {
      if (kind === 'ferias') {
        const resp = await fetch(`${API_BASE}/ferias/${itemId}/aprovar`, {
          method: 'POST',
          headers: getAuthHeaders(),
          credentials: 'include',
          body: JSON.stringify({ aprovar: Boolean(aprovado) })
        });
        if (!resp.ok) {
          const j = await resp.json();
          exibirToast(j.mensagem || 'Erro ao processar férias.', 'error');
          return;
        }
      } else if (kind === 'pendencia') {
        const resp = await fetch(`${API_BASE}/pendencias/${itemId}/resolver`, {
          method: 'POST',
          headers: getAuthHeaders(),
          credentials: 'include',
          body: JSON.stringify({})
        });
        if (!resp.ok) {
          const j = await resp.json();
          exibirToast(j.mensagem || 'Erro ao resolver pendência.', 'error');
          return;
        }
      }
      exibirToast(aprovado ? 'Item homologado no servidor!' : 'Item rejeitado.', aprovado ? 'success' : 'warning');
      await this.carregarPortalGestor();
    } catch (e) {
      exibirToast('Erro de comunicação ao processar ação do gestor.', 'error');
    }
  },

  async carregarBeneficiosCatalogo() {
    if (typeof BeneficiosManager !== 'undefined') {
      await BeneficiosManager.carregarTudo();
    }
  },

  async exportarColaboradoresCSV() {
    try {
      const lista = await DadosService.listar({ situacao: 'todos' });
      if (!lista || lista.length === 0) {
        exibirToast('Nenhum colaborador disponível para exportação.', 'warning');
        return;
      }
      const cabecalho = ['Matricula', 'Nome Completo', 'CPF', 'Cargo', 'Setor', 'Salario Base', 'Situacao'];
      const linhas = lista.map(c => [
        `"${c.matricula || ''}"`,
        `"${(c.nome_completo || '').replace(/"/g, '""')}"`,
        `"${c.cpf || ''}"`,
        `"${(c.cargo || '').replace(/"/g, '""')}"`,
        `"${(c.setor || '').replace(/"/g, '""')}"`,
        Number(c.salario_base || 0).toFixed(2),
        `"${c.situacao || ''}"`
      ].join(';'));
      const csv = '\uFEFF' + [cabecalho.join(';'), ...linhas].join('\n');
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `rh20_funcionarios_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      exibirToast(`Exportação de ${lista.length} funcionário(s) concluída!`, 'success');
    } catch (e) {
      exibirToast('Falha ao exportar relatório de funcionários.', 'error');
    }
  },

  async exportarFolhasCSV() {
    try {
      const resp = await fetch(`${API_BASE}/folha`, { headers: getAuthHeaders(), credentials: 'include' });
      if (!resp.ok) throw new Error('Erro API');
      const json = await resp.json();
      const folhas = json.dados || [];
      if (folhas.length === 0) {
        exibirToast('Nenhuma folha processada encontrada para exportação.', 'warning');
        return;
      }
      const cabecalho = ['Competencia', 'Colaborador', 'Matricula', 'Salario Base', 'Proventos', 'Descontos', 'Liquido', 'Situacao'];
      const linhas = folhas.map(f => [
        `"${f.competencia || ''}"`,
        `"${(f.colaborador_nome || '').replace(/"/g, '""')}"`,
        `"${f.colaborador_matricula || ''}"`,
        Number(f.salario_base_contratual || 0).toFixed(2),
        Number(f.total_proventos || 0).toFixed(2),
        Number(f.total_descontos || 0).toFixed(2),
        Number(f.salario_liquido || 0).toFixed(2),
        `"${f.situacao || ''}"`
      ].join(';'));
      const csv = '\uFEFF' + [cabecalho.join(';'), ...linhas].join('\n');
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `rh20_folha_analitica_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      exibirToast(`Exportação de ${folhas.length} folha(s) concluída!`, 'success');
    } catch (e) {
      exibirToast('Falha ao exportar relatório de folha.', 'error');
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

    // Modal Nova Admissão & Cartão Único Admissional (RF-011 a RF-020)
    document.getElementById('btn-abrir-nova-admissao')?.addEventListener('click', async () => {
      await this.carregarCatalogosAdmissao();
      document.getElementById('modal-nova-admissao')?.classList.remove('hidden');
    });
    document.getElementById('adm-candidato-cpf')?.addEventListener('input', (e) => { e.target.value = mascaraCpf(e.target.value); });
    document.getElementById('btn-fechar-modal-admissao')?.addEventListener('click', () => fecharModal('modal-nova-admissao'));
    document.getElementById('btn-cancelar-modal-admissao')?.addEventListener('click', () => fecharModal('modal-nova-admissao'));
    document.getElementById('btn-salvar-nova-admissao')?.addEventListener('click', () => this.salvarNovaAdmissao());

    document.getElementById('btn-fechar-cartao-admissional')?.addEventListener('click', () => {
      document.getElementById('cartao-processo-admissional')?.classList.add('hidden');
    });
    document.getElementById('btn-adm-chk-upload')?.addEventListener('click', () => this.uploadChecklistAdmissao());
    document.getElementById('btn-adm-salvar-jornada')?.addEventListener('click', () => this.salvarJornadaAdmissao());
    document.getElementById('btn-adm-salvar-cc')?.addEventListener('click', () => this.salvarCentroCustoAdmissao());
    document.getElementById('btn-adm-salvar-aso')?.addEventListener('click', () => this.salvarAsoAdmissional());
    document.getElementById('btn-adm-salvar-beneficios')?.addEventListener('click', () => this.salvarBeneficiosAdmissao());
    document.getElementById('btn-adm-executar-validacao')?.addEventListener('click', () => this.executarValidacaoAdmissional());
    document.getElementById('btn-adm-gerar-contrato')?.addEventListener('click', () => this.gerarContratoAdmissao());
    document.getElementById('btn-adm-gerar-esocial')?.addEventListener('click', () => this.gerarESocialAdmissao());
    document.getElementById('btn-adm-aprovar-final')?.addEventListener('click', () => this.aprovarAdmissaoPainel());
    document.getElementById('btn-adm-reprovar')?.addEventListener('click', () => this.reprovarAdmissaoPainel());
    document.getElementById('btn-adm-cancelar')?.addEventListener('click', () => this.cancelarAdmissaoPainel());

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
    document.getElementById('btn-dash-ir-folha')?.addEventListener('click', () => this.navegarPara('folha'));

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
    document.getElementById('btn-ponto-fechar-competencia')?.addEventListener('click', () => this.fecharCompetenciaPonto());
    document.getElementById('btn-ponto-relatorio-ausencias')?.addEventListener('click', () => this.exportarRelatorioAusenciasPonto());

    // Afastamentos
    document.getElementById('btn-afast-relatorio-csv')?.addEventListener('click', () => this.exportarRelatorioAfastamentosCSV());

    // Rotinas Enterprise Folha (13º, Conferência, Lote, Rateio, Financeiro, eSocial)
    document.getElementById('btn-folha-decimo-lote')?.addEventListener('click', () => this.executarDecimoTerceiroLote());
    document.getElementById('btn-folha-conferencia')?.addEventListener('click', () => this.carregarConferenciaAnalitica());
    document.getElementById('btn-folha-fechar-lote')?.addEventListener('click', () => this.fecharCompetenciaFolhaLote());
    document.getElementById('btn-folha-rateio-cc')?.addEventListener('click', () => this.gerarRateioCentroCusto());
    document.getElementById('btn-folha-integracao-fin')?.addEventListener('click', () => this.gerarIntegracaoFinanceira());
    document.getElementById('btn-folha-esocial-periodicos')?.addEventListener('click', () => this.gerarEsocialPeriodicosFolha());
    document.getElementById('btn-fechar-resultado-enterprise')?.addEventListener('click', () => {
      document.getElementById('folha-painel-resultado-enterprise')?.classList.add('hidden');
    });

    // eSocial
    document.getElementById('btn-esocial-transmitir')?.addEventListener('click', () => this.transmitirLoteESocial());

    // CNAB 240
    document.getElementById('btn-gerar-cnab240')?.addEventListener('click', () => this.gerarCNAB240());
    document.getElementById('btn-download-cnab')?.addEventListener('click', () => this.downloadCNAB());
    document.getElementById('btn-processar-retorno-cnab')?.addEventListener('click', () => this.processarRetornoCNAB240());

    // Auditoria
    document.getElementById('btn-atualizar-auditoria')?.addEventListener('click', () => this.carregarAuditoria());

    // Controle de Documentação (RF-008)
    document.getElementById('doc-ctrl-btn-atualizar')?.addEventListener('click', () => this.carregarControleDocumentacao(false));
    document.getElementById('doc-ctrl-btn-sincronizar')?.addEventListener('click', () => this.carregarControleDocumentacao(true));
    document.getElementById('doc-ctrl-filtro-situacao')?.addEventListener('change', () => this.carregarControleDocumentacao(false));
    document.getElementById('doc-ctrl-filtro-categoria')?.addEventListener('change', () => this.carregarControleDocumentacao(false));
    document.getElementById('doc-ctrl-btn-salvar-config')?.addEventListener('click', () => this.salvarConfigAlertasDocumentos());
  },

  async carregarControleDocumentacao(sincronizar = false) {
    try {
      await carregarCategoriasDocumentosSelect();
      const sit = document.getElementById('doc-ctrl-filtro-situacao')?.value || '';
      const cat = document.getElementById('doc-ctrl-filtro-categoria')?.value || 'todas';
      const params = new URLSearchParams();
      if (sit) params.set('situacao', sit);
      if (cat && cat !== 'todas') params.set('categoria', cat);
      if (sincronizar) params.set('sincronizar', '1');
      const res = await requisitarApi(`${getApiBase()}/documentos/controle?${params.toString()}`);
      const dados = res.dados || {};
      const resumo = dados.resumo || {};
      const cfg = dados.config_alertas || {};

      if (document.getElementById('doc-ctrl-total-regulares')) document.getElementById('doc-ctrl-total-regulares').textContent = resumo.regular || 0;
      if (document.getElementById('doc-ctrl-total-vencendo')) document.getElementById('doc-ctrl-total-vencendo').textContent = resumo.proximo_vencimento || 0;
      if (document.getElementById('doc-ctrl-total-vencidos')) document.getElementById('doc-ctrl-total-vencidos').textContent = resumo.vencido || 0;
      if (document.getElementById('doc-ctrl-total-pendentes')) document.getElementById('doc-ctrl-total-pendentes').textContent = resumo.pendentes_obrigatorios || 0;
      if (document.getElementById('doc-ctrl-dias-alerta') && Array.isArray(cfg.dias_antecedencia_alerta)) {
        document.getElementById('doc-ctrl-dias-alerta').value = cfg.dias_antecedencia_alerta.join(', ');
      }
      if (document.getElementById('doc-ctrl-max-mb') && cfg.tamanho_maximo_mb) {
        document.getElementById('doc-ctrl-max-mb').value = cfg.tamanho_maximo_mb;
      }

      const tbody = document.getElementById('doc-ctrl-tbody');
      const docs = dados.documentos || [];
      if (tbody) {
        if (!docs.length) {
          tbody.innerHTML = '<tr><td colspan="6" class="text-muted text-center">Nenhum documento encontrado para o filtro selecionado.</td></tr>';
        } else {
          tbody.innerHTML = docs.map(d => {
            const st = d.status_validade || 'regular';
            const cls = st === 'vencido' ? 'badge-inativo' : (st === 'proximo_vencimento' ? 'badge-dep' : 'badge-ativo');
            const diasTxt = d.dias_para_vencer !== null && d.dias_para_vencer !== undefined ? ` (${d.dias_para_vencer}d)` : '';
            return `
              <tr>
                <td><strong>${_escHtml(d.colaborador_nome || '')}</strong><br><small class="text-muted">${_escHtml(d.matricula || '')}</small></td>
                <td>${_escHtml(d.categoria || d.tipo_documento)}<br><small class="text-muted">${_escHtml(d.tipo_documento)}</small></td>
                <td>${_escHtml(d.nome_arquivo)} (v${d.versao || 1})</td>
                <td>${d.data_validade ? formatarDataBR(d.data_validade) : 'Sem validade'}</td>
                <td><span class="badge ${cls}">${_escHtml(st)}${diasTxt}</span></td>
                <td class="text-right"><button type="button" class="btn btn-outline btn-sm" onclick="abrirModalDetalhes(${d.colaborador_id})">Abrir Ficha</button></td>
              </tr>
            `;
          }).join('');
        }
      }

      const pendDiv = document.getElementById('doc-ctrl-pendentes-lista');
      const pendentes = dados.pendentes || [];
      if (pendDiv) {
        if (!pendentes.length) {
          pendDiv.innerHTML = 'Nenhuma pendência obrigatória encontrada.';
        } else {
          pendDiv.innerHTML = pendentes.map(p =>
            `<div style="padding:0.35rem 0; border-bottom:1px solid #e5e7eb;">
              <strong>${_escHtml(p.colaborador_nome)} (${_escHtml(p.matricula)})</strong>: pendente ${_escHtml(p.categoria_nome || p.categoria)}
            </div>`
          ).join('');
        }
      }
      if (sincronizar) exibirToast('Pendências documentais sincronizadas com sucesso!', 'success');
    } catch (e) {
      exibirToast(e.message || 'Erro ao carregar controle documental.', 'error');
    }
  },

  async salvarConfigAlertasDocumentos() {
    try {
      const diasTxt = document.getElementById('doc-ctrl-dias-alerta')?.value || '30, 15, 7';
      const dias = diasTxt.split(',').map(x => parseInt(x.trim(), 10)).filter(n => !isNaN(n) && n >= 0);
      const maxMb = parseInt(document.getElementById('doc-ctrl-max-mb')?.value || '10', 10);
      await requisitarApi(`${getApiBase()}/documentos/config-alertas`, {
        method: 'PUT',
        body: JSON.stringify({ dias_antecedencia_alerta: dias, tamanho_maximo_mb: maxMb })
      });
      exibirToast('Regras de alerta documental salvas!', 'success');
      await this.carregarControleDocumentacao(false);
    } catch (e) {
      exibirToast(e.message || 'Erro ao salvar configuração de alertas.', 'error');
    }
  }
};

// ============================================================================
// GERENCIADOR DO MÓDULO DE BENEFÍCIOS & DESCONTOS (RF071 A RF080)
// ============================================================================
const BeneficiosManager = {
  catalogo: [],
  vinculos: [],
  ultimoRelatorio: null,

  inicializar() {
    document.querySelectorAll('.btn-benef-tab').forEach(btn => {
      btn.addEventListener('click', () => this.alternarAba(btn.getAttribute('data-benef-tab')));
    });

    document.getElementById('btn-novo-vinculo-beneficio')?.addEventListener('click', () => this.abrirModalVinculo());
    document.getElementById('btn-fechar-modal-benef-vinc')?.addEventListener('click', () => this.fecharModal('modal-beneficio-colaborador'));
    document.getElementById('btn-cancelar-modal-benef-vinc')?.addEventListener('click', () => this.fecharModal('modal-beneficio-colaborador'));
    document.getElementById('btn-salvar-vinculo-beneficio')?.addEventListener('click', () => this.salvarVinculo());
    document.getElementById('benef-vinc-catalogo')?.addEventListener('change', () => this.atualizarCamposPorTipoBeneficio());

    document.getElementById('btn-novo-catalogo-beneficio')?.addEventListener('click', () => this.abrirModalCatalogo());
    document.getElementById('btn-fechar-modal-benef-cat')?.addEventListener('click', () => this.fecharModal('modal-beneficio-catalogo'));
    document.getElementById('btn-cancelar-modal-benef-cat')?.addEventListener('click', () => this.fecharModal('modal-beneficio-catalogo'));
    document.getElementById('btn-salvar-catalogo-beneficio')?.addEventListener('click', () => this.salvarCatalogo());

    document.getElementById('benef-filtro-colab')?.addEventListener('change', () => this.carregarVinculos());
    document.getElementById('benef-filtro-tipo')?.addEventListener('change', () => this.carregarVinculos());
    document.getElementById('btn-verificar-elegibilidade')?.addEventListener('click', () => this.verificarElegibilidade());
    document.getElementById('btn-simular-desc-folha')?.addEventListener('click', () => this.simularDescontosFolha());
    document.getElementById('btn-enviar-beneficios-folha')?.addEventListener('click', () => this.abrirNaFolhaComBeneficios());
    document.getElementById('btn-atualizar-rel-beneficios')?.addEventListener('click', () => this.carregarRelatorio());
    document.getElementById('btn-exportar-beneficios-csv')?.addEventListener('click', () => this.exportarRelatorioCSV());
    document.getElementById('btn-imprimir-beneficios')?.addEventListener('click', () => window.print());
  },

  alternarAba(aba) {
    ['vinculos', 'catalogo', 'folha', 'relatorio'].forEach(nome => {
      document.getElementById(`tab-benef-${nome}`)?.classList.toggle('hidden', nome !== aba);
    });
    document.querySelectorAll('.btn-benef-tab').forEach(btn => {
      const ativo = btn.getAttribute('data-benef-tab') === aba;
      btn.classList.toggle('btn-primary', ativo);
      btn.classList.toggle('btn-outline', !ativo);
    });
    if (aba === 'relatorio') this.carregarRelatorio();
  },

  fecharModal(id) {
    document.getElementById(id)?.classList.add('hidden');
  },

  async carregarTudo() {
    await PlataformaManager.carregarColaboradoresCache();
    ['benef-filtro-colab', 'benef-eleg-colab', 'benef-folha-colab', 'benef-vinc-colab'].forEach(id => {
      PlataformaManager.popularSelectColaboradores(id);
    });
    const fColab = document.getElementById('benef-filtro-colab');
    if (fColab && fColab.options.length > 0) fColab.options[0].textContent = 'Todos os colaboradores';

    await this.carregarCatalogo();
    await this.carregarVinculos();
    await this.carregarRelatorio();
  },

  async carregarCatalogo() {
    const tbody = document.getElementById('tbody-beneficios-catalogo');
    try {
      const resp = await fetch(`${API_BASE}/beneficios/catalogo`, { headers: getAuthHeaders(), credentials: 'include' });
      const json = await resp.json();
      if (!resp.ok) throw new Error(json.mensagem || 'Erro ao carregar catálogo');
      this.catalogo = json.dados || [];

      const sel = document.getElementById('benef-vinc-catalogo');
      if (sel) {
        sel.innerHTML = '<option value="">Selecione um benefício...</option>' +
          this.catalogo.filter(b => b.ativo).map(b => `<option value="${b.id}" data-tipo="${b.tipo}">[${b.codigo}] ${b.nome} (${b.tipo})</option>`).join('');
      }

      if (!tbody) return;
      if (!this.catalogo.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted" style="padding:1.5rem;">Nenhum benefício cadastrado no catálogo.</td></tr>';
        return;
      }
      tbody.innerHTML = '';
      this.catalogo.forEach(item => {
        const tr = document.createElement('tr');
        const copTxt = item.coparticipacao_tipo === 'percentual'
          ? `${Number(item.coparticipacao_valor || 0)}% (teto ${Number(item.teto_legal_percentual || 0)}%)`
          : `R$ ${Number(item.coparticipacao_valor || 0).toFixed(2)} (teto ${Number(item.teto_legal_percentual || 0)}%)`;
        tr.innerHTML = `
          <td><strong>${item.codigo}</strong></td>
          <td>${item.nome}</td>
          <td>${item.tipo}</td>
          <td>${copTxt}</td>
          <td><span class="badge-status badge-aberta">${item.rubrica_codigo || '0511'}</span></td>
          <td><span class="badge-status ${item.ativo ? 'badge-calculada' : 'badge-inativa'}">${item.ativo ? 'Ativo' : 'Inativo'}</span></td>
          <td>
            <div style="display:flex; gap:0.35rem;">
              <button type="button" class="btn btn-outline btn-sm" onclick="BeneficiosManager.abrirModalCatalogo(${item.id})">Editar</button>
              <button type="button" class="btn btn-danger btn-sm" onclick="BeneficiosManager.excluirCatalogo(${item.id})">Excluir</button>
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="text-center text-danger" style="padding:1.5rem;">Erro ao carregar catálogo de benefícios.</td></tr>';
    }
  },

  async carregarVinculos() {
    const tbody = document.getElementById('tbody-beneficios-colaboradores');
    if (!tbody) return;
    const colabId = document.getElementById('benef-filtro-colab')?.value || '';
    const tipo = document.getElementById('benef-filtro-tipo')?.value || 'todos';
    const qs = new URLSearchParams();
    if (colabId) qs.set('colaborador_id', colabId);
    if (tipo && tipo !== 'todos') qs.set('tipo', tipo);

    try {
      const resp = await fetch(`${API_BASE}/beneficios/colaboradores?${qs.toString()}`, { headers: getAuthHeaders(), credentials: 'include' });
      const json = await resp.json();
      if (!resp.ok) throw new Error(json.mensagem || 'Erro ao listar vínculos');
      this.vinculos = json.dados || [];

      if (!this.vinculos.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted" style="padding:1.5rem;">Nenhum benefício vinculado aos colaboradores.</td></tr>';
        return;
      }
      tbody.innerHTML = '';
      this.vinculos.forEach(v => {
        const tr = document.createElement('tr');
        const vigTxt = `${v.vigencia_inicio}${v.vigencia_fim ? ' até ' + v.vigencia_fim : ' (vigente)'}`;
        tr.innerHTML = `
          <td><strong>${v.colaborador_nome || ''}</strong><div class="text-xs text-muted">${v.colaborador_matricula || ''} &bull; ${v.colaborador_setor || ''}</div></td>
          <td><strong>${v.beneficio_nome || ''}</strong><div class="text-xs text-muted">${v.beneficio_tipo} (Rub. ${v.rubrica_codigo || '0511'})</div></td>
          <td>${vigTxt}</td>
          <td>${formatarMoeda(v.custo_total_mes)}</td>
          <td style="color:#b91c1c;"><strong>${formatarMoeda(v.desconto_colaborador)}</strong></td>
          <td style="color:#0f766e;">${formatarMoeda(v.custo_empresa)}</td>
          <td><span class="badge-status ${v.ativo ? 'badge-calculada' : 'badge-inativa'}">${v.ativo ? 'Ativo' : 'Inativo'}</span></td>
          <td>
            <div style="display:flex; gap:0.35rem;">
              <button type="button" class="btn btn-outline btn-sm" onclick="BeneficiosManager.abrirModalVinculo(${v.id})">Editar</button>
              <button type="button" class="btn btn-danger btn-sm" onclick="BeneficiosManager.excluirVinculo(${v.id})">Excluir</button>
            </div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger" style="padding:1.5rem;">Erro ao carregar vínculos de benefícios.</td></tr>';
    }
  },

  atualizarCamposPorTipoBeneficio() {
    const sel = document.getElementById('benef-vinc-catalogo');
    const bid = Number(sel?.value || 0);
    const cat = this.catalogo.find(b => Number(b.id) === bid);
    const tipo = cat ? cat.tipo : '';

    document.getElementById('benef-vinc-grupo-saude')?.classList.toggle('hidden', !['plano_saude', 'plano_odontologico', ''].includes(tipo));
    document.getElementById('benef-vinc-grupo-farmacia')?.classList.toggle('hidden', tipo !== 'farmacia');
    document.getElementById('benef-vinc-grupo-flex')?.classList.toggle('hidden', tipo !== 'beneficio_flexivel');

    if (cat && !document.getElementById('benef-vinc-id')?.value) {
      const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = String(v ?? 0); };
      setVal('benef-vinc-valor-diario', cat.valor_diario_padrao || 0);
      setVal('benef-vinc-valor-mensal', cat.valor_mensal_padrao || 0);
      setVal('benef-vinc-limite', cat.limite_padrao || 0);
      setVal('benef-vinc-saldo-flex', cat.valor_mensal_padrao || 600);
    }
  },

  abrirModalVinculo(vinculoId = null) {
    const alerta = document.getElementById('benef-vinc-alerta');
    if (alerta) { alerta.textContent = ''; alerta.classList.add('hidden'); }
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v ?? ''; };

    if (vinculoId) {
      const v = this.vinculos.find(x => Number(x.id) === Number(vinculoId));
      if (!v) return;
      document.getElementById('benef-vinc-titulo').textContent = `Editar Benefício #${v.id}`;
      setVal('benef-vinc-id', String(v.id));
      setVal('benef-vinc-colab', String(v.colaborador_id));
      setVal('benef-vinc-catalogo', String(v.beneficio_id));
      setVal('benef-vinc-vig-inicio', v.vigencia_inicio || '');
      setVal('benef-vinc-vig-fim', v.vigencia_fim || '');
      setVal('benef-vinc-optante', String(v.optante ?? 1));
      setVal('benef-vinc-valor-diario', v.valor_diario ?? 0);
      setVal('benef-vinc-dias-uteis', v.dias_uteis_mes ?? 22);
      setVal('benef-vinc-valor-mensal', v.valor_mensal_base ?? 0);
      setVal('benef-vinc-qtd-dep', v.qtd_dependentes ?? 0);
      setVal('benef-vinc-valor-dep', v.valor_dependente ?? 0);
      setVal('benef-vinc-copart-extra', v.coparticipacao_extra ?? 0);
      setVal('benef-vinc-limite', v.limite_mensal ?? 0);
      setVal('benef-vinc-utilizado', v.valor_utilizado_mes ?? 0);
      setVal('benef-vinc-saldo-flex', v.saldo_flexivel ?? 0);
      const aloc = v.alocacao_obj || {};
      setVal('benef-flex-alimentacao', aloc.alimentacao ?? 0);
      setVal('benef-flex-mobilidade', aloc.mobilidade ?? 0);
      setVal('benef-flex-saude', aloc.saude ?? 0);
      setVal('benef-flex-educacao', aloc.educacao ?? 0);
      setVal('benef-flex-cultura', aloc.cultura ?? 0);
      setVal('benef-vinc-obs', v.observacoes || '');
    } else {
      document.getElementById('benef-vinc-titulo').textContent = 'Conceder Benefício ao Colaborador';
      setVal('benef-vinc-id', '');
      setVal('benef-vinc-vig-inicio', new Date().toISOString().slice(0, 10));
      setVal('benef-vinc-vig-fim', '');
      setVal('benef-vinc-optante', '1');
      setVal('benef-vinc-dias-uteis', '22');
      setVal('benef-vinc-valor-diario', '0');
      setVal('benef-vinc-valor-mensal', '0');
      setVal('benef-vinc-qtd-dep', '0');
      setVal('benef-vinc-valor-dep', '0');
      setVal('benef-vinc-copart-extra', '0');
      setVal('benef-vinc-limite', '400');
      setVal('benef-vinc-utilizado', '0');
      setVal('benef-vinc-saldo-flex', '600');
      ['alimentacao', 'mobilidade', 'saude', 'educacao', 'cultura'].forEach(k => setVal(`benef-flex-${k}`, '0'));
      setVal('benef-vinc-obs', '');
    }
    this.atualizarCamposPorTipoBeneficio();
    document.getElementById('modal-beneficio-colaborador')?.classList.remove('hidden');
  },

  async salvarVinculo() {
    const alerta = document.getElementById('benef-vinc-alerta');
    const mostrarErro = (msg) => {
      if (alerta) { alerta.textContent = msg; alerta.classList.remove('hidden'); }
      exibirToast(msg, 'error');
    };
    const id = document.getElementById('benef-vinc-id')?.value;
    const colabId = document.getElementById('benef-vinc-colab')?.value;
    const benefId = document.getElementById('benef-vinc-catalogo')?.value;
    const vigInicio = document.getElementById('benef-vinc-vig-inicio')?.value;
    if (!colabId || !benefId || !vigInicio) {
      mostrarErro('Selecione o colaborador, o benefício e a data de início da vigência.');
      return;
    }

    const cat = this.catalogo.find(b => Number(b.id) === Number(benefId));
    const num = (eid) => Number(document.getElementById(eid)?.value || 0);
    const payload = {
      colaborador_id: Number(colabId),
      beneficio_id: Number(benefId),
      vigencia_inicio: vigInicio,
      vigencia_fim: document.getElementById('benef-vinc-vig-fim')?.value || null,
      optante: Number(document.getElementById('benef-vinc-optante')?.value || 1),
      dias_uteis_mes: Number(document.getElementById('benef-vinc-dias-uteis')?.value || 22),
      valor_diario: num('benef-vinc-valor-diario'),
      valor_mensal_base: num('benef-vinc-valor-mensal'),
      qtd_dependentes: Number(document.getElementById('benef-vinc-qtd-dep')?.value || 0),
      valor_dependente: num('benef-vinc-valor-dep'),
      coparticipacao_extra: num('benef-vinc-copart-extra'),
      limite_mensal: num('benef-vinc-limite'),
      valor_utilizado_mes: num('benef-vinc-utilizado'),
      saldo_flexivel: num('benef-vinc-saldo-flex'),
      observacoes: document.getElementById('benef-vinc-obs')?.value || '',
    };
    if (cat && cat.tipo === 'beneficio_flexivel') {
      payload.alocacao_json = {
        alimentacao: num('benef-flex-alimentacao'),
        mobilidade: num('benef-flex-mobilidade'),
        saude: num('benef-flex-saude'),
        educacao: num('benef-flex-educacao'),
        cultura: num('benef-flex-cultura'),
      };
    }

    const url = id ? `${API_BASE}/beneficios/colaboradores/${id}` : `${API_BASE}/beneficios/colaboradores`;
    const method = id ? 'PUT' : 'POST';
    try {
      const resp = await fetch(url, { method, headers: getAuthHeaders(), credentials: 'include', body: JSON.stringify(payload) });
      const json = await resp.json();
      if (!resp.ok) {
        mostrarErro(json.mensagem || 'Erro ao salvar benefício do colaborador.');
        return;
      }
      exibirToast(json.mensagem || 'Benefício salvo com sucesso!', 'success');
      this.fecharModal('modal-beneficio-colaborador');
      await this.carregarVinculos();
      await this.carregarRelatorio();
    } catch (e) {
      mostrarErro('Erro de comunicação ao salvar benefício.');
    }
  },

  async excluirVinculo(id) {
    try {
      const resp = await fetch(`${API_BASE}/beneficios/colaboradores/${id}`, {
        method: 'DELETE', headers: getAuthHeaders(), credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok) { exibirToast(json.mensagem || 'Erro ao excluir vínculo.', 'error'); return; }
      exibirToast(json.mensagem || 'Vínculo removido.', 'success');
      await this.carregarVinculos();
      await this.carregarRelatorio();
    } catch (e) {
      exibirToast('Erro de comunicação ao excluir vínculo.', 'error');
    }
  },

  abrirModalCatalogo(benefId = null) {
    const alerta = document.getElementById('benef-cat-alerta');
    if (alerta) { alerta.textContent = ''; alerta.classList.add('hidden'); }
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.value = v ?? ''; };
    if (benefId) {
      const b = this.catalogo.find(x => Number(x.id) === Number(benefId));
      if (!b) return;
      const reg = b.regra_elegibilidade_obj || {};
      document.getElementById('benef-cat-titulo').textContent = `Editar Benefício ${b.codigo}`;
      setVal('benef-cat-id', String(b.id));
      setVal('benef-cat-codigo', b.codigo);
      setVal('benef-cat-nome', b.nome);
      setVal('benef-cat-tipo', b.tipo);
      setVal('benef-cat-rubrica', b.rubrica_codigo || '0511');
      setVal('benef-cat-copart-tipo', b.coparticipacao_tipo || 'percentual');
      setVal('benef-cat-copart-valor', b.coparticipacao_valor ?? 0);
      setVal('benef-cat-teto', b.teto_legal_percentual ?? 0);
      setVal('benef-cat-valor-mensal', b.valor_mensal_padrao ?? 0);
      setVal('benef-cat-valor-diario', b.valor_diario_padrao ?? 0);
      setVal('benef-cat-limite', b.limite_padrao ?? 0);
      setVal('benef-cat-tempo-min', reg.tempo_minimo_dias ?? 0);
      setVal('benef-cat-contratos', (reg.tipos_contrato_permitidos || []).join(', '));
      setVal('benef-cat-setores', (reg.setores_permitidos || []).join(', '));
      setVal('benef-cat-descricao', b.descricao || '');
    } else {
      document.getElementById('benef-cat-titulo').textContent = 'Novo Item no Catálogo de Benefícios';
      setVal('benef-cat-id', '');
      setVal('benef-cat-codigo', '');
      setVal('benef-cat-nome', '');
      setVal('benef-cat-tipo', 'vale_refeicao');
      setVal('benef-cat-rubrica', '0511');
      setVal('benef-cat-copart-tipo', 'percentual');
      setVal('benef-cat-copart-valor', '0');
      setVal('benef-cat-teto', '20');
      setVal('benef-cat-valor-mensal', '0');
      setVal('benef-cat-valor-diario', '0');
      setVal('benef-cat-limite', '0');
      setVal('benef-cat-tempo-min', '0');
      setVal('benef-cat-contratos', '');
      setVal('benef-cat-setores', '');
      setVal('benef-cat-descricao', '');
    }
    document.getElementById('modal-beneficio-catalogo')?.classList.remove('hidden');
  },

  async salvarCatalogo() {
    const alerta = document.getElementById('benef-cat-alerta');
    const mostrarErro = (msg) => {
      if (alerta) { alerta.textContent = msg; alerta.classList.remove('hidden'); }
      exibirToast(msg, 'error');
    };
    const id = document.getElementById('benef-cat-id')?.value;
    const codigo = document.getElementById('benef-cat-codigo')?.value?.trim();
    const nome = document.getElementById('benef-cat-nome')?.value?.trim();
    if (!codigo || !nome) {
      mostrarErro('Código e nome do benefício são obrigatórios.');
      return;
    }
    const splitCsv = (eid) => (document.getElementById(eid)?.value || '').split(',').map(s => s.trim()).filter(Boolean);
    const num = (eid) => Number(document.getElementById(eid)?.value || 0);
    const payload = {
      codigo,
      nome,
      tipo: document.getElementById('benef-cat-tipo')?.value,
      rubrica_codigo: document.getElementById('benef-cat-rubrica')?.value?.trim() || '0511',
      coparticipacao_tipo: document.getElementById('benef-cat-copart-tipo')?.value || 'percentual',
      coparticipacao_valor: num('benef-cat-copart-valor'),
      teto_legal_percentual: num('benef-cat-teto'),
      valor_mensal_padrao: num('benef-cat-valor-mensal'),
      valor_diario_padrao: num('benef-cat-valor-diario'),
      limite_padrao: num('benef-cat-limite'),
      descricao: document.getElementById('benef-cat-descricao')?.value?.trim() || '',
      regra_elegibilidade: {
        situacoes_permitidas: ['ativo'],
        tempo_minimo_dias: Number(document.getElementById('benef-cat-tempo-min')?.value || 0),
        tipos_contrato_permitidos: splitCsv('benef-cat-contratos'),
        setores_permitidos: splitCsv('benef-cat-setores'),
      }
    };
    const url = id ? `${API_BASE}/beneficios/catalogo/${id}` : `${API_BASE}/beneficios/catalogo`;
    const method = id ? 'PUT' : 'POST';
    try {
      const resp = await fetch(url, { method, headers: getAuthHeaders(), credentials: 'include', body: JSON.stringify(payload) });
      const json = await resp.json();
      if (!resp.ok) { mostrarErro(json.mensagem || 'Erro ao salvar item no catálogo.'); return; }
      exibirToast(json.mensagem || 'Catálogo atualizado!', 'success');
      this.fecharModal('modal-beneficio-catalogo');
      await this.carregarCatalogo();
    } catch (e) {
      mostrarErro('Erro de comunicação ao salvar item no catálogo.');
    }
  },

  async excluirCatalogo(id) {
    try {
      const resp = await fetch(`${API_BASE}/beneficios/catalogo/${id}`, {
        method: 'DELETE', headers: getAuthHeaders(), credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok) { exibirToast(json.mensagem || 'Não foi possível excluir.', 'error'); return; }
      exibirToast(json.mensagem || 'Item removido do catálogo.', 'success');
      await this.carregarCatalogo();
    } catch (e) {
      exibirToast('Erro de comunicação ao excluir benefício.', 'error');
    }
  },

  async verificarElegibilidade() {
    const colabId = document.getElementById('benef-eleg-colab')?.value;
    const tbody = document.getElementById('tbody-beneficios-elegibilidade');
    if (!colabId || !tbody) {
      exibirToast('Selecione um colaborador para verificar a elegibilidade.', 'warning');
      return;
    }
    try {
      const resp = await fetch(`${API_BASE}/beneficios/elegibilidade?colaborador_id=${colabId}`, {
        headers: getAuthHeaders(), credentials: 'include'
      });
      const json = await resp.json();
      const lista = json.dados || [];
      tbody.innerHTML = '';
      lista.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${r.beneficio_codigo}</strong></td>
          <td>${r.beneficio_nome}</td>
          <td>${r.beneficio_tipo}</td>
          <td><span class="badge-status ${r.elegivel ? 'badge-calculada' : 'badge-pendente'}">${r.elegivel ? 'Elegível' : 'Inelegível'}</span></td>
          <td>${r.elegivel ? 'Atende a todas as regras configuradas' : (r.motivos || []).join(' ')}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Erro ao verificar elegibilidade.</td></tr>';
    }
  },

  async simularDescontosFolha() {
    const colabId = document.getElementById('benef-folha-colab')?.value;
    const comp = document.getElementById('benef-folha-comp')?.value || '2026-10';
    const tbody = document.getElementById('tbody-beneficios-descontos-folha');
    const resumoEl = document.getElementById('benef-folha-resumo');
    if (!colabId || !tbody) {
      exibirToast('Selecione um colaborador e uma competência.', 'warning');
      return;
    }
    try {
      const resp = await fetch(`${API_BASE}/beneficios/descontos-folha?colaborador_id=${colabId}&competencia=${encodeURIComponent(comp)}`, {
        headers: getAuthHeaders(), credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok || !json.dados) {
        exibirToast(json.mensagem || 'Erro ao simular descontos.', 'error');
        return;
      }
      const d = json.dados;
      if (resumoEl) {
        resumoEl.innerHTML = `<strong>${d.colaborador_nome}</strong> (Salário-base: ${formatarMoeda(d.salario_base)}) &bull; Competência <strong>${d.competencia}</strong> &bull; Desconto total em folha: <strong style="color:#b91c1c;">${formatarMoeda(d.total_descontos_beneficios)}</strong> &bull; Custeio empresa: <strong style="color:#0f766e;">${formatarMoeda(d.total_custo_empresa)}</strong>`;
      }
      const itens = d.itens || [];
      if (!itens.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:1.25rem;">Nenhum benefício ativo vigente na competência.</td></tr>';
        return;
      }
      tbody.innerHTML = '';
      itens.forEach(it => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${it.rubrica_codigo}</strong></td>
          <td>${it.nome}</td>
          <td>${it.tipo}</td>
          <td>${formatarMoeda(it.custo_total_mes)}</td>
          <td style="color:#b91c1c;"><strong>${formatarMoeda(it.desconto_colaborador)}</strong></td>
          <td style="color:#0f766e;">${formatarMoeda(it.custo_empresa)}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      exibirToast('Erro de comunicação ao simular descontos.', 'error');
    }
  },

  async abrirNaFolhaComBeneficios() {
    const colabId = document.getElementById('benef-folha-colab')?.value;
    const comp = document.getElementById('benef-folha-comp')?.value || '2026-10';
    if (!colabId) {
      exibirToast('Selecione um colaborador primeiro.', 'warning');
      return;
    }
    await PlataformaManager.navegarPara('folha');
    const elComp = document.getElementById('ind-competencia');
    if (elComp) elComp.value = comp;
    await FolhaManager.abrirPainelIndividual(Number(colabId));
    await FolhaManager.importarBeneficiosAtivosPainel();
  },

  async carregarRelatorio() {
    const comp = document.getElementById('benef-rel-comp')?.value || '';
    const tipo = document.getElementById('benef-rel-tipo')?.value || 'todos';
    const setor = document.getElementById('benef-rel-setor')?.value?.trim() || '';
    const qs = new URLSearchParams();
    if (comp) qs.set('competencia', comp);
    if (tipo && tipo !== 'todos') qs.set('tipo', tipo);
    if (setor) qs.set('setor', setor);

    try {
      const resp = await fetch(`${API_BASE}/beneficios/relatorio?${qs.toString()}`, {
        headers: getAuthHeaders(), credentials: 'include'
      });
      const json = await resp.json();
      if (!resp.ok || !json.dados) return;
      const rel = json.dados;
      this.ultimoRelatorio = rel;
      const r = rel.resumo || {};

      const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
      setTxt('benef-kpi-vinculos', String(r.total_vinculos_ativos || 0));
      setTxt('benef-kpi-custo-total', formatarMoeda(r.custo_total_mensal || 0));
      setTxt('benef-kpi-custo-empresa', formatarMoeda(r.total_custo_empresa || 0));
      setTxt('benef-kpi-desconto-colab', formatarMoeda(r.total_desconto_colaboradores || 0));

      const resEl = document.getElementById('benef-rel-resumo');
      if (resEl) {
        resEl.innerHTML = `Colaboradores beneficiados: <strong>${r.total_colaboradores_beneficiados || 0}</strong> &bull; Vínculos ativos: <strong>${r.total_vinculos_ativos || 0}</strong> &bull; Custo médio/colaborador: <strong>${formatarMoeda(r.custo_medio_por_colaborador || 0)}</strong> &bull; Total Empresa: <strong>${formatarMoeda(r.total_custo_empresa || 0)}</strong> &bull; Descontos Folha: <strong>${formatarMoeda(r.total_desconto_colaboradores || 0)}</strong>`;
      }

      const tbTipo = document.getElementById('tbody-benef-rel-tipo');
      if (tbTipo) {
        tbTipo.innerHTML = (rel.por_tipo || []).length
          ? rel.por_tipo.map(x => `<tr><td>${x.tipo}</td><td>${x.quantidade}</td><td>${formatarMoeda(x.custo_total)}</td><td>${formatarMoeda(x.custo_empresa)}</td><td>${formatarMoeda(x.desconto_colaborador)}</td></tr>`).join('')
          : '<tr><td colspan="5" class="text-center text-muted">Sem dados.</td></tr>';
      }
      const tbSetor = document.getElementById('tbody-benef-rel-setor');
      if (tbSetor) {
        tbSetor.innerHTML = (rel.por_setor || []).length
          ? rel.por_setor.map(x => `<tr><td>${x.setor}</td><td>${x.colaboradores}</td><td>${formatarMoeda(x.custo_total)}</td><td>${formatarMoeda(x.custo_empresa)}</td><td>${formatarMoeda(x.desconto_colaborador)}</td></tr>`).join('')
          : '<tr><td colspan="5" class="text-center text-muted">Sem dados.</td></tr>';
      }
      const tbItens = document.getElementById('tbody-benef-rel-itens');
      if (tbItens) {
        tbItens.innerHTML = (rel.itens || []).length
          ? rel.itens.map(x => `<tr><td><strong>${x.colaborador_nome}</strong></td><td>${x.setor}</td><td>${x.beneficio_nome}</td><td>${x.vigencia_inicio}${x.vigencia_fim ? ' até ' + x.vigencia_fim : ''}</td><td>${formatarMoeda(x.custo_total_mes)}</td><td>${formatarMoeda(x.desconto_colaborador)}</td><td>${formatarMoeda(x.custo_empresa)}</td></tr>`).join('')
          : '<tr><td colspan="7" class="text-center text-muted">Nenhum benefício encontrado.</td></tr>';
      }
    } catch (e) { /* ignore */ }
  },

  exportarRelatorioCSV() {
    const itens = this.ultimoRelatorio?.itens || [];
    if (!itens.length) {
      exibirToast('Nenhum dado de benefício para exportar.', 'warning');
      return;
    }
    const cab = ['Matricula', 'Colaborador', 'Setor', 'Codigo', 'Beneficio', 'Tipo', 'Rubrica', 'Custo Total', 'Desconto Colaborador', 'Custo Empresa'];
    const linhas = itens.map(i => [
      `"${i.matricula || ''}"`,
      `"${(i.colaborador_nome || '').replace(/"/g, '""')}"`,
      `"${(i.setor || '').replace(/"/g, '""')}"`,
      `"${i.beneficio_codigo || ''}"`,
      `"${(i.beneficio_nome || '').replace(/"/g, '""')}"`,
      `"${i.tipo || ''}"`,
      `"${i.rubrica_codigo || ''}"`,
      Number(i.custo_total_mes || 0).toFixed(2),
      Number(i.desconto_colaborador || 0).toFixed(2),
      Number(i.custo_empresa || 0).toFixed(2),
    ].join(';'));
    const csv = '\uFEFF' + [cab.join(';'), ...linhas].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `rh20_relatorio_beneficios_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    exibirToast(`Relatório exportado com ${itens.length} registro(s)!`, 'success');
  }
};

document.addEventListener('DOMContentLoaded', () => {
  PlataformaManager.inicializar();
  BeneficiosManager.inicializar();
  configurarEventos();
  AuthManager.inicializar();
  FolhaManager.inicializar();
});
