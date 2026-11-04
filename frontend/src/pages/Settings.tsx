import { Bot, Database, ShieldCheck, Trash2, UploadCloud, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { DataSourceBadge } from '../components/DataSourceBadge'
import { PayPalMark } from '../components/PayPalMark'
import { Badge } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState, PageSkeleton } from '../components/ui/States'
import { useAuth } from '../context/Auth'
import { useDataStatus } from '../context/DataStatus'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { inr } from '../lib/format'

export default function Settings() {
  const s = useApi(api.settings)
  const { refresh } = useDataStatus()
  const { auth } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [buffer, setBuffer] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (s.data) { setName(s.data.user_name); setBuffer(String(s.data.assumptions.safety_buffer)) }
  }, [s.data])

  if (s.loading && !s.data) return <PageSkeleton />
  if (s.error) return <ErrorState error={s.error} onRetry={s.reload} />
  if (!s.data) return null
  const d = s.data

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true); setMsg(null)
    try { await fn(); setMsg({ ok: true, text: ok }); s.reload(); await refresh() }
    catch (e) { setMsg({ ok: false, text: e instanceof ApiError ? [e.message, ...e.details].join(' — ') : String(e) }) }
    finally { setBusy(false) }
  }
  async function clearAll() {
    if (!window.confirm('Delete all transactions and obligations? Your twin will be rebuilt from your next upload.')) return
    await run(api.clearData, 'All data cleared.')
    navigate('/get-started')
  }
  const bufferNum = Number(buffer)
  const nameValid = name.trim().length > 0 && name.trim().length <= 120

  return (
    <>
      <PageHeader eyebrow="Settings" title="Settings" description="Profile, forecast assumptions, data sources and integrations." />
      {msg && <p role="status" className={`mb-4 rounded-xl p-3 text-sm ${msg.ok ? 'bg-brand-50 text-brand-700' : 'bg-red-50 text-red-700'}`}>{msg.text}</p>}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Profile" icon={<UserRound className="h-4 w-4" />} />
          <label className="block text-xs font-medium text-navy-700" htmlFor="name">Display name</label>
          <div className="mt-1.5 flex gap-2">
            <input id="name" value={name} maxLength={120} placeholder="Your name" onChange={(e) => setName(e.target.value)}
              className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy-700" />
            <button disabled={busy || !nameValid || name.trim() === d.user_name} onClick={() => run(() => api.updateSettings({ name: name.trim() }), 'Profile name updated.')}
              className="rounded-lg bg-navy-900 px-4 text-sm font-medium text-white disabled:opacity-40">Save</button>
          </div>
          {!nameValid && name.length > 0 && <p className="mt-1 text-xs text-red-600">Name can't be blank.</p>}
          <p className="mt-2 text-xs text-navy-400">Used for greetings across FINORA. Currency: {d.currency}.</p>
        </Card>

        <Card>
          <CardHeader title="Forecast assumptions" icon={<ShieldCheck className="h-4 w-4" />} />
          <label className="block text-xs font-medium text-navy-700" htmlFor="buffer">Safety buffer (₹)</label>
          <div className="mt-1.5 flex gap-2">
            <input id="buffer" inputMode="numeric" value={buffer} onChange={(e) => setBuffer(e.target.value.replace(/[^\d]/g, ''))}
              className="tabular flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm" />
            <button disabled={busy || buffer === '' || bufferNum === d.assumptions.safety_buffer} onClick={() => run(() => api.updateSettings({ safety_buffer: bufferNum }), `Safety buffer set to ${inr(bufferNum)}.`)}
              className="rounded-lg bg-navy-900 px-4 text-sm font-medium text-white disabled:opacity-40">Save</button>
          </div>
          <p className="mt-2 text-xs text-navy-400">The minimum balance you want to keep. Used for risk flags and purchase-timing advice.</p>
          <dl className="mt-4 grid grid-cols-2 gap-2 text-[13px]">
            <dt className="text-navy-500">Forecast horizon</dt><dd className="text-right font-medium">{d.assumptions.horizon_days} days</dd>
            <dt className="text-navy-500">Averaging window</dt><dd className="text-right font-medium">{d.assumptions.lookback_days} days</dd>
            <dt className="text-navy-500">Irregular income</dt><dd className="text-right font-medium">{d.assumptions.include_irregular_income ? 'Included' : 'Excluded (conservative)'}</dd>
          </dl>
        </Card>

        <Card>
          <CardHeader title="Your data" icon={<Database className="h-4 w-4" />} action={d.data_source ? <DataSourceBadge source={d.data_source} /> : <Badge>No data</Badge>} />
          <p className="text-sm text-navy-600">{d.has_data ? 'Your twin is built from the files and syncs you provided.' : 'No data yet — add some to build your twin.'}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link to="/get-started" className="inline-flex items-center gap-1.5 rounded-lg bg-navy-900 px-3 py-2 text-sm font-medium text-white hover:bg-navy-800">
              <UploadCloud className="h-4 w-4" /> {d.has_data ? 'Add or replace data' : 'Add data'}
            </Link>
            {d.has_data && (
              <button disabled={busy} onClick={clearAll} className="inline-flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-40">
                <Trash2 className="h-4 w-4" /> Clear all data
              </button>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="PayPal" icon={<PayPalMark size="sm" />} action={<Badge tone={d.paypal.configured ? 'blue' : 'neutral'}>{d.paypal.configured ? `API · ${d.paypal.environment}` : 'Upload only'}</Badge>} />
          <p className="text-sm text-navy-600">{d.paypal.message}</p>
          <Link to="/paypal" className="mt-3 inline-block text-sm font-semibold text-[#003087] hover:underline">Open PayPal hub →</Link>
        </Card>

        <Card>
          <CardHeader title="AI assistant" icon={<Bot className="h-4 w-4" />} action={<Badge tone={d.ai_configured ? 'green' : 'neutral'}>{d.ai_configured ? 'API key set' : 'Not configured'}</Badge>} />
          <p className="text-sm text-navy-600">
            {d.ai_configured
              ? 'The assistant uses the AI model to choose calculations and phrase answers. Every rupee figure is checked against the engine.'
              : 'Without a key, the assistant uses a built-in parser for the core what-if questions. Set '}
            {!d.ai_configured && <><code className="rounded bg-slate-100 px-1">OPENAI_API_KEY</code> on the server for free-form chat.</>}
          </p>
          <Link to="/assistant" className="mt-3 inline-block text-sm font-semibold text-navy-900 hover:underline">Open assistant →</Link>
        </Card>

        <Card>
          <CardHeader title="Sign in with PayPal" icon={<PayPalMark size="sm" />}
            action={<Badge tone={auth?.authenticated ? 'green' : 'neutral'}>{auth?.authenticated ? 'Signed in' : 'Optional'}</Badge>} />
          <p className="text-sm text-navy-600">
            {auth?.authenticated
              ? `Signed in as ${auth.identity?.name || auth.identity?.email}.`
              : 'Optional, and open to any PayPal account. Every feature works without signing in.'}
          </p>
          <Link to="/signin" className="mt-3 inline-block text-sm font-semibold text-[#003087] hover:underline">{auth?.authenticated ? 'Manage sign-in →' : 'Sign in →'}</Link>
        </Card>
      </div>
    </>
  )
}
