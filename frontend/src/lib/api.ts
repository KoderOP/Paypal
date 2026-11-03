import type {
  Dashboard, DemoFile, FileFormat, ImportResult, Obligation, ObligationCreate, PayPalOverview, PurchaseRequest,
  PurchaseSimulation, ScenarioInfo, SettingsData, StatusData, TransactionPage, TwinData,
} from './types'

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  details: string[]
  constructor(status: number, message: string, details: string[] = []) {
    super(message)
    this.status = status
    this.details = details
  }
}

function parseDetail(detail: unknown): { message: string; details: string[] } {
  if (typeof detail === 'string') return { message: detail, details: [] }
  if (Array.isArray(detail)) {
    const msgs = detail.map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`)
    return { message: 'Please check your input', details: msgs }
  }
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; errors?: string[] }
    return { message: d.message ?? 'Request failed', details: d.errors ?? [] }
  }
  return { message: 'Request failed', details: [] }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}/api${path}`, init)
  } catch {
    throw new ApiError(0, 'Cannot reach the FINORA API. Is the backend running on port 8000?')
  }
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const { message, details } = parseDetail(body?.detail)
    throw new ApiError(res.status, message, details)
  }
  return body as T
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
})

export const api = {
  dashboard: () => request<Dashboard>('/dashboard'),
  twin: () => request<TwinData>('/twin'),
  transactions: (params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
    return request<TransactionPage>(`/transactions?${qs}`)
  },
  categories: () => request<string[]>('/transactions/categories'),
  status: () => request<StatusData>('/status'),
  demoFiles: () => request<DemoFile[]>('/demo-files'),
  demoFile: async (f: DemoFile): Promise<File> => {
    const res = await fetch(`${BASE}/api/demo-files/${f.id}`)
    if (!res.ok) throw new ApiError(res.status, 'Could not load the demo file')
    return new File([await res.blob()], f.filename, { type: 'text/csv' })
  },
  demoFileUrl: (id: string) => `${BASE}/api/demo-files/${id}`,
  importFile: (file: File, format: FileFormat | 'auto', openingBalance: string, replace: boolean) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('format', format)
    fd.append('opening_balance', openingBalance)
    fd.append('replace', String(replace))
    return request<ImportResult>('/data/import', { method: 'POST', body: fd })
  },
  clearData: () => request<void>('/data', { method: 'DELETE' }),
  paypal: () => request<PayPalOverview>('/integrations/paypal'),
  paypalSync: (days: number, replace: boolean) => request<ImportResult>('/integrations/paypal/sync', json('POST', { days, replace })),
  obligations: () => request<Obligation[]>('/obligations'),
  createObligation: (o: ObligationCreate) => request<Obligation>('/obligations', json('POST', o)),
  deleteObligation: (id: number) => request<void>(`/obligations/${id}`, { method: 'DELETE' }),
  scenarios: () => request<ScenarioInfo[]>('/simulations/scenarios'),
  simulatePurchase: (body: PurchaseRequest) => request<PurchaseSimulation>('/simulations/purchase', json('POST', body)),
  settings: () => request<SettingsData>('/settings'),
  updateSettings: (patch: { name?: string; safety_buffer?: number }) => request<SettingsData>('/settings', json('PUT', patch)),
}
