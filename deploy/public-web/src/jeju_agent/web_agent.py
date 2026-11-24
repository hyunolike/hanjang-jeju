"""웹 Agent: 계획은 모델, 검증과 계산 도구 실행 계약은 코드가 맡는다."""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import replace
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import cloudflare, pipeline, planner, web_input, web_business
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
    business_task: Literal["quarter_compare", "category_change", "brief"] | None = None


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


WEB_SYSTEM_RULES = """너는 제주 데이터 분석 도우미의 공개 웹 계획 담당이다.
질문을 분석 계획 JSON 하나로만 바꾼다. 계산하거나 문장으로 답하지 않는다.
필수 필드: intent,value,group_by,filters,period,forecast_months,business_task.
value/group_by/filters.column은 전달한 columns에 있는 이름만 쓴다. 없으면 null.

먼저 질문에 맞는 business_task를 고른다.
- 보고용/보고서/요약을 요청하며 분기를 다루면 brief.
- 분류별/업종별 증감이나 기여 항목을 물으면 category_change.
- 전년 같은 분기/전년 동분기 비교를 물으면 quarter_compare.
- 일반 흐름/추세/순위/비중/월별 비교/예측이면 반드시 null.
business_task가 null이 아니면 intent는 반드시 overview다. compare를 쓰지 않는다.
업무 task의 period는 {"kind":"all","n":0}, forecast_months는 0이다.
업무 기간은 코드가 정해 확인받는다. 날짜나 집계값은 추측하지 않는다.
category_change와 brief의 group_by는 가능하면 나눠 볼 분류 열이다.

business_task가 null인 일반 질문의 intent:
- 흐름/추세/전체 현황 -> overview. 이것은 보고용 요약이나 brief가 아니다.
- 기간 비교/작년보다 -> compare. 분기 비교와는 다른 기존 계산이다.
- 비중/구성 -> share. 순위/가장 많은 곳 -> rank. 전망/예측/앞으로 -> forecast.
질문의 나눠 보기 기준이 있으면 group_by에 그 분류나 지역 열을 쓴다.
filters는 특정 지역/업종으로 좁힐 때만 쓴다. text는 질문에 나온 말 그대로다.
period 기본은 {"kind":"all","n":0}. 일반 질문의 최근 N개월만 recent_n으로 쓴다.
forecast_months는 예측 요청 개월 수(최대12), 예측 요청이 없으면 0.

예: "마지막 분기 업종별 전년 동분기 대비 증감" -> business_task="category_change",intent="overview".
예: "최근 분기 실적을 작년 같은 분기와 견줘 보고용으로 요약" -> business_task="brief",intent="overview".
예: "전년 같은 분기와 비교" -> business_task="quarter_compare",intent="overview".
예: "전체 흐름을 보여줘" -> business_task=null,intent="overview".
예: "업종별 순위를 보여줘" -> business_task=null,intent="rank".
"""


def business_scope_error(question: str) -> bool:
    return bool(re.search(r"[0-9]{4}|[1-4]\s*분기|직전|전\s*분기|이전\s*분기|지난\s*분기|이번\s*분기|최근\s*[0-9]+\s*개월|[0-9]+\s*월|반년|상반기|하반기|예측|전망|앞으로", question))


def _finish_business(ds, raw, question, spec, result):
    checked_ds = web_input.dataset(raw, ds.title, spec)
    preview = web_business.preview(checked_ds, spec)
    if business_scope_error(question):
        result['blocked'].append('업무 분석은 자료의 마지막 분기와 전년 같은 분기만 비교해요. 표시된 기간을 확인하거나 다른 분석을 선택해 주세요.')
    if spec.business_task == 'category_change' and not spec.category:
        result['blocked'].append('분류별 증감을 보려면 이전 단계에서 분류 열을 골라 주세요.')
    if preview['status'] == 'blocked':
        result['blocked'].extend(x['message'] for x in preview['limitations'] if x['code'] != 'observation_scope')
    result.update(business_preview=preview, plan_origin=spec.plan_origin, execution_spec=spec.model_dump(), input_digest='' if result['blocked'] else digest(raw, question, spec))
    return result


