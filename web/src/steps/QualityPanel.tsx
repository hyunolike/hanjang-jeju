import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'

const NAMES: Record<string, string> = { missing: '빈값', none: '값 없음', masked: '가림값', trimmed: '공백 정리', subtotal: '분리한 소계', subtotal_candidate: '유지한 소계 표기', invalid_date: '날짜 오류', invalid_number: '숫자 오류' }

export function QualityPanel({ id, time, value }: { id: string; time?: string; value?: string }) {
  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState('')
  const [column, setColumn] = useState('')
  const [offset, setOffset] = useState(0)
  const q = useQuery({ queryKey: ['quality', id, time, value, kind, column, offset], queryFn: () => api.quality(id, { time: time || undefined, value: value || undefined, kind: kind || undefined, column: column || undefined, offset, limit: 50 }), enabled: open })
  const r = q.data
  return <details className="my-4 rounded-xl border border-border p-4" onToggle={e => setOpen(e.currentTarget.open)}>
    <summary className="cursor-pointer py-2 text-[15px] font-semibold">품질 상세와 원본 줄 확인</summary>
    {q.isFetching && <p role="status">원본을 검사하는 중이에요…</p>}
    {q.error && <p role="alert" className="text-destructive">{(q.error as Error).message}</p>}
    {r && <div className="mt-3 space-y-4 text-[14px]">
      <p>{r.rows.toLocaleString()}행 중 확인할 행 {r.affected_rows.toLocaleString()}개. 분석에 남긴 행 {r.clean_rows.toLocaleString()}개.</p>
      {!r.complete && <p role="alert" className="text-destructive">{r.error?.line}행: {r.error?.message} 아래 집계는 읽은 구간만 포함해요.</p>}
      <p>{column ? `${column} 열: ` : '모든 열: '}{Object.entries(column ? r.columns.find(c => c.name === column)?.counts ?? r.counts : r.counts).map(([k, n]) => `${NAMES[k] ?? k} ${n.toLocaleString()}건`).join(' / ')}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label>품질 항목<select aria-label="품질 항목" className="form-control mt-1" value={kind} onChange={e => { setKind(e.target.value); setOffset(0) }}><option value="">모두</option>{Object.entries(NAMES).map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select></label>
        <label>품질 확인 열<select aria-label="품질 확인 열" className="form-control mt-1" value={column} onChange={e => { setColumn(e.target.value); setOffset(0) }}><option value="">모든 열</option>{r.columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}</select></label>
      </div>
      <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>CSV 줄</th><th>열 / 내용</th><th>원본 → 정리</th></tr></thead><tbody>{r.issues.map((x, i) => <tr key={i} className="border-t border-border"><td className="p-2 align-top">{x.line}{x.line_end !== x.line ? `~${x.line_end}` : ''}</td><td className="p-2 align-top">{x.column ?? '행'}<p>{x.message}</p></td><td className="max-w-64 break-all whitespace-pre-wrap p-2">{x.before === null ? '(없음)' : JSON.stringify(x.before)} → {x.after === null ? '(미사용)' : JSON.stringify(x.after)}{x.truncated && ' (200자까지 표시)'}</td></tr>)}</tbody></table></div>
      {!r.issues.length && <p>이 조건에서 확인할 셀이 없어요.</p>}
      <div className="flex flex-wrap items-center gap-3"><Button type="button" variant="soft" disabled={!offset || q.isFetching} onClick={() => setOffset(Math.max(0, offset - 50))}>앞 50건</Button><span>{r.matched_issues ? `${offset + 1}~${Math.min(offset + 50, r.matched_issues)}` : '0'} / {r.matched_issues.toLocaleString()}건</span><Button type="button" variant="soft" disabled={offset + 50 >= r.matched_issues || q.isFetching} onClick={() => setOffset(offset + 50)}>다음 50건</Button></div>
      <p className="text-muted-foreground">여기서는 원본을 바꾸지 않아요. 오류가 있으면 CSV를 수정한 뒤 다른 CSV 넣기로 다시 확인해 주세요. 가림값과 빈값은 0으로 채우지 않아요.</p>
    </div>}
  </details>
}
