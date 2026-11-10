import React, { useState, useEffect } from 'react';
import { Colaborador, ColaboradorFormData } from '../../types/colaborador';

interface Props {
  aberto: boolean;
  colaboradorParaEditar?: Colaborador | null;
  aoFechar: () => void;
  aoSalvar: (dados: ColaboradorFormData) => Promise<void>;
}

export const ColaboradorFormModal: React.FC<Props> = ({
  aberto,
  colaboradorParaEditar,
  aoFechar,
  aoSalvar,
}) => {
  const [secaoAtiva, setSecaoAtiva] = useState<'pessoais' | 'contato' | 'endereco' | 'organizacional'>('pessoais');
  const [salvando, setSalvando] = useState(false);
  const [erroGeral, setErroGeral] = useState<string | null>(null);

  const [formData, setFormData] = useState<ColaboradorFormData>({
    matricula: '',
    nomeCompleto: '',
    cpf: '',
    dataNascimento: '',
    sexo: 'MASCULINO',
    estadoCivil: 'SOLTEIRO',
    email: '',
    telefone: '',
    celular: '',
    cep: '',
    logradouro: '',
    numero: '',
    complemento: '',
    bairro: '',
    cidade: '',
    uf: '',
    departamentoId: '',
    cargoId: '',
    cargo: '',
    setor: '',
    dataAdmissao: '',
    salarioBase: 0,
    situacao: 'ATIVO',
    observacoes: '',
  });

  useEffect(() => {
    if (colaboradorParaEditar) {
      setFormData({
        matricula: colaboradorParaEditar.matricula || '',
        nomeCompleto: colaboradorParaEditar.nome_completo || '',
        cpf: colaboradorParaEditar.cpf || '',
        dataNascimento: colaboradorParaEditar.data_nascimento || '',
        sexo: colaboradorParaEditar.sexo || 'MASCULINO',
        estadoCivil: colaboradorParaEditar.estado_civil || 'SOLTEIRO',
        email: colaboradorParaEditar.email || '',
        telefone: colaboradorParaEditar.telefone || '',
        celular: colaboradorParaEditar.celular || '',
        cep: colaboradorParaEditar.cep || '',
        logradouro: colaboradorParaEditar.logradouro || '',
        numero: colaboradorParaEditar.numero || '',
        complemento: colaboradorParaEditar.complemento || '',
        bairro: colaboradorParaEditar.bairro || '',
        cidade: colaboradorParaEditar.cidade || '',
        uf: colaboradorParaEditar.uf || '',
        departamentoId: colaboradorParaEditar.departamento_id || '',
        cargoId: colaboradorParaEditar.cargo_id || '',
        cargo: colaboradorParaEditar.cargo || '',
        setor: colaboradorParaEditar.setor || '',
        dataAdmissao: colaboradorParaEditar.data_admissao || '',
        salarioBase: colaboradorParaEditar.salario_base || 0,
        situacao: (colaboradorParaEditar.situacao || 'ATIVO').toUpperCase(),
        observacoes: colaboradorParaEditar.observacoes || '',
      });
    } else {
      setFormData({
        matricula: '',
        nomeCompleto: '',
        cpf: '',
        dataNascimento: '',
        sexo: 'MASCULINO',
        estadoCivil: 'SOLTEIRO',
        email: '',
        telefone: '',
        celular: '',
        cep: '',
        logradouro: '',
        numero: '',
        complemento: '',
        bairro: '',
        cidade: '',
        uf: '',
        departamentoId: '',
        cargoId: '',
        cargo: '',
        setor: '',
        dataAdmissao: '',
        salarioBase: 0,
        situacao: 'ATIVO',
        observacoes: '',
      });
    }
    setErroGeral(null);
    setSecaoAtiva('pessoais');
  }, [colaboradorParaEditar, aberto]);

  if (!aberto) return null;

  const handleChange = (campo: keyof ColaboradorFormData, valor: any) => {
    setFormData((prev) => ({ ...prev, [campo]: valor }));
  };

  const aplicarMascaraCpf = (valor: string) => {
    const v = valor.replace(/\D/g, '').slice(0, 11);
    return v.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
  };

  const aplicarMascaraCep = (valor: string) => {
    const v = valor.replace(/\D/g, '').slice(0, 8);
    return v.replace(/(\d{5})(\d{3})/, '$1-$2');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErroGeral(null);

    // Validações imediatas
    if (!formData.nomeCompleto.trim()) {
      setErroGeral('Nome completo é obrigatório.');
      setSecaoAtiva('pessoais');
      return;
    }
    if (!formData.cpf.trim()) {
      setErroGeral('CPF é obrigatório.');
      setSecaoAtiva('pessoais');
      return;
    }
    if (!formData.dataNascimento) {
      setErroGeral('Data de nascimento é obrigatória.');
      setSecaoAtiva('pessoais');
      return;
    }
    if (!formData.matricula.trim()) {
      setErroGeral('Matrícula é obrigatória.');
      setSecaoAtiva('organizacional');
      return;
    }

    try {
      setSalvando(true);
      await aoSalvar(formData);
      aoFechar();
    } catch (err: any) {
      setErroGeral(err.message || 'Erro ao salvar colaborador.');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="modal-overlay" style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
    }}>
      <div className="modal-content" style={{
        background: '#fff', borderRadius: '8px', maxWidth: '800px', width: '90%', maxHeight: '90vh', overflowY: 'auto', padding: '24px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #e0e0e0', paddingBottom: '12px' }}>
          <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#1976d2' }}>
            {colaboradorParaEditar ? 'Editar Colaborador' : 'Novo Colaborador'}
          </h2>
          <button type="button" onClick={aoFechar} style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer' }}>×</button>
        </div>

        {erroGeral && (
          <div style={{ background: '#ffebee', color: '#c62828', padding: '12px', borderRadius: '4px', marginTop: '16px' }} role="alert">
            {erroGeral}
          </div>
        )}

        {/* Abas das 4 seções (SPEC-03 Seção 7.2) */}
        <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid #ccc', margin: '16px 0' }}>
          {(['pessoais', 'contato', 'endereco', 'organizacional'] as const).map((aba) => (
            <button
              key={aba}
              type="button"
              onClick={() => setSecaoAtiva(aba)}
              style={{
                padding: '8px 16px',
                border: 'none',
                borderBottom: secaoAtiva === aba ? '3px solid #1976d2' : 'none',
                background: 'none',
                fontWeight: secaoAtiva === aba ? 'bold' : 'normal',
                color: secaoAtiva === aba ? '#1976d2' : '#666',
                cursor: 'pointer',
                textTransform: 'capitalize'
              }}
            >
              {aba === 'pessoais' && '1. Dados Pessoais'}
              {aba === 'contato' && '2. Contato'}
              {aba === 'endereco' && '3. Endereço'}
              {aba === 'organizacional' && '4. Dados Organizacionais'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit}>
          {/* SEÇÃO 1: DADOS PESSOAIS */}
          {secaoAtiva === 'pessoais' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Nome Completo *</label>
                <input
                  type="text"
                  required
                  value={formData.nomeCompleto}
                  onChange={(e) => handleChange('nomeCompleto', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>CPF *</label>
                <input
                  type="text"
                  required
                  placeholder="000.000.000-00"
                  value={formData.cpf}
                  onChange={(e) => handleChange('cpf', aplicarMascaraCpf(e.target.value))}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Data de Nascimento *</label>
                <input
                  type="date"
                  required
                  value={formData.dataNascimento}
                  onChange={(e) => handleChange('dataNascimento', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Sexo</label>
                <select
                  value={formData.sexo}
                  onChange={(e) => handleChange('sexo', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                >
                  <option value="MASCULINO">Masculino</option>
                  <option value="FEMININO">Feminino</option>
                  <option value="OUTRO">Outro / Prefiro não informar</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Estado Civil</label>
                <select
                  value={formData.estadoCivil}
                  onChange={(e) => handleChange('estadoCivil', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                >
                  <option value="SOLTEIRO">Solteiro(a)</option>
                  <option value="CASADO">Casado(a)</option>
                  <option value="DIVORCIADO">Divorciado(a)</option>
                  <option value="VIUVO">Viúvo(a)</option>
                  <option value="UNIAO_ESTAVEL">União Estável</option>
                </select>
              </div>
            </div>
          )}

          {/* SEÇÃO 2: CONTATO */}
          {secaoAtiva === 'contato' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>E-mail</label>
                <input
                  type="email"
                  placeholder="colaborador@empresa.com.br"
                  value={formData.email}
                  onChange={(e) => handleChange('email', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Telefone Fixo</label>
                <input
                  type="text"
                  placeholder="(00) 0000-0000"
                  value={formData.telefone}
                  onChange={(e) => handleChange('telefone', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Celular / WhatsApp</label>
                <input
                  type="text"
                  placeholder="(00) 90000-0000"
                  value={formData.celular}
                  onChange={(e) => handleChange('celular', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>
            </div>
          )}

          {/* SEÇÃO 3: ENDEREÇO */}
          {secaoAtiva === 'endereco' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>CEP</label>
                <input
                  type="text"
                  placeholder="00000-000"
                  value={formData.cep}
                  onChange={(e) => handleChange('cep', aplicarMascaraCep(e.target.value))}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div style={{ gridColumn: 'span 2' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Logradouro</label>
                <input
                  type="text"
                  value={formData.logradouro}
                  onChange={(e) => handleChange('logradouro', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Número</label>
                <input
                  type="text"
                  value={formData.numero}
                  onChange={(e) => handleChange('numero', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Complemento</label>
                <input
                  type="text"
                  value={formData.complemento}
                  onChange={(e) => handleChange('complemento', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Bairro</label>
                <input
                  type="text"
                  value={formData.bairro}
                  onChange={(e) => handleChange('bairro', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Cidade</label>
                <input
                  type="text"
                  value={formData.cidade}
                  onChange={(e) => handleChange('cidade', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>UF</label>
                <input
                  type="text"
                  maxLength={2}
                  value={formData.uf}
                  onChange={(e) => handleChange('uf', e.target.value.toUpperCase())}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>
            </div>
          )}

          {/* SEÇÃO 4: DADOS ORGANIZACIONAIS */}
          {secaoAtiva === 'organizacional' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Matrícula *</label>
                <input
                  type="text"
                  required
                  value={formData.matricula}
                  onChange={(e) => handleChange('matricula', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Departamento / Setor</label>
                <input
                  type="text"
                  placeholder="Ex: Recursos Humanos, TI"
                  value={formData.setor || formData.departamentoId}
                  onChange={(e) => {
                    handleChange('setor', e.target.value);
                    handleChange('departamentoId', e.target.value);
                  }}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Cargo</label>
                <input
                  type="text"
                  placeholder="Ex: Analista de RH"
                  value={formData.cargo || formData.cargoId}
                  onChange={(e) => {
                    handleChange('cargo', e.target.value);
                    handleChange('cargoId', e.target.value);
                  }}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Data de Admissão</label>
                <input
                  type="date"
                  value={formData.dataAdmissao}
                  onChange={(e) => handleChange('dataAdmissao', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Salário Base (R$)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.salarioBase}
                  onChange={(e) => handleChange('salarioBase', parseFloat(e.target.value) || 0)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Situação</label>
                <select
                  value={formData.situacao}
                  onChange={(e) => handleChange('situacao', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                >
                  <option value="ATIVO">Ativo</option>
                  <option value="INATIVO">Inativo</option>
                </select>
              </div>

              <div style={{ gridColumn: 'span 2' }}>
                <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '4px' }}>Observações</label>
                <textarea
                  rows={3}
                  value={formData.observacoes}
                  onChange={(e) => handleChange('observacoes', e.target.value)}
                  style={{ width: '100%', padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}
                />
              </div>
            </div>
          )}

          {/* Ações do Rodapé */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px', borderTop: '1px solid #e0e0e0', paddingTop: '16px' }}>
            <button
              type="button"
              onClick={aoFechar}
              disabled={salvando}
              style={{ padding: '8px 16px', background: '#f5f5f5', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer' }}
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={salvando}
              style={{
                padding: '8px 24px',
                background: salvando ? '#90caf9' : '#1976d2',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                cursor: salvando ? 'not-allowed' : 'pointer',
                fontWeight: 'bold'
              }}
            >
              {salvando ? 'Salvando...' : 'Salvar Colaborador'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
