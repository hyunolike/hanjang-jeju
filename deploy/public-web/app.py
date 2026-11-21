"""공개 웹 배포 진입점. 로컬 API와 작업 폴더 경로를 외부에 열지 않는다."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / "src").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("JEJU_ROOT", str(ROOT))
os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(tempfile.gettempdir()) / "hanjang-jeju-numba"))

from jeju_agent.web_api import app  # noqa: E402,F401

# Vercel의 public/은 CDN이 제공한다. 로컬 통합 실행에서만 정적 화면을 붙인다.
if not os.environ.get("VERCEL"):
    from fastapi.staticfiles import StaticFiles
    static = ROOT / "public" if (ROOT / "public").exists() else ROOT / "web/dist-public"
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="public-web")
