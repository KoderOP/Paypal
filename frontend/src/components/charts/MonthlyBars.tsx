import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtMonth, inr, signedInr, inrAxis } from '../../lib/format'
import type { MonthSummary } from '../../lib/types'
import { TooltipRow, TooltipShell } from './ChartTooltip'

const SERIES = [
  { key: 'income', label: 'Income', color: 'var(--series-1)' },
  { key: 'spending', label: 'Spending', color: 'var(--series-2)' },
  { key: 'investments', label: 'Investments', color: 'var(--series-3)' },
] as const

export function MonthlyBars({ months, height = 240 }: { months: MonthSummary[]; height?: number }) {
  const data = months.filter((m) => !m.partial)
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-4 text-xs text-navy-500">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />{s.label}</span>
        ))}
      </div>
      <div style={{ height }} role="img" aria-label="Monthly income, spending and investments for complete months">
        <ResponsiveContainer>
          <BarChart data={data} barGap={2} barCategoryGap="28%" margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="month" tickFormatter={fmtMonth} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} />
            <YAxis tickFormatter={inrAxis} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={84} />
            <Tooltip content={<MonthTooltip />} cursor={{ fill: '#0b1b3a', fillOpacity: 0.04 }} />
            {SERIES.map((s) => <Bar key={s.key} dataKey={s.key} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={18} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function MonthTooltip({ active, payload }: { active?: boolean; payload?: { payload: MonthSummary }[] }) {
  if (!active || !payload?.length) return null
  const m = payload[0].payload
  return (
    <TooltipShell title={fmtMonth(m.month)}>
      <TooltipRow label="Income" value={inr(m.income)} />
      <TooltipRow label="Spending" value={inr(m.spending)} />
      <TooltipRow label="Investments" value={inr(m.investments)} />
      <div className="border-t border-slate-100 pt-1.5"><TooltipRow label="Net cash flow" value={signedInr(m.net)} /></div>
    </TooltipShell>
  )
}
