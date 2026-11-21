"""화면이 부르는 분석 흐름: 넣기 → 이해 → 분석 → 결합.

계산은 모두 이 모듈 아래 함수들이 한다. 결과는 JSON으로 바로 내보낼 수 있는 dict다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import aggregate, answers, dictionary, forecast, ingest, insights, paths, regions, semantics
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
        out.append(Dataset(f"upload-{path.stem}", path.name, "upload", path))
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


def understand(ds: Dataset) -> dict:
    result = read_dataset(ds)
    recog = dictionary.recognize(list(result.data.columns))
    spec_columns = {c["name"]: c for c in (recog.table.columns if recog.table else ())}
    columns = []
    for name in result.data.columns:
        ko = spec_columns.get(name, {}).get("ko", "")
        sem = semantics.infer(name, ko)
        if ds.selection:
            role = next((role for key, role in (("time", "time"), ("value", "measure"), ("category", "category")) if ds.selection.get(key) == name), "unknown")
            sem = semantics.Semantic(role, ds.selection.get("unit", "") if role == "measure" else "", True if role == "measure" else None)
        columns.append({"name": name, "ko": ko or name, **vars(sem), **vars(result.columns[name])})
    time = next((c["name"] for c in columns if c["role"] == "time" and c["name"] not in {"pt_year", "pt_month"}), None)
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
        "preview": result.data.head(5).fillna("").to_dict(orient="records"),
    }


GROUP_ROLES = {"category", "region"}


def normalize_value(value: str) -> str:
    return regions.normalize_region_name(ingest.normalize_text(str(value)))


def apply_filters(data: pd.DataFrame, filters: list[dict] | None) -> pd.DataFrame:
    """filters: [{"column": 열, "values": [실제 값...]}]. 열끼리 AND, 값끼리 OR."""
    for f in filters or []:
        wanted = {normalize_value(v) for v in f["values"]}
        data = data[data[f["column"]].map(lambda x: normalize_value(x) in wanted)]
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
) -> dict:
    info = understand(ds)
    time = info["time_column"]
    measures = [c for c in info["columns"] if c["role"] == "measure"]
    if not time or not measures:
        return {"dataset": info["dataset"], "error": "시간 열이나 값 열을 찾지 못했어요. 열의 뜻을 직접 골라 주세요."}
    chosen = next((c for c in measures if c["name"] == value), None) or next((c for c in measures if c["additive"]), measures[0])
    categories = [c["name"] for c in info["columns"] if c["role"] in GROUP_ROLES and c["name"] != time]
    if category not in categories:
        category = None
    for f in filters or []:
        if f.get("column") not in categories:
            return {"dataset": info["dataset"], "error": f"'{f.get('column')}' 열로는 거를 수 없어요."}

    if not info["months"]:
        return {
            "dataset": info["dataset"],
            "error": "월 단위 시간 열이 없어 흐름을 볼 수 없어요. 연 단위 자료는 다른 자료에 붙여 비교하는 데 써 주세요.",
        }
    data = apply_filters(read_dataset(ds).data, filters).copy()
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
    if run_forecast:
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
    }


def join_monthly(left: Dataset, left_value: str, right: Dataset, right_value: str) -> dict:
    """두 자료를 월 합계로 맞춰 결합하고 커버리지를 보고한다."""
    frames = []
    for ds, value in ((left, left_value), (right, right_value)):
        info = understand(ds)
        data = read_dataset(ds).data
        data[value] = pd.to_numeric(data[value], errors="coerce")
        data["base_year_month"] = data[info["time_column"]].map(aggregate.to_month)
        frames.append(data.groupby("base_year_month", as_index=False)[value].sum(min_count=1))
    merged, report = regions.join_with_report(frames[0], frames[1], ["base_year_month"])
    store = FactStore()
    both = merged.dropna(subset=[left_value, right_value])
    corr = both[left_value].corr(both[right_value]) if len(both) > 2 else float("nan")
    fact = store.add("correlation", round(float(corr), 3), "", "월별 상관계수", months=len(both))
    return {
        "left": _ds_dict(left),
        "right": _ds_dict(right),
        "report": report.to_dict(),
        "rows": merged.fillna("").to_dict(orient="records"),
        "facts": {fact.id: fact.to_dict()},
        "note": "상관은 함께 움직이는 정도일 뿐 원인을 뜻하지 않아요.",
    }


def _ds_dict(ds: Dataset) -> dict:
    return {"id": ds.id, "title": ds.title, "source": ds.source, "provider": ds.provider, "period": ds.period}
