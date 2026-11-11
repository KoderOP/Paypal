import { AlertTriangle, CalendarClock, CheckCircle2, CreditCard, Info, Loader2, ShieldCheck, SplitSquareHorizontal, Wallet, X, XCircle } from 'lucide-react'
import { useState } from 'react'
import { ApiError, api } from '../lib/api'
import { fmtDate, fmtShort, inr } from '../lib/format'
import type { PaymentComparison, PaymentOption } from '../lib/types'
import { OptionsChart, optionColor } from './charts/OptionsChart'
import { Badge, ProjectedTag } from './ui/Badge'
import { Card, CardHeader } from './ui/Card'

const VERDICT = {
  pay_now: { Icon: CheckCircle2, tone: 'from-emerald-600 to-emerald-700' },
  wait: { Icon: CalendarClock, tone: 'from-navy-900 to-navy-800' },
  split: { Icon: SplitSquareHorizontal, tone: 'from-[#001c64] to-[#0b4fb3]' },
  not_recommended: { Icon: XCircle, tone: 'from-red-700 to-red-800' },
} as const

/** "Buy now, wait, or split it?" — the comparison, a chart with one line per option, and actions. */
export function PaymentOptions({ cmp, compact = false, onChanged }: { cmp: PaymentComparison; compact?: boolean; onChanged?: () => void }) {
  const [hover, setHover] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<PaymentOption | null>(null)
  const [planned, setPlanned] = useState<string | null>(null)
  const [planError, setPlanError] = useState<string | null>(null)
  const rec = cmp.recommendation
  const v = VERDICT[rec.verdict]

  async function plan(o: PaymentOption) {
    setPlanError(null)
    try {
      await api.planPurchase({ amount: cmp.amount, label: cmp.label, on: o.get_it_on })
      setPlanned(o.id)
      onChanged?.()
    } catch (e) { setPlanError(e instanceof ApiError ? e.message : String(e)) }
  }

  return (
    <Card>
      <CardHeader title="Buy now, wait, or split it?" icon={<Wallet className="h-4 w-4" />} action={<ProjectedTag />}
        subtitle={`${inr(cmp.amount)} · ${cmp.label}. Each option is simulated until ${cmp.assumptions.horizon_days} days after its last payment.`} />

      <div className={`relative overflow-hidden rounded-xl bg-gradient-to-br ${v.tone} p-4 text-white`}>
        <div className="flex items-start gap-3">
          <v.Icon className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <p className="font-semibold">{rec.headline}</p>
            <p className="mt-1 text-[13px] text-white/80">{rec.explanation[0]}</p>
          </div>
        </div>
      </div>

      <div className="mt-5"><OptionsChart cmp={cmp} height={compact ? 220 : 300} highlight={hover} /></div>

      <div className={`mt-5 grid grid-cols-1 gap-3 ${compact ? 'sm:grid-cols-2' : 'sm:grid-cols-2 2xl:grid-cols-4'}`}>
        {cmp.options.map((o) => (
          <OptionCard key={o.id} o={o} cmp={cmp} compact={compact} planned={planned === o.id}
            onHover={setHover} onCheckout={() => setConfirming(o)} onPlan={() => void plan(o)} />
        ))}
      </div>
      {planError && <p role="alert" className="mt-3 text-sm text-red-600">{planError}</p>}

      {!compact && rec.explanation.length > 1 && (
        <details className="mt-4 rounded-xl bg-slate-50 p-3 text-[13px] text-navy-600">
          <summary className="cursor-pointer font-medium text-navy-800">How each option was judged</summary>
          <ul className="mt-2 space-y-1.5">{rec.explanation.slice(1).map((l, i) => <li key={i}>• {l}</li>)}</ul>
        </details>
      )}
      <p className="mt-3 flex gap-1.5 text-[11px] leading-relaxed text-navy-400"><Info className="mt-px h-3.5 w-3.5 shrink-0" />{cmp.terms_note}</p>

      {confirming && <ConfirmCheckout cmp={cmp} option={confirming} onClose={() => setConfirming(null)} />}
    </Card>
  )
}

