import { Bookmark, Columns3, Loader2, Plus, ShieldCheck, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartLegendItem } from '../components/charts/CashflowChart'
import { TooltipRow, TooltipShell, tooltipDate } from '../components/charts/ChartTooltip'
import { Badge, ProjectedTag } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { fmtShort, inr, inrCompact, signedInr } from '../lib/format'
import { describeChange } from '../lib/scenarios'
import type { NamedScenario, ScenarioChange, ScenarioComparison } from '../lib/types'

/** Colour follows the slot (the scenario), never its rank, so editing one never repaints the others. */
const SLOT_COLORS = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']
const MAX = 4

type ChangeType = 'purchase' | 'cancel_subscriptions' | 'income_delay' | 'increase_savings' | 'expense_increase'
  | 'unexpected_payment' | 'add_subscription' | 'fx_change'

const TYPES: { value: ChangeType; label: string }[] = [
  { value: 'purchase', label: 'Make a purchase' },
  { value: 'add_subscription', label: 'Start a subscription' },
  { value: 'cancel_subscriptions', label: 'Cancel subscriptions' },
  { value: 'income_delay', label: 'Income / client pays late' },
  { value: 'increase_savings', label: 'Increase savings' },
  { value: 'expense_increase', label: 'Spending changes' },
  { value: 'unexpected_payment', label: 'Unexpected payment' },
  { value: 'fx_change', label: 'Exchange rate moves' },
]

