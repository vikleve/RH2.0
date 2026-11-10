import { IsOptional, IsString } from 'class-validator';
import { Type } from 'class-transformer';

export class QueryColaboradorDto {
  @IsOptional()
  @Type(() => Number)
  page?: number = 1;

  @IsOptional()
  @Type(() => Number)
  limit?: number = 20;

  @IsOptional()
  @IsString()
  search?: string;

  @IsOptional()
  @IsString()
  q?: string;

  @IsOptional()
  @IsString()
  situacao?: string;

  @IsOptional()
  @IsString()
  departamentoId?: string;

  @IsOptional()
  @IsString()
  setor?: string;

  @IsOptional()
  @IsString()
  filialId?: string;

  @IsOptional()
  @IsString()
  empresaId?: string;
}
