import { CheckCircle2, Download, FileSpreadsheet, FlaskConical, UploadCloud, X } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { inr } from '../lib/format'
import type { DemoFile, FileFormat, ImportResult } from '../lib/types'

export const FORMAT_INFO: Record<FileFormat, { title: string; hint: string; columns: string }> = {
  paypal_activity: {
    title: 'PayPal Activity report',
    hint: 'In PayPal: Activity → Statements → Activity report → Download CSV (Completed payments).',
    columns: 'Date, Name, Type, Status, Currency, Net (or Gross), Transaction ID, Balance',
  },
  bank_statement: {
    title: 'Bank statement',
    hint: 'Download your account statement as CSV from net banking. Opening balance is read from the balance column.',
    columns: 'Date, Narration, Withdrawal Amt., Deposit Amt., Closing Balance',
  },
  transactions: {
    title: 'Transaction file',
    hint: 'Any list of transactions — e.g. a budgeting-app export. Credits positive, debits negative.',
    columns: 'date, description, amount [, category, merchant, balance]',
  },
}

interface Props {
  format: FileFormat
  hasExistingData: boolean
  onImported: (r: ImportResult) => void
  beforeImport?: () => Promise<void>
}

export function DataImporter({ format, hasExistingData, onImported, beforeImport }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [demo, setDemo] = useState<DemoFile | null>(null)
  const [opening, setOpening] = useState('')
  const [replace, setReplace] = useState(true)
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const demos = useApi(api.demoFiles)
  const demoFiles = demos.data?.filter((d) => d.format === format) ?? []
  const info = FORMAT_INFO[format]

  function pick(f: File | null, fromDemo: DemoFile | null = null) {
    setError(null)
    if (f && !/\.csv$/i.test(f.name) && f.type !== 'text/csv') {
      setError(new ApiError(0, 'Please choose a .csv file'))
      return
    }
    setFile(f)
    setDemo(fromDemo)
    if (fromDemo?.suggested_opening_balance != null) setOpening(String(fromDemo.suggested_opening_balance))
  }

  async function chooseDemo(demoFile: DemoFile) {
    try { pick(await api.demoFile(demoFile), demoFile) } catch (e) { setError(e instanceof ApiError ? e : new ApiError(0, String(e))) }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files?.[0] ?? null)
  }

  async function submit() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await beforeImport?.()
      onImported(await api.importFile(file, format, format === 'transactions' ? opening : '', hasExistingData && replace))
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-2xl border-2 border-dashed p-6 text-center transition ${dragging ? 'border-navy-700 bg-slate-50' : 'border-slate-200 bg-white'}`}
      >
        {file ? (
          <div className="flex items-center justify-between gap-3 text-left">
            <div className="flex min-w-0 items-center gap-3">
              <FileSpreadsheet className="h-8 w-8 shrink-0 text-brand-600" />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-navy-900">{file.name}</p>
                <p className="text-xs text-navy-400">
                  {(file.size / 1024).toFixed(1)} KB{demo && <> · <span className="font-medium text-amber-700">demo file · synthetic data</span></>}
                </p>
              </div>
            </div>
            <button onClick={() => pick(null)} aria-label="Remove file" className="rounded-lg p-1.5 text-navy-400 hover:bg-slate-100"><X className="h-4 w-4" /></button>
          </div>
        ) : (
          <>
            <UploadCloud className="mx-auto h-8 w-8 text-navy-400" />
            <p className="mt-2 text-sm font-medium text-navy-900">Drop your {info.title} here</p>
            <p className="mt-0.5 text-xs text-navy-400">CSV, up to 5 MB</p>
            <button onClick={() => input.current?.click()} className="mt-3 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-navy-800 hover:bg-slate-50">
              Browse files
            </button>
            <input ref={input} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => pick(e.target.files?.[0] ?? null)} aria-label="Choose CSV file" />
          </>
        )}
      </div>

      {demoFiles.map((demoFile, i) => (
        <div key={demoFile.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50/60 p-3.5">
          <div className="flex items-start gap-2.5">
            <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
            <div>
              <p className="text-[13px] font-medium text-navy-900">{i === 0 ? 'No file handy? Use the demo file' : demoFile.title}</p>
              <p className="text-xs text-navy-500">{demoFile.description} <b>Synthetic data — not real transactions.</b></p>
            </div>
          </div>
          <div className="flex gap-2">
            <a href={api.demoFileUrl(demoFile.id)} download={demoFile.filename} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-navy-700 hover:bg-slate-50">
              <Download className="h-3.5 w-3.5" /> Download
            </a>
            <button onClick={() => void chooseDemo(demoFile)} className="inline-flex items-center gap-1 rounded-lg bg-navy-900 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-navy-800">
              {demo?.id === demoFile.id ? <CheckCircle2 className="h-3.5 w-3.5 text-brand-500" /> : null} {demo?.id === demoFile.id ? 'Selected' : 'Use demo file'}
            </button>
          </div>
        </div>
      ))}

      {format === 'transactions' && (
        <label className="block text-xs font-medium text-navy-700">
          Balance before the first transaction (₹)
          <input inputMode="decimal" value={opening} placeholder="0" onChange={(e) => setOpening(e.target.value.replace(/[^\d.-]/g, ''))}
            className="tabular mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-normal" />
          <span className="mt-1 block font-normal text-navy-400">{opening ? `Starts from ${inr(Number(opening) || 0)}` : 'Skip if your file has a balance column.'}</span>
        </label>
      )}

      {hasExistingData && (
        <label className="flex items-center gap-2 text-xs text-navy-700">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
          Replace my existing data (recommended — avoids counting the same money twice)
        </label>
      )}

      <p className="text-[11px] text-navy-400"><b className="text-navy-600">Expected columns:</b> {info.columns}. {info.hint}</p>

      {error && (
        <div role="alert" className="rounded-xl bg-red-50 p-3 text-xs text-red-700">
          <p className="font-medium">{error.message}</p>
          {error.details.slice(0, 5).map((d) => <p key={d}>• {d}</p>)}
        </div>
      )}

      <button disabled={!file || busy} onClick={submit}
        className="w-full rounded-xl bg-navy-900 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-navy-800 disabled:opacity-40">
        {busy ? 'Uploading…' : 'Upload & analyse'}
      </button>
    </div>
  )
}
