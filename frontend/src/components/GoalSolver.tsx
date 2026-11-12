import { CalendarCheck, Target, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'
import { Area, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtDate, fmtShort, inr, inrCompact, inrAxis } from '../lib/format'
import type { Affordability, AffordabilityPoint } from '../lib/types'
import { TooltipRow, TooltipShell, tooltipDate } from './charts/ChartTooltip'
import { ProjectedTag } from './ui/Badge'
import { Card, CardHeader } from './ui/Card'

/** Goal solver, worked backwards: "What's the most I can spend?" and "When can I safely buy this?" */
export function GoalSolver({ data, amount, compact = false }: { data: Affordability; amount?: number; compact?: boolean }) {
  const e = data.earliest
  return (
    <Card>
      <CardHeader title="What can I afford?" icon={<Target className="h-4 w-4" />} action={<ProjectedTag />}
        subtitle={`Worked backwards from your ${inr(data.assumptions.safety_buffer)} safety buffer, over the ${data.assumptions.horizon_days} days after each date.`} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Tile icon={<Target className="h-4 w-4" />} label="Most you can spend today" value={inr(data.max_safe_today)}
          sub={`Tightest day: ${fmtShort(data.limiting_date_today)}`} />
        <Tile icon={<TrendingUp className="h-4 w-4" />} label="Most this month" value={inr(data.best_this_month.max_safe_spend)}
          sub={data.best_this_month.day === 0 ? 'Best date: today' : `If you buy on ${fmtShort(data.best_this_month.on)}`} />
        {e ? (
          <Tile icon={<CalendarCheck className="h-4 w-4" />} label={`Earliest safe date for ${inr(e.amount)}`}
            value={e.found ? (e.days_from_now === 0 ? 'Today' : fmtDate(e.on!)) : 'Not in range'}
            sub={e.found ? (e.days_from_now ? `${e.days_from_now} day(s) from now` : 'Safe right now') : `Short by ${inr(e.shortfall_today)} today`}
            alert={!e.found} />
        ) : (
          <Tile icon={<TrendingUp className="h-4 w-4" />} label={`Peak in ${data.search_days} days`} value={inr(data.best_in_window.max_safe_spend)}
            sub={fmtShort(data.best_in_window.on)} />
        )}
      </div>

      {!compact && <Curve data={data} amount={amount} />}
      <details className="mt-4 rounded-xl bg-slate-50 p-3 text-[13px] text-navy-600">
        <summary className="cursor-pointer font-medium text-navy-800">Explanation</summary>
        <ul className="mt-2 space-y-1.5">{data.explanation.map((l, i) => <li key={i}>• {l}</li>)}</ul>
      </details>
    </Card>
  )
}

function Tile({ icon, label, value, sub, alert }: { icon: ReactNode; label: string; value: string; sub: string; alert?: boolean }) {
  return (
    <div className={`rounded-xl border p-4 ${alert ? 'border-red-200 bg-red-50/40' : 'border-slate-200'}`}>
      <p className="flex items-center gap-1.5 text-xs text-navy-500"><span className="text-navy-400">{icon}</span>{label}</p>
      <p className="tabular mt-1.5 text-xl font-semibold tracking-tight text-navy-900">{value}</p>
      <p className="mt-0.5 text-[11px] text-navy-400">{sub}</p>
    </div>
  )
}

function Curve({ data, amount }: { data: Affordability; amount?: number }) {
  return (
    <div className="mt-5">
      <p className="mb-2 text-xs font-medium text-navy-700">Safe spending room by purchase date</p>
      <div style={{ height: 200 }} role="img"
        aria-label={`Most you can safely spend on each of the next ${data.search_days} days. Today ${inr(data.max_safe_today)}, peak ${inr(data.best_in_window.max_safe_spend)} on ${fmtDate(data.best_in_window.on)}.`}>
        <ResponsiveContainer>
          <ComposedChart data={data.curve} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="roomFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--series-3)" stopOpacity={0.22} />
                <stop offset="100%" stopColor="var(--series-3)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="on" tickFormatter={fmtShort} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis tickFormatter={inrAxis} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={84} />
            <Tooltip content={<RoomTooltip />} cursor={{ stroke: 'var(--axis)', strokeDasharray: '3 3' }} />
            {amount ? <ReferenceLine y={amount} stroke="#0b1b3a" strokeOpacity={0.5} strokeDasharray="4 4"
              label={{ value: `Your purchase ${inrCompact(amount)}`, position: 'insideTopRight', fontSize: 11, fill: '#52607d' }} /> : null}
            <Area type="stepAfter" dataKey="max_safe_spend" stroke="var(--series-3)" strokeWidth={2} fill="url(#roomFill)" dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function RoomTooltip({ active, payload }: { active?: boolean; payload?: { payload: AffordabilityPoint }[] }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <TooltipShell title={tooltipDate(p.on)}>
      <TooltipRow swatch="var(--series-3)" label="Safe to spend" value={inr(p.max_safe_spend)} />
      <TooltipRow label="Limited by" value={fmtShort(p.limiting_date)} />
      {p.is_income_day && <p className="text-[11px] text-brand-700">Income lands this day</p>}
    </TooltipShell>
  )
}
