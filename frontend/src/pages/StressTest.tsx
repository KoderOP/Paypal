import { AlertOctagon, ArrowRight, CheckCircle2, LifeBuoy, ShieldAlert, ShieldCheck, Timer, TrendingDown } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartLegendItem } from '../components/charts/CashflowChart'
import { TooltipRow, TooltipShell, tooltipDate } from '../components/charts/ChartTooltip'
import { Badge, ProjectedTag } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState, PageSkeleton } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { fmtDate, fmtShort, inr, inrCompact, pct } from '../lib/format'
import { describeChange } from '../lib/scenarios'
import type { StressReport } from '../lib/types'
import { ProvenanceTag } from '../components/Provenance'

const RESILIENCE = {
  strong: { label: 'Strong', tone: 'from-emerald-600 to-emerald-700', Icon: ShieldCheck, text: 'You can absorb most shocks without dipping below zero.' },
  moderate: { label: 'Moderate', tone: 'from-navy-900 to-navy-800', Icon: ShieldAlert, text: 'Everyday swings are fine, but a big shock would hurt.' },
  fragile: { label: 'Fragile', tone: 'from-red-700 to-red-800', Icon: AlertOctagon, text: 'A single shock could push you into the red.' },
} as const

export default function StressTest() {
  const { data, error, loading, reload } = useApi(api.stress)
  if (loading && !data) return <PageSkeleton />
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data) return null
  const r = RESILIENCE[data.resilience]
  const buffer = data.assumptions.safety_buffer

  return (
    <>
      <PageHeader eyebrow="Stress testing" title="How resilient are your finances?"
        description="Your twin is hit with common shocks and thousands of spending variations, using the same engine as the simulator. Everything here is an estimate."
        actions={<ProvenanceTag />} />

      <div className={`rounded-2xl bg-gradient-to-br ${r.tone} p-6 text-white shadow-lg`}>
        <div className="flex flex-wrap items-start gap-4">
          <div className="rounded-2xl bg-white/10 p-3"><r.Icon className="h-7 w-7" /></div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/70">Resilience</p>
            <h2 className="text-2xl font-semibold tracking-tight">{r.label}</h2>
            <p className="mt-1 text-sm text-white/80">{r.text}</p>
          </div>
        </div>
        <ul className="mt-4 space-y-1 text-[13px] text-white/85">{data.summary.map((l, i) => <li key={i}>• {l}</li>)}</ul>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Tile icon={<Timer className="h-4 w-4" />} label="Emergency runway" value={`${data.runway_months} mo`} sub={`with no income · ${inr(data.monthly_burn)}/mo`} alert={Number(data.runway_months) < 3} />
        <Tile icon={<TrendingDown className="h-4 w-4" />} label="Chance below buffer" value={pct(data.chance_below_buffer, 0)} sub={`next ${data.assumptions.horizon_days} days · ${data.paths} paths`} alert={Number(data.chance_below_buffer) > 0.1} />
        <Tile icon={<AlertOctagon className="h-4 w-4" />} label="Chance of going negative" value={pct(data.chance_below_zero, 0)} sub="from spending swings alone" alert={Number(data.chance_below_zero) > 0} />
        <Tile icon={<LifeBuoy className="h-4 w-4" />} label="Shocks survived" value={`${data.shocks_survived} / ${data.shocks.length}`} sub="balance never below ₹0" alert={data.shocks_survived < data.shocks.length} />
      </div>

      <Card className="mt-6">
        <CardHeader title="Likely range of your balance" action={<ProjectedTag />}
          subtitle={`${data.paths} simulated paths of day-to-day spending, with variation taken from your own history. The band holds 80% of outcomes.`} />
        <Bands data={data} />
      </Card>

      <Card className="mt-6" padded={false}>
        <div className="p-5 pb-0 sm:p-6 sm:pb-0"><CardHeader title="Shock library" subtitle="Each shock on its own, everything else as today." /></div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-[13px]">
            <thead><tr className="border-b border-slate-100 text-left text-xs text-navy-400">
              <th className="px-5 py-3 font-medium sm:px-6">Shock</th><th className="px-3 py-3 text-right font-medium">Lowest balance</th>
              <th className="px-3 py-3 text-right font-medium">Under buffer</th><th className="px-3 py-3 text-right font-medium">Outcome</th><th className="px-5 py-3 sm:px-6" />
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.shocks.map((s) => (
                <tr key={s.id}>
                  <td className="px-5 py-3 sm:px-6"><p className="font-medium text-navy-900">{s.name}</p><p className="text-[11px] text-navy-400">{s.description}</p></td>
                  <td className={`tabular px-3 py-3 text-right font-semibold ${s.solvent ? 'text-navy-900' : 'text-red-700'}`}>{inr(s.min_balance)}<span className="block text-[11px] font-normal text-navy-400">{fmtShort(s.min_balance_date)}</span></td>
                  <td className="tabular px-3 py-3 text-right text-navy-700">{s.days_below_buffer ? `${s.days_below_buffer} day(s)` : '—'}</td>
                  <td className="px-3 py-3 text-right">
                    {!s.solvent ? <Badge tone="red">Negative from {fmtShort(s.first_below_zero!)}</Badge>
                      : !s.above_buffer ? <Badge tone="amber">Below buffer</Badge> : <Badge tone="green" icon={<CheckCircle2 className="h-3 w-3" />}>Absorbed</Badge>}
                  </td>
                  <td className="px-5 py-3 text-right sm:px-6">
                    <Link to={`/assistant?q=${encodeURIComponent(askAbout(s))}`} title={s.changes.map(describeChange).join(' + ')}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-navy-800 hover:underline">Explore <ArrowRight className="h-3 w-3" /></Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t border-slate-100 px-5 py-3 text-[11px] text-navy-400 sm:px-6">{data.disclaimer} Safety buffer {inr(buffer)}. Worst 10% of paths bottom out at or below {inr(data.p10_lowest)}.</p>
      </Card>
    </>
  )
}

function Bands({ data }: { data: StressReport }) {
  const rows = data.bands.map((b) => ({ ...b, range: [b.p10, b.p90] as [number, number] }))
  const buffer = data.assumptions.safety_buffer
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-navy-500">
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: 'var(--series-1)', opacity: 0.18 }} aria-hidden />Likely range (10th–90th percentile)</span>
        <ChartLegendItem swatch="var(--series-1)" label="Median path" />
        <ChartLegendItem swatch="var(--axis)" label="Forecast" dashed thin />
        <ChartLegendItem swatch="var(--status-critical)" label={`Buffer ${inrCompact(buffer)}`} dashed thin />
      </div>
      <div style={{ height: 300 }} role="img" aria-label={`Balance range over ${data.assumptions.horizon_days} days. In 90 days, 80% of paths end between ${inr(data.bands.at(-1)!.p10)} and ${inr(data.bands.at(-1)!.p90)}.`}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="on" tickFormatter={fmtShort} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis tickFormatter={inrCompact} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={56} />
            <Tooltip cursor={{ stroke: 'var(--axis)', strokeDasharray: '3 3' }} content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const b = payload[0].payload as (typeof rows)[number]
              return (
                <TooltipShell title={tooltipDate(b.on)}>
                  <TooltipRow label="Optimistic (90th)" value={inr(b.p90)} />
                  <TooltipRow swatch="var(--series-1)" label="Median" value={inr(b.p50)} />
                  <TooltipRow label="Pessimistic (10th)" value={inr(b.p10)} />
                  <TooltipRow swatch="var(--axis)" dashed label="Forecast" value={inr(b.baseline)} />
                </TooltipShell>
              )
            }} />
            <ReferenceLine y={buffer} stroke="var(--status-critical)" strokeOpacity={0.55} strokeDasharray="4 4" />
            <Area type="monotone" dataKey="range" stroke="none" fill="var(--series-1)" fillOpacity={0.16} isAnimationActive={false} />
            <Line type="monotone" dataKey="baseline" stroke="var(--axis)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="p50" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-[11px] text-navy-400">In 90 days: {inr(data.bands.at(-1)!.p10)} to {inr(data.bands.at(-1)!.p90)} (median {inr(data.bands.at(-1)!.p50)}, as of {fmtDate(data.bands.at(-1)!.on)}).</p>
    </div>
  )
}