export default function Compare() {
  const dash = useApi(api.dashboard)
  const saved = useApi(api.savedScenarios)
  const [slots, setSlots] = useState<NamedScenario[]>([])
  const [result, setResult] = useState<ScenarioComparison | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [running, setRunning] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  const payday = dash.data?.kpis.next_income_date ?? null
  const hasForeign = (dash.data?.recurring ?? []).some((r) => r.currency)
  const presets = useMemo<NamedScenario[]>(() => {
    const laptopLater: ScenarioChange = { type: 'purchase', amount: 75000, label: 'Laptop', ...(payday ? { on: payday } : {}) }
    const cancel: ScenarioChange = { type: 'cancel_subscriptions', count: 3 }
    return [
      { name: 'Cancel 3 subscriptions', changes: [cancel] },
      { name: payday ? 'Laptop on payday' : 'Laptop later', changes: [laptopLater] },
      { name: 'Both', changes: [cancel, laptopLater] },
      { name: 'Laptop today', changes: [{ type: 'purchase', amount: 75000, label: 'Laptop' }] },
      { name: 'Income 15 days late', changes: [{ type: 'income_delay', days: 15 }] },
      ...(hasForeign ? [{ name: 'USD/INR −3%', changes: [{ type: 'fx_change', percent: -3, currency: 'USD' }] }] : []),
    ]
  }, [payday, hasForeign])

  // Start with the classic trio once we know the payday.
  useEffect(() => {
    if (dash.data && slots.length === 0) setSlots(presets.slice(0, 3))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dash.data])

  const key = JSON.stringify(slots)
  useEffect(() => {
    const valid = slots.filter((s) => s.name.trim() && s.changes.length)
    if (!valid.length) { setResult(null); return }
    let cancelled = false
    const t = setTimeout(() => {
      setRunning(true); setError(null)
      api.compare(valid)
        .then((r) => !cancelled && setResult(r))
        .catch((e) => !cancelled && setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
        .finally(() => !cancelled && setRunning(false))
    }, 350)
    return () => { cancelled = true; clearTimeout(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const update = (i: number, s: NamedScenario | null) =>
    setSlots((all) => (s ? all.map((x, j) => (j === i ? s : x)) : all.filter((_, j) => j !== i)))
  const add = (s: NamedScenario) => setSlots((all) => (all.length < MAX ? [...all, s] : all))

  async function save(s: NamedScenario) {
    setMsg(null)
    try { await api.saveScenario(s); saved.reload(); setMsg(`Saved “${s.name}”.`) }
    catch (e) { setMsg(e instanceof ApiError ? e.message : String(e)) }
  }

  // Results are positional over the *valid* slots; map them back to slot indexes for colours.
  const validIdx = slots.map((s, i) => (s.name.trim() && s.changes.length ? i : -1)).filter((i) => i >= 0)

  return (
    <>
      <PageHeader eyebrow="Compare scenarios" title="Which decision leaves you better off?"
        description="Put up to four what-ifs side by side, on the same 90-day baseline: cancel subscriptions vs. delay the laptop vs. both. Save the ones you want to come back to." />
      {msg && <p role="status" className="mb-4 rounded-xl bg-brand-50 p-3 text-sm text-brand-700">{msg}</p>}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="space-y-4">
          {slots.map((s, i) => (
            <SlotEditor key={i} index={i} slot={s} color={SLOT_COLORS[i]} onChange={(x) => update(i, x)} onSave={() => void save(s)} />
          ))}
          {slots.length < MAX && (
            <Card>
              <CardHeader title="Add a scenario" icon={<Plus className="h-4 w-4" />} subtitle={`${slots.length} of ${MAX}`} />
              <div className="flex flex-wrap gap-1.5">
                {presets.filter((p) => !slots.some((s) => s.name === p.name)).map((p) => (
                  <button key={p.name} onClick={() => add(p)} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-navy-700 hover:border-navy-900">{p.name}</button>
                ))}
                <button onClick={() => add({ name: `Scenario ${slots.length + 1}`, changes: [] })}
                  className="rounded-full border border-dashed border-slate-300 px-3 py-1 text-xs font-medium text-navy-500 hover:border-navy-900">Blank</button>
              </div>
              {(saved.data?.length ?? 0) > 0 && (
                <div className="mt-4 border-t border-slate-100 pt-3">
                  <p className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-navy-700"><Bookmark className="h-3.5 w-3.5" /> Saved</p>
                  <ul className="space-y-1">
                    {saved.data!.map((s) => (
                      <li key={s.id} className="flex items-center justify-between gap-2 text-[13px]">
                        <button onClick={() => add({ name: s.name, changes: s.changes })} className="min-w-0 truncate text-left text-navy-800 hover:underline">{s.name}</button>
                        <button onClick={() => void api.deleteScenario(s.id).then(saved.reload)} aria-label={`Delete saved ${s.name}`} className="rounded p-1 text-navy-400 hover:text-red-600"><Trash2 className="h-3.5 w-3.5" /></button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          )}
        </div>

        <div className={`min-w-0 space-y-6 transition-opacity ${running && result ? 'opacity-60' : ''}`} aria-live="polite" aria-busy={running}>
          {error && <ErrorState error={error} />}
          {!result && !error && (
            <Card><p className="flex items-center gap-2 text-sm text-navy-500">{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Columns3 className="h-4 w-4" />} {running ? 'Comparing…' : 'Add a scenario with at least one change to compare.'}</p></Card>
          )}
          {result && <Results result={result} colors={validIdx.map((i) => SLOT_COLORS[i])} />}
        </div>
      </div>
    </>
  )
}

function Results({ result, colors }: { result: ScenarioComparison; colors: string[] }) {
  const rows = result.dates.map((on, i) => {
    const r: Record<string, number | string> = { on, baseline: result.baseline_series[i] }
    result.scenarios.forEach((s) => { r[s.id] = s.series[i] })
    return r
  })
  const buffer = result.assumptions.safety_buffer
  return (
    <>
      <Card>
        <CardHeader title={`${result.assumptions.horizon_days}-day projection`} action={<ProjectedTag />} subtitle={result.summary[0]} />
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-navy-500">
          {result.scenarios.map((s, i) => <ChartLegendItem key={s.id} swatch={colors[i]} label={s.name} />)}
          <ChartLegendItem swatch="var(--axis)" label="Today’s plan" dashed thin />
          <ChartLegendItem swatch="var(--status-critical)" label={`Buffer ${inrCompact(buffer)}`} dashed thin />
        </div>
        <div style={{ height: 320 }} role="img" aria-label={result.summary.join(' ')}>
          <ResponsiveContainer>
            <ComposedChart data={rows} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis dataKey="on" tickFormatter={fmtShort} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} minTickGap={40} />
              <YAxis tickFormatter={inrCompact} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={56} />
              <Tooltip cursor={{ stroke: 'var(--axis)', strokeDasharray: '3 3' }} content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const r = payload[0].payload as Record<string, number | string>
                return (
                  <TooltipShell title={tooltipDate(String(r.on))}>
                    {result.scenarios.map((s, i) => <TooltipRow key={s.id} swatch={colors[i]} label={s.name} value={inr(Number(r[s.id]))} />)}
                    <TooltipRow swatch="var(--axis)" dashed label="Today’s plan" value={inr(Number(r.baseline))} />
                  </TooltipShell>
                )
              }} />
              <ReferenceLine y={buffer} stroke="var(--status-critical)" strokeOpacity={0.55} strokeDasharray="4 4" />
              <Line type="monotone" dataKey="baseline" stroke="var(--axis)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
              {result.scenarios.map((s, i) => (
                <Line key={s.id} type="monotone" dataKey={s.id} stroke={colors[i]} strokeWidth={s.best ? 2.75 : 2} dot={false}
                  activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} animationDuration={400} />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-[13px]">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs text-navy-400">
                <th className="px-5 py-3 font-medium">Scenario</th>
                <th className="px-3 py-3 text-right font-medium">In {result.assumptions.horizon_days} days</th>
                <th className="px-3 py-3 text-right font-medium">vs today’s plan</th>
                <th className="px-3 py-3 text-right font-medium">Lowest balance</th>
                <th className="px-3 py-3 text-right font-medium">Per month</th>
                <th className="px-5 py-3 text-right font-medium">Buffer</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {result.scenarios.map((s, i) => (
                <tr key={s.id} className={s.best ? 'bg-brand-50/40' : ''}>
                  <td className="px-5 py-3">
                    <p className="flex items-center gap-2 font-medium text-navy-900">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: colors[i] }} aria-hidden />{s.name}
                      {s.best && <Badge tone="green" icon={<ShieldCheck className="h-3 w-3" />}>Best</Badge>}
                    </p>
                    <p className="mt-0.5 text-[11px] text-navy-400">{s.applied.map((a) => a.description).join(' · ') || s.notes.join(' ')}</p>
                  </td>
                  <td className="tabular px-3 py-3 text-right font-semibold text-navy-900">{inr(s.end_balance)}</td>
                  <td className={`tabular px-3 py-3 text-right font-medium ${s.end_delta >= 0 ? 'text-brand-700' : 'text-navy-800'}`}>{signedInr(s.end_delta)}</td>
                  <td className="tabular px-3 py-3 text-right text-navy-800">{inr(s.min_balance)}<span className="block text-[11px] text-navy-400">{fmtShort(s.min_balance_date)}</span></td>
                  <td className="tabular px-3 py-3 text-right text-navy-800">{s.monthly_effect ? signedInr(s.monthly_effect) : '—'}</td>
                  <td className="px-5 py-3 text-right">{s.safe ? <Badge tone="green">Stays above</Badge> : <Badge tone="red">{s.days_below_buffer} day(s) under</Badge>}</td>
                </tr>
              ))}
              <tr className="text-navy-500">
                <td className="px-5 py-3">Today’s plan (no changes)</td>
                <td className="tabular px-3 py-3 text-right">{inr(result.baseline_end)}</td>
                <td className="px-3 py-3 text-right">—</td>
                <td className="tabular px-3 py-3 text-right">{inr(result.baseline_min)}</td>
                <td className="px-3 py-3 text-right">—</td>
                <td className="px-5 py-3" />
              </tr>
            </tbody>
          </table>
        </div>
        {result.summary.length > 1 && <ul className="space-y-1 border-t border-slate-100 px-5 py-3 text-[13px] text-navy-600">{result.summary.slice(1).map((l, i) => <li key={i}>• {l}</li>)}</ul>}
      </Card>
    </>
  )
}

function SlotEditor({ index, slot, color, onChange, onSave }: {
  index: number; slot: NamedScenario; color: string; onChange: (s: NamedScenario | null) => void; onSave: () => void
}) {
  const [adding, setAdding] = useState(slot.changes.length === 0)
  return (
    <Card>
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
        <label htmlFor={`slot-${index}`} className="sr-only">Scenario name</label>
        <input id={`slot-${index}`} value={slot.name} maxLength={80} onChange={(e) => onChange({ ...slot, name: e.target.value })}
          className="min-w-0 flex-1 rounded-lg border border-transparent px-1.5 py-1 text-sm font-semibold text-navy-900 outline-none hover:border-slate-200 focus:border-navy-700" />
        <button onClick={onSave} disabled={!slot.changes.length || !slot.name.trim()} aria-label="Save scenario" title="Save" className="rounded-lg p-1.5 text-navy-400 hover:bg-slate-100 hover:text-navy-900 disabled:opacity-30"><Bookmark className="h-4 w-4" /></button>
        <button onClick={() => onChange(null)} aria-label="Remove scenario" title="Remove" className="rounded-lg p-1.5 text-navy-400 hover:bg-slate-100 hover:text-red-600"><X className="h-4 w-4" /></button>
      </div>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {slot.changes.map((c, j) => (
          <li key={j} className="inline-flex items-center gap-1 rounded-full bg-slate-100 py-1 pl-2.5 pr-1 text-xs text-navy-800">
            {describeChange(c)}
            <button onClick={() => onChange({ ...slot, changes: slot.changes.filter((_, k) => k !== j) })} aria-label={`Remove ${describeChange(c)}`} className="rounded-full p-0.5 hover:bg-slate-200"><X className="h-3 w-3" /></button>
          </li>
        ))}
        {!adding && slot.changes.length < 8 && (
          <li><button onClick={() => setAdding(true)} className="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-2.5 py-1 text-xs text-navy-500 hover:border-navy-900"><Plus className="h-3 w-3" /> Add change</button></li>
        )}
      </ul>
      {adding && <ChangeForm onAdd={(c) => { onChange({ ...slot, changes: [...slot.changes, c] }); setAdding(false) }} onCancel={() => setAdding(false)} />}
    </Card>
  )
}

function ChangeForm({ onAdd, onCancel }: { onAdd: (c: ScenarioChange) => void; onCancel: () => void }) {
  const [type, setType] = useState<ChangeType>('purchase')
  const [amount, setAmount] = useState('75000')
  const [label, setLabel] = useState('')
  const [on, setOn] = useState('')
  const [count, setCount] = useState('3')
  const [days, setDays] = useState('15')
  const [merchant, setMerchant] = useState('')
  const [percent, setPercent] = useState('10')
  const [currency, setCurrency] = useState('USD')
  const num = (s: string) => Number(s.replace(/,/g, ''))

  function build(): ScenarioChange | null {
    switch (type) {
      case 'purchase': case 'unexpected_payment':
        return num(amount) > 0 ? { type, amount: num(amount), label: label.trim() || (type === 'purchase' ? 'Purchase' : 'Unexpected payment'), ...(on ? { on } : {}) } : null
      case 'add_subscription':
        return num(amount) > 0 ? { type, amount: num(amount), label: label.trim() || 'New subscription', ...(on ? { start: on } : {}) } : null
      case 'cancel_subscriptions': return num(count) >= 1 ? { type, count: Math.round(num(count)) } : null
      case 'income_delay': return num(days) >= 1 ? { type, days: Math.round(num(days)), ...(merchant.trim() ? { merchant: merchant.trim() } : {}) } : null
      case 'increase_savings': return num(percent) > 0 ? { type, percent: num(percent) } : null
      case 'expense_increase': return Number.isFinite(num(percent)) && num(percent) !== 0 ? { type, percent: num(percent) } : null
      case 'fx_change': return Number.isFinite(num(percent)) && num(percent) !== 0 ? { type, percent: num(percent), currency } : null
    }
  }
  const change = build()
  const field = 'mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm outline-none focus:border-navy-700'
  return (
    <div className="mt-3 rounded-xl bg-slate-50 p-3">
      <label className="block text-xs font-medium text-navy-700">Change
        <select value={type} onChange={(e) => { const t = e.target.value as ChangeType; setType(t); setPercent(t === 'fx_change' ? '-3' : '10'); setAmount(t === 'add_subscription' ? '499' : t === 'unexpected_payment' ? '30000' : '75000') }} className={field}>
          {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </label>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {['purchase', 'unexpected_payment', 'add_subscription'].includes(type) && <>
          <label className="text-xs font-medium text-navy-700">{type === 'add_subscription' ? 'Monthly ₹' : 'Amount ₹'}<input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.,]/g, ''))} className={field} /></label>
          <label className="text-xs font-medium text-navy-700">{type === 'add_subscription' ? 'Starts' : 'Date'}<input type="date" value={on} onChange={(e) => setOn(e.target.value)} className={field} /></label>
          <label className="col-span-2 text-xs font-medium text-navy-700">Label<input value={label} maxLength={80} placeholder={type === 'add_subscription' ? 'Gym membership' : 'Laptop'} onChange={(e) => setLabel(e.target.value)} className={field} /></label>
        </>}
        {type === 'cancel_subscriptions' && <label className="text-xs font-medium text-navy-700">How many (most expensive first)<input inputMode="numeric" value={count} onChange={(e) => setCount(e.target.value.replace(/\D/g, ''))} className={field} /></label>}
        {type === 'income_delay' && <>
          <label className="text-xs font-medium text-navy-700">Days late<input inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ''))} className={field} /></label>
          <label className="text-xs font-medium text-navy-700">Only this payer (optional)<input value={merchant} placeholder="Client name" onChange={(e) => setMerchant(e.target.value)} className={field} /></label>
        </>}
        {['increase_savings', 'expense_increase', 'fx_change'].includes(type) && (
          <label className="text-xs font-medium text-navy-700">Percent{type !== 'increase_savings' ? ' (− for down)' : ''}<input inputMode="decimal" value={percent} onChange={(e) => setPercent(e.target.value.replace(/[^\d.-]/g, ''))} className={field} /></label>
        )}
        {type === 'fx_change' && (
          <label className="text-xs font-medium text-navy-700">Currency<select value={currency} onChange={(e) => setCurrency(e.target.value)} className={field}>{['USD', 'EUR', 'GBP'].map((c) => <option key={c}>{c}</option>)}</select></label>
        )}
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button onClick={onCancel} className="rounded-lg px-3 py-1.5 text-xs font-medium text-navy-600 hover:bg-white">Cancel</button>
        <button disabled={!change} onClick={() => change && onAdd(change)} className="rounded-lg bg-navy-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-navy-800 disabled:opacity-40">Add</button>
      </div>
    </div>
  )
}
