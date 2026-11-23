"""질문에 직접 답하는 사실 (설계 2판 2절 'intent와 답 함수').

모델이 고른 의도(compare, share, rank)마다 결정적으로 계산하고 사실 ID를 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .facts import Fact, FactStore
from .insights import ko_month


@dataclass
class Answer:
    intent: str
    title: str
    facts: list[Fact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"intent": self.intent, "title": self.title, "facts": [f.id for f in self.facts], "warnings": self.warnings}


def _periods(data: pd.DataFrame, time: str) -> pd.Series:
    return pd.PeriodIndex(data[time].astype(str), freq="M")


def _window(n: int, last: pd.Period) -> tuple[pd.Period, pd.Period]:
    return last - (n - 1), last


def _span(start: pd.Period, end: pd.Period) -> str:
    return f"{ko_month(start)}~{ko_month(end)}"


def compare(data: pd.DataFrame, time: str, value: str, store: FactStore, unit: str = "", n: int = 12) -> Answer:
    """최근 n개월 합과 그 전 n개월 합."""
    p = _periods(data, time)
    last = p.max()
    available = (last - p.min()).n + 1
    warnings = []
    if n * 2 > available:
        n = max(1, available // 2)
        warnings.append(f"자료가 {available}개월이라 {n}개월씩 비교했어요.")
    now_start, now_end = _window(n, last)
    before_end = now_start - 1
    before_start = before_end - (n - 1)
    now = data.loc[(p >= now_start) & (p <= now_end), value].sum(min_count=1)
    before = data.loc[(p >= before_start) & (p <= before_end), value].sum(min_count=1)
    if pd.isna(now) or pd.isna(before) or before == 0:
        return Answer("compare", "비교할 값이 비어 있어 답하지 못했어요", warnings=warnings)
    pct = (now / before - 1) * 100
    facts = [
        store.add("level", now, unit, f"{_span(now_start, now_end)} 합계", period=f"{now_start}~{now_end}"),
        store.add("level", before, unit, f"{_span(before_start, before_end)} 합계", period=f"{before_start}~{before_end}"),
        store.add("change_pct", round(pct, 1), "%", f"최근 {n}개월, 그 전 {n}개월 대비"),
    ]
    if pct == 0:
        title = f"최근 {n}개월은 그 전 {n}개월과 비교해 변화가 없어요"
    else:
        word = "늘었어요" if pct > 0 else "줄었어요"
        title = f"최근 {n}개월은 그 전 {n}개월보다 {abs(round(pct, 1))}% {word}"
    return Answer("compare", title, facts, warnings)


def _recent(data: pd.DataFrame, time: str, n: int) -> tuple[pd.DataFrame, str]:
    p = _periods(data, time)
    start, end = _window(n, p.max())
    return data[(p >= start) & (p <= end)], _span(start, end)


def share(data: pd.DataFrame, time: str, value: str, group: str, store: FactStore, n: int = 12, top: int = 5) -> Answer:
    recent, span = _recent(data, time, n)
    sums = recent.groupby(group)[value].sum(min_count=1).dropna()
    total = sums.sum()
    if sums.empty or total == 0:
        return Answer("share", "구성비를 계산할 값이 없어요")
    ranked = (sums / total * 100).sort_values(ascending=False).head(top)
    facts = [store.add("share_pct", round(v, 1), "%", f"{name} 비중 ({span})", category=str(name)) for name, v in ranked.items()]
    return Answer("share", f"{span} 동안 {ranked.index[0]}의 비중이 {round(ranked.iloc[0], 1)}%로 가장 커요", facts)


def rank(data: pd.DataFrame, time: str, value: str, group: str, store: FactStore, unit: str = "", n: int = 12, top: int = 5) -> Answer:
    recent, span = _recent(data, time, n)
    sums = recent.groupby(group)[value].sum(min_count=1).dropna().sort_values(ascending=False).head(top)
    if sums.empty:
        return Answer("rank", "순위를 매길 값이 없어요")
    facts = [store.add("level", v, unit, f"{i}위 {name} ({span})", category=str(name)) for i, (name, v) in enumerate(sums.items(), 1)]
    return Answer("rank", f"{span} 동안 가장 많은 곳은 {sums.index[0]}이에요", facts)
