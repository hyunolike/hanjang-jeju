"""공개 전용 API. CSV는 요청 안에서만 처리한다."""
from __future__ import annotations

import json
import math

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from . import cloudflare, pipeline, web_agent, web_input, web_profile

app = FastAPI(title="한 장 제주 공개 분석", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def request_guard(request: Request, call_next):
    if request.method == "POST":
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > web_input.MAX_BYTES + 65536:
                return JSONResponse({"detail": "CSV는 3MiB 이하로 넣어 주세요."}, status_code=413, headers={"Cache-Control": "private, no-store"})
            chunks.append(chunk)
        request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse({"detail": "파일과 분석 옵션을 확인해 주세요."}, status_code=422)


@app.exception_handler(web_input.SelectionError)
async def invalid_selection(request, exc):
    return JSONResponse({"detail": exc.detail, "issue": exc.issue}, status_code=exc.status_code)


def options(text: str) -> web_input.ExecutionSpec:
    try:
        return web_input.ExecutionSpec.model_validate(json.loads(text))
    except (ValueError, ValidationError, TypeError):
        raise HTTPException(422, "분석할 열, 조건과 도구를 확인해 주세요.") from None


async def read_upload(file: UploadFile) -> bytes:
    try:
        raw = await file.read(web_input.MAX_BYTES + 1)
        if len(raw) > web_input.MAX_BYTES:
            web_input.reject("CSV는 3MiB 이하로 넣어 주세요.", 413)
        return raw
    finally:
        await file.close()


def finite(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(v) for v in value]
    return value


@app.get("/api/web/health")
def health():
    return {"ok": True, "max_bytes": web_input.MAX_BYTES}


@app.get("/api/web/capabilities")
def capabilities():
    return {**cloudflare.status(), "max_bytes": web_input.MAX_BYTES, "max_rows": web_input.MAX_ROWS, "max_columns": web_input.MAX_COLUMNS}


@app.post("/api/web/understand")
async def understand(file: UploadFile = File(), options_text: str = Form("", alias="options")):
    raw = await read_upload(file)
    spec = options(options_text) if options_text and options_text != "{}" else None
    ds = web_input.dataset(raw, file.filename or "upload.csv", spec)
    result = await run_in_threadpool(pipeline.understand, ds)
    result["upload_profile"] = await run_in_threadpool(web_profile.describe, ds)
    if spec is None:
        meanings = {c["name"]: c for c in result["upload_profile"]["columns"]}
        for column in result["columns"]:
            column.update({key: meanings[column["name"]][key] for key in ("role", "unit", "additive")})
    return finite(result)


@app.post("/api/web/analyze")
async def analyze(file: UploadFile = File(), mode: str = Form("manual"), options_text: str = Form("{}", alias="options"), question: str = Form(""), execution_spec: str = Form("{}"), input_digest: str = Form(""), confirmed: bool = Form(False)):
    raw = await read_upload(file)
    if mode == "agent":
        if not confirmed or options_text != "{}":
            web_input.reject("계획을 확인한 뒤 실행해 주세요.")
        try:
            payload = json.loads(execution_spec)
        except ValueError:
            web_input.reject("실행 계획을 읽지 못했어요.")
        spec = web_agent.validate_execution(raw, question, payload, input_digest)
    elif mode == "manual":
        spec = options(options_text)
    else:
        web_input.reject("분석 실행 모드를 확인해 주세요.")
    ds = web_input.dataset(raw, file.filename or "upload.csv", spec)
    result = await run_in_threadpool(pipeline.analyze, ds, value=spec.value, category=spec.category, intent=spec.intent, filters=[f.model_dump() for f in spec.filters], period_n=spec.period_n, horizon=spec.horizon, run_forecast=spec.run_forecast)
    result["execution"] = {"mode": mode, "question": question if mode == "agent" else None, "tools": spec.tools, "verified": web_agent.verify_result(result)}
    return finite(result)


@app.post("/api/web/plan")
async def plan(file: UploadFile = File(), options_text: str = Form(alias="options"), question: str = Form(), edited_spec: str = Form("")):
    raw = await read_upload(file)
    spec = options(options_text)
    ds = web_input.dataset(raw, file.filename or "upload.csv", spec)
    try:
        edited = json.loads(edited_spec) if edited_spec else None
    except ValueError:
        web_input.reject("수정한 계획을 읽지 못했어요.")
    return finite(await run_in_threadpool(web_agent.plan, ds, raw, question, spec.model_dump(), edited))
