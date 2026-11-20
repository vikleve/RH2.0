#!/usr/bin/env bash
# Sobe o backend real (SQLite temporario) e executa o E2E de login com Playwright.
# Requer: python3, node e o pacote 'playwright' com Chromium instalado.
set -euo pipefail
cd "$(dirname "$0")/../.."
TMP="$(mktemp -d)"; export DB_PATH="$TMP/e2e.db"
export ADMIN_INITIAL_PASSWORD='E2e#Admin2026!ok' GUEST_INITIAL_PASSWORD='E2e#Guest2026!ok'
PORT="${PORT:-8000}"; export BASE_URL="http://localhost:$PORT"
python3 -c "
import sys; sys.path.insert(0,'.')
from backend.server import run_server
run_server(port=$PORT, db_path='$DB_PATH')" >"$TMP/server.log" 2>&1 &
SRV=$!; trap 'kill $SRV 2>/dev/null; rm -rf "$TMP"' EXIT
for i in $(seq 1 30); do curl -sf -o /dev/null "$BASE_URL/api/health" && break; sleep 0.3; done
python3 - <<PY
import sqlite3; c=sqlite3.connect("$DB_PATH")
c.execute("INSERT INTO colaboradores(matricula,nome_completo,cpf,data_nascimento,email,data_admissao,cargo,setor,salario_base,criado_em,atualizado_em) VALUES('E2E1','Colaborador E2E','52998224725','1990-01-01','e2e@empresa.com.br','2024-01-01','Analista','TI',3200,'2026-01-01 00:00:00','2026-01-01 00:00:00')")
c.commit()
PY
node tests/e2e/login.e2e.js
