import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import * as cookieParser from 'cookie-parser';
import { AppModule } from '../src/app.module';

describe('Colaboradores e Folha de Pagamento RH2.0 (NestJS E2E)', () => {
  let app: INestApplication;
  let authCookie: string;

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

    // Login administrativo inicial para obter sessão
    const loginRes = await request(app.getHttpServer())
      .post('/api/auth/login')
      .send({
        identificador: 'admin.dp@empresa.com.br',
        senha: 'Sintetico#AdminTest2026!',
      });

    authCookie = loginRes.headers['set-cookie'];
  });

  afterAll(async () => {
    await app.close();
  });

  let colaboradorId: number;
  let folhaId: number;

  it('1. Deve cadastrar um colaborador com sucesso (POST /api/colaboradores)', async () => {
    const payload = {
      matricula: 'MAT-2026-001',
      nome_completo: 'Mariana Silva Santos',
      cpf: '52998224725',
      rg: 'MG-12.345.678',
      data_nascimento: '1990-05-15',
      telefone: '(31) 98765-4321',
      email: 'mariana.silva@empresa.com.br',
      data_admissao: '2022-03-01',
      cargo: 'Analista de RH Pleno',
      setor: 'Recursos Humanos',
      salario_base: 4500.0,
      dependentes: [
        { nome: 'Lucas Silva', parentesco: 'Filho(a)' },
      ],
    };

    const res = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', authCookie)
      .send(payload);

    expect(res.status).toBe(201);
    expect(res.body.sucesso).toBe(true);
    expect(res.body.dados.id).toBeDefined();
    expect(res.body.dados.nome_completo).toBe('Mariana Silva Santos');
    colaboradorId = res.body.dados.id;
  });

  it('2. Deve rejeitar colaborador com CPF duplicado (409 Conflict)', async () => {
    const payload = {
      matricula: 'MAT-2026-002',
      nome_completo: 'Outro Colaborador',
      cpf: '52998224725', // Mesmo CPF
      data_nascimento: '1992-01-01',
      email: 'outro@empresa.com.br',
      data_admissao: '2023-01-01',
      cargo: 'Auxiliar',
      setor: 'Administrativo',
      salario_base: 2000.0,
    };

    const res = await request(app.getHttpServer())
      .post('/api/colaboradores')
      .set('Cookie', authCookie)
      .send(payload);

    expect(res.status).toBe(409);
    expect(res.body.sucesso).toBe(false);
  });

  it('3. Deve listar colaboradores com busca e filtros (GET /api/colaboradores)', async () => {
    const res = await request(app.getHttpServer())
      .get('/api/colaboradores?q=Mariana')
      .set('Cookie', authCookie);

    expect(res.status).toBe(200);
    expect(res.body.sucesso).toBe(true);
    expect(res.body.total).toBe(1);
    expect(res.body.dados[0].matricula).toBe('MAT-2026-001');
  });

  it('4. Deve atualizar dados e registrar histórico de auditoria (PUT /api/colaboradores/:id)', async () => {
    const res = await request(app.getHttpServer())
      .put(`/api/colaboradores/${colaboradorId}`)
      .set('Cookie', authCookie)
      .send({
        matricula: 'MAT-2026-001',
        nome_completo: 'Mariana Silva Santos Oliveira',
        cpf: '52998224725',
        data_nascimento: '1990-05-15',
        email: 'mariana.oliveira@empresa.com.br',
        data_admissao: '2022-03-01',
        cargo: 'Coordenadora de RH',
        setor: 'Recursos Humanos',
        salario_base: 6000.0,
      });

    expect(res.status).toBe(200);
    expect(res.body.dados.cargo).toBe('Coordenadora de RH');

    // Consulta histórico de alterações
    const histRes = await request(app.getHttpServer())
      .get(`/api/colaboradores/${colaboradorId}/historico`)
      .set('Cookie', authCookie);

    expect(histRes.status).toBe(200);
    expect(histRes.body.total).toBeGreaterThan(0);
  });

  it('5. Deve inativar e reativar logicamente colaborador (PATCH)', async () => {
    // Inativação
    const resInat = await request(app.getHttpServer())
      .patch(`/api/colaboradores/${colaboradorId}/inativar`)
      .set('Cookie', authCookie)
      .send({ motivo: 'Afastamento temporário' });

    expect(resInat.status).toBe(200);
    expect(resInat.body.dados.situacao).toBe('inativo');

    // Reativação
    const resReat = await request(app.getHttpServer())
      .patch(`/api/colaboradores/${colaboradorId}/reativar`)
      .set('Cookie', authCookie);

    expect(resReat.status).toBe(200);
    expect(resReat.body.dados.situacao).toBe('ativo');
  });

  it('6. Deve consultar métricas agregadas (GET /api/colaboradores/metricas)', async () => {
    const res = await request(app.getHttpServer())
      .get('/api/colaboradores/metricas')
      .set('Cookie', authCookie);

    expect(res.status).toBe(200);
    expect(res.body.dados.total_ativos).toBeGreaterThanOrEqual(1);
    expect(res.body.dados.total_dependentes).toBeGreaterThanOrEqual(1);
  });

  it('7. Deve calcular folha com horas extras e encargos CLT (POST /api/folha)', async () => {
    const payloadFolha = {
      colaborador_id: colaboradorId,
      competencia: '2026-10',
      dias_trabalhados: 30,
      dias_mes: 30,
      horas_divisor: 220,
      eventos: [
        { tipo: 'hora_extra', quantidade: 10, percentual: 50 },
        { tipo: 'adicional_noturno', quantidade: 20, percentual: 20, reducao_ficta: true },
      ],
    };

    const res = await request(app.getHttpServer())
      .post('/api/folha')
      .set('Cookie', authCookie)
      .send(payloadFolha);

    expect(res.status).toBe(201);
    expect(res.body.sucesso).toBe(true);
    expect(res.body.dados.total_proventos).toBeGreaterThan(6000);
    expect(res.body.dados.total_descontos).toBeGreaterThan(0);
    expect(res.body.dados.salario_liquido).toBeGreaterThan(0);
    expect(res.body.dados.itens.length).toBeGreaterThanOrEqual(4);
    folhaId = res.body.dados.id;
  });

  it('8. Deve fechar a folha e bloquear recálculos indevidos (POST /api/folha/:id/fechar)', async () => {
    const resFechar = await request(app.getHttpServer())
      .post(`/api/folha/${folhaId}/fechar`)
      .set('Cookie', authCookie);

    expect(resFechar.status).toBe(200);
    expect(resFechar.body.dados.situacao).toBe('fechada');

    // Tentativa de recalcular folha fechada deve ser proibida (403 Forbidden)
    const resRecalc = await request(app.getHttpServer())
      .post('/api/folha')
      .set('Cookie', authCookie)
      .send({
        colaborador_id: colaboradorId,
        competencia: '2026-10',
      });

    expect(resRecalc.status).toBe(403);
  });

  it('9. Deve reabrir a folha mediante justificativa obrigatória (POST /api/folha/:id/reabrir)', async () => {
    // Reabertura sem motivo falha (400)
    const resSemMotivo = await request(app.getHttpServer())
      .post(`/api/folha/${folhaId}/reabrir`)
      .set('Cookie', authCookie)
      .send({ motivo: '' });

    expect(resSemMotivo.status).toBe(400);

    // Reabertura com motivo
    const resReaberta = await request(app.getHttpServer())
      .post(`/api/folha/${folhaId}/reabrir`)
      .set('Cookie', authCookie)
      .send({ motivo: 'Inclusão de atestado médico' });

    expect(resReaberta.status).toBe(200);
    expect(resReaberta.body.dados.situacao).toBe('calculada');
  });

  it('10. Deve cancelar a folha com sucesso (DELETE /api/folha/:id)', async () => {
    const resCanc = await request(app.getHttpServer())
      .delete(`/api/folha/${folhaId}`)
      .set('Cookie', authCookie);

    expect(resCanc.status).toBe(200);

    const resCheck = await request(app.getHttpServer())
      .get(`/api/folha/${folhaId}`)
      .set('Cookie', authCookie);

    expect(resCheck.body.dados.situacao).toBe('cancelada');
  });
