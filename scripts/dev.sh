#!/usr/bin/env bash
# J.A.R.V.I.S. — Arranca backend (FastAPI) y frontend (Next.js) en paralelo.
# Uso: ./scripts/dev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[dev] Comprobando dependencias..."
[ -d "$ROOT/frontend/node_modules" ] || { echo "[dev] Instalando frontend..."; (cd "$ROOT/frontend" && npm install); }
[ -d "$ROOT/backend/.venv" ] || { echo "[dev] Creando venv e instalando backend..."; python3 -m venv "$ROOT/backend/.venv" && "$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"; }

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT

echo "[dev] Iniciando FastAPI en http://localhost:8000 (docs en /docs)"
(cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) &

echo "[dev] Iniciando Next.js en http://localhost:3000"
(cd "$ROOT/frontend" && npm run dev) &

wait
