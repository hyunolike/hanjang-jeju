"""웹 Agent: 계획은 모델, 검증과 계산 도구 실행 계약은 코드가 맡는다."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import cloudflare, pipeline, planner, web_input
from .facts import Fact, sentence_matches_facts


class RawFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    column: str
    text: str = Field(min_length=1, max_length=20)


class RawPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["all", "recent_n"]
    n: int = Field(ge=0, le=36)


class RawPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    intent: Literal["overview", "compare", "share", "rank", "forecast"]
    value: str | None
    group_by: str | None
    filters: list[RawFilter] = Field(max_length=2)
    period: RawPeriod
    forecast_months: int = Field(ge=0, le=12)


def digest(raw: bytes, question: str, spec: web_input.ExecutionSpec) -> str:
    canonical = json.dumps({"file": hashlib.sha256(raw).hexdigest(), "question": question, "execution_spec": spec.model_dump()}, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def validate_execution(raw: bytes, question: str, spec: dict, input_digest: str) -> web_input.ExecutionSpec:
    try:
        parsed = web_input.ExecutionSpec.model_validate(spec)
    except ValidationError:
        web_input.reject("계획의 열, 조건과 도구를 다시 확인해 주세요.")
    if not input_digest or digest(raw, question, parsed) != input_digest:
        web_input.reject("파일이나 질문, 계획이 바뀌었어요. 계획을 다시 확인해 주세요.")
    return parsed


def plan(ds: pipeline.Dataset, raw: bytes, question: str, selection: dict, edited_spec: dict | None = None) -> dict:
    if not question.strip() or len(question) > 300:
        web_input.reject("질문은 1자부터 300자까지 입력해 주세요.")
    if edited_spec is not None:
        try:
            spec = web_input.ExecutionSpec.model_validate(edited_spec)
        except ValidationError:
            web_input.reject("수정한 계획을 확인해 주세요.")
        web_input.dataset(raw, ds.title, spec)
        return {"execution_spec": spec.model_dump(), "input_digest": digest(raw, question, spec), "blocked": [], "unresolved": [], "needs": [], "unsupported": [], "edited": True}
    ctx = planner.context(ds)
    metadata = [{k: c[k] for k in ("name", "ko", "role", "unit", "additive")} for c in ctx.measures + ctx.groups]
    # 원본 행, 파일명, 고유값 예시는 외부 모델 맥락에 넣지 않는다.
    text = json.dumps({"columns": metadata}, ensure_ascii=False)
    if len(text) + len(question) + len(planner.SYSTEM_RULES) > 5000:
        web_input.reject("계획에 사용할 열을 줄여 주세요. 열 정보가 너무 길어요.")
    messages = [{"role": "user", "content": text}, {"role": "user", "content": question}]
    started = time.monotonic()
    raw_plan = None
    for attempt in range(2):
        try:
            raw_plan = cloudflare.chat_json(planner.SYSTEM_RULES, messages, planner.schema(ctx))
            break
        except cloudflare.ModelError as err:
            if err.code == "parse_failed" and attempt == 0:
                messages.append({"role": "user", "content": "정해진 JSON 계획 하나로 다시 작성해 주세요."})
                continue
            return {"fallback": True, "reason": err.code}
    try:
        checked = RawPlan.model_validate(raw_plan)
        if checked.value is not None and checked.value not in {c["name"] for c in ctx.measures}:
            raise ValueError
        groups = {c["name"] for c in ctx.groups}
        if checked.group_by is not None and checked.group_by not in groups:
            raise ValueError
        if any(f.column not in groups for f in checked.filters):
            raise ValueError
    except (ValidationError, ValueError):
        return {"fallback": True, "reason": "invalid_plan"}
    result = planner.finish(ctx, question, checked.model_dump(), model=cloudflare.status()["model"], latency_ms=int((time.monotonic() - started) * 1000))
    # 재검증과 사용자 수정에 쓰는 완전한 계획. 확인 전 실행하지 않는다.
    p = result["plan"]
    try:
        spec = web_input.ExecutionSpec.model_validate({**selection, "value": p["value"], "category": p["group_by"] or selection.get("category"), "intent": p["intent"], "filters": p["filters"], "period_n": p["period_n"], "horizon": p["horizon"], "run_forecast": p["intent"] == "forecast", "tools": []})
    except ValidationError:
        return {"fallback": True, "reason": "invalid_plan"}
    if result["unsupported"]:
        result["blocked"].append("자료로 답할 수 없는 질문이에요. 질문을 바꿔 주세요.")
    result.update(execution_spec=spec.model_dump(), input_digest="" if result["blocked"] else digest(raw, question, spec))
    # raw 모델 출력은 클라이언트에 반환하지 않는다.
    result.pop("raw", None)
    return result


def verify_result(result: dict) -> bool:
    if result.get("error"):
        return True
    try:
        facts = {key: Fact(**value) for key, value in result.get("facts", {}).items()}
        for card in [*result.get("cards", []), *([result["answer"]] if result.get("answer") else [])]:
            refs = [replace(facts[key], basis={**facts[key].basis, "label": facts[key].label}) for key in card.get("facts", [])]
            # 결정적 문장은 '10% 줄었어요'처럼 부호를 방향 말로 표현한다.
            refs += [replace(f, value=abs(f.value)) for f in refs if f.kind == "change_pct"]
            if not sentence_matches_facts(card["title"], refs):
                raise ValueError
        if result.get("forecast") and result["forecast"]["fact"] not in facts:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise HTTPException(422, "계산 근거를 확인하지 못했어요. 조건을 바꿔 다시 분석해 주세요.") from None
    return True
