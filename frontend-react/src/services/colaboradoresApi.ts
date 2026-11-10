import {
  Colaborador,
  ColaboradoresListResponse,
  ColaboradorFormData,
} from '../types/colaborador';

const API_BASE = '/api/colaboradores';

export const colaboradoresApi = {
  async listar(filtros: {
    page?: number;
    limit?: number;
    search?: string;
    situacao?: string;
    departamentoId?: string;
    filialId?: string;
  }): Promise<ColaboradoresListResponse> {
    const params = new URLSearchParams();
    if (filtros.page) params.append('page', String(filtros.page));
    if (filtros.limit) params.append('limit', String(filtros.limit));
    if (filtros.search) params.append('search', filtros.search);
    if (filtros.situacao) params.append('situacao', filtros.situacao);
    if (filtros.departamentoId) params.append('departamentoId', filtros.departamentoId);
    if (filtros.filialId) params.append('filialId', filtros.filialId);

    const res = await fetch(`${API_BASE}?${params.toString()}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.mensagem || err.message || 'Erro ao carregar colaboradores');
    }

    return res.json();
  },

  async obterPorId(id: number): Promise<Colaborador> {
    const res = await fetch(`${API_BASE}/${id}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.mensagem || err.message || 'Colaborador não encontrado');
    }

    const json = await res.json();
    return json.dados || json;
  },

  async criar(dados: ColaboradorFormData): Promise<Colaborador> {
    const res = await fetch(API_BASE, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(dados),
    });

    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(json.mensagem || json.message || 'Falha ao cadastrar colaborador');
    }

    return json.dados || json;
  },

  async atualizar(id: number, dados: Partial<ColaboradorFormData>): Promise<Colaborador> {
    const res = await fetch(`${API_BASE}/${id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify(dados),
    });

    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(json.mensagem || json.message || 'Falha ao atualizar colaborador');
    }

    return json.dados || json;
  },

  async inativar(id: number, motivo?: string): Promise<Colaborador> {
    const res = await fetch(`${API_BASE}/${id}/inativar`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ motivo: motivo || 'Inativação manual pelo gestor' }),
    });

    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(json.mensagem || json.message || 'Falha ao inativar colaborador');
    }

    return json.dados || json;
  },

  async obterHistorico(id: number): Promise<any[]> {
    const res = await fetch(`${API_BASE}/${id}/historico`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'include',
    });

    if (!res.ok) return [];
    const json = await res.json();
    return json.dados || [];
  },
};
