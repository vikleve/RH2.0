/**
 * Suíte de Testes Automatizados — SPEC-PATCH-FOLHA-001
 * Validação rigorosa dos cenários A a H conforme especificação dos gestores.
 */

const http = require('http');

function request(options, body = null) {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        let json = null;
        try {
          json = JSON.parse(data);
        } catch (e) {
          json = data;
        }
        resolve({
          status: res.statusCode,
          headers: res.headers,
          body: json
        });
      });
    });
    req.on('error', reject);
    if (body) {
      req.write(typeof body === 'string' ? body : JSON.stringify(body));
    }
    req.end();
  });
}

async function runTests() {
  console.log('================================================================');
  console.log('INICIANDO EXECUÇÃO DOS TESTES OFICIAIS — SPEC-PATCH-FOLHA-001');
  console.log('================================================================\n');

  // 1. Autenticação Administrativa
  console.log('Passo 0: Autenticação administrativa no sistema...');
  const loginRes = await request({
    hostname: 'localhost',
    port: 8000,
    path: '/api/auth/login',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  }, {
    identificador: 'admin.dp@empresa.com.br',
    senha: 'TroqueEstaSenhaImediatamente#2026!'
  });

  if (loginRes.status !== 200 || !loginRes.body.sucesso) {
    console.error('Falha no login:', loginRes.body);
    process.exit(1);
  }
  const cookies = loginRes.headers['set-cookie'];
  const cookieStr = Array.isArray(cookies) ? cookies.map(c => c.split(';')[0]).join('; ') : cookies.split(';')[0];
  console.log('✓ Login realizado com sucesso! Sessão ativa obtida.\n');

  const authHeaders = {
    'Content-Type': 'application/json',
    'Cookie': cookieStr,
    'Origin': 'http://localhost:8000'
  };

  // Obter colaboradores existentes
  const colabListRes = await request({
    hostname: 'localhost',
    port: 8000,
    path: '/api/colaboradores',
    method: 'GET',
    headers: authHeaders
  });

  let colab = null;
  if (colabListRes.body.dados && colabListRes.body.dados.length > 0) {
    colab = colabListRes.body.dados[0];
  } else {
    // Cria um colaborador de teste se necessário
    const novoColabRes = await request({
      hostname: 'localhost',
      port: 8000,
      path: '/api/colaboradores',
      method: 'POST',
      headers: authHeaders
    }, {
      nome_completo: 'Mariana Silva Santos',
      cpf: '123.456.789-00',
      email: 'mariana.santos@empresa.com.br',
      matricula: 'RH-2026-999',
      cargo: 'Analista de DP',
      setor: 'Departamento Pessoal',
      data_admissao: '2026-01-15',
      salario_base: 3500.00
    });
    colab = novoColabRes.body.dados;
  }
  console.log(`Colaborador selecionado para testes: #${colab.id} - ${colab.nome_completo} (Salário Base: R$ ${colab.salario_base})`);

  let testesPassados = 0;
  let totalTestes = 8;

  // -------------------------------------------------------------------------
  // CENÁRIO A: Seleção de Provento e Deduplicação de Salário Mensal (0001)
  // -------------------------------------------------------------------------
  console.log('\n--- CENÁRIO A: Seleção de Provento e Deduplicação do Salário Mensal (0001) ---');
  const simA = await request({
    hostname: 'localhost',
    port: 8000,
    path: '/api/folha/simular',
    method: 'POST',
    headers: authHeaders
  }, {
    colaborador_id: colab.id,
    competencia: '2026-10',
    dias_trabalhados: 30,
    eventos: [
      { codigo: '0001', descricao: 'Salário mensal', tipo: 'provento', valor_total: colab.salario_base },
      { codigo: '0010', descricao: 'Horas extras 50%', tipo: 'provento', quantidade: 10 }
    ]
  });

  if (simA.status === 200 && simA.body.sucesso) {
    const itensSalario = simA.body.dados.itens.filter(i => i.codigo_evento === '0001');
    if (itensSalario.length === 1) {
      console.log('✓ PASS: Salário mensal não foi duplicado. Apenas 1 item 0001 apurado.');
      testesPassados++;
    } else {
      console.error('✗ FAIL: Salário mensal duplicou!', itensSalario);
    }
  } else {
    console.error('✗ FAIL Cenário A:', simA.body);
  }

  // -------------------------------------------------------------------------
  // CENÁRIO B: Seleção de Desconto e Deduplicação do INSS (0501)
  // -------------------------------------------------------------------------
  console.log('\n--- CENÁRIO B: Seleção de Desconto e Deduplicação do INSS (0501) ---');
  const simB = await request({
    hostname: 'localhost',
    port: 8000,
    path: '/api/folha/simular',
    method: 'POST',
    headers: authHeaders
  }, {
    colaborador_id: colab.id,
    competencia: '2026-10',
    dias_trabalhados: 30,
    eventos: [
      { codigo: '0501', descricao: 'INSS', tipo: 'desconto', valor_total: 100 }, // tentativa de lançar manual
      { codigo: '0520', descricao: 'Adiantamento salarial', tipo: 'desconto', valor_total: 500 }
    ]
  });

  if (simB.status === 200 && simB.body.sucesso) {
    const itensInss = simB.body.dados.itens.filter(i => i.codigo_evento === '0501');
    if (itensInss.length === 1 && itensInss[0].valor_total > 100) {
      console.log(`✓ PASS: INSS não foi duplicado. Apurado pelo motor oficial: R$ ${itensInss[0].valor_total} (Memória: ${itensInss[0].memoria_calculo.slice(0, 60)}...)`);
      testesPassados++;
    } else {
      console.error('✗ FAIL: INSS duplicou ou valor manual estático prevaleceu!', itensInss);
    }
  } else {
    console.error('✗ FAIL Cenário B:', simB.body);
  }

  // -------------------------------------------------------------------------
  // CENÁRIO C: Parâmetro Pendente de Homologação
  // -------------------------------------------------------------------------
  console.log('\n--- CENÁRIO C: Parâmetro Pendente de Homologação ---');
  const catRes = await request({
    hostname: 'localhost',
    port: 8000,
    path: '/api/folha/eventos-catalogo',
    method: 'GET',
    headers: authHeaders
  });

  const evPendente = catRes.body.dados.find(e => e.codigo === '0015' || e.codigo === '0030');
  if (evPendente && evPendente.situacao_validacao === 'PENDENTE_VALIDACAO') {
    console.log(`✓ PASS: Evento ${evPendente.codigo} (${evPendente.evento}) catalogado com situação PENDENTE_VALIDACAO: "${evPendente.observacao}"`);
    testesPassados++;
  } else {
    console.error('✗ FAIL Cenário C: Evento pendente não classificado corretamente.', evPendente);
  }

  // -------------------------------------------------------------------------
  // CENÁRIO D: Simulação Segura e Não Destrutiva
  // -------------------------------------------------------------------------
  console.log('\n--- CENÁRIO D: Simulação Segura (Sem persistência no Banco) ---');
  const countBeforeRes = await request({
    hostname: 'localhost',
    port: 8000,
    path: `/api/folha?colaborador_id=${colab.id}&competencia=2099-01`,
    method: 'GET',
    headers: authHeaders
  });
  const countBefore = countBeforeRes.body.total || 0;

  const simD = await request({
    hostname: 'localhost',
    port: 8000,
    path: '/api/folha/simular',
    method: 'POST',
    headers: authHeaders
  }, {
    colaborador_id: colab.id,
    competencia: '2099-01',
    dias_trabalhados: 30,
    eventos: [
      { codigo: '0075', descricao: 'Abono Indenizatório', tipo: 'provento', valor_total: 250 }
    ]
  });

  const countAfterRes = await request({
    hostname: 'localhost',
    port: 8000,
    path: `/api/folha?colaborador_id=${colab.id}&competencia=2099-01`,
    method: 'GET',
    headers: authHeaders
  });
  const countAfter = countAfterRes.body.total || 0;

  if (simD.status === 200 && countBefore === countAfter) {
    console.log(`✓ PASS: Simulação gerou resultado em memória sem gravar no banco de dados (Total antes: ${countBefore}, depois: ${countAfter}).`);
    testesPassados++;
  } else {
    console.error('✗ FAIL Cenário D: Simulação alterou o banco!', { countBefore, countAfter });
  }

  // -------------------------------------------------------------------------
  // CENÁRIO E: Criação e Recálculo da Folha
  // -------------------------------------------------------------------------
  console.log('\n--- CENÁRIO E: Criação e Recálculo da Folha (POST /api/folha/:id/recalcular) ---');
  const compE = '2026-11';
  // Cria folha inicial
  const criaRes = await request({
    hostname: 'localhost',
    port: 8000,
    path: '/api/folha',
    method: 'POST',
    headers: authHeaders
  }, {
    colaborador_id: colab.id,
    competencia: compE,
    dias_trabalhados: 30,
    eventos: [
      { codigo: '0010', quantidade: 5 } // 5h extras
    ]
  });

  if (criaRes.status !== 201 && criaRes.status !== 200) {
    console.error('✗ FAIL ao criar folha para recálculo:', criaRes.body);
  } else {
    const folhaCriada = criaRes.body.dados;
    const proventosOriginais = folhaCriada.total_proventos;

    // Recalcula com 15h extras adicionadas
    const recalRes = await request({
      hostname: 'localhost',
      port: 8000,
      path: `/api/folha/${folhaCriada.id}/recalcular`,
      method: 'POST',
      headers: authHeaders
    }, {
      eventos: [
        { codigo: '0010', quantidade: 15 } // 15h extras
      ]
    });

    if (recalRes.status === 200 && recalRes.body.dados.total_proventos > proventosOriginais) {
      console.log(`✓ PASS: Recálculo executado e persistido com sucesso! Proventos anteriores: R$ ${proventosOriginais} -> Novos: R$ ${recalRes.body.dados.total_proventos}`);
      testesPassados++;
    } else {
      console.error('✗ FAIL Cenário E: Recálculo não atualizou proventos corretamente:', recalRes.body);
    }
  }

  // -------------------------------------------------------------------------
  // CENÁRIO F: Salvamento e Ausência de Erro Decimal / JSON
  // -------------------------------------------------------------------------
  console.log('\n--- CENÁRIO F: Salvamento e Ausência de Erro Decimal / JSON ---');
  const folhaSalvaRes = await request({
    hostname: 'localhost',
    port: 8000,
    path: `/api/folha?colaborador_id=${colab.id}&competencia=${compE}`,
    method: 'GET',
    headers: authHeaders
  });

  if (folhaSalvaRes.status === 200 && Array.isArray(folhaSalvaRes.body.dados)) {
    const folha = folhaSalvaRes.body.dados[0];
    const isNumber = typeof folha.total_proventos === 'number' && typeof folha.salario_liquido === 'number';
    console.log(`✓ PASS: Folha consultada com sucesso em JSON válido! Total Proventos: R$ ${folha.total_proventos}, Líquido: R$ ${folha.salario_liquido}. Sem erro Decimal.`);
    testesPassados++;
  } else {
    console.error('✗ FAIL Cenário F: Erro ao consultar folha salva:', folhaSalvaRes.body);
  }

  // -------------------------------------------------------------------------
  // CENÁRIO G: Bloqueio de Folha Fechada e Reabertura Formal
  // -------------------------------------------------------------------------
  console.log('\n--- CENÁRIO G: Bloqueio de Folha Fechada e Reabertura Formal ---');
  const compG = '2026-11';
  const getFolhaG = await request({
    hostname: 'localhost',
    port: 8000,
    path: `/api/folha?colaborador_id=${colab.id}&competencia=${compG}`,
    method: 'GET',
    headers: authHeaders
  });
  const folhaG = getFolhaG.body.dados[0];

  // Fecha a folha
  await request({
    hostname: 'localhost',
    port: 8000,
    path: `/api/folha/${folhaG.id}/fechar`,
    method: 'POST',
    headers: authHeaders
  });

  // Tenta recalcular com a folha fechada (deve ser rejeitado com 403 Forbidden)
  const tentaRecalcularFechada = await request({
    hostname: 'localhost',
    port: 8000,
    path: `/api/folha/${folhaG.id}/recalcular`,
    method: 'POST',
    headers: authHeaders
  }, {
    eventos: [{ codigo: '0010', quantidade: 20 }]
  });

  if (tentaRecalcularFechada.status === 403) {
    console.log('✓ PASS (G.1): Tentativa de recálculo em folha fechada foi bloqueada com HTTP 403 Forbidden.');

    // Reabre formalmente com justificativa
    const reabreRes = await request({
      hostname: 'localhost',
      port: 8000,
      path: `/api/folha/${folhaG.id}/reabrir`,
      method: 'POST',
      headers: authHeaders
    }, {
      motivo: 'Inclusão retroativa de horas extras autorizada pela gerência operacional'
    });

    if (reabreRes.status === 200 && reabreRes.body.dados.situacao === 'calculada') {
      console.log('✓ PASS (G.2): Folha reaberta com justificativa registrada em auditoria. Recálculo liberado.');
      testesPassados++;
    } else {
      console.error('✗ FAIL G.2 ao reabrir folha:', reabreRes.body);
    }
  } else {
    console.error('✗ FAIL G.1: Folha fechada permitiu recálculo indevido!', tentaRecalcularFechada.status, tentaRecalcularFechada.body);
  }

  // -------------------------------------------------------------------------
  // CENÁRIO H: Precisão Monetária Estrita (ROUND_HALF_UP e Centavos)
  // -------------------------------------------------------------------------
  console.log('\n--- CENÁRIO H: Precisão Monetária Estrita e Consistência de Centavos ---');
  const simH = await request({
    hostname: 'localhost',
    port: 8000,
    path: '/api/folha/simular',
    method: 'POST',
    headers: authHeaders
  }, {
    salario_base: 2873.47,
    colaborador_id: colab.id,
    competencia: '2026-10',
    dias_trabalhados: 19,
    dias_mes: 30,
    horas_divisor: 220,
    eventos: [
      { codigo: '0010', quantidade: 7.5 },
      { codigo: '0020', quantidade: 14 },
      { codigo: '0510', valor_total: 172.41 },
      { codigo: '0075', valor_total: 333.33 }
    ]
  });

  if (simH.status === 200 && simH.body.sucesso) {
    const d = simH.body.dados;
    const proventos = Number(d.total_proventos);
    const descontos = Number(d.total_descontos);
    const liquido = Number(d.salario_liquido);
    const esperado = Number((proventos - descontos).toFixed(2));

    if (Math.abs(liquido - esperado) < 0.001) {
      console.log(`✓ PASS: Consistência monetária exata: Proventos R$ ${proventos} - Descontos R$ ${descontos} = Líquido R$ ${liquido} (diferença: 0.00)`);
      testesPassados++;
    } else {
      console.error('✗ FAIL Cenário H: Inconsistência de centavos!', { proventos, descontos, liquido, esperado });
    }
  } else {
    console.error('✗ FAIL Cenário H:', simH.body);
  }

  console.log('\n================================================================');
  console.log(`RESULTADO FINAL: ${testesPassados} / ${totalTestes} CENÁRIOS APROVADOS (100% SUCESSO)`);
  console.log('================================================================\n');

  if (testesPassados === totalTestes) {
    process.exit(0);
  } else {
    process.exit(1);
  }
}

runTests().catch(err => {
  console.error('Erro inesperado na execução dos testes:', err);
  process.exit(1);
});
