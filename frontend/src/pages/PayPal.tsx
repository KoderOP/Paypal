import type React from 'react'
import { ArrowDownLeft, ArrowRight, ArrowUpRight, Brain, CheckCircle2, CircleDashed, FlaskConical, KeyRound, Loader2, Lock, RefreshCw, ShieldCheck, Upload, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PayPalMark } from '../components/PayPalMark'
import { Badge } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { ErrorState, PageSkeleton } from '../components/ui/States'
import { useDataStatus } from '../context/DataStatus'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { fmtDate, inr } from '../lib/format'
import type { CheckoutOrder, PayPalOverview } from '../lib/types'
import { ProvenanceTag } from '../components/Provenance'

const FLOW = [
  { icon: KeyRound, title: 'Connect', text: 'OAuth 2.0 client credentials. Secrets stay on the server; the browser never sees them.' },
  { icon: RefreshCw, title: 'Sync', text: 'Read-only Transaction Search API, fetched in 31-day windows — or an uploaded Activity report.' },
  { icon: Brain, title: 'Learn', text: 'Transactions are normalised and the twin detects income, recurring payments and habits.' },
  { icon: FlaskConical, title: 'Simulate', text: 'A deterministic engine projects 90 days and compares paying now, waiting, or illustrative Pay in 4 / Pay Monthly terms.' },
  { icon: ShieldCheck, title: 'Act', text: 'Check out with PayPal (Orders v2): you acknowledge, approve on PayPal, then confirm the capture. Subscription actions also need confirmation.' },
]

