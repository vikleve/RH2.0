import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import * as cookieParser from 'cookie-parser';
import { AppModule } from '../src/app.module';
import { RateLimiterService } from '../src/modules/rate-limiter/rate-limiter.service';
import { AuditService } from '../src/modules/audit/audit.service';
import { DatabaseService } from '../src/database/database.service';

describe('Auth & Segurança RH2.0 (NestJS E2E)', () => {
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

  // AC-04: Validação de entradas
  it('AC-04: Rejeita login com campos vazios com HTTP 400', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({ identificador: '', senha: '' });

    expect(res.status).toBe(400);
    expect(res.body.sucesso).toBe(false);
  });

  // AC-05: Login válido
  it('AC-05: Login válido cria sessão e retorna cookie seguro e dados do operador', async () => {
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

  // AC-06: Mensagens genéricas
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

  // AC-07: Rate Limiting
  it('AC-07: Bloqueia na 6ª tentativa consecutiva com HTTP 429 e Retry-After', async () => {
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

  // AC-08: Hashing PBKDF2 com salt
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

  // AC-10: Persistência após refresh
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

  // AC-13: Proteção CSRF / Origin
  it('AC-13: Rejeita POST com Origin não autorizado com HTTP 403 Forbidden', async () => {
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

  // AC-16: Auditoria de Eventos
  it('AC-16: Tabela auditoria_autenticacao registra eventos sem senhas ou tokens', async () => {
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
      expect(det).not.toContain('hash');
    }
  });
});

