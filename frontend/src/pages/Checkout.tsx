import { AlertTriangle, ArrowLeft, CheckCircle2, ExternalLink, Hourglass, Loader2, ShieldCheck, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PayPalMark } from '../components/PayPalMark'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { ErrorState, PageSkeleton } from '../components/ui/States'
import { useDataStatus } from '../context/DataStatus'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { fmtDate, inr } from '../lib/format'
import type { CheckoutOrder } from '../lib/types'

export default function Checkout() {
  const { id } = useParams()
  const orderId = Number(id)
  const order = useApi(() => api.checkoutOrder(orderId), [orderId])
  const { refresh } = useDataStatus()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (order.loading && !order.data) return <PageSkeleton />
  if (order.error) return <ErrorState error={order.error} onRetry={order.reload} />
  if (!order.data) return null
  const o = order.data

  async function act(fn: () => Promise<CheckoutOrder>) {
    setBusy(true); setError(null)
    try { await fn(); order.reload(); await refresh() }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); order.reload() }
    finally { setBusy(false) }
  }

  return (
    <div className="mx-auto max-w-xl">
      <Link to="/simulator" className="inline-flex items-center gap-1.5 text-sm text-navy-500 hover:text-navy-900"><ArrowLeft className="h-4 w-4" /> Back to simulator</Link>
      <Card className="mt-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <PayPalMark />
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#003087]">PayPal checkout · {o.environment}</p>
              <h1 className="text-lg font-semibold text-navy-900">{o.label}</h1>
            </div>
          </div>
          <StatusBadge status={o.status} />
        </div>

        <div className="mt-5 rounded-xl bg-slate-50 p-4">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-navy-500">{o.snapshot.option_name ?? o.option_id}</span>
            <span className="tabular text-2xl font-semibold text-navy-900">{inr(o.amount)}</span>
          </div>
          {o.snapshot.paypal_charge?.rate && (
            <p className="mt-1 text-right text-[13px] font-medium text-[#003087]">
              Charged at PayPal: {o.snapshot.paypal_charge.currency} {Number(o.snapshot.paypal_charge.amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}
              <span className="font-normal text-navy-500"> · your rate ₹{o.snapshot.paypal_charge.rate} per {o.snapshot.paypal_charge.currency}</span>
            </p>
          )}
          {o.snapshot.summary && <p className="mt-1 text-[13px] text-navy-500">{o.snapshot.summary}</p>}
          {o.snapshot.min_balance && o.snapshot.min_balance_date && (
            <p className={`mt-3 flex gap-2 text-[13px] ${o.snapshot.safe ? 'text-brand-700' : 'text-red-700'}`}>
              {o.snapshot.safe ? <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
              When you started: lowest projected balance {inr(Number(o.snapshot.min_balance))} on {fmtDate(o.snapshot.min_balance_date)}
              {o.snapshot.safety_buffer ? ` (buffer ${inr(Number(o.snapshot.safety_buffer))})` : ''}.
            </p>
          )}
          {o.snapshot.payments && o.snapshot.payments.length > 1 && (
            <ul className="mt-3 max-h-36 space-y-1 overflow-y-auto border-t border-slate-200 pt-2 text-[13px] text-navy-700">
              {o.snapshot.payments.map((p, i) => (
                <li key={i} className="flex justify-between"><span>{fmtDate(p.on)}</span><span className="tabular">{inr(Number(p.amount))}</span></li>
              ))}
            </ul>
          )}
          {o.snapshot.terms_note && <p className="mt-2 text-[11px] text-navy-400">{o.snapshot.terms_note}</p>}
        </div>

        {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        {o.error && !error && o.status !== 'captured' && <p className="mt-4 rounded-lg bg-amber-50 p-3 text-[13px] text-amber-800">{o.error}</p>}

        <div className="mt-5">
          {o.status === 'approved' && (
            <>
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-navy-500">Step 2 of 2 · Confirm</p>
              <p className="mt-1 text-sm text-navy-600">PayPal approved this payment. Nothing has been charged yet. Confirm to pay now.</p>
              <div className="mt-4 flex gap-2">
                <button disabled={busy} onClick={() => void act(() => api.cancelCheckout(o.id))}
                  className="flex-1 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-navy-800 hover:bg-slate-50 disabled:opacity-50">Cancel</button>
                <button disabled={busy} onClick={() => void act(() => api.captureCheckout(o.id))}
                  className="inline-flex flex-[2] items-center justify-center gap-2 rounded-xl bg-[#003087] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#002366] disabled:opacity-50">
                  {busy && <Loader2 className="h-4 w-4 animate-spin" />} Confirm and pay {inr(o.amount)}
                </button>
              </div>
            </>
          )}
          {o.status === 'awaiting_approval' && (
            <div className="flex flex-wrap gap-2">
              {o.approve_url && (
                <a href={o.approve_url} className="inline-flex items-center gap-1.5 rounded-xl bg-[#003087] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#002366]">
                  Approve on PayPal <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
              <button disabled={busy} onClick={() => void act(() => api.cancelCheckout(o.id))}
                className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-navy-800 hover:bg-slate-50">Cancel</button>
            </div>
          )}
          {o.status === 'captured' && (
            <div className="rounded-xl bg-brand-50 p-4 text-sm text-brand-700">
              <p className="flex items-center gap-2 font-semibold"><CheckCircle2 className="h-4 w-4" /> Paid with PayPal</p>
              <p className="mt-1 text-[13px]">Capture ID <code className="rounded bg-white/70 px-1">{o.capture_id}</code>.{' '}
                {o.snapshot.recorded?.kind === 'obligations'
                  ? `Your twin now includes ${o.snapshot.recorded.count} Pay Later instalments as upcoming payments.`
                  : 'Your twin now includes this payment, so your balance and forecast are already updated.'}
              </p>
              <div className="mt-3 flex gap-3 text-[13px] font-semibold">
                <Link to="/" className="hover:underline">See your updated forecast →</Link>
                <Link to="/simulator" className="hover:underline">Back to simulator</Link>
              </div>
            </div>
          )}
          {(o.status === 'cancelled' || o.status === 'failed') && (
            <p className="text-sm text-navy-600">{o.status === 'cancelled' ? 'This checkout was cancelled. Nothing was charged.' : 'This checkout didn’t complete. Nothing was charged.'}{' '}
              <Link to="/simulator" className="font-semibold text-[#003087] hover:underline">Try again from the simulator</Link></p>
          )}
        </div>
      </Card>
    </div>
  )
}

function StatusBadge({ status }: { status: CheckoutOrder['status'] }) {
  switch (status) {
    case 'captured': return <Badge tone="green" icon={<CheckCircle2 className="h-3 w-3" />}>Paid</Badge>
    case 'approved': return <Badge tone="blue" icon={<ShieldCheck className="h-3 w-3" />}>Approved</Badge>
    case 'awaiting_approval': case 'created': return <Badge tone="amber" icon={<Hourglass className="h-3 w-3" />}>Awaiting PayPal</Badge>
    case 'cancelled': return <Badge icon={<XCircle className="h-3 w-3" />}>Cancelled</Badge>
    default: return <Badge tone="red" icon={<AlertTriangle className="h-3 w-3" />}>Failed</Badge>
  }
}
