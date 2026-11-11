import {
  CheckSquare, ExternalLink, Link2, Loader2, Pause, Play, Plus, RefreshCw, Repeat, RotateCcw, Sparkles, Square, Trash2, XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { PayPalMark } from '../components/PayPalMark'
import { Badge, ProjectedTag } from '../components/ui/Badge'
import { Card, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState, ErrorState, PageSkeleton } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { ApiError, api } from '../lib/api'
import { fmtShort, inr, signedInr } from '../lib/format'
import type { AddedSubscription, DetectedSubscription, ScenarioResult, SubscriptionInput } from '../lib/types'
import { ProvenanceTag } from '../components/Provenance'

export default function Subscriptions() {
  const ov = useApi(api.subscriptions)
  const [editing, setEditing] = useState<AddedSubscription | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [sim, setSim] = useState<ScenarioResult | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string; link?: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const active = useMemo(() => (ov.data?.detected ?? []).filter((d) => !d.cancelled), [ov.data])
  const selectedKey = selected.join('|')
  useEffect(() => {
    if (!selected.length) { setSim(null); return }
    let cancelled = false
    api.scenario([{ type: 'cancel_subscriptions', names: selected }], 'Cancel selected subscriptions')
      .then((r) => !cancelled && setSim(r)).catch(() => !cancelled && setSim(null))
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey])

  if (ov.loading && !ov.data) return <PageSkeleton />
  if (ov.error) return <ErrorState error={ov.error} onRetry={ov.reload} />
  if (!ov.data) return null
  const d = ov.data

  async function run(id: string, fn: () => Promise<unknown>, ok: string): Promise<boolean> {
    setBusy(id); setMsg(null)
    try { await fn(); setMsg({ ok: true, text: ok }); setSelected([]); ov.reload(); return true }
    catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, String(e))
      setMsg({ ok: false, text: [err.message, ...err.details.filter((x) => !x.startsWith('http'))].join(': '),
        link: err.details.find((x) => x.startsWith('http')) })
      return false
    } finally { setBusy(null) }
  }
  const toggle = (key: string) => setSelected((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]))
  const saving = active.filter((s) => selected.includes(s.key)).reduce((t, s) => t + s.amount, 0)

  return (
    <>
      <PageHeader eyebrow="Subscriptions" title="What are your subscriptions really costing?"
        description="Detected from your recurring payments, added by you, or linked from PayPal. Select any to simulate cancelling them; add a new one to see what it costs you first."
        actions={<ProvenanceTag />} />

      {msg && (
        <p role="status" className={`mb-4 rounded-xl p-3 text-sm ${msg.ok ? 'bg-brand-50 text-brand-700' : 'bg-red-50 text-red-700'}`}>
          {msg.text}{msg.link && <> <a href={msg.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold underline">Open PayPal automatic payments <ExternalLink className="h-3 w-3" /></a></>}
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Active subscriptions" value={String(d.totals.count_active)} sub="detected in your twin" />
        <Stat label="Per month" value={inr(d.totals.monthly_active)} sub="still projected" />
        <Stat label="Per year" value={inr(d.totals.annual_active)} sub="at today's prices" />
        <Stat label="Saved by cancelling" value={inr(d.totals.annual_cancelled)} sub={`${inr(d.totals.monthly_cancelled)}/month`} good={d.totals.monthly_cancelled > 0} />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card padded={false}>
          <div className="p-5 pb-2 sm:p-6 sm:pb-2"><CardHeader title="Your subscriptions" subtitle="Tick the ones you'd cancel to see the impact" icon={<Repeat className="h-4 w-4" />} /></div>
          {d.superseded.length > 0 && (
            <div className="mx-5 mb-3 rounded-xl bg-blue-50 p-3 text-[13px] text-blue-800 sm:mx-6">
              {d.superseded.map((s) => (
                <p key={s.id} className="flex flex-wrap items-center justify-between gap-2">
                  <span>“{s.name}” now shows up in your payment history, so your twin tracks it automatically and ignores the entry you added.</span>
                  <button onClick={() => void run(`sup-${s.id}`, () => api.removeSubscription(s.id), `Removed the duplicate “${s.name}” entry.`)}
                    className="rounded-lg border border-blue-200 bg-white px-2 py-1 text-xs font-semibold hover:bg-blue-100">Remove duplicate</button>
                </p>
              ))}
            </div>
          )}
          {d.detected.length === 0 ? <EmptyState title="No subscriptions yet" message="Recurring monthly subscription payments appear here automatically, or add one yourself." /> : (
            <ul className="divide-y divide-slate-100">
              {d.detected.map((s) => (
                <SubRow key={s.key} s={s} checked={selected.includes(s.key)} onToggle={() => toggle(s.key)} busy={busy}
                  apiAvailable={d.api_available} run={run} onEdit={setEditing} />
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-6 xl:sticky xl:top-6 xl:self-start">
          <AddSubscriptionForm key={editing?.id ?? 'new'} editing={editing} busy={busy}
            onDone={() => setEditing(null)}
            onSave={(body) => run('add', () => editing ? api.editSubscription(editing.id, body) : api.addSubscription(body),
              editing ? `“${body.name}” updated.` : `“${body.name}” added. Every forecast now includes ${inr(body.amount)}/month.`)} />

          <Card>
            <CardHeader title="Cancel simulation" action={<ProjectedTag />} subtitle={selected.length ? `${selected.length} selected` : 'Select subscriptions on the left'} />
            {selected.length === 0 ? (
              <p className="text-sm text-navy-500">Pick one or more subscriptions to see how cancelling them changes your next 90 days.</p>
            ) : (
              <>
                <p className="tabular text-2xl font-semibold text-navy-900">{inr(saving)}<span className="text-sm font-normal text-navy-500">/month</span></p>
                <p className="tabular text-sm text-navy-500">{inr(saving * 12)} a year</p>
                {sim ? (
                  <dl className="mt-4 space-y-2 text-[13px]">
                    {sim.impacts.map((i) => (
                      <div key={i.day} className="flex justify-between"><dt className="text-navy-500">After {i.day} days</dt><dd className="tabular font-semibold text-brand-700">{signedInr(i.delta)}</dd></div>
                    ))}
                    <div className="flex justify-between border-t border-slate-100 pt-2"><dt className="text-navy-500">Lowest balance</dt>
                      <dd className="tabular font-medium text-navy-900">{inr(sim.simulated.min_balance)} <span className="text-navy-400">(was {inr(sim.baseline.min_balance)})</span></dd></div>
                  </dl>
                ) : <Loader2 className="mt-4 h-4 w-4 animate-spin text-navy-400" />}
                <div className="mt-4 flex flex-col gap-2">
                  <button disabled={!!busy} onClick={() => void run('bulk', async () => {
                    for (const key of selected) {
                      const s = active.find((x) => x.key === key)
                      if (!s || s.linked) continue
                      if (s.added) await api.removeSubscription(s.added.id)
                      else await api.markSubscription(key, true)
                    }
                  }, 'Marked as cancelled. They’re removed from your forecast.')}
                    className="rounded-xl bg-navy-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-navy-800 disabled:opacity-50">
                    I’ve cancelled these. Update my forecast
                  </button>
                  <p className="text-[11px] text-navy-400">PayPal-linked subscriptions are cancelled on their own row, through PayPal.</p>
                </div>
              </>
            )}
          </Card>

          <LinkForm detected={d.detected} apiAvailable={d.api_available} busy={busy}
            onLink={(id, key) => run('link', () => api.linkSubscription(id, key || undefined), 'Linked. Live status, price and next billing date come from PayPal.')} />
        </div>
      </div>
    </>
  )
}

const SOURCE_NOTE: Record<DetectedSubscription['source'], (s: DetectedSubscription) => string> = {
  detected: (s) => `${s.occurrences} payments`,
  manual: () => 'Added by you',
  paypal: () => 'From PayPal, no payments seen yet',
}

function SubRow({ s, checked, onToggle, busy, apiAvailable, run, onEdit }: {
  s: DetectedSubscription; checked: boolean; onToggle: () => void; busy: string | null; apiAvailable: boolean
  run: (id: string, fn: () => Promise<unknown>, ok: string) => Promise<boolean>; onEdit: (a: AddedSubscription) => void
}) {
  const added = s.added
  const l = s.linked
  const id = `row-${s.key}`
  const confirmThen = (action: 'cancel' | 'suspend' | 'activate', verb: string) => {
    if (!l) return
    if (action !== 'activate' && !window.confirm(`${verb} “${l.name}” on PayPal? You can re-activate a suspended subscription later; cancelling is permanent.`)) return
    void run(id, () => api.subscriptionAction(l.id, action), `${l.name}: ${action === 'activate' ? 'active again' : action === 'cancel' ? 'cancelled on PayPal' : 'suspended on PayPal'}.`)
  }
  return (
    <li className={`flex flex-wrap items-center gap-3 px-5 py-3.5 sm:px-6 ${s.cancelled ? 'bg-slate-50/70' : ''}`}>
      <button onClick={onToggle} disabled={s.cancelled} aria-pressed={checked} aria-label={`Simulate cancelling ${s.merchant}`}
        className="text-navy-400 hover:text-navy-900 disabled:opacity-30">
        {checked ? <CheckSquare className="h-5 w-5 text-brand-600" /> : <Square className="h-5 w-5" />}
      </button>
      <div className="min-w-0 flex-1">
        <p className={`flex flex-wrap items-center gap-2 text-sm font-medium ${s.cancelled ? 'text-navy-400 line-through' : 'text-navy-900'}`}>
          {s.merchant}
          {s.source === 'manual' && <Badge tone="navy">Added</Badge>}
          {l && <Badge tone="blue" icon={<Link2 className="h-3 w-3" />}>PayPal · {l.status.toLowerCase()}</Badge>}
          {s.cancelled && <Badge>{s.cancelled_via === 'paypal' ? 'Cancelled via PayPal' : 'Marked cancelled'}</Badge>}
        </p>
        <p className="text-[11px] text-navy-400">
          {SOURCE_NOTE[s.source](s)} · {s.cancelled ? 'no longer projected' : `next ${fmtShort(l?.next_billing_date ?? s.next_date)}`} · {inr(s.annual_cost)}/year
        </p>
      </div>
      <span className="tabular text-sm font-semibold text-navy-900">{inr(l?.amount ?? s.amount)}<span className="text-[11px] font-normal text-navy-400">/mo</span></span>
      <div className="flex w-full flex-wrap justify-end gap-1.5 sm:w-auto">
        {busy === id ? <Loader2 className="h-4 w-4 animate-spin text-navy-400" /> : l ? (
          <>
            <IconBtn label="Refresh from PayPal" onClick={() => void run(id, () => api.refreshSubscription(l.id), `${l.name} refreshed.`)}><RefreshCw className="h-3.5 w-3.5" /></IconBtn>
            {l.status === 'ACTIVE' && <>
              <IconBtn label="Suspend on PayPal" onClick={() => confirmThen('suspend', 'Suspend')}><Pause className="h-3.5 w-3.5" /></IconBtn>
              <button onClick={() => confirmThen('cancel', 'Cancel')} disabled={!apiAvailable}
                className="inline-flex items-center gap-1 rounded-lg bg-red-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-40"><XCircle className="h-3.5 w-3.5" /> Cancel via PayPal</button>
            </>}
            {l.status === 'SUSPENDED' && <IconBtn label="Re-activate on PayPal" onClick={() => confirmThen('activate', 'Activate')}><Play className="h-3.5 w-3.5" /></IconBtn>}
            <IconBtn label="Unlink from PayPal" onClick={() => void run(id, () => api.unlinkSubscription(l.id), 'Unlinked.')}><Trash2 className="h-3.5 w-3.5" /></IconBtn>
          </>
        ) : added ? (
          <>
            <button onClick={() => onEdit(added)} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-navy-700 hover:bg-slate-50">Edit</button>
            <button onClick={() => { if (window.confirm(`Remove “${added.name}” from your twin?`)) void run(id, () => api.removeSubscription(added.id), `“${added.name}” removed.`) }}
              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-navy-700 hover:bg-slate-50"><Trash2 className="h-3.5 w-3.5" /> Remove</button>
          </>
        ) : s.cancelled ? (
          <button onClick={() => void run(id, () => api.markSubscription(s.key, false), `${s.merchant} restored to your forecast.`)}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-navy-700 hover:bg-slate-50"><RotateCcw className="h-3.5 w-3.5" /> Restore</button>
        ) : (
          <button onClick={() => void run(id, () => api.markSubscription(s.key, true), `${s.merchant} marked as cancelled.`)}
            className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-navy-700 hover:bg-slate-50">Mark cancelled</button>
        )}
      </div>
    </li>
  )
}

function localToday(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Add (or edit) a subscription, and simulate "what if I subscribe?" before committing to it. */
function AddSubscriptionForm({ editing, busy, onSave, onDone }: {
  editing: AddedSubscription | null; busy: string | null
  onSave: (body: SubscriptionInput) => Promise<boolean>; onDone: () => void
}) {
  const today = localToday()
  const [name, setName] = useState(editing?.name ?? '')
  const [amountText, setAmountText] = useState(editing ? String(editing.amount) : '')
  const [next, setNext] = useState(editing?.next_billing_date ?? today)
  const [preview, setPreview] = useState<ScenarioResult | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const amount = Number(amountText.replace(/,/g, ''))
  const valid = name.trim().length > 0 && Number.isFinite(amount) && amount > 0 && amount <= 1e7 && next >= today
  const body: SubscriptionInput = { name: name.trim(), amount, next_billing_date: next }

  async function simulate() {
    setPreviewing(true); setPreviewError(null)
    try { setPreview(await api.scenario([{ type: 'add_subscription', amount, label: body.name, start: next }], `Subscribe to ${body.name}`)) }
    catch (e) { setPreviewError(e instanceof ApiError ? e.message : String(e)); setPreview(null) }
    finally { setPreviewing(false) }
  }
  async function save() {
    if (await onSave(body)) { setName(''); setAmountText(''); setNext(today); setPreview(null); onDone() }
  }

  const buffer = preview?.assumptions.safety_buffer ?? 0
  return (
    <Card>
      <CardHeader title={editing ? `Edit “${editing.name}”` : 'Add a subscription'} icon={<Plus className="h-4 w-4" />}
        subtitle={editing ? 'Changes apply to every forecast.' : 'For one you’ve just started, before it shows up in your history.'} />
      <label htmlFor="add-name" className="text-xs font-medium text-navy-700">Name</label>
      <input id="add-name" value={name} maxLength={120} onChange={(e) => { setName(e.target.value); setPreview(null) }} placeholder="e.g. Gym membership"
        className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-navy-700" />
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div>
          <label htmlFor="add-amount" className="text-xs font-medium text-navy-700">Monthly price</label>
          <div className="mt-1.5 flex items-center rounded-lg border border-slate-200 px-2.5 focus-within:border-navy-700">
            <span className="text-sm text-navy-400">₹</span>
            <input id="add-amount" inputMode="decimal" value={amountText} placeholder="499"
              onChange={(e) => { setAmountText(e.target.value.replace(/[^\d.,]/g, '')); setPreview(null) }}
              className="tabular w-full bg-transparent px-1.5 py-2 text-sm outline-none" />
          </div>
        </div>
        <div>
          <label htmlFor="add-next" className="text-xs font-medium text-navy-700">Next billing date</label>
          <input id="add-next" type="date" min={today} value={next} onChange={(e) => { setNext(e.target.value); setPreview(null) }}
            className="mt-1.5 w-full rounded-lg border border-slate-200 px-2.5 py-2 text-sm outline-none focus:border-navy-700" />
        </div>
      </div>
      {amountText && !(amount > 0 && amount <= 1e7) && <p className="mt-1 text-xs text-red-600">Enter a monthly price between ₹1 and ₹1,00,00,000.</p>}
      {next < today && <p className="mt-1 text-xs text-red-600">The next billing date must be today or later.</p>}

      {preview && (
        <div className="mt-4 rounded-xl bg-slate-50 p-3 text-[13px]">
          <p className="font-medium text-navy-900">What if you subscribe?</p>
          <dl className="mt-2 space-y-1">
            <div className="flex justify-between"><dt className="text-navy-500">Per year</dt><dd className="tabular font-medium">{inr(amount * 12)}</dd></div>
            {preview.impacts.map((i) => (
              <div key={i.day} className="flex justify-between"><dt className="text-navy-500">Balance after {i.day} days</dt><dd className="tabular font-medium">{signedInr(i.delta)}</dd></div>
            ))}
            <div className="flex justify-between border-t border-slate-200 pt-1"><dt className="text-navy-500">Lowest balance</dt>
              <dd className={`tabular font-semibold ${preview.simulated.min_balance < buffer ? 'text-red-700' : 'text-navy-900'}`}>{inr(preview.simulated.min_balance)}</dd></div>
          </dl>
          <p className={`mt-2 text-[12px] ${preview.risks[0].level === 'low' ? 'text-brand-700' : 'text-red-700'}`}>{preview.risks[0].title}: {preview.risks[0].detail}</p>
        </div>
      )}
      {previewError && <p role="alert" className="mt-2 text-xs text-red-600">{previewError}</p>}

      <div className="mt-4 flex gap-2">
        {editing ? (
          <button onClick={onDone} className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-navy-700 hover:bg-slate-50">Cancel</button>
        ) : (
          <button disabled={!valid || previewing} onClick={() => void simulate()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-navy-800 hover:bg-slate-50 disabled:opacity-40">
            {previewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 text-brand-600" />} Simulate first
          </button>
        )}
        <button disabled={!valid || !!busy} onClick={() => void save()}
          className="flex-1 rounded-lg bg-navy-900 px-3 py-2 text-sm font-semibold text-white hover:bg-navy-800 disabled:opacity-40">
          {editing ? 'Save changes' : 'Add to my twin'}
        </button>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-navy-400">Once real payments to this merchant appear in your history, your twin tracks them automatically and this entry stops counting, so nothing is counted twice.</p>
    </Card>
  )
}

function IconBtn({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return <button onClick={onClick} aria-label={label} title={label} className="rounded-lg border border-slate-200 p-1.5 text-navy-600 hover:bg-slate-50">{children}</button>
}

function LinkForm({ detected, apiAvailable, busy, onLink }: { detected: DetectedSubscription[]; apiAvailable: boolean; busy: string | null; onLink: (id: string, key: string) => void }) {
  const [subId, setSubId] = useState('')
  const [key, setKey] = useState('')
  const demo = useApi(api.paypalDemo)
  const linkedIds = new Set(detected.flatMap((s) => (s.linked ? [s.linked.paypal_subscription_id] : [])))
  const demoSubs = (demo.data?.demo ? demo.data.subscriptions : []).filter((s) => !linkedIds.has(s.id))
  const valid = /^[A-Za-z0-9-]{3,64}$/.test(subId.trim())
  return (
    <Card>
      <CardHeader title="Link a PayPal subscription" icon={<PayPalMark size="sm" />}
        action={<Badge tone={demo.data?.demo ? 'amber' : 'blue'}>{demo.data?.demo ? 'Demo Subscriptions API' : 'Subscriptions API'}</Badge>} />
      {demoSubs.length > 0 && (
        <div className="mb-3 rounded-xl bg-amber-50 p-3 text-[12px] text-amber-900">
          <p className="font-medium">Demo mode: pick a demo PayPal subscription</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {demoSubs.map((s) => (
              <button key={s.id} onClick={() => setSubId(s.id)} title={s.id}
                className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${subId === s.id ? 'border-amber-700 bg-amber-200' : 'border-amber-300 bg-white hover:bg-amber-100'}`}>
                {s.name} · {inr(s.amount)}
              </button>
            ))}
          </div>
        </div>
      )}
      {!apiAvailable ? (
        <p className="text-[13px] text-navy-500">Needs PayPal API credentials on the server (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET). Marking subscriptions cancelled works without them.</p>
      ) : (
        <>
          <label htmlFor="sub-id" className="text-xs font-medium text-navy-700">PayPal subscription ID</label>
          <input id="sub-id" value={subId} onChange={(e) => setSubId(e.target.value)} placeholder="I-BW452GLLEP1G"
            className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-sm outline-none focus:border-navy-700" />
          <label htmlFor="sub-key" className="mt-3 block text-xs font-medium text-navy-700">Matches (optional, auto-detected)</label>
          <select id="sub-key" value={key} onChange={(e) => setKey(e.target.value)} className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm">
            <option value="">Auto-match by name or price</option>
            {detected.filter((s) => !s.linked).map((s) => <option key={s.key} value={s.key}>{s.merchant} · {inr(s.amount)}/mo</option>)}
          </select>
          <button disabled={!valid || !!busy} onClick={() => { onLink(subId.trim(), key); setSubId('') }}
            className="mt-3 w-full rounded-lg bg-[#003087] px-3 py-2 text-sm font-semibold text-white hover:bg-[#002366] disabled:opacity-40">Link subscription</button>
          <p className="mt-2 text-[11px] leading-relaxed text-navy-400">
            Find the ID in PayPal under Settings → Automatic payments. PayPal lets only the merchant’s app cancel through the API; for other merchants FINORA links you to PayPal to cancel there.
          </p>
        </>
      )}
    </Card>
  )
}

function Stat({ label, value, sub, good }: { label: string; value: string; sub: string; good?: boolean }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4">
      <p className="text-xs text-navy-500">{label}</p>
      <p className={`tabular mt-2 text-xl font-semibold tracking-tight ${good ? 'text-brand-700' : 'text-navy-900'}`}>{value}</p>
      <p className="mt-0.5 text-[11px] text-navy-400">{sub}</p>
    </div>
  )
}
