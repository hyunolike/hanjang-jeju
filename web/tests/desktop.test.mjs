import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { QueryClient, MutationObserver } from '@tanstack/react-query'
import { UploadRequestError } from '../src/lib/upload.ts'
import * as selection from '../src/lib/selection.ts'

// Execute original TSX handlers with real cache/mutation state, without a GUI or LLM.
const jsx = (type, props) => ({ type, props: props ?? {} })
function component(file, overrides, globals = {}, staticMode = false) {
  const tags = names => Object.fromEntries(names.map(x => [x, x]))
  const modules = {
    'react/jsx-runtime': { jsx, jsxs: jsx },
    'lucide-react': tags(['ArrowUp', 'Bot', 'PackageSearch', 'Sparkles', 'Puzzle', 'Database', 'Download', 'FileSpreadsheet', 'FlaskConical', 'Upload', 'FileCheck2', 'Printer', 'Trash2']),
    '@/components/kit': tags(['Panel', 'Pill', 'Illust', 'Stat', 'ListRow', 'CtaBar']),
    '@/components/ui/button': { Button: 'Button', buttonVariants: () => '' },
    '@/components/ui/select': tags(['Select', 'SelectContent', 'SelectItem', 'SelectTrigger']),
    '@/components/ui/table': tags(['Table', 'TableBody', 'TableCell', 'TableHead', 'TableHeader', 'TableRow']),
    '@/components/ui/skeleton': { Skeleton: 'Skeleton' },
    '@/components/stage': { StageIntro: 'StageIntro' },
    '@/lib/utils': { cn: (...args) => args.filter(Boolean).join(' ') },
    '@/lib/format': { period: x => x, factText: String, money: String },
    './Analyze': { modelName: String },
    'sonner': { toast: { success() {}, error() {} } },
    ...overrides,
  }
  const source = fs.readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8').replaceAll('import.meta.env.', staticMode ? '({ VITE_STATIC: "1" }).' : '({}).')
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  vm.runInNewContext(code, { exports, URLSearchParams, ...globals, require: name => {
    assert.ok(name in modules, `Unexpected dependency: ${name}`)
    return modules[name]
  } })
  return exports
}
function find(node, predicate) {
  if (!node || typeof node !== 'object') return undefined
  if (Array.isArray(node)) return node.map(n => find(n, predicate)).find(Boolean)
  return predicate(node) ? node : find(node.props?.children, predicate)
}

test('local forecast queries default off, explicitly opt in, and support forecast questions', async () => {
  const requested = []
  const { api } = component('lib/api.ts', { './upload': {} }, { fetch: async url => { requested.push(new URL(url, 'http://localhost')); return new Response('{}') } })
  await api.analyze('upload-local')
  await api.analyze('upload-local', { run_forecast: true })
  await api.analyze('upload-local', { intent: 'forecast' })
  await api.analyze('upload-local', { intent: 'forecast', run_forecast: false })
  assert.deepEqual(requested.map(url => url.searchParams.get('run_forecast')), ['false', 'true', 'true', 'false'])
})

test('native analysis offers an explicit forecast while preserving the chosen filters', () => {
  const tags = names => Object.fromEntries(names.map(name => [name, name]))
  const choice = { value: 'sale_amt', category: 'type_nm', intent: 'share', period_n: 6, filters: [{ column: 'type_nm', values: ['A'] }] }
  let next
  const { Analyze } = component('steps/Analyze.tsx', {
    'react': { useMemo: fn => fn() },
    '@tanstack/react-query': { useQuery: () => ({ data: { dataset: { title: 'synthetic' }, value: { name: 'sale_amt', ko: '매출', unit: '원' }, category: 'type_nm', options: { values: ['sale_amt'], categories: ['type_nm'] }, labels: {}, series: [], cards: [], facts: {}, forecast: null, forecast_refusal: '예측 도구를 선택하지 않았어요.', missing_months: [], filters: choice.filters } }) },
    '@/lib/api': { STATIC: false, WEB_UPLOAD: false, api: {} },
    '@/lib/selection': selection,
    '@/components/form': tags(['ActionFeedback']),
    '@/components/ui/chart': tags(['ChartContainer', 'ChartTooltip', 'ChartTooltipContent']),
    './WebAskPanel': tags(['WebAskPanel']), './AskPanel': tags(['AskPanel']), './JoinPanel': tags(['JoinPanel']),
    'recharts': tags(['Area', 'CartesianGrid', 'ComposedChart', 'Line', 'XAxis', 'YAxis']),
  })
  const tree = Analyze({ dataset: { id: 'local', source: 'upload' }, choice, onChange: value => { next = value } })
  const forecastButton = find(tree, n => n.type === 'Button' && n.props.children === '예측도 계산하기')
  assert.ok(forecastButton, 'native uploads need a separate forecast action')
  forecastButton.props.onClick()
  assert.equal(next.run_forecast, true)
  assert.equal(next.period_n, 6)
  assert.equal(next.intent, 'share')
  assert.deepEqual(next.filters, choice.filters)
})

