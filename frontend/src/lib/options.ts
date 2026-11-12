import type { PaymentOption } from './types'

/** Colour follows the option (entity), never its rank: fixed slots from the validated palette. */
export function optionColor(o: PaymentOption, all: PaymentOption[]): string {
  if (o.kind === 'pay_now') return 'var(--series-1)'
  if (o.kind === 'wait') return 'var(--series-2)'
  const laterIdx = all.filter((x) => x.kind === 'pay_later').findIndex((x) => x.id === o.id)
  return laterIdx === 0 ? 'var(--series-3)' : 'var(--series-4)'
}

/** Short labels for chart toggles: Pay now · Wait · Pay in 4 · Pay Monthly. */
export function optionShortName(o: PaymentOption, all: PaymentOption[]): string {
  if (o.kind === 'pay_now') return 'Pay now'
  if (o.kind === 'wait') return 'Wait'
  if (o.id.includes('pay_in_4')) return 'Pay in 4'
  if (o.id.includes('monthly')) return 'Pay Monthly'
  return all.filter((x) => x.kind === 'pay_later').length > 1 ? o.name : 'Pay Later'
}
