import { FlaskConical } from 'lucide-react'
import type { ReactNode } from 'react'

/** Shown on every screen of the built-in PayPal demo so it can never be mistaken for the real thing. */
export function DemoBanner({ children }: { children?: ReactNode }) {
  return (
    <div role="note" className="flex items-start gap-2.5 rounded-xl border border-amber-300 bg-amber-50 px-3.5 py-2.5 text-[13px] text-amber-900">
      <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <p>
        <b>PayPal demo mode.</b> This is FINORA’s built-in simulation, not PayPal. No real money moves and nothing is sent to PayPal.
        {children ? <> {children}</> : null}
      </p>
    </div>
  )
}
