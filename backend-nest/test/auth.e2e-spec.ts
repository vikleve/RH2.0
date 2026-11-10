import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import * as request from 'supertest';
import * as cookieParser from 'cookie-parser';
import * as crypto from 'crypto';
import { AppModule } from '../src/app.module';
import { RateLimiterService } from '../src/modules/rate-limiter/rate-limiter.service';
import { AuditService } from '../src/modules/audit/audit.service';
import { DatabaseService } from '../src/database/database.service';
import { validarOrigemCors } from '../src/cors.config';

describe('Auth & Segurança RH2.0 — SPEC-02 (NestJS E2E)', () => {
  let app: INestApplication;
  let rateLimiter: RateLimiterService;
  let auditService: AuditService;
  let db: DatabaseService;

  beforeAll(async () => {
    process.env.TESTING = '1';
    process.env.TEST_ADMIN_PASSWORD = 'Sintetico#AdminTest2026!';

    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.setGlobalPrefix('api');
    app.use(cookieParser());

    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        forbidNonWhitelisted: true,
        transform: true,
      }),
    );

    app.enableCors({
      origin: validarOrigemCors,
      credentials: true,
      methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
      allowedHeaders: ['Content-Type', 'Authorization', 'Origin', 'Accept', 'X-Forwarded-Proto'],
    });

    await app.init();

    rateLimiter = moduleFixture.get<RateLimiterService>(RateLimiterService);
    auditService = moduleFixture.get<AuditService>(AuditService);
    db = moduleFixture.get<DatabaseService>(DatabaseService);
  });

  afterAll(async () => {
    await app.close();
  });

  beforeEach(() => {
    rateLimiter.resetar();
  });

  // RF-01 & AC-04: Validação de entradas com ValidationPipe
  it('RF-07 / AC-04: Rejeita login com campos vazios ou inválidos com HTTP 400', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({ identificador: '', senha: '' });

    expect(res.status).toBe(400);
    expect(res.body.message).toBeDefined();
  });

  it('RF-07: Rejeita login com propriedades não autorizadas (forbidNonWhitelisted)', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'Sintetico#AdminTest2026!',
        campoInjetado: 'malicioso',
      });

    expect(res.status).toBe(400);
    expect(JSON.stringify(res.body)).toContain('property campoInjetado should not exist');
  });

  // RF-01: CORS Seguro
  it('RF-01: Permite requisições preflight OPTIONS e cabeçalhos CORS para origens autorizadas', async () => {
    const res = await request(app.getHttpServer())
      .options('/api/auth/login')
      .set('Origin', 'http://localhost:3000')
      .set('Access-Control-Request-Method', 'POST');

    expect(res.status).toBe(204);
    expect(res.headers['access-control-allow-origin']).toBe('http://localhost:3000');
    expect(res.headers['access-control-allow-credentials']).toBe('true');
  });

  it('RF-01: Bloqueia cabeçalhos CORS para origens não autorizadas', async () => {
    const res = await request(app.getHttpServer())
      .options('/api/auth/login')
      .set('Origin', 'http://hacker-dominio-invalido.org')
      .set('Access-Control-Request-Method', 'POST');

    // Express CORS não emite o header de allow para a origem rejeitada
    expect(res.headers['access-control-allow-origin']).toBeUndefined();
  });

  // RF-03 / AC-05: Login válido e Sessão segura
  it('RF-03 / AC-05: Login válido cria sessão, emite cookie HttpOnly e retorna dados', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'Sintetico#AdminTest2026!',
      });

    expect(res.status).toBe(200);
    expect(res.body.sucesso).toBe(true);
    expect(res.body.token).toBeDefined();
    expect(res.body.usuario.email).toBe('admin.dp@empresa.com.br');

    const cookies = res.headers['set-cookie'];
    expect(cookies).toBeDefined();
    expect(cookies[0]).toContain('session_token=');
    expect(cookies[0]).toContain('HttpOnly');
    expect(cookies[0]).toContain('SameSite=Lax');
  });

  // RF-03: Hashing de Token no banco (Token nunca fica cru na tabela sessoes)
  it('RF-03: Token de sessão é persistido no banco como Hash SHA-256 e não em texto puro', async () => {
    const loginRes = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'Sintetico#AdminTest2026!',
      });

    const rawToken = loginRes.body.token;
    const expectedHash = crypto.createHash('sha256').update(rawToken).digest('hex');

    const sessaoDb = await db.query(
      `SELECT token, revogado FROM sessoes WHERE token = $1 AND usuario_id = $2`,
      [expectedHash, loginRes.body.usuario.id],
    );

    expect(sessaoDb.rows.length).toBe(1);
    expect(sessaoDb.rows[0].token).toBe(expectedHash);
    expect(sessaoDb.rows[0].token).not.toBe(rawToken);
    expect(sessaoDb.rows[0].revogado).toBe(0);
  });

  // AC-06: Mensagens de erro uniformes
  it('AC-06: Rejeita usuário inexistente e senha incorreta com a mesma mensagem genérica', async () => {
    const res1 = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'fantasma@empresa.com.br',
        senha: 'QualquerCoisa123',
      });

    expect(res1.status).toBe(401);
    expect(res1.body.mensagem).toBe('E-mail ou senha inválidos.');

    const res2 = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'SenhaErrada999',
      });

    expect(res2.status).toBe(401);
    expect(res2.body.mensagem).toBe('E-mail ou senha inválidos.');
  });

  // RF-03 / AC-06: Usuário inativo
  it('RF-03: Usuário inativo é rejeitado com a mesma mensagem genérica sem vazar status', async () => {
    await db.query(
      `INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, criado_em)
       VALUES ('inativo@empresa.com.br', 'inativo.dp', 'Operador Inativo', 'dummyhash', 'dummysalt', 'operador_dp', 'inativo', '2026-10-28 12:00:00')`,
    );

    const res = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'inativo@empresa.com.br',
        senha: 'QualquerSenha123!',
      });

    expect(res.status).toBe(401);
    expect(res.body.mensagem).toBe('E-mail ou senha inválidos.');
  });

  // RF-05 / AC-07: Rate Limiting
  it('RF-05 / AC-07: Bloqueia na 6ª tentativa consecutiva com HTTP 429 e Retry-After', async () => {
    for (let i = 0; i < 5; i++) {
      const res = await request(app.getHttpServer())
        .post('/api/auth/login')
        .send({
          identificador: 'brute.force@teste.com',
          senha: `tentativa_${i}`,
        });
      expect(res.status).toBe(401);
    }

    const resBloqueio = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'brute.force@teste.com',
        senha: 'tentativa_6',
      });

    expect(resBloqueio.status).toBe(429);
    expect(resBloqueio.body.codigo).toBe('RATE_LIMIT_EXCEDIDO');
    expect(resBloqueio.headers['retry-after']).toBeDefined();
  });

  // AC-08: Hashing PBKDF2 com salt de 16 bytes
  it('AC-08: Senhas armazenadas como PBKDF2 com salt de 16 bytes e sem texto puro', async () => {
    const res = await db.query(
      `SELECT email, senha_hash, salt FROM usuarios WHERE email = $1`,
      ['admin.dp@empresa.com.br'],
    );
    expect(res.rows.length).toBe(1);
    const u = res.rows[0];
    expect(u.senha_hash.length).toBe(64);
    expect(u.salt.length).toBe(32);
    expect(u.senha_hash).not.toContain('Sintetico#AdminTest2026!');
  });

  // AC-10: Persistência após refresh com cookie HttpOnly
  it('AC-10: /api/auth/me mantém autenticação usando o cookie de sessão', async () => {
    const loginRes = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'Sintetico#AdminTest2026!',
      });

    const cookie = loginRes.headers['set-cookie'];

    const meRes = await request(app.getHttpServer())
      .get('/api/auth/me')
      .set('Cookie', cookie);

    expect(meRes.status).toBe(200);
    expect(meRes.body.sucesso).toBe(true);
    expect(meRes.body.usuario.email).toBe('admin.dp@empresa.com.br');
  });

  // AC-11: Proteção de rotas privadas
  it('AC-11: Endpoints privados bloqueiam requisições anônimas com HTTP 401', async () => {
    const res = await request(app.getHttpServer()).get('/api/colaboradores');
    expect(res.status).toBe(401);
    expect(res.body.codigo).toBe('NAO_AUTENTICADO');
  });

  // AC-12: Logout invalida sessão
  it('AC-12: Logout revoga sessão e limpa cookie; reuso retorna 401', async () => {
    const loginRes = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'Sintetico#AdminTest2026!',
      });

    const token = loginRes.body.token;
    const cookie = loginRes.headers['set-cookie'];

    const logoutRes = await request(app.getHttpServer())
      .post('/api/auth/logout')
      .set('Cookie', cookie);

    expect(logoutRes.status).toBe(200);

    const reusoRes = await request(app.getHttpServer())
      .get('/api/auth/me')
      .set('Authorization', `Bearer ${token}`);

    expect(reusoRes.status).toBe(401);
  });

  // RF-04 / AC-13: Proteção CSRF / Origin
  it('RF-04 / AC-13: Rejeita POST com Origin não autorizado com HTTP 403 Forbidden', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/auth/login')
      .set('Origin', 'http://site-hacker-malicioso.com')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'Sintetico#AdminTest2026!',
      });

    expect(res.status).toBe(403);
    expect(res.body.codigo).toBe('ORIGEM_PROIBIDA');
  });

  // RF-06 / AC-16: Auditoria de Eventos
  it('RF-06 / AC-16: Tabela auditoria_autenticacao registra eventos sem senhas ou segredos', async () => {
    const eventos = await auditService.listarEventos(20);
    expect(eventos.length).toBeGreaterThan(0);

    const tipos = new Set(eventos.map((e) => e.evento));
    expect(
      tipos.has('LOGIN_SUCESSO') ||
        tipos.has('LOGIN_FALHA') ||
        tipos.has('LOGOUT') ||
        tipos.has('BLOQUEIO_RATE_LIMIT'),
    ).toBe(true);

    for (const ev of eventos) {
      const det = (ev.detalhes || '').toLowerCase();
      expect(det).not.toContain('sintetico');
      expect(det).not.toContain('password');
    }
  });

  // RF-02: PostgreSQL Fail-fast em ambiente de produção
  it('RF-02: DatabaseService rejeita inicialização sem DATABASE_URL fora do ambiente de testes', async () => {
    const dbTestInstance = new DatabaseService();
    const oldTesting = process.env.TESTING;
    const oldNodeEnv = process.env.NODE_ENV;
    delete process.env.TESTING;
    delete process.env.NODE_ENV;
    delete process.env.DATABASE_URL;

    await expect(dbTestInstance.onModuleInit()).rejects.toThrow(
      /DATABASE_URL é obrigatória para o PostgreSQL operacional/,
    );

    process.env.TESTING = oldTesting;
    process.env.NODE_ENV = oldNodeEnv;
  });
});
