import { ArrowRight, Clock, Coins, Globe2, Info, Percent, TrendingDown, Users } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Badge, ProjectedTag } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState, ErrorState, PageSkeleton } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { fmtDate, fmtShort, inr, pct, signedInr } from '../lib/format'
import type { CrossBorder as CB, CurrencySummary } from '../lib/types'

const fx = (cur: string, v: number) => `${cur} ${v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default function CrossBorder() {
  const res = useApi(api.crossBorder)
  // After saving a reference rate the server returns the updated view; show that instead of the first fetch.
  const [updated, setData] = useState<CB | null>(null)
  const data = updated ?? res.data

  if (res.loading && !data) return <PageSkeleton />
  if (res.error) return <ErrorState error={res.error} onRetry={res.reload} />
  if (!data) return null

  if (!data.has_foreign) {
    return (
      <>
        <PageHeader eyebrow="Cross-border income" title="Paid from abroad through PayPal?" />
        <Card>
          <EmptyState title="No foreign-currency income found"
            message="Upload a PayPal Activity report that includes your international payments and PayPal's currency conversions. Or try the freelancer demo file (USD clients, synthetic data)."
            action={<Link to="/get-started?method=paypal_activity" className="inline-flex items-center gap-1.5 rounded-xl bg-[#003087] px-4 py-2 text-sm font-semibold text-white">Upload a PayPal report <ArrowRight className="h-4 w-4" /></Link>} />
        </Card>
      </>
    )
  }

  const main = data.currencies[0]
  const cur = data.sensitivity_currency ?? main.currency
  return (
    <>
      <PageHeader eyebrow="Cross-border income" title="Your income from abroad, decoded"
        description={`What PayPal's fees and conversions cost you, and how exposed you are to the ${cur}/INR rate and to clients paying late. Every rate comes from your own PayPal report.`} />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Tile icon={<Globe2 className="h-4 w-4" />} label={`Regular income in ${cur}`} value={pct(data.foreign_share, 0)} sub={`${data.clients.length} client(s)`} />
        <Tile icon={<Coins className="h-4 w-4" />} label="Received" value={fx(main.currency, main.gross)} sub={`${inr(main.received_home)} landed · ${main.payments} payments`} />
        <Tile icon={<Percent className="h-4 w-4" />} label="PayPal fees" value={fx(main.currency, main.fees)} sub={`${pct(main.fee_pct)} of gross · ≈ ${inr(main.fee_cost_home)}`} />
        <Tile icon={<TrendingDown className="h-4 w-4" />} label="Rate PayPal applied" value={`₹${main.avg_rate.toFixed(2)}`} sub={`average · latest ₹${main.latest_rate.toFixed(2)} (${fmtShort(main.latest_rate_on)})`} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title={`What if ${cur}/INR moves?`} action={<ProjectedTag />} subtitle="Your regular foreign income re-priced, everything else unchanged, over the next 90 days." />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-[13px]">
              <thead><tr className="text-left text-xs text-navy-400"><th className="pb-2 font-medium">{cur}/INR</th><th className="pb-2 text-right font-medium">Income per month</th><th className="pb-2 text-right font-medium">Balance in 90 days</th><th className="pb-2 text-right font-medium">Lowest balance</th><th className="pb-2 text-right font-medium" /></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.sensitivity.map((s) => (
                  <tr key={s.change_pct}>
                    <td className="py-2.5 font-medium text-navy-900">{s.change_pct > 0 ? '+' : '−'}{Math.abs(s.change_pct)}%</td>
                    <td className={`tabular py-2.5 text-right ${s.monthly_effect < 0 ? 'text-navy-900' : 'text-brand-700'}`}>{signedInr(s.monthly_effect)}</td>
                    <td className="tabular py-2.5 text-right">{signedInr(s.end_balance_delta)}</td>
                    <td className="tabular py-2.5 text-right">{inr(s.min_balance)}</td>
                    <td className="py-2.5 text-right">{s.below_buffer ? <Badge tone="red">Below buffer</Badge> : <Badge tone="green">OK</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex flex-wrap gap-2 text-[13px]">
            <Link to={`/assistant?q=${encodeURIComponent(`What if ${cur}/INR drops 3%?`)}`} className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-navy-800 hover:bg-slate-50">Ask the assistant</Link>
            <Link to="/simulator?view=compare" className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-navy-800 hover:bg-slate-50">Compare scenarios</Link>
          </div>
        </Card>

        <Card>
          <CardHeader title="Clients" icon={<Users className="h-4 w-4" />} subtitle="Regular payers, detected from history" />
          <ul className="divide-y divide-slate-100">
            {data.clients.map((c) => (
              <li key={c.merchant} className="py-2.5 first:pt-0">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate text-sm font-medium text-navy-900">{c.merchant}</p>
                  <p className="tabular text-sm font-semibold text-navy-900">{inr(c.monthly_home)}</p>
                </div>
                <p className="text-[11px] text-navy-400">{fx(c.currency, c.monthly_foreign)} net/mo · {pct(c.share_of_income, 0)} of income · next {fmtShort(c.next_date)}</p>
              </li>
            ))}
          </ul>
          {data.late_client && (
            <div className={`mt-3 rounded-xl p-3 text-[13px] ${data.late_client.first_below_buffer ? 'bg-red-50 text-red-800' : 'bg-slate-50 text-navy-700'}`}>
              <p className="flex items-center gap-1.5 font-semibold"><Clock className="h-3.5 w-3.5" /> If {data.late_client.merchant} pays {data.late_client.days} days late</p>
              <p className="mt-1">Lowest balance {inr(data.late_client.min_balance)} on {fmtDate(data.late_client.min_balance_date)}
                {data.late_client.first_below_buffer ? `, under your buffer from ${fmtShort(data.late_client.first_below_buffer)}.` : ', still above your buffer.'}</p>
            </div>
          )}
        </Card>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="What you're paying to get paid" icon={<Info className="h-4 w-4" />} />
          <ul className="space-y-2 text-[13px] text-navy-700">{data.insights.map((l, i) => <li key={i}>• {l}</li>)}</ul>
          <p className="mt-4 rounded-xl bg-slate-50 p-3 text-[13px] text-navy-600"><b className="text-navy-800">When should I withdraw?</b> {data.withdrawal_note}</p>
          <p className="mt-3 text-[11px] text-navy-400">{data.disclaimer}</p>
        </Card>
        {data.currencies.map((c) => <ReferenceRate key={c.currency} c={c} onSaved={setData} />)}
      </div>
    </>
  )
}

function ReferenceRate({ c, onSaved }: { c: CurrencySummary; onSaved: (d: CB) => void }) {
  const [text, setText] = useState(c.reference_rate ? String(c.reference_rate) : '')
  const [error, setError] = useState<string | null>(null)
  const rate = Number(text)
  async function save(value: number | null) {
    setError(null)
    try { onSaved(await api.setReferenceRate(c.currency, value)) } catch (e) { setError(e instanceof ApiError ? e.message : String(e)) }
  }
  return (
    <Card>
      <CardHeader title={`Conversion cost (${c.currency} → INR)`} icon={<Coins className="h-4 w-4" />}
        subtitle="Optional: enter the market rate you'd compare against, e.g. from your bank or a rates site." />
      <div className="flex gap-2">
        <div className="flex flex-1 items-center rounded-lg border border-slate-200 px-2.5 focus-within:border-navy-700">
          <span className="text-sm text-navy-400">₹</span>
          <input aria-label={`Reference rate, INR per ${c.currency}`} inputMode="decimal" value={text} placeholder="e.g. 84.10"
            onChange={(e) => setText(e.target.value.replace(/[^\d.]/g, ''))} className="tabular w-full bg-transparent px-1.5 py-2 text-sm outline-none" />
          <span className="text-xs text-navy-400">per {c.currency}</span>
        </div>
        <button disabled={!(rate > 0)} onClick={() => void save(rate)} className="rounded-lg bg-navy-900 px-3 text-sm font-semibold text-white disabled:opacity-40">Compare</button>
        {c.reference_rate && <button onClick={() => { setText(''); void save(null) }} className="rounded-lg border border-slate-200 px-3 text-sm font-medium text-navy-700">Clear</button>}
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      {c.reference_rate && c.spread_cost_home != null && c.spread_pct != null ? (
        <div className="mt-4 rounded-xl bg-slate-50 p-3 text-[13px]">
          <p className="tabular text-xl font-semibold text-navy-900">{inr(Math.max(0, c.spread_cost_home))}</p>
          <p className="text-navy-600">{c.spread_cost_home > 0
            ? `lost to conversion vs ₹${c.reference_rate} (${pct(c.spread_pct)} below), on ${fx(c.currency, c.net)} converted.`
            : `PayPal's average rate was at or better than ₹${c.reference_rate}.`}</p>
        </div>
      ) : (
        <p className="mt-3 text-[12px] text-navy-400">FINORA doesn't fetch market rates, so nothing here is a guess.</p>
      )}
    </Card>
  )
}

function Tile({ icon, label, value, sub }: { icon: ReactNode; label: string; value: string; sub: string }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4">
      <p className="flex items-center gap-1.5 text-xs text-navy-500"><span className="text-navy-400">{icon}</span>{label}</p>
      <p className="tabular mt-2 text-xl font-semibold tracking-tight text-navy-900">{value}</p>
      <p className="mt-0.5 text-[11px] text-navy-400">{sub}</p>
    </div>
  )
}
