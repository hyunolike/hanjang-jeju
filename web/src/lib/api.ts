export type Dataset = { id: string; title: string; source: "hub" | "dummy" | "upload"; provider: string; period: string }

export type ColumnInfo = {
  name: string
  ko: string
  role: "time" | "region" | "category" | "measure" | "unknown"
  unit: string
  additive: boolean | null
  note: string
  missing: number
  none: number
  masked: number
  trimmed: number
}

export type Understanding = {
  upload_profile?: UploadProfile
  dataset: Dataset
  recognition: { table_id: string | null; title: string | null; source: string | null; score: number; unknown_columns: string[] }
  clean: { encoding: string; rows: number; subtotal_rows: number }
  columns: ColumnInfo[]
  time_column: string | null
  months: { first?: string; last?: string; count?: number; missing?: string[] }
  preview: Record<string, string>[]
}

export type UploadProfile = {
  analysis_status?: "available" | "no_dates" | "no_values"
  date_status: "ready" | "year_only" | "invalid" | "missing"
  time_candidates: string[]; value_candidates: string[]; category_candidates: string[]
  recommended: { time: string | null; value: string | null }
  columns: { name: string; date_status: "valid" | "year_only" | "invalid" | "not_date" | "too_long"; first: string | null; last: string | null; month_count: number; invalid_date_rows: number[]; invalid_numeric_rows: number[]; numeric_status: "valid" | "invalid" | "empty"; role: ColumnInfo["role"]; unit: string; additive: boolean | null }[]
}

export type Fact = { id: string; kind: string; value: number; unit: string; label: string; basis: Record<string, unknown> }
export type Card = { kind: "change" | "driver" | "anomaly" | "season"; title: string; score: number; facts: string[]; warnings: string[] }
export type Forecast = {
  model: string
  baseline_mae: number
  model_mae: number
  improvement_pct: number
  horizon: number
  periods: string[]
  mean: number[]
  lower: number[]
  upper: number[]
  level: number
  fact: string
}

export type Analysis = {
  execution?: { mode: "manual" | "agent"; question: string | null; tools: string[]; verified: boolean }
  dataset: Dataset
  error?: string
  value: { name: string; ko: string; unit: string; additive: boolean | null; note: string }
  category: string | null
  options: { values: string[]; categories: string[] }
  series: { period: string; value: number | null }[]
  cards: Card[]
  facts: Record<string, Fact>
  forecast: Forecast | null
  forecast_refusal: string | null
  missing_months: string[]
  answer: { intent: Intent; title: string; facts: string[]; warnings: string[] } | null
  filters: { column: string; values: string[] }[]
  labels?: Record<string, string>
}

export type Plan = { intent: Intent; value: string; group_by: string | null; filters: { column: string; values: string[] }[]; period_n: number; horizon: number }
export type Intent = "overview" | "compare" | "share" | "rank" | "forecast"
export type PlanResult = {
  fallback?: boolean
  reason?: string
  plan: Plan
  unresolved: { column: string; text: string; choices?: string[] }[]
  needs: { table_id: string; title: string; reason: string; period: string }[]
  unsupported: string[]
  blocked: string[]
  labels: Record<string, string>
  latency_ms: number
  model: string
}
export type SelfCheck = {
  items: { key: string; label: string; ok: boolean; detail: string; optional?: boolean }[]
  workspace: string
  startup_cleared: number
  auto_delete: boolean
}
export type ModelStatus = { available: boolean; ready: boolean; model: string; backend?: "pack" | "ollama"; loading?: boolean; pack_error?: boolean; reason?: string }
export type AnalyzeOptions = { value?: string; category?: string | null; intent?: Intent; filters?: Plan["filters"]; period_n?: number; horizon?: number; agent_digest?: string; run_forecast?: boolean }

export type JoinResult = {
  report: { left_rows: number; matched_rows: number; unmatched_rows: number; unmatched_keys: string[]; multi_match_keys: string[] }
  facts: Record<string, Fact>
  note: string
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? "서버에 연결하지 못했어요.")
  return res.json()
}

