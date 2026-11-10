import {
  IsArray,
  IsNumber,
  IsOptional,
  IsString,
  Min,
} from 'class-validator';
import { DependenteDto } from './create-colaborador.dto';

export class UpdateColaboradorDto {
  @IsOptional()
  @IsString()
  matricula?: string;

  @IsOptional()
  @IsString()
  nome_completo?: string;

  @IsOptional()
  @IsString()
  cpf?: string;

  @IsOptional()
  @IsString()
  data_nascimento?: string;

  @IsOptional()
  @IsString()
  email?: string;

  @IsOptional()
  @IsString()
  data_admissao?: string;

  @IsOptional()
  @IsString()
  cargo?: string;

  @IsOptional()
  @IsString()
  setor?: string;

  @IsOptional()
  @IsNumber({}, { message: 'Salário base deve ser numérico.' })
  @Min(0, { message: 'Salário base não pode ser negativo.' })
  salario_base?: number;

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
