import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { ArrowUp, Bot, PackageSearch, Sparkles } from "lucide-react"
import { api, STATIC, type AnalyzeOptions, type Dataset, type PlanResult } from "@/lib/api"
import { Illust, Panel, Pill } from "@/components/kit"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select"
import { period } from "@/lib/format"

const INTENT_LABEL: Record<string, string> = {
  overview: "전체 흐름",
  compare: "기간 비교",
  share: "구성비",
  rank: "순위",
  forecast: "전망",
}

/** 질문 → 로컬 모델이 만든 계획 → 이용자 확인 → 분석 (설계 agent-design.md 6절). */
export function AskPanel({ dataset, onRun }: { dataset: Dataset; onRun: (o: AnalyzeOptions) => void }) {
  const model = useQuery({ queryKey: ["model"], queryFn: api.model, refetchInterval: (q) => (q.state.data?.ready ? false : 5000) })
  const [question, setQuestion] = useState("")
  const [picked, setPicked] = useState<Record<string, string>>({})
  const ask = useMutation({ mutationFn: (q: string) => api.plan(dataset.id, q), onSuccess: () => setPicked({}) })
  const r = ask.data

  if (STATIC) {
    return (
      <Panel>
        <div className="flex items-center gap-4">
          <Illust name="model" fallback={Bot} className="size-12" />
          <p className="text-[15px] leading-relaxed text-muted-foreground">질문으로 분석하기는 PC용 프로그램에서 쓸 수 있어요. 로컬 AI가 이 컴퓨터 안에서만 질문을 계획으로 바꿔요.</p>
        </div>
      </Panel>
    )
  }

  const ready = model.data?.ready
  const unresolvedLeft = r && !r.fallback ? r.unresolved.filter((u) => !picked[u.column]) : []
  const otherBlocks = r && !r.fallback ? r.blocked.filter((b) => !b.startsWith("찾지 못한 값")) : []

  const run = (res: PlanResult) => {
    const filters = [...res.plan.filters, ...res.unresolved.filter((u) => picked[u.column] && picked[u.column] !== "__skip").map((u) => ({ column: u.column, values: [picked[u.column]] }))]
    onRun({ value: res.plan.value, category: res.plan.group_by, intent: res.plan.intent, filters, period_n: res.plan.period_n || undefined, horizon: res.plan.horizon })
  }

  return (
    <Panel
      title="무엇이 궁금한가요?"
      action={<Pill tone={ready ? "teal" : "grey"}>{ready ? `로컬 AI 준비됨 (${model.data?.model})` : model.data?.available ? "로컬 AI 준비 중" : "로컬 AI 없음"}</Pill>}
    >
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (question.trim()) ask.mutate(question)
        }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={!ready || ask.isPending}
          placeholder={ready ? "예: 애월읍 어떤 업종 매출 비중이 커?" : "로컬 AI가 없으면 아래에서 직접 골라 주세요"}
          className="h-12 flex-1 rounded-xl border border-[var(--grey-300)] bg-card px-4 text-[16px] outline-none focus:border-primary"
        />
        <Button type="submit" size="md" disabled={!ready || ask.isPending || !question.trim()} aria-label="계획 만들기">
          <ArrowUp />
        </Button>
      </form>
      {ask.isPending && <p className="mt-3 text-[15px] text-muted-foreground">질문을 분석 계획으로 바꾸는 중이에요…</p>}
      {ask.error && <p className="mt-3 text-[15px] text-destructive">{(ask.error as Error).message}</p>}
      {r?.fallback && <p className="mt-3 text-[15px] text-[var(--caution)]">질문을 알아듣지 못했어요. 아래에서 직접 골라 주세요.</p>}

      {r && !r.fallback && (
        <div className="mt-5 space-y-4">
          <div>
            <p className="mb-2 text-[14px] font-semibold text-[var(--grey-700)]">이렇게 분석할게요</p>
            <div className="flex flex-wrap gap-2">
              <Pill tone="teal">{INTENT_LABEL[r.plan.intent]}</Pill>
              <Pill tone="grey">값: {r.labels[r.plan.value] ?? r.plan.value}</Pill>
              {r.plan.group_by && <Pill tone="grey">나눠 보기: {r.labels[r.plan.group_by] ?? r.plan.group_by}</Pill>}
              {r.plan.filters.map((f) => (
                <Pill key={f.column} tone="grey">
                  {r.labels[f.column] ?? f.column}: {f.values.join(", ")}
                </Pill>
              ))}
              {r.plan.period_n > 0 && <Pill tone="grey">최근 {r.plan.period_n}개월</Pill>}
              {r.plan.intent === "forecast" && <Pill tone="violet">{r.plan.horizon}개월 전망</Pill>}
            </div>
          </div>

          {r.unresolved.map((u) => (
            <div key={u.column} className="rounded-2xl bg-[var(--caution-50)] p-4">
              <p className="text-[15px] text-[var(--caution)]">
                <b>'{u.text}'</b>을 {r.labels[u.column] ?? u.column}에서 찾지 못했어요. 값을 골라 주세요.
              </p>
              <Select value={picked[u.column] ?? ""} onValueChange={(v) => setPicked({ ...picked, [u.column]: v as string })}>
                <SelectTrigger className="mt-2 h-10 w-full rounded-xl bg-card px-3 text-[15px]">
                  <span>{picked[u.column] === "__skip" ? "거르지 않고 보기" : picked[u.column] || "값 고르기"}</span>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__skip">거르지 않고 보기</SelectItem>
                  {(u.choices ?? []).map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ))}

          {r.needs.map((n) => (
            <div key={n.table_id} className="flex items-start gap-3 rounded-2xl border border-[var(--teal-100)] bg-secondary/50 p-4">
              <Illust name="request-data" fallback={PackageSearch} className="size-11" />
              <div className="text-[15px] leading-relaxed">
                <p className="font-bold">센터에서 이 표를 더 받아 오면 좋아요</p>
                <p>
                  {n.table_id} {n.title}
                  {n.period && <span className="text-muted-foreground"> ({n.period.split("~").map(period).join("~")})</span>}
                </p>
                <p className="text-muted-foreground">{n.reason}. 지금 자료로 할 수 있는 만큼 먼저 분석할게요.</p>
              </div>
            </div>
          ))}

          {r.unsupported.length > 0 && (
            <div className="rounded-2xl bg-[var(--grey-100)] p-4 text-[15px] text-[var(--grey-700)]">
              <b>자료로 답할 수 없어요:</b> {r.unsupported.join(", ")}
            </div>
          )}
          {otherBlocks.map((b) => (
            <p key={b} className="text-[15px] text-[var(--caution)]">{b}</p>
          ))}

          <div className="flex gap-2">
            <Button size="md" onClick={() => run(r)} disabled={unresolvedLeft.length > 0 || otherBlocks.length > 0}>
              <Sparkles /> 이대로 분석
            </Button>
            <span className="self-center text-[13px] text-muted-foreground">{(r.latency_ms / 1000).toFixed(1)}초, 계산은 하지 않고 계획만 만들었어요</span>
          </div>
        </div>
      )}
    </Panel>
  )
}
