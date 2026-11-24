import { test } from 'node:test'
import assert from 'node:assert/strict'
import * as selection from '../src/lib/selection.ts'

const profile = {
  date_status: 'ready', time_candidates: ['date'], value_candidates: ['amount', 'count', 'avg_sale_amt'], category_candidates: ['kind'],
  recommended: { time: 'date', value: 'count' },
  columns: [{ name: 'date', role: 'time' }, { name: 'amount', role: 'unknown', additive: null }, { name: 'count', role: 'measure', additive: true, unit: '건' }, { name: 'avg_sale_amt', role: 'measure', additive: false }, { name: 'kind', role: 'category' }],
}

test('reuse copies only four criteria and requires fresh meaning confirmation', () => {
  const old = { time: 'date', value: 'amount', category: 'kind', unit: '천원', additive_confirmed: true, filters: [{ column: 'kind', values: ['A'] }], run_forecast: true, question: 'old', intent: 'forecast' }
  const result = selection.reusableSelection(old, profile)
  assert.deepEqual(result.draft, { time: 'date', value: 'amount', category: 'kind', unit: '천원' })
  assert.deepEqual(result.missing, [])
  assert.equal(selection.nextSelectionStep(profile, result.draft, '').target, 'meaning')
})

test('reuse does not silently replace missing columns or allow incompatible roles', () => {
  const r = selection.reusableSelection({ time: 'gone', value: 'avg_sale_amt', category: 'date', unit: '%' }, profile)
  assert.equal(r.draft.time, '')
  assert.equal(r.draft.value, '')
  assert.equal(r.draft.category, '')
  assert.equal(r.draft.unit, '')
  assert.deepEqual(r.missing, ['gone', 'avg_sale_amt', 'date'])
})
