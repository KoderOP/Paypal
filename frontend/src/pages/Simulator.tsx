import {
  AlertOctagon, AlertTriangle, CalendarDays, CheckCircle2, Clock, Hourglass, Info, Laptop, Plane, ShieldCheck,
  Smartphone, Sofa, Sparkles, TrendingDown, XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ScenarioChart } from '../components/charts/ScenarioChart'
import { GoalSolver } from '../components/GoalSolver'
import { PaymentOptions } from '../components/PaymentOptions'
import { Badge, ProjectedTag } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState, Skeleton } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { addDays, fmtDate, inr, signedInr } from '../lib/format'
import type { Affordability, PaymentComparison, PurchaseSimulation, Risk, TimingOption } from '../lib/types'

const PRESETS = [
  { label: 'Laptop', amount: 75000, icon: Laptop },
  { label: 'Smartphone', amount: 40000, icon: Smartphone },
  { label: 'Sofa set', amount: 55000, icon: Sofa },
  { label: 'Vacation', amount: 120000, icon: Plane },
]

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/** Purchase simulator. Rendered inside the What-if Simulator tab, which passes the shared header. */
export default function Simulator({ header }: { header?: ReactNode } = {}) {
  const [label, setLabel] = useState('Laptop purchase')
  const [amountText, setAmountText] = useState('75000')
  const [date, setDate] = useState<string | null>(null) // null = today
  const [buffer, setBuffer] = useState<number | null>(null)
  const [sim, setSim] = useState<PurchaseSimulation | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [running, setRunning] = useState(false)
  const [nonce, setNonce] = useState(0)
  const [cmp, setCmp] = useState<PaymentComparison | null>(null)
  const [aff, setAff] = useState<Affordability | null>(null)
  const scenarios = useApi(api.scenarios)

  const amount = Number(amountText.replace(/,/g, ''))
  const amountValid = Number.isFinite(amount) && amount > 0 && amount <= 1e8
  const request = useDebounced({ amount, label: label.trim() || 'Purchase', date, buffer, nonce }, 300)

  useEffect(() => {
    if (!(Number.isFinite(request.amount) && request.amount > 0 && request.amount <= 1e8)) return
    let cancelled = false
    setRunning(true)
    setError(null)
    api
      .simulatePurchase({
        amount: request.amount,
        label: request.label,
        purchase_date: request.date ?? undefined,
        safety_buffer: request.buffer ?? undefined,
      })
      .then((r) => {
        if (cancelled) return
        setSim(r)
        setBuffer((b) => b ?? r.assumptions.safety_buffer)
      })
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
      .finally(() => !cancelled && setRunning(false))
    return () => {
      cancelled = true
    }
  }, [request])

  // Buy now / wait / split + goal solver depend on amount, label and buffer (not on the chosen date).
  const { amount: reqAmount, label: reqLabel, buffer: reqBuffer, nonce: reqNonce } = request
  useEffect(() => {
    if (!(Number.isFinite(reqAmount) && reqAmount > 0 && reqAmount <= 1e8)) return
    let cancelled = false
    const buffer = reqBuffer ?? undefined
    Promise.all([
      api.paymentOptions({ amount: reqAmount, label: reqLabel, safety_buffer: buffer }),
      api.affordability({ amount: reqAmount, search_days: 60, safety_buffer: buffer }),
    ])
      .then(([c, a]) => { if (!cancelled) { setCmp(c); setAff(a) } })
      .catch(() => { if (!cancelled) { setCmp(null); setAff(null) } })
    return () => { cancelled = true }
  }, [reqAmount, reqLabel, reqBuffer, reqNonce])

  const asOf = sim?.as_of
  const maxDate = asOf ? addDays(asOf, sim!.assumptions.horizon_days) : undefined
  const dateInvalid = !!(date && asOf && maxDate && (date < asOf || date > maxDate))

  return (
    <>
      {header ?? (
        <PageHeader
          eyebrow="What-if Simulator"
          title="Simulate a decision before you make it"
          description="Your financial twin replays your income, bills, obligations and day-to-day spending day by day — with and without the purchase — and tests alternative dates to find the safest moment to buy."
        />
      )}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-6 lg:sticky lg:top-6 lg:self-start">
          <Card>
            <CardHeader title="Scenario" subtitle="Item, amount, date and the balance you always want to keep" icon={<Sparkles className="h-4 w-4 text-brand-600" />} />
            <div className="grid grid-cols-2 gap-2">
              {PRESETS.map((p) => {
                const active = amount === p.amount && label.toLowerCase().startsWith(p.label.toLowerCase())
                return (
                  <button
                    key={p.label}
                    onClick={() => { setLabel(`${p.label} purchase`); setAmountText(String(p.amount)) }}
                    className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-left transition ${active ? 'border-navy-900 bg-navy-900 text-white' : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'}`}
                  >
                    <p.icon className={`h-4 w-4 ${active ? 'text-brand-500' : 'text-navy-400'}`} />
                    <span>
                      <span className="block text-xs font-medium">{p.label}</span>
                      <span className={`tabular block text-[11px] ${active ? 'text-slate-300' : 'text-navy-400'}`}>{inr(p.amount)}</span>
                    </span>
                  </button>
                )
              })}
            </div>

            <label className="mt-5 block text-xs font-medium text-navy-700" htmlFor="sim-label">Item</label>
            <input id="sim-label" value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy-700 focus:ring-2 focus:ring-navy-900/10" />

            <label className="mt-4 block text-xs font-medium text-navy-700" htmlFor="sim-amount">Amount</label>
            <div className={`mt-1.5 flex items-center rounded-xl border px-3 focus-within:ring-2 ${amountValid ? 'border-slate-200 focus-within:border-navy-700 focus-within:ring-navy-900/10' : 'border-red-300 focus-within:ring-red-100'}`}>
              <span className="text-lg text-navy-400">₹</span>
              <input id="sim-amount" inputMode="numeric" value={amountText} aria-invalid={!amountValid}
                onChange={(e) => setAmountText(e.target.value.replace(/[^\d.,]/g, ''))}
                className="tabular w-full bg-transparent px-2 py-2.5 text-xl font-semibold text-navy-900 outline-none" />
            </div>
            {!amountValid && <p className="mt-1 text-xs text-red-600">Enter an amount between ₹1 and ₹10,00,00,000.</p>}
            {amountValid && <p className="mt-1 text-xs text-navy-400">{inr(amount)}</p>}

            <p className="mt-5 text-xs font-medium text-navy-700">Purchase date</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <DateChip active={date === null} onClick={() => setDate(null)}>Today</DateChip>
              {sim?.timing_options.filter((o) => o.days_from_now > 0 && o.label.startsWith('After income')).slice(0, 2).map((o) => (
                <DateChip key={o.purchase_date} active={date === o.purchase_date} onClick={() => setDate(o.purchase_date)}>
                  Payday {fmtDate(o.purchase_date)}
                </DateChip>
              ))}
            </div>
            <div className={`mt-2 flex items-center gap-2 rounded-xl border px-3 py-1.5 ${dateInvalid ? 'border-red-300' : 'border-slate-200'}`}>
              <CalendarDays className="h-4 w-4 text-navy-400" />
              <input type="date" aria-label="Custom purchase date" min={asOf} max={maxDate} value={date ?? asOf ?? ''}
                onChange={(e) => setDate(e.target.value && e.target.value !== asOf ? e.target.value : null)}
                className="w-full bg-transparent text-sm text-navy-800 outline-none" />
            </div>
            {dateInvalid && <p className="mt-1 text-xs text-red-600">Pick a date between {fmtDate(asOf!)} and {fmtDate(maxDate!)} (the forecast window).</p>}

            <div className="mt-5">
              <div className="flex items-center justify-between">
                <label htmlFor="sim-buffer" className="text-xs font-medium text-navy-700">Minimum buffer</label>
                <span className="tabular text-xs font-semibold text-navy-900">{buffer !== null ? inr(buffer) : '—'}</span>
              </div>
              <input id="sim-buffer" type="range" min={0} max={100000} step={5000} value={buffer ?? 20000}
                onChange={(e) => setBuffer(Number(e.target.value))} className="mt-2 w-full accent-[#0b1b3a]" />
              <p className="mt-1 text-[11px] leading-relaxed text-navy-400">The minimum balance you want to keep at all times. A date is "safe" if your balance never drops below it.</p>
            </div>
          </Card>

          <ScenarioLibrary items={scenarios.data ?? []} />
        </div>

        <div className={`min-w-0 space-y-6 transition-opacity ${running && sim ? 'opacity-60' : ''}`} aria-live="polite" aria-busy={running}>
          {error && <ErrorState error={error} onRetry={() => setNonce((n) => n + 1)} />}
          {!sim && !error && <ResultSkeleton />}
          {sim && (
            <Results sim={sim} onPickDate={(d) => setDate(d === sim.as_of ? null : d)}
              planning={<>
                {cmp ? <PaymentOptions cmp={cmp} variant="matrix" onChanged={() => setNonce((n) => n + 1)} /> : <Skeleton className="h-96" />}
                {aff && <GoalSolver data={aff} amount={amount} />}
              </>} />
          )}
        </div>
      </div>
    </>
  )
}

function DateChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} aria-pressed={active}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition ${active ? 'border-navy-900 bg-navy-900 text-white' : 'border-slate-200 text-navy-700 hover:bg-slate-50'}`}>
      {children}
    </button>
  )
}

function ResultSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-36" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      <Skeleton className="h-96" />
    </div>
  )
}

const VERDICT = {
  safe_now: { panel: 'border-emerald-200 bg-emerald-50', icon: 'text-emerald-600', Icon: CheckCircle2, tag: 'Affordable now' },
  wait: { panel: 'border-amber-200 bg-amber-50', icon: 'text-amber-600', Icon: Hourglass, tag: 'Better to wait' },
  not_recommended: { panel: 'border-red-200 bg-red-50', icon: 'text-red-600', Icon: XCircle, tag: 'Not recommended' },
} as const

function Results({ sim, onPickDate, planning }: { sim: PurchaseSimulation; onPickDate: (d: string) => void; planning?: ReactNode }) {
  const rec = sim.recommendation
  const v = VERDICT[rec.verdict]
  const selected = sim.timing_options.find((o) => o.is_selected)!
  const recommended = sim.timing_options.find((o) => o.is_recommended)

  return (
    <>
      {/* Recommendation: restrained panel, severity-coded. The window and wording come from the engine. */}
      <div className={`animate-fade-up rounded-2xl border p-5 sm:p-6 ${v.panel}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <v.Icon className={`mt-1 h-6 w-6 shrink-0 ${v.icon}`} />
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-navy-500">Timing · paying in full · {v.tag}</p>
              {recommended?.safe && !recommended.is_selected
                ? <h2 className="mt-1 text-xl font-semibold tracking-tight text-navy-900">Optimal purchase window: {fmtDate(recommended.purchase_date)}</h2>
                : <h2 className="mt-1 text-xl font-semibold tracking-tight text-navy-900">{rec.headline}</h2>}
              <p className="mt-1 max-w-xl text-[13.5px] text-navy-600">
                {recommended?.safe && !recommended.is_selected
                  ? `Preserves your minimum buffer of ${inr(sim.assumptions.safety_buffer)}: lowest projected balance ${inr(recommended.min_balance)}. ${rec.headline}`
                  : `${inr(sim.scenario.amount)} on ${fmtDate(sim.scenario.purchase_date)} · lowest projected balance ${inr(selected.min_balance)} vs ${inr(sim.assumptions.safety_buffer)} buffer.`}
              </p>
            </div>
          </div>
          {recommended && !recommended.is_selected && (
            <button onClick={() => onPickDate(recommended.purchase_date)} className="h-9 rounded-lg bg-navy-900 px-4 text-sm font-semibold text-white transition hover:bg-navy-800">
              Simulate buying on {fmtDate(recommended.purchase_date)}
            </button>
          )}
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Metric label="Balance after purchase" value={inr(selected.balance_after_purchase)} sub={`on ${fmtDate(sim.scenario.purchase_date)}`} />
        <Metric label="Lowest projected balance" value={inr(sim.simulated.min_balance)} sub={fmtDate(sim.simulated.min_balance_date)}
          alert={sim.simulated.min_balance < sim.assumptions.safety_buffer} />
        <Metric label="Liquidity runway" value={`${sim.runway_months_after} months`} sub={`${sim.runway_months_before} months before the purchase`} />
        <Metric label="Surplus recovery time" value={sim.months_to_recover ? `${sim.months_to_recover} months` : '—'} sub={`to rebuild at ${inr(sim.monthly_surplus)}/month surplus`} />
      </div>

      {planning}

      <Card>
        <CardHeader title="90-day balance projection" subtitle="Day-by-day simulation, with and without the purchase" action={<ProjectedTag />} />
        <ScenarioChart sim={sim} />
      </Card>

      {/* Impact horizons */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {sim.impacts.map((i) => (
          <Card key={i.day} className="!p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-navy-900">After {i.day} days</p>
              <p className="text-xs text-navy-400">{fmtDate(i.on)}</p>
            </div>
            <div className="mt-3 space-y-1.5 text-[13px]">
              <Row swatch="#94a3b8" label="Without" value={inr(i.baseline)} />
              <Row swatch="#4338ca" label="With purchase" value={inr(i.scenario)} />
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
              <span className="text-xs text-navy-500">Change</span>
              <span className="tabular flex items-center gap-1 text-sm font-semibold text-navy-900"><TrendingDown className="h-3.5 w-3.5 text-navy-400" />{signedInr(i.delta)}</span>
            </div>
          </Card>
        ))}
      </div>

      <TimingComparison sim={sim} onPick={onPickDate} />

      <Card>
        <CardHeader title="Cash-Flow Risk Analysis" subtitle={`For a purchase on ${fmtDate(sim.scenario.purchase_date)}, over the next ${sim.assumptions.horizon_days} days`} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-[13px]">
            <thead><tr className="border-b border-slate-200 text-left text-[11.5px] font-semibold uppercase tracking-wide text-navy-500">
              <th className="w-28 py-2 pr-3">Severity</th><th className="py-2 pr-3">Risk</th><th className="py-2">Detail (from the forecast)</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">{sim.risks.map((r, i) => <RiskRow key={i} risk={r} />)}</tbody>
          </table>
        </div>
        <details className="mt-4 rounded-xl bg-slate-50 p-3 text-[13px] text-navy-600">
          <summary className="cursor-pointer font-medium text-navy-800">How the recommendation was reached</summary>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5">{rec.explanation.map((line, i) => <li key={i}>{line}</li>)}</ol>
        </details>
      </Card>

      <Card className="!bg-slate-50/60">
        <div className="flex flex-wrap items-start gap-x-8 gap-y-3 text-xs text-navy-500">
          <div className="flex items-center gap-1.5 font-semibold text-navy-700"><Info className="h-3.5 w-3.5" /> Assumptions</div>
          <span>Horizon: {sim.assumptions.horizon_days} days</span>
          <span>Safety buffer: {inr(sim.assumptions.safety_buffer)}</span>
          <span>Day-to-day spend: {inr(sim.baseline.daily_variable_spend)}/day (median of last 3 months)</span>
          <span>Obligations: {sim.assumptions.include_obligations ? 'included' : 'excluded'}</span>
          <span>Irregular income: {sim.assumptions.include_irregular_income ? 'included' : 'excluded (conservative)'}</span>
        </div>
        <p className="mt-3 text-xs text-navy-400">{sim.disclaimer}</p>
      </Card>
    </>
  )
}

