import { ArrowDownRight, ArrowRight, ArrowUpRight, CalendarClock, PiggyBank, Repeat, Wallet } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertsCard } from '../components/AlertsCard'
import { CashflowChart } from '../components/charts/CashflowChart'
import { MonthlyBars } from '../components/charts/MonthlyBars'
import { ProjectedTag } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState, PageSkeleton } from '../components/ui/States'
import { StatCard } from '../components/ui/StatCard'
import { StatusPill } from '../components/ui/StatusPill'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { daysBetween, fmtDate, fmtShort, greeting, inr, pct, recurringOrigin, signedInr } from '../lib/format'
import type { Dashboard, HealthIndicator } from '../lib/types'
import { ProvenanceTag } from '../components/Provenance'

export default function Overview() {
  const { data, error, loading, reload } = useApi(api.dashboard)
  if (loading && !data) return <PageSkeleton />
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data) return null
  const { kpis, forecast } = data
  const firstName = data.user_name.trim().split(' ')[0] || 'there'
  const delta90 = kpis.projected_balance_90 - kpis.current_balance
  const daysToIncome = kpis.next_income_date ? daysBetween(data.as_of, kpis.next_income_date) : null

  return (
    <>
      <PageHeader
        eyebrow={`As of ${fmtDate(data.as_of)}`}
        title={`${greeting()}, ${firstName}`}
        description={
          <>
            Where you stand today, and where your twin projects you’ll be in {forecast.assumptions.horizon_days} days. Check any purchase against it before you pay.
          </>
        }
        actions={<ProvenanceTag provenance={data.provenance} />}
      />

      <DecisionStrip />
      <AlertsCard />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard emphasis label="Available balance" icon={<Wallet className="h-4 w-4" />} value={inr(kpis.current_balance)}
          hint={daysToIncome !== null ? `Next income in ${daysToIncome} days · ${fmtShort(kpis.next_income_date!)}` : 'No regular income detected'} />
        <StatCard kind="derived" label="Monthly income" icon={<ArrowUpRight className="h-4 w-4 text-brand-600" />} value={inr(kpis.monthly_income)} hint="Regular, detected from recurring credits" />
        <StatCard kind="derived" label="Monthly spending" icon={<ArrowDownRight className="h-4 w-4 text-navy-400" />} value={inr(kpis.monthly_expenditure)} hint="Average of last 90 days, excl. investments" />
        <StatCard kind="derived" label="Savings rate" icon={<PiggyBank className="h-4 w-4 text-navy-400" />} value={pct(kpis.savings_rate)} hint={`incl. ${inr(kpis.monthly_investments)}/mo invested`} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Cash-flow trajectory" subtitle="Recorded balance (solid) and the twin's deterministic projection (dashed)." />
          <CashflowChart history={data.history} forecast={forecast} />
          <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 sm:grid-cols-4">
            <MiniStat label="In 90 days" value={inr(kpis.projected_balance_90)} sub={signedInr(delta90) + ' vs today'} projected />
            <MiniStat label="Lowest point" value={inr(forecast.min_balance)} sub={fmtShort(forecast.min_balance_date)} projected />
            <MiniStat label="Expected inflow" value={inr(forecast.total_inflow)} sub="next 90 days" projected />
            <MiniStat label="Expected outflow" value={inr(forecast.total_outflow)} sub="next 90 days" projected />
          </div>
        </Card>
        <HealthCard health={data.health} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Monthly cash flow" subtitle="Complete months only · actual transactions" />
          <MonthlyBars months={data.months} height={300} />
        </Card>
        <UpcomingCard data={data} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <CategoryCard data={data} />
        <SubscriptionsCard data={data} />
      </div>
    </>
  )
}

function MiniStat({ label, value, sub, projected }: { label: string; value: string; sub?: string; projected?: boolean }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-xs text-navy-500">{label}{projected && <span className="h-1.5 w-1.5 rounded-full border border-dashed border-blue-500" title="Projected" />}</p>
      <p className="tabular mt-1 text-[15px] font-semibold text-navy-900">{value}</p>
      {sub && <p className="text-[11px] text-navy-400">{sub}</p>}
    </div>
  )
}

function formatIndicator(h: HealthIndicator) {
  const v = Number(h.value)
  return h.unit === 'percent' ? pct(v) : h.unit === 'months' ? `${v.toFixed(1)} mo` : inr(v)
}

