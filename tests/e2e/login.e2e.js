// E2E de autenticacao (Playwright). Uso: node tests/e2e/login.e2e.js  (via run_login_e2e.sh)
const { chromium } = require('playwright');
const BASE = process.env.BASE_URL || 'http://localhost:8000';
const ADMIN = { id: 'admin.dp@empresa.com.br', senha: process.env.ADMIN_INITIAL_PASSWORD };
const GUEST = { id: 'visitante@empresa.com.br', senha: process.env.GUEST_INITIAL_PASSWORD };
const DB = process.env.DB_PATH;
const { execFileSync } = require('child_process');

const resultados = [];
const check = (nome, ok, detalhe = '') => { resultados.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${nome}${detalhe ? '  -> ' + detalhe : ''}`); };
const estado = (pg) => pg.evaluate(() => ({
  login: !document.getElementById('tela-login').classList.contains('hidden'),
  sistema: !document.getElementById('tela-sistema').classList.contains('hidden'),
  alerta: (() => { const a = document.getElementById('login-alerta'); return a.classList.contains('hidden') ? '' : a.textContent.trim(); })(),
  linhas: document.querySelectorAll('#corpo-tabela tr').length,
  token: sessionStorage.getItem('AUTH_TOKEN'),
}));
async function novaPagina(b) {
  const ctx = await b.newContext(); const pg = await ctx.newPage();
  const erros = []; pg.on('pageerror', e => erros.push(e.message)); pg.erros = erros;
  await pg.goto(BASE); await pg.waitForTimeout(700); return pg;
}
async function logar(pg, u) {
  await pg.fill('#login-identificador', u.id); await pg.fill('#login-senha', u.senha);
  await pg.click('#form-login button[type=submit]'); await pg.waitForTimeout(1800);
}

(async () => {
  const b = await chromium.launch();

  // 1. Login valido -> tela principal, token armazenado, colaboradores carregados
  const a = await novaPagina(b);
  await logar(a, ADMIN); let e = await estado(a);
  check('Sem excecoes JS no carregamento/login', a.erros.length === 0, a.erros.join('|'));
  check('Login valido entra na tela principal', e.sistema && !e.login, JSON.stringify({ sistema: e.sistema, alerta: e.alerta }));
  check('Token recebido e armazenado (sessionStorage)', !!e.token && /^[0-9a-f]{64}$/.test(e.token));
  check('Colaboradores autorizados carregados', e.linhas >= 1, `linhas=${e.linhas}`);

  // 2. /me valida a sessao (cookie e Bearer usam o mesmo mecanismo)
  const me = await a.evaluate(async (t) => ({
    cookie: (await fetch('/api/auth/me', { credentials: 'include' })).status,
    bearer: (await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + t }, credentials: 'omit' })).status,
  }), e.token);
  check('/api/auth/me = 200 via cookie e via Bearer', me.cookie === 200 && me.bearer === 200, JSON.stringify(me));

  // 3. Atualizar a pagina mantem a sessao
  await a.reload(); await a.waitForTimeout(1500); e = await estado(a);
  check('Recarregar a pagina mantem a sessao', e.sistema && !e.login && e.linhas >= 1);

  // 4. Usuario diferente em outro contexto (sessoes independentes)
  const g = await novaPagina(b); await logar(g, GUEST); const eg = await estado(g);
  check('Segundo usuario autentica em contexto independente', eg.sistema && !eg.login);
  await a.reload(); await a.waitForTimeout(1500);
  check('Login do 2o usuario nao derruba a sessao do 1o', (await estado(a)).sistema);
  const perfilG = await g.evaluate(async () => (await (await fetch('/api/auth/me', { credentials: 'include' })).json()).usuario.perfil);
  check('Perfis distintos por sessao (admin x analista_rh)', perfilG === 'analista_rh', perfilG);

  // 5. Logout encerra a sessao no servidor
  const tokenAntigo = (await estado(a)).token;
  await a.click('#btn-logout'); await a.waitForTimeout(1200); e = await estado(a);
  check('Logout volta para a tela de login', e.login && !e.sistema && !e.token);
  const aposLogout = await a.evaluate(async (t) => (await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + t }, credentials: 'omit' })).status, tokenAntigo);
  check('Token antigo invalido apos logout (401)', aposLogout === 401);
  await a.reload(); await a.waitForTimeout(1200);
  check('Recarregar apos logout permanece no login', (await estado(a)).login);

  // 6. Login invalido -> mensagem visivel, sem entrar
  await logar(a, { id: ADMIN.id, senha: 'senha-errada-xyz' }); e = await estado(a);
  check('Login invalido mostra mensagem e permanece no login', e.login && /inv[aá]lid/i.test(e.alerta), e.alerta);

  // 7. Sessao expirada (revogada no banco) -> volta ao login COM mensagem
  await logar(a, ADMIN); check('Re-login apos logout/erro', (await estado(a)).sistema);
  execFileSync('python3', ['-c', `import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute("UPDATE sessoes SET revogado=1");c.commit()`, DB]);
  await a.evaluate(() => carregarColaboradores()); await a.waitForTimeout(1000); e = await estado(a);
  check('Sessao expirada/revogada volta ao login com mensagem', e.login && /expirad/i.test(e.alerta), e.alerta);

  // 8. Acesso nao autenticado protegido
  const sem = await a.evaluate(async () => {
    const r = {}; for (const p of ['/api/colaboradores', '/api/folha', '/api/bi/indicadores', '/api/auth/me'])
      r[p] = (await fetch(p, { credentials: 'omit' })).status; return r; });
  check('Endpoints protegidos retornam 401 sem autenticacao', Object.values(sem).every(s => s === 401), JSON.stringify(sem));

  await b.close();
  const falhas = resultados.filter(x => !x).length;
  console.log(`\n${resultados.length - falhas}/${resultados.length} verificacoes OK`);
  process.exit(falhas ? 1 : 0);
})();
