"""선택한 두 자료의 월/동일 지역 체계별 비교. 부분합은 상관에서 제외한다."""
from __future__ import annotations

import math
import re

import pandas as pd

from . import aggregate, ingest
from .facts import FactStore

REGIONS = {
    'bjd_cd': 'bjd_code', 'bjd(code)': 'bjd_code', '법정동코드': 'bjd_code',
    'emd_cd': 'emd_code', '행정동코드': 'emd_code',
    'bjd_nm': 'bjd_name', '법정동명': 'bjd_name',
    'emd_nm': 'emd_name', '행정동명': 'emd_name',
}


def _region(values: pd.Series, family: str) -> pd.Series:
    if values.isna().any():
        raise ValueError('지역 값이 비어 있어요. 지역 기준이나 원본을 확인해 주세요.')
    text = values.map(lambda v: ingest.normalize_text(str(v)))
    if family.endswith('_code'):
        pattern = r'\d{8}(?:\d{2})?' if family == 'bjd_code' else r'\d{8}'
        if not text.map(lambda x: re.fullmatch(pattern, x) is not None).all():
            raise ValueError('지역 코드를 읽지 못했어요. 법정동은 8/10자리, 행정동은 8자리 코드가 필요해요.')
        return text.str[:8]
    # 도시 이름을 지우면 제주시와 서귀포시가 같은 키가 되므로 실제 정리 값만 쓴다.
    return text


def _filters(data: pd.DataFrame, columns: list[dict], filters) -> None:
    if not isinstance(filters, list):
        raise ValueError('비교 조건 형식을 확인해 주세요.')
    allowed = {c['name'] for c in columns if c['role'] in {'region', 'category'}}
    for f in filters:
        if not isinstance(f, dict) or f.get('column') not in allowed or not isinstance(f.get('values'), list) or not f['values'] or not all(isinstance(v, str) for v in f['values']):
            raise ValueError('비교 조건의 열과 실제 값을 다시 확인해 주세요.')
        if not set(f['values']) <= set(data[f['column']].dropna().astype(str)):
            raise ValueError('비교 조건에 자료에 없는 값이 있어요.')


