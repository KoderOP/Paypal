import { useMemo } from 'react'
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtShort, inr, inrCompact } from '../../lib/format'
import type { PaymentComparison, PaymentOption } from '../../lib/types'
import { ChartLegendItem } from './CashflowChart'
import { TooltipRow, TooltipShell, tooltipDate } from './ChartTooltip'

/** Colour follows the option (entity), never its rank: fixed slots from the validated palette. */
export function optionColor(o: PaymentOption, all: PaymentOption[]): string {
  if (o.kind === 'pay_now') return 'var(--series-1)'
  if (o.kind === 'wait') return 'var(--series-2)'
  const laterIdx = all.filter((x) => x.kind === 'pay_later').findIndex((x) => x.id === o.id)
  return laterIdx === 0 ? 'var(--series-3)' : 'var(--series-4)'
}

type Row = { on: string; baseline: number } & Record<string, number | string>

export function OptionsChart({ cmp, height = 320, highlight }: { cmp: PaymentComparison; height?: number; highlight?: string | null }) {
  const rows = useMemo<Row[]>(() => cmp.dates.map((on, i) => {
    const r: Row = { on, baseline: cmp.baseline_series[i] }
    cmp.options.forEach((o) => { r[o.id] = o.series[i] })
    return r
  }), [cmp])
  const buffer = cmp.assumptions.safety_buffer
  const rec = cmp.options.find((o) => o.recommended)

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-navy-500">
        {cmp.options.map((o) => (
          <ChartLegendItem key={o.id} swatch={optionColor(o, cmp.options)} label={o.name} />
        ))}
        <ChartLegendItem swatch="var(--axis)" label="No purchase" dashed thin />
        <ChartLegendItem swatch="var(--status-critical)" label={`Buffer ${inrCompact(buffer)}`} dashed thin />
      </div>
      <div style={{ height }} role="img"
        aria-label={`Projected balance for ${cmp.options.length} ways to pay ${inr(cmp.amount)}. ${rec ? `Recommended: ${rec.name}, lowest balance ${inr(rec.min_balance)}.` : 'No option stays above the buffer.'}`}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="on" tickFormatter={fmtShort} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis tickFormatter={inrCompact} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={56} />
            <Tooltip content={<OptionsTooltip cmp={cmp} />} cursor={{ stroke: 'var(--axis)', strokeDasharray: '3 3' }} />
            <ReferenceLine y={buffer} stroke="var(--status-critical)" strokeOpacity={0.55} strokeDasharray="4 4" />
            <Line type="monotone" dataKey="baseline" stroke="var(--axis)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
            {cmp.options.map((o) => {
              const dim = highlight && highlight !== o.id
              return (
                <Line key={o.id} type="monotone" dataKey={o.id} stroke={optionColor(o, cmp.options)} strokeWidth={o.recommended || highlight === o.id ? 2.5 : 2}
                  strokeOpacity={dim ? 0.25 : 1} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} animationDuration={450} />
              )
            })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function OptionsTooltip({ active, payload, cmp }: { active?: boolean; payload?: { payload: Row }[]; cmp: PaymentComparison }) {
  if (!active || !payload?.length) return null
  const r = payload[0].payload
  return (
    <TooltipShell title={tooltipDate(r.on)}>
      {cmp.options.map((o) => (
        <TooltipRow key={o.id} swatch={optionColor(o, cmp.options)} label={o.name} value={inr(Number(r[o.id]))} />
      ))}
      <TooltipRow swatch="var(--axis)" dashed label="No purchase" value={inr(r.baseline)} />
    </TooltipShell>
  )
}
