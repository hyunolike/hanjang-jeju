"""내 작업 지우기와 자동 삭제 설정 (주최 측 답변: 결과 삭제 기능 ON/OFF).

작업 폴더에는 이용자가 넣은 CSV만 둔다. 분석 결과는 화면과 인쇄로만 내보내고 파일로 남기지 않는다.
자동 삭제(기본 켜짐)는 두 곳에서 동작한다.
1. 창을 닫을 때: Windows, Mac 실행기가 엔진을 끄기 전에 POST /api/workspace/exit를 부른다.
2. 다음에 켤 때: 비정상 종료로 남은 파일이 있으면 시작하자마자 지운다.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import pipeline


def workspace() -> Path:
    return pipeline.WORKSPACE  # 업로드와 같은 곳을 본다(테스트에서 바꿔 끼울 수 있게 매번 읽는다)


def settings_path() -> Path:
    return workspace().parent / "settings.json"


def load() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"auto_delete": bool(data.get("auto_delete", True))}


def save(auto_delete: bool) -> dict:
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text(json.dumps({"auto_delete": auto_delete}), encoding="utf-8")
    return load()


def files() -> list[Path]:
    return sorted(workspace().glob("*.csv")) if workspace().exists() else []


def clear() -> int:
    removed = len(files())
    if workspace().exists():
        shutil.rmtree(workspace())
    return removed


def clear_if_auto() -> int:
    return clear() if load()["auto_delete"] else 0


def ollama_host_warning() -> str | None:
    """Ollama가 이 PC 밖에서도 접속되게 열려 있으면 경고한다(설계 7절)."""
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return None
    name = host.split("://")[-1].rsplit(":", 1)[0].strip("[]")
    if name in {"127.0.0.1", "localhost", "::1", ""}:
        return None
    return f"OLLAMA_HOST가 '{host}'로 설정되어 다른 PC에서도 모델에 접속할 수 있어요. 127.0.0.1로 바꿔 주세요."
