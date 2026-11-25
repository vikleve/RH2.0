// Execução Real E2E HTTP contra o servidor ativo + verificação estrutural de UI e tentativa de screenshot
import { spawn } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';

const PORT = 8766;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('evidencias_rf071_rf080');
fs.mkdirSync(OUT_DIR, { recursive: true });

async function waitForServer(url, timeoutMs = 35000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url, { headers: { Connection: 'close' } });
      if (r.status === 200) return true;
    } catch {}
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error('Backend server timeout');
}

async function req(method, endpoint, token, body = null) {
  const opts = {
    method,
    headers: {
      Origin: BASE_URL,
      Connection: 'close',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  };
  if (body !== null) opts.body = JSON.stringify(body);
  const resp = await fetch(`${BASE_URL}${endpoint}`, opts);
  const text = await resp.text();
  let json = {};
  try { json = JSON.parse(text); } catch { json = { raw: text }; }
  return { status: resp.status, json };
}

const tmpDb = path.join(os.tmpdir(), `rh20_live_rf071_rf080_${Date.now()}.db`);
const senhaAdmin = process.env.ADMIN_INITIAL_PASSWORD || 'Sintetico#AdminTest2026!';
const server = spawn('python', ['-u', '-c', `from backend.server import run_server; run_server(port=${PORT})`], {
  env: {
    ...process.env,
    TESTING: '1',
    DB_PATH: tmpDb,
    ADMIN_INITIAL_PASSWORD: senhaAdmin,
    GUEST_INITIAL_PASSWORD: process.env.GUEST_INITIAL_PASSWORD || 'Sintetico#GuestTest2026!',
  },
  stdio: ['ignore', 'pipe', 'pipe'],
});

const evidencias = {
  executed_at: new Date().toISOString(),
  base_url: BASE_URL,
  frontend_checks: {},
  rfs: {},
  screenshot: { attempted: false, ok: false, path: null, note: '' },
};

const assert = (cond, msg) => {
  if (!cond) throw new Error(`Assertion failed: ${msg}`);
};

try {
  await waitForServer(BASE_URL);

  // 1. Verificar HTML e JS servidos ao vivo
  const html = await (await fetch(`${BASE_URL}/`, { headers: { Connection: 'close' } })).text();
  const js = await (await fetch(`${BASE_URL}/app.js`, { headers: { Connection: 'close' } })).text();
  evidencias.frontend_checks = {
    rubrica_bug_0031_0032_removido: !html.includes('Rubricas 0031 / 0032'),
    rubrica_0512_0513_presente: html.includes('Rubricas 0512 / 0513'),
    tem_btn_novo_vinculo: html.includes('id="btn-novo-vinculo-beneficio"'),
    tem_btn_novo_catalogo: html.includes('id="btn-novo-catalogo-beneficio"'),
    tem_modais_beneficios: html.includes('id="modal-beneficio-colaborador"') && html.includes('id="modal-beneficio-catalogo"'),
    tem_btn_importar_beneficios_folha: html.includes('id="ind-btn-importar-beneficios"'),
    tem_beneficios_manager_js: js.includes('const BeneficiosManager ='),
  };
  Object.entries(evidencias.frontend_checks).forEach(([k, v]) => assert(v, `Frontend check ${k}`));

  // 2. Autenticar usuário admin sintético
  const login1 = await req('POST', '/api/auth/login', null, {
    identificador: 'admin.dp@empresa.com.br',
    senha: senhaAdmin,
  });
  assert(login1.status === 200 && login1.json.token, 'Login admin');
  const token = login1.json.token;

  // 3. Cadastrar colaboradores fictícios no DB isolado
  const cClt = await req('POST', '/api/colaboradores', token, {
    matricula: 'QA-8001',
    nome_completo: 'Carla QA Live CLT',
    cpf: '52998224725',
    rg: '11.222.333-4',
    data_nascimento: '1991-06-15',
    cargo: 'Analista Contábil',
    setor: 'Financeiro',
    departamento: 'Financeiro',
    tipo_contrato: 'CLT',
    data_admissao: '2024-02-01',
    salario_base: 3000.00,
    email: 'carla.qa.live@teste.local',
    telefone: '(16) 98888-0001',
    dependentes: [{ nome: 'Pedro QA Filho', parentesco: 'filho' }],
  });
  assert(cClt.status === 201, `Cadastro colaborador CLT: ${JSON.stringify(cClt.json)}`);
  const colabId = cClt.json.dados.id;

  const cEstag = await req('POST', '/api/colaboradores', token, {
    matricula: 'QA-8002',
    nome_completo: 'Lucas QA Live Estagiario',
    cpf: '39053344705',
    rg: '22.333.444-5',
    data_nascimento: '2004-02-18',
    cargo: 'Estagiário',
    setor: 'Tecnologia da Informação',
    tipo_contrato: 'Estagiário',
    data_admissao: '2026-10-05',
    salario_base: 1600.00,
    email: 'lucas.qa.live@teste.local',
    telefone: '(16) 98888-0002',
  });
  assert(cEstag.status === 201, `Cadastro estagiário: ${JSON.stringify(cEstag.json)}`);
  const estagId = cEstag.json.dados.id;

  // 4. Carregar catálogo
  const catRes = await req('GET', '/api/beneficios/catalogo', token);
  assert(catRes.status === 200 && catRes.json.dados.length >= 7, 'Catálogo com 7 itens padrão');
  const cat = Object.fromEntries(catRes.json.dados.map(b => [b.codigo, b]));

  // RF071 - Vale-Transporte
  const vtAdd = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.VT01.id, vigencia_inicio: '2026-10-01', valor_diario: 12.00, dias_uteis_mes: 22
  });
  assert(vtAdd.status === 201 && vtAdd.json.dados.desconto_colaborador === 180, 'RF071 cadastro');
  const vtEd = await req('PUT', `/api/beneficios/colaboradores/${vtAdd.json.dados.id}`, token, { valor_diario: 10.00, dias_uteis_mes: 22 });
  assert(vtEd.status === 200 && vtEd.json.dados.custo_total_mes === 220, 'RF071 edição');
  const vtInv = await req('PUT', `/api/beneficios/colaboradores/${vtAdd.json.dados.id}`, token, { valor_diario: -5 });
  assert(vtInv.status === 400, 'RF071 inválido');
  evidencias.rfs.RF071 = { status: 'APROVADO', vinculo_id: vtAdd.json.dados.id, desconto_pos_edicao: vtEd.json.dados.desconto_colaborador };

  // RF072 - Vale-Alimentação
  const vaAdd = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.VA01.id, vigencia_inicio: '2026-10-01', valor_mensal_base: 650.00
  });
  assert(vaAdd.status === 201 && vaAdd.json.dados.custo_empresa === 650, 'RF072 cadastro');
  const vaEd = await req('PUT', `/api/beneficios/colaboradores/${vaAdd.json.dados.id}`, token, { valor_mensal_base: 720.00 });
  assert(vaEd.status === 200 && vaEd.json.dados.custo_empresa === 720, 'RF072 edição');
  evidencias.rfs.RF072 = { status: 'APROVADO', vinculo_id: vaAdd.json.dados.id, custo_pos_edicao: vaEd.json.dados.custo_empresa };

  // RF073 - Vale-Refeição
  const vrAdd = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.VR01.id, vigencia_inicio: '2026-10-01', valor_diario: 35.00, dias_uteis_mes: 22
  });
  assert(vrAdd.status === 201 && vrAdd.json.dados.desconto_colaborador === 5 && vrAdd.json.dados.custo_empresa === 765, 'RF073 cadastro');
  const vrEd = await req('PUT', `/api/beneficios/colaboradores/${vrAdd.json.dados.id}`, token, { dias_uteis_mes: 20 });
  assert(vrEd.status === 200 && vrEd.json.dados.custo_total_mes === 700, 'RF073 edição');
  evidencias.rfs.RF073 = { status: 'APROVADO', vinculo_id: vrAdd.json.dados.id, custo_pos_edicao: vrEd.json.dados.custo_total_mes };

  // RF074 - Plano de Saúde
  const psAdd = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.PS01.id, vigencia_inicio: '2026-10-01', valor_mensal_base: 480.00, qtd_dependentes: 1, valor_dependente: 120.00
  });
  assert(psAdd.status === 201 && psAdd.json.dados.custo_total_mes === 600 && psAdd.json.dados.desconto_colaborador === 90, 'RF074 cadastro');
  const psEd = await req('PUT', `/api/beneficios/colaboradores/${psAdd.json.dados.id}`, token, { coparticipacao_extra: 30.00 });
  assert(psEd.status === 200 && psEd.json.dados.desconto_colaborador === 120, 'RF074 edição');
  evidencias.rfs.RF074 = { status: 'APROVADO', vinculo_id: psAdd.json.dados.id, desconto_pos_edicao: psEd.json.dados.desconto_colaborador };

  // RF075 - Seguro de Vida
  const svAdd = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.SV01.id, vigencia_inicio: '2026-10-01', valor_mensal_base: 45.00
  });
  assert(svAdd.status === 201 && svAdd.json.dados.custo_empresa === 45 && svAdd.json.dados.desconto_colaborador === 0, 'RF075 cadastro');
  const svEd = await req('PUT', `/api/beneficios/colaboradores/${svAdd.json.dados.id}`, token, { valor_mensal_base: 55.00 });
  assert(svEd.status === 200 && svEd.json.dados.custo_empresa === 55, 'RF075 edição');
  evidencias.rfs.RF075 = { status: 'APROVADO', vinculo_id: svAdd.json.dados.id, custo_pos_edicao: svEd.json.dados.custo_empresa };

  // RF076 - Convênio Farmácia
  const farInv = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.FAR01.id, vigencia_inicio: '2026-10-01', limite_mensal: 300.00, valor_utilizado_mes: 350.00
  });
  assert(farInv.status === 400, 'RF076 bloqueio limite mensal');
  const farAdd = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.FAR01.id, vigencia_inicio: '2026-10-01', limite_mensal: 400.00, valor_utilizado_mes: 110.00
  });
  assert(farAdd.status === 201 && farAdd.json.dados.desconto_colaborador === 110, 'RF076 cadastro');
  const farEd = await req('PUT', `/api/beneficios/colaboradores/${farAdd.json.dados.id}`, token, { valor_utilizado_mes: 150.00 });
  assert(farEd.status === 200 && farEd.json.dados.desconto_colaborador === 150, 'RF076 edição');
  evidencias.rfs.RF076 = { status: 'APROVADO', vinculo_id: farAdd.json.dados.id, desconto_pos_edicao: farEd.json.dados.desconto_colaborador };

  // RF077 - Benefícios Flexíveis
  const flexInv = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.FLEX01.id, vigencia_inicio: '2026-10-01', saldo_flexivel: 500, alocacao_json: { alimentacao: 300, saude: 300 }
  });
  assert(flexInv.status === 400, 'RF077 bloqueio excesso de saldo');
  const flexAdd = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: colabId, beneficio_id: cat.FLEX01.id, vigencia_inicio: '2026-10-01', saldo_flexivel: 600, alocacao_json: { alimentacao: 300, mobilidade: 150, educacao: 150 }
  });
  assert(flexAdd.status === 201 && flexAdd.json.dados.custo_empresa === 600, 'RF077 cadastro');
  const flexEd = await req('PUT', `/api/beneficios/colaboradores/${flexAdd.json.dados.id}`, token, { alocacao_json: { alimentacao: 400, cultura: 200 } });
  assert(flexEd.status === 200 && flexEd.json.dados.alocacao_obj.cultura === 200, 'RF077 edição');
  evidencias.rfs.RF077 = { status: 'APROVADO', vinculo_id: flexAdd.json.dados.id, alocacao: flexEd.json.dados.alocacao_obj };

  // Testar exclusão de vínculo fictício + persistência via nova sessão HTTP (simulando reload)
  const vrExclTest = await req('POST', '/api/beneficios/colaboradores', token, {
    colaborador_id: estagId, beneficio_id: cat.VR01.id, vigencia_inicio: '2026-10-05', valor_diario: 30, dias_uteis_mes: 20
  });
  assert(vrExclTest.status === 201, 'RF073 vínculo temporário estagiário');
  const vrDel = await req('DELETE', `/api/beneficios/colaboradores/${vrExclTest.json.dados.id}`, token);
  assert(vrDel.status === 200, 'Exclusão de vínculo fictício');

  const login2 = await req('POST', '/api/auth/login', null, { identificador: 'admin.dp@empresa.com.br', senha: senhaAdmin });
  const token2 = login2.json.token;
  const listaPosReload = await req('GET', `/api/beneficios/colaboradores?colaborador_id=${colabId}`, token2);
  assert(listaPosReload.status === 200 && listaPosReload.json.dados.length === 7, 'Persistência pós-reload dos 7 benefícios');

  // RF078 - Controle de Elegibilidade
  const elEstagPs = await req('POST', '/api/beneficios/colaboradores', token2, {
    colaborador_id: estagId, beneficio_id: cat.PS01.id, vigencia_inicio: '2026-10-05', valor_mensal_base: 480
  });
  assert(elEstagPs.status === 400, 'RF078 bloqueio estagiário em Plano de Saúde (somente CLT)');
  const elConsulta = await req('GET', `/api/beneficios/elegibilidade?colaborador_id=${estagId}`, token2);
  assert(elConsulta.status === 200 && elConsulta.json.dados.some(x => x.beneficio_codigo === 'PS01' && x.elegivel === false), 'RF078 consulta de elegibilidade');
  evidencias.rfs.RF078 = { status: 'APROVADO', mensagem_bloqueio: elEstagPs.json.mensagem };

  // RF079 - Descontos na Folha
  const descPre = await req('GET', `/api/beneficios/descontos-folha?colaborador_id=${colabId}&competencia=2026-10`, token2);
  assert(descPre.status === 200 && descPre.json.dados.total_descontos_beneficios === 455, `RF079 descontos esperados 455 (180+5+120+150): obteve ${descPre.json.dados.total_descontos_beneficios}`);
  const folhaRes = await req('POST', '/api/folha', token2, {
    colaborador_id: colabId, competencia: '2026-10', incluir_beneficios_ativos: true
  });
  assert(folhaRes.status === 201, `RF079 geração de folha integrada: ${JSON.stringify(folhaRes.json)}`);
  evidencias.rfs.RF079 = {
    status: 'APROVADO',
    total_descontos_beneficios: descPre.json.dados.total_descontos_beneficios,
    folha_id: folhaRes.json.dados.id,
    folha_total_descontos: folhaRes.json.dados.total_descontos,
    folha_salario_liquido: folhaRes.json.dados.salario_liquido,
  };

  // RF080 - Relatório de Benefícios
  const relRes = await req('GET', '/api/beneficios/relatorio?competencia=2026-10', token2);
  assert(relRes.status === 200, 'RF080 relatório');
  const rr = relRes.json.dados.resumo;
  assert(rr.total_vinculos_ativos === 7, 'RF080 7 vínculos ativos');
  assert(Math.abs(rr.custo_total_mensal - (rr.total_custo_empresa + rr.total_desconto_colaboradores)) < 0.02, 'RF080 consistência matemática');
  evidencias.rfs.RF080 = { status: 'APROVADO', resumo: rr };

  fs.writeFileSync(path.join(OUT_DIR, 'execucao_e2e_live.json'), JSON.stringify(evidencias, null, 2));
  console.log('E2E_LIVE_OK: 10/10 RFs executados e validados contra servidor ativo.');
} catch (err) {
  console.error('E2E_LIVE_ERR:', err.message);
  process.exitCode = 1;
} finally {
  try { server.kill('SIGKILL'); } catch {}
  await new Promise(r => setTimeout(r, 300));
  try { fs.rmSync(tmpDb, { force: true }); } catch {}
  process.exit(process.exitCode || 0);
}
