import React, { useState, useEffect } from 'react';
import { Colaborador } from '../../types/colaborador';
import { colaboradoresApi } from '../../services/colaboradoresApi';

interface Props {
  aberto: boolean;
  colaborador: Colaborador | null;
  aoFechar: () => void;
  aoEditar: (colaborador: Colaborador) => void;
}

export const ColaboradorDetailsModal: React.FC<Props> = ({
  aberto,
  colaborador,
  aoFechar,
  aoEditar,
}) => {
  const [historico, setHistorico] = useState<any[]>([]);
  const [carregandoHist, setCarregandoHist] = useState(false);

  useEffect(() => {
    if (aberto && colaborador) {
      setCarregandoHist(true);
      colaboradoresApi
        .obterHistorico(colaborador.id)
        .then((dados) => setHistorico(dados))
        .catch(() => setHistorico([]))
        .finally(() => setCarregandoHist(false));
    } else {
      setHistorico([]);
    }
  }, [aberto, colaborador]);

  if (!aberto || !colaborador) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div style={{
        background: '#fff', borderRadius: '8px', maxWidth: '750px', width: '90%', maxHeight: '90vh', overflowY: 'auto', padding: '24px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e0e0e0', paddingBottom: '12px' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#1976d2' }}>{colaborador.nome_completo}</h2>
            <span style={{ fontSize: '0.85rem', color: '#666' }}>Matrícula: {colaborador.matricula}</span>
          </div>
          <button type="button" onClick={aoFechar} style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer' }}>×</button>
        </div>

        {/* Status Badge */}
        <div style={{ marginTop: '16px', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{
            padding: '4px 10px',
            borderRadius: '12px',
            fontSize: '0.75rem',
            fontWeight: 'bold',
            backgroundColor: colaborador.situacao.toUpperCase() === 'ATIVO' ? '#e8f5e9' : '#ffebee',
            color: colaborador.situacao.toUpperCase() === 'ATIVO' ? '#2e7d32' : '#c62828'
          }}>
            {colaborador.situacao.toUpperCase()}
          </span>
          <span style={{ fontSize: '0.85rem', color: '#555' }}>Cargo: {colaborador.cargo || 'Não especificado'}</span>
          <span style={{ fontSize: '0.85rem', color: '#555' }}>| Setor: {colaborador.setor || 'Não especificado'}</span>
        </div>

        {/* Grid de Informações */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginTop: '20px' }}>
          <div>
            <strong style={{ display: 'block', fontSize: '0.75rem', color: '#777' }}>CPF</strong>
            <span>{colaborador.cpf_mascarado || colaborador.cpf}</span>
          </div>
          <div>
            <strong style={{ display: 'block', fontSize: '0.75rem', color: '#777' }}>DATA DE NASCIMENTO</strong>
            <span>{colaborador.data_nascimento}</span>
          </div>
          <div>
            <strong style={{ display: 'block', fontSize: '0.75rem', color: '#777' }}>E-MAIL</strong>
            <span>{colaborador.email || 'Não informado'}</span>
          </div>
          <div>
            <strong style={{ display: 'block', fontSize: '0.75rem', color: '#777' }}>TELEFONE / CELULAR</strong>
            <span>{colaborador.celular || colaborador.telefone || 'Não informado'}</span>
          </div>
          <div>
            <strong style={{ display: 'block', fontSize: '0.75rem', color: '#777' }}>DATA DE ADMISSÃO</strong>
            <span>{colaborador.data_admissao || 'Não concluída'}</span>
          </div>
          <div>
            <strong style={{ display: 'block', fontSize: '0.75rem', color: '#777' }}>SALÁRIO BASE</strong>
            <span>R$ {Number(colaborador.salario_base || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
          </div>
          <div style={{ gridColumn: 'span 2' }}>
            <strong style={{ display: 'block', fontSize: '0.75rem', color: '#777' }}>ENDEREÇO</strong>
            <span>{colaborador.logradouro ? `${colaborador.logradouro}, ${colaborador.numero || 'S/N'} - ${colaborador.bairro || ''}, ${colaborador.cidade || ''}/${colaborador.uf || ''}` : 'Não cadastrado'}</span>
          </div>
        </div>

        {colaborador.observacoes && (
          <div style={{ marginTop: '16px', background: '#f9f9f9', padding: '12px', borderRadius: '4px' }}>
            <strong style={{ display: 'block', fontSize: '0.75rem', color: '#555', marginBottom: '4px' }}>OBSERVAÇÕES</strong>
            <p style={{ margin: 0, fontSize: '0.85rem' }}>{colaborador.observacoes}</p>
          </div>
        )}

        {/* Histórico de Auditoria */}
        <div style={{ marginTop: '24px', borderTop: '1px solid #e0e0e0', paddingTop: '16px' }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '1rem', color: '#333' }}>Histórico de Alterações & Auditoria</h3>
          {carregandoHist ? (
            <p style={{ fontSize: '0.85rem', color: '#777' }}>Carregando histórico...</p>
          ) : historico.length === 0 ? (
            <p style={{ fontSize: '0.85rem', color: '#777' }}>Nenhum registro de alteração anterior.</p>
          ) : (
            <div style={{ maxHeight: '160px', overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
                <thead>
                  <tr style={{ background: '#f5f5f5', textAlign: 'left' }}>
                    <th style={{ padding: '6px' }}>Data/Hora</th>
                    <th style={{ padding: '6px' }}>Campo / Ação</th>
                    <th style={{ padding: '6px' }}>Valor Anterior</th>
                    <th style={{ padding: '6px' }}>Novo Valor</th>
                    <th style={{ padding: '6px' }}>Responsável</th>
                  </tr>
                </thead>
                <tbody>
                  {historico.map((h, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
                      <td style={{ padding: '6px' }}>{h.data_hora}</td>
                      <td style={{ padding: '6px' }}>{h.campo_alterado}</td>
                      <td style={{ padding: '6px', color: '#c62828' }}>{h.valor_anterior || '-'}</td>
                      <td style={{ padding: '6px', color: '#2e7d32' }}>{h.valor_novo || '-'}</td>
                      <td style={{ padding: '6px' }}>{h.usuario_responsavel}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Rodapé com Ações */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px', borderTop: '1px solid #e0e0e0', paddingTop: '16px' }}>
          <button
            type="button"
            onClick={aoFechar}
            style={{ padding: '8px 16px', background: '#f5f5f5', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer' }}
          >
            Fechar
          </button>
          <button
            type="button"
            onClick={() => {
              aoFechar();
              aoEditar(colaborador);
            }}
            style={{ padding: '8px 20px', background: '#1976d2', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
          >
            Editar Colaborador
          </button>
        </div>
      </div>
    </div>
  );
};
