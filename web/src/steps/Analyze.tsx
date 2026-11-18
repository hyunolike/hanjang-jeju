import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Area, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts"
import { BarChart3, CalendarRange, CalendarX, Lightbulb, TrendingUp } from "lucide-react"
import { api, type Analysis, type AnalyzeOptions, type Card, type Dataset } from "@/lib/api"
import { BigTitle, CtaBar, Illust, Panel, Pill, Stat } from "@/components/kit"
import { Button } from "@/components/ui/button"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { factText, money, period } from "@/lib/format"
import { JoinPanel } from "./JoinPanel"
import { AskPanel } from "./AskPanel"

const CARD_ICON: Record<Card["kind"], { name: string; icon: typeof Lightbulb; tag: string }> = {
  change: { name: "insight", icon: TrendingUp, tag: "변화" },
  driver: { name: "insight", icon: BarChart3, tag: "이끈 항목" },
  anomaly: { name: "gap", icon: Lightbulb, tag: "평소와 달라요" },
  season: { name: "insight", icon: CalendarRange, tag: "계절" },
}

const chartConfig = {
  value: { label: "실제", color: "var(--teal-500)" },
  mean: { label: "추정", color: "var(--violet)" },
  band: { label: "80% 범위", color: "var(--violet)" },
} satisfies ChartConfig

