import { AlertTriangle, CalendarClock, CheckCircle2, Info, Loader2, Lock, ShieldCheck, SplitSquareHorizontal, Wallet, X, XCircle } from 'lucide-react'
import { useState } from 'react'
import { ApiError, api } from '../lib/api'
import { fmtDate, inr } from '../lib/format'
import type { PaymentComparison, PaymentOption } from '../lib/types'
import { OptionsChart, optionColor, optionShortName } from './charts/OptionsChart'
import { Badge, ProjectedTag } from './ui/Badge'
import { Card, CardHeader } from './ui/Card'

/** Restrained, severity-coded verdict panels. Green only when paying in full is itself safe. */
const VERDICT = {
  pay_now: { Icon: CheckCircle2, panel: 'border-emerald-200 bg-emerald-50 text-emerald-950', icon: 'text-emerald-600' },
  split: { Icon: SplitSquareHorizontal, panel: 'border-sky-200 bg-sky-50 text-navy-950', icon: 'text-[#003087]' },
  wait: { Icon: CalendarClock, panel: 'border-amber-200 bg-amber-50 text-amber-950', icon: 'text-amber-600' },
  not_recommended: { Icon: XCircle, panel: 'border-red-200 bg-red-50 text-red-950', icon: 'text-red-600' },
} as const

/**
 * "Buy now, wait, or split it?"
 * variant="cards"  (Assistant) a card per option with consistent fields and actions.
 * variant="matrix" (Simulator) a compact comparison table, so the same cards aren't repeated on two screens.
 */
export function PaymentOptions({ cmp, compact = false, variant = 'cards', onChanged }: {
  cmp: PaymentComparison; compact?: boolean; variant?: 'cards' | 'matrix'; onChanged?: () => void
}) {
  const [confirming, setConfirming] = useState<PaymentOption | null>(null)
  const [planned, setPlanned] = useState<string | null>(null)
  const [planError, setPlanError] = useState<string | null>(null)
  const rec = cmp.recommendation
  const v = VERDICT[rec.verdict]
  const focus = cmp.options.find((o) => o.id === rec.option_id) ?? cmp.options.find((o) => o.id === rec.least_risky_id) ?? cmp.options[0]
  const [shown, setShown] = useState<string[] | 'all'>([focus.id])

  async function plan(o: PaymentOption) {
    setPlanError(null)
    try {
      await api.planPurchase({ amount: cmp.amount, label: cmp.label, on: o.get_it_on })
      setPlanned(o.id)
      onChanged?.()
    } catch (e) { setPlanError(e instanceof ApiError ? e.message : String(e)) }
  }

  const hasPayLater = cmp.options.some((o) => o.kind === 'pay_later')
  return (
    <Card>
      <CardHeader title="Payment strategies" icon={<Wallet className="h-4 w-4" />} action={<ProjectedTag />}
        subtitle={`${inr(cmp.amount)} · ${cmp.label}. Each option is simulated until ${cmp.assumptions.horizon_days} days after its last payment.`} />

      <div className={`flex items-start gap-3 rounded-xl border p-4 ${v.panel}`}>
        <v.Icon className={`mt-0.5 h-5 w-5 shrink-0 ${v.icon}`} />
        <div>
          <p className="font-semibold">{rec.headline}</p>
          <p className="mt-1 text-[13px] opacity-80">{rec.explanation[0]}</p>
        </div>
      </div>

      <div className="mt-5">
        <div className="mb-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="Strategies shown on the chart">
          <span className="mr-1 text-[12px] text-navy-500">Show:</span>
          {cmp.options.map((o) => {
            const on = shown === 'all' || shown.includes(o.id)
            return (
              <button key={o.id} aria-pressed={on}
                onClick={() => setShown((s) => s === 'all' ? [o.id] : s.includes(o.id) ? (s.length > 1 ? s.filter((x) => x !== o.id) : s) : [...s, o.id])}
                className={`inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[12px] font-medium transition ${on ? 'border-navy-900 bg-navy-900 text-white' : 'border-slate-200 text-navy-700 hover:bg-slate-50'}`}>
                <span className="h-2 w-2 rounded-full" style={{ background: optionColor(o, cmp.options) }} aria-hidden />{optionShortName(o, cmp.options)}
              </button>
            )
          })}
          <button aria-pressed={shown === 'all'} onClick={() => setShown(shown === 'all' ? [focus.id] : 'all')}
            className={`inline-flex h-7 items-center rounded-full border px-2.5 text-[12px] font-medium ${shown === 'all' ? 'border-navy-900 bg-navy-900 text-white' : 'border-slate-200 text-navy-700 hover:bg-slate-50'}`}>All</button>
        </div>
        <OptionsChart cmp={cmp} height={compact ? 230 : 300} visible={shown === 'all' ? cmp.options.map((o) => o.id) : shown} />
      </div>

      {variant === 'matrix'
        ? <Matrix cmp={cmp} planned={planned} onCheckout={setConfirming} onPlan={(o) => void plan(o)} />
        : (
          <div className={`mt-5 grid grid-cols-1 gap-3 ${compact ? 'sm:grid-cols-2' : 'sm:grid-cols-2 2xl:grid-cols-4'}`}>
            {cmp.options.map((o) => (
              <OptionCard key={o.id} o={o} cmp={cmp} planned={planned === o.id} onCheckout={() => setConfirming(o)} onPlan={() => void plan(o)} />
            ))}
          </div>
        )}
      {planError && <p role="alert" className="mt-3 text-sm text-red-600">{planError}</p>}

      {!compact && rec.explanation.length > 1 && (
        <details className="mt-4 rounded-xl bg-slate-50 p-3 text-[13px] text-navy-600">
          <summary className="cursor-pointer font-medium text-navy-800">How each option was judged</summary>
          <ul className="mt-2 space-y-1.5">{rec.explanation.slice(1).map((l, i) => <li key={i}>• {l}</li>)}</ul>
        </details>
      )}
      {hasPayLater && <p className="mt-3 flex gap-1.5 text-[11.5px] leading-relaxed text-navy-500"><Info className="mt-px h-3.5 w-3.5 shrink-0" />{cmp.terms_note}</p>}

      {confirming && <ConfirmCheckout cmp={cmp} option={confirming} onClose={() => setConfirming(null)} />}
    </Card>
  )
}

