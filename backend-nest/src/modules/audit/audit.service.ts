import { Injectable, Logger } from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';

export type EventoAuditoria = 'LOGIN_SUCESSO' | 'LOGIN_FALHA' | 'LOGOUT' | 'BLOQUEIO_RATE_LIMIT';

@Injectable()
export class AuditService {
  private readonly logger = new Logger(AuditService.name);

  constructor(private readonly db: DatabaseService) {}

  sanitizarIdentificador(identificador?: string): string {
    if (!identificador) return 'anônimo';
    return String(identificador).trim().replace(/[\r\n]/g, ' ').slice(0, 100);
  }

  async registrarEvento(
    evento: EventoAuditoria,
    identificador?: string,
    ipOrigem?: string,
    detalhes?: string,
  ): Promise<boolean> {
    const identSeguro = this.sanitizarIdentificador(identificador);
    const ipSeguro = (ipOrigem ? String(ipOrigem).trim() : '127.0.0.1').slice(0, 45);
    const detalhesSeguro = (detalhes ? String(detalhes).trim() : '').slice(0, 255);
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

    try {
      await this.db.query(
        `INSERT INTO auditoria_autenticacao (evento, identificador, ip_origem, detalhes, criado_em)
         VALUES ($1, $2, $3, $4, $5)`,
        [evento, identSeguro, ipSeguro, detalhesSeguro, agora],
      );
      return true;
    } catch (err) {
      this.logger.error(`Falha ao registrar auditoria de autenticação: ${err.message}`);
      return false;
    }
  }

  async listarEventos(limite = 50, evento?: EventoAuditoria): Promise<any[]> {
    if (evento) {
      const res = await this.db.query(
        `SELECT id, evento, identificador, ip_origem, detalhes, criado_em
         FROM auditoria_autenticacao
         WHERE evento = $1
         ORDER BY id DESC
         LIMIT $2`,
        [evento, limite],
      );
      return res.rows;
    } else {
      const res = await this.db.query(
        `SELECT id, evento, identificador, ip_origem, detalhes, criado_em
         FROM auditoria_autenticacao
         ORDER BY id DESC
         LIMIT $1`,
        [limite],
      );
      return res.rows;
    }
  }
}

