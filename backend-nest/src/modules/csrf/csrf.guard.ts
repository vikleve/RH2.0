import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { Request } from 'express';
import * as url from 'url';

@Injectable()
export class CsrfGuard implements CanActivate {
  private origensPermitidas: Set<string>;

  constructor() {
    const envOrigins = process.env.ALLOWED_ORIGINS || '';
    this.origensPermitidas = new Set(
      envOrigins
        .split(',')
        .map((o) => o.trim().replace(/\/$/, ''))
        .filter(Boolean),
    );
  }

  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<Request>();
    const metodo = req.method.toUpperCase();

    // Métodos seguros não alteram estado
    if (['GET', 'HEAD', 'OPTIONS'].includes(metodo)) {
      return true;
    }

    const origem = (req.headers['origin'] as string) || '';
    const referer = (req.headers['referer'] as string) || '';
    const hostHeader = (req.headers['host'] as string) || '';

    // 1. Verificação de Origin
    if (origem) {
      const origemNorm = origem.replace(/\/$/, '');
      if (this.origensPermitidas.has(origemNorm)) {
        return true;
      }

      const parsed = url.parse(origemNorm);
      if (hostHeader && parsed.host === hostHeader) {
        return true;
      }

      if (['127.0.0.1', 'localhost', '0.0.0.0'].includes(parsed.hostname || '')) {
        const hostNameOnly = hostHeader.split(':')[0];
        if (!hostHeader || ['127.0.0.1', 'localhost', '0.0.0.0'].includes(hostNameOnly)) {
          return true;
        }
      }

      throw new ForbiddenException({
        sucesso: false,
        mensagem: `Requisição bloqueada por política de segurança de origem: Origem '${origem}' não autorizada.`,
        codigo: 'ORIGEM_PROIBIDA',
      });
    }

    // 2. Verificação de Referer quando Origin não está presente
    if (referer) {
      const parsedRef = url.parse(referer);
      if (hostHeader && parsedRef.host === hostHeader) {
        return true;
      }
      if (['127.0.0.1', 'localhost'].includes(parsedRef.hostname || '')) {
        return true;
      }
      throw new ForbiddenException({
        sucesso: false,
        mensagem: `Requisição bloqueada por política de segurança de origem: Referer '${referer}' não autorizado.`,
        codigo: 'ORIGEM_PROIBIDA',
      });
    }

    // 3. Sec-Fetch-Site cross-site
    const secFetch = req.headers['sec-fetch-site'];
    if (secFetch === 'cross-site') {
      throw new ForbiddenException({
        sucesso: false,
        mensagem: 'Requisição cross-site bloqueada por Sec-Fetch-Site.',
        codigo: 'ORIGEM_PROIBIDA',
      });
    }

    return true;
  }
}