const dueToday = (o: PaymentOption, asOf: string) => o.payments.filter((p) => p.on === asOf).reduce((t, p) => t + p.amount, 0)

function BufferImpact({ o }: { o: PaymentOption }) {
  return o.safe
    ? <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" />Stays above</span>
    : <span className="inline-flex items-center gap-1 text-red-700"><AlertTriangle className="h-3.5 w-3.5" />{o.days_below_buffer} day{o.days_below_buffer === 1 ? '' : 's'} below</span>
}

function OptionCard({ o, cmp, planned, onCheckout, onPlan }: {
  o: PaymentOption; cmp: PaymentComparison; planned: boolean; onCheckout: () => void; onPlan: () => void
}) {
  const later = o.payments.filter((p) => p.on !== cmp.as_of)
  const why = o.recommended ? 'Recommended: the cheapest option that keeps you above your buffer.'
    : !o.safe ? 'Not recommended: your balance would fall below the buffer.'
    : o.extra_cost > 0 ? 'Safe, but costs more than the recommended option.' : 'Safe, but the recommended option suits your cash flow better.'
  return (
    <div className={`flex flex-col rounded-xl border p-4 transition ${o.recommended ? 'border-emerald-500 bg-emerald-50/40 ring-1 ring-emerald-500' : o.safe ? 'border-slate-200' : 'border-slate-200 bg-slate-50/60'}`}>
      <div className="flex items-start justify-between gap-2">
        <p className={`flex items-center gap-2 text-[13.5px] font-semibold ${o.safe ? 'text-navy-900' : 'text-navy-600'}`}>
          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: optionColor(o, cmp.options) }} aria-hidden />{o.name}
        </p>
        {o.recommended ? <Badge tone="green" icon={<ShieldCheck className="h-3 w-3" />}>Recommended</Badge>
          : o.safe ? <Badge tone="neutral">Safe</Badge> : <Badge tone="red">Below buffer</Badge>}
      </div>
      {o.kind === 'pay_later' && <p className="mt-1 text-[11px] font-medium text-amber-800">Illustrative terms. PayPal decides eligibility, APR and schedule.</p>}

      <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12.5px]">
        <dt className="text-navy-500">Due today</dt><dd className="tabular text-right font-medium text-navy-900">{inr(dueToday(o, cmp.as_of))}</dd>
        <dt className="text-navy-500">Later payments</dt>
        <dd className="tabular text-right font-medium text-navy-900">{later.length ? `${later.length} × ${inr(later[0].amount)}` : 'None'}</dd>
        <dt className="text-navy-500">Lowest balance</dt>
        <dd className={`tabular text-right font-semibold ${o.safe ? 'text-navy-900' : 'text-red-700'}`}>{inr(o.min_balance)}</dd>
        <dt className="text-navy-500">Buffer</dt><dd className="text-right font-medium"><BufferImpact o={o} /></dd>
        <dt className="text-navy-500">Extra cost</dt>
        <dd className="tabular text-right font-medium text-navy-900">{o.extra_cost > 0 ? `${inr(o.extra_cost)} · ${o.apr}% APR` : '₹0'}</dd>
      </dl>
      <p className="mt-3 border-t border-slate-100 pt-2 text-[11.5px] leading-relaxed text-navy-500">{why}</p>
      <div className="mt-auto pt-3"><OptionAction o={o} planned={planned} onCheckout={onCheckout} onPlan={onPlan} /></div>
    </div>
  )
}

