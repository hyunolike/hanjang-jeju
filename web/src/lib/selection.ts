import type { Analysis, ColumnInfo, UploadProfile } from "./api"
import type { ExecutionSpec } from "./upload"

export function columnLabel(c: Pick<ColumnInfo, "name" | "ko">) {
  return !c.ko || c.ko === c.name ? c.name : `${c.ko} (${c.name})`
}

export function selectedUnit(profile: UploadProfile, value: string) {
  return profile.columns.find(c => c.name === value)?.unit ?? ""
}

export function initialSelection(profile: UploadProfile, old?: Partial<ExecutionSpec>) {
  const times = availableTimes(profile)
  const time = old?.time && times.includes(old.time) ? old.time : profile.recommended.time && times.includes(profile.recommended.time) ? profile.recommended.time : ""
  const candidates = availableValues(profile, time)
  const value = old?.value && candidates.includes(old.value) ? old.value : profile.recommended.value && candidates.includes(profile.recommended.value) ? profile.recommended.value : candidates.length === 1 ? candidates[0] : ""
  const category = old?.category && profile.category_candidates.includes(old.category) && old.category !== time && old.category !== value ? old.category : ""
  const unit = old?.value === value ? old.unit ?? selectedUnit(profile, value) : selectedUnit(profile, value)
  return { time, value, category, unit }
}

export function selectionReady(profile: UploadProfile, time: string, value: string, confirmed: boolean) {
  const column = profile.columns.find(c => c.name === value)
  return profile.date_status === "ready" && time !== value && profile.time_candidates.includes(time) && availableValues(profile, time).includes(value) && !!column && (column.additive === true || (column.additive == null && confirmed))
}

export type SelectionDraft = { time: string; value: string; category: string; unit: string }
export type ReusableSelection = Pick<SelectionDraft, 'time' | 'value' | 'category' | 'unit'>

export function reusableSelection(previous: ReusableSelection, profile: UploadProfile) {
  const missing: string[] = []
  const time = profile.time_candidates.includes(previous.time) ? previous.time : ''
  if (!time && previous.time) missing.push(previous.time)
  const column = profile.columns.find(c => c.name === previous.value)
  const value = availableValues(profile, time).includes(previous.value) && column?.additive !== false && previous.value !== time ? previous.value : ''
  if (!value && previous.value) missing.push(previous.value)
  const category = previous.category && profile.category_candidates.includes(previous.category) && previous.category !== time && previous.category !== value ? previous.category : ''
  if (!category && previous.category) missing.push(previous.category)
  return { draft: { time, value, category, unit: value ? previous.unit : '' }, missing }
}
export type ValueMeaning = "" | "sum" | "nonadditive"

export function availableValues(profile: UploadProfile, time: string) {
  return profile.value_candidates.filter(name => name !== time && !["time", "category", "region"].includes(profile.columns.find(c => c.name === name)?.role ?? "unknown"))
}

export function hasAnalysisPair(profile: UploadProfile) {
  return availableTimes(profile).length > 0
}

export function availableTimes(profile: UploadProfile) {
  return profile.time_candidates.filter(time => availableValues(profile, time).length > 0)
}

export function assignSelection(profile: UploadProfile, old: SelectionDraft, field: "time" | "value", name: string): SelectionDraft {
  if (field === "time") return name ? initialSelection(profile, { ...old, time: name }) : { ...old, time: "" }
  if (!availableValues(profile, old.time).includes(name)) return { ...old, value: "", unit: "" }
  return { ...old, value: name, unit: selectedUnit(profile, name), category: old.category === name ? "" : old.category }
}

export function nextSelectionStep(profile: UploadProfile, draft: SelectionDraft, meaning: ValueMeaning, knownMeanings: Record<string, ValueMeaning> = {}) {
  if (!hasAnalysisPair(profile)) return { target: "back", label: "다른 CSV 넣기", title: "이 자료로 가능한 분석을 확인해 주세요", message: "월별 흐름을 보려면 서로 다른 날짜와 금액·수량 항목이 필요해요." } as const
  if (!availableTimes(profile).includes(draft.time)) return { target: "time", label: "날짜 선택하기", title: "기준으로 볼 날짜를 골라 주세요", message: "분석할 숫자와 함께 볼 수 있는 날짜를 골라 주세요." } as const
  if (!availableValues(profile, draft.time).includes(draft.value)) return { target: "value", label: "분석할 값 선택하기", title: "분석할 금액이나 수량을 골라 주세요", message: "선택한 날짜와 함께 볼 숫자 항목이 필요해요." } as const
  if (meaning === "nonadditive" && profile.columns.find(c => c.name === draft.value)?.additive == null) {
    const alternatives = availableValues(profile, draft.time).filter(name => name !== draft.value && knownMeanings[name] !== "nonadditive")
    if (!alternatives.length) return { target: "back", label: "다른 CSV 넣기", title: "이 자료는 합계로 분석하기 어려워요", message: "분석할 수 있는 다른 금액이나 수량 항목이 없어요. 해당 숫자가 있는 CSV를 넣어 주세요." } as const
    return { target: "value", label: "다른 값 선택하기", title: "평균과 비율은 합계를 낼 수 없어요", message: "각 행의 금액이나 수량이 있는 다른 항목을 골라 주세요." } as const
  }
  if (!selectionReady(profile, draft.time, draft.value, meaning === "sum")) return { target: "meaning", label: "숫자의 뜻 확인하기", title: "이 숫자가 어떤 값인지 확인해 주세요", message: "각 행의 금액·수량인지, 평균·비율인지 선택하면 다음으로 갈 수 있어요." } as const
  return { target: "run", label: "월별 흐름 보기", title: "분석할 준비가 됐어요", message: "확인한 날짜와 숫자로 월별 합계를 계산해요." } as const
}

export function canOfferForecast(a: Pick<Analysis, "execution" | "filters">) {
  return a.execution?.mode === "manual" && !a.execution.tools.includes("forecast") && !a.filters.length
}

export const EXAMPLE_CSV = "\uFEFF날짜,판매액 (원),업종명\n202401,100000,가상업종A\n202402,120000,가상업종A\n202403,110000,가상업종A\n202404,140000,가상업종A\n202405,130000,가상업종A\n202406,150000,가상업종A\n"
