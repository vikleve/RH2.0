import { IsNotEmpty, IsString, MaxLength } from 'class-validator';

export class LoginDto {
  @IsNotEmpty({ message: 'E-mail ou usuário é obrigatório.' })
  @IsString({ message: 'Identificador deve ser uma cadeia de texto.' })
  @MaxLength(100, { message: 'Identificador não pode exceder 100 caracteres.' })
  identificador: string;

  @IsNotEmpty({ message: 'Senha é obrigatória.' })
  @IsString({ message: 'Senha deve ser uma cadeia de texto.' })
  @MaxLength(128, { message: 'Senha não pode exceder 128 caracteres.' })
  senha: string;
}

