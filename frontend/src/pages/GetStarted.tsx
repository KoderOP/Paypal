import { ArrowRight, Building2, CheckCircle2, FileSpreadsheet, RefreshCw, ShieldCheck, Upload } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AnalysisRun } from '../components/AnalysisRun'
import { DataImporter, FORMAT_INFO } from '../components/DataImporter'
import { PayPalMark } from '../components/PayPalMark'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { useDataStatus } from '../context/DataStatus'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import type { FileFormat, ImportResult } from '../lib/types'

type Method = 'paypal_api' | FileFormat

export default function GetStarted() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { status, refresh } = useDataStatus()
  const paypal = useApi(api.paypal)
  const [method, setMethod] = useState<Method>((params.get('method') as Method) || 'paypal_activity')
  const [name, setName] = useState('')
  const [nameTouched, setNameTouched] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [syncDays, setSyncDays] = useState(180)
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState<ApiError | null>(null)

  useEffect(() => { if (status && !nameTouched) setName(status.user_name) }, [status, nameTouched])
  const hasData = !!status?.has_data

  async function saveName() {
    const n = name.trim()
    if (n && n !== status?.user_name) await api.updateSettings({ name: n })
  }

  async function syncPayPal() {
    setSyncing(true); setSyncError(null)
    try { await saveName(); setResult(await api.paypalSync(syncDays, hasData)); void refresh() }
    catch (e) { setSyncError(e instanceof ApiError ? e : new ApiError(0, String(e))) }
    finally { setSyncing(false) }
  }

  async function finish(to: string) {
    await refresh()
    navigate(to)
  }

  if (result) return <AnalysisRun result={result} onDone={() => finish('/')} onSimulate={() => finish('/simulator')} />

  const apiReady = !!paypal.data?.configured

  return (
    <div className="mx-auto max-w-4xl">
      <div className="text-center">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-600">{hasData ? 'Add or replace data' : 'Welcome to FINORA'}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-navy-900 sm:text-4xl">Build your financial digital twin</h1>
        <p className="mx-auto mt-3 max-w-2xl text-[15px] text-navy-500">
          Bring in your transactions — FINORA learns your income cycles, recurring bills and spending, then projects your next 90 days so you can simulate decisions before you make them.
        </p>
      </div>

      <Card className="mt-8">
        <label htmlFor="profile-name" className="text-sm font-semibold text-navy-900">What should we call you?</label>
        <input id="profile-name" value={name} maxLength={120} placeholder="Your name"
          onChange={(e) => { setName(e.target.value); setNameTouched(true) }} onBlur={() => void saveName().then(refresh)}
          className="mt-2 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-navy-700 focus:ring-2 focus:ring-navy-900/10" />
      </Card>

      <h2 className="mt-8 text-sm font-semibold text-navy-900">Choose how to bring in your data</h2>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="md:col-span-3">
          <button onClick={() => setMethod('paypal_activity')} aria-pressed={method === 'paypal_activity' || method === 'paypal_api'}
            className={`w-full rounded-2xl border-2 p-5 text-left transition ${method === 'paypal_activity' || method === 'paypal_api' ? 'border-[#003087] bg-[#003087]/[0.03]' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
            <div className="flex flex-wrap items-start gap-4">
              <PayPalMark size="lg" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-base font-semibold text-navy-900">PayPal</p>
                  <Badge tone="blue">Recommended</Badge>
                  <Badge tone={paypal.data?.demo ? 'amber' : apiReady ? 'green' : 'neutral'}>
                    {paypal.data?.demo ? 'Demo mode · simulated API' : apiReady ? `API connected · ${paypal.data?.environment}` : 'Activity report upload'}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-navy-500">Sync your PayPal transactions through the read-only Transaction Search API, or upload a PayPal Activity report. PayPal is FINORA's primary data source.</p>
              </div>
            </div>
          </button>
        </div>
        <MethodCard active={method === 'bank_statement'} onClick={() => setMethod('bank_statement')} icon={<Building2 className="h-5 w-5" />}
          title="Bank statement" text="CSV statement from your bank's net banking." />
        <MethodCard active={method === 'transactions'} onClick={() => setMethod('transactions')} icon={<FileSpreadsheet className="h-5 w-5" />}
          title="Transaction file" text="Any CSV list of transactions, e.g. from a budgeting app." />
        <div className="flex items-start gap-3 rounded-2xl border border-dashed border-slate-200 p-4 text-navy-400">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
          <p className="text-xs leading-relaxed">Files are processed on your FINORA server only. Balances are always rebuilt from your transactions — nothing is estimated by AI.</p>
        </div>
      </div>

      <Card className="mt-6">
        {(method === 'paypal_activity' || method === 'paypal_api') && (
          <div className="mb-5 flex flex-wrap gap-2" role="tablist" aria-label="PayPal import method">
            <Tab active={method === 'paypal_activity'} onClick={() => setMethod('paypal_activity')} icon={<Upload className="h-3.5 w-3.5" />}>Upload Activity report</Tab>
            <Tab active={method === 'paypal_api'} onClick={() => setMethod('paypal_api')} icon={<RefreshCw className="h-3.5 w-3.5" />}>Sync via PayPal API</Tab>
          </div>
        )}
        {method === 'paypal_api' ? (
          <div>
            {apiReady ? (
              <>
                <p className="text-sm text-navy-700">{paypal.data?.message}</p>
                <label className="mt-4 block text-xs font-medium text-navy-700">History to import
                  <select value={syncDays} onChange={(e) => setSyncDays(Number(e.target.value))} className="mt-1 block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm">
                    <option value={90}>Last 3 months</option><option value={180}>Last 6 months</option><option value={365}>Last 12 months</option>
                  </select>
                </label>
                {syncError && <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-xs text-red-700">{syncError.message}</p>}
                <button disabled={syncing} onClick={syncPayPal} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#003087] py-3 text-sm font-semibold text-white hover:bg-[#002366] disabled:opacity-50">
                  <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} /> {syncing ? 'Syncing with PayPal…' : paypal.data?.demo ? 'Sync demo PayPal & analyse' : 'Sync & analyse'}
                </button>
                <p className="mt-2 text-[11px] text-navy-400">
                  {paypal.data?.demo ? 'Demo mode: imports synthetic PayPal history through the simulated Transaction Search API. ' : ''}
                  Read-only access. FINORA never moves money without your explicit confirmation.
                </p>
              </>
            ) : (
              <div className="rounded-xl bg-slate-50 p-4 text-sm text-navy-600">
                <p className="font-medium text-navy-900">API sync isn't configured on this server yet</p>
                <p className="mt-1 text-[13px]">{paypal.data?.message ?? 'Checking PayPal status…'}</p>
                <button onClick={() => setMethod('paypal_activity')} className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#003087] hover:underline">
                  Upload an Activity report instead <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="mb-4 flex items-center gap-2">
              {method === 'paypal_activity' ? <PayPalMark size="sm" /> : <CheckCircle2 className="h-4 w-4 text-brand-600" />}
              <p className="text-sm font-semibold text-navy-900">{FORMAT_INFO[method].title}</p>
            </div>
            <DataImporter key={method} format={method} hasExistingData={hasData} beforeImport={saveName} onImported={(r) => { setResult(r); void refresh() }} />
          </>
        )}
      </Card>
    </div>
  )
}

function MethodCard({ active, onClick, icon, title, text }: { active: boolean; onClick: () => void; icon: ReactNode; title: string; text: string }) {
  return (
    <button onClick={onClick} aria-pressed={active}
      className={`rounded-2xl border-2 p-4 text-left transition ${active ? 'border-navy-900 bg-white' : 'border-slate-200 bg-white hover:border-slate-300'}`}>
      <span className={active ? 'text-navy-900' : 'text-navy-400'}>{icon}</span>
      <p className="mt-2 text-sm font-semibold text-navy-900">{title}</p>
      <p className="mt-0.5 text-xs text-navy-500">{text}</p>
    </button>
  )
}

function Tab({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: ReactNode; children: ReactNode }) {
  return (
    <button role="tab" aria-selected={active} onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${active ? 'border-[#003087] bg-[#003087] text-white' : 'border-slate-200 text-navy-700 hover:bg-slate-50'}`}>
      {icon}{children}
    </button>
  )
}