def join(left, right, left_value: str, right_value: str, *, left_region: str | None = None,
         right_region: str | None = None, left_filters: list[dict] | None = None) -> dict:
    from . import pipeline

    if bool(left_region) != bool(right_region):
        raise ValueError('양쪽 지역 기준을 함께 골라 주세요.')
    family = REGIONS.get(left_region) if left_region else None
    if left_region and (family is None or family != REGIONS.get(right_region)):
        raise ValueError('같은 지역 체계의 열을 골라 주세요. 법정동과 행정동은 대응표 없이 결합하지 않아요.')
    frames, plan = [], {}
    keys = ['base_year_month', 'region'] if family else ['base_year_month']
    for side, ds, value, region in [('left', left, left_value, left_region), ('right', right, right_value, right_region)]:
        snapshot = pipeline.read_dataset(ds)
        info = pipeline.understand(ds, snapshot)
        chosen = next((c for c in info['columns'] if c['name'] == value and c['role'] == 'measure'), None)
        time = info['time_column']
        if not time or chosen is None:
            raise ValueError('결합할 날짜와 값 항목을 다시 골라 주세요.')
        if region and region not in snapshot.data.columns:
            raise ValueError('고른 지역 열이 자료에 없어요.')
        data = pipeline.checked_data(ds, time, chosen, snapshot)
        filters = (left_filters if left_filters is not None else []) if side == 'left' else []
        _filters(data, info['columns'], filters)
        data = pipeline.apply_filters(data, filters)
        if data.empty:
            raise ValueError('비교 조건에 맞는 행이 없어요.')
        status = snapshot.status.loc[data.index, value]
        work = pd.DataFrame({'base_year_month': data[time].map(aggregate.to_month),
                             f'{side}_value': data[value], f'{side}_valid_rows': data[value].notna().astype(int),
                             f'{side}_masked_rows': status.eq('masked').astype(int),
                             f'{side}_empty_rows': status.isin(['missing', 'none']).astype(int)})
        if family:
            work['region'] = _region(data[region], family)
        grouped = work.groupby(keys)
        frame = grouped[[f'{side}_value']].sum(min_count=1)
        for suffix in ['valid_rows', 'masked_rows', 'empty_rows']:
            frame[f'{side}_{suffix}'] = grouped[f'{side}_{suffix}'].sum()
        frame[f'{side}_partial'] = (frame[f'{side}_masked_rows'] + frame[f'{side}_empty_rows']).gt(0)
        frames.append(frame.reset_index())
        plan[side] = {**pipeline._ds_dict(ds), 'time': time, 'value': value, 'unit': chosen['unit'],
                      'region': region, 'filters': filters, 'used_rows': len(data),
                      'source_sha256': snapshot.source_sha256, 'source_bytes': snapshot.source_bytes}
    outer = frames[0].merge(frames[1], on=keys, how='outer', indicator=True)
    matched = outer['_merge'].eq('both')
    left_missing, right_missing = outer['_merge'].eq('left_only'), outer['_merge'].eq('right_only')
    def missing_keys(mask):
        rows = outer.loc[mask, keys].sort_values(keys).itertuples(index=False, name=None)
        return [r[0] if len(keys) == 1 else list(r) for r in rows]
    merged = outer.loc[~right_missing].drop(columns='_merge').sort_values(keys)
    report = {'left_rows': len(frames[0]), 'right_rows': len(frames[1]), 'matched_rows': int(matched.sum()),
              'unmatched_rows': int(left_missing.sum()), 'unmatched_keys': missing_keys(left_missing),
              'right_unmatched_rows': int(right_missing.sum()), 'right_unmatched_keys': missing_keys(right_missing),
              'multi_match_keys': [], 'key_columns': keys}
    groups, facts = [], {}
    store = FactStore()
    grouped_rows = merged.groupby('region', sort=True) if family else [('전체', merged)]
    for region, rows in grouped_rows:
        both = rows.loc[rows.left_value.notna() & rows.right_value.notna() & rows.left_partial.eq(False) & rows.right_partial.eq(False)]
        corr, refusal = None, None
        if len(both) < 3:
            refusal = '완전한 값으로 함께 비교할 월이 부족해요. 3개월 이상이 필요해요.'
        elif both.left_value.nunique() < 2 or both.right_value.nunique() < 2:
            refusal = '한 자료의 값이 일정해 상관계수를 계산하지 못했어요.'
        else:
            computed = float(both.left_value.corr(both.right_value))
            if math.isfinite(computed):
                corr = round(computed, 3)
            else:
                refusal = '자료의 값으로 상관계수를 계산하지 못했어요.'
        fact = store.add('correlation', corr if corr is not None else float('nan'), '', f'{region} 월별 상관계수', months=len(both))
        facts[fact.id] = {**fact.to_dict(), 'value': corr}
        groups.append({'region': region, 'months': len(both), 'correlation': corr, 'refusal': refusal, 'fact': fact.id})
    plan.update({'region_basis': '동일 법정동 체계: 10자리 코드는 앞 8자리 읍면동으로 맞춤' if family == 'bjd_code' else '동일 행정동 8자리 코드' if family == 'emd_code' else '같은 지역 이름의 정리 값 일치' if family else '월 전체 합계',
                 'aggregation': '양쪽 선택 값의 월별 관측 합계. 가림/빈값이 있는 부분합은 상관에서 제외.'})
    return {'left': pipeline._ds_dict(left), 'right': pipeline._ds_dict(right), 'plan': plan, 'report': report,
            'rows': merged.astype(object).where(pd.notna(merged), None).to_dict(orient='records'),
            'groups': groups, 'facts': facts,
            'correlation_refusal': '지역별로 따로 계산했어요. 전체를 섞은 상관은 제공하지 않아요.' if family else groups[0]['refusal'],
            'note': '상관은 함께 움직이는 정도일 뿐 원인을 뜻하지 않아요. 부분합은 관측된 값만의 합이에요.'}
