import { useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Download } from "lucide-react"
import type { Dataset, Understanding, UploadProfile } from "@/lib/api"
import { selectUpload, uploadSelection, UploadRequestError, type ExecutionSpec } from "@/lib/upload"
import { assignSelection, availableTimes, availableValues, columnLabel, EXAMPLE_CSV, hasAnalysisPair, initialSelection, nextSelectionStep, type ValueMeaning } from "@/lib/selection"
import { ActionFeedback, FormField } from "@/components/form"
import { Panel, Pill } from "@/components/kit"
import { Button } from "@/components/ui/button"
import { period } from "@/lib/format"

type Props = { dataset: Dataset; info: Understanding; onNext: () => void; onBack: () => void }

export function WebSelection(props: Props) {
  const profile = props.info.upload_profile
  if (!profile) return <Panel title="자료 정보를 다시 읽어 주세요"><ActionFeedback tone="caution" title="분석 안내를 불러오지 못했어요" description="CSV를 다시 넣으면 날짜와 분석할 숫자를 확인할 수 있어요." /><Button size="cta" className="mt-5 w-full" onClick={props.onBack}>CSV 다시 넣기</Button></Panel>
  return <SelectionForm key={props.dataset.id} {...props} profile={profile} />
}

function downloadExample() {
  const url = URL.createObjectURL(new Blob([EXAMPLE_CSV], { type: "text/csv;charset=utf-8" }))
  const link = document.createElement("a")
  link.href = url
  link.download = "한장제주-분석연습용-가상자료.csv"
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function UnsupportedSelection({ profile, onBack }: { profile: UploadProfile; onBack: () => void }) {
  const date = profile.columns.find(c => c.name === profile.recommended.time) ?? profile.columns.find(c => c.date_status === "valid")
  const noDates = profile.time_candidates.length === 0
  const badDate = profile.columns.find(c => c.date_status === "invalid" || c.date_status === "too_long")
  const badNumber = profile.columns.find(c => c.role === "measure" && c.additive !== false && c.numeric_status === "invalid")
  const title = noDates ? profile.date_status === "year_only" ? "이 파일에는 연도 정보만 있어요" : "분석할 날짜를 확인해 주세요" : "합계를 낼 숫자 항목을 찾지 못했어요"
  const description = noDates
    ? badDate?.date_status === "too_long" ? "날짜 범위가 100년을 넘어요. 분석할 기간을 줄여 다시 넣어 주세요."
      : badDate ? `‘${badDate.name}’의 ${badDate.invalid_date_rows.join(", ")}행을 날짜로 읽지 못했어요. CSV의 날짜를 확인한 뒤 다시 넣어 주세요.`
      : "현재는 월별 자료를 분석할 수 있어요. 연도와 월이 함께 있는 CSV를 넣어 주세요."
    : badNumber ? `‘${badNumber.name}’에 숫자로 읽지 못한 값이 있어요. CSV의 해당 항목을 확인한 뒤 다시 넣어 주세요.`
      : "월별 합계를 보려면 날짜 외에 금액이나 수량이 있는 항목이 필요해요. 날짜, 품목명과 코드만으로는 합계를 계산할 수 없어요."
  return <Panel title="이 자료에서 확인한 내용이에요">
    {date && <div className="mb-5 flex flex-wrap items-center gap-2 text-[16px]"><Pill tone="teal">날짜 항목</Pill><span>{date.name}</span>{date.first && date.last && <span className="text-[14px] text-muted-foreground">{period(date.first)} ~ {period(date.last)}</span>}</div>}
    <ActionFeedback tone="caution" title={title} description={description} />
    {noDates && <p className="mt-3 text-[14px] text-muted-foreground">분석할 수 있는 날짜 예: 202401, 2024-01, 2024-01-01</p>}
    <div className="mt-5 flex flex-col gap-3 sm:flex-row"><Button type="button" size="cta" className="flex-1" onClick={onBack}>다른 CSV 넣기</Button><Button type="button" size="cta" variant="soft" className="whitespace-normal" onClick={downloadExample}><Download aria-hidden className="size-4" />연습용 CSV 받기</Button></div>
    <p className="mt-3 text-[14px] leading-relaxed text-muted-foreground">연습용 CSV는 날짜와 판매액이 있는 가상 자료예요. 실제 통계가 아니에요.</p>
  </Panel>
}

function SelectionForm({ dataset, info, profile, onNext, onBack }: Props & { profile: UploadProfile }) {
  const queryClient = useQueryClient()
  const old = uploadSelection(dataset.id)
  const [draft, setDraft] = useState(() => initialSelection(profile, old))
  const [meanings, setMeanings] = useState<Record<string, ValueMeaning>>(() => old?.value === initialSelection(profile, old).value && old?.additive_confirmed ? { [old.value]: "sum" } : {})
  const meaning = meanings[draft.value] ?? ""
  const setMeaning = (value: ValueMeaning) => setMeanings(previous => ({ ...previous, [draft.value]: value }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<{ field?: string; message: string } | null>(null)
  const timeRef = useRef<HTMLSelectElement>(null)
  const valueRef = useRef<HTMLSelectElement>(null)
  const meaningRef = useRef<HTMLInputElement>(null)
  const step = nextSelectionStep(profile, draft, meaning, meanings)
  const valueColumn = profile.columns.find(c => c.name === draft.value)
  const dateColumn = profile.columns.find(c => c.name === draft.time)
  const options = (names: string[]) => info.columns.filter(c => names.includes(c.name)).map(c => <option key={c.name} value={c.name}>{columnLabel(c)}</option>)
  const focus = (field?: string) => {
    const element = field === "time" ? timeRef.current : field === "value" ? valueRef.current : meaningRef.current
    element?.focus()
    element?.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" })
  }
  useEffect(() => {
    if (!busy && error?.field === "time") timeRef.current?.focus()
    if (!busy && error?.field === "value") valueRef.current?.focus()
  }, [busy, error])

  if (!hasAnalysisPair(profile)) return <UnsupportedSelection profile={profile} onBack={onBack} />

  const change = (field: "time" | "value", name: string) => {
    const next = assignSelection(profile, draft, field, name)
    setDraft(next)
    setError(null)
  }
  const submit = async () => {
    if (busy) return
    if (step.target !== "run") {
      if (step.target === "back") onBack()
      else focus(step.target)
      return
    }
    setBusy(true); setError(null)
    try {
      const spec: ExecutionSpec = { ...draft, category: draft.category || null, additive_confirmed: valueColumn?.additive === true || meaning === "sum", intent: "overview", filters: [], period_n: 0, horizon: 6, run_forecast: false }
      await selectUpload(dataset.id, spec)
      await queryClient.invalidateQueries({ queryKey: ["understand", dataset.id] })
      queryClient.removeQueries({ queryKey: ["analyze", dataset.id] })
      onNext()
    } catch (e) {
      setError({ field: e instanceof UploadRequestError ? e.field : undefined, message: (e as Error).message })
    } finally { setBusy(false) }
  }

  return <Panel title="어떤 흐름을 볼까요?" action={<Pill tone="teal">월별 분석</Pill>}>
    <p className="mb-6 text-[16px] leading-relaxed text-muted-foreground">날짜를 먼저 확인하고, 함께 볼 금액이나 수량을 골라 주세요.</p>
    <form className="data-form" onSubmit={event => { event.preventDefault(); void submit() }} aria-busy={busy}>
      <div className="space-y-6">
        <FormField id="web-time" label="기준으로 볼 날짜" description={dateColumn?.first && dateColumn.last ? `${period(dateColumn.first)}부터 ${period(dateColumn.last)}까지 월별로 모아 볼 수 있어요.` : "날짜로 읽을 수 있는 항목을 골라 주세요."} error={error?.field === "time" ? error.message : undefined}>
          {props => <select {...props} ref={timeRef} className="form-control" value={draft.time} disabled={busy} onChange={e => change("time", e.target.value)}><option value="">날짜 항목 고르기</option>{options(availableTimes(profile))}</select>}
        </FormField>
        <FormField id="web-value" label="분석할 금액이나 수량" description={valueColumn?.additive === true ? `월별 합계로 계산해요.${draft.unit ? ` 단위는 ${draft.unit}이에요.` : ""}` : "각 행에 금액이나 수량이 들어 있는 항목을 골라 주세요."} error={error?.field === "value" ? error.message : undefined}>
          {props => <select {...props} ref={valueRef} className="form-control" value={draft.value} disabled={busy} onChange={e => change("value", e.target.value)}><option value="">금액이나 수량 고르기</option>{options(availableValues(profile, draft.time))}</select>}
        </FormField>
        {draft.value && valueColumn?.additive == null && <fieldset className="rounded-xl border border-border p-4" disabled={busy}>
          <legend className="px-1 text-[16px] font-semibold">‘{info.columns.find(c => c.name === draft.value)?.ko ?? draft.value}’의 뜻 확인</legend>
          <p className="mb-3 text-[14px] leading-relaxed text-muted-foreground">합계를 계산해도 되는 숫자인지 확인이 필요해요.</p>
          <label className="flex min-h-11 items-center gap-3 text-[15px]"><input ref={meaningRef} type="radio" name="value-meaning" checked={meaning === "sum"} onChange={() => { setMeaning("sum"); setError(null) }} />각 행의 금액이나 수량이에요</label>
          <label className="flex min-h-11 items-center gap-3 text-[15px]"><input type="radio" name="value-meaning" checked={meaning === "nonadditive"} onChange={() => { setMeaning("nonadditive"); setError(null) }} />평균이나 비율이에요</label>
        </fieldset>}
      </div>
      <details className="my-6 border-t border-border pt-3"><summary className="cursor-pointer py-3 text-[15px] font-medium">비교 항목과 단위 바꾸기 <span className="font-normal text-muted-foreground">선택</span></summary>
        <div className="mt-3 grid gap-5 sm:grid-cols-2">
          <FormField id="web-category" label="비교할 항목" optional description="지역이나 품목별로 나눠 볼 수 있어요.">{props => <select {...props} className="form-control" value={draft.category} disabled={busy} onChange={e => { setDraft({ ...draft, category: e.target.value }); setError(null) }}><option value="">전체로 보기</option>{options(profile.category_candidates.filter(name => name !== draft.time && name !== draft.value))}</select>}</FormField>
          <FormField id="web-unit" label="숫자의 단위" optional description="단위 표기만 바꿔요. 숫자의 크기는 바꾸지 않아요.">{props => <input {...props} className="form-control" maxLength={20} value={draft.unit} disabled={busy} placeholder="예: 원, 천원, 건" onChange={e => { setDraft({ ...draft, unit: e.target.value }); setError(null) }} />}</FormField>
        </div>
      </details>
      <ActionFeedback tone={error ? "danger" : step.target === "run" ? "positive" : step.target === "back" || meaning === "nonadditive" ? "caution" : "info"} title={busy ? "자료를 확인하는 중이에요" : error ? "분석 조건을 확인해 주세요" : step.title} description={busy ? "확인이 끝나면 월별 흐름을 보여드릴게요." : error ? error.message : step.message} action={error?.field === "time" && profile.recommended.time && draft.time !== profile.recommended.time ? { label: "추천 날짜로 바꾸기", onClick: () => change("time", profile.recommended.time!) } : undefined} />
      <div className="mt-5 flex flex-col gap-3 sm:flex-row-reverse"><Button type="submit" size="cta" className="flex-1 whitespace-normal" disabled={busy}>{busy ? "확인하는 중…" : step.label}</Button>{step.target !== "back" && <Button type="button" variant="soft" size="cta" disabled={busy} onClick={onBack}>다른 CSV 넣기</Button>}</div>
      <p className="mt-3 text-[14px] text-muted-foreground">예측은 월별 흐름을 본 뒤 추가할 수 있어요.</p>
    </form>
  </Panel>
}
