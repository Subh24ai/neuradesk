import { useCallback, useEffect, useRef, useState } from 'react'
import { CATEGORY_LABEL, statusMeta } from '../lib/tickets'

interface OrgInfo {
  id: string
  name: string
  slug: string
  created_at: string
}

interface Invite {
  id: string
  code: string
  note: string | null
  used_at: string | null
  used_by_email: string | null
  expires_at: string | null
  created_at: string
}

interface Member {
  id: string
  email: string
  role: string
  first_name?: string
  last_name?: string
  is_active?: boolean
  created_at: string
}

interface TicketRow {
  ticket_id: string
  status: string
  category: string | null
  confidence: number | null
  resolution: string | null
  escalation_reason: string | null
  admin_note: string | null
  assignee_group: string | null
  priority: string | null
  user_email: string | null
  raw_text: string | null
  created_at: string
}

interface Stats {
  total: number
  resolved: number
  auto_resolved: number
  human_resolved: number
  escalated: number
  pending: number
  processing: number
  failed: number
  awaiting_confirmation: number
}

interface Comment {
  id: string
  ticket_id: string
  content: string
  is_admin_note: boolean
  created_at: string
}

interface KbDoc {
  id: string
  title: string
  content: string
  source_type?: string | null
  file_name?: string | null
  created_at: string
}

interface Props {
  token: string
  /** The signed-in admin — they can't change their own role or access. */
  currentUserId: string
  onNewTicket: () => void
  onToast?: (message: string, variant?: 'success' | 'error' | 'info') => void
}

type Toast = (msg: string, v?: 'success' | 'error' | 'info') => void

// Admin-facing wording for statuses (the employee screens say "With support team").
const ADMIN_STATUS_LABEL: Record<string, string> = {
  escalated: 'Needs review',
  awaiting_confirmation: 'Waiting on employee',
}

function adminStatusLabel(status: string): string {
  return ADMIN_STATUS_LABEL[status] ?? statusMeta(status).label
}

/** "5m ago" for past times, "in 7d" for future ones (e.g. invite expiry). */
function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const future = diff < 0
  const m = Math.floor(Math.abs(diff) / 60_000)
  if (m < 1) return future ? 'in under a minute' : 'just now'
  const h = Math.floor(m / 60)
  const span = m < 60 ? `${m}m` : h < 24 ? `${h}h` : `${Math.round(m / 1440)}d`
  return future ? `in ${span}` : `${span} ago`
}

function Svg({ d, className = 'h-4 w-4' }: { d: string; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  )
}

const I = {
  check: 'M4.5 12.75l6 6 9-13.5',
  shield: 'M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z',
  bolt: 'M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z',
  clock: 'M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z',
  inbox: 'M2.25 13.5h3.86a2.25 2.25 0 012.012 1.244l.256.512a2.25 2.25 0 002.013 1.244h3.218a2.25 2.25 0 002.013-1.244l.256-.512a2.25 2.25 0 012.013-1.244h3.859m-19.5.338V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H6.911a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661z',
  book: 'M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25',
  users: 'M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z',
  plus: 'M12 4.5v15m7.5-7.5h-15',
  search: 'M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z',
  chevron: 'M19.5 8.25l-7.5 7.5-7.5-7.5',
  upload: 'M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5',
  ticket: 'M16.5 6v.75m0 3v.75m0 3v.75m0 3V18m-9-5.25h5.25M7.5 15h3M3.375 5.25c-.621 0-1.125.504-1.125 1.125v3.026a2.999 2.999 0 010 5.198v3.026c0 .621.504 1.125 1.125 1.125h17.25c.621 0 1.125-.504 1.125-1.125v-3.026a2.999 2.999 0 010-5.198V6.375c0-.621-.504-1.125-1.125-1.125H3.375z',
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })}
      className={`inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg border transition-all ${
        copied ? 'bg-emerald-50 border-emerald-200 text-emerald-700' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300 hover:shadow-sm'
      }`}
    >
      {copied ? (
        <><svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 00-1.414 0L8 12.586 4.707 9.293a1 1 0 00-1.414 1.414l4 4a1 1 0 001.414 0l8-8a1 1 0 000-1.414z" clipRule="evenodd" /></svg>Copied</>
      ) : (
        <><svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path d="M7 3.5A1.5 1.5 0 018.5 2h3.879a1.5 1.5 0 011.06.44l3.122 3.12A1.5 1.5 0 0117 6.622V12.5a1.5 1.5 0 01-1.5 1.5h-1v-3.379a3 3 0 00-.879-2.121L10.5 5.379A3 3 0 008.379 4.5H7v-1z" /><path d="M4.5 6A1.5 1.5 0 003 7.5v9A1.5 1.5 0 004.5 18h7a1.5 1.5 0 001.5-1.5v-5.879a1.5 1.5 0 00-.44-1.06L9.44 6.439A1.5 1.5 0 008.378 6H4.5z" /></svg>Copy</>
      )}
    </button>
  )
}

// ── Resolve panel (shared by the review queue and All tickets) ──────────────

