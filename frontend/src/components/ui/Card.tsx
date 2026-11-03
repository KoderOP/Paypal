import type { ReactNode } from 'react'

export function Card({ children, className = '', padded = true }: { children: ReactNode; className?: string; padded?: boolean }) {
  return (
    <section className={`rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(11,27,58,0.04)] ${padded ? 'p-5 sm:p-6' : ''} ${className}`}>
      {children}
    </section>
  )
}

export function CardHeader({ title, subtitle, action, icon }: { title: string; subtitle?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-2.5">
        {icon && <div className="mt-0.5 text-navy-400">{icon}</div>}
        <div>
          <h2 className="text-[15px] font-semibold tracking-tight text-navy-900">{title}</h2>
          {subtitle && <p className="mt-0.5 text-[13px] text-navy-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}
