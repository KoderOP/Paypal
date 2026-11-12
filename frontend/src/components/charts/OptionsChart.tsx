import { useMemo } from 'react'
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtShort, inr, inrAxis } from '../../lib/format'
import type { PaymentComparison, PaymentOption } from '../../lib/types'
import { optionColor } from '../../lib/options'
import { ChartLegendItem } from './CashflowChart'
import { TooltipRow, TooltipShell, tooltipDate } from './ChartTooltip'

type Row = { on: string; baseline: number } & Record<string, number | string>

/** Baseline (no purchase) is always shown; `visible` picks which payment strategies are drawn. */
export function OptionsChart({ cmp, height = 320, visible }: { cmp: PaymentComparison; height?: number; visible?: string[] }) {
  const rows = useMemo<Row[]>(() => cmp.dates.map((on, i) => {
    const r: Row = { on, baseline: cmp.baseline_series[i] }
    cmp.options.forEach((o) => { r[o.id] = o.series[i] })
    return r
  }), [cmp])
  const buffer = cmp.assumptions.safety_buffer
  const drawn = cmp.options.filter((o) => !visible || visible.includes(o.id))
  const rec = cmp.options.find((o) => o.recommended)

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-navy-500">
        {drawn.map((o) => <ChartLegendItem key={o.id} swatch={optionColor(o, cmp.options)} label={o.name} />)}
        <ChartLegendItem swatch="#94a3b8" label="Without purchase" dashed thin />
        <ChartLegendItem swatch="var(--status-critical)" label={`Safety buffer ${inr(buffer)}`} dashed thin />
      </div>
      <div style={{ height }} role="img"
        aria-label={`Projected balance for ${drawn.map((o) => o.name).join(', ')} against no purchase. ${rec ? `Recommended: ${rec.name}, lowest balance ${inr(rec.min_balance)}.` : 'No option stays above the buffer.'}`}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="on" tickFormatter={fmtShort} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis tickFormatter={inrAxis} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={84} />
            <Tooltip content={<OptionsTooltip cmp={cmp} drawn={drawn} />} cursor={{ stroke: 'var(--axis)', strokeDasharray: '3 3' }} />
            <ReferenceLine y={buffer} stroke="var(--status-critical)" strokeOpacity={0.6} strokeDasharray="2 4" />
            <Line type="monotone" dataKey="baseline" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            {drawn.map((o) => (
              <Line key={o.id} type="monotone" dataKey={o.id} stroke={optionColor(o, cmp.options)} strokeWidth={o.recommended ? 2.75 : 2}
                dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} animationDuration={400} />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function OptionsTooltip({ active, payload, cmp, drawn }: { active?: boolean; payload?: { payload: Row }[]; cmp: PaymentComparison; drawn: PaymentOption[] }) {
  if (!active || !payload?.length) return null
  const r = payload[0].payload
  return (
    <TooltipShell title={tooltipDate(r.on)}>
      {drawn.map((o) => (
        <TooltipRow key={o.id} swatch={optionColor(o, cmp.options)} label={o.name} value={inr(Number(r[o.id]))} />
      ))}
      <TooltipRow swatch="#94a3b8" dashed label="Without purchase" value={inr(r.baseline)} />
    </TooltipShell>
  )
}
