import { useMemo } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtShort, inr, inrCompact, signedInr } from '../../lib/format'
import type { CashEvent, PurchaseSimulation } from '../../lib/types'
import { ChartLegendItem } from './CashflowChart'
import { TooltipEvents, TooltipRow, TooltipShell, tooltipDate } from './ChartTooltip'

interface Row { on: string; baseline: number; scenario: number; events: CashEvent[] }

export function ScenarioChart({ sim, height = 340 }: { sim: PurchaseSimulation; height?: number }) {
  const rows = useMemo<Row[]>(
    () => sim.baseline.points.map((p, i) => ({ on: p.on, baseline: p.balance, scenario: sim.simulated.points[i].balance, events: sim.simulated.points[i].events })),
    [sim],
  )
  const buffer = sim.assumptions.safety_buffer
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-xs text-navy-500">
        <ChartLegendItem swatch="var(--series-1)" label="Without purchase" />
        <ChartLegendItem swatch="var(--series-2)" label={`With ${sim.scenario.label.toLowerCase()}`} />
        <ChartLegendItem swatch="var(--axis)" label={`Safety buffer ${inrCompact(buffer)}`} dashed thin />
      </div>
      <div style={{ height }} role="img" aria-label={`Projected balance with and without the purchase. Lowest balance with purchase ${inr(sim.simulated.min_balance)}.`}>
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 24, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="gapFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--series-2)" stopOpacity={0.16} />
                <stop offset="100%" stopColor="var(--series-2)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="on" tickFormatter={fmtShort} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} minTickGap={40} />
            <YAxis tickFormatter={inrCompact} tick={{ fontSize: 11, fill: 'var(--axis)' }} tickLine={false} axisLine={false} width={56} />
            <Tooltip content={<ScenarioTooltip label={sim.scenario.label} />} cursor={{ stroke: 'var(--axis)', strokeDasharray: '3 3' }} />
            <ReferenceLine y={0} stroke="var(--status-critical)" strokeOpacity={0.4} />
            <ReferenceLine y={buffer} stroke="var(--axis)" strokeDasharray="4 4" />
            <ReferenceLine x={sim.scenario.purchase_date} stroke="var(--series-2)" strokeOpacity={0.5} strokeDasharray="2 3"
              label={{ value: 'Purchase', position: 'top', fontSize: 11, fill: '#52607d' }} />
            <Line type="monotone" dataKey="baseline" stroke="var(--series-1)" strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} animationDuration={500} />
            <Area type="monotone" dataKey="scenario" stroke="var(--series-2)" strokeWidth={2} fill="url(#gapFill)" dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }} animationDuration={500} />
            <ReferenceDot x={sim.simulated.min_balance_date} y={sim.simulated.min_balance} r={5} fill="var(--series-2)" stroke="#fff" strokeWidth={2}
              label={{ value: `Low ${inrCompact(sim.simulated.min_balance)}`, position: 'bottom', fontSize: 11, fill: '#0b1b3a', fontWeight: 600 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function ScenarioTooltip({ active, payload, label: scenarioLabel }: { active?: boolean; payload?: { payload: Row }[]; label: string }) {
  if (!active || !payload?.length) return null
  const r = payload[0].payload
  return (
    <TooltipShell title={tooltipDate(r.on)}>
      <TooltipRow swatch="var(--series-1)" label="Without purchase" value={inr(r.baseline)} />
      <TooltipRow swatch="var(--series-2)" label={`With ${scenarioLabel.toLowerCase()}`} value={inr(r.scenario)} />
      <TooltipRow label="Difference" value={signedInr(r.scenario - r.baseline)} />
      <TooltipEvents events={r.events} />
    </TooltipShell>
  )
}