function HealthCard({ health }: { health: HealthIndicator[] }) {
  return (
    <Card>
      <CardHeader title="Financial health" subtitle="Rule-based indicators · estimates, not guarantees" />
      <ul className="divide-y divide-slate-100">
        {health.map((h) => (
          <li key={h.key} className="py-3 first:pt-0 last:pb-0" title={h.detail}>
            <div className="flex items-center justify-between">
              <span className="text-sm text-navy-700">{h.label}</span>
              <span className="tabular text-sm font-semibold text-navy-900">{formatIndicator(h)}</span>
            </div>
            <div className="mt-1 flex items-center justify-between gap-2">
              <span className="truncate text-[11px] text-navy-400">{h.detail}</span>
              <StatusPill status={h.status} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function UpcomingCard({ data }: { data: Dashboard }) {
  const events = data.upcoming_events.slice(0, 7)
  return (
    <Card>
      <CardHeader title="Next 30 days" subtitle="Expected income, bills & obligations" icon={<CalendarClock className="h-4 w-4" />} action={<ProjectedTag />} />
      <ul className="space-y-2.5">
        {events.map((e, i) => (
          <li key={i} className="flex items-center gap-3">
            <div className="w-11 shrink-0 rounded-lg bg-slate-50 py-1 text-center">
              <p className="text-[10px] uppercase text-navy-400">{new Date(`${e.on}T00:00:00`).toLocaleDateString('en-IN', { month: 'short' })}</p>
              <p className="text-sm font-semibold leading-none text-navy-900">{new Date(`${e.on}T00:00:00`).getDate()}</p>
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-navy-800">{e.label}</p>
              <p className="text-[11px] capitalize text-navy-400">{e.kind === 'obligation' ? 'Obligation' : e.category}</p>
            </div>
            <span className={`tabular text-sm font-medium ${e.amount > 0 ? 'text-brand-700' : 'text-navy-800'}`}>{signedInr(e.amount)}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function CategoryCard({ data }: { data: Dashboard }) {
  const max = Math.max(...data.categories.map((c) => c.monthly_average), 1)
  return (
    <Card>
      <CardHeader title="Where your money goes" subtitle="Monthly average · last 90 days" />
      <ul className="space-y-3">
        {data.categories.slice(0, 8).map((c) => (
          <li key={c.category} title={`${c.category}: ${inr(c.monthly_average)}/month (${pct(c.share)} of spending)`}>
            <div className="flex justify-between text-[13px]">
              <span className="text-navy-700">{c.category}</span>
              <span className="tabular font-medium text-navy-900">{inr(c.monthly_average)}</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-slate-100">
              <div className="h-1.5 rounded-full transition-all duration-700" style={{ width: `${(c.monthly_average / max) * 100}%`, background: 'var(--series-1)' }} />
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function SubscriptionsCard({ data }: { data: Dashboard }) {
  const subs = data.recurring.filter((r) => r.kind === 'subscription')
  return (
    <Card>
      <CardHeader title="Recurring subscriptions" subtitle={`${subs.length} active · ${inr(data.kpis.subscriptions_monthly)}/month`} icon={<Repeat className="h-4 w-4" />} />
      <ul className="divide-y divide-slate-100">
        {subs.map((s) => (
          <li key={s.key} className="flex items-center justify-between py-2.5 first:pt-0">
            <div>
              <p className="text-sm text-navy-800">{s.merchant}</p>
              <p className="text-[11px] text-navy-400">Renews {fmtShort(s.next_date)} · {recurringOrigin(s)}</p>
            </div>
            <span className="tabular text-sm font-medium text-navy-900">{inr(s.amount)}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 border-t border-slate-100 pt-3 text-xs text-navy-500">≈ {inr(data.kpis.subscriptions_monthly * 12)} per year</p>
    </Card>
  )
}


const JOURNEY = ['Understand your cash flow', 'Ask about a purchase', 'Compare payment choices', 'Get a PayPal checkout proposal', 'Confirm it yourself', 'See the PayPal result']

/** The product in one line: type an amount, and the agent tests it against your future before you pay. */
function DecisionStrip() {
  const navigate = useNavigate()
  const [amount, setAmount] = useState('75000')
  const [item, setItem] = useState('laptop')
  function go(e: React.FormEvent) {
    e.preventDefault()
    const n = Number(amount.replace(/[^\d.]/g, ''))
    if (!n) return
    navigate(`/assistant?q=${encodeURIComponent(`Should I buy a ₹${n.toLocaleString('en-IN')} ${item.trim() || 'purchase'}?`)}`)
  }
  return (
    <section className="mb-5 rounded-2xl bg-navy-900 p-5 text-white sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-emerald-300">Simulate before you pay</p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight">Thinking of buying something?</h2>
        </div>
        <form onSubmit={go} className="flex flex-1 flex-wrap items-center gap-2 sm:max-w-xl">
          <label className="sr-only" htmlFor="ds-amount">Amount in rupees</label>
          <div className="flex items-center rounded-xl bg-white/10 px-3 ring-1 ring-white/15 focus-within:ring-emerald-300">
            <span className="text-slate-300">₹</span>
            <input id="ds-amount" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} className="w-28 bg-transparent px-1.5 py-2 text-sm outline-none" />
          </div>
          <label className="sr-only" htmlFor="ds-item">What is it?</label>
          <input id="ds-item" value={item} maxLength={40} onChange={(e) => setItem(e.target.value)} placeholder="laptop" className="min-w-0 flex-1 rounded-xl bg-white/10 px-3 py-2 text-sm outline-none ring-1 ring-white/15 focus:ring-emerald-300" />
          <button type="submit" className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-400 px-4 py-2 text-sm font-semibold text-navy-950 hover:bg-emerald-300">
            Ask FINORA <ArrowRight className="h-4 w-4" />
          </button>
        </form>
      </div>
      <ol className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-[11.5px] text-slate-400">
        {JOURNEY.map((j, i) => (
          <li key={j} className={`flex items-center gap-1.5 ${i === 0 ? 'text-emerald-300' : ''}`}>
            <span className={`flex h-4 w-4 items-center justify-center rounded-full font-mono text-[9.5px] ${i === 0 ? 'bg-emerald-300 text-navy-950' : 'bg-white/10'}`}>{i + 1}</span>{j}
          </li>
        ))}
      </ol>
    </section>
  )
}
