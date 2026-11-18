"""자료, 화면, 작업 폴더의 위치.

- 개발 중: 저장소 루트 기준.
- 묶은 실행 파일(PyInstaller): 실행 파일에 함께 넣은 자료(`sys._MEIPASS`) 기준.
- 작업 폴더(이용자가 넣은 CSV): 환경 변수 `JEJU_WORKSPACE`가 있으면 그곳.
  Windows 프로그램은 `%LOCALAPPDATA%\\HanJangJeju\\workspace`를 넘겨준다. 지우기 기능이 이 폴더를 지운다.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _root() -> Path:
    if os.environ.get("JEJU_ROOT"):
        return Path(os.environ["JEJU_ROOT"])
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


ROOT = _root()
HUB = ROOT / "data/hub"
DUMMY = ROOT / "data/dummy"
REFERENCE = ROOT / "data/reference"
WEB_DIST = Path(os.environ.get("JEJU_WEB_DIST", ROOT / "web/dist"))
WORKSPACE = Path(os.environ.get("JEJU_WORKSPACE", ROOT / "data/private/workspace"))
