"""질문 → 분석 계획 (설계 agent-design.md 2판).

모델은 계획만 만든다. 출력은 자료마다 만든 JSON Schema로 제한해 자료에 없는 열을 낼 수 없게 한다.
필터 값 맞추기, 받아 올 표 제안, 답할 수 없는 부분 찾기, 실행 막기는 코드가 결정적으로 한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import dictionary, ingest, llm, pipeline

INTENTS = ["overview", "compare", "share", "rank", "forecast"]
PERSONAL = re.compile(r"(user_id|card_id|mac_address|user_card_id)", re.I)
UNSUPPORTED_WORDS = {
    "왜": "원인은 자료로 단정할 수 없어요",
    "원인": "원인은 자료로 단정할 수 없어요",
    "때문": "원인은 자료로 단정할 수 없어요",
    "누가": "개인을 특정하는 질문은 답하지 않아요",
    "개인": "개인을 특정하는 질문은 답하지 않아요",
}
# 주제어 → (센터 명세 표 번호, 지금 자료에 이 주제가 있는지 볼 단서)
TOPICS = {
    "유동인구": ("4-11", ("pop", "인구", "visit")),
    "방문객": ("4-11", ("pop", "인구", "visit")),
    "외국인": ("4-15", ("외국", "foreign", "nationality")),
    "매장": ("1-17", ("store", "매장")),
    "카드": ("1-08", ("카드", "card")),
    "메뉴": ("1-24", ("menu", "메뉴")),
    "날씨": ("5-02", ("rain", "temperature", "강수", "기온")),
    "강수": ("5-02", ("rain", "강수")),
    "기온": ("5-02", ("temperature", "기온")),
    "버스": ("3-04", ("bus", "버스")),
    "와이파이": ("4-05", ("wifi", "와이파이")),
    "쓰레기": ("5-03", ("waste", "쓰레기", "종량제")),
}

# 의도 단서어 (평가 1차에서 1.5B~3B 모델이 '추세'를 전망으로, '대비'를 구성비로 읽는 일이 잦아 코드가 정한다).
INTENT_CUES = {
    "forecast": re.compile(r"전망|예측|앞으로|뒤까지|내년|다음 ?달|향후"),
    "compare": re.compile(r"작년|지난해|전년|1년 ?전|일 ?년 ?전|전보다|그 ?전|직전|비교"),
    "share": re.compile(r"비중|구성|점유|차지"),
    "rank": re.compile(r"순위|상위|가장|제일|1위"),
}
SPLIT_CUE = re.compile(r"별|나눠|나누어")
RECENT = re.compile(r"(최근|요즘|지난)\s*(\d+)\s*개월")
RECENT_HALF = re.compile(r"(최근|요즘|지난)\s*반년")
HORIZON = re.compile(r"(\d+)\s*개월")


def intent_from_question(question: str, model_intent: str | None) -> str:
    """단서어가 있는 의도 가운데 모델이 고른 것이 있으면 그것을, 없으면 앞 순서를. 단서어가 없으면 overview."""
    found = [name for name, cue in INTENT_CUES.items() if cue.search(question)]
    if not found:
        return "overview"
    return model_intent if model_intent in found else found[0]


def horizon_from_question(question: str, model_months: int) -> int:
    if m := HORIZON.search(question):
        return min(max(int(m.group(1)), 1), 12)
    if re.search(r"반년|상반기|하반기", question):
        return 6
    if re.search(r"1년|일 ?년|12개월", question):
        return 12
    return min(max(model_months, 1), 12) if model_months else 6


def period_from_question(question: str) -> int:
    if m := RECENT.search(question):
        return int(m.group(2))
    if RECENT_HALF.search(question):
        return 6
    return 0


SYSTEM_RULES = """너는 제주 데이터 분석 도우미의 계획 담당이다. 질문을 분석 계획 JSON 하나로만 바꾼다.
규칙:
- 계산하지 않는다. 숫자를 지어내지 않는다.
- value, group_by, filters.column은 아래 '열 목록'에 있는 이름만 쓴다. 맞는 것이 없으면 null.
- intent: overview(전체 흐름), compare(기간끼리 비교, '작년보다', '전보다'), share(비중, 구성), rank(가장 많은 곳, 순위), forecast(앞으로, 전망, 예측).
- group_by: 질문이 '어떤 업종', '어디', '읍면동별'처럼 나눠 보기를 원할 때 그 분류나 지역 열.
- filters: 질문이 특정 지역이나 업종으로 좁힐 때. text에는 질문에 나온 말을 그대로 쓴다(예: "애월").
- period: 기본 {"kind":"all","n":0}. '최근 6개월'이면 {"kind":"recent_n","n":6}.
- forecast_months: 전망 기간(개월). 없으면 0. 12를 넘으면 12.
예시 1) 질문 "작년보다 늘었어?" -> {"intent":"compare","value":"<값 열>","group_by":null,"filters":[],"period":{"kind":"all","n":0},"forecast_months":0}
예시 2) 질문 "<지역> 어떤 업종 비중이 커?" -> {"intent":"share","value":"<값 열>","group_by":"<업종 열>","filters":[{"column":"<지역 열>","text":"<지역>"}],"period":{"kind":"all","n":0},"forecast_months":0}
"""


@dataclass
class Context:
    ds: pipeline.Dataset
    info: dict
    measures: list[dict]
    groups: list[dict]
    uniques: dict[str, list[str]]


def context(ds: pipeline.Dataset) -> Context:
    info = pipeline.understand(ds)
    measures = [c for c in info["columns"] if c["role"] == "measure"]
    groups = [c for c in info["columns"] if c["role"] in pipeline.GROUP_ROLES and c["name"] != info["time_column"]]
    # 이름 열(…_nm)이 있으면 같은 짝의 코드 열(…_cd)은 후보에서 뺀다. 사람은 이름으로 묻는다.
    names = {c["name"] for c in groups}
    groups = [c for c in groups if not (c["name"].endswith("_cd") and c["name"][:-3] + "_nm" in names)]
    data = ingest.load(ds.path).data
    uniques = {c["name"]: sorted(data[c["name"]].dropna().astype(str).unique().tolist()) for c in groups}
    return Context(ds, info, measures, groups, uniques)


def schema(ctx: Context) -> dict:
    values = [c["name"] for c in ctx.measures] + [None]
    groups = [c["name"] for c in ctx.groups]
    return {
        "type": "object",
        "required": ["intent", "value", "group_by", "filters", "period", "forecast_months"],
        "properties": {
            "intent": {"type": "string", "enum": INTENTS},
            "value": {"enum": values},
            "group_by": {"enum": groups + [None]},
            "filters": {
                "type": "array",
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "required": ["column", "text"],
                    "properties": {"column": {"type": "string", "enum": groups or ["_"]}, "text": {"type": "string", "maxLength": 20}},
                },
            },
            "period": {
                "type": "object",
                "required": ["kind", "n"],
                "properties": {"kind": {"type": "string", "enum": ["all", "recent_n"]}, "n": {"type": "integer", "minimum": 0, "maximum": 36}},
            },
            "forecast_months": {"type": "integer", "minimum": 0, "maximum": 12},
        },
    }


def semantic_layer(ctx: Context, with_meaning: bool = True) -> str:
    """기획안 13.1 의미 계층. with_meaning=False는 평가용(열 이름만)."""
    lines = [f"자료: {ctx.ds.title}", "열 목록:"]
    for c in ctx.measures + ctx.groups:
        if not with_meaning:
            lines.append(f"- {c['name']}")
            continue
        role = {"measure": "값", "category": "분류", "region": "지역"}[c["role"]]
        extra = f", 단위 {c['unit']}" if c["unit"] else ""
        if c["role"] == "measure":
            extra += ", 더해도 됨" if c["additive"] else ", 더하지 않음"
        line = f"- {c['name']}: {c['ko']} ({role}{extra})"
        values = ctx.uniques.get(c["name"])
        if values and len(values) <= 50 and not PERSONAL.search(c["name"]):
            line += " 예: " + ", ".join(f'"{v[:20]}"' for v in values[:8])
        lines.append(line)
    return "\n".join(lines)


def _match(ctx: Context, column: str, text: str) -> list[str]:
    t = pipeline.normalize_value(text)
    if len(t) < 2:
        return []
    found = []
    for v in ctx.uniques.get(column, []):
        nv = pipeline.normalize_value(v)
        if nv == t or (len(nv) >= 2 and (t in nv or nv in t)):
            found.append(v)
    return found


def _keys(value: str, role: str) -> set[str]:
    """값을 질문에서 찾을 열쇠. 지역은 '한림읍'을 '한림'으로도 찾는다(읍면동 글자 뺀 줄기, 2자 이상)."""
    v = pipeline.normalize_value(value)
    keys = {v}
    if role == "region" and len(v) >= 3 and v[-1] in "읍면동리":
        keys.add(v[:-1])
    return keys


def _code_filters(ctx: Context, question: str, already: set[str]) -> list[dict]:
    """질문에 열의 실제 값이 그대로 나오면 필터로 더한다(모델이 놓친 경우).

    분류 열은 값 하나만 나올 때만 더한다. "제주도민, 내국인, 외국인 중"처럼 여럿이면 거르기가 아니라 나눠 보기다.
    """
    q = pipeline.normalize_value(question)
    out = []
    for c in ctx.groups:
        if c["name"] in already:
            continue
        hits = [v for v in ctx.uniques.get(c["name"], []) if any(len(k) >= 2 and k in q for k in _keys(v, c["role"]))]
        if c["role"] != "region" and len(hits) != 1:
            continue
        if hits:
            out.append({"column": c["name"], "values": hits, "text": hits[0], "source": "code"})
    return out


def needs(ctx: Context, question: str) -> list[dict]:
    values = [v for vs in ctx.uniques.values() if len(vs) <= 200 for v in vs]
    haystack = " ".join([ctx.ds.title] + [f"{c['name']} {c['ko']}" for c in ctx.info["columns"]] + values).lower()
    months = ctx.info["months"]
    out, seen = [], set()
    for word, (table_id, clues) in TOPICS.items():
        if word in question and table_id not in seen and not any(clue.lower() in haystack for clue in clues):
            seen.add(table_id)
            out.append({
                "table_id": table_id,
                "title": dictionary.table(table_id).title,
                "reason": f"지금 자료에는 '{word}' 항목이 없어요",
                "period": f"{months.get('first', '')}~{months.get('last', '')}" if months else "",
            })
    return out[:2]


def plan(ds: pipeline.Dataset, question: str, model: str = llm.DEFAULT_MODEL, with_meaning: bool = True, timeout: float = 20) -> dict:
    ctx = context(ds)
    if not ctx.measures or not ctx.info["time_column"]:
        return {"fallback": True, "reason": "no_measure"}
    system = SYSTEM_RULES + "\n" + semantic_layer(ctx, with_meaning)
    messages = [{"role": "user", "content": f"질문: {question.strip()[:200]}"}]
    attempts, raw, result = 0, None, None
    total_ms, prompt_tokens = 0, 0
    try:
        for _ in range(2):
            attempts += 1
            result = llm.chat_json(system, messages, schema(ctx), model=model, timeout=timeout)
            total_ms += result.latency_ms
            prompt_tokens = result.prompt_tokens
            try:
                raw = json.loads(result.content)
                break
            except json.JSONDecodeError:
                messages = messages + [{"role": "assistant", "content": result.content[:200]}, {"role": "user", "content": "JSON 하나만 다시 보내 주세요."}]
    except llm.ModelUnavailable as err:
        reason = "timeout" if "timed out" in str(err).lower() else "model_unavailable"
        return {"fallback": True, "reason": reason, "detail": str(err)}
    if raw is None:
        return {"fallback": True, "reason": "parse_failed", "attempts": attempts}
    return finish(ctx, question, raw, model=model, attempts=attempts, latency_ms=total_ms, prompt_tokens=prompt_tokens)


def finish(ctx: Context, question: str, raw: dict, **meta) -> dict:
    """모델 출력(raw)을 검증하고 실행 가능한 계획으로 만든다. 브라우저가 고친 계획도 여기를 다시 거친다."""
    names = {c["name"] for c in ctx.measures}
    groups = {c["name"] for c in ctx.groups}
    value = raw.get("value") if raw.get("value") in names else None
    if value is None:
        value = next((c["name"] for c in ctx.measures if c["additive"]), ctx.measures[0]["name"])
    group_by = raw.get("group_by") if raw.get("group_by") in groups else None
    intent = intent_from_question(question, raw.get("intent"))
    # 나눠 보기는 구성비, 순위이거나 질문에 '~별'이 있을 때만. "여성 이용자수 흐름"의 성별은 거르기다.
    if intent not in {"share", "rank"} and not SPLIT_CUE.search(question):
        group_by = None

    resolved, unresolved = [], []
    for f in (raw.get("filters") or [])[:2]:
        column, text = f.get("column"), str(f.get("text", ""))
        if column not in groups:
            continue
        hits = _match(ctx, column, text)
        source = "model"
        if not hits:
            # 모델이 열을 잘못 골랐어도 같은 말이 다른 열 한 곳에만 있으면 그 열로 옮긴다.
            others = {g: m for g in groups if g != column and (m := _match(ctx, g, text))}
            if len(others) == 1:
                column, hits = next(iter(others.items()))
                source = "model_moved"
        entry = {"column": column, "text": text, "values": hits, "source": source}
        if not hits:
            entry["choices"] = ctx.uniques.get(column, [])[:50]
        (resolved if hits else unresolved).append(entry)
    # 같은 열에 같은 필터가 겹치면 하나로 합친다.
    merged: dict[str, dict] = {}
    for f in resolved:
        if f["column"] in merged:
            merged[f["column"]]["values"] = sorted(set(merged[f["column"]]["values"]) | set(f["values"]))
        else:
            merged[f["column"]] = f
    resolved = list(merged.values())
    resolved += _code_filters(ctx, question, {f["column"] for f in resolved + unresolved} | {group_by})
    # 거르는 열과 나눠 보는 열이 같으면 나눠 보기가 무의미하다.
    if group_by and any(f["column"] == group_by for f in resolved):
        group_by = None

    # 기간과 전망 개월은 질문 속 숫자에서 코드가 읽는다(모델은 '앞으로 6개월'을 '최근 6개월'로 자주 바꿨다).
    period_n = period_from_question(question)
    horizon = horizon_from_question(question, int(raw.get("forecast_months") or 0)) if intent == "forecast" else 6

    unsupported: list[str] = []
    for word, text in UNSUPPORTED_WORDS.items():
        if word in question and text not in unsupported:
            unsupported.append(text)

    blocked = []
    if unresolved:
        blocked.append("찾지 못한 값이 있어요. 값을 고르거나 거르지 않고 볼지 정해 주세요.")
    if intent in {"share", "rank"} and not group_by:
        blocked.append("무엇으로 나눠 볼지 골라 주세요.")
    return {
        "plan": {
            "intent": intent,
            "value": value,
            "group_by": group_by,
            "filters": [{"column": f["column"], "values": f["values"]} for f in resolved],
            "period_n": period_n,
            "horizon": horizon,
        },
        "resolved_filters": resolved,
        "unresolved": unresolved,
        "needs": needs(ctx, question),
        "unsupported": unsupported,
        "blocked": blocked,
        "labels": {c["name"]: c["ko"] for c in ctx.measures + ctx.groups},
        "raw": raw,
        **meta,
    }