function Metric({ label, value, sub, alert }: { label: string; value: string; sub: string; alert?: boolean }) {
  return (
    <div className={`rounded-2xl border bg-white p-4 ${alert ? 'border-red-200' : 'border-slate-200/80'}`}>
      <p className="flex items-center gap-1.5 text-xs text-navy-500">
        {alert && <AlertTriangle className="h-3.5 w-3.5" style={{ color: 'var(--status-critical)' }} aria-label="Below buffer" />}
        {label}
      </p>
      <p className="tabular mt-2 text-xl font-semibold tracking-tight text-navy-900">{value}</p>
      <p className="mt-0.5 text-[11px] text-navy-400">{sub}</p>
    </div>
  )
}

function Row({ swatch, label, value }: { swatch: string; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="flex items-center gap-2 text-navy-500"><span className="h-0.5 w-3 rounded" style={{ background: swatch }} />{label}</span>
      <span className="tabular font-medium text-navy-900">{value}</span>
    </div>
  )
}

function TimingComparison({ sim, onPick }: { sim: PurchaseSimulation; onPick: (d: string) => void }) {
  const buffer = sim.assumptions.safety_buffer
  const values = sim.timing_options.map((o) => o.min_balance)
  const lo = Math.min(0, ...values)
  const hi = Math.max(buffer * 1.5, ...values)
  const scale = (v: number) => ((v - lo) / (hi - lo)) * 100
  return (
    <Card>
      <CardHeader title="When should you buy?" subtitle="Each date is simulated over the 90 days that follow it. Higher low point = safer."
        icon={<Clock className="h-4 w-4" />} />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-4">
        {sim.timing_options.map((o) => <TimingCard key={o.purchase_date} o={o} buffer={buffer} scale={scale} onPick={onPick} />)}
      </div>
    </Card>
  )
}

