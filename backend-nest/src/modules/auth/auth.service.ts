import {
  BadRequestException,
  Injectable,
  OnModuleInit,
  UnauthorizedException,
} from '@nestjs/common';
import * as crypto from 'crypto';
import { DatabaseService } from '../../database/database.service';
import { AuditService } from '../audit/audit.service';

export const ITERATIONS = 100_000;
export const SESSION_DURATION_HOURS = 12;
export const MENSAGEM_GENERICA_ERRO = 'E-mail ou senha inválidos.';

@Injectable()
export class AuthService implements OnModuleInit {
  constructor(
    private readonly db: DatabaseService,
    private readonly audit: AuditService,
  ) {}

  async onModuleInit() {
    await this.provisionarUsuarioInicial();
  }

  hashSenha(senha: string, salt?: string): { hashHex: string; saltHex: string } {
    const saltHex = salt || crypto.randomBytes(16).toString('hex');
    const hashBytes = crypto.pbkdf2Sync(
      senha,
      saltHex,
      ITERATIONS,
      32,
      'sha256',
    );
    return {
      hashHex: hashBytes.toString('hex'),
      saltHex,
    };
  }

  verificarSenha(senha: string, senhaHashHex: string, saltHex: string): boolean {
    const { hashHex } = this.hashSenha(senha, saltHex);
    const bufCalculado = Buffer.from(hashHex, 'hex');
    const bufArmazenado = Buffer.from(senhaHashHex, 'hex');
    if (bufCalculado.length !== bufArmazenado.length) {
      return false;
    }
    return crypto.timingSafeEqual(bufCalculado, bufArmazenado);
  }

  async provisionarUsuarioInicial(): Promise<void> {
    const res = await this.db.query(
      `SELECT id, email, usuario FROM usuarios WHERE email = $1 OR usuario = $2`,
      ['admin.dp@empresa.com.br', 'admin.dp'],
    );

    const isTest =
      process.env.NODE_ENV === 'test' ||
      process.env.TESTING === '1' ||
      typeof jest !== 'undefined';

    if (res.rows.length === 0) {
      let senhaInicial = process.env.ADMIN_INITIAL_PASSWORD;
      if (!senhaInicial) {
        if (isTest) {
          senhaInicial = process.env.TEST_ADMIN_PASSWORD || 'Sintetico#AdminTest2026!';
        } else {
          throw new Error(
            'Falha de segurança operacional: A variável de ambiente ADMIN_INITIAL_PASSWORD não foi configurada.',
          );
        }
      }

      const { hashHex, saltHex } = this.hashSenha(senhaInicial);
      const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

      await this.db.query(
        `INSERT INTO usuarios (
          email, usuario, nome_completo, senha_hash, salt, perfil, status, criado_em
        ) VALUES ($1, $2, $3, $4, $5, $6, 'ativo', $7)`,
        [
          'admin.dp@empresa.com.br',
          'admin.dp',
          'Administrador (RH/DP)',
          hashHex,
          saltHex,
          'administrador',
          agora,
        ],
      );
    }
  }

  async autenticar(
    identificador: string,
    senha: string,
    ipOrigem?: string,
  ): Promise<{ usuario: any; token: string }> {
    if (!identificador || !senha) {
      throw new BadRequestException({
        sucesso: false,
        mensagem: 'E-mail e senha são obrigatórios.',
      });
    }

    const identLimpo = identificador.trim().toLowerCase();
    const res = await this.db.query(
      `SELECT id, email, usuario, nome_completo, senha_hash, salt, perfil, status
       FROM usuarios
       WHERE LOWER(email) = $1 OR LOWER(usuario) = $2`,
      [identLimpo, identLimpo],
    );

    if (res.rows.length === 0) {
      await this.audit.registrarEvento(
        'LOGIN_FALHA',
        identLimpo,
        ipOrigem,
        'Usuário não encontrado',
      );
      throw new UnauthorizedException({
        sucesso: false,
        mensagem: MENSAGEM_GENERICA_ERRO,
      });
    }

    const usuario = res.rows[0];

    if (usuario.status !== 'ativo') {
      await this.audit.registrarEvento(
        'LOGIN_FALHA',
        identLimpo,
        ipOrigem,
        'Tentativa em conta inativa',
      );
      throw new UnauthorizedException({
        sucesso: false,
        mensagem: MENSAGEM_GENERICA_ERRO,
      });
    }

    const senhaCorreta = this.verificarSenha(
      senha,
      usuario.senha_hash,
      usuario.salt,
    );
    if (!senhaCorreta) {
      await this.audit.registrarEvento(
        'LOGIN_FALHA',
        identLimpo,
        ipOrigem,
        'Senha incorreta',
      );
      throw new UnauthorizedException({
        sucesso: false,
        mensagem: MENSAGEM_GENERICA_ERRO,
      });
    }

    // Regeneração de sessão (invalida sessões ativas prévias)
    await this.db.query(
      `UPDATE sessoes SET revogado = 1 WHERE usuario_id = $1 AND revogado = 0`,
      [usuario.id],
    );

    const token = crypto.randomBytes(32).toString('hex');
    const agoraDt = new Date();
    const expiraDt = new Date(
      agoraDt.getTime() + SESSION_DURATION_HOURS * 3600 * 1000,
    );
    const agoraStr = agoraDt.toISOString().replace('T', ' ').slice(0, 19);
    const expiraStr = expiraDt.toISOString().replace('T', ' ').slice(0, 19);

    await this.db.query(
      `INSERT INTO sessoes (token, usuario_id, criado_em, expira_em, revogado)
       VALUES ($1, $2, $3, $4, 0)`,
      [token, usuario.id, agoraStr, expiraStr],
    );

    await this.db.query(
      `UPDATE usuarios SET ultimo_login = $1 WHERE id = $2`,
      [agoraStr, usuario.id],
    );

    await this.audit.registrarEvento(
      'LOGIN_SUCESSO',
      usuario.email,
      ipOrigem,
      'Autenticação válida',
    );

    return {
      usuario: {
        id: usuario.id,
        email: usuario.email,
        usuario: usuario.usuario,
        nome_completo: usuario.nome_completo,
        perfil: usuario.perfil,
      },
      token,
    };
  }

  async validarSessao(token: string): Promise<any | null> {
    if (!token) return null;
    const agoraStr = new Date().toISOString().replace('T', ' ').slice(0, 19);

    const res = await this.db.query(
      `SELECT u.id, u.email, u.usuario, u.nome_completo, u.perfil
       FROM sessoes s
       JOIN usuarios u ON u.id = s.usuario_id
       WHERE s.token = $1
         AND s.revogado = 0
         AND s.expira_em > $2
         AND u.status = 'ativo'`,
      [token, agoraStr],
    );

    if (res.rows.length === 0) return null;
    return res.rows[0];
  }

  async encerrarSessao(token: string, ipOrigem?: string): Promise<boolean> {
    if (!token) return false;
    const usuario = await this.validarSessao(token);
    const ident = usuario?.email || 'token-desconhecido';

    const res = await this.db.query(
      `UPDATE sessoes SET revogado = 1 WHERE token = $1`,
      [token],
    );

    if (res.rowCount > 0) {
      await this.audit.registrarEvento(
        'LOGOUT',
        ident,
        ipOrigem,
        'Sessão encerrada com sucesso',
      );
      return true;
    }
    return false;
  }
}

