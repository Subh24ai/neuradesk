import { useCallback, useEffect, useState } from 'react'

interface TicketSummary {
  ticket_id: string
  status: string
  raw_text: string | null
  category: string | null
  confidence: number | null
  resolution: string | null
  escalation_reason: string | null
  admin_note: string | null
  trace_url: string | null
  created_at: string
}

interface Props {
  token: string
  onNewTicket: () => void
  onRetry?: (text: string) => void
}

type Filter = 'all' | 'resolved' | 'escalated' | 'pending'

const LIMIT = 20

const STATUS_CONFIG: Record<string, { dot: string; badge: string; label: string }> = {
  resolved:  { dot: 'bg-emerald-500',  badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',  label: 'Resolved'  },
  escalated: { dot: 'bg-amber-500',    badge: 'bg-amber-50 text-amber-700 border-amber-200',         label: 'Escalated' },
  pending:   { dot: 'bg-indigo-400',   badge: 'bg-indigo-50 text-indigo-700 border-indigo-200',        label: 'Pending'   },
}

const CATEGORY_LABEL: Record<string, string> = {
  password_reset:   'Password Reset',
  access_request:   'Access Request',
  software_install: 'Software Install',
  incident_report:  'Incident',
  leave_approval:   'Leave',
  unknown:          'Unknown',
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return d === 1 ? 'yesterday' : `${d}d ago`
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

const GROUP_ORDER = ['Today', 'Yesterday', 'This week', 'Earlier']

function groupTickets(tickets: TicketSummary[]) {
  const map: Record<string, TicketSummary[]> = {}
  for (const t of tickets) {
    const g = getDateGroup(t.created_at)
    if (!map[g]) map[g] = []
    map[g].push(t)
  }
  return GROUP_ORDER.filter((g) => map[g]).map((g) => ({ label: g, items: map[g] }))
}

function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 animate-pulse">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-slate-200 rounded-lg w-4/5" />
          <div className="flex gap-2">
            <div className="h-3 bg-slate-100 rounded w-12" />
            <div className="h-3 bg-slate-100 rounded w-16" />
          </div>
        </div>
        <div className="h-5 bg-slate-100 rounded-full w-20" />
      </div>
    </div>
  )
}