export default function PayPal() {
  const pp = useApi(api.paypal)
  const { refresh } = useDataStatus()
  const navigate = useNavigate()
  const [syncing, setSyncing] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const orders = useApi(api.checkoutOrders)
  const [offerReplace, setOfferReplace] = useState(false)

  if (pp.loading && !pp.data) return <PageSkeleton />
  if (pp.error) return <ErrorState error={pp.error} onRetry={pp.reload} />
  if (!pp.data) return null
  const d = pp.data

  async function sync(replace = false) {
    setSyncing(true); setMsg(null); setOfferReplace(false)
    try {
      const r = await api.paypalSync(180, replace)
      setMsg({ ok: true, text: `Transaction Search returned ${r.rows} record(s): ${r.imported} new, ${r.skipped_duplicates} already stored.` })
      pp.reload(); await refresh()
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) })
      setOfferReplace(e instanceof ApiError && e.status === 409)
      pp.reload()
    } finally { setSyncing(false) }
  }

  return (
    <>
      <div className="rounded-2xl bg-[#0b1b3a] p-6 text-white sm:p-7">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3">
              <span className="rounded-2xl bg-white/10 p-1"><PayPalMark size="lg" /></span>
              <div>
                <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-sky-300">PayPal integration</p>
                <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">Connection status and records</h1>
              </div>
            </div>
            <p className="mt-4 text-[15px] leading-relaxed text-sky-100/90">
              FINORA reads PayPal records through Transaction Search and runs checkout through the Orders v2 API, with your approval on PayPal and an explicit capture confirmation. Pay in 4 and Pay Monthly figures elsewhere in FINORA are illustrative calculations, not a PayPal financing integration.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-medium ${d.demo ? 'bg-amber-300 text-amber-950' : 'bg-white/10'}`}>
                {d.demo ? 'Demo mode · simulated PayPal' : d.configured ? `${d.environment === 'sandbox' ? 'Sandbox' : 'Live'} credentials set` : 'REST API not configured'}
              </span>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium">{d.linked ? `${d.transaction_count} records from PayPal's APIs` : 'No records from PayPal yet'}</span>
              {d.sample_transactions > 0 && <span className="rounded-full bg-amber-300 px-3 py-1 text-xs font-semibold text-amber-950">{d.sample_transactions} sample transactions · not from PayPal</span>}
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium">Read-only sync · confirmed checkout</span>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            {d.configured && (
              <button disabled={syncing} onClick={() => void sync()} className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-[#003087] hover:bg-sky-50 disabled:opacity-60">
                <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} /> {syncing ? 'Syncing…' : d.demo ? 'Sync now (demo)' : 'Sync now'}
              </button>
            )}
            <button onClick={() => navigate('/get-started?method=paypal_activity')} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/30 px-4 py-2.5 text-sm font-semibold text-white hover:bg-white/10">
              <Upload className="h-4 w-4" /> {d.linked ? 'Upload new Activity report' : 'Connect PayPal data'}
            </button>
          </div>
        </div>
      </div>

      <IntegrationStatus d={d} orders={orders.data ?? []} />

      {msg && (
        <div role="status" className={`mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl p-3 text-sm ${msg.ok ? 'bg-brand-50 text-brand-700' : 'bg-red-50 text-red-700'}`}>
          <span>{msg.text}</span>
          {offerReplace && (
            <button onClick={() => { if (window.confirm('Replace the fictional sample profile with your PayPal records? The sample is removed from your twin.')) void sync(true) }}
              className="rounded-lg bg-[#003087] px-3 py-1.5 text-[13px] font-semibold text-white hover:bg-[#002366]">Replace the sample with PayPal records</button>
          )}
        </div>
      )}

      {d.linked ? (
        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 xl:col-span-2">
            <Stat label="Records from PayPal APIs" value={String(d.transaction_count)} sub={d.first_date && d.last_date ? `${fmtDate(d.first_date)} – ${fmtDate(d.last_date)}` : ''} />
            <Stat label="Money in via PayPal" value={inr(d.inflow)} sub="received" icon={<ArrowDownLeft className="h-4 w-4 text-brand-600" />} />
            <Stat label="Money out via PayPal" value={inr(d.outflow)} sub="paid" icon={<ArrowUpRight className="h-4 w-4 text-navy-400" />} />
            <Card className="sm:col-span-3">
              <CardHeader title="Where these records feed in" subtitle="PayPal records join the same ledger as your other data, each labelled with its source" />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Jump to="/overview" title="Overview" text="Balance, cash flow & 90-day projection" />
                <Jump to="/twin" title="My Financial Twin" text="Income cycles, recurring payments, habits" />
                <Jump to="/simulator" title="What-if Simulator" text="Simulate a ₹75,000 laptop purchase" />
              </div>
            </Card>
          </div>
          <Card>
            <CardHeader title="Top PayPal payees" subtitle="From PayPal API records only" />
            <ul className="divide-y divide-slate-100">
              {d.top_merchants.map((m) => (
                <li key={m.merchant} className="flex items-center justify-between py-2.5 first:pt-0">
                  <div><p className="text-sm text-navy-800">{m.merchant}</p><p className="text-[11px] text-navy-400">{m.count} payments</p></div>
                  <span className="tabular text-sm font-medium text-navy-900">{inr(m.total)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      ) : (
        <Card className="mt-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="font-semibold text-navy-900">No records from PayPal’s APIs yet</p>
              <p className="mt-1 text-sm text-navy-500">{d.sample_transactions ? `The ${d.sample_transactions} transactions you see elsewhere are fictional sample data in PayPal’s Activity-report format; none were retrieved from PayPal. ` : ''}Sync with Transaction Search, or upload your own PayPal Activity report.</p>
            </div>
            <Link to="/get-started?method=paypal_activity" className="inline-flex items-center gap-1.5 rounded-xl bg-[#003087] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#002366]">
              Get started <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </Card>
      )}

      <Card className="mt-6">
        <CardHeader title="How the PayPal integration works" />
        <ol className="grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-5">
          {FLOW.map((f, i) => (
            <li key={f.title} className="relative rounded-xl bg-slate-50 p-4">
              <span className="absolute right-3 top-3 text-[11px] font-semibold text-navy-400">0{i + 1}</span>
              <f.icon className="h-5 w-5 text-[#003087]" />
              <p className="mt-2 text-sm font-semibold text-navy-900">{f.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-navy-500">{f.text}</p>
            </li>
          ))}
        </ol>
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card>
          <CardHeader title="Trust & safety" icon={<ShieldCheck className="h-4 w-4" />} />
          <ul className="space-y-2 text-[13px] text-navy-600">
            <li className="flex gap-2"><Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-400" />Syncing is read-only. Money moves only through checkout, after three human steps: you confirm in FINORA, approve on PayPal, then confirm the capture in FINORA.</li>
            <li className="flex gap-2"><Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-400" />Credentials live only in the server environment.</li>
            <li className="flex gap-2"><Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-400" />Subscription cancel, suspend and re-activate each ask you to confirm first.</li>
            <li className="flex gap-2"><Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-400" />Sign in with PayPal is optional. Every feature works without it.</li>
            <li className="flex gap-2"><Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-400" />Duplicate-safe: re-syncs are matched on PayPal transaction ID.</li>
          </ul>
        </Card>
        <Card>
          <CardHeader title="Connection" action={<Badge tone={d.demo ? 'amber' : d.configured ? 'green' : 'neutral'}>{d.demo ? 'Demo mode' : d.configured ? d.environment : 'Not configured'}</Badge>} />
          <p className="text-[13px] text-navy-600">{d.message}</p>
          {d.demo && (
            <ul className="mt-3 space-y-1 text-[12px] text-navy-500">
              <li>• <b>Sync now</b> returns FINORA’s simulated history (the same fictional records as the sample file, so they are skipped as duplicates).</li>
              <li>• <b>Pay with PayPal / Pay Later</b> opens a labelled demo approval page; the “capture” is simulated (PayPal is never contacted) and recorded in your twin as demo mode.</li>
              <li>• <b>Subscriptions</b> can link demo PayPal subscriptions and cancel, suspend or re-activate them.</li>
              <li>• <b>Sign in with PayPal</b> uses a demo sign-in page with any name and email.</li>
            </ul>
          )}
          {(!d.configured || d.demo) && (
            <pre className="mt-3 overflow-x-auto rounded-lg bg-navy-900 p-3 text-[11px] text-slate-200">{`# .env (repo root) or backend/.env
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com`}</pre>
          )}
        </Card>
      </div>
    </>
  )
}

function Stat({ label, value, sub, icon }: { label: string; value: string; sub: string; icon?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5">
      <p className="flex items-center gap-1.5 text-[13px] text-navy-500">{icon}{label}</p>
      <p className="tabular mt-2 text-2xl font-semibold tracking-tight text-navy-900">{value}</p>
      <p className="mt-1 text-[11px] text-navy-400">{sub}</p>
    </div>
  )
}

function Jump({ to, title, text }: { to: string; title: string; text: string }) {
  return (
    <Link to={to} className="group rounded-xl border border-slate-200 p-4 transition hover:border-navy-900">
      <p className="flex items-center justify-between text-sm font-semibold text-navy-900">{title}<ArrowRight className="h-4 w-4 text-navy-400 transition group-hover:translate-x-0.5 group-hover:text-navy-900" /></p>
      <p className="mt-1 text-xs text-navy-500">{text}</p>
    </Link>
  )
}

const STATE_LABEL: Record<string, string> = {
  created: 'Created', awaiting_approval: 'Awaiting buyer approval', approved: 'Approved, not captured', captured: 'Captured',
  failed: 'Failed', cancelled: 'Cancelled',
}

/** What is actually verified about the PayPal connection, row by row. Nothing here is inferred from sample data. */
function IntegrationStatus({ d, orders }: { d: PayPalOverview; orders: CheckoutOrder[] }) {
  const [auth, setAuth] = useState<{ ok: boolean; message: string } | null>(null)
  const [checking, setChecking] = useState(false)
  async function check() {
    setChecking(true)
    try { setAuth(await api.paypalCheckAuth()) } catch (e) { setAuth({ ok: false, message: e instanceof ApiError ? e.message : String(e) }) } finally { setChecking(false) }
  }
  const env = d.demo ? 'demo mode (simulated)' : d.environment
  const ls = d.last_sync
  const apiRecords = d.records_by_origin.filter((r) => r.origin === 'paypal_api')
  const captured = orders.filter((o) => o.status === 'captured')
  type Row = { label: string; state: 'ok' | 'warn' | 'off' | 'info'; status: string; detail: React.ReactNode; action?: React.ReactNode }
  const rows: Row[] = [
    { label: `${d.demo ? 'Demo' : env === 'sandbox' ? 'Sandbox' : 'PayPal'} API authentication`,
      state: !d.configured ? 'off' : auth ? (auth.ok ? 'ok' : 'warn') : 'info',
      status: !d.configured ? 'Not configured' : auth ? (auth.ok ? (d.demo ? 'Simulated token' : 'Verified now') : 'Failed') : (d.demo ? 'Demo mode' : 'Not tested yet'),
      detail: !d.configured ? 'No credentials set.' : auth ? auth.message
        : d.demo ? 'No PayPal credentials: this is FINORA’s simulated PayPal. Nothing is sent to PayPal.' : 'Credentials are set. Not tested in this session.',
      action: d.configured ? <button onClick={() => void check()} disabled={checking} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1 text-[12px] font-semibold text-[#003087] hover:bg-slate-50 disabled:opacity-50">{checking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />} Test connection</button> : undefined },
    { label: 'Read-only Transaction Search',
      state: !ls ? 'off' : ls.outcome === 'ok' ? 'ok' : 'warn',
      status: !ls ? 'Not run' : ls.outcome === 'ok' ? 'Last sync OK' : ls.outcome === 'empty' ? 'No records' : 'Last sync failed',
      detail: !ls ? 'Not run yet in this database.' : `${new Date(ls.at).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })} · ${ls.environment} · `
        + (ls.outcome === 'ok' ? `${ls.records} record(s) returned` : (ls.message ?? ls.outcome)) },
    { label: `${d.demo ? 'Simulated' : 'Actual'} PayPal records in your twin`,
      state: apiRecords.length ? 'ok' : 'off',
      status: apiRecords.length ? `${apiRecords.reduce((t, r) => t + r.count, 0)} record(s)` : 'None',
      detail: apiRecords.length ? apiRecords.map((r) => `${r.count} from ${r.label}`).join(' · ') : 'None. No transaction in your twin was retrieved from PayPal.' },
    { label: 'Sample transactions (fictional)',
      state: d.sample_transactions ? 'info' : 'off',
      status: d.sample_transactions ? 'Fictional' : 'None',
      detail: d.sample_transactions ? `${d.sample_transactions} synthetic transactions in PayPal Activity format, created by FINORA. Not retrieved from PayPal.` : 'None loaded.' },
    { label: 'Orders API checkout & capture',
      state: captured.length ? 'ok' : orders.length ? 'info' : 'off',
      status: captured.length ? `${captured.length} captured` : orders.length ? 'Not captured yet' : 'None yet',
      detail: orders.length ? Object.entries(d.checkouts_by_status).map(([k, n]) => `${n} ${STATE_LABEL[k]?.toLowerCase() ?? k}`).join(' · ') : 'No checkouts yet. Payments start from a drafted proposal in Ask FINORA.' },
  ]
  const icon = (st: Row['state']) => st === 'ok' ? <CheckCircle2 className="h-4 w-4 text-brand-600" /> : st === 'warn' ? <XCircle className="h-4 w-4 text-red-600" /> : st === 'info' ? <CircleDashed className="h-4 w-4 text-amber-600" /> : <CircleDashed className="h-4 w-4 text-slate-300" />
  return (
    <Card className="mt-6">
      <CardHeader title="What’s connected, and what’s real" subtitle="Each row reports what was actually verified. Sample data is never counted as PayPal data."
        action={<ProvenanceTag />} />
      <ul className="divide-y divide-slate-100">
        {rows.map((r) => (
          <li key={r.label} className="flex flex-wrap items-start gap-3 py-3 first:pt-0">
            <span className="mt-0.5">{icon(r.state)}</span>
            <div className="min-w-0 flex-1"><p className="text-sm font-medium text-navy-900">{r.label}</p><p className="text-[12.5px] text-navy-500">{r.detail}</p></div>
            <Badge tone={r.state === 'ok' ? 'green' : r.state === 'warn' ? 'red' : r.state === 'info' ? 'amber' : 'neutral'}>{r.status}</Badge>
            {r.action}
          </li>
        ))}
      </ul>
      {orders.length > 0 && (
        <div className="mt-4 overflow-x-auto border-t border-slate-100 pt-4">
          <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-navy-400">Recent checkouts</p>
          <table className="w-full min-w-[560px] text-[12.5px]">
            <thead><tr className="text-left text-navy-400"><th className="py-1 font-medium">Item</th><th className="py-1 font-medium">State</th><th className="py-1 font-medium">Environment</th><th className="py-1 text-right font-medium">Amount</th><th className="py-1 pl-3 font-medium">PayPal ids</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {orders.slice(0, 6).map((o) => {
                const charge = o.snapshot.paypal_charge
                const cleared = (o.snapshot as { recorded?: { cleared_from_twin?: boolean } }).recorded?.cleared_from_twin
                return (
                  <tr key={o.id}>
                    <td className="py-1.5"><Link to={`/checkout/${o.id}`} className="font-medium text-navy-900 hover:underline">{o.label}</Link></td>
                    <td className="py-1.5"><Badge tone={o.status === 'captured' ? 'green' : o.status === 'failed' ? 'red' : 'neutral'}>{STATE_LABEL[o.status] ?? o.status}</Badge>{cleared && <span className="ml-1 text-[11px] text-navy-400">· not in current twin (data reset)</span>}</td>
                    <td className="py-1.5 capitalize text-navy-600">{o.environment === 'demo' ? 'Demo (simulated)' : o.environment}</td>
                    <td className="tabular py-1.5 text-right text-navy-800">{inr(o.amount)}{charge?.rate && <span className="block text-[11px] text-navy-400">{charge.currency} {charge.amount}</span>}</td>
                    <td className="py-1.5 pl-3 font-mono text-[11px] text-navy-500">{o.paypal_order_id ?? '—'}{o.capture_id && <span className="block">capture {o.capture_id}</span>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
