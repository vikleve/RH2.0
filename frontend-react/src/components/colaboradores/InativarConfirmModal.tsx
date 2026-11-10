import React, { useState } from 'react';
import { Colaborador } from '../../types/colaborador';

interface Props {
  aberto: boolean;
  colaborador: Colaborador | null;
  aoFechar: () => void;
  aoConfirmar: (id: number, motivo: string) => Promise<void>;
}

export const InativarConfirmModal: React.FC<Props> = ({
  aberto,
  colaborador,
  aoFechar,
  aoConfirmar,
}) => {
  const [motivo, setMotivo] = useState('');
  const [processando, setProcessando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  if (!aberto || !colaborador) return null;

  const handleConfirmar = async () => {
    try {
      setProcessando(true);
      setErro(null);
      await aoConfirmar(colaborador.id, motivo);
      aoFechar();
    } catch (err: any) {
      setErro(err.message || 'Erro ao inativar colaborador.');
    } finally {
      setProcessando(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100
    }}>
      <div style={{
        background: '#fff', borderRadius: '8px', maxWidth: '480px', width: '90%', padding: '24px'
      }}>
        <h3 style={{ margin: '0 0 12px 0', color: '#c62828', fontSize: '1.15rem' }}>
          Confirmar Inativação de Colaborador
        </h3>
        <p style={{ margin: '0 0 16px 0', fontSize: '0.9rem', color: '#444', lineHeight: '1.4' }}>
          Tem certeza de que deseja inativar o colaborador <strong>{colaborador.nome_completo}</strong> (Matrícula: {colaborador.matricula})?
        </p>
        <p style={{ margin: '0 0 16px 0', fontSize: '0.8rem', color: '#666', background: '#f5f5f5', padding: '8px', borderRadius: '4px' }}>
          ℹ️ Esta operação é lógica: o histórico, dependentes e folhas de pagamento anteriores serão integralmente preservados.
        </p>

        {erro && (
          <div style={{ background: '#ffebee', color: '#c62828', padding: '8px', borderRadius: '4px', marginBottom: '12px', fontSize: '0.85rem' }}>
            {erro}
          </div>
        )}

        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px', color: '#333' }}>
            Motivo da inativação (opcional):
          </label>
          <input
            type="text"
            placeholder="Ex: Demissão sem justa causa, Afastamento..."
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
          <button
            type="button"
            onClick={aoFechar}
            disabled={processando}
            style={{ padding: '8px 16px', background: '#f5f5f5', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer' }}
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleConfirmar}
            disabled={processando}
            style={{
              padding: '8px 16px',
              background: processando ? '#e57373' : '#c62828',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              cursor: processando ? 'not-allowed' : 'pointer',
              fontWeight: 'bold'
            }}
          >
            {processando ? 'Inativando...' : 'Confirmar Inativação'}
          </button>
        </div>
      </div>
    </div>
  );
};
