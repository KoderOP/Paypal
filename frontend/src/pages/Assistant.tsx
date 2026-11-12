import { AlertTriangle, Bookmark, Bot, Calculator, CheckCircle2, ChevronRight, CornerDownRight, Cpu, Loader2, Lock, SendHorizontal, ShieldCheck, ShieldAlert, Sparkles, User, Wrench } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartLegendItem } from '../components/charts/CashflowChart'
import { TooltipRow, TooltipShell, tooltipDate } from '../components/charts/ChartTooltip'
import { GoalSolver } from '../components/GoalSolver'
import { PaymentOptions } from '../components/PaymentOptions'
import { Badge, ProjectedTag } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { useDataStatus } from '../context/DataStatus'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { fmtShort, inr, inrCompact, signedInr, inrAxis } from '../lib/format'
import { describeChange } from '../lib/scenarios'
import type { ChatContext, ChatResponse, ChatTurn, CheckoutProposal, CrossBorder, ScenarioCard, ScenarioChange, SnapshotCard, ToolCall, TraceStep } from '../lib/types'

// A few useful starting points, grouped by what people actually ask about.
const PROMPT_GROUPS: { title: string; prompts: string[] }[] = [
  { title: 'Major purchases', prompts: ['Should I buy a ₹75,000 laptop?', 'When can I safely buy a ₹1.2 lakh vacation?'] },
  { title: 'Cash-flow limits', prompts: ['What’s the most I can spend this month?', 'What if my income is delayed by 15 days?'] },
  { title: 'Recurring subscriptions', prompts: ['What if I cancel three subscriptions?', 'What if I add a ₹499/month gym membership?'] },
]
// One-tap follow-ups after a payment comparison: the agent drafts a checkout, the user still confirms.
const PAY_FOLLOWUPS = ['Go ahead with PayPal Pay in 4', 'Pay in full now with PayPal', 'And what if my salary is also 10 days late?']

interface Msg { role: 'user' | 'assistant'; content: string; res?: ChatResponse; error?: string }