/** Payment actions (prepare a PayPal checkout) look different from planning actions. Neither imitates PayPal's buttons. */
function OptionAction({ o, planned, onCheckout, onPlan, small = false }: { o: PaymentOption; planned: boolean; onCheckout: () => void; onPlan: () => void; small?: boolean }) {
  const size = small ? 'h-8 whitespace-nowrap px-2.5 text-[12px]' : 'h-9 w-full px-3 text-[13px]'
  if (o.action === 'checkout') {
    return (
      <button onClick={onCheckout} className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-semibold transition ${size} ${o.safe ? 'bg-navy-900 text-white hover:bg-navy-800' : 'border border-slate-300 bg-white text-navy-700 hover:bg-slate-50'}`}>
        <Lock className="h-3.5 w-3.5" /> {small ? 'PayPal checkout' : 'Prepare PayPal checkout'}
      </button>
    )
  }
  if (o.action === 'plan') {
    return (
      <button onClick={onPlan} disabled={planned} className={`inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white font-semibold text-navy-800 hover:bg-slate-50 disabled:opacity-60 ${size}`}>
        <CalendarClock className="h-3.5 w-3.5" /> {planned ? (small ? 'Planned' : `Planned for ${fmtDate(o.get_it_on)}`) : (small ? 'Plan purchase' : `Plan for ${fmtDate(o.get_it_on)}`)}
      </button>
    )
  }
  return null
}

function Matrix({ cmp, planned, onCheckout, onPlan }: { cmp: PaymentComparison; planned: string | null; onCheckout: (o: PaymentOption) => void; onPlan: (o: PaymentOption) => void }) {
  return (
    <div className="mt-5 overflow-x-auto">
      <table className="w-full min-w-[760px] text-[13px]">
        <thead>
          <tr className="border-b border-slate-200 text-left text-[11.5px] font-semibold uppercase tracking-wide text-navy-500">
            <th className="py-2 pr-3">Payment option</th><th className="py-2 pr-3 text-right">Upfront outflow</th>
            <th className="py-2 pr-3 text-right">Lowest projected balance</th><th className="py-2 pr-3 text-right">Extra fees / APR</th>
            <th className="py-2 pr-3">Cash-flow impact</th><th className="py-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {cmp.options.map((o) => (
            <tr key={o.id} className={o.recommended ? 'bg-emerald-50/50' : ''}>
              <td className="py-2.5 pr-3">
                <p className={`flex items-center gap-2 font-medium ${o.safe ? 'text-navy-900' : 'text-navy-600'}`}>
                  <span className="h-2 w-2 rounded-full" style={{ background: optionColor(o, cmp.options) }} aria-hidden />{o.name}
                  {o.recommended && <Badge tone="green">Recommended</Badge>}
                </p>
                {o.kind === 'pay_later' && <p className="ml-4 text-[11px] text-amber-800">Illustrative terms</p>}
              </td>
              <td className="tabular py-2.5 pr-3 text-right">{inr(dueToday(o, cmp.as_of))}{o.kind === 'wait' && <span className="block text-[11px] text-navy-400">{inr(o.payments[0].amount)} on {fmtDate(o.get_it_on)}</span>}</td>
              <td className={`tabular py-2.5 pr-3 text-right font-semibold ${o.safe ? 'text-navy-900' : 'text-red-700'}`}>{inr(o.min_balance)}<span className="block text-[11px] font-normal text-navy-400">{fmtDate(o.min_balance_date)}</span></td>
              <td className="tabular py-2.5 pr-3 text-right">{o.extra_cost > 0 ? `${inr(o.extra_cost)} · ${o.apr}%` : '₹0'}</td>
              <td className="py-2.5 pr-3"><BufferImpact o={o} /></td>
              <td className="py-2.5 text-right"><OptionAction small o={o} planned={planned === o.id} onCheckout={() => onCheckout(o)} onPlan={() => onPlan(o)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Step 1 of 3: review the simulated impact before FINORA asks PayPal to create the order. */
function ConfirmCheckout({ cmp, option, onClose }: { cmp: PaymentComparison; option: PaymentOption; onClose: () => void }) {
  const [ack, setAck] = useState(false)
  const [risk, setRisk] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const ready = ack && (option.safe || risk)

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
            <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#003087]">Step 1 of 3 · Review</p>
            <h2 id="confirm-title" className="mt-1 text-lg font-semibold text-navy-900">{option.name}: {inr(cmp.amount)}</h2>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 hover:bg-slate-100"><X className="h-4 w-4" /></button>
        </div>

        <div className={`mt-4 flex gap-2 rounded-xl border p-3 text-[13px] ${option.safe ? 'border-emerald-200 bg-emerald-50 text-emerald-900' : 'border-red-200 bg-red-50 text-red-800'}`}>
          {option.safe ? <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
          <span>
            {option.safe
              ? `Your balance is projected to stay above your ${inr(cmp.assumptions.safety_buffer)} buffer. The lowest point is ${inr(option.min_balance)} on ${fmtDate(option.min_balance_date)}.`
              : `Your balance is projected to drop to ${inr(option.min_balance)} on ${fmtDate(option.min_balance_date)}, below your ${inr(cmp.assumptions.safety_buffer)} buffer for ${option.days_below_buffer} day(s).`}
          </span>
        </div>

        <ul className="mt-4 max-h-40 space-y-1 overflow-y-auto text-[13px] text-navy-700">
          {option.payments.map((p, i) => (
            <li key={i} className="flex justify-between"><span>{p.on === cmp.as_of ? 'Today' : fmtDate(p.on)}</span><span className="tabular font-medium">{inr(p.amount)}</span></li>
          ))}
        </ul>
        {option.extra_cost > 0 && <p className="mt-2 text-[13px] text-navy-600">Includes {inr(option.extra_cost)} interest at {option.apr}% APR (illustrative).</p>}
        {option.funding === 'paylater' && <p className="mt-2 text-[11.5px] text-navy-500">{cmp.terms_note} If offered, choose Pay Later on PayPal’s page.</p>}

        <label className="mt-4 flex cursor-pointer items-start gap-2.5 text-[13px] text-navy-800">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 h-4 w-4 accent-[#003087]" />
          I’ve reviewed how this payment affects my projected balance.
        </label>
        {!option.safe && (
          <label className="mt-2 flex cursor-pointer items-start gap-2.5 text-[13px] text-red-800">
            <input type="checkbox" checked={risk} onChange={(e) => setRisk(e.target.checked)} className="mt-0.5 h-4 w-4 accent-red-600" />
            I understand this takes my balance below my safety buffer.
          </label>
        )}

        {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-2.5 text-[13px] text-red-700">{error.message}</p>}

        <div className="mt-5 flex gap-2">
          <button onClick={onClose} className="h-10 flex-1 rounded-xl border border-slate-200 px-4 text-sm font-semibold text-navy-800 hover:bg-slate-50">Not now</button>
          <button onClick={() => void go()} disabled={!ready || busy}
            className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-xl bg-[#003087] px-4 text-sm font-semibold text-white hover:bg-[#002366] disabled:opacity-40">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Continue to PayPal
          </button>
        </div>
        <p className="mt-3 text-center text-[11.5px] text-navy-500">Nothing is charged yet. Next you approve on PayPal (step 2), then confirm the capture in FINORA (step 3).</p>
      </div>
    </div>
  )
}
