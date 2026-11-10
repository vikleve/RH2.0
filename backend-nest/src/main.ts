import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import * as cookieParser from 'cookie-parser';
import { Logger } from '@nestjs/common';

async function bootstrap() {
  const logger = new Logger('RH2.0-NestJS');
  const app = await NestFactory.create(AppModule);

  app.setGlobalPrefix('api');
  app.use(cookieParser());

  app.enableCors({
    origin: (origin, callback) => {
      // Permite mesma origem ou origens de desenvolvimento/configuradas
      callback(null, true);
    },
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Origin', 'Accept', 'X-Forwarded-Proto'],
  });

  // Headers de segurança padrão
  app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    next();
  });

  const port = process.env.PORT || 8000;
  await app.listen(port);
  logger.log(`Servidor RH2.0 (NestJS + PostgreSQL) operando com sucesso na porta ${port}`);
}

bootstrap();

