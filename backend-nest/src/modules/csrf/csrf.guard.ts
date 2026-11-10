import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { Request } from 'express';
import { obterOrigensPermitidas } from '../../cors.config';

@Injectable()
export class CsrfGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest<Request>();
    const metodo = req.method.toUpperCase();

    // Métodos seguros (idempotentes/leitura) são isentos de CSRF
    if (['GET', 'HEAD', 'OPTIONS'].includes(metodo)) {
      return true;
    }

    const permitidas = new Set(obterOrigensPermitidas());
    const origem = (req.headers['origin'] as string) || '';
    const referer = (req.headers['referer'] as string) || '';
    const hostHeader = (req.headers['host'] as string) || '';

    // 1. Verificação de cabeçalho Origin
    if (origem) {
      const origemNorm = origem.trim().replace(/\/$/, '');
      if (permitidas.has(origemNorm)) {
        return true;
      }

      try {
        const parsed = new URL(origemNorm);
        if (hostHeader && parsed.host === hostHeader) {
          return true;
        }

        if (['127.0.0.1', 'localhost', '0.0.0.0'].includes(parsed.hostname)) {
          const hostNameOnly = hostHeader.split(':')[0];
          if (!hostHeader || ['127.0.0.1', 'localhost', '0.0.0.0'].includes(hostNameOnly)) {
            return true;
          }
        }
      } catch {
        // Formato de URL inválido
      }

      throw new ForbiddenException({
        sucesso: false,
        mensagem: `Requisição bloqueada por política de segurança de origem: Origem '${origem}' não autorizada.`,
        codigo: 'ORIGEM_PROIBIDA',
      });
    }

    // 2. Verificação de Referer quando Origin estiver ausente
    if (referer) {
      try {
        const parsedRef = new URL(referer);
        const refOrigem = `${parsedRef.protocol}//${parsedRef.host}`;
        if (permitidas.has(refOrigem)) {
          return true;
        }
        if (hostHeader && parsedRef.host === hostHeader) {
          return true;
        }
        if (['127.0.0.1', 'localhost'].includes(parsedRef.hostname)) {
          return true;
        }
      } catch {
        // Referer malformado
      }

      throw new ForbiddenException({
        sucesso: false,
        mensagem: `Requisição bloqueada por política de segurança de origem: Referer '${referer}' não autorizado.`,
        codigo: 'ORIGEM_PROIBIDA',
      });
    }

    // 3. Verificação de Sec-Fetch-Site para mitigar ataques cross-site de navegadores modernos
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
