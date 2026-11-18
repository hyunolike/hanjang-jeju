"""예측 (요구사항 F01, F02, 기획안 13.6).

계절 단순 예측(같은 달 반복)을 기준선으로 두고, AutoETS와 AutoARIMA가 마지막 12개월 시험에서
기준선보다 나을 때만 쓴다. 결과는 값 하나가 아니라 80% 범위다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SEASON = 12
HOLDOUT = 12
MIN_LENGTH = 2 * SEASON
LEVEL = 80


class NotEnoughData(ValueError):
    pass


@dataclass
class Forecast:
    model: str
    baseline_mae: float
    model_mae: float
    horizon: int
    periods: list[str]
    mean: list[float]
    lower: list[float]
    upper: list[float]

    @property
    def improvement_pct(self) -> float:
        if self.baseline_mae == 0:
            return 0.0
        return round((1 - self.model_mae / self.baseline_mae) * 100, 1)

    def to_dict(self) -> dict:
        return {**vars(self), "improvement_pct": self.improvement_pct, "level": LEVEL}


def _models():
    # statsforecast는 읽어 들이는 데 오래 걸려(numba) 예측할 때만 불러온다. 엔진 시작이 빨라진다.
    from statsforecast.models import AutoARIMA, AutoETS, SeasonalNaive

    return [SeasonalNaive(season_length=SEASON), AutoETS(season_length=SEASON), AutoARIMA(season_length=SEASON)]


def _frame(series: pd.Series) -> pd.DataFrame:
    index = series.index.to_timestamp() if isinstance(series.index, pd.PeriodIndex) else pd.to_datetime(series.index)
    return pd.DataFrame({"unique_id": "s", "ds": index, "y": series.to_numpy(dtype=float)})


def forecast(series: pd.Series, horizon: int = 6) -> Forecast:
    """series: 월 단위(PeriodIndex 또는 날짜) 값. 결측 없이 이어져 있어야 한다."""
    series = series.sort_index()
    if series.isna().any():
        gaps = ", ".join(f"{pd.Period(p, freq='M').year}년 {pd.Period(p, freq='M').month}월" for p in series[series.isna()].index)
        raise NotEnoughData(f"비어 있는 달이 있어 예측하지 않아요: {gaps}. 빈 달을 채워 넣지 않아요.")
    if len(series) < MIN_LENGTH:
        raise NotEnoughData(f"계절을 보려면 {MIN_LENGTH}개월이 필요해요. 지금은 {len(series)}개월이에요.")
    horizon = int(min(horizon, SEASON, len(series) // 3))

    from statsforecast import StatsForecast

    train, test = series.iloc[:-HOLDOUT], series.iloc[-HOLDOUT:]
    if len(train) >= MIN_LENGTH:
        sf = StatsForecast(models=_models(), freq="MS", n_jobs=1)
        pred = sf.forecast(df=_frame(train), h=HOLDOUT)
        errors = {
            name: float(np.mean(np.abs(pred[name].to_numpy() - test.to_numpy())))
            for name in ("SeasonalNaive", "AutoETS", "AutoARIMA")
        }
    else:
        # 시험할 만큼 길지 않으면 기준선만 쓴다.
        errors = {"SeasonalNaive": float("nan")}
    baseline = errors["SeasonalNaive"]
    best = min(errors, key=lambda k: errors[k] if not np.isnan(errors[k]) else np.inf)
    if not (errors[best] < baseline):
        best = "SeasonalNaive"

    model = {m.__class__.__name__: m for m in _models()}[best]
    sf = StatsForecast(models=[model], freq="MS", n_jobs=1)
    out = sf.forecast(df=_frame(series), h=horizon, level=[LEVEL])
    periods = [str(pd.Period(ts, freq="M")) for ts in out["ds"]]
    return Forecast(
        model=best,
        baseline_mae=round(baseline, 3),
        model_mae=round(errors[best], 3),
        horizon=horizon,
        periods=periods,
        mean=[round(float(v), 3) for v in out[best]],
        lower=[round(float(v), 3) for v in out[f"{best}-lo-{LEVEL}"]],
        upper=[round(float(v), 3) for v in out[f"{best}-hi-{LEVEL}"]],
    )
