import { useMemo, useState } from 'react'
import { Area, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtShort, inr, inrCompact } from '../../lib/format'
import type { CashEvent, Forecast } from '../../lib/types'
import { Segmented } from '../ui/Segmented'
import { TooltipEvents, TooltipRow, TooltipShell, tooltipDate } from './ChartTooltip'

interface Row { on: string; actual?: number; projected?: number; events?: CashEvent[]; isProjected: boolean }
type Range = '30' | '90' | '180'

export function CashflowChart({ history, forecast, height = 320 }: { history: { on: string; balance: number }[]; forecast: Forecast; height?: number }) {
  const [range, setRange] = useState<Range>('90')
  const buffer = forecast.assumptions.safety_buffer
  const today = forecast.start_date

  const rows = useMemo<Row[]>(() => {
    const hist = history.slice(-Number(range))
    const out: Row[] = hist.map((h) => ({ on: h.on, actual: h.balance, isProjected: false }))
    // Bridge: projection starts from the last actual point so the lines join.
    if (out.length) out[out.length - 1].projected = out[out.length - 1].actual
    forecast.points.forEach((p) => out.push({ on: p.on, projected: p.balance, events: p.events, isProjected: true }))
    return out
  }, [history, forecast, range])

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4 text-xs text-navy-500">
          <Legend swatch="var(--series-1)" label="Actual balance" />
          <Legend swatch="var(--series-1)" label="Projected (90 days)" dashed />
          <Legend swatch="var(--axis)" label={`Safety buffer ${inrCompact(buffer)}`} dashed thin />
        </div>
        <Segmented<Range>
          label="History range"
          value={range}
          onChange={setRange}
          options={[{ value: '30', label: '1M' }, { value: '90', label: '3M' }, { value: '180', label: '6M' }]}
        />
      </div>
      <div style={{ height }} role="img" aria-label={`Balance history and 90-day projection. Projected balance in 90 days ${inr(forecast.end_balance)}; lowest projected ${inr(forecast.min_balance)}.`}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 10, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.18} />
                <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="projFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.07} />
                <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="on" tickFormatter={fmtShort} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis tickFormatter={inrCompact} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={56} />
            <Tooltip content={<CashTooltip />} cursor={{ stroke: 'var(--axis)', strokeDasharray: '3 3' }} />
            <ReferenceLine y={buffer} stroke="var(--axis)" strokeDasharray="4 4" />
            <ReferenceLine x={today} stroke="#0b1b3a" strokeOpacity={0.35} label={{ value: 'Today', position: 'insideTopLeft', fontSize: 11, fill: '#52607d' }} />
            <Area type="monotone" dataKey="actual" stroke="var(--series-1)" strokeWidth={2} fill="url(#actualFill)" dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} connectNulls={false} isAnimationActive={false} />
            <Area type="monotone" dataKey="projected" stroke="var(--series-1)" strokeWidth={2} strokeDasharray="5 4" fill="url(#projFill)" dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function Legend({ swatch, label, dashed, thin }: { swatch: string; label: string; dashed?: boolean; thin?: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block w-4" style={{ borderTop: `${thin ? 1.5 : 2}px ${dashed ? 'dashed' : 'solid'} ${swatch}` }} aria-hidden />
      {label}
    </span>
  )
}

function CashTooltip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload?.length) return null
  const r = payload[0].payload
  return (
    <TooltipShell title={tooltipDate(r.on)}>
      {r.isProjected ? (
        <TooltipRow swatch="var(--series-1)" dashed label="Projected balance" value={inr(r.projected ?? 0)} />
      ) : (
        <TooltipRow swatch="var(--series-1)" label="Actual balance" value={inr(r.actual ?? 0)} />
      )}
      <TooltipEvents events={r.events} />
    </TooltipShell>
  )
}

export { Legend as ChartLegendItem }