def plan(ds: pipeline.Dataset, raw: bytes, question: str, selection: dict, edited_spec: dict | None = None, business_task: str | None = None) -> dict:
    if not question.strip() or len(question) > 300:
        web_input.reject("질문은 1자부터 300자까지 입력해 주세요.")
    if business_task is not None:
        if edited_spec is not None or business_task not in web_business.TASKS:
            web_input.reject('업무 분석 종류와 수정한 계획을 함께 보낼 수 없어요.')
        try:
            spec = web_input.ExecutionSpec.model_validate({**selection, 'business_task': business_task, 'plan_origin': 'recipe', 'intent': 'overview', 'period_n': 0, 'run_forecast': False, 'tools': []})
        except ValidationError:
            web_input.reject('업무 분석 조건을 다시 확인해 주세요.')
        result = {'blocked': [], 'unresolved': [], 'needs': [], 'unsupported': []}
        return _finish_business(ds, raw, question, spec, result)
    if edited_spec is not None:
        try:
            spec = web_input.ExecutionSpec.model_validate(edited_spec)
        except ValidationError:
            web_input.reject("수정한 계획을 확인해 주세요.")
        web_input.dataset(raw, ds.title, spec)
        if spec.business_task:
            return _finish_business(ds, raw, question, spec, {'blocked': [], 'unresolved': [], 'needs': [], 'unsupported': [], 'edited': True})
        if '분기' in question:
            web_input.reject('분기 질문은 업무 분석 계획으로 다시 확인해 주세요.')
        return {"execution_spec": spec.model_dump(), "input_digest": digest(raw, question, spec), "blocked": [], "unresolved": [], "needs": [], "unsupported": [], "edited": True}
    ctx = planner.context(ds)
    metadata = [{k: c[k] for k in ("name", "ko", "role", "unit", "additive")} for c in ctx.measures + ctx.groups]
    # 원본 행, 파일명, 고유값 예시는 외부 모델 맥락에 넣지 않는다.
    text = json.dumps({"columns": metadata}, ensure_ascii=False)
    if len(text) + len(question) + len(WEB_SYSTEM_RULES) > 5000:
        web_input.reject("계획에 사용할 열을 줄여 주세요. 열 정보가 너무 길어요.")
    messages = [{"role": "user", "content": text}, {"role": "user", "content": question}]
    started = time.monotonic()
    raw_plan = None
    for attempt in range(2):
        try:
            schema = planner.schema(ctx)
            schema['properties']['business_task'] = {'enum': [None, *web_business.TASKS]}
            schema['required'].append('business_task')
            raw_plan = cloudflare.chat_json(WEB_SYSTEM_RULES, messages, schema)
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
        if checked.business_task and (checked.intent != 'overview' or checked.period.kind != 'all' or checked.period.n or checked.forecast_months):
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
    if checked.business_task:
        p.update(intent='overview', period_n=0, horizon=6)
        p['group_by'] = checked.group_by or selection.get('category')
    elif '분기' in question:
        result['blocked'].append('분기 질문에 맞는 업무 계획을 만들지 못했어요. 전년 같은 분기 비교 예시나 검토된 절차를 선택해 주세요.')
    try:
        spec = web_input.ExecutionSpec.model_validate({**selection, "value": p["value"], "category": p["group_by"] or selection.get("category"), "intent": p["intent"], "filters": p["filters"], "period_n": p["period_n"], "horizon": p["horizon"], "run_forecast": p["intent"] == "forecast", "tools": [], "business_task": checked.business_task, "plan_origin": "model" if checked.business_task else None})
    except ValidationError:
        return {"fallback": True, "reason": "invalid_plan"}
    if result["unsupported"]:
        result["blocked"].append("자료로 답할 수 없는 질문이에요. 질문을 바꿔 주세요.")
    if spec.business_task:
        result.pop('raw', None)
        return _finish_business(ds, raw, question, spec, result)
    result.update(execution_spec=spec.model_dump(), input_digest="" if result["blocked"] else digest(raw, question, spec))
    # raw 모델 출력은 클라이언트에 반환하지 않는다.
    result.pop("raw", None)
    return result


def verify_result(result: dict) -> bool:
    if result.get('business'):
        return web_business.verify(result)
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
