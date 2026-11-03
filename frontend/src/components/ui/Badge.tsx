import type { ReactNode } from 'react'

type Tone = 'neutral' | 'green' | 'amber' | 'red' | 'blue' | 'navy'
const tones: Record<Tone, string> = {
  neutral: 'bg-slate-100 text-slate-600 ring-slate-200',
  green: 'bg-brand-50 text-brand-700 ring-brand-100',
  amber: 'bg-amber-50 text-amber-800 ring-amber-200',
  red: 'bg-red-50 text-red-700 ring-red-200',
  blue: 'bg-blue-50 text-blue-700 ring-blue-200',
  navy: 'bg-navy-900 text-white ring-navy-900',
}

export function Badge({ children, tone = 'neutral', icon }: { children: ReactNode; tone?: Tone; icon?: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${tones[tone]}`}>
      {icon}
      {children}
    </span>
  )
}

/** Visually tags a figure as a model estimate, distinct from recorded actuals. */
export function ProjectedTag() {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-dashed border-blue-300 bg-blue-50/60 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-blue-700">
      Projected
    </span>
  )
}

export function ActualTag() {
  return (
    <span className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-slate-500">
      Actual
    </span>
  )
}