export function Analyze({
  dataset,
  choice,
  onChange,
  onBack,
  onNext,
}: {
  dataset: Dataset
  choice: AnalyzeOptions
  onChange: (v: AnalyzeOptions) => void
  onBack: () => void
  onNext: (a: Analysis) => void
}) {
  const q = useQuery({ queryKey: ["analyze", dataset.id, JSON.stringify(choice)], queryFn: () => api.analyze(dataset.id, choice), placeholderData: (prev) => prev })
  const a = q.data
  const chart = useMemo(() => (a && !a.error ? chartData(a) : []), [a])
  if (q.isLoading) return <Skeleton className="h-[640px] rounded-[22px]" />
  if (q.error || !a) return <Panel><p className="text-destructive">{(q.error as Error)?.message}</p></Panel>
  if (a.error)
    return (
      <div className="space-y-5">
        <BigTitle eyebrow="3단계 분석" title="이 자료로는 흐름을 볼 수 없어요" sub={a.error} />
        <CtaBar>
          <Button size="cta" className="flex-1" onClick={onBack}>
            이전
          </Button>
        </CtaBar>
      </div>
    )

  const unit = a.value.unit
  const lead = a.cards[0]

  return (
    <div className="space-y-5">
      <AskPanel dataset={dataset} onRun={onChange} />

      <BigTitle eyebrow="3단계 분석" title={a.answer ? a.answer.title : lead ? lead.title : "눈에 띄는 점을 찾지 못했어요"} sub={`${a.value.ko}${unit && !a.value.ko.includes(unit) ? ` (${unit})` : ""} 기준이에요. ${a.answer ? "질문에 맞춰 계산했어요." : "묻기 전에 먼저 찾아 봤어요."}`} />

      <div className="no-print flex flex-wrap gap-2">
        <Select value={a.value.name} onValueChange={(v) => onChange({ value: v as string, category: a.category })}>
          <SelectTrigger className="h-11 rounded-xl bg-card px-4 text-[15px] font-semibold">
            <span>값: {a.value.ko}</span>
          </SelectTrigger>
          <SelectContent>
            {a.options.values.map((v) => (
              <SelectItem key={v} value={v}>
                값: {v}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {a.options.categories.length > 0 && (
          <Select value={a.category ?? "__none"} onValueChange={(v) => onChange({ value: a.value.name, category: v === "__none" ? null : (v as string) })}>
            <SelectTrigger className="h-11 rounded-xl bg-card px-4 text-[15px] font-semibold">
              <span>{a.category ? `나눠 보기: ${a.labels?.[a.category] ?? a.category}` : "나눠 보지 않기"}</span>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none">나눠 보지 않기</SelectItem>
              {a.options.categories.map((c) => (
                <SelectItem key={c} value={c}>
                  나눠 보기: {a.labels?.[c] ?? c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {a.answer && (
        <Panel title="질문에 대한 답" action={<Pill tone="teal">근거 {a.answer.facts.join(", ")}</Pill>}>
          <div className="grid gap-4 sm:grid-cols-3">
            {a.answer.facts.map((id) => {
              const f = a.facts[id]
              return f ? <Stat key={id} label={f.label} value={factText(f.value, f.unit)} /> : null
            })}
          </div>
          {a.answer.warnings.map((w) => (
            <p key={w} className="mt-3 text-[14px] text-[var(--caution)]">{w}</p>
          ))}
        </Panel>
      )}
      {a.filters?.length > 0 && (
        <p className="text-[14px] text-muted-foreground">조건: {a.filters.map((f) => f.values.join(", ")).join(" / ")}</p>
      )}

      <Panel title="흐름" action={a.forecast ? <Pill tone="violet">추정 포함</Pill> : undefined}>
        <ChartContainer config={chartConfig} className="h-[280px] w-full">
          <ComposedChart data={chart} margin={{ left: 4, right: 8, top: 8 }}>
            <CartesianGrid vertical={false} stroke="var(--grey-200)" />
            <XAxis dataKey="period" tickLine={false} axisLine={false} minTickGap={32} tick={{ fontSize: 12 }} />
            <YAxis tickLine={false} axisLine={false} width={64} tick={{ fontSize: 12 }} tickFormatter={(v) => money(v, unit).replace(/ ?원$/, "")} />
            <ChartTooltip content={<ChartTooltipContent formatter={(v, n) => (n === "band" ? null : `${chartConfig[n as keyof typeof chartConfig]?.label ?? n} ${money(Number(v), unit)}`)} />} />
            <Area dataKey="band" stroke="none" fill="var(--violet)" fillOpacity={0.12} connectNulls={false} isAnimationActive={false} />
            <Line dataKey="value" stroke="var(--teal-500)" strokeWidth={2.5} dot={false} connectNulls={false} />
            <Line dataKey="mean" stroke="var(--violet)" strokeWidth={2.5} strokeDasharray="6 5" dot={false} />
          </ComposedChart>
        </ChartContainer>
        <p className="mt-3 text-[13px] text-muted-foreground">출처: {a.dataset.title}{a.dataset.provider ? ` (${a.dataset.provider})` : ""}. 월 합계.</p>
      </Panel>

      <div className="grid gap-4 sm:grid-cols-2">
        {a.cards.map((c, i) => {
          const meta = CARD_ICON[c.kind]
          const main = a.facts[c.facts[c.facts.length - 1]]
          return (
            <Panel key={i} className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <Pill tone={c.kind === "anomaly" ? "caution" : "teal"}>{meta.tag}</Pill>
                <Illust name={meta.name} fallback={meta.icon} className="size-10" />
              </div>
              <p className="text-[18px] leading-snug font-bold">{c.title}</p>
              {main && <Stat label={main.label} value={factText(main.value, main.unit)} />}
              {c.warnings.map((w) => (
                <p key={w} className="text-[14px] text-[var(--caution)]">{w}</p>
              ))}
              <p className="mt-auto font-mono text-[12px] text-[var(--grey-400)]">근거 {c.facts.join(", ")}</p>
            </Panel>
          )
        })}
      </div>

      {a.forecast ? (
        <Panel>
          <div className="flex items-start gap-4">
            <Illust name="forecast" fallback={TrendingUp} className="size-14" />
            <div className="flex-1 space-y-4">
              <div>
                <Pill tone="violet">추정</Pill>
                <p className="mt-2 text-[19px] font-bold leading-snug">
                  {period(a.forecast.periods[0])}은 {money(a.forecast.lower[0], unit)}에서 {money(a.forecast.upper[0], unit)} 사이로 추정돼요
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <Stat label="고른 방법" value={modelName(a.forecast.model)} />
                <Stat label="기준선보다 줄인 오차" value={`${a.forecast.improvement_pct}%`} tone="violet" />
                <Stat label="범위" value={`${a.forecast.level}%`} />
              </div>
              <p className="text-[14px] leading-relaxed text-muted-foreground">
                작년 같은 달을 그대로 쓰는 방법을 기준선으로 두고, 마지막 12개월로 시험해 더 나은 방법만 골랐어요. 과거 흐름이 이어진다는 가정이고, 원인을 설명하지 않아요.
              </p>
            </div>
          </div>
        </Panel>
      ) : (
        <Panel>
          <div className="flex items-center gap-4">
            <Illust name="gap" fallback={CalendarX} className="size-14" />
            <div>
              <p className="text-[17px] font-bold">이번에는 추정하지 않을게요</p>
              <p className="mt-1 text-[15px] leading-relaxed text-muted-foreground">{a.forecast_refusal}</p>
            </div>
          </div>
        </Panel>
      )}

      <JoinPanel dataset={a.dataset} value={a.value.name} />

      <CtaBar>
        <Button variant="soft" size="cta" className="flex-1 sm:flex-none" onClick={onBack}>
          이전
        </Button>
        <Button size="cta" className="flex-[2]" onClick={() => onNext(a)}>
          결과 한 장 만들기
        </Button>
      </CtaBar>
    </div>
  )
}

export function modelName(model: string) {
  return { SeasonalNaive: "작년 같은 달", AutoETS: "지수평활", AutoARIMA: "ARIMA" }[model] ?? model
}

function chartData(a: Analysis) {
  const rows: { period: string; value?: number | null; mean?: number; band?: [number, number] }[] = a.series.map((s) => ({ period: s.period, value: s.value }))
  if (a.forecast) {
    const last = rows[rows.length - 1]
    if (last?.value != null) {
      last.mean = last.value
      last.band = [last.value, last.value]
    }
    a.forecast.periods.forEach((p, i) => rows.push({ period: p, mean: a.forecast!.mean[i], band: [a.forecast!.lower[i], a.forecast!.upper[i]] }))
  }
  return rows
}
