import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type Analysis, type JoinResult } from '@/lib/api'
import { Panel } from '@/components/kit'
import { Button } from '@/components/ui/button'

const REGION_COLUMNS = new Set(['bjd_cd', 'bjd(code)', '법정동코드', 'emd_cd', '행정동코드', 'bjd_nm', '법정동명', 'emd_nm', '행정동명'])
const keyText = (keys: (string | string[])[]) => keys.map(k => Array.isArray(k) ? k.join(' / ') : k).join(', ')

export function CenterJoinPanel({ analysis: a, included, onInclude }: { analysis: Analysis; included: boolean; onInclude: (result: JoinResult | null) => void }) {
  const [other, setOther] = useState('')
  const [rightValue, setRightValue] = useState('')
  const [mode, setMode] = useState('month')
  const [leftRegion, setLeftRegion] = useState('')
  const [rightRegion, setRightRegion] = useState('')
  const [request, setRequest] = useState<string | null>(null)
  const list = useQuery({ queryKey: ['datasets'], queryFn: api.datasets })
  const left = useQuery({ queryKey: ['understand', a.dataset.id], queryFn: () => api.understand(a.dataset.id) })
  const right = useQuery({ queryKey: ['understand', other], queryFn: () => api.understand(other), enabled: !!other })
  const candidates = (list.data ?? []).filter(d => d.id !== a.dataset.id)
  const measures = right.data?.columns.filter(c => c.role === 'measure' && c.additive === true) ?? []
  const value = rightValue || measures.find(c => c.name === right.data?.selection?.value)?.name || measures[0]?.name || ''
  const rightMeasure = measures.find(c => c.name === value)
  const filters = a.filters ?? []
  const signature = JSON.stringify([a.dataset.id, a.value.name, filters, other, value, mode, leftRegion, rightRegion])
  const ready = !!other && !!right.data?.time_column && !!rightMeasure && (mode === 'month' || (!!leftRegion && !!rightRegion))
  const query = useQuery({ queryKey: ['comparison', signature], queryFn: () => api.join(a.dataset.id, a.value.name, other, value, { left_filters: filters, ...(mode === 'region' ? { left_region: leftRegion, right_region: rightRegion } : {}) }), enabled: ready && request === signature, retry: false })
  const r = request === signature ? query.data : undefined
  const reset = () => { setRequest(null); onInclude(null) }
  return <Panel title="다른 자료와 함께 보기" className="space-y-4">
    <h3 className="text-[17px] font-bold">비교할 기준을 확인해 주세요</h3>
    <p className="text-[14px] text-muted-foreground">왼쪽: {a.dataset.title} / {a.value.ko} ({a.value.unit || '단위 미지정'}) / 날짜 {left.data?.time_column ?? '확인 중'}. 조건: {filters.length ? filters.map(f => `${f.column}: ${f.values.join(', ')}`).join(' / ') : '전체 행'}</p>
    <label className="block text-[15px]">함께 볼 자료<select aria-label="함께 볼 자료" className="form-control mt-1" value={other} onChange={e => { reset(); setOther(e.target.value); setRightValue(''); setRightRegion('') }}><option value="">자료를 골라 주세요</option>{candidates.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}</select></label>
    {list.error && <p role="alert" className="text-destructive">자료 목록을 불러오지 못했어요.</p>}
    {right.error && <p role="alert" className="text-destructive">{(right.error as Error).message}</p>}
    {other && right.data && <>
      <label className="block text-[15px]">오른쪽 값과 단위<select aria-label="오른쪽 값과 단위" className="form-control mt-1" value={value} onChange={e => { reset(); setRightValue(e.target.value) }}><option value="">합계 가능한 값을 골라 주세요</option>{measures.map(c => <option key={c.name} value={c.name}>{c.ko} ({c.unit || '단위 미지정'})</option>)}</select></label>
      <p className="text-[14px] text-muted-foreground">오른쪽 날짜: {right.data.time_column || '월별 날짜 없음'}. 오른쪽은 전체 행을 사용해요. 금액과 건수 등 단위는 각각 유지해요.</p>
      <label className="block text-[15px]">비교할 묶음<select aria-label="비교할 묶음" className="form-control mt-1" value={mode} onChange={e => { reset(); setMode(e.target.value) }}><option value="month">월 전체 합계</option><option value="region">같은 월과 지역별 합계</option></select></label>
      {mode === 'region' && <div className="grid gap-3 sm:grid-cols-2">{([['왼쪽 지역 열', leftRegion, setLeftRegion, left.data], ['오른쪽 지역 열', rightRegion, setRightRegion, right.data]] as const).map(([label, selected, set, info]) => <label key={label} className="text-[15px]">{label}<select aria-label={label} className="form-control mt-1" value={selected} onChange={e => { reset(); set(e.target.value) }}><option value="">지역 열 고르기</option>{info?.columns.filter(c => REGION_COLUMNS.has(c.name)).map(c => <option key={c.name} value={c.name}>{c.ko} ({c.name})</option>)}</select></label>)}</div>}
      {mode === 'region' && <p className="text-[14px] text-muted-foreground">같은 법정동/행정동 코드 또는 같은 체계의 이름끼리 맞춰요. 법정동 10자리 코드는 앞 8자리로 모아요. 지역별로 상관을 계산하고 가림이나 빈값이 있는 부분합은 제외해요.</p>}
      <Button type="button" variant="soft" disabled={!ready || (request === signature && query.isFetching)} onClick={() => { onInclude(null); setRequest(signature) }}>이 기준으로 비교하기</Button>
    </>}
    {request === signature && query.isFetching && <p role="status">기준에 맞춰 비교하는 중이에요…</p>}
    {request === signature && query.error && <p role="alert" className="text-destructive">{(query.error as Error).message}</p>}
    {r && <div className="space-y-3 text-[14px]">
      <p>붙은 묶음 {r.report.matched_rows}개 / 왼쪽만 {r.report.unmatched_rows}개 / 오른쪽만 {r.report.right_unmatched_rows ?? 0}개</p>
      <p>{r.plan?.region_basis}. {r.plan?.aggregation}</p>
      <details><summary className="cursor-pointer py-2">붙지 않은 월과 지역</summary><p>왼쪽에만 있음: {keyText(r.report.unmatched_keys) || '없음'}</p><p>오른쪽에만 있음: {keyText(r.report.right_unmatched_keys ?? []) || '없음'}</p></details>
      <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>지역</th><th>완전한 월</th><th>상관계수</th></tr></thead><tbody>{r.groups?.map(g => <tr key={g.region} className="border-t border-border"><td className="p-2">{g.region}</td><td className="p-2">{g.months}개월</td><td className="p-2">{g.correlation == null ? g.refusal : g.correlation.toFixed(3)} <span className="font-mono">[비교-{g.fact}]</span></td></tr>)}</tbody></table></div>
      <p>{r.note}</p>
      <label className="flex min-h-11 items-center gap-3"><input type="checkbox" checked={included} onChange={e => onInclude(e.target.checked ? r : null)} />이 비교와 근거를 보고서에 포함하기</label>
    </div>}
  </Panel>
}
