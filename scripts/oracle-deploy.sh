#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ ! -f .env ]]; then
  echo "Missing .env in ${ROOT_DIR}"
  echo "Start from .env.oracle.example and fill in your real values."
  exit 1
fi

mkdir -p tmp/uploaded_contexts tmp/canvas_artifacts tmp/logs

docker compose -f docker-compose.oracle.yml up -d --build

echo
echo "Backend stack is starting."
echo "Verify with: curl -I https://${APP_DOMAIN:-api.your-domain.com}/api/health"