test('editing a question hides the previous executable plan', async () => {
  const cache = new QueryClient()
  const observer = new MutationObserver(cache, { mutationFn: async () => ({ fallback: false, plan: { intent: 'compare', value: 'sale_amt', group_by: null, filters: [], period_n: 12, horizon: 6 }, unresolved: [], blocked: [], needs: [], unsupported: [], labels: {}, latency_ms: 1 }) })
  await observer.mutate('old question')
  let state = ['old question', {}], cursor = 0
  const { AskPanel } = component('steps/AskPanel.tsx', {
    'react': { useState: initial => { const i = cursor++; return [state[i] ?? initial, v => { state[i] = v }] } },
    '@tanstack/react-query': { useQuery: () => ({ data: { ready: true } }), useMutation: () => ({ ...observer.getCurrentResult(), reset: () => observer.reset() }) },
    '@/lib/api': { STATIC: false, api: {} },
  })
  const render = () => { cursor = 0; return AskPanel({ dataset: { id: 'local' }, onRun: () => assert.fail('stale plan executed') }) }
  assert.ok(find(render(), n => n.type === 'Button' && n.props.onClick))
  find(render(), n => n.type === 'input').props.onChange({ target: { value: 'new question' } })
  assert.equal(find(render(), n => n.type === 'Button' && n.props.onClick), undefined)
  cache.clear()
})

test('a late local plan does not return after the question is changed', async () => {
  const cache = new QueryClient()
  let release
  const observer = new MutationObserver(cache, { mutationFn: () => new Promise(resolve => { release = resolve }) })
  const pending = observer.mutate('old question')
  await new Promise(resolve => setImmediate(resolve))
  let state = ['old question', {}], cursor = 0
  const { AskPanel } = component('steps/AskPanel.tsx', {
    'react': { useState: initial => { const i = cursor++; return [state[i] ?? initial, v => { state[i] = v }] } },
    '@tanstack/react-query': { useQuery: () => ({ data: { ready: true } }), useMutation: () => ({ ...observer.getCurrentResult(), reset: () => observer.reset() }) },
    '@/lib/api': { STATIC: false, api: {} },
  })
  const render = () => { cursor = 0; return AskPanel({ dataset: { id: 'local' }, onRun: () => assert.fail('late plan executed') }) }
  find(render(), n => n.type === 'input').props.onChange({ target: { value: 'new question' } })
  release({ plan: { filters: [], intent: 'overview', value: 'sale_amt' }, unresolved: [], blocked: [], needs: [], unsupported: [], labels: {}, latency_ms: 1 })
  await pending
  assert.equal(find(render(), n => n.type === 'Button' && n.props.onClick), undefined)
  cache.clear()
})

test('local selection sends a PUT request and preserves selection issues', async () => {
  let request
  const { api } = component('lib/api.ts', { './upload': {} }, { fetch: async (url, init) => { request = { url, ...init }; return new Response(JSON.stringify({ selection: {} })) } })
  await api.selectDataset('upload-local', { time: '기간', value: '실적', additive_confirmed: true })
  assert.equal(request.url, '/api/datasets/upload-local/selection')
  assert.equal(request.method, 'PUT')
  assert.equal(JSON.parse(request.body).value, '실적')
  const failed = component('lib/api.ts', { './upload': { UploadRequestError } }, { fetch: async () => new Response(JSON.stringify({ detail: '3행을 확인해 주세요', issue: { field: 'time' } }), { status: 422 }) }).api
  await assert.rejects(failed.selectDataset('upload-local', {}), error => error.field === 'time' && error.message.includes('3행'))
})

test('local deletion errors do not resolve as a successful deletion', async () => {
  const { api } = component('lib/api.ts', { './upload': {} }, { fetch: async () => new Response(JSON.stringify({ detail: '지우지 못했어요' }), { status: 403 }) })
  await assert.rejects(api.clearWorkspace(), /지우지 못했어요/)
})

test('local analysis can explicitly clear a stored category', async () => {
  let requested
  const { api } = component('lib/api.ts', { './upload': {} }, { fetch: async url => { requested = url; return new Response('{}') } })
  await api.analyze('upload-local', { category: null })
  assert.equal(new URL(requested, 'http://localhost').searchParams.get('category'), '')
})

test('static sample join explains an unsupported value instead of treating it as a result', async () => {
  const { api } = component('lib/api.ts', { './upload': {} }, { fetch: async () => new Response(JSON.stringify({ error: '합계로 계산할 수 없어요' })) }, true)
  await assert.rejects(api.join('a', 'sale_amt', 'b', 'visit_pop_cnt'), /합계/)
})

test('a null correlation renders its refusal instead of throwing', () => {
  const { JoinPanel } = component('steps/JoinPanel.tsx', {
    'react': { useState: () => [null, () => {}] },
    '@tanstack/react-query': { useQuery: () => ({ data: [] }), useMutation: () => ({ data: { result: { facts: { F001: { value: null } }, correlation_refusal: '비교할 월이 부족해요', report: { matched_rows: 2, unmatched_rows: 0, unmatched_keys: [] } } } }) },
    '@/lib/api': { api: {} },
  })
  const tree = JoinPanel({ dataset: { id: 'local' }, value: 'sale_amt' })
  assert.ok(JSON.stringify(tree).includes('비교할 월이 부족해요'))
})

