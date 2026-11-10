/**
 * Configuração Centralizada de CORS para o RH2.0 (NestJS)
 * Garante que apenas origens autorizadas possam interagir com credenciais seguras.
 */

export function obterOrigensPermitidas(): string[] {
  const envOrigins = process.env.ALLOWED_ORIGINS;
  if (envOrigins && envOrigins.trim().length > 0) {
    return envOrigins
      .split(',')
      .map((o) => o.trim().replace(/\/$/, ''))
      .filter(Boolean);
  }

  // Em desenvolvimento, origens padrão locais autorizadas do ecossistema RH2.0
  return [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
  ];
}

export function validarOrigemCors(
  origin: string | undefined,
  callback: (err: Error | null, allow?: boolean) => void,
): void {
  // Chamadas sem header Origin (curl, testes internos supertest sem origin explicito, server-to-server)
  if (!origin) {
    return callback(null, true);
  }

  const permitidas = obterOrigensPermitidas();
  const origemNorm = origin.trim().replace(/\/$/, '');

  if (permitidas.includes(origemNorm)) {
    return callback(null, true);
  }

  // Bloqueio de origens não autorizadas (RF-01): não emitir cabeçalhos permissivos
  return callback(null, false);
}
