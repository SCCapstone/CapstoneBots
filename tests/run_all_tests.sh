#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR/backend"
if [[ -x ".venv/bin/python" ]]; then
	.venv/bin/python -m pytest tests/ -v --ignore=tests/test_storage.py --ignore=tests/test_object_storage.py
else
	echo "backend/.venv not found. Create it with: cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
	exit 1
fi

cd "$ROOT_DIR/frontend"
npm test -- --runInBand
