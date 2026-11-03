import { Banknote, BrainCircuit, CalendarPlus, Repeat, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Badge } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState, ErrorState, PageSkeleton } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { fmtDate, fmtMonth, fmtShort, inr, pct, signedInr, titleCase } from '../lib/format'
import type { RecurringItem } from '../lib/types'

export default function Twin() {
  const twin = useApi(api.twin)
  const obligations = useApi(api.obligations)
  if (twin.loading && !twin.data) return <PageSkeleton />
  if (twin.error) return <ErrorState error={twin.error} onRetry={twin.reload} />
  if (!twin.data) return null
  const p = twin.data.profile
  const reloadAll = () => { twin.reload(); obligations.reload() }

  return (
    <>
      <PageHeader eyebrow="My Financial Twin" title="Your financial behaviour, modelled"
        description={`Learned from ${p.transaction_count} transactions since ${p.history_start ? fmtDate(p.history_start) : '—'}. This profile drives every forecast and simulation.`} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Fact label="Regular income" value={`${inr(p.monthly_income)}/mo`} />
        <Fact label="Avg. spending" value={`${inr(p.avg_monthly_spending)}/mo`} />
        <Fact label="Committed (recurring)" value={`${inr(p.recurring_outflow_monthly)}/mo`} />
        <Fact label="Day-to-day (variable)" value={`${inr(p.variable_monthly)}/mo`} />
        <Fact label="Essentials" value={`${inr(p.essential_monthly)}/mo`} />
        <Fact label="Invested" value={`${inr(p.avg_monthly_investments)}/mo`} />
        <Fact label="Savings rate" value={pct(p.savings_rate)} />
        <Fact label="Irregular income (90d)" value={inr(p.irregular_income_lookback)} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Income sources" subtitle="Recurring credits detected from history" icon={<Banknote className="h-4 w-4" />} />
          {p.recurring_income.length ? <RecurringTable items={p.recurring_income} /> : <EmptyState title="No regular income detected" message="Import at least three months of salary credits." />}
        </Card>
        <Card>
          <CardHeader title="How the twin learns" icon={<BrainCircuit className="h-4 w-4" />} />
          <ul className="space-y-2.5 text-[13px] leading-relaxed text-navy-600">
            <li><b className="text-navy-900">Recurring:</b> same merchant, ≥3 times, ~monthly (25–35 days apart), stable amount (±40%), seen in the last 45 days.</li>
            <li><b className="text-navy-900">Variable spending:</b> everything else, estimated per category as the median of the last three 30-day windows — robust to one-off spikes.</li>
            <li><b className="text-navy-900">Investments</b> (SIPs) count as savings, not spending.</li>
            <li><b className="text-navy-900">Obligations</b> are known future payments you add below.</li>
            <li className="text-navy-400">All maths is deterministic Decimal arithmetic — the same data always yields the same twin.</li>
          </ul>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Recurring commitments" subtitle={`${p.recurring_outflows.length} detected · ${inr(p.recurring_outflow_monthly)}/month`} icon={<Repeat className="h-4 w-4" />} />
        <RecurringTable items={p.recurring_outflows} />
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Spending behaviour by category" subtitle="Monthly · last 90 days" />
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead><tr className="text-left text-xs text-navy-400"><th className="pb-2 font-medium">Category</th><th className="pb-2 text-right font-medium">Average</th><th className="pb-2 text-right font-medium">Recurring</th><th className="pb-2 text-right font-medium">Variable*</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {p.categories.map((c) => (
                  <tr key={c.category}>
                    <td className="py-2 text-navy-800">{c.category} {c.essential && <Badge>Essential</Badge>}</td>
                    <td className="tabular py-2 text-right font-medium text-navy-900">{inr(c.monthly_average)}</td>
                    <td className="tabular py-2 text-right text-navy-500">{inr(c.recurring_monthly)}</td>
                    <td className="tabular py-2 text-right text-navy-500">{inr(c.variable_monthly)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[11px] text-navy-400">*Variable = median of last three 30-day windows; used for forecasting.</p>
        </Card>
        <Card>
          <CardHeader title="Monthly history" subtitle="Actual, from transactions" />
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead><tr className="text-left text-xs text-navy-400"><th className="pb-2 font-medium">Month</th><th className="pb-2 text-right font-medium">Income</th><th className="pb-2 text-right font-medium">Spending</th><th className="pb-2 text-right font-medium">Invested</th><th className="pb-2 text-right font-medium">Net</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {p.months.map((m) => (
                  <tr key={m.month}>
                    <td className="py-2 text-navy-800">{fmtMonth(m.month)} {m.partial && <span className="text-[10px] text-navy-400">(partial)</span>}</td>
                    <td className="tabular py-2 text-right">{inr(m.income)}</td>
                    <td className="tabular py-2 text-right">{inr(m.spending)}</td>
                    <td className="tabular py-2 text-right">{inr(m.investments)}</td>
                    <td className={`tabular py-2 text-right font-medium ${m.net >= 0 ? 'text-brand-700' : 'text-red-600'}`}>{signedInr(m.net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <ObligationsCard state={obligations} onChange={reloadAll} asOf={p.as_of} />
    </>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4">
      <p className="text-xs text-navy-500">{label}</p>
      <p className="tabular mt-1.5 text-lg font-semibold tracking-tight text-navy-900">{value}</p>
    </div>
  )
}

function RecurringTable({ items }: { items: RecurringItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead><tr className="text-left text-xs text-navy-400"><th className="pb-2 font-medium">Merchant</th><th className="pb-2 font-medium">Type</th><th className="pb-2 text-right font-medium">Amount</th><th className="pb-2 text-right font-medium">Day</th><th className="pb-2 text-right font-medium">Next</th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((r) => (
            <tr key={r.key}>
              <td className="py-2"><p className="text-navy-800">{r.merchant}</p><p className="text-[11px] text-navy-400">{r.category} · seen {r.occurrences}×</p></td>
              <td className="py-2"><Badge tone={r.kind === 'income' ? 'green' : r.kind === 'subscription' ? 'blue' : 'neutral'}>{titleCase(r.kind)}</Badge></td>
              <td className="tabular py-2 text-right font-medium text-navy-900">{inr(r.amount)}</td>
              <td className="tabular py-2 text-right text-navy-500">{r.day_of_month}</td>
              <td className="py-2 text-right text-navy-500">{fmtShort(r.next_date)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ObligationsCard({ state, onChange, asOf }: { state: ReturnType<typeof useApi<import('../lib/types').Obligation[]>>; onChange: () => void; asOf: string }) {
  const [form, setForm] = useState({ title: '', amount: '', due_on: '', category: 'Other' })
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const amount = Number(form.amount)
    if (!form.title.trim() || !(amount > 0) || !form.due_on) { setErr('Title, a positive amount and a due date are required.'); return }
    setBusy(true); setErr(null)
    try {
      await api.createObligation({ title: form.title.trim(), amount, due_on: form.due_on, category: form.category })
      setForm({ title: '', amount: '', due_on: '', category: 'Other' })
      onChange()
    } catch (e) { setErr(e instanceof ApiError ? [e.message, ...e.details].join(' — ') : String(e)) } finally { setBusy(false) }
  }
  async function remove(id: number) {
    try { await api.deleteObligation(id); onChange() } catch (e) { setErr(e instanceof Error ? e.message : String(e)) }
  }

  return (
    <Card className="mt-6">
      <CardHeader title="Upcoming obligations" subtitle="Known future payments included in every forecast" icon={<CalendarPlus className="h-4 w-4" />} />
      {state.error ? <ErrorState error={state.error} onRetry={state.reload} /> : (
        <>
          {state.data?.length ? (
            <ul className="divide-y divide-slate-100">
              {state.data.map((o) => (
                <li key={o.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div><p className="text-sm text-navy-800">{o.title}</p><p className="text-[11px] text-navy-400">{o.category} · due {fmtDate(o.due_on)}</p></div>
                  <div className="flex items-center gap-3">
                    <span className="tabular text-sm font-medium">{inr(o.amount)}</span>
                    <button onClick={() => remove(o.id)} aria-label={`Delete ${o.title}`} className="rounded-lg p-1.5 text-navy-400 hover:bg-red-50 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
                  </div>
                </li>
              ))}
            </ul>
          ) : !state.loading && <EmptyState title="No upcoming obligations" />}
          <form onSubmit={submit} className="mt-4 grid grid-cols-1 gap-2 border-t border-slate-100 pt-4 sm:grid-cols-[1fr_140px_160px_auto]">
            <input placeholder="e.g. Insurance renewal" value={form.title} maxLength={160} onChange={(e) => setForm({ ...form, title: e.target.value })} aria-label="Obligation title" className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy-700" />
            <input placeholder="Amount ₹" inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value.replace(/[^\d.]/g, '') })} aria-label="Amount" className="tabular rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy-700" />
            <input type="date" min={asOf} value={form.due_on} onChange={(e) => setForm({ ...form, due_on: e.target.value })} aria-label="Due date" className="rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy-700" />
            <button disabled={busy} className="rounded-lg bg-navy-900 px-4 py-2 text-sm font-medium text-white hover:bg-navy-800 disabled:opacity-50">Add</button>
          </form>
          {err && <p className="mt-2 text-xs text-red-600" role="alert">{err}</p>}
        </>
      )}
    </Card>
  )
}
