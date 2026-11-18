import { FileCheck2, Printer, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { api, type Analysis } from "@/lib/api"
import { BigTitle, CtaBar, Illust, Panel, Pill } from "@/components/kit"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { factText, money, period } from "@/lib/format"
import { modelName } from "./Analyze"

export function Result({ analysis: a, onBack, onDone }: { analysis: Analysis; onBack: () => void; onDone: () => void }) {
  const unit = a.value.unit
  const today = new Date().toLocaleDateString("ko-KR")
  const conditions = (a.filters ?? []).map((f) => `${a.labels?.[f.column] ?? f.column} ${f.values.join(", ")}`)
  return (
    <div className="space-y-5">
      <BigTitle eyebrow="4단계 결과" title="결과 한 장이 준비됐어요" sub="보고서에 그대로 붙일 수 있게 정리했어요. 숫자마다 근거 번호가 있어요." />

      <Panel className="space-y-6 print:shadow-none">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[14px] text-muted-foreground">{a.dataset.title}<span className="ml-2 text-[var(--grey-400)]">{today} 작성</span></p>
            <h2 className="mt-1 text-[22px] font-bold tracking-[-0.02em]">{a.value.ko} 현황과 전망</h2>
            {conditions.length > 0 && <p className="mt-1 text-[15px] font-semibold text-primary">조건: {conditions.join(" / ")}</p>}
          </div>
          <Illust name="report" fallback={FileCheck2} className="size-14" />
        </div>

        <section>
          <h3 className="mb-2 text-[15px] font-bold text-[var(--grey-700)]">요약</h3>
          <ol className="list-decimal space-y-1.5 pl-5 text-[16px] leading-relaxed">
            {a.answer && a.answer.facts.length > 0 && (
              <li className="font-semibold">
                {a.answer.title}. <span className="font-mono text-[12px] font-normal text-[var(--grey-500)]">[{a.answer.facts.join(", ")}]</span>
              </li>
            )}
            {a.cards.slice(0, a.answer ? 2 : 3).map((c) => (
              <li key={c.title}>
                {c.title}. <span className="font-mono text-[12px] text-[var(--grey-500)]">[{c.facts.join(", ")}]</span>
              </li>
            ))}
            {a.forecast && (
              <li>
                {period(a.forecast.periods[0])}은 {money(a.forecast.lower[0], unit)}~{money(a.forecast.upper[0], unit)} 사이로 추정돼요({a.forecast.level}% 범위, {modelName(a.forecast.model)}). <span className="font-mono text-[12px] text-[var(--grey-500)]">[{a.forecast.fact}]</span>
              </li>
            )}
            {a.forecast_refusal && <li>추정하지 않았어요. {a.forecast_refusal}</li>}
          </ol>
        </section>

        <section>
          <h3 className="mb-2 text-[15px] font-bold text-[var(--grey-700)]">숫자 근거</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>번호</TableHead>
                <TableHead>내용</TableHead>
                <TableHead className="text-right">값</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.values(a.facts).map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="font-mono text-[13px]">{f.id}</TableCell>
                  <TableCell className="text-[15px]">{f.label}</TableCell>
                  <TableCell className="num text-right text-[15px] font-semibold">{factText(f.value, f.unit)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </section>

        <section className="space-y-1 text-[13px] leading-relaxed text-muted-foreground">
          <p>쓴 자료: {a.dataset.title}{a.dataset.provider ? ` (${a.dataset.provider})` : ""}{a.dataset.period ? `, ${a.dataset.period}` : ""}</p>
          {conditions.length > 0 && <p>조건: {conditions.join(" / ")}에 해당하는 행만 썼어요.</p>}
          <p>계산: 월 합계. 빈 칸은 0으로 세지 않았어요.{a.missing_months.length ? ` 비어 있는 달: ${a.missing_months.map(period).join(", ")}.` : ""}</p>
          {a.dataset.source === "dummy" && <Pill tone="caution">더미 자료로 만든 결과예요</Pill>}
        </section>
      </Panel>

      <CtaBar>
        <Button variant="soft" size="cta" className="flex-1 sm:flex-none" onClick={onBack}>
          이전
        </Button>
        <Button variant="soft" size="cta" className="flex-1" onClick={() => window.print()}>
          <Printer /> 인쇄, PDF
        </Button>
        <Button
          size="cta"
          className="flex-1"
          onClick={async () => {
            const r = await api.clearWorkspace()
            toast.success(r.removed ? `내 자료 ${r.removed}개를 지웠어요` : "지울 자료가 없어요")
            onDone()
          }}
        >
          <Trash2 /> 마치고 지우기
        </Button>
      </CtaBar>
    </div>
  )
}
