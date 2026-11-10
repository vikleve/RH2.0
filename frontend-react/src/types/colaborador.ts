export interface Colaborador {
  id: number;
  empresa_id: string;
  filial_id?: string | null;
  matricula: string;
  nome_completo: string;
  cpf: string;
  cpf_mascarado?: string;
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
  rg?: string | null;
  criado_em?: string;
  atualizado_em?: string;
  dependentes?: Array<{
    id?: number;
    nome: string;
    parentesco: string;
    cpf?: string;
  }>;
}

export interface ColaboradoresMeta {
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

export interface ColaboradoresListResponse {
  data: Colaborador[];
  meta: ColaboradoresMeta;
}

export interface ColaboradorFormData {
  empresaId?: string;
  filialId?: string;
  matricula: string;
  nomeCompleto: string;
  cpf: string;
  dataNascimento: string;
  sexo?: string;
  estadoCivil?: string;
  email?: string;
  telefone?: string;
  celular?: string;
  cep?: string;
  logradouro?: string;
  numero?: string;
  complemento?: string;
  bairro?: string;
  cidade?: string;
  uf?: string;
  departamentoId?: string;
  cargoId?: string;
  cargo?: string;
  setor?: string;
  dataAdmissao?: string;
  salarioBase?: number;
  situacao?: string;
  observacoes?: string;
}
