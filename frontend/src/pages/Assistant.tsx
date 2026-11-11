import { Bookmark, Bot, Calculator, CornerDownRight, Loader2, SendHorizontal, ShieldCheck, ShieldAlert, Sparkles, User } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
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
import { fmtShort, inr, inrCompact, signedInr } from '../lib/format'
import { describeChange } from '../lib/scenarios'
import type { ChatContext, ChatResponse, ChatTurn, CrossBorder, ScenarioCard, ScenarioChange, SnapshotCard, ToolCall } from '../lib/types'

const SUGGESTIONS = [
  'What happens if I buy a laptop worth ₹75,000 this month?',
  'What’s the most I can spend this month?',
  'What if I cancel three subscriptions?',
  'What if I add a ₹499/month gym membership?',
  'What if USD/INR drops 3%?',
  'How much am I losing to PayPal fees?',
  'What if my income is delayed by 15 days?',
  'What if I increase my monthly savings by 10%?',
  'When can I safely buy a ₹1.2 lakh vacation?',
]

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
  return (
    <>
      <PageHeader eyebrow="AI Financial Assistant" title="Ask your twin anything"
        description="Ask in plain English. The assistant picks which calculation to run, and every figure comes from the same deterministic engine as the simulator."
        actions={mode && (mode === 'llm'
          ? <Badge tone="green" icon={<Sparkles className="h-3 w-3" />}>AI · {status.data?.model}</Badge>
          : <Badge tone="neutral" icon={<Calculator className="h-3 w-3" />}>Built-in calculator</Badge>)} />

      <div className="space-y-5">
        {msgs.length === 0 && (
          <Card>
            <CardHeader title="Try one of these" icon={<Sparkles className="h-4 w-4 text-brand-600" />}
              subtitle={mode === 'rules' ? 'No AI key is set, so a built-in parser answers these questions exactly. Add OPENAI_API_KEY for free-form chat.' : undefined} />
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => void send(s)} className="rounded-full border border-slate-200 px-3 py-1.5 text-left text-[13px] text-navy-700 transition hover:border-navy-900 hover:bg-slate-50">{s}</button>
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
        {busy && <p className="flex items-center gap-2 text-sm text-navy-500"><Loader2 className="h-4 w-4 animate-spin" /> Running the numbers…</p>}
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
  return c.tool.replace(/_/g, ' ')
}

function AssistantMessage({ m, onChanged }: { m: Msg; onChanged: () => void }) {
  const lines = useMemo(() => m.content.split('\n').filter(Boolean), [m.content])
  return (
    <div className="flex gap-2.5">
      <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-50"><Bot className="h-3.5 w-3.5 text-brand-700" /></span>
      <div className="min-w-0 flex-1 space-y-4">
        {m.error ? (
          <p role="alert" className="rounded-2xl rounded-tl-md bg-red-50 px-4 py-3 text-sm text-red-700">{m.error}</p>
        ) : (
          <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3">
            <div className="space-y-1.5 text-sm leading-relaxed text-navy-800">
              {lines.map((l, i) => i === 0 ? <p key={i} className="font-medium text-navy-900">{l}</p> : <p key={i}>{l}</p>)}
            </div>
            {m.res?.built_on && (
              <p className="mt-2 flex items-center gap-1 text-[12px] text-navy-500"><CornerDownRight className="h-3.5 w-3.5" /> Built on your previous question: kept {m.res.built_on}.</p>
            )}
            {m.res && (
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2.5">
                {m.res.guardrail === 'replaced'
                  ? <Badge tone="amber" icon={<ShieldAlert className="h-3 w-3" />}>Rewritten from computed figures</Badge>
                  : <Badge tone="green" icon={<ShieldCheck className="h-3 w-3" />}>Every figure checked against the engine</Badge>}
                <Badge>{m.res.mode === 'llm' ? `AI · ${m.res.model}` : 'Built-in calculator'}</Badge>
                {m.res.tool_calls.map((t, i) => <Badge key={i} tone="navy">{t.tool.replace(/_/g, ' ')}</Badge>)}
                {m.res.note && <p className="w-full text-[11px] text-navy-400">{m.res.note}</p>}
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
            ? <Link to="/compare" className="text-[12px] font-semibold text-brand-700 hover:underline">Saved · Compare →</Link>
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
            <YAxis tickFormatter={inrCompact} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={56} />
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
