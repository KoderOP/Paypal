import { FlaskConical, Microscope, ShieldCheck, Terminal, TrendingUp } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState, PageSkeleton } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import type { AgentEval, BacktestModel, EvalBlock, RedteamSummary } from '../lib/types'

const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`)
const MODEL_NAMES: Record<string, string> = {
  twin: 'FINORA twin', seasonal_naive: 'Seasonal naive (replay last 30 days)', linear_drift: 'Linear drift (90-day average)', flat: 'Flat balance',
}
const VARIANT_NAMES: Record<string, string> = {
  engine_reply: 'Engine reply, verbatim', lakh_k_notation: 'Amounts in lakh / K notation', rounded_to_rupee: 'Amounts rounded to the rupee',
  long_month_dates: 'Dates as “November 15”', scale_x1_05: 'One amount ×1.05', 'scale_x1.05': 'One amount ×1.05', 'scale_x1.2': 'One amount ×1.2',
  'scale_x0.5': 'One amount halved', 'small_error_x1.005': 'One amount ×1.005', digit_transposition: 'Two digits swapped',
  fabricated_sentence: 'Fabricated extra sentence', date_shift_3d: 'Date moved 3 days', percent_plus_5: 'Percentage +5 points',
}

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return <th className={`px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-navy-500 ${right ? 'text-right' : 'text-left'}`}>{children}</th>
}
function Td({ children, right, strong }: { children: React.ReactNode; right?: boolean; strong?: boolean }) {
  return <td className={`px-3 py-2 text-[13px] ${right ? 'tabular text-right' : ''} ${strong ? 'font-semibold text-navy-900' : 'text-navy-700'}`}>{children}</td>
}

function AgentTable({ a }: { a: AgentEval }) {
  const rows: [string, EvalBlock][] = [
    ['Overall', a.summary.overall], ['Wording the planner was written for', a.summary.seen_wording], ['Held-out paraphrases', a.summary.paraphrases],
    ...Object.entries(a.summary.by_category).map(([k, v]) => [`· ${k.replace(/_/g, ' ')}`, v] as [string, EvalBlock]),
  ]
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px]">
        <thead className="border-b border-slate-200"><tr><Th>Slice</Th><Th right>n</Th><Th right>Tool</Th><Th right>Arguments</Th><Th right>Grounded</Th><Th right>Rewrites</Th><Th right>p50</Th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map(([name, s], i) => (
            <tr key={name}>
              <Td strong={i < 3}>{name}</Td><Td right>{s.n}</Td><Td right>{pct(s.tool_accuracy)}</Td><Td right>{pct(s.arg_accuracy)}</Td>
              <Td right>{pct(s.grounded_rate)}</Td><Td right>{pct(s.guardrail_replaced)}</Td><Td right>{s.latency_ms_p50 == null ? '—' : `${Math.round(s.latency_ms_p50)} ms`}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RedteamTable({ s, flat }: { s: RedteamSummary; flat: RedteamSummary }) {
  const entries = Object.entries(s.by_variant).sort(([, a], [, b]) => Number(a.acceptance_rate == null) - Number(b.acceptance_rate == null))
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px]">
        <thead className="border-b border-slate-200"><tr><Th>Draft</Th><Th>Should be</Th><Th right>n</Th><Th right>Shipped</Th><Th right>Flat 1% (ablation)</Th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {entries.map(([v, d]) => {
            const accept = d.acceptance_rate != null
            const mine = accept ? d.acceptance_rate : d.detection_rate
            const other = accept ? flat.by_variant[v]?.acceptance_rate : flat.by_variant[v]?.detection_rate
            return (
              <tr key={v}>
                <Td>{VARIANT_NAMES[v] ?? v}</Td>
                <Td><Badge tone={accept ? 'green' : 'amber'}>{accept ? 'accepted' : 'caught'}</Badge></Td>
                <Td right>{d.n}</Td><Td right strong>{pct(mine)}</Td>
                <Td right><span className={other != null && mine != null && other < mine - 0.05 ? 'text-red-600' : ''}>{pct(other)}</span></Td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function BacktestTable({ agg }: { agg: Record<string, BacktestModel> }) {
  const rows = Object.entries(agg).sort(([, a], [, b]) => a.path_mae - b.path_mae)
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px]">
        <thead className="border-b border-slate-200"><tr><Th>Forecaster</Th><Th right>Daily balance MAE</Th><Th right>% of income</Th><Th right>Low-point MAE</Th><Th right>Decision accuracy</Th><Th right>False-safe</Th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map(([m, a]) => (
            <tr key={m} className={m === 'twin' ? 'bg-brand-50/50' : ''}>
              <Td strong={m === 'twin'}>{MODEL_NAMES[m] ?? m}</Td>
              <Td right>₹{a.path_mae.toLocaleString('en-IN')}</Td><Td right>{a.path_mae_pct_income}%</Td>
              <Td right>₹{a.low_point_mae.toLocaleString('en-IN')}</Td><Td right strong={m === 'twin'}>{pct(a.decision_accuracy)}</Td><Td right>{pct(a.false_safe_rate)}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Evals() {
  const ev = useApi(api.evals)
  if (ev.loading) return <PageSkeleton />
  if (ev.error || !ev.data) return <ErrorState error={ev.error ?? new Error('No evaluation data')} onRetry={ev.reload} />
  const d = ev.data
  return (
    <>
      <PageHeader eyebrow="Evaluation" title="How we know it works"
        description="Four reproducible evaluations from backend/evals. This page shows the committed results unmodified; nothing is computed in the browser." />

      <div className="mb-5 rounded-2xl border-2 border-amber-300 bg-amber-50 px-5 py-4 text-[13px] leading-relaxed text-amber-950">
        <p className="font-semibold">None of these numbers is real-customer accuracy.</p>
        <p className="mt-1">The forecast backtest runs on <b>synthetic histories</b>; the agent benchmarks run on the <b>fictional sample profile</b>.
          They show the method works and is measured honestly. Real-world accuracy would need real histories: run
          <code className="mx-1 font-mono">python -m evals.forecast_backtest --file &lt;your PayPal export&gt;</code>on your own data.</p>
        <ol className="mt-2 grid gap-x-6 gap-y-0.5 sm:grid-cols-2">
          <li>1 · Synthetic forecast backtest</li><li>2 · Guardrail red-team (seeded corruptions)</li>
          <li>3 · Live Groq agent benchmark</li><li>4 · Offline deterministic planner benchmark</li>
        </ol>
      </div>

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-navy-900 px-5 py-4 text-white">
        <p className="flex items-center gap-2 text-sm"><Terminal className="h-4 w-4 text-emerald-300" /> Reproduce every number:</p>
        <code className="rounded-lg bg-white/10 px-3 py-1.5 font-mono text-[12.5px] text-emerald-200">{d.reproduce}</code>
      </div>

      <div className="space-y-5">
        <Card>
          <CardHeader icon={<TrendingUp className="h-4 w-4" />} title="1 · Forecast backtest on synthetic histories: is the purchase safe?"
            subtitle={`Walk-forward: the twin sees only history before each cut-off, forecasts ${d.backtest?.horizon_days ?? 30} days, and is scored against what happened. “Decision” = is a purchase of 10–150% of monthly income safe above the ₹20,000 buffer? False-safe = predicted safe, actually breached.`} />
          <dl className="mb-5 grid gap-3 text-[12.5px] sm:grid-cols-2">
            {[
              ['Dataset', 'Synthetic only. 30 seeds × 2 personas (salaried; USD freelancer paid via PayPal) = 60 six-month histories per condition, from the same generator family as the demo. “Noise-injected” adds late income (−3…+4 days), 10% skipped bills, random one-offs and ±25% monthly spend.'],
              ['Baselines', 'Flat balance; linear drift (90-day average daily net flow); seasonal naive (replay the last 30 days of flows), a strong baseline for monthly cash flow.'],
              ['Method', 'Walk-forward: 5 cut-offs per history; each model sees only transactions before the cut-off and forecasts 30 days. Decision = is a purchase of 10–150% of monthly income, made on the cut-off day, safe above the ₹20,000 buffer?'],
              ['Limitations', 'Not real-user accuracy. The generator has the monthly structure the twin looks for, which favours it; real histories are messier. Single deterministic path; 30-day horizon only. Run it on a real export: python -m evals.forecast_backtest --file export.csv'],
            ].map(([k, v]) => (
              <div key={k} className={`rounded-xl p-3 ${k === 'Limitations' ? 'bg-amber-50 text-amber-900' : 'bg-slate-50 text-navy-700'}`}>
                <dt className="font-semibold">{k}</dt><dd className="mt-0.5 leading-relaxed">{v}</dd>
              </div>
            ))}
          </dl>
          {d.backtest ? Object.entries(d.backtest.results).map(([cond, r]) => (
            <div key={cond} className="mb-6 last:mb-0">
              <p className="mb-2 text-[13px] font-semibold text-navy-900">
                {cond === 'clean' ? 'Clean synthetic histories' : cond === 'perturbed' ? 'Noise-injected histories (late income, skipped bills, one-offs, ±25% spend)' : cond}
                <span className="ml-2 font-normal text-navy-500">{r.n_histories} histories × {r.cutoffs_per_history} cut-offs</span>
              </p>
              <BacktestTable agg={r.aggregate} />
            </div>
          )) : <p className="text-sm text-navy-500">Not run yet.</p>}

        </Card>

        <Card>
          <CardHeader icon={<ShieldCheck className="h-4 w-4" />} title="2 · Guardrail red-team: does it catch made-up numbers?"
            subtitle="For every benchmark question we take the engine’s correct answer, then rewrite it faithfully (must pass) or corrupt one claim (must be caught). The ablation column is the earlier flat 1% money tolerance." />
          {d.guardrail ? <>
            <div className="mb-4 grid gap-3 sm:grid-cols-3">
              {[
                ['Corruptions caught', pct(d.guardrail.summary.corruption_detection_rate), `flat 1%: ${pct(d.guardrail.ablation_flat_1pct_tolerance.corruption_detection_rate)}`],
                ['Faithful answers accepted', pct(d.guardrail.summary.faithful_acceptance_rate), `n = ${d.guardrail.summary.faithful_n}`],
                ['Corrupted drafts', String(d.guardrail.summary.corrupted_n), 'seeded, reproducible'],
              ].map(([k, v, sub]) => (
                <div key={k} className="rounded-xl bg-slate-50 p-4"><p className="text-[12px] text-navy-500">{k}</p><p className="font-display text-4xl text-navy-900">{v}</p><p className="text-[11.5px] text-navy-400">{sub}</p></div>
              ))}
            </div>
            <RedteamTable s={d.guardrail.summary} flat={d.guardrail.ablation_flat_1pct_tolerance} />
            <p className="mt-3 text-[12px] text-navy-500">Misses are coincidences: a corrupted value that happens to equal another figure the tools legitimately returned. Value-based grounding can’t tell those apart.</p>
          </> : <p className="text-sm text-navy-500">Not run yet.</p>}
        </Card>

        {(['llm', 'rules'] as const).map((m) => {
          const a = d.agent[m]
          return (
            <Card key={m}>
              <CardHeader icon={m === 'llm' ? <FlaskConical className="h-4 w-4" /> : <Microscope className="h-4 w-4" />}
                title={m === 'llm' ? '3 · Live Groq agent benchmark' : '4 · Offline deterministic planner benchmark'}
                subtitle={m === 'llm'
                  ? 'Real Groq API calls: does the model pick the right engine tool with the right arguments, and is the final answer grounded? Same 40 questions as section 4.'
                  : 'The no-API-key fallback: a rule-based planner on the same 40 questions, including 14 held-out paraphrases it was not written for. No model involved.'}
                action={a && <Badge tone="navy">{a.model ?? 'rules'} · commit {a.commit ?? '?'}</Badge>} />
              {a && m === 'llm' && (
                <p className="mb-3 text-[12px] text-navy-500">
                  Paced to Groq&apos;s free-tier limit of 8,000 tokens/minute{a.summary.overall.mean_tokens ? ` (~${Math.round(a.summary.overall.mean_tokens).toLocaleString('en-IN')} tokens per question)` : ''}.
                  “Rewrites” are drafts the guardrail rejected and replaced with engine wording; the ones we reproduced were the model doing its own arithmetic.
                  “Fallback” means a provider error was answered by the offline planner. Benchmark questions run on the fictional sample profile.
                </p>
              )}
              {a && m === 'llm' && <FailureCases a={a} />}
              {a ? <AgentTable a={a} /> : (
                <p className="rounded-lg border border-dashed border-slate-300 px-3 py-3 text-[13px] text-navy-500">
                  Not run in this build: it needs a <code className="font-mono">GROQ_API_KEY</code>. Run <code className="font-mono">python -m evals.agent_eval --mode llm --tpm 8000</code>; results appear here.
                </p>
              )}
            </Card>
          )
        })}
      </div>
    </>
  )
}

/** Every case that missed, fell back or was rewritten, with the recorded reason. Totals alone hide this. */
function FailureCases({ a }: { a: AgentEval }) {
  const rows = a.cases.filter((c) => !c.args_ok || c.mode === 'rules' || c.guardrail === 'replaced')
  if (!rows.length) return null
  const kind = (c: AgentEval['cases'][number]) => c.mode === 'rules' ? 'Fallback to offline planner' : !c.tool_ok ? 'Wrong tool' : !c.args_ok ? 'Wrong arguments' : 'Draft rewritten by guardrail'
  return (
    <details className="mb-4 rounded-xl border border-slate-200 p-3">
      <summary className="cursor-pointer text-[13px] font-semibold text-navy-900">Known failure cases in this run ({rows.length} of {a.cases.length})</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[620px] text-[12.5px]">
          <thead><tr className="border-b border-slate-200 text-left text-navy-500"><th className="py-1.5 pr-2 font-medium">Case</th><th className="py-1.5 pr-2 font-medium">Question</th><th className="py-1.5 pr-2 font-medium">What happened</th><th className="py-1.5 font-medium">Detail</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((c) => (
              <tr key={c.id} className="align-top">
                <td className="py-1.5 pr-2 font-mono text-[11px] text-navy-500">{c.id}{c.paraphrase && <span className="ml-1 text-amber-700">held-out</span>}</td>
                <td className="py-1.5 pr-2 text-navy-800">{c.question}</td>
                <td className="py-1.5 pr-2"><Badge tone={c.mode === 'rules' || c.guardrail === 'replaced' ? 'amber' : 'red'}>{kind(c)}</Badge></td>
                <td className="py-1.5 text-navy-500">{c.why || (c.mode === 'rules' ? 'Provider error; the offline planner answered. This run did not record the error text.' : c.guardrail === 'replaced' ? 'Final answer still grounded (engine wording).' : '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
