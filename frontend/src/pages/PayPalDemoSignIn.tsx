import { Loader2, LogIn } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { DemoBanner } from '../components/DemoBanner'
import { Card } from '../components/ui/Card'
import { useDataStatus } from '../context/DataStatus'
import { ApiError, api } from '../lib/api'

/** Stand-in for PayPal's sign-in screen (Log in with PayPal), used only in PayPal demo mode. */
export default function PayPalDemoSignIn() {
  const [params] = useSearchParams()
  const { status } = useDataStatus()
  const state = params.get('state') ?? ''
  const redirectUri = params.get('redirect_uri') ?? ''
  const [name, setName] = useState(status?.user_name || '')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const valid = name.trim().length > 0 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())

  async function submit() {
    setBusy(true); setError(null)
    try {
      const { redirect } = await api.demoAuthorize({ state, redirect_uri: redirectUri, name: name.trim(), email: email.trim() })
      window.location.assign(redirect)
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); setBusy(false) }
  }

  if (!state || !redirectUri) {
    return <div className="mx-auto max-w-md py-4"><DemoBanner>Start sign-in from FINORA’s “Sign in with PayPal” button.</DemoBanner></div>
  }
  return (
    <div className="mx-auto max-w-md space-y-4 py-4">
      <DemoBanner>Enter any name and email. FINORA uses them as your signed-in PayPal identity.</DemoBanner>
      <Card>
        <h1 className="text-lg font-semibold text-navy-900">Sign in (demo)</h1>
        <p className="mt-1 text-sm text-navy-500">FINORA is asking for your name and email (scopes: openid profile email).</p>
        <form onSubmit={(e) => { e.preventDefault(); if (valid) void submit() }} className="mt-4 space-y-3">
          <label className="block text-xs font-medium text-navy-700">Name
            <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} autoComplete="name"
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy-700" />
          </label>
          <label className="block text-xs font-medium text-navy-700">Email
            <input type="email" value={email} maxLength={200} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com"
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy-700" />
          </label>
          {error && <p role="alert" className="rounded-lg bg-red-50 p-2.5 text-[13px] text-red-700">{error}</p>}
          <button type="submit" disabled={!valid || busy}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-navy-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-navy-800 disabled:opacity-40">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />} Continue to FINORA
          </button>
          <button type="button" onClick={() => window.location.assign(`${redirectUri}?error=access_denied&state=${encodeURIComponent(state)}`)}
            className="w-full rounded-xl px-4 py-2 text-sm font-medium text-navy-600 hover:bg-slate-50">Cancel</button>
        </form>
      </Card>
    </div>
  )
}
