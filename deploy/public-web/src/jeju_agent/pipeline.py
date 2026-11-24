"""화면이 부르는 분석 흐름: 넣기 → 이해 → 분석 → 결합.

계산은 모두 이 모듈 아래 함수들이 한다. 결과는 JSON으로 바로 내보낼 수 있는 dict다.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import aggregate, answers, dictionary, forecast, ingest, insights, paths, processing, regions, semantics
from .facts import FactStore

ROOT = paths.ROOT
HUB = paths.HUB
DUMMY = paths.DUMMY
WORKSPACE = paths.WORKSPACE


@dataclass(frozen=True)
class Dataset:
    id: str
    title: str
    source: str  # hub | dummy | upload
    path: Path
    provider: str = ""
    period: str = ""
    data: ingest.CleanResult | None = None
    selection: dict | None = None


def read_dataset(ds: Dataset) -> ingest.CleanResult:
    return ds.data if ds.data is not None else ingest.load(ds.path)


def datasets() -> list[Dataset]:
    out: list[Dataset] = []
    manifest_path = HUB / "manifest.json"  # 공개 배포판에는 허브 원본이 없다
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"files": []}
    for f in manifest["files"]:
        out.append(Dataset(f"hub-{f['hub_id']}", f["title"], "hub", HUB / f["file"], f["provider"], f["period"]))
    for path in sorted(DUMMY.glob("*.csv")):
        out.append(Dataset(path.stem, _dummy_title(path), "dummy", path, "더미 (공개 명세서 기준)", ""))
    for path in sorted(WORKSPACE.glob("*.csv")):
        try:
            meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        out.append(Dataset(f"upload-{path.stem}", meta.get("title", path.name), "upload", path, selection=meta.get("selection")))
    return out


def _dummy_title(path: Path) -> str:
    table_id = path.stem.split("-dummy")[0].replace("center-", "")
    try:
        return f"{dictionary.table(table_id).title} (더미)"
    except StopIteration:
        return path.name


def find(dataset_id: str) -> Dataset:
    for ds in datasets():
        if ds.id == dataset_id:
            return ds
    raise KeyError(dataset_id)


def understand(ds: Dataset, result: ingest.CleanResult | None = None) -> dict:
    result = result if result is not None else read_dataset(ds)
    recog = dictionary.recognize(list(result.data.columns))
    spec_columns = {c["name"]: c for c in (recog.table.columns if recog.table else ())}
    columns = []
    for name in result.data.columns:
        ko = spec_columns.get(name, {}).get("ko", "")
        sem = semantics.value_semantic(name, ko)
        if ds.selection:
            role = next((role for key, role in (("time", "time"), ("value", "measure"), ("category", "category")) if ds.selection.get(key) == name), sem.role if ds.data is None else "unknown")
            if name == ds.selection.get("value"):
                sem = semantics.Semantic(role, ds.selection.get("unit", ""), sem.additive if sem.additive is False else True, sem.note)
            elif role != sem.role:
                sem = semantics.Semantic(role)
        columns.append({"name": name, "ko": ko or name, **vars(sem), **vars(result.columns[name])})
    time = ds.selection.get("time") if ds.selection else next((c["name"] for c in columns if c["role"] == "time" and c["name"] not in {"pt_year", "pt_month"}), None)
    months: dict = {}
    if time:
        try:
            periods = pd.PeriodIndex(result.data[time].dropna().map(aggregate.to_month), freq="M")
            full = pd.period_range(periods.min(), periods.max(), freq="M")
            months = {
                "first": str(periods.min()),
                "last": str(periods.max()),
                "count": len(full),
                "missing": [str(p) for p in sorted(set(full) - set(periods))],
            }
        except ValueError:
            months = {}
    return {
        "dataset": _ds_dict(ds),
        "recognition": recog.to_dict(),
        "clean": result.report(),
        "columns": columns,
        "time_column": time,
        "months": months,
        "preview": result.data.head(5).astype(object).fillna("").to_dict(orient="records"),
    }


GROUP_ROLES = {"category", "region"}


def normalize_value(value: str) -> str:
    return regions.normalize_region_name(ingest.normalize_text(str(value)))


def apply_filters(data: pd.DataFrame, filters: list[dict] | None) -> pd.DataFrame:
    """filters: [{"column": 열, "values": [실제 값...]}]. 열끼리 AND, 값끼리 OR."""
    for f in filters or []:
        wanted = {ingest.normalize_text(str(v)) for v in f["values"]}
        data = data[data[f["column"]].map(lambda x: pd.notna(x) and ingest.normalize_text(str(x)) in wanted)]
    return data


def checked_data(ds: Dataset, time: str, chosen: dict, result: ingest.CleanResult | None = None) -> pd.DataFrame:
    """Check the full original rows before filtering or aggregating."""
    if chosen["additive"] is not True:
        raise ValueError(f"‘{chosen['ko']}’은 합계를 낼 수 없어요. 평균·비율·인구는 더하지 않고, 다른 금액이나 수량을 골라 주세요.")
    result = result if result is not None else read_dataset(ds)
    data = result.data.copy()
    rows = result.source_rows or list(range(2, len(data) + 2))
    for row, raw in zip(rows, data[time]):
        if aggregate.parse_month(str(raw)) is None:
            raise ValueError(f"‘{time}’의 {row}행을 날짜로 읽지 못했어요. CSV의 날짜를 확인해 주세요.")
    numeric = pd.to_numeric(data[chosen["name"]], errors="coerce")
    for row, original, value in zip(rows, data[chosen["name"]], numeric):
        if pd.notna(original) and not math.isfinite(float(value)):
            raise ValueError(f"‘{chosen['ko']}’의 {row}행을 숫자로 읽지 못했어요. CSV의 해당 값을 확인해 주세요.")
    data[chosen["name"]] = numeric
    return data


def analyze(
    ds: Dataset,
    value: str | None = None,
    category: str | None = None,
    horizon: int = 6,
    filters: list[dict] | None = None,
    intent: str | None = None,
    period_n: int | None = None,
    run_forecast: bool = True,
    include_processing: bool = False,
) -> dict:
    result = read_dataset(ds)
    info = understand(ds, result)
    time = info["time_column"]
    measures = [c for c in info["columns"] if c["role"] == "measure"]
    if not time or not measures:
        return {"dataset": info["dataset"], "error": "시간 열이나 값 열을 찾지 못했어요. 열의 뜻을 직접 골라 주세요."}
    value = value or (ds.selection or {}).get("value")
    chosen = next((c for c in measures if c["name"] == value), None) or next((c for c in measures if c["additive"]), measures[0])
    if category is None and ds.selection:
        category = ds.selection.get("category")
    categories = [c["name"] for c in info["columns"] if c["role"] in GROUP_ROLES and c["name"] != time]
    if category not in categories:
        category = None
    for f in filters or []:
        if f.get("column") not in categories:
            return {"dataset": info["dataset"], "error": f"'{f.get('column')}' 열로는 거를 수 없어요."}

    dates = result.data[time].dropna().astype(str)
    if not info["months"] and not dates.empty and dates.str.fullmatch(r"[1-9][0-9]{3}").all():
        return {"dataset": info["dataset"], "error": "월 단위 시간 열이 없어 흐름을 볼 수 없어요. 연도와 월이 함께 있는 자료를 넣어 주세요."}
    try:
        validated = checked_data(ds, time, chosen, result)
    except ValueError as err:
        return {"dataset": info["dataset"], "error": str(err)}
    if not info["months"]:
        return {
            "dataset": info["dataset"],
            "error": "월 단위 시간 열이 없어 흐름을 볼 수 없어요. 연 단위 자료는 다른 자료에 붙여 비교하는 데 써 주세요.",
        }
    data = apply_filters(validated, filters).copy()
    if data.empty:
        return {"dataset": info["dataset"], "error": "고른 조건에 맞는 행이 없어요. 거르는 값을 다시 골라 주세요."}
    # 사용자 열 이름이 _ym/_p 등 내부 보조 열과 같아도 원본을 덮지 않는다.
    working = pd.DataFrame({"__jeju_month": data[time].map(aggregate.to_month), "__jeju_value": pd.to_numeric(data[chosen["name"]], errors="coerce")})
    if category:
        working["__jeju_group"] = data[category]
    unit = chosen["unit"]
    group = "__jeju_group" if category else None
    cards, store = insights.cards(working, "__jeju_month", "__jeju_value", group, unit)
    answer = None
    n = int(period_n) if period_n else 12
    if intent == "compare":
        answer = answers.compare(working, "__jeju_month", "__jeju_value", store, unit, n)
    elif intent in {"share", "rank"} and category:
        fn = answers.share if intent == "share" else answers.rank
        kwargs = {"n": n} if intent == "share" else {"unit": unit, "n": n}
        answer = fn(working, "__jeju_month", "__jeju_value", group, store, **kwargs)
    series = insights.total_series(working, "__jeju_month", "__jeju_value")
    fc, refusal = None, "예측 도구를 선택하지 않았어요."
    completeness = processing.monthly_quality(result, data, time, chosen['name'])
    partial = any(x['partial'] and x['valid_rows'] > 0 for x in completeness)
    if run_forecast and partial:
        refusal = "가림이나 빈값이 섞인 달은 관측 부분합이에요. 전체 합계를 확인하기 전에는 예측하지 않아요."
    elif run_forecast:
        try:
            fc = forecast.forecast(series, horizon).to_dict()
            fc_fact = store.add("forecast_mean", fc["mean"][0], unit, f"{insights.ko_month(fc['periods'][0])} 추정 중앙값", period=fc["periods"][0])
            fc["fact"] = fc_fact.id
            refusal = None
        except forecast.NotEnoughData as err:
            fc, refusal = None, str(err)
    return {
        "dataset": info["dataset"],
        "value": {k: chosen[k] for k in ("name", "ko", "unit", "additive", "note")},
        "category": category,
        "options": {"values": [c["name"] for c in measures], "categories": categories},
        "labels": {c["name"]: c["ko"] for c in info["columns"]},
        "series": [{"period": str(p), "value": None if pd.isna(v) else float(v)} for p, v in series.items()],
        "cards": [c.to_dict() for c in cards],
        "facts": {f.id: f.to_dict() for f in store.all()},
        "forecast": fc,
        "forecast_refusal": refusal,
        "missing_months": insights.missing_months(series),
        "filters": filters or [],
        "answer": answer.to_dict() if answer else None,
        **({'processing': processing.record(result, data, time=time, chosen=chosen, category=category, filters=filters, forecast_requested=run_forecast)} if include_processing else {}),
    }


def join_monthly(left: Dataset, left_value: str, right: Dataset, right_value: str, *,
                 left_region: str | None = None, right_region: str | None = None,
                 left_filters: list[dict] | None = None) -> dict:
    """두 자료의 선택 값과 월/지역 기준을 확인해 비교한다."""
    from . import comparison
    return comparison.join(left, right, left_value, right_value,
                           left_region=left_region, right_region=right_region, left_filters=left_filters)


def _ds_dict(ds: Dataset) -> dict:
    return {"id": ds.id, "title": ds.title, "source": ds.source, "provider": ds.provider, "period": ds.period}
