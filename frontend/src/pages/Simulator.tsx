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
import { addDays, fmtDate, fmtShort, inr, inrCompact, signedInr } from '../lib/format'
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

export default function Simulator() {
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

  return (
    <>
      <PageHeader
        eyebrow="What-if Simulator"
        title="Simulate a decision before you make it"
        description="Your financial twin replays your income, bills, obligations and day-to-day spending day by day — with and without the purchase — and tests alternative dates to find the safest moment to buy."
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-6 lg:sticky lg:top-6 lg:self-start">
          <Card>
            <CardHeader title="Scenario" subtitle="One-time purchase" icon={<Sparkles className="h-4 w-4 text-brand-600" />} />
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
                      <span className={`tabular block text-[11px] ${active ? 'text-slate-300' : 'text-navy-400'}`}>{inrCompact(p.amount)}</span>
                    </span>
                  </button>
                )
              })}
            </div>

            <label className="mt-5 block text-xs font-medium text-navy-700" htmlFor="sim-label">What are you buying?</label>
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

            <p className="mt-5 text-xs font-medium text-navy-700">When?</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <DateChip active={date === null} onClick={() => setDate(null)}>Today</DateChip>
              {sim?.timing_options.filter((o) => o.days_from_now > 0 && o.label.startsWith('After income')).slice(0, 2).map((o) => (
                <DateChip key={o.purchase_date} active={date === o.purchase_date} onClick={() => setDate(o.purchase_date)}>
                  Payday {fmtShort(o.purchase_date)}
                </DateChip>
              ))}
            </div>
            <div className="mt-2 flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-1.5">
              <CalendarDays className="h-4 w-4 text-navy-400" />
              <input type="date" aria-label="Custom purchase date" min={asOf} max={maxDate} value={date ?? asOf ?? ''}
                onChange={(e) => setDate(e.target.value && e.target.value !== asOf ? e.target.value : null)}
                className="w-full bg-transparent text-sm text-navy-800 outline-none" />
            </div>

            <div className="mt-5">
              <div className="flex items-center justify-between">
                <label htmlFor="sim-buffer" className="text-xs font-medium text-navy-700">Safety buffer</label>
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
                {cmp ? <PaymentOptions cmp={cmp} onChanged={() => setNonce((n) => n + 1)} /> : <Skeleton className="h-96" />}
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
  safe_now: { tone: 'from-emerald-600 to-emerald-700', Icon: CheckCircle2, tag: 'Affordable', ring: 'ring-emerald-500/30' },
  wait: { tone: 'from-navy-900 to-navy-800', Icon: Hourglass, tag: 'Better to wait', ring: 'ring-amber-400/30' },
  not_recommended: { tone: 'from-red-700 to-red-800', Icon: XCircle, tag: 'Not recommended', ring: 'ring-red-500/30' },
} as const

function Results({ sim, onPickDate, planning }: { sim: PurchaseSimulation; onPickDate: (d: string) => void; planning?: ReactNode }) {
  const rec = sim.recommendation
  const v = VERDICT[rec.verdict]
  const selected = sim.timing_options.find((o) => o.is_selected)!
  const recommended = sim.timing_options.find((o) => o.is_recommended)

  return (
    <>
      {/* Verdict */}
      <div className={`animate-fade-up relative overflow-hidden rounded-2xl bg-gradient-to-br ${v.tone} p-6 text-white shadow-lg sm:p-7`}>
        <div className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/5" aria-hidden />
        <div className="absolute -bottom-20 right-24 h-40 w-40 rounded-full bg-white/5" aria-hidden />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className={`rounded-2xl bg-white/10 p-3 ring-4 ${v.ring}`}><v.Icon className="h-7 w-7" /></div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/70">{v.tag} · {sim.scenario.label}</p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight sm:text-[28px]">{rec.headline}</h2>
              <p className="mt-1.5 max-w-xl text-sm text-white/80">
                {inr(sim.scenario.amount)} on {fmtDate(sim.scenario.purchase_date)} · lowest projected balance {inr(selected.min_balance)} vs. {inr(sim.assumptions.safety_buffer)} buffer
              </p>
            </div>
          </div>
          {recommended && !recommended.is_selected && (
            <button onClick={() => onPickDate(recommended.purchase_date)} className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-navy-900 shadow-sm transition hover:bg-brand-50">
              Simulate buying on {fmtShort(recommended.purchase_date)}
            </button>
          )}
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Metric label="Balance after purchase" value={inr(selected.balance_after_purchase)} sub={`on ${fmtShort(sim.scenario.purchase_date)}`} />
        <Metric label="Lowest projected balance" value={inr(sim.simulated.min_balance)} sub={fmtShort(sim.simulated.min_balance_date)}
          alert={sim.simulated.min_balance < sim.assumptions.safety_buffer} />
        <Metric label="Emergency runway" value={`${sim.runway_months_after} mo`} sub={`from ${sim.runway_months_before} months today`} />
        <Metric label="Recovery time" value={sim.months_to_recover ? `${sim.months_to_recover} mo` : '—'} sub={`at ${inr(sim.monthly_surplus)}/mo surplus`} />
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
              <p className="text-xs text-navy-400">{fmtShort(i.on)}</p>
            </div>
            <div className="mt-3 space-y-1.5 text-[13px]">
              <Row swatch="var(--series-1)" label="Without" value={inr(i.baseline)} />
              <Row swatch="var(--series-2)" label="With purchase" value={inr(i.scenario)} />
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
              <span className="text-xs text-navy-500">Change</span>
              <span className="tabular flex items-center gap-1 text-sm font-semibold text-navy-900"><TrendingDown className="h-3.5 w-3.5 text-navy-400" />{signedInr(i.delta)}</span>
            </div>
          </Card>
        ))}
      </div>

      <TimingComparison sim={sim} onPick={onPickDate} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Why this recommendation" subtitle="Generated from computed figures — no estimates by AI" />
          <ol className="space-y-3">
            {rec.explanation.map((line, i) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed text-navy-700">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-navy-700">{i + 1}</span>
                {line}
              </li>
            ))}
          </ol>
        </Card>
        <Card>
          <CardHeader title="Risk assessment" subtitle="For the date you selected" />
          <ul className="space-y-2.5">{sim.risks.map((r, i) => <RiskRow key={i} risk={r} />)}</ul>
        </Card>
      </div>

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
        {o.days_below_buffer > 0 ? `${o.days_below_buffer} day(s) under buffer` : 'Never under buffer'} · low on {fmtShort(o.min_balance_date)}
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
    <li className="flex gap-3 rounded-xl border border-slate-100 p-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0" style={{ color }} aria-hidden />
      <div className="min-w-0">
        <p className="text-sm font-medium text-navy-900">{risk.title} <span className="ml-1 text-[10px] font-semibold uppercase tracking-wide text-navy-400">{label}</span></p>
        <p className="mt-0.5 text-[13px] text-navy-500">{risk.detail}</p>
      </div>
    </li>
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
      <CardHeader title="More what-ifs" subtitle="Run in the AI assistant, on the same engine" />
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
