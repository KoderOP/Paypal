import { ArrowRight, BarChart3, CheckCircle2, FlaskConical, Gauge, Loader2, Lock, ShieldCheck, Sparkles, Wallet, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDataStatus } from '../context/DataStatus'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { fmtDate, inr } from '../lib/format'
import type { DemoPreview } from '../lib/types'

function Mark({ light = false }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="9" fill={light ? '#ffffff' : '#0b1b3a'} />
        <path d="M8 21l5-6 4 3 7-9" fill="none" stroke="#10b981" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className={`text-[15px] font-bold tracking-[0.12em] ${light ? 'text-white' : 'text-navy-900'}`}>FINORA</span>
    </div>
  )
}

/** Hero visual: the engine's real answer for the fictional sample profile. No figure here is typed by hand. */
function ImpactPreview() {
  const pv = useApi(api.demoPreview)
  const d = pv.data
  if (pv.error) {
    return (
      <div className="rounded-2xl bg-white p-6 text-sm text-navy-600 shadow-xl">
        The preview needs the FINORA backend. Start it, or launch the demo to see the full analysis.
      </div>
    )
  }
  if (!d) return <div className="h-[420px] animate-pulse rounded-2xl bg-white/10" aria-label="Loading preview" />
  return <PreviewCard d={d} />
}

function PreviewCard({ d }: { d: DemoPreview }) {
  const chosen = d.options.find((o) => o.id === d.recommendation.option_id) ?? d.options[0]
  const payNow = d.options.find((o) => o.kind === 'pay_now')
  const [first, ...later] = chosen.payments
  return (
    <div className="overflow-hidden rounded-2xl bg-white text-navy-900 shadow-[0_24px_60px_-20px_rgba(0,0,0,.5)]" aria-label="Payment impact preview for the sample profile">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <p className="text-[13px] font-semibold">Payment impact preview</p>
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900 ring-1 ring-inset ring-amber-300">
          <FlaskConical className="h-3 w-3" /> Sample profile · {fmtDate(d.as_of)}
        </span>
      </div>

      <div className="space-y-4 px-5 py-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-[12px] text-navy-500">Purchase</p>
            <p className="text-[15px] font-semibold">{d.label}</p>
          </div>
          <p className="tabular text-2xl font-semibold tracking-tight">{inr(d.amount)}</p>
        </div>

        <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[13px] font-semibold text-emerald-900">{chosen.name}</p>
            <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[10.5px] font-semibold text-white">Recommended</span>
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12.5px]">
            <dt className="text-navy-500">First payment</dt>
            <dd className="tabular text-right font-medium">{first ? `${inr(first.amount)} · ${first.on === d.as_of ? 'today' : fmtDate(first.on)}` : '—'}</dd>
            <dt className="text-navy-500">Later payments</dt>
            <dd className="tabular text-right font-medium">{later.length ? `${later.length} × ${inr(later[0].amount)}` : 'None'}</dd>
            <dt className="text-navy-500">Lowest projected balance</dt>
            <dd className="tabular text-right font-semibold">{inr(chosen.min_balance)}</dd>
            <dt className="text-navy-500">Safety buffer ({inr(d.safety_buffer)})</dt>
            <dd className="text-right">
              {chosen.safe
                ? <span className="inline-flex items-center gap-1 font-medium text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" />Stays above</span>
                : <span className="inline-flex items-center gap-1 font-medium text-red-700"><XCircle className="h-3.5 w-3.5" />Breached</span>}
            </dd>
          </dl>
          {later.length > 0 && (
            <ol className="mt-2 flex flex-wrap gap-1.5 border-t border-emerald-200/70 pt-2 text-[11px] text-navy-600">
              {chosen.payments.map((p) => (
                <li key={p.on} className="tabular rounded-md bg-white px-1.5 py-0.5 ring-1 ring-emerald-200">{fmtDate(p.on).replace(/ \d{4}$/, '')} · {inr(p.amount)}</li>
              ))}
            </ol>
          )}
        </div>

        {payNow && payNow.id !== chosen.id && (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 px-3 py-2.5 text-[12.5px]">
            <div>
              <p className="font-medium text-navy-800">{payNow.name}</p>
              <p className="text-navy-500">Lowest projected balance {inr(payNow.min_balance)}</p>
            </div>
            {payNow.safe
              ? <span className="text-emerald-700">Safe</span>
              : <span className="whitespace-nowrap rounded-full bg-red-50 px-2 py-0.5 font-medium text-red-700 ring-1 ring-inset ring-red-200">Below buffer {payNow.days_below_buffer} days</span>}
          </div>
        )}
      </div>

      <div className="flex items-start gap-2 border-t border-slate-100 bg-slate-50 px-5 py-3 text-[11.5px] leading-relaxed text-navy-500">
        <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>
          {chosen.illustrative_terms && 'Pay in 4 terms are illustrative; PayPal decides eligibility at checkout. '}
          FINORA prepares the checkout; you approve on PayPal and confirm the capture.
        </span>
      </div>
    </div>
  )
}

