"""공개 입력의 분석 후보. 전체 행을 검사하고 원본 값 없이 결과만 반환한다."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import pipeline, web_input


def describe(ds: pipeline.Dataset) -> dict:
    clean = pipeline.read_dataset(ds)
    data = clean.data
    rows = clean.source_rows or list(range(2, len(data) + 2))
    info = pipeline.understand(ds)
    columns = []
    for column in info["columns"]:
        name = column["name"]
        sem = web_input.value_semantic(name, column["ko"])
        values = [str(v) if pd.notna(v) else "" for v in data[name]]
        cache = {value: web_input.parse_month(value) for value in set(values)}
        months = [cache[v] for v in values]
        invalid_dates = [row for row, month in zip(rows, months) if month is None]
        date_allowed = sem.role not in {"measure", "region", "category"}
        year_only = sem.role == "time" and all(re.fullmatch(r"[1-9][0-9]{3}", v) for v in values)
        date_status = "not_date"
        first = last = None
        month_count = 0
        if date_allowed and not invalid_dates:
            first, last = min(months), max(months)
            month_count = (int(last[:4]) - int(first[:4])) * 12 + int(last[4:]) - int(first[4:]) + 1
            date_status = "valid" if month_count <= 1200 else "too_long"
            first, last = f"{first[:4]}-{first[4:]}", f"{last[:4]}-{last[4:]}"
        elif year_only:
            date_status = "year_only"
        elif date_allowed and (sem.role == "time" or any(months)):
            date_status = "invalid"
        numeric = pd.to_numeric(data[name], errors="coerce")
        invalid_numbers = [row for row, old, new in zip(rows, data[name], numeric) if pd.notna(old) and not np.isfinite(new)]
        numeric_status = "invalid" if invalid_numbers else "valid" if numeric.notna().any() else "empty"
        columns.append({"name": name, "date_status": date_status, "first": first, "last": last, "month_count": month_count, "invalid_date_rows": invalid_dates[:3] if date_status == "invalid" else [], "numeric_status": numeric_status, "invalid_numeric_rows": invalid_numbers[:3], "role": sem.role, "unit": sem.unit, "additive": sem.additive})
    times = [c["name"] for c in columns if c["date_status"] == "valid"]
    values = [c["name"] for c in columns if c["numeric_status"] == "valid" and c["date_status"] != "year_only" and c["role"] not in {"time", "region", "category"} and c["additive"] is not False]
    groups = [c["name"] for c in columns if c["role"] in {"category", "region"} or (c["role"] == "unknown" and c["date_status"] == "not_date" and c["numeric_status"] != "valid")]
    preferred_time = next((c["name"] for c in columns if c["name"] in times and c["role"] == "time"), None)
    preferred_value = next((c["name"] for c in columns if c["name"] in values and c["additive"] is True), None)
    date_status = "ready" if times else "year_only" if any(c["date_status"] == "year_only" for c in columns) else "invalid" if any(c["date_status"] in {"invalid", "too_long"} for c in columns) else "missing"
    analysis_status = "no_dates" if not times else "available" if any(time != value for time in times for value in values) else "no_values"
    return {"columns": columns, "time_candidates": times, "value_candidates": values, "category_candidates": groups, "recommended": {"time": preferred_time, "value": preferred_value}, "date_status": date_status, "analysis_status": analysis_status}
