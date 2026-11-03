import { CheckCircle2, AlertTriangle, XOctagon } from 'lucide-react'

// Status always ships with icon + label, never colour alone.
const map = {
  good: { label: 'Healthy', color: 'var(--status-good)', Icon: CheckCircle2 },
  watch: { label: 'Watch', color: 'var(--status-warning)', Icon: AlertTriangle },
  risk: { label: 'At risk', color: 'var(--status-critical)', Icon: XOctagon },
} as const

export function StatusPill({ status }: { status: keyof typeof map }) {
  const { label, color, Icon } = map[status]
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-navy-700">
      <Icon className="h-3.5 w-3.5" style={{ color }} aria-hidden />
      {label}
    </span>
  )
}
