import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import * as request from 'supertest';
import * as cookieParser from 'cookie-parser';
import { AppModule } from '../src/app.module';
import { DatabaseService } from '../src/database/database.service';
import { AuthService } from '../src/modules/auth/auth.service';

describe('SPEC-03.1 — Segurança Multiempresa & Homologação de Colaboradores', () => {
  let app: INestApplication;
  let db: DatabaseService;
  let authService: AuthService;

  const empresa1Id = '11111111-1111-1111-1111-111111111111';
  const empresa2Id = '22222222-2222-2222-2222-222222222222';
  const senhaPadrao = 'SenhaSegura#2026!';

  let cookieAnalistaEmpresa1: string;
  let cookieAnalistaEmpresa2: string;
  let cookieOperadorEmpresa1: string;

  let colabEmpresa1Id: number;
  let colabEmpresa2Id: number;

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
        transform: true,
      }),
    );
    await app.init();

    db = app.get(DatabaseService);
    authService = app.get(AuthService);

    // Provisionar usuários de teste com segregação de escopo multiempresa (SPEC-03.1 Seção 3.1)
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const { hashHex, saltHex } = authService.hashSenha(senhaPadrao);

    // Analista RH da Empresa 1
    await db.query(
      `INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, criado_em, empresa_id)
       VALUES ($1, $2, $3, $4, $5, $6, 'ativo', $7, $8)`,
      [
        'analista.empresa1@rh2.com.br',
        'analista.emp1',
        'Analista RH Empresa 1',
        hashHex,
        saltHex,
        'analista_rh',
        agora,
        empresa1Id,
      ],
    );

    // Analista RH da Empresa 2
    await db.query(
      `INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, criado_em, empresa_id)
       VALUES ($1, $2, $3, $4, $5, $6, 'ativo', $7, $8)`,
      [
        'analista.empresa2@rh2.com.br',
        'analista.emp2',
        'Analista RH Empresa 2',
        hashHex,
        saltHex,
        'analista_rh',
        agora,
        empresa2Id,
      ],
    );

    // Operador DP da Empresa 1
    await db.query(
      `INSERT INTO usuarios (email, usuario, nome_completo, senha_hash, salt, perfil, status, criado_em, empresa_id)
       VALUES ($1, $2, $3, $4, $5, $6, 'ativo', $7, $8)`,
      [
        'operador.empresa1@rh2.com.br',
        'operador.emp1',
        'Operador DP Empresa 1',
        hashHex,
        saltHex,
        'operador_dp',
        agora,
        empresa1Id,
      ],
    );

    // Login dos usuários
    const loginEmp1 = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({ identificador: 'analista.empresa1@rh2.com.br', senha: senhaPadrao });
    cookieAnalistaEmpresa1 = loginEmp1.headers['set-cookie'][0];

    const loginEmp2 = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({ identificador: 'analista.empresa2@rh2.com.br', senha: senhaPadrao });
    cookieAnalistaEmpresa2 = loginEmp2.headers['set-cookie'][0];

    const loginOpEmp1 = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({ identificador: 'operador.empresa1@rh2.com.br', senha: senhaPadrao });
    cookieOperadorEmpresa1 = loginOpEmp1.headers['set-cookie'][0];

    // Criar colaborador da Empresa 1
    const resColab1 = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', cookieAnalistaEmpresa1)
      .send({
        matricula: 'EMP1-001',
        nomeCompleto: 'Colaborador Um Empresa 1',
        cpf: '11144477735',
        dataNascimento: '1990-05-10',
        email: 'colab1@empresa1.com.br',
        cargo: 'Desenvolvedor',
        setor: 'Tecnologia',
        salarioBase: 7000.0,
      });
    expect(resColab1.status).toBe(201);
    colabEmpresa1Id = resColab1.body.dados.id;
    expect(resColab1.body.dados.empresa_id).toBe(empresa1Id);

    // Criar colaborador da Empresa 2
    const resColab2 = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', cookieAnalistaEmpresa2)
      .send({
        matricula: 'EMP2-001',
        nomeCompleto: 'Colaborador Dois Empresa 2',
        cpf: '22255588846',
        dataNascimento: '1992-08-15',
        email: 'colab2@empresa2.com.br',
        cargo: 'Analista Financeiro',
        setor: 'Financeiro',
        salarioBase: 8000.0,
      });
    expect(resColab2.status).toBe(201);
    colabEmpresa2Id = resColab2.body.dados.id;
    expect(resColab2.body.dados.empresa_id).toBe(empresa2Id);
  });

  afterAll(async () => {
    await app.close();
  });

  // 3.4.1 — Usuário autorizado consultando sua empresa
  it('3.4.1: Usuário autorizado consulta exclusivamente os colaboradores de sua própria empresa', async () => {
    const res = await request(app.getHttpServer())
      .get('/api/colaboradores')
      .set('Cookie', cookieAnalistaEmpresa1);

    expect(res.status).toBe(200);
    expect(res.body.sucesso).toBe(true);
    expect(Array.isArray(res.body.data)).toBe(true);

    // Todos os colaboradores retornados devem pertencer à Empresa 1
    const ids = res.body.data.map((c: any) => c.id);
    expect(ids).toContain(colabEmpresa1Id);
    expect(ids).not.toContain(colabEmpresa2Id);

    res.body.data.forEach((c: any) => {
      expect(c.empresa_id).toBe(empresa1Id);
    });
  });

  // 3.4.2 — Usuário tentando consultar outra empresa
  it('3.4.2: Usuário é bloqueado ao tentar consultar colaboradores de outra empresa via filtro (403 Forbidden)', async () => {
    const res = await request(app.getHttpServer())
      .get(`/api/colaboradores?empresaId=${empresa2Id}`)
      .set('Cookie', cookieAnalistaEmpresa1);

    expect(res.status).toBe(403);
    expect(res.body.codigo).toBe('EMPRESA_NAO_AUTORIZADA');
    expect(res.body.mensagem).toContain('fora da sua abrangência autorizada');
  });

  // 3.4.3 — Usuário tentando acessar colaborador por ID de outra empresa (IDOR)
  it('3.4.3: Proteção contra IDOR — Usuário não pode acessar colaborador de outra empresa por ID (404 Not Found)', async () => {
    const res = await request(app.getHttpServer())
      .get(`/api/colaboradores/${colabEmpresa2Id}`)
      .set('Cookie', cookieAnalistaEmpresa1);

    // Retorna 404 para não vazar a existência do ID na outra empresa
    expect(res.status).toBe(404);
    expect(res.body.mensagem).toContain('não encontrado');
  });

  // 3.4.4 — Usuário tentando editar colaborador de outra empresa
  it('3.4.4: Proteção contra IDOR — Usuário não pode editar colaborador de outra empresa (404 Not Found)', async () => {
    const res = await request(app.getHttpServer())
      .patch(`/api/colaboradores/${colabEmpresa2Id}`)
      .set('Cookie', cookieAnalistaEmpresa1)
      .send({ celular: '11999998888', salarioBase: 9999 });

    expect(res.status).toBe(404);
    expect(res.body.mensagem).toContain('não encontrado');
  });

  // 3.4.5 — Usuário tentando inativar colaborador de outra empresa
  it('3.4.5: Proteção contra IDOR — Usuário não pode inativar colaborador de outra empresa (404 Not Found)', async () => {
    const res = await request(app.getHttpServer())
      .patch(`/api/colaboradores/${colabEmpresa2Id}/inativar`)
      .set('Cookie', cookieAnalistaEmpresa1)
      .send({ motivo: 'Ataque IDOR de inativação indevida' });

    expect(res.status).toBe(404);
    expect(res.body.mensagem).toContain('não encontrado');

    // Confirma com o analista da Empresa 2 que o colaborador 2 permanece ativo
    const checkRes = await request(app.getHttpServer())
      .get(`/api/colaboradores/${colabEmpresa2Id}`)
      .set('Cookie', cookieAnalistaEmpresa2);
    expect(checkRes.status).toBe(200);
    expect(checkRes.body.dados.situacao.toLowerCase()).toBe('ativo');
  });

  // 3.4.6 — Usuário tentando alterar "empresaId" no payload
  it('3.4.6a: Bloqueia cadastro com empresaId de outra empresa injetado no payload (403 Forbidden)', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', cookieAnalistaEmpresa1)
      .send({
        empresaId: empresa2Id, // Tentativa de cadastrar na Empresa 2
        matricula: 'EMP1-INJ-001',
        nomeCompleto: 'Injeção Empresa Indevida',
        cpf: '52998224725',
        dataNascimento: '1985-01-01',
      });

    expect(res.status).toBe(403);
    expect(res.body.codigo).toBe('EMPRESA_NAO_AUTORIZADA');
    expect(res.body.mensagem).toContain('fora do seu escopo autorizado');
  });

  it('3.4.6b: Bloqueia transferência de empresa alterando empresaId no payload do PATCH (403 Forbidden)', async () => {
    const res = await request(app.getHttpServer())
      .patch(`/api/colaboradores/${colabEmpresa1Id}`)
      .set('Cookie', cookieAnalistaEmpresa1)
      .send({
        empresaId: empresa2Id, // Tentativa de transferir para a Empresa 2
        observacoes: 'Tentando transferir para outra empresa',
      });

    expect(res.status).toBe(403);
    expect(res.body.codigo).toBe('EMPRESA_NAO_AUTORIZADA');
  });

  // 3.4.7 — Usuário tentando ampliar abrangência usando filtros
  it('3.4.7: Bloqueia tentativa de ampliação de abrangência por filtros combinados (403 Forbidden)', async () => {
    const res = await request(app.getHttpServer())
      .get(`/api/colaboradores?empresaId=${empresa2Id}&situacao=ativo&search=Colaborador`)
      .set('Cookie', cookieAnalistaEmpresa1);

    expect(res.status).toBe(403);
    expect(res.body.codigo).toBe('EMPRESA_NAO_AUTORIZADA');
  });

  // RBAC — Controle de perfil: operador_dp não pode cadastrar nem inativar
  it('Fase 2 / RBAC: Bloqueia operador_dp de cadastrar colaborador (403 Forbidden)', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', cookieOperadorEmpresa1)
      .send({
        matricula: 'OP-001',
        nomeCompleto: 'Operador Tentando Cadastrar',
        cpf: '33366699957',
        dataNascimento: '1990-01-01',
      });

    expect(res.status).toBe(403);
  });

  it('Fase 2 / RBAC: Bloqueia operador_dp de inativar colaborador (403 Forbidden)', async () => {
    const res = await request(app.getHttpServer())
      .patch(`/api/colaboradores/${colabEmpresa1Id}/inativar`)
      .set('Cookie', cookieOperadorEmpresa1)
      .send({ motivo: 'Operador tentando inativar' });

    expect(res.status).toBe(403);
  });
});
