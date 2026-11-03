import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ApiError } from '../../lib/api'

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton rounded-lg ${className}`} />
}

export function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-9 w-64" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)}
      </div>
      <Skeleton className="h-96" />
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  const details = 'details' in error ? error.details : []
  return (
    <div role="alert" className="flex flex-col items-center rounded-2xl border border-red-200 bg-red-50/50 px-6 py-10 text-center">
      <AlertTriangle className="h-8 w-8 text-red-500" />
      <p className="mt-3 font-medium text-navy-900">Something went wrong</p>
      <p className="mt-1 max-w-md text-sm text-navy-500">{error.message}</p>
      {details.length > 0 && (
        <ul className="mt-2 max-w-md text-left text-xs text-red-700">
          {details.slice(0, 6).map((d) => <li key={d}>• {d}</li>)}
        </ul>
      )}
      {onRetry && (
        <button onClick={onRetry} className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-navy-800 hover:bg-slate-50">
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, message, action }: { title: string; message?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-10 text-center">
      <div className="rounded-full bg-slate-100 p-3"><Inbox className="h-5 w-5 text-navy-400" /></div>
      <p className="mt-3 text-sm font-medium text-navy-900">{title}</p>
      {message && <p className="mt-1 max-w-sm text-sm text-navy-500">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
