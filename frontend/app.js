/**
 * Sistema de Departamento Pessoal — Módulo 1: Cadastro de Colaboradores
 * Lógica do Frontend (Vanilla JavaScript)
 * Integração com API REST e fallback autônomo para LocalStorage
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
    situacao: 'ativo',
    setor: ''
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
    return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9,11)}`;
  }
  return cpf;
}

function mascaraCpf(valor) {
  let v = normalizarCpf(valor).slice(0, 11);
  if (v.length > 9) return `${v.slice(0,3)}.${v.slice(3,6)}.${v.slice(6,9)}-${v.slice(9)}`;
  if (v.length > 6) return `${v.slice(0,3)}.${v.slice(3,6)}.${v.slice(6)}`;
  if (v.length > 3) return `${v.slice(0,3)}.${v.slice(3)}`;
  return v;
}

function mascaraTelefone(valor) {
  let v = String(valor || '').replace(/\D/g, '').slice(0, 11);
  if (v.length > 10) return `(${v.slice(0,2)}) ${v.slice(2,7)}-${v.slice(7)}`;
  if (v.length > 6) return `(${v.slice(0,2)}) ${v.slice(2,6)}-${v.slice(6)}`;
  if (v.length > 2) return `(${v.slice(0,2)}) ${v.slice(2)}`;
  return v;
}

function mascaraCep(valor) {
  let v = String(valor || '').replace(/\D/g, '').slice(0, 8);
  if (v.length > 5) return `${v.slice(0,5)}-${v.slice(5)}`;
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
  const n = normalizarCpf(cpf);
  if (n.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(n)) return false;

  let soma = 0;
  for (let i = 0; i < 9; i++) soma += parseInt(n[i], 10) * (10 - i);
  let resto = (soma * 10) % 11;
  let d1 = resto === 10 ? 0 : resto;
  if (d1 !== parseInt(n[9], 10)) return false;

  soma = 0;
  for (let i = 0; i < 10; i++) soma += parseInt(n[i], 10) * (11 - i);
  resto = (soma * 10) % 11;
  let d2 = resto === 10 ? 0 : resto;
  if (d2 !== parseInt(n[10], 10)) return false;

  return true;
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

  exibirTelaLogin(mensagemErro = null) {
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

    renderizarTabela();
    atualizarCardsMetricas();

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
    const telaLogin = document.getElementById('tela-login');
    const telaSistema = document.getElementById('tela-sistema');
    if (telaLogin) telaLogin.classList.add('hidden');
    if (telaSistema) telaSistema.classList.remove('hidden');

    const elNome = document.getElementById('header-user-nome');
    const elPerfil = document.getElementById('header-user-perfil');
    if (elNome) elNome.textContent = usuario.nome_completo || usuario.usuario;
    if (elPerfil) elPerfil.textContent = usuario.perfil || 'administrador';
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
// Camada de Dados (API e LocalStorage Seguro)
// ============================================================================
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
        if (filtros.situacao && filtros.situacao !== 'todos') params.set('situacao', filtros.situacao);
        if (filtros.setor) params.set('setor', filtros.setor);

        const resp = await fetch(`${API_BASE}/colaboradores?${params.toString()}`, {
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
        console.warn('Erro ao consultar API:', e.message);
        return [];
      }
    }
    return this._listarLocal(filtros);
  },

  async obter(id) {
    if (Estado.usaApi) {
      const resp = await fetch(`${API_BASE}/colaboradores/${id}`, {
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
    return this._obterLocal(id);
  },

  async cadastrar(dados) {
    if (Estado.usaApi) {
      const resp = await fetch(`${API_BASE}/colaboradores`, {
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
    return this._cadastrarLocal(dados);
  },

  async atualizar(id, dados) {
    if (Estado.usaApi) {
      const resp = await fetch(`${API_BASE}/colaboradores/${id}`, {
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
    return this._atualizarLocal(id, dados);
  },

  async inativar(id, motivo) {
    if (Estado.usaApi) {
      const resp = await fetch(`${API_BASE}/colaboradores/${id}/inativar`, {
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
    return this._inativarLocal(id, motivo);
  },

  async reativar(id) {
    if (Estado.usaApi) {
      const resp = await fetch(`${API_BASE}/colaboradores/${id}/reativar`, {
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
    return this._reativarLocal(id);
  },

  // Implementação Local Segura (Sem seed para visitantes anônimos)
  _getStorage() {
    const raw = localStorage.getItem('DP_COLABORADORES');
    if (!raw) return [];
    try {
      return JSON.parse(raw);
    } catch {
      return [];
    }
  },

  _saveStorage(lista) {
    localStorage.setItem('DP_COLABORADORES', JSON.stringify(lista));
  },

  _listarLocal(filtros) {
    let lista = this._getStorage();
    if (filtros.situacao && filtros.situacao !== 'todos') {
      lista = lista.filter(c => c.situacao === filtros.situacao);
    }
    if (filtros.setor) {
      lista = lista.filter(c => c.setor === filtros.setor);
    }
    if (filtros.termo) {
      const t = filtros.termo.toLowerCase().trim();
      const cpfLimpo = normalizarCpf(t);
      lista = lista.filter(c => 
        c.nome_completo.toLowerCase().includes(t) ||
        c.matricula.toLowerCase().includes(t) ||
        c.cpf.includes(t) ||
        (cpfLimpo && normalizarCpf(c.cpf).includes(cpfLimpo))
      );
    }
    return lista;
  },

  _obterLocal(id) {
    const item = this._getStorage().find(c => c.id === parseInt(id, 10));
    if (!item) throw new Error('Colaborador não encontrado.');
    return item;
  },

  _cadastrarLocal(dados) {
    const lista = this._getStorage();
    const novoId = lista.length > 0 ? Math.max(...lista.map(c => c.id)) + 1 : 1;
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

    const novo = {
      ...dados,
      id: novoId,
      total_dependentes: (dados.dependentes || []).length,
      historico: [
        {
          id: 1,
          data_hora: agora,
          campo_alterado: 'Criação de Cadastro',
          valor_anterior: null,
          valor_novo: `Colaborador ${dados.nome_completo} cadastrado com matrícula ${dados.matricula}.`,
          usuario_responsavel: 'Administrador (RH/GTI)'
        }
      ]
    };
    lista.push(novo);
    this._saveStorage(lista);
    return novo;
  },

  _atualizarLocal(id, dados) {
    const lista = this._getStorage();
    const idx = lista.findIndex(c => c.id === parseInt(id, 10));
    if (idx === -1) throw new Error('Colaborador não encontrado');

    const antigo = lista[idx];
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const historico = antigo.historico || [];

    // Checar alterações
    if (antigo.cargo !== dados.cargo) {
      historico.unshift({ id: historico.length + 1, data_hora: agora, campo_alterado: 'Cargo', valor_anterior: antigo.cargo, valor_novo: dados.cargo, usuario_responsavel: 'Administrador (RH/GTI)' });
    }
    if (antigo.salario_base !== dados.salario_base) {
      historico.unshift({ id: historico.length + 1, data_hora: agora, campo_alterado: 'Salário-base', valor_anterior: formatarMoeda(antigo.salario_base), valor_novo: formatarMoeda(dados.salario_base), usuario_responsavel: 'Administrador (RH/GTI)' });
    }

    const atualizado = {
      ...antigo,
      ...dados,
      id: antigo.id,
      total_dependentes: (dados.dependentes || []).length,
      historico
    };
    lista[idx] = atualizado;
    this._saveStorage(lista);
    return atualizado;
  },

  _inativarLocal(id, motivo) {
    const lista = this._getStorage();
    const colab = lista.find(c => c.id === parseInt(id, 10));
    if (!colab) throw new Error('Colaborador não encontrado');
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    colab.situacao = 'inativo';
    colab.historico = colab.historico || [];
    colab.historico.unshift({
      id: colab.historico.length + 1,
      data_hora: agora,
      campo_alterado: 'Situação do Vínculo',
      valor_anterior: 'ativo',
      valor_novo: `inativo (Motivo: ${motivo || 'Não informado'})`,
      usuario_responsavel: 'Administrador (RH/GTI)'
    });
    this._saveStorage(lista);
    return colab;
  },

  _reativarLocal(id) {
    const lista = this._getStorage();
    const colab = lista.find(c => c.id === parseInt(id, 10));
    if (!colab) throw new Error('Colaborador não encontrado');
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    colab.situacao = 'ativo';
    colab.historico = colab.historico || [];
    colab.historico.unshift({
      id: colab.historico.length + 1,
      data_hora: agora,
      campo_alterado: 'Situação do Vínculo',
      valor_anterior: 'inativo',
      valor_novo: 'ativo',
      usuario_responsavel: 'Administrador (RH/GTI)'
    });
    this._saveStorage(lista);
    return colab;
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

  const row = document.createElement('div');
  row.className = 'dependente-row';
  row.innerHTML = `
    <div>
      <input type="text" class="form-control dep-nome" placeholder="Nome do Dependente *" value="${dados.nome || ''}" required>
    </div>
    <div>
      <input type="text" class="form-control dep-cpf" placeholder="CPF (Opcional)" maxlength="14" value="${dados.cpf || ''}">
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
    const parentesco = r.querySelector('.dep-parentesco').value;
    if (nome || parentesco) {
      deps.push({ nome, cpf, parentesco });
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
  limparErrosFormulario();
  document.getElementById('modal-form').classList.remove('hidden');
}

async function abrirModalEditar(id) {
  try {
    const colab = await DadosService.obter(id);
    Estado.colaboradorEmEdicao = colab;
    document.getElementById('form-modal-title').textContent = `Editar Colaborador: ${colab.nome_completo}`;
    document.getElementById('colaborador-id').value = colab.id;

    // Preenchimento dos campos
    document.getElementById('campo-nome').value = colab.nome_completo || '';
    document.getElementById('campo-cpf').value = colab.cpf || '';
    document.getElementById('campo-rg').value = colab.rg || '';
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
    salario_base: document.getElementById('campo-salario').value,
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
    document.getElementById('view-nome').textContent = colab.nome_completo;
    document.getElementById('view-cpf').textContent = colab.cpf;
    document.getElementById('view-rg').textContent = colab.rg || 'Não informado';
    document.getElementById('view-nasc').textContent = formatarDataBR(colab.data_nascimento);

    document.getElementById('view-email').textContent = colab.email;
    document.getElementById('view-telefone').textContent = colab.telefone || 'Não informado';
    const end = [colab.logradouro, colab.numero, colab.bairro, colab.cidade, colab.uf, colab.cep].filter(Boolean).join(', ');
    document.getElementById('view-endereco').textContent = end || 'Não informado';

    document.getElementById('view-matricula').textContent = colab.matricula;
    document.getElementById('view-admissao').textContent = formatarDataBR(colab.data_admissao);
    document.getElementById('view-cargo').textContent = colab.cargo;
    document.getElementById('view-setor').textContent = colab.setor;
    document.getElementById('view-salario').textContent = formatarMoeda(colab.salario_base);
    document.getElementById('view-situacao').innerHTML = colab.situacao === 'ativo' 
      ? '<span class="badge badge-ativo">Ativo</span>' 
      : '<span class="badge badge-inativo">Inativo</span>';

    // Dependentes
    const listaDep = colab.dependentes || [];
    document.getElementById('detalhes-qtd-dep').textContent = listaDep.length;
    const containerDep = document.getElementById('detalhes-lista-dependentes');
    if (listaDep.length === 0) {
      containerDep.innerHTML = '<p class="text-muted" style="padding:1rem;">Nenhum dependente cadastrado para este colaborador.</p>';
    } else {
      containerDep.innerHTML = `
        <table class="data-table">
          <thead>
            <tr><th>Nome do Dependente</th><th>CPF</th><th>Parentesco</th></tr>
          </thead>
          <tbody>
            ${listaDep.map(d => `
              <tr>
                <td><strong>${d.nome}</strong></td>
                <td>${d.cpf || 'Não informado'}</td>
                <td><span class="badge badge-dep">${d.parentesco}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    }

    // Histórico de Alterações / Auditoria
    const timeline = document.getElementById('detalhes-timeline');
    const historico = colab.historico || [];
    if (historico.length === 0) {
      timeline.innerHTML = '<p class="text-muted">Nenhuma alteração registrada até o momento.</p>';
    } else {
      timeline.innerHTML = historico.map(h => {
        let detalheAlteracao = '';
        if (h.valor_anterior !== null && h.valor_anterior !== undefined && h.valor_anterior !== '') {
          detalheAlteracao = `De: <s>${h.valor_anterior}</s> &rarr; Para: <strong>${h.valor_novo}</strong>`;
        } else {
          detalheAlteracao = `<strong>${h.valor_novo}</strong>`;
        }

        return `
          <div class="timeline-item">
            <div class="timeline-header">
              <span class="timeline-action">${h.campo_alterado}</span>
              <span class="timeline-date">${h.data_hora}</span>
            </div>
            <div class="timeline-body">
              ${detalheAlteracao}
              <div class="timeline-user">Registrado por: ${h.usuario_responsavel || 'Sistema'}</div>
            </div>
          </div>
        `;
      }).join('');
    }

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

  document.getElementById('btn-recarregar').addEventListener('click', carregarColaboradores);
  document.getElementById('btn-limpar-filtros').addEventListener('click', () => {
    inputPesquisa.value = '';
    btnLimpar.classList.add('hidden');
    document.getElementById('filtro-situacao').value = 'todos';
    document.getElementById('filtro-setor').value = '';
    Estado.filtros = { termo: '', situacao: 'todos', setor: '' };
    carregarColaboradores();
  });

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

﻿// ============================================================================
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
        if (json.sucesso && json.dados) {
          this.colaboradoresElegiveis = json.dados;
          const select = document.getElementById('folha-campo-colaborador');
          if (select) {
            select.innerHTML = '<option value="">Selecione um colaborador ativo...</option>';
            this.colaboradoresElegiveis.forEach(c => {
              const opt = document.createElement('option');
              opt.value = c.id;
              opt.textContent = `${c.matricula} — ${c.nome_completo} (${c.cargo})`;
              select.appendChild(opt);
            });
          }
        }
      }
    } catch (e) {
      console.error('Erro ao carregar colaboradores elegíveis:', e);
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
    if (this.filtros.setor) params.append('setor', this.filtros.setor);
    if (this.filtros.termo) params.append('q', this.filtros.termo);

    try {
      const resp = await fetch(`${API_BASE}/folha?${params.toString()}`, {
        headers: getAuthHeaders(),
        credentials: 'include'
      });

      if (resp.status === 401) {
        AuthManager.exibirTelaLogin();
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
  },

  renderizarTabelaFolhas() {
    const corpo = document.getElementById('corpo-tabela-folha');
    const estadoVazio = document.getElementById('estado-vazio-folha');
    if (!corpo) return;

    corpo.innerHTML = '';

    if (this.folhas.length === 0) {
      if (estadoVazio) estadoVazio.classList.remove('hidden');
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
  },

  async abrirModalNovaFolha() {
    this.folhaEmEdicao = null;
    this.rubricasManuais = [
      { tipo: 'provento', codigo: '0010', descricao: 'Horas extras 50%', referencia: 1, valor_total: 100, isCustom: false },
      { tipo: 'desconto', codigo: '0520', descricao: 'Adiantamento salarial', referencia: 1, valor_total: 100, isCustom: false }
    ];
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

      (folha.itens || []).forEach(it => {
        if (it.codigo_evento === '101') he50 = it.referencia;
        else if (it.codigo_evento === '102') he100 = it.referencia;
        else if (it.codigo_evento === '103') noturno = it.referencia;
        else if (it.codigo_evento === '201') faltas = it.referencia;
        else if (it.codigo_evento === '202') atrasos = it.referencia;
        else if (it.origem === 'manual') {
          this.rubricasManuais.push({
            tipo: it.tipo,
            descricao: it.descricao,
            referencia: it.referencia,
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
        <td>
          <select class="form-control select-control rub-tipo" data-idx="${idx}" style="font-size: 0.8rem; padding: 0.35rem 0.5rem; font-weight: 600;">
            <option value="provento" ${rub.tipo === 'provento' ? 'selected' : ''}>Provento (+)</option>
            <option value="desconto" ${rub.tipo === 'desconto' ? 'selected' : ''}>Desconto (-)</option>
          </select>
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
          <input type="number" class="form-control rub-val" data-idx="${idx}" value="${rub.valor_total ?? 0}" min="0" step="0.01" style="font-size: 0.82rem; padding: 0.35rem; font-weight: 600;">
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

    corpo.querySelectorAll('.rub-tipo').forEach(el => {
      el.addEventListener('change', (e) => {
        const idx = Number(e.target.dataset.idx);
        const novoTipo = e.target.value;
        this.rubricasManuais[idx].tipo = novoTipo;
        if (!this.rubricasManuais[idx].isCustom) {
          if (novoTipo === 'desconto') {
            this.rubricasManuais[idx].codigo = '0520';
            this.rubricasManuais[idx].descricao = 'Adiantamento salarial';
          } else {
            this.rubricasManuais[idx].codigo = '0010';
            this.rubricasManuais[idx].descricao = 'Horas extras 50%';
          }
          const vAuto = this.calcularValorAutomaticoEvento(this.rubricasManuais[idx].codigo, this.rubricasManuais[idx].referencia, novoTipo);
          if (vAuto > 0) this.rubricasManuais[idx].valor_total = vAuto;
        }
        this.renderizarRubricasManuais();
        this.atualizarPreviaCalculo();
      });
    });

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
          codigo: r.codigo || `MANUAL_${i+1}`,
          descricao: r.descricao,
          tipo: r.tipo,
          referencia: r.referencia,
          valor_total: r.valor_total
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
        document.getElementById('preview-salario-prop').textContent = formatarMoeda(d.salario_base_proporcional);
        document.getElementById('preview-total-proventos').textContent = formatarMoeda(d.total_proventos);
        document.getElementById('preview-total-descontos').textContent = formatarMoeda(d.total_descontos);
        document.getElementById('preview-salario-liquido').textContent = formatarMoeda(d.salario_liquido);
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
      document.getElementById('preview-salario-prop').textContent = formatarMoeda(d.salario_base_proporcional);
      document.getElementById('preview-total-proventos').textContent = formatarMoeda(d.total_proventos);
      document.getElementById('preview-total-descontos').textContent = formatarMoeda(d.total_descontos);
      document.getElementById('preview-salario-liquido').textContent = formatarMoeda(d.salario_liquido);
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
      if (r.tipo === 'provento') totProventos += Number(r.valor_total || 0);
      else totDescontos += Number(r.valor_total || 0);
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

    document.getElementById('preview-salario-prop').textContent = formatarMoeda(sbProp);
    document.getElementById('preview-total-proventos').textContent = formatarMoeda(totProventos);
    document.getElementById('preview-total-descontos').textContent = formatarMoeda(totDescontos);
    document.getElementById('preview-salario-liquido').textContent = formatarMoeda(liquido);
  },

  atualizarPreviaCalculo() {
    this.simularFolhaNoBackend(false);
  },

  async salvarFolha() {
    const colabId = document.getElementById('folha-campo-colaborador').value;
    const competencia = document.getElementById('folha-campo-competencia').value;
    const inicio = document.getElementById('folha-campo-inicio').value;
    const fim = document.getElementById('folha-campo-fim').value;
    const pagto = document.getElementById('folha-campo-pagamento').value;
    const dias = Number(document.getElementById('folha-campo-dias').value || 30);
    const divisor = Number(document.getElementById('folha-campo-divisor').value || 220);
    const observacoes = document.getElementById('folha-campo-observacoes').value;
    const folhaId = document.getElementById('folha-id-edicao').value;

    const alerta = document.getElementById('folha-form-alerta');
    alerta.classList.add('hidden');

    if (!colabId) {
      alerta.textContent = 'Selecione um colaborador ativo para a folha.';
      alerta.classList.remove('hidden');
      return;
    }

    if (!competencia) {
      alerta.textContent = 'Informe a competência no formato AAAA-MM.';
      alerta.classList.remove('hidden');
      return;
    }

    const payload = {
      colaborador_id: Number(colabId),
      competencia: competencia.trim(),
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

    try {
      const resp = await fetch(url, {
        method: metodo,
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify(payload)
      });

      const resJson = await resp.json();

      if (!resp.ok) {
        if (resJson.erros && resJson.erros.competencia) {
          alerta.textContent = resJson.erros.competencia;
        } else {
          alerta.textContent = resJson.mensagem || 'Ocorreu um erro ao processar a folha.';
        }
        alerta.classList.remove('hidden');
        return;
      }

      const msgSucesso = folhaId ? 'Folha recalculada e salva com sucesso!' : 'Folha de pagamento gerada e salva com sucesso no banco de dados!';
      exibirToast(msgSucesso, 'success');
      document.getElementById('modal-folha-form').classList.add('hidden');
      await this.carregarFolhas();
      if (resJson.dados && resJson.dados.id) {
        this.abrirModalHolerite(resJson.dados.id, true);
      }
    } catch (e) {
      console.error('Falha ao salvar folha:', e);
      alerta.textContent = 'Erro de comunicação com o servidor backend.';
      alerta.classList.remove('hidden');
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

      // Preencher Contracheque
      document.getElementById('h-competencia').textContent = f.competencia;
      document.getElementById('h-matricula').textContent = f.colaborador_matricula || '--';
      document.getElementById('h-nome').textContent = f.colaborador_nome || '--';
      document.getElementById('h-cpf').textContent = formatarCpf(f.colaborador_cpf || '');
      document.getElementById('h-cargo').textContent = f.colaborador_cargo || '--';
      document.getElementById('h-setor').textContent = f.colaborador_setor || '--';
      document.getElementById('h-admissao').textContent = formatarDataBR(f.colaborador_data_admissao);
      document.getElementById('h-data-pagto').textContent = formatarDataBR(f.data_pagamento) || '05 do mês subsequente';

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
      const btnFecharAcao = document.getElementById('btn-fechar-folha-acao');
      const btnReabrirAcao = document.getElementById('btn-reabrir-folha-acao');
      if (f.situacao === 'fechada') {
        if (btnFecharAcao) btnFecharAcao.style.display = 'none';
        if (btnReabrirAcao) btnReabrirAcao.style.display = 'inline-flex';
      } else {
        if (btnFecharAcao) btnFecharAcao.style.display = 'inline-flex';
        if (btnReabrirAcao) btnReabrirAcao.style.display = 'none';
      }

      document.getElementById('modal-holerite').classList.remove('hidden');
    } catch (e) {
      console.error('Erro ao abrir demonstrativo da folha:', e);
      exibirToast('Erro ao carregar demonstrativo.', 'error');
    }
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

    try {
      const resp = await fetch(`${API_BASE}/folha/${folhaId}/reabrir`, {
        method: 'POST',
        headers: getAuthHeaders(),
        credentials: 'include',
        body: JSON.stringify({ motivo })
      });
      const json = await resp.json();
      if (!resp.ok) {
        exibirToast(json.mensagem || 'Falha ao reabrir folha.', 'error');
        return;
      }
      exibirToast(`Folha #${folhaId} reaberta para edição!`, 'success');
      document.getElementById('modal-reabrir-folha-confirm').classList.add('hidden');
      document.getElementById('modal-holerite').classList.add('hidden');
      await this.carregarFolhas();
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
document.addEventListener('DOMContentLoaded', () => {
  configurarEventos();
  AuthManager.inicializar();
  FolhaManager.inicializar();
});
