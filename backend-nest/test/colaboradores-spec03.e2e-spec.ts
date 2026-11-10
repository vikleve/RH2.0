import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import * as request from 'supertest';
import * as cookieParser from 'cookie-parser';
import { AppModule } from '../src/app.module';

describe('Módulo de Cadastro de Colaboradores — SPEC-03 (NestJS E2E)', () => {
  let app: INestApplication;
  let authCookie: string;
  const empresaTesteId = 'b1111111-1111-1111-1111-111111111111';
  const filialTesteId = 'c2222222-2222-2222-2222-222222222222';
  const deptTesteId = 'd3333333-3333-3333-3333-333333333333';
  let colaboradorCriadoId: number;

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

    // Autenticação para obter o cookie seguro
    const loginRes = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'Sintetico#AdminTest2026!',
      });

    expect(loginRes.status).toBe(200);
    const cookies = loginRes.headers['set-cookie'];
    expect(cookies).toBeDefined();
    authCookie = cookies[0];
  });

  afterAll(async () => {
    await app.close();
  });

  // RF-10: Segurança — bloqueio de acesso anônimo
  it('RF-10: Bloqueia acesso a endpoints de colaboradores sem autenticação (401)', async () => {
    const res = await request(app.getHttpServer()).get('/api/colaboradores');
    expect(res.status).toBe(401);
  });

  // RF-04 & Seção 6.1: Cadastro de Colaborador com sucesso
  it('RF-04 & Seção 6.1: Cadastra novo colaborador com payload oficial SPEC-03 (201)', async () => {
    const payload = {
      empresaId: empresaTesteId,
      filialId: filialTesteId,
      matricula: 'SPEC03-001',
      nomeCompleto: 'Carlos Eduardo Oliveira',
      cpf: '52998224725',
      dataNascimento: '1988-04-12',
      sexo: 'MASCULINO',
      estadoCivil: 'CASADO',
      email: 'carlos.oliveira@empresa.com.br',
      telefone: '1133334444',
      celular: '11988887777',
      cep: '01310-100',
      logradouro: 'Avenida Paulista',
      numero: '1000',
      complemento: 'Andar 15',
      bairro: 'Bela Vista',
      cidade: 'São Paulo',
      uf: 'SP',
      departamentoId: deptTesteId,
      cargoId: 'cargo-coord-ti',
      cargo: 'Coordenador de TI',
      setor: 'Tecnologia da Informação',
      salarioBase: 9500.0,
      situacao: 'ATIVO',
      observacoes: 'Colaborador admitido com regime híbrido.',
    };

    const res = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', authCookie)
      .send(payload);

    expect(res.status).toBe(201);
    expect(res.body.sucesso).toBe(true);
    expect(res.body.dados).toBeDefined();
    expect(res.body.dados.id).toBeDefined();
    expect(res.body.dados.matricula).toBe('SPEC03-001');
    expect(res.body.dados.nome_completo).toBe('Carlos Eduardo Oliveira');
    expect(res.body.dados.empresa_id).toBe(empresaTesteId);

    colaboradorCriadoId = res.body.dados.id;
  });

  // RF-07: Validação de CPF inválido
  it('RF-07: Rejeita cadastro com CPF inválido (400 Bad Request)', async () => {
    const payloadInvalido = {
      empresaId: empresaTesteId,
      matricula: 'SPEC03-INV-CPF',
      nomeCompleto: 'Teste CPF Inválido',
      cpf: '111.222.333-44', // Dígitos verificadores incorretos
      dataNascimento: '1990-01-01',
      email: 'cpf.invalido@teste.com',
    };

    const res = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', authCookie)
      .send(payloadInvalido);

    expect(res.status).toBe(400);
    expect(res.body.mensagem).toContain('Inconsistência nos dados do colaborador');
  });

  // RF-07: Prevenção de duplicidade de CPF na mesma empresa
  it('RF-07: Bloqueia cadastro com CPF duplicado dentro da mesma empresa (409 Conflict)', async () => {
    const payloadDuplicado = {
      empresaId: empresaTesteId,
      matricula: 'SPEC03-MAT-NOVA',
      nomeCompleto: 'Outro Nome Mesmo CPF',
      cpf: '52998224725', // Mesmo CPF já cadastrado no teste 2
      dataNascimento: '1992-06-15',
      email: 'outro@empresa.com.br',
    };

    const res = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', authCookie)
      .send(payloadDuplicado);

    expect(res.status).toBe(409);
    expect(res.body.mensagem).toContain('Já existe um colaborador cadastrado com este CPF');
  });

  // RF-08: Prevenção de duplicidade de Matrícula na mesma empresa
  it('RF-08: Bloqueia cadastro com Matrícula duplicada dentro da mesma empresa (409 Conflict)', async () => {
    const payloadMatDuplicada = {
      empresaId: empresaTesteId,
      matricula: 'SPEC03-001', // Mesma matrícula já cadastrada
      nomeCompleto: 'Terceiro Nome',
      cpf: '84078175031', // CPF válido diferente
      dataNascimento: '1985-08-20',
      email: 'terceiro@empresa.com.br',
    };

    const res = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', authCookie)
      .send(payloadMatDuplicada);

    expect(res.status).toBe(409);
    expect(res.body.mensagem).toContain('Já existe um colaborador cadastrado com esta Matrícula');
  });

  // RF-01 & Seção 6.2: Listagem paginada oficial
  it('RF-01 & Seção 6.2: Retorna listagem paginada com metadados e CPF mascarado', async () => {
    const res = await request(app.getHttpServer())
      .get('/api/colaboradores?page=1&limit=10')
      .set('Cookie', authCookie);

    expect(res.status).toBe(200);
    expect(res.body.data).toBeDefined();
    expect(Array.isArray(res.body.data)).toBe(true);
    expect(res.body.meta).toBeDefined();
    expect(res.body.meta.page).toBe(1);
    expect(res.body.meta.limit).toBe(10);
    expect(res.body.meta.total).toBeGreaterThanOrEqual(1);

    // Validação de máscara de CPF (RF-01, RF-07)
    const encontrado = res.body.data.find((c: any) => c.id === colaboradorCriadoId);
    expect(encontrado).toBeDefined();
    expect(encontrado.cpf_mascarado).toBe('529.***.***-25');
  });

  // RF-02: Pesquisa por nome, CPF e matrícula
  it('RF-02: Pesquisa colaboradores por termo no backend (search)', async () => {
    const resPorNome = await request(app.getHttpServer())
      .get('/api/colaboradores?search=Carlos')
      .set('Cookie', authCookie);

    expect(resPorNome.status).toBe(200);
    expect(resPorNome.body.data.length).toBeGreaterThanOrEqual(1);
    expect(resPorNome.body.data[0].nome_completo).toContain('Carlos Eduardo');

    const resPorMat = await request(app.getHttpServer())
      .get('/api/colaboradores?search=SPEC03-001')
      .set('Cookie', authCookie);

    expect(resPorMat.status).toBe(200);
    expect(resPorMat.body.data.length).toBe(1);
    expect(resPorMat.body.data[0].matricula).toBe('SPEC03-001');
  });

  // RF-03: Filtros combináveis
  it('RF-03: Filtra colaboradores por departamento e filial', async () => {
    const resFiltro = await request(app.getHttpServer())
      .get(`/api/colaboradores?departamentoId=${deptTesteId}&filialId=${filialTesteId}`)
      .set('Cookie', authCookie);

    expect(resFiltro.status).toBe(200);
    expect(resFiltro.body.data.length).toBe(1);
    expect(resFiltro.body.data[0].departamento_id).toBe(deptTesteId);
  });

  // RF-05 & Seção 6.3: Visualização detalhada
  it('RF-05 & Seção 6.3: Consulta detalhes completos de um colaborador (200 OK)', async () => {
    const res = await request(app.getHttpServer())
      .get(`/api/colaboradores/${colaboradorCriadoId}`)
      .set('Cookie', authCookie);

    expect(res.status).toBe(200);
    expect(res.body.dados.id).toBe(colaboradorCriadoId);
    expect(res.body.dados.nome_completo).toBe('Carlos Eduardo Oliveira');
    expect(res.body.dados.logradouro).toBe('Avenida Paulista');
    expect(res.body.dados.observacoes).toContain('regime híbrido');
  });

  // RF-06 & Seção 6.4: Edição de dados cadastrais (PATCH)
  it('RF-06 & Seção 6.4: Atualiza dados cadastrais e preserva campos não enviados (PATCH 200)', async () => {
    const updatePayload = {
      celular: '11999990000',
      salarioBase: 10500.0,
      observacoes: 'Promovido a Coordenador Sênior.',
    };

    const res = await request(app.getHttpServer())
      .patch(`/api/colaboradores/${colaboradorCriadoId}`)
      .set('Cookie', authCookie)
      .send(updatePayload);

    expect(res.status).toBe(200);
    expect(res.body.dados.celular).toBe('11999990000');
    expect(Number(res.body.dados.salario_base)).toBe(10500.0);
    expect(res.body.dados.observacoes).toBe('Promovido a Coordenador Sênior.');
    // Preservação de campos não enviados
    expect(res.body.dados.nome_completo).toBe('Carlos Eduardo Oliveira');
    expect(res.body.dados.matricula).toBe('SPEC03-001');

    // Verifica se histórico de auditoria foi gerado
    const histRes = await request(app.getHttpServer())
      .get(`/api/colaboradores/${colaboradorCriadoId}/historico`)
      .set('Cookie', authCookie);

    expect(histRes.status).toBe(200);
    expect(histRes.body.dados.length).toBeGreaterThanOrEqual(2);
  });

  // RF-09 & Seção 6.5: Inativação lógica com preservação do registro
  it('RF-09 & Seção 6.5: Inativa colaborador logicamente com histórico e confirmação (PATCH 200)', async () => {
    const resInat = await request(app.getHttpServer())
      .patch(`/api/colaboradores/${colaboradorCriadoId}/inativar`)
      .set('Cookie', authCookie)
      .send({ motivo: 'Suspensão de contrato temporária' });

    expect(resInat.status).toBe(200);
    expect(resInat.body.dados.situacao.toLowerCase()).toBe('inativo');

    // Confirma que o registro permanece no banco de dados e pode ser consultado (não foi apagado)
    const checkRes = await request(app.getHttpServer())
      .get(`/api/colaboradores/${colaboradorCriadoId}`)
      .set('Cookie', authCookie);

    expect(checkRes.status).toBe(200);
    expect(checkRes.body.dados.id).toBe(colaboradorCriadoId);
    expect(checkRes.body.dados.situacao.toLowerCase()).toBe('inativo');
  });
});
