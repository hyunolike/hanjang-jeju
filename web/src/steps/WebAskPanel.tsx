import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { api, type AnalyzeOptions, type Dataset } from "@/lib/api"
import { confirmUploadPlan, discardPlan, planUpload, type WebPlan } from "@/lib/upload"
import { Panel, Pill } from "@/components/kit"
import { Button } from "@/components/ui/button"

const INTENTS: Record<string, string> = { overview: "전체 흐름", compare: "기간 비교", share: "구성비", rank: "순위", forecast: "전망" }
const REASONS: Record<string, string> = {
  model_unconfigured: "AI 연결 설정이 아직 없어요.", free_plan_unconfirmed: "무료 플랜 확인이 필요해요.", quota_exhausted: "오늘 무료 AI 한도를 다 썼어요.", rate_limited: "AI 요청이 많아요. 잠시 뒤 다시 시도해 주세요.", timeout: "AI가 제한 시간 안에 답하지 못했어요.", invalid_plan: "자료에 맞는 분석 계획을 만들지 못했어요.", parse_failed: "AI가 올바른 계획 형식으로 답하지 못했어요.",
}

export function WebAskPanel({ dataset, onRun }: { dataset: Dataset; onRun: (o: AnalyzeOptions) => void }) {
  const model = useQuery({ queryKey: ["web-model"], queryFn: api.model, retry: false })
  const [question, setQuestion] = useState("")
  const [result, setResult] = useState<WebPlan | null>(null)
  const [picked, setPicked] = useState<Record<string, string>>({})
  const ask = useMutation({ mutationFn: (edited?: boolean) => {
    const spec = edited && result ? { ...result.execution_spec, filters: [...result.execution_spec.filters, ...result.unresolved.filter(u => picked[u.column] && picked[u.column] !== "__skip").map(u => ({ column: u.column, values: [picked[u.column]] }))] } : undefined
    return planUpload(dataset.id, question, spec)
  }, onSuccess: r => { setResult(r); setPicked({}) }, retry: false })
  const ready = model.data?.ready
  const pending = result?.unresolved?.filter(u => !picked[u.column]) ?? []
  return <Panel title="AI Agent에게 질문하기" action={<Pill tone={ready ? "teal" : "grey"}>{ready ? "Cloudflare AI" : "직접 선택 가능"}</Pill>}>
    <p className="mb-3 text-[14px] text-muted-foreground">AI는 질문을 계획으로 바꾸고, 확인한 계획의 숫자는 분석 도구가 계산해요. CSV 원본은 모델에 보내지 않아요.</p>
    {!ready && <p className="mb-3 text-[15px]">{REASONS[model.data?.reason ?? ""] ?? (model.isLoading ? "AI 연결을 확인하는 중이에요." : "AI에 연결하지 못했어요.")} 직접 고른 열로 분석은 계속할 수 있어요.</p>}
    <form className="flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); setResult(null); discardPlan(dataset.id); ask.mutate(false) }}>
      <input aria-label="분석 질문" className="h-12 min-w-0 flex-1 rounded-xl border border-[var(--grey-300)] bg-card px-4 text-[16px]" maxLength={300} value={question} onChange={e => { setQuestion(e.target.value); setResult(null); discardPlan(dataset.id); ask.reset() }} placeholder="예: 작년보다 매출이 늘었어?" />
      <Button type="submit" size="md" disabled={!ready || !question.trim() || ask.isPending}>계획 만들기</Button>
    </form>
    {ask.isPending && <p className="mt-3" role="status">분석 계획을 만들고 검사하는 중이에요…</p>}
    {ask.error && <p className="mt-3 text-destructive" role="alert">{(ask.error as Error).message}</p>}
    {result?.fallback && <p className="mt-3">{REASONS[result.reason ?? ""] ?? "계획을 만들지 못했어요."} 열과 조건을 직접 골라 분석해 주세요.</p>}
    {result && !result.fallback && <div className="mt-5 space-y-3">
      <p className="font-semibold">이렇게 분석할게요</p>
      <div className="flex flex-wrap gap-2"><Pill tone="teal">{INTENTS[result.execution_spec.intent]}</Pill><Pill tone="grey">값: {result.execution_spec.value}</Pill>{result.execution_spec.category && <Pill tone="grey">분류: {result.execution_spec.category}</Pill>}<Pill tone="grey">{result.execution_spec.run_forecast ? `${result.execution_spec.horizon}개월 예측 포함` : "예측 도구 실행 안 함"}</Pill></div>
      <p className="text-[14px]">실행 도구: {result.execution_spec.tools?.join(", ")}{result.execution_spec.period_n ? ` · 최근 ${result.execution_spec.period_n}개월` : ""}</p>
      {result.execution_spec.filters.map(f => <p key={f.column} className="text-[14px]">{f.column}: {f.values.join(", ")}</p>)}
      {result.unresolved?.map(u => <label key={u.column} className="block text-[15px]">'{u.text}'에 해당하는 {u.column} 값을 골라 주세요<select className="mt-2 h-11 w-full rounded-xl border border-[var(--grey-300)] bg-card px-3" value={picked[u.column] ?? ""} onChange={e => setPicked({ ...picked, [u.column]: e.target.value })}><option value="">값 선택</option><option value="__skip">이 조건 없이 분석하기</option>{u.choices?.map(v => <option key={v} value={v}>{v}</option>)}</select></label>)}
      {result.blocked?.map(b => <p key={b} className="text-[15px] text-[var(--caution)]">{b}</p>)}
      {result.unsupported?.map(text => <p key={text} className="text-[15px] text-[var(--caution)]">{text}</p>)}
      {result.needs?.map(n => <p key={n.table_id} className="text-[15px]">추가 자료: {n.table_id} {n.title}. {n.reason}</p>)}
      {result.unresolved?.length > 0 ? <Button disabled={pending.length > 0 || ask.isPending || result.blocked.some(b => !b.startsWith("찾지 못한 값"))} onClick={() => ask.mutate(true)}>수정한 계획 다시 확인</Button> : <Button disabled={!result.input_digest || result.blocked?.length > 0} onClick={() => { confirmUploadPlan(dataset.id, result, question); onRun({ agent_digest: result.input_digest }) }}>이 계획으로 분석하기</Button>}
    </div>}
  </Panel>
}