function pct(v: number | null | undefined, digits = 1) {
  return v == null ? '—' : `${(v * 100).toFixed(digits)}%`
}

/** Controlled evaluations only, clearly labelled as such. Methods and caveats live on the Evaluation page. */
function Evidence() {
  const ev = useApi(api.evals)
  const d = ev.data
  const twin = d?.backtest?.results.perturbed?.aggregate.twin
  const seasonal = d?.backtest?.results.perturbed?.aggregate.seasonal_naive
  const red = d?.guardrail
  const agent = d?.agent.llm
  const stats = [
    { k: 'Synthetic forecast backtest', v: pct(twin?.decision_accuracy), what: 'purchase-safety decisions correct',
      sub: seasonal ? `Seasonal-naive baseline ${pct(seasonal.decision_accuracy)}. Synthetic histories, not real customers.` : '' },
    { k: 'Guardrail red-team evaluation', v: pct(red?.summary.corruption_detection_rate), what: 'of deliberately corrupted answers caught',
      sub: red ? `${pct(red.summary.faithful_acceptance_rate, 0)} of correct answers still accepted (n = ${red.summary.corrupted_n} + ${red.summary.faithful_n}).` : '' },
    { k: 'Live Groq agent benchmark', v: pct(agent?.summary.overall.tool_accuracy), what: 'correct tool selection',
      sub: agent ? `${agent.summary.overall.n} questions on the sample profile; ${pct(agent.summary.overall.grounded_rate, 0)} of final answers grounded in engine figures.` : '' },
  ]
  return (
    <section className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-brand-700">Measured in controlled tests</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-navy-900 sm:text-[34px]">Evidence, with its limits stated</h2>
        </div>
        <Link to="/evals" className="inline-flex items-center gap-1.5 text-sm font-semibold text-[#003087] hover:underline">
          Methods, baselines and limitations <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.k} className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="text-[12px] font-semibold uppercase tracking-wide text-navy-500">{s.k}</p>
            <p className="tabular mt-3 text-4xl font-semibold tracking-tight text-navy-900">{ev.loading ? <span className="skeleton inline-block h-9 w-24 rounded" /> : s.v}</p>
            <p className="mt-1 text-sm font-medium text-navy-800">{s.what}</p>
            <p className="mt-2 text-[12.5px] leading-relaxed text-navy-500">{s.sub}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 text-[12.5px] text-navy-500">None of these is a real-world accuracy figure: they come from synthetic histories and the fictional sample profile.</p>
    </section>
  )
}

const STEPS = [
  { icon: Wallet, t: 'Understand your finances', d: 'Organise transaction history, recurring commitments and income.' },
  { icon: Gauge, t: 'Forecast your balance', d: 'Project future liquidity and upcoming obligations, day by day.' },
  { icon: BarChart3, t: 'Evaluate a purchase', d: 'Compare affordability and payment scenarios against your safety buffer.' },
  { icon: Lock, t: 'Take action with control', d: 'Review a PayPal checkout proposal and explicitly authorise the next step.' },
]

const TRUST = [
  ['Calculations come from a deterministic engine.', 'Balances, forecasts and payment comparisons are computed by tested code: same inputs, same results.'],
  ['AI interprets your request and picks the tool.', 'The assistant understands the question and selects which calculation to run. It doesn’t do the arithmetic.'],
  ['Financial claims are checked before you see them.', 'Amounts, percentages and dates in an AI answer are validated against the engine’s output; failing drafts are replaced and flagged.'],
  ['Payments need your explicit confirmation.', 'FINORA can prepare a PayPal checkout. You acknowledge it, approve it on PayPal, then confirm the capture.'],
]

