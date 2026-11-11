import {
  ArrowLeftRight, Bot, FlaskConical, Globe2, LayoutDashboard, LogIn, LogOut, Menu, Microscope, Repeat, Settings, ShieldAlert,
  Sparkles, UploadCloud, UserRound, Wallet, X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/Auth'
import { useDataStatus } from '../../context/DataStatus'
import { SampleDataBanner } from '../Provenance'

interface NavItem { to: string; label: string; icon: typeof Bot; highlight?: boolean; paypal?: boolean }
// One journey: ask → decide → pay with PayPal. Everything else supports that loop.
const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  { title: 'Decide', items: [
    { to: '/assistant', label: 'Ask FINORA', icon: Bot, highlight: true },
    { to: '/simulator', label: 'What-if Simulator', icon: FlaskConical },
    { to: '/stress', label: 'Stress Test', icon: ShieldAlert },
  ] },
  { title: 'PayPal', items: [
    { to: '/paypal', label: 'PayPal Hub', icon: Wallet, paypal: true },
    { to: '/subscriptions', label: 'Subscriptions', icon: Repeat },
    { to: '/crossborder', label: 'Cross-border income', icon: Globe2 },
  ] },
  { title: 'Understand', items: [
    { to: '/', label: 'Overview', icon: LayoutDashboard },
    { to: '/twin', label: 'My Financial Twin', icon: UserRound },
    { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  ] },
  { title: 'System', items: [
    { to: '/evals', label: 'Evaluation', icon: Microscope },
    { to: '/settings', label: 'Settings', icon: Settings },
  ] },
]
function Logo() {
  return (
    <Link to="/welcome" className="flex items-center gap-2.5 px-2" aria-label="FINORA home">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden>
        <rect width="32" height="32" rx="9" fill="#0b1b3a" />
        <path d="M8 21l5-6 4 3 7-9" fill="none" stroke="#34d399" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div>
        <p className="text-[15px] font-bold tracking-[0.08em] text-navy-900">FINORA</p>
        <p className="-mt-0.5 text-[10px] font-medium text-navy-400">Simulate before you pay</p>
      </div>
    </Link>
  )
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="mt-6 space-y-4 overflow-y-auto" aria-label="Main">
      {NAV_GROUPS.map((g) => (
        <div key={g.title}>
          <p className="px-3 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.14em] text-navy-400">{g.title}</p>
          <div className="space-y-0.5">
            {g.items.map(({ to, label, icon: Icon, highlight, paypal }) => (
              <NavLink key={to} to={to} end={to === '/'} onClick={onNavigate}
                className={({ isActive }) =>
                  `group flex items-center gap-3 rounded-xl px-3 py-[7px] text-[13.5px] font-medium transition ${
                    isActive ? 'bg-navy-900 text-white shadow-sm' : 'text-navy-700 hover:bg-slate-100'}`}>
                {({ isActive }) => (
                  <>
                    <Icon className={`h-4 w-4 ${isActive ? (paypal ? 'text-sky-300' : 'text-brand-500') : paypal ? 'text-[#003087]' : 'text-navy-400 group-hover:text-navy-700'}`} />
                    <span className="flex-1">{label}</span>
                    {highlight && !isActive && <Sparkles className="h-3.5 w-3.5 text-brand-500" />}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  )
}

function DemoModeNote({ onNavigate }: { onNavigate?: () => void }) {
  const { auth } = useAuth()
  if (!auth?.demo) return null
  return (
    <Link to="/paypal" onClick={onNavigate} title="No PayPal credentials are set, so FINORA uses its built-in PayPal simulation."
      className="mt-3 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] font-medium text-amber-900 hover:bg-amber-100">
      <FlaskConical className="h-3.5 w-3.5 shrink-0" /> PayPal demo mode · no real money
    </Link>
  )
}

function Account({ onNavigate }: { onNavigate?: () => void }) {
  const { auth, signOut } = useAuth()
  if (!auth) return null
  if (auth.authenticated && auth.identity) {
    const initials = (auth.identity.name || auth.identity.email || '?').split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
    return (
      <div className="mt-3 flex items-center gap-2.5 rounded-xl border border-slate-200 px-3 py-2">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#003087] text-xs font-semibold text-white" aria-hidden>{initials}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-navy-900">{auth.identity.name || 'PayPal user'}</p>
          <p className="truncate text-[11px] text-navy-400">{auth.identity.email ?? 'Signed in with PayPal'}</p>
        </div>
        <button onClick={() => void signOut()} aria-label="Sign out" title="Sign out" className="rounded-lg p-1.5 text-navy-400 hover:bg-slate-100 hover:text-navy-900">
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    )
  }
  return (
    <Link to="/signin" onClick={onNavigate} className="mt-3 flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-[13px] font-semibold text-[#003087] hover:bg-slate-50">
      <LogIn className="h-4 w-4" /> Sign in with PayPal
    </Link>
  )
}

function DataCta({ onNavigate }: { onNavigate?: () => void }) {
  const { status } = useDataStatus()
  return (
    <div className="rounded-xl bg-gradient-to-br from-navy-900 to-navy-800 p-4 text-white">
      <p className="text-xs font-semibold text-brand-500">
        {!status?.has_data ? 'No data yet'
          : status.sample_count === status.transaction_count ? `${status.sample_count} sample transactions (fictional)`
          : status.sample_count ? `${status.transaction_count} transactions · ${status.sample_count} sample`
          : `${status.transaction_count} transactions in your twin`}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-slate-300">
        {status?.sample_count ? 'Replace the sample with your own PayPal data or statement.' : 'Connect PayPal or upload a statement to keep your twin current.'}
      </p>
      <Link to="/get-started" onClick={onNavigate} className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-2.5 py-1.5 text-xs font-semibold hover:bg-white/20">
        <UploadCloud className="h-3.5 w-3.5" /> {status?.has_data ? 'Add or replace data' : 'Add your data'}
      </Link>
    </div>
  )
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  if (pathname === '/welcome') return <>{children}</>  // the landing page is full-bleed
  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-[272px] flex-col border-r border-slate-200/80 bg-white px-4 py-6 lg:flex">
        <Logo />
        <Nav />
        <div className="mt-auto pt-4" />
        <DataCta />
        <DemoModeNote />
        <Account />
      </aside>

      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
        <Logo />
        <button onClick={() => setOpen(true)} aria-label="Open menu" className="rounded-lg p-2 hover:bg-slate-100"><Menu className="h-5 w-5" /></button>
      </div>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy-950/30" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 bg-white px-4 py-6 shadow-xl">
            <div className="flex items-center justify-between">
              <Logo />
              <button onClick={() => setOpen(false)} aria-label="Close menu" className="rounded-lg p-2 hover:bg-slate-100"><X className="h-5 w-5" /></button>
            </div>
            <Nav onNavigate={() => setOpen(false)} />
            <div className="mt-6"><DataCta onNavigate={() => setOpen(false)} /><DemoModeNote onNavigate={() => setOpen(false)} /><Account onNavigate={() => setOpen(false)} /></div>
          </div>
        </div>
      )}

      <div className="lg:ml-[272px]"><SampleDataBanner /></div>
      <main key={pathname} className="animate-fade-up px-4 py-6 sm:px-6 lg:ml-[272px] lg:px-10 lg:py-9">
        <div className="mx-auto max-w-[1280px]">{children}</div>
      </main>
    </div>
  )
}
