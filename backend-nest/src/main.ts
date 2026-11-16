import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import * as cookieParser from 'cookie-parser';
import * as express from 'express';
import * as path from 'path';
import * as fs from 'fs';
import { Logger, ValidationPipe } from '@nestjs/common';
import { validarOrigemCors } from './cors.config';

async function bootstrap() {
  const logger = new Logger('RH2.0-NestJS');
  const app = await NestFactory.create(AppModule);

  app.setGlobalPrefix('api');
  app.use(cookieParser());

  // Configuração global de validação estrita (RF-07)
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      forbidNonWhitelisted: true,
      transform: true,
    }),
  );

  // Configuração restritiva e segura de CORS (RF-01)
  app.enableCors({
    origin: validarOrigemCors,
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: [
      'Content-Type',
      'Authorization',
      'Origin',
      'Accept',
      'X-Forwarded-Proto',
      'X-Requested-With',
    ],
  });

  // Headers de segurança HTTP recomendados
  app.use((req: any, res: any, next: any) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('X-XSS-Protection', '1; mode=block');
    next();
  });

  // Servir frontend estático na raiz
  const candidatosFrontend = [
    path.resolve(process.cwd(), '../frontend'),
    path.resolve(process.cwd(), 'frontend'),
    path.resolve(__dirname, '../../frontend'),
    path.resolve(__dirname, '../../../frontend'),
  ];
  const frontendDir = candidatosFrontend.find((dir) => fs.existsSync(dir));
  if (frontendDir) {
    app.use(express.static(frontendDir));
    app.use((req: any, res: any, next: any) => {
      if (req.method === 'GET' && !req.path.startsWith('/api')) {
        return res.sendFile(path.join(frontendDir, 'index.html'));
      }
      next();
    });
    logger.log(`Frontend integrado ativo e servido a partir de: ${frontendDir}`);
  }

  const port = process.env.PORT || 8000;
  await app.listen(port);
  logger.log(`Servidor RH2.0 (NestJS + PostgreSQL) operando com sucesso na porta ${port}`);
}

bootstrap();
