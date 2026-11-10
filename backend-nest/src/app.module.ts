import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { DatabaseModule } from './database/database.module';
import { AuditModule } from './modules/audit/audit.module';
import { RateLimiterModule } from './modules/rate-limiter/rate-limiter.module';
import { CsrfModule } from './modules/csrf/csrf.module';
import { AuthModule } from './modules/auth/auth.module';
import { ColaboradoresModule } from './modules/colaboradores/colaboradores.module';
import { FolhaModule } from './modules/folha/folha.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    DatabaseModule,
    AuditModule,
    RateLimiterModule,
    CsrfModule,
    AuthModule,
    ColaboradoresModule,
    FolhaModule,
  ],
})
export class AppModule {}

