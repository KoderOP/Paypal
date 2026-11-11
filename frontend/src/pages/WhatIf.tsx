import { Columns3, ShoppingBag } from 'lucide-react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '../components/ui/PageHeader'
import Compare from './Compare'
import Simulator from './Simulator'
import { ProvenanceTag } from '../components/Provenance'

type View = 'purchase' | 'compare'

const VIEWS: { value: View; label: string; icon: ReactNode; title: string; description: string }[] = [
  {
    value: 'purchase', label: 'Plan a purchase', icon: <ShoppingBag className="h-4 w-4" />,
    title: 'Simulate a decision before you make it',
    description: 'Your twin replays your income, bills, obligations and day-to-day spending, with and without the purchase. '
      + 'It finds the safest date to buy and compares paying now, waiting and PayPal Pay Later.',
  },
  {
    value: 'compare', label: 'Compare scenarios', icon: <Columns3 className="h-4 w-4" />,
    title: 'Which decision leaves you better off?',
    description: 'Put up to four what-ifs side by side on the same 90-day baseline, e.g. cancel subscriptions vs. '
      + 'delay the laptop vs. both. Save the ones you want to come back to.',
  },
]

/** One What-if Simulator tab: plan a single purchase, or compare several scenarios side by side. */
export default function WhatIf() {
  const [params, setParams] = useSearchParams()
  const view: View = params.get('view') === 'compare' ? 'compare' : 'purchase'
  const current = VIEWS.find((v) => v.value === view)!

  const header = (
    <>
      <PageHeader eyebrow="What-if Simulator" title={current.title} description={current.description} actions={<ProvenanceTag />} />
      <div role="tablist" aria-label="Simulator view" className="mb-6 inline-flex rounded-xl bg-slate-100 p-1">
        {VIEWS.map((v) => (
          <button key={v.value} role="tab" aria-selected={view === v.value} aria-controls="whatif-panel"
            onClick={() => setParams(v.value === 'purchase' ? {} : { view: v.value })}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition ${
              view === v.value ? 'bg-white text-navy-900 shadow-sm' : 'text-navy-500 hover:text-navy-800'}`}>
            {v.icon}{v.label}
          </button>
        ))}
      </div>
    </>
  )

  return (
    <div id="whatif-panel" role="tabpanel">
      {view === 'compare' ? <Compare header={header} /> : <Simulator header={header} />}
    </div>
  )
}
