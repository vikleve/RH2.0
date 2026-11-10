import { Injectable, OnModuleInit, OnModuleDestroy, Logger } from '@nestjs/common';
import { Pool, PoolClient } from 'pg';
import { newDb } from 'pg-mem';
import * as fs from 'fs';
import * as path from 'path';

@Injectable()
export class DatabaseService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(DatabaseService.name);
  private pool: Pool | any;
  private isPgMem = false;

  async onModuleInit() {
    const databaseUrl = process.env.DATABASE_URL?.trim();
    const isTest =
      process.env.NODE_ENV === 'test' ||
      process.env.TESTING === '1';

    // Se estiver em modo de teste e nenhuma DATABASE_URL foi explicitamente apontada
    if (isTest && !databaseUrl) {
      this.logger.log('Inicializando PostgreSQL em memória (pg-mem) para ambiente isolado de testes...');
      const db = newDb();
      const adapter = db.adapters.createPg();
      this.pool = new adapter.Pool();
      this.isPgMem = true;
      await this.executarMigracoes();
      return;
    }

    // Ambiente operacional (Produção, Staging ou Desenvolvimento sem flag de teste)
    if (!databaseUrl) {
      const msgErro =
        'FALHA CRÍTICA DE INICIALIZAÇÃO: A variável de ambiente DATABASE_URL é obrigatória para o PostgreSQL operacional. O sistema não pode inicializar sem banco persistente.';
      this.logger.error(msgErro);
      throw new Error(msgErro);
    }

    // Sanitiza connection string para logs sem expor credenciais
    const safeUrl = databaseUrl.replace(/:([^:@]+)@/, ':****@');
    this.logger.log(`Conectando ao PostgreSQL operacional: ${safeUrl}`);

    this.pool = new Pool({
      connectionString: databaseUrl,
      ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : undefined,
    });

    // Validação ativa da conexão (Fail-Fast)
    try {
      await this.pool.query('SELECT 1');
      this.logger.log('Conexão com PostgreSQL operacional estabelecida e validada com sucesso.');
    } catch (err) {
      const msgFalha = `FALHA CRÍTICA: Não foi possível conectar ao PostgreSQL operacional: ${err.message}`;
      this.logger.error(msgFalha);
      throw new Error(msgFalha);
    }

    // Executa e valida migrações obrigatórias
    await this.executarMigracoes();
  }

  async onModuleDestroy() {
    if (this.pool && typeof this.pool.end === 'function') {
      await this.pool.end();
    }
  }

  async query(text: string, params?: any[]): Promise<any> {
    return this.pool.query(text, params);
  }

  async getClient(): Promise<PoolClient> {
    return this.pool.connect();
  }

  private async executarMigracoes() {
    const migrationsDir = path.resolve(__dirname, '../../../migrations');
    if (!fs.existsSync(migrationsDir)) {
      const erroDir = `Diretório obrigatório de migrações não encontrado em: ${migrationsDir}`;
      this.logger.error(erroDir);
      throw new Error(erroDir);
    }

    const arquivos = [
      '001_schema_inicial.sql',
      '002_modulo_folha_pagamento.sql',
      '003_auditoria_autenticacao.sql',
      '004_modulo_colaboradores_spec03.sql',
    ];

    for (const arq of arquivos) {
      const fullPath = path.join(migrationsDir, arq);
      if (!fs.existsSync(fullPath)) {
        const erroArq = `Arquivo de migração obrigatório ausente: ${arq}`;
        this.logger.error(erroArq);
        throw new Error(erroArq);
      }

      let sql = fs.readFileSync(fullPath, 'utf-8');

      // Adaptações estritamente para o ambiente de testes sintéticos pg-mem
      if (this.isPgMem) {
        sql = sql
          .replace(/ALTER TABLE .* ENABLE ROW LEVEL SECURITY;/gi, '')
          .replace(/DROP POLICY IF EXISTS .*;/gi, '')
          .replace(/CREATE POLICY [\s\S]*?WITH CHECK \(true\);/gi, '')
          .replace(/BEGIN;/gi, '')
          .replace(/COMMIT;/gi, '')
          .replace(/TO_CHAR\(NOW\(\), 'YYYY-MM-DD HH24:MI:SS'\)/gi, "'2026-10-28 12:00:00'");
      }

      try {
        await this.pool.query(sql);
        this.logger.log(`Migração executada com sucesso: ${arq}`);
      } catch (err) {
        const erroMigracao = `FALHA CRÍTICA na execução da migração [${arq}]: ${err.message}`;
        this.logger.error(erroMigracao);
        throw new Error(erroMigracao);
      }
    }
  }
}
