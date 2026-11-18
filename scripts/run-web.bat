@echo off
rem 개발용(Windows): 화면을 빌드하고 엔진을 켠 뒤 기본 웹 브라우저로 연다.
cd /d "%~dp0\.."
if not exist web\dist (pushd web & call pnpm install --frozen-lockfile & call pnpm build & popd)
uv run python -m jeju_agent.server --open %*
