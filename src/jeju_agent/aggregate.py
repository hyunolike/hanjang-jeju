"""시간 단위 맞추기 (요구사항 J04).

일 자료(YYYYMMDD)를 월(YYYYMM)로 올린다. 합산 가능한 측정값은 합계로, 합산할 수 없는 측정값(평균,
비율, 시각마다 잰 인구)은 평균으로 올린다. 어떤 방법을 썼는지 돌려줘 처리 기록에 남긴다.
"""

from __future__ import annotations

import pandas as pd

from . import semantics


def to_month(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) < 6:
        raise ValueError(f"연월로 바꿀 수 없는 값이에요: {value}")
    return digits[:6]


def monthly(
    frame: pd.DataFrame,
    time_column: str,
    keys: list[str],
    measures: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """measures: {열 이름: 명세서 한글명}. 반환: (월 집계 표, {열: 'sum'|'mean'})."""
    data = frame.copy()
    data["base_year_month"] = data[time_column].map(to_month)
    methods = {}
    for column, ko in measures.items():
        data[column] = pd.to_numeric(data[column], errors="coerce")
        additive = semantics.infer(column, ko).additive
        methods[column] = "sum" if additive else "mean"
    grouped = data.groupby(["base_year_month", *keys], dropna=False)
    out = grouped.agg({c: m for c, m in methods.items()}).reset_index()
    # 값이 하나도 없는 달은 합계가 0으로 바뀌지 않게 결측으로 둔다.
    counts = grouped[list(measures)].count().reset_index(drop=True)
    for column in measures:
        out.loc[counts[column].to_numpy() == 0, column] = float("nan")
    return out, methods