function StatCard({ label, value, color, icon }: {
  label: string; value: number;
  color: 'slate' | 'emerald' | 'amber' | 'indigo'
  icon: React.ReactNode
}) {
  const styles = {
    slate:   { card: 'bg-white border-slate-200',               num: 'text-slate-900', sub: 'text-slate-400', icon: 'bg-slate-100 text-slate-500'    },
    emerald: { card: 'bg-emerald-50 border-emerald-200',         num: 'text-emerald-800', sub: 'text-emerald-500', icon: 'bg-emerald-100 text-emerald-600' },
    amber:   { card: 'bg-amber-50 border-amber-200',             num: 'text-amber-800',   sub: 'text-amber-500',   icon: 'bg-amber-100 text-amber-600'     },
    indigo:  { card: 'bg-indigo-50 border-indigo-200',           num: 'text-indigo-800',  sub: 'text-indigo-500',  icon: 'bg-indigo-100 text-indigo-600'   },
  }
  const s = styles[color]
  return (
    <div className={`rounded-2xl border px-4 py-4 fade-in ${s.card}`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-3 ${s.icon}`}>
        {icon}
      </div>
      <p className={`text-2xl font-bold tracking-tight ${s.num}`}>{value}</p>
      <p className={`text-xs font-semibold mt-0.5 ${s.sub}`}>{label}</p>
    </div>
  )
}

function EmptyState({ filtered, onNewTicket }: { filtered: boolean; onNewTicket: () => void }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 py-16 text-center fade-in">
      <div className="w-14 h-14 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
        <svg className="w-7 h-7 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
        </svg>
      </div>
      {filtered ? (
        <p className="text-slate-500 text-sm font-medium">No tickets match this filter.</p>
      ) : (
        <>
          <p className="text-slate-900 font-semibold mb-1.5">No tickets yet</p>
          <p className="text-slate-400 text-sm mb-6 max-w-[220px] mx-auto">Submit your first request and it will appear here.</p>
          <button
            onClick={onNewTicket}
            className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors shadow-sm"
          >
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
            </svg>
            Submit your first ticket
          </button>
        </>
      )}
    </div>
  )
}

function TicketCard({ t, isOpen, onToggle, onRetry }: {
  t: TicketSummary
  isOpen: boolean
  onToggle: () => void
  onRetry?: (text: string) => void
}) {
  const cfg = STATUS_CONFIG[t.status] ?? STATUS_CONFIG.pending
  const categoryLabel = t.category ? (CATEGORY_LABEL[t.category] ?? t.category) : null
  const isPending = t.status === 'pending'
  const preview = isPending
    ? (t.raw_text?.slice(0, 130) ?? 'Awaiting processing…')
    : (t.resolution?.slice(0, 130) ?? t.escalation_reason ?? 'No resolution recorded')
  const shortId = '#' + t.ticket_id.slice(0, 8).toUpperCase()

  return (
    <div className={`bg-white rounded-xl border overflow-hidden transition-all duration-200 ${isOpen ? 'border-slate-300 shadow-md' : 'border-slate-200 hover:border-slate-300 hover:shadow-sm'}`}>
      <button onClick={onToggle} className="w-full text-left px-4 py-4 group">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cfg.dot}`} aria-hidden="true" />
              <span className="text-[11px] font-mono text-slate-400 font-medium">{shortId}</span>
              {categoryLabel && (
                <>
                  <span className="text-slate-200 text-xs">·</span>
                  <span className="text-[11px] font-semibold text-slate-500">{categoryLabel}</span>
                </>
              )}
            </div>
            <p className="text-sm text-slate-700 leading-snug line-clamp-2 pr-4">{preview}</p>
            <p className="text-xs text-slate-400 mt-1.5">{relativeTime(t.created_at)}</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 pt-0.5">
            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold border capitalize ${cfg.badge}`}>
              {cfg.label}
            </span>
            <svg
              className={`w-4 h-4 text-slate-300 group-hover:text-slate-500 transition-all duration-200 ${isOpen ? 'rotate-180 text-slate-500' : ''}`}
              viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"
            >
              <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
            </svg>
          </div>
        </div>
      </button>

      {isOpen && (
        <div className="border-t border-slate-100 px-4 py-4 bg-slate-50/40 fade-in space-y-3">
          {/* Original request */}
          {t.raw_text && (
            <div>
              <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Original request</p>
              <p className="text-sm text-slate-600 leading-relaxed">{t.raw_text}</p>
            </div>
          )}

          {isPending && (
            <div className="bg-slate-100 border border-slate-200 rounded-xl px-3.5 py-3 flex items-start gap-2.5">
              <svg className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-600 font-medium">Processing did not complete</p>
                <p className="text-xs text-slate-400 mt-0.5">The connection was interrupted. You can resubmit this request.</p>
              </div>
              {onRetry && t.raw_text && (
                <button
                  onClick={() => onRetry(t.raw_text!)}
                  className="flex-shrink-0 text-xs font-semibold text-indigo-600 hover:text-indigo-800 bg-white border border-indigo-200 hover:border-indigo-300 rounded-lg px-3 py-1.5 transition-all hover:shadow-sm"
                >
                  Resubmit
                </button>
              )}
            </div>
          )}

          {!isPending && t.resolution && (
            <div>
              <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Resolution</p>
              <p className="text-sm text-slate-600 leading-relaxed">{t.resolution}</p>
            </div>
          )}
          {t.escalation_reason && (
            <div className="bg-amber-50 border border-amber-100 rounded-xl px-3.5 py-2.5">
              <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide mb-1">Escalation reason</p>
              <p className="text-sm text-amber-800">{t.escalation_reason}</p>
            </div>
          )}
          {t.admin_note && (
            <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-3.5 py-2.5">
              <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide mb-1">Admin note</p>
              <p className="text-sm text-indigo-800">{t.admin_note}</p>
            </div>
          )}
          <div className="flex items-center gap-4 pt-0.5 flex-wrap">
            {t.confidence != null && (
              <div className="flex items-center gap-2">
                <div className="w-20 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-400 rounded-full transition-all" style={{ width: `${Math.round(t.confidence * 100)}%` }} />
                </div>
                <span className="text-xs text-slate-400 font-medium">{Math.round(t.confidence * 100)}% conf.</span>
              </div>
            )}
            {t.trace_url && (
              <a
                href={t.trace_url}
                target="_blank"
                rel="noreferrer"
                className="ml-auto inline-flex items-center gap-1 text-xs text-indigo-500 hover:text-indigo-700 font-semibold transition-colors"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M4.25 5.5a.75.75 0 00-.75.75v8.5c0 .414.336.75.75.75h8.5a.75.75 0 00.75-.75v-4a.75.75 0 011.5 0v4A2.25 2.25 0 0112.75 17h-8.5A2.25 2.25 0 012 14.75v-8.5A2.25 2.25 0 014.25 4h5a.75.75 0 010 1.5h-5z" clipRule="evenodd" />
                  <path fillRule="evenodd" d="M6.194 12.753a.75.75 0 001.06.053L16.5 4.44v2.81a.75.75 0 001.5 0v-4.5a.75.75 0 00-.75-.75h-4.5a.75.75 0 000 1.5h2.553l-9.056 8.194a.75.75 0 00-.053 1.06z" clipRule="evenodd" />
                </svg>
                View trace
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function TicketHistory({ token, onNewTicket, onRetry }: Props) {
  const [tickets, setTickets] = useState<TicketSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = useCallback(async (newOffset: number) => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: String(LIMIT), offset: String(newOffset) })
      const r = await fetch(`/tickets/?${params}`, { headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      setTickets(data.tickets ?? [])
      setTotal(data.total ?? 0)
      setOffset(newOffset)
    } catch {
      setError('Failed to load ticket history.')
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => { load(0) }, [load])

  const resolved  = tickets.filter((t) => t.status === 'resolved').length
  const escalated = tickets.filter((t) => t.status === 'escalated').length
  const pending   = tickets.filter((t) => t.status === 'pending').length

  const filtered = filter === 'all' ? tickets : tickets.filter((t) => t.status === filter)
  const groups   = groupTickets(filtered)

  const FILTERS: { key: Filter; label: string; count: number }[] = [
    { key: 'all',       label: 'All',       count: tickets.length },
    { key: 'resolved',  label: 'Resolved',  count: resolved  },
    { key: 'escalated', label: 'Escalated', count: escalated },
    { key: 'pending',   label: 'Pending',   count: pending   },
  ]

  return (
    <div className="fade-in">
      {/* Header */}
      <div className="flex items-start justify-between mb-7">
        <div>
          <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">My Tickets</h2>
          <p className="mt-1 text-sm text-slate-500">
            {total > LIMIT ? `Showing ${offset + 1}–${Math.min(offset + LIMIT, total)} of ${total}` : `${total} ticket${total !== 1 ? 's' : ''}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => load(offset)}
            disabled={loading}
            aria-label="Refresh"
            className="w-9 h-9 flex items-center justify-center rounded-xl border border-slate-200 bg-white hover:bg-slate-50 hover:border-slate-300 disabled:opacity-40 transition-all shadow-sm"
          >
            <svg className={`w-4 h-4 text-slate-500 ${loading ? 'animate-spin' : ''}`} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
          </button>
          <button
            onClick={onNewTicket}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl px-4 py-2.5 text-sm font-semibold transition-colors shadow-sm hover:shadow-md"
          >
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
            </svg>
            New ticket
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700 font-medium mb-6">
          <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          </svg>
          {error}
        </div>
      )}

      {/* Stats */}
      {!loading && tickets.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <StatCard label="Total" value={total} color="slate" icon={
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
            </svg>
          } />
          <StatCard label="Resolved" value={resolved} color="emerald" icon={
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
            </svg>
          } />
          <StatCard label="Escalated" value={escalated} color="amber" icon={
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
          } />
          <StatCard label="Pending" value={pending} color="indigo" icon={
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z" clipRule="evenodd" />
            </svg>
          } />
        </div>
      )}

      {/* Filter tabs */}
      {!loading && tickets.length > 0 && (
        <div className="flex gap-1 bg-slate-100 rounded-xl p-1 mb-5 overflow-x-auto scrollbar-none">
          {FILTERS.filter(f => f.count > 0 || f.key === 'all').map(({ key, label, count }) => (
            <button
              key={key}
              onClick={() => { setFilter(key); setExpanded(null) }}
              className={`flex-1 min-w-max py-1.5 px-3 text-xs font-semibold rounded-lg transition-all duration-150 whitespace-nowrap ${
                filter === key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              {label}
              {count > 0 && (
                <span className={`ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                  filter === key ? 'bg-slate-100 text-slate-700' : 'bg-slate-200/60 text-slate-500'
                }`}>
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Skeletons */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {/* Empty */}
      {!loading && filtered.length === 0 && (
        <EmptyState filtered={filter !== 'all'} onNewTicket={onNewTicket} />
      )}

      {/* Ticket groups */}
      {!loading && filtered.length > 0 && (
        <div className="space-y-6">
          {groups.map(({ label, items }) => (
            <div key={label}>
              <div className="flex items-center gap-3 mb-3">
                <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">{label}</p>
                <div className="flex-1 h-px bg-slate-100" />
                <span className="text-[11px] font-semibold text-slate-300">{items.length}</span>
              </div>
              <div className="space-y-2">
                {items.map((t) => (
                  <TicketCard
                    key={t.ticket_id}
                    t={t}
                    isOpen={expanded === t.ticket_id}
                    onToggle={() => setExpanded(expanded === t.ticket_id ? null : t.ticket_id)}
                    onRetry={onRetry}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {!loading && total > LIMIT && (
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-slate-100">
          <span className="text-xs text-slate-400">
            {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
          </span>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => load(Math.max(0, offset - LIMIT))}
              className="text-xs font-semibold text-slate-600 border border-slate-200 rounded-xl px-3.5 py-1.5 hover:bg-slate-50 disabled:opacity-40 transition-all"
            >
              ← Previous
            </button>
            <button
              disabled={offset + LIMIT >= total}
              onClick={() => load(offset + LIMIT)}
              className="text-xs font-semibold text-slate-600 border border-slate-200 rounded-xl px-3.5 py-1.5 hover:bg-slate-50 disabled:opacity-40 transition-all"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
