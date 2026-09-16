#!/usr/bin/env bash
# One-command cold start: venv, deps, models, demo faces, samples, server.
# Idempotent — safe to re-run; each step skips work already done.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "!! python3 not found on PATH. Install Python 3.10+ and re-run." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> Creating virtualenv (.venv)"
  python3 -m venv .venv
fi

if [ ! -x .venv/bin/python ]; then
  echo "!! .venv exists but is broken (no .venv/bin/python). Delete .venv and re-run." >&2
  exit 1
fi

echo "==> Installing dependencies"
./.venv/bin/pip install -q -r requirements.txt

if [ ! -f models/face_detection_yunet_2023mar.onnx ] || [ ! -f models/face_recognition_sface_2021dec.onnx ]; then
  echo "==> Downloading face models (one time, needs network)"
  ./.venv/bin/python -m scripts.download_models || \
    echo "!! Face models unavailable — the face and liveness engines will degrade gracefully."
fi

if [ ! -d data/faces ] || [ -z "$(ls -A data/faces 2>/dev/null)" ]; then
  echo "==> Fetching synthetic demo faces (one time, needs network)"
  ./.venv/bin/python -m scripts.fetch_faces || \
    echo "!! Demo faces unavailable — sample documents will render without portraits."
else
  echo "==> Demo faces already present, skipping fetch"
fi

if [ ! -f data/samples/manifest.json ]; then
  echo "==> Generating sample documents"
  ./.venv/bin/python -m scripts.make_samples
else
  echo "==> Sample documents already present, skipping generation"
fi

echo "==> Starting on http://localhost:8000"
exec ./.venv/bin/uvicorn app.main:app --port 8000
