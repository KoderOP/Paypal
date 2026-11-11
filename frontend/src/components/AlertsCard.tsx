import { AlertOctagon, AlertTriangle, ArrowRight, BellRing, Info, RotateCcw, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import type { Alert, AlertsView } from '../lib/types'

const LEVEL = {
  critical: { Icon: AlertOctagon, color: 'var(--status-critical)', label: 'Urgent', bg: 'bg-red-50/60 border-red-200' },
  warning: { Icon: AlertTriangle, color: 'var(--status-warning)', label: 'Heads-up', bg: 'bg-amber-50/50 border-amber-200' },
  info: { Icon: Info, color: 'var(--series-1)', label: 'FYI', bg: 'bg-white border-slate-200' },
} as const

/** Proactive alerts: what your twin sees coming, before it happens. Dismissing hides one occurrence. */
export function AlertsCard() {
  const [view, setView] = useState<AlertsView | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => { api.alerts().then(setView).catch(() => setFailed(true)) }, [])

  if (failed || !view) return null
  if (view.alerts.length === 0 && view.dismissed === 0) return null
  const dismiss = (a: Alert) => { void api.dismissAlert(a.id).then(setView) }

  return (
    <section aria-label="Alerts" className="mb-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-navy-900">
          <BellRing className="h-4 w-4 text-navy-400" /> Heads-up
          {view.alerts.length > 0 && <span className="rounded-full bg-navy-900 px-1.5 text-[11px] font-semibold text-white">{view.alerts.length}</span>}
        </h2>
        {view.dismissed > 0 && (
          <button onClick={() => void api.restoreAlerts().then(setView)} className="inline-flex items-center gap-1 text-xs font-medium text-navy-500 hover:text-navy-900">
            <RotateCcw className="h-3.5 w-3.5" /> Show {view.dismissed} dismissed
          </button>
        )}
      </div>
      {view.alerts.length === 0 ? (
        <p className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-navy-500">Nothing needs your attention right now.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {view.alerts.slice(0, 6).map((a) => {
            const { Icon, color, label, bg } = LEVEL[a.level]
            return (
              <li key={a.id} className={`relative flex gap-3 rounded-2xl border p-4 ${bg}`}>
                <Icon className="mt-0.5 h-5 w-5 shrink-0" style={{ color }} aria-hidden />
                <div className="min-w-0 flex-1 pr-6">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-navy-400">{label}</p>
                  <p className="text-sm font-semibold text-navy-900">{a.title}</p>
                  <p className="mt-0.5 text-[13px] text-navy-600">{a.detail}</p>
                  {a.action && (
                    <Link to={a.action.to} className="mt-2 inline-flex items-center gap-1 text-[13px] font-semibold text-navy-900 hover:underline">
                      {a.action.label} <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  )}
                </div>
                <button onClick={() => dismiss(a)} aria-label={`Dismiss: ${a.title}`} title="Dismiss"
                  className="absolute right-2.5 top-2.5 rounded-lg p-1 text-navy-400 hover:bg-white hover:text-navy-900">
                  <X className="h-4 w-4" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
