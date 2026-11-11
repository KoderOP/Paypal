import type React from 'react'
import { ArrowDownLeft, ArrowRight, ArrowUpRight, Brain, FlaskConical, KeyRound, Lock, RefreshCw, ShieldCheck, Upload } from 'lucide-react'
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

const FLOW = [
  { icon: KeyRound, title: 'Connect', text: 'OAuth 2.0 client credentials. Secrets stay on the server; the browser never sees them.' },
  { icon: RefreshCw, title: 'Sync', text: 'Read-only Transaction Search API, fetched in 31-day windows — or an uploaded Activity report.' },
  { icon: Brain, title: 'Learn', text: 'Transactions are normalised and the twin detects income, recurring payments and habits.' },
  { icon: FlaskConical, title: 'Simulate', text: 'A deterministic engine projects 90 days and compares paying now, waiting or PayPal Pay Later.' },
  { icon: ShieldCheck, title: 'Act', text: 'Pay with PayPal (Orders API) or cancel a subscription (Subscriptions API), each only after you confirm.' },
]

export default function PayPal() {
  const pp = useApi(api.paypal)
  const { refresh } = useDataStatus()
  const navigate = useNavigate()
  const [syncing, setSyncing] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  if (pp.loading && !pp.data) return <PageSkeleton />
  if (pp.error) return <ErrorState error={pp.error} onRetry={pp.reload} />
  if (!pp.data) return null
  const d = pp.data

  async function sync() {
    setSyncing(true); setMsg(null)
    try {
      const r = await api.paypalSync(180, false)
      setMsg({ ok: true, text: `Synced ${r.imported} new PayPal transactions (${r.skipped_duplicates} already up to date).` })
      pp.reload(); await refresh()
    } catch (e) { setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) }) } finally { setSyncing(false) }
  }

  return (
    <>
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#001c64] via-[#003087] to-[#0b4fb3] p-6 text-white shadow-xl shadow-[#003087]/20 sm:p-8">
        <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/5" aria-hidden />
        <div className="absolute -bottom-28 right-40 h-56 w-56 rounded-full bg-sky-300/10" aria-hidden />
        <div className="relative flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-2xl">
            <div className="flex items-center gap-3">
              <span className="rounded-2xl bg-white/10 p-1"><PayPalMark size="lg" /></span>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-sky-200">PayPal × FINORA</p>
                <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Your PayPal activity, turned into foresight</h1>
              </div>
            </div>
            <p className="mt-4 text-[15px] leading-relaxed text-sky-100/90">
              FINORA builds a financial digital twin from your PayPal transactions — then simulates purchases, salary delays and shocks so you know the impact before money moves.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-medium ${d.demo ? 'bg-amber-300 text-amber-950' : 'bg-white/10'}`}>
                {d.demo ? 'Demo mode · simulated PayPal' : d.configured ? `REST API connected · ${d.environment}` : 'REST API not configured'}
              </span>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium">{d.linked ? `${d.transaction_count} PayPal transactions in your twin` : 'No PayPal data yet'}</span>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium">Read-only sync · confirmed checkout</span>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            {d.configured && (
              <button disabled={syncing} onClick={sync} className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-[#003087] hover:bg-sky-50 disabled:opacity-60">
                <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} /> {syncing ? 'Syncing…' : d.demo ? 'Sync now (demo)' : 'Sync now'}
              </button>
            )}
            <button onClick={() => navigate('/get-started?method=paypal_activity')} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/30 px-4 py-2.5 text-sm font-semibold text-white hover:bg-white/10">
              <Upload className="h-4 w-4" /> {d.linked ? 'Upload new Activity report' : 'Connect PayPal data'}
            </button>
          </div>
        </div>
      </div>

      {msg && <p role="status" className={`mt-4 rounded-xl p-3 text-sm ${msg.ok ? 'bg-brand-50 text-brand-700' : 'bg-red-50 text-red-700'}`}>{msg.text}</p>}

      {d.linked ? (
        <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 xl:col-span-2">
            <Stat label="PayPal transactions" value={String(d.transaction_count)} sub={d.first_date && d.last_date ? `${fmtDate(d.first_date)} – ${fmtDate(d.last_date)}` : ''} />
            <Stat label="Money in via PayPal" value={inr(d.inflow)} sub="received" icon={<ArrowDownLeft className="h-4 w-4 text-brand-600" />} />
            <Stat label="Money out via PayPal" value={inr(d.outflow)} sub="paid" icon={<ArrowUpRight className="h-4 w-4 text-navy-400" />} />
            <Card className="sm:col-span-3">
              <CardHeader title="What your twin learned from PayPal" subtitle="Every module runs on this data" />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Jump to="/" title="Overview" text="Balance, cash flow & 90-day projection" />
                <Jump to="/twin" title="My Financial Twin" text="Income cycles, recurring payments, habits" />
                <Jump to="/simulator" title="What-if Simulator" text="Simulate a ₹75,000 laptop purchase" />
              </div>
            </Card>
          </div>
          <Card>
            <CardHeader title="Top PayPal payees" subtitle="By total paid" />
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
              <p className="font-semibold text-navy-900">Connect your PayPal data to build your twin</p>
              <p className="mt-1 text-sm text-navy-500">Upload a PayPal Activity report (or use the demo file) — it takes under a minute.</p>
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
            <li className="flex gap-2"><Lock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-400" />Syncing is read-only. Money moves only through checkout, after two explicit confirmations: once before PayPal and again after you approve.</li>
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
              <li>• <b>Sync now</b> imports the demo PayPal history (duplicates of the demo file are skipped).</li>
              <li>• <b>Pay with PayPal / Pay Later</b> in the simulator opens a demo approval page, then captures for real in your twin.</li>
              <li>• <b>Subscriptions</b> can link demo PayPal subscriptions and cancel, suspend or re-activate them.</li>
              <li>• <b>Sign in with PayPal</b> uses a demo sign-in page with any name and email.</li>
            </ul>
          )}
          {(!d.configured || d.demo) && (
            <pre className="mt-3 overflow-x-auto rounded-lg bg-navy-900 p-3 text-[11px] text-slate-200">{`# backend/.env
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
