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

test('recipe plan uses business mode and binds chosen task', async () => {
  let request
  const business = { ...fakePlan, plan_origin: 'recipe', execution_spec: { ...spec, business_task: 'brief', plan_origin: 'recipe', tools: ['quarter_compare', 'category_change', 'brief'] } }
  globalThis.fetch = (url, init) => { request = init; return response(url.endsWith('plan') ? business : info) }
  const ds = await uploadFile(file())
  await selectUpload(ds.id, spec)
  const plan = await planUpload(ds.id, '보고용 정리', undefined, 'brief')
  assert.equal(request.body.get('business_task'), 'brief')
  confirmUploadPlan(ds.id, plan, '보고용 정리')
  await analyzeUpload(ds.id, { agent_digest: plan.input_digest })
  assert.equal(request.body.get('mode'), 'business')
  assert.equal(JSON.parse(request.body.get('execution_spec')).plan_origin, 'recipe')
})

test('replacing a recipe rejects the old plan response', async () => {
  let release
  globalThis.fetch = url => url.endsWith('plan') ? new Promise(resolve => { release = () => resolve(new Response(JSON.stringify(fakePlan))) }) : response(info)
  const ds = await uploadFile(file())
  await selectUpload(ds.id, spec)
  const old = planUpload(ds.id, '보고용 정리', undefined, 'brief')
  discardPlan(ds.id)
  release()
  await assert.rejects(old, /변경|질문/)
})
