import type { BusinessResult } from "@/lib/api"
import { Pill } from "@/components/kit"

const TOOLS: Record<string, string> = { quarter_compare: "전년 동분기 비교", category_change: "분류별 증감", brief: "보고용 정리" }
const STATES = { done: "완료", skipped: "생략", blocked: "중단" }

export function BusinessSummary({ result: b }: { result: BusinessResult }) {
  return <section className="space-y-3 rounded-xl border border-border p-4" aria-label="업무 분석 결과">
    <div className="flex flex-wrap items-center gap-2"><h3 className="font-bold">{TOOLS[b.task]}</h3><Pill tone={b.status === "complete" ? "teal" : "caution"}>{b.status === "complete" ? "계산 완료" : b.status === "limited" ? "일부 계산 가능" : "자료 확인 필요"}</Pill></div>
    <p className="text-[14px]">대상: {b.periods.current.join(", ")} / 전년 동분기: {b.periods.baseline.join(", ")}</p>
    <p className="text-[14px]">날짜: {b.criteria.time} / 값: {b.criteria.value} / 분류: {b.criteria.category ?? "전체"} / 단위: {b.criteria.unit || "미지정"}</p>
    {b.criteria.filters.length > 0 && <p className="text-[14px]">필터: {b.criteria.filters.map(f => `${f.column}: ${f.values.join(", ")}`).join(" / ")}</p>}
    <ul className="space-y-2 text-[16px] leading-relaxed">{b.statements.map((s, i) => <li key={i}>{s.text} <span className="font-mono text-[13px] text-[var(--text-evidence)]">[{s.facts.join(", ")}]</span></li>)}</ul>
    <ul className="space-y-1 text-[14px] text-[var(--caution)]">{b.limitations.map(x => <li key={x.code}>{x.message}</li>)}</ul>
    <p className="text-[13px] text-muted-foreground">{b.steps.map(s => `${TOOLS[s.tool] ?? s.tool}: ${STATES[s.status]}${s.reason ? ` (${s.reason})` : ""}`).join(" / ")}</p>
  </section>
}
