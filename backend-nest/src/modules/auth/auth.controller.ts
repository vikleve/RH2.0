import {
  Body,
  Controller,
  Get,
  HttpCode,
  HttpException,
  HttpStatus,
  Post,
  Req,
  Res,
  UseGuards,
} from '@nestjs/common';
import { Request, Response } from 'express';
import { AuthService } from './auth.service';
import { SessionGuard } from './session.guard';
import { RateLimiterService } from '../rate-limiter/rate-limiter.service';
import { AuditService } from '../audit/audit.service';
import { CsrfGuard } from '../csrf/csrf.guard';
import { LoginDto } from './dto/login.dto';

@Controller('auth')
@UseGuards(CsrfGuard)
export class AuthController {
  constructor(
    private readonly authService: AuthService,
    private readonly rateLimiter: RateLimiterService,
    private readonly audit: AuditService,
  ) {}

  private extrairIp(req: Request): string {
    const xff = req.headers['x-forwarded-for'];
    if (xff) {
      return (Array.isArray(xff) ? xff[0] : xff.split(',')[0]).trim();
    }
    return req.socket.remoteAddress || '127.0.0.1';
  }

  @Post('login')
  @HttpCode(HttpStatus.OK)
  async login(
    @Body() body: LoginDto,
    @Req() req: Request,
    @Res({ passthrough: true }) res: Response,
  ) {
    const ip = this.extrairIp(req);
    const chave = `ip:${ip}`;

    // 1. Verificação de Rate Limit (5 tentativas em 15min / 900s)
    const { bloqueado, restante } = this.rateLimiter.estaBloqueado(chave);
    if (bloqueado) {
      await this.audit.registrarEvento(
        'BLOQUEIO_RATE_LIMIT',
        body.identificador ? String(body.identificador).slice(0, 100) : 'anônimo',
        ip,
        `Bloqueio ativo: excesso de tentativas (${restante}s restantes)`,
      );
      res.setHeader('Retry-After', String(restante));
      throw new HttpException(
        {
          sucesso: false,
          mensagem: 'Excesso de tentativas de login. Tente novamente mais tarde.',
          codigo: 'RATE_LIMIT_EXCEDIDO',
        },
        HttpStatus.TOO_MANY_REQUESTS,
      );
    }

    try {
      const { usuario, token } = await this.authService.autenticar(
        body.identificador,
        body.senha,
        ip,
      );

      // Sucesso reseta contador de tentativas
      this.rateLimiter.registrarSucesso(chave);

      // Configuração segura do Cookie de Sessão
      const isHttps =
        req.secure || req.headers['x-forwarded-proto'] === 'https';
      res.cookie('session_token', token, {
        path: '/',
        httpOnly: true,
        sameSite: 'lax',
        secure: isHttps,
        maxAge: 12 * 3600 * 1000,
      });

      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');

      return {
        sucesso: true,
        mensagem: 'Autenticação realizada com sucesso.',
        token, // Disponibilizado para clientes Bearer / testes
        usuario,
      };
    } catch (err) {
      if (err.status === HttpStatus.UNAUTHORIZED) {
        this.rateLimiter.registrarFalha(chave);
      }
      throw err;
    }
  }

  @Get('me')
  @UseGuards(SessionGuard)
  async me(@Req() req: any, @Res({ passthrough: true }) res: Response) {
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    return {
      sucesso: true,
      usuario: req.user,
    };
  }

  @Post('logout')
  @HttpCode(HttpStatus.OK)
  async logout(@Req() req: any, @Res({ passthrough: true }) res: Response) {
    const ip = this.extrairIp(req);
    let token = req.cookies?.['session_token'];
    const authHeader = req.headers['authorization'];
    if (!token && authHeader && authHeader.startsWith('Bearer ')) {
      token = authHeader.slice(7).trim();
    }

    if (token) {
      await this.authService.encerrarSessao(token, ip);
    }

    res.clearCookie('session_token', {
      path: '/',
      httpOnly: true,
      sameSite: 'lax',
    });
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');

    return {
      sucesso: true,
      mensagem: 'Sessão encerrada com sucesso.',
    };
  }
}