<<<<<<< HEAD
=======

  it('11. Deve consultar o catálogo oficial de eventos da folha (GET /api/folha/eventos-catalogo)', async () => {
    const res = await request(app.getHttpServer())
      .get('/api/folha/eventos-catalogo')
      .set('Cookie', authCookie);

    expect(res.status).toBe(200);
    expect(res.body.sucesso).toBe(true);
    expect(res.body.total).toBe(82);

    const codigos = res.body.dados.map((e: any) => e.codigo);
    expect(codigos).toContain('0520'); // Adiantamento salarial
    expect(codigos).toContain('0010'); // Horas extras 50%
    expect(codigos).toContain('0011'); // Horas extras 100%
    expect(codigos).toContain('0075'); // Abono / benefício indenizatório
  });

  it('12. Deve calcular e persistir eventos avulsos do catálogo (Adiantamento, Abono) em folha_itens', async () => {
    const payload = {
      colaborador_id: colaboradorId,
      competencia: '2026-11',
      dias_trabalhados: 30,
      dias_mes: 30,
      horas_divisor: 220,
      eventos: [
        {
          codigo: '0520',
          descricao: 'Adiantamento salarial',
          tipo: 'desconto',
          referencia: 1,
          valor_total: 500.0,
        },
        {
          codigo: '0075',
          descricao: 'Abono / benefício indenizatório',
          tipo: 'provento',
          referencia: 1,
          valor_total: 300.0,
        },
      ],
    };

    const res = await request(app.getHttpServer())
      .post('/api/folha')
      .set('Cookie', authCookie)
      .send(payload);

    expect(res.status).toBe(201);
    expect(res.body.sucesso).toBe(true);

    const itens = res.body.dados.itens;
    const adiantamentoItem = itens.find((it: any) => it.codigo_evento === '0520');
    expect(adiantamentoItem).toBeDefined();
    expect(adiantamentoItem.tipo).toBe('desconto');
    expect(adiantamentoItem.valor_total).toBe(500.0);

    const abonoItem = itens.find((it: any) => it.codigo_evento === '0075');
    expect(abonoItem).toBeDefined();
    expect(abonoItem.tipo).toBe('provento');
    expect(abonoItem.valor_total).toBe(300.0);

    // Salário base 6000 + 300 abono = 6300 proventos
    expect(res.body.dados.total_proventos).toBe(6300.0);
    // Total descontos deve incluir os 500 de adiantamento
    expect(res.body.dados.total_descontos).toBeGreaterThanOrEqual(500.0);
  });
>>>>>>> bb3d88436cf3fade853898912a2ca4504d021ed8
});

