import { ChevronLeft, ChevronRight, Search, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { fmtDate, inr } from '../lib/format'
import { OriginBadge, ProvenanceTag } from '../components/Provenance'
import { useDataStatus } from '../context/DataStatus'

const PAGE_SIZE = 25

export default function Transactions() {
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [direction, setDirection] = useState('')
  const [origin, setOrigin] = useState('')
  const { status } = useDataStatus()
  const [page, setPage] = useState(1)
  useEffect(() => { const t = setTimeout(() => { setQ(search); setPage(1) }, 300); return () => clearTimeout(t) }, [search])

  const cats = useApi(api.categories)
  const txns = useApi(() => api.transactions({ search: q, category, direction, origin, page, page_size: PAGE_SIZE }), [q, category, direction, origin, page])
  const pages = txns.data ? Math.max(1, Math.ceil(txns.data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageHeader eyebrow="Transactions" title="Transaction history" description="The raw data your twin learns from. Every balance in FINORA is derived from these records, and each row shows where it came from."
        actions={<ProvenanceTag />} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card padded={false}>
          <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-4">
            <div className="flex min-w-[200px] flex-1 items-center gap-2 rounded-lg border border-slate-200 px-3">
              <Search className="h-4 w-4 text-navy-400" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search description or merchant" aria-label="Search transactions" maxLength={100} className="w-full py-2 text-sm outline-none" />
            </div>
            <select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1) }} aria-label="Category" className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
              <option value="">All categories</option>
              {cats.data?.map((c) => <option key={c}>{c}</option>)}
            </select>
            <select value={direction} onChange={(e) => { setDirection(e.target.value); setPage(1) }} aria-label="Direction" className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
              <option value="">In & out</option><option value="in">Money in</option><option value="out">Money out</option>
            </select>
            {(status?.provenance.length ?? 0) > 1 && (
              <select value={origin} onChange={(e) => { setOrigin(e.target.value); setPage(1) }} aria-label="Source" className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
                <option value="">All sources</option>
                {status?.provenance.map((p) => <option key={p.origin} value={p.origin}>{p.label} ({p.count})</option>)}
              </select>
            )}
          </div>
          {txns.error ? <div className="p-4"><ErrorState error={txns.error} onRetry={txns.reload} /></div> : !txns.data ? (
            <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-10" />)}</div>
          ) : txns.data.items.length === 0 ? <EmptyState title="No transactions match" message="Try a different search or filter." /> : (
            <div className={`overflow-x-auto ${txns.loading ? 'opacity-60' : ''}`}>
              <table className="w-full text-[13px]">
                <thead><tr className="border-b border-slate-100 text-left text-xs text-navy-400">
                  <th className="px-4 py-2.5 font-medium">Date</th><th className="px-4 py-2.5 font-medium">Description</th><th className="px-4 py-2.5 font-medium">Category</th><th className="px-4 py-2.5 font-medium">Source</th><th className="px-4 py-2.5 text-right font-medium">Amount</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {txns.data.items.map((t) => (
                    <tr key={t.id} className="hover:bg-slate-50/60">
                      <td className="whitespace-nowrap px-4 py-2.5 text-navy-500">{fmtDate(t.posted_on)}</td>
                      <td className="px-4 py-2.5"><p className="text-navy-800">{t.description}</p><p className="text-[11px] text-navy-400">{t.merchant}</p></td>
                      <td className="px-4 py-2.5"><Badge>{t.category}</Badge></td>
                      <td className="px-4 py-2.5"><OriginBadge origin={t.origin} environment={t.environment} title={t.origin_label} /></td>
                      <td className={`tabular whitespace-nowrap px-4 py-2.5 text-right font-medium ${t.amount > 0 ? 'text-brand-700' : 'text-navy-900'}`}>{t.amount > 0 ? '+' : '−'}{inr(Math.abs(t.amount), true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {txns.data && txns.data.total > 0 && (
            <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-xs text-navy-500">
              <span>{txns.data.total} transactions · page {page} of {pages}</span>
              <div className="flex gap-1">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page" className="rounded-lg border border-slate-200 p-1.5 disabled:opacity-40"><ChevronLeft className="h-4 w-4" /></button>
                <button disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page" className="rounded-lg border border-slate-200 p-1.5 disabled:opacity-40"><ChevronRight className="h-4 w-4" /></button>
              </div>
            </div>
          )}
        </Card>
        <Card className="self-start">
          <CardHeader title="Add more data" subtitle="PayPal, bank statement or transaction file" icon={<Upload className="h-4 w-4" />} />
          <p className="text-[13px] text-navy-500">Re-uploading the same file is safe — duplicates are skipped automatically.</p>
          <Link to="/get-started" className="mt-4 inline-flex w-full items-center justify-center rounded-lg bg-navy-900 py-2 text-sm font-medium text-white hover:bg-navy-800">Upload or sync</Link>
        </Card>
      </div>
    </>
  )
}

