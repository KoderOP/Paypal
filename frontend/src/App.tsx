import type React from 'react'
import { Bot, ShieldAlert } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { EmptyState, ErrorState, PageSkeleton } from './components/ui/States'
import { DataStatusProvider, useDataStatus } from './context/DataStatus'
import { ApiError } from './lib/api'
import { ComingSoon } from './pages/ComingSoon'

const Overview = lazy(() => import('./pages/Overview'))
const Twin = lazy(() => import('./pages/Twin'))
const Simulator = lazy(() => import('./pages/Simulator'))
const Transactions = lazy(() => import('./pages/Transactions'))
const Settings = lazy(() => import('./pages/Settings'))
const GetStarted = lazy(() => import('./pages/GetStarted'))
const PayPal = lazy(() => import('./pages/PayPal'))

// Pages that work before any data exists; everything else redirects to onboarding.
const OPEN_ROUTES = ['/get-started', '/paypal', '/settings', '/assistant', '/stress']

function Gate({ children }: { children: React.ReactNode }) {
  const { status, error, refresh } = useDataStatus()
  const { pathname } = useLocation()
  if (error && !status) return <ErrorState error={new ApiError(0, error)} onRetry={() => void refresh()} />
  if (!status) return <PageSkeleton />
  if (!status.has_data && !OPEN_ROUTES.includes(pathname)) return <Navigate to="/get-started" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <DataStatusProvider>
      <AppLayout>
        <Gate>
          <Suspense fallback={<PageSkeleton />}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/get-started" element={<GetStarted />} />
              <Route path="/paypal" element={<PayPal />} />
              <Route path="/twin" element={<Twin />} />
              <Route path="/simulator" element={<Simulator />} />
              <Route path="/assistant" element={
                <ComingSoon eyebrow="AI Financial Assistant" title="Ask your twin anything" icon={<Bot className="h-6 w-6" />}
                  description="A conversational layer on top of the deterministic engine. The LLM chooses which calculation to run; it never computes figures itself."
                  points={['“Can I afford a ₹75,000 laptop?” → calls the purchase simulator', 'Tool calling over twin, forecast and simulation APIs', 'Answers cite the exact computed figures and assumptions', 'Model configurable via OPENAI_MODEL; key stays on the server']} />
              } />
              <Route path="/stress" element={
                <ComingSoon eyebrow="Stress Testing" title="How resilient are your finances?" icon={<ShieldAlert className="h-6 w-6" />}
                  description="Shock your financial twin with adverse events and measure liquidity risk — clearly labelled as estimates."
                  points={['Income disruption and salary delays', 'Medical / emergency expenses', 'Rising living costs (+10–30%)', 'Emergency runway, liquidity risk, savings trajectory and deficit indicators']} />
              } />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<EmptyState title="Page not found" />} />
            </Routes>
          </Suspense>
        </Gate>
      </AppLayout>
    </DataStatusProvider>
  )
}
