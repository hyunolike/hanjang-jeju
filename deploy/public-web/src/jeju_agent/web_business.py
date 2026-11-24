"""공개 웹의 검토 가능한 업무 절차. 모델/파일 저장 없이 계산 사실로 설명한다."""
from __future__ import annotations

import math

import pandas as pd
from fastapi import HTTPException

from . import aggregate, pipeline, processing, web_input
from .facts import FactStore

TASKS = {'quarter_compare': '전년 같은 분기와 비교', 'category_change': '분류별 증감', 'brief': '보고용 정리'}
OBSERVATION_LIMIT = '업로드된 기록의 합계예요. 월이 존재해도 월 전체의 영업일이나 모집단이 수집됐음을 보증하지 않아요. 관측된 증감은 원인을 설명하지 않아요.'


def _statements(b: dict, facts: dict) -> list[dict]:
    if b['status'] == 'blocked':
        return []
    ids = b['metric_facts']
    t = b['totals']
    now, before = b['periods']['current'], b['periods']['baseline']
    unit = b['criteria']['unit']
    value = b['criteria']['value']
    rows = [{'text': f"{now[0]}~{now[-1]} {value} 합계는 {t['current']:,.1f}{unit}, {before[0]}~{before[-1]} 합계는 {t['baseline']:,.1f}{unit}예요.", 'facts': [ids['current'], ids['baseline']]}]
    direction = '증가' if t['delta'] > 0 else '감소' if t['delta'] < 0 else '변화 없음'
    text = f"전년 같은 분기 대비 증감은 {t['delta']:,.1f}{unit}({direction})이에요."
    refs = [ids['delta']]
    if t['change_pct'] is not None:
        text += f" 증감률은 {t['change_pct']:,.1f}%예요."
        refs.append(ids['change_pct'])
    rows.append({'text': text, 'facts': refs})
    for g in b['groups']:
        rows.append({'text': f"{g['label']}의 전년 같은 분기 대비 증감은 {g['delta']:,.1f}{unit}예요.", 'facts': g['facts']})
    return rows


def _total(values) -> float:
    try:
        value = math.fsum(float(x) for x in values)
        if not math.isfinite(value):
            raise OverflowError
        return value
    except OverflowError:
        web_input.reject('합계가 계산 가능한 숫자 범위를 벗어났어요. 값의 단위를 조정한 CSV를 넣어 주세요.')


