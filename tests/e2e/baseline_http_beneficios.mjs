import { spawn } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';

const PORT = 8765;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const OUT_DIR = path.resolve('evidencias_rf071_rf080');
fs.mkdirSync(OUT_DIR, { recursive: true });

async function waitForServer(url, timeoutMs = 35000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.status === 200) return true;
    } catch {}
    await new Promise(r => setTimeout(r, 250));
  }
  throw new Error('Backend server timeout');
}

const tmpDb = path.join(os.tmpdir(), `rh20_base_${Date.now()}.db`);
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
let srvLog = '';
server.stdout?.on('data', d => { srvLog += d.toString(); });
server.stderr?.on('data', d => { srvLog += d.toString(); });

try {
  await waitForServer(BASE_URL);
  const htmlResp = await fetch(`${BASE_URL}/`);
  const html = await htmlResp.text();

  const loginResp = await fetch(`${BASE_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Origin: BASE_URL },
    body: JSON.stringify({ identificador: 'admin.dp@empresa.com.br', senha: senhaAdmin }),
  });
  const loginJson = await loginResp.json();
  const token = loginJson.token;

  const headers = { Authorization: `Bearer ${token}`, Origin: BASE_URL };
  const endpoints = [
    '/api/beneficios/catalogo',
    '/api/beneficios/colaboradores',
    '/api/beneficios/elegibilidade?colaborador_id=1',
    '/api/beneficios/descontos-folha?colaborador_id=1&competencia=2026-10',
    '/api/beneficios/relatorio',
  ];
  const apiResults = {};
  for (const ep of endpoints) {
    const r = await fetch(`${BASE_URL}${ep}`, { headers });
    apiResults[ep] = { status: r.status, body: await r.text() };
  }

  const report = {
    executed_at: new Date().toISOString(),
    server_status: htmlResp.status,
    login_status: loginResp.status,
    frontend_checks: {
      rubrica_bug_0031_0032_presente: html.includes('Rubricas 0031 / 0032'),
      rubrica_correta_0512_0513_presente: html.includes('Rubricas 0512 / 0513'),
      tem_btn_novo_vinculo: html.includes('btn-novo-vinculo-beneficio'),
      tem_modal_beneficio_colaborador: html.includes('modal-beneficio-colaborador'),
      tem_aba_elegibilidade: html.includes('benef-eleg-colab'),
      tem_aba_relatorio_beneficios: html.includes('tbody-benef-rel-tipo'),
    },
    api_results: apiResults,
  };

  fs.writeFileSync(path.join(OUT_DIR, '00_baseline_http.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally {
  try { server.kill('SIGKILL'); } catch {}
  await new Promise(r => setTimeout(r, 300));
  try { fs.rmSync(tmpDb, { force: true }); } catch {}
}
