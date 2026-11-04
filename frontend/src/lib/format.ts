const inrFmt = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const inrFmt2 = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const inr = (v: number, decimals = false) => (decimals ? inrFmt2 : inrFmt).format(v)

/** Compact Indian notation for axes: ₹1.2L, ₹45K, ₹1.1Cr. */
export function inrCompact(v: number): string {
  const a = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (a >= 1e7) return `${sign}₹${trim(a / 1e7)}Cr`
  if (a >= 1e5) return `${sign}₹${trim(a / 1e5)}L`
  if (a >= 1e3) return `${sign}₹${trim(a / 1e3)}K`
  return `${sign}₹${Math.round(a)}`
}
const trim = (n: number) => (n >= 100 ? n.toFixed(0) : n.toFixed(1)).replace(/\.0$/, '')

export const signedInr = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${inr(Math.abs(v))}`

export const pct = (v: string | number, digits = 1) => `${(Number(v) * 100).toFixed(digits)}%`

const parse = (d: string) => new Date(`${d}T00:00:00`)
export const fmtDate = (d: string) => parse(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
export const fmtShort = (d: string) => parse(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
export const fmtMonth = (m: string) => parse(`${m}-01`).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })

export function daysBetween(from: string, to: string): number {
  return Math.round((parse(to).getTime() - parse(from).getTime()) / 86_400_000)
}

export function addDays(d: string, n: number): string {
  const x = parse(d)
  x.setDate(x.getDate() + n)
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
}

export function greeting(): string {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

/** Where a recurring item came from, for small captions: "seen 6×", "added by you", "from PayPal". */
export const recurringOrigin = (r: { source?: 'detected' | 'manual' | 'paypal'; occurrences: number }) =>
  r.source === 'manual' ? 'added by you' : r.source === 'paypal' ? 'from PayPal' : `seen ${r.occurrences}×`

export const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
