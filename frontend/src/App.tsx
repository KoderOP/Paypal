import type React from 'react'
import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { EmptyState, ErrorState, PageSkeleton } from './components/ui/States'
import { AuthProvider } from './context/Auth'
import { DataStatusProvider, useDataStatus } from './context/DataStatus'
import { ApiError } from './lib/api'

const Overview = lazy(() => import('./pages/Overview'))
const Twin = lazy(() => import('./pages/Twin'))
const WhatIf = lazy(() => import('./pages/WhatIf'))
const Transactions = lazy(() => import('./pages/Transactions'))
const Settings = lazy(() => import('./pages/Settings'))
const GetStarted = lazy(() => import('./pages/GetStarted'))
const PayPal = lazy(() => import('./pages/PayPal'))
const SignIn = lazy(() => import('./pages/SignIn'))
const Subscriptions = lazy(() => import('./pages/Subscriptions'))
const Assistant = lazy(() => import('./pages/Assistant'))
const Checkout = lazy(() => import('./pages/Checkout'))
const CrossBorder = lazy(() => import('./pages/CrossBorder'))
const StressTest = lazy(() => import('./pages/StressTest'))
const PayPalDemoCheckout = lazy(() => import('./pages/PayPalDemoCheckout'))
const PayPalDemoSignIn = lazy(() => import('./pages/PayPalDemoSignIn'))

// Pages that work before any data exists; everything else redirects to onboarding.
const OPEN_ROUTES = ['/get-started', '/paypal', '/settings', '/signin']
const OPEN_PREFIXES = ['/checkout/', '/paypal-demo/']

// Only "has data?" gates pages. Sign-in never does: every feature works signed out.
function Gate({ children }: { children: React.ReactNode }) {
  const { status, error, refresh } = useDataStatus()
  const { pathname } = useLocation()
  if (pathname === '/signin' || pathname.startsWith('/paypal-demo/')) return <>{children}</>
  if (error && !status) return <ErrorState error={new ApiError(0, error)} onRetry={() => void refresh()} />
  if (!status) return <PageSkeleton />
  if (!status.has_data && !OPEN_ROUTES.includes(pathname) && !OPEN_PREFIXES.some((p) => pathname.startsWith(p))) {
    return <Navigate to="/get-started" replace />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <AuthProvider>
      <DataStatusProvider>
        <AppLayout>
          <Gate>
            <Suspense fallback={<PageSkeleton />}>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/signin" element={<SignIn />} />
                <Route path="/get-started" element={<GetStarted />} />
                <Route path="/paypal" element={<PayPal />} />
                <Route path="/twin" element={<Twin />} />
                <Route path="/simulator" element={<WhatIf />} />
                <Route path="/compare" element={<Navigate to="/simulator?view=compare" replace />} />
                <Route path="/crossborder" element={<CrossBorder />} />
                <Route path="/checkout/:id" element={<Checkout />} />
                <Route path="/subscriptions" element={<Subscriptions />} />
                <Route path="/assistant" element={<Assistant />} />
                <Route path="/stress" element={<StressTest />} />
                <Route path="/paypal-demo/checkout" element={<PayPalDemoCheckout />} />
                <Route path="/paypal-demo/signin/authorize" element={<PayPalDemoSignIn />} />
                <Route path="/transactions" element={<Transactions />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="*" element={<EmptyState title="Page not found" />} />
              </Routes>
            </Suspense>
          </Gate>
        </AppLayout>
      </DataStatusProvider>
    </AuthProvider>
  )
}
