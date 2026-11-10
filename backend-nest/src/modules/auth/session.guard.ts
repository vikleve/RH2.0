import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { Request } from 'express';
import { AuthService } from './auth.service';

@Injectable()
export class SessionGuard implements CanActivate {
  constructor(private readonly authService: AuthService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const req = context.switchToHttp().getRequest<Request>();
    let token: string | undefined;

    // 1. Authorization: Bearer <token>
    const authHeader = req.headers['authorization'];
    if (authHeader && authHeader.startsWith('Bearer ')) {
      token = authHeader.slice(7).trim();
    }

    // 2. Cookie session_token
    if (!token && req.cookies && req.cookies['session_token']) {
      token = req.cookies['session_token'];
    }

    if (!token) {
      throw new UnauthorizedException({
        sucesso: false,
        mensagem:
          'Acesso não autorizado. É necessário efetuar login para acessar este recurso.',
        codigo: 'NAO_AUTENTICADO',
      });
    }

    const usuario = await this.authService.validarSessao(token);
    if (!usuario) {
      throw new UnauthorizedException({
        sucesso: false,
        mensagem:
          'Acesso não autorizado. É necessário efetuar login para acessar este recurso.',
        codigo: 'NAO_AUTENTICADO',
      });
    }

    (req as any).user = usuario;
    (req as any).sessionToken = token;
    return true;
  }
}

