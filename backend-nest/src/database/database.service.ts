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
    const isTest = process.env.NODE_ENV === 'test' || process.env.TESTING === '1';

    if (databaseUrl && !isTest) {
      this.logger.log(`Conectando ao PostgreSQL via DATABASE_URL...`);
      this.pool = new Pool({
        connectionString: databaseUrl,
        ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : undefined,
      });
      await this.executarMigracoes();
    } else {
      this.logger.log(`Inicializando PostgreSQL em memória (pg-mem) para testes e ambiente efêmero...`);
      const db = newDb();
      const adapter = db.adapters.createPg();
      this.pool = new adapter.Pool();
      this.isPgMem = true;
      await this.executarMigracoes();
    }
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
    // Procura as migrações SQL em migrations/
    const migrationsDir = path.resolve(__dirname, '../../../migrations');
    if (!fs.existsSync(migrationsDir)) {
      this.logger.warn(`Diretório de migrações não encontrado em ${migrationsDir}`);
      return;
    }

    const arquivos = ['001_schema_inicial.sql', '002_modulo_folha_pagamento.sql', '003_auditoria_autenticacao.sql'];
    for (const arq of arquivos) {
      const fullPath = path.join(migrationsDir, arq);
      if (fs.existsSync(fullPath)) {
        let sql = fs.readFileSync(fullPath, 'utf-8');
        // Remove comandos específicos não suportados pelo pg-mem se aplicável
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
          this.logger.error(`Erro ao aplicar migração ${arq}: ${err.message}`);
        }
      }
    }
  }
}