def analyze(ds: pipeline.Dataset, spec: web_input.ExecutionSpec) -> dict:
    if not spec.business_task:
        web_input.reject('업무 분석 종류를 골라 주세요.')
    clean = pipeline.read_dataset(ds)
    info = pipeline.understand(ds, clean)
    chosen = next(c for c in info['columns'] if c['name'] == spec.value)
    validated = pipeline.checked_data(ds, spec.time, chosen, clean)
    validated[spec.value] = validated[spec.value].astype(float)
    periods = validated[spec.time].map(aggregate.to_month).map(lambda x: pd.Period(x, freq='M'))
    last = periods.max()
    start = pd.Period(year=last.year, month=((last.month - 1) // 3) * 3 + 1, freq='M')
    current = [str(start + i) for i in range(3)]
    baseline = [str(start - 12 + i) for i in range(3)]
    data = pipeline.apply_filters(validated, [f.model_dump() for f in spec.filters])
    work = pd.DataFrame({'month': periods.loc[data.index].astype(str), 'value': data[spec.value]})
    if spec.category:
        work['group'] = data[spec.category]
    quality = processing.monthly_quality(clean, data, spec.time, spec.value)
    quality_by_month = {str(pd.Period(x['period'], freq='M')): x for x in quality}
    sums = work.groupby('month').value.sum(min_count=1)
    if any(not math.isfinite(float(v)) for v in sums.dropna()):
        web_input.reject('월 합계가 계산 가능한 숫자 범위를 벗어났어요.')
    all_months = pd.period_range(periods.min(), last, freq='M')
    series = [{'period': str(m), 'value': None if str(m) not in sums or quality_by_month[str(m)]['partial'] or pd.isna(sums[str(m)]) else float(sums[str(m)])} for m in all_months]
    b = {'task': spec.business_task, 'status': 'complete', 'periods': {'current': current, 'baseline': baseline},
         'criteria': {key: getattr(spec, key) for key in ('time', 'value', 'category', 'unit')},
         'limitations': [], 'steps': [], 'groups': [], 'totals': {}, 'metric_facts': {}, 'statements': []}
    b['criteria']['filters'] = [f.model_dump() for f in spec.filters]

    def limit(code, message):
        b['limitations'].append({'code': code, 'message': message})

    needed = set(current + baseline)
    missing = sorted(needed - set(work.month))
    if missing:
        limit('missing_months', f"비교에 필요한 달이 없어요: {', '.join(missing)}. 해당 기간을 포함한 CSV를 넣어 주세요.")
    relevant = work[work.month.isin(needed)]
    statuses = clean.status.loc[relevant.index, spec.value]
    if statuses.eq('masked').any():
        limit('masked_values', '비교 기간에 가림값이 있어 전체 합계를 확정하지 않아요.')
    if statuses.isin(['missing', 'none']).any():
        limit('empty_values', '비교 기간에 빈값이나 값 없음이 있어 전체 합계를 확정하지 않아요.')
    if relevant.value.isna().any() and not b['limitations']:
        limit('empty_values', '비교 기간의 값을 확인해 주세요.')
    store = FactStore()
    basis = {'periods': b['periods'], 'criteria': b['criteria']}

    def fact(key, value, label, *, group=None, unit=None):
        if not math.isfinite(float(value)):
            raise ValueError('집계 결과가 유한한 숫자 범위를 벗어났어요.')
        f = store.add('business_' + key, float(value), spec.unit if unit is None else unit, label, **basis, group=group)
        return f.id

    if b['limitations']:
        b['status'] = 'blocked'
        b['steps'].append({'tool': 'quarter_compare', 'status': 'blocked', 'reason': '필수 기간이나 값이 부족해요.'})
    else:
        now, before = _total(sums[m] for m in current), _total(sums[m] for m in baseline)
        delta = now - before
        pct = (now / before - 1) * 100 if before != 0 else None
        totals = {'current': now, 'baseline': before, 'delta': delta, 'change_pct': pct}
        if any(v is not None and not math.isfinite(v) for v in totals.values()):
            web_input.reject('합계나 증감률이 계산 가능한 숫자 범위를 벗어났어요.')
        b['totals'] = totals
        for key, value in totals.items():
            if value is not None:
                b['metric_facts'][key] = fact(key, value, {'current': '대상 분기 합계', 'baseline': '전년 동분기 합계', 'delta': '전년 동분기 대비 증감', 'change_pct': '전년 동분기 대비 증감률'}[key], unit='%' if key == 'change_pct' else None)
        b['steps'].append({'tool': 'quarter_compare', 'status': 'done'})
        if pct is None:
            b['status'] = 'limited'
            limit('zero_baseline', '전년 동분기 합계가 0이어서 증감률은 계산하지 않아요. 합계와 절대 증감만 확인해 주세요.')
        if spec.business_task != 'quarter_compare':
            reason = None
            if not spec.category:
                reason = '나눠 볼 분류 열을 고르지 않아 분류별 증감은 생략했어요.'
            elif relevant['group'].isna().any():
                reason = '분류가 비어 있는 행이 있어 분류별 증감을 확정하지 않아요.'
            else:
                labels = set(relevant['group'].astype(str))
                counts = relevant.groupby(['group', 'month']).value.count()
                if any((label, month) not in counts or counts.loc[(label, month)] == 0 for label in labels for month in needed):
                    reason = '분류별로 두 분기의 모든 달에 값이 있어야 해요. 한쪽에 없는 분류는 0으로 채우지 않아요.'
            if reason:
                b['status'] = 'limited'
                limit('category_coverage', reason)
                b['steps'].append({'tool': 'category_change', 'status': 'skipped', 'reason': reason})
            else:
                grouped = relevant.groupby(['group', 'month']).value.sum(min_count=1)
                groups = []
                for label in labels:
                    a = _total(grouped.loc[(label, m)] for m in current)
                    z = _total(grouped.loc[(label, m)] for m in baseline)
                    groups.append({'label': str(label), 'current': a, 'baseline': z, 'delta': a - z})
                if not math.isclose(_total(g['delta'] for g in groups), delta, rel_tol=1e-9, abs_tol=1e-7):
                    web_input.reject('분류별 증감과 전체 증감의 근거가 맞지 않아요.')
                for g in sorted(groups, key=lambda x: (-abs(x['delta']), x['label']))[:5]:
                    g['facts'] = [fact('group_' + key, g[key], f"{g['label']} " + {'current': '대상 분기 합계', 'baseline': '전년 동분기 합계', 'delta': '전년 동분기 대비 증감'}[key], group=g['label']) for key in ('current', 'baseline', 'delta')]
                    b['groups'].append(g)
                b['steps'].append({'tool': 'category_change', 'status': 'done'})
        if spec.business_task == 'brief':
            b['steps'].append({'tool': 'brief', 'status': 'done'})
    for tool in spec.tools:
        if not any(x['tool'] == tool for x in b['steps']):
            b['steps'].append({'tool': tool, 'status': 'skipped', 'reason': '전체 비교를 완료하지 못했어요.'})
    limit('observation_scope', OBSERVATION_LIMIT)
    facts = {f.id: f.to_dict() for f in store.all()}
    b['statements'] = _statements(b, facts)
    return {'dataset': info['dataset'], 'value': {k: chosen[k] for k in ('name', 'ko', 'unit', 'additive', 'note')}, 'category': spec.category,
            'options': {'values': [c['name'] for c in info['columns'] if c['role'] == 'measure'], 'categories': [c['name'] for c in info['columns'] if c['role'] in pipeline.GROUP_ROLES]},
            'labels': {c['name']: c['ko'] for c in info['columns']}, 'series': series, 'cards': [], 'answer': None,
            'forecast': None, 'forecast_refusal': '업무 분석에는 예측을 포함하지 않아요.',
            'missing_months': [s['period'] for s in series if s['value'] is None], 'filters': b['criteria']['filters'], 'facts': facts, 'business': b}


def preview(ds, spec) -> dict:
    b = analyze(ds, spec)['business']
    return {key: b[key] for key in ('task', 'status', 'periods', 'criteria', 'limitations', 'steps')}


def _require(condition: bool):
    if not condition:
        raise ValueError('invalid business evidence')


def verify(result: dict) -> bool:
    try:
        b, facts = result['business'], result['facts']
        _require(b['task'] in TASKS and b['status'] in {'complete', 'limited', 'blocked'})
        current = [pd.Period(x, freq='M') for x in b['periods']['current']]
        _require(len(current) == 3 and current[0].month in (1, 4, 7, 10))
        _require(current == [current[0] + i for i in range(3)])
        _require(b['periods']['baseline'] == [str(x - 12) for x in current])
        for key, ref in b['metric_facts'].items():
            f = facts[ref]
            _require(f['kind'] == 'business_' + key and f['value'] == b['totals'][key])
            _require(f['unit'] == ('%' if key == 'change_pct' else b['criteria']['unit']))
        for ref, f in facts.items():
            _require(f['id'] == ref)
            _require(math.isfinite(f['value']) and f['basis']['periods'] == b['periods'] and f['basis']['criteria'] == b['criteria'])
        for g in b['groups']:
            _require(math.isclose(g['current'] - g['baseline'], g['delta'], rel_tol=1e-9, abs_tol=1e-7))
            _require(len(g['facts']) == 3)
            for key, ref in zip(('current', 'baseline', 'delta'), g['facts']):
                f = facts[ref]
                _require(f['kind'] == 'business_group_' + key and f['basis']['group'] == g['label'] and f['value'] == g[key] and f['unit'] == b['criteria']['unit'])
        if b['status'] != 'blocked':
            t = b['totals']
            _require({'current', 'baseline', 'delta'} <= b['metric_facts'].keys())
            _require(math.isclose(t['current'] - t['baseline'], t['delta'], rel_tol=1e-9, abs_tol=1e-7))
            _require(t['change_pct'] == ((t['current'] / t['baseline'] - 1) * 100 if t['baseline'] != 0 else None))
            _require(next(s for s in b['steps'] if s['tool'] == 'quarter_compare')['status'] == 'done')
        else:
            _require(not facts and not b['groups'] and not b['totals'])
        expected_tools = ['quarter_compare']
        if b['task'] != 'quarter_compare':
            expected_tools.append('category_change')
        if b['task'] == 'brief':
            expected_tools.append('brief')
        _require([s['tool'] for s in b['steps']] == expected_tools)
        codes = {x['code'] for x in b['limitations']}
        if b['status'] == 'blocked':
            _require([s['status'] for s in b['steps']] == ['blocked'] + ['skipped'] * (len(expected_tools) - 1))
            _require(bool(codes & {'missing_months', 'masked_values', 'empty_values'}))
        else:
            _require(not codes & {'missing_months', 'masked_values', 'empty_values'})
            category_skipped = b['task'] != 'quarter_compare' and 'category_coverage' in codes
            zero = b['totals']['baseline'] == 0
            _require(('zero_baseline' in codes) == zero)
            _require(b['status'] == ('limited' if zero or category_skipped else 'complete'))
            expected_states = ['done']
            if b['task'] != 'quarter_compare':
                _require(bool(b['groups']) != category_skipped)
                expected_states.append('skipped' if category_skipped else 'done')
            else:
                _require(not b['groups'])
            if b['task'] == 'brief':
                expected_states.append('done')
            _require([s['status'] for s in b['steps']] == expected_states)
        _require(b['statements'] == _statements(b, facts))
        _require(all(ref in facts for s in b['statements'] for ref in s['facts']))
        _require(not result['cards'] and result['answer'] is None and result['forecast'] is None)
    except (AssertionError, KeyError, ValueError, TypeError, StopIteration, ZeroDivisionError):
        raise HTTPException(422, '업무 분석의 계산 근거와 설명을 확인하지 못했어요.') from None
    return True