function TimingCard({ o, buffer, scale, onPick }: { o: TimingOption; buffer: number; scale: (v: number) => number; onPick: (d: string) => void }) {
  return (
    <button onClick={() => onPick(o.purchase_date)} aria-pressed={o.is_selected}
      className={`relative rounded-xl border p-4 text-left transition hover:shadow-md ${o.is_recommended ? 'border-brand-500 bg-brand-50/40 ring-1 ring-brand-500' : o.is_selected ? 'border-navy-900' : 'border-slate-200'}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[13px] font-semibold text-navy-900">{o.days_from_now === 0 ? 'Today' : fmtDate(o.purchase_date)}</p>
          <p className="text-[11px] text-navy-400">{o.days_from_now === 0 ? fmtDate(o.purchase_date) : o.label}</p>
        </div>
        {o.is_recommended ? <Badge tone="green" icon={<ShieldCheck className="h-3 w-3" />}>Best</Badge>
          : o.safe ? <Badge tone="green">Safe</Badge> : <Badge tone="red">Below buffer</Badge>}
      </div>
      <p className="mt-3 text-[11px] text-navy-500">Lowest balance</p>
      <p className="tabular text-lg font-semibold text-navy-900">{inr(o.min_balance)}</p>
      <div className="relative mt-2 h-2 rounded-full bg-slate-100" aria-hidden>
        <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
          style={{ width: `${Math.max(2, scale(Math.max(o.min_balance, 0)))}%`, background: o.safe ? 'var(--status-good)' : 'var(--status-critical)' }} />
        <div className="absolute -top-1 h-4 w-px bg-navy-900" style={{ left: `${scale(buffer)}%` }} title="Safety buffer" />
      </div>
      <p className="mt-2 text-[11px] text-navy-400">
        {o.days_below_buffer > 0 ? `${o.days_below_buffer} day(s) under buffer` : 'Never under buffer'} · low on {fmtDate(o.min_balance_date)}
      </p>
      {o.is_selected && <span className="absolute -top-2 left-3 rounded bg-navy-900 px-1.5 text-[10px] font-semibold text-white">Selected</span>}
    </button>
  )
}

const RISK = {
  critical: { Icon: AlertOctagon, color: 'var(--status-critical)', label: 'Critical' },
  high: { Icon: AlertTriangle, color: 'var(--status-critical)', label: 'High' },
  medium: { Icon: AlertTriangle, color: 'var(--status-warning)', label: 'Medium' },
  low: { Icon: ShieldCheck, color: 'var(--status-good)', label: 'Low' },
  info: { Icon: Info, color: 'var(--series-1)', label: 'Info' },
} as const

function RiskRow({ risk }: { risk: Risk }) {
  const { Icon, color, label } = RISK[risk.level]
  return (
    <tr className="align-top">
      <td className="py-2.5 pr-3">
        <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset" style={{ color }}>
          <Icon className="h-3.5 w-3.5" aria-hidden />{label}
        </span>
      </td>
      <td className="py-2.5 pr-3 font-medium text-navy-900">{risk.title}</td>
      <td className="py-2.5 text-navy-600">{risk.detail}</td>
    </tr>
  )
}

// What-ifs that aren't purchases open in the assistant, which runs them on the same engine.
const ASK: Record<string, string> = {
  add_subscription: 'What if I add a ₹499/month gym membership?',
  cancel_subscriptions: 'What if I cancel three subscriptions?',
  income_delay: 'What if my income is delayed by 15 days?',
  increase_savings: 'What if I increase my monthly savings by 10%?',
  unexpected_payment: 'What if I have an unexpected medical bill of ₹30,000?',
  expense_increase: 'What if my expenses increase by 20%?',
}

function ScenarioLibrary({ items }: { items: { type: string; title: string; description: string; status: string }[] }) {
  const more = useMemo(() => items.filter((i) => ASK[i.type]), [items])
  if (!more.length) return null
  return (
    <Card>
      <CardHeader title="More what-ifs" subtitle="Ask the AI assistant, or compare several side by side"
        action={<Link to="/simulator?view=compare" className="text-xs font-semibold text-navy-900 hover:underline">Compare →</Link>} />
      <ul className="space-y-1">
        {more.map((s) => (
          <li key={s.type}>
            <Link to={`/assistant?q=${encodeURIComponent(ASK[s.type])}`} className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 hover:bg-slate-50">
              <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-600" />
              <div>
                <p className="text-[13px] font-medium text-navy-800">{s.title}</p>
                <p className="text-[11px] text-navy-400">{s.description}</p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  )
}