/** 공개 웹 체험판: 서버 없이 미리 계산한 결과(static-api)를 읽는다. 올리기는 막는다. */
export const STATIC = import.meta.env.VITE_STATIC === "1"
export const WEB_UPLOAD = import.meta.env.VITE_WEB_UPLOAD === "1"
const S = "/static-api"
const k = (v?: string | null) => v || "_"

const staticApi = {
  datasets: () => get<Dataset[]>(`${S}/datasets.json`),
  understand: (id: string) => get<Understanding>(`${S}/understand/${id}.json`),
  analyze: (id: string, o: AnalyzeOptions = {}) => get<Analysis>(`${S}/analyze/${id}/${k(o.value)}__${k(o.category)}.json`),
  model: async (): Promise<ModelStatus> => ({ available: false, ready: false, model: "", reason: "공개 체험판" }),
  plan: async (_id: string, _q: string): Promise<PlanResult> => {
    void _id; void _q
    throw new Error("질문은 PC용 프로그램에서 쓸 수 있어요.")
  },
  join: (left: string, leftValue: string, right: string) => get<JoinResult>(`${S}/join/${left}/${leftValue}/${right}.json`),
  upload: async (_file: File): Promise<Dataset> => {
    void _file
    throw new Error("공개 체험판에서는 자료를 올릴 수 없어요. PC용 프로그램을 써 주세요.")
  },
  clearWorkspace: async () => ({ removed: 0 }),
  selfcheck: async (): Promise<SelfCheck> => ({ items: [], workspace: "", startup_cleared: 0, auto_delete: true }),
  setAutoDelete: async (auto_delete: boolean) => ({ auto_delete }),
}

const serverApi = {
  datasets: () => get<Dataset[]>("/api/datasets"),
  understand: (id: string) => get<Understanding>(`/api/datasets/${id}/understand`),
  analyze: (id: string, o: AnalyzeOptions = {}) => {
    const q = new URLSearchParams()
    if (o.value) q.set("value", o.value)
    if (o.category) q.set("category", o.category)
    if (o.intent) q.set("intent", o.intent)
    if (o.filters?.length) q.set("filters", JSON.stringify(o.filters))
    if (o.period_n) q.set("period_n", String(o.period_n))
    if (o.horizon) q.set("horizon", String(o.horizon))
    return get<Analysis>(`/api/datasets/${id}/analyze?${q}`)
  },
  model: () => get<ModelStatus>("/api/model"),
  plan: async (id: string, question: string) => {
    const res = await fetch(`/api/datasets/${id}/plan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) })
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? "계획을 만들지 못했어요.")
    return (await res.json()) as PlanResult
  },
  join: (left: string, leftValue: string, right: string, rightValue: string) =>
    get<JoinResult>(`/api/join?${new URLSearchParams({ left, left_value: leftValue, right, right_value: rightValue })}`),
  upload: async (file: File) => {
    const body = new FormData()
    body.append("file", file)
    const res = await fetch("/api/datasets", { method: "POST", body })
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? "파일을 넣지 못했어요.")
    return (await res.json()) as Dataset
  },
  clearWorkspace: async () => (await fetch("/api/workspace", { method: "DELETE" })).json() as Promise<{ removed: number }>,
  selfcheck: () => get<SelfCheck>("/api/selfcheck"),
  setAutoDelete: async (auto_delete: boolean) =>
    (await fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ auto_delete }) })).json() as Promise<{ auto_delete: boolean }>,
}

import { analyzeUpload, clearUpload, uploadFile, uploadInfo, webModel } from "./upload"

const baseApi = STATIC ? staticApi : serverApi
export const api = WEB_UPLOAD ? {
  ...baseApi,
  upload: uploadFile,
  understand: (id: string) => id.startsWith("web-") ? uploadInfo(id) : baseApi.understand(id),
  analyze: (id: string, choice: AnalyzeOptions = {}) => id.startsWith("web-") ? analyzeUpload(id, choice) : baseApi.analyze(id, choice),
  model: webModel,
  clearWorkspace: async () => clearUpload(),
} : baseApi
