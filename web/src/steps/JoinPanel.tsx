import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { Puzzle } from "lucide-react"
import { api, type Dataset } from "@/lib/api"
import { Illust, Panel, Pill, Stat } from "@/components/kit"
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select"
import { period } from "@/lib/format"

/** 다른 자료를 월 단위로 붙이고, 붙지 않은 달을 먼저 보여 준다 (명세 J03, 기획안 13.4). */
export function JoinPanel({ dataset, value }: { dataset: Dataset; value: string }) {
  const list = useQuery({ queryKey: ["datasets"], queryFn: api.datasets })
  const [other, setOther] = useState<Dataset | null>(null)
  const join = useMutation({
    mutationFn: async (right: Dataset) => {
      const u = await api.understand(right.id)
      const measure = u.columns.find((c) => c.name === u.selection?.value && c.role === "measure") ?? u.columns.find((c) => c.role === "measure" && c.additive) ?? u.columns.find((c) => c.role === "measure")
      if (!u.time_column || !measure) throw new Error("이 자료에서 시간이나 값 열을 찾지 못했어요.")
      return { result: await api.join(dataset.id, value, right.id, measure.name), measure: measure.ko }
    },
  })
  const candidates = (list.data ?? []).filter((d) => d.id !== dataset.id && d.id !== "hub-793" && d.id !== "hub-830")
  const r = join.data?.result
  const corr = r ? Object.values(r.facts)[0] : undefined

  return (
    <Panel title="다른 자료와 함께 보기" action={<Illust name="join" fallback={Puzzle} className="size-11" />}>
      <Select
        value={other?.id ?? ""}
        onValueChange={(id) => {
          const ds = candidates.find((d) => d.id === id)
          if (ds) {
            setOther(ds)
            join.mutate(ds)
          }
        }}
      >
        <SelectTrigger className="h-11 w-full rounded-xl px-4 text-[15px] font-semibold">
          <span>{other ? other.title : "붙여 볼 자료를 골라 주세요"}</span>
        </SelectTrigger>
        <SelectContent>
          {candidates.map((d) => (
            <SelectItem key={d.id} value={d.id}>
              {d.title}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {join.isPending && <p className="mt-4 text-[15px] text-muted-foreground">달을 맞춰 붙이는 중이에요…</p>}
      {join.error && <p className="mt-4 text-[15px] text-destructive">{(join.error as Error).message}</p>}
      {r && (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <Stat label="붙은 달" value={`${r.report.matched_rows}개월`} />
            <Stat label="못 붙은 달" value={`${r.report.unmatched_rows}개월`} />
            <Stat label="함께 움직인 정도" value={corr && typeof corr.value === "number" && Number.isFinite(corr.value) ? corr.value.toFixed(2) : "계산 불가"} />
          </div>
          {r.correlation_refusal && <p className="text-[14px] text-muted-foreground">{r.correlation_refusal}</p>}
          {r.report.unmatched_keys.length > 0 && (
            <div className="rounded-2xl bg-[var(--caution-50)] p-4 text-[15px] leading-relaxed text-[var(--caution)]">
              <b>{r.report.unmatched_keys.map((k) => period(`${k.slice(0, 4)}-${k.slice(4)}`)).join(", ")}</b>은 {other?.title}에 없어서 붙이지 못했어요. 이 달은 비교에서 빠져요.
            </div>
          )}
          <p className="text-[14px] text-muted-foreground">
            {join.data?.measure} 기준이에요. <Pill tone="grey">{r.note}</Pill>
          </p>
        </div>
      )}
    </Panel>
  )
}
