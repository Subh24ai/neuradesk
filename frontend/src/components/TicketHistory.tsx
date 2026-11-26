import { useCallback, useEffect, useRef, useState } from 'react'
import {
  CATEGORY_LABEL,
  decideTicket,
  relativeTime,
  statusMeta,
  type TicketSummary,
} from '../lib/tickets'

export type HistoryFilter = 'all' | 'action' | 'in_progress' | 'resolved' | 'escalated' | 'failed'

interface Props {
  token: string
  onNewTicket: () => void
  /** Open New Ticket with this text pre-filled (resubmit, or a quick-start template). */
  onRetry?: (text: string) => void
  onToast?: (message: string, variant?: 'success' | 'error' | 'info') => void
  /** Open with this filter selected (e.g. 'action' from the "needs your confirmation" alert). */
  initialFilter?: HistoryFilter
}

interface Summary { total: number; by_status: Record<string, number> }

const LIMIT = 20
const REFRESH_MS = 4000

// Each filter maps to the statuses the server should return.
const FILTERS: { key: HistoryFilter; label: string; statuses: string[] }[] = [
  { key: 'all', label: 'All', statuses: [] },
  { key: 'action', label: 'Needs action', statuses: ['awaiting_confirmation'] },
  { key: 'in_progress', label: 'In progress', statuses: ['pending', 'processing'] },
  { key: 'resolved', label: 'Resolved', statuses: ['resolved'] },
  { key: 'escalated', label: 'With support', statuses: ['escalated'] },
  { key: 'failed', label: 'Failed', statuses: ['failed'] },
]

const QUICK_STARTS = [
  { label: 'Reset my password', text: "I forgot my password and can't sign in." },
  { label: 'Request access', text: 'I need access to [system or shared drive] for [reason].' },
  { label: 'Ask about a policy', text: 'What is our policy on [topic]?' },
]

function countFor(summary: Summary | null, key: HistoryFilter): number {
  if (!summary) return 0
  const f = FILTERS.find((x) => x.key === key)!
  if (key === 'all') return summary.total
  return f.statuses.reduce((n, s) => n + (summary.by_status[s] ?? 0), 0)
}

function getDateGroup(iso: string): string {
  const t = new Date(iso)
  const today = new Date()
  const diff = Math.round((
    new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() -
    new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime()
  ) / 86_400_000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  if (diff < 7) return 'This week'
  return 'Earlier'
}

function groupTickets(tickets: TicketSummary[]) {
  const order = ['Today', 'Yesterday', 'This week', 'Earlier']
  const map: Record<string, TicketSummary[]> = {}
  for (const t of tickets) (map[getDateGroup(t.created_at)] ??= []).push(t)
  return order.filter((g) => map[g]).map((g) => ({ label: g, items: map[g] }))
}

function Icon({ d, className = 'h-4 w-4' }: { d: string; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  )
}

const ICON = {
  search: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z',
  refresh: 'M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99',
  plus: 'M12 4.5v15m7.5-7.5h-15',
  chevron: 'M19.5 8.25l-7.5 7.5-7.5-7.5',
  copy: 'M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 01-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 00-3.375-3.375h-1.5a1.125 1.125 0 01-1.125-1.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25',
  inbox: 'M2.25 13.5h3.86a2.25 2.25 0 012.012 1.244l.256.512a2.25 2.25 0 002.013 1.244h3.218a2.25 2.25 0 002.013-1.244l.256-.512a2.25 2.25 0 012.013-1.244h3.859m-19.5.338V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H6.911a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661z',
}

function SkeletonRow() {
  return (
    <div className="animate-pulse rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-2 h-4 w-3/5 rounded bg-slate-200" />
      <div className="h-3 w-2/5 rounded bg-slate-100" />
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={() => navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800) })}
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
      aria-label="Copy resolution"
    >
      <Icon d={ICON.copy} className="h-3.5 w-3.5" />
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function Outcome({ t, onDecide, deciding, onRetry }: {
  t: TicketSummary
  onDecide: (id: string, d: 'confirm-action' | 'cancel') => void
  deciding: boolean
  onRetry?: (text: string) => void
}) {
  const meta = statusMeta(t.status)
  if (meta.inProgress) {
    return <p className="text-sm text-indigo-700">Our agents are working on this. It updates here automatically — you don’t need to stay on this page.</p>
  }
  if (meta.needsAction) {
    return (
      <div>
        <p className="text-sm font-medium text-rose-800">{t.escalation_reason ?? 'This request changes your account and needs your confirmation.'}</p>
        <p className="mt-1 text-xs text-rose-700/80">Nothing has been changed yet.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => onDecide(t.ticket_id, 'confirm-action')}
            disabled={deciding}
            className="rounded-lg bg-rose-600 px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-rose-700 disabled:opacity-50"
          >
            {deciding ? 'Working…' : 'Confirm and proceed'}
          </button>
          <button
            onClick={() => onDecide(t.ticket_id, 'cancel')}
            disabled={deciding}
            className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel request
          </button>
        </div>
      </div>
    )
  }
  if (t.status === 'failed') {
    return (
      <div>
        <p className="text-sm text-red-800">{t.escalation_reason ?? 'We couldn’t process this request.'}</p>
        {onRetry && t.raw_text && (
          <button onClick={() => onRetry(t.raw_text!)} className="mt-2.5 rounded-lg border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 hover:border-red-300">
            Resubmit this request
          </button>
        )}
      </div>
    )
  }
  if (t.status === 'escalated') {
    return (
      <div>
        <p className="text-sm text-amber-900">{t.escalation_reason ?? 'This request needs a member of the support team.'}</p>
        <p className="mt-1 text-xs text-amber-700/80">The support team will follow up with you.</p>
      </div>
    )
  }
  return t.resolution ? (
    <div>
      <p className="text-sm leading-relaxed text-slate-800">{t.resolution}</p>
      <div className="mt-1 -ml-2"><CopyButton text={t.resolution} /></div>
    </div>
  ) : <p className="text-sm text-slate-500">Completed.</p>
}