function ResolvePanel({ ticket, token, onDone, onToast }: {
  ticket: TicketRow; token: string
  onDone: (updated: TicketRow) => void
  onToast?: Toast
}) {
  const [reply, setReply] = useState(ticket.admin_note || '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [posting, setPosting] = useState(false)
  const json = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  const needsReply = !reply.trim()

  useEffect(() => {
    fetch(`/admin/tickets/${ticket.ticket_id}/comments`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : { comments: [] }))
      .then((d) => setComments(d.comments || []))
      .catch(() => { /* non-critical */ })
  }, [ticket.ticket_id, token])

  async function update(newStatus: 'resolved' | 'escalated') {
    setSaving(true); setError(null)
    try {
      const r = await fetch(`/admin/tickets/${ticket.ticket_id}`, {
        method: 'PATCH', headers: json,
        body: JSON.stringify({ status: newStatus, admin_note: reply.trim() || undefined }),
      })
      if (!r.ok) throw new Error((await r.json()).detail?.error ?? `HTTP ${r.status}`)
      onDone(await r.json())
      onToast?.(newStatus === 'resolved' ? 'Resolved — the employee can see your reply.' : 'Moved to the review queue.', 'success')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update')
    } finally {
      setSaving(false)
    }
  }

  async function postComment() {
    if (!newComment.trim()) return
    setPosting(true)
    try {
      const r = await fetch(`/admin/tickets/${ticket.ticket_id}/comments`, {
        method: 'POST', headers: json, body: JSON.stringify({ content: newComment.trim() }),
      })
      if (r.ok) { const c = await r.json(); setComments((p) => [...p, c]); setNewComment('') }
      else onToast?.('Could not send the message.', 'error')
    } finally {
      setPosting(false)
    }
  }

  return (
    <div className="mt-4 space-y-4 border-t border-slate-100 pt-4 fade-in">
      <div>
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
          <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-slate-400">What the agents found</p>
          <p className="text-sm text-slate-700">
            {ticket.category ? (CATEGORY_LABEL[ticket.category] ?? ticket.category) : 'Uncategorised'}
            {ticket.confidence != null && <span className="text-slate-400"> · {Math.round(ticket.confidence * 100)}% confidence</span>}
          </p>
          {ticket.escalation_reason && <p className="mt-1 text-xs leading-relaxed text-amber-700">{ticket.escalation_reason}</p>}
          {ticket.resolution && (
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              {ticket.status === 'escalated' ? 'AI draft — not shown to the employee: ' : 'Current reply: '}{ticket.resolution}
            </p>
          )}
        </div>
      </div>

      <div>
        <label htmlFor={`reply-${ticket.ticket_id}`} className="mb-1.5 block text-xs font-bold text-slate-700">Reply to employee</label>
        <textarea
          id={`reply-${ticket.ticket_id}`}
          rows={3}
          value={reply}
          onChange={(e) => setReply(e.target.value)}
          placeholder="Explain what you did or what they should do next…"
          className="w-full resize-none rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
        <p className="mt-1 text-[11px] text-slate-400">Shown on the employee’s ticket when you resolve it.</p>
      </div>
      {error && <p role="alert" className="text-xs font-medium text-red-600">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => update('resolved')}
          disabled={saving || needsReply}
          title={needsReply ? 'Write a reply first so the employee knows the outcome' : undefined}
          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-sm transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
        >
          <Svg d={I.check} className="h-3.5 w-3.5" /> {saving ? 'Saving…' : 'Resolve with reply'}
        </button>
        {ticket.status !== 'escalated' && (
          <button
            onClick={() => update('escalated')}
            disabled={saving}
            className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-xs font-bold text-amber-800 transition-colors hover:bg-amber-100 disabled:opacity-50"
          >
            Move to review queue
          </button>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3">
        <p className="mb-2 text-xs font-bold text-slate-700">
          Messages <span className="font-normal text-slate-400">· visible to the employee</span>
        </p>
        {comments.length > 0 && (
          <ul className="mb-3 max-h-48 space-y-2 overflow-y-auto">
            {comments.map((c) => (
              <li key={c.id} className="rounded-lg border border-slate-100 bg-white px-3 py-2">
                <p className="text-xs leading-relaxed text-slate-700">{c.content}</p>
                <p className="mt-0.5 text-[10px] text-slate-400">{relativeTime(c.created_at)}</p>
              </li>
            ))}
          </ul>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') postComment() }}
            placeholder="Ask a question or share an update…"
            aria-label="Message to the employee"
            className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
          <button
            onClick={postComment}
            disabled={posting || !newComment.trim()}
            className="rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-bold text-white transition-colors hover:bg-indigo-700 disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}


// ── Invites panel ────────────────────────────────────────────────────────────

function inviteStatus(inv: Invite): 'available' | 'used' | 'expired' {
  if (inv.used_at) return 'used'
  if (inv.expires_at && new Date(inv.expires_at) < new Date()) return 'expired'
  return 'available'
}

function InvitesPanel({ token, invites, onInvitesChange, onToast }: {
  token: string
  invites: Invite[]
  onInvitesChange: (invites: Invite[]) => void
  onToast?: (msg: string, v?: 'success' | 'error' | 'info') => void
}) {
  const [creating, setCreating] = useState(false)
  const [note, setNote] = useState('')
  const [expiresDays, setExpiresDays] = useState(7)
  const [revoking, setRevoking] = useState<string | null>(null)
  const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  async function handleCreate() {
    setCreating(true)
    try {
      const r = await fetch('/admin/invites', {
        method: 'POST', headers,
        body: JSON.stringify({ note: note.trim() || null, expires_days: expiresDays }),
      })
      if (!r.ok) throw new Error()
      const inv: Invite = await r.json()
      onInvitesChange([inv, ...invites])
      setNote('')
      onToast?.('Invite created — copy the code and share it', 'success')
    } catch {
      onToast?.('Failed to create invite', 'error')
    } finally {
      setCreating(false)
    }
  }

  async function handleRevoke(id: string) {
    setRevoking(id)
    try {
      const r = await fetch(`/admin/invites/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } })
      if (!r.ok) throw new Error()
      onInvitesChange(invites.filter(i => i.id !== id))
      onToast?.('Invite revoked', 'info')
    } catch {
      onToast?.('Failed to revoke invite', 'error')
    } finally {
      setRevoking(null)
    }
  }

  const STATUS_STYLE = {
    available: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    used:      'bg-slate-100 text-slate-500 border-slate-200',
    expired:   'bg-red-50 text-red-600 border-red-200',
  }

  return (
    <div className="space-y-4">
      {/* Create invite */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-900">Generate invite</h3>
          <p className="text-xs text-slate-400 mt-0.5">Each code is unique and can only be used once — by one person.</p>
        </div>
        <div className="px-5 py-4 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[180px]">
            <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-1.5">
              Label <span className="normal-case font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder="e.g. For Alice from Marketing"
              maxLength={200}
              className="w-full text-sm border border-slate-200 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 hover:border-slate-300 transition-shadow bg-slate-50/50 focus:bg-white"
            />
          </div>
          <div className="w-32">
            <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-widest mb-1.5">Expires in</label>
            <select
              value={expiresDays}
              onChange={e => setExpiresDays(Number(e.target.value))}
              className="w-full text-sm border border-slate-200 rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-slate-50/50 focus:bg-white"
            >
              {[1, 3, 7, 14, 30].map(d => (
                <option key={d} value={d}>{d} day{d > 1 ? 's' : ''}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleCreate}
            disabled={creating}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-xl px-4 py-2.5 disabled:opacity-40 transition-colors shadow-sm"
          >
            {creating ? (
              <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            ) : (
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z"/></svg>
            )}
            Generate invite
          </button>
        </div>
      </div>

      {/* Invite list */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <h3 className="text-sm font-bold text-slate-900">
            All invites
            <span className="text-slate-400 font-normal ml-2 text-xs">({invites.length})</span>
          </h3>
        </div>

        {invites.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <div className="w-10 h-10 bg-slate-100 rounded-xl flex items-center justify-center mx-auto mb-3">
              <svg className="w-5 h-5 text-slate-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M13 4.5a2.5 2.5 0 11.702 1.737L6.97 9.604a2.518 2.518 0 010 .792l6.733 3.367a2.5 2.5 0 11-.671 1.341l-6.733-3.367a2.5 2.5 0 110-3.475l6.733-3.366A2.52 2.52 0 0113 4.5z" />
              </svg>
            </div>
            <p className="text-sm text-slate-500 font-medium">No invites yet</p>
            <p className="text-xs text-slate-400 mt-1">Generate an invite above to share with a teammate.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {invites.map(inv => {
              const st = inviteStatus(inv)
              return (
                <div key={inv.id} className="px-5 py-4 flex items-center gap-4 hover:bg-slate-50/60 transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <code className="text-xs font-mono text-slate-700 bg-slate-100 rounded-lg px-2 py-0.5 tracking-wide select-all">
                        {inv.code}
                      </code>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border capitalize ${STATUS_STYLE[st]}`}>
                        {st}
                      </span>
                    </div>
                    {inv.note && <p className="text-xs text-slate-500 font-medium truncate">{inv.note}</p>}
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      {st === 'used'
                        ? `Used by ${inv.used_by_email} · ${relativeTime(inv.used_at!)}`
                        : inv.expires_at
                          ? `Expires ${relativeTime(inv.expires_at)}`
                          : 'No expiry'}
                      {' · '}Created {relativeTime(inv.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {st === 'available' && <CopyButton text={inv.code} />}
                    {st === 'available' && (
                      <button
                        onClick={() => handleRevoke(inv.id)}
                        disabled={revoking === inv.id}
                        className="text-xs text-red-400 hover:text-red-600 border border-red-100 hover:border-red-200 rounded-lg px-2.5 py-1.5 hover:bg-red-50 transition-all font-semibold disabled:opacity-40"
                      >
                        {revoking === inv.id ? '…' : 'Revoke'}
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}


// ── Knowledge base panel ──────────────────────────────────────────────────────

const KB_ACCEPT = '.pdf,.txt,.md,.docx'

/** One file waiting in (or going through) the knowledge-base upload queue. */
interface QueueItem {
  id: string
  file: File
  title: string
  status: 'ready' | 'uploading' | 'done' | 'error'
  error?: string
  /** A document with this file name or title is already in the knowledge base. */
  duplicate?: boolean
}
const KB_MAX_MB = 10

const FILE_TYPE_BADGE: Record<string, { label: string; cls: string }> = {
  pdf:  { label: 'PDF',  cls: 'bg-red-50 text-red-600 border-red-200' },
  txt:  { label: 'TXT',  cls: 'bg-slate-100 text-slate-600 border-slate-200' },
  md:   { label: 'MD',   cls: 'bg-purple-50 text-purple-600 border-purple-200' },
  docx: { label: 'DOCX', cls: 'bg-blue-50 text-blue-600 border-blue-200' },
}

function fileExt(name: string): string {
  return name.includes('.') ? name.split('.').pop()!.toLowerCase() : ''
}

function KnowledgeBasePanel({ token, onToast, onCountChange }: {
  token: string
  onToast?: (msg: string, v?: 'success' | 'error' | 'info') => void
  /** Reports the document count so the setup checklist can tick itself off. */
  onCountChange?: (count: number) => void
}) {
  const [docs, setDocs] = useState<KbDoc[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { if (!loading) onCountChange?.(docs.length) }, [docs, loading]) // eslint-disable-line react-hooks/exhaustive-deps
  const [mode, setMode] = useState<'write' | 'upload'>('write')

  // write mode
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [writeError, setWriteError] = useState<string | null>(null)

  // upload mode — a queue so several files can be added and uploaded together
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const authHeaders = { Authorization: `Bearer ${token}` }

  useEffect(() => {
    fetch('/admin/kb', { headers: authHeaders })
      .then(r => r.ok ? r.json() : { docs: [] })
      .then(d => { setDocs(d.docs || []); setLoading(false) })
  }, [token])

  // ── Write ──────────────────────────────────────────────────────────────────

  async function handleAdd() {
    if (!title.trim() || !content.trim()) return
    setSaving(true); setWriteError(null)
    try {
      const r = await fetch('/admin/kb', {
        method: 'POST',
        headers: { ...authHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim(), content: content.trim() }),
      })
      if (!r.ok) throw new Error((await r.json()).detail?.error ?? `HTTP ${r.status}`)
      const doc: KbDoc = await r.json()
      setDocs(prev => [doc, ...prev])
      setTitle(''); setContent('')
      onToast?.('Document added to knowledge base', 'success')
    } catch (e) {
      setWriteError(e instanceof Error ? e.message : 'Failed to add document')
    } finally {
      setSaving(false)
    }
  }

  // ── Upload ─────────────────────────────────────────────────────────────────

  /** Validate and queue the chosen files; invalid ones stay visible with the reason. */
  function addFiles(files: FileList | File[]) {
    const known = new Set(docs.flatMap(d => [d.file_name?.toLowerCase(), d.title.toLowerCase()]).filter(Boolean))
    // Copy now: a FileList is live and is emptied when the input is reset below,
    // before React runs the state updater.
    const picked = Array.from(files)
    setQueue(prev => {
      const next = [...prev]
      for (const file of picked) {
        if (next.some(q => q.file.name === file.name && q.file.size === file.size)) continue // picked twice
        const ext = fileExt(file.name)
        const title = file.name.replace(/\.[^.]+$/, '')
        let error: string | undefined
        if (!['pdf', 'txt', 'md', 'docx'].includes(ext)) error = `Unsupported type ".${ext}" — use PDF, TXT, MD or DOCX`
        else if (file.size > KB_MAX_MB * 1024 * 1024) error = `Too large (${(file.size / 1_048_576).toFixed(1)} MB) — max ${KB_MAX_MB} MB`
        else if (file.size === 0) error = 'File is empty'
        next.push({
          id: `${file.name}-${file.size}-${file.lastModified}`,
          file, title,
          status: error ? 'error' : 'ready',
          error,
          duplicate: !error && (known.has(file.name.toLowerCase()) || known.has(title.toLowerCase())),
        })
      }
      return next
    })
    if (fileInputRef.current) fileInputRef.current.value = '' // allow re-picking the same file
  }

  function updateItem(id: string, patch: Partial<QueueItem>) {
    setQueue(prev => prev.map(q => q.id === id ? { ...q, ...patch } : q))
  }

  async function handleUploadAll() {
    const pending = queue.filter(q => q.status === 'ready')
    if (!pending.length) return
    setUploading(true)
    let added = 0
    // One at a time: keeps the server load predictable and the progress readable.
    for (const item of pending) {
      updateItem(item.id, { status: 'uploading', error: undefined })
      try {
        const form = new FormData()
        form.append('file', item.file)
        if (item.title.trim()) form.append('title', item.title.trim())
        const r = await fetch('/admin/kb/upload', { method: 'POST', headers: authHeaders, body: form })
        if (!r.ok) {
          const body = await r.json().catch(() => ({}))
          throw new Error(body?.detail?.error ?? (r.status >= 500 ? 'Server error — try again' : `HTTP ${r.status}`))
        }
        const doc: KbDoc = await r.json()
        setDocs(prev => [doc, ...prev])
        updateItem(item.id, { status: 'done' })
        added++
      } catch (e) {
        updateItem(item.id, { status: 'error', error: e instanceof Error ? e.message : 'Upload failed' })
      }
    }
    setUploading(false)
    const failed = pending.length - added
    // Clear the ones that made it; keep failures on screen with their reason.
    setTimeout(() => setQueue(prev => prev.filter(q => q.status !== 'done')), 1200)
    if (failed === 0) onToast?.(`${added} document${added === 1 ? '' : 's'} added to the knowledge base`, 'success')
    else onToast?.(`${added} added, ${failed} failed — see the list for details`, added ? 'info' : 'error')
  }

  // ── Delete ─────────────────────────────────────────────────────────────────

  async function handleDelete(id: string) {
    await fetch(`/admin/kb/${id}`, { method: 'DELETE', headers: authHeaders })
    setDocs(prev => prev.filter(d => d.id !== id))
    onToast?.('Document deleted', 'info')
  }

  if (loading) return <div className="bg-white rounded-2xl border border-slate-200 h-24 animate-pulse" />

  return (
    <div className="space-y-4">
      {/* Add / Upload card */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h3 className="text-sm font-bold text-slate-900">Add to knowledge base</h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Documents are searched by AI agents when resolving tickets.
              </p>
            </div>
            {/* Mode toggle */}
            <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5 flex-shrink-0">
              {(['write', 'upload'] as const).map(m => (
                <button
                  key={m}
                  onClick={() => { setMode(m); setWriteError(null) }}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all capitalize ${
                    mode === m ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {m === 'write' ? 'Write' : 'Upload file'}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Write mode */}
        {mode === 'write' && (
          <div className="px-5 py-4 space-y-3">
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="Title (e.g. VPN Setup Guide, Leave Policy 2025)"
              className="w-full text-sm border border-slate-200 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 hover:border-slate-300 transition-shadow bg-slate-50/50 focus:bg-white"
            />
            <textarea
              rows={5}
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder="Paste your company policy, IT runbook, HR procedure, or any other knowledge here…"
              className="w-full text-sm border border-slate-200 rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 hover:border-slate-300 transition-shadow resize-none bg-slate-50/50 focus:bg-white"
            />
            {writeError && <p className="text-xs text-red-600 font-medium">{writeError}</p>}
            <button
              onClick={handleAdd}
              disabled={saving || !title.trim() || !content.trim()}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl px-4 py-2.5 transition-colors disabled:opacity-40 shadow-sm"
            >
              {saving ? (
                <><svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Saving…</>
              ) : (
                <><svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z"/></svg>Add document</>
              )}
            </button>
          </div>
        )}

        {/* Upload mode */}
        {mode === 'upload' && (
          <div className="px-5 py-4 space-y-3">
            {/* Drop zone — accepts several files; stays available to add more */}
            <div
              role="button"
              tabIndex={0}
              aria-label="Choose files to upload"
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click() } }}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files) }}
              onClick={() => fileInputRef.current?.click()}
              className={`relative cursor-pointer rounded-xl border-2 border-dashed text-center transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                queue.length ? 'px-4 py-3' : 'px-5 py-8'
              } ${dragging ? 'border-indigo-400 bg-indigo-50' : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50'}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={KB_ACCEPT}
                className="hidden"
                onChange={e => { if (e.target.files?.length) addFiles(e.target.files) }}
              />
              {queue.length ? (
                <p className="text-xs font-semibold text-slate-500">
                  <span className="text-indigo-600">+ Add more files</span> — or drop them here
                </p>
              ) : (
                <>
                  <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                    <svg className="w-5 h-5 text-slate-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                      <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <p className="text-sm font-semibold text-slate-700">Drop files here or click to browse</p>
                  <p className="text-xs text-slate-400 mt-1">Select several at once · PDF, TXT, MD, DOCX — up to {KB_MAX_MB} MB each</p>
                </>
              )}
            </div>

            {/* Queue */}
            {queue.length > 0 && (
              <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200" aria-label="Files to upload">
                {queue.map(item => (
                  <li key={item.id} className="flex items-center gap-3 px-3.5 py-2.5">
                    <span className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      item.status === 'error' ? 'bg-red-50 text-red-500'
                        : item.status === 'done' ? 'bg-emerald-50 text-emerald-600'
                        : 'bg-slate-100 text-slate-500'
                    }`} aria-hidden="true">
                      {item.status === 'uploading' ? (
                        <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                      ) : item.status === 'done' ? (
                        <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" /></svg>
                      ) : (
                        <span className="text-[10px] font-bold uppercase">{fileExt(item.file.name) || '?'}</span>
                      )}
                    </span>
                    <div className="flex-1 min-w-0">
                      {item.status === 'ready' ? (
                        <input
                          type="text"
                          value={item.title}
                          onChange={e => updateItem(item.id, { title: e.target.value })}
                          aria-label={`Title for ${item.file.name}`}
                          className="w-full text-sm font-semibold text-slate-800 bg-transparent border-0 border-b border-transparent hover:border-slate-200 focus:border-indigo-400 focus:outline-none px-0 py-0.5"
                        />
                      ) : (
                        <p className="text-sm font-semibold text-slate-800 truncate">{item.title || item.file.name}</p>
                      )}
                      <p className={`text-xs truncate ${item.status === 'error' ? 'text-red-600' : item.duplicate && item.status === 'ready' ? 'text-amber-600' : 'text-slate-400'}`}>
                        {item.status === 'error' ? item.error
                          : item.status === 'uploading' ? 'Uploading and extracting…'
                          : item.status === 'done' ? 'Added'
                          : item.duplicate ? `${item.file.name} · Already in the knowledge base — uploading adds a second copy`
                          : `${item.file.name} · ${Math.max(1, Math.round(item.file.size / 1024))} KB`}
                      </p>
                    </div>
                    {(item.status === 'ready' || item.status === 'error') && !uploading && (
                      <button
                        type="button"
                        onClick={() => setQueue(prev => prev.filter(q => q.id !== item.id))}
                        aria-label={`Remove ${item.file.name}`}
                        className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 flex-shrink-0"
                      >
                        <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" /></svg>
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={handleUploadAll}
                disabled={uploading || queue.filter(q => q.status === 'ready').length === 0}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl px-4 py-2.5 transition-colors disabled:opacity-40 shadow-sm"
              >
                {uploading ? (
                  <><svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Uploading…</>
                ) : (
                  <><svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM6.293 6.707a1 1 0 010-1.414l3-3a1 1 0 011.414 0l3 3a1 1 0 01-1.414 1.414L11 5.414V13a1 1 0 11-2 0V5.414L7.707 6.707a1 1 0 01-1.414 0z" clipRule="evenodd" /></svg>
                  {queue.filter(q => q.status === 'ready').length > 1 ? `Upload ${queue.filter(q => q.status === 'ready').length} documents` : 'Upload document'}</>
                )}
              </button>
              {queue.some(q => q.status === 'error') && !uploading && (
                <button type="button" onClick={() => setQueue(prev => prev.filter(q => q.status !== 'error'))}
                  className="text-xs font-semibold text-slate-500 hover:text-slate-800">
                  Clear failed
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Doc list */}
      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-900">
            Documents
            <span className="text-slate-400 font-normal ml-2 text-xs">({docs.length})</span>
          </h3>
          <p className="text-xs text-slate-400">Searched by AI on every ticket</p>
        </div>
        {docs.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <div className="w-12 h-12 bg-slate-100 rounded-2xl flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-slate-700">No documents yet</p>
            <p className="text-xs text-slate-400 mt-1 max-w-[220px] mx-auto">
              Add your company policies, IT runbooks, and HR procedures above.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {docs.map(doc => {
              const ext = doc.file_name ? fileExt(doc.file_name) : ''
              const badge = FILE_TYPE_BADGE[ext]
              return (
                <div key={doc.id} className="px-5 py-4 flex items-start justify-between gap-4 hover:bg-slate-50/60 transition-colors">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <p className="text-sm font-semibold text-slate-800">{doc.title}</p>
                      {badge && (
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border flex-shrink-0 ${badge.cls}`}>
                          {badge.label}
                        </span>
                      )}
                      {doc.source_type === 'upload' && !badge && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded border bg-slate-100 text-slate-500 border-slate-200">
                          FILE
                        </span>
                      )}
                    </div>
                    {doc.file_name && (
                      <p className="text-[11px] text-slate-400 font-mono mb-0.5 truncate">{doc.file_name}</p>
                    )}
                    <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                      {doc.content.slice(0, 140)}{doc.content.length > 140 ? '…' : ''}
                    </p>
                    <p className="text-[10px] text-slate-300 mt-1.5 font-medium">{relativeTime(doc.created_at)}</p>
                  </div>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="flex-shrink-0 text-xs text-red-400 hover:text-red-600 border border-red-100 hover:border-red-200 rounded-lg px-2.5 py-1.5 hover:bg-red-50 transition-all font-semibold"
                  >
                    Delete
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Escalated queue ───────────────────────────────────────────────────────────

const PRIORITY_CONFIG: Record<string, { badge: string; label: string }> = {
  CRITICAL: { badge: 'bg-red-100 text-red-700 border-red-200',    label: 'Critical' },
  HIGH:     { badge: 'bg-orange-100 text-orange-700 border-orange-200', label: 'High' },
  MEDIUM:   { badge: 'bg-amber-100 text-amber-700 border-amber-200',  label: 'Medium' },
  LOW:      { badge: 'bg-slate-100 text-slate-600 border-slate-200',   label: 'Low'  },
}

const GROUP_CONFIG: Record<string, { icon: string; label: string; cls: string }> = {
  'sre-oncall':    { icon: 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z', label: 'SRE On-call',   cls: 'text-red-600 bg-red-50 border-red-200' },
  'tier-2-support':{ icon: 'M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z', label: 'Tier-2 Support', cls: 'text-orange-600 bg-orange-50 border-orange-200' },
  'tier-1-support':{ icon: 'M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z', label: 'Tier-1 Support', cls: 'text-indigo-600 bg-indigo-50 border-indigo-200' },
}



// ── Review queue ─────────────────────────────────────────────────────────────

const PRIORITY_RANK: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }

/** Highest priority first, then oldest first — the order a support team should work in. */
function triageOrder(a: TicketRow, b: TicketRow): number {
  const pa = PRIORITY_RANK[(a.priority ?? 'MEDIUM').toUpperCase()] ?? 2
  const pb = PRIORITY_RANK[(b.priority ?? 'MEDIUM').toUpperCase()] ?? 2
  return pa - pb || new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
}

function ReviewQueue({ tickets, loading, token, onToast, onChanged }: {
  tickets: TicketRow[]; loading: boolean; token: string
  onToast?: Toast
  onChanged: () => void
}) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [priority, setPriority] = useState('')

  if (loading) return <div className="h-40 animate-pulse rounded-2xl border border-slate-200 bg-white" />

  if (tickets.length === 0) {
    return (
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-6 py-10 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
          <Svg d={I.check} className="h-6 w-6" />
        </div>
        <p className="font-bold text-emerald-900">All clear</p>
        <p className="mt-1 text-sm text-emerald-700">Nothing needs review. New escalations appear here instantly — no refresh needed.</p>
      </div>
    )
  }

  const counts = (p: string) => tickets.filter((t) => (t.priority ?? 'MEDIUM').toUpperCase() === p).length
  const shown = [...tickets].filter((t) => !priority || (t.priority ?? 'MEDIUM').toUpperCase() === priority).sort(triageOrder)

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
        <p className="text-sm text-slate-600">
          <span className="font-bold text-slate-900">{tickets.length} need{tickets.length === 1 ? 's' : ''} review</span>
          <span className="text-slate-400"> · highest priority and oldest first</span>
        </p>
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filter by priority">
          {['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].filter((p) => !p || counts(p) > 0).map((p) => (
            <button
              key={p || 'all'}
              role="tab"
              aria-selected={priority === p}
              onClick={() => setPriority(p)}
              className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                priority === p ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
              }`}
            >
              {p ? `${PRIORITY_CONFIG[p].label} ${counts(p)}` : `All ${tickets.length}`}
            </button>
          ))}
        </div>
      </div>
      <ul className="divide-y divide-slate-100">
        {shown.map((t) => {
          const p = (t.priority ?? 'MEDIUM').toUpperCase()
          const pc = PRIORITY_CONFIG[p] ?? PRIORITY_CONFIG.MEDIUM
          const gc = GROUP_CONFIG[t.assignee_group ?? 'tier-1-support'] ?? GROUP_CONFIG['tier-1-support']
          const open = expanded === t.ticket_id
          return (
            <li key={t.ticket_id} className={`px-5 py-4 ${open ? 'bg-slate-50/60' : ''}`}>
              <button onClick={() => setExpanded(open ? null : t.ticket_id)} aria-expanded={open} className="flex w-full items-start gap-3 text-left">
                <span className="min-w-0 flex-1">
                  <span className="mb-1.5 flex flex-wrap items-center gap-1.5">
                    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${pc.badge}`}>{pc.label}</span>
                    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${gc.cls}`}>{gc.label}</span>
                    <span className="text-[11px] text-slate-400">waiting {relativeTime(t.created_at).replace(' ago', '')}</span>
                  </span>
                  <span className="block text-sm font-semibold leading-snug text-slate-900">{t.raw_text ?? '—'}</span>
                  <span className="mt-1 block text-xs text-slate-500">
                    {t.user_email ?? 'Unknown employee'}
                    {t.category && <> · {CATEGORY_LABEL[t.category] ?? t.category}</>}
                  </span>
                  {t.escalation_reason && !open && <span className="mt-1.5 block text-xs text-amber-700">Why: {t.escalation_reason}</span>}
                </span>
                <span className="flex-shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700">
                  {open ? 'Close' : 'Review'}
                </span>
              </button>
              {open && (
                <ResolvePanel ticket={t} token={token} onToast={onToast} onDone={() => { setExpanded(null); onChanged() }} />
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ── All tickets ──────────────────────────────────────────────────────────────

const ALL_FILTERS: { key: string; label: string; statuses: string[]; count: (s: Stats) => number }[] = [
  { key: 'all', label: 'All', statuses: [], count: (s) => s.total },
  { key: 'review', label: 'Needs review', statuses: ['escalated'], count: (s) => s.escalated },
  { key: 'waiting', label: 'Waiting on employee', statuses: ['awaiting_confirmation'], count: (s) => s.awaiting_confirmation },
  { key: 'resolved', label: 'Resolved', statuses: ['resolved'], count: (s) => s.resolved },
  { key: 'progress', label: 'In progress', statuses: ['pending', 'processing'], count: (s) => s.pending + s.processing },
  { key: 'failed', label: 'Failed', statuses: ['failed'], count: (s) => s.failed },
]

function AllTickets({ token, stats, version, onToast, onChanged }: {
  token: string; stats: Stats | null; version: number
  onToast?: Toast
  onChanged: () => void
}) {
  const LIMIT = 20
  const [tickets, setTickets] = useState<TicketRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => { const id = setTimeout(() => setQ(query.trim()), 300); return () => clearTimeout(id) }, [query])

  const load = useCallback(async (newOffset: number, silent = false) => {
    if (!silent) setLoading(true)
    try {
      const params = new URLSearchParams({ limit: String(LIMIT), offset: String(newOffset) })
      const st = ALL_FILTERS.find((f) => f.key === filter)!.statuses
      if (st.length) params.set('status', st.join(','))
      if (q) params.set('q', q)
      const r = await fetch(`/admin/tickets?${params}`, { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) { const d = await r.json(); setTickets(d.tickets); setTotal(d.total); setOffset(newOffset) }
    } finally {
      if (!silent) setLoading(false)
    }
  }, [token, filter, q])

  useEffect(() => { load(0) }, [load])
  useEffect(() => { if (version > 0) load(offset, true) }, [version]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <label className="relative block">
        <span className="sr-only">Search tickets</span>
        <Svg d={I.search} className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by request, reply, category or employee email…"
          className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-sm shadow-sm focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
      </label>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Filter by status">
        {ALL_FILTERS.filter((f) => f.key === 'all' || f.key === filter || (stats && f.count(stats) > 0)).map((f) => (
          <button
            key={f.key}
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => { setFilter(f.key); setExpanded(null) }}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
              filter === f.key ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
            }`}
          >
            {f.label}
            {stats && <span className={`rounded-full px-1.5 text-[10px] ${filter === f.key ? 'bg-white/20' : 'bg-slate-100'}`}>{f.count(stats)}</span>}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-xl border border-slate-200 bg-white" />)}</div>
      ) : tickets.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
          <p className="font-semibold text-slate-800">{q ? `No tickets match “${q}”` : 'No tickets here yet'}</p>
          {(q || filter !== 'all') && (
            <button onClick={() => { setQuery(''); setQ(''); setFilter('all') }} className="mt-3 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white">
          {tickets.map((t) => {
            const meta = statusMeta(t.status)
            const open = expanded === t.ticket_id
            return (
              <li key={t.ticket_id} className={`px-5 py-3.5 ${open ? 'bg-slate-50/60' : ''}`}>
                <button onClick={() => setExpanded(open ? null : t.ticket_id)} aria-expanded={open} className="flex w-full items-start gap-3 text-left">
                  <span className={`mt-[7px] h-2 w-2 flex-shrink-0 rounded-full ${meta.dot}`} aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className={`block text-sm font-medium text-slate-900 ${open ? '' : 'truncate'}`}>{t.raw_text ?? '—'}</span>
                    <span className="mt-0.5 block truncate text-xs text-slate-500">
                      {t.user_email ?? 'Unknown'}{t.category && <> · {CATEGORY_LABEL[t.category] ?? t.category}</>} · {relativeTime(t.created_at)}
                    </span>
                  </span>
                  <span className={`flex-shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${meta.badge}`}>{adminStatusLabel(t.status)}</span>
                  <Svg d={I.chevron} className={`mt-1 h-4 w-4 flex-shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
                </button>
                {open && (
                  <ResolvePanel ticket={t} token={token} onToast={onToast} onDone={() => { setExpanded(null); load(offset, true); onChanged() }} />
                )}
              </li>
            )
          })}
        </ul>
      )}

      {!loading && total > LIMIT && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">{offset + 1}–{Math.min(offset + LIMIT, total)} of {total}</span>
          <div className="flex gap-2">
            <button disabled={offset === 0} onClick={() => load(Math.max(0, offset - LIMIT))} className="rounded-lg border border-slate-200 px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40">← Previous</button>
            <button disabled={offset + LIMIT >= total} onClick={() => load(offset + LIMIT)} className="rounded-lg border border-slate-200 px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40">Next →</button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Setup checklist & KPIs ───────────────────────────────────────────────────

function SetupChecklist({ steps, onDismiss }: {
  steps: { label: string; hint: string; done: boolean; action: string; onClick: () => void }[]
  onDismiss: () => void
}) {
  const done = steps.filter((s) => s.done).length
  return (
    <section className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white px-5 py-4" aria-labelledby="setup-h">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 id="setup-h" className="text-sm font-bold text-slate-900">Get your helpdesk ready</h3>
          <p className="text-xs text-slate-500">{done} of {steps.length} done</p>
        </div>
        <button onClick={onDismiss} className="text-xs font-semibold text-slate-400 hover:text-slate-600">Hide</button>
      </div>
      <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-indigo-100">
        <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${(done / steps.length) * 100}%` }} />
      </div>
      <ol className="grid gap-2.5 sm:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.label} className={`rounded-xl border px-3.5 py-3 ${s.done ? 'border-emerald-200 bg-emerald-50/60' : 'border-slate-200 bg-white'}`}>
            <div className="mb-1 flex items-center gap-2">
              <span className={`flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${s.done ? 'bg-emerald-500 text-white' : 'bg-slate-100 text-slate-500'}`}>
                {s.done ? <Svg d={I.check} className="h-3 w-3" /> : i + 1}
              </span>
              <span className={`text-sm font-semibold ${s.done ? 'text-emerald-800 line-through decoration-emerald-300' : 'text-slate-900'}`}>{s.label}</span>
            </div>
            <p className="mb-2 text-xs leading-relaxed text-slate-500">{s.hint}</p>
            {!s.done && (
              <button onClick={s.onClick} className="text-xs font-bold text-indigo-600 hover:text-indigo-800">{s.action} →</button>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}

function Kpi({ label, value, sub, icon, tone, onClick }: {
  label: string; value: string; sub: string; icon: string
  tone: 'rose' | 'emerald' | 'indigo' | 'slate' | 'amber'
  onClick?: () => void
}) {
  const t = {
    rose: 'bg-rose-100 text-rose-600', emerald: 'bg-emerald-100 text-emerald-600',
    indigo: 'bg-indigo-100 text-indigo-600', slate: 'bg-slate-100 text-slate-500', amber: 'bg-amber-100 text-amber-600',
  }[tone]
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={`rounded-2xl border border-slate-200 bg-white px-4 py-3.5 text-left shadow-sm transition-shadow ${onClick ? 'hover:shadow-md' : 'cursor-default'} ${tone === 'rose' ? 'ring-1 ring-rose-200' : ''}`}
    >
      <div className="flex items-center gap-2">
        <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${t}`}><Svg d={icon} className="h-4 w-4" /></span>
        <span className="text-xs font-semibold text-slate-500">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-extrabold tracking-tight text-slate-900">{value}</p>
      <p className="mt-0.5 text-[11px] text-slate-400">{sub}</p>
    </button>
  )
}

// ── Member row (role & access management) ───────────────────────────────────

function MemberRow({ m, isSelf, token, onToast, onChanged }: {
  m: Member; isSelf: boolean; token: string
  onToast?: Toast
  onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const active = m.is_active !== false
  const name = m.first_name ? `${m.first_name} ${m.last_name ?? ''}`.trim() : null
  const initials = (m.first_name?.[0] ?? m.email[0]).toUpperCase() + (m.last_name?.[0] ?? '').toUpperCase()

  async function update(body: { role?: string; is_active?: boolean }, done: string) {
    setBusy(true)
    try {
      const r = await fetch(`/orgs/members/${m.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) { onToast?.(d?.detail?.error ?? 'Could not update this member.', 'error'); return }
      onToast?.(done, 'success')
      onChanged()
    } finally {
      setBusy(false); setConfirming(false)
    }
  }

  return (
    <li className={`flex flex-wrap items-center justify-between gap-3 px-5 py-3 ${active ? '' : 'bg-slate-50'}`}>
      <div className="flex min-w-0 items-center gap-3">
        <span className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white ${active ? 'bg-gradient-to-br from-indigo-400 to-indigo-600' : 'bg-slate-300'}`}>{initials}</span>
        <div className="min-w-0">
          <p className={`truncate text-sm font-semibold ${active ? 'text-slate-900' : 'text-slate-500'}`}>
            {name ?? m.email}{isSelf && <span className="ml-1.5 text-xs font-normal text-slate-400">(you)</span>}
          </p>
          <p className="truncate text-xs text-slate-500">{name ? `${m.email} · ` : ''}joined {relativeTime(m.created_at)}</p>
        </div>
      </div>
      <div className="flex flex-shrink-0 items-center gap-2">
        {!active && <span className="rounded-full bg-slate-200 px-2.5 py-1 text-[11px] font-bold text-slate-600">Deactivated</span>}
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold capitalize ${m.role === 'admin' ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600'}`}>{m.role}</span>
        {!isSelf && active && !confirming && (
          <>
            <button
              onClick={() => update({ role: m.role === 'admin' ? 'member' : 'admin' }, m.role === 'admin' ? `${name ?? m.email} is now a member.` : `${name ?? m.email} is now an admin.`)}
              disabled={busy}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {m.role === 'admin' ? 'Make member' : 'Make admin'}
            </button>
            <button onClick={() => setConfirming(true)} disabled={busy}
              className="rounded-lg border border-red-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50">
              Deactivate
            </button>
          </>
        )}
        {!isSelf && active && confirming && (
          <span className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-700">Sign them out and block access?</span>
            <button onClick={() => update({ is_active: false }, `${name ?? m.email} has been deactivated and signed out.`)} disabled={busy}
              className="rounded-lg bg-red-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50">
              {busy ? 'Working…' : 'Deactivate'}
            </button>
            <button onClick={() => setConfirming(false)} className="px-1 text-xs font-semibold text-slate-500 hover:text-slate-700">Cancel</button>
          </span>
        )}
        {!isSelf && !active && (
          <button onClick={() => update({ is_active: true }, `${name ?? m.email} can sign in again.`)} disabled={busy}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
            Reactivate
          </button>
        )}
      </div>
    </li>
  )
}

// ── Main component ───────────────────────────────────────────────────────────

type AdminTab = 'review' | 'tickets' | 'kb' | 'people'

function dismissKey(orgId: string) { return `nd_setup_dismissed_${orgId}` }

export default function AdminDashboard({ token, currentUserId, onNewTicket, onToast }: Props) {
  const [org, setOrg] = useState<OrgInfo | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [members, setMembers] = useState<Member[]>([])
  const [invites, setInvites] = useState<Invite[]>([])
  const [kbCount, setKbCount] = useState<number | null>(null)
  const [queue, setQueue] = useState<TicketRow[]>([])
  const [queueLoading, setQueueLoading] = useState(true)
  const [loading, setLoading] = useState(true)
  const [live, setLive] = useState(false)
  const [tab, setTab] = useState<AdminTab>('review')
  const [ticketsVersion, setTicketsVersion] = useState(0)
  const [setupHidden, setSetupHidden] = useState(false)

  const loadStats = useCallback(async () => {
    try {
      const r = await fetch('/admin/stats', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setStats(await r.json())
    } catch { /* keep last */ }
  }, [token])

  const loadQueue = useCallback(async () => {
    try {
      const r = await fetch('/admin/tickets?status=escalated&limit=100', { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) setQueue((await r.json()).tickets ?? [])
    } finally {
      setQueueLoading(false)
    }
  }, [token])

  const loadPeople = useCallback(async () => {
    const h = { headers: { Authorization: `Bearer ${token}` } }
    try {
      const [m, i] = await Promise.all([fetch('/orgs/members', h), fetch('/admin/invites', h)])
      if (m.ok) setMembers((await m.json()).members)
      if (i.ok) setInvites((await i.json()).invites)
    } catch { /* keep last */ }
  }, [token])

  const refreshAll = useCallback(() => {
    loadStats(); loadQueue(); loadPeople(); setTicketsVersion((v) => v + 1)
  }, [loadStats, loadQueue, loadPeople])

  useEffect(() => {
    const h = { headers: { Authorization: `Bearer ${token}` } }
    async function load() {
      setLoading(true)
      const [orgR, membersR, invitesR, kbR] = await Promise.all([
        fetch('/orgs/me', h), fetch('/orgs/members', h), fetch('/admin/invites', h), fetch('/admin/kb', h),
      ])
      if (orgR.ok) {
        const o: OrgInfo = await orgR.json()
        setOrg(o)
        try { setSetupHidden(localStorage.getItem(dismissKey(o.id)) === '1') } catch { /* storage unavailable */ }
      }
      if (membersR.ok) setMembers((await membersR.json()).members)
      if (invitesR.ok) setInvites((await invitesR.json()).invites)
      if (kbR.ok) setKbCount((await kbR.json()).total ?? 0)
      await Promise.all([loadStats(), loadQueue()])
      setLoading(false)
    }
    load()

    // Live updates. EventSource can't send headers, so the JWT goes in the query string.
    const sse = new EventSource(`/admin/stream?token=${encodeURIComponent(token)}`)
    sse.onopen = () => setLive(true)
    sse.onerror = () => setLive(false)
    sse.onmessage = (e: MessageEvent) => {
      try {
        const ev = JSON.parse(e.data as string) as Partial<TicketRow>
        if (ev.status === 'escalated') onToast?.(`New ticket needs review${ev.user_email ? ` — ${ev.user_email}` : ''}`, 'info')
      } catch { /* ignore malformed events */ }
      setLive(true)
      refreshAll()
    }
    return () => sse.close()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="space-y-4 fade-in">
        <div className="h-10 w-48 animate-pulse rounded-lg bg-slate-200" />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl border border-slate-200 bg-white" />)}</div>
        <div className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white" />
      </div>
    )
  }

  const s = stats
  const autoRate = s && s.total > 0 ? `${Math.round((s.auto_resolved / s.total) * 100)}%` : '—'
  const steps = [
    { label: 'Upload your policies', hint: 'Answers come from your own documents — PDF, Word, Markdown or text.', done: (kbCount ?? 0) > 0, action: 'Upload a policy', onClick: () => setTab('kb') },
    { label: 'Invite your team', hint: 'Create a single-use invite code for each colleague.', done: members.length > 1 || invites.length > 0, action: 'Invite people', onClick: () => setTab('people') },
    { label: 'Try a test ticket', hint: 'See the agents resolve a request end to end.', done: (s?.total ?? 0) > 0, action: 'Submit a ticket', onClick: onNewTicket },
  ]
  const showSetup = !setupHidden && steps.some((st) => !st.done)

  const TABS: { key: AdminTab; label: string; count?: number; urgent?: boolean }[] = [
    { key: 'review', label: 'Needs review', count: queue.length, urgent: queue.length > 0 },
    { key: 'tickets', label: 'All tickets', count: s?.total },
    { key: 'kb', label: 'Knowledge base', count: kbCount ?? undefined },
    { key: 'people', label: 'People', count: members.length },
  ]

  return (
    <div className="space-y-6 fade-in">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">Overview</h2>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${live ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-slate-200 bg-slate-50 text-slate-500'}`}
              title={live ? 'Receiving ticket updates in real time' : 'Reconnecting to live updates…'}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${live ? 'animate-pulse bg-emerald-500' : 'bg-slate-400'}`} aria-hidden="true" />
              {live ? 'Live' : 'Connecting'}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">Your organisation’s helpdesk at a glance.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setTab('people')} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50">
            <Svg d={I.users} /> Invite people
          </button>
          <button onClick={() => setTab('kb')} className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700">
            <Svg d={I.upload} /> Upload policy
          </button>
        </div>
      </div>

      {showSetup && (
        <SetupChecklist
          steps={steps}
          onDismiss={() => {
            setSetupHidden(true)
            try { if (org) localStorage.setItem(dismissKey(org.id), '1') } catch { /* storage unavailable */ }
          }}
        />
      )}

      {s && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi label="Needs review" value={String(s.escalated)} icon={I.shield}
            tone={s.escalated > 0 ? 'rose' : 'emerald'} sub={s.escalated > 0 ? 'Waiting for your team' : 'All clear'}
            onClick={() => setTab('review')} />
          <Kpi label="Resolved automatically" value={autoRate} icon={I.bolt} tone="emerald"
            sub={s.total > 0 ? `${s.auto_resolved} of ${s.total} with no human effort` : 'No tickets yet'} />
          <Kpi label="Waiting on employees" value={String(s.awaiting_confirmation)} icon={I.clock} tone={s.awaiting_confirmation > 0 ? 'amber' : 'slate'}
            sub="Need the employee’s confirmation" />
          <Kpi label="Total tickets" value={String(s.total)} icon={I.ticket} tone="indigo"
            sub={s.failed > 0 ? `${s.failed} failed — check All tickets` : `${s.human_resolved} resolved by your team`}
            onClick={() => setTab('tickets')} />
        </div>
      )}

      <div>
        <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200" role="tablist" aria-label="Admin sections">
          {TABS.map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
              className={`-mb-px inline-flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3.5 py-2.5 text-sm font-semibold transition-colors ${
                tab === t.key ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              {t.label}
              {t.count !== undefined && (
                <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                  t.urgent ? 'bg-rose-100 text-rose-700' : tab === t.key ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'
                }`}>{t.count}</span>
              )}
            </button>
          ))}
        </div>

        {tab === 'review' && <ReviewQueue tickets={queue} loading={queueLoading} token={token} onToast={onToast} onChanged={refreshAll} />}
        {tab === 'tickets' && <AllTickets token={token} stats={stats} version={ticketsVersion} onToast={onToast} onChanged={refreshAll} />}
        {tab === 'kb' && <KnowledgeBasePanel token={token} onToast={onToast} onCountChange={setKbCount} />}
        {tab === 'people' && (
          <div className="space-y-5">
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white" aria-labelledby="members-h">
              <div className="border-b border-slate-100 px-5 py-3.5">
                <h3 id="members-h" className="text-sm font-bold text-slate-900">Members <span className="font-normal text-slate-400">({members.length})</span></h3>
              </div>
              <ul className="divide-y divide-slate-100">
                {members.map((m) => (
                  <MemberRow key={m.id} m={m} isSelf={m.id === currentUserId} token={token} onToast={onToast} onChanged={loadPeople} />
                ))}
              </ul>
            </section>
            <InvitesPanel token={token} invites={invites} onInvitesChange={setInvites} onToast={onToast} />
          </div>
        )}
      </div>
    </div>
  )
}