/** A plain-English question the assistant understands, for exploring one shock in more depth. */
function askAbout(s: StressReport['shocks'][number]): string {
  const c = s.changes[0] ?? {}
  switch (s.id) {
    case 'job_loss_1': return 'What if I lose my job for 1 month?'
    case 'job_loss_3': return 'What if I lose my job for 3 months?'
    case 'pay_cut': return 'What if I get a 30% pay cut for 3 months?'
    case 'medical': return `What if I have an unexpected medical bill of ₹${Number(c.amount ?? 0).toLocaleString('en-IN')}?`
    case 'costs_up': return 'What if my expenses increase by 30%?'
    case 'late_30': return 'What if my salary is delayed by 30 days?'
    default: return s.id.startsWith('fx_') ? `What if ${String(c.currency ?? 'USD')}/INR drops 10%?` : `What if ${s.name.toLowerCase()}?`
  }
}

function Tile({ icon, label, value, sub, alert }: { icon: ReactNode; label: string; value: string; sub: string; alert?: boolean }) {
  return (
    <div className={`rounded-2xl border bg-white p-4 ${alert ? 'border-amber-200' : 'border-slate-200/80'}`}>
      <p className="flex items-center gap-1.5 text-xs text-navy-500"><span className="text-navy-400">{icon}</span>{label}</p>
      <p className="tabular mt-2 text-xl font-semibold tracking-tight text-navy-900">{value}</p>
      <p className="mt-0.5 text-[11px] text-navy-400">{sub}</p>
    </div>
  )
}
