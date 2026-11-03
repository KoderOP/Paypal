import type { ReactNode } from 'react'
import { ActualTag, ProjectedTag } from './Badge'

interface Props {
  label: string
  value: string
  hint?: ReactNode
  icon?: ReactNode
  kind?: 'actual' | 'projected' | 'derived'
  emphasis?: boolean
}

export function StatCard({ label, value, hint, icon, kind = 'derived', emphasis = false }: Props) {
  return (
    <div
      className={`animate-fade-up rounded-2xl border p-5 ${
        emphasis
          ? 'border-navy-900 bg-navy-900 text-white shadow-lg shadow-navy-900/10'
          : kind === 'projected'
            ? 'border-dashed border-blue-200 bg-white'
            : 'border-slate-200/80 bg-white'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`flex items-center gap-1.5 text-[13px] font-medium ${emphasis ? 'text-slate-300' : 'text-navy-500'}`}>
          {icon}
          {label}
        </span>
        {kind === 'projected' ? <ProjectedTag /> : kind === 'actual' && !emphasis ? <ActualTag /> : null}
      </div>
      <p className={`tabular mt-3 text-2xl font-semibold tracking-tight sm:text-[26px] ${emphasis ? 'text-white' : 'text-navy-900'}`}>{value}</p>
      {hint && <div className={`mt-1.5 text-xs ${emphasis ? 'text-slate-300' : 'text-navy-500'}`}>{hint}</div>}
    </div>
  )
}