export default function Landing() {
  const { status, refresh } = useDataStatus()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const files = useApi(api.demoFiles)
  const sampleRows = files.data?.find((f) => f.id === 'paypal_activity')?.rows

  async function launchDemo() {
    setBusy(true)
    setError(null)
    try {
      await api.loadSample('paypal_activity', true) // generated server-side and stored as origin="sample"
      await refresh()
      navigate('/assistant') // open Ask FINORA empty: the user chooses what to ask
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the demo. Is the backend running on :8000?')
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#f6f7f9]">
      <header className="relative overflow-hidden bg-[#0b1b3a] text-white">
        <div className="pointer-events-none absolute inset-0" aria-hidden
          style={{ background: 'radial-gradient(800px 420px at 90% 0%, rgba(0,156,222,.16), transparent 60%)' }} />
        <nav className="relative mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
          <Mark light />
          <div className="flex items-center gap-1">
            <Link to="/evals" className="rounded-full px-3 py-1.5 text-[13px] text-slate-300 hover:text-white">Evaluation</Link>
            {status?.has_data && (
              <Link to="/overview" className="rounded-full border border-white/20 px-4 py-1.5 text-[13px] font-semibold hover:bg-white/10">Open dashboard</Link>
            )}
          </div>
        </nav>

        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-5 pb-20 pt-8 sm:px-8 lg:grid-cols-[1.05fr_0.95fr] lg:pt-14">
          <div>
            <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-sky-300">Intelligent cash flow management</p>
            <h1 className="mt-4 text-[42px] font-semibold leading-[1.05] tracking-tight sm:text-[56px]">
              Know the impact before money moves.
            </h1>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-slate-300">
              Understand how a purchase affects your future balance, compare payment strategies, and make more informed decisions before checkout.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button onClick={() => void launchDemo()} disabled={busy}
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-white px-5 text-[15px] font-semibold text-[#0b1b3a] transition hover:bg-sky-50 disabled:opacity-70">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4 text-[#003087]" />}
                {busy ? 'Building your financial twin…' : 'Launch the live demo'}
                {!busy && <ArrowRight className="h-4 w-4" />}
              </button>
              <Link to="/get-started" className="inline-flex h-11 items-center gap-2 rounded-xl border border-white/25 px-5 text-[15px] font-semibold text-white hover:bg-white/10">
                Use my own data
              </Link>
            </div>
            {error && <p role="alert" className="mt-4 rounded-lg bg-red-500/15 px-3 py-2 text-sm text-red-200">{error}</p>}
            <div className="mt-6 max-w-xl rounded-xl border border-amber-300/30 bg-amber-300/[0.08] px-4 py-3 text-[13px] leading-relaxed text-amber-50">
              <p className="mb-1 text-[11px] font-bold uppercase tracking-widest text-amber-300">Sample data</p>
              This is a fictional financial profile containing {sampleRows ? <b className="text-white">{sampleRows}</b> : 'about 300'} synthetic
              transactions, created to demonstrate FINORA’s financial intelligence. No real customer financial data is displayed.
              <span className="text-amber-100/80"> It uses PayPal’s Activity-report format, but none of it came from PayPal. Demo payments run in PayPal Sandbox or a labelled simulation, never with real money.</span>
            </div>
          </div>
          <ImpactPreview />
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-brand-700">How FINORA works</p>
        <h2 className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight text-navy-900 sm:text-[34px]">From your transactions to a payment decision you control</h2>
        <ol className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(({ icon: Icon, t, d }, i) => (
            <li key={t} className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-navy-900 text-white"><Icon className="h-4.5 w-4.5" /></span>
                <span className="text-[12px] font-semibold text-navy-400">Step {i + 1}</span>
              </div>
              <h3 className="mt-4 text-[16px] font-semibold text-navy-900">{t}</h3>
              <p className="mt-1.5 text-[14px] leading-relaxed text-navy-600">{d}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="border-y border-slate-200 bg-white/70"><Evidence /></div>

      <section className="mx-auto max-w-6xl px-5 py-16 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[0.85fr_1.15fr]">
          <div>
            <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-brand-700">Trust and safety</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-navy-900 sm:text-[34px]">The AI explains. The engine calculates. You decide.</h2>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {TRUST.map(([t, d]) => (
              <li key={t} className="rounded-2xl border border-slate-200 bg-white p-5">
                <ShieldCheck className="h-5 w-5 text-brand-600" />
                <p className="mt-3 font-semibold text-navy-900">{t}</p>
                <p className="mt-1 text-[14px] leading-relaxed text-navy-600">{d}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <footer className="border-t border-slate-200">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-8 text-[12.5px] text-navy-500 sm:px-8">
          <Mark />
          <p>Projections are estimates from transaction history, not financial advice. PayPal decides Pay Later eligibility and terms at checkout.</p>
        </div>
      </footer>
    </div>
  )
}
