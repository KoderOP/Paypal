import { Database, FlaskConical, ShieldCheck, Upload, Wallet } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useDataStatus } from '../context/DataStatus'
import type { Origin, Provenance } from '../lib/types'

/** Short, consistent names for where data came from. The backend records provenance; the UI only labels it. */
function originShort(origin: Origin, environment: string | null): string {
  switch (origin) {
    case 'sample': return 'Sample · fictional'
    case 'user_import': return 'Your imported file'
    case 'paypal_api': return environment === 'demo' ? 'PayPal demo mode · simulated' : `PayPal ${cap(environment)} · Transaction Search`
    case 'paypal_checkout': return environment === 'demo' ? 'Checkout · PayPal demo mode' : `PayPal ${cap(environment)} · Orders API capture`
    default: return 'Source not recorded'
  }
}
const cap = (s: string | null) => (s ? s[0].toUpperCase() + s.slice(1) : '')

function tone(origin: Origin, environment: string | null): string {
  if (origin === 'sample' || environment === 'demo') return 'bg-amber-50 text-amber-900 ring-amber-300'
  if (origin === 'paypal_api' || origin === 'paypal_checkout') return 'bg-[#003087]/[0.06] text-[#003087] ring-[#003087]/25'
  return 'bg-slate-50 text-navy-700 ring-slate-300'
}

function Icon({ origin, environment }: { origin: Origin; environment: string | null }) {
  const cls = 'h-3 w-3 shrink-0'
  if (origin === 'sample' || environment === 'demo') return <FlaskConical className={cls} />
  if (origin === 'paypal_checkout') return <ShieldCheck className={cls} />
  if (origin === 'paypal_api') return <Wallet className={cls} />
  if (origin === 'user_import') return <Upload className={cls} />
  return <Database className={cls} />
}

/** One row's source, e.g. in the transaction table. */
export function OriginBadge({ origin, environment, title }: { origin: Origin; environment: string | null; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${tone(origin, environment)}`}>
      <Icon origin={origin} environment={environment} />{originShort(origin, environment)}
    </span>
  )
}

/** Where the data on this page comes from: one badge per source present, with counts. For page headers. */
export function ProvenanceTag({ provenance }: { provenance?: Provenance[] }) {
  const { status } = useDataStatus()
  const rows = provenance ?? status?.provenance ?? []
  if (!rows.length) return null
  return (
    <div className="flex flex-wrap items-center justify-end gap-1.5" aria-label="Data sources">
      <span className="text-[11px] font-medium text-navy-400">Data:</span>
      {rows.map((p) => (
        <OriginBadge key={`${p.origin}-${p.environment}`} origin={p.origin} environment={p.environment}
          title={`${p.label}: ${p.count} transaction(s)`} />
      ))}
    </div>
  )
}

/** Persistent strip shown on every app page while any fictional data is loaded. */
export function SampleDataBanner() {
  const { status } = useDataStatus()
  if (!status?.sample_count) return null
  const real = status.provenance.filter((p) => !p.synthetic)
  return (
    <div role="note" className="z-20 border-b lg:sticky lg:top-0 border-amber-300 bg-[repeating-linear-gradient(135deg,#fffbeb_0,#fffbeb_12px,#fef3c7_12px,#fef3c7_24px)] px-4 py-1.5 text-[12.5px] text-amber-950 sm:px-6 lg:px-10">
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-3 gap-y-1">
        <span className="inline-flex items-center gap-1.5 rounded bg-amber-900 px-1.5 py-0.5 font-mono text-[10.5px] font-bold uppercase tracking-widest text-amber-50">
          <FlaskConical className="h-3 w-3" /> Sample data
        </span>
        <span>
          Fictional profile: <b>{status.sample_count}</b> synthetic transaction{status.sample_count === 1 ? '' : 's'}, not real customer or PayPal data.
          {real.length > 0 && <> Also loaded: {real.map((p) => `${p.count} ${originShort(p.origin, p.environment)}`).join(', ')}.</>}
        </span>
        <Link to="/paypal" className="font-semibold underline decoration-amber-700/50 underline-offset-2 hover:decoration-amber-900">What’s real?</Link>
      </div>
    </div>
  )
}
