import { CalendarClock, CheckCircle2, Loader2, Wallet, XCircle } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { DemoBanner } from '../components/DemoBanner'
import { Card } from '../components/ui/Card'
import { ErrorState, PageSkeleton } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { inr } from '../lib/format'

/** Stand-in for PayPal's checkout approval screen, used only in PayPal demo mode. */
export default function PayPalDemoCheckout() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const order = useApi(() => api.demoOrder(token), [token])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!token) return <ErrorState error={new Error('Missing order token.')} />
  if (order.loading && !order.data) return <PageSkeleton />
  if (order.error) return <ErrorState error={order.error} onRetry={order.reload} />
  if (!order.data) return null
  const o = order.data
  const open = o.status === 'PAYER_ACTION_REQUIRED'

  async function go(kind: 'paypal' | 'paylater' | 'cancel') {
    setBusy(kind); setError(null)
    try {
      const { redirect } = kind === 'cancel' ? await api.demoCancel(o.id) : await api.demoApprove(o.id, kind)
      window.location.assign(redirect)
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy(null) }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 py-4">
      <DemoBanner>Choose how you’d pay, just as you would on PayPal’s approval page.</DemoBanner>
      <Card>
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-navy-500">Approve payment to {o.merchant}</p>
        <p className="tabular mt-2 text-3xl font-semibold tracking-tight text-navy-900">{inr(o.amount)}</p>
        {o.description && <p className="mt-1 text-sm text-navy-600">{o.description}</p>}
        <p className="mt-1 text-[11px] text-navy-400">Demo order {o.id} · {o.currency}</p>

        {open ? (
          <div className="mt-6 space-y-2.5">
            <Choice icon={<Wallet className="h-5 w-5" />} title="Pay in full" text="Demo PayPal balance" busy={busy === 'paypal'} disabled={!!busy} onClick={() => void go('paypal')} />
            <Choice icon={<CalendarClock className="h-5 w-5" />} title="Pay Later" text="Instalments (demo: always approved)" busy={busy === 'paylater'} disabled={!!busy} onClick={() => void go('paylater')} />
            <button disabled={!!busy} onClick={() => void go('cancel')} className="w-full rounded-xl px-4 py-2.5 text-sm font-medium text-navy-600 hover:bg-slate-50 disabled:opacity-50">
              {busy === 'cancel' ? 'Cancelling…' : 'Cancel and return to FINORA'}
            </button>
            <p className="pt-1 text-center text-[11px] text-navy-400">Approving doesn’t charge anything yet. You’ll confirm once more in FINORA.</p>
          </div>
        ) : (
          <div className="mt-6 rounded-xl bg-slate-50 p-4 text-sm text-navy-700">
            <p className="flex items-center gap-2 font-medium">
              {o.status === 'VOIDED' ? <XCircle className="h-4 w-4 text-navy-400" /> : <CheckCircle2 className="h-4 w-4 text-brand-600" />}
              This demo order is {o.status.toLowerCase()}{o.funding ? ` (${o.funding === 'paylater' ? 'Pay Later' : 'pay in full'})` : ''}.
            </p>
            <Link to="/simulator" className="mt-2 inline-block font-semibold text-navy-900 hover:underline">Back to the simulator</Link>
          </div>
        )}
        {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-2.5 text-[13px] text-red-700">{error}</p>}
      </Card>
    </div>
  )
}

function Choice({ icon, title, text, busy, disabled, onClick }: { icon: ReactNode; title: string; text: string; busy: boolean; disabled: boolean; onClick: () => void }) {
  return (
    <button disabled={disabled} onClick={onClick}
      className="flex w-full items-center gap-3 rounded-xl border-2 border-slate-200 px-4 py-3 text-left transition hover:border-navy-900 disabled:opacity-50">
      <span className="text-navy-700">{icon}</span>
      <span className="flex-1"><span className="block text-sm font-semibold text-navy-900">{title}</span><span className="block text-xs text-navy-500">{text}</span></span>
      {busy && <Loader2 className="h-4 w-4 animate-spin text-navy-400" />}
    </button>
  )
}