export default function Assistant() {
  const status = useApi(api.assistantStatus)
  const { refresh } = useDataStatus()
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  // What the last answer computed; sent with the next question so follow-ups build on it.
  const [context, setContext] = useState<ChatContext | null>(null)
  const [params, setParams] = useSearchParams()
  const end = useRef<HTMLDivElement>(null)
  const sentQ = useRef(false)

  async function send(q: string) {
    const question = q.trim()
    if (!question || busy) return
    const history: ChatTurn[] = [...msgs, { role: 'user' as const, content: question }]
      .filter((m) => m.content).slice(-10).map((m) => ({ role: m.role, content: m.content }))
    setMsgs((m) => [...m, { role: 'user', content: question }])
    setText('')
    setBusy(true)
    try {
      const res = await api.chat(history, context)
      setMsgs((m) => [...m, { role: 'assistant', content: res.reply, res }])
      if (res.context) setContext(res.context)
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', content: '', error: e instanceof ApiError ? e.message : String(e) }])
    } finally { setBusy(false) }
  }

  useEffect(() => {
    const q = params.get('q')
    if (q && !sentQ.current) { sentQ.current = true; setParams({}, { replace: true }); void send(q) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [msgs, busy])

  const mode = status.data?.mode
  const last = [...msgs].reverse().find((m) => m.role === 'assistant')
  const offerPay = !busy && last?.res?.context?.tool === 'compare_payment_options'
  return (
    <>
      <PageHeader eyebrow="Ask FINORA" title="Know the impact before money moves"
        description="Ask about a purchase or a what-if. FINORA runs the numbers on your forecast, checks every figure, and can prepare a PayPal checkout that only you can authorise."
        actions={mode && (mode === 'llm'
          ? <Badge tone="green" icon={<Sparkles className="h-3 w-3" />}>AI assistant</Badge>
          : <Badge tone="neutral" icon={<Calculator className="h-3 w-3" />}>Offline mode · exact answers to common questions</Badge>)} />

      <div className="space-y-5">
        {msgs.length === 0 && (
          <Card>
            <CardHeader title="What would you like to check?" icon={<Sparkles className="h-4 w-4 text-brand-600" />}
              subtitle={mode === 'rules' ? 'Offline mode answers these common questions exactly. With an AI key, you can ask in your own words.' : 'Ask in your own words. Follow-up questions build on the previous answer.'} />
            <div className="grid gap-4 sm:grid-cols-3">
              {PROMPT_GROUPS.map((g) => (
                <div key={g.title}>
                  <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-navy-400">{g.title}</p>
                  <div className="flex flex-col gap-1.5">
                    {g.prompts.map((q) => (
                      <button key={q} onClick={() => void send(q)} className="rounded-lg border border-slate-200 px-3 py-2 text-left text-[13.5px] text-navy-800 transition hover:border-[#003087]/40 hover:bg-slate-50">{q}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {msgs.map((m, i) => m.role === 'user' ? (
          <div key={i} className="flex justify-end gap-2.5">
            <p className="max-w-[80%] rounded-2xl rounded-tr-md bg-navy-900 px-4 py-2.5 text-sm text-white">{m.content}</p>
            <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-200"><User className="h-3.5 w-3.5 text-navy-700" /></span>
          </div>
        ) : (
          <AssistantMessage key={i} m={m} onChanged={() => void refresh()} />
        ))}
        {offerPay && (
          <div className="flex flex-wrap gap-2 pl-9">
            {PAY_FOLLOWUPS.map((q) => (
              <button key={q} onClick={() => void send(q)} className="inline-flex items-center gap-1 rounded-full border border-[#003087]/25 bg-[#003087]/[0.04] px-3 py-1.5 text-[13px] font-medium text-[#003087] hover:bg-[#003087]/10">
                <CornerDownRight className="h-3.5 w-3.5" />{q}
              </button>
            ))}
          </div>
        )}
        {busy && <p className="flex items-center gap-2 pl-9 text-sm text-navy-500"><Loader2 className="h-4 w-4 animate-spin" /> {mode === 'llm' ? 'The agent is choosing tools and running the engine…' : 'Running the numbers…'}</p>}
        <div ref={end} />
      </div>

      {context && (
        <div className="sticky bottom-[76px] mt-6 flex items-center justify-between gap-2 rounded-xl bg-slate-100/90 px-3 py-1.5 text-xs text-navy-600 backdrop-blur">
          <span className="truncate"><CornerDownRight className="mr-1 inline h-3.5 w-3.5" />Follow-ups build on: <b className="text-navy-800">{contextLabel(context)}</b>. Try “and what if my salary is also late?”</span>
          <button onClick={() => setContext(null)} className="shrink-0 rounded-md px-2 py-0.5 font-semibold text-navy-700 hover:bg-white">New topic</button>
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); void send(text) }}
        className={`sticky bottom-4 ${context ? 'mt-2' : 'mt-6'} flex items-center gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-lg shadow-navy-900/5`}>
        <label htmlFor="ask" className="sr-only">Ask FINORA</label>
        <input id="ask" value={text} maxLength={2000} onChange={(e) => setText(e.target.value)} placeholder="e.g. What if I cancel Netflix and my salary is 2 weeks late?"
          className="min-w-0 flex-1 bg-transparent px-3 py-2 text-sm outline-none" />
        <button type="submit" disabled={!text.trim() || busy} aria-label="Send"
          className="inline-flex items-center gap-1.5 rounded-xl bg-navy-900 px-4 py-2 text-sm font-semibold text-white hover:bg-navy-800 disabled:opacity-40">
          <SendHorizontal className="h-4 w-4" /><span className="hidden sm:inline">Ask</span>
        </button>
      </form>
    </>
  )
}

function contextLabel(c: ChatContext): string {
  const a = c.arguments as { changes?: ScenarioChange[]; amount?: number; label?: string }
  if (c.tool === 'simulate_scenario' && a.changes?.length) return a.changes.map(describeChange).join(' + ')
  if (c.tool === 'compare_payment_options') return `${a.label ?? 'Purchase'} ${inr(Number(a.amount ?? 0))}`
  if (c.tool === 'find_affordability') return a.amount ? `affordability of ${inr(a.amount)}` : 'how much you can spend'
  if (c.tool === 'prepare_paypal_checkout') return `PayPal checkout for ${a.label ?? 'purchase'} ${inr(Number(a.amount ?? 0))}`
  return c.tool.replace(/_/g, ' ')
}

function AssistantMessage({ m, onChanged }: { m: Msg; onChanged: () => void }) {
  return (
    <div className="flex gap-2.5">
      <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-50"><Bot className="h-3.5 w-3.5 text-brand-700" /></span>
      <div className="min-w-0 flex-1 space-y-4">
        {m.error ? (
          <p role="alert" className="rounded-2xl rounded-tl-md bg-red-50 px-4 py-3 text-sm text-red-700">{m.error}</p>
        ) : (
          <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3">
            <AnswerText text={m.content} />
            {m.res?.built_on && (
              <p className="mt-2 flex items-center gap-1 text-[12px] text-navy-500"><CornerDownRight className="h-3.5 w-3.5" /> Built on your previous question: kept {m.res.built_on}.</p>
            )}
            {m.res && (
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2.5">
                <VerificationBadge res={m.res} />
                {m.res.mode === 'rules' && m.res.note && <Badge tone="neutral">Answered in offline mode</Badge>}
                {m.res.guardrail === 'replaced' && <p className="w-full text-[11.5px] text-navy-500">The AI’s draft included a figure the calculations didn’t produce, so this answer uses the calculated wording instead.</p>}
                <TracePanel res={m.res} />
              </div>
            )}
          </div>
        )}
        {m.res?.tool_calls.map((t, i) => <ToolCardView key={i} call={t} onChanged={onChanged} />)}
      </div>
    </div>
  )
}

function ToolCardView({ call, onChanged }: { call: ToolCall; onChanged: () => void }) {
  const c = call.card
  if (!call.ok || !c) return null
  switch (c.kind) {
    case 'payment_options': return <PaymentOptions cmp={c} compact onChanged={onChanged} />
    case 'affordability': return <GoalSolver data={c} amount={c.earliest?.amount} />
    case 'scenario': return <ScenarioView card={c} changes={(call.arguments.changes as ScenarioChange[] | undefined) ?? []} />
    case 'snapshot': return <SnapshotView card={c} />
    case 'cross_border': return <CrossBorderView card={c} />
    case 'checkout_proposal': return <CheckoutProposalCard p={c} />
    case 'stress': return (
      <Card>
        <CardHeader title={`Resilience: ${c.resilience}`} action={<Link to="/stress" className="text-[13px] font-semibold text-navy-900 hover:underline">Open stress test →</Link>} />
        <ul className="space-y-1 text-[13px] text-navy-700">{c.summary.map((l, i) => <li key={i}>• {l}</li>)}</ul>
      </Card>
    )
  }
}

function CrossBorderView({ card }: { card: CrossBorder }) {
  const c = card.currencies[0]
  if (!card.has_foreign || !c) return null
  return (
    <Card>
      <CardHeader title="Income from abroad" action={<Link to="/crossborder" className="text-[13px] font-semibold text-navy-900 hover:underline">Open →</Link>} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[['Received', `${c.currency} ${c.gross.toLocaleString('en-IN')}`], ['PayPal fees', `${c.currency} ${c.fees.toLocaleString('en-IN')}`],
          ['Avg rate', `₹${c.avg_rate.toFixed(2)}`], ['Landed', inr(c.received_home)]].map(([k, v]) => (
          <div key={k}><p className="text-[11px] text-navy-500">{k}</p><p className="tabular text-sm font-semibold text-navy-900">{v}</p></div>
        ))}
      </div>
    </Card>
  )
}

function ScenarioView({ card, changes }: { card: ScenarioCard; changes: ScenarioChange[] }) {
  const rows = card.dates.map((on, i) => ({ on, baseline: card.baseline_series[i], scenario: card.scenario_series[i] }))
  const [saved, setSaved] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  async function save() {
    setSaved('saving')
    try { await api.saveScenario({ name: card.title.slice(0, 80), changes }); setSaved('saved') } catch { setSaved('error') }
  }
  return (
    <Card>
      <CardHeader title={card.title} subtitle={card.applied.map((a) => a.description).join(' · ')} action={
        <div className="flex items-center gap-2">
          <ProjectedTag />
          {changes.length > 0 && (saved === 'saved'
            ? <Link to="/simulator?view=compare" className="text-[12px] font-semibold text-brand-700 hover:underline">Saved · Compare →</Link>
            : <button onClick={() => void save()} disabled={saved === 'saving'} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[12px] font-medium text-navy-700 hover:bg-slate-50 disabled:opacity-50">
                <Bookmark className="h-3.5 w-3.5" /> {saved === 'error' ? 'Retry save' : 'Save to compare'}
              </button>)}
        </div>} />
      <div className="mb-3 flex flex-wrap gap-4 text-xs text-navy-500">
        <ChartLegendItem swatch="var(--series-1)" label="Today’s plan" />
        <ChartLegendItem swatch="var(--series-2)" label="With these changes" />
        <ChartLegendItem swatch="var(--status-critical)" label={`Buffer ${inrCompact(card.safety_buffer)}`} dashed thin />
      </div>
      <div style={{ height: 220 }} role="img" aria-label={`${card.title}: ${card.summary.join(' ')}`}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="on" tickFormatter={fmtShort} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis tickFormatter={inrAxis} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={84} />
            <Tooltip cursor={{ stroke: 'var(--axis)', strokeDasharray: '3 3' }} content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const r = payload[0].payload as (typeof rows)[number]
              return (
                <TooltipShell title={tooltipDate(r.on)}>
                  <TooltipRow swatch="var(--series-1)" label="Today’s plan" value={inr(r.baseline)} />
                  <TooltipRow swatch="var(--series-2)" label="With changes" value={inr(r.scenario)} />
                  <TooltipRow label="Difference" value={signedInr(r.scenario - r.baseline)} />
                </TooltipShell>
              )
            }} />
            <ReferenceLine y={card.safety_buffer} stroke="var(--status-critical)" strokeOpacity={0.55} strokeDasharray="4 4" />
            <Line type="monotone" dataKey="baseline" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="scenario" stroke="var(--series-2)" strokeWidth={2} dot={false} animationDuration={450} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3">
        {card.impacts.map((i) => (
          <div key={i.day} className="rounded-xl bg-slate-50 p-3">
            <p className="text-[11px] text-navy-500">After {i.day} days</p>
            <p className={`tabular text-sm font-semibold ${i.delta >= 0 ? 'text-brand-700' : 'text-navy-900'}`}>{signedInr(i.delta)}</p>
          </div>
        ))}
      </div>
      {card.notes.length > 0 && <ul className="mt-3 space-y-1 text-[11px] text-navy-400">{card.notes.map((n, i) => <li key={i}>• {n}</li>)}</ul>}
    </Card>
  )
}

function SnapshotView({ card }: { card: SnapshotCard }) {
  const items = [
    ['Balance', inr(card.current_balance)], ['Regular income', `${inr(card.monthly_income)}/mo`],
    ['Spending', `${inr(card.avg_monthly_spending)}/mo`], ['Subscriptions', `${inr(card.subscriptions_monthly)}/mo`],
    ['In 90 days', inr(card.projected_balance_90)], ['Next income', card.next_income_date ? fmtShort(card.next_income_date) : '—'],
  ]
  return (
    <Card>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {items.map(([k, v]) => (
          <div key={k}><p className="text-[11px] text-navy-500">{k}</p><p className="tabular text-sm font-semibold text-navy-900">{v}</p></div>
        ))}
      </div>
    </Card>
  )
}

/** Shown only when the grounding check actually passed for the answer on screen. */
function VerificationBadge({ res }: { res: ChatResponse }) {
  if (!res.grounding?.ok) return null
  return res.guardrail === 'replaced'
    ? <Badge tone="amber" icon={<ShieldAlert className="h-3 w-3" />}>Rewritten from verified calculations</Badge>
    : <Badge tone="green" icon={<ShieldCheck className="h-3 w-3" />}>Verified against financial calculations</Badge>
}

/** Renders the assistant's text: bold, bullet and numbered lines, without showing raw Markdown symbols. */
function AnswerText({ text }: { text: string }) {
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  const inline = (l: string) => l.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, k) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={k} className="font-semibold text-navy-900">{part.slice(2, -2)}</strong>
      : <span key={k}>{part.replace(/\*\*/g, '').replace(/(^|\s)\*(\S)/g, '$1$2').replace(/(\S)\*(\s|$)/g, '$1$2')}</span>)
  const blocks: React.ReactNode[] = []
  let list: string[] = []
  const flush = () => {
    if (list.length) blocks.push(<ul key={`l${blocks.length}`} className="ml-1 space-y-1">{list.map((x, k) => <li key={k} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-navy-400" />{<span>{inline(x)}</span>}</li>)}</ul>)
    list = []
  }
  lines.forEach((l, i) => {
    const bullet = l.match(/^(?:[-•*]|\d+[.)])\s+(.*)$/)
    if (bullet) { list.push(bullet[1]); return }
    flush()
    const clean = l.replace(/^#{1,6}\s+/, '')
    blocks.push(<p key={`p${i}`} className={i === 0 ? 'font-medium text-navy-900' : ''}>{inline(clean)}</p>)
  })
  flush()
  return <div className="space-y-2 text-sm leading-relaxed text-navy-800">{blocks}</div>
}

const STEP_ICON: Record<TraceStep['type'], typeof Cpu> = { llm: Cpu, tool: Wrench, guardrail: ShieldCheck, plan: Calculator, fallback: AlertTriangle }

/** How the answer was produced: model rounds, tool calls with arguments, guardrail verdict. */
function TracePanel({ res }: { res: ChatResponse }) {
  if (!res.trace?.length) return null
  return (
    <details className="group w-full">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-[11.5px] font-medium text-navy-500 hover:text-navy-900">
        <ChevronRight className="h-3.5 w-3.5 transition group-open:rotate-90" />
        Technical details
      </summary>
      <ol className="mt-2 space-y-1.5 border-l border-slate-200 pl-3">
        {res.trace.map((t, i) => {
          const Icon = STEP_ICON[t.type]
          const d = t.detail as Record<string, unknown>
          return (
            <li key={i} className="text-[12px]">
              <div className="flex items-center gap-1.5">
                <Icon className={`h-3.5 w-3.5 ${t.ok ? 'text-navy-500' : 'text-amber-600'}`} />
                <span className="font-medium text-navy-800">{t.type === 'tool' ? <code className="font-mono">{t.label}</code> : t.label}</span>
                {t.ms > 0 && <span className="text-navy-400">{t.ms} ms</span>}
                {t.type === 'guardrail' && <Badge tone={t.ok ? 'green' : 'amber'}>{t.ok ? 'passed' : 'rejected'}</Badge>}
              </div>
              {t.type === 'tool' && d.arguments != null && (
                <pre className="mt-0.5 overflow-x-auto rounded bg-slate-50 px-2 py-1 font-mono text-[11px] text-navy-600">{JSON.stringify(d.arguments)}</pre>
              )}
              {t.type === 'llm' && (
                <p className="text-navy-400">
                  {(d.requested_tools as string[] | undefined)?.length ? `requested ${(d.requested_tools as string[]).join(', ')}` : 'wrote the answer'}
                  {d.prompt_tokens != null && ` · ${String(d.prompt_tokens)}+${String(d.completion_tokens)} tokens`}
                  {(d.notes as string[] | undefined)?.map((n) => ` · ${n}`)}
                </p>
              )}
              {t.type === 'guardrail' && (() => {
                const g = d as unknown as ChatResponse['grounding']
                const bad = [...g.invented.money.map((v) => inr(v)), ...g.invented.percent.map((v) => `${v}%`), ...g.invented.dates]
                return <p className="text-navy-400">checked {g.checked.money} amount(s), {g.checked.percent} percentage(s), {g.checked.dates} date(s){bad.length ? ` · not in engine output: ${bad.join(', ')}` : ''}</p>
              })()}
              {t.type === 'fallback' && <p className="text-amber-700">{String(d.error ?? '')}</p>}
            </li>
          )
        })}
      </ol>
    </details>
  )
}

/** The agent's only action: a drafted PayPal checkout. Nothing is created until the user confirms here. */
function CheckoutProposalCard({ p }: { p: CheckoutProposal }) {
  const [ack, setAck] = useState(false)
  const [risk, setRisk] = useState(false)
  const [state, setState] = useState<'idle' | 'busy' | 'error'>('idle')
  const [err, setErr] = useState<string | null>(null)
  const ready = ack && (p.safe || risk)
  async function go() {
    setState('busy')
    setErr(null)
    try {
      const order = await api.startCheckout({ amount: p.amount, label: p.label, option_id: p.option_id, acknowledged: true })
      if (order.approve_url) window.location.assign(order.approve_url)
      else { setErr(order.error ?? 'PayPal did not return an approval link.'); setState('error') }
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : String(e))
      setState('error')
    }
  }
  return (
    <section className="overflow-hidden rounded-2xl border border-[#003087]/20 bg-white shadow-[0_1px_2px_rgba(11,27,58,0.04)]">
      <div className="flex flex-wrap items-center justify-between gap-2 bg-[#003087] px-5 py-3 text-white">
        <p className="flex items-center gap-2 text-sm font-semibold"><Lock className="h-4 w-4" /> Drafted PayPal checkout · not paid</p>
        <span className="rounded-full bg-white/15 px-2 py-0.5 text-[11px] font-medium">
          {p.paypal_environment === 'demo' ? 'PayPal demo mode · no real money' : p.paypal_environment === 'sandbox' ? 'PayPal Sandbox' : 'PayPal Live'}
        </span>
      </div>
      <div className="space-y-4 p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[12px] text-navy-500">{p.label}</p>
            <p className="tabular text-2xl font-semibold text-navy-900">{inr(p.amount)}</p>
            <p className="text-[13px] text-navy-600">{p.option_name}{p.extra_cost > 0 && ` · ${inr(p.extra_cost)} extra`}</p>
          </div>
          <div className="text-right">
            <p className="text-[12px] text-navy-500">Lowest projected balance</p>
            <p className={`tabular text-lg font-semibold ${p.safe ? 'text-brand-700' : 'text-red-600'}`}>{inr(p.min_balance)}</p>
            <p className="text-[12px] text-navy-500">on {fmtShort(p.min_balance_date)} · buffer {inr(p.safety_buffer)}</p>
          </div>
        </div>
        {p.payments.length > 1 && (
          <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {p.payments.slice(0, 8).map((x, i) => (
              <li key={i} className="rounded-lg bg-slate-50 px-3 py-2"><p className="text-[11px] text-navy-500">{fmtShort(x.on)}</p><p className="tabular text-[13px] font-semibold text-navy-900">{inr(x.amount)}</p></li>
            ))}
          </ol>
        )}
        {p.safe
          ? <p className="flex items-center gap-2 rounded-lg bg-brand-50 px-3 py-2 text-[13px] text-brand-700"><CheckCircle2 className="h-4 w-4" /> Stays above your safety buffer for the whole forecast.</p>
          : <p className="flex items-start gap-2 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              Below your buffer for {p.days_below_buffer} day(s).{p.safer_alternative && ` Waiting until ${fmtShort(p.safer_alternative.get_it_on)} keeps you safe.`}</p>}
        {p.terms_note && <p className="text-[11.5px] text-navy-400">{p.terms_note}</p>}
        {p.note && <p className="text-[11.5px] text-navy-500">{p.note}</p>}
        <div className="space-y-2 border-t border-slate-100 pt-4">
          <label className="flex items-start gap-2 text-[13px] text-navy-700">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#003087]" />
            I’ve reviewed the simulated impact and want to continue to PayPal.
          </label>
          {!p.safe && (
            <label className="flex items-start gap-2 text-[13px] text-red-700">
              <input type="checkbox" checked={risk} onChange={(e) => setRisk(e.target.checked)} className="mt-0.5 h-4 w-4 accent-red-600" />
              I understand this takes my balance below my safety buffer.
            </label>
          )}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button onClick={() => void go()} disabled={!ready || state === 'busy'}
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#003087] px-5 text-sm font-semibold text-white transition hover:bg-[#002366] disabled:cursor-not-allowed disabled:opacity-40">
              {state === 'busy' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />} Continue to PayPal
            </button>
            <p className="text-[11.5px] text-navy-400">You approve on PayPal, then confirm the capture in FINORA. Nothing is charged before that.</p>
          </div>
          {err && <p role="alert" className="text-[13px] text-red-600">{err}</p>}
        </div>
      </div>
    </section>
  )
}
