import React, { useState, useEffect, useCallback } from 'react';
import { Colaborador, ColaboradoresMeta, ColaboradorFormData } from '../types/colaborador';
import { colaboradoresApi } from '../services/colaboradoresApi';
import { ColaboradorFormModal } from '../components/colaboradores/ColaboradorFormModal';
import { ColaboradorDetailsModal } from '../components/colaboradores/ColaboradorDetailsModal';
import { InativarConfirmModal } from '../components/colaboradores/InativarConfirmModal';

export const ColaboradoresPage: React.FC = () => {
  const [colaboradores, setColaboradores] = useState<Colaborador[]>([]);
  const [meta, setMeta] = useState<ColaboradoresMeta>({ page: 1, limit: 10, total: 0, totalPages: 0 });
  const [carregando, setCarregando] = useState(false);
  const [mensagemSucesso, setMensagemSucesso] = useState<string | null>(null);
  const [mensagemErro, setMensagemErro] = useState<string | null>(null);

  // Filtros
  const [search, setSearch] = useState('');
  const [situacao, setSituacao] = useState('');
  const [departamento, setDepartamento] = useState('');
  const [page, setPage] = useState(1);

  // Modais
  const [modalFormAberto, setModalFormAberto] = useState(false);
  const [colaboradorParaEditar, setColaboradorParaEditar] = useState<Colaborador | null>(null);

  const [modalDetalhesAberto, setModalDetalhesAberto] = useState(false);
  const [colaboradorParaDetalhes, setColaboradorParaDetalhes] = useState<Colaborador | null>(null);

  const [modalInativarAberto, setModalInativarAberto] = useState(false);
  const [colaboradorParaInativar, setColaboradorParaInativar] = useState<Colaborador | null>(null);

  const carregarColaboradores = useCallback(async () => {
    try {
      setCarregando(true);
      setMensagemErro(null);
      const res = await colaboradoresApi.listar({
        page,
        limit: 10,
        search: search.trim() || undefined,
        situacao: situacao || undefined,
        departamentoId: departamento || undefined,
      });
      setColaboradores(res.data);
      setMeta(res.meta);
    } catch (err: any) {
      setMensagemErro(err.message || 'Falha ao carregar colaboradores');
    } finally {
      setCarregando(false);
    }
  }, [page, search, situacao, departamento]);

  useEffect(() => {
    carregarColaboradores();
  }, [carregarColaboradores]);

  const handleSalvarColaborador = async (dados: ColaboradorFormData) => {
    if (colaboradorParaEditar) {
      await colaboradoresApi.atualizar(colaboradorParaEditar.id, dados);
      setMensagemSucesso('Colaborador atualizado com sucesso!');
    } else {
      await colaboradoresApi.criar(dados);
      setMensagemSucesso('Colaborador cadastrado com sucesso!');
    }
    carregarColaboradores();
    setTimeout(() => setMensagemSucesso(null), 4000);
  };

  const handleConfirmarInativacao = async (id: number, motivo: string) => {
    await colaboradoresApi.inativar(id, motivo);
    setMensagemSucesso('Colaborador inativado com sucesso.');
    carregarColaboradores();
    setTimeout(() => setMensagemSucesso(null), 4000);
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {/* Cabeçalho */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.75rem', color: '#1a237e' }}>Colaboradores</h1>
          <p style={{ margin: '4px 0 0 0', color: '#666', fontSize: '0.9rem' }}>
            Gestão do quadro de colaboradores, registros cadastrais e auditoria
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setColaboradorParaEditar(null);
            setModalFormAberto(true);
          }}
          style={{
            backgroundColor: '#1976d2',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            padding: '10px 20px',
            fontWeight: 'bold',
            fontSize: '0.9rem',
            cursor: 'pointer',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
          }}
        >
          + Novo Colaborador
        </button>
      </div>

      {/* Alertas */}
      {mensagemSucesso && (
        <div style={{ background: '#e8f5e9', color: '#2e7d32', padding: '12px 16px', borderRadius: '6px', marginBottom: '16px', fontSize: '0.9rem' }}>
          ✓ {mensagemSucesso}
        </div>
      )}
      {mensagemErro && (
        <div style={{ background: '#ffebee', color: '#c62828', padding: '12px 16px', borderRadius: '6px', marginBottom: '16px', fontSize: '0.9rem' }}>
          ✕ {mensagemErro}
        </div>
      )}

      {/* Barra de Pesquisa e Filtros (RF-02, RF-03) */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', background: '#f5f5f5', padding: '16px', borderRadius: '8px', marginBottom: '20px' }}>
        <div style={{ flex: '2', minWidth: '240px' }}>
          <input
            type="text"
            placeholder="Pesquisar por nome, CPF ou matrícula..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            style={{ width: '100%', padding: '10px 12px', border: '1px solid #ccc', borderRadius: '6px', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ flex: '1', minWidth: '150px' }}>
          <select
            value={situacao}
            onChange={(e) => {
              setSituacao(e.target.value);
              setPage(1);
            }}
            style={{ width: '100%', padding: '10px 12px', border: '1px solid #ccc', borderRadius: '6px', background: '#fff' }}
          >
            <option value="">Todas as Situações</option>
            <option value="ATIVO">Ativos</option>
            <option value="INATIVO">Inativos</option>
          </select>
        </div>

        <div style={{ flex: '1', minWidth: '180px' }}>
          <input
            type="text"
            placeholder="Filtrar por setor..."
            value={departamento}
            onChange={(e) => {
              setDepartamento(e.target.value);
              setPage(1);
            }}
            style={{ width: '100%', padding: '10px 12px', border: '1px solid #ccc', borderRadius: '6px', boxSizing: 'border-box' }}
          />
        </div>
      </div>

      {/* Tabela de Resultados (RF-01) */}
      <div style={{ background: '#fff', borderRadius: '8px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ background: '#fafafa', borderBottom: '2px solid #e0e0e0', color: '#555' }}>
              <th style={{ padding: '14px 16px' }}>Matrícula</th>
              <th style={{ padding: '14px 16px' }}>Nome Completo</th>
              <th style={{ padding: '14px 16px' }}>CPF</th>
              <th style={{ padding: '14px 16px' }}>Departamento</th>
              <th style={{ padding: '14px 16px' }}>Cargo</th>
              <th style={{ padding: '14px 16px' }}>Situação</th>
              <th style={{ padding: '14px 16px', textAlign: 'center' }}>Ações</th>
            </tr>
          </thead>
          <tbody>
            {carregando ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '32px', color: '#777' }}>
                  Carregando colaboradores...
                </td>
              </tr>
            ) : colaboradores.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '32px', color: '#777' }}>
                  Nenhum colaborador encontrado para os filtros selecionados.
                </td>
              </tr>
            ) : (
              colaboradores.map((c) => {
                const isAtivo = (c.situacao || '').toUpperCase() === 'ATIVO';
                return (
                  <tr key={c.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={{ padding: '14px 16px', fontWeight: 'bold', color: '#333' }}>{c.matricula}</td>
                    <td style={{ padding: '14px 16px' }}>{c.nome_completo}</td>
                    <td style={{ padding: '14px 16px', color: '#666' }}>{c.cpf_mascarado || c.cpf}</td>
                    <td style={{ padding: '14px 16px' }}>{c.setor || c.departamento_id || '-'}</td>
                    <td style={{ padding: '14px 16px' }}>{c.cargo || c.cargo_id || '-'}</td>
                    <td style={{ padding: '14px 16px' }}>
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: '12px',
                        fontSize: '0.75rem',
                        fontWeight: 'bold',
                        backgroundColor: isAtivo ? '#e8f5e9' : '#ffebee',
                        color: isAtivo ? '#2e7d32' : '#c62828'
                      }}>
                        {isAtivo ? 'ATIVO' : 'INATIVO'}
                      </span>
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        <button
                          type="button"
                          onClick={() => {
                            setColaboradorParaDetalhes(c);
                            setModalDetalhesAberto(true);
                          }}
                          title="Visualizar Detalhes"
                          style={{ padding: '6px 10px', fontSize: '0.8rem', background: '#e3f2fd', color: '#1565c0', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                        >
                          👁️ Detalhes
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setColaboradorParaEditar(c);
                            setModalFormAberto(true);
                          }}
                          title="Editar"
                          style={{ padding: '6px 10px', fontSize: '0.8rem', background: '#fff3e0', color: '#e65100', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                        >
                          ✏️ Editar
                        </button>
                        {isAtivo && (
                          <button
                            type="button"
                            onClick={() => {
                              setColaboradorParaInativar(c);
                              setModalInativarAberto(true);
                            }}
                            title="Inativar"
                            style={{ padding: '6px 10px', fontSize: '0.8rem', background: '#ffebee', color: '#c62828', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
                          >
                            ⛔ Inativar
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Paginação (RF-01, Seção 6.2) */}
        {meta.totalPages > 1 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px', borderTop: '1px solid #e0e0e0', fontSize: '0.85rem', color: '#666' }}>
            <span>Total de colaboradores: <strong>{meta.total}</strong></span>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                style={{ padding: '6px 12px', border: '1px solid #ccc', borderRadius: '4px', background: '#fff', cursor: page <= 1 ? 'not-allowed' : 'pointer' }}
              >
                Anterior
              </button>
              <span>Página {meta.page} de {meta.totalPages}</span>
              <button
                type="button"
                disabled={page >= meta.totalPages}
                onClick={() => setPage((p) => Math.min(meta.totalPages, p + 1))}
                style={{ padding: '6px 12px', border: '1px solid #ccc', borderRadius: '4px', background: '#fff', cursor: page >= meta.totalPages ? 'not-allowed' : 'pointer' }}
              >
                Próxima
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modais de Fluxo */}
      <ColaboradorFormModal
        aberto={modalFormAberto}
        colaboradorParaEditar={colaboradorParaEditar}
        aoFechar={() => setModalFormAberto(false)}
        aoSalvar={handleSalvarColaborador}
      />

      <ColaboradorDetailsModal
        aberto={modalDetalhesAberto}
        colaborador={colaboradorParaDetalhes}
        aoFechar={() => setModalDetalhesAberto(false)}
        aoEditar={(c) => {
          setColaboradorParaEditar(c);
          setModalFormAberto(true);
        }}
      />

      <InativarConfirmModal
        aberto={modalInativarAberto}
        colaborador={colaboradorParaInativar}
        aoFechar={() => setModalInativarAberto(false)}
        aoConfirmar={handleConfirmarInativacao}
      />
    </div>
  );
};
