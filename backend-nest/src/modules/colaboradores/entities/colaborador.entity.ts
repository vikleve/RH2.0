/**
 * Entidade Colaborador — RH2.0 (SPEC-03)
 */
export interface ColaboradorEntity {
  id: number;
  empresa_id: string;
  filial_id?: string | null;
  matricula: string;
  nome_completo: string;
  cpf: string;
  data_nascimento: string;
  sexo?: string | null;
  estado_civil?: string | null;
  email?: string | null;
  telefone?: string | null;
  celular?: string | null;
  cep?: string | null;
  logradouro?: string | null;
  numero?: string | null;
  complemento?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  uf?: string | null;
  departamento_id?: string | null;
  cargo_id?: string | null;
  data_admissao?: string | null;
  cargo?: string | null;
  setor?: string | null;
  salario_base?: number | null;
  situacao: 'ATIVO' | 'INATIVO' | 'ativo' | 'inativo';
  observacoes?: string | null;
  criado_em: string;
  atualizado_em: string;
  criado_por: string;
  atualizado_por?: string | null;
  dependentes?: any[];
}
