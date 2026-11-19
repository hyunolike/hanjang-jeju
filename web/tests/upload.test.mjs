import { test, afterEach } from "node:test"
import assert from "node:assert/strict"
import { uploadFile, selectUpload, planUpload, confirmUploadPlan, analyzeUpload, discardPlan, clearUpload } from "../src/lib/upload.ts"

const info = { columns: [], clean: {}, months: {} }
const spec = { time: "date", value: "sale_amt", category: null, unit: "원", additive_confirmed: true, intent: "overview", filters: [], period_n: 0, horizon: 6, run_forecast: false }
const fakePlan = { execution_spec: spec, input_digest: "digest", blocked: [], unresolved: [], needs: [], unsupported: [] }
const file = () => new File(["date,sale_amt\n202401,10"], "mine.csv")
afterEach(() => clearUpload())
const response = value => Promise.resolve(new Response(JSON.stringify(value), { status: 200 }))

test("reselecting a file creates a fresh cache identity", async () => {
  globalThis.fetch = () => response(info)
  const a = await uploadFile(file())
  const b = await uploadFile(file())
  assert.notEqual(a.id, b.id)
})

test("changed question cannot silently run an old plan as manual analysis", async () => {
  globalThis.fetch = url => response(url.endsWith("plan") ? fakePlan : info)
  const ds = await uploadFile(file())
  await selectUpload(ds.id, spec)
  const p = await planUpload(ds.id, "흐름은?")
  confirmUploadPlan(ds.id, p, "흐름은?")
  discardPlan(ds.id)
  await assert.rejects(analyzeUpload(ds.id, { agent_digest: "digest" }), /계획/)
})

test("late model response does not restore a discarded question", async () => {
  let release
  globalThis.fetch = url => url.endsWith("plan") ? new Promise(resolve => { release = () => resolve(new Response(JSON.stringify(fakePlan))) }) : response(info)
  const ds = await uploadFile(file())
  await selectUpload(ds.id, spec)
  const planning = planUpload(ds.id, "old question")
  discardPlan(ds.id)
  release()
  await assert.rejects(planning, /변경|질문/)
})

test("server selection issue keeps its field and useful error message", async () => {
  globalThis.fetch = () => response(info)
  const ds = await uploadFile(file())
  globalThis.fetch = () => Promise.resolve(new Response(JSON.stringify({ detail: "날짜 항목을 바꿔 주세요.", issue: { field: "time", code: "invalid_date" } }), { status: 422 }))
  await assert.rejects(selectUpload(ds.id, spec), error => error.message === "날짜 항목을 바꿔 주세요." && error.field === "time")
})

test("forecast is requested after the first overview without using an old agent plan", async () => {
  let request
  globalThis.fetch = (url, init) => { request = init; return response(url.endsWith("analyze") ? {} : info) }
  const ds = await uploadFile(file())
  await selectUpload(ds.id, spec)
  await analyzeUpload(ds.id, { run_forecast: true })
  const options = JSON.parse(request.body.get("options"))
  assert.equal(options.run_forecast, true)
  assert.equal(request.body.get("mode"), "manual")
})
