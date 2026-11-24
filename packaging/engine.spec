# PyInstaller 설정: 분석 엔진을 한 폴더짜리 실행 파일로 묶는다.
# 사용(저장소 루트에서): uv run pyinstaller packaging/engine.spec --noconfirm
# 결과: dist/jeju-engine/  (jeju-engine.exe 와 자료, 화면)
# JEJU_PUBLIC=1 이면 공개 배포판: 허브 원본(data/hub)은 재배포할 수 없으므로 빼고 센터 더미만 넣는다.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
public = os.environ.get("JEJU_PUBLIC") == "1"
datas = [] if public else [(str(root / "data/hub"), "data/hub")]
datas += [
    (str(root / "pyproject.toml"), "."),
    (str(root / "data/dummy"), "data/dummy"),
    (str(root / "data/reference/center_spec.json"), "data/reference"),
    (str(root / "data/reference/hub_tables.json"), "data/reference"),
    (str(root / "web/dist"), "web/dist"),
]
binaries, hiddenimports = [], collect_submodules("uvicorn") + ["jeju_agent.api"]
for package in ("statsforecast", "numba", "llvmlite", "coreforecast"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(root / "src/jeju_agent/server.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "openpyxl"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="jeju-engine", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="jeju-engine", upx=False)
