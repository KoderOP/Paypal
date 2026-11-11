import { ArrowRight, Bot, CheckCircle2, FileSpreadsheet, Gauge, Loader2, Lock, ShieldCheck, Sparkles, Wallet, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useDataStatus } from '../context/DataStatus'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'

const DEMO_QUESTION = 'Should I buy a ₹75,000 laptop?'

function Mark({ light = false }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="9" fill={light ? '#ffffff' : '#0b1b3a'} />
        <path d="M8 21l5-6 4 3 7-9" fill="none" stroke="#10b981" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className={`text-[15px] font-bold tracking-[0.14em] ${light ? 'text-white' : 'text-navy-900'}`}>FINORA</span>
    </div>
  )
}

/** The hero visual: one decision, start to finish. Illustrative, from the synthetic demo profile. */
function DecisionReceipt() {
  const [reduce] = useState(() => Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches))
  const [step, setStep] = useState(reduce ? 5 : 0)
  useEffect(() => {
    if (reduce) return
    const timers = [400, 1300, 2300, 3300, 4200].map((ms, i) => window.setTimeout(() => setStep(i + 1), ms))
    return () => timers.forEach(clearTimeout)
  }, [reduce])
  const row = (show: boolean) => (show ? 'rise' : 'opacity-0')

  return (
    <div className="relative mx-auto w-full max-w-[420px]" aria-label="Example: how FINORA answers a purchase question">
      <div className="absolute -inset-6 rounded-[36px] bg-brand-500/10 blur-2xl" aria-hidden />
      <div className="relative overflow-hidden rounded-[22px] bg-[#fbfaf7] text-navy-900 shadow-[0_30px_80px_-20px_rgba(0,0,0,.55)]">
        <div className="flex items-center justify-between border-b border-dashed border-slate-300 px-5 py-3">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-navy-500">Decision receipt</span>
          <span className="font-mono text-[10.5px] text-navy-400">example · synthetic profile</span>
        </div>

        <div className="space-y-3.5 px-5 py-4 text-[13px]">
          <div className={row(step >= 1)}>
            <p className="font-mono text-[10px] uppercase tracking-widest text-navy-400">You ask</p>
            <p className="mt-0.5 font-display text-[22px] leading-tight">“{DEMO_QUESTION}”</p>
          </div>

          <div className={row(step >= 2)}>
            <p className="font-mono text-[10px] uppercase tracking-widest text-navy-400">Groq agent picks a tool</p>
            <p className="mt-1 rounded-md bg-navy-900 px-2.5 py-1.5 font-mono text-[11.5px] text-emerald-300">
              compare_payment_options<span className="text-slate-400">(amount=75000)</span>
            </p>
          </div>

          <div className={row(step >= 3)}>
            <p className="font-mono text-[10px] uppercase tracking-widest text-navy-400">Engine simulates 90 days</p>
            <svg viewBox="0 0 300 70" className="mt-1.5 h-[70px] w-full" aria-hidden>
              <line x1="0" y1="58" x2="300" y2="58" stroke="#d03b3b" strokeOpacity=".5" strokeDasharray="4 4" />
              <text x="298" y="54" textAnchor="end" className="fill-red-600/70 font-mono" fontSize="8">buffer ₹20k</text>
              {step >= 3 && <>
                <path className="draw" style={{ ['--len' as string]: 420 }} d="M0 22 L40 26 L70 30 L95 18 L140 24 L190 14 L240 20 L300 10" fill="none" stroke="#2a78d6" strokeWidth="2" />
                <path className="draw [animation-delay:250ms]" style={{ ['--len' as string]: 420 }} d="M0 22 L8 63 L40 66 L70 66 L95 40 L140 46 L190 36 L240 42 L300 32" fill="none" stroke="#eb6834" strokeWidth="2" />
              </>}
            </svg>
            <ul className="mt-1 space-y-1">
              {[
                ['Pay in full today', 'dips below buffer', false],
                ['Wait for payday', 'stays safe', true],
                ['PayPal Pay in 4', 'stays safe · no interest', true],
              ].map(([name, note, ok], i) => (
                <li key={name as string} className={`flex items-center justify-between ${row(step >= 3)}`} style={{ animationDelay: `${150 * (i + 1)}ms` }}>
                  <span className="flex items-center gap-1.5">
                    {ok ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" /> : <XCircle className="h-3.5 w-3.5 text-red-600" />}
                    {name}
                  </span>
                  <span className={`font-mono text-[11px] ${ok ? 'text-emerald-700' : 'text-red-600'}`}>{note}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className={`flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-[12px] text-emerald-800 ${row(step >= 4)}`}>
            <ShieldCheck className="h-4 w-4 shrink-0" /> Guardrail: every figure traced to the engine · 0 invented
          </div>
        </div>

        <div className="perforation h-3 text-[#0b1b3a]" aria-hidden />
        <div className="relative bg-[#0b1b3a] px-5 py-4">
          <div className={`flex items-center justify-between gap-3 ${row(step >= 5)}`}>
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-slate-400">Drafted, not paid</p>
              <p className="text-[13px] font-medium text-white">PayPal Pay in 4 · awaiting you</p>
            </div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#ffc439] px-3.5 py-1.5 text-[12.5px] font-bold text-[#003087]">
              <Lock className="h-3.5 w-3.5" /> You confirm
            </span>
          </div>
          {step >= 5 && (
            <span className="stamp absolute right-4 -top-9 rounded-md border-2 border-emerald-600 px-2 py-0.5 font-mono text-[11px] font-bold uppercase tracking-widest text-emerald-700 bg-[#fbfaf7]/90">
              Safe choice
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function pct(v: number | null | undefined, digits = 0) {
  return v == null ? '—' : `${(v * 100).toFixed(digits)}%`
}

function Evidence() {
  const ev = useApi(api.evals)
  const d = ev.data
  const twin = d?.backtest?.results.perturbed?.aggregate.twin
  const seasonal = d?.backtest?.results.perturbed?.aggregate.seasonal_naive
  const red = d?.guardrail
  const agent = d?.agent.llm ?? d?.agent.rules
  const stats = [
    { k: 'Purchase-safety calls correct in a synthetic backtest', v: pct(twin?.decision_accuracy, 1),
      sub: seasonal ? `Seasonal-naive baseline: ${pct(seasonal.decision_accuracy, 1)}. Walk-forward, 60 noise-injected synthetic histories × 5 cut-offs. Not real-user accuracy.` : 'walk-forward backtest on synthetic histories' },
    { k: 'Corrupted AI answers caught', v: pct(red?.summary.corruption_detection_rate, 1), sub: red ? `${pct(red.summary.faithful_acceptance_rate)} of faithful answers still pass · n=${red.summary.corrupted_n} seeded corruptions` : 'guardrail red-team' },
    { k: 'Answers fully grounded', v: pct(agent?.summary.overall.grounded_rate), sub: agent ? `${agent.mode === 'llm' ? `Groq ${agent.model}, live` : 'deterministic planner'} · ${agent.summary.overall.n} benchmark questions` : 'agent benchmark' },
  ]
  return (
    <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-brand-700">Measured, not claimed</p>
          <h2 className="mt-2 font-display text-4xl text-navy-900 sm:text-5xl">Evidence you can rerun.</h2>
        </div>
        <Link to="/evals" className="inline-flex items-center gap-1.5 text-sm font-semibold text-navy-900 hover:underline">
          Full evaluation report <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
      <div className="mt-10 grid gap-px overflow-hidden rounded-2xl border border-slate-200 bg-slate-200 sm:grid-cols-3">
        {stats.map((s) => (
          <div key={s.k} className="bg-white p-6">
            <p className="font-display text-5xl tabular text-navy-900">{ev.loading ? <span className="skeleton inline-block h-10 w-28 rounded" /> : s.v}</p>
            <p className="mt-3 text-sm font-semibold text-navy-900">{s.k}</p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-navy-500">{s.sub}</p>
          </div>
        ))}
      </div>
      <p className="mt-4 max-w-3xl text-[12.5px] leading-relaxed text-navy-500">
        The forecast numbers come from synthetic histories generated by the same family of generator as the demo data, so they show
        the method works on regular monthly cash flow; they are not a measure of accuracy on real users. Dataset, baselines,
        method and limitations are on the <Link to="/evals" className="font-semibold text-navy-900 underline">evaluation page</Link>,
        and the backtest can be run on a real PayPal export.
      </p>
      <p className="mt-2 font-mono text-[11.5px] text-navy-400">$ cd backend && python -m evals.run_all</p>
    </section>
  )
}

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
      await api.loadSample('paypal_activity', true)  // generated server-side and stored as origin="sample"
      await refresh()
      navigate(`/assistant?q=${encodeURIComponent(DEMO_QUESTION)}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the demo. Is the backend running on :8000?')
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#f4f2ec]">
      <header className="relative grain overflow-hidden bg-[#071330] text-white">
        <div className="pointer-events-none absolute inset-0" aria-hidden
          style={{ background: 'radial-gradient(900px 500px at 85% 10%, rgba(16,185,129,.22), transparent 60%), radial-gradient(700px 400px at 0% 100%, rgba(0,156,222,.18), transparent 60%)' }} />
        <nav className="relative mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
          <Mark light />
          <div className="flex items-center gap-2">
            {status?.has_data && (
              <Link to="/" className="rounded-full border border-white/20 px-4 py-1.5 text-[13px] font-semibold hover:bg-white/10">Open my dashboard</Link>
            )}
            <Link to="/evals" className="hidden rounded-full px-3 py-1.5 text-[13px] text-slate-300 hover:text-white sm:inline">Evaluation</Link>
          </div>
        </nav>

        <div className="relative mx-auto grid max-w-6xl items-center gap-14 px-5 pb-24 pt-10 sm:px-8 lg:grid-cols-[1.1fr_0.9fr] lg:pt-16">
          <div>
            <p className="rise inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.18em] text-slate-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> PayPal · Groq · deterministic engine
            </p>
            <h1 className="rise mt-6 font-display text-[56px] leading-[0.95] tracking-tight [animation-delay:80ms] sm:text-[84px]">
              Simulate<br />before <em className="text-emerald-300">you pay.</em>
            </h1>
            <p className="rise mt-6 max-w-xl text-[17px] leading-relaxed text-slate-300 [animation-delay:160ms]">
              FINORA turns your PayPal activity into a day-by-day model of your cash flow. Ask about any purchase and an AI agent
              tests it against your future: pay now, wait for payday, or PayPal Pay in 4. It drafts the PayPal checkout.
              <span className="text-white"> Only you can send it.</span>
            </p>
            <div className="rise mt-9 flex flex-wrap items-center gap-3 [animation-delay:240ms]">
              <button onClick={() => void launchDemo()} disabled={busy}
                className="group inline-flex items-center gap-2 rounded-full bg-emerald-400 px-6 py-3 text-[15px] font-semibold text-[#071330] shadow-[0_10px_30px_-10px_rgba(16,185,129,.8)] transition hover:bg-emerald-300 disabled:opacity-70">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {busy ? 'Building your twin…' : 'Launch the live demo'}
                {!busy && <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />}
              </button>
              <Link to="/get-started" className="inline-flex items-center gap-2 rounded-full border border-white/20 px-6 py-3 text-[15px] font-semibold text-white hover:bg-white/10">
                <Wallet className="h-4 w-4" /> Use my PayPal data
              </Link>
            </div>
            <div className="rise mt-5 max-w-xl rounded-xl border border-amber-300/30 bg-amber-300/[0.07] px-4 py-3 text-[13px] leading-relaxed text-amber-100 [animation-delay:300ms]">
              <p className="mb-1 font-mono text-[10.5px] font-bold uppercase tracking-widest text-amber-300">Sample data</p>
              This is a fictional financial profile containing {sampleRows ? <b className="text-white">{sampleRows}</b> : 'about 285'} synthetic
              transactions, created to demonstrate FINORA’s financial intelligence. No real customer financial data is displayed.
              <span className="text-amber-200/80"> It uses PayPal’s Activity-report format, but none of it came from PayPal. Payments in the demo
              go through PayPal Sandbox (or a labelled simulation), never real money.</span>
            </div>
            {error && <p role="alert" className="mt-4 rounded-lg bg-red-500/15 px-3 py-2 text-sm text-red-200">{error}</p>}
          </div>
          <DecisionReceipt />
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-brand-700">One loop</p>
        <h2 className="mt-2 max-w-3xl font-display text-4xl text-navy-900 sm:text-5xl">From PayPal data to a payment you won't regret.</h2>
        <ol className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { icon: FileSpreadsheet, t: 'Read', d: 'PayPal Transaction Search or an Activity report. Multi-currency payments keep PayPal’s own rates and fees.' },
            { icon: Gauge, t: 'Model', d: 'A deterministic twin learns income cycles, recurring bills and variable spend, then projects every day for 90 days. Decimal money, no randomness.' },
            { icon: Bot, t: 'Decide', d: 'A Groq tool-calling agent chooses among 7 engine tools. A guardrail rejects any amount, percentage or date the engine didn’t produce.' },
            { icon: Lock, t: 'Act', d: 'The agent can only draft a PayPal Orders checkout. You confirm, approve on PayPal, then confirm the capture. Three human steps.' },
          ].map(({ icon: Icon, t, d }, i) => (
            <li key={t} className="relative">
              <span className="font-mono text-[11px] text-navy-400">0{i + 1}</span>
              <div className="mt-2 flex h-10 w-10 items-center justify-center rounded-xl bg-navy-900 text-emerald-300"><Icon className="h-5 w-5" /></div>
              <h3 className="mt-4 font-display text-3xl text-navy-900">{t}</h3>
              <p className="mt-2 text-[14px] leading-relaxed text-navy-600">{d}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="border-y border-slate-300/70 bg-white/60"><Evidence /></div>

      <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-brand-700">Safety by architecture</p>
            <h2 className="mt-2 font-display text-4xl text-navy-900 sm:text-5xl">The model talks. The engine counts. You pay.</h2>
          </div>
          <ul className="space-y-5">
            {[
              ['No money-moving tool exists.', 'The agent’s most powerful action is a proposal card. Creating a PayPal order needs your acknowledgement, approval happens on PayPal, and capture needs a second explicit confirmation.'],
              ['Numbers are computed, never generated.', 'Every figure comes from a pure, tested engine. Drafts with an ungrounded amount, percentage or date are replaced with the engine’s own wording, and the answer says so.'],
              ['It still works when the AI doesn’t.', 'No Groq key, rate-limited or down: a deterministic planner answers the core questions with the same tools, and the trace shows which path ran.'],
            ].map(([t, d]) => (
              <li key={t} className="flex gap-4 rounded-2xl border border-slate-200 bg-white p-5">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                <div><p className="font-semibold text-navy-900">{t}</p><p className="mt-1 text-[14px] leading-relaxed text-navy-600">{d}</p></div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <footer className="border-t border-slate-300/70">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-8 text-[12.5px] text-navy-500 sm:px-8">
          <Mark />
          <p>Projections are estimates from your own history, not financial advice. PayPal decides Pay Later eligibility at checkout.</p>
        </div>
      </footer>
    </div>
  )
}
