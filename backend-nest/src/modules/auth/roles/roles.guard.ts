import {
  Injectable,
  CanActivate,
  ExecutionContext,
  ForbiddenException,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { ROLES_KEY } from './roles.decorator';

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.getAllAndOverride<string[]>(ROLES_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);

    if (!requiredRoles || requiredRoles.length === 0) {
      return true;
    }

    const { user } = context.switchToHttp().getRequest();
    if (!user || !user.perfil) {
      throw new ForbiddenException({
        sucesso: false,
        mensagem: 'Acesso negado: perfil de usuário não identificado.',
        codigo: 'PERFIL_INVALIDO',
      });
    }

    const autorizado = requiredRoles.includes(user.perfil);
    if (!autorizado) {
      throw new ForbiddenException({
        sucesso: false,
        mensagem: `Acesso negado: o perfil '${user.perfil}' não possui permissão para este recurso. Perfis autorizados: ${requiredRoles.join(', ')}.`,
        codigo: 'PERMISSAO_INSUFICIENTE',
      });
    }

    return true;
  }
}