function OptionCard({ o, cmp, compact, planned, onHover, onCheckout, onPlan }: {
  o: PaymentOption; cmp: PaymentComparison; compact: boolean; planned: boolean
  onHover: (id: string | null) => void; onCheckout: () => void; onPlan: () => void
}) {
  const shown = o.payments.slice(0, 4)
  return (
    <div onMouseEnter={() => onHover(o.id)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(o.id)} onBlur={() => onHover(null)}
      className={`flex flex-col rounded-xl border p-4 transition ${o.recommended ? 'border-brand-500 bg-brand-50/40 ring-1 ring-brand-500' : 'border-slate-200'}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="flex items-center gap-2 text-[13px] font-semibold text-navy-900">
          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: optionColor(o, cmp.options) }} aria-hidden />
          {o.name}
        </p>
        {o.recommended ? <Badge tone="green" icon={<ShieldCheck className="h-3 w-3" />}>Best</Badge>
          : o.safe ? <Badge tone="green">Safe</Badge> : <Badge tone="red" icon={<AlertTriangle className="h-3 w-3" />}>Below buffer</Badge>}
      </div>
      <p className="mt-1 text-[11px] leading-relaxed text-navy-500">{o.summary}</p>

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12px]">
        <dt className="text-navy-500">You get it</dt><dd className="tabular text-right font-medium text-navy-900">{o.get_it_on === cmp.as_of ? 'Today' : fmtShort(o.get_it_on)}</dd>
        <dt className="text-navy-500">Lowest balance</dt><dd className={`tabular text-right font-semibold ${o.safe ? 'text-navy-900' : 'text-red-700'}`}>{inr(o.min_balance)}</dd>
        <dt className="text-navy-500">Total paid</dt><dd className="tabular text-right font-medium text-navy-900">{inr(o.total_paid)}</dd>
        <dt className="text-navy-500">Extra cost</dt><dd className="tabular text-right font-medium text-navy-900">{o.extra_cost > 0 ? inr(o.extra_cost) : '₹0'}</dd>
      </dl>

      {!compact && (
        <ul className="mt-3 space-y-1 border-t border-slate-100 pt-2 text-[11px] text-navy-500">
          {shown.map((p, i) => (
            <li key={i} className="flex justify-between"><span>{p.on === cmp.as_of ? 'Today' : fmtShort(p.on)}</span><span className="tabular">{inr(p.amount)}</span></li>
          ))}
          {o.payments.length > shown.length && <li className="text-navy-400">+{o.payments.length - shown.length} more payments</li>}
        </ul>
      )}

      <div className="mt-auto pt-3">
        {o.action === 'checkout' && (
          <button onClick={onCheckout}
            className={`inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-semibold transition ${o.funding === 'paylater' ? 'bg-[#ffc439] text-[#001c64] hover:bg-[#f2b72e]' : 'bg-[#003087] text-white hover:bg-[#002366]'}`}>
            <CreditCard className="h-3.5 w-3.5" /> {o.funding === 'paylater' ? 'Pay Later with PayPal' : 'Pay with PayPal'}
          </button>
        )}
        {o.action === 'plan' && (
          <button onClick={onPlan} disabled={planned}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-[13px] font-semibold text-navy-800 hover:bg-slate-50 disabled:opacity-60">
            <CalendarClock className="h-3.5 w-3.5" /> {planned ? `Planned for ${fmtShort(o.get_it_on)}` : `Plan it for ${fmtShort(o.get_it_on)}`}
          </button>
        )}
      </div>
    </div>
  )
}

/** First explicit confirmation: review the simulated impact before being sent to PayPal. */
function ConfirmCheckout({ cmp, option, onClose }: { cmp: PaymentComparison; option: PaymentOption; onClose: () => void }) {
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function go() {
    setBusy(true); setError(null)
    try {
      const order = await api.startCheckout({ amount: cmp.amount, label: cmp.label, option_id: option.id, acknowledged: true,
        safety_buffer: cmp.assumptions.safety_buffer })
      if (order.approve_url) window.location.assign(order.approve_url)
      else setError(new ApiError(502, order.error ?? 'PayPal did not return an approval link.'))
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)))
    } finally { setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-navy-950/40 p-4 sm:items-center" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-2xl sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#003087]">Step 1 of 2 · Review</p>
            <h2 id="confirm-title" className="mt-1 text-lg font-semibold text-navy-900">{option.name}: {inr(cmp.amount)}</h2>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 hover:bg-slate-100"><X className="h-4 w-4" /></button>
        </div>

        <div className={`mt-4 flex gap-2 rounded-xl p-3 text-[13px] ${option.safe ? 'bg-brand-50 text-brand-700' : 'bg-red-50 text-red-700'}`}>
          {option.safe ? <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
          <span>
            {option.safe
              ? `Your balance is projected to stay above your ${inr(cmp.assumptions.safety_buffer)} buffer. The lowest point is ${inr(option.min_balance)} on ${fmtDate(option.min_balance_date)}.`
              : `Warning: your balance is projected to drop to ${inr(option.min_balance)} on ${fmtDate(option.min_balance_date)}, below your ${inr(cmp.assumptions.safety_buffer)} buffer for ${option.days_below_buffer} day(s).`}
          </span>
        </div>

        <ul className="mt-4 max-h-40 space-y-1 overflow-y-auto text-[13px] text-navy-700">
          {option.payments.map((p, i) => (
            <li key={i} className="flex justify-between"><span>{p.on === cmp.as_of ? 'Today' : fmtDate(p.on)}</span><span className="tabular font-medium">{inr(p.amount)}</span></li>
          ))}
        </ul>
        {option.extra_cost > 0 && <p className="mt-2 text-[13px] text-navy-600">Includes {inr(option.extra_cost)} interest at {option.apr}% APR (illustrative).</p>}
        {option.funding === 'paylater' && <p className="mt-2 text-[11px] text-navy-400">{cmp.terms_note} Choose Pay Later on PayPal’s page.</p>}

        <label className="mt-4 flex cursor-pointer items-start gap-2.5 text-[13px] text-navy-800">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#003087]" />
          I’ve reviewed how this payment affects my projected balance.
        </label>

        {error && (
          <p role="alert" className="mt-3 rounded-lg bg-red-50 p-2.5 text-[13px] text-red-700">{error.message}</p>
        )}

        <div className="mt-5 flex gap-2">
          <button onClick={onClose} className="flex-1 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-navy-800 hover:bg-slate-50">Not now</button>
          <button onClick={() => void go()} disabled={!ack || busy}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-[#003087] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#002366] disabled:opacity-40">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Continue to PayPal
          </button>
        </div>
        <p className="mt-3 text-center text-[11px] text-navy-400">Nothing is charged yet. You’ll confirm once more after approving on PayPal.</p>
      </div>
    </div>
  )
}
