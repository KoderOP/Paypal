import { ArrowRight, CheckCircle2, Circle, FlaskConical, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ApiError, api } from '../lib/api'
import { fmtDate, inr, pct } from '../lib/format'
import type { Dashboard, ImportResult } from '../lib/types'
import { ErrorState } from './ui/States'

interface Step { title: string; detail: (d: Dashboard, r: ImportResult) => string }

const STEPS: Step[] = [
  { title: 'Reading your file', detail: (_, r) => `${r.rows} rows read · ${r.imported} new transactions${r.skipped_duplicates ? ` · ${r.skipped_duplicates} duplicates skipped` : ''}` },
  { title: 'Reconciling your balance', detail: (d) => `Current balance ${inr(d.kpis.current_balance)}, rebuilt from ${d.history.length} days of activity` },
  { title: 'Detecting income cycles', detail: (d) => {
    const inc = d.recurring.filter((r) => r.direction === 'in')
    return inc.length ? `${inc.map((i) => `${inr(i.amount)} from ${i.merchant}`).join(', ')} · next on ${fmtDate(inc[0].next_date)}` : 'No regular income found'
  } },
  { title: 'Finding recurring payments', detail: (d) => {
    const out = d.recurring.filter((r) => r.direction === 'out')
    const subs = out.filter((r) => r.kind === 'subscription')
    return `${out.length} recurring payments, incl. ${subs.length} subscriptions (${inr(d.kpis.subscriptions_monthly)}/mo)`
  } },
  { title: 'Learning your spending habits', detail: (d) => `${d.categories.length} categories · ${inr(d.kpis.monthly_expenditure)}/month on average` },
  { title: 'Projecting the next 90 days', detail: (d) => `Balance in 90 days ${inr(d.kpis.projected_balance_90)} · lowest point ${inr(d.forecast.min_balance)} on ${fmtDate(d.forecast.min_balance_date)}` },
  { title: 'Running a health check', detail: (d) => {
    const runway = d.health.find((h) => h.key === 'runway')
    return `Savings rate ${pct(d.kpis.savings_rate)}${runway ? ` · emergency runway ${Number(runway.value).toFixed(1)} months` : ''}`
  } },
]

const SECTIONS = ['Overview', 'My Financial Twin', 'What-if Simulator', 'Transactions']

export function AnalysisRun({ result, onDone, onSimulate }: { result: ImportResult; onDone: () => void; onSimulate: () => void }) {
  const [dash, setDash] = useState<Dashboard | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [done, setDone] = useState(0)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    api.dashboard().then((d) => !cancelled && setDash(d)).catch((e) => !cancelled && setError(e instanceof ApiError ? e : new ApiError(0, String(e))))
    return () => { cancelled = true }
  }, [attempt])

  useEffect(() => {
    if (!dash || done >= STEPS.length) return
    const t = setTimeout(() => setDone((n) => n + 1), done === 0 ? 400 : 650)
    return () => clearTimeout(t)
  }, [dash, done])

  if (error) return <ErrorState error={error} onRetry={() => { setError(null); setAttempt((a) => a + 1) }} />
  const finished = dash !== null && done >= STEPS.length

  return (
    <div className="mx-auto max-w-2xl animate-fade-up">
      <div className="rounded-3xl border border-slate-200/80 bg-white p-6 shadow-xl shadow-navy-900/5 sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-600">{finished ? 'Analysis complete' : 'Analysing'}</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-navy-900">{finished ? 'Your financial twin is ready' : 'Building your financial twin…'}</h2>
        {result.warnings.length > 0 && (
          <ul className="mt-3 rounded-xl bg-amber-50 p-3 text-xs text-amber-800">{result.warnings.map((w) => <li key={w}>• {w}</li>)}</ul>
        )}
        <ol className="mt-6 space-y-1">
          {STEPS.map((s, i) => {
            const state = !dash ? (i === 0 ? 'active' : 'pending') : i < done ? 'done' : i === done ? 'active' : 'pending'
            return (
              <li key={s.title} className={`flex gap-3 rounded-xl px-3 py-2.5 transition ${state === 'active' ? 'bg-slate-50' : ''}`}>
                {state === 'done' ? <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                  : state === 'active' ? <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-navy-700" />
                  : <Circle className="mt-0.5 h-5 w-5 shrink-0 text-slate-300" />}
                <div>
                  <p className={`text-sm font-medium ${state === 'pending' ? 'text-navy-400' : 'text-navy-900'}`}>{s.title}</p>
                  {state === 'done' && dash && <p className="tabular animate-fade-up text-[13px] text-navy-500">{s.detail(dash, result)}</p>}
                </div>
              </li>
            )
          })}
        </ol>
        {finished && (
          <div className="mt-6 animate-fade-up border-t border-slate-100 pt-5">
            <div className="flex flex-wrap gap-2">
              {SECTIONS.map((s) => (
                <span key={s} className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700">
                  <CheckCircle2 className="h-3.5 w-3.5" /> {s} ready
                </span>
              ))}
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <button onClick={onDone} className="inline-flex items-center gap-1.5 rounded-xl bg-navy-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-navy-800">
                Open my dashboard <ArrowRight className="h-4 w-4" />
              </button>
              <button onClick={onSimulate} className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-navy-900 hover:bg-slate-50">
                <FlaskConical className="h-4 w-4 text-brand-600" /> Simulate a purchase
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