interface SupportMessage { id: string; content: string; created_at: string }

/** Messages the support team wrote on this ticket (admin comments are visible to the owner). */
function SupportMessages({ ticketId, token }: { ticketId: string; token: string }) {
  const [messages, setMessages] = useState<SupportMessage[]>([])
  useEffect(() => {
    let cancelled = false
    fetch(`/tickets/${ticketId}/comments`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : { comments: [] }))
      .then((d) => { if (!cancelled) setMessages(d.comments ?? []) })
      .catch(() => { /* non-critical */ })
    return () => { cancelled = true }
  }, [ticketId, token])
  if (messages.length === 0) return null
  return (
    <div className="rounded-xl border border-violet-100 bg-violet-50 px-4 py-3">
      <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-violet-500">Messages from support</p>
      <ul className="space-y-2">
        {messages.map((m) => (
          <li key={m.id} className="rounded-lg bg-white px-3 py-2">
            <p className="text-sm text-slate-800">{m.content}</p>
            <p className="mt-0.5 text-[10px] text-slate-400">{relativeTime(m.created_at)}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}

function TicketRow({ t, token, isOpen, onToggle, onDecide, deciding, onRetry }: {
  t: TicketSummary
  token: string
  isOpen: boolean
  onToggle: () => void
  onDecide: (id: string, d: 'confirm-action' | 'cancel') => void
  deciding: boolean
  onRetry?: (text: string) => void
}) {
  const meta = statusMeta(t.status)
  const category = t.category ? (CATEGORY_LABEL[t.category] ?? t.category) : null
  const outcomeTone =
    meta.needsAction ? 'border-rose-200 bg-rose-50'
    : meta.inProgress ? 'border-indigo-100 bg-indigo-50'
    : t.status === 'failed' ? 'border-red-100 bg-red-50'
    : t.status === 'escalated' ? 'border-amber-100 bg-amber-50'
    : 'border-emerald-100 bg-emerald-50/60'

  return (
    <li className={`overflow-hidden rounded-xl border bg-white transition-all ${
      meta.needsAction ? 'border-rose-200 ring-1 ring-rose-100' : isOpen ? 'border-slate-300 shadow-sm' : 'border-slate-200 hover:border-slate-300'
    }`}>
      <button onClick={onToggle} aria-expanded={isOpen} className="flex w-full items-start gap-3 px-4 py-3.5 text-left sm:px-5">
        <span className={`mt-[7px] h-2 w-2 flex-shrink-0 rounded-full ${meta.dot}`} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className={`block text-sm font-medium text-slate-900 ${isOpen ? '' : 'truncate'}`}>{t.raw_text ?? 'Request'}</span>
          <span className="mt-0.5 block text-xs text-slate-500">
            {category && <>{category} · </>}
            <span className="font-mono text-slate-400">#{t.ticket_id.slice(0, 8).toUpperCase()}</span> · {relativeTime(t.created_at)}
          </span>
        </span>
        <span className={`hidden flex-shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold sm:inline-flex ${meta.badge}`}>{meta.label}</span>
        <Icon d={ICON.chevron} className={`mt-0.5 h-4 w-4 flex-shrink-0 text-slate-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      <span className={`mx-4 mb-3 -mt-1 inline-flex rounded-full border px-2.5 py-0.5 text-[11px] font-semibold sm:hidden ${meta.badge}`}>{meta.label}</span>

      {isOpen && (
        <div className="space-y-3 border-t border-slate-100 bg-slate-50/50 px-4 py-4 sm:px-5 fade-in">
          <div className={`rounded-xl border px-4 py-3 ${outcomeTone}`}>
            <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-slate-500">Outcome</p>
            <Outcome t={t} onDecide={onDecide} deciding={deciding} onRetry={onRetry} />
          </div>
          {t.admin_note && t.admin_note !== t.resolution && (
            <div className="rounded-xl border border-violet-100 bg-violet-50 px-4 py-3">
              <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-violet-500">Note from support</p>
              <p className="text-sm text-violet-900">{t.admin_note}</p>
            </div>
          )}
          <SupportMessages ticketId={t.ticket_id} token={token} />
          {t.trace_url && (
            <a href={t.trace_url} target="_blank" rel="noreferrer" className="inline-flex text-xs font-semibold text-indigo-600 hover:text-indigo-800">
              View agent trace ↗
            </a>
          )}
        </div>
      )}
    </li>
  )
}

export default function TicketHistory({ token, onNewTicket, onRetry, onToast, initialFilter = 'all' }: Props) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<HistoryFilter>(initialFilter)
  const [query, setQuery] = useState('')
  const [q, setQ] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [deciding, setDeciding] = useState<string | null>(null)
  const autoOpened = useRef(false)

  // Debounce the search box → server query.
  useEffect(() => {
    const id = setTimeout(() => setQ(query.trim()), 300)
    return () => clearTimeout(id)
  }, [query])

  const loadSummary = useCallback(async () => {
    try {
      const r = await fetch('/tickets/summary', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setSummary(await r.json())
    } catch { /* keep last */ }
  }, [token])

  const loadList = useCallback(async (newOffset: number, silent = false) => {
    if (!silent) { setLoading(true); setError(null) }
    try {
      const params = new URLSearchParams({ limit: String(LIMIT), offset: String(newOffset) })
      const statuses = FILTERS.find((f) => f.key === filter)!.statuses
      if (statuses.length) params.set('status', statuses.join(','))
      if (q) params.set('q', q)
      const r = await fetch(`/tickets/?${params}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      setTickets(data.tickets ?? [])
      setTotal(data.total ?? 0)
      setOffset(newOffset)
    } catch {
      if (!silent) setError('We couldn’t load your tickets. Check your connection and try again.')
    } finally {
      if (!silent) setLoading(false)
    }
  }, [token, filter, q])

  useEffect(() => { loadSummary() }, [loadSummary])
  useEffect(() => { loadList(0) }, [loadList])

  // Opened from the "needs your confirmation" alert → expand the first one.
  useEffect(() => {
    if (autoOpened.current || loading || initialFilter !== 'action' || !tickets.length) return
    setExpanded(tickets[0].ticket_id)
    autoOpened.current = true
  }, [tickets, loading, initialFilter])

  // Live updates while anything is still being processed.
  const inProgress = countFor(summary, 'in_progress') > 0
  useEffect(() => {
    if (!inProgress) return
    const id = setInterval(() => { loadSummary(); loadList(offset, true) }, REFRESH_MS)
    return () => clearInterval(id)
  }, [inProgress, offset, loadSummary, loadList])

  async function handleDecide(ticketId: string, decision: 'confirm-action' | 'cancel') {
    setDeciding(ticketId)
    const err = await decideTicket(ticketId, token, decision)
    setDeciding(null)
    if (err) onToast?.(err, 'error')
    else onToast?.(decision === 'confirm-action' ? 'Confirmed — action completed.' : 'Cancelled — passed to the support team.', 'success')
    await Promise.all([loadSummary(), loadList(offset, true)])
  }

  function refresh() { loadSummary(); loadList(offset) }
  function clearFilters() { setQuery(''); setQ(''); setFilter('all') }

  const hasNoTicketsAtAll = summary !== null && summary.total === 0
  // In the All view, anything waiting on the user is pinned above the timeline.
  const pinned = filter === 'all' ? tickets.filter((t) => statusMeta(t.status).needsAction) : []
  const groups = [
    ...(pinned.length ? [{ label: 'Needs your action', items: pinned }] : []),
    ...groupTickets(pinned.length ? tickets.filter((t) => !statusMeta(t.status).needsAction) : tickets),
  ]

  // ── First-run empty state ────────────────────────────────────────────────
  if (hasNoTicketsAtAll) {
    return (
      <div className="fade-in">
        <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">My Tickets</h2>
        <p className="mt-1 text-sm text-slate-500">Track every request from submission to resolution.</p>
        <div className="mt-7 rounded-2xl border border-slate-200 bg-white px-6 py-12 text-center shadow-sm sm:px-12">
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
            <Icon d={ICON.inbox} className="h-7 w-7" />
          </div>
          <h3 className="text-lg font-bold text-slate-900">Your requests will appear here</h3>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-slate-500">
            Submit an IT or HR request and follow it live — most are resolved automatically in seconds,
            and anything that needs your confirmation or a person shows up here first.
          </p>
          {onRetry && (
            <div className="mt-7">
              <p className="mb-3 text-[11px] font-bold uppercase tracking-widest text-slate-400">Start with a common request</p>
              <div className="flex flex-wrap justify-center gap-2">
                {QUICK_STARTS.map((s) => (
                  <button
                    key={s.label}
                    onClick={() => onRetry(s.text)}
                    className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition-all hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          <button
            onClick={onNewTicket}
            className="mt-7 inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700"
          >
            <Icon d={ICON.plus} /> Describe your own request
          </button>
        </div>
      </div>
    )
  }

  // ── Main view ─────────────────────────────────────────────────────────────
  return (
    <div className="fade-in">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">My Tickets</h2>
          <p className="mt-1 text-sm text-slate-500">
            Track and manage your requests.
            {inProgress && <span className="ml-1.5 text-indigo-600">Updating live…</span>}
          </p>
        </div>
        <button
          onClick={onNewTicket}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700"
        >
          <Icon d={ICON.plus} /> New ticket
        </button>
      </div>

      <div className="mb-5 space-y-3">
        <div className="flex gap-2">
          <label className="relative flex-1">
            <span className="sr-only">Search your tickets</span>
            <Icon d={ICON.search} className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your tickets…"
              className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-sm text-slate-800 placeholder-slate-400 shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </label>
          <button
            onClick={refresh}
            disabled={loading}
            aria-label="Refresh"
            title="Refresh"
            className="flex w-11 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 shadow-sm transition-colors hover:bg-slate-50 disabled:opacity-40"
          >
            <Icon d={ICON.refresh} className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Filter by status">
          {FILTERS.filter((f) => f.key === 'all' || f.key === filter || countFor(summary, f.key) > 0).map((f) => {
            const n = countFor(summary, f.key)
            const active = filter === f.key
            const urgent = f.key === 'action' && n > 0
            return (
              <button
                key={f.key}
                role="tab"
                aria-selected={active}
                onClick={() => { setFilter(f.key); setExpanded(null) }}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-all ${
                  active
                    ? urgent ? 'border-rose-600 bg-rose-600 text-white' : 'border-slate-900 bg-slate-900 text-white'
                    : urgent ? 'border-rose-200 bg-rose-50 text-rose-700 hover:border-rose-300' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                }`}
              >
                {f.label}
                <span className={`rounded-full px-1.5 text-[10px] ${active ? 'bg-white/20' : urgent ? 'bg-rose-100' : 'bg-slate-100'}`}>{n}</span>
              </button>
            )
          })}
        </div>
      </div>

      {error && (
        <div role="alert" className="mb-5 flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
          <button onClick={refresh} className="font-semibold underline">Try again</button>
        </div>
      )}

      {loading ? (
        <div className="space-y-2.5">{[0, 1, 2, 3].map((i) => <SkeletonRow key={i} />)}</div>
      ) : tickets.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <p className="font-semibold text-slate-800">{q ? `No tickets match “${q}”` : 'No tickets in this view'}</p>
          <p className="mt-1 text-sm text-slate-500">Try a different search or filter.</p>
          <button onClick={clearFilters} className="mt-4 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
            Clear filters
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {groups.map(({ label, items }) => (
            <section key={label} aria-label={label}>
              <h3 className={`mb-2.5 text-[11px] font-bold uppercase tracking-widest ${label === 'Needs your action' ? 'text-rose-600' : 'text-slate-400'}`}>{label}</h3>
              <ul className="space-y-2">
                {items.map((t) => (
                  <TicketRow
                    key={t.ticket_id}
                    t={t}
                    token={token}
                    isOpen={expanded === t.ticket_id}
                    onToggle={() => setExpanded(expanded === t.ticket_id ? null : t.ticket_id)}
                    onDecide={handleDecide}
                    deciding={deciding === t.ticket_id}
                    onRetry={onRetry}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {!loading && total > LIMIT && (
        <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4">
          <span className="text-xs text-slate-500">{offset + 1}–{Math.min(offset + LIMIT, total)} of {total}</span>
          <div className="flex gap-2">
            <button disabled={offset === 0} onClick={() => loadList(Math.max(0, offset - LIMIT))}
              className="rounded-lg border border-slate-200 px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40">
              ← Previous
            </button>
            <button disabled={offset + LIMIT >= total} onClick={() => loadList(offset + LIMIT)}
              className="rounded-lg border border-slate-200 px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40">
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
