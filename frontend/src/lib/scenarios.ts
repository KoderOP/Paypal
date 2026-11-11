import { fmtShort, inr } from './format'
import type { ScenarioChange } from './types'

/** Short human label for one scenario change, e.g. "Laptop ₹75,000 on 15 Nov" or "USD/INR −3%". */
export function describeChange(c: ScenarioChange): string {
  const n = (k: string) => Number(c[k] ?? 0)
  const signed = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v)}%`
  switch (c.type) {
    case 'purchase': return `${c.label ?? 'Purchase'} ${inr(n('amount'))}${c.on ? ` on ${fmtShort(String(c.on))}` : ' today'}`
    case 'add_subscription': return `Subscribe: ${c.label ?? 'New subscription'} ${inr(n('amount'))}/mo`
    case 'cancel_subscriptions': return Array.isArray(c.names) && c.names.length ? `Cancel ${c.names.join(', ')}` : `Cancel ${n('count')} subscription(s)`
    case 'income_delay': return `${c.merchant ? `${c.merchant} pays` : 'Income'} ${n('days')} days late`
    case 'increase_savings': return `Savings +${n('percent')}%`
    case 'expense_increase': return `Spending ${signed(n('percent'))}`
    case 'unexpected_payment': return `${c.label ?? 'Unexpected payment'} ${inr(n('amount'))}`
    case 'fx_change': return `${c.currency ?? 'USD'}/INR ${signed(n('percent'))}`
    case 'income_loss': return `${c.percent && n('percent') < 100 ? `Income −${n('percent')}%` : 'No income'} for ${n('months') || 1} month(s)`
    default: return c.type
  }
}
