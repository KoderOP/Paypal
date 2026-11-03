import { Database } from 'lucide-react'
import { Badge } from './ui/Badge'

const labels: Record<string, string> = { paypal_activity: 'PayPal activity', paypal_api: 'PayPal (live sync)', bank_statement: 'Bank statement', transactions: 'Transaction file', mixed: 'Multiple sources' }

export function DataSourceBadge({ source }: { source: string }) {
  return <Badge tone={source.startsWith('paypal') ? 'blue' : 'neutral'} icon={<Database className="h-3 w-3" />}>{labels[source] ?? source}</Badge>
}
