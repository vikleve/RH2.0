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
  @IsNotEmpty({ message: 'Matrícula é obrigatória.' })
  @IsString()
  matricula: string;

  @IsNotEmpty({ message: 'Nome completo é obrigatório.' })
  @IsString()
  nome_completo: string;

  @IsNotEmpty({ message: 'CPF é obrigatório.' })
  @IsString()
  cpf: string;

  @IsNotEmpty({ message: 'Data de nascimento é obrigatória.' })
  @IsString()
  data_nascimento: string;

  @IsNotEmpty({ message: 'E-mail é obrigatório.' })
  @IsString()
  email: string;

  @IsNotEmpty({ message: 'Data de admissão é obrigatória.' })
  @IsString()
  data_admissao: string;

  @IsNotEmpty({ message: 'Cargo é obrigatório.' })
  @IsString()
  cargo: string;

  @IsNotEmpty({ message: 'Setor é obrigatório.' })
  @IsString()
  setor: string;

  @IsNotEmpty({ message: 'Salário base é obrigatório.' })
  @IsNumber({}, { message: 'Salário base deve ser numérico.' })
  @Min(0, { message: 'Salário base não pode ser negativo.' })
  salario_base: number;

  @IsOptional()
  @IsString()
  rg?: string;

  @IsOptional()
  @IsString()
  telefone?: string;

  @IsOptional()
  @IsString()
  logradouro?: string;

  @IsOptional()
  @IsString()
  numero?: string;

  @IsOptional()
  @IsString()
  bairro?: string;

  @IsOptional()
  @IsString()
  cidade?: string;

  @IsOptional()
  @IsString()
  uf?: string;

  @IsOptional()
  @IsString()
  cep?: string;

  @IsOptional()
  @IsArray()
  dependentes?: DependenteDto[];
}
