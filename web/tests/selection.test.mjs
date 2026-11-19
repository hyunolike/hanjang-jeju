import { test } from "node:test"
import assert from "node:assert/strict"
import { columnLabel, initialSelection, selectionReady, selectedUnit, canOfferForecast, assignSelection, nextSelectionStep, hasAnalysisPair, availableTimes } from "../src/lib/selection.ts"

const profile = { date_status: "ready", time_candidates: ["기준연월"], value_candidates: ["판매액 (천원)", "건수", "실적"], category_candidates: [], recommended: { time: "기준연월", value: "판매액 (천원)" }, columns: [
  { name: "기준연월", date_status: "valid", additive: null, unit: "" },
  { name: "판매액 (천원)", date_status: "not_date", numeric_status: "valid", additive: true, unit: "천원" },
  { name: "건수", date_status: "not_date", numeric_status: "valid", additive: true, unit: "건" },
  { name: "실적", date_status: "not_date", numeric_status: "valid", additive: null, unit: "" },
] }

test("recommended values are ready without asking users to interpret sum rules", () => {
  const s = initialSelection(profile)
  assert.deepEqual(s, { time: "기준연월", value: "판매액 (천원)", category: "", unit: "천원" })
  assert.equal(selectionReady(profile, s.time, s.value, false), true)
  assert.equal(selectedUnit(profile, "건수"), "건")
})

test("ambiguous numbers need specific meaning confirmation and old invalid choices are dropped", () => {
  assert.equal(selectionReady(profile, "기준연월", "실적", false), false)
  assert.equal(selectionReady(profile, "기준연월", "실적", true), true)
  assert.equal(selectionReady(profile, "판매액 (천원)", "실적", true), false)
  const old = { time: "판매량", value: "missing", category: "기준연월", unit: "wrong" }
  assert.deepEqual(initialSelection(profile, old), initialSelection(profile))
})

test("year-only data never appears ready", () => {
  const p = { ...profile, date_status: "year_only", time_candidates: [], recommended: { time: null, value: "판매액 (천원)" } }
  const s = initialSelection(p)
  assert.equal(s.time, "")
  assert.equal(selectionReady(p, "기준연월", s.value, true), false)
})

test("identical labels are not repeated but distinct source names remain visible", () => {
  assert.equal(columnLabel({ name: "판매액 (천원)", ko: "판매액 (천원)" }), "판매액 (천원)")
  assert.equal(columnLabel({ name: "sale_amt", ko: "매출액" }), "매출액 (sale_amt)")
})

test("additional forecast is restricted to manual overview so agent filters cannot be lost", () => {
  assert.equal(canOfferForecast({ execution: { mode: "manual", tools: ["overview"] }, filters: [] }), true)
  assert.equal(canOfferForecast({ execution: { mode: "agent", tools: ["overview"] }, filters: [{ column: "kind_nm", values: ["A"] }] }), false)
  assert.equal(canOfferForecast({ execution: { mode: "manual", tools: ["overview", "forecast"] }, filters: [] }), false)
})

const collision = { date_status: "ready", time_candidates: ["기준일"], value_candidates: ["기준일", "실적"], category_candidates: ["품목"], recommended: { time: "기준일", value: null }, columns: [
  { name: "기준일", role: "time", date_status: "valid", numeric_status: "valid", additive: null, unit: "" },
  { name: "실적", role: "unknown", date_status: "not_date", numeric_status: "valid", additive: null, unit: "천원" },
] }

test("stored calendar-as-value is repaired as a complete pair with its unit reset", () => {
  const s = initialSelection(collision, { time: "", value: "기준일", unit: "건", category: "품목" })
  assert.deepEqual(s, { time: "기준일", value: "실적", category: "품목", unit: "천원" })
  assert.equal(selectionReady(collision, "실적", "기준일", true), false)
})

test("a lone date-looking number cannot produce a misleading ready form", () => {
  const p = { ...collision, value_candidates: ["기준일"], recommended: { time: "기준일", value: null } }
  assert.equal(hasAnalysisPair(p), false)
  assert.equal(nextSelectionStep(p, initialSelection(p), "sum").target, "back")
})

test("choosing a date moves it out of the numeric slot in the same update", () => {
  const p = { ...collision, time_candidates: ["기록", "실적"], value_candidates: ["건수", "실적"], recommended: { time: null, value: null }, columns: [{ name: "기록", role: "unknown" }, { name: "실적", role: "unknown", unit: "천원", additive: null }, { name: "건수", role: "unknown", unit: "건", additive: null }] }
  const s = assignSelection(p, { time: "기록", value: "실적", unit: "천원", category: "" }, "time", "실적")
  assert.equal(s.time, "실적")
  assert.equal(s.value, "건수")
  assert.equal(s.unit, "건")
})

test("incomplete selections have an actionable target and never run", () => {
  const s = initialSelection(profile)
  assert.equal(nextSelectionStep(profile, { ...s, time: "" }, "").target, "time")
  assert.equal(nextSelectionStep(profile, { ...s, value: "" }, "").target, "value")
  assert.equal(nextSelectionStep(profile, { ...s, value: "실적" }, "").target, "meaning")
  assert.equal(nextSelectionStep(profile, { ...s, value: "실적" }, "nonadditive").target, "value")
  assert.equal(nextSelectionStep(profile, { ...s, value: "실적" }, "sum").target, "run")
})

test("dates with no compatible numeric partner cannot lead to an empty value picker", () => {
  const p = { ...collision, time_candidates: ["기준일", "실적"], value_candidates: ["실적"] }
  assert.deepEqual(availableTimes(p), ["기준일"])
  const old = { time: "실적", value: "", unit: "", category: "" }
  assert.equal(nextSelectionStep(p, old, "").target, "time")
  const repaired = initialSelection(p, old)
  assert.equal(repaired.time, "기준일")
  assert.equal(repaired.value, "실적")
})

test("rejecting the only numeric candidate offers a real file replacement action", () => {
  const p = { ...collision, value_candidates: ["실적"] }
  const step = nextSelectionStep(p, initialSelection(p), "nonadditive")
  assert.equal(step.target, "back")
})

test("clearing a date is an explicit user choice until the user selects another", () => {
  const draft = initialSelection(profile)
  const cleared = assignSelection(profile, draft, "time", "")
  assert.equal(cleared.time, "")
  assert.equal(nextSelectionStep(profile, cleared, "").target, "time")
})

test("previous nonadditive answers are remembered when finding another value", () => {
  const s = { ...initialSelection(profile), value: "실적" }
  const p = { ...profile, value_candidates: ["실적", "확인값"], columns: [...profile.columns, { name: "확인값", role: "unknown", additive: null }] }
  assert.equal(nextSelectionStep(p, s, "nonadditive", { "확인값": "nonadditive" }).target, "back")
})
