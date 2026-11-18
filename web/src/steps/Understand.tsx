import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CalendarX, Check, Sparkles } from "lucide-react"
import { api, type ColumnInfo, type Dataset } from "@/lib/api"
import { BigTitle, CtaBar, Illust, Panel, Pill } from "@/components/kit"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { period } from "@/lib/format"

const ROLE: Record<ColumnInfo["role"], { label: string; tone: "teal" | "grey" | "violet" | "caution" | "positive" }> = {
  time: { label: "시간", tone: "violet" },
  region: { label: "지역", tone: "teal" },
  category: { label: "분류", tone: "grey" },
  measure: { label: "값", tone: "positive" },
  unknown: { label: "모름", tone: "caution" },
}

export function Understand({ dataset, onBack, onNext }: { dataset: Dataset; onBack: () => void; onNext: () => void }) {
  const q = useQuery({ queryKey: ["understand", dataset.id], queryFn: () => api.understand(dataset.id) })
  if (q.isLoading) return <Skeleton className="h-[520px] rounded-[22px]" />
  if (q.error || !q.data) return <Panel><p className="text-destructive">{(q.error as Error)?.message}</p></Panel>
  const u = q.data
  const name = u.recognition.title ?? "알 수 없는 표"
  const sum = (k: "missing" | "none" | "masked" | "trimmed") => u.columns.reduce((acc, c) => acc + c[k], 0)

  const done: string[] = [`${u.clean.encoding === "cp949" ? "CP949" : "UTF-8"} 글자로 읽었어요`]
  if (u.clean.subtotal_rows) done.push(`소계 행 ${u.clean.subtotal_rows.toLocaleString()}개를 따로 뺐어요. 그대로 더하면 두 번 세요`)
  if (sum("trimmed")) done.push(`글자 앞뒤 공백 ${sum("trimmed").toLocaleString()}곳을 정리했어요`)
  if (sum("masked")) done.push(`가려진 값 ${sum("masked").toLocaleString()}칸은 0이 아니라 '알 수 없음'으로 둬요`)
  if (sum("missing") + sum("none")) done.push(`빈 값 ${(sum("missing") + sum("none")).toLocaleString()}칸은 계산에서 빼요`)
  const notes = u.columns.filter((c) => c.note)
  const gaps = u.months.missing ?? []

  return (
    <div className="space-y-5">
      <BigTitle
        eyebrow="2단계 이해"
        title={u.recognition.table_id ? <>이 자료는<br className="sm:hidden" /> <span className="text-primary">{name}</span>이에요</> : "어떤 표인지 알아보지 못했어요"}
        sub={
          u.months.first
            ? `${period(u.months.first)}부터 ${period(u.months.last!)}까지 ${u.months.count}개월, ${u.clean.rows.toLocaleString()}행이에요.`
            : `${u.clean.rows.toLocaleString()}행이에요.`
        }
      />

      <Panel title="이렇게 정리했어요" action={<Illust name="clean" fallback={Sparkles} className="size-11" />}>
        <ul className="space-y-3">
          {done.map((t) => (
            <li key={t} className="flex gap-3 text-[16px] leading-relaxed">
              <Check className="mt-0.5 size-5 shrink-0 text-primary" />
              {t}
            </li>
          ))}
          {notes.map((c) => (
            <li key={c.name} className="flex gap-3 text-[16px] leading-relaxed">
              <AlertTriangle className="mt-0.5 size-5 shrink-0 text-[var(--caution)]" />
              <span>
                <b>{c.ko}</b>: {c.note}
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      {gaps.length > 0 && (
        <Panel className="border border-[var(--caution-50)]">
          <div className="flex items-center gap-4">
            <Illust name="gap" fallback={CalendarX} className="size-14" />
            <div>
              <p className="text-[17px] font-bold">비어 있는 달이 {gaps.length}개 있어요</p>
              <p className="mt-1 text-[15px] text-muted-foreground">{gaps.map(period).join(", ")}. 채워 넣지 않고 그대로 둘게요.</p>
            </div>
          </div>
        </Panel>
      )}

      <Panel title="열마다 뜻을 붙였어요">
        <div className="-mx-2 overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>열</TableHead>
                <TableHead>뜻</TableHead>
                <TableHead>역할</TableHead>
                <TableHead>단위</TableHead>
                <TableHead>더해도 되나요</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {u.columns.map((c) => (
                <TableRow key={c.name}>
                  <TableCell className="font-mono text-[13px] text-muted-foreground">{c.name}</TableCell>
                  <TableCell className="text-[15px] font-medium">{c.ko}</TableCell>
                  <TableCell>
                    <Pill tone={ROLE[c.role].tone}>{ROLE[c.role].label}</Pill>
                  </TableCell>
                  <TableCell className="text-[15px]">{c.unit || "-"}</TableCell>
                  <TableCell className="text-[15px]">{c.role !== "measure" ? "-" : c.additive ? "네" : <span className="text-[var(--caution)]">아니요</span>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Panel>

      <CtaBar>
        <Button variant="soft" size="cta" className="flex-1 sm:flex-none" onClick={onBack}>
          다른 자료
        </Button>
        <Button size="cta" className="flex-[2]" onClick={onNext} disabled={!u.time_column}>
          분석하기
        </Button>
      </CtaBar>
    </div>
  )
}
