import {
  IsArray,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsString,
  Min,
} from 'class-validator';

export class DependenteDto {
  @IsNotEmpty({ message: 'Nome do dependente é obrigatório.' })
  @IsString()
  nome: string;

  @IsNotEmpty({ message: 'Parentesco do dependente é obrigatório.' })
  @IsString()
  parentesco: string;

  @IsOptional()
  @IsString()
  cpf?: string;
}

export class CreateColaboradorDto {
  // Empresa & Filial
  @IsOptional()
  @IsString()
  empresaId?: string;

  @IsOptional()
  @IsString()
  empresa_id?: string;

  @IsOptional()
  @IsString()
  filialId?: string;

  @IsOptional()
  @IsString()
  filial_id?: string;

  // Identificação
  @IsNotEmpty({ message: 'Matrícula é obrigatória.' })
  @IsString()
  matricula: string;

  @IsOptional()
  @IsString()
  nomeCompleto?: string;

  @IsOptional()
  @IsString()
  nome_completo?: string;

  @IsNotEmpty({ message: 'CPF é obrigatório.' })
  @IsString()
  cpf: string;

  @IsOptional()
  @IsString()
  dataNascimento?: string;

  @IsOptional()
  @IsString()
  data_nascimento?: string;

  @IsOptional()
  @IsString()
  sexo?: string;

  @IsOptional()
  @IsString()
  estadoCivil?: string;

  @IsOptional()
  @IsString()
  estado_civil?: string;

  // Contato
  @IsOptional()
  @IsString()
  email?: string;

  @IsOptional()
  @IsString()
  telefone?: string;

  @IsOptional()
  @IsString()
  celular?: string;

  // Endereço
  @IsOptional()
  @IsString()
  cep?: string;

  @IsOptional()
  @IsString()
  logradouro?: string;

  @IsOptional()
  @IsString()
  numero?: string;

  @IsOptional()
  @IsString()
  complemento?: string;

  @IsOptional()
  @IsString()
  bairro?: string;

  @IsOptional()
  @IsString()
  cidade?: string;

  @IsOptional()
  @IsString()
  uf?: string;

  // Dados Organizacionais
  @IsOptional()
  @IsString()
  departamentoId?: string;

  @IsOptional()
  @IsString()
  departamento_id?: string;

  @IsOptional()
  @IsString()
  cargoId?: string;

  @IsOptional()
  @IsString()
  cargo_id?: string;

  @IsOptional()
  @IsString()
  cargo?: string;

  @IsOptional()
  @IsString()
  setor?: string;

  @IsOptional()
  @IsString()
  dataAdmissao?: string;

  @IsOptional()
  @IsString()
  data_admissao?: string;

  @IsOptional()
  @IsNumber({}, { message: 'Salário base deve ser numérico.' })
  @Min(0, { message: 'Salário base não pode ser negativo.' })
  salario_base?: number;

  @IsOptional()
  @IsNumber({}, { message: 'Salário base deve ser numérico.' })
  @Min(0, { message: 'Salário base não pode ser negativo.' })
  salarioBase?: number;

  @IsOptional()
  @IsString()
  situacao?: string;

  @IsOptional()
  @IsString()
  observacoes?: string;

  @IsOptional()
  @IsString()
  rg?: string;

  @IsOptional()
  @IsArray()
  dependentes?: DependenteDto[];
}
