"""로컬 API 서버. 127.0.0.1에서만 열고 외부 주소를 부르지 않는다.

실행: uv run uvicorn jeju_agent.api:app --port 8100
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

import json
import os
import threading

from pydantic import BaseModel

from . import llm, paths, pipeline, planner, privacy

app = FastAPI(title="제주 센터 데이터 분석 에이전트", docs_url="/api/docs")

# 이 엔진은 이용자의 브라우저에서도 열리므로(--open), 같은 브라우저의 다른 사이트가 요청을 보낼 수 있다.
# 1) Host 허용 목록(P01): DNS rebinding으로 다른 이름을 달고 온 요청은 400.
# 2) 출처 검사(P02): 다른 출처 화면이 보낸 상태 변경 요청은 403. 헤더가 없는 실행기 요청은 허용한다.
LOCAL_HOSTS = ["127.0.0.1", "localhost"]
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def _same_origin_only(request: Request, call_next):
    if request.method not in _SAFE_METHODS:
        site = request.headers.get("sec-fetch-site")
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if (site is not None and site not in {"same-origin", "none"}) or (
            origin is not None and origin != f"http://{host}"
        ):
            return JSONResponse({"detail": "다른 사이트에서 온 요청은 받지 않아요."}, status_code=403)
    return await call_next(request)


# 나중에 붙인 미들웨어가 먼저 실행된다. Host 검사가 출처 검사보다 앞선다.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)
_warm = {"ready": False}
_model = {"ready": False, "checked": False, "reason": "", "warming": False}
_startup = {"cleared": 0}


def _warm_up() -> None:
    """예측 모델을 처음 쓸 때의 컴파일(약 30초)을 시작 직후 뒤에서 끝내 둔다."""
    import numpy as np
    import pandas as pd

    from . import forecast

    idx = pd.period_range("2020-01", periods=48, freq="M")
    try:
        forecast.forecast(pd.Series(100 + 10 * np.sin(np.arange(48) / 12 * 2 * np.pi), index=idx), horizon=3)
    finally:
        _warm["ready"] = True


@app.on_event("startup")
def _start_warm_up() -> None:
    import os
    import threading

    # 지난번에 창을 닫지 못하고 꺼졌다면 남은 작업을 여기서 지운다(자동 삭제가 켜져 있을 때).
    if os.environ.get("JEJU_KEEP_WORKSPACE") != "1":
        _startup["cleared"] = privacy.clear_if_auto()
    if os.environ.get("JEJU_SKIP_WARMUP") != "1":
        threading.Thread(target=_warm_up, daemon=True).start()
        threading.Thread(target=_warm_model, daemon=True).start()


def _warm_model() -> None:
    """고정 질문 하나를 실제 모델로 왕복해 ready를 정한다(설계 5절). 모델을 처음 불러오는 시간도 여기서 쓴다."""
    if _model["warming"]:
        return
    _model["warming"] = True
    try:
        ids = {ds.id for ds in pipeline.datasets()}
        probe = "hub-502" if "hub-502" in ids else "center-1-19-dummy"  # 공개 배포판에는 허브 원본이 없다
        result = planner.plan(pipeline.find(probe), "작년보다 늘었어?", timeout=60)
        _model["ready"] = not result.get("fallback")
        _model["reason"] = result.get("reason", "")
    except Exception as err:  # 점검 실패는 직접 선택으로 쓰면 되므로 앱을 멈추지 않는다
        _model["reason"] = str(err)
    finally:
        _model["checked"] = True
        _model["warming"] = False
WEB_DIST = paths.WEB_DIST


def _dataset(dataset_id: str) -> pipeline.Dataset:
    try:
        return pipeline.find(dataset_id)
    except KeyError:
        raise HTTPException(404, "자료를 찾지 못했어요.") from None


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "offline": True, "model_ready": _model["ready"], "forecast_ready": _warm["ready"]}


@app.get("/api/model")
def model_status() -> dict:
    status = llm.status()
    # 프로그램을 켠 뒤에 Ollama를 켜거나 모델을 받은 경우: 다시 점검한다.
    if status.get("available") and not _model["ready"] and not _model["warming"] and os.environ.get("JEJU_SKIP_WARMUP") != "1":
        threading.Thread(target=_warm_model, daemon=True).start()
    return {**status, "ready": bool(status.get("available") and _model["ready"]), "checked": _model["checked"]}


class Question(BaseModel):
    question: str


@app.post("/api/datasets/{dataset_id}/plan")
def make_plan(dataset_id: str, body: Question) -> dict:
    if not body.question.strip():
        raise HTTPException(400, "질문을 적어 주세요.")
    return planner.plan(_dataset(dataset_id), body.question)


@app.get("/api/datasets")
def list_datasets() -> list[dict]:
    return [pipeline._ds_dict(ds) for ds in pipeline.datasets()]


@app.post("/api/datasets")
async def upload(file: UploadFile) -> dict:
    name = Path(file.filename or "upload.csv").name
    if not name.lower().endswith(".csv"):
        raise HTTPException(400, "CSV 파일만 넣을 수 있어요.")
    safe = re.sub(r"[^\w.\-가-힣]", "_", name)
    pipeline.WORKSPACE.mkdir(parents=True, exist_ok=True)
    target = pipeline.WORKSPACE / safe
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return pipeline._ds_dict(pipeline.find(f"upload-{target.stem}"))


@app.get("/api/datasets/{dataset_id}/understand")
def understand(dataset_id: str) -> dict:
    return pipeline.understand(_dataset(dataset_id))


@app.get("/api/datasets/{dataset_id}/analyze")
def analyze(
    dataset_id: str,
    value: str | None = None,
    category: str | None = None,
    intent: str | None = None,
    filters: str | None = None,
    period_n: int | None = None,
    horizon: int = 6,
) -> dict:
    """filters는 JSON 문자열 [{"column":..., "values":[...]}]. 서버가 열과 값을 다시 검증한다."""
    ds = _dataset(dataset_id)
    parsed: list[dict] = []
    if filters:
        try:
            parsed = json.loads(filters)
        except json.JSONDecodeError:
            raise HTTPException(400, "거르는 조건을 읽지 못했어요.") from None
        ctx = planner.context(ds)
        for f in parsed:
            allowed = set(ctx.uniques.get(f.get("column"), []))
            if not allowed or not set(f.get("values") or []) <= allowed:
                raise HTTPException(400, "자료에 없는 열이나 값으로 거를 수 없어요.")
    if intent not in planner.INTENTS:
        intent = None
    horizon = min(max(int(horizon), 1), 12)
    return pipeline.analyze(ds, value, category, horizon=horizon, filters=parsed, intent=intent, period_n=period_n)


@app.get("/api/join")
def join(left: str, left_value: str, right: str, right_value: str) -> dict:
    return pipeline.join_monthly(_dataset(left), left_value, _dataset(right), right_value)


@app.delete("/api/workspace")
def clear_workspace() -> dict:
    return {"removed": privacy.clear()}


@app.post("/api/workspace/exit")
def on_exit() -> dict:
    """실행기가 창을 닫기 직전에 부른다. 자동 삭제가 켜져 있을 때만 지운다."""
    return {"removed": privacy.clear_if_auto(), **privacy.load()}


class Settings(BaseModel):
    auto_delete: bool


@app.get("/api/settings")
def get_settings() -> dict:
    return privacy.load()


@app.put("/api/settings")
def put_settings(body: Settings) -> dict:
    return privacy.save(body.auto_delete)


@app.get("/api/selfcheck")
def selfcheck() -> dict:
    """자가 점검. 심사와 센터 운영자가 설치 직후 한눈에 확인한다."""
    status = llm.status()
    try:
        llm.base_url()
        url_ok, url_detail = True, "이 PC(127.0.0.1)의 모델만 불러요"
    except llm.ModelUnavailable as err:
        url_ok, url_detail = False, str(err)
    warning = privacy.ollama_host_warning()
    files = privacy.files()
    settings = privacy.load()
    items = [
        {"key": "engine", "label": "분석 엔진", "ok": True, "detail": "켜져 있어요"},
        {"key": "forecast", "label": "예측 준비", "ok": _warm["ready"], "detail": "준비됐어요" if _warm["ready"] else "준비 중이에요(처음 켤 때 30초쯤)"},
        {
            "key": "model",
            "label": "로컬 AI",
            "ok": bool(status.get("available") and _model["ready"]),
            "detail": f"{status['model']} 준비됐어요" if status.get("available") and _model["ready"] else status.get("reason") or "준비 중이에요",
            "optional": True,
        },
        {"key": "model_url", "label": "모델 주소", "ok": url_ok, "detail": url_detail},
        {"key": "ollama_host", "label": "모델 외부 접속", "ok": warning is None, "detail": warning or "다른 PC에서 접속할 수 없어요"},
        {"key": "workspace", "label": "내 작업", "ok": True, "detail": f"파일 {len(files)}개"},
        {"key": "auto_delete", "label": "끝낼 때 자동 지우기", "ok": True, "detail": "켜짐" if settings["auto_delete"] else "꺼짐"},
    ]
    return {"items": items, "workspace": str(privacy.workspace()), "startup_cleared": _startup["cleared"], **settings}


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
