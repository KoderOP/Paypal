import type { ReactNode } from 'react'
import type { CashEvent } from '../../lib/types'
import { fmtDate, inr, signedInr } from '../../lib/format'

export function TooltipShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="min-w-[200px] max-w-[280px] rounded-xl border border-slate-200 bg-white/95 px-3.5 py-3 text-xs shadow-xl shadow-navy-900/10 backdrop-blur">
      <p className="mb-2 font-semibold text-navy-900">{title}</p>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

export function TooltipRow({ swatch, label, value, dashed }: { swatch?: string; label: string; value: string; dashed?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="flex items-center gap-1.5 text-navy-500">
        {swatch && (
          <span
            className="inline-block h-0 w-3"
            style={{ borderTop: `2px ${dashed ? 'dashed' : 'solid'} ${swatch}` }}
            aria-hidden
          />
        )}
        {label}
      </span>
      <span className="tabular font-semibold text-navy-900">{value}</span>
    </div>
  )
}

export function TooltipEvents({ events }: { events?: CashEvent[] }) {
  if (!events?.length) return null
  return (
    <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
      {events.slice(0, 5).map((e, i) => (
        <div key={i} className="flex justify-between gap-3">
          <span className="truncate text-navy-500">{e.label}</span>
          <span className={`tabular font-medium ${e.amount > 0 ? 'text-brand-700' : 'text-navy-800'}`}>{signedInr(e.amount)}</span>
        </div>
      ))}
      {events.length > 5 && <p className="text-navy-400">+{events.length - 5} more</p>}
    </div>
  )
}

export const tooltipDate = (d: string) => fmtDate(d)
export { inr }