test('joining uses the right dataset saved measure rather than the first measure', async () => {
  let callbacks, requested
  const { JoinPanel } = component('steps/JoinPanel.tsx', {
    'react': { useState: () => [null, () => {}] },
    '@tanstack/react-query': { useQuery: () => ({ data: [] }), useMutation: options => { callbacks = options; return {} } },
    '@/lib/api': { api: {
      understand: async () => ({ time_column: 'date', selection: { value: 'use_cnt' }, columns: [{ name: 'sale_amt', ko: '매출', role: 'measure', additive: true }, { name: 'use_cnt', ko: '건수', role: 'measure', additive: true }] }),
      join: async (...args) => { requested = args; return {} },
    } },
  })
  JoinPanel({ dataset: { id: 'left' }, value: 'sale_amt' })
  await callbacks.mutationFn({ id: 'right' })
  assert.equal(requested[3], 'use_cnt')
})

test('the local unsupported form identifies invalid numeric source rows', () => {
  const cache = new QueryClient()
  const { WebSelection } = component('steps/WebSelection.tsx', {
    'react': { useState: initial => [typeof initial === 'function' ? initial() : initial, () => {}], useRef: () => ({ current: null }), useEffect() {} },
    '@tanstack/react-query': { useQueryClient: () => cache },
    '@/lib/api': { WEB_UPLOAD: false, api: {} },
    '@/lib/upload': {}, '@/lib/selection': selection,
    '@/components/form': { ActionFeedback: 'ActionFeedback', FormField: 'FormField' },
  })
  const profile = { time_candidates: ['date'], value_candidates: [], category_candidates: [], date_status: 'ready', recommended: { time: 'date' }, columns: [{ name: 'date', role: 'time', date_status: 'valid' }, { name: 'sale_amt', role: 'measure', additive: true, numeric_status: 'invalid', invalid_numeric_rows: [3] }] }
  const outer = WebSelection({ dataset: { id: 'local' }, info: { columns: [], upload_profile: profile }, onBack() {} })
  const unsupported = outer.type(outer.props)
  const tree = unsupported.type(unsupported.props)
  assert.ok(JSON.stringify(tree).includes('3행'))
  cache.clear()
})

test('uploading a local CSV invalidates the file list even with infinite stale time', async () => {
  const cache = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } })
  cache.setQueryData(['datasets'], [])
  let callbacks
  const { Upload } = component('steps/Upload.tsx', {
    'react': { useRef: () => ({ current: null }), useState: () => [false, () => {}] },
    '@tanstack/react-query': { useQueryClient: () => cache, useQuery: () => ({ data: [] }), useMutation: options => { callbacks = options; return {} } },
    '@/lib/api': { api: {}, STATIC: false, WEB_UPLOAD: false },
  })
  Upload({ onPick() {} })
  await callbacks.onSuccess({ id: 'new-id' })
  assert.equal(cache.getQueryState(['datasets']).isInvalidated, true)
  cache.clear()
})

test('finishing a local report removes cached data for deleted files', async () => {
  const cache = new QueryClient()
  for (const key of [['datasets'], ['understand', 'local'], ['analyze', 'local', '{}']]) cache.setQueryData(key, { marker: 'private data' })
  let done = false
  const { Result } = component('steps/Result.tsx', {
    '@tanstack/react-query': { useQueryClient: () => cache },
    '@/lib/api': { api: { clearWorkspace: async () => ({ removed: 1 }) } },
  })
  const tree = Result({ analysis: { dataset: { title: 'synthetic' }, value: {}, cards: [], facts: {}, missing_months: [] }, onDone: () => { done = true } })
  await find(tree, n => n.type === 'Button' && n.props.variant === 'ghost').props.onClick()
  assert.equal(done, true)
  assert.equal(cache.getQueryData(['understand', 'local']), undefined)
  assert.equal(cache.getQueryData(['analyze', 'local', '{}']), undefined)
  cache.clear()
})

test('a failed deletion keeps the report and cached data and shows an error', async () => {
  const cache = new QueryClient()
  cache.setQueryData(['understand', 'local'], { retained: true })
  let error = '', done = false
  const { Result } = component('steps/Result.tsx', {
    '@tanstack/react-query': { useQueryClient: () => cache },
    '@/lib/api': { api: { clearWorkspace: async () => { throw new Error('지우지 못했어요') } } },
    'sonner': { toast: { success: () => assert.fail('false success'), error: message => { error = message } } },
  })
  const tree = Result({ analysis: { dataset: { title: 'synthetic' }, value: {}, cards: [], facts: {}, missing_months: [] }, onDone: () => { done = true } })
  await assert.doesNotReject(find(tree, n => n.type === 'Button' && n.props.variant === 'ghost').props.onClick())
  assert.equal(done, false)
  assert.equal(cache.getQueryData(['understand', 'local']).retained, true)
  assert.equal(error, '지우지 못했어요')
  cache.clear()
})
