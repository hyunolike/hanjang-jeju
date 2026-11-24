"""계산에 쓴 snapshot의 출처와 완전성. 원본 셀이나 경로는 내보내지 않는다."""
from __future__ import annotations

import tomllib

import pandas as pd

from . import aggregate, ingest, paths


def version() -> str:
    try:
        return tomllib.loads((paths.ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    except (OSError, KeyError, ValueError):
        return '확인 불가'


def monthly_quality(result: ingest.CleanResult, data: pd.DataFrame, time: str, value: str) -> list[dict]:
    status = result.status.loc[data.index, value]
    work = pd.DataFrame({'period': data[time].map(aggregate.to_month).astype(str),
                         'valid_rows': data[value].notna().astype(int),
                         'masked_rows': status.eq('masked').astype(int),
                         'empty_rows': status.isin(['missing', 'none']).astype(int)})
    counts = work.groupby('period', as_index=False).sum()
    counts['partial'] = (counts.masked_rows + counts.empty_rows).gt(0)
    return counts.to_dict(orient='records')


def record(result: ingest.CleanResult, data: pd.DataFrame, *, time: str, chosen: dict,
           category: str | None, filters: list[dict] | None, forecast_requested: bool) -> dict:
    status = result.status.loc[data.index, chosen['name']]
    return {
        'source_sha256': result.source_sha256, 'source_bytes': result.source_bytes, 'version': version(),
        'time': time, 'value': chosen['name'], 'category': category, 'unit': chosen['unit'], 'filters': filters or [],
        'input_rows': len(result.data) + len(result.subtotals), 'clean_rows': len(result.data),
        'used_rows': len(data), 'subtotal_rows': len(result.subtotals),
        'masked_cells': int(status.eq('masked').sum()), 'empty_cells': int(status.isin(['missing', 'none']).sum()),
        'aggregation': '선택한 행의 월별 관측값 합계',
        'missing_policy': '빈값·값 없음·가림은 0으로 채우지 않음. 일부 값이 없는 달은 관측 부분합이며 예측하지 않음.',
        'forecast_requested': forecast_requested,
        'monthly_quality': monthly_quality(result, data, time, chosen['name']),
    }
