import { AlertTriangle, CheckCircle2, LockKeyhole, LogOut, ShieldCheck } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { PayPalMark } from '../components/PayPalMark'
import { Card } from '../components/ui/Card'
import { PageSkeleton } from '../components/ui/States'
import { useAuth } from '../context/Auth'
import { api } from '../lib/api'

const ERRORS: Record<string, string> = {
  not_configured: 'Sign in with PayPal isn’t set up on this server yet. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to backend/.env.',
  denied: 'You cancelled the PayPal sign-in.',
  state_mismatch: 'That sign-in link expired or was tampered with. Please try again.',
  paypal_error: 'PayPal couldn’t complete the sign-in. Check that “Log in with PayPal” is enabled for the app and the return URL matches.',
}

export default function SignIn() {
  const { auth, signOut } = useAuth()
  const [params] = useSearchParams()
  const error = params.get('error')
  if (!auth) return <PageSkeleton />

  return (
    <div className="mx-auto max-w-lg py-6 sm:py-12">
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#001c64] via-[#003087] to-[#0b4fb3] p-7 text-white shadow-xl shadow-[#003087]/20 sm:p-9">
        <div className="absolute -right-20 -top-20 h-60 w-60 rounded-full bg-white/5" aria-hidden />
        <div className="relative">
          <span className="inline-flex rounded-2xl bg-white/10 p-1"><PayPalMark size="lg" /></span>
          <h1 className="mt-5 text-2xl font-semibold tracking-tight sm:text-3xl">
            {auth.authenticated ? `Signed in as ${auth.identity?.name || 'PayPal user'}` : 'Sign in to FINORA'}
          </h1>
          <p className="mt-2 text-[15px] leading-relaxed text-sky-100/90">
            {auth.authenticated
              ? `You’re using FINORA as ${auth.identity?.email ?? 'your PayPal account'}.`
              : 'Optional. Every FINORA feature works without signing in. Any PayPal account can sign in to personalise the app; FINORA only sees your name and email, never your password.'}
          </p>

          {error && ERRORS[error] && (
            <p role="alert" className="mt-5 flex gap-2 rounded-xl bg-white/10 p-3 text-sm text-white">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" /> {ERRORS[error]}
            </p>
          )}

          {auth.authenticated ? (
            <button onClick={() => void signOut()} className="mt-6 inline-flex items-center gap-2 rounded-xl border border-white/30 px-4 py-2.5 text-sm font-semibold hover:bg-white/10">
              <LogOut className="h-4 w-4" /> Sign out
            </button>
          ) : auth.login_available ? (
            <>
              <a href={api.loginUrl} className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#ffc439] px-4 py-3 text-[15px] font-semibold text-[#001c64] shadow-sm transition hover:bg-[#f2b72e]">
                <LockKeyhole className="h-4 w-4" /> {auth.demo ? 'Log in with PayPal (demo)' : 'Log in with PayPal'}
              </a>
              {auth.demo && (
                <p className="mt-2 text-center text-xs text-sky-200">Demo mode: you’ll sign in on FINORA’s simulated sign-in page with any name and email.</p>
              )}
            </>
          ) : (
            <p className="mt-6 rounded-xl bg-white/10 p-3 text-sm">{ERRORS.not_configured}</p>
          )}
          {!auth.authenticated && (
            <Link to="/overview" className="mt-3 block text-center text-sm font-medium text-sky-100 hover:text-white hover:underline">
              Continue without signing in →
            </Link>
          )}
        </div>
      </div>

      <Card className="mt-6">
        <ul className="space-y-2.5 text-[13px] text-navy-600">
          <li className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />OAuth 2.0 with a signed state check. The authorization code is exchanged on the server, never in the browser.</li>
          <li className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />Scopes: <code className="rounded bg-slate-100 px-1">openid profile email</code>. Signing in grants no payment access.</li>
          <li className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />Your session is a signed HttpOnly cookie that scripts can’t read.</li>
          {auth.login_available && !auth.authenticated && (
            <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-navy-400" />
              <span>PayPal app return URL: <code className="break-all rounded bg-slate-100 px-1">{auth.callback_url}</code></span></li>
          )}
          {auth.ephemeral_sessions && (
            <li className="flex gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" style={{ color: 'var(--status-warning)' }} />
              No SESSION_SECRET is set, so sign-ins end when the backend restarts.</li>
          )}
        </ul>
      </Card>
    </div>
  )
}
