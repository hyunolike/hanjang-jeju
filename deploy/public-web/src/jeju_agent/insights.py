"""자동 분석 카드 (요구사항 A01, A02, 기획안 13.5).

묻기 전에 눈여겨볼 점을 찾는다. 계산은 모두 여기서 하고, 카드의 숫자는 사실 저장소에 남긴다.
모델은 카드 문장을 다듬을 뿐 숫자를 만들지 않는다.

입력은 월 단위 긴 표: 연월(YYYYMM), 분류(선택), 값.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .facts import Fact, FactStore


@dataclass
class Card:
    kind: str
    title: str
    score: float
    facts: list[Fact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "score": round(self.score, 3),
            "facts": [f.id for f in self.facts],
            "warnings": self.warnings,
        }


def ko_month(period) -> str:
    p = pd.Period(period, freq="M")
    return f"{p.year}년 {p.month}월"


def _period_index(frame: pd.DataFrame, time: str) -> pd.Series:
    return pd.PeriodIndex(frame[time].astype(str), freq="M")


def total_series(frame: pd.DataFrame, time: str, value: str) -> pd.Series:
    data = frame.assign(_p=_period_index(frame, time))
    series = data.groupby("_p")[value].sum(min_count=1).sort_index()
    # 빠진 달을 건너뛰지 않도록 연속된 월 범위로 펼친다. 빈 달은 결측으로 남긴다.
    full = pd.period_range(series.index.min(), series.index.max(), freq="M")
    return series.reindex(full)


def missing_months(series: pd.Series) -> list[str]:
    return [str(p) for p in series[series.isna()].index]


def year_over_year(frame, time, value, store: FactStore, unit="") -> Card | None:
    series = total_series(frame, time, value).dropna()
    if len(series) < 13:
        return None
    last = series.index.max()
    prev = last - 12
    if prev not in series.index or series[prev] == 0:
        return None
    change = (series[last] / series[prev] - 1) * 100
    now = store.add("level", series[last], unit, f"{ko_month(last)} 합계", period=str(last))
    before = store.add("level", series[prev], unit, f"{ko_month(prev)} 합계", period=str(prev))
    pct = store.add("change_pct", round(change, 1), "%", "전년 같은 달 대비", period=f"{prev}->{last}")
    direction = "늘었어요" if change > 0 else "줄었어요"
    return Card("change", f"{ko_month(last)}은 전년 같은 달보다 {abs(round(change, 1))}% {direction}", abs(change) / 10, [now, before, pct])


def contributors(frame, time, category, value, store: FactStore, unit="", top=3) -> Card | None:
    """전년 같은 달 대비 전체 증감에서 분류별 기여도."""
    data = frame.assign(_p=_period_index(frame, time))
    last = data["_p"].max()
    prev = last - 12
    pivot = data[data["_p"].isin([last, prev])].pivot_table(
        index=category, columns="_p", values=value, aggfunc="sum"
    )
    if prev not in pivot.columns or last not in pivot.columns:
        return None
    diff = (pivot[last] - pivot[prev]).dropna()
    total = diff.sum()
    if total == 0 or diff.empty:
        return None
    ranked = diff.reindex(diff.abs().sort_values(ascending=False).index).head(top)
    facts = [
        store.add("contribution", float(v), unit, f"{name} 증감", category=str(name), period=f"{prev}->{last}")
        for name, v in ranked.items()
    ]
    share = abs(ranked.iloc[0]) / diff.abs().sum() * 100
    facts.append(store.add("share_pct", round(share, 1), "%", "가장 큰 기여 항목의 비중"))
    return Card("driver", f"변화를 가장 크게 이끈 항목은 {ranked.index[0]}이에요", share / 20, facts)


def anomalies(frame, time, value, store: FactStore, unit="", threshold=3.5) -> list[Card]:
    """평소 범위를 벗어난 달을 찾는다.

    같은 달의 전년 대비 비율(로그)을 계열 전체의 중앙값과 MAD로 견준다. 계절과 추세를 함께 지우고
    최근 달까지 판정할 수 있다. 한 달이 튀면 그 달과 1년 뒤 같은 달이 반대 방향으로 함께 걸리므로
    앞의 달만 남긴다.
    """
    series = total_series(frame, time, value)
    if series.dropna().size < 24:
        return []
    log_ratio = np.log(series / series.shift(12)).dropna()
    med = log_ratio.median()
    mad = max((log_ratio - med).abs().median(), 0.01)
    z = 0.6745 * (log_ratio - med) / mad
    flagged = z[abs(z) > threshold]
    keep = {
        p: score for p, score in flagged.items()
        if not ((p - 12) in flagged.index and np.sign(flagged[p - 12]) != np.sign(score))
    }
    cards = []
    last = series.dropna().index.max()
    for period, score in keep.items():
        recency = 1.0 if (last - period).n <= 24 else 0.5
        fact = store.add("level", series[period], unit, f"{ko_month(period)} 값", period=str(period))
        ratio = store.add(
            "ratio", round(float(series[period] / series[period - 12]), 3), "배",
            "전년 같은 달 대비", period=str(period),
        )
        word = "늘었어요" if score > 0 else "줄었어요"
        times = round(float(series[period] / series[period - 12]), 2)
        cards.append(Card(
            "anomaly",
            f"{ko_month(period)}은 전년 같은 달보다 {times}배로, 평소보다 유난히 크게 {word}",
            min(abs(score) / 3, 5) * recency, [fact, ratio],
            warnings=["전년 같은 달이 평소와 달랐을 수도 있어요. 두 해를 함께 보세요"],
        ))
    return cards


def seasonality(frame, time, value, store: FactStore) -> Card | None:
    series = total_series(frame, time, value).dropna()
    if len(series) < 24:
        return None
    detrended = series / series.rolling(12, center=True, min_periods=6).mean()
    detrended = detrended.replace([np.inf, -np.inf], np.nan).dropna()
    if len(detrended) < 12:
        return None
    by_month = detrended.groupby(detrended.index.month).mean()
    strength = float(by_month.std() / max(detrended.std(), 1e-9))
    peak, low = int(by_month.idxmax()), int(by_month.idxmin())
    gap = float((by_month.max() - by_month.min()) * 100)
    facts = [
        store.add("month", peak, "월", "가장 높은 달"),
        store.add("month", low, "월", "가장 낮은 달"),
        store.add("gap_pct", round(gap, 1), "%p", "최고 달과 최저 달의 차이(추세 제거 후)"),
    ]
    return Card("season", f"매년 {peak}월이 가장 높고 {low}월이 가장 낮아요", strength * 2, facts)


def cards(frame: pd.DataFrame, time: str, value: str, category: str | None = None, unit: str = "", limit: int = 5) -> tuple[list[Card], FactStore]:
    store = FactStore()
    found: list[Card] = []
    card = year_over_year(frame, time, value, store, unit)
    if card:
        found.append(card)
    if category:
        card = contributors(frame, time, category, value, store, unit)
        if card:
            found.append(card)
    found += anomalies(frame, time, value, store, unit)
    card = seasonality(frame, time, value, store)
    if card:
        found.append(card)
    # 대표 문장은 최근 변화와 계절처럼 지금 쓸 수 있는 발견을 먼저 둔다.
    priority = {"change": 3, "season": 2, "driver": 1, "anomaly": 0}
    found.sort(key=lambda c: (-priority[c.kind], -c.score))
    return found[:limit], store


