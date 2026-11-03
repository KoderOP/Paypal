import { ArrowRight, CheckCircle2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'

export function ComingSoon({ eyebrow, title, description, points, icon }: { eyebrow: string; title: string; description: string; points: string[]; icon: ReactNode }) {
  return (
    <>
      <PageHeader eyebrow={eyebrow} title={title} description={description} actions={<Badge tone="amber">Next milestone</Badge>} />
      <Card className="max-w-3xl">
        <div className="flex items-start gap-4">
          <div className="rounded-2xl bg-navy-900 p-3 text-brand-500">{icon}</div>
          <div>
            <p className="font-semibold text-navy-900">What's coming</p>
            <ul className="mt-3 space-y-2">
              {points.map((p) => <li key={p} className="flex gap-2 text-sm text-navy-600"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />{p}</li>)}
            </ul>
            <Link to="/simulator" className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-navy-900 hover:underline">
              Try the What-if Simulator now <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </Card>
    </>
  )
}
