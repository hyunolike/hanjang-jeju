#!/usr/bin/env bash
# 개발용: 화면을 빌드하고 엔진을 켠 뒤 기본 웹 브라우저로 연다.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d web/dist ] || (cd web && pnpm install --frozen-lockfile && pnpm build)
uv run python -m jeju_agent.server --open "$@"
