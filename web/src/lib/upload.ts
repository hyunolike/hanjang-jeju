import type { Analysis, AnalyzeOptions, Dataset, ModelStatus, PlanResult, Understanding } from "./api"

export type ExecutionSpec = {
  time: string; value: string; category: string | null; unit: string; additive_confirmed: boolean
  intent: "overview" | "compare" | "share" | "rank" | "forecast"
  filters: { column: string; values: string[] }[]; period_n: number; horizon: number; run_forecast: boolean; tools?: string[]
}
export type WebPlan = PlanResult & { execution_spec: ExecutionSpec; input_digest: string }
type Entry = { file: File; dataset: Dataset; info?: Understanding; spec?: ExecutionSpec; plan?: WebPlan; question?: string; revision: number }
let current: Entry | undefined
const running = new Set<AbortController>()
export const MAX_UPLOAD_BYTES = 3 * 1024 * 1024

export class UploadRequestError extends Error {
  field: string | undefined
  constructor(message: string, issue?: { field?: string }) {
    super(message)
    this.field = issue?.field
  }
}

export function clearUpload() {
  const removed = current ? 1 : 0
  current = undefined
  running.forEach(controller => controller.abort())
  running.clear()
  return { removed }
}

function entry(id: string): Entry {
  if (!current || current.dataset.id !== id) throw new Error("자료가 바뀌었거나 지워졌어요. CSV를 다시 넣어 주세요.")
  return current
}

async function post<T>(path: string, e: Entry, fields: Record<string, string>): Promise<T> {
  const revision = e.revision
  const body = new FormData()
  body.set("file", e.file)
  Object.entries(fields).forEach(([key, value]) => body.set(key, value))
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 240_000)
  running.add(controller)
  try {
    const res = await fetch(`/api/web/${path}`, { method: "POST", body, signal: controller.signal, cache: "no-store" })
    const json = await res.json().catch(() => null)
    if (!res.ok) throw new UploadRequestError(typeof json?.detail === "string" ? json.detail : "서버에서 자료를 처리하지 못했어요. 잠시 뒤 다시 시도해 주세요.", json?.issue)
    if (!current || current !== e || revision !== e.revision) throw new Error("자료나 질문이 변경되어 이전 요청을 멈췄어요.")
    return json as T
  } catch (error) {
    if (controller.signal.aborted) throw new Error("분석이 취소됐거나 시간이 초과됐어요. 다시 시도해 주세요.")
    throw error
  } finally {
    clearTimeout(timeout)
    running.delete(controller)
  }
}

export async function uploadFile(file: File): Promise<Dataset> {
  if (!file.name.toLowerCase().endsWith(".csv")) throw new Error("CSV 파일만 넣을 수 있어요.")
  if (file.size > MAX_UPLOAD_BYTES) throw new Error("CSV는 3MiB 이하로 넣어 주세요.")
  clearUpload()
  const dataset: Dataset = { id: `web-${crypto.randomUUID()}`, title: file.name, source: "upload", provider: "직접 넣은 CSV", period: "" }
  const e: Entry = { file, dataset, revision: 0 }
  current = e
  try {
    const info = await post<Understanding>("understand", e, {})
    e.info = { ...info, dataset }
    return dataset
  } catch (error) {
    if (current === e) clearUpload()
    throw error
  }
}

export function uploadInfo(id: string): Promise<Understanding> {
  const e = entry(id)
  if (!e.info) throw new Error("CSV를 다시 넣어 주세요.")
  return Promise.resolve(e.info)
}

export function uploadSelection(id: string): ExecutionSpec | undefined { return entry(id).spec }

export async function selectUpload(id: string, spec: ExecutionSpec) {
  const e = entry(id)
  e.revision += 1
  e.plan = undefined
  e.question = undefined
  const info = await post<Understanding>("understand", e, { options: JSON.stringify(spec) })
  e.spec = spec
  e.info = { ...info, dataset: e.dataset }
}

export function discardPlan(id: string) {
  const e = entry(id)
  e.revision += 1
  e.plan = undefined
  e.question = undefined
}

export async function planUpload(id: string, question: string, edited?: ExecutionSpec): Promise<WebPlan> {
  const e = entry(id)
  if (!e.spec) throw new Error("분석할 날짜와 값 열을 먼저 골라 주세요.")
  e.revision += 1
  e.question = question
  e.plan = undefined
  const result = await post<WebPlan>("plan", e, { options: JSON.stringify(e.spec), question, ...(edited ? { edited_spec: JSON.stringify(edited) } : {}) })
  e.plan = undefined // 확인 버튼을 누르기 전까지 실행하지 않는다.
  e.question = question
  return result
}

export function confirmUploadPlan(id: string, plan: WebPlan, question: string) {
  const e = entry(id)
  if (!plan.input_digest || plan.blocked?.length || question !== e.question) throw new Error("변경한 질문과 계획을 다시 확인해 주세요.")
  e.plan = plan
}

export async function analyzeUpload(id: string, choice: AnalyzeOptions): Promise<Analysis> {
  const e = entry(id)
  if (!e.spec) throw new Error("분석할 열을 먼저 골라 주세요.")
  if (choice.agent_digest && (!e.plan || choice.agent_digest !== e.plan.input_digest)) throw new Error("이전 계획을 사용할 수 없어요. 질문과 계획을 다시 확인해 주세요.")
  const fields: Record<string, string> = e.plan && choice.agent_digest === e.plan.input_digest
    ? { mode: "agent", question: e.question!, execution_spec: JSON.stringify(e.plan.execution_spec), input_digest: e.plan.input_digest, confirmed: "true" }
    : { mode: "manual", options: JSON.stringify({ ...e.spec, ...(choice.value ? { value: choice.value } : {}), ...(choice.category !== undefined ? { category: choice.category } : {}), ...(choice.run_forecast !== undefined ? { run_forecast: choice.run_forecast, tools: [] } : {}) }) }
  if (!choice.agent_digest) e.plan = undefined
  const result = await post<Analysis>("analyze", e, fields)
  return { ...result, dataset: e.dataset }
}

export async function webModel(): Promise<ModelStatus> {
  const res = await fetch("/api/web/capabilities", { cache: "no-store" })
  if (!res.ok) throw new Error("공개 분석 서버에 연결하지 못했어요.")
  return res.json()
}
